# Ánh xạ bảng và schema bằng @Table

## 1. Vai trò của @Table trong Spring Data R2DBC

Spring Data R2DBC ánh xạ đối tượng Java thành các hàng trong relational database thông qua metadata và naming convention. Annotation `@Table` cho framework biết một class được ánh xạ tới bảng nào và, khi cần, nằm trong schema nào.

`@Table` thuộc package:

```java
import org.springframework.data.relational.core.mapping.Table;
```

Đây là annotation của Spring Data Relational, được dùng chung cho các module relational như Spring Data JDBC và Spring Data R2DBC. Không nhầm nó với `jakarta.persistence.Table` của JPA. Một ứng dụng R2DBC nên dùng annotation thuộc `org.springframework.data.relational.core.mapping`.

Ví dụ đơn giản:

```java
@Table("customer")
public class Customer {

    @Id
    private Long id;

    private String email;
    private String displayName;
}
```

Class `Customer` được ánh xạ tới bảng `customer`. Các thao tác repository hoặc `R2dbcEntityTemplate` dùng metadata này để xác định bảng khi tạo SQL.

`@Table` có thể được dùng không kèm tên:

```java
@Table
public class Customer {
    @Id
    private Long id;
    private String email;
}
```

Khi không chỉ định tên, Spring Data sử dụng `NamingStrategy` để suy ra tên bảng từ class. Cách suy ra cụ thể phụ thuộc naming strategy và identifier processing của phiên bản đang dùng.

## 2. @Table là metadata mapping, không phải lệnh tạo bảng

`@Table` mô tả cách Spring Data tìm bảng khi đọc hoặc ghi entity. Annotation không tự tạo schema, bảng, index, constraint hay sequence.

Ví dụ:

```java
@Table(value = "customer", schema = "crm")
public class Customer {
    @Id
    private Long id;
    private String email;
}
```

Đoạn code này yêu cầu mapping tới bảng `crm.customer` theo cách database/dialect biểu diễn identifier. Nó không tương đương với DDL:

```sql
CREATE SCHEMA crm;

CREATE TABLE crm.customer (
    id BIGINT PRIMARY KEY,
    email VARCHAR(255) NOT NULL
);
```

DDL cần được quản lý bằng migration như Flyway, Liquibase hoặc quy trình schema deployment của dự án. Khi đổi `@Table` từ tên cũ sang tên mới, cần có migration tương ứng để bảng thật tồn tại.

## 3. Các thuộc tính của @Table

Trong Javadoc Spring Data Relational hiện hành, annotation có ba thuộc tính chính:

| Thuộc tính | Ý nghĩa |
| --- | --- |
| `value` | Tên bảng |
| `name` | Alias của `value` để chỉ tên bảng |
| `schema` | Schema (hoặc user/schema tương ứng theo database) chứa bảng |

`value` và `name` là hai cách viết thay thế nhau cho tên bảng. `schema` xác định namespace đứng trước tên bảng.

### 3.1. Dùng value

Đây là cách viết ngắn thường gặp:

```java
@Table("purchase_order")
public class PurchaseOrder {
    @Id
    private Long id;
}
```

Tương đương:

```java
@Table(value = "purchase_order")
public class PurchaseOrder {
    @Id
    private Long id;
}
```

### 3.2. Dùng name

Các phiên bản có thuộc tính `name` cho phép viết:

```java
@Table(name = "purchase_order")
public class PurchaseOrder {
    @Id
    private Long id;
}
```

`name` là alias của `value`, không phải tên một trường khác trong database. Để code dễ đọc và tương thích với các ví dụ phổ biến, có thể dùng `value`.

### 3.3. Dùng schema

Để ánh xạ tới một bảng trong schema cụ thể:

```java
@Table(value = "purchase_order", schema = "sales")
public class PurchaseOrder {
    @Id
    private Long id;
}
```

Schema là namespace của bảng. Khi schema được chỉ định, Spring Data dùng nó làm prefix cho tên bảng theo quy tắc render identifier của dialect.

### 3.4. Chỉ định schema, để tên bảng theo convention

Có thể chỉ định schema nhưng vẫn để Spring Data suy ra tên bảng:

```java
@Table(schema = "sales")
public class PurchaseOrder {
    @Id
    private Long id;
}
```

Tên bảng được suy ra từ class theo `NamingStrategy`, còn schema được cố định là `sales`.

### 3.5. Không chỉ định schema

Nếu bỏ `schema`, Spring Data sử dụng schema mặc định theo `NamingStrategy.getSchema()` nếu strategy cung cấp, hoặc để database áp dụng schema mặc định của connection/user.

Ví dụ:

```java
@Table("customer")
public class Customer {
    @Id
    private Long id;
}
```

Tên bảng không có nghĩa là luôn nằm trong schema `public`. Schema mặc định có thể là `public` trong PostgreSQL, `dbo` trong SQL Server, schema/user mặc định ở Oracle hoặc database/schema đã chọn trong MySQL. Hãy xác nhận cấu hình user và database thực tế.

## 4. Phân biệt table, schema, database và catalog

Các khái niệm này có quan hệ nhưng không đồng nghĩa:

- **Table:** đối tượng lưu các hàng dữ liệu.
- **Schema:** namespace dùng để nhóm và định danh bảng, view, sequence hoặc object khác.
- **Database:** đơn vị database được server quản lý và connection thường chọn khi kết nối.
- **Catalog:** lớp namespace cấp cao hơn trong một số hệ quản trị và API metadata.

Tên gọi và cấu trúc khác nhau giữa database:

| Hệ quản trị | Ví dụ cách hiểu |
| --- | --- |
| PostgreSQL | Một database chứa nhiều schema; schema mặc định thường là `public` |
| SQL Server | Database chứa schema; schema mặc định của nhiều user là `dbo` |
| MySQL | `SCHEMA` thường được dùng đồng nghĩa với `DATABASE` |
| Oracle | Schema gắn với user; Javadoc `@Table` cũng đề cập trường hợp schema/user |
| H2 | Database có thể chứa nhiều schema |

`@Table.schema` dùng để xác định schema namespace theo abstraction của Spring Data. Nó không thay đổi host, port, database/catalog mà `ConnectionFactory` đã kết nối tới. Với MySQL, cần đặc biệt phân biệt database được chọn trong connection với cách driver/dialect render tên schema.

Nếu muốn chuyển sang một database khác, phải cấu hình `ConnectionFactory`/R2DBC URL tương ứng. Không thể chỉ thay `@Table(schema = ...)` để chuyển server hoặc database connection.

## 5. Cách Spring Data suy ra tên bảng

Khi không cung cấp tên trong `@Table`, Spring Data dùng `NamingStrategy`.

Naming strategy mặc định tách các phần camel case bằng dấu gạch dưới. Ví dụ:

| Tên Java | Tên logic được suy ra |
| --- | --- |
| `Customer` | `customer` |
| `PurchaseOrder` | `purchase_order` |
| `SavingsAccount` | `savings_account` |
| `OrderLineItem` | `order_line_item` |

Chữ hoa/thường cuối cùng và cách quote identifier phụ thuộc dialect và cấu hình mapping. Tài liệu mapping của các phiên bản có thể mô tả kết quả render khác nhau do thay đổi identifier processing.

Ví dụ:

```java
@Table
public class SavingsAccount {
    @Id
    private Long id;
    private String accountNumber;
}
```

Spring Data suy ra tên bảng từ class và tên cột từ property. Trong convention camel case, `accountNumber` được chuyển thành tên logic `account_number`.

### 5.1. Tên bảng lấy từ class đơn giản

Tên bảng mặc định dựa trên tên class đơn giản, không phải toàn bộ package name. Hai class ở package khác nhau nhưng có cùng simple name có thể tạo xung đột nếu cùng mapping context và cùng naming strategy.

Trong trường hợp đó, dùng `@Table` để chỉ định tên rõ ràng:

```java
@Table("billing_customer")
public class Customer {
    @Id
    private Long id;
}
```

### 5.2. Tên cột không được đặt bằng @Table

`@Table` chỉ định table/schema. Nếu tên property không khớp tên cột vật lý, dùng `@Column`:

```java
@Table("customer")
public class Customer {

    @Id
    private Long id;

    @Column("display_name")
    private String displayName;
}
```

Ở đây `@Table` chọn bảng `customer`; `@Column` ánh xạ property `displayName` tới cột `display_name`.

## 6. Ánh xạ một entity vào schema cụ thể

Ví dụ entity nằm trong schema `crm`:

```java
package com.example.customer;

import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Column;
import org.springframework.data.relational.core.mapping.Table;

@Table(value = "customer", schema = "crm")
public class Customer {

    @Id
    private Long id;

    @Column("email_address")
    private String email;

    @Column("display_name")
    private String displayName;

    protected Customer() {
    }

    public Customer(String email, String displayName) {
        this.email = email;
        this.displayName = displayName;
    }

    public Long getId() {
        return id;
    }

    public String getEmail() {
        return email;
    }

    public String getDisplayName() {
        return displayName;
    }
}
```

Repository:

```java
import org.springframework.data.repository.reactive.ReactiveCrudRepository;

public interface CustomerRepository
        extends ReactiveCrudRepository<Customer, Long> {
}
```

Schema/table cần tồn tại trong database:

```sql
CREATE SCHEMA crm;

CREATE TABLE crm.customer (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    email_address VARCHAR(255) NOT NULL,
    display_name VARCHAR(150)
);
```

Đây là DDL minh họa theo cú pháp PostgreSQL. Database khác có thể dùng cú pháp identity/auto increment và schema khác nhau.

Khi gọi:

```java
customerRepository.findById(10L);
```

Spring Data dùng metadata entity để tạo thao tác trên bảng đã khai báo. Tên schema/table trong SQL thực tế được render theo dialect.

## 7. Ánh xạ nhiều bảng cùng tên ở các schema khác nhau

Một database có thể có nhiều schema, mỗi schema chứa bảng cùng tên. Ví dụ schema `crm` và `archive` đều có bảng `customer`.

Có thể khai báo hai entity riêng:

```java
@Table(value = "customer", schema = "crm")
public class CurrentCustomer {
    @Id
    private Long id;
    private String email;
}

@Table(value = "customer", schema = "archive")
public class ArchivedCustomer {
    @Id
    private Long id;
    private String email;
}
```

Hai entity đại diện cho hai bảng vật lý khác nhau:

- `crm.customer`.
- `archive.customer`.

Có thể dùng repository riêng:

```java
public interface CurrentCustomerRepository
        extends ReactiveCrudRepository<CurrentCustomer, Long> {
}

public interface ArchivedCustomerRepository
        extends ReactiveCrudRepository<ArchivedCustomer, Long> {
}
```

Việc đặt tên class rõ nghĩa giúp tránh nhầm dữ liệu đang hoạt động với dữ liệu lưu trữ. Cả hai entity vẫn dùng chung các annotation mapping của Spring Data Relational.

## 8. Schema mặc định bằng NamingStrategy

Nếu phần lớn entity nằm trong cùng một schema, có thể cung cấp `NamingStrategy` bean thay vì lặp lại schema trong mọi annotation.

Ví dụ:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.relational.core.mapping.NamingStrategy;

@Configuration
class RelationalNamingConfiguration {

    @Bean
    NamingStrategy namingStrategy() {
        return new NamingStrategy() {
            @Override
            public String getSchema() {
                return "app";
            }
        };
    }
}
```

Với strategy này, schema mặc định cho mapping là `app`. Entity có thể chỉ định table:

```java
@Table("customer")
public class Customer {
    @Id
    private Long id;
}
```

Nếu entity có `@Table(schema = "audit")`, schema được chỉ định trực tiếp trên annotation sẽ được dùng cho entity đó. Javadoc `@Table` mô tả rằng schema annotation được dùng làm schema của table; khi không khai báo, Spring Data có thể lấy default schema từ `NamingStrategy.getSchema()`.

### 8.1. Tùy chỉnh table name bằng NamingStrategy

Ngoài schema, `NamingStrategy` có thể thay đổi cách suy ra tên bảng/cột. Ví dụ:

```java
@Configuration
class RelationalNamingConfiguration {

    @Bean
    NamingStrategy namingStrategy() {
        return new NamingStrategy() {

            @Override
            public String getSchema() {
                return "app";
            }

            @Override
            public String getTableName(Class<?> type) {
                return NamingStrategy.super.getTableName(type);
            }
        };
    }
}
```

Ví dụ trên giữ quy tắc table name mặc định và chỉ đặt schema mặc định. Có thể override `getTableName` để áp dụng prefix hoặc quy ước riêng, nhưng cần bảo đảm naming strategy ổn định và không tạo xung đột giữa entity.

### 8.2. NamingStrategy và @Table phối hợp

Có thể hiểu:

- `NamingStrategy` cung cấp quy tắc mặc định cho mapping context.
- `@Table(value = ...)` ghi đè tên bảng cho một entity.
- `@Table(schema = ...)` ghi đè schema cho một entity.
- Nếu thuộc tính không được chỉ định, framework có thể dùng metadata/naming strategy mặc định.

Không nên tạo nhiều quy tắc naming khác nhau một cách ngẫu nhiên. Hãy giữ quy ước tên nhất quán giữa entity, DDL và migration.

## 9. Quote identifier và chữ hoa/chữ thường

Identifier là tên bảng/schema/cột. Database có thể chuyển chữ hoa/thường của identifier không được quote hoặc xem identifier được quote là phân biệt chữ hoa/chữ thường.

Spring Data R2DBC dùng `R2dbcDialect` và identifier processing để render identifier. Dấu quote có thể khác nhau theo database:

| Database | Dấu quote identifier thường gặp |
| --- | --- |
| PostgreSQL | Dấu nháy kép `"` |
| MySQL | Backtick |
| SQL Server | Ngoặc vuông hoặc dấu nháy kép khi cấu hình phù hợp |
| H2 | Dấu nháy kép |

Ví dụ tên bảng:

```sql
-- PostgreSQL
SELECT * FROM "purchase_order";

-- MySQL: tên identifier được bao bằng backtick
SELECT * FROM `purchase_order`;

-- SQL Server
SELECT * FROM [purchase_order];
```

Đây là cú pháp native minh họa. Ứng dụng dùng Spring Data thường để dialect render identifier khi framework tạo SQL.

### 9.1. Quote behavior phụ thuộc phiên bản

Không nên giả định mọi phiên bản Spring Data Relational có cùng mặc định quote identifier:

- Tài liệu Spring Data Relational 3.5 mô tả `forceQuote` cho R2DBC là tắt mặc định trong phần `@Column`.
- Tài liệu mapping Spring Data Relational 4.1 mô tả tên bảng/cột suy ra từ class/property được render bằng quote theo database mặc định; có thể tắt bằng `R2dbcMappingContext.setForceQuote(false)` hoặc dùng `R2dbcMappingContext.forPlainIdentifiers()`.

Vì vậy, khi nâng version, hãy đọc mapping reference đúng release train do Spring Boot BOM quản lý và xác nhận SQL thực tế được sinh. Đừng dựa vào hành vi quote của một phiên bản cũ để thiết kế schema cho phiên bản mới.

### 9.2. Tắt quote khi cần plain identifiers

Tài liệu Spring Data Relational hiện hành mô tả khả năng tạo mapping context dùng plain identifiers:

```java
R2dbcMappingContext.forPlainIdentifiers(...);
```

Hoặc cấu hình context với:

```java
context.setForceQuote(false);
```

Đây là các API cấu hình mapping context; cách override bean/context cụ thể phụ thuộc phiên bản Spring Data R2DBC và cấu hình ứng dụng. Chỉ tắt quote khi schema được đặt tên theo quy tắc identifier không quote của database và không dựa vào reserved keyword hoặc ký tự đặc biệt.

### 9.3. Tránh tên cần quote

Nên ưu tiên:

- Chữ thường.
- Tên đơn giản.
- `snake_case`.
- Không chứa dấu cách hoặc dấu câu đặc biệt.
- Không trùng reserved keyword.

Ví dụ dùng `purchase_order` thay cho `order`. Tên đơn giản giúp DDL, native query, migration và công cụ quản trị nhất quán hơn.

## 10. Tên bảng trùng từ khóa SQL

Nếu schema cũ có bảng tên `order`, việc quote identifier phụ thuộc dialect và cấu hình mapping.

Ví dụ PostgreSQL:

```sql
CREATE TABLE sales."order" (
    id BIGINT PRIMARY KEY,
    status VARCHAR(30) NOT NULL
);
```

Entity:

```java
@Table(value = "order", schema = "sales")
public class PurchaseOrder {
    @Id
    private Long id;
    private String status;
}
```

Phải kiểm tra cách Spring Data render tên `order` trong phiên bản đang dùng. Nếu identifier processing không quote đúng như DDL, query có thể lỗi cú pháp.

Giải pháp dài hạn tốt hơn là đổi tên vật lý thành `purchase_order` qua migration khi có thể. Không dựa vào quote để hợp thức hóa tên bảng khó dùng trong mọi công cụ.

## 11. @Table và @Column phối hợp

`@Table` chọn bảng/schema; `@Column` chọn tên cột. Ví dụ:

```java
@Table(value = "customer_profile", schema = "crm")
public class CustomerProfile {

    @Id
    private Long id;

    @Column("first_name")
    private String firstName;

    @Column("last_name")
    private String lastName;

    @Column("email_address")
    private String email;
}
```

Mapping:

| Java property | Database object |
| --- | --- |
| Entity `CustomerProfile` | `crm.customer_profile` |
| `id` | `id` |
| `firstName` | `first_name` |
| `lastName` | `last_name` |
| `email` | `email_address` |

Annotation `@Column` có thể làm tên cột khác property name. Quy tắc quote của tên cột cũng phụ thuộc `R2dbcMappingContext` và dialect.

## 12. @Table với aggregate và bảng con

Spring Data Relational tổ chức mapping theo aggregate. Aggregate root là entry point cho thao tác persistence; các object con hoặc collection có thể được lưu ở bảng riêng theo mapping metadata.

Ví dụ:

```java
@Table(value = "purchase_order", schema = "sales")
public class PurchaseOrder {

    @Id
    private Long id;

    private String orderNumber;

    @MappedCollection(idColumn = "order_id")
    private List<OrderLine> lines;
}

public class OrderLine {
    private String productCode;
    private Integer quantity;
}
```

`@Table` xác định bảng aggregate root. `@MappedCollection` điều khiển cách ánh xạ collection và cột tham chiếu tới ID của root. Nó không phải annotation thay thế `@Table` cho root.

Nếu cần tùy chỉnh tên bảng hoặc cột của cấu trúc con, kiểm tra mapping metadata và quy tắc tên của Spring Data Relational phiên bản đang dùng. `@Table` không tự tạo foreign key hoặc DDL cho các quan hệ này.

### 12.1. Không nhầm với JPA relationship

Spring Data Relational không phải JPA/Hibernate. Không thể suy luận rằng chỉ cần đặt `@Table` trên hai class và thêm `@OneToMany` là R2DBC tự tạo join/lazy loading như ORM.

Spring Data Relational dùng mô hình aggregate và mapping riêng. Cần thiết kế schema, foreign key và thao tác load/save theo quy tắc relational mapping.

## 13. @Table và repository scanning

`@Table` đánh dấu class là candidate cho relational mapping. Annotation cũng giúp metadata scanning phát hiện và tiền xử lý domain type.

Ví dụ:

```java
@Table("invoice")
public class Invoice {
    @Id
    private Long id;
}
```

Repository:

```java
public interface InvoiceRepository
        extends ReactiveCrudRepository<Invoice, Long> {
}
```

Trong một số cấu hình mapping, POJO có thể được ánh xạ theo convention ngay cả khi không có `@Table`. Tuy nhiên, dùng annotation cho entity giúp mapping metadata rõ ràng và hỗ trợ classpath scanning. Đặc biệt khi ứng dụng có nhiều Spring Data modules, hãy bảo đảm repository được nhận diện với đúng store.

Nếu repository không được tạo:

- Kiểm tra package được scan.
- Kiểm tra annotation cấu hình repository R2DBC nếu dùng cấu hình thủ công.
- Kiểm tra domain type có metadata phù hợp.
- Kiểm tra dependency Spring Data R2DBC có trên classpath.

## 14. @Table không tự sửa native SQL

Một điểm quan trọng: `@Table` được dùng bởi mapping metadata khi Spring Data tạo thao tác persistence. Nó không viết lại mọi câu SQL do lập trình viên tự viết.

Ví dụ repository native query:

```java
public interface CustomerRepository
        extends ReactiveCrudRepository<Customer, Long> {

    @Query("SELECT * FROM crm.customer WHERE email_address = :email")
    Mono<Customer> findByEmail(String email);
}
```

Trong câu `@Query` trên, tên bảng `crm.customer` đã được viết trực tiếp. Nếu đổi annotation thành:

```java
@Table(value = "client", schema = "crm")
public class Customer {
    @Id
    private Long id;
}
```

native query không tự động đổi thành `crm.client`. Phải sửa câu SQL thủ công hoặc dùng API mapping phù hợp.

Tương tự, `DatabaseClient.sql("SELECT ... FROM ...")` thực thi SQL do ứng dụng cung cấp. `@Table` không thay thế tên bảng trong raw SQL.

## 15. Schema trong nhiều môi trường

Một ứng dụng có thể chạy local, test, staging và production với schema khác nhau:

| Môi trường | Schema ví dụ |
| --- | --- |
| Local | `app_dev` |
| Test | `app_test` |
| Staging | `app_staging` |
| Production | `app` |

Nếu schema khác nhau theo môi trường, có thể dùng cấu hình migration và `NamingStrategy` phù hợp cho mỗi profile.

Ví dụ:

```java
@Configuration
class MappingConfiguration {

    @Bean
    NamingStrategy namingStrategy(
            @Value("#{environment.getProperty('app.database.schema', 'app')}") String schema) {

        return new NamingStrategy() {
            @Override
            public String getSchema() {
                return schema;
            }
        };
    }
}
```

Ví dụ này dùng schema mặc định từ cấu hình. Cần bảo đảm bean `NamingStrategy` được Spring Data R2DBC auto-configuration sử dụng và schema tương ứng đã được migration tạo trước khi ứng dụng chạy.

Không đặt schema theo giá trị request tùy ý. Schema là identifier, không phải bind parameter thông thường. Nếu có nhiều tenant, dùng tenant routing/connection strategy được thiết kế rõ ràng, kiểm tra allowlist và quyền database.

## 16. Schema-per-tenant và giới hạn của annotation tĩnh

Một số hệ thống lưu mỗi tenant trong một schema riêng, ví dụ:

- `tenant_a.customer`.
- `tenant_b.customer`.

Nếu schema cố định cho từng entity, `@Table(schema = ...)` phù hợp. Nhưng nếu schema thay đổi theo request/tenant, một annotation tĩnh trên class không đủ để tự động chọn schema theo người dùng hiện tại.

Các hướng thiết kế có thể cân nhắc:

1. Mỗi tenant hoặc nhóm tenant có `ConnectionFactory`/mapping context riêng.
2. Routing connection chọn database/schema đã được xác thực trước khi query.
3. Database session đặt schema/search path theo connection một cách an toàn.
4. Dùng tính năng expression/schema động chỉ khi phiên bản Spring Data đang dùng hỗ trợ rõ ràng và context resolution được kiểm soát.

Một số phiên bản `@Table` hỗ trợ value expression cho tên bảng/schema. Khả năng, cache behavior và cơ chế sanitize thay đổi theo phiên bản. Nếu expression trả về `SqlIdentifier`, Javadoc hiện hành ghi nhận identifier được dùng trực tiếp mà không qua sanitize thêm. Vì vậy, không tạo `SqlIdentifier` từ chuỗi do người dùng gửi.

Đối với multi-tenancy, hãy kiểm tra connection pool và transaction context: một connection đã được gán tenant A không được tái sử dụng cho tenant B khi session schema/search path chưa được reset.

## 17. Quyền truy cập schema

Ngay cả khi mapping đúng, query vẫn có thể lỗi nếu database user không có quyền truy cập schema hoặc table.

Ví dụ PostgreSQL:

```sql
GRANT USAGE ON SCHEMA crm TO app_user;
GRANT SELECT, INSERT, UPDATE, DELETE
ON TABLE crm.customer
TO app_user;
```

Nếu dùng sequence hoặc identity sequence có quyền riêng theo database, kiểm tra quyền tương ứng. DDL migration thường chạy bằng migration user có quyền cao hơn runtime user; không mặc định runtime user có quyền tạo schema/table.

Các lỗi thường gặp:

- Schema không tồn tại.
- Table không tồn tại trong schema đã chọn.
- User không có quyền USAGE/SELECT/INSERT.
- Connection đang trỏ tới database khác.
- Schema mặc định hoặc search path khác với môi trường local.

Khi chẩn đoán, kiểm tra cả SQL đã render và database user/connection thực tế.

## 18. Dùng migration để đồng bộ @Table với schema

Khi đổi mapping:

```java
@Table(value = "customer", schema = "crm")
public class Customer {
    @Id
    private Long id;
}
```

migration phải tạo đúng bảng:

```sql
CREATE SCHEMA IF NOT EXISTS crm;

CREATE TABLE IF NOT EXISTS crm.customer (
    id BIGINT PRIMARY KEY
);
```

Nếu đổi từ bảng `public.customer` sang `crm.customer`, migration cần:

- Tạo schema `crm`.
- Tạo hoặc chuyển dữ liệu sang bảng mới.
- Tạo index/constraint.
- Cấp quyền cho runtime user.
- Kiểm tra view, trigger, foreign key và job phụ thuộc.
- Chuyển application mapping.
- Có kế hoạch rollback hoặc compatibility trong thời gian rollout.

Không chỉ thay annotation rồi cho rằng dữ liệu cũ tự di chuyển.

### 18.1. Tên schema trong migration và mapping phải khớp

Các lỗi chính tả hoặc khác biệt case có thể gây lỗi khó tìm:

```text
@Table(schema = "CRM", value = "customer")
Migration: CREATE TABLE crm.customer ...
```

Nếu database phân biệt case khi identifier được quote, `CRM` và `crm` có thể là hai schema khác nhau. Dùng quy ước chữ thường và nhất quán.

## 19. Kiểm thử mapping @Table

Một integration test nên xác nhận Spring Data thực sự truy cập đúng schema/table.

Ví dụ repository:

```java
public interface CustomerRepository
        extends ReactiveCrudRepository<Customer, Long> {

    Mono<Customer> findByEmail(String email);
}
```

Test minh họa:

```java
@DataR2dbcTest
class CustomerMappingTest {

    @Autowired
    CustomerRepository repository;

    @Test
    void savesCustomerInConfiguredSchema() {
        Customer customer = new Customer(
                "person@example.com",
                "Example Person");

        StepVerifier.create(repository.save(customer))
                .assertNext(saved -> assertThat(saved.getId()).isNotNull())
                .verifyComplete();

        StepVerifier.create(repository.findByEmail("person@example.com"))
                .assertNext(found ->
                        assertThat(found.getDisplayName())
                                .isEqualTo("Example Person"))
                .verifyComplete();
    }
}
```

Đây là khung test; entity constructor/getter, schema initialization, database test và dependency test cần được cấu hình cho project cụ thể. Dùng đúng R2DBC driver và database mà ứng dụng hỗ trợ.

### 19.1. Test schema riêng

Nếu dùng schema cụ thể, test setup phải tạo schema trước khi repository chạy:

```sql
CREATE SCHEMA crm;
CREATE TABLE crm.customer (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    email_address VARCHAR(255) NOT NULL,
    display_name VARCHAR(150)
);
```

Test phải xác nhận dữ liệu xuất hiện ở đúng schema. Có thể query trực tiếp qualified table để kiểm tra:

```sql
SELECT COUNT(*) FROM crm.customer;
```

### 19.2. Test nhiều schema cùng tên bảng

Nếu có `crm.customer` và `archive.customer`, hãy ghi một bản ghi vào mỗi repository và xác nhận không có dữ liệu ghi nhầm schema.

### 19.3. Test naming strategy

Nếu có custom `NamingStrategy`, test tên bảng/cột được render theo đúng quy ước. Khi có thể, chạy integration test với database thật để xác nhận quoting/case folding.

## 20. Những lỗi thường gặp với @Table

| Triệu chứng | Nguyên nhân có thể có | Cách xử lý |
| --- | --- | --- |
| Relation/table not found | Sai tên bảng hoặc schema | Kiểm tra `value`, `schema` và DDL |
| Query chạy vào schema mặc định | Annotation không có schema hoặc naming strategy chưa được áp dụng | Kiểm tra metadata và default schema |
| Bảng có tên khác dự kiến | NamingStrategy suy ra tên từ class | Dùng `@Table(value = ...)` rõ ràng |
| Tên bảng trùng keyword gây syntax error | Identifier chưa được quote theo dialect | Kiểm tra forceQuote/dialect hoặc đổi tên bảng |
| Bảng có chữ hoa không tìm thấy | Khác biệt case folding và quoted identifier | Dùng đúng case hoặc chuẩn hóa schema |
| Repository không được tạo | Domain type/repository scan không đúng | Kiểm tra package scan và mapping metadata |
| Native query vẫn truy cập bảng cũ | `@Table` không viết lại SQL native | Sửa câu SQL hoặc dùng mapping API phù hợp |
| Local chạy nhưng production lỗi | Schema default, quyền hoặc search path khác | Kiểm tra connection user và schema permissions |
| Hai entity ghi nhầm cùng bảng | Tên suy ra bị trùng | Đặt tên tường minh bằng `@Table` |
| Multi-tenant đọc nhầm dữ liệu | Schema/connection context bị chia sẻ sai | Thiết kế routing và reset connection state |
| Đổi annotation nhưng không thấy bảng mới | `@Table` không tạo DDL/migration | Tạo migration tương ứng |

## 21. Quy tắc đặt tên bảng và schema

Để mapping dễ duy trì:

- Dùng tên bảng có nghĩa nghiệp vụ.
- Dùng `snake_case` và chữ thường.
- Tránh reserved keyword như `order`, `user` hoặc `group`.
- Không dùng dấu cách hoặc ký tự đặc biệt trong identifier mới.
- Dùng schema theo bounded context hoặc chức năng khi cần phân tách namespace.
- Giữ tên trong annotation đồng nhất với migration.
- Không nhúng tên schema vào `value` khi đã có thuộc tính `schema`.
- Không dùng schema từ request mà chưa xác thực/allowlist.

Ví dụ:

```java
@Table(value = "purchase_order", schema = "sales")
public class PurchaseOrder {
    @Id
    private Long id;
}
```

Đọc rõ nghĩa hơn `@Table("order")` và tránh xung đột từ khóa.

## 22. Khi nào nên dùng @Table và khi nào nên dùng NamingStrategy?

| Tình huống | Cách phù hợp |
| --- | --- |
| Một entity có tên bảng đặc biệt | `@Table(value = ...)` |
| Một entity nằm trong schema riêng | `@Table(schema = ...)` |
| Phần lớn entity dùng chung schema | `NamingStrategy.getSchema()` |
| Toàn project cần quy tắc tên bảng riêng | Custom `NamingStrategy` |
| Native SQL viết tay | Ghi tên bảng/schema đúng trong SQL |
| Schema thay đổi theo tenant | Tenant-aware routing hoặc cơ chế động được hỗ trợ và kiểm soát |
| Cần tạo bảng/index/constraint | Migration tool/DDL |

Không cần dùng custom naming strategy chỉ để đổi tên một bảng. Dùng annotation trực tiếp sẽ dễ đọc và ít ảnh hưởng entity khác hơn.

## 23. Kiểm tra API theo phiên bản Spring Data

`@Table` thuộc Spring Data Relational và được Spring Data R2DBC sử dụng. Tuy nhiên, mapping, naming, identifier quoting và expression support có thể thay đổi giữa các release train.

Khi xem tài liệu:

1. Xác định Spring Boot version của ứng dụng.
2. Xem BOM để biết Spring Data release train.
3. Mở Javadoc `Table` của đúng version.
4. Kiểm tra `value`, `name` và `schema` có trong annotation.
5. Đọc mapping reference R2DBC cùng release.
6. Xác nhận `NamingStrategy` và `R2dbcMappingContext` behavior.
7. Chạy integration test để xem SQL hoạt động với driver thật.

Javadoc hiện hành mô tả `value` và `name` là alias, `schema` là schema prefix. Các phiên bản mới cũng mô tả expression support cho tên bảng/schema; nếu sử dụng tính năng này, phải đọc đúng Javadoc của version đang chạy.

## 24. Checklist khi thêm @Table cho entity

Khi ánh xạ một entity mới, hãy xác nhận:

1. Đã import đúng `org.springframework.data.relational.core.mapping.Table`.
2. Đã chọn tên bảng phù hợp với schema thật.
3. Đã chỉ định `schema` khi không muốn phụ thuộc schema mặc định của connection.
4. Đã dùng `@Column` cho các cột có tên khác property.
5. Tên bảng/cột phù hợp quy tắc case và quoting của dialect.
6. Không dùng identifier trùng reserved keyword nếu có thể tránh.
7. Migration đã tạo schema/table/index/constraint tương ứng.
8. Runtime user có quyền truy cập schema/table.
9. Repository hoặc `R2dbcEntityTemplate` dùng đúng mapping context.
10. Native SQL đã được cập nhật riêng nếu tên bảng/schema thay đổi.
11. Integration test chạy trên driver/database mục tiêu.
12. Nếu có multi-tenancy, connection/schema routing không thể rò giữa tenant.

## 25. Tài liệu tham khảo chính thức

- [Spring Data Relational R2DBC Mapping](https://docs.spring.io/spring-data/relational/reference/r2dbc/mapping.html) — convention mapping, `@Table`, `NamingStrategy` và identifier quoting.
- [Javadoc @Table — Spring Data Relational 4.1](https://docs.spring.io/spring-data/relational/reference/api/java/org/springframework/data/relational/core/mapping/Table.html) — thuộc tính `value`, `name` và `schema`.
- [Javadoc @Table — Spring Data Relational 3.5](https://docs.spring.io/spring-data/jdbc/docs/3.5.x/api/org/springframework/data/relational/core/mapping/Table.html) — API của release train 3.5.
- [Javadoc NamingStrategy](https://docs.spring.io/spring-data/relational/reference/api/java/org/springframework/data/relational/core/mapping/NamingStrategy.html) — cách suy ra tên bảng, cột và schema mặc định.
- [Spring Data R2DBC Reference](https://docs.spring.io/spring-data/relational/reference/r2dbc/) — repository và persistence với R2DBC.

`@Table` là điểm khai báo mapping giữa entity và bảng relational trong Spring Data R2DBC. Dùng `value` hoặc `name` để chỉ định tên bảng, `schema` để chỉ định namespace và `NamingStrategy` cho quy tắc mặc định toàn ứng dụng. Hãy đồng bộ annotation với DDL/migration, quyền database, identifier quoting và native query. Vì hành vi naming/quoting có thể thay đổi theo release train, luôn kiểm tra tài liệu đúng version và xác nhận mapping bằng integration test trên R2DBC driver thực tế.
