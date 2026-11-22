# Sinh, xác thực hoặc cập nhật lược đồ từ metadata trong Hibernate

Hibernate không chỉ chuyển đổi entity thành những câu lệnh `SELECT`, `INSERT`, `UPDATE` hay `DELETE`. Nó còn có một nhóm công cụ **schema management** dùng metadata ánh xạ entity để **sinh lệnh DDL**, **kiểm tra lược đồ đang có**, hoặc **thử điều chỉnh cấu trúc database**.

Ví dụ, khi một entity khai báo `@Table(name = "purchase_orders")`, `@Id`, `@Column(nullable = false)` và `@ManyToOne`, Hibernate có thể suy ra rằng database cần một bảng, cột khóa chính, cột không được null và một khóa ngoại. Nếu database chưa có các thành phần ấy, schema tooling có thể tạo chúng. Nếu database đã có, chế độ validation có thể phát hiện một số sự sai lệch giữa metadata và schema thật.

Điều dễ nhầm nhất là xem ba việc sau như một:

1. **Generate/create:** tạo DDL hoặc thực thi DDL để có schema theo mapping.
2. **Validate:** đọc metadata database và đối chiếu với mapping, **không sửa schema**.
3. **Update:** cố điều chỉnh schema hiện có theo mapping, nhưng **không phải một hệ thống database migration đầy đủ**.

Bài học thuộc chương **Lược đồ và chuyển đổi** của module *Data Persistence Relational Access ORM Hibernate*. Nội dung trình bày trong ngữ cảnh Hibernate ORM 6.x, Jakarta Persistence và Spring Boot. Những câu SQL sinh ra chỉ là minh họa: kiểu cột, khóa, sequence, quoting và cách ALTER TABLE cụ thể phụ thuộc Hibernate version, database `Dialect` và JDBC driver.

## 1. Schema được suy ra từ đâu?

Hibernate xây một mô hình metadata từ các nguồn ánh xạ mà ứng dụng cung cấp, chẳng hạn:

- Annotation Jakarta Persistence: `@Entity`, `@Table`, `@Id`, `@Column`, `@ManyToOne`, `@JoinColumn`, `@Embeddable`, v.v.
- Annotation đặc thù của Hibernate khi dự án sử dụng.
- File mapping XML nếu persistence unit có cấu hình.
- Naming strategy, type mapping, custom converters, identifier generators và những thiết lập ORM liên quan.
- Thông tin `Dialect` và các khả năng DDL của DBMS.

Sơ đồ khái niệm:

~~~mermaid
flowchart TD
    A["Java entities và annotations"] --> M["Hibernate mapping metadata"]
    B["XML mappings / custom types"] --> M
    C["Naming strategy và Dialect"] --> M
    M --> D{"Schema-management action"}
    D -->|create / create-only| E["Sinh và thực thi CREATE DDL"]
    D -->|validate| F["Đọc database metadata để đối chiếu"]
    D -->|update| G["Thử tạo hoặc điều chỉnh objects còn thiếu"]
    D -->|drop / create-drop| H["DROP DDL theo action"]
    M --> S["Xuất DDL thành script nếu cấu hình"]
    E --> DB[("Database schema")]
    F --> DB
    G --> DB
    H --> DB
~~~

**Metadata ORM không phải database migration history.** Nó mô tả schema mà phiên bản hiện tại của entity mapping mong đợi; nó không biết tại sao schema cũ khác, dữ liệu nào phải được chuyển đổi khi đổi kiểu, hay thay đổi nào đã được áp dụng ở từng môi trường.

## 2. Mô hình ví dụ: khách hàng và đơn hàng

Giả sử ứng dụng có hai entity `Customer` và `PurchaseOrder`.

### 2.1. Customer

~~~java
package com.example.sales;

import jakarta.persistence.*;

@Entity
@Table(
    name = "customers",
    uniqueConstraints = @UniqueConstraint(
        name = "uk_customers_email",
        columnNames = "email"
    ),
    indexes = @Index(
        name = "idx_customers_name",
        columnList = "display_name"
    )
)
public class Customer {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "display_name", nullable = false, length = 150)
    private String displayName;

    @Column(name = "email", nullable = false, length = 254)
    private String email;

    protected Customer() {}
}
~~~

### 2.2. PurchaseOrder

~~~java
package com.example.sales;

import jakarta.persistence.*;
import java.math.BigDecimal;
import java.time.Instant;

@Entity
@Table(
    name = "purchase_orders",
    indexes = {
        @Index(
            name = "idx_orders_customer",
            columnList = "customer_id"
        ),
        @Index(
            name = "idx_orders_created",
            columnList = "created_at"
        )
    }
)
public class PurchaseOrder {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(
        name = "customer_id",
        nullable = false,
        foreignKey = @ForeignKey(name = "fk_orders_customer")
    )
    private Customer customer;

    @Column(name = "total_amount", nullable = false,
            precision = 14, scale = 2)
    private BigDecimal totalAmount;

    @Column(name = "created_at", nullable = false)
    private Instant createdAt;

    @Enumerated(EnumType.STRING)
    @Column(name = "status", nullable = false, length = 30)
    private OrderStatus status;

    @Version
    @Column(name = "row_version", nullable = false)
    private long version;

    protected PurchaseOrder() {}
}
~~~

### 2.3. Enum

~~~java
package com.example.sales;

public enum OrderStatus {
    DRAFT,
    CONFIRMED,
    CANCELLED
}
~~~

Mỗi `public` class/enum thuộc file Java riêng. Những ví dụ không trình bày đầy đủ constructors và domain methods vì bài học tập trung vào schema metadata.

### 2.4. Hibernate có thể suy ra điều gì?

| Mapping | Thông tin schema được suy ra |
| --- | --- |
| `@Table(name="customers")` | Bảng `customers` |
| `@Id` và `IDENTITY` | Cột PK với cơ chế sinh ID phù hợp DBMS |
| `@Column(nullable=false)` | Mong muốn ràng buộc NOT NULL |
| `length=150` | Độ dài chuỗi theo JDBC/SQL type mapping |
| `precision=14, scale=2` | Độ chính xác/thang đo của cột số |
| `@UniqueConstraint` | Ràng buộc UNIQUE theo cột đã chọn |
| `@Index` | Metadata đề nghị tạo index |
| `@ManyToOne`/`@JoinColumn` | Cột FK `customer_id` và constraint nếu mapping cho phép |
| `@Version` | Cột version cho optimistic locking |
| `@Enumerated(EnumType.STRING)` | Giá trị enum được lưu theo mapping chuỗi |

SQL PostgreSQL minh họa (không phải output nguyên văn bắt buộc của Hibernate):

~~~sql
create table customers (
    id bigint generated by default as identity primary key,
    display_name varchar(150) not null,
    email varchar(254) not null,
    constraint uk_customers_email unique (email)
);

create table purchase_orders (
    id bigint generated by default as identity primary key,
    customer_id bigint not null,
    total_amount numeric(14,2) not null,
    created_at timestamp with time zone not null,
    status varchar(30) not null,
    row_version bigint not null
);

alter table purchase_orders
    add constraint fk_orders_customer
    foreign key (customer_id) references customers(id);

create index idx_orders_customer
    on purchase_orders(customer_id);
~~~

Ví dụ chỉ minh họa hình dạng DDL. Với Hibernate 6 và PostgreSQL, enum mapping có thể tạo column type/constraint khác tùy version và Dialect; `Instant` cũng có thể được render thành SQL temporal type khác. Muốn biết DDL thật, hãy sinh script bằng đúng Hibernate version/DBMS của ứng dụng.

**Lưu ý:** `@ManyToOne(fetch = LAZY)` chỉ nói về thời điểm tải association khi đọc entity; nó không có nghĩa database được phép thiếu FK. Lazy fetching và database schema là hai vấn đề khác nhau.

## 3. Hibernate điều khiển schema bằng cách nào?

Một setting thường gặp là:

~~~properties
hibernate.hbm2ddl.auto=validate
~~~

Trong Spring Boot:

~~~properties
spring.jpa.hibernate.ddl-auto=validate
~~~

Về ý nghĩa, Spring Boot property `spring.jpa.hibernate.ddl-auto` là cách cấu hình Hibernate schema action theo tích hợp Spring Boot. Không nên cấu hình nhiều nguồn với giá trị mâu thuẫn rồi dựa vào thứ tự override ngầm.

### 3.1. Bảng các action của Hibernate

| Giá trị `hibernate.hbm2ddl.auto` | Ý nghĩa chính | Rủi ro |
| --- | --- | --- |
| `none` | Không thực hiện tác vụ schema tự động theo setting này | Schema phải do công cụ khác chuẩn bị |
| `validate` | Đối chiếu mapping với schema hiện có, không tạo/sửa | Startup có thể thất bại khi schema lệch |
| `update` | Thử điều chỉnh schema hiện có để gần mapping hơn | Không xử lý đầy đủ migration; có thể tạo DDL ngoài ý muốn |
| `create-only` | Thực thi tạo schema objects, không chủ động drop trước theo action này | Có thể lỗi khi objects đã tồn tại |
| `create` | Drop rồi tạo lại schema objects do Hibernate quản lý | **Mất dữ liệu** ở các objects được drop |
| `create-drop` | Drop/tạo lúc khởi động, cố drop lúc đóng SessionFactory | **Mất dữ liệu** và cleanup không chắc khi crash |
| `drop` | Thực thi drop schema objects do Hibernate quản lý | **Mất dữ liệu** |

Bảng mô tả các action của Hibernate ORM 6.x. Giá trị hỗ trợ chính xác cần kiểm tra tài liệu phiên bản đang dùng. Đặc biệt, **Hibernate `create` không có nghĩa “chỉ tạo những thứ còn thiếu”**: action này có thể drop schema trước khi tạo lại.

### 3.2. Không nhầm với Jakarta Persistence schema-generation action

Jakarta Persistence định nghĩa property riêng như:

~~~properties
jakarta.persistence.schema-generation.database.action=none
~~~

Các giá trị tiêu chuẩn cho `database.action` gồm `none`, `create`, `drop` và `drop-and-create`. Chúng là **nhóm hành động chuẩn JPA**, không phải chuỗi value đồng nhất 1:1 với `hibernate.hbm2ddl.auto`.

Ví dụ, trong JPA action `create` mang ý nghĩa tạo schema; trong Hibernate legacy setting `hibernate.hbm2ddl.auto=create` thường có hành vi drop-then-create. **Đừng trộn hai tên property chỉ dựa trên việc hai giá trị cùng viết là “create”.**

Nếu dùng cả JPA-standard và Hibernate-specific schema settings, provider có thể áp dụng precedence theo đặc tả/implementation. Tốt nhất là dùng **một cơ chế cấu hình chính rõ ràng**, kiểm tra startup logs và DDL thực tế.

## 4. Chế độ `none`: để công cụ khác sở hữu schema

Ví dụ:

~~~properties
spring.jpa.hibernate.ddl-auto=none
~~~

Hibernate không tự thực hiện schema create/update/validate qua action này. Ứng dụng kỳ vọng bảng, index, constraint và sequences đã tồn tại hoặc được chuẩn bị bằng cơ chế khác.

Cách này phù hợp khi:

- Schema được quản lý bởi Flyway/Liquibase hoặc database team.
- Ứng dụng không có quyền DDL trong môi trường production.
- Dự án muốn tự điều khiển migration riêng, không dùng ORM startup tooling.
- Các khác biệt schema được kiểm tra bởi pipeline/health checks khác.

**Hệ quả:** `none` không xác nhận schema đúng. Nếu bảng/cột thiếu, lỗi có thể xuất hiện khi chạy query thay vì khi khởi động. Vì vậy một lựa chọn thường có lợi cho ứng dụng dùng migration là `validate` thay cho `none`, nếu cơ chế validation hỗ trợ tốt mapping/DBMS và không tạo false failures không mong muốn.

## 5. Chế độ `create-only`: sinh bảng mà không drop trước

~~~properties
hibernate.hbm2ddl.auto=create-only
~~~

Hibernate cố thực thi CREATE DDL cho các schema objects được metadata mô tả, mà không chủ động chạy chuỗi DROP như action `create`.

Điều này không đồng nghĩa cơ chế “nếu thiếu thì tạo, nếu đã có thì giữ nguyên” hoàn chỉnh:

- Nếu bảng `customers` đã tồn tại, `CREATE TABLE customers` có thể thất bại.
- Nếu constraints/indexes tồn tại với tên khác, có thể phát sinh conflict.
- Khả năng dùng `IF NOT EXISTS` hoặc xử lý lỗi có thể phụ thuộc Dialect/settings.
- Cấu trúc schema cũ không được đối chiếu đầy đủ chỉ vì CREATE được yêu cầu.

Dùng cho môi trường trống, bootstrap lần đầu hoặc thử sinh DDL có kiểm soát. Không dùng như công cụ migration idempotent cho hệ thống đang hoạt động.

## 6. Chế độ `create`: tạo lại schema từ đầu

~~~properties
spring.jpa.hibernate.ddl-auto=create
~~~

Với Hibernate action này, database schema objects thuộc phạm vi quản lý có thể bị **drop rồi create lại** khi SessionFactory khởi động.

Một chuỗi thao tác khái quát:

~~~text
Ứng dụng khởi động
    ↓
Đọc mapping metadata
    ↓
DROP các tables/sequences/constraints thuộc mapping (theo khả năng tool)
    ↓
CREATE tables, indexes, FKs...
    ↓
Ứng dụng bắt đầu dùng schema mới
~~~

### 6.1. Mục đích phù hợp

- Ví dụ học ORM.
- Test đơn giản trên database dùng riêng.
- Môi trường phát triển có dữ liệu **có thể xóa toàn bộ**.
- Tạo baseline schema trong database tạm.

### 6.2. Điều nguy hiểm nhất

Nếu trỏ nhầm datasource vào database dùng chung hoặc production, `create` có thể xóa dữ liệu ở những tables Hibernate drop. Một biến môi trường hoặc profile sai đủ gây sự cố nghiêm trọng.

Không chỉ cần kiểm tra file config. Hãy thiết kế phân quyền DB:

- Ứng dụng production không cần `DROP TABLE`/`CREATE TABLE` nên không được cấp quyền DDL.
- Migration account có quyền DDL riêng và được vận hành qua pipeline kiểm soát.
- Test/development dùng database/schema cô lập.
- Cấu hình profiles được review và có safeguard ở startup/deployment.

**Không áp dụng `create` vào database cần giữ dữ liệu.**

## 7. Chế độ `create-drop`: thường dùng cho test ngắn

~~~properties
spring.jpa.hibernate.ddl-auto=create-drop
~~~

Hibernate tạo schema khi khởi động và cố drop các schema objects khi đóng SessionFactory/EntityManagerFactory đúng vòng đời.

Điều này hữu ích cho integration tests chạy database riêng:

~~~text
Test application context starts
    → tạo schema mới

Các test đọc/ghi rows
    → chạy nghiệp vụ

Test context closes bình thường
    → cố drop schema
~~~

Nhưng cần hiểu giới hạn:

- **Không bảo đảm cleanup khi tiến trình crash hoặc bị kill**.
- Khi có nhiều application instances trỏ cùng schema, các instances có thể phá schema của nhau.
- Test data bị xóa theo vòng đời schema.
- Restart ứng dụng có thể làm mất toàn bộ rows đã tạo trong phiên trước.
- Nếu test dùng database chia sẻ, action này vẫn có thể rất nguy hiểm.

Trong một số framework test, application context được cache giữa nhiều tests, nên thời điểm `create-drop` thực sự drop là khi factory/context đóng, **không nhất thiết sau từng test method**.

## 8. Chế độ `validate`: so sánh mapping với schema hiện có

~~~properties
spring.jpa.hibernate.ddl-auto=validate
~~~

Hibernate khởi tạo metadata ORM, truy vấn metadata database qua JDBC và kiểm tra các phần mapping mà schema validator hỗ trợ.

Nếu entity `PurchaseOrder` yêu cầu bảng `purchase_orders` nhưng bảng không tồn tại, startup có thể thất bại với lỗi đại loại:

~~~text
Schema-validation: missing table [purchase_orders]
~~~

Nếu bảng có nhưng cột `total_amount` thiếu:

~~~text
Schema-validation: missing column [total_amount]
~~~

Nếu kiểu SQL của cột không tương thích với mapping:

~~~text
Schema-validation: wrong column type encountered ...
~~~

Đây là minh họa nhóm lỗi, không phải cam kết thông báo chính xác ở mọi phiên bản.

### 8.1. Validate KHÔNG cập nhật schema

`validate` chỉ đối chiếu. Nó không thêm cột, thay datatype, tạo index hoặc sửa constraint.

Ví dụ mapping mới thêm:

~~~java
@Column(name = "customer_note", length = 500)
private String customerNote;
~~~

nhưng database chưa có cột, `validate` có thể báo schema thiếu cột. Ứng dụng phải dùng migration hoặc một thao tác DDL khác để thêm cột rồi mới xác thực lại.

### 8.2. Những gì validator thường kiểm tra

Tùy Hibernate version/Dialect/JDBC metadata, schema validation thường tập trung vào các thành phần như:

- Bảng hoặc view tương ứng mapping có tồn tại không.
- Những columns được yêu cầu có tồn tại không.
- JDBC/SQL column types có tương thích theo tiêu chí validator không.
- Một số schema objects bổ sung, chẳng hạn sequences và các đặc tính liên quan identifier generators, nếu validator/version hỗ trợ.

Không nên khẳng định mọi property của mọi schema object đều được kiểm tra giống nhau.

### 8.3. Những gì validate không bảo đảm

Schema validation **không phải schema diff/migration auditor toàn diện**. Nó không đảm bảo phát hiện đầy đủ:

- Mọi khác biệt nullability, default expression hoặc column comment.
- Toàn bộ FK/UNIQUE/CHECK/index definitions và index ordering.
- Thay đổi collation, character set, partitioning hoặc tablespace.
- Mọi khác biệt precision/scale, enum constraints hoặc type aliases giữa các Dialects.
- Trigger, stored procedure, policy, grant/role, row-level security.
- Dữ liệu vi phạm logic nghiệp vụ hoặc quan hệ dữ liệu bị hỏng.
- Migration nào đã chạy, checksum nào được áp dụng.
- Index có đang được optimizer sử dụng hay không.
- Schema có đáp ứng yêu cầu hiệu năng/locking khi traffic tăng không.

Do đó “Hibernate validate thành công” chỉ nói rằng **những phần nó biết kiểm tra** khớp đủ để khởi động theo validator hiện tại. Nó không thay thế integration tests, constraints và quy trình quản lý schema.

### 8.4. Trường hợp validator báo khác dù schema dùng được

DBMS và JDBC drivers có thể biểu diễn datatype dưới nhiều tên hoặc type codes khác nhau. Ví dụ `VARCHAR`/`TEXT`, temporal types, enum native types, JSON types hoặc numeric aliases. Nếu validation báo mismatch, cần đối chiếu:

1. Java attribute và annotation mapping.
2. Hibernate `JdbcType`/`Dialect`.
3. DB column type thật.
4. JDBC `DatabaseMetaData` trả về type nào.
5. Hibernate/driver versions.

Không nên tắt validate vĩnh viễn chỉ để giấu một mismatch thực sự. Nhưng cũng không ép DB migration sai để chiều lòng một validator không nhận ra các kiểu tương đương; cần giải quyết mapping/version hoặc chọn cơ chế kiểm tra phù hợp.

## 9. Chế độ `update`: tiện cho thử nghiệm nhưng không phải migration framework

~~~properties
spring.jpa.hibernate.ddl-auto=update
~~~

Hibernate so sánh metadata với database hiện có và cố áp DDL để những objects cần thiết xuất hiện. Ví dụ entity mới có thể dẫn đến tạo bảng; field mới có thể dẫn đến `ALTER TABLE ... ADD COLUMN` theo khả năng dialect.

Mô phỏng đơn giản:

~~~text
Mapping cũ:
  Product(id, name)

Schema cũ:
  products(id, name)

Mapping mới:
  Product(id, name, sku)

Update có thể cố thực thi:
  ALTER TABLE products ADD COLUMN sku ...
~~~

Tuy nhiên `update` không biết sự tiến hóa nghiệp vụ của schema. Nếu developer **đổi tên field** từ `name` thành `displayName`, Hibernate có thể xem đây là cột cũ dư và cột mới thiếu, không tự suy ra thao tác `RENAME COLUMN`. Kết quả có thể là thêm cột mới, bỏ lại dữ liệu trong cột cũ.

### 9.1. Ví dụ đổi tên gây lỗi logic

Ban đầu:

~~~java
@Column(name = "phone_number")
private String phoneNumber;
~~~

Schema:

~~~sql
customers(phone_number varchar(30))
~~~

Sau refactor:

~~~java
@Column(name = "contact_number")
private String contactNumber;
~~~

Nếu dùng `update`, tool có thể tạo `contact_number` nhưng **không di chuyển dữ liệu** từ `phone_number`. Ứng dụng đọc field mới sẽ thấy null hoặc default không đúng nghiệp vụ.

Migration đúng khi cần đổi tên có thể là:

~~~sql
alter table customers
    rename column phone_number to contact_number;
~~~

Cú pháp chính xác phụ thuộc DBMS. Migration này phải được version hóa và kiểm thử để bảo đảm bảo toàn dữ liệu.

### 9.2. Những thay đổi update không xử lý đáng tin cậy

| Thay đổi | Vì sao không nên giao toàn bộ cho `update` |
| --- | --- |
| Rename column/table | Metadata mới không nói cột nào là tên cũ |
| Drop cột không dùng | Tool không nên tự xóa dữ liệu do mapping bỏ field |
| Đổi type từ string sang integer | Cần kiểm tra và chuyển đổi dữ liệu |
| Thêm NOT NULL vào cột đã có null | Cần backfill dữ liệu và kiểm soát lock |
| Chia/gộp bảng | Cần copy dữ liệu, mapping mới và kế hoạch chuyển đổi |
| Thay đổi khóa chính/foreign key | Có thể ảnh hưởng toàn bộ quan hệ dữ liệu |
| Đổi enum lưu STRING sang ORDINAL | Giá trị DB cần chuyển đổi có ý nghĩa |
| Sửa constraint UNIQUE | Cần dọn dữ liệu trùng trước |
| Chỉnh index lớn ở production | Cần cân nhắc lock, online/concurrent index, window triển khai |
| Thay đổi partitioning | Liên quan di chuyển rows và vận hành DB |
| Thay đổi timezone/temporal semantics | Không thể suy ra ý định nghiệp vụ từ kiểu Java |

`update` có thể làm một số `ALTER` trong những tình huống cụ thể, nhưng phạm vi/độ an toàn tùy DBMS và Hibernate version. Không lấy việc nó thêm một cột thành công trong local dev làm bằng chứng nó quản lý an toàn mọi thay đổi schema production.

### 9.3. DDL có thể không transactional

Nhiều DBMS có quy tắc transaction khác nhau với DDL. Có DBMS hỗ trợ transactional DDL cho nhiều câu lệnh; có DBMS implicit commit hoặc hạn chế rollback đối với một số thao tác.

Nếu `update` chạy một loạt DDL rồi lỗi ở giữa, schema có thể ở trạng thái **thay đổi một phần**. Không giả định rollback Java transaction sẽ khôi phục toàn bộ schema.

### 9.4. Update có thể làm startup phụ thuộc quyền DDL

Nếu Hibernate dùng `update` ở startup, database user của ứng dụng phải được cấp các quyền DDL cần thiết. Điều này mở rộng quyền của runtime application vượt nhu cầu thông thường. Trong production, thường muốn **application account chỉ có quyền DML cần thiết**, còn DDL do migration pipeline/role riêng xử lý.

## 10. Khi nào dùng action nào?

| Môi trường/tình huống | Action thường phù hợp | Lý do |
| --- | --- | --- |
| Demo học Hibernate trên DB tạm | `create` hoặc `create-drop` | Tạo schema nhanh, dữ liệu có thể bỏ |
| Test tự động với DB cô lập | `create-drop` hoặc migration + `validate` | Chạy lặp lại trong môi trường kiểm soát |
| Dev prototype còn thay mapping liên tục | `update` có thể thuận tiện trong giai đoạn ngắn | Không cần viết migration cho dữ liệu có thể bỏ |
| Dev nhóm với DB có dữ liệu muốn giữ | Migration + `validate` | Mọi người có cùng lịch sử schema |
| Staging trước release | Migration + `validate` | Diễn tập chính xác đường triển khai |
| Production | Migration versioned + `validate` hoặc `none` | Tránh Hibernate tự thay schema lúc startup |
| DBA quản lý schema riêng | `validate` nếu tương thích | ORM chỉ kiểm tra yêu cầu tối thiểu |
| Xuất DDL để review, chưa áp vào DB | JPA scripts action hoặc Hibernate schema tooling | Không sửa DB trực tiếp |

Đây là hướng dẫn lựa chọn, không phải quy tắc tuyệt đối. Các tổ chức có quy trình riêng, nhưng **không nên bật hành động phá schema hoặc auto-update trong production chỉ để giảm thao tác quản lý migration**.

## 11. Jakarta Persistence schema generation

Jakarta Persistence cung cấp nhóm properties để cấu hình schema generation. Nhóm này tách việc **tác động tới database** khỏi việc **ghi ra script**.

### 11.1. Database action

Ví dụ trong `persistence.xml`:

~~~xml
<persistence xmlns="https://jakarta.ee/xml/ns/persistence"
             version="3.1">
    <persistence-unit name="salesPU">
        <properties>
            <property
                name="jakarta.persistence.schema-generation.database.action"
                value="none"/>
        </properties>
    </persistence-unit>
</persistence>
~~~

Property `database.action` có thể chỉ định hoạt động trên DB theo chuẩn JPA:

- `none`: không tác động schema.
- `create`: tạo database objects từ nguồn đã cấu hình.
- `drop`: drop những objects theo action.
- `drop-and-create`: drop trước rồi tạo mới.

Cách JPA action `create` khác Hibernate setting `hibernate.hbm2ddl.auto=create` là lý do cần đọc đúng **tên đầy đủ của property** khi xem config.

### 11.2. Tách script generation khỏi database action

Bạn có thể muốn xem trước DDL mà **không chạy trên database**:

~~~xml
<persistence xmlns="https://jakarta.ee/xml/ns/persistence"
             version="3.1">
    <persistence-unit name="salesPU">
        <properties>
            <property
                name="jakarta.persistence.schema-generation.database.action"
                value="none"/>

            <property
                name="jakarta.persistence.schema-generation.scripts.action"
                value="drop-and-create"/>

            <property
                name="jakarta.persistence.schema-generation.scripts.create-target"
                value="build/schema-create.sql"/>

            <property
                name="jakarta.persistence.schema-generation.scripts.drop-target"
                value="build/schema-drop.sql"/>

            <property
                name="jakarta.persistence.schema-generation.create-source"
                value="metadata"/>

            <property
                name="jakarta.persistence.schema-generation.drop-source"
                value="metadata"/>
        </properties>
    </persistence-unit>
</persistence>
~~~

Ý tưởng:

- `database.action=none`: không áp DDL trực tiếp lên database theo nhóm standard properties này.
- `scripts.action=drop-and-create`: tạo script cho thao tác drop và create.
- `create-target`/`drop-target`: đích ghi script.
- `create-source=metadata`/`drop-source=metadata`: lấy DDL từ mapping metadata.

Đường dẫn target phải được cấp quyền ghi, thư mục cha tồn tại theo cấu hình build/runtime, và provider thực sự chạy schema generation. Ví dụ output path chỉ là minh họa; không giả định mọi môi trường sử dụng cùng working directory.

### 11.3. Các nguồn tạo schema

Jakarta Persistence schema-generation properties hỗ trợ chọn nguồn, ví dụ:

- `metadata`: từ ORM mapping metadata.
- `script`: từ DDL script được chỉ định.
- `metadata-then-script`: thực hiện metadata trước rồi script.
- `script-then-metadata`: thực hiện script trước rồi metadata.

Khi dùng script source, cấu hình các properties tương ứng như:

~~~properties
jakarta.persistence.schema-generation.create-source=script
jakarta.persistence.schema-generation.create-script-source=META-INF/create-schema.sql
~~~

Khi drop từ script, dùng `drop-source` và `drop-script-source` phù hợp. Các đường dẫn/URL phải được provider giải quyết được; hãy kiểm tra khả năng đọc tài nguyên theo cách đóng gói JAR/classpath và version JPA tương ứng.

Việc sinh DDL thành file là một **đầu ra kỹ thuật**, không tự biến file ấy thành migration idempotent, có rollback hoặc được kiểm thử dữ liệu production.

### 11.4. SQL load scripts và dữ liệu seed

Schema generation có thể đi kèm nạp SQL seed. Jakarta Persistence có property `jakarta.persistence.sql-load-script-source`; Hibernate cũng có các cơ chế như `import.sql` hoặc import-files theo cấu hình/provider.

Phân biệt rõ:

- **DDL:** tạo/đổi bảng, index, constraints.
- **Seed DML:** INSERT dữ liệu tham chiếu/test.
- **Migration:** biến đổi cả schema và dữ liệu từ phiên bản cũ sang phiên bản mới.

Không để test seed script chạy tự động trong production chỉ vì nó nằm trên classpath. Tránh INSERT trùng khi startup nhiều lần và xác định rõ script chỉ được thực thi ở action nào.

## 12. Spring Boot và cấu hình profile

Trong Spring Boot, một cấu hình phát triển có thể là:

~~~properties
# application-dev.properties
spring.jpa.hibernate.ddl-auto=update
~~~

Một cấu hình integration test dùng DB tạm có thể là:

~~~properties
# application-test.properties
spring.jpa.hibernate.ddl-auto=create-drop
~~~

Một cấu hình production có migration versioned có thể là:

~~~properties
# application-prod.properties
spring.jpa.hibernate.ddl-auto=validate
~~~

Đây là ví dụ profiles. Không copy nguyên mẫu khi không biết Spring Boot version, datasource và Flyway/Liquibase integration đang chạy. Một số mặc định của Spring Boot khác nhau giữa embedded database và database bên ngoài; **nên đặt giá trị tường minh** để tránh dựa vào default khó nhận biết.

### 12.1. Chọn một nguồn cấu hình

Có thể gặp cả hai:

~~~properties
spring.jpa.hibernate.ddl-auto=validate
spring.jpa.properties.hibernate.hbm2ddl.auto=update
~~~

Đây là cấu hình mâu thuẫn về ý định. Thay vì đoán property nào thắng, xóa một nguồn, giữ một setting rõ ràng và xác nhận action thực tế qua startup logs. Trong dự án dùng JPA standard database action, cũng cần tránh set thêm Hibernate action khác mà không có chủ đích.

### 12.2. Không nhầm schema action với SQL logging

~~~properties
spring.jpa.show-sql=true
spring.jpa.hibernate.ddl-auto=validate
~~~

`show-sql` kiểm soát việc hiển thị SQL trong một cách logging, không phải lệnh tạo bảng. Ngược lại, `ddl-auto=update` không có nghĩa ứng dụng tự bật logging. Nếu cần quan sát, cấu hình logger/Hibernate statistics riêng.

### 12.3. Flyway/Liquibase chạy trước khi validate

Trong ứng dụng Spring Boot quản lý migration, thông thường startup sequence có thể được thiết kế theo hướng:

~~~text
Khởi động datasource
    ↓
Flyway/Liquibase áp các migrations còn thiếu
    ↓
EntityManagerFactory / Hibernate metadata bootstrap
    ↓
Hibernate validate schema đã được cập nhật
    ↓
Ứng dụng bắt đầu phục vụ traffic
~~~

Thứ tự thực tế phụ thuộc autoconfiguration và dependency graph của dự án. Nếu Hibernate validate chạy **trước** khi migration hoàn thành, startup có thể báo thiếu cột dù migration chuẩn bị tạo nó. Cần thiết lập dependency/order rõ thay vì tắt validation để che vấn đề khởi động.

## 13. Ví dụ tiến hóa schema đúng cách

Giả sử phiên bản V1 có entity Customer với cột email:

~~~java
@Column(name = "email", nullable = false)
private String email;
~~~

Phiên bản V2 bổ sung số điện thoại đã chuẩn hóa:

~~~java
@Column(name = "normalized_phone", length = 30)
private String normalizedPhone;
~~~

Một migration versioned:

~~~sql
-- V2__add_normalized_phone.sql
alter table customers
    add column normalized_phone varchar(30);
~~~

Sau đó Hibernate `validate` giúp phát hiện liệu môi trường đã có cột cần thiết hay chưa.

### 13.1. Thay đổi cần backfill

Giả sử sau một thời gian muốn cột `normalized_phone` là NOT NULL. Nếu dữ liệu cũ có hàng chưa có giá trị, không thể chỉ đổi:

~~~java
@Column(name = "normalized_phone", nullable = false)
private String normalizedPhone;
~~~

rồi hy vọng Hibernate `update` tự chọn số điện thoại phù hợp cho mọi customer.

Một quy trình **expand → backfill → enforce**:

1. **Expand:** thêm cột nullable.
2. **Deploy code tương thích:** code mới ghi cột normalized phone khi có dữ liệu.
3. **Backfill:** chuyển đổi/cập nhật dữ liệu cũ theo quy tắc nghiệp vụ.
4. **Validate data:** kiểm tra số hàng vẫn có null/giá trị không hợp lệ.
5. **Enforce:** migration thêm NOT NULL khi dữ liệu đã sạch.
6. **Update mapping:** đặt nullable=false và chạy validation/integration tests.

Ví dụ SQL minh họa:

~~~sql
-- Bước kiểm tra:
select count(*)
from customers
where normalized_phone is null;

-- Chỉ thực hiện khi dữ liệu đã sạch:
alter table customers
    alter column normalized_phone set not null;
~~~

Cú pháp ALTER khác nhau giữa DBMS. Không dùng một câu SQL trong ví dụ như migration universal.

### 13.2. Rename không phải add new column

Nếu đổi `normalized_phone` thành `phone_e164`, cần một migration `RENAME COLUMN` hoặc kế hoạch tương thích nhiều phiên bản, không chờ `update` suy đoán:

~~~sql
-- SQL minh họa:
alter table customers
    rename column normalized_phone to phone_e164;
~~~

Trong hệ thống triển khai rolling deployment, phiên bản cũ và mới có thể cùng chạy một thời gian. Một rename trực tiếp đôi khi phá ứng dụng cũ; khi đó cần expand/migrate/contract hoặc dual-read/dual-write có kiểm soát.

**Schema migration là bài toán về dữ liệu và triển khai phiên bản**, còn Hibernate metadata chỉ mô tả trạng thái mapping đích.

## 14. Flyway và Liquibase khác schema generation thế nào?

### 14.1. Hibernate schema tooling

Hibernate biết các entity mappings hiện tại và có thể sinh/validate/update schema ở mức ORM. Nó phù hợp tạo DB ban đầu, học tập, thử nghiệm và kiểm tra khớp cơ bản.

Nó **không cung cấp một lịch sử migration nghiệp vụ đầy đủ** với lý do thay đổi, checksum, thứ tự version, backfill và quy trình review/rollback có kiểm soát như các migration tools.

### 14.2. Flyway

Flyway quản lý các migration scripts được version hóa, ví dụ:

~~~text
db/migration/
  V1__create_customers.sql
  V2__create_purchase_orders.sql
  V3__add_normalized_phone.sql
  V4__create_orders_index.sql
~~~

Flyway theo dõi các migration đã áp dụng và metadata/checksum theo cơ chế của công cụ. Nó giúp các môi trường tiến hóa từ phiên bản schema trước sang sau theo một lịch sử rõ ràng.

### 14.3. Liquibase

Liquibase dùng changelog/changesets (XML, YAML, JSON hoặc SQL theo khả năng công cụ), với cơ chế tracking và các khả năng quản lý thay đổi schema. Nó cũng phục vụ mục tiêu **versioned database change management** chứ không chỉ suy ra schema từ entity.

### 14.4. Bảng đối chiếu

| Tiêu chí | Hibernate schema tooling | Flyway/Liquibase |
| --- | --- | --- |
| Đầu vào chính | ORM metadata hiện tại | Migration scripts/changesets |
| Tạo schema test nhanh | Phù hợp | Cũng được, cần migration baseline |
| Kiểm tra mapping với DB | `validate` kiểm tra một phần | Không tự thay thế ORM mapping validation |
| Giữ lịch sử từng thay đổi | Không phải mục tiêu chính | Có |
| Rename có chủ đích | Không thể suy luận đáng tin cậy | Viết rõ migration |
| Backfill dữ liệu | Không suy ra từ metadata | Có thể viết DML/transformation |
| Review/approval/rollback plan | Ngoài phạm vi schema action | Hỗ trợ theo quy trình migration |
| Production startup tự động tạo/sửa bảng | Không nên dùng trực tiếp nếu cần kiểm soát | Áp migration theo pipeline phù hợp |
| DB-specific index/partitioning | Có giới hạn theo metadata/Dialect | Có thể mô tả SQL/changelog phù hợp DBMS |

Một cách phối hợp thường hiệu quả:

**Migration tool chịu trách nhiệm thay đổi schema; Hibernate `validate` chịu trách nhiệm kiểm tra mapping có thể hoạt động trên schema đã triển khai.**

## 15. Cơ chế naming strategy ảnh hưởng DDL

Một entity:

~~~java
@Entity
public class PurchaseOrder {
    @Column
    private String customerReference;
}
~~~

có thể được ánh xạ theo naming strategy thành bảng/cột với tên vật lý khác `PurchaseOrder`/`customerReference`, ví dụ `purchase_order` và `customer_reference`. Cách chuyển đổi tùy `ImplicitNamingStrategy`, `PhysicalNamingStrategy` và framework integration.

### 15.1. Đặt tên tường minh khi cần ổn định

~~~java
@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {

    @Column(name = "customer_reference")
    private String customerReference;
}
~~~

Tên tường minh thường giúp đối chiếu migration SQL, nhưng physical naming strategy vẫn có thể được áp vào identifier theo quy tắc của provider. Kiểm tra SQL generated thật trên stack đang chạy.

### 15.2. Thay naming strategy cũng có thể là schema change lớn

Nếu thay convention từ camelCase sang snake_case, Hibernate có thể nghĩ hàng loạt bảng/cột cũ không còn khớp. `update` không tự xác định mọi rename một cách đáng tin cậy. Vì vậy thay naming strategy trong một hệ thống có dữ liệu cần migration plan riêng.

### 15.3. Schema và catalog

Các annotation như `@Table(schema = "sales")` hoặc settings `hibernate.default_schema` ảnh hưởng nơi Hibernate tìm/tạo objects. Nếu app validate ở schema `public` nhưng Flyway chạy trong `sales`, lỗi thiếu bảng có thể chỉ là cấu hình search path/schema không đồng nhất.

Xác định rõ:

- Database/catalog nào được dùng.
- Schema nào có tables.
- User hiện tại nhìn thấy những schema nào.
- Quoting/case folding của identifier.
- Migration tool và Hibernate có cùng default schema không.

## 16. Dialect quyết định nhiều chi tiết DDL

Cùng một mapping:

~~~java
@Id
@GeneratedValue(strategy = GenerationType.IDENTITY)
private Long id;
~~~

có thể cho SQL khác nhau theo database:

- PostgreSQL có các cú pháp identity.
- MySQL có `AUTO_INCREMENT`.
- SQL Server có `IDENTITY`.
- Oracle và một số DBMS có cách hỗ trợ identity/sequence riêng.

Với `GenerationType.SEQUENCE`:

~~~java
@Id
@GeneratedValue(
    strategy = GenerationType.SEQUENCE,
    generator = "orderIdGenerator"
)
@SequenceGenerator(
    name = "orderIdGenerator",
    sequenceName = "purchase_order_seq",
    allocationSize = 50
)
private Long id;
~~~

Hibernate có thể cần sequence hoặc đối tượng sinh ID tương ứng. Nhưng không phải DBMS nào cũng có cùng sequence capabilities, và `allocationSize` ảnh hưởng cơ chế cấp phát ID trong ORM.

### 16.1. Không dùng một Dialect để sinh script rồi mặc định chạy trên DB khác

Một DDL script được sinh cho H2 có thể khác PostgreSQL ở:

- Data types.
- Sequence/identity syntax.
- Identifier quoting.
- Enum/JSON support.
- Index/constraint syntax.
- Temporal types và timezone support.
- DDL transaction behavior.

Nếu production dùng PostgreSQL, hãy sinh và thử script trên PostgreSQL version tương thích. H2 in-memory phù hợp test một số logic nhưng không bảo đảm phản ánh hoàn toàn production DDL.

### 16.2. Database version và JDBC driver cũng quan trọng

Ngay cả trong cùng một DBMS, các phiên bản khác nhau có thể hỗ trợ những loại index, generated columns hoặc DDL features khác nhau. Hibernate chọn SQL theo Dialect/database capabilities; cần kiểm tra driver, metadata và database version thực tế.

## 17. Các annotation không đồng nghĩa constraint theo cách trực giác

### 17.1. Bean Validation khác database validation

~~~java
@NotNull
private String customerCode;
~~~

`@NotNull` từ Bean Validation (ví dụ Jakarta Validation) diễn đạt một constraint trong validation layer. Hibernate/Bean Validation integration có thể tham gia tác động schema generation tùy cấu hình/provider, nhưng **không nên dựa vào nó như thay thế cho DB NOT NULL** trong migration.

Để thể hiện ý định column mapping:

~~~java
@Column(name = "customer_code", nullable = false)
private String customerCode;
~~~

Và production migration vẫn phải tạo constraint trong DB thực tế. Cần phân biệt:

- `@NotNull`: kiểm tra giá trị object theo Bean Validation.
- `nullable=false`: thông tin mapping có thể dùng để sinh DDL.
- `NOT NULL` tại database: constraint thực sự được DB enforcement.

Không loại nào tự động thay thế mọi chức năng của hai loại còn lại.

### 17.2. Unique và index

~~~java
@Table(
    uniqueConstraints = @UniqueConstraint(
        name = "uk_external_ref",
        columnNames = "external_ref"
    ),
    indexes = @Index(
        name = "idx_created_at",
        columnList = "created_at"
    )
)
~~~

Metadata này giúp schema generation tạo UNIQUE/index phù hợp. Nhưng ở production:

- Unique constraint thực tế phải được tạo bằng migration/DB.
- Dữ liệu cũ có duplicate cần được xử lý trước khi thêm UNIQUE.
- Index creation có thể giữ locks hoặc tốn tài nguyên lớn.
- Validator không nhất thiết xác minh chi tiết mọi index definition.

**Đừng coi annotation là ràng buộc DB đã tồn tại** nếu schema được tạo bằng migration ngoài Hibernate.

### 17.3. Foreign keys và cascade

~~~java
@ManyToOne(fetch = FetchType.LAZY)
@JoinColumn(
    name = "customer_id",
    foreignKey = @ForeignKey(name = "fk_orders_customer")
)
private Customer customer;
~~~

Hibernate có thể sinh FK theo metadata. Nhưng cascading entity operations (`CascadeType.PERSIST`, `REMOVE`) và database `ON DELETE CASCADE` là những cơ chế khác nhau. Không suy từ một annotation cascade của JPA rằng DDL tự có cùng hành vi FK cascade.

## 18. Lược đồ có thể khác dù entity code không đổi

Ví dụ những yếu tố làm schema khác giữa hai môi trường:

- Hibernate version hoặc Dialect khác nhau.
- Spring Boot naming strategies khác.
- Database version khác.
- JDBC driver metadata khác.
- Database default schema/search path khác.
- Quoted identifiers và case-sensitive names.
- Thiết lập custom `AttributeConverter`/`JdbcType`/enum khác.
- DDL chạy dưới role có quyền khác.
- Một môi trường có Flyway migration bổ sung.
- Một môi trường đã từng chạy `update` nhiều lần nên còn các cột cũ dư.

Điều này giải thích vì sao **generate schema local thành công** không tự chứng minh production schema đúng. Cần chung migration history, dependency versions và validation/integration tests tương thích.

## 19. Khởi động production an toàn

Một kiến trúc triển khai thường dùng:

~~~mermaid
flowchart TD
    A["Build application và migration artifact"] --> B["Review SQL/changelog"]
    B --> C["Backup / rollback plan / DBA approval khi cần"]
    C --> D["Apply versioned migrations"]
    D --> E["Kiểm tra migration history + data invariants"]
    E --> F["Khởi động ứng dụng: Hibernate validate"]
    F --> G{"Validation pass?"}
    G -->|Có| H["Bắt đầu phục vụ traffic"]
    G -->|Không| I["Dừng rollout, điều tra schema/mapping"]
~~~

Ý nghĩa chính:

- Schema changes phải được xác định **trước** khi ứng dụng dùng chúng.
- Runtime application không cần quyền drop bảng.
- Hibernate validation phát hiện sớm một số lỗi phối hợp giữa Java mapping và schema.
- Pipeline có cơ chế fail nếu migration lỗi, chưa đạt điều kiện dữ liệu hoặc validate không đạt.

### 19.1. Fail fast tốt hơn sửa schema âm thầm

Nếu schema thiếu cột `row_version` mà entity yêu cầu, `validate` có thể khiến ứng dụng không khởi động. Đây thường là tín hiệu tốt ở staging/production: phát hiện deployment chưa áp migration thay vì để request đầu tiên gây lỗi đọc/ghi hoặc để Hibernate tự thêm cột bất ngờ.

### 19.2. Migrations có thể cần chạy ngoài ứng dụng

Trong hệ thống nhiều replicas, không nên để mỗi instance tự chạy các lệnh ALTER đồng thời một cách không kiểm soát. Migration tool có cơ chế tracking/locking phù hợp nhưng quy trình orchestrator vẫn phải bảo đảm thứ tự và quyền thực thi. Có thể chạy một job migration duy nhất trước rollout, tùy kiến trúc.

### 19.3. Quyền database

Một phân quyền mẫu:

| Tài khoản | Quyền chính |
| --- | --- |
| Application runtime | SELECT/INSERT/UPDATE/DELETE và quyền thực sự cần |
| Migration role | CREATE/ALTER/DROP/INDEX theo schema được duyệt |
| Read-only analytics | SELECT giới hạn |
| DBA/operator | Quyền vận hành đặc thù theo quy trình |

Quyền cụ thể phụ thuộc DBMS. Đây là nguyên tắc **least privilege**, không phải mẫu GRANT SQL hoàn chỉnh.

## 20. Kiểm thử migration và schema validation

Một quy trình integration test đáng tin cậy thường là:

1. Khởi tạo database trống tương thích DBMS production.
2. Chạy toàn bộ migrations từ đầu.
3. Khởi động Hibernate với `ddl-auto=validate`.
4. Thử các entity reads/writes quan trọng.
5. Kiểm tra FK, UNIQUE, NOT NULL, versioning và type conversions.
6. Thử đường nâng cấp từ bản schema cũ sang mới.
7. Nếu có dữ liệu legacy, chạy backfill và xác nhận không mất/đổi nghĩa dữ liệu.
8. Kiểm tra cleanup và cô lập database test.

### 20.1. Vì sao không chỉ test với create-drop?

Nếu test dùng `create-drop`, Hibernate tạo schema trực tiếp từ entity hiện tại. Test có thể pass dù **migration production bị thiếu một cột**, vì test không dùng migration scripts.

Muốn chứng minh migration đúng, test nên dùng chính migration pipeline để tạo schema rồi Hibernate validate. Có thể có cả hai loại tests:

- Unit/simple integration tests nhanh dùng schema tự sinh.
- Migration compatibility tests dùng DBMS thật hoặc container DB tương thích và chạy migrations.

Hai loại test phục vụ hai mục tiêu khác nhau, không nên lẫn lộn.

### 20.2. Testcontainers hoặc database tạm

Với PostgreSQL production, một database PostgreSQL chạy bằng Testcontainers có thể giúp kiểm tra syntax/DDL behavior sát thực tế hơn H2. Không phải mọi vấn đề performance/locking của production đều tái hiện được với dữ liệu ít, nhưng DDL compatibility sẽ có cơ sở đáng tin cậy hơn.

### 20.3. Tập tình huống cần test

- Migration từ V1 → V2 không làm mất rows.
- Đổi cột có backfill đúng dữ liệu.
- Thêm NOT NULL sau khi dữ liệu sạch.
- UNIQUE constraint thật sự chặn duplicate.
- FK thật sự chặn orphan references nếu domain yêu cầu.
- Version column và optimistic locking hoạt động.
- Enum/JSON/temporal mapping tương thích.
- Schema name/naming strategy khớp migration.
- Validate startup fail khi thiếu bảng/cột quan trọng.
- Một ứng dụng phiên bản cũ có còn chạy được trong rolling deploy không, nếu yêu cầu tương thích.

## 21. Theo dõi schema-tooling SQL

Khi khởi động, Hibernate có thể log các DDL statements hoặc lỗi DDL tùy logging configuration.

Trong Hibernate 6, logger `org.hibernate.SQL` thường hiển thị SQL được phát ở mức DEBUG khi logging framework cấu hình. Một số thông tin schema tooling còn đi qua log categories riêng của Hibernate tool subsystem theo version.

Ví dụ Spring Boot logger:

~~~properties
logging.level.org.hibernate.SQL=DEBUG
~~~

Đừng dùng logging như biện pháp duy nhất để phát hiện việc schema bị sửa. Với production, quan sát migration logs/history, database audit DDL nếu phù hợp và deployment configuration; hạn chế quyền DDL của application là safeguard mạnh hơn.

### 21.1. Khi validate thất bại, cần xem gì?

Nếu nhận lỗi “missing table” hoặc “wrong column type”, kiểm tra lần lượt:

1. Entity mapping hiện tại và các annotation liên quan.
2. Tên bảng/cột thực tế sau naming strategy.
3. Default schema/catalog và search path của database user.
4. Flyway/Liquibase migration history.
5. Database user có quyền xem object metadata không.
6. DDL thật ở schema mục tiêu.
7. Dialect, driver và phiên bản Hibernate.
8. Mapping `@Enumerated`, `@JdbcTypeCode`, converter hoặc custom type.
9. Cách DBMS báo JDBC type metadata.
10. Migrations có chạy trước Hibernate startup không.

Đừng chữa lỗi bằng cách đổi ngay `validate` thành `update` trên production; như vậy có thể tạo schema drift mới thay vì giải quyết nguyên nhân.

## 22. Lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Mỗi lần startup đều mất dữ liệu | Đang dùng `create` hoặc `create-drop` | Chuyển sang migration + validate/none với DB có dữ liệu |
| Validation báo thiếu bảng dù DB có | Sai schema/catalog/search path hoặc tên vật lý | Kiểm tra naming và connection target |
| Validation báo thiếu cột sau deploy | Migration chưa áp hoặc mapping chưa đồng bộ | Chạy migration đúng version rồi validate |
| Update tạo cột mới sau khi rename Java field | Tool không biết đây là rename | Viết migration rename/backfill |
| Update không xóa cột cũ | Không phải migration destructive đầy đủ | Viết migration drop có kiểm soát |
| Enum cột mismatch sau nâng version | Hibernate/Dialect enum type mapping khác | Đối chiếu mapping, DB type, migration |
| Test pass nhưng production lỗi schema | Test dùng create-drop thay vì migrations | Test migration + validate trên DBMS mục tiêu |
| DDL permission denied | Runtime user không có CREATE/ALTER | Dùng migration role riêng, không mở quyền bừa bãi |
| UNIQUE annotation có nhưng DB vẫn chứa duplicate | Constraint chưa được tạo/kiểm tra | Kiểm tra actual DB DDL và migration |
| Thêm NOT NULL thất bại | Dữ liệu cũ có null | Expand/backfill/enforce |
| Hibernate tạo bảng vào schema sai | Default schema/naming khác migration | Đồng bộ schema config và metadata |
| Nhiều replicas đụng nhau khi startup | Mỗi instance cùng auto-create/update | Tách migration thành một bước rollout |
| Generated DDL chạy trên H2 nhưng không chạy trên PostgreSQL | Dialect/data types khác | Sinh và test trên DBMS đích |
| Startup fail vì JDBC metadata inaccessible | DB role, network hoặc driver | Kiểm tra datasource/privileges |
| Migrate đã chạy nhưng validation vẫn fail | Mapping lệch migration hoặc validator/type metadata issue | Kiểm tra từng khác biệt, không bỏ qua mù quáng |
| Hibernate `none` nhưng request đầu tiên lỗi SQL | Không có startup schema validation | Dùng migration tests hoặc `validate` khi phù hợp |

## 23. Ví dụ một quy trình hoàn chỉnh

Giả sử dự án muốn triển khai phiên bản mới thêm cột `shipping_reference` vào `purchase_orders`.

### 23.1. Thay đổi mapping

~~~java
@Column(
    name = "shipping_reference",
    length = 100
)
private String shippingReference;
~~~

### 23.2. Tạo migration versioned

~~~sql
-- V5__add_shipping_reference.sql
alter table purchase_orders
    add column shipping_reference varchar(100);
~~~

### 23.3. CI kiểm chứng trên database tạm

~~~text
1. Tạo database test cô lập.
2. Chạy V1...V5 theo Flyway/Liquibase.
3. Khởi động Hibernate với ddl-auto=validate.
4. Chạy integration tests đọc/ghi PurchaseOrder.
5. Kiểm tra những constraint/data invariants liên quan.
~~~

### 23.4. Staging

Áp migrations lên staging copy hoặc dữ liệu tương tự production, kiểm tra tác động ALTER, khóa, backfill/rollout compatibility nếu cần. Khởi động ứng dụng với `validate`, không với `update`.

### 23.5. Production

1. Backup/rollback/feature toggle plan nếu thay đổi rủi ro.
2. Migration job áp schema mới.
3. Xác nhận history/điều kiện dữ liệu.
4. Khởi động phiên bản app mới với `validate`.
5. Theo dõi startup, error rate và DB metrics.
6. Chỉ sau khi tương thích phiên bản cũ đã được xử lý mới contract/drop các cột cũ.

Quy trình có nhiều bước hơn `ddl-auto=update`, nhưng cho phép biết **chính xác đã thay đổi cái gì, ở đâu, theo phiên bản nào**.

## 24. Phân biệt tạo cấu trúc với xác thực dữ liệu

Schema metadata không tự chứng minh dữ liệu nghiệp vụ đúng.

Ví dụ database đã có:

~~~sql
purchase_orders(
    id,
    customer_id,
    total_amount,
    created_at,
    status,
    row_version
)
~~~

Hibernate `validate` có thể báo thành công nếu những checks nó thực hiện đều đạt. Nhưng vẫn có thể tồn tại:

- `total_amount` âm trong khi domain cấm.
- `status` có giá trị không còn hợp lệ với enum.
- `customer_id` chứa reference hỏng nếu FK không được enforce.
- Dữ liệu duplicate email nếu UNIQUE constraint chưa thực thi.
- Timestamp bị sai timezone do import legacy.
- Version values bị cập nhật ngoài ORM không đúng quy tắc.

Cần thêm:

- DB constraints được quản lý bằng migrations.
- Data validation và backfill scripts.
- Integration tests cho entity conversion.
- Business invariants trong domain/service.
- Monitoring/auditing cho data-quality khi phù hợp.

**Schema validate là công cụ kiểm tra cấu trúc tương thích, không phải một hệ thống kiểm toán chất lượng dữ liệu.**

## 25. Những câu hỏi cần tự trả lời trước khi dùng schema auto-action

1. Database có dữ liệu cần giữ không?
2. Có ai khác hoặc instance khác đang dùng cùng schema không?
3. Runtime DB user có quyền DROP/ALTER không? Có cần không?
4. Hibernate version và Dialect có giống môi trường triển khai không?
5. Mapping mới có rename, data conversion hay backfill không?
6. Migrations có cần hỗ trợ rolling/zero-downtime deployment không?
7. Validation hiện tại kiểm tra những gì và còn khoảng trống nào?
8. Entity có `@SequenceGenerator`, inheritance, secondary tables, JSON/enum hay custom type không?
9. Có DDL-specific logic ngoài metadata như trigger, partial index, grants hoặc partitioning không?
10. Có integration tests chạy migrations thật không?
11. Có history/checksum/version của schema không?
12. Có thể phục hồi nếu một DDL thất bại giữa chừng không?

Nếu câu trả lời cho nhiều câu chưa rõ, **đừng dùng `update` hoặc `create` trên database có giá trị**. Hãy xác định quyền sở hữu schema và quy trình migration trước.

## 26. Bài tập thực hành

### Bài 1 — Chọn action

Với các trường hợp sau, chọn action phù hợp và giải thích:

- Một ví dụ Hibernate đang học trên H2 in-memory, không cần giữ dữ liệu.
- Một ứng dụng production có Flyway và dữ liệu khách hàng thật.
- Một staging environment cần kiểm tra mapping trước rollout.
- Một prototype cá nhân có database disposable nhưng entity thay đổi thường xuyên.

### Bài 2 — Đọc mapping thành DDL

Cho entity:

~~~java
@Entity
@Table(name = "invoices")
public class Invoice {
    @Id
    private Long id;

    @Column(name = "invoice_code", nullable = false, length = 50)
    private String code;

    @Version
    private long version;
}
~~~

Hãy phác thảo bảng, PK và các cột mà metadata cho phép suy ra. Giải thích vì sao SQL type cụ thể của `version` có thể cần xác nhận theo Dialect.

### Bài 3 — Rename và backfill

Một bảng có cột `phone` với 50.000 rows. Entity đổi mapping thành `phone_e164`. Vì sao `update` không đủ để bảo đảm dữ liệu đúng? Hãy thiết kế migration an toàn.

### Bài 4 — Validate không phải toàn bộ schema audit

Liệt kê ba thứ mà schema validator có thể không kiểm tra đầy đủ và giải thích cần công cụ khác để xác nhận chúng như thế nào.

### Bài 5 — Test migration thật

Vì sao integration test dùng `create-drop` có thể pass dù migration SQL thiếu cột? Hãy thiết kế một test dùng Flyway/Liquibase rồi Hibernate `validate`.

### Bài 6 — Tách sinh script và tác động database

Sử dụng Jakarta Persistence properties để sinh create/drop scripts nhưng không chạy DDL lên DB. Giải thích vai trò của `database.action` và `scripts.action`.

### Bài 7 — Multi-instance production

Một hệ thống có 10 replicas cùng kết nối database chung và mỗi replica bật `ddl-auto=update`. Nêu các rủi ro và đề xuất pipeline thay thế.

### Bài 8 — @Column và Bean Validation

Giải thích khác biệt giữa `@NotNull`, `@Column(nullable=false)` và constraint `NOT NULL` đã được tạo thật tại database.

**Gợi ý:** (1) create-drop cho DB disposable, validate cho production/staging sau migration, update chỉ cân nhắc prototype; (2) id PK, invoice_code varchar(50) not null, version mapped; (3) rename/backfill/data checks thay vì add cột rỗng; (4) index/constraints/grants/data checks; (5) test bằng migrations thực; (6) database.action=none, scripts.action=drop-and-create; (7) một migration job với version tracking; (8) object validation, ORM mapping metadata và DB enforcement là ba tầng khác nhau.

## 27. Tài liệu tham khảo

- [Hibernate ORM 6.6 User Guide — Schema Generation](https://docs.hibernate.org/orm/6.6/userguide/html_single/Hibernate_User_Guide.html#schema-generation): schema-management actions và mapping metadata.
- [Hibernate ORM 6.6 User Guide](https://docs.hibernate.org/orm/6.6/userguide/html_single/Hibernate_User_Guide.html): `@Table`, `@Column`, identifier generators, associations, type mapping và Dialect.
- [Hibernate ORM Documentation](https://hibernate.org/orm/documentation/): các tài liệu migration và cấu hình phù hợp phiên bản Hibernate đang chạy.
- [Jakarta Persistence Specification](https://jakarta.ee/specifications/persistence/): schema-generation properties, metadata và DDL generation semantics.
- [Spring Boot Reference — Working with SQL Databases](https://docs.spring.io/spring-boot/reference/data/sql.html): JPA/Hibernate schema initialization và phối hợp database migration.
- [Flyway Documentation](https://documentation.red-gate.com/fd): versioned migrations và schema history.
- [Liquibase Documentation](https://docs.liquibase.com/): changelogs, changesets và triển khai thay đổi database.

**Kết luận:** Hibernate có thể dùng metadata để **sinh**, **xác thực** hoặc **thử cập nhật** schema, nhưng ba công việc có phạm vi và rủi ro rất khác. `create`/`create-drop` phù hợp database disposable và có thể làm mất dữ liệu; `validate` hữu ích để phát hiện một số mismatch mà không sửa DB; `update` tiện khi thử nghiệm nhưng không suy ra được rename, data backfill hay kế hoạch migration an toàn. Với schema cần giữ dữ liệu, hãy quản lý thay đổi bằng migrations có phiên bản và dùng Hibernate validation như một lớp kiểm tra bổ sung. Không để sự thuận tiện của ORM schema tooling thay thế trách nhiệm bảo vệ dữ liệu thật.
