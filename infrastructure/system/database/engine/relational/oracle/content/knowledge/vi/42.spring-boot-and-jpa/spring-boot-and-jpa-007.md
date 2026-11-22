# Ánh xạ entity, schema, tên đối tượng và định danh có dấu ngoặc kép trong Spring Boot và JPA

Khi một ứng dụng Spring Boot dùng Spring Data JPA để truy cập Oracle Database, tên class Java không nhất thiết trùng tên bảng, tên field không nhất thiết trùng tên cột, và tên schema cũng không tự động là username đang đăng nhập. Hibernate phải chuyển metadata của entity thành tên bảng, cột, sequence, join table và các đối tượng SQL mà Oracle thực sự hiểu.

Khác biệt này trở nên quan trọng khi ứng dụng kết nối tới schema có sẵn, đặc biệt là database legacy có:
- Tên bảng/cột viết hoa theo quy ước Oracle.
- Tên object có chữ thường hoặc chữ hoa hỗn hợp được tạo bằng dấu ngoặc kép.
- Tên trùng từ khóa SQL như ORDER, USER hoặc LEVEL.
- Schema owner khác database user mà ứng dụng dùng để đăng nhập.
- Naming convention cũ không giống naming strategy mặc định của Hibernate.
- Sequence, synonym, view, trigger và foreign key được quản lý bằng script riêng.

Một mapping sai có thể dẫn đến ORA-00942, ORA-00904, ORA-02289 hoặc SQL chạy được nhưng truy cập nhầm schema. Cách xử lý bền vững là hiểu rõ tên object trong Oracle, khai báo mapping JPA tường minh ở nơi cần thiết, kiểm soát Hibernate naming strategy và xác minh SQL mà Hibernate sinh ra.

Bài học lấy Spring Boot, Jakarta Persistence/JPA và Oracle Database 19c làm trọng tâm. Một số ví dụ cũng áp dụng cho ứng dụng Spring Boot 2 dùng javax.persistence; ứng dụng Spring Boot 3 trở lên thường dùng jakarta.persistence. Các annotation giống nhau về ý nghĩa, nhưng package import và phiên bản Hibernate khác nhau.

## 1. Các lớp tên trong JPA và Oracle

### 1.1. Entity name không phải table name

Một entity có thể được khai báo:

~~~java
@Entity(name = "Customer")
@Table(name = "CUSTOMER", schema = "APP")
public class CustomerEntity {
    // fields
}
~~~

Ở đây có hai tên khác nhau:
- Entity name Customer được dùng trong JPQL/HQL.
- Table name APP.CUSTOMER được dùng trong SQL gửi tới Oracle.

Ví dụ JPQL dùng entity name:

~~~java
SELECT c
FROM Customer c
WHERE c.id = :id
~~~

Hibernate chuyển JPQL thành SQL tham chiếu bảng APP.CUSTOMER. Không dùng @Entity(name = ...) để đổi tên bảng vật lý.

Nếu bỏ name trong @Entity, entity name mặc định thường là tên class đơn giản. Tên này vẫn độc lập với @Table.

### 1.2. Field/property name không phải column name

Ví dụ:

~~~java
@Entity
@Table(name = "CUSTOMER", schema = "APP")
public class CustomerEntity {

    @Id
    @Column(name = "CUSTOMER_ID")
    private Long id;

    @Column(name = "DISPLAY_NAME")
    private String displayName;
}
~~~

Java field displayName được ánh xạ tới cột DISPLAY_NAME. Nếu không khai báo @Column(name=...), Hibernate có thể tạo tên logic từ field và chuyển tiếp qua naming strategy.

Đối với schema hiện hữu, khai báo column name tường minh giúp tránh phụ thuộc vào quy tắc tự đổi camelCase thành snake_case.

### 1.3. Schema owner, database user và current schema

Trong Oracle:
- **Database user** là tài khoản xác thực khi mở session.
- **Schema** là tập object thuộc sở hữu của một database user.
- **Current schema** là schema được Oracle dùng để phân giải tên object không được qualify trong session.
- Một user có thể truy cập object của schema khác nếu có privilege phù hợp.

Ví dụ ứng dụng đăng nhập bằng APP_RUNTIME nhưng bảng thuộc APP_DATA. Mapping có thể trỏ tới APP_DATA.CUSTOMER:

~~~java
@Table(name = "CUSTOMER", schema = "APP_DATA")
~~~

APP_RUNTIME vẫn cần quyền SELECT/INSERT/UPDATE/DELETE phù hợp trên object đó. Ghi schema vào annotation không cấp quyền truy cập.

### 1.4. Tên object mà Oracle thực sự lưu

Oracle xử lý identifier không đặt trong dấu ngoặc kép theo quy tắc chuẩn hóa chữ hoa:

~~~sql
CREATE TABLE customer (
    customer_id NUMBER PRIMARY KEY
);
~~~

Trong dictionary, tên thường được lưu là CUSTOMER và CUSTOMER_ID.

Tên được tạo bằng dấu ngoặc kép giữ nguyên kiểu chữ:

~~~sql
CREATE TABLE "Customer" (
    "CustomerId" NUMBER PRIMARY KEY
);
~~~

Object này có tên chính xác là Customer và CustomerId. Khi truy cập, phải dùng đúng cách viết có dấu ngoặc kép:

~~~sql
SELECT "CustomerId"
FROM "Customer";
~~~

Câu lệnh không đặt ngoặc kép CUSTOMER sẽ tìm object CUSTOMER, không tự động tìm object "Customer".

## 2. Quy tắc identifier của Oracle

### 2.1. Identifier không đặt trong dấu ngoặc kép

Unquoted identifier:
- Không phân biệt chữ hoa/chữ thường khi phân giải tên.
- Oracle chuẩn hóa tên thành chữ hoa.
- Không được chứa một số ký tự đặc biệt tùy ý.
- Không được là reserved word trong ngữ cảnh cấm.
- Có giới hạn độ dài theo database compatibility.

Vì vậy CUSTOMER, Customer và customer khi không quote được hiểu như cùng identifier CUSTOMER.

Đây là lý do phần lớn schema Oracle dùng tên object viết hoa trong data dictionary dù script DDL có thể viết chữ thường.

### 2.2. Quoted identifier

Quoted identifier dùng dấu ngoặc kép hai bên tên:

~~~sql
CREATE TABLE "SalesOrder" (
    "OrderId" NUMBER,
    "CreatedAt" TIMESTAMP
);
~~~

Oracle giữ chính xác chữ hoa/thường và yêu cầu tham chiếu đúng tên:

~~~sql
SELECT "OrderId", "CreatedAt"
FROM "SalesOrder";
~~~

Các dạng sau không tương đương với tên quoted hỗn hợp:

~~~sql
SELECT ORDERID FROM SALESORDER;
SELECT "ORDERID" FROM "SALESORDER";
~~~

Cả hai đều tham chiếu identifier khác với "SalesOrder"."OrderId".

Quoted identifier có thể cần cho database legacy hoặc tên đặc biệt, nhưng làm SQL khó đọc và tăng rủi ro mapping. Với schema mới, ưu tiên identifier không quote, chữ hoa theo quy ước Oracle và tránh reserved words.

### 2.3. Reserved words và tên dễ gây xung đột

Không nên đặt tên object hoặc column trùng từ khóa SQL như ORDER, GROUP, USER, LEVEL, DATE hoặc các từ khóa khác. Một số từ có thể là keyword/reserved word tùy phiên bản và ngữ cảnh.

Nếu schema legacy đã có tên như "Order", JPA phải quote đúng identifier. Đừng đổi tên trong annotation thành ORDER rồi hy vọng Oracle tự hiểu.

Tốt hơn, nếu có thể thay đổi schema, dùng tên rõ nghĩa như SALES_ORDER hoặc ORDER_HEADER. Với schema không thể đổi, mapping phải thể hiện chính xác tên hiện hữu.

### 2.4. Giới hạn độ dài identifier

Oracle 19c hỗ trợ identifier dài tối đa 128 bytes khi database COMPATIBLE được đặt ở mức 12.2 trở lên. Với compatibility thấp hơn, giới hạn cũ 30 bytes có thể vẫn áp dụng.

Kiểm tra:

~~~sql
SHOW PARAMETER compatible;
~~~

Giới hạn tính theo byte, không nhất thiết là số ký tự đối với database character set đa byte. Tên dài có thể bị từ chối hoặc tạo vấn đề tương thích khi migration sang database có COMPATIBLE thấp hơn.

Tên được Hibernate sinh tự động cho constraint, index hoặc sequence cũng cần nằm trong giới hạn của database đích.

### 2.5. Tên trong dictionary

Với object thông thường:

~~~sql
SELECT owner,
       table_name
FROM   all_tables
WHERE  owner IN ('APP', 'APP_DATA')
ORDER  BY owner, table_name;
~~~

Với cột:

~~~sql
SELECT owner,
       table_name,
       column_name,
       data_type,
       nullable
FROM   all_tab_columns
WHERE  owner = 'APP_DATA'
AND    table_name = 'CUSTOMER'
ORDER  BY column_id;
~~~

Tên unquoted thường xuất hiện uppercase. Tên quoted hỗn hợp được lưu đúng case. Dùng giá trị dictionary để xác định chính xác identifier thay vì suy đoán từ Java class.

## 3. Mapping entity với @Table và @Column

### 3.1. Mapping rõ schema và table

~~~java
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.Column;

@Entity
@Table(name = "CUSTOMER", schema = "APP_DATA")
public class CustomerEntity {

    @Id
    @Column(name = "CUSTOMER_ID")
    private Long id;

    @Column(name = "DISPLAY_NAME", nullable = false, length = 120)
    private String displayName;
}
~~~

@table:
- name: tên bảng hoặc view mà entity ánh xạ.
- schema: schema owner.
- catalog: catalog nếu database/provider hỗ trợ; với Oracle thông thường schema là thuộc tính cần dùng.

@Column:
- name: tên cột.
- nullable: metadata về nullability.
- length: độ dài khai báo cho loại chuỗi.
- precision/scale: metadata cho numeric.
- insertable/updatable: kiểm soát cột tham gia INSERT/UPDATE.
- unique: metadata uniqueness, thường hữu ích cho schema generation.

Các thuộc tính metadata không tự sửa schema khi ddl-auto=validate hoặc none. Chúng ảnh hưởng mapping và có thể được dùng khi provider tạo DDL.

### 3.2. Entity ánh xạ view

Entity có thể ánh xạ view nếu có khóa định danh ổn định mà JPA dùng để nhận diện hàng:

~~~java
@Entity
@Table(name = "CUSTOMER_SUMMARY_V", schema = "APP_REPORT")
public class CustomerSummary {
    @Id
    @Column(name = "CUSTOMER_ID")
    private Long customerId;

    @Column(name = "ORDER_COUNT")
    private Long orderCount;
}
~~~

JPA cần @Id để xác định identity của entity, kể cả khi object vật lý là view. Không chọn một cột không duy nhất làm @Id vì persistence context có thể gộp nhầm nhiều hàng thành một entity.

Nếu view không có khóa duy nhất, cân nhắc DTO/projection và native query thay vì ánh xạ thành entity quản lý.

### 3.3. Mapping field có tên khác

~~~java
@Column(name = "CUST_NM")
private String customerName;
~~~

Không yêu cầu tên Java phải giống tên cột. Giữ Java naming rõ nghĩa, còn tên DB phản ánh schema hiện hữu.

### 3.4. Insertable và updatable

Một cột do trigger hoặc database expression quản lý có thể được ánh xạ chỉ đọc:

~~~java
@Column(name = "CREATED_AT", insertable = false, updatable = false)
private LocalDateTime createdAt;
~~~

Điều này ngăn Hibernate đưa cột vào INSERT/UPDATE. Nó không tự bảo đảm giá trị được sinh; cần trigger, default expression hoặc cơ chế database tương ứng. Cách lấy lại giá trị sau INSERT tùy Hibernate/dialect và mapping.

Không đặt insertable=false cho cột bắt buộc nếu database không có default/trigger, nếu không INSERT có thể lỗi constraint.

### 3.5. Một field ánh xạ cột đã được quản lý nơi khác

Trong một số mapping, cùng một cột có thể xuất hiện trong nhiều quan hệ. Chỉ một mapping nên ghi cột; mapping còn lại có thể dùng insertable=false, updatable=false.

Ví dụ foreign key được expose vừa như association vừa như scalar:

~~~java
@ManyToOne(fetch = FetchType.LAZY)
@JoinColumn(name = "CUSTOMER_ID")
private CustomerEntity customer;

@Column(name = "CUSTOMER_ID", insertable = false, updatable = false)
private Long customerId;
~~~

Cần hiểu ownership của association để tránh hai property cùng ghi một cột và gây mapping exception hoặc update khó dự đoán.

## 4. Hibernate naming strategy trong Spring Boot

### 4.1. Vì sao naming strategy quan trọng?

Hibernate không chỉ lấy nguyên tên Java field rồi gửi SQL. Quá trình mapping có thể đi qua:
1. Entity/property name.
2. Implicit naming strategy nếu không khai báo tên rõ ràng.
3. Logical identifier.
4. Physical naming strategy.
5. SQL dialect và quy tắc quote.
6. SQL cuối cùng gửi tới Oracle.

Ví dụ field customerAddress có thể được chuyển thành CUSTOMER_ADDRESS hoặc customer_address tùy naming strategy và cách quote.

### 4.2. Implicit naming strategy

Implicit naming strategy quyết định tên logic khi annotation không chỉ định tên object.

Ví dụ:

~~~java
@Entity
public class CustomerProfile {
    @Id
    private Long id;

    private String displayName;
}
~~~

Nếu không có @Table và @Column, Hibernate cần suy ra table/column name từ entity và property. Kết quả phụ thuộc implicit strategy, physical strategy và phiên bản Hibernate.

### 4.3. Physical naming strategy

Physical naming strategy chuyển tên logic thành tên vật lý cuối cùng. Một strategy có thể:
- Chuyển camelCase thành snake_case.
- Chuyển tên sang lowercase/uppercase.
- Áp quy tắc prefix/suffix.
- Giữ nguyên tên.

Quan trọng: explicit name trong @Table/@Column cũng có thể đi qua physical naming strategy. Vì vậy, ghi @Column(name="CUSTOMER_ID") chưa đủ nếu strategy tùy chỉnh tiếp tục đổi tên.

### 4.4. Default naming của Spring Boot thay đổi theo phiên bản

Spring Boot đã thay đổi implementation và tên class naming strategy qua các thế hệ Hibernate. Không nên copy class name của một dự án Boot 2 sang Boot 3/4 mà không kiểm tra dependency thực tế.

Khi mapping schema legacy:
- Xác định Spring Boot version.
- Xác định Hibernate ORM version.
- Xem cấu hình spring.jpa.hibernate.naming.*.
- Kiểm tra SQL được sinh.
- Nếu muốn giữ nguyên logical name, cấu hình PhysicalNamingStrategyStandardImpl phù hợp với Hibernate version hiện tại.

Ví dụ property:

~~~properties
spring.jpa.hibernate.naming.physical-strategy=org.hibernate.boot.model.naming.PhysicalNamingStrategyStandardImpl
~~~

PhysicalNamingStrategyStandardImpl giữ physical name theo logical identifier mà Hibernate đưa vào. Nó không tự sửa implicit naming đã được tạo trước đó; nếu cần tên chính xác, khai báo @Table/@Column tường minh.

### 4.5. Cấu hình implicit strategy khi cần

Ví dụ dùng strategy tuân thủ quy tắc JPA:

~~~properties
spring.jpa.hibernate.naming.implicit-strategy=org.hibernate.boot.model.naming.ImplicitNamingStrategyJpaCompliantImpl
~~~

Đây là một lựa chọn cấu hình, không phải yêu cầu mọi ứng dụng phải đặt. Trước khi đổi, kiểm tra class có trong Hibernate version đang chạy và so sánh tên SQL trước/sau.

### 4.6. Naming strategy không đổi tên object trong Oracle

Naming strategy chỉ thay cách Hibernate phát sinh identifier. Nó không:
- Rename table thật.
- Rename column thật.
- Tạo synonym.
- Cấp quyền.
- Đổi schema owner.
- Sửa sequence đã tồn tại.

Nếu strategy đổi CUSTOMER_ID thành customer_id trong SQL không quote, Oracle vẫn phân giải thành CUSTOMER_ID. Nhưng nếu tên bị quote thành "customer_id", đó là identifier khác. Đây là một nguyên nhân quan trọng khiến ứng dụng có thể lỗi sau khi bật global quoting.

## 5. Ánh xạ schema trong Spring Boot

### 5.1. Khai báo schema ở từng entity

~~~java
@Entity
@Table(name = "CUSTOMER", schema = "APP_DATA")
public class CustomerEntity {
    // ...
}
~~~

Ưu điểm:
- Rõ schema owner của từng entity.
- Có thể ánh xạ nhiều schema trong cùng persistence unit nếu quyền phù hợp.
- Ít phụ thuộc session current schema.
- Dễ đọc khi xem mapping.

Nhược điểm:
- Lặp lại schema trên nhiều entity.
- Đổi schema cần sửa nhiều mapping nếu ứng dụng chuyển môi trường.

### 5.2. Dùng default schema của Hibernate

Có thể cấu hình schema mặc định:

~~~properties
spring.jpa.properties.hibernate.default_schema=APP_DATA
~~~

Hibernate có thể qualify các object không khai báo schema bằng default schema này.

Đây là cấu hình Hibernate, không phải lệnh đổi current schema của Oracle session. Nó cũng không cấp privilege cho database user.

Nếu một entity khai báo @Table(schema="OTHER_SCHEMA"), mapping tường minh có thể ghi đè default schema theo metadata/provider.

### 5.3. Khi nào không nên đặt default schema?

Không nên đặt một default schema chung nếu:
- Entity thuộc nhiều schema khác nhau.
- Ứng dụng dựa vào synonym theo current schema.
- Có native SQL được thiết kế để phân giải theo session.
- Mỗi tenant có schema riêng và schema được chọn theo connection/session.
- Một số object thuộc schema owner khác.

Trong trường hợp nhiều schema, khai báo schema tường minh hoặc thiết kế multi-tenancy phù hợp.

### 5.4. Cấu hình đầy đủ minh họa

~~~properties
spring.datasource.url=jdbc:oracle:thin:@//dbhost.example.com:1521/appsvc.example.com
spring.datasource.username=APP_RUNTIME
spring.datasource.password=ENV_DB_PASSWORD

spring.jpa.database-platform=org.hibernate.dialect.OracleDialect
spring.jpa.properties.hibernate.default_schema=APP_DATA
spring.jpa.hibernate.ddl-auto=validate

spring.jpa.show-sql=false
logging.level.org.hibernate.SQL=DEBUG
~~~

Tên dialect/class cụ thể phụ thuộc Hibernate version; Hibernate hiện đại thường tự chọn dialect từ JDBC metadata nếu không cần override. Tránh khai báo class dialect cũ không tương thích Hibernate 6.

Không bật log bind parameter ở production một cách tùy tiện vì giá trị bind có thể chứa dữ liệu cá nhân hoặc bí mật. Nếu cần debug, dùng môi trường kiểm thử và giới hạn thời gian.

### 5.5. Datasource username và default schema là hai việc khác nhau

Ví dụ:
- Datasource username: APP_RUNTIME.
- Hibernate default schema: APP_DATA.
- Bảng vật lý: APP_DATA.CUSTOMER.

APP_RUNTIME phải có quyền phù hợp trên APP_DATA.CUSTOMER. Đặt default schema không khiến Oracle coi APP_RUNTIME là owner của APP_DATA.

## 6. CURRENT_SCHEMA và synonym trong Oracle

### 6.1. ALTER SESSION SET CURRENT_SCHEMA

Oracle cho phép thay schema mặc định dùng để phân giải tên không qualify:

~~~sql
ALTER SESSION SET CURRENT_SCHEMA = APP_DATA;
~~~

Sau lệnh này, câu SQL không ghi schema:

~~~sql
SELECT * FROM CUSTOMER;
~~~

có thể được phân giải tới APP_DATA.CUSTOMER theo quy tắc name resolution.

CURRENT_SCHEMA không đổi SESSION_USER và không cấp thêm privilege. Session vẫn xác thực bằng user ban đầu; quyền truy cập vẫn phải tồn tại.

### 6.2. Kiểm tra session context

~~~sql
SELECT
    sys_context('USERENV', 'SESSION_USER') AS session_user,
    sys_context('USERENV', 'CURRENT_SCHEMA') AS current_schema,
    sys_context('USERENV', 'SERVICE_NAME') AS service_name,
    sys_context('USERENV', 'CON_NAME') AS con_name
FROM dual;
~~~

Dùng truy vấn này để kiểm tra ứng dụng đã vào đúng service/PDB và current schema có đúng kỳ vọng hay không.

### 6.3. CURRENT_SCHEMA với connection pool

Connection pool tái sử dụng physical connection. Nếu một request chạy ALTER SESSION SET CURRENT_SCHEMA, session state có thể tồn tại khi connection được trả về pool, tùy pool/reset policy.

Rủi ro:
- Request tenant A trả connection về pool.
- Request tenant B mượn cùng connection.
- CURRENT_SCHEMA vẫn là tenant A.
- SQL không qualify schema có thể truy cập sai dữ liệu.

Nếu phải thay current schema theo request:
- Thiết lập schema trước mỗi lần mượn connection.
- Reset về trạng thái chuẩn trước khi trả connection.
- Dùng connection initialization/reset hook của pool.
- Test với nhiều request và concurrency.
- Không tin rằng pool tự reset mọi session state.

Đối với hệ thống multi-tenant, ưu tiên cơ chế Hibernate multi-tenancy hoặc giải pháp routing có quản lý rõ ràng thay vì chạy ALTER SESSION tùy tiện trong business code.

### 6.4. Synonym

Synonym là tên thay thế trỏ tới object khác:

~~~sql
CREATE SYNONYM CUSTOMER FOR APP_DATA.CUSTOMER;
~~~

Private synonym thuộc schema tạo nó; public synonym có phạm vi toàn database theo quy tắc Oracle. Synonym không phải bản sao dữ liệu và không tự cấp quyền trên object đích.

Nếu Hibernate phát sinh SQL không qualify schema, Oracle có thể resolve synonym theo quy tắc name resolution. Nếu Hibernate thêm APP_DATA.CUSTOMER, synonym CUSTOMER không được dùng để thay thế tên đã qualify.

### 6.5. Mapping qua synonym

Nếu ứng dụng được thiết kế để truy cập synonym:

~~~java
@Entity
@Table(name = "CUSTOMER")
public class CustomerEntity {
    // ...
}
~~~

Cần tránh đặt hibernate.default_schema=APP_DATA nếu điều đó khiến Hibernate qualify bảng và bỏ qua synonym mong muốn. Kiểm tra SQL thực tế và quyền trên object đích.

Không ánh xạ synonym như thể nó có metadata độc lập; JPA mapping vẫn cần column và key thực tế của object đích.

## 7. Quoted identifiers trong JPA

### 7.1. Ánh xạ table có chữ hoa/thường hỗn hợp

Giả sử Oracle đã có:

~~~sql
CREATE TABLE "SalesOrder" (
    "OrderId" NUMBER PRIMARY KEY,
    "OrderStatus" VARCHAR2(20)
);
~~~

JPA mapping:

~~~java
@Entity
@Table(name = "\"SalesOrder\"", schema = "APP_DATA")
public class SalesOrderEntity {

    @Id
    @Column(name = "\"OrderId\"")
    private Long orderId;

    @Column(name = "\"OrderStatus\"")
    private String orderStatus;
}
~~~

Trong Java string, dấu ngoặc kép của identifier được escape bằng backslash. Hibernate cần nhận đúng tên quoted để sinh SQL tham chiếu "SalesOrder"."OrderId".

Nếu chỉ viết @Table(name="SalesOrder"), tên có thể được xử lý như unquoted identifier và Oracle sẽ tìm SALESORDER, không phải quoted mixed-case SalesOrder.

### 7.2. Ánh xạ tên trùng reserved word

Ví dụ bảng "Order" có cột "Date":

~~~java
@Entity
@Table(name = "\"Order\"", schema = "APP_DATA")
public class PurchaseOrderEntity {

    @Id
    @Column(name = "\"OrderId\"")
    private Long id;

    @Column(name = "\"Date\"")
    private LocalDate orderDate;
}
~~~

Không dùng tên entity Java Order nếu điều đó gây nhầm lẫn với JPQL hoặc từ khóa trong query. Entity name có thể là PurchaseOrder trong khi table vật lý là "Order".

### 7.3. Quoting một column riêng lẻ

Không cần quote toàn bộ schema nếu chỉ một object dùng tên hỗn hợp:

~~~java
@Column(name = "\"DisplayName\"")
private String displayName;
~~~

Các cột unquoted khác có thể giữ mapping uppercase thông thường.

### 7.4. Global quoted identifiers

Hibernate hỗ trợ cấu hình quote tất cả identifier:

~~~properties
spring.jpa.properties.hibernate.globally_quoted_identifiers=true
~~~

Cấu hình này khiến table/column/sequence và nhiều identifier được quote theo quy tắc Hibernate. Nó có thể hữu ích với schema có tên đặc biệt, nhưng cũng có thể tạo SQL khác với schema legacy.

Ví dụ tên logic CUSTOMER_ADDRESS nếu được quote thành "customerAddress" hoặc "customer_address" tùy naming strategy, Oracle sẽ xem đây là identifier phân biệt case và khác với CUSTOMER_ADDRESS unquoted.

Không bật global quoting để chữa một lỗi reserved word đơn lẻ. Thường nên quote đúng object cần thiết hoặc dùng tên vật lý không reserved.

### 7.5. Skip column definitions

Hibernate có một số property liên quan đến global quoting và DDL column definition. Chỉ cấu hình chúng khi hiểu rõ tác động tới columnDefinition hoặc native SQL fragment. Không copy toàn bộ thuộc tính quote từ một dự án khác mà không xem generated DDL.

### 7.6. Backtick và dấu ngoặc kép

Hibernate có hỗ trợ cú pháp backtick trong một số annotation/version như một cách yêu cầu quote identifier, nhưng đó là quy ước riêng của Hibernate. Với mapping JPA portable cho Oracle, dùng double quote được escape trong annotation string và kiểm tra SQL sinh ra.

## 8. Mapping quan hệ và các object phụ trợ

### 8.1. Many-to-one với JoinColumn

~~~java
@ManyToOne(fetch = FetchType.LAZY)
@JoinColumn(
    name = "CUSTOMER_ID",
    referencedColumnName = "CUSTOMER_ID",
    nullable = false
)
private CustomerEntity customer;
~~~

name là tên foreign key column trong bảng hiện tại. referencedColumnName là tên cột ở bảng đích; nếu bỏ, JPA thường dùng primary key column của entity đích.

Nếu bảng hiện tại thuộc schema khác, schema của bảng được xác định bởi @Table trên entity chứa association. Entity đích có schema riêng.

### 8.2. One-to-many

~~~java
@OneToMany(mappedBy = "customer")
private List<SalesOrderEntity> orders = new ArrayList<>();
~~~

mappedBy phải trỏ tới property association ở entity con. Nó không phải tên cột CUSTOMER_ID. Cột foreign key được cấu hình ở @JoinColumn phía ManyToOne.

### 8.3. Many-to-many với JoinTable

~~~java
@ManyToMany
@JoinTable(
    name = "USER_ROLE",
    schema = "APP_DATA",
    joinColumns = @JoinColumn(name = "USER_ID"),
    inverseJoinColumns = @JoinColumn(name = "ROLE_ID")
)
private Set<RoleEntity> roles = new HashSet<>();
~~~

JoinTable có schema riêng. Không mặc định nó nằm trong schema của entity phía kia; hãy khai báo rõ nếu object đã tồn tại.

### 8.4. ElementCollection và CollectionTable

~~~java
@ElementCollection
@CollectionTable(
    name = "CUSTOMER_TAG",
    schema = "APP_DATA",
    joinColumns = @JoinColumn(name = "CUSTOMER_ID")
)
@Column(name = "TAG_VALUE")
private Set<String> tags = new HashSet<>();
~~~

CollectionTable ánh xạ bảng chứa collection của value type. Tên bảng, schema và join column đều phải khớp database.

### 8.5. Embedded object và AttributeOverride

~~~java
@Embeddable
public class Address {
    private String city;
    private String postalCode;
}

@Entity
@Table(name = "CUSTOMER", schema = "APP_DATA")
public class CustomerEntity {
    @Embedded
    @AttributeOverrides({
        @AttributeOverride(
            name = "city",
            column = @Column(name = "CITY_NAME")
        ),
        @AttributeOverride(
            name = "postalCode",
            column = @Column(name = "POST_CODE")
        )
    })
    private Address address;
}
~~~

name trong AttributeOverride là property của embeddable; name trong @Column là tên column vật lý. Hai lớp tên này không giống nhau.

### 8.6. SecondaryTable

Một entity có thể trải trên nhiều bảng:

~~~java
@Entity
@Table(name = "EMPLOYEE", schema = "HR")
@SecondaryTable(
    name = "EMPLOYEE_DETAIL",
    schema = "HR",
    pkJoinColumns = @PrimaryKeyJoinColumn(name = "EMPLOYEE_ID")
)
public class EmployeeEntity {
    @Id
    @Column(name = "EMPLOYEE_ID")
    private Long id;

    @Column(name = "BIO", table = "EMPLOYEE_DETAIL")
    private String biography;
}
~~~

Thuộc tính table trong @Column trỏ tới tên secondary table theo metadata entity. Kiểm tra khóa join và schema thực tế của cả hai bảng.

## 9. Mapping sequence và generated identifier của Oracle

### 9.1. Sequence generator

Oracle thường dùng sequence để cấp khóa:

~~~sql
CREATE SEQUENCE APP_DATA.CUSTOMER_SEQ
    START WITH 1
    INCREMENT BY 1
    NOCACHE;
~~~

JPA:

~~~java
@Id
@GeneratedValue(
    strategy = GenerationType.SEQUENCE,
    generator = "customer_seq_generator"
)
@SequenceGenerator(
    name = "customer_seq_generator",
    sequenceName = "CUSTOMER_SEQ",
    schema = "APP_DATA",
    allocationSize = 1
)
@Column(name = "CUSTOMER_ID")
private Long id;
~~~

name trong @SequenceGenerator là tên generator trong persistence metadata. sequenceName là tên sequence vật lý. schema xác định owner sequence.

### 9.2. Allocation size và INCREMENT BY

allocationSize ảnh hưởng cách Hibernate cấp phát ID từ sequence. Nếu Hibernate dùng pooled optimizer, allocationSize cần tương thích với INCREMENT BY của sequence theo chiến lược Hibernate.

Với sequence tăng từng đơn vị, allocationSize=1 là cấu hình đơn giản dễ hiểu. Nếu đặt allocationSize lớn để giảm round trip, phải tạo sequence và cấu hình optimizer phù hợp; nếu không có thể gặp lỗi sequence increment mismatch hoặc sinh ID không như mong đợi.

Không đổi allocationSize trong entity mà quên kiểm tra sequence hiện hữu.

### 9.3. Sequence ở schema khác

Nếu sequence thuộc APP_ID nhưng bảng thuộc APP_DATA:

~~~java
@SequenceGenerator(
    name = "customer_seq_generator",
    sequenceName = "CUSTOMER_SEQ",
    schema = "APP_ID",
    allocationSize = 1
)
~~~

User runtime cần quyền SELECT trên sequence và quyền truy cập bảng. Tên schema của sequence không nhất thiết phải trùng schema của table.

### 9.4. Oracle identity column

Oracle hỗ trợ identity column trên các phiên bản hiện đại:

~~~sql
CREATE TABLE APP_DATA.CUSTOMER (
    CUSTOMER_ID NUMBER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    DISPLAY_NAME VARCHAR2(120) NOT NULL
);
~~~

Có thể ánh xạ:

~~~java
@Id
@GeneratedValue(strategy = GenerationType.IDENTITY)
@Column(name = "CUSTOMER_ID")
private Long id;
~~~

Khả năng và SQL được sinh phụ thuộc Oracle version, dialect và Hibernate version. Nếu schema đã dùng sequence/trigger truyền thống, không đổi sang IDENTITY chỉ bằng cách sửa annotation.

### 9.5. Kiểm tra sequence trong dictionary

~~~sql
SELECT sequence_owner,
       sequence_name,
       increment_by,
       cache_size,
       last_number
FROM   all_sequences
WHERE  sequence_owner = 'APP_DATA'
AND    sequence_name = 'CUSTOMER_SEQ';
~~~

LAST_NUMBER với sequence có cache không nhất thiết là giá trị tiếp theo chắc chắn sẽ được cấp. Dùng dictionary để kiểm tra metadata, không dùng LAST_NUMBER làm phép đếm chính xác ID đã phát.

## 10. Schema legacy và các trường hợp đặc biệt

### 10.1. Schema owner khác runtime user

Ví dụ:
- APP_RUNTIME đăng nhập.
- APP_DATA sở hữu CUSTOMER, SALES_ORDER.
- APP_RUNTIME được grant quyền DML trên các bảng.

Mapping:

~~~java
@Table(name = "CUSTOMER", schema = "APP_DATA")
~~~

DBA có thể cấp quyền theo object:

~~~sql
GRANT SELECT, INSERT, UPDATE, DELETE
ON APP_DATA.CUSTOMER
TO APP_RUNTIME;
~~~

Cấp quyền tối thiểu theo nghiệp vụ. Không cấp DBA, SELECT ANY TABLE hoặc quyền rộng chỉ để tránh lỗi mapping.

### 10.2. Synonym không phải privilege

Nếu tạo synonym:

~~~sql
CREATE SYNONYM APP_RUNTIME.CUSTOMER
FOR APP_DATA.CUSTOMER;
~~~

APP_RUNTIME vẫn cần privilege trên APP_DATA.CUSTOMER. Synonym chỉ cung cấp tên thay thế để phân giải object.

### 10.3. Mapping view và read-only entity

View báo cáo thường không nên được cập nhật qua JPA. Có thể dùng DTO projection/native query hoặc mapping entity read-only theo quy ước ứng dụng. Hibernate có thể hỗ trợ @Immutable trong Hibernate-specific annotation; đây không phải annotation chuẩn JPA.

Nếu view không có primary key, đừng tạo @Id giả từ một cột không duy nhất.

### 10.4. Database link

Object được truy cập qua database link có tên dạng TABLE@DBLINK trong SQL. Mapping JPA thông thường không tự mô hình hóa database link như schema. Có thể dùng native query hoặc view/synonym tại local database, nhưng phải xem xét transaction, privilege và giới hạn distributed query.

### 10.5. Partitioned table

JPA thường ánh xạ table owner/name, không cần chỉ định partition trong @Table. Oracle optimizer chọn partition qua predicate và partition pruning. Nếu cần truy vấn partition cụ thể, dùng native SQL có cú pháp phù hợp và kiểm soát rủi ro phụ thuộc cấu trúc vật lý.

## 11. Schema generation và migration

### 11.1. ddl-auto

Spring Boot có thể cấu hình:

~~~properties
spring.jpa.hibernate.ddl-auto=none
~~~

Các giá trị thường gặp:
- none: không tự quản lý schema.
- validate: kiểm tra mapping với schema có sẵn.
- update: cố gắng điều chỉnh schema theo mapping.
- create: tạo schema mới theo mapping.
- create-drop: tạo lúc start và drop khi shutdown trong một số môi trường.

Đối với production có schema được quản lý bởi DBA/Flyway/Liquibase, thường dùng validate hoặc none. Không dựa vào update để quản lý migration quan trọng: nó không thay thế migration script có review và có thể không biểu diễn đúng mọi thay đổi.

### 11.2. Validate phát hiện gì?

validate giúp Hibernate so khớp một số metadata như table/column mapping với database. Nó không chứng minh:
- Mọi constraint đều đúng.
- Index có đúng như thiết kế.
- Trigger/default/sequence hoạt động đúng.
- Query nghiệp vụ cho kết quả đúng.
- Tất cả grant/synonym đều phù hợp.
- Dữ liệu có sạch.

Kết hợp validate với migration tool, integration test và kiểm tra dictionary.

### 11.3. Flyway/Liquibase quản lý DDL

Ví dụ migration SQL:

~~~sql
CREATE TABLE APP_DATA.CUSTOMER (
    CUSTOMER_ID NUMBER(19) NOT NULL,
    DISPLAY_NAME VARCHAR2(120) NOT NULL,
    CONSTRAINT PK_CUSTOMER PRIMARY KEY (CUSTOMER_ID)
);
~~~

Mapping JPA cần khớp tên thực tế. Migration là nguồn thay đổi schema có version, review và rollback/forward-fix rõ ràng.

### 11.4. Tránh Hibernate tự tạo quoted object không mong muốn

Nếu global quoting hoặc naming strategy không thống nhất giữa migration và Hibernate, schema có thể được tạo thành "customer" trong khi migration tạo CUSTOMER. Đây là hai object khác nhau theo quy tắc Oracle.

Quy định một convention:
- DDL unquoted uppercase.
- JPA annotation dùng uppercase.
- Không bật global quoting nếu không có lý do.
- Quote riêng các object legacy bắt buộc.
- Integration test trên cùng Oracle version/COMPATIBLE với production.

## 12. Chẩn đoán SQL Hibernate sinh ra

### 12.1. Bật SQL logging ở môi trường test

Ví dụ:

~~~properties
logging.level.org.hibernate.SQL=DEBUG
spring.jpa.show-sql=false
~~~

Hibernate SQL log giúp xem:
- Table/schema có được qualify không.
- Tên column có đúng không.
- Identifier có dấu quote không.
- Join column có khớp không.
- Sequence name được gọi là gì.

Không bật log bind value ở production nếu chưa đánh giá dữ liệu nhạy cảm. SQL có thể chứa tên bảng/cột và cấu trúc nghiệp vụ.

### 12.2. Kiểm tra Hibernate metadata

Có thể xem mapping metadata khi khởi tạo EntityManagerFactory hoặc dùng log bootstrapping phù hợp với Hibernate version. Mục tiêu là tìm logical name, physical name và quote state trước khi chạy query.

Không sửa database theo tên SQL nghi ngờ trước khi xác nhận Hibernate đã áp naming strategy nào.

### 12.3. Dùng Oracle dictionary

Bảng:

~~~sql
SELECT owner, table_name
FROM   all_tables
WHERE  owner = 'APP_DATA'
AND    table_name LIKE '%CUSTOMER%';
~~~

Cột:

~~~sql
SELECT owner, table_name, column_name, data_type
FROM   all_tab_columns
WHERE  owner = 'APP_DATA'
AND    table_name = 'CUSTOMER'
ORDER  BY column_id;
~~~

Sequence:

~~~sql
SELECT sequence_owner, sequence_name
FROM   all_sequences
WHERE  sequence_owner = 'APP_DATA';
~~~

Constraint:

~~~sql
SELECT owner,
       table_name,
       constraint_name,
       constraint_type,
       status
FROM   all_constraints
WHERE  owner = 'APP_DATA'
AND    table_name = 'CUSTOMER';
~~~

### 12.4. Phân biệt lỗi mapping và lỗi quyền

ORA-00942 có thể xuất hiện khi:
- Bảng/view không tồn tại.
- Tên/schema sai.
- Quoted case không đúng.
- User không có quyền truy cập object.
- Synonym không resolve được object đích.

Hãy đăng nhập bằng đúng database user của ứng dụng rồi thử SQL được Hibernate sinh. DBA truy vấn bằng SYS/owner có thể thấy object trong khi runtime user không có quyền.

### 12.5. Native SQL và JPQL

JPQL dùng entity name và property name:

~~~java
@Query("select c from CustomerEntity c where c.displayName = :name")
List<CustomerEntity> findByName(@Param("name") String name);
~~~

Native SQL dùng tên object vật lý:

~~~java
@Query(
    value = "select CUSTOMER_ID, DISPLAY_NAME " +
            "from APP_DATA.CUSTOMER where DISPLAY_NAME = :name",
    nativeQuery = true
)
List<Object[]> findNativeByName(@Param("name") String name);
~~~

Không viết APP_DATA.CUSTOMER trong JPQL như thể đó là entity name. Ngược lại, native query phải dùng đúng schema/table/column Oracle.

## 13. Lỗi phổ biến và cách xử lý

| Lỗi | Nguyên nhân có thể | Hướng điều tra |
| --- | --- | --- |
| ORA-00942 | Sai schema/table, quoted case hoặc thiếu privilege | SQL sinh ra, ALL_TABLES, grants, synonym |
| ORA-00904 | Sai tên cột hoặc quoted case | ALL_TAB_COLUMNS, @Column, naming strategy |
| ORA-00903 | Tên table không hợp lệ hoặc mapping sai | @Table, schema, quote, SQL log |
| ORA-01747 | Column specification không hợp lệ, thường do tên/alias/quote sai | SQL generated, reserved word |
| ORA-02289 | Sequence không tồn tại hoặc không có quyền | @SequenceGenerator, ALL_SEQUENCES, GRANT |
| ORA-01031 | Thiếu privilege | Quyền runtime user trên object/sequence |
| ORA-00972 | Identifier quá dài theo COMPATIBLE | Tên object/constraint/sequence |
| MappingException duplicate column | Hai property cùng ghi một cột | insertable/updatable và association ownership |
| Schema-validation error | Mapping và dictionary không khớp | DDL thật, schema, naming strategy, type |

### 13.1. ORA-00942: table or view does not exist

Quy trình:
1. Bật SQL log để lấy câu SQL thực tế.
2. Xác định table có schema prefix hay không.
3. Đăng nhập bằng đúng runtime user.
4. Kiểm tra ALL_TABLES/ALL_VIEWS.
5. Kiểm tra object owner và grant.
6. Kiểm tra synonym nếu dùng.
7. Kiểm tra quoted identifier.

Không cấp SELECT ANY TABLE chỉ để làm lỗi biến mất.

### 13.2. ORA-00904: invalid identifier

Nguyên nhân thường:
- @Column sai.
- Hibernate chuyển camelCase thành snake_case ngoài ý muốn.
- Database có quoted mixed-case column.
- Column thuộc secondary table nhưng mapping sai.
- Native SQL dùng property name thay column name.

So sánh chính xác với ALL_TAB_COLUMNS và SQL log.

### 13.3. ORA-02289: sequence does not exist

Kiểm tra sequence owner, schema trong @SequenceGenerator và privilege SELECT. Nếu sequence nằm schema khác, khai báo schema đúng hoặc cấp quyền/đồng nghĩa phù hợp.

### 13.4. Schema validation failure

Khi Hibernate validate báo missing table/column hoặc type mismatch:
- Kiểm tra datasource có trỏ đúng database/service/PDB.
- Kiểm tra schema default và entity schema.
- Kiểm tra naming strategy.
- Kiểm tra identifier có quote hay không.
- Kiểm tra column type/precision/scale.
- Kiểm tra migration đã chạy đúng môi trường.

Không chuyển ddl-auto sang update chỉ để bỏ qua validation error.

## 14. Mẫu cấu hình thực tế

### 14.1. Schema Oracle uppercase chuẩn

Oracle DDL:

~~~sql
CREATE TABLE APP_DATA.CUSTOMER (
    CUSTOMER_ID NUMBER(19) NOT NULL,
    DISPLAY_NAME VARCHAR2(120) NOT NULL,
    CONSTRAINT PK_CUSTOMER PRIMARY KEY (CUSTOMER_ID)
);
~~~

JPA:

~~~java
@Entity
@Table(name = "CUSTOMER", schema = "APP_DATA")
public class CustomerEntity {
    @Id
    @Column(name = "CUSTOMER_ID")
    private Long id;

    @Column(name = "DISPLAY_NAME", nullable = false, length = 120)
    private String displayName;
}
~~~

### 14.2. Schema legacy có quoted mixed-case

Oracle DDL:

~~~sql
CREATE TABLE APP_DATA."SalesOrder" (
    "OrderId" NUMBER PRIMARY KEY,
    "OrderStatus" VARCHAR2(20)
);
~~~

JPA:

~~~java
@Entity
@Table(name = "\"SalesOrder\"", schema = "APP_DATA")
public class SalesOrderEntity {
    @Id
    @Column(name = "\"OrderId\"")
    private Long id;

    @Column(name = "\"OrderStatus\"")
    private String status;
}
~~~

### 14.3. Runtime user khác owner

Datasource:

~~~properties
spring.datasource.username=APP_RUNTIME
spring.jpa.properties.hibernate.default_schema=APP_DATA
spring.jpa.hibernate.ddl-auto=validate
~~~

DBA grants:

~~~sql
GRANT SELECT, INSERT, UPDATE, DELETE
ON APP_DATA.CUSTOMER
TO APP_RUNTIME;
~~~

Sequence privilege nếu dùng sequence ở schema owner:

~~~sql
GRANT SELECT ON APP_DATA.CUSTOMER_SEQ TO APP_RUNTIME;
~~~

### 14.4. Một persistence unit có nhiều schema

Entity A:

~~~java
@Table(name = "CUSTOMER", schema = "APP_DATA")
~~~

Entity B:

~~~java
@Table(name = "COUNTRY", schema = "REF_DATA")
~~~

Runtime user cần privilege phù hợp trên cả hai schema. Không đặt một default schema duy nhất nếu nó làm mapping thiếu qualifier hoặc qualify sai object.

### 14.5. Mapping association giữa schema

~~~java
@Entity
@Table(name = "SALES_ORDER", schema = "APP_DATA")
public class SalesOrderEntity {
    @Id
    @Column(name = "ORDER_ID")
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "CUSTOMER_ID")
    private CustomerEntity customer;
}
~~~

~~~java
@Entity
@Table(name = "CUSTOMER", schema = "CRM_DATA")
public class CustomerEntity {
    @Id
    @Column(name = "CUSTOMER_ID")
    private Long id;
}
~~~

Hibernate cần join tới đúng schema của entity đích. Kiểm tra SQL sinh ra và grants giữa các owner.

## 15. Quy trình thiết kế mapping cho schema Oracle có sẵn

### Bước 1 — Khám phá database

Thu thập:
- Service name/PDB.
- Runtime username.
- Schema owner.
- Table/view/sequence thực tế.
- Column name và datatype.
- Primary key/foreign key.
- Quoted identifier có tồn tại không.
- Grants và synonyms.

### Bước 2 — Chốt convention tên

Quyết định:
- Entity Java đặt tên theo domain.
- Entity name dùng cho JPQL.
- Table/column name lấy theo dictionary.
- Schema khai báo rõ ở entity hoặc default schema.
- Reserved words được tránh hoặc quote riêng.
- Không bật global quoting nếu không cần.

### Bước 3 — Kiểm tra phiên bản

Ghi nhận:
- Spring Boot version.
- Hibernate ORM version.
- Jakarta Persistence hay javax.persistence.
- Oracle JDBC driver.
- Oracle Database version và COMPATIBLE.

Naming strategy, dialect và hỗ trợ identity/sequence có thể khác theo các phiên bản này.

### Bước 4 — Viết mapping tường minh

Khai báo:
- @Entity.
- @Table.
- @Id.
- @Column.
- @JoinColumn/@JoinTable.
- @SequenceGenerator nếu cần.
- @SecondaryTable/@CollectionTable nếu object thực tế sử dụng.

### Bước 5 — Kiểm soát naming strategy

Đọc implicit/physical naming configuration. Nếu schema legacy dùng tên chính xác, cân nhắc PhysicalNamingStrategyStandardImpl và annotation tường minh.

### Bước 6 — Kiểm tra quyền

Dùng runtime user đăng nhập thử SELECT/INSERT cần thiết. Xác nhận privilege trên table, sequence, view và object phụ thuộc.

### Bước 7 — Validate và integration test

Dùng ddl-auto=validate hoặc none theo chính sách. Chạy test trên Oracle thật hoặc môi trường tương thích; H2 không mô phỏng đầy đủ quoted identifier, Oracle sequence, datatype và SQL dialect.

### Bước 8 — Quan sát SQL thực tế

Bật SQL log trong test. Đối chiếu schema/table/column/sequence với dictionary. Xác nhận service và PDB sau khi mở connection.

### Bước 9 — Đưa migration vào version control

Quản lý DDL bằng Flyway/Liquibase hoặc quy trình migration nội bộ. Review DDL và mapping cùng nhau trong pull request.

### Bước 10 — Kiểm soát production

- Không tự tạo/sửa schema từ mỗi application instance.
- Dùng runtime account ít quyền.
- Không log bind values nhạy cảm.
- Có smoke test sau deploy.
- Theo dõi lỗi ORA và schema validation.
- Giữ naming convention ổn định giữa môi trường.

## 16. Bài thực hành

Dùng Oracle schema test. Tạo các object bằng DDL trong schema được cấp, sau đó ánh xạ bằng Spring Boot/JPA. Không đổi schema production để thử.

### Bài 1 — Entity name và table name

Tạo CustomerEntity với @Entity(name="Customer") và @Table(name="CUSTOMER"). Viết JPQL dùng Customer và kiểm tra SQL tham chiếu CUSTOMER.

### Bài 2 — Explicit column mapping

Ánh xạ Java displayName tới DISPLAY_NAME. Xem SQL sinh ra và xác nhận dictionary.

### Bài 3 — Schema owner khác runtime user

Đăng nhập bằng APP_RUNTIME, map bảng APP_DATA.CUSTOMER, cấp quyền object tối thiểu và xác minh truy vấn.

### Bài 4 — Default schema

Bỏ schema khỏi @Table và cấu hình hibernate.default_schema=APP_DATA. Kiểm tra SQL. Sau đó thử bỏ property và ghi nhận khác biệt.

### Bài 5 — Physical naming strategy

So sánh default strategy của dự án với PhysicalNamingStrategyStandardImpl. Ghi nhận tên table/column thực tế được sinh.

### Bài 6 — Quoted mixed-case table

Tạo "SalesOrder" và "OrderId". Map bằng chuỗi quote đã escape trong annotation. Kiểm tra SQL có đúng case và dấu ngoặc kép.

### Bài 7 — Reserved word

Tạo bảng test có cột quoted "Order". Ánh xạ riêng cột này và so sánh với một tên không reserved.

### Bài 8 — Global quoted identifiers

Trong môi trường test, bật globally_quoted_identifiers. Xem SQL và giải thích vì sao identifier lowercase quoted có thể khác uppercase unquoted. Khôi phục cấu hình.

### Bài 9 — Synonym

Tạo synonym cho một bảng ở schema khác. Map unqualified table name và xem tác động khi thêm hibernate.default_schema.

### Bài 10 — Association và JoinColumn

Tạo CUSTOMER và SALES_ORDER với foreign key. Ánh xạ ManyToOne, xác minh JOIN column và schema của hai entity.

### Bài 11 — Sequence generator

Tạo CUSTOMER_SEQ INCREMENT BY 1. Dùng @SequenceGenerator allocationSize=1 và insert entity. Sau đó thử kiểm tra metadata sequence.

### Bài 12 — CollectionTable

Ánh xạ một Set<String> vào bảng CUSTOMER_TAG. Xác minh schema, join column và value column.

### Bài 13 — Schema validation

Chạy ddl-auto=validate với mapping đúng, sau đó cố tình đổi một column name trong test để quan sát lỗi. Khôi phục mapping.

### Bài 14 — Điều tra ORA-00942/00904

Tạo một mapping sai schema hoặc sai quoted case. Dùng SQL log và ALL_TABLES/ALL_TAB_COLUMNS để tìm nguyên nhân. Sửa annotation/naming strategy và chạy lại.

## 17. Những hiểu nhầm thường gặp

**“@Entity(name) là tên bảng.”** Không. Đó là entity name dùng trong JPQL; @Table xác định table vật lý.

**“Tên class Java tự động bằng tên table.”** Không bắt buộc. Hibernate có implicit/physical naming strategy và @Table cho mapping rõ ràng.

**“Database user cũng chính là schema trong mọi trường hợp.”** Không. Runtime user có thể truy cập object của schema owner khác.

**“hibernate.default_schema cấp quyền cho user.”** Không. Nó chỉ ảnh hưởng cách Hibernate qualify tên object.

**“ALTER SESSION SET CURRENT_SCHEMA thay đổi user đăng nhập.”** Không. SESSION_USER vẫn giữ nguyên; CURRENT_SCHEMA chỉ ảnh hưởng name resolution.

**“Oracle không phân biệt chữ hoa/thường.”** Unquoted identifier được chuẩn hóa uppercase; quoted identifier giữ chính xác case và phải tham chiếu đúng.

**“Chỉ cần đặt tên table trong ngoặc kép ở Oracle là JPA tự hiểu.”** Không. Annotation phải yêu cầu quote đúng cách và naming strategy không được làm biến đổi identifier.

**“Bật globally_quoted_identifiers luôn an toàn.”** Không. Nó có thể tạo quoted identifier khác với object unquoted hiện có.

**“Synonym cấp quyền truy cập object.”** Không. User vẫn cần privilege trên object đích.

**“@Column(length=120) tự thay đổi cột production.”** Không. Nó là mapping metadata; ddl-auto/migration policy quyết định schema có được thay đổi hay không.

**“ddl-auto=update thay thế Flyway/Liquibase.”** Không. Nó không thay thế migration có version, review, rollback và kiểm soát production.

**“H2 test thành công chứng minh Oracle mapping đúng.”** Không. H2 không mô phỏng đầy đủ Oracle identifier, sequence, datatype, synonym và SQL dialect.

## 18. Tài liệu tham khảo

- [Jakarta Persistence Specification](https://jakarta.ee/specifications/persistence/): quy tắc entity, table, column, identifier và mapping quan hệ.
- [Hibernate ORM User Guide](https://docs.jboss.org/hibernate/orm/current/userguide/html_single/Hibernate_User_Guide.html): implicit/physical naming strategy, identifier quoting, schema và sequence mapping.
- [Spring Boot Reference — Data Access](https://docs.spring.io/spring-boot/reference/data/sql.html): cấu hình datasource, JPA và Hibernate trong Spring Boot.
- [Oracle Database 19c SQL Language Reference — Database Object Names and Qualifiers](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/Database-Object-Names-and-Qualifiers.html): quy tắc identifier, quoted name và giới hạn tên object.
- [Oracle Database 19c SQL Language Reference — CREATE TABLE](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/CREATE-TABLE.html): tên bảng, cột, constraint và DDL.
- [Oracle Database 19c SQL Language Reference — CREATE SEQUENCE](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/CREATE-SEQUENCE.html): sequence và thuộc tính cấp số.
- [Oracle Database 19c Database Reference — ALL_TAB_COLUMNS](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/ALL_TAB_COLUMNS.html): metadata cột.
- [Oracle Database 19c Database Reference — ALL_TABLES](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/ALL_TABLES.html): metadata bảng.
- [Oracle Database 19c SQL Language Reference — CREATE SYNONYM](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/CREATE-SYNONYM.html): synonym và name resolution.

Mapping JPA với Oracle cần phân biệt entity/property name với tên bảng/cột vật lý, schema owner với runtime user, và unquoted identifier với quoted identifier. Dùng @Table/@Column/@JoinColumn/@SequenceGenerator để mô tả object hiện có; kiểm soát implicit/physical naming strategy; chỉ dùng default schema hoặc CURRENT_SCHEMA khi hiểu rõ phạm vi; và kiểm tra SQL sinh ra bằng đúng runtime account. **Giữ tên vật lý nhất quán với dictionary Oracle, quote chính xác các identifier legacy bắt buộc và để migration tool quản lý DDL có version.**
