# Tác động của tên bảng, cột, catalog và schema

> **Chủ đề:** Data Persistence Relational Access ORM JPA  
> **Nhóm kiến thức:** Siêu dữ liệu và lược đồ

Một entity Java không tự biết dữ liệu của nó nằm trong bảng nào. **JPA mapping metadata** mô tả cách tên lớp, thuộc tính và quan hệ Java được nối với **tên bảng, tên cột, catalog và schema** của hệ quản trị cơ sở dữ liệu. Khi các tên này bị khai báo sai, ứng dụng có thể không đọc được dữ liệu, ghi nhầm bảng, tạo SQL không hợp lệ, tạo ràng buộc tại vị trí không mong muốn hoặc mất tính tương thích khi triển khai sang môi trường khác.

Ví dụ một hệ thống PostgreSQL lưu đơn hàng tại bảng **sales.purchase_orders**, với các cột **order_id**, **customer_id**, **order_status**. Lớp Java là **PurchaseOrder**, nhưng tên SQL không bắt buộc giống Java:

~~~java
@Entity(name = "PurchaseOrder")
@Table(name = "purchase_orders", schema = "sales")
public class PurchaseOrder {

    @Id
    @Column(name = "order_id")
    private Long id;

    @Column(name = "order_status", nullable = false)
    private String status;
}
~~~

JPA entity có thể được truy vấn bằng:

~~~java
em.createQuery(
    "select o from PurchaseOrder o where o.status = :status",
    PurchaseOrder.class
)
.setParameter("status", "PAID")
.getResultList();
~~~

Trong khi SQL tương ứng có thể giống:

~~~sql
SELECT o.order_id, o.order_status
FROM sales.purchase_orders o
WHERE o.order_status = 'PAID';
~~~

Đây là **minh họa**, không phải SQL bắt buộc provider phải sinh chính xác. Điểm cần nhận ra:

- **PurchaseOrder** và **status** ở JPQL là **tên entity/thuộc tính Java**, không phải bảng/cột SQL.
- **sales** là schema trong ví dụ PostgreSQL.
- **purchase_orders**, **order_id** và **order_status** là những tên vật lý trong database.
- **catalog** có ý nghĩa phụ thuộc database; không thể đánh đồng với schema trên mọi RDBMS.

Bài học sẽ giải thích metadata mapping, default naming, schema/catalog qualification, names của relationships và auxiliary tables, tác động lên SQL/DDL/migration, tính portable, bảo mật đa tenant, lỗi thường gặp và kiểm thử tích hợp.

## 1. Hai hệ thống tên: mô hình Java và lược đồ quan hệ

### 1.1. Tên phía Java/JPA

Một entity có:
- **Tên lớp Java:** com.example.sales.PurchaseOrder;
- **Tên entity JPA:** mặc định thường là tên lớp không có package, hoặc tên chỉ định trong @Entity(name=...);
- **Tên thuộc tính Java:** id, customer, status, totalAmount;
- **Tên relationship:** customer hoặc orderLines;
- **Tên persistence unit:** định danh cấu hình riêng, không phải tên bảng.

Những tên này được dùng khi viết Java và JPQL.

~~~java
@Entity(name = "OrderRecord")
public class PurchaseOrder {
    @Id
    private Long id;

    private String status;
}
~~~

JPQL phù hợp dùng:

~~~sql
select o from OrderRecord o where o.status = :status
~~~

chứ không phải:

~~~sql
select o from purchase_orders o where o.order_status = :status
~~~

Câu thứ hai không phải JPQL chuẩn chỉ vì nó trông giống SQL. Entity name được khai báo là OrderRecord, còn thuộc tính Java vẫn là status.

### 1.2. Tên phía database

Một database row được xác định qua những thành phần như:

~~~text
[catalog].[schema].[table].[column]
       \       \       \       \
        \       \       \       +-- order_status
         \       \       +---------- purchase_orders
          \       +------------------ sales
           +-------------------------- tùy DBMS
~~~

Không phải DB nào cũng cho phép hoặc yêu cầu đủ bốn phần. Một SQL SELECT thường nêu table identifier và column references; catalog/schema có thể được ngầm suy ra từ connection/session.

### 1.3. Tên entity không phải tên table

~~~java
@Entity(name = "SalesOrder")
@Table(name = "purchase_orders")
public class PurchaseOrder {
    // ...
}
~~~

Có ba tên độc lập:
- Java class: PurchaseOrder;
- JPQL entity: SalesOrder;
- SQL table: purchase_orders.

Nếu đổi @Entity(name="...") mà không đổi @Table, JPQL đã viết trước có thể hỏng trong khi database table không đổi. Nếu đổi @Table mà không đổi @Entity, SQL mapping có thể hỏng trong khi JPQL giữ nguyên tên entity.

### 1.4. Tên thuộc tính không phải tên column

~~~java
@Column(name = "order_status")
private String status;
~~~

- Java/JPQL: status;
- Database SQL: order_status.

Đổi tên Java field **status → state** đòi cập nhật JPQL và code sử dụng property, nhưng không bắt buộc đổi tên cột nếu vẫn giữ @Column(name="order_status"). Ngược lại, đổi cột DB order_status → current_status phải được phản ánh trong mapping/migration dù tên Java không đổi.

### 1.5. Ý nghĩa trong production

Mapping sai có thể gây:
- SQL lỗi “table/relation does not exist”;
- SQL lỗi “column does not exist/invalid column name”;
- Truy vấn đọc nhầm schema;
- Foreign key tham chiếu bảng/cột sai;
- Database migration và entity metadata bị lệch;
- Hai entity vô tình ánh xạ cùng bảng;
- Truy vấn không chạy do quyền với schema/catalog;
- Test pass trên H2 nhưng fail trên PostgreSQL/Oracle.

Vì thế naming metadata không chỉ là thẩm mỹ; nó tác động đến **tính đúng đắn dữ liệu, độ ổn định deploy và boundary bảo mật**.

## 2. @Table: ánh xạ entity vào bảng

Annotation **jakarta.persistence.Table** mô tả tên, schema, catalog và một số metadata DDL cho primary table của entity.

~~~java
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "purchase_orders", schema = "sales")
public class PurchaseOrder {

    @Id
    private Long id;
}
~~~

### 2.1. Thuộc tính name

~~~java
@Table(name = "purchase_orders")
~~~

đặt tên table. Nếu không chỉ định name, JPA có default table naming dựa trên entity name và naming rules của provider. SQL thực tế còn có thể đi qua implicit/physical naming strategies, đặc biệt trong Hibernate/Spring Boot.

Không mặc định rằng bỏ @Table sẽ luôn sinh ra đúng chuỗi **purchase_order** hoặc **purchase_orders** trên mọi stack. Phải nhìn generated SQL/schema thực tế.

### 2.2. Thuộc tính schema

~~~java
@Table(name = "purchase_orders", schema = "sales")
~~~

ý nghĩa trên PostgreSQL: bảng được ánh xạ vào **schema sales** thuộc database đang kết nối.

Provider có thể phát SQL tương tự:

~~~sql
SELECT ... FROM sales.purchase_orders ...
~~~

Nếu schema sales không tồn tại, role kết nối không có quyền hoặc table nằm ở public, query có thể thất bại. Schema không được tạo tự động chỉ vì tên xuất hiện trong @Table ở mọi cấu hình. Việc provisioning schema là trách nhiệm triển khai/migration.

### 2.3. Thuộc tính catalog

~~~java
@Table(
    name = "purchase_orders",
    catalog = "sales_database",
    schema = "sales"
)
~~~

**catalog** là thành phần định danh namespace cấp cao theo mô hình metadata SQL/JDBC. Nhưng mỗi DBMS dùng và hỗ trợ nó khác nhau; ví dụ này **không phải cấu hình portable để copy qua PostgreSQL, Oracle, MySQL và SQL Server**.

Catalog có thể đồng nghĩa database trong một số hệ, không được hỗ trợ trong SQL identifier qualification của hệ khác, hoặc chỉ phù hợp với JDBC metadata chứ không phải một cú pháp cross-database query.

### 2.4. Không đặt schema/catalog khi cần dựa vào connection

~~~java
@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder { /* ... */ }
~~~

Lúc đó table thường được xác định trong **default namespace** của connection/provider. Điều này giúp mapping linh hoạt giữa các môi trường nếu DB search path/default schema được cấu hình nhất quán, nhưng cũng có rủi ro ứng dụng đọc **nhầm** bảng cùng tên trong schema khác.

### 2.5. @Table không đổi tên dữ liệu tồn tại

Nếu database đang có bảng:

~~~sql
sales.orders
~~~

và developer đổi Java mapping:

~~~java
@Table(name = "purchase_orders", schema = "sales")
~~~

điều đó **không bảo đảm** bảng sales.orders trong production được rename. Với schema migrations đang dùng, phải có DDL tương thích, chẳng hạn:

~~~sql
ALTER TABLE sales.orders
RENAME TO purchase_orders;
~~~

Đây là cú pháp minh họa cho PostgreSQL. Không dùng auto-ddl update làm thay thế một quy trình rename/migrate đã được review, nhất là khi dữ liệu, indexes, views, stored procedures và các services khác đang tham chiếu tên cũ.

### 2.6. Những thuộc tính DDL khác của @Table

~~~java
@Table(
    name = "purchase_orders",
    schema = "sales",
    uniqueConstraints = {
        @UniqueConstraint(
            name = "uk_orders_external_id",
            columnNames = {"external_id"}
        )
    },
    indexes = {
        @Index(
            name = "ix_orders_status",
            columnList = "order_status"
        )
    }
)
~~~

**columnNames/columnList ở ví dụ này dùng tên cột database**, không phải Java field names. Các metadata này hỗ trợ schema generation; không mặc nhiên tạo UNIQUE/INDEX trên bảng production đã có nếu ứng dụng không sinh/cập nhật DDL.

## 3. @Column: ánh xạ thuộc tính đến cột vật lý

~~~java
@Entity
@Table(name = "purchase_orders", schema = "sales")
public class PurchaseOrder {

    @Id
    @Column(name = "order_id")
    private Long id;

    @Column(name = "order_status", nullable = false, length = 24)
    private String status;

    @Column(name = "total_amount", precision = 19, scale = 2)
    private BigDecimal totalAmount;
}
~~~

### 3.1. Tên cột ảnh hưởng SQL đọc và ghi

Nếu @Column(name="order_status"), provider tìm hoặc cập nhật SQL column **order_status** cho thuộc tính Java **status**. Nếu schema thực tế chỉ có cột status, SQL có thể lỗi khi prepare/execute.

Bảng mapping:

| Java property | SQL column | Kiểu Java | SQL type minh họa |
|---|---|---|---|
| id | order_id | Long | BIGINT |
| status | order_status | String | VARCHAR(24) |
| totalAmount | total_amount | BigDecimal | NUMERIC(19,2) |

### 3.2. Mặc định tên cột

Nếu chỉ:

~~~java
private BigDecimal totalAmount;
~~~

provider có thể dùng tên logic tương ứng property và naming strategy biến thành **total_amount** hoặc giữ **totalAmount** tùy cấu hình.

Vì vậy trong project dùng snake_case, phải phân biệt:
- JPA mapping không chỉ định @Column(name=...);
- Hibernate implicit naming strategy;
- Hibernate physical naming strategy;
- Spring Boot conventions;
- Database identifier folding.

Không khẳng định một Java field camelCase mặc nhiên thành snake_case trong Jakarta Persistence specification.

### 3.3. @Column không dùng cho mọi association

~~~java
@ManyToOne
@JoinColumn(name = "customer_id")
private Customer customer;
~~~

Đây là foreign-key relationship, dùng **@JoinColumn** chứ không phải đặt @Column lên thuộc tính association chỉ vì trong DB nó tương ứng customer_id.

### 3.4. Cột có tên khác do migration

Một migration:

~~~sql
ALTER TABLE sales.purchase_orders
RENAME COLUMN order_status TO status_code;
~~~

đòi sửa mapping:

~~~java
@Column(name = "status_code")
private String status;
~~~

Các JPQL queries vẫn dùng **o.status**. Những native SQL queries, database views, reports, triggers và scripts chứa **order_status** phải được điều chỉnh riêng.

### 3.5. Tên cột cũng xuất hiện trong Index/UNIQUE

~~~java
@Table(
    name = "purchase_orders",
    indexes = {
        @Index(
            name = "ix_orders_customer_status",
            columnList = "customer_id, order_status"
        )
    }
)
~~~

**customer_id, order_status** là tên SQL columns. Nếu nhập nhầm **customer, status** (tên Java fields), DDL generation có thể tạo SQL không hợp lệ hoặc trỏ sai columns.

### 3.6. @Column(table=...) cho secondary table

Khi thuộc tính được lưu ở một secondary table đã khai báo, @Column có thể chỉ định table chứa column:

~~~java
@Column(name = "notes", table = "order_details")
private String notes;
~~~

Điều này **khác** với property table name của @Table: nó lựa chọn bảng thứ cấp cho column, và cần mapping @SecondaryTable phù hợp. Ví dụ đầy đủ ở phần sau.

## 4. Catalog và schema: hai khái niệm dễ bị nhầm

### 4.1. Phân cấp tên mang tính khái niệm

Một mô hình tổng quát:

~~~text
Database server / cluster
       |
       +-- Catalog (tùy DBMS)
              |
              +-- Schema
                     |
                     +-- Table
                            |
                            +-- Column
~~~

Không phải mọi SQL dialect sử dụng đúng hệ phân cấp hoặc cú pháp này. Có hệ xem catalog và database là gần tương đương; có hệ tập trung vào user-owned schema.

### 4.2. PostgreSQL

Trong PostgreSQL:
- Connection thường chọn **một database**.
- Database chứa nhiều schemas, ví dụ **public**, **sales**, **audit**.
- Bảng có thể được tham chiếu bằng **schema.table**, ví dụ **sales.purchase_orders**.
- **search_path** ảnh hưởng cách tìm table khi không ghi schema.
- Không thể dùng catalog qualification như một cách truy vấn tùy ý tới một database PostgreSQL khác trên cùng connection.

Ví dụ:

~~~sql
CREATE SCHEMA IF NOT EXISTS sales;

CREATE TABLE sales.purchase_orders (
    order_id BIGINT PRIMARY KEY,
    order_status VARCHAR(24) NOT NULL
);

SELECT order_id
FROM sales.purchase_orders;
~~~

Với PostgreSQL, nhiều ứng dụng chỉ cần @Table(schema="sales"), **không nhất thiết cần đặt catalog**.

### 4.3. SQL Server

Trong SQL Server, cú pháp thường gặp:

~~~sql
SELECT order_id
FROM SalesDb.sales.purchase_orders;
~~~

Trong ví dụ:
- **SalesDb** là database/catalog;
- **sales** là schema;
- **purchase_orders** là table.

Default schema thường liên quan DB user/role và không nên mặc định luôn là dbo trong mọi tài khoản. Quyền đọc/ghi có thể khác nhau theo database/schema/table.

### 4.4. MySQL và MariaDB

Trong MySQL, **database** và **schema** thường gần đồng nghĩa trong tên SQL:

~~~sql
SELECT order_id
FROM sales_db.purchase_orders;
~~~

Chỉ thấy một thành phần namespace trước table không có nghĩa hệ đang triển khai một schema bên trong catalog theo cách PostgreSQL.

Provider/JDBC có thể biểu diễn **database** qua catalog metadata, nhưng việc kết hợp @Table(schema=..., catalog=...) cần kiểm tra dialect và driver.

### 4.5. Oracle Database

Oracle dùng **schema** gắn với database user/owner trong cách đặt tên object:

~~~sql
SELECT order_id
FROM SALES.PURCHASE_ORDERS;
~~~

Nhiều object names không được quote sẽ được Oracle xử lý theo quy tắc chữ hoa. Catalog trong JPA/JDBC không nên bị coi là một database qualifier có thể sử dụng tương tự SQL Server ba phần.

### 4.6. Bảng so sánh

| DBMS | Namespace thường gặp | Ví dụ SQL | Lưu ý |
|---|---|---|---|
| PostgreSQL | database + schema | sales.purchase_orders | search_path; catalog không dùng để cross-DB tùy ý |
| SQL Server | database/catalog + schema | SalesDb.sales.purchase_orders | multi-part names, default schema, quyền |
| MySQL | database/schema gần đồng nghĩa | sales_db.purchase_orders | Cách provider ánh xạ catalog/schema cần kiểm tra |
| Oracle | owner/schema | SALES.PURCHASE_ORDERS | Chữ hoa thường gặp khi không quote |
| H2/test DB | Tùy mode/cấu hình | PUBLIC.PURCHASE_ORDERS | Không suy ra production dialect |

**Kết luận:** @Table(catalog=...) và @Table(schema=...) là metadata có ý nghĩa, nhưng **SQL cụ thể và mức hỗ trợ phụ thuộc database/provider**.

## 5. Default schema và default catalog tác động thế nào?

### 5.1. Không ghi schema không đồng nghĩa bảng nằm trong public

Với PostgreSQL:

~~~java
@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {
    // ...
}
~~~

Provider có thể phát SQL không có schema:

~~~sql
SELECT ... FROM purchase_orders ...
~~~

Database sẽ tìm bảng theo **search_path** của connection. Nếu search_path là **sales, public**, bảng **sales.purchase_orders** có thể được chọn trước **public.purchase_orders**.

Ngược lại, nếu connection dùng search_path **public**, query có thể:
- Không tìm thấy bảng; hoặc
- Tìm thấy bảng cùng tên ở public, nhưng đó **không phải bảng muốn truy cập**.

### 5.2. search_path là cấu hình session, không phải thuộc tính Java

Ví dụ PostgreSQL:

~~~sql
SHOW search_path;

SET search_path TO sales, public;

SELECT order_id
FROM purchase_orders;
~~~

Phần SQL trên có thể tìm **sales.purchase_orders** tùy các schemas/tables thực sự tồn tại. Nếu dùng application connection pool, việc sửa **session search_path** cần lifecycle management để không rò cấu hình sang request khác.

### 5.3. Default schema của Hibernate

Hibernate có các cấu hình provider-specific, thường gặp:

~~~properties
hibernate.default_schema=sales
~~~

Với Spring Boot có thể được chuyển qua property namespace:

~~~properties
spring.jpa.properties.hibernate.default_schema=sales
~~~

Vì đây là **cấu hình Hibernate**, không phải annotation/setting portable của mọi JPA provider, cần kiểm tra phiên bản, dialect và cách provider dùng default schema trong SQL/DDL/metadata.

### 5.4. Default catalog cũng phụ thuộc provider/dialect

Một cấu hình Hibernate thường gặp:

~~~properties
hibernate.default_catalog=SalesDb
~~~

Không dùng tùy tiện **SalesDb** như default catalog khi deploy PostgreSQL, vì catalog/database semantics khác SQL Server. Dự án nên xác định rõ DBMS và tránh hard-code một namespace không cần thiết.

### 5.5. Tên được đặt rõ trong @Table và cấu hình mặc định

~~~java
@Table(name = "purchase_orders", schema = "sales")
~~~

biểu diễn schema tường minh. Khi có cả explicit metadata và default schema, cần kiểm tra **effective mapping** mà provider sinh ra. Đừng cho rằng default schema sẽ luôn override explicit schema hoặc rằng SQL không bao giờ có qualification.

### 5.6. JDBC connection có current catalog/schema

JDBC cung cấp các khả năng như:

~~~java
Connection connection = dataSource.getConnection();

try {
    System.out.println(connection.getCatalog());
    System.out.println(connection.getSchema());
} finally {
    connection.close();
}
~~~

Kết quả phụ thuộc driver/DB và có thể là null. **getSchema()** không bắt buộc phản ánh toàn bộ PostgreSQL search_path; nó là JDBC API metadata/state, không phải mô tả portable của thứ tự tìm bảng trong mọi dialect.

### 5.7. Tên namespace ảnh hưởng quyền

Giả sử role chỉ có quyền với **sales.purchase_orders**:

~~~sql
SELECT ... FROM sales.purchase_orders;
~~~

Nếu ứng dụng đổi default schema sang **audit** hoặc dùng role không có quyền USAGE/SELECT phù hợp, query có thể bị từ chối dù bảng sales vẫn tồn tại.

**Object tồn tại** và **connection có quyền dùng object** là hai điều kiện khác nhau. Khi gặp lỗi truy vấn, đừng tự động đổi @Table name nếu nguyên nhân là database authorization.

## 6. Chữ hoa/chữ thường, quoted identifiers và từ khóa SQL

Cùng một chuỗi Java có thể được database hiểu khác nhau khi **identifier** có hoặc không được quote.

### 6.1. Unquoted và quoted names trong PostgreSQL

PostgreSQL thường gấp unquoted identifiers về chữ thường:

~~~sql
CREATE TABLE SalesOrders (
    OrderId BIGINT PRIMARY KEY
);
~~~

Table thực tế mang tên **salesorders** và column **orderid** theo cách PostgreSQL xử lý unquoted names.

Trong khi:

~~~sql
CREATE TABLE "SalesOrders" (
    "OrderId" BIGINT PRIMARY KEY
);
~~~

tạo identifiers có chữ hoa/chữ thường phân biệt theo dấu nháy. Sau đó query:

~~~sql
SELECT "OrderId"
FROM "SalesOrders";
~~~

không tương đương với:

~~~sql
SELECT OrderId
FROM SalesOrders;
~~~

nếu chỉ bảng quoted mixed-case tồn tại.

### 6.2. Oracle có quy tắc folding khác

Nhiều unquoted identifiers trong Oracle được xử lý thành chữ hoa, còn quoted identifiers giữ nguyên cách viết. Vì vậy việc dùng quoted identifiers kiểu camelCase có thể khiến migration/SQL clients phải quote liên tục.

**Không khẳng định** PostgreSQL, Oracle, SQL Server và MySQL có một quy tắc case sensitivity duy nhất.

### 6.3. Reserved words

Một entity có bảng tên SQL **order** hoặc cột tên **user** có thể va chạm keywords/chức năng đặc biệt của database.

~~~java
@Entity
@Table(name = "order")
public class Order {
    // ...
}
~~~

Nếu DB coi ORDER là reserved word, provider có thể sinh SQL lỗi khi identifier không được quote.

Chiến lược thường đơn giản nhất: chọn tên không xung đột, ví dụ **purchase_orders**, **account_users** thay vì order/user.

### 6.4. Quoting trong metadata

Cách đặt quoted identifiers ở mapping là **phụ thuộc cú pháp mà JPA/provider chấp nhận** và quy tắc dialect. Ví dụ dùng double quote làm tên:

~~~java
@Table(name = "\"SalesOrders\"")
public class SalesOrder {
    // ...
}
~~~

Phải kiểm tra exact SQL thực tế do provider sinh và cách database hiểu tên. Một số provider hỗ trợ cú pháp/backticks/setting global identifier quoting riêng.

Không trộn Java string escaping với SQL identifier escaping: Java chuỗi "\"SalesOrders\"" chứa dấu quote thực, không phải tên table không-quoted SalesOrders.

### 6.5. Ưu và nhược của quoting

| Cách đặt tên | Ưu điểm | Rủi ro |
|---|---|---|
| lower_snake_case, unquoted | Thường dễ dùng trên PostgreSQL, phù hợp SQL scripts | Phụ thuộc naming strategy nếu Java camelCase |
| UPPERCASE unquoted | Phổ biến ở một số schema Oracle | Khác khi chuyển DB |
| CamelCase quoted | Giữ chính xác chữ hoa/chữ thường | SQL phải quote nhất quán |
| Tên trùng keyword quoted | Có thể dùng tên bắt buộc | Query/migration/tools phải luôn quote |
| Tên không trùng keyword | Ít phải quote | Đôi khi cần migration legacy schema |

**Khuyến nghị kỹ thuật:** Khi thiết kế schema mới, ưu tiên một quy ước đơn giản, nhất quán, không trùng reserved words; chỉ dùng quoted mixed-case khi tương thích với một schema legacy hoặc có yêu cầu rõ.

### 6.6. Giới hạn độ dài identifier

Database thường giới hạn độ dài tên bảng/cột/index/constraint. Quy tắc tính byte/ký tự và mức giới hạn khác nhau; một tên như **uk_tenant_products_historical_external_reference_identifier** có thể bị cắt hoặc từ chối tùy DB.

Nếu nhiều constraints có tên dài và bị truncate thành giống nhau, migration có thể thất bại hoặc khó debug. Nên dùng naming convention với prefix ngắn và uniqueness có chủ đích.

### 6.7. Identifier không phải dữ liệu bind parameter

Có thể bind **giá trị**:

~~~java
query.setParameter("status", "PAID");
~~~

Nhưng không thể dùng JPQL/JDBC parameter bình thường để bind **schema/table/column identifiers** kiểu:

~~~sql
SELECT * FROM :schema.:table
~~~

Các identifiers phải được xác định qua mapping/SQL generation hoặc các cơ chế driver/dialect riêng. Nếu cần chọn tenant schema động, phải dùng **cơ chế multi-tenancy an toàn**, không nối trực tiếp input HTTP vào SQL.

## 7. Implicit naming và physical naming strategy

### 7.1. Default JPA mapping không phải một chính sách snake_case portable

Nếu không chỉ định:

~~~java
@Entity
public class PurchaseOrder {
    @Id
    private Long id;

    private Instant createdAt;
}
~~~

naming mặc định và SQL thực tế có thể khác giữa:
- Provider;
- Phiên bản provider;
- Spring Boot configuration;
- Database dialect;
- Physical naming strategy;
- Cách database xử lý identifier case.

Đừng viết migration với **created_at** chỉ vì Java có createdAt mà chưa xác định actual naming rule.

### 7.2. Implicit naming strategy là gì?

Trong Hibernate, implicit naming strategy định hình **logical name** khi mapping không khai báo tên rõ. Ví dụ entity PurchaseOrder không có @Table name, property createdAt không có @Column name.

### 7.3. Physical naming strategy là gì?

Physical naming strategy trong Hibernate chuyển logical identifiers sang **physical database identifiers**. Một strategy có thể chuyển:
- PurchaseOrder → purchase_order;
- createdAt → created_at;
- customerID → customer_id, tùy thuật toán.

Đây là behavior của Hibernate/configuration cụ thể, không phải phần của tên @Column theo mọi implementation JPA.

### 7.4. Vì sao hai strategy dễ làm schema lệch?

Một project từng chạy Hibernate với strategy tạo snake_case. Khi thay framework/provider configuration, SQL có thể chuyển từ **order_status** sang **orderStatus** hoặc ngược lại.

Nếu migration vẫn dùng bảng/cột cũ, sẽ có lỗi ở startup/first query. Không thay naming strategy mà không kiểm tra metadata và SQL generated.

### 7.5. Explicit names có được physical strategy biến đổi không?

Tùy provider và physical naming strategy, **tên tường minh** trong annotations có thể vẫn được đưa qua giai đoạn physical naming. Vì thế:

~~~java
@Column(name = "OrderStatus")
private String status;
~~~

không nên bị hiểu là cam kết vật lý luôn chính xác **OrderStatus** trên mọi Hibernate configuration. Kiểm tra generated SQL và quoting behavior. Nếu cần giữ tên legacy case-sensitive, thiết kế quoting/naming strategy tương thích.

### 7.6. Đặt tên tường minh cho schema legacy

Khi database đã tồn tại:

~~~java
@Table(name = "legacy_ord_hdr", schema = "legacy_sales")
public class PurchaseOrder {

    @Id
    @Column(name = "ord_hdr_id")
    private Long id;

    @Column(name = "ord_sts_cd")
    private String status;
}
~~~

thường dễ kiểm soát hơn việc dựa vào implicit naming strategy để suy ra các abbreviations như **ord_hdr_id** và **ord_sts_cd**.

### 7.7. Quy trình đổi naming strategy

Khi cần đổi quy ước:
1. Liệt kê entity/table mappings đang dùng trong deployment;
2. Xác định mọi implicit columns và relationships;
3. Mô tả tên SQL cũ và mới;
4. Thiết kế migration/compatibility strategy;
5. Kiểm tra SQL/DDL trên DB mục tiêu;
6. Kiểm tra native SQL và views/procedures dùng tên cũ;
7. Chuyển ứng dụng theo trình tự deploy an toàn.

Đừng chỉ thay class strategy rồi hy vọng ORM tự tìm đúng bảng production.

## 8. @JoinColumn: tên khóa ngoại và referenced column

Giả sử Order trỏ tới Customer qua cột SQL **customer_id**.

~~~java
@Entity
@Table(name = "customers", schema = "sales")
public class Customer {
    @Id
    @Column(name = "customer_id")
    private Long id;

    @Column(name = "display_name")
    private String displayName;
}
~~~

Order:

~~~java
@Entity
@Table(name = "purchase_orders", schema = "sales")
public class PurchaseOrder {
    @Id
    @Column(name = "order_id")
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(
        name = "customer_id",
        referencedColumnName = "customer_id",
        nullable = false,
        foreignKey = @ForeignKey(name = "fk_order_customer")
    )
    private Customer customer;
}
~~~

### 8.1. name là cột FK phía owning table

**@JoinColumn(name="customer_id")** là cột của bảng **purchase_orders** đang chứa foreign key, không phải tên Java property customer.

### 8.2. referencedColumnName là cột phía referenced table

**referencedColumnName="customer_id"** trỏ tới column trong **customers**. Nếu Customer.id thực sự ánh xạ @Column(name="customer_id"), thì có thể dùng default referenced primary key behavior khi phù hợp, không nhất thiết viết nó ở mọi relationship.

**Không dùng tên Java id** trong referencedColumnName nếu cột vật lý được đặt là customer_id, trừ khi mapping/provider định nghĩa trường hợp khác.

### 8.3. Tên FK constraint là chuyện khác với tên FK column

~~~java
@JoinColumn(
    name = "customer_id",
    foreignKey = @ForeignKey(name = "fk_order_customer")
)
~~~

- **customer_id:** SQL column trong orders;
- **fk_order_customer:** tên database FOREIGN KEY constraint;
- **customer:** Java relationship field.

Ba tên độc lập. Đổi tên FK constraint không đồng nghĩa đổi tên column.

### 8.4. @JoinColumn không tự sửa bảng đã tạo

Nếu bảng production thiếu column customer_id hoặc FK constraint, thêm @JoinColumn không đảm bảo migration sẽ tự áp đúng thay đổi. DB cần DDL tương ứng.

### 8.5. @JoinColumns khi khóa kép

Nếu Customer có primary key phức hợp gồm tenant_id và customer_number, relationship có thể cần nhiều join columns:

~~~java
@ManyToOne
@JoinColumns({
    @JoinColumn(
        name = "customer_tenant_id",
        referencedColumnName = "tenant_id"
    ),
    @JoinColumn(
        name = "customer_number",
        referencedColumnName = "customer_number"
    )
})
private Customer customer;
~~~

Mapping này cần Customer composite ID hợp lệ (ví dụ @EmbeddedId) và cặp columns trong DB tương ứng. **Thứ tự/cặp referenced columns phải chính xác**; nếu trỏ nhầm tenant_id, có nguy cơ liên kết cross-tenant hoặc SQL lỗi.

### 8.6. @OneToMany(mappedBy) và tên SQL

~~~java
@OneToMany(mappedBy = "customer")
private List<PurchaseOrder> orders;
~~~

**mappedBy="customer"** là **tên Java relationship property ở PurchaseOrder**, không phải SQL column customer_id. Nếu đổi PurchaseOrder.customer → buyer nhưng chưa đổi mappedBy, mapping có thể fail startup.

### 8.7. @PrimaryKeyJoinColumn và joined inheritance

Các chiến lược như **@Inheritance(strategy = JOINED)** hoặc @SecondaryTable có thể dùng @PrimaryKeyJoinColumn để chỉ rõ names của cột khóa chính/khóa ngoại trong bảng phụ. Các names này ảnh hưởng join SQL và DDL, không tự được suy ra đúng nếu legacy schema sử dụng tên khác mặc định.

## 9. @JoinTable: đặt tên bảng liên kết và các cột của quan hệ

Với một quan hệ many-to-many, JPA thường dùng **join table**. Nếu không khai báo tên tường minh, provider có thể tạo tên dựa trên hai entity và naming strategy. Trong legacy schema, default này thường không khớp.

Giả sử **Product** và **Tag** liên kết qua bảng **catalog.product_tags**.

### 9.1. Ví dụ ManyToMany

~~~java
@Entity
@Table(name = "products", schema = "catalog")
public class Product {

    @Id
    @Column(name = "product_id")
    private Long id;

    @ManyToMany
    @JoinTable(
        name = "product_tags",
        schema = "catalog",
        joinColumns = {
            @JoinColumn(
                name = "product_id",
                referencedColumnName = "product_id"
            )
        },
        inverseJoinColumns = {
            @JoinColumn(
                name = "tag_id",
                referencedColumnName = "tag_id"
            )
        }
    )
    private Set<Tag> tags = new HashSet<>();
}
~~~

Tag:

~~~java
@Entity
@Table(name = "tags", schema = "catalog")
public class Tag {

    @Id
    @Column(name = "tag_id")
    private Long id;

    @Column(name = "tag_name")
    private String name;
}
~~~

Đây là mapping minh họa; để biên dịch cần các imports Jakarta Persistence, java.util.Set/HashSet và constructors/accessors thích hợp.

### 9.2. DDL minh họa

~~~sql
CREATE TABLE catalog.product_tags (
    product_id BIGINT NOT NULL,
    tag_id BIGINT NOT NULL,

    CONSTRAINT pk_product_tags
        PRIMARY KEY (product_id, tag_id),

    CONSTRAINT fk_product_tags_product
        FOREIGN KEY (product_id)
        REFERENCES catalog.products(product_id),

    CONSTRAINT fk_product_tags_tag
        FOREIGN KEY (tag_id)
        REFERENCES catalog.tags(tag_id)
);
~~~

**@JoinTable(name="product_tags", schema="catalog")** ảnh hưởng bảng ở giữa; **joinColumns/inverseJoinColumns** điều khiển tên và hướng FK columns.

### 9.3. Phân biệt owning side và inverse side

Nếu Tag khai báo quan hệ hai chiều:

~~~java
@ManyToMany(mappedBy = "tags")
private Set<Product> products;
~~~

**mappedBy="tags"** trỏ tới Java property Product.tags, không phải table product_tags. Tên table vật lý thuộc mapping ở owning side theo ví dụ.

### 9.4. Sai schema của join table

Một lỗi phổ biến:

~~~java
@Table(name = "products", schema = "catalog")
~~~

nhưng:

~~~java
@JoinTable(name = "product_tags")
~~~

không chỉ định schema, trong khi bảng thực tế là **catalog.product_tags**. Tùy default schema/provider, JPA có thể tìm **public.product_tags** hoặc schema khác.

**Schema của entity table không nên được xem là bằng chứng mọi join table mặc nhiên ở cùng schema.** Hãy xác định default/explicit metadata và generated SQL.

### 9.5. Join table ở schema khác

Có thể có bảng:

~~~text
catalog.products
catalog.tags
relations.product_tags
~~~

Khi đó @JoinTable(schema="relations") giúp trỏ tới namespace khác. Tuy nhiên cross-schema foreign keys và privileges phụ thuộc DB. Người vận hành cần cấp quyền cho cả schema **relations** và referenced tables.

### 9.6. Khi join table thành entity riêng

Nếu product_tags có thêm **created_at**, **assigned_by**, **priority** hoặc trạng thái nghiệp vụ, nên cân nhắc ánh xạ **ProductTag** thành entity riêng với @Table(schema=..., name=...). Khi đó các join columns và entity names không còn chỉ là tự động @ManyToMany nữa.

Thay đổi này đòi migration và API compatibility khi DB table đã được dùng bởi SQL writers khác.

## 10. @CollectionTable cho ElementCollection

Một entity có danh sách các mã alias không nhất thiết ánh xạ alias thành entity riêng. JPA cho phép **@ElementCollection** lưu giá trị trong collection table.

~~~java
@Entity
@Table(name = "products", schema = "catalog")
public class Product {

    @Id
    @Column(name = "product_id")
    private Long id;

    @ElementCollection
    @CollectionTable(
        name = "product_aliases",
        schema = "catalog",
        joinColumns = @JoinColumn(name = "product_id")
    )
    @Column(name = "alias_name")
    private Set<String> aliases = new HashSet<>();
}
~~~

SQL table tương ứng:

~~~sql
CREATE TABLE catalog.product_aliases (
    product_id BIGINT NOT NULL,
    alias_name VARCHAR(255) NOT NULL,

    CONSTRAINT fk_aliases_product
        FOREIGN KEY (product_id)
        REFERENCES catalog.products(product_id)
);
~~~

### 10.1. Có hai tên cột khác nhau

- **product_id** từ @CollectionTable.joinColumns: FK trỏ tới Product.
- **alias_name** từ @Column trên element collection: cột lưu String value.

Không nhầm collection Java name **aliases** với SQL column alias_name.

### 10.2. Default collection table naming có thể không khớp legacy

Nếu bỏ @CollectionTable, provider sẽ suy ra table name theo rules. Với schema legacy đã có **catalog.product_aliases**, đặt name/schema tường minh tránh phụ thuộc naming strategy.

### 10.3. @AttributeOverride trong Embeddable collection

Khi @ElementCollection chứa embeddables, các @AttributeOverride có thể đổi tên cột của properties nhúng trong collection table.

~~~java
@Embeddable
public class Dimension {
    private BigDecimal width;
    private BigDecimal height;
}
~~~

Ví dụ dùng:

~~~java
@ElementCollection
@CollectionTable(
    name = "product_dimensions",
    schema = "catalog",
    joinColumns = @JoinColumn(name = "product_id")
)
@AttributeOverrides({
    @AttributeOverride(
        name = "width",
        column = @Column(name = "dimension_width")
    ),
    @AttributeOverride(
        name = "height",
        column = @Column(name = "dimension_height")
    )
})
private List<Dimension> dimensions = new ArrayList<>();
~~~

**name="width"** trong AttributeOverride là Java embeddable property path; **@Column(name="dimension_width")** là SQL column. Mapping nhầm hai namespace dẫn tới lỗi tìm column hoặc ghi nhầm.

## 11. @SecondaryTable và một entity trên nhiều bảng

Đôi khi một entity logic được chia thành:
- Bảng chính **sales.purchase_orders** chứa ID, customer_id, status;
- Bảng phụ **sales.order_details** chứa note dài hoặc metadata bổ sung.

JPA hỗ trợ @SecondaryTable cho trường hợp này.

### 11.1. Mapping minh họa

~~~java
@Entity
@Table(name = "purchase_orders", schema = "sales")
@SecondaryTable(
    name = "order_details",
    schema = "sales",
    pkJoinColumns = @PrimaryKeyJoinColumn(
        name = "order_id",
        referencedColumnName = "order_id"
    )
)
public class PurchaseOrder {

    @Id
    @Column(name = "order_id")
    private Long id;

    @Column(name = "order_status")
    private String status;

    @Column(
        name = "internal_notes",
        table = "order_details"
    )
    private String internalNotes;
}
~~~

Ở đây Java class chỉ là **một entity** nhưng state của nó nằm ở hai SQL tables, được liên kết qua primary key.

### 11.2. DDL minh họa

~~~sql
CREATE TABLE sales.purchase_orders (
    order_id BIGINT PRIMARY KEY,
    order_status VARCHAR(24) NOT NULL
);

CREATE TABLE sales.order_details (
    order_id BIGINT PRIMARY KEY,
    internal_notes TEXT,

    CONSTRAINT fk_details_order
        FOREIGN KEY (order_id)
        REFERENCES sales.purchase_orders(order_id)
);
~~~

### 11.3. @Column(table=...) có thể ảnh hưởng nơi ghi dữ liệu

Nếu quên **table="order_details"** cho internalNotes, provider có thể mặc định cột nằm ở primary table. Nếu DB chỉ có column đó ở secondary table, SQL sẽ lỗi. Ngược lại đặt sai secondary table name làm provider phát JOIN/INSERT/UPDATE tới bảng không tồn tại.

### 11.4. Các quy tắc schema/catalog vẫn áp cho secondary table

@SecondaryTable có thể có schema/catalog riêng. Không mặc định vì @Table(schema="sales") mà mọi secondary table luôn ở sales trong mọi cấu hình.

### 11.5. @SecondaryTables khi có nhiều bảng phụ

Một entity có thể sử dụng nhiều secondary tables. Tên secondary tables phải đủ rõ để phân biệt @Column(table=...). Khi schema có những bảng phụ cùng tên ở nhiều namespaces, cần kiểm tra cách provider resolve tên table trong metadata và SQL qualification.

### 11.6. Secondary table khác OneToOne entity

@SecondaryTable nói **một entity mapping qua nhiều tables**. @OneToOne nói **hai entity có identity/lifecycle riêng** được liên kết. Khi có hai bảng với quan hệ 1:1, không tự kết luận hai cách ánh xạ này tương đương về cascade, locking, versioning và semantics.

## 12. Tên của sequences và table generators

Khi primary key được sinh từ database, namespace của object cấp ID cũng quan trọng.

### 12.1. Sequence generator

~~~java
@Id
@GeneratedValue(
    strategy = GenerationType.SEQUENCE,
    generator = "purchase_order_seq_gen"
)
@SequenceGenerator(
    name = "purchase_order_seq_gen",
    sequenceName = "purchase_order_seq",
    schema = "sales",
    allocationSize = 50
)
private Long id;
~~~

Một số thuộc tính/khả năng của generator khác nhau theo phiên bản Jakarta Persistence/provider. Ví dụ minh họa dùng các thành phần phổ biến: **generator name** trong Java metadata khác **SQL sequenceName**, và **schema** xác định namespace cho database sequence khi được hỗ trợ.

### 12.2. DDL PostgreSQL minh họa

~~~sql
CREATE SEQUENCE sales.purchase_order_seq
    START WITH 1
    INCREMENT BY 50;
~~~

**INCREMENT BY** trong SQL và **allocationSize** trong JPA cần tương thích với strategy/provider đang dùng. Không mặc định cứ allocationSize=50 thì mọi DB sequence DDL phải viết y hệt trong mọi phiên bản Hibernate; cần kiểm tra generator optimizer và migration.

### 12.3. Sequence không nằm ở schema của table một cách mặc nhiên

Một entity @Table(schema="sales") không bảo đảm sequence auto-generated mặc định cũng mang namespace sales nếu generator/provider config khác. Việc lookup sequence ở schema sai có thể khiến INSERT thất bại ngay cả khi SELECT trên bảng chính hoạt động.

### 12.4. TableGenerator cũng có namespace

Một @TableGenerator dùng bảng lưu giá trị ID (ví dụ **sales.id_generators**) cũng cần table name/schema/catalog/column metadata đúng. Đây là **bảng phụ trợ để sinh khóa**, không phải bảng entity chính.

Nếu generator table không được deploy hoặc quyền không đủ, provider có thể không cấp được ID. Vấn đề không nằm ở @Table của entity dù exception xuất hiện khi persist.

### 12.5. Không lạm dụng fully qualified sequence name trong sequenceName

Một vài developers ghi sequenceName="sales.purchase_order_seq" đồng thời schema="sales". Tùy provider/dialect có thể tạo qualification lặp hoặc quoting khó đoán. Ưu tiên dùng metadata schema tách riêng khi provider hỗ trợ và kiểm tra generated SQL.

## 13. @AttributeOverride, @AssociationOverride và tên nhúng

### 13.1. Embeddable dùng lại với tên cột khác

~~~java
@Embeddable
public class Money {
    @Column(name = "amount")
    private BigDecimal amount;

    @Column(name = "currency")
    private String currency;
}
~~~

Một Order có hai Money fields:

~~~java
@Embedded
@AttributeOverrides({
    @AttributeOverride(
        name = "amount",
        column = @Column(name = "total_amount")
    ),
    @AttributeOverride(
        name = "currency",
        column = @Column(name = "total_currency")
    )
})
private Money total;

@Embedded
@AttributeOverrides({
    @AttributeOverride(
        name = "amount",
        column = @Column(name = "shipping_amount")
    ),
    @AttributeOverride(
        name = "currency",
        column = @Column(name = "shipping_currency")
    )
})
private Money shipping;
~~~

Nếu không override phù hợp, hai embeddable properties có thể muốn ánh xạ đến cùng SQL columns **amount/currency**, gây mapping collision hoặc nhầm giá trị.

### 13.2. Java property paths và SQL column names

Trong @AttributeOverride:
- **name="amount"** là thuộc tính Java của embeddable;
- **column = @Column(name="total_amount")** là cột vật lý.

Đối với nested embeddables, property path có thể gồm nhiều mức theo mapping, và cú pháp path/behavior phải theo provider/spec hỗ trợ.

### 13.3. AssociationOverride

Nếu một embeddable chứa association cần tham chiếu cột FK khác nhau khi được dùng nhiều lần, **@AssociationOverride** cho phép chỉ định join columns tương ứng.

~~~java
@AssociationOverride(
    name = "contact",
    joinColumns = @JoinColumn(
        name = "billing_contact_id"
    )
)
~~~

**contact** là Java property path, **billing_contact_id** là SQL FK column. Không đảo hai tên.

### 13.4. Chuyển tên embeddable không nhất thiết đổi DB

Nếu Java refactor **total** thành **grandTotal**, nhưng @AttributeOverrides vẫn chỉ tới các physical columns cũ đúng cách, bảng DB không bắt buộc đổi tên. Ngược lại refactor Java property trong Money **amount → value** đòi cập nhật override paths, dù SQL column vẫn là total_amount.

## 14. JPQL, Criteria API và native SQL chịu tác động khác nhau

### 14.1. JPQL đi qua entity metadata

~~~java
List<PurchaseOrder> orders = em.createQuery(
    """
    select o
    from PurchaseOrder o
    where o.status = :status
    """,
    PurchaseOrder.class
)
.setParameter("status", "PAID")
.getResultList();
~~~

Provider dùng mapping @Entity/@Table/@Column để chuyển **PurchaseOrder.status** thành đúng SQL table/column. Nếu rename SQL column trong DB và cập nhật mapping đúng, JPQL có thể giữ nguyên.

### 14.2. Criteria API dùng metamodel attributes

~~~java
CriteriaBuilder cb = em.getCriteriaBuilder();
CriteriaQuery<PurchaseOrder> cq =
    cb.createQuery(PurchaseOrder.class);

Root<PurchaseOrder> root =
    cq.from(PurchaseOrder.class);

cq.select(root).where(
    cb.equal(root.get("status"), "PAID")
);

List<PurchaseOrder> result =
    em.createQuery(cq).getResultList();
~~~

**root.get("status")** là tên Java persistent attribute. Không thay bằng **"order_status"** trừ khi entity thực sự có property đó.

Với static JPA metamodel, có thể dùng typed attributes để giảm lỗi string refactor.

### 14.3. Native SQL dùng physical names

~~~java
List<?> rows = em.createNativeQuery(
    """
    select o.order_id, o.order_status
    from sales.purchase_orders o
    where o.order_status = :status
    """
)
.setParameter("status", "PAID")
.getResultList();
~~~

Trong native SQL phải dùng đúng syntax/qualification của DB. @Column(name="order_status") **không tự rewrite một SQL string sai**.

### 14.4. Các chỗ dễ quên khi rename DB column

Khi đổi **order_status → status_code**:
- JPQL dùng o.status có thể giữ nguyên nếu mapping update;
- Criteria root.get("status") có thể giữ nguyên;
- Native SQL phải đổi order_status → status_code;
- Views, reports, stored procedures, functions và triggers cần review;
- Index/constraint definitions cần review;
- DTO projection qua native SQL aliases có thể thay đổi;
- Data migration/backfill có thể cần dual-column compatibility.

### 14.5. Native result mapping và aliases

Nếu dùng SQL projection:

~~~sql
SELECT o.order_id AS id,
       o.order_status AS status
FROM sales.purchase_orders o;
~~~

**AS id/status** là output aliases; chúng có thể được DTO/result mappings sử dụng và không đồng nghĩa với tên cột thật. Đừng nhầm alias của SELECT với @Column(name) khi chẩn đoán lỗi.

### 14.6. Tên schema/cột không được bind bằng :param

Trong JPQL hoặc native SQL, bind parameters đại diện **giá trị**, không phải table/column identifier. Dynamic SQL tự ghép raw user input vào schema/table name tạo nguy cơ SQL injection và truy cập cross-tenant. Cần định nghĩa allowlist/metadata/multi-tenancy strategy riêng.

## 15. Tên vật lý tác động tới DDL, constraints và indexes

Metadata JPA không chỉ giúp SELECT/UPDATE. Khi provider tạo schema, tên của **tables, columns, foreign keys, unique constraints và indexes** có thể xuất hiện trong DDL.

### 15.1. Ví dụ metadata tổng hợp

~~~java
@Entity(name = "PurchaseOrder")
@Table(
    name = "purchase_orders",
    schema = "sales",
    uniqueConstraints = {
        @UniqueConstraint(
            name = "uk_orders_external_ref",
            columnNames = {"external_ref"}
        )
    },
    indexes = {
        @Index(
            name = "ix_orders_customer_status",
            columnList = "customer_id, order_status"
        )
    }
)
public class PurchaseOrder {

    @Id
    @Column(name = "order_id")
    private Long id;

    @Column(name = "external_ref", nullable = false)
    private String externalReference;

    @Column(name = "order_status", nullable = false)
    private String status;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(
        name = "customer_id",
        referencedColumnName = "customer_id",
        foreignKey = @ForeignKey(
            name = "fk_orders_customer"
        )
    )
    private Customer customer;
}
~~~

Đây là mapping minh họa; Customer phải được khai báo entity và imports tương ứng phải có. **Các tên physical identifiers** tại @UniqueConstraint, @Index, @JoinColumn khác với tên Java **externalReference/status/customer**.

### 15.2. DDL tương ứng về mặt ý tưởng

~~~sql
CREATE TABLE sales.purchase_orders (
    order_id BIGINT PRIMARY KEY,
    external_ref VARCHAR(255) NOT NULL,
    order_status VARCHAR(24) NOT NULL,
    customer_id BIGINT NOT NULL,

    CONSTRAINT uk_orders_external_ref
        UNIQUE (external_ref),

    CONSTRAINT fk_orders_customer
        FOREIGN KEY (customer_id)
        REFERENCES sales.customers(customer_id)
);

CREATE INDEX ix_orders_customer_status
ON sales.purchase_orders (
    customer_id,
    order_status
);
~~~

Provider/database có thể sinh DDL với kiểu cột, indexes và constraint order khác. Đây không phải script được JPA bảo đảm 100%.

### 15.3. Đặt lại tên constraint không làm dữ liệu đổi

Nếu đổi **uk_orders_external_ref** thành **uk_purchase_orders_external_reference**, dữ liệu/column vẫn có thể như cũ; chỉ tên object constraint thay đổi. Nhưng migration tool và database metadata phải phản ánh tên mới, và error handler nào dựa vào constraint name cũng cần cập nhật.

### 15.4. Constraint/index name có phạm vi uniqueness riêng

Trong một số databases, index names cần unique trong schema/database namespace chứ không chỉ trong từng table; databases khác có quy tắc khác. Nếu mọi entity đều dùng tên **ix_status**, schema generation có thể gặp collision. Dùng prefix có ý nghĩa như ix_orders_status, ix_invoices_status và kiểm tra identifier length.

### 15.5. Tên tables/columns trong SQL migration phải khớp mapping

Nếu Java:

~~~java
@Column(name = "external_ref")
private String externalReference;
~~~

nhưng migration lại tạo **external_reference**, startup với schema validation có thể lỗi; hoặc ứng dụng chỉ lỗi khi chạy SQL đầu tiên nếu không validate.

Quy trình review nên so **mapping và migration**, không chỉ so Java field names.

### 15.6. DDL generation không đồng nghĩa migration engine

JPA/Hibernate schema generation hữu ích trong môi trường dev/test, nhưng production thường có migration đã được kiểm soát bởi Flyway, Liquibase hoặc pipeline khác.

**Thêm @Index/@UniqueConstraint/@Table(schema=...) không bảo đảm thay đổi tự được áp lên bảng production.** Cần deploy và xác minh SQL migration.

## 16. Schema drift và đổi tên bảng/cột an toàn

**Schema drift** xảy ra khi mapping của ứng dụng, database thực tế và scripts/tools khác không còn nói cùng một ngôn ngữ về tên.

### 16.1. Một đổi tên nhỏ có thể ảnh hưởng nhiều thành phần

Giả sử đổi:

~~~text
sales.orders → sales.purchase_orders
sales.orders.status → sales.purchase_orders.order_status
~~~

Những thành phần có thể phải cập nhật:
- @Table và @Column;
- @JoinColumn/@JoinTable trong các entity liên quan;
- DDL migration;
- Views và materialized views;
- Triggers/stored procedures/functions;
- Native SQL trong application;
- ETL/batch scripts;
- DB grants;
- Index/constraint names nếu quy ước yêu cầu;
- Reports/dashboards;
- CDC configurations và downstream consumers;
- Tests/fixtures và monitoring queries.

Đổi tên mapping trong Java chưa có nghĩa tất cả dependencies được sửa.

### 16.2. Rename tại chỗ

Một migration PostgreSQL minh họa:

~~~sql
ALTER TABLE sales.orders
RENAME TO purchase_orders;

ALTER TABLE sales.purchase_orders
RENAME COLUMN status TO order_status;
~~~

Nếu chỉ một version application chạy và có maintenance window, cách này có thể đủ sau khi kiểm tra tất cả phụ thuộc. Với rolling deploy nhiều versions, **version cũ có thể vẫn tìm sales.orders** trong lúc migration đã rename table.

### 16.3. Expand-and-contract cho rolling deployments

Khi old app và new app cùng tồn tại:
1. **Expand:** bổ sung cột/bảng/mapping tương thích với cả hai phiên bản, hoặc compatibility view/dual-write được thiết kế.
2. **Backfill:** đồng bộ dữ liệu cũ sang cấu trúc mới.
3. **Deploy:** chuyển reads và writes sang tên mới.
4. **Observe:** kiểm tra không còn clients dùng tên cũ.
5. **Contract:** loại cột/bảng/view cũ sau khi bảo đảm không còn phụ thuộc.

Không phải mọi rename chỉ cần thêm một column; có thể cần trigger/sync protocol để tránh dữ liệu lệch trong giai đoạn hai schema versions.

### 16.4. Đổi schema của bảng

Với PostgreSQL:

~~~sql
ALTER TABLE public.purchase_orders
SET SCHEMA sales;
~~~

Đây là thay đổi namespace của table, không phải câu lệnh tạo một bản sao ở sales. Phải xét:
- Privileges;
- Foreign keys và các object phụ thuộc;
- Search path của sessions;
- Migration order;
- Các SQL scripts dùng public.purchase_orders;
- Rollback strategy;
- Downtime hoặc lock behavior.

**Đừng chỉ sửa @Table(schema="sales") rồi kỳ vọng production tự di chuyển bảng từ public sang sales.**

### 16.5. Kiểm tra sau deploy

Một verification thực tế:
- Kết nối bằng **đúng DB role** của ứng dụng;
- Xem table/column và schema/catalog thực tế;
- Chạy JPA find và một query JPQL;
- Chạy join relationships thường dùng;
- Kiểm tra ID generators;
- Kiểm tra native SQL;
- Kiểm tra quyền SELECT/INSERT/UPDATE;
- Kiểm tra cả multi-node/multi-version nếu rollout chưa kết thúc.

### 16.6. Schema validation không phải chứng minh mọi thứ đều đúng

Hibernate hỗ trợ các chế độ như **validate** để đối chiếu một phần mapping/schema:

~~~properties
spring.jpa.hibernate.ddl-auto=validate
~~~

Nhưng khả năng kiểm tra indexes, CHECK constraints, privileges, triggers, stored procedures, cross-schema associations và naming behavior phụ thuộc provider. Một startup validate thành công **không bảo đảm** mọi SQL path/ràng buộc business đều đúng. Cần integration tests cho những đường truy cập quan trọng.

### 16.7. Không dùng một rename migration để đổi ý nghĩa nghiệp vụ

Nếu bảng **orders** hiện lưu purchase orders, đổi thành **purchase_orders** có thể chỉ là đổi tên. Nếu chuyển một phần rows sang bảng khác và thay đổi constraints, đó là **data migration**, không chỉ naming metadata. Phải định nghĩa semantics, row identities, backfills và transaction consistency.

## 17. Multi-tenancy và schema-per-tenant

Một thiết kế multi-tenant có thể dùng cùng các table names nhưng tách schema:

~~~text
Database: app_db
  |
  +-- tenant_acme
  |     +-- purchase_orders
  |     +-- customers
  |
  +-- tenant_beta
  |     +-- purchase_orders
  |     +-- customers
  |
  +-- shared
        +-- currencies
~~~

Mỗi tenant có bảng **purchase_orders**, nhưng chúng không phải cùng bảng. **Tên schema là một phần của identity của SQL object**.

### 17.1. Hard-code schema trong @Table không phù hợp với đổi tenant động

~~~java
@Table(
    name = "purchase_orders",
    schema = "tenant_acme"
)
~~~

là mapping trỏ rõ tới schema tenant_acme. Nếu service xử lý tenant_beta, không thể chỉ đổi một Java variable tenantId rồi mong annotation tự thay schema trong mọi query.

Một mapping có schema cố định phù hợp ứng dụng/scope cố định; với dynamic schema-per-tenant cần cơ chế quản lý tenant-aware connections hoặc SQL identifier qualification.

### 17.2. Hibernate multi-tenancy là khả năng provider-specific

Hibernate có các cơ chế chọn tenant, quản lý connections, điều chỉnh namespace hoặc datasource tùy phiên bản và chiến lược. Những tên interface/config có thể thay đổi giữa các phiên bản; cần sử dụng tài liệu đúng Hibernate release.

**Đừng coi multi-tenancy strategy của Hibernate là API chuẩn của mọi Jakarta Persistence provider.**

### 17.3. Thay đổi search_path trong pooled connection phải được quản lý

Một cách DB-specific có thể là đặt PostgreSQL search_path phù hợp với tenant:

~~~sql
SET search_path TO tenant_acme, public;
~~~

Nếu connection này được trả về pool mà search_path không reset đúng, request tiếp theo của tenant_beta có thể vô tình đọc **tenant_acme.purchase_orders**.

Đây là lỗi **rò dữ liệu giữa tenants** chứ không chỉ lỗi “table not found”.

Cần:
- Chọn tenant từ thông tin xác thực và server-side authorization;
- Chỉ dùng schema names từ allowlist do server quản lý;
- Thiết lập namespace trước mọi SQL của transaction;
- Reset/restore connection state khi connection được trả về pool;
- Test concurrency giữa tenants;
- Dùng provider multi-tenancy/connection management đáng tin cậy thay vì tự rải SET search_path ở mỗi repository.

### 17.4. SET LOCAL trong PostgreSQL

Khi phù hợp với transaction, một lựa chọn là:

~~~sql
BEGIN;
SET LOCAL search_path TO tenant_acme, public;
SELECT * FROM purchase_orders;
COMMIT;
~~~

**SET LOCAL** có phạm vi transaction trong PostgreSQL, giúp giảm nguy cơ rò session state nếu được sử dụng đúng. Nhưng:
- Không giải quyết injection nếu tenant name đến từ input không đáng tin;
- Không tự tạo transaction khi application chưa bắt đầu;
- Không tự bảo vệ connection pool hay queries phát trước SET LOCAL;
- Không thay tenant authorization;
- Không portable sang mọi DB.

### 17.5. Không nối raw tenantId vào SQL

Rất nguy hiểm:

~~~java
String sql = "select * from " +
    request.getTenantId() + ".purchase_orders";
~~~

Tenant identifier có thể bị dùng để chèn SQL hoặc truy cập schema khác nếu không được validate. JDBC bind parameters không thể bind table/schema identifiers như một value thông thường.

Cần ánh xạ **tenant identity được xác thực → schema định nghĩa sẵn**; sử dụng identifier quoting/whitelisting và provider/driver controls phù hợp.

### 17.6. Schema không tự thay row-level authorization

Ngay cả khi mỗi tenant có schema riêng, application vẫn phải xác minh:
- Caller được phép truy cập tenant đó;
- Chỉ đúng datasource/schema được chọn;
- Shared tables áp tenant constraints nếu có;
- Background jobs và cache keys phân biệt tenant;
- Migrations được chạy cho đúng tenants.

Một user biết chuỗi schema tenant_acme không có nghĩa họ được quyền truy vấn hoặc cập nhật nó.

### 17.7. Multi-tenancy và sequence names

Nếu các tenants có tables/sequences riêng:
- tenant_acme.purchase_order_seq;
- tenant_beta.purchase_order_seq;

thì generator phải tham chiếu đúng tenant namespace. Nếu sequence dùng chung ngoài ý muốn, ID allocation/permission có thể khác kỳ vọng; nếu sequence tenant-specific không tồn tại, persist thất bại dù table có tồn tại.

### 17.8. Migrations theo tenant

Một migration tạo cột order_status trên tenant_acme.purchase_orders nhưng quên tenant_beta làm schema drift. Cần:
- Migration orchestration cho từng tenant;
- Tracking phiên bản schema per tenant;
- Backward compatibility khi rolling deploy;
- Monitoring tenant migration failures;
- Chặn requests vào tenant chưa được migration khi không tương thích.

### 17.9. Alternatives: tenant_id và database-per-tenant

Schema-per-tenant không phải lựa chọn duy nhất:

| Chiến lược | Cách phân tách | Tác động metadata |
|---|---|---|
| Shared tables + tenant_id | Một table, tenant_id phân biệt | Cần tenant predicates/RLS và constraints |
| Schema-per-tenant | Tên table giống nhau ở schemas khác | Namespace chọn theo tenant, migrations từng schema |
| Database-per-tenant | Database/catalog/connection riêng | Routing datasource/catalog, quản trị nhiều DB |
| Hybrid | Tables shared và tenant-specific | Cần mapping rõ cho từng nhóm |

Một ứng dụng có thể dùng schema cố định cho shared tables và tenant schema động cho business tables. Phải hiểu scope mỗi mapping và SQL context, không đặt mọi @Table(schema=...) giống nhau.

## 18. Security: tên bảng/schema không phải chỉ là metadata vô hại

### 18.1. Least privilege

DB role chạy ứng dụng nên chỉ có:
- Quyền connect tới DB phù hợp;
- Quyền USAGE/CREATE trong schema khi thực sự cần;
- SELECT/INSERT/UPDATE/DELETE trên tables cần thiết;
- Quyền dùng sequences cần thiết;
- Không có quyền truy cập audit/private schemas nếu không phục vụ nghiệp vụ.

Không cấp quyền rộng chỉ để “chữa” một lỗi @Table(schema=...) bị đặt nhầm.

### 18.2. Default search path đáng tin

Ở PostgreSQL, search_path liên quan cách lookup SQL objects. Nếu một schema trong search_path cho phép một role không đáng tin tạo functions/objects, điều đó có thể tạo rủi ro name resolution, không chỉ chọn nhầm table.

Cần tránh search_path bao gồm các namespaces không đáng tin trong những thao tác nhạy cảm; sử dụng schema qualification/permission management thích hợp.

### 18.3. SQL injection qua identifier khác injection qua value

Binding:

~~~java
query.setParameter("status", userInput);
~~~

giúp xử lý **giá trị** an toàn hơn so với nối chuỗi. Nhưng userInput chứa **schema/table name** không thể được bảo vệ bằng cách đặt vào :status; cần mapping/allowlist identifiers và không cho client điều khiển schema raw.

### 18.4. Logging cũng có thể làm lộ namespace

SQL logs có thể lộ tên schema tenant, bảng nhạy cảm, column names hoặc bind values. Trong production, đừng bật debug SQL/parameter logging không kiểm soát. Với hệ đa tenant, logs nên bảo vệ identifiers chứa thông tin nhạy cảm và có correlation IDs.

### 18.5. Tên schema không thay data security

Một lỗi authorization có thể làm role/query chọn sai tenant schema ngay cả khi @Table hoàn toàn đúng. Bài toán bảo mật cần test per-tenant isolation, quyền database và application authorization, không chỉ schema naming convention.

## 19. Chẩn đoán lỗi table/column/catalog/schema

Khi một lời gọi JPA thất bại vì tên SQL, đừng vội kết luận entity hoặc database hỏng. Xác định **tên Java**, **tên physical identifier**, **namespace connection**, **SQL do provider sinh** và **quyền DB**.

### 19.1. “relation/table does not exist”

Ví dụ PostgreSQL:

~~~text
ERROR: relation "purchase_orders" does not exist
~~~

Các nguyên nhân:
- @Table(name="purchase_orders") nhưng DB dùng orders;
- Table tồn tại ở sales, query tìm public;
- Search_path của connection không chứa sales;
- Migration chưa chạy ở database hiện tại;
- Application đang kết nối sai database;
- Quoted mixed-case table khác unquoted identifier;
- Role không có quyền/khả năng nhìn thấy object phù hợp;
- Multi-tenant routing chọn schema sai.

Quy trình:
1. Xác nhận JDBC URL/database/user hiện tại;
2. Xem generated SQL;
3. Xem schema và table trong DB catalog;
4. Kiểm tra search_path/default schema;
5. Kiểm tra quoting/case;
6. Kiểm tra migration history và grants.

### 19.2. “column does not exist / invalid column name”

Có thể do:
- Java field camelCase nhưng physical strategy kỳ vọng snake_case khác;
- @Column(name=...) cũ sau migration rename;
- @JoinColumn dùng sai FK column;
- @AttributeOverride đặt nhầm tên;
- @Column(table=...) trỏ sai secondary table;
- @Index.columnList/uniqueConstraint.columnNames dùng Java property thay DB column;
- Native SQL vẫn dùng tên cũ.

Đọc SQL thật để xác định **provider đang tìm cột ở bảng nào**, không chỉ so tên với Java source.

### 19.3. Foreign key mapping lỗi

Ví dụ @JoinColumn:

~~~java
@JoinColumn(
    name = "customer_id",
    referencedColumnName = "customer_id"
)
~~~

nhưng Customer entity ánh xạ @Column(name="id"). Nếu database FK reference thực tế tới **customers.id**, giá trị referencedColumnName sai có thể khiến provider không resolve mapping/DDL hoặc query join. Kiểm tra cả **owning table column** và **referenced table column**.

### 19.4. Lỗi khi startup trước khi có SQL SELECT

Provider có thể phát lỗi metadata tại bootstrap nếu:
- Duplicate logical/physical columns;
- mappedBy trỏ tới property không tồn tại;
- AttributeOverride path sai;
- @Column(table="...") không trỏ bảng mapped;
- Relationship join references không hợp lệ;
- Một entity mâu thuẫn giữa @Table và inheritance mapping.

Không đổ lỗi toàn bộ cho “table chưa tồn tại”. Một lỗi boot mapping có thể chỉ liên quan Java metadata.

### 19.5. Lỗi permission denied

~~~text
permission denied for schema sales
~~~

cần xử lý grant/role/schema access; **đổi @Table(schema="public") để query chạy được** có thể khiến ứng dụng truy cập sai dữ liệu. Ưu tiên sửa role/privileges hoặc đúng schema theo thiết kế.

### 19.6. “sequence does not exist”

Nếu entity mapped sales.purchase_orders nhưng generator dùng sequence ở public, INSERT có thể fail vì không tìm thấy sequence/không có USAGE, dù SELECT trên table hoạt động.

Cần xác nhận sequence name/schema và generator configuration, không chỉ @Table.

### 19.7. Quoted mixed-case lookup

Nếu table thực tế là PostgreSQL **"PurchaseOrders"**, SQL:

~~~sql
SELECT * FROM purchaseorders;
~~~

không tương đương:

~~~sql
SELECT * FROM "PurchaseOrders";
~~~

Không sửa tên Java class bằng cách đổi chữ hoa tùy tiện; phải xác định quoted physical identifier và mapping/dialect.

### 19.8. Multi-node khác nhau nhưng mapping giống nhau

Nếu node A và B dùng cùng code nhưng:
- A kết nối database đúng;
- B dùng JDBC URL khác;
- A search_path=sales;
- B search_path=public;
- A migration mới;
- B migration cũ;

cùng query Java có thể cho kết quả khác. Cần log configuration fingerprint an toàn, schema version và tenant routing, không chỉ diff source code.

### 19.9. Bảng khắc phục nhanh

| Triệu chứng | Tầng cần xem | Kiểm tra đầu tiên |
|---|---|---|
| JPQL lỗi “unknown entity” | JPA entity naming | @Entity(name), persistence unit scanning |
| JPQL lỗi “could not resolve property” | Java attribute naming | status hay orderStatus? |
| SQL “table not found” | @Table/default schema | effective schema.table, DB connection |
| SQL “column not found” | @Column/naming strategy | physical column actual |
| @ManyToOne SQL join sai | @JoinColumn | FK/PK physical names |
| @OneToMany(mappedBy) bootstrap lỗi | Java property reference | mappedBy là tên field Java |
| Join table không tồn tại | @JoinTable/default namespace | schema của bảng liên kết |
| ElementCollection lỗi | @CollectionTable/@Column | FK và element value column |
| Secondary table lỗi | @SecondaryTable/@Column(table) | table/PK join names |
| Cannot obtain generated ID | @SequenceGenerator/TableGenerator | generator object schema/permission |
| Quoted identifiers fail | SQL case sensitivity | double-quotes, actual case |
| Query chạy ở dev, lỗi prod | Migration/dialect/default naming | schema actual và SQL |
| Không đọc được tenant B | Tenant schema routing | tenant identifier → schema mapping |
| Đọc dữ liệu tenant khác | Search_path leakage/security | Connection reset, auth, tests |
| Schema đổi nhưng API query lỗi | Native SQL còn tên cũ | grep SQL strings và views |
| Index DDL lỗi | @Index columnList | physical column names; index namespace |
| Provider validate pass, runtime vẫn lỗi | Validation không bao phủ toàn bộ | Run integration queries |
| DB object tồn tại nhưng permission denied | DB grants/owner | Role, schema privileges |
| Table trong public thay vì sales | Default schema/DDL | migration và @Table mapping |
| Schema tên đúng, data sai | Wrong database/replica/tenant | JDBC connection/transaction routing |

## 20. Quy trình kiểm chứng ánh xạ trên database thực

Một kiểm thử mapping nên trả lời: **JPA đang đọc/ghi đúng SQL object trong đúng namespace hay không?** Không chỉ test em.persist trả về ID.

### 20.1. Thiết lập fixture hai schema cùng table name

Trên PostgreSQL:

~~~sql
CREATE SCHEMA IF NOT EXISTS sales;
CREATE SCHEMA IF NOT EXISTS archive;

CREATE TABLE sales.purchase_orders (
    order_id BIGINT PRIMARY KEY,
    order_status VARCHAR(24) NOT NULL
);

CREATE TABLE archive.purchase_orders (
    order_id BIGINT PRIMARY KEY,
    order_status VARCHAR(24) NOT NULL
);

INSERT INTO sales.purchase_orders(order_id, order_status)
VALUES (42, 'PAID');

INSERT INTO archive.purchase_orders(order_id, order_status)
VALUES (42, 'ARCHIVED');
~~~

Trong môi trường test, bảo đảm schema/rows được tạo bằng migrations/fixtures cách ly, không chạy DDL hủy dữ liệu trong database production.

### 20.2. Entity mapping chỉ rõ schema

~~~java
import jakarta.persistence.*;

@Entity(name = "PurchaseOrder")
@Table(name = "purchase_orders", schema = "sales")
public class PurchaseOrder {

    @Id
    @Column(name = "order_id")
    private Long id;

    @Column(name = "order_status", nullable = false)
    private String status;

    protected PurchaseOrder() {}

    public Long getId() { return id; }
    public String getStatus() { return status; }
}
~~~

### 20.3. Test đọc đúng table sales

~~~java
@Test
void readsSalesSchemaNotArchive() {
    EntityManager em = emf.createEntityManager();

    try {
        PurchaseOrder order =
            em.find(PurchaseOrder.class, 42L);

        assertNotNull(order);
        assertEquals("PAID", order.getStatus());
    } finally {
        em.close();
    }
}
~~~

Fixture có cùng ID nhưng status khác trong archive giúp phát hiện **đọc nhầm schema** nếu có misconfiguration. Chỉ có một table duy nhất sẽ khó chứng minh provider đã qualify đúng namespace.

### 20.4. Test JPQL dùng entity/property names

~~~java
@Test
void jpqlUsesEntityAndAttributeNames() {
    EntityManager em = emf.createEntityManager();

    try {
        List<PurchaseOrder> result = em.createQuery(
            """
            select o
            from PurchaseOrder o
            where o.status = :status
            """,
            PurchaseOrder.class
        )
        .setParameter("status", "PAID")
        .getResultList();

        assertEquals(1, result.size());
        assertEquals(42L, result.get(0).getId());
    } finally {
        em.close();
    }
}
~~~

Test dùng **PurchaseOrder** (entity name) và **status** (Java property), không phải sales.purchase_orders/order_status trong JPQL.

### 20.5. Test SQL namespace độc lập với JPA

Dùng JDBC DataSource:

~~~java
try (Connection c = dataSource.getConnection();
     PreparedStatement ps = c.prepareStatement(
         """
         select order_status
         from sales.purchase_orders
         where order_id = ?
         """
     )) {

    ps.setLong(1, 42L);

    try (ResultSet rs = ps.executeQuery()) {
        assertTrue(rs.next());
        assertEquals("PAID", rs.getString(1));
    }
}
~~~

Đây là SQL đọc database trực tiếp; nó chứng minh fixture ở sales có giá PAID nhưng không chứng minh JPA mapping đúng. **Ghép cả hai tests** mới có cơ sở kết luận JPA đọc đúng object.

### 20.6. Test default schema bị bỏ trống

Có thể tạo **một test persistence unit/mapping riêng** không dùng @Table(schema=...), rồi cấu hình connection search_path cố ý tới archive để quan sát nó đọc archive.purchase_orders. Test này minh họa sự phụ thuộc namespace.

Không sửa một mapped entity đang chạy để thay schema trong cùng EntityManagerFactory rồi kỳ vọng provider tự rebuild mapping. Mapping thường được thiết lập khi tạo EntityManagerFactory.

### 20.7. Kiểm tra database metadata

JDBC DatabaseMetaData có APIs như:

~~~java
DatabaseMetaData md = connection.getMetaData();

try (ResultSet tables = md.getTables(
        null,
        "sales",
        "purchase_orders",
        new String[] {"TABLE"}
)) {
    while (tables.next()) {
        System.out.println(
            tables.getString("TABLE_SCHEM") + "." +
            tables.getString("TABLE_NAME")
        );
    }
}
~~~

Các tham số **catalog** và **schemaPattern** phụ thuộc JDBC driver/DB; database identifier folding có thể ảnh hưởng kết quả. Có thể cần điều chỉnh case/pattern tùy DB. Metadata lookup không thay phép thử truy vấn JPA.

### 20.8. Test @JoinColumn và join SQL

Tạo Customer#100 trong sales.customers và Order#42 có customer_id=100. Test:

~~~java
PurchaseOrder order =
    em.find(PurchaseOrder.class, 42L);

assertEquals(
    100L,
    order.getCustomer().getId()
);
~~~

Ví dụ yêu cầu PurchaseOrder có field/getter **customer** theo mapping đã khai báo ở bài; không copy riêng test sang lớp không có association.

Bật SQL logs để biết provider đang dùng **sales.customers** với **customer_id**, không phải một table/cột khác do implicit naming.

### 20.9. Test association table và secondary table

Với @JoinTable, @CollectionTable và @SecondaryTable, nên có fixture chứa:
- Sản phẩm có ít nhất một tag;
- Alias element collection có dữ liệu;
- Order có internalNotes ở secondary table;
- IDs tồn tại ở đúng schema.

Nếu chỉ test empty collections, nhiều mapping sai có thể chưa thực sự truy cập bảng liên kết.

### 20.10. Test generator schema

Tạo entity mới bằng @SequenceGenerator(sequenceName="purchase_order_seq", schema="sales") và gọi persist/flush trong transaction test. Nếu sequence sai namespace hoặc quyền, lỗi có thể xuất hiện tại thời điểm cấp ID. Kiểm tra sequence/schema hiện hữu bằng SQL riêng để phân biệt permission và naming.

### 20.11. Test explicit quoted identifiers

Nếu schema có legacy quoted table **"SalesOrders"**, tạo test mapping tương ứng rồi xác minh:
- Generated SQL có quote đúng;
- Connection role có quyền;
- JPQL entity name vẫn độc lập SQL table name;
- Migration có đúng quoted identifier.

Không dùng H2 mặc định làm bằng chứng case folding giống PostgreSQL/Oracle.

### 20.12. Test native SQL sau rename

Khi migration đổi order_status → status_code, nên test cả:
- JPQL o.status qua updated @Column;
- Native SQL gọi status_code;
- DTO mapping/aliases;
- Stored procedure hoặc report SQL có liên quan.

Chỉ test repository.findById chưa phát hiện một native SQL string cũ nằm ở endpoint ít gọi.

### 20.13. Test multi-tenant isolation

Với schema-per-tenant:
1. Tenant A có Order#42 status=PAID;
2. Tenant B có Order#42 status=DRAFT;
3. Request A đọc PAID;
4. Request B đọc DRAFT;
5. Dùng connection pool và chạy chuỗi A → B → A;
6. Xác minh không có search_path/session leak;
7. Kiểm tra request giả mạo tenant name bị từ chối;
8. Kiểm tra quyền DB và schema migration versions.

Một test chạy một tenant ở một JVM không chứng minh isolation của schema switching.

### 20.14. SQL logging và security

Trong test có thể bật SQL logging của provider để quan sát generated SQL. Nhưng không dùng SQL debug logs trong production một cách không kiểm soát khi queries chứa thông tin nhạy cảm.

### 20.15. Kết luận của integration tests

Một mapping đáng tin nên được kiểm chứng bằng:
- Database schema thực đã có table/columns;
- JPA entity truy cập đúng row/namespace;
- JPQL sử dụng đúng entity/property names;
- Native SQL dùng đúng physical identifiers;
- Relationships và auxiliary tables hoạt động;
- Generators và grants hợp lệ;
- Tenant routing không làm rò dữ liệu;
- Migration tương thích deployment.

Không chỉ nhìn annotations mà cho rằng metadata đã chính xác ở runtime.

## 21. Một ví dụ chuyển đổi từ schema cũ sang schema mới

Giả sử hệ thống legacy có:

~~~text
Database: sales_db
Schema: legacy
Table: ORD_HDR
Columns: ORD_ID, CUST_ID, STS_CD, TOT_AMT
~~~

Java code mới dùng tên thân thiện:

~~~java
@Entity(name = "PurchaseOrder")
@Table(name = "ORD_HDR", schema = "legacy")
public class PurchaseOrder {

    @Id
    @Column(name = "ORD_ID")
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(
        name = "CUST_ID",
        referencedColumnName = "CUST_ID"
    )
    private Customer customer;

    @Column(name = "STS_CD")
    private String status;

    @Column(name = "TOT_AMT")
    private BigDecimal totalAmount;
}
~~~

### 21.1. Không cần đổi SQL table khi refactor Java class

Trong JPQL:

~~~sql
select o from PurchaseOrder o where o.status = :status
~~~

Vẫn có thể truy cập bảng legacy. Lợi ích: code Java có tên dễ hiểu mà không buộc đổi schema production ngay.

### 21.2. Nhưng legacy uppercase có thể cần quy tắc case rõ

Nếu DB là Oracle với unquoted identifiers, uppercase convention có thể là bình thường. Nếu PostgreSQL có quoted legacy table **"ORD_HDR"**, mapping và SQL dialect phải quote chính xác. Không đánh đồng mọi uppercase strings với quoted identifiers.

### 21.3. Khi quyết định rename DB sau đó

Giả sử muốn chuyển legacy.ORD_HDR → sales.purchase_orders:
1. Xác định owner của schema, quyền và dependencies;
2. Thiết kế migration/backfill;
3. Xử lý compatibility old/new apps;
4. Sửa @Table/@Column và các joins/secondary/generators;
5. Kiểm tra SQL native và ETL;
6. Test cùng database và role production;
7. Theo dõi errors sau rollout.

### 21.4. Refactor Java và DB là hai công việc có thể tách rời

| Thay đổi | Bắt buộc sửa SQL schema ngay? | Nơi khác cần xem |
|---|---|---|
| Java class PurchaseOrder → SalesOrder, giữ @Entity name | Không nhất thiết | Imports, Java APIs |
| @Entity(name="PurchaseOrder") → "SalesOrder" | Không nhất thiết | JPQL entity references |
| Java field status → state, giữ @Column | Không nhất thiết | JPQL paths, Criteria, getters |
| @Column(name="STS_CD") → "order_status" | Có nếu DB thực tế vẫn STS_CD | Migration/native SQL |
| @Table(schema="legacy") → "sales" | Có nếu table chưa chuyển | Namespace, grants, migration |
| SQL table ORD_HDR → purchase_orders | Có | @Table, scripts, views, grants |
| SQL column CUST_ID → customer_id | Có | @JoinColumn, FK, SQL |
| Đổi constraint name | Có nếu muốn đổi vật lý | Migration, error handling |
| Đổi Hibernate physical naming strategy | Có thể | Effective mapping, migration, SQL logs |

## 22. Bài tập thực hành

Các bài tập giúp người học xác định **tên nào thuộc Java/JPA metadata, tên nào thuộc SQL database**, đồng thời đánh giá hệ quả khi đổi table, column, catalog và schema. Mỗi bài nên trả lời cả hai câu: “Mapping/SQL nào đúng?” và “Cần kiểm chứng điều gì trên database thực tế?”.

### Bài 1. Phân biệt ba tên của entity

Cho:

~~~java
@Entity(name = "OrderRecord")
@Table(name = "purchase_orders", schema = "sales")
public class PurchaseOrder {
    @Id
    private Long id;
}
~~~

Hãy ghi:
- Java class name;
- JPQL entity name;
- SQL table name;
- SQL schema;
- Một JPQL SELECT đúng;
- Một SQL SELECT đúng cho PostgreSQL.

### Bài 2. Tên property khác tên column

Field:

~~~java
@Column(name = "order_status")
private String status;
~~~

Viết JPQL WHERE lọc theo trạng thái PAID và SQL WHERE tương đương. Vì sao JPQL o.order_status không đúng nếu entity không có Java property order_status?

### Bài 3. Đổi Java field nhưng giữ database column

Developer refactor field **status → state** và giữ @Column(name="order_status"). Những gì cần đổi:
- Java accessors;
- JPQL;
- Criteria root.get(...);
- SQL migration;
- Native SQL?

Giải thích vì sao DB column có thể giữ nguyên.

### Bài 4. Đổi @Entity(name) nhưng giữ @Table

Đổi:

~~~java
@Entity(name = "PurchaseOrder")
~~~

thành:

~~~java
@Entity(name = "SalesOrder")
~~~

nhưng giữ @Table(name="purchase_orders"). Điều gì xảy ra với JPQL dùng FROM PurchaseOrder? Bảng SQL có bắt buộc đổi không?

### Bài 5. Default table naming

Bỏ @Table khỏi class PurchaseOrder. Có chắc provider tạo/đọc table purchase_order không? Trình bày vai trò implicit và physical naming strategies.

### Bài 6. @Column mặc định

Field Java **createdAt** không có @Column. Có chắc database column là created_at? Thiết kế test/quan sát generated SQL để xác định physical name.

### Bài 7. catalog khác schema

So sánh namespace trong PostgreSQL, SQL Server, MySQL và Oracle:
- Mỗi hệ dùng catalog/database/schema như thế nào?
- Cú pháp qualification thường gặp?
- Vì sao không copy nguyên @Table(catalog="SalesDb", schema="sales") qua cả bốn DB?

### Bài 8. PostgreSQL search_path

Có hai bảng:
- public.purchase_orders, status=TEST;
- sales.purchase_orders, status=PAID.

Entity chỉ khai báo @Table(name="purchase_orders"). Khi search_path là public, sales, kết quả có thể là gì? Nếu đổi thành sales, public thì sao? Đề xuất cách tránh accidental table selection.

### Bài 9. SQL Server database và schema

Viết một SQL SELECT dùng SalesDb.sales.purchase_orders. Xác định catalog/database, schema và table. Những quyền nào có thể khiến query lỗi dù object tồn tại?

### Bài 10. Quoted identifier PostgreSQL

Database tạo:

~~~sql
CREATE TABLE "SalesOrders" (
    "OrderId" BIGINT PRIMARY KEY
);
~~~

Tại sao SELECT * FROM SalesOrders có thể thất bại? Viết SQL đúng và mô tả cách mapping JPA cần tương thích quoting/case.

### Bài 11. Reserved word

Một entity @Table(name="order") gây syntax error. Đề xuất hai giải pháp:
- Rename table thành tên không trùng keyword;
- Quote identifier theo dialect/provider.

Nêu đánh đổi khi portable qua nhiều databases.

### Bài 12. Tên index/constraint

Cho:

~~~java
@Column(name = "external_ref")
private String externalReference;
~~~

Khi khai báo @UniqueConstraint(columnNames=...), nên dùng external_ref hay externalReference? Viết ví dụ @Index cho customer_id và order_status.

### Bài 13. Tên khóa ngoại

~~~java
@ManyToOne
@JoinColumn(name = "customer_id")
private Customer customer;
~~~

Hãy phân biệt:
- customer;
- customer_id;
- fk_order_customer.

Cột nào thuộc bảng orders? Tên nào là constraint nếu dùng @ForeignKey?

### Bài 14. referencedColumnName

Customer.id mapped @Column(name="customer_pk"). Order.customer dùng @JoinColumn(name="customer_id"). Nếu viết referencedColumnName="id", có thể sai thế nào? Khi nào có thể bỏ referencedColumnName để dựa vào referenced primary key mặc định?

### Bài 15. mappedBy

Parent có:

~~~java
@OneToMany(mappedBy = "customer")
private List<PurchaseOrder> orders;
~~~

Nếu child đổi Java field customer thành buyer mà SQL column vẫn customer_id, phải sửa mappedBy thành gì? Vì sao không đổi mappedBy thành customer_id?

### Bài 16. Composite FK qua tenant_id

Customer có khóa kép tenant_id/customer_number. PurchaseOrder có customer_tenant_id/customer_number. Hãy viết @JoinColumns và phân tích rủi ro cross-tenant nếu bỏ tenant_id trong join.

### Bài 17. JoinTable schema

Product và Tag dùng many-to-many qua catalog.product_tags. Tạo @JoinTable với schema/catalog phù hợp, joinColumns product_id, inverseJoinColumns tag_id. Nếu quên schema mà connection default=public, lỗi gì có thể xảy ra?

### Bài 18. ElementCollection

Một Product có Set<String> aliases, DB lưu ở catalog.product_aliases(product_id, alias_name). Viết @ElementCollection, @CollectionTable và @Column. Phân biệt FK column với value column.

### Bài 19. Secondary table

Order lưu status ở sales.purchase_orders và notes ở sales.order_details. Viết @SecondaryTable và @Column(name="internal_notes", table="order_details"). Điều gì xảy ra nếu quên thuộc tính table?

### Bài 20. Embeddable overrides

Order có Money total và Money shipping, mỗi Money có amount/currency. Hãy viết @AttributeOverrides sao cho columns không trùng nhau. Tên bên trái name và tên @Column có thuộc cùng namespace không?

### Bài 21. Sequence namespace

Order table nằm sales.purchase_orders, sequence nằm sales.purchase_order_seq. Viết @SequenceGenerator. Nếu provider tìm public.purchase_order_seq, INSERT có thể thất bại khi nào? Lỗi có nhất thiết thuộc @Table không?

### Bài 22. Physical naming strategy đổi

Một phiên bản Spring Boot/Hibernate tạo order_status, phiên bản sau sinh orderStatus. DB vẫn có order_status. Hãy đề xuất một quy trình an toàn để đổi strategy hoặc giữ compatibility mapping.

### Bài 23. Native SQL không được metadata rewrite

JPA field status mapped order_status. Một native query dùng WHERE status = :status và DB chỉ có order_status. Tại sao @Column không tự rewrite native SQL string? Viết query đúng.

### Bài 24. JPQL và criteria

Viết cùng một điều kiện lọc order.status="PAID" bằng JPQL và Criteria API. Trong Criteria root.get(...), sử dụng status hay order_status? Vì sao?

### Bài 25. Đổi table trong production

Đổi sales.orders thành sales.purchase_orders. Nêu các thành phần phải review: mappings, migrations, grants, views, ETL, native SQL, sequences, constraints, rolling deploy. Vì sao đổi annotation không phải database migration?

### Bài 26. Thay schema của bảng

Bảng public.purchase_orders được chuyển sang sales.purchase_orders. Viết DDL PostgreSQL minh họa và kế hoạch cập nhật @Table, default schema, grants và services dùng table cũ.

### Bài 27. Schema drift

Ứng dụng có @Column(name="external_ref") nhưng database cột external_reference. Hibernate validate có thể phát hiện gì? Cần kiểm chứng thêm những gì nếu validate pass nhưng runtime query lỗi?

### Bài 28. Multi-tenancy schema-per-tenant

Hai tenants A/B cùng có table purchase_orders và Order#42 khác dữ liệu. Đề xuất kiến trúc selection tenant schema và ít nhất năm tests chứng minh một request tenant B không đọc được dữ liệu tenant A.

### Bài 29. Connection pool search_path leak

Request A đặt search_path=tenant_acme, trả connection về pool mà không reset. Request B nhận connection ấy. Mô tả một kịch bản dữ liệu bị lộ và cách tránh bằng transaction-local settings/provider multi-tenancy/connection cleanup.

### Bài 30. SQL injection qua tên schema

Một endpoint nhận tenantSchema từ query parameter rồi nối:

~~~java
"SELECT * FROM " + tenantSchema + ".purchase_orders"
~~~

Vì sao :param binding không giải quyết thay thế SQL identifier? Đề xuất allowlist mappings và tenant authorization từ authenticated context.

### Bài 31. Database metadata

Dùng JDBC DatabaseMetaData.getTables(...) để liệt kê bảng ở schema sales. Những khác biệt catalog/schemaPattern/case có thể khiến cùng code trả kết quả khác trên PostgreSQL và MySQL?

### Bài 32. Test hai schemas cùng tên bảng

Tạo:
- sales.purchase_orders(order_id=42, order_status=PAID);
- archive.purchase_orders(order_id=42, order_status=ARCHIVED).

Viết entity @Table(schema="sales") và integration test assert find(42).status == PAID. Giải thích tại sao fixture này kiểm chứng schema mapping tốt hơn khi chỉ có một table.

### Bài 33. Schema catalog không cùng DB

Một developer gán catalog="inventory_db" cho entity PostgreSQL với hy vọng đọc database khác. Tại sao cách này không portable và thường không phù hợp cross-database query trên PostgreSQL? Hãy đề xuất datasource/service boundary nếu thật sự có hai databases.

### Bài 34. Roles và quyền trên schema

Table sales.purchase_orders tồn tại, nhưng ứng dụng nhận permission denied. Liệt kê các bước kiểm tra DB role, quyền schema và table, sequence permission, connection current user. Vì sao đổi @Table(schema="public") chỉ để query chạy là nguy hiểm?

### Bài 35. Tổng hợp mapping legacy

Thiết kế các mappings cho hệ legacy:
- Tables **legacy.ORD_HDR**, **legacy.CUST**, **legacy.ORD_DETAIL**;
- PK **ORD_ID**, **CUST_ID**;
- Order có Java properties **id/status/customer/notes**;
- SQL columns **ORD_ID/STS_CD/CUST_ID/NOTE_TEXT**;
- Notes ở secondary table;
- Orders dùng sequence **legacy.ORD_SEQ**;
- JPQL vẫn dùng entity name **PurchaseOrder**;
- Có reporting native SQL cần SELECT từ legacy.ORD_HDR.

Viết @Entity/@Table/@Column/@JoinColumn/@SecondaryTable/@SequenceGenerator và SQL/JPQL minh họa. Chỉ rõ những điểm không portable nếu database dùng quoted uppercase identifiers.

### Bài 36. Migrate khi nhiều versions cùng chạy

Old app truy vấn sales.orders, new app truy vấn sales.purchase_orders. Deploy theo rolling strategy, không được downtime. Hãy thiết kế expand-and-contract/compatibility view hoặc phương án chuyển đổi khác, bảo đảm cả hai versions đọc/ghi đúng trong cửa sổ rollout.

### Bài 37. Tác động đổi tên đối với cache

Nếu entity mapping chuyển từ table sales.orders sang sales.purchase_orders mà EntityManagerFactory/provider cache còn state cũ từ deployment trước, cần cân nhắc gì về schema migrations, cache regions, invalidation và compatibility? Có thể kết luận chỉ đổi @Table là mọi cache tự sạch không?

### Bài 38. Test provider migration

Ứng dụng chuyển Hibernate sang một JPA provider khác. Những implicit naming assumptions nào cần kiểm thử:
- Default table/column names;
- Quoting;
- Join tables;
- Secondary tables;
- Schema/catalog;
- Sequences;
- Generated DDL?

Vì sao explicit mapping và integration tests quan trọng hơn việc chỉ compile?

### Bài 39. Mismatch index column list

@Table(indexes=@Index(columnList="createdAt")) nhưng DB physical column là created_at. Sửa ra sao? Giải thích vì sao @Index.columnList dùng physical column identifiers, không phải JPQL property paths.

### Bài 40. Thiết kế naming convention

Một project mới dùng PostgreSQL và JPA:
- Chọn naming convention cho tables, columns, indexes, foreign keys và sequences;
- Chọn cách biểu diễn schema names;
- Quy định quoting/reserved words;
- Quy định explicit mapping với legacy tables;
- Quy định schema migration ownership;
- Quy định cách kiểm thử JPQL/native SQL/multi-tenancy.

Trình bày tradeoff giữa implicit naming để giảm annotation và explicit naming để giảm phụ thuộc framework configuration.

## 23. Bảng tra cứu nhanh về tên và phạm vi

| Cấu hình/API | Tên thuộc Java/JPA hay SQL? | Ví dụ | Ghi nhớ |
|---|---|---|---|
| Java class | Java | PurchaseOrder | Không nhất thiết là SQL table |
| @Entity(name) | JPQL entity | PurchaseOrder | Dùng sau FROM trong JPQL |
| Java field | Java/JPQL property | status | Dùng o.status |
| @Table(name) | SQL table | purchase_orders | Primary table của entity |
| @Table(schema) | SQL schema | sales | Phụ thuộc DB/dialect |
| @Table(catalog) | Catalog/database metadata | SalesDb | Không portable như nhau |
| @Column(name) | SQL column | order_status | Khác tên property |
| @JoinColumn(name) | SQL FK column phía owning table | customer_id | Không phải relationship property |
| @JoinColumn(referencedColumnName) | SQL referenced column | customer_id | Cần đúng target column |
| @ForeignKey(name) | SQL constraint | fk_order_customer | Không phải FK column |
| @JoinTable(name) | SQL association table | product_tags | Có schema riêng nếu khai báo |
| @CollectionTable(name) | SQL collection table | product_aliases | ElementCollection |
| @SecondaryTable(name) | SQL secondary table | order_details | Một entity nhiều bảng |
| @Column(table) | SQL secondary table selector | order_details | Không phải column name |
| @AttributeOverride(name) | Java property path | amount | @Column bên trong chọn SQL column |
| @AssociationOverride(name) | Java association path | contact | JoinColumn bên trong là SQL |
| @OneToMany(mappedBy) | Java owner-side field | customer | Không phải SQL FK column |
| @SequenceGenerator(name) | JPA generator name | order_seq_gen | Dùng bởi @GeneratedValue(generator=...) |
| @SequenceGenerator(sequenceName) | SQL sequence | purchase_order_seq | Cần đúng namespace |
| @UniqueConstraint(columnNames) | SQL column names | external_ref | DDL metadata |
| @Index(columnList) | SQL column identifiers | customer_id,order_status | Không dùng Java fields |
| JPQL FROM/WHERE | JPA entity/property | PurchaseOrder/status | Provider chuyển sang SQL |
| Criteria root.get | Java persistent attribute | status | Không dùng physical column name |
| Native SQL | SQL identifiers | sales.purchase_orders | Không được mapping rewrite tùy ý |
| Default schema | JDBC/provider/DB session | sales | Không đồng nhất mọi DB |
| Hibernate naming strategies | Provider-specific naming | camelCase → snake_case | Phải test effective SQL |
| search_path | PostgreSQL namespace resolution | sales,public | Có rủi ro pool/tenant leak |
| Quoted identifier | DB physical exact name | "SalesOrders" | Case/keyword semantics |

## 24. Checklist triển khai mapping tên bảng, cột, catalog và schema

### 24.1. Xác nhận metadata Java/JPA

1. **Entity class Java và @Entity(name) đã được phân biệt chưa?** JPQL dùng tên nào?
2. **@Table(name) có khớp physical table thực tế không?**
3. **@Table(schema) có cần khai báo tường minh không?**
4. **@Table(catalog) có phù hợp DBMS đang dùng không?**
5. **@Column(name) có khớp column đã migration không?**
6. **Có hiểu default names không phải luôn snake_case không?**
7. **Implicit và physical naming strategies của provider đã được xác định chưa?**
8. **Nếu upgrade Hibernate/Spring Boot, naming strategy có bị đổi không?**
9. **Có quoted identifiers và case-sensitive names nào không?**
10. **Có table/column names trùng reserved keywords không?**
11. **Những tên quá dài có vượt identifier limit không?**
12. **Có hai entities vô tình mapping cùng physical table không?**
13. **Có multi-persistence-unit metadata với defaults khác nhau không?**

### 24.2. Quan hệ và bảng phụ

14. **@JoinColumn.name có đúng FK column phía owning table không?**
15. **referencedColumnName có đúng column phía referenced table không?**
16. **@ManyToOne(optional=false) và FK NOT NULL có phản ánh domain không?**
17. **mappedBy có dùng Java property name, không dùng SQL column không?**
18. **Composite @JoinColumns có đủ các thành phần PK/FK không?**
19. **@JoinTable có chỉ đúng name/schema/catalog cho association table không?**
20. **joinColumns và inverseJoinColumns có đúng hướng không?**
21. **@CollectionTable có trỏ đúng bảng chứa element collection không?**
22. **@Column trên ElementCollection có đặt đúng value column không?**
23. **@SecondaryTable có đúng tên và PK join không?**
24. **@Column(table=...) có gắn đúng secondary table không?**
25. **@AttributeOverride.name là Java embeddable path đúng không?**
26. **@AssociationOverride có đúng association property và FK columns không?**
27. **Inheritance JOINED/PK join columns có phù hợp schema không?**

### 24.3. ID generators, DDL và database namespace

28. **Sequence/table generator có đúng SQL object name không?**
29. **Sequence schema/catalog có tương thích entity table và dialect không?**
30. **GeneratedValue.generator có khớp @SequenceGenerator.name không?**
31. **allocationSize/sequence increment được cấu hình tương thích chưa?**
32. **Role có quyền dùng sequence/generator table không?**
33. **@Index.columnList dùng physical column names không?**
34. **@UniqueConstraint.columnNames có đúng columns không?**
35. **Foreign key/unique/index constraint names có tránh collision không?**
36. **Schema/table đã được tạo bằng migrations, không chỉ annotations chưa?**
37. **Có so đúng DDL thực tế của test/staging/production không?**
38. **Có migration history và rollback plan khi rename không?**
39. **Có data backfill/compatibility strategy cho rolling deploy không?**
40. **Có views, procedures, triggers, reports, ETL và native SQL dùng tên cũ không?**

### 24.4. Catalog/schema và bảo mật

41. **Đang kết nối đúng database/catalog/server/role không?**
42. **Default schema/search_path có được xác định rõ không?**
43. **Có table cùng tên trong nhiều schemas không?**
44. **Có kiểm tra app role được quyền trên đúng schema/table không?**
45. **Có tránh cấp quyền rộng để che mapping sai không?**
46. **Nếu multi-tenant, schema được suy ra từ authenticated tenant không?**
47. **Schema name có đi qua allowlist, không nối raw user input không?**
48. **Connection pool có reset search_path/session state không?**
49. **Mỗi tenant có migrations/schema versions được theo dõi không?**
50. **Các ID generators/shared tables có scope đúng tenant không?**
51. **Logging có tránh tiết lộ sensitive schema/table/parameter details không?**
52. **Có test tenant A → B → A trên reused connections không?**

### 24.5. Runtime và kiểm thử

53. **Đã bật generated SQL logging hợp lý trong test chưa?**
54. **Đã test JPQL entity/property names độc lập physical names chưa?**
55. **Đã test native SQL với actual SQL table/column names chưa?**
56. **Đã test relationships, JOIN FETCH và associated join tables chưa?**
57. **Đã test secondary tables và element collections có dữ liệu chưa?**
58. **Đã test persist/flush với ID generator chưa?**
59. **Đã test table cùng tên ở hai schemas để phát hiện schema sai chưa?**
60. **Đã test mixed-case/quoted legacy table trên đúng DB dialect chưa?**
61. **Đã test permission bằng đúng production-like DB user chưa?**
62. **Đã xác minh schema validate không bỏ sót query SQL đặc thù chưa?**
63. **Đã kiểm tra identifier length/collisions trong indexes và constraints chưa?**
64. **Có versioned migration tests trên database giống production không?**
65. **Có tránh lấy H2 naming behavior làm bằng chứng cho PostgreSQL/Oracle không?**
66. **Có kiểm thử sau nâng cấp provider/driver/database không?**
67. **Có phân biệt lỗi mapping với lỗi DB privilege/connection không?**
68. **Có kiểm tra thực tế SQL object mà ứng dụng đọc/ghi khi deploy không?**

### 24.6. Cây quyết định cho một lỗi liên quan tên

~~~text
JPA query/persist phát sinh lỗi liên quan SQL object
                         |
                         v
               Lỗi ở JPQL parsing?
                  /            \
                Có             Không
                |                |
      Kiểm tra @Entity(name)     v
      và Java property paths   SQL đã được sinh chưa?
                                /             \
                              Chưa             Rồi
                               |                |
                     Mapping bootstrap        v
                     (mappedBy/override)   SQL tên gì?
                                              |
                         +--------------------+----------------+
                         |                    |                |
                     Table lỗi           Column lỗi       Sequence lỗi
                         |                    |                |
                  @Table name           @Column/Join      @SequenceGenerator
                  schema/catalog        naming strategy   privileges/schema
                         |                    |                |
                         +--------------------+----------------+
                                              |
                                              v
                         Object có thật trong đúng DB/schema?
                                 /               \
                               Không              Có
                                |                  |
                           Migration/DDL        Quyền/case/
                           hoặc connection      quoting/search_path
                                |                  |
                                +--------+---------+
                                         |
                                         v
                          Test JPA + native SQL + DB metadata
                                         |
                                         v
                              Multi-tenant routing đúng?
                                         |
                                         v
                            Rollout + migration + monitoring
~~~

## 25. Tổng kết

Trong JPA, **tên bảng, cột, catalog và schema** là phần nối giữa mô hình đối tượng Java và lược đồ quan hệ, không chỉ là chi tiết trang trí của annotation.

Ba nhóm tên phải được tách bạch:

1. **Java/JPA names:** tên entity trong @Entity, tên thuộc tính Java, mappedBy và property paths trong JPQL/Criteria.
2. **Database physical names:** @Table.name, @Column.name, @JoinColumn.name, @JoinTable.name, @SecondaryTable, sequences, constraint/index names.
3. **Database namespaces:** catalog và schema, cũng như default namespace của connection/session, phụ thuộc DBMS/dialect.

Ví dụ:

~~~java
@Entity(name = "PurchaseOrder")
@Table(name = "purchase_orders", schema = "sales")
public class PurchaseOrder {

    @Id
    @Column(name = "order_id")
    private Long id;

    @Column(name = "order_status")
    private String status;
}
~~~

JPQL:

~~~sql
select o
from PurchaseOrder o
where o.status = :status
~~~

SQL minh họa trên PostgreSQL:

~~~sql
SELECT order_id, order_status
FROM sales.purchase_orders
WHERE order_status = 'PAID';
~~~

**Những khác biệt cần nhớ:**

- **@Entity(name)** đổi tên entity trong JPQL, **không tự đổi table vật lý**.
- **@Table(name/schema/catalog)** xác định đối tượng SQL ở namespace phù hợp, nhưng các thành phần catalog/schema **không portable y hệt** giữa PostgreSQL, SQL Server, MySQL và Oracle.
- **@Column(name)** đặt physical column cho property Java; JPQL vẫn dùng **property name**, còn native SQL phải dùng **SQL identifier thực tế**.
- **@JoinColumn, @JoinTable, @CollectionTable, @SecondaryTable và generators** cũng có names/schema riêng; chỉ mapping @Table chính là chưa đủ.
- **Implicit/physical naming strategies, identifier quoting, case folding, default schema/search_path** có thể thay kết quả SQL thực tế. Cần kiểm tra generated SQL, migration và database metadata.
- **Đổi annotation không tự rename database production**. Migration cần đồng bộ với old/new applications, SQL scripts, views, constraints và quyền truy cập.
- **Trong multi-tenancy**, sai schema hoặc search_path/session cleanup có thể thành **lỗi rò dữ liệu giữa tenants**, không chỉ lỗi SQL syntax.
- **Kiểm thử bằng database thật** với hai schemas có cùng table names giúp xác nhận ứng dụng thực sự đọc đúng SQL object.

~~~text
Java PurchaseOrder.status
          |
          v
JPA metadata
  @Entity(name="PurchaseOrder")
  @Table(schema="sales", name="purchase_orders")
  @Column(name="order_status")
          |
          v
Provider naming + SQL dialect
          |
          v
SQL: sales.purchase_orders.order_status
          |
          v
JDBC connection namespace + DB role
          |
          v
Actual database row
~~~

**Nguyên tắc thực hành:** Trước khi quy một lỗi truy vấn cho JPA, hãy xác định **tên Java, tên SQL vật lý, schema/catalog thực tế, naming strategy và database connection hiện hành**. Khi năm yếu tố này nhất quán với migrations và quyền truy cập, metadata mới thực sự giúp ứng dụng JPA truy vấn chính xác và vận hành ổn định.













