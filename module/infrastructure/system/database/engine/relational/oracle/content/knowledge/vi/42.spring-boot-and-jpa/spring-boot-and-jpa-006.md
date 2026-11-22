# Chọn Oracle dialect theo phiên bản Hibernate và database

## 1. Oracle dialect trong Hibernate là gì?

Hibernate là ORM, chịu trách nhiệm chuyển thao tác Java/JPA thành SQL và ánh xạ kết quả SQL về entity. Cùng một thao tác như phân trang, sinh khóa, khóa dòng hoặc tạo DDL có thể cần SQL khác nhau giữa Oracle và các hệ quản trị cơ sở dữ liệu khác. Ngay trong Oracle, cú pháp và khả năng cũng thay đổi theo phiên bản database.

**Dialect** là thành phần Hibernate mô tả SQL và các đặc điểm riêng của một hệ quản trị cơ sở dữ liệu. Oracle dialect cung cấp cho Hibernate thông tin về:

- Cú pháp phân trang và giới hạn số dòng.
- Cách dùng sequence, identity column và sinh khóa.
- Kiểu dữ liệu JDBC/SQL và cách ánh xạ kiểu Java.
- Cú pháp `FOR UPDATE`, locking và các biểu thức SQL đặc thù.
- Hàm SQL, DDL, kiểu dữ liệu lớn và các khả năng do Oracle hỗ trợ.
- Các giới hạn/khả năng phụ thuộc phiên bản như độ dài identifier hoặc cú pháp mới.

Chọn dialect đúng giúp Hibernate sinh SQL phù hợp với database. Chọn dialect quá cũ có thể khiến Hibernate không sử dụng được khả năng của Oracle mới hoặc sinh SQL theo cú pháp cũ. Chọn dialect mới hơn khả năng database có thể dẫn đến SQL syntax error hoặc sử dụng tính năng mà server chưa hỗ trợ.

Dialect không phải JDBC driver. JDBC driver tạo kết nối, gửi SQL và chuyển dữ liệu giữa Java với Oracle. Dialect quyết định cách Hibernate tạo SQL và diễn giải khả năng của database. Hai thành phần phải tương thích với nhau nhưng giải quyết hai nhiệm vụ khác nhau.

## 2. Quan hệ giữa Hibernate version, Oracle version và JDBC driver

Khi cấu hình Spring Boot/JPA, cần xem xét đồng thời ít nhất ba phiên bản:

1. **Hibernate ORM version:** quyết định dialect class nào tồn tại và API dialect nào được hỗ trợ.
2. **Oracle Database version:** quyết định server hiểu cú pháp và hỗ trợ tính năng nào.
3. **Oracle JDBC driver version:** quyết định driver tương thích với JDK, cung cấp metadata database và hỗ trợ giao thức JDBC/XA nào.

Ngoài ra còn có Spring Boot version, Java version, Jakarta Persistence version và tham số `COMPATIBLE` của Oracle.

```text
Spring Boot dependency management
            |
            v
      Hibernate ORM version
            |
            v
   Oracle Dialect implementation
            |
            +------ JDBC DatabaseMetaData
            |                  |
            |                  v
            |          Oracle DB product/version
            v
       Generated SQL
            |
            v
    Oracle JDBC driver
            |
            v
      Oracle Database
```

Không thể chọn dialect chỉ bằng cách nhìn tên Oracle Database. Trước hết phải biết ứng dụng đang dùng Hibernate 5, 6 hay 7, vì tên class và cách Hibernate phát hiện phiên bản database đã thay đổi qua các major release.

## 3. Chọn dialect theo major version của Hibernate

### 3.1. Hibernate ORM 5.x

Trong Hibernate 5.x, Oracle có các dialect theo thế hệ database. Với các bản Hibernate 5.x hiện đại như 5.4/5.6, `Oracle12cDialect` thường được dùng cho Oracle 12c trở lên, bao gồm các release 18c và 19c:

```properties
spring.jpa.database-platform=org.hibernate.dialect.Oracle12cDialect
```

Hoặc cấu hình trực tiếp Hibernate property:

```properties
spring.jpa.properties.hibernate.dialect=org.hibernate.dialect.Oracle12cDialect
```

`Oracle12cDialect` là class thuộc API dialect của Hibernate 5.x. Không có lý do để tự tạo tên `Oracle19cDialect` nếu phiên bản Hibernate đang dùng không cung cấp class đó. Với Oracle 19c trên Hibernate 5.6, dialect Oracle 12c thường là lựa chọn phù hợp vì dialect đó đã mô tả các khả năng của thế hệ Oracle 12c trở lên.

Với database cũ hơn, các bản Hibernate 5 có thể còn các class như `Oracle10gDialect` hoặc dialect legacy tương ứng. Chỉ chọn chúng khi Oracle release thực tế và phiên bản Hibernate nằm trong phạm vi hỗ trợ. Không nên lấy một class cũ chỉ vì tên gần với phiên bản database; hãy kiểm tra danh sách dialect của đúng Hibernate artifact.

### 3.2. Hibernate ORM 6.x

Hibernate 6 chuẩn hóa hệ thống dialect hơn và sử dụng:

```text
org.hibernate.dialect.OracleDialect
```

Trong phần lớn cấu hình, Hibernate 6 có thể đọc `DatabaseMetaData` từ JDBC connection để nhận diện Oracle và phiên bản server, sau đó chọn hành vi phù hợp. Vì vậy, thường không cần đặt `hibernate.dialect` thủ công.

Nếu cần khai báo rõ dialect vì lý do triển khai hoặc metadata access bị giới hạn, dùng class được cung cấp trong chính Hibernate 6 đang chạy:

```properties
spring.jpa.database-platform=org.hibernate.dialect.OracleDialect
```

Các dialect cũ theo từng đời Oracle của Hibernate 5 đã bị loại bỏ, hợp nhất hoặc chuyển sang legacy/deprecated tùy major/minor release. Không sao chép cấu hình `Oracle12cDialect` của dự án Hibernate 5 sang Hibernate 6 nếu class không còn trong artifact.

### 3.3. Hibernate ORM 7.x

Hibernate 7 tiếp tục dùng dialect Oracle tổng quát:

```text
org.hibernate.dialect.OracleDialect
```

Ưu tiên để Hibernate tự phát hiện database version từ JDBC metadata, trừ khi có lý do kỹ thuật rõ ràng phải cấu hình dialect tường minh hoặc dùng custom dialect. Hỗ trợ một tính năng mới của Oracle còn phụ thuộc đúng minor release Hibernate; việc database có tính năng không có nghĩa Hibernate version đang dùng đã biết cách sinh SQL cho tính năng đó.

### 3.4. Bảng định hướng nhanh

| Hibernate ORM | Oracle dialect thường gặp | Ghi chú |
|---|---|---|
| Hibernate 5.x hiện đại | `org.hibernate.dialect.Oracle12cDialect` cho Oracle 12c/18c/19c | Kiểm tra class trong đúng phiên bản 5.x; database cũ có thể cần dialect legacy khác |
| Hibernate 6.x | `org.hibernate.dialect.OracleDialect` | Các dialect cũ theo version đã được hợp nhất/loại bỏ; ưu tiên auto-detection |
| Hibernate 7.x | `org.hibernate.dialect.OracleDialect` | Kiểm tra hỗ trợ tính năng theo minor release và JDBC driver |

Bảng trên là định hướng theo major version, không thay thế ma trận tương thích chính thức của Hibernate, Spring Boot, Oracle JDBC và Oracle Database. Nếu dự án dùng Hibernate 5.0/5.1 hoặc database rất cũ, hãy xem tài liệu đúng minor release thay vì áp dụng cấu hình của Hibernate 5.6.

## 4. Spring Boot chọn Hibernate version như thế nào?

### 4.1. Dependency management của Spring Boot

Spring Boot quản lý phiên bản Hibernate thông qua dependency management/BOM. Vì vậy, Spring Boot major/minor version thường quyết định Hibernate version mặc định được đưa vào ứng dụng.

Định hướng tổng quát:

| Spring Boot generation | Hibernate generation thường đi kèm | JPA namespace |
|---|---|---|
| Spring Boot 2.x | Hibernate 5.x | `javax.persistence` |
| Spring Boot 3.x | Hibernate 6.x | `jakarta.persistence` |
| Spring Boot 4.x | Hibernate 7.x theo dòng dependency được quản lý | `jakarta.persistence` |

Không nên suy ra chính xác Hibernate minor version chỉ từ major version Spring Boot. Các bản Spring Boot minor/patch có thể nâng Hibernate trong cùng major. Kiểm tra dependency thực tế của dự án trước khi đặt dialect.

### 4.2. Kiểm tra Hibernate version bằng Maven

```bash
mvn dependency:tree -Dincludes=org.hibernate.orm:hibernate-core,org.hibernate:hibernate-core
```

Trong Hibernate 5, artifact thường có tọa độ `org.hibernate:hibernate-core`; từ Hibernate 6, tọa độ chính là `org.hibernate.orm:hibernate-core`. Lệnh trên bao gồm cả hai để tránh bỏ sót.

### 4.3. Kiểm tra Hibernate version bằng Gradle

```bash
./gradlew dependencyInsight \
  --dependency hibernate-core \
  --configuration runtimeClasspath
```

Trên Windows có thể dùng `gradlew.bat` thay cho `./gradlew`. `dependencyInsight` cho biết version được resolve và dependency nào đã đưa version đó vào graph.

### 4.4. Không override Hibernate tùy tiện

Nếu Spring Boot BOM đã chọn Hibernate tương thích, không nên override riêng `hibernate-core` chỉ để dùng một dialect class hoặc tính năng mới. Override có thể làm lệch version giữa Hibernate core, community dialects, integration modules, JPA provider và các thư viện Spring.

Nếu thật sự cần nâng Hibernate ngoài BOM, phải kiểm tra migration guide, Jakarta Persistence compatibility, Java baseline, Spring integration và driver trước khi triển khai.

## 5. Cấu hình dialect trong Spring Boot

### 5.1. Trường hợp khuyến nghị: auto-detection

Với Hibernate 6/7 và Oracle JDBC driver có metadata phù hợp, cấu hình thường chỉ cần datasource:

```yaml
spring:
  datasource:
    url: jdbc:oracle:thin:@//db-host.example.com:1521/app_service
    username: app_user
    password: ${DB_PASSWORD}
    driver-class-name: oracle.jdbc.OracleDriver

  jpa:
    hibernate:
      ddl-auto: validate
```

Không cần thêm `spring.jpa.database-platform` nếu Hibernate đã tự nhận diện Oracle và phiên bản database. Đây là cách giảm nguy cơ đặt nhầm class dialect sau khi nâng Spring Boot/Hibernate.

Trong ví dụ, mật khẩu lấy từ environment/secret store; không commit credential vào source control. `ddl-auto: validate` chỉ yêu cầu Hibernate kiểm tra mapping/schema, không tự tạo hoặc sửa schema.

### 5.2. Cấu hình rõ dialect cho Hibernate 5.x

Ví dụ ứng dụng Spring Boot 2.x đang dùng Hibernate 5.6 và Oracle 19c:

```yaml
spring:
  datasource:
    url: jdbc:oracle:thin:@//db-host.example.com:1521/app_service
    username: app_user
    password: ${DB_PASSWORD}
    driver-class-name: oracle.jdbc.OracleDriver

  jpa:
    database-platform: org.hibernate.dialect.Oracle12cDialect
    hibernate:
      ddl-auto: validate
```

Hãy xác nhận class `Oracle12cDialect` tồn tại trong Hibernate 5.x thực tế của dự án. Nếu đã nâng lên Hibernate 6, cần bỏ/đổi cấu hình theo dialect API mới.

### 5.3. Cấu hình rõ dialect cho Hibernate 6/7

Nếu cần cấu hình tường minh:

```yaml
spring:
  jpa:
    database-platform: org.hibernate.dialect.OracleDialect
```

Trong đa số trường hợp auto-detection đã đủ. Chỉ cấu hình khi muốn kiểm soát rõ ràng hoặc có vấn đề với metadata. Nếu dùng custom dialect, class phải tương thích với Hibernate major version và được đặt trong classpath.

### 5.4. Chỉ chọn một nơi cấu hình

Hai cách cấu hình thường gặp:

```properties
spring.jpa.database-platform=org.hibernate.dialect.OracleDialect
```

và:

```properties
spring.jpa.properties.hibernate.dialect=org.hibernate.dialect.OracleDialect
```

`spring.jpa.database-platform` là thuộc tính Spring Boot để đặt database platform/dialect. `spring.jpa.properties.*` chuyển thuộc tính tương ứng xuống Hibernate. Không nên khai báo cả hai với hai giá trị khác nhau; việc trùng cấu hình khiến khó xác định giá trị cuối cùng và gây nhầm lẫn khi nâng cấp.

## 6. Hibernate phát hiện Oracle version bằng cách nào?

### 6.1. JDBC DatabaseMetaData

Khi khởi tạo SessionFactory/EntityManagerFactory, Hibernate có thể lấy metadata từ JDBC connection:

- Database product name, ví dụ `Oracle`.
- Database product version, ví dụ release Oracle đang chạy.
- JDBC driver name và version.
- Các khả năng JDBC mà driver báo cáo.

Ứng dụng có thể kiểm tra metadata độc lập:

```java
try (Connection connection = dataSource.getConnection()) {
    DatabaseMetaData metadata = connection.getMetaData();

    System.out.println(metadata.getDatabaseProductName());
    System.out.println(metadata.getDatabaseProductVersion());
    System.out.println(metadata.getDriverName());
    System.out.println(metadata.getDriverVersion());
}
```

Nếu metadata báo sai hoặc không truy cập được, Hibernate có thể không xác định được database version và dialect capabilities như mong muốn. Hãy kiểm tra driver, URL, quyền kết nối và log khởi tạo trước khi hard-code dialect.

### 6.2. Kiểm tra version trực tiếp trong Oracle

```sql
SELECT banner
FROM v$version
ORDER BY banner;
```

Hoặc nếu tài khoản có quyền truy vấn view phù hợp:

```sql
SELECT version
FROM product_component_version
WHERE product LIKE 'Oracle Database%';
```

Các view version có thể yêu cầu quyền data dictionary. Ứng dụng runtime không nên được cấp quyền quản trị chỉ để đọc version; DBA có thể cung cấp thông tin từ môi trường triển khai.

### 6.3. Database version khác COMPATIBLE

Oracle database release và tham số `COMPATIBLE` là hai thông tin khác nhau:

```sql
SELECT name, value
FROM v$parameter
WHERE name = 'compatible';
```

Database có thể chạy Oracle 19c nhưng giữ `COMPATIBLE` ở mức cũ trong giai đoạn nâng cấp. Dialect detection thường dựa trên JDBC metadata/database version; `COMPATIBLE` lại kiểm soát định dạng và khả năng database được phép sử dụng. Khi dựa vào tính năng mới như data type hoặc DDL mới, phải kiểm tra cả release lẫn `COMPATIBLE` và cấu hình thực tế.

Không đặt dialect cũ chỉ vì `COMPATIBLE` đang thấp hơn release binary, cũng không dùng tính năng mới chỉ vì `V$VERSION` báo release mới.

## 7. Những khả năng Oracle mà dialect ảnh hưởng

### 7.1. Pagination

Các release Oracle khác nhau có cú pháp phân trang khác nhau. Oracle 12c trở lên hỗ trợ row limiting clause:

```sql
SELECT order_id, order_date
FROM orders
ORDER BY order_date, order_id
OFFSET 20 ROWS FETCH NEXT 10 ROWS ONLY;
```

Oracle cũ hơn thường cần cách viết dựa trên `ROWNUM` hoặc truy vấn lồng. Hibernate dialect chịu trách nhiệm chọn chiến lược pagination phù hợp. Nếu dialect cho rằng database quá cũ, Hibernate có thể sinh SQL dạng cũ dù database mới hỗ trợ cú pháp mới; nếu dialect cho rằng database mới hơn thực tế, SQL có thể không chạy.

### 7.2. Sequence và identity column

Oracle hỗ trợ sequence từ lâu; identity column được bổ sung trong Oracle 12c. Với entity dùng sequence:

```java
@Entity
@Table(name = "ORDERS")
public class OrderEntity {
    @Id
    @SequenceGenerator(
        name = "order_seq_gen",
        sequenceName = "ORDER_SEQ",
        allocationSize = 50
    )
    @GeneratedValue(
        strategy = GenerationType.SEQUENCE,
        generator = "order_seq_gen"
    )
    private Long id;
}
```

Hibernate có thể dùng sequence và cơ chế allocation/optimizer để giảm số lần gọi sequence. Cấu hình `allocationSize` phải tương thích với increment của sequence thực tế và chiến lược Hibernate đang dùng. Nếu database schema do Flyway/Liquibase quản lý, phải đồng bộ sequence increment với mapping.

Với identity column:

```java
@Id
@GeneratedValue(strategy = GenerationType.IDENTITY)
private Long id;
```

Chỉ dùng khi database release/schema hỗ trợ identity và Hibernate dialect/driver biết cách lấy generated key. Với Oracle, sequence-based generation vẫn là lựa chọn phổ biến và có thể kiểm soát rõ ràng.

### 7.3. Identifier length và naming

Oracle có giới hạn độ dài identifier phụ thuộc release và mức `COMPATIBLE`. Những database cũ có giới hạn ngắn hơn so với Oracle 12.2 trở lên. Hibernate có thể dùng giới hạn dialect để tạo tên bảng, cột, index hoặc constraint.

Tên do naming strategy sinh ra quá dài có thể gây lỗi khi tạo schema hoặc migration. Không nên chỉ rút ngắn tên bằng cách sửa dialect; cần kiểm tra giới hạn Oracle thực tế và naming strategy của dự án.

### 7.4. Kiểu dữ liệu và biểu thức SQL

Dialect tham gia chọn kiểu SQL cho các kiểu Java/JDBC như:

- `String`, `BigDecimal`, `Long`, `Boolean`.
- `LocalDate`, `LocalDateTime`, `OffsetDateTime`.
- Binary data, `BLOB`, `CLOB`, `NCLOB`.
- JSON hoặc kiểu dữ liệu đặc thù nếu Hibernate version/Oracle release hỗ trợ.

Không phải mọi kiểu Java đều có một kiểu Oracle duy nhất. Ví dụ, `BigDecimal` có thể ánh xạ sang `NUMBER`; String dài có thể cần `CLOB`; timestamp có timezone có các semantics khác nhau. Hãy kiểm tra schema thực tế, annotation mapping và JDBC type được Hibernate chọn.

### 7.5. Locking và SQL đặc thù

Các thao tác JPA như `LockModeType.PESSIMISTIC_WRITE` có thể sinh `SELECT ... FOR UPDATE` với cú pháp/option phù hợp. Oracle có các quy tắc riêng về `NOWAIT`, `WAIT`, `SKIP LOCKED` và locking khi join/view. Dialect giúp Hibernate tạo SQL đúng, nhưng ứng dụng vẫn phải thiết kế transaction boundary và timeout phù hợp.

## 8. Chọn dialect khi nâng cấp Spring Boot/Hibernate

### 8.1. Từ Spring Boot 2/Hibernate 5 sang Spring Boot 3/Hibernate 6

Đây là thay đổi lớn vì Hibernate 6 chuyển từ `javax.persistence` sang `jakarta.persistence` và thay đổi dialect system.

Các việc cần làm:

1. Kiểm tra Hibernate version thực tế sau khi nâng BOM.
2. Tìm mọi cấu hình `Oracle12cDialect`, `Oracle10gDialect` hoặc dialect legacy trong properties/YAML/XML.
3. Với Hibernate 6, dùng `OracleDialect` hoặc bỏ cấu hình để auto-detect.
4. Chuyển import JPA từ `javax.persistence.*` sang `jakarta.persistence.*` theo yêu cầu Spring Boot 3.
5. Kiểm tra custom dialect, custom type, naming strategy và Hibernate extension vì API Hibernate 6 có thay đổi.
6. Chạy test SQL generation, pagination, sequence, identity, locking và schema validation.

Không chỉ đổi tên dialect rồi coi nâng cấp đã hoàn tất. Các thay đổi khác trong Hibernate 6 có thể ảnh hưởng SQL, type mapping và query behavior.

### 8.2. Từ Hibernate 6 sang Hibernate 7

Giữ nguyên nguyên tắc: dùng dialect Oracle tổng quát được Hibernate 7 cung cấp và ưu tiên metadata detection. Đọc migration guide của đúng minor release, kiểm tra custom dialect và các extension. Không mang một custom dialect được biên dịch cho Hibernate 5/6 sang Hibernate 7 mà không build/test lại.

### 8.3. Không chọn dialect theo Spring Boot version một cách máy móc

Spring Boot chỉ quản lý dependency. Nếu dự án override Hibernate hoặc dùng starter khác, version thực tế có thể khác với mặc định. Hãy xem dependency tree/runtime classpath và log bootstrap của Hibernate trước khi cấu hình.

## 9. Custom Oracle dialect

### 9.1. Khi nào cần custom dialect?

Chỉ nên tạo custom dialect khi có nhu cầu thực sự như:

- Một kiểu dữ liệu/SQL function đặc thù của ứng dụng chưa được dialect chuẩn hỗ trợ.
- Cần đăng ký function hoặc type bổ sung theo API Hibernate version đang dùng.
- Có khác biệt giữa Oracle deployment và behavior mặc định mà không thể giải quyết bằng mapping/configuration chuẩn.

Không tạo custom dialect chỉ để đổi một câu SQL đơn lẻ nếu có thể dùng JPQL, native query hoặc function registration phù hợp.

### 9.2. Khung custom dialect cho Hibernate 6/7

Ví dụ khái quát:

```java
package com.example.persistence;

import org.hibernate.dialect.OracleDialect;

public class ApplicationOracleDialect extends OracleDialect {
    public ApplicationOracleDialect() {
        super();
        // Register application-specific behavior using the API
        // supported by the exact Hibernate major/minor version.
    }
}
```

Đăng ký:

```properties
spring.jpa.database-platform=com.example.persistence.ApplicationOracleDialect
```

Đây chỉ là khung minh họa; API đăng ký function/type thay đổi giữa Hibernate major version. Không copy code override method từ Hibernate 5 vào Hibernate 6/7 vì class/method signature có thể đã thay đổi.

### 9.3. Tránh override behavior chuẩn nếu không cần

Khi custom dialect override pagination, sequence, type mapping hoặc locking, có thể vô tình làm mất các cải tiến mà Hibernate cung cấp cho Oracle release mới. Chỉ override phần cần thiết, viết integration test với Oracle thật hoặc môi trường tương thích, và ghi rõ lý do custom behavior tồn tại.

## 10. JDBC driver và tương thích

### 10.1. Chọn ojdbc theo Java runtime

Oracle cung cấp nhiều JDBC driver artifact. Ví dụ thường gặp:

| Artifact | Môi trường Java thường nhắm tới | Ghi chú |
|---|---|---|
| `ojdbc8` | Java 8 trở lên theo ma trận driver tương ứng | Dùng khi runtime cần driver tương thích Java 8 |
| `ojdbc11` | Java 11 trở lên theo ma trận driver tương ứng | Thường dùng cho ứng dụng chạy Java 11+ |

Không chọn driver chỉ theo Oracle Database version. Kiểm tra Oracle JDBC download/support matrix để chọn driver tương thích với JDK, Oracle Database release, application server và các tính năng cần dùng. Driver mới hơn có thể kết nối database cũ trong phạm vi Oracle hỗ trợ; không có quy tắc phải dùng đúng số release trùng database.

### 10.2. Dependency Maven minh họa

```xml
<dependency>
    <groupId>com.oracle.database.jdbc</groupId>
    <artifactId>ojdbc11</artifactId>
    <version>${oracle.jdbc.version}</version>
    <scope>runtime</scope>
</dependency>
```

Đặt version theo ma trận hỗ trợ và dependency management của tổ chức. Không dùng version placeholder chưa được định nghĩa trong project; ví dụ này minh họa cấu trúc dependency.

### 10.3. Dependency Gradle minh họa

```kotlin
runtimeOnly("com.oracle.database.jdbc:ojdbc11:$oracleJdbcVersion")
```

Nếu dùng Spring Boot dependency management, kiểm tra BOM và cấu hình override có chủ đích. Tránh đưa nhiều bản `ojdbc` vào runtime classpath vì class loading có thể chọn nhầm driver.

### 10.4. Driver version và dialect version không cần giống nhau

Ví dụ Oracle 19c có thể được truy cập bằng `ojdbc11` phù hợp với JDK 17 và Hibernate 6. Không có yêu cầu dialect phải mang tên `Oracle19cDialect` hay driver phải có version number trùng `19`.

Hibernate nhận diện database qua JDBC metadata và dùng dialect implementation để sinh SQL. Driver chịu trách nhiệm giao tiếp. Chọn từng thành phần theo ma trận tương thích riêng của chúng.

## 11. Kiểm tra dialect đang được dùng

### 11.1. Xem log bootstrap

Khi khởi tạo Hibernate, bật log phù hợp để quan sát thông tin dialect và database metadata. Tùy Hibernate version, logger/message có thể khác nhau; tìm các thông tin:

- Database product/version mà JDBC metadata báo.
- Dialect class Hibernate đã resolve.
- JDBC driver name/version.
- Cảnh báo về dialect class deprecated, không tồn tại hoặc không hỗ trợ database version.

Không bật log bind parameter ở mức TRACE trong production nếu chưa kiểm soát dữ liệu nhạy cảm; log có thể ghi giá trị parameter chứa thông tin cá nhân hoặc bí mật.

### 11.2. Kiểm tra SQL sinh ra

Trong môi trường development/test:

```yaml
logging:
  level:
    org.hibernate.SQL: DEBUG
```

Đối với Hibernate 6, logger bind parameter thường là `org.hibernate.orm.jdbc.bind`; Hibernate 5 có logger khác, ví dụ `org.hibernate.type.descriptor.sql.BasicBinder`. Chỉ bật khi cần điều tra và tránh log dữ liệu nhạy cảm.

Quan sát các câu SQL quan trọng:

- Pagination có dùng cú pháp Oracle phù hợp không?
- Sequence/identity có được gọi đúng không?
- DDL và identifier có vượt giới hạn Oracle không?
- Kiểu `TIMESTAMP`, `NUMBER`, `CLOB`/`BLOB` có mapping đúng không?
- `FOR UPDATE`, generated keys và batch insert có hành vi mong đợi không?

### 11.3. Kiểm tra schema bằng validate

Với schema được quản lý bằng Flyway/Liquibase, cấu hình:

```yaml
spring:
  jpa:
    hibernate:
      ddl-auto: validate
```

Hibernate sẽ kiểm tra mapping với schema hiện có theo khả năng hỗ trợ; nó không thay thế kiểm thử migration hoặc kiểm tra mọi ràng buộc nghiệp vụ. Không dùng `ddl-auto: create` hoặc `update` trên production chỉ để thử dialect.

## 12. Các lỗi thường gặp khi chọn sai dialect

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| `ClassNotFoundException`/không resolve dialect | Cấu hình class thuộc Hibernate major khác hoặc artifact không có class đó | Kiểm tra Hibernate version và dialect class trong runtime JAR |
| SQL syntax error gần `FETCH FIRST`/`OFFSET` | Dialect sinh cú pháp không phù hợp release hoặc `COMPATIBLE` | Kiểm tra Oracle version, metadata và dialect resolution |
| Hibernate dùng pagination kiểu cũ | Dialect/metadata nhận diện database quá cũ hoặc cấu hình dialect legacy | Xem log metadata và class dialect thực tế |
| Identity/generated key lỗi | Database/dialect/driver không thống nhất về identity support | Kiểm tra Oracle release, mapping và driver generated-key support |
| Sequence allocation không khớp | `allocationSize` không đồng bộ với sequence increment/optimizer | Kiểm tra sequence DDL và generator mapping |
| Identifier quá dài | Tên do naming strategy sinh vượt giới hạn database/COMPATIBLE | Kiểm tra giới hạn Oracle và naming strategy |
| Kiểu dữ liệu bị đổi hoặc không validate | Hibernate dialect/type mapping khác version hoặc schema không tương thích | Kiểm tra JDBC type, column definition và migration |
| Warning về dialect class deprecated | Cấu hình class legacy trong Hibernate mới | Bỏ cấu hình để auto-detect hoặc chuyển sang dialect hiện hành |
| Không lấy được metadata | JDBC driver, connection hoặc quyền/metadata access có vấn đề | Kiểm tra driver, datasource và cấu hình bootstrap |

Không sửa lỗi bằng cách đổi dialect ngẫu nhiên. Hãy đọc exception SQL, log Hibernate, database version và SQL thực tế để xác định nguồn sai lệch.

## 13. Quy trình chọn Oracle dialect cho dự án mới hoặc nâng cấp

1. Xác định Oracle Database release thực tế bằng `V$VERSION` hoặc thông tin DBA cung cấp.
2. Kiểm tra `COMPATIBLE` và các feature mà ứng dụng cần dùng.
3. Xác định Spring Boot version và Hibernate ORM version được resolve trong runtime classpath.
4. Kiểm tra JDK version và chọn Oracle JDBC driver phù hợp theo ma trận hỗ trợ.
5. Với Hibernate 5.x hiện đại và Oracle 12c/18c/19c, kiểm tra `Oracle12cDialect` có trong artifact và dùng đúng phiên bản nếu cấu hình thủ công.
6. Với Hibernate 6/7, ưu tiên auto-detection; nếu cần khai báo, dùng `org.hibernate.dialect.OracleDialect`.
7. Không khai báo hai dialect properties mâu thuẫn; không tự tạo tên `Oracle19cDialect` nếu Hibernate không cung cấp.
8. Chạy integration test với Oracle release mục tiêu: pagination, sequence, identity, DDL, type mapping, locking, batch và generated keys.
9. Dùng `ddl-auto: validate` và migration tool để kiểm soát schema; không dựa vào schema auto-update ở production.
10. Kiểm tra log dialect/metadata, theo dõi warning và lưu lại bộ phiên bản Boot, Hibernate, JDK, ojdbc, Oracle release/RU và COMPATIBLE.

## 14. Nguyên tắc cần ghi nhớ

- Dialect mô tả cách Hibernate sinh SQL cho database; JDBC driver thực hiện giao tiếp JDBC.
- Chọn dialect theo Hibernate major version trước, rồi đối chiếu Oracle Database release và khả năng driver.
- Hibernate 5.x hiện đại thường dùng `Oracle12cDialect` cho Oracle 12c trở lên, gồm cả 19c.
- Hibernate 6/7 dùng `OracleDialect`; ưu tiên để Hibernate tự phát hiện version từ JDBC metadata.
- Không mặc định tồn tại `Oracle19cDialect`; kiểm tra class trong artifact thực tế.
- Spring Boot BOM quyết định Hibernate version mặc định; dùng dependency tree để xác nhận thay vì suy đoán.
- Oracle Database release và tham số `COMPATIBLE` là hai thông tin khác nhau; kiểm tra cả hai khi dùng feature mới.
- Chọn `ojdbc` theo JDK, Oracle release và ma trận hỗ trợ; driver version không cần trùng tên dialect.
- Sau khi đổi dialect/nâng Hibernate, kiểm tra SQL pagination, sequence/identity, type mapping, locking và DDL trên Oracle thật.
- Chỉ tạo custom dialect khi cần; custom API phải được viết theo đúng Hibernate major/minor version.

## Tài liệu tham khảo

- [Hibernate ORM User Guide — Dialects](https://docs.hibernate.org/orm/6.6/userguide/html_single/Hibernate_User_Guide.html#database-dialect)
- [Hibernate ORM 5.6 User Guide](https://docs.jboss.org/hibernate/orm/5.6/userguide/html_single/Hibernate_User_Guide.html)
- [Hibernate ORM 6 Migration Guide](https://docs.hibernate.org/orm/6.0/migration-guide/)
- [Hibernate ORM 7 User Guide](https://docs.hibernate.org/orm/7.0/userguide/html_single/Hibernate_User_Guide.html)
- [Spring Boot Reference Documentation — Data Access](https://docs.spring.io/spring-boot/reference/data/sql.html)
- [Oracle JDBC Developer's Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/jjdbc/)
- [Oracle Database 19c SQL Language Reference](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/)
