# DataClassRowMapper cho kiểu có hàm khởi tạo dữ liệu phù hợp

Trong Spring JDBC, **`DataClassRowMapper<T>`** là một implementation của `RowMapper<T>` giúp chuyển từng hàng `ResultSet` thành đối tượng Java **bằng constructor nhận dữ liệu**. Nó phù hợp với **Java record**, DTO bất biến và class có constructor với tên tham số trùng hoặc tương ứng với column labels trong SQL. Mapper cũng có thể kết hợp constructor và JavaBean setters cho các thuộc tính không được constructor xử lý.

Ví dụ, query trả:

| id | display_name | completed_orders |
| ---: | --- | ---: |
| 1 | Linh Tran | 3 |
| 3 | Mai Pham | 5 |

DTO Java 17:

~~~java
public record CustomerSummary(
        long id, String displayName, int completedOrders) {
}
~~~

Truy vấn:

~~~java
List<CustomerSummary> results = jdbcTemplate.query(
        """
        SELECT id, display_name, completed_orders
        FROM customers
        WHERE completed_orders >= ?
        ORDER BY id
        """,
        DataClassRowMapper.newInstance(CustomerSummary.class),
        3);
~~~

Đây là **snippet tích hợp**: cần `JdbcTemplate`, bảng `customers` và record ở trên. Tên column `display_name` có thể khớp constructor parameter `displayName` theo quy ước snake_case/camelCase mà Spring hỗ trợ. Ở mục 5 có chương trình Java 17+ đầy đủ, có file build và stdout xác định.

**Điểm cốt lõi:** `DataClassRowMapper` làm **row-to-object mapping**, không quản lý transaction, không tự tạo database schema, không phải ORM/JPA và không tự xây dựng quan hệ cha–con từ nhiều hàng.

## 1. Mục tiêu bài học

Sau bài học, bạn có thể:

1. Giải thích cách `DataClassRowMapper` đọc tên cột, nhận diện constructor, convert giá trị JDBC và tạo object.
2. Chọn record Java 17, immutable class hay class kết hợp constructor + setter.
3. Hiểu khi nào phải bật `-parameters` khi compile class có constructor thường.
4. Viết SQL alias tương ứng tên constructor parameter, ví dụ `full_name AS display_name` cho `displayName`.
5. Đọc data với `JdbcTemplate.query(...)` và `queryForObject(...)`, phân biệt list rỗng với lỗi cardinality.
6. Xử lý SQL `NULL`, primitive/wrapper, kiểu số, date/time, conversion và validation của constructor.
7. So sánh `DataClassRowMapper` với `BeanPropertyRowMapper` và `RowMapper` tự viết.
8. Nhận diện giới hạn: nested object, join one-to-many, hiệu năng, non-static inner class, tên tham số thiếu metadata.
9. Viết integration test kiểm tra constructor mapping và lỗi schema trên driver phù hợp.

## 2. DataClassRowMapper hoạt động thế nào?

`DataClassRowMapper<T>` nằm trong package `org.springframework.jdbc.core`; class này **kế thừa `BeanPropertyRowMapper<T>`** và là một `RowMapper<T>`. Spring gọi `mapRow(rs, rowNum)` cho từng hàng trong kết quả truy vấn. Mapper tìm cách tạo target bằng constructor phù hợp, ánh xạ giá trị từ cột SQL vào các tham số theo **tên**, rồi gán các thuộc tính còn lại bằng setter nếu có.

~~~text
Repository / DAO
   |
   +--> JdbcTemplate.query(SQL, mapper, args...)
             |
             v
          JDBC ResultSet
             |
             +--> row 0
             |    +--> match SQL column labels to parameter names
             |    +--> read/convert values for each constructor argument
             |    +--> invoke constructor: CustomerSummary(...)
             |    +--> assign remaining writable properties if any
             |
             +--> row 1 -> another CustomerSummary(...)
             |
             +--> ...
             |
             v
        List<CustomerSummary>
~~~

### Ai chịu trách nhiệm việc gì?

| Thành phần | Trách nhiệm |
| --- | --- |
| `DataSource` | Cấp `Connection`, có thể qua pool |
| `JdbcTemplate` | Bind SQL parameters, execute query, duyệt rows, quản lý JDBC resources, dịch `SQLException` |
| `DataClassRowMapper` | Biến **một hàng** đang được định vị thành một instance `T` |
| Constructor DTO/record | Nhận dữ liệu và có thể bảo vệ invariant của object |
| Setter còn lại | Gán property chưa được constructor map nếu target cho phép |
| Repository method | Quy định SQL, điều kiện lọc, sort, trả `List<T>`/single object |

`RowMapper` không tự gọi `rs.next()`. `JdbcTemplate` điều khiển việc di chuyển con trỏ; mapper chỉ đọc hàng hiện tại. Mỗi hàng được map thành một object; nếu query không trả hàng, `query(...)` cho danh sách rỗng và mapper không chạy.

**Không nhầm với JPA:** Đối tượng tạo từ `DataClassRowMapper` không được EntityManager theo dõi, không có dirty checking, lazy-loading hay cascading. `@Entity`/`@Column` không tự thay đổi alias/mapping của mapper JDBC. Khi ánh xạ SQL, chính query và type Java là hợp đồng chính.

## 3. Điều kiện của kiểu dữ liệu và constructor

Tài liệu Spring yêu cầu target là **top-level class** hoặc **static nested class**. Một target hợp lệ có thể có:

- Data-class constructor với các tham số được đặt tên theo column labels;
- Các property setter kiểu JavaBean;
- Hoặc kết hợp cả hai.

### 3.1. Java record: trường hợp rõ ràng nhất

~~~java
public record OrderSummary(
        long id,
        String customerName,
        int itemCount) {
}
~~~

SQL:

~~~sql
SELECT
    o.id,
    c.name AS customer_name,
    COUNT(i.id) AS item_count
FROM orders o
JOIN customers c ON c.id = o.customer_id
LEFT JOIN order_items i ON i.order_id = o.id
GROUP BY o.id, c.name
ORDER BY o.id
~~~

Đây là **SQL minh họa**, yêu cầu các bảng `orders`, `customers` và `order_items`. Constructor canonical của record có component `id`, `customerName` và `itemCount`, tương ứng cột `id`, `customer_name`, `item_count`.

Java record cung cấp tên record components ở runtime theo cơ chế ngôn ngữ; Spring có thể lấy metadata cần thiết để gọi canonical constructor. Vì record không có setter thông thường, cách tiếp cận “gọi constructor rồi fill properties” phù hợp hơn so với yêu cầu constructor không tham số và setter ở `BeanPropertyRowMapper`.

Record bất biến giúp hạn chế việc vô tình mutate DTO sau mapping; tuy nhiên không có nghĩa SQL dữ liệu luôn hợp lệ. Constructor có thể reject dữ liệu, và application cần xử lý lỗi phù hợp.

### 3.2. Immutable class với constructor nhận dữ liệu

~~~java
public final class CustomerCard {
    private final long id;
    private final String displayName;

    public CustomerCard(long id, String displayName) {
        this.id = id;
        this.displayName = displayName;
    }

    public long id() {
        return id;
    }

    public String displayName() {
        return displayName;
    }
}
~~~

Với query có cột `id` và `display_name`, `DataClassRowMapper.newInstance(CustomerCard.class)` có thể gọi constructor trên **nếu Spring biết tên tham số `id`, `displayName`** ở runtime.

**Lưu ý build rất quan trọng:** Java reflection không nhất thiết lưu đúng tên tham số của constructor thường khi biên dịch chỉ bằng `javac` mặc định. Với các class như `CustomerCard`, hãy bật **`-parameters`**:

~~~bash
javac -parameters CustomerCard.java
~~~

Lệnh `javac` này minh họa cách compile source Java không phụ thuộc Spring. Ở ứng dụng thật, cấu hình build của module chứa DTO phải bảo đảm metadata tương ứng được lưu.

Gradle Groovy DSL:

~~~groovy
tasks.withType(JavaCompile).configureEach {
    options.compilerArgs.add('-parameters')
}
~~~

Maven compiler plugin (đoạn trong phần configuration):

~~~xml
<configuration>
    <release>17</release>
    <parameters>true</parameters>
</configuration>
~~~

Nếu không có `-parameters` hoặc cơ chế metadata tương thích, Spring có thể thấy tham số kiểu `arg0`/`arg1` thay vì `id`/`displayName`, không thể ghép chúng với tên cột một cách đáng tin. Đừng chỉ nhìn tên trong source và giả định tên đó còn tồn tại trong build artifact production.

### 3.3. Static nested class khác non-static inner class

~~~java
public class Views {
    public static record Summary(long id, String name) {}

    public static final class Card {
        private final long id;

        public Card(long id) {
            this.id = id;
        }
    }
}
~~~

`Views.Summary` và `Views.Card` là static nested types có thể là target nếu constructor/mapping phù hợp. **Non-static inner class** có tham chiếu ngầm đến outer instance và không nằm trong dạng target được `DataClassRowMapper` khuyến nghị/hỗ trợ. Dùng top-level DTO hoặc static nested DTO, nhất là khi đặt DTO trong một class test/demo.

### 3.4. Constructor nào được chọn?

Spring phải xác định **constructor phù hợp có thể được resolve** cho target. Record thường có canonical constructor rõ ràng. Với class bình thường có nhiều constructor (mặc định, overloaded hoặc do thư viện sinh), lựa chọn có thể khó đoán hoặc không phù hợp với data class contract. Khi thiết kế DTO cho mapping:

- Ưu tiên một constructor dữ liệu rõ ràng;
- Tránh overloaded constructors cùng số tham số với ý nghĩa khác;
- Bảo đảm metadata tên tham số được giữ;
- Kiểm tra access modifiers/module boundaries nếu reflection không gọi được constructor;
- Viết integration test trên bản compile thực thay vì chỉ dựa vào IDE.

Đừng sửa bằng cách thêm constructor rỗng chỉ để mapper chạy nếu bạn muốn DTO bất biến; điều đó có thể phá invariant của model.

## 4. Quy tắc khớp tên cột và tên tham số

Ví dụ:

~~~java
public record ProductSummary(
        long productId,
        String productName,
        int stockCount) {
}
~~~

SQL:

~~~sql
SELECT
    id AS product_id,
    name AS product_name,
    stock_count
FROM products
ORDER BY id
~~~

| Label trong SQL result | Record component / constructor parameter |
| --- | --- |
| `product_id` | `productId` |
| `product_name` | `productName` |
| `stock_count` | `stockCount` |

Spring hỗ trợ tên trực tiếp và convention camelCase/snake_case ở những dạng thường gặp. **Dùng alias rõ ràng** để loại bỏ suy đoán. Nếu cột nguồn là `full_name` nhưng DTO đòi `displayName`, viết `full_name AS display_name`, không trông chờ mapper suy luận hai từ đó cùng ý nghĩa.

### 4.1. Dùng column labels thay vì SELECT * mơ hồ

~~~sql
SELECT
    c.id AS customer_id,
    c.full_name AS display_name,
    COUNT(o.id) AS completed_orders
FROM customers c
LEFT JOIN orders o ON o.customer_id = c.id
GROUP BY c.id, c.full_name
ORDER BY c.id
~~~

SQL này **minh họa**, yêu cầu bảng `orders` và quan hệ tương ứng. Nếu record là `record CustomerAggregate(long customerId, String displayName, long completedOrders) {}`, aliases thể hiện đúng contract. Không nên dùng `SELECT *` với JOIN nhiều bảng cùng có `id`: collision/ambiguity và schema thay đổi dễ phá mapping.

### 4.2. Mapper không dựa thuần túy vào thứ tự SELECT

Mục tiêu là ghép tên tham số với tên cột/alias, rồi convert kiểu. Thay thứ tự cột khi names ổn định thường không làm thay đổi ý nghĩa mapping. Tuy nhiên **đừng dựa vào điều này để bỏ test**: driver và SQL projection vẫn quyết định metadata và kiểu giá trị thực được đọc.

### 4.3. Thiếu một cột constructor là lỗi, không phải giá trị mặc định

Record `CustomerSummary(long id, String displayName, int completedOrders)` đòi cột `completed_orders`. SQL chỉ `SELECT id, display_name` không cung cấp giá trị cho constructor. Spring không tự đoán completedOrders bằng 0; thao tác mapping có thể thất bại ở runtime. Sửa query để cung cấp đủ projection hoặc dùng DTO khác chỉ có hai component.

## 5. Ví dụ Java 17+ chạy được: record và constructor kết hợp setter

Ví dụ này dùng **Spring Framework 6.2.11**, H2 **2.3.232** và Java 17. Nó cho thấy:

1. `DataClassRowMapper` ánh xạ record bằng canonical constructor;
2. Class thường được tạo qua constructor hai tham số;
3. Property `city` được điền bằng setter sau constructor;
4. Truy vấn không có hàng trả list rỗng.

Project không cần Spring Boot; JDBC được dựng rõ ràng để tập trung vào mapping.

Cấu trúc:

~~~text
data-class-row-mapper-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/App.java
~~~

File `settings.gradle`:

~~~groovy
rootProject.name = 'data-class-row-mapper-demo'
~~~

File `build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-jdbc:6.2.11'
    runtimeOnly 'com.h2database:h2:2.3.232'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.compilerArgs.add('-parameters')
}

application {
    mainClass = 'demo.App'
}
~~~

`-parameters` đặc biệt quan trọng cho constructor thường của `CustomerProfile`. Gradle `application` plugin cung cấp lệnh `run`. Source Java đặt đúng theo package `demo`.

File `src/main/java/demo/App.java`:

~~~java
package demo;

import org.springframework.jdbc.core.DataClassRowMapper;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowMapper;
import org.springframework.jdbc.datasource.DriverManagerDataSource;

import javax.sql.DataSource;
import java.util.List;

public class App {

    public record CustomerSummary(
            long id,
            String displayName,
            int completedOrders) {
    }

    public static final class CustomerProfile {
        private final long id;
        private final String displayName;
        private String city;

        public CustomerProfile(long id, String displayName) {
            this.id = id;
            this.displayName = displayName;
        }

        public void setCity(String city) {
            this.city = city;
        }

        @Override
        public String toString() {
            return "CustomerProfile[id=" + id
                    + ", displayName=" + displayName
                    + ", city=" + city + "]";
        }
    }

    public static final class CustomerDao {
        private static final RowMapper<CustomerSummary> SUMMARY_MAPPER =
                DataClassRowMapper.newInstance(CustomerSummary.class);

        private static final RowMapper<CustomerProfile> PROFILE_MAPPER =
                DataClassRowMapper.newInstance(CustomerProfile.class);

        private final JdbcTemplate jdbc;

        public CustomerDao(JdbcTemplate jdbc) {
            this.jdbc = jdbc;
        }

        public List<CustomerSummary> withAtLeast(int minimum) {
            return jdbc.query(
                    """
                    SELECT id, display_name, completed_orders
                    FROM customers
                    WHERE completed_orders >= ?
                    ORDER BY id
                    """,
                    SUMMARY_MAPPER,
                    minimum);
        }

        public CustomerProfile profile(long id) {
            return jdbc.queryForObject(
                    """
                    SELECT id, display_name, city
                    FROM customers WHERE id = ?
                    """,
                    PROFILE_MAPPER,
                    id);
        }
    }

    public static void main(String[] args) {
        DataSource source = new DriverManagerDataSource(
                "jdbc:h2:mem:customer_mapping;DB_CLOSE_DELAY=-1",
                "sa",
                "");
        JdbcTemplate jdbc = new JdbcTemplate(source);

        jdbc.execute("""
                CREATE TABLE customers (
                    id BIGINT PRIMARY KEY,
                    display_name VARCHAR(100) NOT NULL,
                    completed_orders INT NOT NULL,
                    city VARCHAR(100)
                )
                """);

        jdbc.update(
                """
                INSERT INTO customers
                (id, display_name, completed_orders, city)
                VALUES (?, ?, ?, ?)
                """,
                1L, "Linh Tran", 3, "Ha Noi");

        jdbc.update(
                """
                INSERT INTO customers
                (id, display_name, completed_orders, city)
                VALUES (?, ?, ?, ?)
                """,
                2L, "Nam Le", 0, "Da Nang");

        jdbc.update(
                """
                INSERT INTO customers
                (id, display_name, completed_orders, city)
                VALUES (?, ?, ?, ?)
                """,
                3L, "Mai Pham", 5, null);

        CustomerDao dao = new CustomerDao(jdbc);

        System.out.println("Record: " + dao.withAtLeast(3));
        System.out.println("Empty: " + dao.withAtLeast(99));
        System.out.println("Mixed: " + dao.profile(1L));
    }
}
~~~

Chạy từ thư mục project khi có JDK 17+ và Gradle phù hợp:

~~~bash
gradle run --quiet
~~~

**Stdout chương trình** (không tính log môi trường nếu có):

~~~text
Record: [CustomerSummary[id=1, displayName=Linh Tran, completedOrders=3], CustomerSummary[id=3, displayName=Mai Pham, completedOrders=5]]
Empty: []
Mixed: CustomerProfile[id=1, displayName=Linh Tran, city=Ha Noi]
~~~

### 5.1. Phân tích vì sao chạy đúng

1. `DriverManagerDataSource` cung cấp JDBC connections đến H2 in-memory. `DB_CLOSE_DELAY=-1` giữ DB bộ nhớ tồn tại trong cùng JVM sau khi đóng kết nối cuối. Đây là cấu hình **demo/test**, không có connection pool như HikariCP production.
2. `JdbcTemplate` thực thi DDL và các lệnh INSERT có tham số, rồi đọc SQL query qua hai mapper.
3. `SUMMARY_MAPPER` ánh xạ `id`, `display_name` và `completed_orders` vào record `CustomerSummary`. Java record tự có `toString()` in tên component và giá trị, nên stdout theo dạng `CustomerSummary[id=..., ...]`.
4. `withAtLeast(3)` chọn ID 1 và 3. `ORDER BY id` bảo đảm thứ tự hai phần tử. `withAtLeast(99)` không có hàng, kết quả `List` rỗng.
5. `PROFILE_MAPPER` ánh xạ ID và display name qua constructor `CustomerProfile(long id, String displayName)`. `city` không thuộc constructor nên `setCity(...)` được gọi cho thuộc tính còn lại.
6. `CustomerProfile.toString()` do class tự triển khai, tạo dòng cuối như mong đợi.
7. Cả `CustomerSummary` và `CustomerProfile` đều là static nested types (record bên trong class mặc nhiên static). Cấu hình `-parameters` cho phép nhận diện tham số constructor thường.
8. Mapper và `JdbcTemplate` không cache kết quả query; chúng điều phối việc tạo đối tượng và lấy dữ liệu từ SQL khi gọi.

Ví dụ không cấu hình Spring transaction manager vì trọng tâm là mapping. Trong ứng dụng thực, Spring Boot thường tự cấu hình `DataSource`/`JdbcTemplate`, còn repository nhận template bằng constructor injection.

## 6. Constructor argument có ưu tiên trước setter

Theo contract của `DataClassRowMapper`, **một thuộc tính đã được map thành công thông qua constructor argument sẽ không được map lại bằng setter**. Điều này khác với giả định rằng mọi public setter luôn được gọi.

Ví dụ:

~~~java
public static final class DisplayCard {
    private String name;
    private String city;

    public DisplayCard(String name) {
        this.name = name.trim();
    }

    public void setName(String value) {
        this.name = "setter:" + value;
    }

    public void setCity(String city) {
        this.city = city;
    }
}
~~~

Với SQL cột `name` là chuỗi có khoảng trắng `"  Anh  "` và `city` là `Hue`:

- Constructor nhận `name` và gọi `trim()`, tạo `Anh`.
- Setter `setName` **không** chạy thêm một lần cho property đã map qua constructor.
- `setCity` có thể được dùng cho cột `city` vì constructor không nhận thuộc tính này.

Đây là **đoạn minh họa trong static nested class**, không phải chương trình hoàn chỉnh. Đừng nhầm thứ tự này với cơ chế Bean Validation hoặc JPA dirty checking: constructor mapping chỉ quyết định cách tạo object từ một row.

### Vì sao quy tắc này hữu ích?

- Constructor có thể đảm bảo invariant của immutable DTO.
- Tránh việc setter ghi đè giá trị constructor đã normalize.
- Giúp thiết kế rõ thành phần bắt buộc nằm ở constructor, thành phần tùy chọn nằm ở setter.

Tuy nhiên nếu constructor ném exception khi dữ liệu thiếu/sai, mapping cũng sẽ thất bại. Đây có thể là dấu hiệu database không thỏa domain contract; không nên bắt rồi âm thầm thay bằng object rỗng.

## 7. So sánh với BeanPropertyRowMapper và RowMapper tự viết

| Đặc điểm | `DataClassRowMapper<T>` | `BeanPropertyRowMapper<T>` | Custom `RowMapper<T>` |
| --- | --- | --- | --- |
| Target Java record | Rất phù hợp | Không phải cách chính | Rất phù hợp |
| Constructor với tham số dữ liệu | Hỗ trợ nếu tên có thể xác định | Thường dựa vào no-arg + setters | Chủ động gọi constructor |
| Setter kiểu JavaBean | Có thể kết hợp | Hỗ trợ | Tùy code |
| Constructor thắng setter | Có | Không phải trường hợp thông thường | Do code quyết định |
| SQL column/alias naming | Ghép theo tên/convention | Ghép theo tên/convention | Tự đọc cột tường minh |
| Chi phí reflection/conversion | Có | Có | Thường kiểm soát tốt hơn |
| Mapper cho object graph | Không tự dựng quan hệ nested phức tạp | Không tự dựng quan hệ nested phức tạp | Có thể tự xử lý |
| Lượng boilerplate | Ít | Ít | Nhiều hơn |
| Khi cần logic chuyển đổi đặc biệt | Custom converter hoặc đổi mapper | Custom converter hoặc đổi mapper | Rõ và linh hoạt nhất |

### 7.1. Ví dụ với JavaBean có constructor rỗng

~~~java
public class CustomerBean {
    private long id;
    private String displayName;

    public CustomerBean() {}

    public void setId(long id) {
        this.id = id;
    }

    public void setDisplayName(String name) {
        this.displayName = name;
    }
}
~~~

Khi đó, snippet query:

~~~java
List<CustomerBean> beans = jdbcTemplate.query(
        "SELECT id, display_name FROM customers ORDER BY id",
        BeanPropertyRowMapper.newInstance(CustomerBean.class));
~~~

`BeanPropertyRowMapper` phù hợp class mutable có setter. `DataClassRowMapper` kế thừa và có thể xử lý cả mô hình setter ở nhiều trường hợp; nhưng việc dùng mapper cụ thể giúp đọc code hiểu ý đồ target.

### 7.2. Custom RowMapper kiểm soát trường dữ liệu

~~~java
private static final RowMapper<CustomerSummary> SUMMARY =
        (rs, rowNum) -> new CustomerSummary(
                rs.getLong("id"),
                rs.getString("display_name"),
                rs.getInt("completed_orders"));
~~~

Snippet này nằm trong DAO đã import `RowMapper` và kiểu record. Nó rõ tên cột, getter, thứ tự argument, giúp sửa conversion theo yêu cầu và có thể giảm overhead reflection. Nếu mapping khó hoặc hiệu năng thực sự là bottleneck, mapper tự viết là lựa chọn hợp lý.

### 7.3. Spring Framework 6.1+ và JdbcClient

`JdbcClient` có fluent interface:

~~~java
List<CustomerSummary> customers = jdbcClient.sql(
        """
        SELECT id, display_name, completed_orders
        FROM customers ORDER BY id
        """)
    .query(CustomerSummary.class)
    .list();
~~~

Đoạn trên cần bean `JdbcClient` và schema như ví dụ. `JdbcClient.query(CustomerSummary.class)` dùng cơ chế mapping class tự động của API tương ứng, **không nên nói rằng nó nhất thiết dùng đúng `DataClassRowMapper`** bên dưới. Khi cần học hoặc kiểm soát rõ mapper nào xử lý dữ liệu, vẫn có thể truyền `DataClassRowMapper.newInstance(...)` trực tiếp cho `JdbcTemplate.query(...)`.

## 8. NULL và kiểu dữ liệu trong constructor

Đây là nhóm lỗi dễ bỏ sót nhất. SQL `NULL` khác `0`, `false` hay chuỗi rỗng:

~~~java
public record ProductView(
        long id,
        String name,
        Integer stockCount,
        java.math.BigDecimal price) {
}
~~~

Với schema có cột `stock_count` nullable:

- `long id` nên đọc từ `PRIMARY KEY`/`NOT NULL` vì primitive không nhận được null.
- `Integer stockCount` giữ được phân biệt giữa “chưa biết số lượng” và `0`.
- `BigDecimal price` thường phù hợp dữ liệu tiền tệ hơn `double`, nhưng cần kiểm tra scale/rounding.
- `String name` có thể là null theo Java; constructor có thể kiểm tra riêng business constraint.

### 8.1. NULL đưa vào primitive

Khi constructor đòi `int`/`long`/`boolean` nhưng SQL column có thể NULL, mapper không thể biểu diễn trực tiếp null bằng primitive, nên có thể thất bại ở conversion/invocation. Không mặc định dựa vào số `0`. Chọn wrapper type hoặc ràng buộc `NOT NULL`; nếu dùng SQL `COALESCE`, phải chắc biến null thành 0 là đúng về nghiệp vụ.

~~~sql
SELECT
    id,
    COALESCE(stock_count, 0) AS stock_count
FROM products
ORDER BY id
~~~

SQL trên chỉ đúng nếu null có thể được diễn giải như số lượng bằng 0. Nếu null nghĩa “chưa kiểm kê”, `Integer` mới mô tả đúng dữ liệu.

### 8.2. ConversionService, enum, BigDecimal, date/time

`DataClassRowMapper` thừa hưởng khả năng conversion của mapper Spring. Có thể cung cấp một `ConversionService` tùy chỉnh thông qua overload:

~~~java
DataClassRowMapper<ProductView> mapper =
        DataClassRowMapper.newInstance(
                ProductView.class, conversionService);
~~~

Đây là snippet giả sử có `ConversionService conversionService` được định nghĩa. Không cần custom converter cho mọi kiểu; chỉ tạo khi driver/type/domain đòi hỏi.

Cần đặc biệt test:

- `DATE` -> `LocalDate`;
- `TIMESTAMP` -> `LocalDateTime` và timezone;
- `TIMESTAMP WITH TIME ZONE` -> `OffsetDateTime`;
- `NUMERIC`/`DECIMAL` -> `BigDecimal`, `Integer`, `Long`;
- `VARCHAR` -> `enum` khi code/name/casing khác nhau;
- PostgreSQL enum/JSONB/UUID/ARRAY hoặc kiểu đặc thù database.

Kết quả conversion còn phụ thuộc driver JDBC và dữ liệu thực, không phải mọi dialect cùng trả một Java type. Nếu conversion phức tạp và business-sensitive, `RowMapper` thủ công thường dễ kiểm soát hơn.

### 8.3. Constructor có validation

~~~java
public record PriceView(
        long id, java.math.BigDecimal amount) {

    public PriceView {
        if (amount == null || amount.signum() < 0) {
            throw new IllegalArgumentException(
                    "amount must be non-negative");
        }
    }
}
~~~

Nếu SQL trả amount null hoặc âm, constructor sẽ từ chối object. Mapper không được coi dữ liệu không hợp lệ là một hàng bình thường. Hãy phân biệt lỗi domain validation, lỗi conversion và `DataAccessException` do SQL/driver.

## 9. Một hàng SQL không đồng nghĩa một object graph

`DataClassRowMapper` áp dụng “một hàng -> một instance” chứ không dựng quan hệ cha–con.

~~~sql
SELECT
    c.id,
    c.display_name,
    o.id AS order_id
FROM customers c
JOIN orders o ON o.customer_id = c.id
ORDER BY c.id, o.id
~~~

Nếu một khách hàng có ba đơn, SQL trên có ba hàng cho khách hàng đó, nên mapping trực tiếp sang record khách có thể tạo ba instance lặp. Mapper không tự gom ba đơn vào một `List<Order>` trong object cha.

Các lựa chọn đúng hơn:

1. Chỉ cần số lượng đơn: dùng SQL aggregate `COUNT(o.id) AS order_count` với `GROUP BY`, trả một record tổng hợp/khách.
2. Chỉ cần khách có đơn: dùng `EXISTS` thay vì JOIN để tránh nhân hàng.
3. Cần object graph: dùng `ResultSetExtractor`, mapper thủ công hoặc hai query và merge theo key.
4. Cần phân trang khách: phân trang parent trước, tránh `LIMIT/OFFSET` trực tiếp trên JOIN one-to-many khiến trang chứa ít khách hơn dự kiến.

**Giới hạn của loại mapper này:** nó không thay JPA `@OneToMany`, entity graph hay ORM hydration. Sử dụng đúng abstraction để khỏi tạo những DTO sai cấu trúc.

## 10. Hiệu năng và tái sử dụng mapper

Spring mô tả `DataClassRowMapper` là tiện lợi chứ **không được tối ưu cho hiệu năng cực cao**. Nó có công việc metadata/reflection/conversion trong quá trình mapping. Tuy nhiên không nên tối ưu hóa sớm mà bỏ qua chi phí SQL, index, network, driver, allocation, sort và paging.

Một cách tổ chức tốt trong DAO:

~~~java
private static final RowMapper<CustomerSummary> MAPPER =
        DataClassRowMapper.newInstance(CustomerSummary.class);
~~~

Mapper tĩnh không có request state dùng lại được. `JdbcTemplate` thường cũng là một bean tái sử dụng giữa các repository. Dùng mapper từng hàng **không** có nghĩa mở connection mới cho từng hàng: `JdbcTemplate` quản lý một operation SQL trên connection phù hợp.

Khi kết quả rất lớn:

- Chỉ SELECT cột cần cho DTO (projection).
- Phân trang với `ORDER BY` ổn định và `LIMIT/OFFSET` hoặc keyset pagination theo dialect.
- Không mặc định đọc hàng triệu object vào `List<T>` rồi mới filter bằng Java.
- Chọn fetch size/transaction/cursor theo driver nếu cần streaming; `setFetchSize` là hint chứ không phải page size.
- Có thể dùng `RowCallbackHandler` hoặc `queryForStream` khi không cần list. Với `queryForStream` phải **đóng stream** bằng try-with-resources.
- Benchmark/phân tích profile trước khi đổi sang manual mapper; nếu mapping là hot spot, mapper thủ công giúp kiểm soát type reads và allocation.

### 10.1. Không gắn mutable state vào mapper dùng chung

Mapper hoặc constructor DTO không nên lưu `ResultSet`, `Connection` hay bộ đệm dùng chung giữa nhiều request. Dữ liệu object trả về thuộc từng kết quả query. Có thể tái sử dụng metadata/mapping policy, nhưng một `List<CustomerSummary>` đang trả cho request A không nên trở thành field singleton được request B mutate.

## 11. Một số lỗi thực tế và cách khắc phục

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Không tìm thấy constructor hoặc khởi tạo object thất bại | Class không phù hợp, nhiều constructor không rõ, non-static inner class | Dùng record hoặc top-level/static nested class với constructor rõ |
| Mapper tìm tên `arg0`, `arg1` | Class thường không được compile với `-parameters` | Bật compiler flag và test artifact cuối |
| Báo không có cột `displayName` | SQL trả `full_name`, thiếu alias thích hợp | Dùng `AS display_name` |
| Thiếu dữ liệu constructor | Query chỉ SELECT một phần fields | Chọn projection đầy đủ hoặc DTO khác |
| Primitive gặp null | SQL nullable nhưng constructor dùng `int`/`long` | Wrapper hoặc schema/SQL xử lý null chính xác |
| Kiểu ngày giờ sai | JDBC driver/timezone/converter không hợp | Test trên database thật; conversion/manual mapper |
| Setter không chạy sau constructor | Property đã map qua constructor nên bị bỏ qua setter | Chuyển validation vào constructor; hiểu precedence |
| Kết quả bị trùng do JOIN | Mỗi hàng SQL tạo một instance | Sửa query/aggregate, map object graph riêng |
| Record được tạo nhưng JPA không thấy thay đổi | JDBC DTO không phải managed JPA entity | Dùng repository/SQL update hoặc JPA đúng nhiệm vụ |
| Query không trả hàng | `JdbcTemplate.query` cho list rỗng | Xử lý contract rỗng, không coi là lỗi mapper |
| `queryForObject` không có hàng | API đòi đúng một row | Xử lý not-found/`Optional` theo nghiệp vụ |
| Mapper bị chậm trên tập lớn | Reflection/conversion + số object nhiều | Profile, paging, custom `RowMapper` |
| IDE tự import class R2DBC cùng tên | Nhầm package `org.springframework.r2dbc.core` | Dùng `org.springframework.jdbc.core.DataClassRowMapper` |

### 11.1. Chẩn đoán metadata tên tham số

Với constructor thường:

~~~java
import java.lang.reflect.Constructor;
import java.lang.reflect.Parameter;

Constructor<?> ctor =
        CustomerCard.class.getDeclaredConstructors()[0];

for (Parameter p : ctor.getParameters()) {
    System.out.println(
            p.getName() + " / present=" + p.isNamePresent());
}
~~~

Đây là snippet chẩn đoán khi có `CustomerCard` ở scope và một constructor phù hợp. Nếu build có `-parameters`, bạn mong thấy `id`/`displayName` với `isNamePresent() == true`. Nếu Java reflection thấy `arg0`/`arg1` và false, metadata chưa được giữ theo cách reflection dùng. Kiểm tra riêng mỗi module/library chứa DTO.

### 11.2. Không chữa lỗi bằng cách bỏ tất cả validation

Nếu constructor từ chối `amount < 0`, đừng xóa validation để mapper không lỗi. Tìm nguồn dữ liệu sai, sửa migration/SQL hoặc xác định DTO phù hợp. Mapper có thể bộc lộ bất nhất giữa dữ liệu database và contract Java; đó thường là tín hiệu đáng xử lý.

### 11.3. Cẩn trọng với API trong các nhánh Spring khác nhau

`org.springframework.jdbc.core.DataClassRowMapper` là API Spring JDBC từ dòng Spring Framework 5.3. Ngoài ra còn có `DataClassRowMapper` trong package R2DBC cho giao diện reactive khác. Kiểm tra import, version API và các overload của `newInstance`/`JdbcTemplate` đúng dependency thực tế.

## 12. Kiểm thử ánh xạ có ý nghĩa

Với integration test trên H2 hoặc DB thực, hãy kiểm tra:

1. **Record mapping:** Query chứa `display_name`/`completed_orders` và nhận được object với component đúng.
2. **Class constructor mapping:** Class được compile với `-parameters` và khởi tạo đúng `id`/`displayName`.
3. **Constructor + setter:** `city` được gán qua setter, còn property đã map trong constructor không bị ghi đè.
4. **Không có hàng:** `query(...)` trả list rỗng, không ném `EmptyResultDataAccessException`.
5. **Thiếu cột:** Cố ý query thiếu component và kiểm tra mapping lỗi; đảm bảo không âm thầm tạo object sai.
6. **NULL:** Dùng cột nullable và wrapper/reference, kiểm tra primitive không bị đánh đồng NULL với 0.
7. **Conversion:** DATE/TIMESTAMP/DECIMAL/enum trên driver production.
8. **JOIN:** Một parent có nhiều child; kiểm tra query trả số DTO theo contract mong muốn.
9. **Ordering:** Nếu API yêu cầu list có thứ tự, SQL phải có `ORDER BY`.
10. **Performance:** Với large dataset, đo query time, mapping time và memory nếu cần tối ưu.

### Ví dụ JUnit 5 (snippet tích hợp)

Giả sử có JUnit 5, bảng `customers` tạo trước test và `JdbcTemplate jdbc` sẵn:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import org.junit.jupiter.api.Test;

@Test
void mapsSnakeCaseIntoRecord() {
    jdbc.update(
            """
            INSERT INTO customers
            (id, display_name, completed_orders, city)
            VALUES (?, ?, ?, ?)
            """,
            10L, "An Nguyen", 4, "Hue");

    List<CustomerSummary> actual = jdbc.query(
            """
            SELECT id, display_name, completed_orders
            FROM customers WHERE id = ?
            """,
            DataClassRowMapper.newInstance(CustomerSummary.class),
            10L);

    assertEquals(
            List.of(new CustomerSummary(10L, "An Nguyen", 4)),
            actual);
}
~~~

Đoạn trên **không chạy độc lập**: test class cần `jdbc`, `CustomerSummary`, imports `java.util.List`/mapper, Spring test configuration và fixture database. Java record cung cấp `equals()` theo components nên có thể so sánh trực tiếp bằng `assertEquals`. Trong project thật nên để test DB isolated/rollback giữa các test, tránh key trùng.

### Unit test và integration test khác nhau

Mock `JdbcTemplate` có thể chứng minh service sử dụng repository đúng cách, nhưng **không chứng minh SQL aliases hay reflection mapping chạy thật**. Mapper tự động phụ thuộc `ResultSetMetaData`, nên integration test nhỏ có database thật/embedded thường hữu ích. Khi production dùng PostgreSQL/MySQL/Oracle với kiểu khác H2, chạy test bổ sung trên DB tương thích, có thể bằng Testcontainers.

## 13. Quy trình thiết kế DTO dùng DataClassRowMapper

1. **Chọn dữ liệu đầu ra:** Viết record chỉ chứa các cột query cần trả, không cố mô phỏng toàn bộ bảng nếu API chỉ cần summary.
2. **Quy định nullability:** Chọn primitive cho cột thật sự `NOT NULL`; wrapper/reference cho cột nullable.
3. **Thiết kế constructor:** Record hoặc một constructor dữ liệu rõ; bảo toàn metadata tên ở runtime.
4. **Viết SQL projection:** SELECT đủ cột, alias theo tên component/parameters, dùng bind placeholders.
5. **Tạo mapper:** `DataClassRowMapper.newInstance(Dto.class)`; tái sử dụng instance stateless khi phù hợp.
6. **Đưa vào repository:** Inject `JdbcTemplate` qua constructor, dùng `query(sql, mapper, args...)` cho nhiều hàng.
7. **Xử lý kết quả:** List rỗng, lỗi cardinality, mapping/conversion error có contract riêng; không nuốt lỗi rồi giả làm “không có dữ liệu”.
8. **Test:** H2 cho demo, DB thực cho dialect/type đặc biệt, test metadata `-parameters` khi dùng class thường.
9. **Đo khi cần:** Nếu throughput/latency bị ảnh hưởng bởi reflection, thử manual mapping đã được benchmark.

### Câu hỏi ôn tập

1. Vì sao `DataClassRowMapper` phù hợp Java record hơn `BeanPropertyRowMapper` truyền thống?
2. Class có constructor `CustomerCard(long id, String displayName)` không dùng record; tại sao build production có thể lỗi nếu thiếu `-parameters`?
3. Query có cột `full_name` nhưng record cần `displayName`: alias nào thể hiện đúng contract?
4. Một class có constructor và setter cho cùng `name`: cách nào được ưu tiên?
5. Vì sao nullable SQL `stock_count` không nên dùng `int` nếu null có ý nghĩa “chưa thống kê”?
6. JOIN trả ba hàng cho một khách hàng: mapper có tự xây dựng một `CustomerWithOrders` chứa ba phần tử không?
7. Khi nào chi phí mapper tự động đáng chuyển sang custom `RowMapper`?
8. Vì sao DTO tạo bởi Spring JDBC mapper không tự được JPA persistence context theo dõi?

## 14. Checklist triển khai

- [ ] Target class là top-level hoặc static nested, constructor/record components phù hợp.
- [ ] Class thường có parameter name metadata runtime; compiler có `-parameters` nếu cần.
- [ ] SQL trả **đủ cột** cho constructor, aliases khớp tên tham số.
- [ ] Nullable fields dùng wrapper/reference type; primitive không nhận null mơ hồ.
- [ ] Hiểu constructor arguments có ưu tiên so với setters.
- [ ] Không dùng `SELECT *` tùy tiện với JOIN; tránh thiếu/đụng column labels.
- [ ] Mapper được tái sử dụng, không giữ mutable request state.
- [ ] `JdbcTemplate` và datasource/transaction manager được cấu hình đúng riêng với mapper.
- [ ] Không mong `DataClassRowMapper` tự gộp nhiều SQL rows thành nested graph.
- [ ] Query không có hàng được xử lý như kết quả hợp lệ của `List<T>`.
- [ ] Test bằng JDBC driver phù hợp; riêng type/date/time/conversion cần test production-like.
- [ ] Chỉ tối ưu sang mapper thủ công khi có nhu cầu rõ và profiling phù hợp.

**Kết luận:** Chọn `DataClassRowMapper` khi **các cột SQL ghép được rõ ràng với tên constructor parameters/record components**. Nó giúp Spring JDBC tạo DTO bất biến và các class kết hợp constructor–setter mà không phải viết `RowMapper` cho từng cột. Độ chính xác phụ thuộc thiết kế constructor, compiler metadata, SQL aliases, nullability và kiểu conversion; các trường hợp cần object graph hoặc mapping đặc biệt vẫn nên dùng mapper thủ công.

## Tài liệu chính thức

- [Spring Framework — DataClassRowMapper API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jdbc/core/DataClassRowMapper.html)
- [Spring Framework — BeanPropertyRowMapper API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jdbc/core/BeanPropertyRowMapper.html)
- [Spring Framework — JDBC Core Operations](https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html)
- [Spring Framework — JdbcTemplate API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jdbc/core/JdbcTemplate.html)
- [Spring Framework — Data Access with JDBC](https://docs.spring.io/spring-framework/reference/data-access/jdbc.html)
- [Java 17 — java.lang.reflect.Parameter API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Parameter.html)
