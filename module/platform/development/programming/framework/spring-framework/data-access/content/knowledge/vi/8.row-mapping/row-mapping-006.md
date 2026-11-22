# BeanPropertyRowMapper và quy tắc ánh xạ tên thuộc tính

Trong Spring JDBC, dữ liệu từ `ResultSet` thường có tên cột theo quy ước SQL như `first_name`, `email_address`, `created_at`, trong khi đối tượng Java dùng thuộc tính `firstName`, `emailAddress`, `createdAt`. `BeanPropertyRowMapper<T>` là một triển khai `RowMapper<T>` có thể tự tạo một JavaBean và đưa giá trị cột vào các **thuộc tính có setter công khai** tương ứng. Đây là cách giảm phần mã lặp khi ánh xạ các truy vấn JDBC thông thường, nhưng chỉ hoạt động đúng nếu hiểu các quy tắc về tên, constructor, setter, kiểu dữ liệu, `NULL` và phạm vi ánh xạ.

Bài học giải thích cách `BeanPropertyRowMapper` khớp tên cột–tên property, những tình huống cần dùng SQL alias, giới hạn của ánh xạ tự động và khi nào nên chuyển sang `DataClassRowMapper` hoặc tự viết `RowMapper`. Ví dụ dùng **Java 17+, Spring JDBC 6.1.x và H2**.

## 1. Vị trí của `BeanPropertyRowMapper` trong luồng JDBC

Một truy vấn JDBC thường đi qua các bước:

```text
JdbcTemplate.query(sql, rowMapper, args...)
        |
        v
PreparedStatement -> ResultSet (n hàng, m cột)
                          |
                          | mỗi hàng
                          v
              BeanPropertyRowMapper<T>.mapRow(...)
                          |
              tạo JavaBean bằng constructor không tham số
                          |
              đọc metadata tên/label cột
                          |
              tìm JavaBeans PropertyDescriptor tương ứng
                          |
              đọc SQL value, chuyển kiểu khi hỗ trợ
                          |
              gọi setter phù hợp
                          |
                          v
                    đối tượng T
        |
        v
List<T> (cho query) hoặc đúng 1 T (cho queryForObject)
```

`BeanPropertyRowMapper` làm việc ở tầng **một hàng → một object**. Nó không quyết định SQL trả mấy hàng, không tự tạo bảng, không thực hiện transaction và không tự biến quan hệ một-nhiều thành danh sách lồng nhau. `JdbcTemplate` quản lý việc chạy truy vấn và vòng đời JDBC resources.

Cách sử dụng điển hình:

```java
// Ví dụ tích hợp: jdbc là JdbcTemplate, CustomerBean là JavaBean.
List<CustomerBean> customers = jdbc.query(
    "SELECT id, first_name, email_address FROM customer ORDER BY id",
    BeanPropertyRowMapper.newInstance(CustomerBean.class)
);
```

Nếu `CustomerBean` có constructor không tham số và các setter `setId`, `setFirstName`, `setEmailAddress`, các cột có thể được điền tự động. Đây là **đoạn mã tích hợp**, không phải chương trình độc lập; ví dụ chạy được từ đầu đến cuối xuất hiện ở phần sau.

## 2. Quy tắc ánh xạ tên: JavaBeans property, không phải tên field bất kỳ

`BeanPropertyRowMapper` dùng mô hình **JavaBeans writable properties**. Spring tìm các property có phương thức setter theo chuẩn JavaBeans và chuẩn bị các tên cột ứng viên cho từng property.

Ví dụ JavaBean:

```java
public class CustomerBean {
    private String firstName;
    private String emailAddress;

    public CustomerBean() {}

    public String getFirstName() {
        return firstName;
    }

    public void setFirstName(String firstName) {
        this.firstName = firstName;
    }

    public String getEmailAddress() {
        return emailAddress;
    }

    public void setEmailAddress(String emailAddress) {
        this.emailAddress = emailAddress;
    }
}
```

Đây là một JavaBean độc lập về mặt khai báo lớp, nhưng cần đặt trong tệp `CustomerBean.java` và sử dụng cùng Spring JDBC để chạy ánh xạ. Với property `firstName`, mapper mặc định nhận diện tên tương ứng dạng chữ thường như `firstname` hoặc tên tách bằng gạch dưới `first_name`. Với `emailAddress`, tên `emailaddress` hoặc `email_address` phù hợp.

Bảng quy tắc thường gặp:

| Thuộc tính JavaBeans | Setter cần có | Tên cột / SQL alias điển hình | Kết quả |
| --- | --- | --- | --- |
| `id` | `setId(...)` | `id`, `ID` | Khớp. |
| `firstName` | `setFirstName(...)` | `first_name`, `FIRST_NAME`, `firstName` | Khớp tên tương đương theo quy tắc mặc định. |
| `emailAddress` | `setEmailAddress(...)` | `email_address` | Khớp. |
| `createdAt` | `setCreatedAt(...)` | `created_at` | Khớp nếu kiểu có thể chuyển đổi. |
| `isActive` (tên field) | Tùy property thực tế | `is_active` | Không suy ra property tên `isActive` chỉ từ tên field; phải xét setter. |
| `departmentName` | `setDepartmentName(...)` | `department_name` | Khớp khi query chủ động cung cấp cột/alias đó. |

Đối với boolean, JavaBeans property thường là `active` khi có `isActive()` và `setActive(boolean)`. Khi đó SQL alias `active` là rõ ràng nhất; tên field nội bộ có thể là `isActive` nhưng field không phải nguồn sự thật của JavaBeans property.

**Điểm cần nhớ:** Mapper không đơn thuần tìm field trùng tên bằng reflection rồi set trực tiếp. Nó dựa trên property descriptors, chủ yếu là **setter công khai**, và dữ liệu phải có kiểu tương thích hoặc chuyển đổi được.

### Mapper xử lý chữ hoa/thường và gạch dưới như thế nào?

Cơ chế mặc định chuẩn bị các tên ứng viên cho property, gồm dạng lower-case và underscore-lower-case. Với `firstName`, hai dạng chính là `firstname` và `first_name`. Tên/label cột JDBC được chuẩn hóa về chữ thường trước khi tra cứu. Vì vậy các DB trả metadata `FIRST_NAME`, `first_name` hay `firstName` thường vẫn map được property `firstName`.

Điều này không có nghĩa mapper hiểu mọi biến thể tên. Một cột `given_name` **không tự map** sang `firstName`; một cột `customer_email` **không tự map** sang `emailAddress`; ký tự phân tách tùy tiện, prefix lạ hoặc tên viết tắt cũng không được suy luận theo ngữ nghĩa.

Khi quy ước không trùng, **SQL alias** là cách trực tiếp, đọc được và dễ bảo trì.

## 3. SQL alias và `columnLabel`: phương án chuẩn để đổi tên

Ví dụ tên cột thật `given_name` nhưng JavaBean có `firstName`:

```sql
SELECT
    customer_id AS id,
    given_name  AS first_name,
    mail_addr   AS email_address
FROM legacy_customer
WHERE customer_id = ?;
```

Mapper nhìn các **column labels** mà JDBC báo về (thường là alias khi query có `AS`), nên những nhãn `id`, `first_name` và `email_address` map vào các setter tương ứng.

Hình dung phép biến đổi:

```text
DB column: given_name
       |
SQL projection: given_name AS first_name
       |
ResultSetMetaData column label: first_name
       |
BeanPropertyRowMapper lookup: first_name -> firstName
       |
CustomerBean.setFirstName(value)
```

Không cần đổi schema database chỉ để trùng quy ước Java. Alias cũng hữu ích khi có `JOIN`:

```sql
SELECT
    c.id           AS id,
    c.full_name    AS full_name,
    d.name         AS department_name
FROM customer c
JOIN department d ON d.id = c.department_id
WHERE c.id = ?;
```

Giả sử target bean có `setId`, `setFullName`, `setDepartmentName`, mapper có thể điền ba property. Ngược lại, `SELECT c.*, d.*` dễ có nhãn trùng như `id`, `name` hoặc thuộc tính không nằm trong bean. Khi hai cột có cùng nhãn/nhãn quy về cùng property, không nên dựa vào “cột nào thắng” như một quy tắc nghiệp vụ; hãy **chọn cột tường minh và alias duy nhất**.

**Không phải alias nào cũng ngang nhau:** `AS first_name` đáng tin hơn `AS firstName` ở các DB có quy tắc chuyển chữ hoa/thường với identifier không trích dẫn. Với cột có dấu cách hoặc tên cần quote theo SQL dialect, nên alias về `snake_case` đơn giản.

## 4. Điều kiện để target class có thể được ánh xạ

### 4.1. JavaBean, không phải record bất biến

`BeanPropertyRowMapper<T>` đòi hỏi target class là top-level class hoặc **static nested class** và có **constructor mặc định không tham số** để mapper tạo instance; class cần các setter công khai cho thuộc tính muốn điền.

Ví dụ hợp lệ:

```java
public class ProductBean {
    private long id;
    private String productName;

    public ProductBean() {}

    public void setId(long id) {
        this.id = id;
    }

    public void setProductName(String productName) {
        this.productName = productName;
    }

    public long getId() {
        return id;
    }

    public String getProductName() {
        return productName;
    }
}
```

Mã này là định nghĩa lớp Java, đặt trong `ProductBean.java` khi sử dụng độc lập. Ngược lại, class chỉ có constructor nhận tham số và các field `final` thường **không hợp với BeanPropertyRowMapper** nếu không có JavaBeans setter tương ứng.

Ví dụ:

```java
// Không phải target thích hợp cho BeanPropertyRowMapper mặc định.
public record ProductView(long id, String productName) {}
```

Record không có no-arg constructor hay các setter đổi state. Với Java record, dùng `DataClassRowMapper` (phần 9) hoặc `RowMapper` tùy chỉnh.

### 4.2. Chỉ thuộc tính writable mới được điền

Một field có getter nhưng không có setter công khai **không tự động được gán** chỉ vì tên trùng. Các property thừa so với tập cột sẽ giữ giá trị sau constructor/initializer khi `checkFullyPopulated` ở mặc định `false`; các cột không khớp property thường được bỏ qua.

Ví dụ:

```java
// Minh họa: target có thêm trường displayName.
public class ProfileBean {
    private String firstName;
    private String displayName = "(unknown)";

    public ProfileBean() {}

    public void setFirstName(String value) {
        this.firstName = value;
    }

    public String getFirstName() {
        return firstName;
    }

    public String getDisplayName() {
        return displayName;
    }
}
```

`displayName` ở đây là read-only property, không có setter; mapper không thể gán nó trực tiếp qua cơ chế JavaBeans. Không nên suy ra rằng toàn bộ field của target đều được đồng bộ với SQL. Nếu muốn điền một thuộc tính, hãy thiết kế setter/cấu trúc target phù hợp hoặc dùng cách ánh xạ khác.

### 4.3. Dùng projection rõ ràng

Việc truy vấn chỉ một số cột là hợp lệ khi DTO/JavaBean đại diện cho **projection** đó:

```sql
SELECT id, display_name
FROM account
WHERE active = TRUE;
```

Nếu bean còn `createdAt`, `emailAddress` nhưng query không chọn, mặc định các thuộc tính đó **không tự xuất hiện** và giữ giá trị mặc định. Điều này có thể là mong muốn của projection, hoặc là lỗi dữ liệu bị bỏ sót. Hãy dùng DTO chuyên biệt khi contract chỉ cần hai trường thay vì tái sử dụng một bean quá rộng.

## 5. Cách viết `JdbcTemplate` với `BeanPropertyRowMapper`

Với một bean `CustomerBean` và một `JdbcTemplate` đã cấu hình:

```java
BeanPropertyRowMapper<CustomerBean> mapper =
    BeanPropertyRowMapper.newInstance(CustomerBean.class);

// Nhiều hàng, trả List.
List<CustomerBean> all = jdbc.query(
    "SELECT id, first_name, email_address " +
    "FROM customer WHERE active = ? ORDER BY id",
    mapper,
    true
);

// Đúng một hàng theo hợp đồng.
CustomerBean one = jdbc.queryForObject(
    "SELECT id, first_name, email_address " +
    "FROM customer WHERE id = ?",
    mapper,
    customerId
);
```

Đây là code minh họa trong repository với các biến `jdbc`, `customerId`, bean/table cần có; không phải chương trình độc lập.

Quan trọng:

- `query(...)` với `RowMapper<T>` tạo danh sách, có thể gồm 0, 1 hoặc nhiều bean.
- `queryForObject(...)` kỳ vọng đúng **một hàng**. Không có hàng thường ném `EmptyResultDataAccessException`; hơn một hàng ném `IncorrectResultSizeDataAccessException`. `BeanPropertyRowMapper` không thay đổi quy tắc số hàng.
- `BeanPropertyRowMapper` tạo đối tượng **mới cho từng hàng**; không hứa gộp nhiều hàng có cùng khóa thành một object.
- Nếu SQL trả thêm cột không cần, mapper có thể bỏ qua; không được đánh đồng với “đã map đầy đủ”.

Nếu dự án dùng JDBC SQL lặp đi lặp lại, có thể tạo một instance mapper chung cho một type và tái sử dụng: nó nắm metadata property sau khi cấu hình; không cần khởi tạo mapper mới ở mỗi lần lặp. Không thay đổi `setMappedClass`/`setCheckFullyPopulated`/conversion config trong khi các luồng cùng sử dụng mapper đã được chia sẻ.

## 6. Tùy chọn kiểm tra thiếu property: `checkFullyPopulated`

Mặc định:

```java
BeanPropertyRowMapper<CustomerBean> mapper =
    BeanPropertyRowMapper.newInstance(CustomerBean.class);
System.out.println(mapper.isCheckFullyPopulated()); // false
```

Khi `false`, nếu SQL không chọn một số cột tương ứng với writable properties, mapper thường vẫn tạo bean, để các property chưa ánh xạ giữ giá trị khởi tạo ban đầu. Hữu ích cho một số projection, nhưng cũng dễ che giấu việc query bị thiếu cột do sửa schema.

Để đòi hỏi **mọi writable property đã được ánh xạ**, bật chế độ strict:

```java
BeanPropertyRowMapper<CustomerBean> strict =
    BeanPropertyRowMapper.newInstance(CustomerBean.class);
strict.setCheckFullyPopulated(true);

CustomerBean customer = jdbc.queryForObject(
    "SELECT id, first_name, last_name, email_address, reward_points " +
    "FROM customer WHERE id = ?",
    strict,
    1L
);
```

Nếu target có năm writable property nhưng query chỉ chọn `id` và `first_name`, mapper strict có thể ném `InvalidDataAccessApiUsageException` vì những property còn lại không được điền. Nó kiểm tra **mức độ phủ của property có setter**, không đếm field vật lý hay bảo đảm một giá trị nghiệp vụ không-null.

**Không nên bật strict cho bean dùng nhiều projection khác nhau.** Một query thật sự chỉ cần `id` và `firstName` sẽ bị từ chối nếu bean có thêm setters. Khi strict không phù hợp, dùng DTO riêng hoặc mapper tường minh.

Cũng đừng hiểu strict là validation domain hoàn chỉnh:

- Nó không bắt buộc field `emailAddress` là email hợp lệ.
- Nó không bảo đảm `id` dương.
- Nếu cột được map nhưng giá trị SQL `NULL`, điều kiện “đã map property” vẫn cần xét **kiểu Java và nullability** riêng.
- Nó không đảm bảo truy vấn đúng một hàng; `query` có thể map nhiều bean bằng strict mapper.

## 7. SQL NULL, primitive và wrapper

Một giá trị SQL `NULL` có thể được ánh xạ thành Java `null` đối với property kiểu tham chiếu, chẳng hạn `String`, `Integer`, `Long`, `BigDecimal`. Tuy nhiên Java primitive `int`, `long`, `boolean` không chứa được `null`.

Ví dụ target:

```java
public class ScoreBean {
    private int score;

    public ScoreBean() {}

    public void setScore(int score) {
        this.score = score;
    }

    public int getScore() {
        return score;
    }
}
```

Nếu cột `score` trả SQL `NULL`, `BeanPropertyRowMapper` mặc định cố gọi setter với giá trị không tương thích và có thể ném `TypeMismatchException`. Đổi sang `Integer score` là cách giữ được phân biệt giữa **chưa có điểm** và **điểm số 0**.

Có tùy chọn:

```java
BeanPropertyRowMapper<ScoreBean> mapper =
    BeanPropertyRowMapper.newInstance(ScoreBean.class);
mapper.setPrimitivesDefaultedForNullValue(true);
```

Khi bật, mapper có thể **bỏ qua** việc gán primitive nếu cột có `NULL`, nên thuộc tính giữ giá trị có sẵn sau khi tạo object (thường là 0/false). Dùng tùy chọn này phải hết sức thận trọng: SQL `NULL` bị mất khác biệt so với giá trị thực 0/false; nếu ghi object trở lại DB, có nguy cơ thay `NULL` bằng giá trị mặc định ngoài ý muốn.

Cách chọn:

| Giá trị DB | Java type | Kết quả mong muốn |
| --- | --- | --- |
| `score = 15` | `int` hoặc `Integer` | 15. |
| `score = NULL` | `Integer` | `null`, bảo toàn ý nghĩa chưa có dữ liệu. |
| `score = NULL` | `int`, config mặc định | Lỗi chuyển giá trị sang primitive, giúp phát hiện mismatch. |
| `score = NULL` | `int`, default-for-null bật | Bỏ qua setter trong trường hợp này; giá trị primitive khởi tạo vẫn giữ nguyên. |

Đừng giải quyết mọi `NULL` bằng cách chuyển cột SQL thành `COALESCE(score, 0)` nếu 0 khác về nghĩa với NULL. Chỉ dùng khi luật nghiệp vụ xác nhận hai trường hợp tương đương.

## 8. Chuyển kiểu và giới hạn của auto-mapping

`BeanPropertyRowMapper` không chỉ gán `String` vào `String`: Spring có cơ chế đọc giá trị JDBC phù hợp với kiểu đích và dùng `ConversionService` (mặc định có `DefaultConversionService` trong nhiều phiên bản) để hỗ trợ nhiều kiểu thông thường như `Integer`, `Long`, `BigDecimal`, `Boolean` và một số kiểu ngày giờ.

Nhưng việc có một phương thức setter không bảo đảm mọi cặp SQL type/Java type đều chuyển được. Ví dụ:

- Driver trả `Timestamp` nhưng target dùng một type thời gian khác: cần xem JDBC driver, time zone và conversion behavior.
- Cột text chứa dữ liệu không phải số nhưng setter nhận `Integer`: có thể ném lỗi type conversion.
- Cột kiểu JSON/array/vendor-specific: thường cần truy xuất/converter chuyên biệt.
- Cột có giá trị ngoài miền của kiểu Java: có thể lỗi tràn hoặc chuyển đổi không phù hợp.
- Boolean và enum lưu dạng chuỗi/mã đặc thù: không tự suy diễn đúng semantics cho mọi database.

Có thể cấu hình:

```java
BeanPropertyRowMapper<CustomerBean> mapper =
    BeanPropertyRowMapper.newInstance(CustomerBean.class);
mapper.setConversionService(customConversionService);
```

Đây là ví dụ tích hợp vì cần `customConversionService` thuộc kiểu `org.springframework.core.convert.ConversionService` đã được cấu hình. Conversion service tùy chỉnh nên thể hiện quy tắc ổn định, có test và không biến dữ liệu bất hợp lệ thành giá trị mặc định một cách im lặng.

**Đặc biệt về annotation:** `BeanPropertyRowMapper` là công cụ Spring JDBC, **không phải JPA provider**. Các annotation như `@Entity`, `@Column(name = "db_name")` hay mapping quan hệ JPA không có tác dụng biến `db_name` thành tên JavaBeans property tùy ý trong mapper này. Nếu tên cột lệch, dùng alias SQL, thay target type hoặc tự viết `RowMapper`.

## 9. Khi dùng Java record, hãy chọn `DataClassRowMapper`

Một Java record là kiểu immutable, truyền dữ liệu qua constructor thay vì public setter:

```java
public record CustomerView(
    long id,
    String firstName,
    String emailAddress
) {}
```

`BeanPropertyRowMapper` thông thường không phù hợp vì record không có constructor không tham số và các setter. Spring JDBC có `DataClassRowMapper<T>` dành cho class có **constructor với các tham số có tên**, ví dụ Java record hoặc Kotlin data class:

```java
CustomerView customer = jdbc.queryForObject(
    "SELECT id, first_name, email_address " +
    "FROM customer WHERE id = ?",
    DataClassRowMapper.newInstance(CustomerView.class),
    customerId
);
```

Đây là đoạn tích hợp, cần bean/database và `jdbc`. `DataClassRowMapper` ánh xạ các tham số constructor như `firstName` qua tên cột `first_name`, đồng thời vẫn hỗ trợ setter đối với một số kiểu hỗn hợp. Nếu cả constructor và setter có thể nhận cùng property, constructor được ưu tiên để tránh gán trùng.

Đối với class bất biến thông thường có constructor tham số, việc ánh xạ theo tên cần **metadata tên tham số** có sẵn; với Java class thường, nên biên dịch với `-parameters`. Java record có thông tin thành phần record, nhưng cấu hình compiler ổn định giúp tránh bất ngờ khi đổi thành kiểu class khác.

Tương quan:

| Tiêu chí | `BeanPropertyRowMapper` | `DataClassRowMapper` | `RowMapper` tùy chỉnh |
| --- | --- | --- | --- |
| Kiểu target | JavaBean có no-arg constructor và setter | Record/data class/constructor parameters; có thể kết hợp setter | Bất kỳ object nào code tạo được |
| Quy tắc tên | Property name và underscore name | Constructor parameter/property name tương ứng | Do code tự định nghĩa |
| SQL alias | Nên dùng khi tên lệch | Nên dùng khi tên lệch | Có thể đọc tên cột theo ý muốn |
| Mapping phức tạp | Khả năng giới hạn | Khả năng giới hạn | Linh hoạt nhất |
| Tối ưu mapping trên đường nóng | Thuận tiện hơn là tối ưu tuyệt đối | Thuận tiện | Có thể tránh nhiều chi phí phản chiếu nếu viết hợp lý |

Không phải mọi DTO constructor nào cũng nên dùng `DataClassRowMapper`. Khi phép chuyển đổi cần logic nghiệp vụ, nested objects, quan hệ hoặc kiểm tra kỹ, mapper tùy chỉnh thường rõ ràng hơn.

## 10. Ví dụ hoàn chỉnh Java 17+: tên cột, alias, NULL, strict và record

Chương trình này dùng **Spring JDBC 6.1.14, H2 2.2.224, Java 17+ và Maven**. Không cần Spring Boot. Mục tiêu là quan sát:

1. Tên cột `first_name` đi vào setter `setFirstName`.
2. Tên cột `email_address` đi vào `setEmailAddress`.
3. SQL alias `chosen_name` đi vào `setChosenName` dù tên gốc là `first_name`.
4. SQL `NULL` được giữ như `null` ở property `String`/`Integer`.
5. `DataClassRowMapper` tạo record từ constructor.
6. `query(...)` trả hai bean cho hai hàng.
7. `checkFullyPopulated(true)` phát hiện thiếu các writable properties.

### Cấu trúc dự án

```text
bean-mapper-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── BeanMapperDemo.java
```

### File `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>learning</groupId>
    <artifactId>bean-mapper-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <maven.compiler.parameters>true</maven.compiler.parameters>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jdbc</artifactId>
            <version>6.1.14</version>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <version>2.2.224</version>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.3.0</version>
            </plugin>
        </plugins>
    </build>
</project>
```

### File `src/main/java/BeanMapperDemo.java`

```java
import java.util.List;

import org.springframework.dao.InvalidDataAccessApiUsageException;
import org.springframework.jdbc.core.BeanPropertyRowMapper;
import org.springframework.jdbc.core.DataClassRowMapper;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;

public class BeanMapperDemo {
    // Static nested class + public no-arg constructor.
    public static class CustomerBean {
        private long id;
        private String firstName;
        private String lastName;
        private String emailAddress;
        private Integer rewardPoints;

        public CustomerBean() {}

        public long getId() {
            return id;
        }

        public void setId(long id) {
            this.id = id;
        }

        public String getFirstName() {
            return firstName;
        }

        public void setFirstName(String firstName) {
            this.firstName = firstName;
        }

        public String getLastName() {
            return lastName;
        }

        public void setLastName(String lastName) {
            this.lastName = lastName;
        }

        public String getEmailAddress() {
            return emailAddress;
        }

        public void setEmailAddress(String emailAddress) {
            this.emailAddress = emailAddress;
        }

        public Integer getRewardPoints() {
            return rewardPoints;
        }

        public void setRewardPoints(Integer rewardPoints) {
            this.rewardPoints = rewardPoints;
        }
    }

    public static class LabelBean {
        private String chosenName;

        public LabelBean() {}

        public String getChosenName() {
            return chosenName;
        }

        public void setChosenName(String chosenName) {
            this.chosenName = chosenName;
        }
    }

    public record CustomerView(
            long id, String firstName, String emailAddress) {}

    public static void main(String[] args) {
        DriverManagerDataSource source = new DriverManagerDataSource();
        source.setDriverClassName("org.h2.Driver");
        source.setUrl("jdbc:h2:mem:bean_mapper;DB_CLOSE_DELAY=-1");
        source.setUsername("sa");
        source.setPassword("");

        JdbcTemplate jdbc = new JdbcTemplate(source);
        jdbc.execute(
            "CREATE TABLE customer (" +
            "id BIGINT PRIMARY KEY, " +
            "first_name VARCHAR(80) NOT NULL, " +
            "last_name VARCHAR(80), " +
            "email_address VARCHAR(120) NOT NULL, " +
            "reward_points INTEGER)"
        );

        jdbc.update(
            "INSERT INTO customer " +
            "(id, first_name, last_name, email_address, reward_points) " +
            "VALUES (?, ?, ?, ?, ?)",
            1L, "An", "Nguyen", "an@example.test", 15
        );
        jdbc.update(
            "INSERT INTO customer " +
            "(id, first_name, last_name, email_address, reward_points) " +
            "VALUES (?, ?, ?, ?, ?)",
            2L, "Binh", null, "binh@example.test", null
        );

        BeanPropertyRowMapper<CustomerBean> beanMapper =
            BeanPropertyRowMapper.newInstance(CustomerBean.class);

        String columns =
            "SELECT id, first_name, last_name, " +
            "email_address, reward_points " +
            "FROM customer WHERE id = ?";

        CustomerBean an = jdbc.queryForObject(
            columns, beanMapper, 1L
        );
        System.out.println(
            "Bean: " + an.getId() + " | " +
            an.getFirstName() + " " + an.getLastName() +
            " | " + an.getRewardPoints()
        );

        CustomerBean binh = jdbc.queryForObject(
            columns, beanMapper, 2L
        );
        System.out.println(
            "SQL NULL: lastName=" + (binh.getLastName() == null) +
            ", rewardPoints=" + (binh.getRewardPoints() == null)
        );

        LabelBean label = jdbc.queryForObject(
            "SELECT first_name AS chosen_name " +
            "FROM customer WHERE id = ?",
            BeanPropertyRowMapper.newInstance(LabelBean.class),
            1L
        );
        System.out.println("Alias: " + label.getChosenName());

        CustomerView record = jdbc.queryForObject(
            "SELECT id, first_name, email_address " +
            "FROM customer WHERE id = ?",
            DataClassRowMapper.newInstance(CustomerView.class),
            1L
        );
        System.out.println(
            "Record: " + record.id() + " | " +
            record.firstName() + " | " + record.emailAddress()
        );

        List<CustomerBean> all = jdbc.query(
            "SELECT id, first_name, last_name, " +
            "email_address, reward_points " +
            "FROM customer ORDER BY id",
            beanMapper
        );
        System.out.println("List size: " + all.size());

        BeanPropertyRowMapper<CustomerBean> strict =
            BeanPropertyRowMapper.newInstance(CustomerBean.class);
        strict.setCheckFullyPopulated(true);
        try {
            jdbc.queryForObject(
                "SELECT id, first_name FROM customer WHERE id = ?",
                strict, 1L
            );
            throw new AssertionError("Strict mapping should fail");
        } catch (InvalidDataAccessApiUsageException expected) {
            System.out.println(
                "Strict: missing writable properties detected"
            );
        }
    }
}
```

### Biên dịch và chạy

Trong thư mục chứa `pom.xml`, cần JDK 17+ và Maven:

```bash
mvn -q compile exec:java -Dexec.mainClass=BeanMapperDemo
```

Các dòng `System.out.println` của chương trình:

```text
Bean: 1 | An Nguyen | 15
SQL NULL: lastName=true, rewardPoints=true
Alias: An
Record: 1 | An | an@example.test
List size: 2
Strict: missing writable properties detected
```

Tùy môi trường, Maven và thư viện có thể in log riêng; những dòng đó không nằm trong phần output ứng dụng ở trên.

### Giải thích output

- Dòng `Bean` chứng minh các nhãn `FIRST_NAME`/`LAST_NAME` mà H2 có thể đưa qua metadata vẫn gán đúng `firstName`/`lastName`. `reward_points` map vào `Integer rewardPoints`.
- Dòng `SQL NULL` cho thấy `last_name` và `reward_points` của Binh đều là SQL `NULL`; hai property Java tham chiếu giữ `null`.
- Dòng `Alias` kiểm chứng `first_name AS chosen_name` map được vào setter `setChosenName` dù bean không có property `firstName`.
- Dòng `Record` cho thấy `DataClassRowMapper` ánh xạ qua record constructor với các tham số `id`, `firstName` và `emailAddress`; không cần setter.
- `List size: 2` minh họa `RowMapper` chạy cho từng hàng và `query` thu thập danh sách.
- Strict mapper nhận projection chỉ có `id` và `first_name` trong khi target còn writable properties `lastName`, `emailAddress` và `rewardPoints`. Nó ném `InvalidDataAccessApiUsageException`, được catch và in dòng cuối.

Ví dụ dùng `DriverManagerDataSource` đơn giản để chạy độc lập; implementation này **không phải connection pool** và không nên xem là cấu hình hiệu năng cho production. Chương trình không cần application context, `@Repository` hoặc `@Transactional` để minh họa cơ chế mapping.

## 11. So sánh mapper tự động với `RowMapper` viết tay

`BeanPropertyRowMapper` phù hợp khi kết quả SQL tương ứng trực tiếp với một bean đơn giản và quy tắc tên cột nhất quán. Nhưng nếu truy vấn có logic phức tạp, code mapper tường minh có thể tốt hơn.

Ví dụ có record kết quả với tên cột không khớp hoặc cần chuẩn hóa:

```java
public record PersonSummary(long id, String label) {}

// Đoạn minh họa trong ứng dụng có JdbcTemplate jdbc.
List<PersonSummary> people = jdbc.query(
    "SELECT user_id, first_name, last_name FROM legacy_user",
    (rs, rowNum) -> new PersonSummary(
        rs.getLong("user_id"),
        rs.getString("first_name") + " " +
        rs.getString("last_name")
    )
);
```

Đây là mã ví dụ, không tự chạy vì thiếu table, JdbcTemplate và file chứa type. Mapper viết tay làm rõ phép ghép nhãn. Nếu `last_name` có thể `NULL`, ví dụ trên còn cần quy tắc nghiệp vụ để tránh chuỗi `"null"`; hãy xử lý rõ bằng `rs.getString(...)`, điều kiện và chính sách domain thay vì mong BeanPropertyRowMapper tự suy luận.

Những trường hợp nên cân nhắc mapper tường minh:

- Query từ nhiều bảng mà một hàng phải xây dựng object lồng nhau theo logic riêng.
- JSON/array/enum/vendor-specific SQL type cần chuyển đổi có kiểm soát.
- Tên cột không đồng nhất, hoặc một property được tính từ **nhiều cột**.
- Validation/domain invariant phức tạp: ví dụ ngày bắt đầu phải trước ngày kết thúc.
- Đường xử lý nhạy cảm hiệu năng cần tránh một phần chi phí reflection/property binding.
- Model bất biến với constructor/record nhưng quy tắc mapping không giống tên tham số.

Dù viết mapper tay, mỗi lời gọi `mapRow` vẫn đại diện cho một hàng. Nếu cần **gộp nhiều hàng thành một cây object**, hãy thiết kế extractor/aggregation ở mức toàn `ResultSet` hoặc xây map theo khóa trong tầng truy cập dữ liệu. `BeanPropertyRowMapper` không tự giải quyết quan hệ một-nhiều.

## 12. Những lỗi thường gặp khi dùng quy tắc tên thuộc tính

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra và sửa |
| --- | --- | --- |
| `firstName` luôn `null` | SQL cột tên `given_name` nhưng bean chỉ có `setFirstName`. | `SELECT given_name AS first_name` hoặc custom mapper. |
| Field tồn tại nhưng vẫn không được điền | Không có writable JavaBeans property (setter công khai), hoặc class không phù hợp. | Xem `PropertyDescriptor` theo JavaBeans; thêm setter hoặc đổi mapper. |
| Bean không khởi tạo được | Chỉ có constructor tham số, hoặc non-static inner class. | Dùng top-level/static nested JavaBean có no-arg constructor; record dùng `DataClassRowMapper`. |
| `NULL` gây `TypeMismatchException` | Property là primitive như `int`/`boolean`. | Dùng wrapper `Integer`/`Boolean` nếu DB có NULL; không che mất NULL bằng default vô cớ. |
| SQL trả đủ hàng nhưng một số property bị bỏ trống | Query thiếu các cột đó; mặc định `checkFullyPopulated=false`. | Kiểm tra projection, dùng bean DTO phù hợp hoặc bật strict khi thật sự cần tất cả writable properties. |
| Strict mapper báo lỗi với projection hợp lệ | Target bean có nhiều setter hơn số cột select. | Tách projection DTO hoặc tắt strict có chủ đích. |
| SELECT có JOIN, property bị gán không rõ | Tên cột/alias bị trùng giữa bảng. | Projection tường minh và alias không trùng. |
| `@Column(name="...")` không tác động tới mapper | Annotation thuộc JPA, không phải quy tắc của Spring JDBC bean mapper. | SQL alias, DTO hoặc mapper riêng. |
| `queryForObject` ném `IncorrectResultSizeDataAccessException` | Truy vấn trả 0 hay trên 1 hàng, không phải lỗi tên property. | Phân biệt cardinality; dùng `query` nếu cần danh sách. |
| `BeanPropertyRowMapper` không tạo nested child | Mapper không tự gom nhiều hàng/nested mapping. | Custom `RowMapper` hoặc `ResultSetExtractor`/aggregation. |
| Sai kiểu ngày giờ, enum, JSON | JDBC value hoặc conversion service không đáp ứng quy tắc domain. | Kiểm tra driver/kiểu SQL và custom converter/mapper. |
| Dùng chung mapper rồi chỉnh cấu hình khi đang chạy nhiều thread | Mapping metadata và options có thể không còn nhất quán. | Cấu hình một lần, sau đó tái sử dụng như đối tượng đọc. |

## 13. Chiến lược test cho ánh xạ tự động

Một test tốt không chỉ xác nhận `id` được điền, mà phải kiểm tra các trường hợp dễ hỏng khi đổi SQL/schema:

1. **Quy tắc tên:** `first_name` → `firstName`; `email_address` → `emailAddress`; alias `chosen_name` → `chosenName`.
2. **Đủ và thiếu cột:** projection tường minh chỉ gồm một số property và strict mapping đòi hỏi tất cả writable properties.
3. **NULL:** `String`/`Integer` nhận null; primitive null ném lỗi ở cấu hình mặc định; kiểm tra nếu chủ động bật default-for-null.
4. **Constructor:** bean có no-arg/setters; record dùng `DataClassRowMapper`; class non-static inner không dùng như DTO thông thường.
5. **Kiểu dữ liệu:** số, boolean, time, enum hoặc converter đặc thù nếu domain sử dụng.
6. **Alias khi JOIN:** SQL có nhiều bảng với tên `id`, `name`; đảm bảo alias rõ ràng và không map nhầm.
7. **Cardinality:** không có hàng, một hàng và nhiều hàng khi gọi `queryForObject`; danh sách khi dùng `query`.
8. **Kiểm tra kết quả chứ không chỉ không ném lỗi:** assert chính xác từng property quan trọng, kể cả giá trị mặc định không mong muốn.

Ví dụ một assertion hữu ích trong unit/integration test:

```java
// Đoạn minh họa trong test đã có bean được map.
assertEquals("An", bean.getFirstName());
assertEquals("an@example.test", bean.getEmailAddress());
assertEquals(Integer.valueOf(15), bean.getRewardPoints());
```

Đây không phải test hoàn chỉnh; cần framework assertion (ví dụ JUnit), đối tượng `bean` và dữ liệu fixture. Với mapping JDBC, bài kiểm thử chạy trên database cùng dialect hoặc H2 fixture được thiết kế có chủ đích sẽ phát hiện nhiều vấn đề alias/case/type. H2 có thể khác PostgreSQL/MySQL/Oracle ở metadata tên cột và SQL type, vì vậy đường quan trọng nên kiểm tra thêm trên đúng database production.

## 14. Chọn mapper theo nhu cầu thực tế

Một hướng ra quyết định:

```text
Muốn map một hàng ResultSet sang object?
        |
        +-- JavaBean no-arg + public setters, tên cột tương ứng?
        |       |
        |       +-- Có, mapping đơn giản
        |             -> BeanPropertyRowMapper
        |             -> Alias SQL khi tên DB và property lệch
        |
        +-- Record / Kotlin data class / constructor parameters?
        |       -> DataClassRowMapper
        |
        +-- Giá trị cần biến đổi/nested/logic riêng?
        |       -> RowMapper viết tay hoặc extractor/aggregation phù hợp
        |
        +-- Nhiều hàng trong kết quả?
                -> query(...) hoặc API thu thập/stream thích hợp
                -> Không mong BeanPropertyRowMapper gộp nhiều hàng
```

Đối với dự án lớn, hãy giữ ranh giới:

- **SQL** quyết định dữ liệu nào được chọn và tên/alias của các cột đầu ra.
- **`RowMapper`** quyết định một hàng được chuyển thành object nào.
- **Repository API** quyết định trả một object, Optional hay danh sách.
- **Service/domain** quyết định invariants, validation và phép biến đổi nghiệp vụ.
- **Transaction manager** quyết định ranh giới giao dịch; mapper không thay thế nó.

Đặt việc biến đổi quá nhiều vào một bean setter có side effect cũng có thể gây khó đoán. Tốt hơn là giữ DTO đơn giản, đặt logic phức tạp ở tầng có contract rõ ràng và kiểm thử riêng.

## 15. Checklist trước khi đưa `BeanPropertyRowMapper` vào production

1. **Class phù hợp chưa?** Top-level hoặc static nested, khởi tạo được bằng constructor không tham số, có setter công khai cho các thuộc tính cần map.
2. **SQL projection có tường minh không?** Hạn chế `SELECT *`, đặc biệt khi có JOIN.
3. **Tên cột/alias có tương ứng JavaBeans property không?** Kiểm tra `camelCase` ↔ `snake_case`; dùng alias cho tên không tương ứng.
4. **Có nhãn cột trùng không?** Dùng alias duy nhất để tránh gán sai.
5. **Mỗi SQL NULL có type Java tương thích không?** Ưu tiên wrapper nếu DB cho phép NULL.
6. **Có property bị bỏ sót không?** Cân nhắc strict hoặc DTO dành riêng cho projection.
7. **Có annotation JPA mà bạn đang lầm tưởng mapper hiểu không?** `BeanPropertyRowMapper` không dựa vào JPA annotations.
8. **Loại object có bất biến không?** Record/constructor DTO nên dùng `DataClassRowMapper` hoặc custom mapper.
9. **Số hàng có đúng contract repository không?** Phân biệt `queryForObject` và `query`.
10. **Đã có test với tên, alias, NULL, conversion, nhiều hàng và database dialect thật chưa?**
11. **Ánh xạ tự động có đủ rõ ràng không?** Nếu phải xử lý nested/derived value phức tạp hoặc performance-critical, hãy ưu tiên mapper tường minh.

### Tóm tắt trọng tâm

- `BeanPropertyRowMapper<T>` tạo **một JavaBean cho một hàng ResultSet** và điền các **writable JavaBeans properties** bằng setter.
- Quy tắc tên điển hình: `first_name` hoặc `FIRST_NAME` khớp `firstName`; `email_address` khớp `emailAddress`. Nó không suy luận rằng `given_name` có cùng nghĩa với `firstName`.
- Khi tên cột khác tên property, **`SELECT db_column AS java_property_in_snake_case`** là cách chuyển đổi đơn giản và rõ ràng.
- JavaBean cần constructor không tham số và setter; **record** nên sử dụng `DataClassRowMapper` hoặc custom `RowMapper`.
- `checkFullyPopulated` mặc định `false`, nên thuộc tính thiếu có thể giữ giá trị mặc định; bật `true` khi cần xác nhận toàn bộ writable properties đã được map.
- SQL `NULL` map được thành `null` ở reference types; primitive null mặc định gây mismatch. Tránh bật chế độ primitive-default-for-null nếu điều đó làm mất ngữ nghĩa dữ liệu.
- `BeanPropertyRowMapper` không thay thế `JdbcTemplate`, cardinality handling, transaction, validation domain hay xử lý quan hệ nested.
- Khi automatic mapping khó giải thích hoặc nhạy cảm về hiệu năng, dùng `RowMapper` riêng; mã rõ ràng và đúng hợp đồng quan trọng hơn việc ít dòng code.

### Tài liệu tham khảo

- Spring Framework — `BeanPropertyRowMapper` Javadoc: https://docs.spring.io/spring-framework/docs/6.1.13/javadoc-api/org/springframework/jdbc/core/BeanPropertyRowMapper.html
- Spring Framework — `DataClassRowMapper` Javadoc: https://docs.spring.io/spring-framework/docs/6.1.13/javadoc-api/org/springframework/jdbc/core/DataClassRowMapper.html
- Spring Framework — JDBC querying: https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html
- Spring Framework — `JdbcTemplate` API: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/core/JdbcTemplate.html
- Java SE — JavaBeans introspection: https://docs.oracle.com/en/java/javase/17/docs/api/java.desktop/java/beans/Introspector.html
