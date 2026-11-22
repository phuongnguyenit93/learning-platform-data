# Tên tham số constructor và tùy chọn biên dịch `-parameters`

Spring Data JDBC phải tạo lại đối tượng Java từ dữ liệu đọc được trong database. Khi một repository đọc một hàng trong bảng, framework lấy các giá trị cột, chuyển đổi chúng sang kiểu Java thích hợp, rồi khởi tạo aggregate hoặc các đối tượng thành phần của aggregate. Với entity bất biến, constructor thường là nơi nhận các giá trị đó.

Để gán đúng giá trị cho đúng thuộc tính, Spring Data cần biết **tên tham số của constructor**. Java source có thể viết:

~~~java
public Customer(Long id, String firstName, String email) {
    // ...
}
~~~

nhưng tên tham số có thể không còn hiện diện trong bytecode nếu mã được biên dịch mà không bật tùy chọn `-parameters`. Khi đó, framework có thể chỉ nhìn thấy các tên tổng quát như `arg0`, `arg1`, `arg2`, khiến việc ghép tham số constructor với thuộc tính persistent không thực hiện được như mong đợi.

Bài học này giải thích vai trò của tên tham số, cách bật `-parameters`, cách dùng `@ConstructorProperties` và `@PersistenceCreator`, cùng cách kiểm tra lỗi khởi tạo đối tượng trong Spring Data Relational JDBC.

## 1. Vì sao Spring Data JDBC cần tên tham số?

Spring Data JDBC ánh xạ dữ liệu theo **metadata của entity**. Metadata mô tả tên thuộc tính Java, tên cột SQL, kiểu dữ liệu, định danh và chiến lược tạo đối tượng. Khi materialize một hàng, framework phải xác định giá trị nào được truyền vào tham số nào của constructor.

Ví dụ bảng:

~~~sql
CREATE TABLE customers (
    id BIGINT PRIMARY KEY,
    first_name VARCHAR(100) NOT NULL,
    email VARCHAR(320) NOT NULL
);
~~~

Entity:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Column;
import org.springframework.data.relational.core.mapping.Table;

@Table("customers")
public class Customer {
    @Id
    private final Long id;

    @Column("first_name")
    private final String firstName;

    private final String email;

    public Customer(Long id, String firstName, String email) {
        this.id = id;
        this.firstName = firstName;
        this.email = email;
    }

    public Long getId() { return id; }
    public String getFirstName() { return firstName; }
    public String getEmail() { return email; }
}
~~~

Khi đọc một hàng, framework cần tạo tương đương với:

~~~java
new Customer(10L, "Lan", "lan@example.test");
~~~

Spring Data phải biết:

- Giá trị cột `id` đi vào thuộc tính `id`.
- Giá trị cột `first_name` được ánh xạ thành thuộc tính Java `firstName`, rồi truyền vào tham số constructor `firstName`.
- Giá trị cột `email` đi vào tham số `email`.

Điểm quan trọng là **tên tham số constructor được ghép với tên thuộc tính Java**, không phải mặc nhiên với tên cột vật lý trong database. Trong ví dụ, tham số tên `firstName` vẫn đúng dù cột SQL tên `first_name`, bởi `@Column("first_name")` đã khai báo quan hệ giữa hai tên đó.

~~~mermaid
flowchart TD
    A["Hàng SQL<br/>id, first_name, email"] --> B["Mapping metadata"]
    B --> C["Thuộc tính Java<br/>id, firstName, email"]
    C --> D["Tên tham số constructor"]
    D --> E["new Customer(id, firstName, email)"]
    E --> F["Aggregate được khởi tạo"]
~~~

Nếu tên tham số không thể được xác định hoặc không khớp với thuộc tính cần nạp, Spring Data có thể không tìm được cách cung cấp giá trị cho constructor. Đây là lý do việc biên dịch có lưu tên tham số là một phần quan trọng của object mapping.

## 2. Tên tham số trong Java source và trong bytecode

Trong mã nguồn Java, tên tham số luôn hiển thị:

~~~java
public Customer(Long id, String firstName, String email) {
    // Các tên id, firstName, email có mặt trong source.
}
~~~

Nhưng bytecode Java không nhất thiết lưu các tên này dưới dạng metadata reflection có thể truy cập. Nếu biên dịch không bật `-parameters`, lời gọi reflection có thể trả về tên dạng `arg0`, `arg1` và `arg2`; phương thức `Parameter.isNamePresent()` trả về `false`.

Ví dụ kiểm tra:

~~~java
import java.lang.reflect.Constructor;
import java.lang.reflect.Parameter;

public class ConstructorParameterInspector {
    public static void main(String[] args) {
        for (Constructor<?> constructor
                : Customer.class.getDeclaredConstructors()) {
            System.out.println(constructor);

            for (Parameter parameter : constructor.getParameters()) {
                System.out.printf(
                    "name=%s, namePresent=%s, type=%s%n",
                    parameter.getName(),
                    parameter.isNamePresent(),
                    parameter.getType().getName()
                );
            }
        }
    }
}
~~~

Khi biên dịch có lưu tên tham số, kết quả có thể cho thấy:

~~~text
name=id, namePresent=true, type=java.lang.Long
name=firstName, namePresent=true, type=java.lang.String
name=email, namePresent=true, type=java.lang.String
~~~

Khi không lưu tên, kết quả thường có dạng:

~~~text
name=arg0, namePresent=false, type=java.lang.Long
name=arg1, namePresent=false, type=java.lang.String
name=arg2, namePresent=false, type=java.lang.String
~~~

Tên `arg0` không cho biết nó đại diện cho thuộc tính `id`, `customerId` hay `accountId`. Kiểu dữ liệu cũng không đủ để suy luận đáng tin cậy: một constructor có thể nhận nhiều tham số cùng kiểu `String` hoặc `Long`.

**Không nên dựa vào thứ tự tham số để đoán thuộc tính.** Khi có nhiều tham số cùng kiểu, việc đoán theo vị trí rất dễ gán sai dữ liệu mà không phát hiện ngay.

## 3. `-parameters` làm gì?

`-parameters` là tùy chọn của **Java compiler**. Nó yêu cầu trình biên dịch ghi metadata tên tham số vào file `.class`, để reflection và các framework có thể đọc được tên khai báo trong source.

Ví dụ:

~~~bash
javac -parameters Customer.java
~~~

Đây là tùy chọn lúc **biên dịch**, không phải tham số chạy JVM. Các lệnh sau không có ý nghĩa tương đương:

~~~bash
java -parameters com.example.CustomerApplication
~~~

~~~bash
java -Dparameters=true com.example.CustomerApplication
~~~

`-g` hoặc việc bật debug symbols cũng không thay thế `-parameters`. Debug information và metadata tên tham số phục vụ các mục đích khác nhau. Không nên giả định tên biến cục bộ trong bảng debug có thể thay thế metadata constructor parameter mà Spring Data cần.

### Điều kiện quan trọng

Tùy chọn phải được áp dụng khi biên dịch **class chứa constructor entity**. Nếu entity nằm trong một thư viện JAR đã được biên dịch không có tên tham số, việc bật `-parameters` ở ứng dụng tiêu thụ thư viện không thể khôi phục những tên đã mất trong bytecode của thư viện đó. Cần biên dịch lại module/thư viện sở hữu entity hoặc dùng metadata tường minh như `@ConstructorProperties`.

## 4. Bật `-parameters` với Gradle

Trong dự án dùng Gradle Groovy DSL, có thể cấu hình các task `JavaCompile`:

~~~groovy
tasks.withType(JavaCompile).configureEach {
    options.compilerArgs.add("-parameters")
}
~~~

Đặt cấu hình ở build script của module chứa entity, hoặc ở build convention dùng chung nếu toàn bộ module Java cần metadata tên tham số.

Nếu dùng Kotlin DSL (`build.gradle.kts`):

~~~kotlin
tasks.withType<JavaCompile>().configureEach {
    options.compilerArgs.add("-parameters")
}
~~~

Nếu dự án quản lý compiler options trong convention plugin, nên đưa tùy chọn vào đúng nơi chịu trách nhiệm cấu hình Java compilation. Tránh khai báo rải rác ở nhiều build file khiến một module có `-parameters` còn module khác thì không.

### Áp dụng theo phạm vi module

Giả sử cấu trúc:

~~~text
java-learning/
├── module/
│   └── shop/
│       ├── build.gradle
│       └── src/main/java/
│           └── com/example/shop/Customer.java
└── build.gradle
~~~

Nếu chỉ `shop` sở hữu entity cần constructor mapping, có thể cấu hình tại `module/shop/build.gradle`. Nếu repository có convention chung cho các module Java, cấu hình ở convention plugin sẽ nhất quán hơn.

Một điểm cần kiểm tra là module tạo ra JAR entity. Ví dụ module `domain-model` biên dịch `Customer.class`, còn module `shop-app` chỉ phụ thuộc JAR đó. Tùy chọn cần có ở **domain-model**, không chỉ ở `shop-app`.

### Biên dịch lại sau khi thay đổi

Sau khi thêm tùy chọn, cần để Gradle biên dịch lại các class liên quan. Nếu đang kiểm tra một artifact cũ trong thư mục build hoặc JAR cũ, kết quả reflection vẫn có thể không có tên tham số.

Có thể chạy task biên dịch phù hợp trong môi trường phát triển:

~~~bash
./gradlew :shop:clean :shop:compileJava
~~~

Tên project path phụ thuộc cấu trúc Gradle thực tế. Với dự án nhiều module, hãy dùng đúng project path của module chứa entity.

## 5. Bật `-parameters` với Maven

Với Maven, cấu hình Java compiler plugin:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-compiler-plugin</artifactId>
    <configuration>
        <parameters>true</parameters>
    </configuration>
</plugin>
~~~

Nếu dự án dùng thuộc tính quản lý phiên bản Java, giữ cấu hình source/release hiện có và bổ sung `parameters` vào plugin. Ví dụ này chỉ bật lưu tên tham số; nó không thay thế việc chọn đúng JDK, release hoặc cấu hình annotation processor.

Với dự án sử dụng một thư viện nội bộ, hãy bảo đảm chính module Maven tạo ra entity được biên dịch với cấu hình này.

## 6. `-parameters` và `@ConstructorProperties`

Có hai cách phổ biến để Spring Data biết tên tham số constructor:

- Lưu tên tham số vào bytecode bằng tùy chọn `-parameters`.
- Khai báo tên tường minh trên constructor bằng annotation `java.beans.ConstructorProperties`.

Ví dụ:

~~~java
import java.beans.ConstructorProperties;

public class Customer {
    private final Long id;
    private final String firstName;
    private final String email;

    @ConstructorProperties({"id", "firstName", "email"})
    public Customer(Long id, String firstName, String email) {
        this.id = id;
        this.firstName = firstName;
        this.email = email;
    }
}
~~~

Mảng chuỗi trong `@ConstructorProperties` phải có số phần tử và thứ tự tương ứng với danh sách tham số constructor. Mỗi chuỗi là **tên thuộc tính Java** mà tham số tương ứng đại diện.

| Tham số constructor | Giá trị annotation cùng vị trí |
| --- | --- |
| Tham số thứ nhất `Long id` | `"id"` |
| Tham số thứ hai `String firstName` | `"firstName"` |
| Tham số thứ ba `String email` | `"email"` |

Nếu đảo thứ tự annotation:

~~~java
@ConstructorProperties({"email", "firstName", "id"})
public Customer(Long id, String firstName, String email) {
    // ...
}
~~~

metadata đã khai báo sai: tham số đầu tiên kiểu `Long` lại được nói là thuộc tính `email`. Đây là lỗi mapping, không phải cách đổi thứ tự cột trong SQL.

### Khi nào dùng cách nào?

| Tình huống | Lựa chọn phù hợp |
| --- | --- |
| Ứng dụng Gradle/Maven do bạn kiểm soát | Bật `-parameters` trên module biên dịch entity |
| Thư viện cần metadata constructor rõ ràng | Có thể dùng `@ConstructorProperties` trên constructor |
| Không thể thay đổi cách biên dịch dependency | Dùng annotation metadata nếu có thể chỉnh sửa và biên dịch lại class; nếu không, xem xét một constructor persistence phù hợp khác |
| Nhiều module cần cùng quy ước | Cấu hình compiler option trong convention/build plugin dùng chung |
| Java record | Dùng canonical constructor và tên record component; vẫn cần kiểm tra cách build/metadata theo môi trường |

Hai cách này bổ sung khả năng khám phá tên tham số. Không cần khai báo cả hai chỉ để lặp lại cùng thông tin nếu compiler đã lưu tên đúng. Nếu dùng cả hai, hãy bảo đảm metadata nhất quán.

## 7. `@PersistenceCreator` chọn constructor nào?

Một entity có thể có nhiều constructor: constructor đầy đủ cho persistence, constructor tiện dụng cho nghiệp vụ, constructor không tham số hoặc constructor phục vụ test. Spring Data cần biết constructor nào được dùng để khôi phục entity.

Annotation `@PersistenceCreator` của Spring Data đánh dấu constructor hoặc factory method dùng cho persistence khi cần lựa chọn tường minh.

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.PersistenceCreator;
import org.springframework.data.relational.core.mapping.Table;

@Table("customers")
public class Customer {
    @Id
    private final Long id;
    private final String firstName;
    private final String email;

    @PersistenceCreator
    public Customer(Long id, String firstName, String email) {
        this.id = id;
        this.firstName = firstName;
        this.email = email;
    }

    public Customer(String firstName, String email) {
        this(null, firstName, email);
    }
}
~~~

Constructor ba tham số được chọn cho persistence; constructor hai tham số có thể phục vụ nghiệp vụ tạo khách hàng mới.

**`@PersistenceCreator` không thay thế `-parameters`.** Nó giải quyết câu hỏi *dùng constructor nào*, còn tên tham số của constructor đó vẫn phải được khám phá qua metadata phù hợp, ví dụ `-parameters` hoặc `@ConstructorProperties`.

### Quy tắc lựa chọn constructor ở mức khái quát

Spring Data có các quy tắc object creation dựa trên số lượng constructor, constructor được đánh dấu và loại class. Thông thường:

- Nếu chỉ có một constructor phù hợp, framework có thể dùng constructor đó.
- Nếu có nhiều constructor, đánh dấu constructor persistence bằng `@PersistenceCreator` để tránh lựa chọn mơ hồ.
- Nếu dùng static factory method cho persistence, có thể đánh dấu factory method phù hợp.
- Với Java record, canonical constructor là constructor tự nhiên để tạo record từ các component.

Khi class có nhiều constructor và một constructor không tham số, đừng dựa vào phỏng đoán rằng constructor đầy đủ luôn được chọn. Hãy xác định rõ persistence constructor theo quy tắc phiên bản Spring Data đang dùng.

## 8. Tên tham số phải khớp tên thuộc tính Java, không phải tên cột

Đây là điểm dễ nhầm khi kết hợp `@Column` với constructor mapping.

~~~java
@Table("customers")
public class Customer {
    @Id
    private final Long id;

    @Column("first_name")
    private final String givenName;

    private final String email;

    public Customer(Long id, String givenName, String email) {
        this.id = id;
        this.givenName = givenName;
        this.email = email;
    }
}
~~~

Bảng ánh xạ:

| Tầng | Tên |
| --- | --- |
| Cột database | `first_name` |
| Annotation | `@Column("first_name")` |
| Thuộc tính Java | `givenName` |
| Tham số constructor | `givenName` |

Đây là mapping nhất quán. Framework dùng metadata cột để đọc `first_name` vào property `givenName`, sau đó dùng tên property tương ứng để tìm giá trị cho tham số constructor `givenName`.

Nếu viết constructor như sau:

~~~java
public Customer(Long id, String firstName, String email) {
    this.id = id;
    this.givenName = firstName;
    this.email = email;
}
~~~

thì tham số `firstName` không còn cùng tên với property `givenName`. Chỉ đổi tên biến bên trong constructor không làm Spring Data tự biết `firstName` đại diện cho `givenName`. Hãy đổi tên tham số thành `givenName`, hoặc cung cấp metadata constructor tường minh phù hợp.

**Không đặt tên tham số theo cột SQL** nếu tên property Java khác. Ví dụ, tham số `first_name` không phải cách thay thế cho `givenName`; dấu gạch dưới trong tên cột đã được xử lý bởi mapping metadata.

## 9. Entity bất biến và constructor mapping

Spring Data JDBC hỗ trợ mô hình entity bất biến. Các thuộc tính có thể là `final`, không cần setter công khai; framework tạo instance qua constructor và có thể dùng cơ chế property population khi cần thiết.

Ví dụ:

~~~java
@Table("products")
public class Product {
    @Id
    private final Long id;

    @Column("product_name")
    private final String name;

    private final int quantity;

    @PersistenceCreator
    public Product(Long id, String name, int quantity) {
        this.id = id;
        this.name = name;
        this.quantity = quantity;
    }

    public Product(String name, int quantity) {
        this(null, name, quantity);
    }

    public Long getId() { return id; }
    public String getName() { return name; }
    public int getQuantity() { return quantity; }
}
~~~

Với constructor persistence đầy đủ, framework có thể truyền các giá trị đọc từ database ngay khi tạo object. Constructor nghiệp vụ hai tham số cho phép ứng dụng tạo sản phẩm mới mà không cần biết ID do database sinh.

Một constructor rõ ràng có lợi ích:

- Trạng thái object được thiết lập đầy đủ ngay lúc tạo.
- Không cần setter công khai chỉ để phục vụ persistence.
- Các bất biến nghiệp vụ có thể được kiểm tra trong constructor.
- Các trường cùng kiểu không bị gán nhầm chỉ vì code khởi tạo theo vị trí ở nhiều nơi.

Tuy nhiên, constructor mapping chỉ thành công nếu Spring Data xác định được constructor persistence, tên tham số và cách chuyển đổi kiểu cho từng giá trị.

## 10. Java record và tên component

Java record biểu diễn dữ liệu bằng các record component:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Column;
import org.springframework.data.relational.core.mapping.Table;

@Table("customers")
public record Customer(
    @Id Long id,
    @Column("first_name") String firstName,
    String email
) {}
~~~

Compiler tạo canonical constructor có các tham số tương ứng với record component. Tên component là một phần metadata của record, nên Spring Data có thể dùng canonical constructor để materialize record.

Tên component vẫn là tên property Java:

- `firstName` là tên component/property.
- `first_name` là tên cột do `@Column` chỉ định.

Không cần viết một constructor trùng hoàn toàn với canonical constructor nếu không có nhu cầu logic riêng. Nếu định nghĩa constructor bổ sung, hãy chú ý quy tắc chọn constructor và giữ mapping rõ ràng.

Dự án sử dụng Java record phải biên dịch bằng JDK hỗ trợ record (Java 16 trở lên). Với codebase Java 21, tính năng này đã có sẵn. `-parameters` vẫn là lựa chọn compiler tốt cho các constructor Java thông thường; không nên suy rộng đặc tính metadata record sang mọi class Java.

## 11. Chuyển đổi kiểu và tên tham số là hai việc khác nhau

Tên tham số đúng không bảo đảm giá trị có thể chuyển thành kiểu Java. Ví dụ cột SQL `created_at` có kiểu timestamp, trong khi constructor nhận `Instant`:

~~~java
public Customer(Long id, String firstName, Instant createdAt) {
    this.id = id;
    this.firstName = firstName;
    this.createdAt = createdAt;
}
~~~

Spring Data JDBC sử dụng conversion infrastructure để chuyển giá trị JDBC sang kiểu thuộc tính/constructor tương ứng. Có hai nhóm lỗi khác nhau:

| Nhóm | Ví dụ | Cách xử lý |
| --- | --- | --- |
| Không xác định được tên | Tham số chỉ hiện `arg2`, hoặc tên không khớp property | Bật `-parameters`, dùng `@ConstructorProperties`, sửa tên tham số |
| Không chuyển được kiểu | Database trả `Timestamp`, constructor cần kiểu chưa có converter | Dùng kiểu được hỗ trợ hoặc đăng ký converter phù hợp |
| Không tìm được constructor phù hợp | Có nhiều constructor nhưng chưa chỉ định persistence constructor | Dùng `@PersistenceCreator` theo đúng quy tắc |
| Thiếu giá trị cần thiết | Constructor đòi property không có trong kết quả mapping | Kiểm tra schema, projection và mapping của query |
| Giá trị không thỏa bất biến | Constructor từ chối dữ liệu không hợp lệ | Xác định dữ liệu/schema và quy tắc nghiệp vụ |

Không nên cố chữa lỗi chuyển đổi kiểu bằng cách đổi tên tham số, hoặc chữa lỗi tên tham số bằng cách thêm converter. Hãy phân loại đúng nguyên nhân.

## 12. Constructor mapping khi dùng repository và custom query

Một repository CRUD có thể khôi phục aggregate từ bảng:

~~~java
import org.springframework.data.repository.CrudRepository;

public interface CustomerRepository
        extends CrudRepository<Customer, Long> {
}
~~~

Khi gọi:

~~~java
Customer customer = customerRepository.findById(10L).orElseThrow();
~~~

Spring Data JDBC đọc dữ liệu và sử dụng object mapping metadata để tạo `Customer`.

Với query tùy chỉnh, kết quả vẫn cần được ánh xạ vào kiểu Java đích:

~~~java
import org.springframework.data.jdbc.repository.query.Query;
import org.springframework.data.repository.CrudRepository;

public interface CustomerRepository
        extends CrudRepository<Customer, Long> {

    @Query("""
        SELECT id, first_name, email
        FROM customers
        WHERE email = :email
        """)
    Customer findByEmail(String email);
}
~~~

Ví dụ này giả định câu query trả về các cột cần thiết để dựng `Customer`. Nếu query chỉ trả về một phần cột trong khi constructor persistence yêu cầu nhiều thuộc tính bắt buộc, framework có thể không tạo được entity hoàn chỉnh. Cần thiết kế projection/DTO riêng cho kết quả rút gọn, hoặc trả về đủ dữ liệu theo mapping.

Đối với custom query, có hai việc phải đúng đồng thời:

1. SQL phải trả về tên cột và giá trị phù hợp với mapping.
2. Kiểu đích phải có constructor mà Spring Data có thể chọn và cung cấp đủ tham số.

Một SQL query chạy thành công ở database chưa chắc đã có thể materialize thành mọi class Java.

## 13. Cách kiểm tra tên tham số đã được biên dịch

### 13.1. Kiểm tra bằng reflection

Dùng `Parameter.isNamePresent()` như ví dụ ở phần 2. Đây là cách kiểm tra trực tiếp metadata mà ứng dụng sẽ thấy khi chạy.

Có thể thêm một test nhỏ:

~~~java
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.lang.reflect.Constructor;
import java.lang.reflect.Parameter;
import org.junit.jupiter.api.Test;

class CustomerConstructorMetadataTest {

    @Test
    void constructorParameterNamesArePresent() {
        Constructor<?> constructor =
            Customer.class.getDeclaredConstructors()[0];

        for (Parameter parameter : constructor.getParameters()) {
            assertTrue(
                parameter.isNamePresent(),
                () -> "Missing parameter name for " + parameter
            );
        }
    }
}
~~~

Đoạn test chỉ phù hợp nếu class có một constructor hoặc test chọn đúng constructor persistence. Nếu có nhiều constructor, hãy tìm constructor theo chữ ký thay vì lấy phần tử đầu tiên từ mảng reflection, vì thứ tự trả về của `getDeclaredConstructors()` không phải hợp đồng lựa chọn persistence.

### 13.2. Kiểm tra bytecode bằng `javap`

JDK cung cấp công cụ `javap` để xem metadata class:

~~~bash
javap -v -p path/to/Customer.class
~~~

Tìm phần `MethodParameters` của constructor. Khi được biên dịch với `-parameters`, phần này có thể hiển thị tên tham số như `id`, `firstName`, `email`. Nếu chỉ có thông tin debug mà không có `MethodParameters`, điều đó không chứng minh reflection có thể đọc được tên tham số.

### 13.3. Kiểm tra artifact thật đang được chạy

Đôi khi build đã thay đổi nhưng ứng dụng vẫn chạy JAR cũ. Hãy xác định class được nạp từ thư mục/JAR nào, kiểm tra bytecode của chính artifact đó và chạy lại ứng dụng sau khi build module sở hữu entity.

Nếu entity đến từ dependency nội bộ, kiểm tra JAR dependency thay vì chỉ kiểm tra thư mục `build/classes` của ứng dụng.

## 14. Lỗi thường gặp và cách khắc phục

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Constructor parameter chỉ có tên `arg0`, `arg1` | Class được biên dịch thiếu `-parameters\) và không có metadata thay thế | Bật compiler option trong module tạo entity hoặc dùng `@ConstructorProperties` |
| Spring Data không khởi tạo được entity | Không tìm thấy constructor phù hợp hoặc tên tham số không khớp property | Xem lại constructor, tên property và `@PersistenceCreator` |
| Class có constructor nghiệp vụ và persistence nhưng chọn sai | Có nhiều constructor, chưa đánh dấu constructor persistence | Dùng `@PersistenceCreator` trên constructor cần dùng |
| Tên tham số đúng nhưng dữ liệu vẫn gán sai | Thứ tự/name trong `@ConstructorProperties` sai hoặc property mapping không nhất quán | So khớp từng tham số với property Java |
| Đã bật `-parameters` nhưng vẫn lỗi | Bật ở module ứng dụng thay vì module biên dịch entity, hoặc đang dùng JAR cũ | Kiểm tra class/JAR thật bằng reflection hoặc `javap\) |
| Constructor không nhận được giá trị cột | Custom query thiếu cột hoặc tên cột không khớp mapping | Trả về đủ cột, dùng `@Column` đúng hoặc dùng projection phù hợp |
| Không chuyển đổi được giá trị | Kiểu JDBC không tương thích kiểu tham số | Dùng kiểu được hỗ trợ hoặc đăng ký converter |
| Refactor field nhưng constructor chưa đổi tên | Tham số constructor còn tên cũ | Đổi tên tham số hoặc cung cấp metadata mapping phù hợp |
| Java record hoạt động nhưng class thường lỗi | Record component có metadata riêng; class thường thiếu parameter metadata | Bật `-parameters` cho class thường |

### Checklist điều tra thực tế

Khi gặp lỗi materialization, đi theo trình tự:

1. Xác định class entity cụ thể và constructor mà Spring Data dự kiến sử dụng.
2. Kiểm tra tên các property persistent của entity.
3. Kiểm tra reflection của constructor: `getParameters()`, `getName()\), `isNamePresent()`.
4. Kiểm tra `-parameters` trên task biên dịch của module tạo class hoặc kiểm tra `@ConstructorProperties`.
5. Kiểm tra `@PersistenceCreator` nếu có nhiều constructor.
6. So sánh tên tham số với **tên property Java**, sau đó kiểm tra `@Column` nối property với cột SQL.
7. Kiểm tra query có trả đủ cột và converter có xử lý được kiểu dữ liệu.
8. Xác minh class đang chạy là artifact vừa được biên dịch.

Không nên thay đổi nhiều cấu hình cùng lúc trước khi xác định metadata nào đang thiếu. Reflection là bằng chứng nhanh để phân biệt lỗi compiler metadata với lỗi mapping khác.

## 15. Quy ước triển khai nên áp dụng

Đối với dự án Java dùng Spring Data JDBC:

- Bật `-parameters` trong cấu hình Java compile chung hoặc tại mọi module biên dịch entity.
- Dùng một constructor persistence rõ ràng cho entity bất biến.
- Dùng `@PersistenceCreator` khi class có nhiều constructor và cần chọn constructor cụ thể.
- Dùng `@ConstructorProperties` khi cần khai báo tên tham số tường minh hoặc không kiểm soát được tùy chọn compiler ở một số môi trường.
- Giữ tên tham số constructor trùng tên property Java, kể cả khi tên cột SQL được tùy chỉnh bằng `@Column`.
- Dùng record khi mô hình phù hợp với dữ liệu bất biến và canonical constructor.
- Kiểm tra artifact đã build, đặc biệt với entity nằm trong module hoặc thư viện nội bộ.
- Không nhầm `-parameters` với `-g`, JVM system property, annotation processor hoặc cấu hình Hibernate.

Một ví dụ build convention tối thiểu:

~~~groovy
tasks.withType(JavaCompile).configureEach {
    options.compilerArgs.add("-parameters")
}
~~~

Cấu hình này giúp các constructor Java được biên dịch trong phạm vi task đó giữ lại tên tham số. Nó không thay thế việc khai báo đúng schema, mapping annotation, constructor selection hay converter.

## 16. Bài tập tự thực hành

### Bài 1 — Quan sát bytecode

Tạo class:

~~~java
public class Account {
    private final Long id;
    private final String accountNumber;

    public Account(Long id, String accountNumber) {
        this.id = id;
        this.accountNumber = accountNumber;
    }
}
~~~

Biên dịch một lần không có `-parameters`, một lần có `-parameters`. Dùng reflection để so sánh `Parameter.getName()` và `isNamePresent()`. Giải thích vì sao source code giống nhau nhưng metadata runtime khác nhau.

### Bài 2 — Constructor mapping với tên cột khác tên property

Tạo bảng `customers` có cột `first_name`, rồi khai báo entity có property `givenName\) và constructor tham số `givenName`. Dùng `@Column("first_name")` để ánh xạ. Thử đổi tham số thành `firstName` nhưng giữ property `givenName`, quan sát lỗi và giải thích.

### Bài 3 — Hai constructor

Tạo entity có constructor đầy đủ nhận `id`, `name\), `email` và constructor nghiệp vụ nhận `name\), `email`. Đánh dấu constructor persistence bằng `@PersistenceCreator`. Xác nhận tên tham số constructor persistence được lưu trong bytecode.

### Bài 4 — Thử `@ConstructorProperties`

Tắt `-parameters` cho module chứa một entity học tập, thêm `@ConstructorProperties` với tên property đúng. Kiểm tra metadata bằng reflection và thử đọc entity qua repository. Sau đó cố ý đảo thứ tự annotation để quan sát sự khác biệt.

### Bài 5 — Kiểm tra module dependency

Đặt entity trong một module tạo JAR riêng, còn ứng dụng Spring Data JDBC ở module khác. Chỉ bật `-parameters` ở module ứng dụng rồi kiểm tra constructor của entity trong JAR. Sau đó bật ở module sở hữu entity, build lại JAR và so sánh.

### Bài 6 — Phân biệt lỗi tên và lỗi kiểu

Tạo constructor có tham số `Instant createdAt` ánh xạ vào cột timestamp. Thử hai trường hợp: tên tham số không khớp property; tên đã đúng nhưng kiểu dữ liệu cần converter. Giải thích vì sao hai lỗi cần cách xử lý khác nhau.

## 17. Tài liệu tham khảo chính thức

- [Spring Data Relational — Object Mapping](https://docs.spring.io/spring-data/relational/reference/object-mapping.html): cách Spring Data tạo object, chọn constructor/factory và ánh xạ tham số với property.
- [Spring Data Commons — Object Mapping Fundamentals](https://docs.spring.io/spring-data/commons/reference/object-mapping.html): quy tắc constructor, immutable object, metadata và annotation persistence.
- [Spring Data Commons — `@PersistenceCreator` API](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/annotation/PersistenceCreator.html): đánh dấu constructor hoặc factory method được dùng để tạo persistent object.
- [Java `ConstructorProperties` API](https://docs.oracle.com/en/java/javase/21/docs/api/java.desktop/java/beans/ConstructorProperties.html): khai báo tên property tương ứng với tham số constructor.
- [Java Compiler — `javac` options](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html): tùy chọn `-parameters` để lưu metadata tên tham số.
- [Gradle JavaCompile](https://docs.gradle.org/current/dsl/org.gradle.api.tasks.compile.JavaCompile.html): cấu hình compiler arguments trong task Java.

Tên tham số constructor là một phần của hợp đồng object mapping: Spring Data cần nối tham số với property Java để khôi phục entity từ hàng SQL. Bật `-parameters\) giúp giữ tên trong bytecode; `@ConstructorProperties\) là cách khai báo tên tường minh; `@PersistenceCreator\) chọn constructor cần dùng. Khi ba phần này được cấu hình đúng và thống nhất với property mapping, Spring Data JDBC có thể tạo entity bất biến một cách rõ ràng và ổn định.
