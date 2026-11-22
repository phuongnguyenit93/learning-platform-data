# Ánh xạ lược đồ có sẵn với tên đặc biệt, kiểu cột cũ hoặc cấu trúc bất thường

Khi bắt đầu một dự án mới, lập trình viên thường thiết kế entity rồi để migration tạo bảng tương ứng. Với hệ thống đang vận hành nhiều năm, chiều công việc có thể ngược lại: **database đã tồn tại**, có dữ liệu thật, ràng buộc và quy ước tên cũ; nhiệm vụ của JPA/Hibernate là ánh xạ chính xác lược đồ đó mà vẫn giữ hành vi của ứng dụng cũ.

Những khó khăn thường gặp gồm tên bảng có khoảng trắng hoặc trùng từ khóa SQL, identifier phân biệt chữ hoa/chữ thường, kiểu `CHAR(1)` lưu trạng thái, ngày lưu bằng `CHAR(8)`, số tiền lưu bằng số nguyên, khóa ghép, khóa ngoại tham chiếu mã nghiệp vụ, bảng không có khóa chính, view chỉ đọc hoặc một entity trải trên nhiều bảng. Chúng không nhất thiết yêu cầu viết lại toàn bộ dữ liệu; Hibernate có nhiều cơ chế ánh xạ nhưng mỗi cơ chế có giới hạn.

Bài học thuộc chương **Ánh xạ nâng cao** của module *Data Persistence Relational Access ORM Hibernate*, sử dụng Jakarta Persistence (`jakarta.persistence.*`) và một số phần mở rộng của Hibernate ORM. Ví dụ SQL dùng **PostgreSQL** để thể hiện cách trích dẫn identifier; ký tự quote và những kiểu dữ liệu đặc thù khác nhau giữa các hệ quản trị.

## 1. Tư duy database-first: ánh xạ đúng hợp đồng hiện có

Với schema mới, ta thường bắt đầu:

~~~text
Java entity → migration → bảng, cột, khóa, chỉ mục
~~~

Với schema cũ, luồng công việc là:

~~~text
Schema thực tế + dữ liệu + quy tắc truy cập cũ
                        ↓
             Phân tích ánh xạ
                        ↓
       Entity, identifier, converter,
      relationship và metadata Hibernate
                        ↓
        Truy vấn/ghi đúng dữ liệu hiện có
~~~

Một ánh xạ “biên dịch được” vẫn có thể sai nếu đọc nhầm cột, chọn sai kiểu Java, không xử lý phần đệm `CHAR` hoặc cho rằng một bảng không có PK có thể được Hibernate quản lý như entity bình thường.

Cần phân biệt bốn tầng:

| Tầng | Ví dụ | Cần xác minh |
| --- | --- | --- |
| Cấu trúc vật lý | `"Legacy"."Order Archive"`, `"Amt_Cents"`, `CHAR(8)` | Tên chính xác, kiểu cột, nullability, constraint, index |
| Hợp đồng dữ liệu | `N` = New; ngày `20261201`; tiền lưu theo cent | Ý nghĩa, đơn vị, cách mã hóa, giá trị lịch sử |
| Mapping ORM | `@Table`, `@Column`, `@Convert`, `@EmbeddedId` | Entity có nạp/ghi đúng bảng, khóa và kiểu không |
| Quy tắc nghiệp vụ | Không đặt số tiền âm, không đổi mã đơn đã lưu | Kiểm tra giá trị và giao dịch phù hợp |

**Mục tiêu không chỉ là “Hibernate đọc được một hàng”.** Các thao tác ghi, quan hệ, tìm theo khóa, khóa đồng thời và hệ thống khác đang dùng database đó phải tiếp tục nhất quán.

## 2. Một schema giả định có tên và kiểu cũ

Giả sử hệ thống lưu đơn đặt hàng từ phần mềm cũ. Trong PostgreSQL, tên schema có chữ hoa, tên bảng và cột chứa khoảng trắng, một số cột dùng định dạng dữ liệu riêng.

~~~sql
CREATE SCHEMA "Legacy";

CREATE TABLE "Legacy"."Customer Registry" (
    "Cust No"      CHAR(8) PRIMARY KEY,
    "Display Name" VARCHAR(80) NOT NULL
);

CREATE TABLE "Legacy"."Order Archive" (
    "Order No"     BIGINT PRIMARY KEY,
    "Cust No"      CHAR(8) NOT NULL,
    "Amt_Cents"    BIGINT NOT NULL,
    "Status Flag"  CHAR(1) NOT NULL,
    "Planned Date" CHAR(8),
    "Created At"   TIMESTAMP WITHOUT TIME ZONE NOT NULL,

    CONSTRAINT "fk_order_customer"
        FOREIGN KEY ("Cust No")
        REFERENCES "Legacy"."Customer Registry"("Cust No"),

    CONSTRAINT "ck_order_status"
        CHECK ("Status Flag" IN ('N', 'C')),

    CONSTRAINT "ck_order_amount"
        CHECK ("Amt_Cents" >= 0)
);
~~~

Dữ liệu minh họa:

~~~sql
INSERT INTO "Legacy"."Customer Registry"
    ("Cust No", "Display Name")
VALUES ('CUST0001', 'Công ty An');

INSERT INTO "Legacy"."Order Archive"
    ("Order No", "Cust No", "Amt_Cents",
     "Status Flag", "Planned Date", "Created At")
VALUES
    (10001, 'CUST0001', 157500, 'N', '20261201',
     TIMESTAMP '2026-11-15 09:30:00');
~~~

Trong schema này:

- `"Order Archive"` và `"Cust No"` chứa khoảng trắng; PostgreSQL yêu cầu **double quotes** để giữ tên nguyên văn.
- `"Legacy"` có chữ hoa nên phải quote đúng khi truy cập dưới chế độ phân biệt identifier.
- `"Order No"` là ID do hệ thống cũ gán, không có khai báo identity/sequence.
- `"Amt_Cents"` lưu **đơn vị nhỏ nhất** bằng `BIGINT`, không phải `DECIMAL` tiền.
- `"Status Flag"` dùng các mã `N`/`C`.
- `"Planned Date"` lưu ngày theo chuỗi `yyyyMMdd`.
- `"Created At"` là timestamp **không kèm múi giờ**.
- `"Cust No"` là FK trỏ tới bảng khách hàng, không phải một object lồng trực tiếp trong ô.

Ta sẽ dùng ví dụ này để ánh xạ từ schema có sẵn sang mã Java có kiểu dữ liệu dễ hiểu.

## 3. Tên bảng, cột, schema và dấu trích dẫn identifier

Với JPA, `@Table` và `@Column` có thể chỉ định tên chính xác:

~~~java
@Entity
@Table(name = "orders")
public class OrderEntity {
    @Id
    @Column(name = "order_id")
    private Long id;
}
~~~

Với tên đặc biệt, cần phân biệt **chuỗi Java** và **tên SQL sau khi quote**. Để ánh xạ bảng `"Legacy"."Order Archive"` trong Hibernate:

~~~java
@Entity
@Table(
    name = "\"Order Archive\"",
    schema = "\"Legacy\""
)
public class LegacyOrder {
    @Id
    @Column(name = "\"Order No\"")
    private Long orderNumber;

    // ...
}
~~~

Một chuỗi Java `"\"Order Archive\""` có giá trị là `"Order Archive"` với **hai dấu double quote thực** được truyền vào metadata, nhờ đó Hibernate biết đây là identifier cần quote.

Với cột:

~~~java
@Column(name = "\"Status Flag\"")
private String statusCode;
~~~

SQL tương ứng sẽ tham chiếu dạng:

~~~sql
SELECT o."Order No", o."Status Flag"
FROM "Legacy"."Order Archive" o;
~~~

Trường hợp identifier đặc biệt thường cần quote:

| Tình huống | Ví dụ | Ghi chú |
| --- | --- | --- |
| Chứa khoảng trắng | `"Order Archive"` | Không thể để identifier trần theo cú pháp SQL thông thường |
| Trùng từ khóa SQL | `"Order"`, `"User"` | Danh sách từ khóa phụ thuộc dialect/database |
| Phân biệt hoa/thường | `"Cust No"`, `"MixedCase"` | Quote giữ cách viết trong PostgreSQL |
| Ký tự đặc biệt | `"net-amount"` | Có thể cần quote vì dấu gạch ngang được hiểu như toán tử |
| Tên chuẩn, không đặc biệt | `customer_id` | Thường không cần quote |

**Không phải mọi hệ quản trị dùng cùng cú pháp trích dẫn.** PostgreSQL và nhiều hệ thống SQL dùng double quotes, MySQL có thể dùng backticks, SQL Server có các kiểu quote riêng. Hibernate Dialect chịu trách nhiệm biểu diễn identifier đã được đánh dấu quoted theo database đang dùng.

### Tên entity Java khác tên bảng SQL

~~~java
@Entity(name = "ArchivedOrder")
@Table(name = "\"Order Archive\"", schema = "\"Legacy\"")
public class LegacyOrder {
}
~~~

Khi đó:

- `LegacyOrder` là tên class Java.
- `ArchivedOrder` là **tên entity** dùng trong JPQL/HQL.
- `"Legacy"."Order Archive"` là **tên bảng SQL**.

Truy vấn JPQL:

~~~java
List<LegacyOrder> orders = em.createQuery(
    "select o from ArchivedOrder o",
    LegacyOrder.class
).getResultList();
~~~

JPQL dùng entity name và thuộc tính Java; không viết trực tiếp `FROM "Legacy"."Order Archive"` trừ khi đang viết SQL native.

## 4. Quoting toàn cục và naming strategy

Hibernate có tùy chọn đặt tất cả identifier trong dấu quote, thường qua thuộc tính:

~~~properties
hibernate.globally_quoted_identifiers=true
~~~

Tùy phiên bản/cấu hình, Hibernate còn có cơ chế tự quote keyword:

~~~properties
hibernate.auto_quote_keyword=true
~~~

Hai lựa chọn không hoàn toàn giống nhau:

- **Global quoting:** yêu cầu quote toàn bộ identifier được Hibernate quản lý, kể cả những tên thông thường.
- **Auto-quote keywords:** hỗ trợ quote các tên được nhận diện là keyword theo metadata/dialect.
- **Quote tường minh** trong `@Table(name = "\"...\"")` và `@Column(name = "\"...\"")`: kiểm soát từng tên cụ thể.

Không nên bật global quoting chỉ vì có một bảng đặc biệt rồi mặc định mọi schema đang có sẽ tương thích. Ở database phân biệt tên khi quote, `customer` và `"Customer"` có thể là **hai identifier khác nhau**. Cấu hình quoting toàn cục có thể làm những tên vốn hoạt động theo quy tắc folding của database trở thành tên phải khớp cách viết nguyên văn.

### Naming strategy có thể thay đổi tên cuối cùng

Hibernate phân biệt **implicit naming strategy** và **physical naming strategy**:

- **Implicit:** đề xuất tên logic khi annotation không khai báo tên.
- **Physical:** có thể biến đổi tên logic thành tên vật lý cuối cùng, ví dụ `camelCase` → `snake_case`.

Spring Boot thường có quy ước đặt tên riêng theo cấu hình, nên `@Column(name="CustomerNo")` chưa đủ để kết luận SQL cuối cùng chắc chắn dùng đúng cách viết đó dưới mọi naming strategy.

Với database cũ, nên:

1. Khai báo tên bảng/cột thực sự bằng annotation.
2. Xem physical naming strategy đang được cấu hình.
3. Nếu cần giữ nguyên tên khai báo, dùng chiến lược tương ứng như `org.hibernate.boot.model.naming.PhysicalNamingStrategyStandardImpl` trong Hibernate, sau khi xem hệ quả với **toàn bộ mô hình**.
4. Quan sát SQL thực tế và xác nhận schema có đúng identifier.

Ví dụ cấu hình Spring Boot có thể cung cấp:

~~~properties
spring.jpa.hibernate.naming.physical-strategy=org.hibernate.boot.model.naming.PhysicalNamingStrategyStandardImpl
~~~

Đây là tùy chọn **Hibernate/Spring Boot**, không phải thuộc tính chuẩn Jakarta Persistence. Tên class và cách cấu hình cần phù hợp với phiên bản framework đang chạy.

## 5. Định danh `@Id` trong schema cũ: đừng áp đặt bộ sinh khóa

Trong schema ví dụ:

~~~sql
"Order No" BIGINT PRIMARY KEY
~~~

Cột không được khai báo `GENERATED ... AS IDENTITY` hoặc gắn sequence. Do đó entity có thể ánh xạ dạng ID **do ứng dụng hoặc hệ thống cũ cung cấp**:

~~~java
@Id
@Column(name = "\"Order No\"", nullable = false, updatable = false)
private Long orderNumber;
~~~

Constructor nghiệp vụ nhận ID:

~~~java
public LegacyOrder(Long orderNumber, CustomerRecord customer) {
    this.orderNumber = Objects.requireNonNull(orderNumber);
    this.customer = Objects.requireNonNull(customer);
}
~~~

Khi persist, ứng dụng phải cấp `orderNumber` hợp lệ và duy nhất trước khi gửi insert.

**Không tự thêm `@GeneratedValue(strategy = GenerationType.IDENTITY)` vào một cột không có cơ chế sinh ID**, chỉ vì các entity trong dự án mới thường dùng IDENTITY. Hibernate có thể gửi SQL trông đợi database tạo khóa nhưng database lại yêu cầu ứng dụng cung cấp nó.

Với schema khác, nếu ID được sinh bằng **sequence**, có thể ánh xạ bằng `@SequenceGenerator` / `@GeneratedValue(strategy=SEQUENCE)` với tên sequence, schema và `allocationSize` phù hợp. Nếu ID được sinh bằng **trigger, default hoặc stored procedure** cũ, cần tìm hiểu cơ chế provider lấy giá trị được sinh ra; không thể mặc định mọi trigger đều tương thích ngay với `GenerationType.IDENTITY`.

### ID không phải một giá trị có thể đổi tùy ý

Ngay cả khi schema dùng mã cũ làm PK, entity ID phải ổn định sau khi đối tượng đã persistent. Muốn sửa mã nghiệp vụ thường xuyên thì nên đặt mã ấy ở một cột khác có unique constraint nếu có thể cải tiến schema. Đổi PK trực tiếp trong managed entity có thể phá vỡ persistence context và quan hệ.

## 6. Map lớp khách hàng với khóa `CHAR(8)`

**`CustomerRecord.java`:**

~~~java
package com.example.legacy.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(
    name = "\"Customer Registry\"",
    schema = "\"Legacy\""
)
public class CustomerRecord {
    @Id
    @Column(name = "\"Cust No\"", length = 8, nullable = false)
    private String customerNumber;

    @Column(name = "\"Display Name\"", length = 80, nullable = false)
    private String displayName;

    protected CustomerRecord() {
    }

    public CustomerRecord(String customerNumber, String displayName) {
        this.customerNumber = customerNumber;
        this.displayName = displayName;
    }

    public String getCustomerNumber() {
        return customerNumber;
    }

    public String getDisplayName() {
        return displayName;
    }
}
~~~

`@Id` không cần `@GeneratedValue` vì mã khách hàng do dữ liệu cũ cấp.

**`CHAR(8)` khác `VARCHAR(8)`.** `CHAR` có ngữ nghĩa độ dài cố định; một số driver/database đệm khoảng trắng khi lưu/đọc. Ví dụ mã `"A123"` có thể được biểu diễn thành chuỗi có dấu cách ở cuối tùy truy vấn và driver.

Với khóa dùng để `JOIN`, so sánh hoặc cache, không tự áp dụng `trim()` một cách tùy tiện. Cần hiểu quy tắc so sánh `CHAR` của database, cách ứng dụng cũ cấp mã và liệu dấu cách có là dữ liệu hợp lệ không. Trong ví dụ, mã `CUST0001` đủ đúng 8 ký tự để tránh trường hợp đệm.

Một converter chuẩn JPA cũng **không được đảm bảo áp dụng cho identifier `@Id`**, vì vậy muốn xử lý ID legacy nên ưu tiên kiểu Java/JDBC được hỗ trợ, giữ nguyên dữ liệu khóa và chọn chiến lược mapping có chủ đích.

## 7. Ánh xạ FK mang tên đặc biệt

Bảng `"Order Archive"` có cột FK `"Cust No"` tham chiếu `"Customer Registry"."Cust No"`. Ở Java, đó có thể là một quan hệ object:

~~~java
@ManyToOne(fetch = FetchType.LAZY, optional = false)
@JoinColumn(
    name = "\"Cust No\"",
    referencedColumnName = "\"Cust No\"",
    nullable = false
)
private CustomerRecord customer;
~~~

Ý nghĩa:

| Metadata | Cột/bảng vật lý |
| --- | --- |
| Entity sở hữu | `"Legacy"."Order Archive"` |
| `joinColumns/name` của `@JoinColumn` | `"Order Archive"."Cust No"` |
| `referencedColumnName` | `"Customer Registry"."Cust No"` |
| Đối tượng Java | `CustomerRecord customer` |

Không cần tạo một `CustomerRecord` mới chỉ để mô phỏng giá trị FK. Khi đã nạp đúng `CustomerRecord` hoặc lấy managed reference phù hợp, Hibernate có thể lấy identifier của entity được tham chiếu để ghi FK.

Đoạn truy vấn:

~~~java
List<LegacyOrder> orders = em.createQuery(
    "select o from LegacyOrder o join fetch o.customer",
    LegacyOrder.class
).getResultList();
~~~

sẽ dùng metadata association để JOIN hai bảng đã quote đúng tên. Nếu entity được đặt `@Entity(name = "...")` riêng thì JPQL phải dùng entity name đó.

### FK tham chiếu cột không phải PK

Một số schema cũ lưu FK trỏ tới **mã nghiệp vụ unique**, thay vì khóa chính. `@JoinColumn(referencedColumnName = "...")` có thể trỏ tới cột được ánh xạ phù hợp và được Hibernate hỗ trợ cho quan hệ tham chiếu non-PK, nhưng đây là trường hợp cần kiểm tra kỹ tính duy nhất và hành vi provider.

Ví dụ ý tưởng:

~~~java
@ManyToOne(fetch = FetchType.LAZY)
@JoinColumn(
    name = "\"Customer External Code\"",
    referencedColumnName = "\"External Code\""
)
private CustomerRecord customer;
~~~

Phải đảm bảo `"External Code"` được ánh xạ và **duy nhất**, phù hợp độ dài/kiểu và thực sự có dữ liệu tương ứng. Không nên trỏ relationship tới một cột có nhiều hàng cùng giá trị rồi chờ Hibernate biết chọn object nào.

Nếu schema legacy có FK ghép, dùng `@JoinColumns` cùng các cặp tên tham chiếu, và kiểm tra khóa ghép của entity đích. Không cố gom hai khóa ngoại thành một thuộc tính kiểu chuỗi ghép bằng `@Column` nếu mô hình thực tế là quan hệ.

## 8. Dữ liệu cũ cần một lớp chuyển đổi kiểu có chủ đích

Ngay cả khi cột SQL là `BIGINT` hoặc `CHAR`, ứng dụng mới có thể muốn một kiểu Java diễn đạt ý nghĩa nghiệp vụ. Đây là lúc cân nhắc **`AttributeConverter<X,Y>`**.

Trong ví dụ:

| Cột cũ | Kiểu SQL | Ý nghĩa thật | Kiểu Java mong muốn |
| --- | --- | --- | --- |
| `"Amt_Cents"` | `BIGINT` | Số tiền theo đơn vị nhỏ nhất | `MoneyInCents` |
| `"Status Flag"` | `CHAR(1)` | `N` = New, `C` = Closed | `OrderStatus` |
| `"Planned Date"` | `CHAR(8)` | Ngày `yyyyMMdd` | `LocalDate` |
| `"Created At"` | `TIMESTAMP WITHOUT TIME ZONE` | Thời điểm địa phương | `LocalDateTime` |

Một converter thực hiện:

~~~java
Y convertToDatabaseColumn(X attribute);
X convertToEntityAttribute(Y dbData);
~~~

`X` là kiểu Java mong muốn, `Y` là kiểu cơ bản mà Hibernate/JDBC có thể ánh xạ xuống cột. Converter chỉ biến đổi **một thuộc tính sang một biểu diễn cột**, không tự xây dựng join, thêm bảng hoặc chia một object thành nhiều cột.

### Không dùng `columnDefinition` như một converter

~~~java
@Column(columnDefinition = "CHAR(8)")
private LocalDate plannedDate;
~~~

Đoạn này không tự xác định cách chuyển `LocalDate` thành chuỗi `20261201`. `columnDefinition` chủ yếu cung cấp mô tả DDL/kiểu cột khi sinh schema, còn việc chuyển dữ liệu cần mapping JDBC và/hoặc converter tương thích.

## 9. Converter cho trạng thái lưu bằng `CHAR(1)`

Đầu tiên định nghĩa enum nghiệp vụ:

**`OrderStatus.java`:**

~~~java
package com.example.legacy.domain;

public enum OrderStatus {
    NEW,
    CLOSED
}
~~~

Converter:

**`OrderStatusConverter.java`:**

~~~java
package com.example.legacy.persistence;

import com.example.legacy.domain.OrderStatus;
import jakarta.persistence.AttributeConverter;
import jakarta.persistence.Converter;

@Converter(autoApply = false)
public class OrderStatusConverter
        implements AttributeConverter<OrderStatus, String> {

    @Override
    public String convertToDatabaseColumn(OrderStatus value) {
        if (value == null) {
            return null;
        }

        return switch (value) {
            case NEW -> "N";
            case CLOSED -> "C";
        };
    }

    @Override
    public OrderStatus convertToEntityAttribute(String dbData) {
        if (dbData == null) {
            return null;
        }

        return switch (dbData.trim()) {
            case "N" -> OrderStatus.NEW;
            case "C" -> OrderStatus.CLOSED;
            default -> throw new IllegalArgumentException(
                "Unknown legacy order status: " + dbData
            );
        };
    }
}
~~~

Việc `trim()` trong chiều đọc ở đây chỉ được dùng **cho mã trạng thái một ký tự**, nơi phần đệm `CHAR` không mang ý nghĩa nghiệp vụ. Không nên sao chép cách xử lý này sang mọi cột, nhất là mã định danh hoặc dữ liệu mà khoảng trắng có ý nghĩa.

Trong entity:

~~~java
@Convert(converter = OrderStatusConverter.class)
@Column(name = "\"Status Flag\"", length = 1, nullable = false)
private OrderStatus status;
~~~

**Không đặt `@Enumerated` trên chính field đã dùng converter.** `@Enumerated(EnumType.STRING)` sẽ dự kiến lưu `NEW` và `CLOSED`, không tương thích mã cũ `N` và `C`. Chọn một cách ánh xạ: enum mapping chuẩn hoặc converter tùy biến.

## 10. Converter cho ngày lưu dưới dạng `yyyyMMdd`

Cột `"Planned Date" CHAR(8)` không phải kiểu SQL `DATE` thực sự. Ta có thể dùng converter ánh xạ thành `LocalDate`:

**`LegacyDateConverter.java`:**

~~~java
package com.example.legacy.persistence;

import jakarta.persistence.AttributeConverter;
import jakarta.persistence.Converter;
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;

@Converter(autoApply = false)
public class LegacyDateConverter
        implements AttributeConverter<LocalDate, String> {

    private static final DateTimeFormatter FORMAT =
        DateTimeFormatter.BASIC_ISO_DATE;

    @Override
    public String convertToDatabaseColumn(LocalDate value) {
        return value == null ? null : FORMAT.format(value);
    }

    @Override
    public LocalDate convertToEntityAttribute(String dbData) {
        if (dbData == null) {
            return null;
        }

        String normalized = dbData.trim();
        if (normalized.isEmpty()) {
            return null; // Chỉ khi nghiệp vụ quy định chuỗi trống = thiếu ngày.
        }

        return LocalDate.parse(normalized, FORMAT);
    }
}
~~~

Trong entity:

~~~java
@Convert(converter = LegacyDateConverter.class)
@Column(name = "\"Planned Date\"", length = 8)
private LocalDate plannedDate;
~~~

`DateTimeFormatter.BASIC_ISO_DATE` xử lý ví dụ `20261201`. Nếu database thực tế có giá trị `00000000`, `99999999` hay chuỗi trống mang ý nghĩa đặc biệt, cần bổ sung quy tắc xử lý **theo tài liệu nghiệp vụ**, không tự đoán đó là ngày hợp lệ.

**Không thêm `@Temporal` cho `LocalDate` trong ví dụ.** `@Temporal` thuộc kiểu ngày giờ legacy như `java.util.Date`/`Calendar`; thuộc tính có `@Temporal` cũng không thuộc nhóm áp dụng converter bình thường theo chuẩn JPA.

### Giới hạn truy vấn ngày dạng chuỗi

Nếu cột lưu đúng `yyyyMMdd` với ngày hợp lệ và độ dài đồng nhất, so sánh chuỗi theo thứ tự từ điển có thể cùng thứ tự thời gian ở một số truy vấn; tuy nhiên database vẫn xem đó là `CHAR`, không phải `DATE`. Các phép cộng ngày, múi giờ, index trên biểu thức chuyển đổi và kiểm tra ngày hợp lệ có thể khó hơn.

Nếu có quyền cải tiến schema, chuyển dần sang cột `DATE` thực sự thường là lựa chọn lâu dài. Nếu chưa thể đổi, converter giúp domain dùng kiểu Java đúng mà không phá định dạng cũ.

## 11. Tiền lưu dưới dạng số nguyên đơn vị nhỏ nhất

Cột `"Amt_Cents" BIGINT` lưu lượng tiền theo cent. Không thể đọc số `157500` rồi hiển thị như `157500.00` đơn vị chính mà không tính đến đơn vị lưu.

Một value object cho tiền theo cent:

**`MoneyInCents.java`:**

~~~java
package com.example.legacy.domain;

import java.math.BigDecimal;
import java.util.Objects;

public final class MoneyInCents {
    private final long cents;

    private MoneyInCents(long cents) {
        if (cents < 0) {
            throw new IllegalArgumentException("Amount cannot be negative");
        }
        this.cents = cents;
    }

    public static MoneyInCents ofCents(long cents) {
        return new MoneyInCents(cents);
    }

    public long cents() {
        return cents;
    }

    public BigDecimal toMajorUnits() {
        return BigDecimal.valueOf(cents, 2);
    }

    @Override
    public boolean equals(Object other) {
        return other instanceof MoneyInCents that
            && cents == that.cents;
    }

    @Override
    public int hashCode() {
        return Long.hashCode(cents);
    }

    @Override
    public String toString() {
        return Objects.toString(toMajorUnits());
    }
}
~~~

Đoạn này **giả định đơn vị nhỏ nhất có 2 chữ số thập phân**. Đây không phải quy tắc áp dụng cho tất cả tiền tệ; nếu hệ thống dùng VND không có cent hoặc một cột lưu theo đơn vị khác, hãy đặt tên value object và phép đổi cho đúng hợp đồng dữ liệu.

Converter:

**`MoneyInCentsConverter.java`:**

~~~java
package com.example.legacy.persistence;

import com.example.legacy.domain.MoneyInCents;
import jakarta.persistence.AttributeConverter;
import jakarta.persistence.Converter;

@Converter(autoApply = false)
public class MoneyInCentsConverter
        implements AttributeConverter<MoneyInCents, Long> {

    @Override
    public Long convertToDatabaseColumn(MoneyInCents amount) {
        return amount == null ? null : amount.cents();
    }

    @Override
    public MoneyInCents convertToEntityAttribute(Long stored) {
        return stored == null ? null : MoneyInCents.ofCents(stored);
    }
}
~~~

Trong entity:

~~~java
@Convert(converter = MoneyInCentsConverter.class)
@Column(name = "\"Amt_Cents\"", nullable = false)
private MoneyInCents amount;
~~~

`AttributeConverter<MoneyInCents, Long>` hợp với cột `BIGINT` trong ví dụ. Nếu cột cũ là `DECIMAL(19,0)` hoặc Oracle `NUMBER(19,0)`, kiểu JDBC và kiểu `Y` cần được lựa chọn lại sau khi kiểm tra driver và metadata. Đừng mặc định mọi loại cột số không có phần thập phân đều nên đọc bằng `Long` nếu giá trị có thể vượt phạm vi số nguyên 64-bit.

## 12. Entity `LegacyOrder` kết hợp các ánh xạ

Sau khi có `CustomerRecord` và các converter, ta viết entity ánh xạ toàn bộ bảng đơn hàng.

**`LegacyOrder.java`:**

~~~java
package com.example.legacy.domain;

import com.example.legacy.persistence.LegacyDateConverter;
import com.example.legacy.persistence.MoneyInCentsConverter;
import com.example.legacy.persistence.OrderStatusConverter;
import jakarta.persistence.Column;
import jakarta.persistence.Convert;
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.Table;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.util.Objects;

@Entity
@Table(
    name = "\"Order Archive\"",
    schema = "\"Legacy\""
)
public class LegacyOrder {
    @Id
    @Column(name = "\"Order No\"", nullable = false, updatable = false)
    private Long orderNumber;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(
        name = "\"Cust No\"",
        referencedColumnName = "\"Cust No\"",
        nullable = false
    )
    private CustomerRecord customer;

    @Convert(converter = MoneyInCentsConverter.class)
    @Column(name = "\"Amt_Cents\"", nullable = false)
    private MoneyInCents amount;

    @Convert(converter = OrderStatusConverter.class)
    @Column(name = "\"Status Flag\"", nullable = false, length = 1)
    private OrderStatus status;

    @Convert(converter = LegacyDateConverter.class)
    @Column(name = "\"Planned Date\"", length = 8)
    private LocalDate plannedDate;

    @Column(name = "\"Created At\"", nullable = false)
    private LocalDateTime createdAt;

    protected LegacyOrder() {
    }

    public LegacyOrder(
        Long orderNumber,
        CustomerRecord customer,
        MoneyInCents amount,
        LocalDate plannedDate,
        LocalDateTime createdAt
    ) {
        this.orderNumber = Objects.requireNonNull(orderNumber);
        this.customer = Objects.requireNonNull(customer);
        this.amount = Objects.requireNonNull(amount);
        this.plannedDate = plannedDate;
        this.createdAt = Objects.requireNonNull(createdAt);
        this.status = OrderStatus.NEW;
    }

    public Long getOrderNumber() {
        return orderNumber;
    }

    public CustomerRecord getCustomer() {
        return customer;
    }

    public MoneyInCents getAmount() {
        return amount;
    }

    public OrderStatus getStatus() {
        return status;
    }

    public LocalDate getPlannedDate() {
        return plannedDate;
    }

    public LocalDateTime getCreatedAt() {
        return createdAt;
    }

    public void close() {
        this.status = OrderStatus.CLOSED;
    }
}
~~~

Lớp giữ tên Java dễ đọc, trong khi annotation trỏ tới những tên SQL legacy có dấu quote. Trong Java:

~~~java
LegacyOrder order = em.find(LegacyOrder.class, 10001L);

System.out.println(order.getStatus()); // NEW
System.out.println(order.getAmount().toMajorUnits()); // 1575.00
System.out.println(order.getPlannedDate()); // 2026-12-01
~~~

Đoạn này giả định hàng minh họa tồn tại, ứng dụng đã cấu hình factory hợp lệ và mapping của hai entity/converter được đăng ký.

Ở database, dữ liệu cũ vẫn giữ:

~~~text
"Order No"     = 10001
"Amt_Cents"    = 157500
"Status Flag"  = N
"Planned Date" = 20261201
~~~

**Một mô hình domain rõ nghĩa không bắt buộc database cũ phải được đổi tên ngay.** Tên Java và tên SQL là hai tầng được ánh xạ thông qua metadata.

## 13. Phân biệt kiểu Java, kiểu JDBC và kiểu SQL thực tế

Legacy mapping dễ sai khi tưởng ba tầng kiểu dữ liệu luôn giống nhau:

~~~text
Kiểu Java         →  Java/JDBC binding        →  Cột SQL thực tế
OrderStatus       →  String("N")              →  CHAR(1)
LocalDate         →  String("20261201")       →  CHAR(8)
MoneyInCents      →  Long(157500)             →  BIGINT
LocalDateTime     →  JDBC timestamp          →  TIMESTAMP WITHOUT TIME ZONE
~~~

`@Column(columnDefinition = "...")` không tự thay thế type resolution hay converter. Nếu driver trả kiểu lạ, cần xem mapping type và API Hibernate tương ứng.

### Một số cột legacy thường gặp

| Cột SQL hoặc kiểu dữ liệu | Rủi ro khi map mặc định | Hướng xử lý |
| --- | --- | --- |
| `CHAR(n)` | Giá trị có thể được đệm khoảng trắng | Xác minh cách driver trả chuỗi và ngữ nghĩa khoảng trắng |
| `NUMBER(p,0)` / `NUMERIC(p,0)` | Chuyển sang `Long` có thể tràn với precision lớn | Xem phạm vi dữ liệu, cân nhắc `BigDecimal` hoặc kiểu số phù hợp |
| `DECIMAL(p,s)` | Dùng `double` mất độ chính xác thập phân | Dùng `BigDecimal` và precision/scale đúng |
| `SMALLINT`/`TINYINT` làm trạng thái | Không phản ánh ý nghĩa nghiệp vụ | Converter mã trạng thái hoặc enum mapping phù hợp |
| `CHAR(1)` dạng `Y/N`, `0/1` | Không phải boolean SQL chuẩn | Converter boolean ↔ mã legacy; tránh đảo nghĩa |
| `DATE` lưu cả giờ ở một số DB | Kiểu Java có thể mất phần thời gian | Kiểm tra hành vi driver và loại dữ liệu thật |
| `TIMESTAMP WITHOUT TIME ZONE` | Dễ nhầm với instant UTC | Dùng kiểu phù hợp, định nghĩa rõ timezone nghiệp vụ |
| `VARCHAR` lưu ngày `yyyyMMdd` | Không phải ngày SQL | Converter, xử lý giá trị sentinel và dữ liệu sai |
| `BLOB`/`CLOB`/`LONGTEXT` | Tải dữ liệu lớn, khác biệt driver | `@Lob`, streaming/API riêng khi cần |
| `BINARY`/`VARBINARY` | Chuỗi byte không phải text UTF-8 | `byte[]` hoặc mapping kiểu chuyên biệt |
| `UUID` lưu chuỗi/binary | Kiểu cột có thể không phải native UUID | Dùng converter/type mapping phù hợp và thống nhất encoding |
| `JSON`/`JSONB` | Mapping JDBC khác chuỗi text thông thường | Dùng Hibernate JSON type phù hợp phiên bản hoặc converter khi chỉ cần text |

**Không đoán từ tên cột.** Cột `PRICE` có thể lưu cents, phần nghìn, đơn vị tiền, hoặc một giá trị quy ước cũ. Cần biết dữ liệu và hợp đồng nghiệp vụ, không chỉ xem kiểu `BIGINT`.

## 14. Kiểu SQL đặc thù và API Hibernate 6

Với Hibernate 6, ngoài `AttributeConverter` còn có những annotation/cơ chế kiểu dữ liệu chuyên biệt như `@JdbcTypeCode`, `@JdbcType`, `@JavaType` và hệ thống basic type của Hibernate.

Ví dụ một thuộc tính cần ánh xạ qua JDBC type đặc thù:

~~~java
import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.type.SqlTypes;

@JdbcTypeCode(SqlTypes.JSON)
@Column(name = "metadata_json")
private Map<String, Object> metadata;
~~~

Đây là ví dụ **Hibernate-specific**, yêu cầu phiên bản Hibernate, JDBC driver và SQL dialect hỗ trợ kiểu JSON tương ứng. Cột ở database cũ có thể là `TEXT` chứa JSON, không phải `JSONB`; áp đặt `SqlTypes.JSON` mà không xét kiểu cột thực tế có thể tạo lỗi validate/binding.

Với cột ký tự kiểu cố định, Hibernate còn có tùy chọn chọn JDBC type code như `SqlTypes.CHAR` trong những mapping phù hợp. Tuy nhiên, việc sử dụng `@JdbcTypeCode` chỉ định cách bind/extract qua JDBC, **không tự dọn khoảng trắng, giải mã trạng thái hay kiểm tra dữ liệu nghiệp vụ**.

### Khi nào dùng converter, khi nào dùng custom type?

| Nhu cầu | Cơ chế thường phù hợp |
| --- | --- |
| `N/C` thành enum `OrderStatus` | `AttributeConverter<OrderStatus,String>` |
| `yyyyMMdd` trong `CHAR(8)` thành `LocalDate` | `AttributeConverter<LocalDate,String>` |
| Wrapper một giá trị `BIGINT` | `AttributeConverter<ValueObject,Long>` |
| Chỉ định JDBC type trong Hibernate 6 | `@JdbcTypeCode` hoặc basic type mapping tương ứng |
| Kiểu SQL đặc thù, nhiều thao tác bind/extract phức tạp | API type của Hibernate được thiết kế cho phiên bản đang dùng |
| Một object cần hai cột độc lập | `@Embeddable` hoặc nhiều thuộc tính mapped |
| Một entity nằm trên nhiều bảng | `@SecondaryTable` hoặc entity association |
| Cần tái cấu trúc dữ liệu, join hoặc aggregation | View, native SQL hoặc mô hình data access khác |

Trong codebase Hibernate cũ có thể gặp `UserType`, `BasicType` hoặc thư viện custom types. **API của các kiểu này thay đổi đáng kể giữa các phiên bản Hibernate lớn**. Không nên sao chép máy móc một `UserType` viết cho Hibernate 5 vào Hibernate 6; cần chọn API đúng phiên bản và kiểm tra cách bind/extract của driver.

## 15. Ngày giờ cũ và vấn đề múi giờ

Một cột `TIMESTAMP WITHOUT TIME ZONE` của PostgreSQL lưu ngày giờ theo lịch, **không gắn offset/zone**. Ánh xạ vào `LocalDateTime` phù hợp khi ứng dụng muốn giữ đúng số giờ/phút đã được lưu mà không khẳng định đó là một khoảnh khắc tuyệt đối trên trục thời gian.

Ví dụ:

~~~java
@Column(name = "\"Created At\"", nullable = false)
private LocalDateTime createdAt;
~~~

Nếu giá trị `2026-11-15 09:30:00` thực ra luôn được hệ thống cũ hiểu là giờ Hà Nội hoặc UTC, cần tài liệu hóa quy ước đó. Chỉ đổi field Java thành `Instant` chưa chắc chuyển đổi đúng; JDBC, timezone mặc định của session và kiểu SQL có thể dẫn đến lệch giờ.

Bảng quyết định đơn giản:

| Dữ liệu cũ | Ý nghĩa thật | Kiểu Java nên cân nhắc |
| --- | --- | --- |
| `DATE` chỉ ngày | Ngày trên lịch, không có giờ | `LocalDate` |
| `TIMESTAMP WITHOUT TIME ZONE` là giờ địa phương | Ngày và giờ không kèm zone | `LocalDateTime` |
| Timestamp lưu mốc thời gian tuyệt đối | Một thời điểm trên timeline | `Instant`/`OffsetDateTime` với mapping và DB type phù hợp |
| Số epoch seconds/millis | Thời gian mã hóa bằng số | Converter và xác định chính xác **đơn vị** |
| Chuỗi `yyyyMMdd` | Ngày ở định dạng cũ | Converter sang `LocalDate` |

**Epoch seconds và epoch milliseconds khác nhau 1.000 lần.** Một cột cũ kiểu `BIGINT` chứa timestamp nhưng không ghi đơn vị là nguồn lỗi phổ biến; phải xem tài liệu, dữ liệu mẫu và logic của hệ thống gốc trước khi triển khai converter.

## 16. Khóa ghép trong bảng cũ

Schema legacy thường có khóa chính gồm hai hoặc nhiều cột, ví dụ bảng chi tiết đơn hàng:

~~~sql
CREATE TABLE "Legacy"."Order Item" (
    "Order No" BIGINT NOT NULL,
    "Line No"  INTEGER NOT NULL,
    "SKU"      VARCHAR(32) NOT NULL,
    "Qty"      INTEGER NOT NULL,

    PRIMARY KEY ("Order No", "Line No"),
    FOREIGN KEY ("Order No")
        REFERENCES "Legacy"."Order Archive"("Order No")
);
~~~

Trong Java, một khóa ghép cần được khai báo chính xác. Có thể dùng `@EmbeddedId`:

**`OrderItemId.java`:**

~~~java
package com.example.legacy.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Embeddable;
import java.io.Serializable;
import java.util.Objects;

@Embeddable
public class OrderItemId implements Serializable {
    @Column(name = "\"Order No\"")
    private Long orderNumber;

    @Column(name = "\"Line No\"")
    private Integer lineNumber;

    protected OrderItemId() {
    }

    public OrderItemId(Long orderNumber, Integer lineNumber) {
        this.orderNumber = Objects.requireNonNull(orderNumber);
        this.lineNumber = Objects.requireNonNull(lineNumber);
    }

    public Long getOrderNumber() {
        return orderNumber;
    }

    public Integer getLineNumber() {
        return lineNumber;
    }

    @Override
    public boolean equals(Object other) {
        if (this == other) {
            return true;
        }
        if (!(other instanceof OrderItemId that)) {
            return false;
        }
        return Objects.equals(orderNumber, that.orderNumber)
            && Objects.equals(lineNumber, that.lineNumber);
    }

    @Override
    public int hashCode() {
        return Objects.hash(orderNumber, lineNumber);
    }
}
~~~

**`OrderItem.java`:**

~~~java
package com.example.legacy.domain;

import jakarta.persistence.Column;
import jakarta.persistence.EmbeddedId;
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.MapsId;
import jakarta.persistence.Table;

@Entity
@Table(name = "\"Order Item\"", schema = "\"Legacy\"")
public class OrderItem {
    @EmbeddedId
    private OrderItemId id;

    @MapsId("orderNumber")
    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(
        name = "\"Order No\"",
        referencedColumnName = "\"Order No\""
    )
    private LegacyOrder order;

    @Column(name = "\"SKU\"", nullable = false, length = 32)
    private String sku;

    @Column(name = "\"Qty\"", nullable = false)
    private Integer quantity;

    protected OrderItem() {
    }

    public OrderItem(
        LegacyOrder order,
        int lineNumber,
        String sku,
        int quantity
    ) {
        this.order = order;
        this.id = new OrderItemId(order.getOrderNumber(), lineNumber);
        this.sku = sku;
        this.quantity = quantity;
    }
}
~~~

`@MapsId("orderNumber")` cho biết khóa FK của quan hệ `order` đồng thời cung cấp **thành phần `orderNumber` của khóa ghép**. Đây là derived identity; không cần tự tạo một quan hệ độc lập khác với cột `"Order No"`.

Các chú ý:

- `OrderItemId` là value object định danh, cần `Serializable` và `equals/hashCode` phù hợp.
- Tên field `orderNumber` trong `@MapsId` phải khớp thuộc tính của `OrderItemId`.
- Hai cột `"Order No"` và `"Line No"` cùng xác định duy nhất một dòng.
- Không đổi một thành phần khóa sau khi entity đã persistent.
- Nếu mapping FK ghép tới hai cột của entity cha, có thể cần `@JoinColumns` và `@MapsId` theo cấu trúc khóa tương ứng.

**Đừng thêm `@GeneratedValue` vào `"Line No"`** chỉ vì muốn Hibernate tự tăng thứ tự chi tiết. Cơ chế cấp số dòng trong từng đơn có thể cần quy tắc nghiệp vụ, khóa hoặc transaction riêng để tránh xung đột khi nhiều người cùng thêm chi tiết.

## 17. Bảng không có khóa chính: giới hạn nền tảng của JPA entity

Một số hệ thống cũ có bảng như:

~~~sql
CREATE TABLE "Legacy"."Import Log" (
    "File Name" VARCHAR(255),
    "Message"   TEXT,
    "Logged At" TIMESTAMP
);
~~~

Bảng không có `PRIMARY KEY` và có thể có nhiều hàng giống hệt nhau. JPA entity **cần một identifier** để phân biệt các instance theo dữ liệu. Nếu không có khóa ổn định, Hibernate không thể quản lý đáng tin cậy một hàng cụ thể để cập nhật hoặc xóa.

Những cách xử lý phù hợp tùy quyền thay đổi schema:

1. **Nếu được phép cải tiến database:** thêm cột ID ổn định (chẳng hạn identity/sequence) và migration dữ liệu; tạo primary key thật.
2. **Nếu một tập cột thực sự duy nhất và bất biến:** xem xét khóa ghép bằng `@EmbeddedId`/`@IdClass`, đồng thời nên tạo constraint unique/PK ở database.
3. **Nếu dữ liệu chỉ dùng để đọc và không có ID chắc chắn:** dùng native SQL, JDBC, projection/DTO hoặc báo cáo thay vì ép thành managed entity có identity giả.
4. **Nếu cần trình bày một view:** ánh xạ read-only khi view có khóa ổn định, hoặc dùng DTO nếu view không có identifier.

**Không dùng `row_number() over (...)` làm ID tùy tiện cho một entity lâu dài** nếu thứ tự hàng có thể đổi giữa các lần truy vấn. Số thứ tự động không đảm bảo cùng một bản ghi giữ cùng identifier; cache và persistence context có thể nhận diện sai hàng.

Một bảng “trông như có khóa” vì hiện tại chưa có dữ liệu trùng cũng không đồng nghĩa có bảo đảm uniqueness trong tương lai. Chất lượng mapping phụ thuộc **ràng buộc và hành vi dữ liệu thực tế**, không phải may mắn của một lần chạy.

## 18. Một entity trải trên hai bảng: `@SecondaryTable`

Một schema legacy có thể tách trường hiếm dùng sang bảng bổ sung nhưng vẫn lưu theo **cùng khóa chính**:

~~~sql
CREATE TABLE "Legacy"."Order Extra" (
    "Order No" BIGINT PRIMARY KEY
        REFERENCES "Legacy"."Order Archive"("Order No"),
    "Operator Note" VARCHAR(500)
);
~~~

Nếu `Order Extra` chỉ bổ sung dữ liệu 1:1 cho `LegacyOrder`, JPA hỗ trợ `@SecondaryTable`:

~~~java
@Entity
@Table(
    name = "\"Order Archive\"",
    schema = "\"Legacy\""
)
@SecondaryTable(
    name = "\"Order Extra\"",
    schema = "\"Legacy\"",
    pkJoinColumns = @PrimaryKeyJoinColumn(
        name = "\"Order No\"",
        referencedColumnName = "\"Order No\""
    )
)
public class LegacyOrder {
    @Id
    @Column(name = "\"Order No\"")
    private Long orderNumber;

    @Column(
        table = "\"Order Extra\"",
        name = "\"Operator Note\"",
        length = 500
    )
    private String operatorNote;

    // Các field khác ...
}
~~~

Đoạn code là phần **minh họa annotation** cho entity đã định nghĩa ở trên; khi triển khai thật cần nhập các import từ `jakarta.persistence` và hợp nhất annotation vào **cùng một class**, không khai báo hai class `LegacyOrder` riêng.

`@SecondaryTable` cho phép field của **cùng một entity** nằm ở hai bảng có liên kết khóa chính. Nó khác `@OneToOne`:

| Trường hợp | `@SecondaryTable` | `@OneToOne` |
| --- | --- | --- |
| Hai bảng biểu diễn cùng một entity identity | Phù hợp | Có thể nhưng sẽ tạo hai entity |
| Bảng phụ có vòng đời nghiệp vụ riêng | Thường không phù hợp | Thường rõ hơn |
| Muốn truy vấn/đổi trạng thái bản ghi phụ độc lập | Hạn chế | Thuận tiện hơn |
| Bảng phụ dùng cùng PK với bảng chính | Phù hợp | Có thể dùng shared PK |
| Quan hệ 1:N | Không | Dùng `@OneToMany` hoặc entity con |

Nếu bảng phụ không bảo đảm một hàng cho mỗi khóa chính, có khóa khác hoặc có thể có nhiều hàng, `@SecondaryTable` không phải lựa chọn đúng. Nếu bảng phụ có thể thiếu hàng, phải xem chế độ optional, cách ghi/update và hành vi phiên bản Hibernate; không mặc định ghi field ở bảng phụ luôn hoạt động như một cột cùng bảng.

## 19. View, bảng tổng hợp và quyền chỉ đọc

Một view có thể ghép dữ liệu từ nhiều bảng nhưng ứng dụng chỉ cần đọc:

~~~sql
CREATE VIEW "Legacy"."Order Summary" AS
SELECT o."Order No" AS "Order No",
       c."Display Name" AS "Customer Name",
       o."Amt_Cents" AS "Amt_Cents"
FROM "Legacy"."Order Archive" o
JOIN "Legacy"."Customer Registry" c
  ON c."Cust No" = o."Cust No";
~~~

Nếu mỗi hàng view có một **identifier ổn định, duy nhất** (ở ví dụ `"Order No"`), Hibernate có thể map view như entity đọc dữ liệu:

~~~java
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import org.hibernate.annotations.Immutable;

@Entity
@Immutable
@Table(
    name = "\"Order Summary\"",
    schema = "\"Legacy\""
)
public class OrderSummary {
    @Id
    @Column(name = "\"Order No\"")
    private Long orderNumber;

    @Column(name = "\"Customer Name\"")
    private String customerName;

    @Column(name = "\"Amt_Cents\"")
    private Long amountCents;

    protected OrderSummary() {
    }
}
~~~

`@Immutable` là annotation riêng của Hibernate, biểu thị entity không được theo dõi để cập nhật các thuộc tính qua dirty checking theo cách thông thường. Nó hỗ trợ **ý định đọc-only**, nhưng quyền ghi thực sự còn do database, cấu hình và đường thao tác khác quyết định; đừng coi annotation là hàng rào bảo mật cho mọi lệnh SQL.

Với view phức tạp, Hibernate còn có các cơ chế như `@Subselect` để định nghĩa entity từ truy vấn SQL, thường kết hợp `@Immutable`. Đây là **cơ chế riêng của Hibernate**, yêu cầu một identifier đáng tin cậy và phải cân nhắc đồng bộ dữ liệu/caching. Không nên cố ánh xạ view tổng hợp có nhiều hàng trùng khóa làm một managed entity bình thường.

### Khi nào ưu tiên DTO thay entity?

Nếu dữ liệu dùng để lập báo cáo tổng hợp, không cần cập nhật và không có khóa ổn định, projection/DTO của native query hoặc `JdbcTemplate` thường rõ ràng hơn. Ví dụ “tổng số đơn theo tháng” có thể không có một entity ID tự nhiên. Dùng một DTO cho kết quả là đúng về mô hình, thay vì phát minh PK giả để thỏa mãn `@Id`.

## 20. Cột tính toán, công thức và hàm SQL đặc thù

Schema cũ đôi khi không có cột được mong muốn, nhưng có thể tính ra dữ liệu bằng biểu thức SQL. Hibernate hỗ trợ `@Formula`:

~~~java
import org.hibernate.annotations.Formula;

@Formula("\"Amt_Cents\" / 100.0")
private BigDecimal amountInMajorUnits;
~~~

Đây là ví dụ **Hibernate-specific**, thường mang tính **read-only**: giá trị được tính khi truy vấn, không phải một cột writable. Biểu thức phải phù hợp dialect/database; cách quote và phép chia số nguyên/số thập phân có thể thay đổi giữa hệ quản trị. Trong nhiều trường hợp, chuyển đổi ở domain bằng `MoneyInCents.toMajorUnits()` vẫn dễ hiểu hơn.

Nếu database yêu cầu **hàm SQL khi đọc/ghi cùng một cột**, Hibernate có `@ColumnTransformer`. Ý tưởng:

~~~java
@ColumnTransformer(
    read = "decrypt(data_ciphertext)",
    write = "encrypt(?)"
)
private String sensitiveData;
~~~

Đây là **cú pháp minh họa**, không phải lời khuyên tự triển khai bảo mật. Các hàm `encrypt/decrypt` phụ thuộc database và cơ chế quản lý khóa; cú pháp, quyền truy cập và xử lý dữ liệu nhạy cảm phải được thiết kế riêng. Một expression viết phải tuân thủ quy tắc placeholder của Hibernate (thường có đúng một dấu `?` cho giá trị ghi).

Phân biệt:

- `@Formula`: một **biểu thức đọc** không tương đương cột writable độc lập.
- `@ColumnTransformer`: biến đổi biểu thức SQL khi đọc/ghi một thuộc tính.
- `AttributeConverter`: chuyển đổi giá trị **ở phía Java** trước khi bind và sau khi extract JDBC.
- Database **generated column**: cột vật lý/ảo do database tính, phải map theo quyền ghi/thời điểm tạo phù hợp.

Không chọn `@Formula` chỉ vì có một biểu thức phức tạp; nếu nó đắt hoặc phụ thuộc nhiều bảng, projection và query riêng có thể dễ kiểm soát hiệu năng hơn.

## 21. Cột được database quản lý: default, trigger và generated value

Một schema cũ có thể tự cấp timestamp hoặc trạng thái qua default:

~~~sql
ALTER TABLE "Legacy"."Order Archive"
ALTER COLUMN "Created At"
SET DEFAULT CURRENT_TIMESTAMP;
~~~

Với:

~~~java
@Column(name = "\"Created At\"", nullable = false)
private LocalDateTime createdAt;
~~~

Hibernate có thể gửi giá trị thuộc tính trong `INSERT`. Nếu Java để `null` và Hibernate vẫn chèn cột với `NULL`, default của database **không nhất thiết chạy**, vì nhiều DB chỉ áp dụng default khi cột bị bỏ khỏi `INSERT` hoặc dùng từ khóa `DEFAULT`.

Tùy nhu cầu, có thể xét:

- Cấp giá trị ở Java khi tạo entity.
- Dùng `@Column(insertable = false, updatable = false)` cho cột do DB quản lý, đồng thời có cách nạp lại giá trị sau insert.
- Sử dụng cơ chế generated property của Hibernate cho phiên bản phù hợp.
- Xem schema thực tế có trigger, stored procedure hay default đặc biệt không.

Không tự đặt `insertable=false` cho mọi cột legacy để “tránh lỗi”. Làm vậy có thể khiến Hibernate không ghi giá trị cần thiết, dẫn đến dữ liệu thiếu hoặc hành vi khác ứng dụng cũ.

### Dữ liệu do trigger thay đổi

Một trigger có thể tự động sửa giá, trạng thái, timestamp hoặc một mã định danh. Lúc đó object Java sau `persist`/`flush` có thể chưa biết giá trị cuối cùng trong database nếu mapping không cấu hình nạp giá trị sinh. Cần xem cách Hibernate đồng bộ lại trạng thái của entity, yêu cầu `refresh()` khi phù hợp, và giới hạn của việc dùng trigger trên cột định danh/phiên bản.

## 22. Đọc-only và quyền ghi từng cột

Một số cột do ứng dụng cũ hoặc database quản lý và ứng dụng mới chỉ được đọc. Annotation JPA hỗ trợ:

~~~java
@Column(
    name = "\"External Audit Code\"",
    insertable = false,
    updatable = false
)
private String externalAuditCode;
~~~

Ý nghĩa:

- `insertable = false`: Hibernate không đưa cột vào SQL `INSERT` do mapping này.
- `updatable = false`: Hibernate không đưa cột vào SQL `UPDATE` do mapping này.

Đây là **quy tắc sinh SQL của ORM cho thuộc tính**, không phải quyền truy cập database. Một ứng dụng khác hoặc native SQL có quyền vẫn có thể thay cột đó.

Nếu cùng một FK được ánh xạ hai lần, ví dụ vừa có field `customerNo` vừa có association `CustomerRecord customer`, cần xác định **một đường ghi** và đánh dấu đường còn lại đọc-only khi phù hợp:

~~~java
@ManyToOne(fetch = FetchType.LAZY)
@JoinColumn(name = "\"Cust No\"")
private CustomerRecord customer;

@Column(
    name = "\"Cust No\"",
    insertable = false,
    updatable = false
)
private String customerNo;
~~~

Đây là ví dụ một kiểu mapping hai góc nhìn cho cùng FK; nó tăng nguy cơ trạng thái Java không đồng bộ nếu app dựa trên cả hai field. **Chỉ sử dụng khi có lý do cụ thể**, và quản lý cách truy cập/nạp lại nhất quán.

## 23. Soft delete, cờ hoạt động và dữ liệu lịch sử

Schema legacy đôi khi không xóa bản ghi thật mà đặt cột:

~~~text
"Deleted Flag" CHAR(1): 'Y' / 'N'
~~~

Nếu ứng dụng mới dùng Hibernate, có thể:

1. Map cờ này thành một thuộc tính bình thường qua converter.
2. Dùng điều kiện truy vấn để loại các hàng đã xóa logic.
3. Cân nhắc cơ chế soft delete riêng của Hibernate nếu phiên bản và schema tương thích.
4. Giữ riêng các thao tác xóa/chuyển trạng thái trong service để tránh xóa vật lý nhầm.

Một số phiên bản Hibernate có các annotation như `@SQLDelete`, `@SQLRestriction` hoặc `@SoftDelete` (khả năng và cú pháp thay đổi theo phiên bản; `@SoftDelete` có từ Hibernate 6.4). Không nên giả định mọi annotation đó đều hoạt động với **cột kiểu `Y/N` và tên có khoảng trắng** theo mặc định.

Ví dụ về **ý tưởng**, không phải entity mapping hoàn chỉnh:

~~~sql
UPDATE "Legacy"."Order Archive"
SET "Deleted Flag" = 'Y'
WHERE "Order No" = ?;
~~~

Nếu triển khai custom SQL deletion, cần tính đến optimistic locking, số lượng hàng bị tác động, collection, cache và cách provider kỳ vọng bind tham số. Khi chỉ cần đọc các bản ghi còn hoạt động, có thể đặt điều kiện ở repository/query thay vì thay đổi toàn bộ ngữ nghĩa xóa của entity.

## 24. Thực hành truy vấn khi tên SQL và tên Java khác nhau

Giả sử entity có field:

~~~java
private Long orderNumber;
private CustomerRecord customer;
private MoneyInCents amount;
private OrderStatus status;
~~~

Một truy vấn JPQL:

~~~java
List<LegacyOrder> orders = em.createQuery(
    "select o from LegacyOrder o " +
    "where o.status = :status " +
    "order by o.orderNumber desc",
    LegacyOrder.class
)
.setParameter("status", OrderStatus.NEW)
.getResultList();
~~~

JPQL dùng **`status`** và **`orderNumber`** theo property Java. Hibernate sử dụng converter để bind `OrderStatus.NEW` thành mã SQL `N` và tạo SQL tham chiếu đúng `"Status Flag"`, `"Order No"`.

Với SQL native:

~~~java
List<?> ids = em.createNativeQuery(
    "select \"Order No\" from \"Legacy\".\"Order Archive\" " +
    "where \"Status Flag\" = :code"
)
.setParameter("code", "N")
.getResultList();
~~~

SQL native dùng trực tiếp **identifier SQL** và giá trị lưu **`N`**. Không mặc định provider sẽ tìm `OrderStatusConverter` cho một tham số native SQL không gắn với đường dẫn thuộc tính JPA.

### Kiểm tra hai chiều mapping

Một bài thử đọc/ghi có thể gồm:

1. Nạp đơn hiện có bằng `em.find(LegacyOrder.class, 10001L)`.
2. Kiểm tra Java nhận đúng `OrderStatus.NEW`, `MoneyInCents.ofCents(157500)` và ngày `2026-12-01`.
3. Gọi `order.close()` trong transaction, commit.
4. Truy vấn SQL trực tiếp và xác nhận `"Status Flag" = 'C'` nhưng các cột khác giữ đúng dữ liệu.
5. Mở persistence context mới, nạp lại và xác nhận `OrderStatus.CLOSED`.

Đây là cách quan sát **hợp đồng đọc/ghi**; kết quả phụ thuộc môi trường và dữ liệu thật. STEP 4 của bài học chỉ mô tả ví dụ, chưa thực thi nội dung kiểm thử.

## 25. Hibernate schema validation và giới hạn của nó

Với database đã có sẵn, tránh cho Hibernate tự tùy tiện tạo hoặc sửa bảng. Một cấu hình thường dùng:

~~~properties
hibernate.hbm2ddl.auto=validate
~~~

Trong Spring Boot, thuộc tính tương ứng thường là:

~~~properties
spring.jpa.hibernate.ddl-auto=validate
~~~

Chế độ `validate` kiểm tra những khía cạnh schema theo metadata provider, hữu ích để phát hiện bảng/cột thiếu hoặc không tương thích. Tuy nhiên **validate không phải bằng chứng rằng mọi giá trị legacy đã đúng**:

- `Status Flag = 'X'` vẫn có thể tồn tại nếu DB không có CHECK; converter chỉ báo lỗi khi đọc.
- `Planned Date = '20261399'` có thể đúng `CHAR(8)` về độ dài nhưng sai ngày.
- Một khóa nghiệp vụ tưởng duy nhất có thể chứa hàng trùng.
- Một cột `TIMESTAMP` có thể đúng kiểu JDBC nhưng sai quy ước múi giờ.
- Dữ liệu tiền có thể đúng kiểu `BIGINT` nhưng ứng dụng hiểu sai đơn vị.

Không dùng `update` như phương án migration mặc định cho production legacy schema: provider có thể phát sinh DDL không phù hợp với quy tắc cũ, khóa, quyền hoặc dữ liệu. Thường nên dùng migration có kiểm soát (ví dụ Flyway/Liquibase hay quy trình DBA hiện có), kiểm tra thay đổi trước khi áp dụng.

## 26. Quan sát SQL và parameter binding khi xử lý lỗi

Khi Hibernate báo “column not found”, “relation does not exist” hoặc “cannot convert value”, cần quan sát **SQL đã được phát** thay vì chỉ xem tên annotation.

Trong Hibernate 6, cấu hình logging có thể dùng:

~~~properties
hibernate.show_sql=true
hibernate.format_sql=true
~~~

Với SLF4J/Logback hoặc hệ thống logging tương ứng, có thể bật SQL logger như:

~~~properties
logging.level.org.hibernate.SQL=DEBUG
~~~

Trong Spring Boot, để quan sát bind parameter với Hibernate 6:

~~~properties
logging.level.org.hibernate.orm.jdbc.bind=TRACE
~~~

**Cẩn thận với dữ liệu nhạy cảm trong parameter logging**: trace có thể ghi PII, token hoặc thông tin thanh toán. Chỉ bật trong môi trường phát triển/test phù hợp và có xử lý log an toàn.

Khi xem log, lần lượt hỏi:

- Hibernate có quote `"Legacy"`, `"Order Archive"` đúng không?
- Tên cột có đúng dấu cách/case/physical naming không?
- Giá trị bind của `OrderStatus.NEW` là `N` hay nhầm `NEW`?
- Giá trị ngày dùng `20261201` hay `2026-12-01`?
- FK `"Cust No"` có đúng kiểu và mã khách hàng không?
- SQL có lỡ cập nhật cột do trigger/ứng dụng cũ sở hữu không?
- Truy vấn được thực thi trong transaction và persistence context phù hợp không?

Đây là các dấu hiệu thực tế để định vị một mapping sai giữa ba tầng Java, JDBC và SQL.

## 27. Thay đổi schema cũ theo từng bước nhỏ

Khi có quyền cải tiến database, thay đổi dần thường an toàn hơn viết lại một lần. Ví dụ muốn đổi `"Planned Date" CHAR(8)` sang cột `DATE` thực sự:

~~~text
Cột cũ: "Planned Date" CHAR(8)
                    ↓
Bổ sung cột DATE mới (nullable)
                    ↓
Chuyển dữ liệu và xử lý giá trị sentinel
                    ↓
Ứng dụng đọc được cả hai biểu diễn trong giai đoạn chuyển tiếp
                    ↓
Bắt đầu ghi định dạng mới theo kế hoạch rollout
                    ↓
Kiểm tra dữ liệu, thêm constraint, bỏ cột cũ khi an toàn
~~~

Các bước cần cân nhắc:

| Bước | Câu hỏi |
| --- | --- |
| Khảo sát | Có dữ liệu không hợp lệ, null, khoảng trắng, sentinel, trùng khóa không? |
| Migration | Câu lệnh chuyển đổi có chạy được với mọi hàng không? |
| Tương thích | Ứng dụng cũ còn đọc/ghi cột nào trong lúc rollout? |
| Concurrency | Có transaction nào ghi dữ liệu cũ khi migration đang chạy không? |
| Constraint | Khi nào có thể thêm `NOT NULL`, FK, unique, CHECK mà không chặn ứng dụng? |
| Mapping | Lúc nào đổi converter và annotation sang cột mới? |
| Rollback | Nếu quay lại phiên bản cũ, nó có hiểu dữ liệu do phiên bản mới ghi không? |

**Đổi Java field từ `String` thành `LocalDate` không tự chuyển dữ liệu vật lý ở database.** Converter có thể giữ tương thích trong giai đoạn chuyển đổi, nhưng khi thay schema và hợp đồng dữ liệu cần migration riêng.

### Không dùng global quoting để sửa dữ liệu sai case

Nếu bảng đã được tạo `"Orders"` nhưng entity nhắm `orders`, bật hoặc tắt global quoting không tự đổi tên bảng trong database. Hãy xác định tên vật lý đúng rồi sửa mapping/migration có chủ đích. Identifier quoting giải quyết cách **tham chiếu tên**, không làm sạch dữ liệu hay đổi schema.

## 28. Vấn đề transaction, khóa đồng thời và cache trong schema legacy

Một schema cũ có thể được truy cập bởi:

- Ứng dụng Hibernate mới.
- Ứng dụng desktop cũ dùng SQL trực tiếp.
- Batch job chạy ban đêm.
- Stored procedure và trigger.
- Công cụ nhập liệu từ bên thứ ba.

Vì vậy entity mapping đúng **chưa đủ** để ngăn hai ứng dụng ghi đè nhau. `@Version` hỗ trợ optimistic locking nếu schema có cột version thích hợp và các writer liên quan phối hợp cập nhật nó. Nếu writer cũ không dùng cơ chế version, Hibernate khó phát hiện mọi cập nhật cạnh tranh chỉ nhờ annotation.

Khi dữ liệu bị cập nhật ngoài Hibernate:

- Managed entity đã nạp có thể chứa giá trị cũ trong persistence context.
- Query cache hoặc second-level cache (nếu bật) có thể không được báo invalidation.
- `em.refresh(entity)`, kết thúc context, clear cache hoặc cơ chế đồng bộ có thể cần thiết tùy luồng xử lý.
- Native SQL/bulk update không nhất thiết cập nhật object managed đang có.

Đừng bật cache cấp hai cho toàn bộ entity legacy khi có writer ngoài Hibernate mà chưa có chiến lược invalidation cụ thể. Với các bảng thường xuyên bị thay đổi bởi job khác, truy vấn trực tiếp theo nhu cầu có thể phù hợp hơn caching lâu dài.

## 29. Các lỗi thường gặp và cách định vị

| Biểu hiện | Nguyên nhân đáng kiểm tra | Hướng xử lý |
| --- | --- | --- |
| PostgreSQL báo `relation does not exist` | Schema/table bị thiếu quote hoặc sai case | Kiểm tra `@Table(schema,name)`, SQL thực tế và quyền |
| Hibernate báo không thấy cột | `@Column` thiếu tên chính xác hoặc physical naming strategy đổi tên | Đối chiếu JDBC metadata và identifier có quote |
| Query JPQL báo unknown entity | Dùng tên bảng thay vì entity name, entity chưa đăng ký | Dùng `@Entity(name=...)` và kiểm tra persistence unit |
| Cột `CHAR` đọc có khoảng trắng | Fixed-length char padding | Xử lý theo quy tắc dữ liệu; không trim ID vô điều kiện |
| Converter gặp mã trạng thái lạ | DB có `X`, blank hoặc dữ liệu legacy không được định nghĩa | Khảo sát dữ liệu, xác định mapping/migration đúng |
| Ngày `yyyyMMdd` đọc lỗi | Có chuỗi sai/ngày sentinel | Thiết kế quy tắc null/sentinel và làm sạch dữ liệu |
| Tiền hiển thị sai 100 lần | Không hiểu đơn vị cents/major units | Định nghĩa value object và converter có đơn vị chính xác |
| Schema validate báo wrong column type | Type JDBC hoặc columnDefinition không phù hợp DB thực tế | Kiểm tra driver, Dialect, converter/custom type |
| Insert báo null ID | Cột PK không có generator như annotation giả định | Dùng assigned ID hoặc generator tương thích |
| Ánh xạ `@ManyToOne` nhưng không tìm đúng khách hàng | FK/referencedColumnName sai, cột đích không unique hoặc padding | Xác minh FK và data type từng cột |
| Entity bị trùng trong context khi dùng bảng không PK | Không có identifier thật sự ổn định | Bổ sung khóa, hoặc dùng DTO/JDBC cho dữ liệu không có ID |
| Cột do trigger cấp nhưng object không thấy giá trị | ORM chưa nạp lại generated value | Cấu hình generated property hoặc refresh thích hợp |
| Sửa entity nhưng view/bảng không cho update | Mapping tới view read-only hoặc thiếu quyền | Dùng `@Immutable`/DTO hay thao tác đúng bảng gốc |
| Đổi cột hai chiều nhưng mất dữ liệu | Mapping ghi trùng hoặc converter không tương thích dữ liệu cũ | Một đường ghi rõ, migration và hợp đồng phiên bản |
| Nạp entity đúng nhưng cache cho dữ liệu cũ | Writer khác sửa DB ngoài Hibernate | Đồng bộ cache/context hoặc không cache dữ liệu đó |

### Khi gặp lỗi ánh xạ, đọc từ trong ra ngoài

~~~mermaid
flowchart TD
    A["Lỗi khi nạp/ghi entity legacy"] --> B{"Tên bảng/cột SQL đúng?"}
    B -- "Không" --> C["Sửa @Table/@Column/@JoinColumn và quoting"]
    B -- "Có" --> D{"Kiểu JDBC và giá trị bind đúng?"}
    D -- "Không" --> E["Sửa converter, type, đơn vị hoặc timezone"]
    D -- "Có" --> F{"Khóa/quan hệ có ràng buộc hợp lệ?"}
    F -- "Không" --> G["Xem @Id, @EmbeddedId, FK và unique"]
    F -- "Có" --> H{"Quyền ghi, trigger, cache, transaction đúng?"}
    H -- "Không" --> I["Sửa mapping lifecycle và truy cập dữ liệu"]
    H -- "Có" --> J["Kiểm tra dữ liệu legacy thực và câu SQL cụ thể"]
~~~

Sơ đồ là cách định vị nguyên nhân theo lớp: **identifier → type conversion → identity/relationship → lifecycle/transaction**. Nó giúp tránh thay đổi ngẫu nhiên nhiều annotation khi chưa xác định vấn đề nằm ở đâu.

## 30. Bài tập thực hành

### Bài 1 — Tên bảng có khoảng trắng và chữ hoa

Bảng SQL:

~~~sql
SELECT "Display Name"
FROM "Legacy"."Customer Registry";
~~~

Hãy viết annotation trên entity `CustomerRecord` và field `displayName`.

**Đáp án:**

~~~java
@Entity
@Table(name = "\"Customer Registry\"", schema = "\"Legacy\"")
public class CustomerRecord {
    @Id
    @Column(name = "\"Cust No\"")
    private String customerNumber;

    @Column(name = "\"Display Name\"")
    private String displayName;

    protected CustomerRecord() {}
}
~~~

### Bài 2 — Trạng thái `Y/N`

Một bảng cũ có cột `"Active Flag" CHAR(1)` lưu `Y` cho true và `N` cho false. Một ứng dụng muốn dùng `Boolean`. Chọn cách ánh xạ nào?

**Đáp án:** có thể dùng `AttributeConverter<Boolean,String>` chuyển `true↔"Y"`, `false↔"N"` và xử lý `null` theo quy tắc nghiệp vụ. Không nên giả định Hibernate tự hiểu mọi `CHAR(1)` là boolean chuẩn SQL. Nếu dùng Hibernate-specific built-in boolean mapping cần kiểm tra khả năng hỗ trợ và dữ liệu cũ.

### Bài 3 — Bảng có khóa ghép

Bảng `"Order Item"` có PK `("Order No","Line No")` và FK `"Order No"` tới `"Order Archive"`. Nên dùng gì?

**Đáp án:** `@EmbeddedId` hoặc `@IdClass`; nếu mapping quan hệ tới đơn hàng và FK đồng thời là một phần ID, có thể dùng `@MapsId("orderNumber")`. Cần giữ khóa ổn định sau khi entity persistent.

### Bài 4 — Bảng log không có PK

Bảng `"Import Log"` có thể có hai hàng hoàn toàn giống nhau. Có thể dùng một field `@Id` tùy ý, chẳng hạn `"Message"`, để Hibernate quản lý không?

**Đáp án:** Không đáng tin cậy. `Message` không unique nên nhiều hàng sẽ có cùng entity ID, phá vỡ identity map. Nếu không thể thêm khóa ổn định, dùng projection/native SQL/JDBC cho báo cáo đọc dữ liệu.

### Bài 5 — Thay tên cột nhưng giữ dữ liệu

DB lưu `"Planned Date" CHAR(8)` dạng `yyyyMMdd`. Ứng dụng muốn dùng `LocalDate` nhưng chưa được phép đổi schema. Cách thực hiện?

**Đáp án:** đặt `@Column(name = "\"Planned Date\"")` và `@Convert(converter = LegacyDateConverter.class)` với `AttributeConverter<LocalDate,String>`, xử lý `null`/sentinel và format có chủ đích.

### Bài 6 — View tổng hợp

View có hàng theo tháng nhưng không có khóa duy nhất ổn định. Có nên tạo entity `@Id` là tháng không?

**Đáp án:** Chỉ khi mỗi giá trị tháng thực sự xác định duy nhất một hàng cho toàn bộ phạm vi view và điều kiện dữ liệu. Nếu view có nhiều hàng cùng tháng theo khách hàng/khu vực, `month` không đủ. Thường dùng DTO projection hoặc thiết kế khóa ghép thực sự phù hợp.

### Bài 7 — Cột do database tự tạo

Schema có default `CURRENT_TIMESTAMP` cho `"Created At"`, nhưng Java gửi `NULL` ở insert. Tại sao default có thể không hoạt động?

**Đáp án:** Default thường chỉ áp dụng nếu cột không được đưa vào `INSERT` hoặc nếu câu SQL yêu cầu `DEFAULT`. Cần cấu hình field do DB quản lý đúng cách, hoặc cấp timestamp từ Java theo hợp đồng ứng dụng.

### Bài 8 — Dữ liệu được sửa bởi hệ thống cũ

Hibernate đọc đơn 10001, sau đó một batch SQL đổi `"Status Flag"` ở database. Object đã managed có tự cập nhật ngay không?

**Đáp án:** Không. Persistence context có thể giữ snapshot cũ. Cần chiến lược refresh/reload và cache invalidation phù hợp; transaction hoặc annotation converter không tự theo dõi SQL của một hệ thống khác.

## 31. Lựa chọn cơ chế theo đặc điểm legacy

| Đặc điểm schema cũ | Cơ chế đầu tiên nên cân nhắc |
| --- | --- |
| Tên bảng/cột đặc biệt hoặc khác tên Java | `@Table`, `@Column`, quoted identifier |
| Khác schema/catalog | `@Table(schema=..., catalog=...)`, quyền truy cập phù hợp |
| Naming strategy làm sai tên | Physical naming strategy và quote tường minh |
| `CHAR(1)`/`SMALLINT` mã trạng thái | `AttributeConverter` hoặc type mapping được hỗ trợ |
| Ngày lưu bằng chuỗi/epoch | Converter với format, unit, null và sentinel rõ ràng |
| Kiểu cột đặc thù driver/dialect | Hibernate JDBC type/custom mapping phù hợp phiên bản |
| FK tên lạ hoặc tới cột unique khác PK | `@JoinColumn(referencedColumnName=...)`, kiểm tra unique |
| Khóa ghép | `@EmbeddedId`, `@IdClass`, `@MapsId` khi cần |
| Một entity trải trên hai bảng cùng PK | `@SecondaryTable` |
| Bảng liên kết mang dữ liệu nghiệp vụ | Entity trung gian với `@ManyToOne` |
| View có identifier ổn định | Entity đọc-only (`@Immutable` của Hibernate) |
| View hoặc bảng không có ID ổn định | Native query/JDBC/DTO projection |
| Cột tính toán, biểu thức đọc | `@Formula` hoặc database view |
| Cột có transform khi đọc/ghi | `@ColumnTransformer` hoặc converter thích hợp |
| Soft delete cũ | Mapping cờ + truy vấn, hoặc cơ chế Hibernate theo version/schema |
| Default/trigger tự cấp giá trị | Generated-value mapping, quyền ghi cột, refresh khi cần |
| Dữ liệu bị writer ngoài Hibernate thay đổi | Chiến lược transaction và cache invalidation |

**Không có annotation duy nhất “sửa mọi schema legacy”.** Hãy phân loại vấn đề là tên identifier, kiểu dữ liệu, identity, quan hệ, cấu trúc nhiều bảng hay vòng đời ghi/đọc; chọn cơ chế tương ứng.

## 32. Nguyên tắc tổng kết

Một schema có sẵn luôn mang theo **hợp đồng dữ liệu thực tế**, bao gồm cả những quy ước không được thể hiện đầy đủ bằng DDL. Hibernate ánh xạ được nhiều cấu trúc không đẹp về mặt tên hoặc kiểu dữ liệu, nhưng phải được hướng dẫn đủ rõ:

1. **Giữ tên SQL chính xác:** dùng `@Table`, `@Column`, `@JoinColumn` và quoted identifier đúng theo dialect; kiểm soát naming strategy.
2. **Giữ đúng ý nghĩa giá trị:** dùng converter hoặc JDBC type mapping phù hợp cho mã cũ, đơn vị tiền, định dạng ngày và kiểu SQL đặc thù.
3. **Không làm sai định danh:** xác định PK thực, khóa ghép và FK; bảng không có ID ổn định thường không nên bị ép thành managed entity.
4. **Chọn mapping cấu trúc đúng:** `@SecondaryTable` cho các cột của cùng entity ở bảng phụ, association/entity trung gian cho quan hệ có vòng đời riêng, DTO cho kết quả báo cáo không có identity.
5. **Tôn trọng database đang chạy:** tránh DDL tự động phá schema, hiểu trigger/default, transaction, cache và các writer ngoài Hibernate.
6. **Thay đổi hợp đồng bằng migration:** khi cần sửa tên, kiểu hoặc format, triển khai từng bước sao cho dữ liệu cũ và các phiên bản ứng dụng liên quan cùng được xử lý.

Khi nắm rõ những nguyên tắc đó, ta có thể xây dựng một **mô hình Java có tên và kiểu rõ nghĩa** trên một database cũ mà vẫn bảo toàn dữ liệu, khóa quan hệ và giao dịch. Đó chính là giá trị thực tế của ánh xạ nâng cao trong JPA/Hibernate: thích ứng lớp persistence với cấu trúc đang tồn tại, đồng thời mở đường cải tiến schema một cách có kiểm soát.
