# Đối tượng bất biến, constructor và Java record theo phiên bản hỗ trợ

Spring Data Elasticsearch không chỉ đọc JSON rồi gán từng field vào một object rỗng. Khi chuyển một Elasticsearch document thành entity Java, Spring Data phải xác định class nào cần tạo, constructor nào được dùng và giá trị của từng property được truyền vào đâu.

Với entity có setter, quá trình này khá trực tiếp: tạo object rồi điền các thuộc tính. Với entity bất biến, các field thường là final và không có setter; Spring Data cần tạo object bằng constructor có đủ dữ liệu. Java record cũng hoạt động theo hướng đó: các component được khai báo một lần và được khởi tạo qua canonical constructor.

Bài học này giải thích cách Spring Data Elasticsearch tạo entity, cách chọn constructor, cách thiết kế class bất biến, cách dùng record và những điểm cần kiểm tra theo phiên bản Java/Spring Data.

## 1. Từ Elasticsearch document đến Java object

Elasticsearch lưu document dưới dạng dữ liệu JSON trong index. Khi tìm kiếm hoặc đọc document, response có thể chứa:

- _source: dữ liệu document.
- _id: document ID do Elasticsearch quản lý.
- _index: index chứa document.
- _version hoặc sequence metadata tùy API và cấu hình.
- _score, sort values, highlight và các metadata tìm kiếm khác.

Spring Data Elasticsearch nhận response, dùng mapping metadata để chuyển dữ liệu thành entity Java. Ví dụ, document có _source như sau:

~~~json
{
  "name": "Mechanical Keyboard",
  "category": "accessories",
  "price": 89.5,
  "available": true
}
~~~

Entity tương ứng có thể là:

~~~java
@Document(indexName = "products")
public class Product {

    @Id
    private String id;

    @Field(type = FieldType.Text)
    private String name;

    @Field(type = FieldType.Keyword)
    private String category;

    @Field(type = FieldType.Double)
    private double price;

    private boolean available;

    // constructors, getters, setters
}
~~~

Khi gọi repository:

~~~java
Optional<Product> product = productRepository.findById("p-100");
~~~

Spring Data đọc document, chuyển từng giá trị sang kiểu Java phù hợp, tạo Product và trả object cho ứng dụng. @Id liên kết thuộc tính id với document ID; thuộc tính này không nhất thiết phải xuất hiện trong _source.

Quá trình tạo object là một phần của object mapping. Nó có liên hệ với ElasticsearchConverter, persistent entity metadata, constructor metadata và property accessor. Vì vậy, thiết kế constructor có ảnh hưởng trực tiếp đến việc Spring Data có thể đọc entity hay không.

## 2. Entity mutable và entity immutable

Một entity mutable cho phép thay đổi trạng thái sau khi được tạo. Thường class có constructor rỗng, field có thể được gán và setter được cung cấp:

~~~java
@Document(indexName = "customers")
public class Customer {

    @Id
    private String id;

    private String email;
    private String displayName;

    public Customer() {
    }

    public void setId(String id) {
        this.id = id;
    }

    public void setEmail(String email) {
        this.email = email;
    }

    public void setDisplayName(String displayName) {
        this.displayName = displayName;
    }

    public String getId() {
        return id;
    }

    public String getEmail() {
        return email;
    }

    public String getDisplayName() {
        return displayName;
    }
}
~~~

Spring Data có thể tạo Customer bằng constructor rỗng rồi điền các property thông qua property accessor. Đây là cách đơn giản, nhưng object có thể tồn tại trong trạng thái chưa hoàn chỉnh giữa lúc được tạo và lúc các field được gán.

Entity immutable không cho phép thay đổi trạng thái sau khi khởi tạo. Các property thường là final, không có setter và được truyền qua constructor:

~~~java
@Document(indexName = "customers")
public final class Customer {

    @Id
    private final String id;

    private final String email;
    private final String displayName;

    public Customer(String id, String email, String displayName) {
        this.id = id;
        this.email = email;
        this.displayName = displayName;
    }

    public String getId() {
        return id;
    }

    public String getEmail() {
        return email;
    }

    public String getDisplayName() {
        return displayName;
    }
}
~~~

Spring Data có thể tạo entity bằng constructor này và truyền các giá trị tương ứng. Sau khi constructor hoàn tất, object đã có trạng thái đầy đủ theo những property được truyền vào.

### Lợi ích của entity bất biến

- **Trạng thái ổn định:** object không bị thay đổi ngoài ý muốn sau khi tạo.
- **Dễ suy luận:** khi đọc một entity, có thể tin rằng các giá trị không bị một đoạn code khác thay đổi qua setter.
- **An toàn hơn khi chia sẻ:** nhiều thành phần có thể đọc cùng object mà ít phải lo về thay đổi trạng thái đồng thời.
- **Ràng buộc dữ liệu ngay lúc tạo:** constructor có thể kiểm tra điều kiện bắt buộc và từ chối object không hợp lệ.
- **Phù hợp với domain model:** những giá trị được xem là cố định sau khi tạo có thể được biểu diễn bằng field final.

Đổi lại, entity bất biến cần được thiết kế đúng với cơ chế object mapping. Nếu constructor không nhận đủ property, Spring Data có thể không khôi phục được trạng thái đầy đủ. Những property do Elasticsearch sinh ra, chẳng hạn ID, cũng cần được xử lý có chủ đích.

## 3. Spring Data chọn constructor như thế nào?

Spring Data sử dụng metadata để xác định constructor hoặc factory method phù hợp khi tạo một persistent entity. Các quy ước giúp framework tự chọn trong trường hợp đơn giản; annotation được dùng để làm rõ ý định khi có nhiều lựa chọn.

Các trường hợp thiết kế thường gặp:

| Cấu trúc class | Cách xử lý |
|---|---|
| Chỉ có một constructor | Spring Data có thể dùng constructor đó để tạo entity |
| Có nhiều constructor | Đánh dấu constructor muốn dùng bằng @PersistenceCreator |
| Có constructor rỗng và các constructor khác | Cần xác định rõ constructor phù hợp; không dựa vào thứ tự khai báo |
| Java record | Dùng canonical constructor của record |
| Có static factory method được đánh dấu phù hợp | Spring Data có thể dùng factory method theo quy tắc object mapping |

Quy tắc chi tiết có thể phụ thuộc phiên bản Spring Data. Khi class có nhiều constructor, cách rõ ràng nhất là đánh dấu constructor persistence bằng annotation.

### Dùng @PersistenceCreator

@PersistenceCreator thuộc Spring Data Commons:

~~~java
import org.springframework.data.annotation.PersistenceCreator;

@Document(indexName = "customers")
public class Customer {

    @Id
    private final String id;

    private final String email;
    private final String displayName;

    @PersistenceCreator
    public Customer(String id, String email, String displayName) {
        this.id = id;
        this.email = email;
        this.displayName = displayName;
    }

    public Customer(String email, String displayName) {
        this(null, email, displayName);
    }

    public String getId() {
        return id;
    }

    public String getEmail() {
        return email;
    }

    public String getDisplayName() {
        return displayName;
    }
}
~~~

Class có constructor đầy đủ để khôi phục entity và constructor ngắn để tạo object mới trong nghiệp vụ. Annotation chỉ rõ constructor mà Spring Data cần dùng khi đọc dữ liệu.

Nếu class chỉ có một constructor phù hợp, annotation có thể không cần thiết. Tuy nhiên, khi thêm constructor phục vụ nghiệp vụ, factory hoặc overload trong tương lai, annotation giúp tránh việc lựa chọn constructor thay đổi ngoài ý muốn.

### Constructor parameter phải ánh xạ được với property

Spring Data cần biết tham số constructor nào tương ứng với property nào. Tên tham số thường được dùng để liên kết với tên property trong entity.

Với class Java thông thường, nên bật tùy chọn biên dịch giữ lại tên tham số:

Gradle:

~~~groovy
tasks.withType(JavaCompile).configureEach {
    options.compilerArgs.add("-parameters")
}
~~~

Maven:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-compiler-plugin</artifactId>
    <configuration>
        <parameters>true</parameters>
    </configuration>
</plugin>
~~~

Nếu tên tham số không được giữ trong bytecode, framework có thể không suy ra được property tương ứng trong một số trường hợp. Khi đó, việc tạo entity có thể thất bại hoặc chọn sai cách ánh xạ.

Tên tham số constructor nên khớp với tên property Java. Nếu tên field trong Elasticsearch khác tên property Java, dùng mapping annotation để mô tả tên field lưu trữ; không đổi tên tham số constructor chỉ để bắt chước tên JSON nếu property Java vẫn giữ tên khác.

### Constructor và kiểm tra dữ liệu

Constructor là nơi phù hợp để đảm bảo các bất biến của object:

~~~java
public Customer(String id, String email, String displayName) {
    if (email == null || email.isBlank()) {
        throw new IllegalArgumentException("email is required");
    }

    this.id = id;
    this.email = email;
    this.displayName = displayName;
}
~~~

Tuy nhiên, dữ liệu cũ trong Elasticsearch có thể thiếu field hoặc chứa giá trị null. Nếu constructor mới thêm validation nghiêm ngặt, những document cũ không thỏa điều kiện có thể không đọc được nữa.

Khi thay đổi constructor của entity đang được lưu trữ, hãy xem xét:

- Field có thể bị thiếu trong document cũ không?
- Field mới có default value hợp lệ không?
- Primitive như int hoặc boolean có làm mất khác biệt giữa giá trị mặc định và dữ liệu thiếu không?
- Có cần migration dữ liệu trước khi triển khai phiên bản mới không?

Với field có thể vắng mặt, wrapper như Integer, Boolean hoặc Double giữ được trạng thái null để ứng dụng quyết định cách xử lý.

## 4. Property population sau khi constructor chạy

Constructor không phải lúc nào cũng nhận mọi property. Spring Data có thể cần điền các property còn lại sau khi tạo instance. Việc này được thực hiện thông qua cơ chế property accessor.

Với entity mutable, framework có thể sử dụng setter hoặc field access theo mapping metadata. Với entity immutable, property chưa được constructor khởi tạo cần một cơ chế tạo instance mới, chẳng hạn wither method.

Một wither method nhận giá trị mới và trả về một object mới:

~~~java
public Customer withDisplayName(String displayName) {
    return new Customer(id, email, displayName);
}
~~~

Vì method trả về object mới, class vẫn giữ được tính bất biến. Spring Data có thể sử dụng quy ước wither khi cần cập nhật một property không thể thay đổi trực tiếp.

### Property do Elasticsearch sinh ra

Một trường hợp quan trọng là ID được sinh khi lưu document. Ứng dụng có thể tạo entity với id = null, gửi entity lên Elasticsearch, rồi nhận ID do server tạo.

Entity immutable có thể cung cấp wither cho ID:

~~~java
@Document(indexName = "customers")
public final class Customer {

    @Id
    private final String id;

    private final String email;
    private final String displayName;

    @PersistenceCreator
    public Customer(String id, String email, String displayName) {
        this.id = id;
        this.email = email;
        this.displayName = displayName;
    }

    public Customer withId(String id) {
        return new Customer(id, email, displayName);
    }

    public String getId() {
        return id;
    }

    public String getEmail() {
        return email;
    }

    public String getDisplayName() {
        return displayName;
    }
}
~~~

Sau khi lưu, hãy sử dụng object được trả về từ repository:

~~~java
Customer input = new Customer(null, "dev@example.com", "Developer");

Customer saved = customerRepository.save(input);

System.out.println(saved.getId());
~~~

Không nên giả định object đầu vào luôn được mutate tại chỗ để nhận ID. Với entity immutable, instance được trả về có thể là instance mới chứa ID vừa được gán.

### Không bỏ quên property ngoài constructor

Nếu entity có một property persistent nhưng không được constructor nhận vào, Spring Data phải tìm cách điền property đó sau khi tạo instance. Với field mutable, việc này thường đơn giản. Với field final và không có setter hoặc wither phù hợp, framework không thể cập nhật trạng thái theo cách thông thường.

Do đó, khi thiết kế entity immutable, hãy đưa các property persistent cần khôi phục vào constructor được chọn. Nếu property có thể thay đổi theo vòng đời, hãy cân nhắc wither trả instance mới hoặc điều chỉnh mô hình dữ liệu.

## 5. Java record là gì?

Java record là một dạng class dành cho dữ liệu có cấu trúc cố định. Record tự cung cấp:

- Các component được khai báo trong phần header.
- Field tương ứng và accessor cùng tên component.
- Canonical constructor để khởi tạo tất cả component.
- equals, hashCode và toString dựa trên component.

Ví dụ:

~~~java
public record CustomerRecord(
    String id,
    String email,
    String displayName
) {}
~~~

Record là immutable ở mức component: các field component là final và không thể gán lại sau khi constructor hoàn tất. Tuy vậy, nếu một component tham chiếu đến collection hoặc object mutable, bản thân object được tham chiếu vẫn có thể thay đổi. Record không tự động tạo deep immutable object graph.

Record phù hợp với entity hoặc document có cấu trúc dữ liệu rõ ràng, ít cần mutation sau khi đọc. Nó cũng giúp giảm boilerplate getter, constructor, equals và hashCode.

### Dùng record làm Elasticsearch entity

Spring Data Elasticsearch có thể ánh xạ record khi phiên bản Spring Data đang dùng hỗ trợ record mapping:

~~~java
@Document(indexName = "orders")
public record Order(
    @Id String id,
    @Field(type = FieldType.Keyword) String orderNumber,
    @Field(type = FieldType.Double) Double total,
    boolean paid
) {}
~~~

Khi đọc document, Spring Data sử dụng canonical constructor của Order và truyền giá trị cho các component tương ứng. Annotation mapping trên component mô tả cách Spring Data liên kết record với index và field.

Ứng dụng có thể dùng repository như với entity class thông thường:

~~~java
public interface OrderRepository
        extends ElasticsearchRepository<Order, String> {
}
~~~

Ví dụ service:

~~~java
Order order = new Order(
    null,
    "ORD-2026-001",
    129.90,
    false
);

Order saved = orderRepository.save(order);
~~~

Nếu Elasticsearch sinh ID, cần đảm bảo phiên bản Spring Data đang dùng có thể gán ID cho entity record theo cơ chế mapping mà dự án sử dụng. Có thể cung cấp wither method trả về record mới để biểu diễn việc cập nhật ID:

~~~java
public record Order(
    @Id String id,
    String orderNumber,
    Double total,
    boolean paid
) {
    public Order withId(String id) {
        return new Order(id, orderNumber, total, paid);
    }
}
~~~

Record không cho phép thay đổi component trực tiếp, nhưng vẫn có thể khai báo method tạo một record mới với một component được thay đổi.

## 6. Canonical constructor và compact constructor

Mỗi record có canonical constructor tương ứng với toàn bộ component. Nếu không tự khai báo, Java tự sinh constructor này.

Có thể viết compact constructor để kiểm tra hoặc chuẩn hóa dữ liệu:

~~~java
public record ProductSnapshot(
    String sku,
    String name,
    Double price
) {
    public ProductSnapshot {
        if (sku == null || sku.isBlank()) {
            throw new IllegalArgumentException("sku is required");
        }

        if (price != null && price < 0) {
            throw new IllegalArgumentException("price must be non-negative");
        }
    }
}
~~~

Compact constructor không cần viết lại danh sách tham số hoặc các phép gán field. Java thực hiện gán component sau khi phần thân compact constructor hoàn tất.

Spring Data vẫn cần tạo record thông qua canonical constructor. Vì vậy, validation trong compact constructor cũng được áp dụng khi dữ liệu được đọc từ Elasticsearch.

Điều này có hai mặt:

- Dữ liệu hợp lệ luôn đi qua cùng một quy tắc khởi tạo.
- Document cũ hoặc document không đầy đủ có thể khiến việc đọc entity ném exception.

Trước khi thêm validation mới vào record đang đại diện cho dữ liệu đã lưu, cần đánh giá dữ liệu lịch sử và kế hoạch migration.

## 7. Phiên bản Java và Spring Data hỗ trợ record

Record là tính năng ngôn ngữ Java được hoàn thiện trong Java 16. Các bản Java 14 và 15 từng cung cấp record dưới dạng preview; không nên dùng preview feature cho ứng dụng thông thường nếu không có lý do đặc biệt.

Tuy nhiên, Java compiler hỗ trợ record không đồng nghĩa mọi phiên bản Spring Data đều có thể ánh xạ record. Cần đồng thời đáp ứng hai điều kiện:

1. JVM và compiler của dự án hỗ trợ Java record.
2. Phiên bản Spring Data Commons/Spring Data Elasticsearch đang dùng hỗ trợ record object mapping.

Trong các dự án Spring Boot hiện đại dùng Java 17 trở lên và Spring Data tương ứng, record là lựa chọn thực tế cho document immutable. Với dự án cũ, hãy kiểm tra reference documentation và release notes của đúng release train. Không chỉ nâng JDK rồi giả định mapping record đã được hỗ trợ.

### Bảng định hướng theo môi trường

| Môi trường | Định hướng |
|---|---|
| Java thấp hơn 16 | Dùng class thông thường; record không phải tính năng Java chuẩn của runtime này |
| Java 16+ nhưng Spring Data cũ | Xác nhận record mapping được hỗ trợ trước khi dùng |
| Spring Boot 3.x với Java 17+ | Record thường phù hợp; vẫn cần giữ dependency Spring Data do release train quản lý |
| Dự án đã override Spring Data/client | Kiểm tra dependency tree và tài liệu phiên bản thực tế trước khi dựa vào hỗ trợ record |

Spring Boot quản lý một bộ dependency đã được chọn để làm việc cùng nhau. Nếu override Spring Data Elasticsearch hoặc Spring Data Commons, cần xác nhận phiên bản record mapping thực tế đang được nạp.

### Nếu phiên bản cũ chưa hỗ trợ record mapping

Có thể dùng immutable class với constructor được đánh dấu @PersistenceCreator:

~~~java
@Document(indexName = "orders")
public final class Order {

    @Id
    private final String id;

    private final String orderNumber;
    private final Double total;

    @PersistenceCreator
    public Order(String id, String orderNumber, Double total) {
        this.id = id;
        this.orderNumber = orderNumber;
        this.total = total;
    }

    public String getId() {
        return id;
    }

    public String getOrderNumber() {
        return orderNumber;
    }

    public Double getTotal() {
        return total;
    }
}
~~~

Cách này vẫn cung cấp constructor binding và trạng thái immutable mà không phụ thuộc vào record support.

## 8. Record, immutable class và mutable class: chọn loại nào?

Không có một loại entity phù hợp với mọi trường hợp. Hãy chọn dựa trên vòng đời dữ liệu và khả năng của phiên bản Spring Data.

| Tiêu chí | Mutable class | Immutable class | Java record |
|---|---|---|---|
| Thay đổi property sau khi tạo | Có | Không, tạo instance mới | Không, tạo record mới |
| Constructor rỗng | Thường có | Không cần nếu constructor binding | Không có theo cách thông thường |
| Boilerplate | Nhiều hơn | Có thể nhiều getter/constructor | Ít |
| Constructor mapping | Có thể dùng | Là cơ chế chính | Canonical constructor |
| Generated ID | Có thể gán qua setter/field | Có thể cần wither | Có thể cần wither trả record mới |
| Validation khi khởi tạo | Có thể có | Tự nhiên trong constructor | Có thể dùng compact constructor |
| Phù hợp dữ liệu cấu trúc cố định | Có | Có | Rất phù hợp |

### Khi nào chọn mutable class?

Chọn mutable class nếu domain model cần cập nhật nhiều field trong vòng đời, code hiện tại dựa vào setter hoặc thư viện tích hợp yêu cầu object mutable. Đây cũng là lựa chọn dễ tiếp cận với dự án legacy.

### Khi nào chọn immutable class?

Chọn immutable class khi muốn kiểm soát trạng thái chặt chẽ, constructor có thể đảm bảo các invariant và entity có nhiều hành vi nghiệp vụ. Immutable class cũng phù hợp khi cần tương thích với Java cũ chưa có record.

### Khi nào chọn record?

Chọn record cho document chủ yếu biểu diễn dữ liệu, có cấu trúc ổn định và không cần hành vi mutation. Record giúp code ngắn, accessor rõ ràng và equality dựa trên component.

Nếu entity chứa nhiều hành vi domain, cần kế thừa class, cần proxy đặc biệt hoặc có vòng đời thay đổi phức tạp, class thông thường có thể phù hợp hơn.

## 9. Các lỗi thường gặp khi ánh xạ constructor và record

| Dấu hiệu | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| Không tạo được entity | Không tìm được constructor phù hợp | Kiểm tra constructor và @PersistenceCreator |
| Constructor nhận sai hoặc thiếu giá trị | Không suy ra được tên tham số | Kiểm tra -parameters và tên property |
| Entity immutable có field null | Property không được truyền qua constructor và không có cơ chế cập nhật | Đưa property vào constructor hoặc cung cấp wither |
| Record không được ánh xạ | Spring Data release chưa hỗ trợ record mapping | Kiểm tra phiên bản Spring Data |
| Đọc document cũ gây exception | Constructor/compact constructor mới yêu cầu field bắt buộc nhưng dữ liệu cũ thiếu | Kiểm tra dữ liệu lịch sử và migration |
| ID null sau save | Entity immutable không được cập nhật theo cách ứng dụng mong đợi | Kiểm tra wither và dùng object trả về từ save |
| Giá trị số thành 0 dù field thiếu | Dùng primitive không phân biệt null với giá trị mặc định | Cân nhắc wrapper type |
| Thêm constructor làm thay đổi mapping | Framework chọn constructor khác hoặc có nhiều candidate | Đánh dấu constructor persistence |

### Lỗi thiếu tên tham số constructor

Nếu Spring Data không thể liên kết tham số constructor với property, hãy kiểm tra bytecode và cấu hình compiler. Với Gradle, xác nhận -parameters được áp dụng cho module chứa entity. Với Maven, kiểm tra parameters trong compiler plugin.

Cũng cần đảm bảo tên tham số khớp với tên property Java và constructor được chọn đúng.

### Lỗi record trên phiên bản cũ

Nếu record compile thành công nhưng Spring Data không thể tạo entity, xác định phiên bản thực tế của Spring Data Commons và Spring Data Elasticsearch. Đối chiếu release notes để xác nhận record mapping. Nếu phiên bản không hỗ trợ, dùng immutable class với constructor binding hoặc nâng cấp cả bộ dependency theo release train tương thích.

### Lỗi ID của immutable entity

Khi ID do Elasticsearch tạo, object đầu vào ban đầu có thể vẫn giữ id = null. Hãy kiểm tra object trả về từ save và cách Spring Data cập nhật property immutable. Nếu cần, định nghĩa wither có tên đúng quy ước và trả về instance mới.

## 10. Ví dụ hoàn chỉnh: repository với immutable entity

Ví dụ dưới đây minh họa một entity bất biến có ID, field được ánh xạ rõ ràng và wither cho ID:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.PersistenceCreator;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "products")
public final class Product {

    @Id
    private final String id;

    @Field(type = FieldType.Keyword)
    private final String sku;

    @Field(type = FieldType.Text)
    private final String name;

    @Field(type = FieldType.Double)
    private final Double price;

    @PersistenceCreator
    public Product(
            String id,
            String sku,
            String name,
            Double price) {
        this.id = id;
        this.sku = sku;
        this.name = name;
        this.price = price;
    }

    public Product withId(String id) {
        return new Product(id, sku, name, price);
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
~~~

Repository:

~~~java
public interface ProductRepository
        extends ElasticsearchRepository<Product, String> {
}
~~~

Service:

~~~java
@Service
public class ProductService {

    private final ProductRepository repository;

    public ProductService(ProductRepository repository) {
        this.repository = repository;
    }

    public Product create(
            String sku,
            String name,
            Double price) {

        Product input = new Product(null, sku, name, price);

        // Dùng instance trả về vì ID có thể được Elasticsearch sinh.
        return repository.save(input);
    }

    public Optional<Product> find(String id) {
        return repository.findById(id);
    }
}
~~~

Trong ví dụ này:

1. @Document xác định index.
2. @Id liên kết ID Java với document ID.
3. @Field mô tả kiểu dữ liệu trên index.
4. @PersistenceCreator xác định constructor dùng để khôi phục entity.
5. Các field final và không có setter giữ trạng thái bất biến.
6. withId cung cấp cách tạo instance mới khi ID cần được cập nhật.
7. Service trả về kết quả của save để caller nhận entity sau khi lưu.

Ví dụ thể hiện mô hình constructor binding. Khi áp dụng, cần xác nhận phiên bản Spring Data Elasticsearch và cách cấu hình ID generation trong dự án.

## 11. Lưu ý khi dùng Lombok và code generation

Lombok có thể giảm boilerplate nhưng cũng ảnh hưởng đến constructor mà Spring Data nhìn thấy.

Ví dụ, kết hợp @NoArgsConstructor, @AllArgsConstructor và @RequiredArgsConstructor có thể tạo nhiều constructor. Nếu không xác định rõ constructor persistence, Spring Data có thể không chọn constructor mà developer mong muốn.

Một số nguyên tắc:

- Kiểm tra constructor thực tế được Lombok sinh ra.
- Đánh dấu constructor persistence bằng @PersistenceCreator khi có nhiều constructor.
- Đảm bảo tham số constructor có tên phù hợp với property.
- Không thêm setter cho field immutable chỉ để tránh xử lý constructor nếu domain cần giữ tính bất biến.
- Nếu dùng builder, nhớ rằng builder không tự động thay thế cơ chế constructor mapping của Spring Data.

Có thể dùng builder để tạo entity trong code nghiệp vụ, nhưng Spring Data vẫn cần constructor hoặc factory method mà object mapping có thể nhận diện.

## 12. Hiệu năng của constructor-based mapping

Spring Data sử dụng metadata và cơ chế tạo object/property accessor để giảm chi phí reflection trong các trường hợp hỗ trợ. Tuy nhiên, khả năng tối ưu phụ thuộc cấu trúc class, visibility, runtime và phiên bản framework.

Để mapping hoạt động hiệu quả:

- Dùng constructor rõ ràng, không có logic nặng hoặc truy cập mạng.
- Giữ entity ở dạng top-level hoặc static nested class.
- Tránh constructor private nếu framework cần truy cập mà không có cơ chế phù hợp.
- Bật lưu tên tham số khi biên dịch class Java thông thường.
- Dùng constructor binding cho entity immutable để tránh nhiều bước gán property.
- Không tạo validation tốn kém cho từng hit nếu có thể kiểm tra dữ liệu ở một tầng phù hợp hơn.

Không nên thay đổi thiết kế domain chỉ vì một giả định hiệu năng. Nếu mapping là điểm nghẽn, đo thời gian và profiling trước khi tối ưu.

## 13. Quy trình kiểm tra entity mapping

Khi một entity immutable hoặc record không đọc được, hãy kiểm tra theo thứ tự:

1. Xác nhận phiên bản Java runtime và compiler.
2. Xác nhận phiên bản Spring Data Elasticsearch/Spring Data Commons thực tế trong runtime.
3. Kiểm tra entity có @Document và property có annotation mapping phù hợp không.
4. Kiểm tra constructor được chọn; nếu có nhiều constructor, dùng @PersistenceCreator.
5. Kiểm tra tên tham số constructor và tùy chọn compiler -parameters.
6. Đảm bảo mọi property persistent cần khôi phục đều được constructor nhận hoặc có cơ chế property population phù hợp.
7. Với record, xác nhận canonical constructor và record mapping được hỗ trợ.
8. Kiểm tra document thực tế, nhất là field bị thiếu hoặc có kiểu dữ liệu khác.
9. Kiểm tra ID được gán thế nào và caller có dùng instance trả về từ save không.

Khi cần phân biệt lỗi mapping với lỗi truy vấn, thử đọc một document có cấu trúc đơn giản đã biết. Nếu Elasticsearch trả hit nhưng không tạo được entity, tập trung vào constructor, property metadata và converter thay vì thay đổi Query DSL.

## 14. Nguyên tắc thiết kế

Entity mutable, immutable class và record đều có chỗ đứng trong Spring Data Elasticsearch. Điều quan trọng là lựa chọn phải phù hợp với vòng đời dữ liệu và phiên bản framework.

- Dùng constructor binding để tạo entity immutable với trạng thái hoàn chỉnh.
- Dùng @PersistenceCreator để xác định constructor khi có nhiều lựa chọn.
- Giữ tên tham số constructor tương ứng với property Java.
- Dùng -parameters cho class Java thông thường để Spring Data có thể khám phá tên tham số.
- Dùng wither khi một property immutable cần được cập nhật bằng instance mới, đặc biệt với ID được sinh.
- Dùng canonical constructor và component mapping khi phiên bản Spring Data hỗ trợ Java record.
- Kiểm tra dữ liệu lịch sử trước khi thêm validation bắt buộc vào constructor.
- Giữ dependency trong release train tương thích, không chỉ dựa vào việc code compile được.

Khi hiểu cách Spring Data lựa chọn constructor và khôi phục property, ta có thể thiết kế entity bất biến hoặc record mà vẫn tương thích với quy trình đọc, lưu và tìm kiếm document trong Elasticsearch.

