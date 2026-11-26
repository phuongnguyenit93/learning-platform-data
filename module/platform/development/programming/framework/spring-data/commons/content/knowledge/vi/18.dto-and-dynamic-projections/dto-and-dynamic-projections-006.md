# Tên thuộc tính, alias và mapping kết quả theo store

## 1. Một giá trị có thể đi qua nhiều lớp tên

Khi một DTO nhận giá trị null hoặc không tạo được đối tượng, nguyên nhân thường nằm ở hợp đồng giữa query và bộ ánh xạ kết quả. Hai tên cùng chỉ “tên khách hàng” về mặt nghiệp vụ chưa chắc được framework xem là một.

Cần phân biệt bốn lớp tên:

| Lớp | Ví dụ | Nơi quyết định |
|---|---|---|
| Property domain | `Customer.fullName` | Mô hình Java |
| Tên lưu trữ | Cột hoặc field `full_name` | Schema, mapping và naming strategy |
| Tên đầu ra của query | Alias `display_name` hoặc `displayName` | SQL, JPQL, aggregation |
| Thành phần mô hình đọc | `displayName`, `getDisplayName()` | DTO, projection và mapper đích |

Một đường ánh xạ có thể là:

```text
Customer.fullName
        |
        | mapping domain
        v
customers.full_name
        |
        | query chọn dữ liệu và đặt alias
        v
display_name
        |
        | mapper của kiểu kết quả
        v
CustomerLabel.displayName
```

Mỗi mũi tên cần một quy tắc cụ thể. Spring Data Commons cung cấp abstraction projection dùng chung, nhưng module store quyết định cách đọc row, tuple hoặc document rồi tạo kết quả.

Bài này dùng cùng ý tưởng “nhãn khách hàng” để so sánh JPA, JDBC, R2DBC và MongoDB. Các ví dụ thuộc những cấu hình store riêng; không ghép các annotation cùng tên của chúng vào một entity.

## 2. Derived projection bắt đầu từ property domain

Giả sử domain `Customer` có:

| Property | Kiểu trong ví dụ relational |
|---|---|
| `id` | `Long` |
| `fullName` | `String` |
| `active` | `boolean` |

Với projection trực tiếp theo domain, có thể khai báo:

```java
public interface CustomerNameView {
    Long getId();
    String getFullName();
}
```

Hoặc một DTO:

```java
package example.readmodel;

public record CustomerName(Long id, String fullName) {
}
```

Một repository query tương ứng, khi store hỗ trợ đường projection đó:

```java
List<CustomerName> findByActiveTrueOrderByIdAsc();
```

Accessor `getFullName()` và tham số constructor `fullName` mô tả property `fullName`. Nếu property được lưu thành `full_name`, mapping domain chịu trách nhiệm chuyển tên.

Tên `displayName` không tự trở thành từ đồng nghĩa của `fullName`. DTO dưới đây có thể phù hợp với một query khai báo rõ, nhưng không tự khớp derived projection của domain trên:

```java
package example.readmodel;

public record CustomerLabel(Long customerId, String displayName) {
}
```

Commons mô tả việc interface accessor khớp property và việc DTO dùng tên tham số constructor để xác định dữ liệu đầu vào. Với class thường, cần giữ metadata tên tham số; với nhiều constructor, cần chọn constructor phù hợp. Xem [Commons — Projections](https://docs.spring.io/spring-data/commons/reference/repositories/projections.html).

Trong các phần sau, `CustomerName` là mô hình đọc giữ tên domain; `CustomerLabel` là mô hình đọc có tên đầu ra riêng.

## 3. JPA: alias cho interface và đối số cho DTO là hai hợp đồng

### 3.1. Interface đọc từ kết quả JPQL có alias

Một interface cho nhãn có thể khai báo:

```java
public interface CustomerLabelView {
    Long getCustomerId();
    String getDisplayName();
}
```

Trong repository JPA, query có thể tạo các tên đầu ra tương ứng:

```java
import java.util.List;

import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

// Phương thức trong repository của entity Customer.
@Query("""
        select c.id as customerId,
               c.fullName as displayName
        from Customer c
        where c.active = :active
        order by c.id
        """)
List<CustomerLabelView> loadLabelViews(
        @Param("active") boolean active);
```

`c.fullName` là property entity dùng trong JPQL. `displayName` là alias của phần tử được chọn, phục vụ getter `getDisplayName()`.

Đây là view của query khai báo rõ đầu ra. Nó không yêu cầu domain tự có property `displayName` để một derived query suy ra.

Spring Data JPA thường dùng `Tuple` để tạo interface projection. Vì vậy, khi query chọn nhiều biểu thức, tên đầu ra là một phần quan trọng của hợp đồng. Xem [JPA 3.5 — Projections](https://docs.spring.io/spring-data/jpa/reference/3.5/repositories/projections.html).

### 3.2. DTO trong JPQL constructor expression nhận đối số theo vị trí

Với record `example.readmodel.CustomerLabel` đã khai báo ở phần 2:

```java
@Query("""
        select new example.readmodel.CustomerLabel(
                c.id, c.fullName)
        from Customer c
        where c.active = :active
        order by c.id
        """)
List<CustomerLabel> loadLabelDtos(
        @Param("active") boolean active);
```

Lời gọi constructor có ý nghĩa:

```text
customerId  <- đối số thứ nhất: c.id
displayName <- đối số thứ hai: c.fullName
```

Constructor parameter `displayName` không cần là property của `Customer` trong biểu thức `new` đã viết rõ. Query cung cấp đối số trực tiếp.

Không viết:

```text
new example.readmodel.CustomerLabel(
    c.id as customerId,
    c.fullName as displayName)
```

JPQL constructor expression không dùng alias bên trong danh sách đối số. Việc đặt alias phù hợp với interface tuple không được sao chép nguyên sang `select new`.

Đặc biệt, khi hai đối số có cùng kiểu Java, đảo thứ tự có thể tạo DTO sai ý nghĩa dù query vẫn khớp chữ ký constructor. Tên tham số không biến biểu thức constructor thành lời gọi có named argument.

### 3.3. Alias không tự tạo phép chuyển đổi kiểu

Nếu query trả một số đếm nhưng DTO đòi một ngày giờ, đặt alias khớp tên không giải quyết được khác biệt kiểu. Cần chọn biểu thức, constructor hoặc converter đúng.

Tương tự, alias không thay đổi số hàng. Một join một-nhiều vẫn có thể tạo nhiều hàng cho một khách hàng. Hình dạng tên cột đúng chưa xác nhận cardinality của kết quả đúng nghiệp vụ.

## 4. JPA native SQL: kiểm tra column label và result-set mapping

### 4.1. Native SQL dùng tên lưu trữ thật

Với bảng `customers(id, full_name, active)`, một SQL cho interface trên có thể là:

```sql
select id as "customerId",
       full_name as "displayName"
from customers
where active = true
order by id;
```

Các SQL trong bài giả định cú pháp phù hợp PostgreSQL. Với dialect khác, cần điều chỉnh boolean literal và cách quote identifier.

Ở đây, `full_name` là cột vật lý. Alias được quote để thể hiện tên đầu ra có chữ hoa chữ thường mong muốn. Khi áp dụng, vẫn cần xem column label thực tế mà driver/provider cung cấp.

Không giả định mọi mapper đều chuyển mọi tên snake_case thành camelCase giống nhau. Một số đường có cơ chế hỗ trợ tên thay thế; đó không phải lý do bỏ qua hợp đồng kết quả của query đích.

### 4.2. Mapping constructor tường minh

Khi cần ánh xạ native result rõ ràng sang `CustomerLabel`, có thể dùng `@SqlResultSetMapping` của JPA. Ví dụ entity tối thiểu trong cấu hình JPA:

```java
import jakarta.persistence.Column;
import jakarta.persistence.ColumnResult;
import jakarta.persistence.ConstructorResult;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.SqlResultSetMapping;
import jakarta.persistence.Table;

@Entity
@Table(name = "customers")
@SqlResultSetMapping(
        name = "CustomerLabelMapping",
        classes = @ConstructorResult(
                targetClass = example.readmodel.CustomerLabel.class,
                columns = {
                        @ColumnResult(
                                name = "customer_id",
                                type = Long.class),
                        @ColumnResult(
                                name = "display_name",
                                type = String.class)
                }))
public class Customer {

    @Id
    private Long id;

    @Column(name = "full_name")
    private String fullName;

    private boolean active;

    protected Customer() {
    }
}
```

Annotation mapping đặt trên một entity được persistence unit quản lý, không chỉ gắn tùy ý lên DTO rồi mong provider tự phát hiện.

Repository có thể tham chiếu tên mapping bằng API `@NativeQuery` hỗ trợ thuộc tính đó:

```java
import java.util.List;

import example.readmodel.CustomerLabel;
import org.springframework.data.jpa.repository.NativeQuery;

@NativeQuery(
        value = """
                select id as customer_id,
                       full_name as display_name
                from customers
                where active = true
                order by id
                """,
        sqlResultSetMapping = "CustomerLabelMapping")
List<CustomerLabel> loadNativeLabels();
```

`@NativeQuery` có từ Spring Data JPA 3.4; Javadoc 3.5.4 công bố thuộc tính `sqlResultSetMapping`. Khi dùng phiên bản khác, cần đối chiếu đúng API thay vì sao chép annotation không có trong dependency. Xem [NativeQuery 3.5.4](https://docs.spring.io/spring-data/data-jpa/docs/3.5.4/api/org/springframework/data/jpa/repository/NativeQuery.html).

Thứ tự trong `@ConstructorResult.columns` phải tương ứng thứ tự tham số constructor. Các tên trong `@ColumnResult` tham chiếu cột đầu ra của SQL; chúng không cần giống tên field DTO. Xem [Jakarta Persistence — ConstructorResult](https://jakarta.ee/specifications/persistence/3.2/apidocs/jakarta.persistence/jakarta/persistence/ConstructorResult.html).

Ví dụ cố ý dùng alias snake_case và mapping rõ ràng:

```text
customer_id  -> đối số Long   -> customerId
display_name -> đối số String -> displayName
```

Đây là một lựa chọn khi cần kiểm soát mapping. Không phải mọi native DTO query đều bắt buộc dùng result-set mapping; khả năng ánh xạ trực tiếp còn phụ thuộc kết quả, kiểu và phiên bản đang dùng.

## 5. JDBC: SQL đầu ra phải phù hợp với RowMapper

Với Spring Data JDBC, query SQL khai báo phải trả các cột mà mapper của đường đọc cần. Tài liệu JDBC 3.5 lưu ý rằng các cột phục vụ constructor entity phải được cung cấp; không thể lấy một `select` tùy ý rồi coi mọi field chưa có là đã được điền đầy đủ.

Nếu cần mô hình đọc có tên riêng, một custom `RowMapper` giúp thể hiện chính xác hợp đồng:

```java
import java.sql.ResultSet;
import java.sql.SQLException;

import example.readmodel.CustomerLabel;
import org.springframework.jdbc.core.RowMapper;

public final class CustomerLabelRowMapper
        implements RowMapper<CustomerLabel> {

    @Override
    public CustomerLabel mapRow(ResultSet rs, int rowNum)
            throws SQLException {

        return new CustomerLabel(
                rs.getLong("customer_id"),
                rs.getString("display_name"));
    }
}
```

Ví dụ giả định `customer_id` khác null và tương thích kiểu `long`. Nếu cột có thể null, cần cách đọc giữ được trạng thái đó; `getLong` đơn thuần không đủ phân biệt SQL null với số không.

Phương thức repository JDBC:

```java
import java.util.List;

import example.readmodel.CustomerLabel;
import org.springframework.data.jdbc.repository.query.Query;

@Query(
        value = """
                select id as customer_id,
                       full_name as display_name
                from customers
                where active = true
                order by id
                """,
        rowMapperClass = CustomerLabelRowMapper.class)
List<CustomerLabel> loadJdbcLabels();
```

`RowMapper` chủ động đọc column label rồi gọi constructor. Tên tham số constructor không cần khớp alias vì mã Java đã chỉ rõ từng phép lấy giá trị.

JDBC 3.5 hỗ trợ chỉ định `rowMapperClass` hoặc tham chiếu bean mapper qua `rowMapperRef`. Lớp ở ví dụ có constructor mặc định công khai do không khai báo constructor riêng. Khi dùng mapper tùy chỉnh, cũng cần lưu ý lifecycle callback/event không chạy theo đường mapping entity thông thường. Xem [JDBC 3.5 — Query Methods](https://docs.spring.io/spring-data/relational/reference/3.5/jdbc/query-methods.html).

Điểm cần ghi nhớ là query và mapper phải thay đổi cùng nhau. Đổi alias từ `display_name` sang `name` mà giữ nguyên lời đọc `rs.getString("display_name")` làm đứt hợp đồng.

## 6. R2DBC: phân biệt derived DTO với DTO của @Query

Tài liệu R2DBC 3.5 nêu hai đường mapping khác nhau:

- Derived query dùng domain type làm cơ sở và DTO chỉ sử dụng property có trên domain.
- Query khai báo bằng chuỗi với `@Query` map kết quả trực tiếp vào DTO; field mapping của domain type không được áp dụng như ở đường derived.

Vì vậy, annotation `@Column` trên `Customer.fullName` không tự giải thích cách điền một DTO có property `displayName` khi DTO được map trực tiếp. Xem [R2DBC 3.5 — Result Mapping](https://docs.spring.io/spring-data/relational/reference/3.5/r2dbc/repositories.html#r2dbc.repositories.projections).

Có thể khai báo mapping trên chính DTO kết quả:

```java
import org.springframework.data.relational.core.mapping.Column;

public record R2dbcCustomerLabel(
        @Column("customer_id") Long customerId,
        @Column("display_name") String displayName) {
}
```

Query R2DBC trả đúng các tên cột đó:

```java
import org.springframework.data.r2dbc.repository.Query;
import reactor.core.publisher.Flux;

@Query("""
        select id as customer_id,
               full_name as display_name
        from customers
        where active = true
        order by id
        """)
Flux<R2dbcCustomerLabel> loadR2dbcLabels();
```

Ví dụ dùng record và metadata mapping của DTO. Với class thông thường, cần constructor và metadata tham số thích hợp để tạo đối tượng.

Naming strategy cũng ảnh hưởng tên cột được mong đợi nếu không khai báo rõ. R2DBC converter có quy ước tên và cho phép điều chỉnh bằng `NamingStrategy`; xem [R2DBC — Mapping](https://docs.spring.io/spring-data/relational/reference/r2dbc/mapping.html).

Ở ví dụ này, `Flux` biểu diễn cách phân phối kết quả reactive. Nó không sửa alias sai hoặc tự đổi tên property đầu vào cho DTO.

## 7. MongoDB: field lưu trữ và field đầu ra của pipeline

### 7.1. Mapping domain với @Field

Ví dụ MongoDB độc lập dùng ID chuỗi:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;

@Document("customers")
public class CustomerDocument {

    @Id
    private String id;

    @Field("full_name")
    private String fullName;
}
```

Document mẫu:

```json
{
  "_id": "C-41",
  "full_name": "Nguyễn An"
}
```

Property Java là `fullName`; tên field BSON là `full_name`. `@Field` mô tả liên hệ đó. `@Id` ánh xạ định danh trong ví dụ với `_id`. Xem [MongoDB — Object Mapping](https://docs.spring.io/spring-data/mongodb/reference/mongodb/mapping/mapping.html).

### 7.2. Typed aggregation có kiểu nguồn và kiểu đích riêng

DTO đầu ra:

```java
public record MongoCustomerLabel(
        String customerId,
        String displayName) {
}
```

Một typed aggregation có thể chọn và đổi tên field:

```java
import java.util.List;

import org.springframework.data.mongodb.core.aggregation.Aggregation;
import org.springframework.data.mongodb.core.aggregation.TypedAggregation;

TypedAggregation<CustomerDocument> aggregation =
        Aggregation.newAggregation(
                CustomerDocument.class,
                Aggregation.project()
                        .and("id").as("customerId")
                        .and("fullName").as("displayName")
                        .andExclude("_id"));

List<MongoCustomerLabel> labels =
        mongoTemplate
                .aggregate(aggregation, MongoCustomerLabel.class)
                .getMappedResults();
```

Typed aggregation biết kiểu nguồn để xử lý tham chiếu property theo mapping, gồm `@Field`. Pipeline chọn giá trị từ nguồn và tạo field đầu ra có tên phù hợp với DTO.

Hình dạng kết quả mong muốn:

```json
{
  "customerId": "C-41",
  "displayName": "Nguyễn An"
}
```

Đây là ví dụ định hướng mapping, không phải kết quả thực thi đã đọc từ một MongoDB cụ thể.

Ở đây, `@Field("full_name")` của domain giúp đọc nguồn; alias `displayName` do pipeline tạo giúp mô tả đầu ra. Hai việc xảy ra ở hai phía khác nhau của phép biến đổi.

Sau một bước project đổi tên, các bước sau phải dùng field còn tồn tại hoặc alias đã tạo. Không tiếp tục tham chiếu field cũ đã bị loại khỏi pipeline. Xem [MongoDB — Aggregation Framework Support](https://docs.spring.io/spring-data/mongodb/reference/mongodb/aggregation-framework.html#mongo.aggregation.projection).

Nếu đổi ID MongoDB sang `ObjectId`, phải đánh giá lại kiểu của `customerId` hoặc khai báo chuyển đổi tương ứng. Chỉ đặt alias giống nhau không làm kiểu BSON biến thành mọi kiểu Java mong muốn.

## 8. Projection động thay kiểu kết quả, không tự sửa query

Một query method có thể nhận kiểu projection:

```java
<T> List<T> findByActiveTrueOrderByIdAsc(Class<T> resultType);
```

Với đường query hỗ trợ, bên gọi có thể chọn:

```java
List<CustomerName> rows =
        repository.findByActiveTrueOrderByIdAsc(CustomerName.class);

List<CustomerNameView> views =
        repository.findByActiveTrueOrderByIdAsc(CustomerNameView.class);
```

Hai kiểu đều dựa trên `id` và `fullName` của domain. Cơ chế dynamic projection được mô tả tại [Commons — Dynamic Projections](https://docs.spring.io/spring-data/commons/reference/repositories/projections.html#projection.dynamic).

Không thay bằng `CustomerLabel.class` rồi kỳ vọng framework tự biết `customerId` lấy từ `id`, `displayName` lấy từ `fullName` trong derived query. Các tên khác nhau vẫn cần một đường mapping có căn cứ.

Tương tự, truyền `Class<T>` không biến một native SQL cố định thành bộ query hợp lệ cho mọi DTO. Query, kiểu dữ liệu và mapper vẫn phải tương thích với kiểu đã chọn.

## 9. Ma trận lựa chọn cách ánh xạ

| Đường đọc | Tên nào cần đối chiếu trước? | Cách xử lý khi muốn đổi tên đầu ra |
|---|---|---|
| Derived interface projection | Accessor với property domain | Giữ tên khớp hoặc chọn query/mapping rõ ràng |
| Derived DTO projection | Tham số constructor với property domain | Không tự coi tên khác là từ đồng nghĩa |
| JPA interface từ tuple | Alias kết quả với accessor | Đặt alias rõ cho từng biểu thức |
| JPA JPQL `select new` | Thứ tự, kiểu đối số và constructor | Chọn biểu thức đúng vị trí |
| JPA native DTO có mapping | Column label với `@ColumnResult`, rồi constructor | Khai báo result-set mapping khi cần |
| JDBC custom RowMapper | Column label mà mã mapper đọc | Đổi query và mapper cùng nhau |
| R2DBC @Query DTO | Kết quả row với metadata của DTO đích | Alias hoặc mapping trên DTO đích |
| Mongo typed aggregation | Property nguồn, field pipeline và metadata kiểu đích | Dùng projection/alias ở pipeline phù hợp |

Bảng mô tả các đường cụ thể, không phải danh sách bảo đảm cho mọi bản phát hành. Khi đổi store hoặc nâng phiên bản, cần đối chiếu reference và API của đúng bộ dependency thực tế.

Các annotation cùng tên cũng có thể thuộc package khác nhau:

```text
JPA Query:
org.springframework.data.jpa.repository.Query

JDBC Query:
org.springframework.data.jdbc.repository.query.Query

R2DBC Query:
org.springframework.data.r2dbc.repository.Query

MongoDB Query:
org.springframework.data.mongodb.repository.Query
```

Không dùng cùng một đoạn query cho các annotation này chỉ vì tên ngắn đều là `@Query`. Ngôn ngữ truy vấn và cơ chế mapping của chúng khác nhau.

## 10. Chẩn đoán kết quả thiếu hoặc sai dữ liệu

Nên bắt đầu từ chính một hàng hoặc document mẫu, rồi lần theo đường ánh xạ.

1. Xác định domain type, kiểu kết quả và query đang dùng.
2. Xem property nguồn cùng mapping cột/field lưu trữ.
3. Xác định dữ liệu thực tế mà query xuất ra: tên, thứ tự, kiểu và null.
4. Đối chiếu dữ liệu đó với tuple accessor, constructor hoặc mapper đích.
5. Kiểm tra một giá trị cụ thể đến đúng vị trí trong kết quả Java.

Các tình huống hữu ích khi áp dụng:

| Tình huống | Điều cần quan sát |
|---|---|
| Property `fullName` lưu thành `full_name` | Query đang dùng tên domain hay tên vật lý đúng ngữ cảnh |
| Getter `getDisplayName()` trả null | Alias/mapping có thật sự cung cấp `displayName` không |
| DTO đảo hai giá trị cùng kiểu | Thứ tự biểu thức hoặc lời gọi constructor có bị đảo không |
| Join trả hai cột cùng tên `id` | Đặt alias riêng, tránh column label mơ hồ |
| Giá trị là null | Phân biệt dữ liệu null thật với đầu vào projection bị thiếu |
| Số đếm hoặc số tiền sai kiểu | Xem kiểu runtime và quy tắc chuyển đổi, không chỉ alias |
| Native query đổi thứ tự cột | Mapping theo vị trí có còn khớp không |
| Mongo project đổi tên field | Bước pipeline sau dùng tên nào |
| Đổi DTO trong dynamic projection | Query cố định có còn cung cấp đủ dữ liệu không |
| Nâng phiên bản provider/driver | Column label và conversion có thay đổi không |

Nếu accessor trả `Optional.empty()`, chưa đủ để kết luận dữ liệu nguồn là null. Một tên đầu ra không được map đúng có thể tạo cùng triệu chứng ở một số đường xử lý.

Với join, nên chọn tên riêng như `customer_id` và `order_id` thay cho kết quả có nhiều cột `id` không phân biệt được. Với constructor, dùng dữ liệu mẫu có giá trị khác nhau để phát hiện lỗi đảo vị trí.

Những tình huống trên là nội dung thực hành cho ứng dụng đích; chúng không mô tả một bộ kiểm chứng đã được chạy cho dự án này.

## 11. Giữ hợp đồng tên khi thay đổi mô hình đọc

Một lần đổi tên có thể tác động đến nhiều vị trí: property domain, mapping lưu trữ, query khai báo, alias và DTO. Không phải vị trí nào cũng phải đổi cùng một tên, nhưng mối liên hệ giữa chúng phải tiếp tục rõ ràng.

Với màn hình cần `customerId` và `displayName`, có thể chọn DTO giữ tên domain rồi ánh xạ ở service, hoặc chọn query tạo đúng tên đầu ra. Lựa chọn phụ thuộc mức tái sử dụng, khả năng của store và chi phí duy trì mapping.

Thiết kế có thể bảo trì là thiết kế giải thích được mỗi giá trị đi từ đâu đến đâu. Alias chỉ là một mắt xích; đúng tên, đúng kiểu, đúng vị trí và đúng đường thực thi cùng tạo nên kết quả projection đáng tin cậy.
