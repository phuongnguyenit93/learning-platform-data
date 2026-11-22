# Entity, tên bảng/cột, backtick và phân biệt hoa/thường theo nền tảng

Trong ứng dụng Spring Boot dùng JPA với MySQL, tên class Entity, tên thuộc tính Java và tên bảng/cột trong database có liên quan nhưng không nhất thiết giống nhau. JPA/Hibernate chuyển mapping của Entity thành SQL; naming strategy có thể đổi tên theo quy ước; MySQL lại có quy tắc riêng về identifier, từ khóa dành riêng và phân biệt chữ hoa/chữ thường. Nếu không kiểm soát các lớp này, ứng dụng có thể chạy trên máy phát triển nhưng lỗi `Table doesn't exist`, `Unknown column` hoặc lỗi mapping khi triển khai lên Linux.

Bài học này trình bày cách ánh xạ Entity bằng `@Entity`, `@Table`, `@Column`, cách Hibernate áp dụng implicit/physical naming strategy, cách dùng backtick khi phải làm việc với identifier đặc biệt và ảnh hưởng của `lower_case_table_names` trên các nền tảng. Ví dụ dùng Spring Boot, Hibernate ORM và MySQL; hành vi cụ thể cần được xác nhận với phiên bản đang dùng.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt tên Entity trong JPQL với tên bảng vật lý trong MySQL.
- Ánh xạ rõ ràng tên bảng, cột và khóa ngoại bằng annotation JPA.
- Giải thích implicit naming strategy và physical naming strategy.
- Tránh xung đột với từ khóa SQL và biết khi nào cần quote identifier bằng backtick.
- Phân biệt quy tắc chữ hoa/thường của database/table và column trong MySQL.
- Kiểm tra `lower_case_table_names` và phát hiện rủi ro khi chuyển ứng dụng giữa Windows, macOS và Linux.
- Đồng bộ mapping JPA với schema migration và kiểm thử trên MySQL thật.

## 1. Bốn lớp tên cần phân biệt

Khi đọc một Entity, cần phân biệt các tên sau:

| Lớp tên | Ví dụ | Được dùng ở đâu? |
|---|---|---|
| Tên class Java | `PurchaseOrder` | Mã Java, reflection và type system |
| Tên Entity | `PurchaseOrder` hoặc tên đặt trong `@Entity(name = ...)` | JPQL/HQL, ví dụ `SELECT p FROM PurchaseOrder p` |
| Tên bảng vật lý | `purchase_order` | SQL gửi tới MySQL |
| Tên cột vật lý | `customer_id`, `created_at` | SQL và cấu trúc bảng MySQL |

Tên Entity không phải tên bảng. Ví dụ, `@Entity(name = "PurchaseOrder")` đặt tên dùng trong JPQL; `@Table(name = "purchase_order")` xác định bảng vật lý mà Hibernate truy cập. Tương tự, tên thuộc tính Java `customerId` có thể được ánh xạ sang cột `customer_id`.

JPQL dùng tên Entity và thuộc tính Java, còn SQL dùng tên bảng/cột vật lý. Nhầm hai loại tên này là nguyên nhân thường gặp khi viết query hoặc đọc log Hibernate.

## 2. Ánh xạ Entity rõ ràng bằng annotation

Ví dụ một Entity đại diện cho bảng `purchase_order`:

```java
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.time.LocalDateTime;

@Entity
@Table(name = "purchase_order")
public class PurchaseOrder {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "customer_id", nullable = false)
    private Long customerId;

    @Column(name = "created_at", nullable = false)
    private LocalDateTime createdAt;

    @Enumerated(EnumType.STRING)
    @Column(name = "order_status", nullable = false, length = 30)
    private OrderStatus status;

    protected PurchaseOrder() {
    }

    // Constructor, getter và method nghiệp vụ được lược bỏ.
}
```

Ở đây:

- `@Entity` đánh dấu class là persistent entity.
- `@Table(name = "purchase_order")` chỉ rõ bảng trong MySQL.
- `@Id` xác định khóa chính ở cấp JPA.
- `@Column(name = "customer_id")` ánh xạ thuộc tính Java sang tên cột vật lý.
- `@Enumerated(EnumType.STRING)` lưu tên enum thay vì vị trí ordinal; cách này tránh việc đổi thứ tự enum làm thay đổi ý nghĩa dữ liệu cũ.

Tên cột trong `@Column` phải khớp với schema thực tế sau khi áp dụng naming strategy. `nullable`, `length` và các thuộc tính annotation mô tả mapping/DDL metadata; chúng không tự thay thế migration SQL trong production.

### 2.1. Entity name khác table name

Có thể đặt tên Entity riêng cho JPQL:

```java
@Entity(name = "Purchase")
@Table(name = "purchase_order")
public class PurchaseOrder {
    // Fields...
}
```

JPQL sử dụng tên Entity:

```java
@Query("select p from Purchase p where p.customerId = :customerId")
List<PurchaseOrder> findByCustomer(@Param("customerId") Long customerId);
```

Native SQL sử dụng tên bảng và cột trong database:

```java
@Query(value = "SELECT * FROM purchase_order WHERE customer_id = :customerId",
       nativeQuery = true)
List<PurchaseOrder> findNativeByCustomer(@Param("customerId") Long customerId);
```

Không dùng `purchase_order` làm tên Entity trong JPQL trừ khi đó là tên Entity được khai báo. Ngược lại, không dùng `Purchase` trong SQL native nếu bảng vật lý không có tên đó.

### 2.2. Ánh xạ khóa ngoại

Tên cột khóa ngoại có thể được chỉ rõ bằng `@JoinColumn`:

```java
@ManyToOne(fetch = FetchType.LAZY, optional = false)
@JoinColumn(name = "customer_id", nullable = false)
private Customer customer;
```

Nếu Entity `Customer` có `@Table(name = "customer")` và khóa chính `id`, mapping trên dùng cột `customer_id` trong bảng `purchase_order` để tham chiếu. Cần bảo đảm kiểu dữ liệu, signedness, index và constraint của hai phía tương thích trong MySQL.

Khi một cột vừa được ánh xạ qua field scalar vừa được dùng làm join column, tránh để cả hai mapping cùng ghi vào một cột. Nếu thật sự cần đọc giá trị scalar riêng, có thể cấu hình một mapping chỉ đọc bằng `insertable = false, updatable = false`, nhưng cần thiết kế rõ bên nào sở hữu thao tác ghi.

## 3. Implicit naming và physical naming strategy

Hibernate có hai giai đoạn đặt tên:

1. **Implicit naming strategy** xác định logical name khi mapping không chỉ rõ tên đầy đủ. Ví dụ, tên bảng có thể được suy ra từ tên class Entity; tên cột có thể được suy ra từ thuộc tính.
2. **Physical naming strategy** chuyển logical name thành physical name dùng trong database. Chiến lược này có thể đổi camelCase thành snake_case, viết thường hoặc áp dụng quy tắc riêng của tổ chức.

Ví dụ nếu không chỉ rõ tên:

```java
@Entity
public class CustomerAccount {
    @Id
    private Long id;

    private LocalDateTime createdAt;
}
```

Một physical naming strategy kiểu Spring có thể tạo tên vật lý như `customer_account` và `created_at`. Tuy nhiên, kết quả chính xác phụ thuộc implicit strategy, physical strategy, phiên bản Spring Boot/Hibernate và cấu hình ứng dụng. Không suy đoán schema chỉ từ tên class.

### 3.1. Cấu hình physical naming strategy

Spring Boot cho phép cấu hình strategy bằng property:

```properties
spring.jpa.hibernate.naming.physical-strategy=org.hibernate.boot.model.naming.CamelCaseToUnderscoresNamingStrategy
```

Class strategy phải tồn tại trong phiên bản Hibernate mà ứng dụng đang dùng. Một dự án cũng có thể dùng strategy riêng hoặc strategy mặc định do Spring Boot cấu hình. Trước khi thay đổi, kiểm tra cấu hình thực tế và SQL được Hibernate phát ra.

Physical naming strategy thường được áp dụng cho cả logical name sinh tự động và tên được chỉ rõ trong mapping. Vì vậy, nếu annotation đã đặt `customerId` nhưng strategy chuyển sang `customer_id`, schema phải được tạo theo tên vật lý cuối cùng đó. Dùng tên đã theo chuẩn vật lý ngay trong annotation sẽ dễ dự đoán hơn.

### 3.2. Chọn một quy ước ổn định

Một quy ước phổ biến cho MySQL là:

- Class và property Java dùng `PascalCase`/`camelCase`.
- Tên database, table và column dùng chữ thường cùng dấu gạch dưới.
- Không dùng dấu cách, dấu gạch ngang hoặc ký tự đặc biệt trong identifier.
- Tên bảng là danh từ nghiệp vụ rõ nghĩa, ví dụ `customer_account`, `purchase_order`, `payment_transaction`.
- Tên khóa ngoại thể hiện quan hệ, ví dụ `customer_id`, `warehouse_id`.
- Tránh từ khóa SQL và tên dễ gây nhầm lẫn như `order`, `group`, `rank`, `user` nếu chưa kiểm tra danh sách reserved words của phiên bản MySQL.

Chọn quy ước trước khi tạo schema và áp dụng nhất quán ở Entity, migration SQL, native query, view, stored procedure và script vận hành. Một naming strategy tốt không thể tự sửa các native SQL đang hard-code tên cũ.

## 4. Từ khóa SQL và backtick trong MySQL

MySQL dùng backtick (`` ` ``) để quote identifier. Identifier là tên database, table, column, index hoặc đối tượng khác. Backtick giúp dùng tên trùng với từ khóa SQL hoặc chứa ký tự cần quote.

Ví dụ nếu phải làm việc với một bảng cũ có tên `order`:

```sql
SELECT id, customer_id
FROM `order`
WHERE id = 1001;
```

Nếu tên cột cũng trùng từ khóa:

```sql
SELECT `rank`, `group`
FROM `order`;
```

Trong MySQL, chuỗi ký tự dùng dấu nháy đơn:

```sql
SELECT *
FROM purchase_order
WHERE order_status = 'PAID';
```

Không dùng backtick để quote giá trị dữ liệu; backtick dành cho identifier.

### 4.1. Quote identifier trong mapping Hibernate

Hibernate hỗ trợ cú pháp backtick trong tên mapping để yêu cầu quote identifier theo dialect:

```java
@Entity
@Table(name = "`order`")
public class LegacyOrder {

    @Id
    private Long id;

    @Column(name = "`rank`")
    private Integer rank;
}
```

Đây là cú pháp quoting của Hibernate, không phải quy tắc annotation độc lập của mọi JPA provider. Hibernate đọc dấu backtick trong mapping và dialect MySQL phát SQL có quote phù hợp. Nếu ứng dụng đổi JPA provider, phải kiểm tra lại mapping.

Với bảng mới, nên chọn tên không phải từ khóa như `purchase_order` thay vì phụ thuộc vào quoting. Quote là công cụ tương thích với schema cũ hoặc identifier bắt buộc phải giữ nguyên.

### 4.2. Backtick trong SQL và ký tự backtick bên trong tên

Trong MySQL, một backtick bên trong identifier đã quote được biểu diễn bằng hai backtick liên tiếp. Tuy nhiên, tên chứa backtick rất khó đọc và dễ gây lỗi khi sinh SQL; không nên đặt tên mới theo cách này.

Một số hệ quản trị dùng dấu nháy kép để quote identifier. Trong MySQL, dấu nháy kép mặc định thường biểu diễn string literal; khi bật SQL mode `ANSI_QUOTES`, dấu nháy kép được dùng cho identifier và không còn dùng như string literal thông thường. Vì vậy, không viết SQL phụ thuộc vào double quote nếu môi trường không kiểm soát SQL mode.

Kiểm tra SQL mode:

```sql
SELECT @@SESSION.sql_mode;
SELECT @@GLOBAL.sql_mode;
```

Không thay đổi `ANSI_QUOTES` tùy tiện vì nó có thể làm thay đổi cách diễn giải SQL hiện có.

### 4.3. Quote toàn bộ identifier có nên không?

Hibernate có tùy chọn quote toàn bộ identifier, chẳng hạn property `hibernate.globally_quoted_identifiers`. Cách này có thể giúp tránh keyword conflict, nhưng cũng làm thay đổi SQL sinh ra và tương tác với metadata, tên đã viết hoa/thường, migration và native query.

Không bật quote toàn cục chỉ để che một vài tên bảng/cột không tốt. Ưu tiên quy ước tên an toàn, quote có chọn lọc cho schema legacy và kiểm tra SQL được sinh ra sau khi thay đổi cấu hình.

## 5. Phân biệt hoa/thường trong MySQL

MySQL không áp dụng cùng một quy tắc case sensitivity cho mọi loại identifier. Điểm quan trọng nhất khi triển khai đa nền tảng là tên database và table có thể phân biệt hoa/thường khác nhau tùy hệ điều hành và cấu hình `lower_case_table_names`.

### 5.1. `lower_case_table_names`

Kiểm tra giá trị đang chạy:

```sql
SELECT @@GLOBAL.lower_case_table_names;
```

Các giá trị chính:

| Giá trị | Cách lưu tên database/table | Cách so sánh |
|---:|---|---|
| `0` | Giữ nguyên chữ hoa/thường khi tạo | Phân biệt hoa/thường |
| `1` | Lưu tên dưới dạng chữ thường | Không phân biệt hoa/thường |
| `2` | Giữ cách viết khi lưu trên filesystem hỗ trợ, nhưng so sánh dạng chữ thường | Không phân biệt hoa/thường |

Các mặc định phổ biến thường khác nhau theo nền tảng: Linux thường dùng `0`, Windows thường dùng `1`, macOS có thể dùng `2`. Giá trị thực tế phụ thuộc bản cài đặt, filesystem và cách server được khởi tạo; luôn đọc biến trên instance thay vì dựa vào hệ điều hành một cách tuyệt đối.

Trong MySQL 8.0, `lower_case_table_names` phải được chọn khi khởi tạo data directory và không thể đổi tùy ý sau khi instance đã được khởi tạo. Giá trị phải tương thích với filesystem; server có thể từ chối khởi động nếu cấu hình không hợp lệ trên nền tảng đó.

### 5.2. Ví dụ lỗi khi chuyển Windows sang Linux

Giả sử một schema có bảng mang tên `CustomerAccount`:

```sql
CREATE TABLE CustomerAccount (
  id BIGINT PRIMARY KEY,
  email VARCHAR(255) NOT NULL
);
```

Trên server không phân biệt hoa/thường (thường gặp ở Windows với `lower_case_table_names=1`), truy vấn `SELECT * FROM customeraccount` có thể tìm thấy bảng đó. Trên Linux với `lower_case_table_names=0`, tên `CustomerAccount` và `customeraccount` là hai identifier khác nhau; cùng câu truy vấn viết thường có thể báo không tìm thấy bảng. Đây là lý do cần thống nhất tên vật lý trong migration và mapping, rồi kiểm thử trên cấu hình production.

Nếu hệ thống có cả bảng `User` và `user`, chúng có thể cùng tồn tại trên môi trường phân biệt hoa/thường nhưng không thể được phân biệt trên môi trường không phân biệt hoa/thường. Đây là xung đột schema cần xử lý trước khi chuyển nền tảng.

### 5.3. Column name khác table name

Tên cột trong MySQL không phân biệt hoa/thường theo cách tên database/table có thể phân biệt. Ví dụ `customer_id` và `CUSTOMER_ID` chỉ cùng một cột. Quy tắc này không có nghĩa nên trộn cách viết; dùng một kiểu chữ nhất quán giúp SQL dễ đọc và giảm lỗi khi chuyển đổi sang hệ quản trị khác.

Tên alias, tên Entity và thuộc tính Java có quy tắc riêng. Java phân biệt hoa/thường, và tên Entity/thuộc tính trong JPQL cần khớp mapping. Vì vậy, một property `customerId` không thể được gọi là `CustomerID` trong JPQL chỉ vì tên cột MySQL không phân biệt hoa/thường.

## 6. Tên vật lý, reserved words và migration schema

Entity mapping phải khớp với schema thực tế. Trong ứng dụng Spring Boot production, nên quản lý thay đổi schema bằng Flyway hoặc Liquibase thay vì phụ thuộc vào Hibernate tự tạo/sửa bảng.

Ví dụ migration SQL:

```sql
CREATE TABLE purchase_order (
  id BIGINT NOT NULL AUTO_INCREMENT,
  customer_id BIGINT NOT NULL,
  created_at DATETIME NOT NULL,
  order_status VARCHAR(30) NOT NULL,
  PRIMARY KEY (id),
  KEY idx_purchase_order_customer (customer_id)
) ENGINE = InnoDB;
```

Mapping JPA phải trỏ đúng tên bảng và cột này. Nếu đổi tên `customer_id` trong migration mà quên cập nhật `@Column` hoặc naming strategy, ứng dụng sẽ phát sinh lỗi khi chạy truy vấn.

### 6.1. Dùng schema validation

Trong production, cấu hình Hibernate kiểm tra mapping thay vì tự động sửa schema:

```properties
spring.jpa.hibernate.ddl-auto=validate
```

`validate` yêu cầu Hibernate kiểm tra schema hiện tại có tương thích với mapping hay không. Nó không tạo migration và không thay thế kiểm tra đầy đủ về index, dữ liệu, constraint hay hiệu năng. Trong môi trường phát triển, có thể dùng cấu hình khác tùy workflow, nhưng không dùng `update` như công cụ quản lý schema production.

### 6.2. Kiểm tra bảng và cột thực tế

Khi gặp lỗi `Table doesn't exist` hoặc `Unknown column`, kiểm tra định nghĩa vật lý:

```sql
SHOW CREATE TABLE app.purchase_order\G

SELECT TABLE_NAME
FROM INFORMATION_SCHEMA.TABLES
WHERE TABLE_SCHEMA = 'app'
ORDER BY TABLE_NAME;

SELECT COLUMN_NAME, COLUMN_TYPE
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA = 'app'
  AND TABLE_NAME = 'purchase_order'
ORDER BY ORDINAL_POSITION;
```

So sánh kết quả với:

- `@Table`, `@Column`, `@JoinColumn` trong Entity.
- Implicit và physical naming strategy đang cấu hình.
- Native query, JPQL và query trong repository.
- Migration đã chạy ở môi trường đích.
- Giá trị `lower_case_table_names` của database.

Không chỉ sửa câu SQL cho chạy được; xác định nguồn tạo ra tên vật lý sai để các Entity và migration tiếp theo không tiếp tục lệch nhau.

## 7. Quan sát SQL do Hibernate sinh ra

Khi mapping không khớp, cần biết Hibernate thực sự phát câu SQL nào. Trong môi trường phát triển có thể bật log SQL:

```properties
logging.level.org.hibernate.SQL=DEBUG
```

Với Hibernate 6, log bind parameter có thể bật bằng:

```properties
logging.level.org.hibernate.orm.jdbc.bind=TRACE
```

Log bind parameter có thể chứa email, token, thông tin cá nhân hoặc dữ liệu nhạy cảm. Không bật mức TRACE trong production nếu chưa có biện pháp bảo vệ, che dữ liệu và giới hạn thời gian lưu log.

Để quan sát tên được phát ra, thực hiện một truy vấn repository hoặc thao tác flush trên môi trường thử nghiệm rồi đối chiếu SQL với `SHOW CREATE TABLE`. Chú ý Hibernate có thể chỉ phát DML khi flush; `save()` không nhất thiết gửi SQL ngay tại dòng code đó.

### 7.1. Lỗi thường gặp và hướng điều tra

| Lỗi | Nguyên nhân thường gặp | Kiểm tra |
|---|---|---|
| `Table 'app.customer_account' doesn't exist` | Tên vật lý do naming strategy khác tên migration hoặc khác chữ hoa/thường | `SHOW CREATE TABLE`, `@@lower_case_table_names`, naming strategy |
| `Unknown column 'created_at'` | `@Column`/strategy không khớp schema hoặc migration chưa chạy | `INFORMATION_SCHEMA.COLUMNS`, log Hibernate |
| `You have an error in your SQL syntax` gần tên bảng | Identifier trùng reserved word hoặc thiếu quote | Kiểm tra keyword list và backtick trong SQL |
| JPQL báo không tìm thấy Entity | Dùng tên bảng thay cho entity name hoặc sai tên Entity | `@Entity(name=...)` và query JPQL |
| Chạy trên Windows, lỗi trên Linux | Tên bảng khác case và `lower_case_table_names` khác | Chuẩn hóa tên vật lý và kiểm thử trên Linux |
| Migration chạy nhưng Hibernate không tìm thấy bảng | Migration tạo tên khác với tên do physical strategy sinh | So sánh SQL migration với tên vật lý cuối cùng |

## 8. Quy trình thiết kế tên cho dự án mới

Khi tạo module Spring Boot/JPA mới, có thể đi theo thứ tự:

1. Chọn quy ước tên vật lý cho database, table, column, index và constraint.
2. Chọn implicit/physical naming strategy phù hợp với convention đó.
3. Dùng `@Entity`, `@Table`, `@Column` và `@JoinColumn` để thể hiện mapping rõ ràng ở những chỗ quan trọng.
4. Tránh reserved words, dấu cách, dấu gạch ngang và identifier chỉ khác nhau ở chữ hoa/thường.
5. Tạo schema bằng Flyway/Liquibase với tên vật lý đã thống nhất.
6. Đặt `ddl-auto=validate` trong production để phát hiện lệch mapping.
7. Chạy integration test trên MySQL cùng major version và cấu hình case sensitivity gần production.
8. Kiểm tra SQL Hibernate sinh ra và `SHOW CREATE TABLE` trước khi phát hành.

Với hệ thống legacy, không đổi đồng loạt tên bảng chỉ bằng cách đổi naming strategy. Một thay đổi strategy có thể làm Hibernate phát SQL tới tên khác trên hàng loạt Entity. Cần migration có kiểm soát, tương thích với phiên bản ứng dụng cũ/mới và kế hoạch chuyển dữ liệu hoặc view nếu cần.

## 9. Kiểm thử đa nền tảng

Nếu developer dùng Windows hoặc macOS nhưng production chạy Linux, kiểm thử chỉ bằng H2 hoặc MySQL cài local có thể bỏ sót lỗi case sensitivity. Hãy dùng MySQL thật trong integration test, ví dụ qua Testcontainers, với image và cấu hình gần môi trường triển khai.

Kiểm thử cần bao gồm:

- Khởi tạo schema từ toàn bộ migration trên database rỗng.
- Khởi động Spring context và để Hibernate validate mapping.
- Chạy repository query, JPQL và native SQL.
- Kiểm tra các tên bảng/cột có chữ hoa/thường hoặc reserved word trong schema legacy.
- Xác minh `lower_case_table_names` trên test server phù hợp môi trường production.
- Chạy migration nâng cấp từ schema phiên bản trước, không chỉ kiểm thử tạo mới.

Không nên tạo hai bảng chỉ khác chữ hoa/thường để phục vụ logic nghiệp vụ. Nếu schema cũ đã có tên xung đột, cần đổi tên theo migration trước khi chuyển sang nền tảng có quy tắc khác.

## 10. Bài thực hành

Một ứng dụng Spring Boot chạy trên Windows ở môi trường phát triển và Linux ở production. Entity hiện có:

```java
@Entity
public class UserOrder {
    @Id
    private Long id;

    private Long customerId;
    private LocalDateTime createdAt;
}
```

Migration production lại tạo bảng `user_order` với các cột `customer_id` và `created_at`. Một native query tham chiếu bảng `User_Order`, trong khi một bảng legacy khác có tên `order`.

Hãy giải quyết các yêu cầu:

1. Giải thích tên Entity, tên class và tên bảng vật lý khác nhau thế nào.
2. Viết mapping `@Table` và `@Column` rõ ràng cho `user_order`, `customer_id`, `created_at`.
3. Xác định implicit và physical naming strategy có thể tạo tên vật lý nào nếu bỏ annotation.
4. Sửa native query để dùng đúng tên bảng và cột.
5. Nếu buộc phải truy vấn bảng legacy tên `order`, viết SQL dùng backtick và giải thích vì sao nên đổi tên khi có thể.
6. So sánh `lower_case_table_names=0`, `1` và `2`; giải thích vì sao ứng dụng chạy trên Windows có thể lỗi trên Linux.
7. Vì sao không thể dùng backtick để làm cho `Order` và `order` trở thành hai bảng khác nhau trên server không phân biệt hoa/thường?
8. Nêu cách kiểm tra schema bằng `SHOW CREATE TABLE`, `INFORMATION_SCHEMA` và log Hibernate.
9. Đề xuất cấu hình schema validation và quy trình migration cho production.
10. Thiết kế integration test để phát hiện lỗi tên bảng/cột trước khi phát hành.

Hãy thử chạy migration trên MySQL test có cấu hình gần production, khởi động Spring Boot với `ddl-auto=validate`, thực thi repository query và đối chiếu SQL được log với định nghĩa bảng.

## Kết luận

JPA Entity name, tên class Java và tên bảng/cột vật lý là các lớp tên khác nhau. `@Entity`, `@Table`, `@Column` và `@JoinColumn` giúp thể hiện mapping; implicit/physical naming strategy quyết định cách tên được suy ra và chuyển đổi. MySQL dùng backtick để quote identifier, nhưng quote không thay đổi quy tắc phân biệt hoa/thường của server. Đặc biệt, `lower_case_table_names` ảnh hưởng tên database/table và phải được chọn khi khởi tạo data directory. Hãy chuẩn hóa tên chữ thường theo snake_case, tránh reserved words, quản lý schema bằng migration và kiểm thử trên MySQL có cấu hình tương đương production.
