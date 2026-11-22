# Đánh giá các kiểu đặc thù vượt phạm vi ánh xạ chuẩn

Khi ánh xạ thuộc tính của Java entity vào cơ sở dữ liệu quan hệ bằng Jakarta Persistence (JPA), các kiểu quen thuộc như `String`, `Integer`, `BigDecimal` hoặc `LocalDate` thường không cần nhiều cấu hình. Nhưng dữ liệu thực tế còn có JSON/JSONB, mảng SQL, kiểu enum do database định nghĩa, địa lý (geometry), khoảng thời gian (range), địa chỉ IP, vector, kiểu do người dùng tự định nghĩa, hoặc đối tượng miền dữ liệu có cấu trúc phức tạp.

**Vấn đề quan trọng không chỉ là lưu được giá trị.** Một ánh xạ tốt còn phải bảo đảm giá trị đọc lại đúng, có thể truy vấn và lập chỉ mục theo yêu cầu, được phát hiện thay đổi khi cập nhật entity, không làm mất dữ liệu khi migrate và có chi phí phụ thuộc database/provider chấp nhận được.

Bài học này trình bày cách xác định giới hạn của ánh xạ thuộc tính chuẩn trong **JPA**, lựa chọn từ `@Embeddable`, `AttributeConverter` tới các extension của Hibernate hoặc SQL trực tiếp, và đánh giá cái giá của từng lựa chọn trong thiết kế hệ thống.

## 1. “Ánh xạ chuẩn” bao phủ đến đâu?

### 1.1. Các loại thuộc tính trong JPA

JPA hỗ trợ nhiều kiểu ánh xạ hơn là “một field = một cột”. Ta cần phân biệt:

| Cách ánh xạ | Dùng cho | Ví dụ |
|---|---|---|
| **Basic attribute** (`@Basic` hoặc mặc định) | Giá trị đơn lẻ được provider ánh xạ bằng JDBC | `String`, `int`, `BigDecimal`, `LocalDate`, `byte[]` |
| **Enum** (`@Enumerated`) | Giá trị thuộc tập tên enum Java | `EnumType.STRING`, `EnumType.ORDINAL` |
| **Temporal** | Giá trị ngày/giờ Java | `LocalDate`, `LocalDateTime`, `Instant`, `OffsetDateTime` theo phiên bản/khả năng provider |
| **LOB** (`@Lob`) | Dữ liệu ký tự hoặc nhị phân lớn | `String` dạng CLOB, `byte[]` dạng BLOB theo mapping/provider |
| **Embeddable** (`@Embeddable`, `@Embedded`) | Value object có thể trải trên nhiều cột của hàng cha | `Address(street, city, zipCode)` |
| **Element collection** (`@ElementCollection`) | Tập hợp giá trị hoặc embeddable lưu trong bảng phụ | Danh sách tag, nhiều địa chỉ |
| **Relationship** | Tham chiếu entity khác | `@ManyToOne`, `@OneToMany` |
| **Attribute converter** (`@Convert`) | Chuyển đổi một kiểu Java thành kiểu cơ bản khác khi đọc/ghi một thuộc tính | `MoneyStatus ↔ String`, `Preferences ↔ String` |

Các kiểu như UUID và API thời gian hiện đại có mức hỗ trợ khác nhau giữa các thế hệ JPA; ví dụ **Jakarta Persistence 3.1** đã chuẩn hóa thêm hỗ trợ UUID và sinh ID kiểu UUID. Điều đó **không bảo đảm mọi database sẽ lưu UUID bằng cùng một kiểu SQL**.

Mỗi khi gặp “kiểu lạ”, hãy phân biệt ba câu hỏi:

1. **JPA có hiểu kiểu Java không?**
2. **JDBC/driver có biết truyền giá trị đó bằng kiểu SQL phù hợp không?**
3. **Database có hỗ trợ phép toán, index và ràng buộc cần thiết cho kiểu đó không?**

Có thể câu 1 đúng nhưng câu 2 hoặc câu 3 chưa đáp ứng, và ngược lại.

### 1.2. Năm lớp cần đi qua

```text
Thuộc tính Java
     │  (Preferences, InetAddress, Geometry, List<String>...)
     ▼
Metadata JPA
     │  (@Basic, @Convert, @JdbcTypeCode, @Embedded...)
     ▼
JPA provider / ORM type system
     │  (Java type, mutability plan, JDBC mapping)
     ▼
JDBC driver
     │  (PreparedStatement binding, ResultSet extraction)
     ▼
Cơ sở dữ liệu
        (JSONB, ARRAY, geometry, enum, range, VARCHAR...)
```

Không thể chỉ thay `@Column(columnDefinition = "jsonb")` rồi mặc định Java object tự biến thành JSONB. `columnDefinition` chủ yếu mô tả kiểu cột để DDL hoặc metadata; **nó không tự cung cấp serialization, JDBC binding và SQL operator**.

Ngược lại, nếu dùng `AttributeConverter<Preferences, String>` thì JPA có thể biết chuyển một object thành chuỗi, nhưng điều đó **không có nghĩa** database nhận chuỗi đó làm tham số kiểu JSONB hoặc JPA biết truy vấn các khóa con của JSON.

## 2. Một loại dữ liệu “đặc thù” được đánh giá theo những tiêu chí nào?

Trước khi chọn cách mapping, xác định những yêu cầu sau:

| Câu hỏi | Tác động đến lựa chọn |
|---|---|
| Dữ liệu có cấu trúc cố định hay thường thay đổi? | Cấu trúc cố định, có ràng buộc rõ thường hợp với cột/bảng chuẩn hóa; thuộc tính tùy biến có thể hợp JSON. |
| Chỉ lưu và đọc lại, hay phải lọc/nhóm/sắp xếp theo thuộc tính con? | Nhu cầu query/index mạnh ưu tiên native SQL type hoặc thiết kế quan hệ. |
| Có cần ràng buộc unique, check, foreign key, exclusion? | Database thường kiểm soát tốt hơn ở các cột quan hệ riêng. |
| Giá trị có thể sửa từng phần trong bộ nhớ không? | Mutable object làm phức tạp dirty checking và cache. |
| Dung lượng mỗi giá trị và số hàng là bao nhiêu? | Ảnh hưởng kích thước row, TOAST/LOB, băng thông và chi phí chuyển đổi. |
| Có cần đổi database hoặc provider không? | Mức phụ thuộc vào dialect và extension phải được chấp nhận. |
| Có phải cập nhật schema/migrate dữ liệu trong tương lai không? | DDL, đổi tên trường JSON, đổi enum/database type có thể tốn công. |
| Dữ liệu có cần mã hóa hoặc kiểm soát truy cập riêng không? | Cần thiết kế bảo mật, index và phân quyền phù hợp, không chỉ converter. |

Một quyết định mapping cần mô tả **hành vi truy cập dữ liệu**. Ví dụ “profile của khách hàng được đọc toàn bộ, ít thay đổi” rất khác “tìm 100.000 khách có cờ `marketingOptIn` trong JSON và sắp xếp theo hạng thành viên”.

## 3. Bộ công cụ: từ JPA chuẩn tới extension của nhà cung cấp

| Giải pháp | Mức phụ thuộc | Thế mạnh | Giới hạn chính |
|---|---|---|---|
| Basic mapping JPA chuẩn | Thấp | Đơn giản, dễ bảo trì | Không biểu diễn hết các SQL type đặc thù |
| `@Embeddable` trên nhiều cột | Thấp | Ràng buộc, lọc, index từng thành phần | Cần schema cố định |
| `@ElementCollection` / entity con | Thấp đến vừa | Truy vấn quan hệ, khóa ngoại/index rõ | Thêm bảng, JOIN và quản lý collection |
| `AttributeConverter<X,Y>` | Theo JPA | Tự chuyển một giá trị Java sang một kiểu basic hỗ trợ được | Không tự định nghĩa SQL type, operator, JDBC binding đặc thù |
| Hibernate `@JdbcTypeCode`, `@Type` hoặc hệ Type SPI | Cao hơn | Hỗ trợ JSON, SQL ARRAY, custom JDBC type... | Phụ thuộc phiên bản provider, dialect và driver |
| Native SQL / SQL builder | Phụ thuộc SQL dialect | Dùng trực tiếp operator, index, hàm database | Cần quản lý mapping kết quả và khả năng di chuyển |
| Thiết kế lại schema / hệ thống chuyên dụng | Phụ thuộc kiến trúc | Phù hợp query, ràng buộc và quy mô dữ liệu | Thay đổi mô hình, migration và vận hành |

**Không có mức “chuẩn” nào bảo đảm tốc độ nhanh hơn.** Lựa chọn phụ thuộc vào thao tác cụ thể, hình dạng dữ liệu và các yêu cầu dài hạn.

## 4. Trường hợp điển hình: JSON và JSONB

### 4.1. Khi nào hợp lý để lưu JSON trong một cột?

Ví dụ bảng `customer_profiles` có những thuộc tính cơ bản như `id`, `email` và một cấu trúc `preferences`:

```json
{
  "theme": "dark",
  "notificationsEnabled": true,
  "language": "vi"
}
```

JSON phù hợp khi cấu trúc preferences có thể thay đổi, thường được đọc/ghi như một khối và không cần nhiều quan hệ độc lập. Nếu ứng dụng liên tục JOIN theo `language`, tạo báo cáo theo `theme`, yêu cầu unique hoặc ràng buộc phức tạp, cột riêng hoặc bảng quan hệ có thể rõ ràng hơn.

Cần phân biệt:

- **JSON dạng chuỗi:** nội dung được serialize thành `VARCHAR`/`TEXT`/CLOB; database không nhất thiết hiểu cấu trúc JSON.
- **Kiểu JSON/JSONB của database:** database hiểu cấu trúc hoặc lưu ở định dạng riêng, hỗ trợ operator/hàm/index đặc thù. PostgreSQL có `json` và `jsonb` với các tính chất khác nhau; các hệ CSDL khác có cú pháp/tính năng khác.

### 4.2. Hướng A: dùng `AttributeConverter` lưu JSON thành chuỗi

Đây là ví dụ **JPA tương đối độc lập provider**. Java 17 record được dùng làm value object có trường ổn định:

```java
package com.example.shop.domain;

public record Preferences(
    String theme,
    boolean notificationsEnabled,
    String language
) {}
```

Converter sử dụng Jackson để serialize/deserialize. Thư viện Jackson cần được khai báo trong dependencies:

```java
package com.example.shop.persistence;

import com.example.shop.domain.Preferences;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.persistence.AttributeConverter;
import jakarta.persistence.Converter;
import jakarta.persistence.PersistenceException;

@Converter
public class PreferencesJsonConverter
        implements AttributeConverter<Preferences, String> {

    private static final ObjectMapper JSON = new ObjectMapper();

    @Override
    public String convertToDatabaseColumn(Preferences value) {
        if (value == null) {
            return null;
        }
        try {
            return JSON.writeValueAsString(value);
        } catch (JsonProcessingException ex) {
            throw new PersistenceException(
                "Không thể chuyển Preferences thành JSON", ex);
        }
    }

    @Override
    public Preferences convertToEntityAttribute(String raw) {
        if (raw == null) {
            return null;
        }
        try {
            return JSON.readValue(raw, Preferences.class);
        } catch (JsonProcessingException ex) {
            throw new PersistenceException(
                "Dữ liệu Preferences JSON không hợp lệ", ex);
        }
    }
}
```

Áp dụng lên entity:

```java
package com.example.shop.domain;

import com.example.shop.persistence.PreferencesJsonConverter;
import jakarta.persistence.Column;
import jakarta.persistence.Convert;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "customer_profiles")
public class CustomerProfile {

    @Id
    @GeneratedValue
    private Long id;

    @Column(name = "preferences_json", length = 4000)
    @Convert(converter = PreferencesJsonConverter.class)
    private Preferences preferences;

    protected CustomerProfile() {}

    public void updatePreferences(Preferences value) {
        this.preferences = value;
    }

    public Preferences getPreferences() {
        return preferences;
    }
}
```

Với cấu hình này, converter trả về `String` nên cột được xử lý như loại ký tự phù hợp với mapping của provider. `length = 4000` chỉ là giới hạn minh họa, cần chọn loại cột/độ dài thực tế theo dữ liệu và database. Việc dùng CLOB/TEXT hoặc kích thước lớn hơn là quyết định schema riêng.

Ưu điểm: dễ triển khai, tập trung logic chuyển đổi, không yêu cầu loại JSON native của một database.

Giới hạn:

1. JPA xử lý thuộc tính như **một giá trị**; truy vấn JPQL không tự có cú pháp portable để truy cập `preferences.theme`.
2. Mọi lần đổi toàn bộ thuộc tính có thể phải serialize/ghi lại chuỗi JSON, tùy cơ chế dirty checking.
3. Nếu database cần ràng buộc JSON hợp lệ hoặc query theo JSON path, giải pháp chuỗi đơn thuần không tự cung cấp.
4. Converter chuyển sang `String` không tự bảo đảm JDBC binder dùng kiểu `jsonb` của PostgreSQL. Trỏ cùng field vào cột `jsonb` chỉ bằng `columnDefinition="jsonb"` có thể gây lỗi kiểu tham số; khi đó cần JDBC mapping dành cho JSON hoặc cơ chế ép kiểu phù hợp.

Không nên bật `@Converter(autoApply = true)` cho mọi `Preferences` nếu các property cùng Java type lại cần SQL representation khác nhau ở từng bảng.

### 4.3. Hướng B: JSONB native với Hibernate 6 và PostgreSQL

Nếu muốn database quản lý dữ liệu bằng kiểu JSON thực, Hibernate 6 có thể dùng `@JdbcTypeCode(SqlTypes.JSON)`:

```java
package com.example.shop.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.type.SqlTypes;

@Entity
public class CustomerProfile {

    @Id
    private Long id;

    @JdbcTypeCode(SqlTypes.JSON)
    @Column(name = "preferences", columnDefinition = "jsonb")
    private Preferences preferences;

    protected CustomerProfile() {}

    public void replacePreferences(Preferences newPreferences) {
        this.preferences = newPreferences;
    }
}
```

Cấu hình này có hai phần riêng:

- `@JdbcTypeCode(SqlTypes.JSON)` là chỉ dẫn **riêng Hibernate** để provider chọn mapping JDBC loại JSON.
- `columnDefinition = "jsonb"` là DDL cụ thể **PostgreSQL**; database khác có tên type hoặc cách xử lý khác.

Ứng dụng cần Hibernate phiên bản tương thích, driver PostgreSQL và thư viện serialize JSON mà Hibernate sử dụng (thường Jackson hoặc JSON-B tùy cấu hình). Đoạn mã là lựa chọn cho một stack cụ thể, **không phải annotation chuẩn của Jakarta Persistence**.

Ví dụ lược đồ PostgreSQL:

```sql
CREATE TABLE customer_profiles (
    id bigint PRIMARY KEY,
    preferences jsonb NOT NULL
);
```

Khi truy vấn theo khóa nằm trong JSON:

```sql
SELECT id, preferences
FROM customer_profiles
WHERE preferences ->> 'theme' = 'dark';
```

Đây là **SQL PostgreSQL**: `->>` lấy giá trị JSON theo key dưới dạng text. Nếu truy vấn xuất hiện thường xuyên, cân nhắc expression index:

```sql
CREATE INDEX ix_customer_theme
    ON customer_profiles ((preferences ->> 'theme'));
```

Đối với những phép lọc containment JSONB, có thể cân nhắc GIN index tùy operator và workload:

```sql
CREATE INDEX ix_customer_preferences_gin
    ON customer_profiles USING GIN (preferences);
```

Hai loại index phục vụ những mẫu truy vấn khác nhau. Không nên tạo cả hai chỉ vì cột là JSONB: index làm chậm thao tác ghi và tốn dung lượng. Cần kiểm tra bằng `EXPLAIN (ANALYZE, BUFFERS)` trên dữ liệu và khối lượng phù hợp.

### 4.4. Những chi tiết khó của JSON

**SQL NULL và JSON null khác nhau.** Ở PostgreSQL, `NULL` nghĩa là giá trị cột vắng mặt; `'null'::jsonb` là một giá trị JSON hợp lệ. Trong JSON object, một key không tồn tại cũng khác key có giá trị `null`. Converter và mô hình Java cần xác định rõ hành vi đối với từng trường hợp.

**Thứ tự và định dạng:** JSONB có thể chuẩn hóa cách lưu trữ khác văn bản đầu vào. Nếu cần giữ nguyên từng byte, khoảng trắng hoặc thứ tự key ban đầu, phải xét đến định dạng và kiểu lưu.

**Schema evolution:** sửa tên `notificationsEnabled` trong record không tự di chuyển dữ liệu đã tồn tại. Cần migration, cơ chế đọc tương thích ngược hoặc version payload.

**Dirty checking:** với object mutable như `Map<String, Object>` hoặc class có setter, thay đổi lồng bên trong có thể không được provider phát hiện như mong đợi nếu cơ chế snapshot/mutability không phù hợp. Dùng value object bất biến và **thay cả reference** thường dễ kiểm soát hơn; vẫn phải kiểm chứng cách provider so sánh giá trị khi flush.

**Validation:** database chỉ biết chuỗi JSON hoặc cấu trúc JSON hợp lệ chưa chắc biết business rule. Validate giá trị đầu vào trước khi persist, ví dụ theme chỉ thuộc danh sách cho phép. Nếu ràng buộc phải luôn đúng kể cả khi SQL bên ngoài ứng dụng ghi, cần constraint hoặc cơ chế kiểm soát ở database.

## 5. SQL ARRAY và tập hợp giá trị

### 5.1. Mảng của database không giống collection Java

Một entity có `Set<String> tags` hoặc `List<Integer> scores` không đương nhiên được JPA chuẩn ánh xạ thành một cột SQL `ARRAY`. Database như PostgreSQL có `text[]`, `integer[]`; cách JDBC gửi/nhận mảng có API riêng (`java.sql.Array`), và Hibernate có thể cung cấp hỗ trợ tùy phiên bản/dialect.

Ví dụ cột đặc thù:

```sql
CREATE TABLE products (
    id bigint PRIMARY KEY,
    tags text[] NOT NULL
);
```

PostgreSQL có operator mảng như kiểm tra chứa giá trị và có thể hỗ trợ GIN index. Tuy nhiên, chuyển đoạn này sang một database khác không nhất thiết giữ nguyên cú pháp hay khả năng xử lý mảng.

### 5.2. Phương án JPA chuẩn: `@ElementCollection`

Nếu tag là các phần tử cần tìm kiếm, ràng buộc hoặc sửa độc lập, có thể lưu trong bảng phụ:

```java
@Entity
@Table(name = "products")
public class Product {

    @Id
    private Long id;

    @ElementCollection
    @CollectionTable(
        name = "product_tags",
        joinColumns = @JoinColumn(name = "product_id")
    )
    @Column(name = "tag", nullable = false)
    private Set<String> tags = new HashSet<>();
}
```

Schema logic:

```text
products               product_tags
--------               ---------------------
id (PK)   ---------->  product_id (FK)
name                    tag
                        (product_id, tag) UNIQUE, nếu cần
```

Ưu điểm là SQL quan hệ thông thường dễ index từng tag, có thể đặt ràng buộc unique và truy vấn JOIN. Đánh đổi là thêm bảng và có thể phát sinh truy vấn/batch/collection update nhiều hơn.

Nếu tag thực chất có định danh, metadata và vòng đời riêng, một entity `Tag` cùng quan hệ `@ManyToMany` hoặc association entity có thể thích hợp hơn `@ElementCollection`.

### 5.3. Chọn ARRAY, JSON array hay bảng phụ?

| Đặc điểm | SQL ARRAY | JSON array | Bảng phụ |
|---|---|---|---|
| Dữ liệu | Đồng nhất về kiểu, thường gắn chặt với hàng cha | Linh hoạt, có thể lồng object | Có cấu trúc quan hệ rõ |
| Portability JPA | Phụ thuộc dialect/type support | Type native cũng phụ thuộc dialect | Tốt hơn với mapping chuẩn |
| Query từng phần tử | Operator riêng database | JSON path/operator riêng database | JOIN/WHERE SQL thông thường |
| Unique/FK từng phần tử | Khó hơn | Khó hơn | Rõ ràng hơn |
| Cập nhật từng phần tử | Có thể phải ghi lại cả mảng/tùy SQL | Có thể cần JSON update đặc thù | UPDATE/INSERT/DELETE từng hàng |
| Phù hợp | Tập giá trị nhỏ, truy cập theo hàng cha | Payload linh hoạt | Quan hệ cần tìm kiếm/ràng buộc thường xuyên |

Một giá trị byte array (`byte[]`) cho nội dung nhị phân **không đồng nghĩa** với SQL ARRAY các giá trị nghiệp vụ. Đây là hai loại mapping khác nhau.

## 6. Enum: tên enum Java và kiểu ENUM native

### 6.1. `@Enumerated` là tính năng JPA chuẩn

```java
public enum ShipmentStatus {
    NEW, PACKED, SHIPPED, CANCELLED
}

@Entity
public class Shipment {
    @Id
    private Long id;

    @Enumerated(EnumType.STRING)
    @Column(name = "status", nullable = false)
    private ShipmentStatus status;
}
```

Sử dụng `EnumType.STRING` để lưu tên hằng giúp tránh việc đổi thứ tự enum Java làm diễn giải sai dữ liệu như cách lưu `ORDINAL`. Nhưng đổi tên hằng `PACKED` thành `READY` vẫn có thể làm dữ liệu cũ không đọc được nếu không migrate tương ứng.

Trong trường hợp chung, JPA có thể dùng kiểu ký tự hoặc kiểu phù hợp theo provider/dialect. `@Enumerated(EnumType.STRING)` **không phải lời cam kết** rằng cột SQL là PostgreSQL native ENUM.

### 6.2. PostgreSQL native ENUM đòi hỏi đánh giá riêng

Ví dụ:

```sql
CREATE TYPE shipment_state AS ENUM (
    'NEW', 'PACKED', 'SHIPPED', 'CANCELLED'
);

CREATE TABLE shipments (
    id bigint PRIMARY KEY,
    status shipment_state NOT NULL
);
```

Kiểu enum ở database giúp ràng buộc tập giá trị và có hành vi so sánh riêng, nhưng ứng dụng phải bind SQL parameter đúng kiểu. Với một số cấu hình, truyền parameter VARCHAR vào cột enum native có thể phát sinh lỗi không tương thích kiểu; cần mapping/dialect phù hợp, ví dụ tính năng enum đặc thù của Hibernate hoặc SQL có cast được kiểm soát.

Cần cân nhắc việc **thêm, đổi tên, ngừng sử dụng giá trị enum** qua các lần triển khai. Database migration và ứng dụng phải tương thích trong giai đoạn rolling deployment. Nếu tập giá trị biến động thường xuyên hoặc có metadata, bảng tra cứu với khóa ngoại có thể thích hợp hơn native ENUM.

### 6.3. Một số enum cần converter, nhưng không phải lúc nào cũng nên dùng

Nếu cơ sở dữ liệu đã lưu mã `"N"`, `"P"`, `"S"`, có thể tạo converter `ShipmentStatus ↔ String` để tương thích hệ thống cũ. Tuy nhiên, trên cùng thuộc tính, việc phối hợp `@Enumerated` với `AttributeConverter` không phải cách dùng được JPA tiêu chuẩn hóa; nên chọn một chiến lược mapping rõ ràng.

Khi dùng converter cho enum, phải xử lý giá trị không nhận biết và migration; không nên lặng lẽ trả về default làm che mất dữ liệu không hợp lệ.

## 7. UUID, thời gian, tiền tệ và kiểu “đã hỗ trợ nhưng chưa đủ ngữ nghĩa”

Một kiểu Java có mapping chuẩn không có nghĩa **ngữ nghĩa miền dữ liệu** đã được giải quyết.

### 7.1. UUID

Trong Jakarta Persistence 3.1, UUID được hỗ trợ như kiểu định danh và có `GenerationType.UUID`:

```java
@Entity
public class Invoice {

    @Id
    @GeneratedValue(strategy = GenerationType.UUID)
    private UUID id;
}
```

Cơ sở dữ liệu có thể lưu thành kiểu `uuid` (như PostgreSQL), dạng ký tự hoặc binary tùy provider/dialect. Cần đánh giá:

- Index và hiệu năng ghi khi ID sinh ngẫu nhiên.
- Khả năng tương thích UUID format giữa ứng dụng và database.
- Nhu cầu truyền ID qua API hoặc giữa các dịch vụ.
- Chiến lược sinh ID khi dữ liệu được import từ hệ thống khác.

Không nên tự đặt `columnDefinition="uuid"` nếu dự án cần chạy trên database không có kiểu đó.

### 7.2. Instant, offset, timezone và khoảng thời gian

Các kiểu như `Instant`, `LocalDateTime` và `OffsetDateTime` mang ý nghĩa khác nhau:

| Java type | Ý nghĩa miền dữ liệu | Câu hỏi khi lưu |
|---|---|---|
| `LocalDate` | Ngày trên lịch không gắn timezone | Database giữ đúng ngày không? |
| `LocalDateTime` | Ngày/giờ địa phương, không có offset | Nếu sự kiện diễn ra ở nhiều múi giờ, lấy timezone từ đâu? |
| `Instant` | Một thời điểm trên trục UTC | Cột SQL/provider có giữ đủ độ chính xác cần thiết không? |
| `OffsetDateTime` | Thời điểm kèm offset | Database có giữ offset gốc hay chỉ giữ instant? |
| `ZonedDateTime` | Thời điểm kèm timezone region | Database có lưu được zone ID như `Asia/Ho_Chi_Minh` hay không? |

Ví dụ, PostgreSQL `timestamp with time zone` biểu diễn thời điểm và **không lưu nguyên tên timezone region đã nhập**. Nếu lịch họp phải giữ múi giờ của người đặt để áp dụng quy tắc DST trong tương lai, có thể cần cột `zone_id` riêng, không chỉ một timestamp.

`Duration` và `Period` cũng khác nhau: độ dài thời gian chính xác so với khoảng lịch như “một tháng”. Kiểu SQL `INTERVAL` và mapping của từng provider có thể không bảo toàn mọi cách diễn giải. Với thời hạn nghiệp vụ, lựa chọn schema cần phản ánh ý nghĩa “90 ngày” hay “3 tháng theo lịch”.

### 7.3. Money và các giá trị gồm nhiều thành phần

`BigDecimal` thường dùng để lưu lượng tiền, nhưng “100.00” không đủ mô tả tiền tệ nếu hệ thống hỗ trợ nhiều currency. Thay vì serialize đối tượng `Money` vào chuỗi mơ hồ như `"USD:100.00"`, có thể dùng embeddable trên hai cột:

```java
@Embeddable
public class Money {

    @Column(name = "amount", precision = 19, scale = 4)
    private BigDecimal amount;

    @Column(name = "currency", length = 3)
    private String currency;

    protected Money() {}

    public Money(BigDecimal amount, String currency) {
        this.amount = Objects.requireNonNull(amount);
        this.currency = Objects.requireNonNull(currency);
    }
}

@Entity
public class Payment {

    @Id
    private Long id;

    @Embedded
    private Money total;
}
```

Cách này cho phép truy vấn, index và constraint theo tiền tệ và số tiền. Cần bổ sung quy tắc làm tròn, tỷ giá và số chữ số thập phân theo business; `precision`/`scale` của cột không tự thực thi mọi quy tắc tài chính.

## 8. Kiểu không gian địa lý: geometry/geography

Một ứng dụng giao hàng muốn lưu vùng phục vụ dưới dạng đa giác và tìm cửa hàng nằm trong bán kính khách hàng. Với PostgreSQL + PostGIS, lược đồ có thể dùng:

```sql
CREATE EXTENSION IF NOT EXISTS postgis;

CREATE TABLE delivery_zones (
    id bigint PRIMARY KEY,
    boundary geometry(Polygon, 4326) NOT NULL
);

CREATE INDEX ix_delivery_zones_boundary
    ON delivery_zones USING GIST (boundary);
```

`geometry(Polygon, 4326)` là kiểu đặc thù của PostGIS; `4326` biểu diễn một hệ tọa độ phổ biến. Kích hoạt extension có thể cần quyền administrator/database owner.

Ở tầng Java, có thể dùng kiểu geometry của JTS và tích hợp **Hibernate Spatial** tương thích với phiên bản Hibernate đang chạy. Đây không phải một phần mapping cơ bản độc lập provider của JPA.

Ví dụ SQL không gian:

```sql
SELECT id
FROM delivery_zones
WHERE ST_Contains(
    boundary,
    ST_SetSRID(ST_MakePoint(:longitude, :latitude), 4326)
);
```

Cần hiểu tọa độ và hệ quy chiếu: `ST_MakePoint(x, y)` ở đây dùng **longitude trước, latitude sau**. Những bài toán đo khoảng cách theo mét có thể cần `geography`, chuyển hệ tọa độ hoặc cách tính thích hợp; không nên coi một độ kinh/vĩ là một mét.

Cách đánh giá:

- Chỉ cần lưu cặp tọa độ? Hai cột `latitude`/`longitude` với constraint có thể đủ.
- Cần phép `contains`, `intersects`, khoảng cách, nhiều polygon và spatial index? Native spatial type phù hợp hơn.
- Cần chạy đa database? Xác định công cụ GIS/ORM và SQL của từng database từ đầu; đừng kỳ vọng JPQL chuẩn biểu diễn mọi toán tử không gian.

## 9. Kiểu range, IP, vector và kiểu tự định nghĩa của database

### 9.1. Range thời gian

PostgreSQL có các kiểu như `tsrange`, `tstzrange` và toán tử kiểm tra chồng lấn `&&`. Với bài toán đặt phòng:

```sql
CREATE TABLE reservations (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    room_id bigint NOT NULL,
    slot tstzrange NOT NULL
);

CREATE INDEX ix_reservations_slot
    ON reservations USING GIST (slot);
```

Cột `slot` biểu diễn khoảng thời gian có semantics cận dưới/cận trên; không chỉ là chuỗi chứa hai timestamp. Nếu phải ngăn hai lần đặt cùng phòng chồng lấn, PostgreSQL còn hỗ trợ exclusion constraint với GiST và extension thích hợp:

```sql
CREATE EXTENSION IF NOT EXISTS btree_gist;

ALTER TABLE reservations
ADD CONSTRAINT no_overlapping_reservations
EXCLUDE USING gist (
    room_id WITH =,
    slot WITH &&
);
```

Cách biểu diễn `TimeRange(start, end)` bằng `@Embeddable` trên hai cột JPA tương đối portable hơn, nhưng không tự có operator range và constraint chống chồng lấn mạnh như trên. **Độ phù hợp của kiểu dữ liệu liên quan trực tiếp đến ràng buộc nghiệp vụ**.

### 9.2. Địa chỉ IP và kiểu mạng

PostgreSQL có `inet` và `cidr`, hỗ trợ cú pháp và phép so sánh mạng đặc thù. Một Java field `InetAddress` không bảo đảm được JDBC tự ánh xạ sang `inet` bởi JPA chuẩn.

Các phương án:

- Lưu chuỗi chuẩn hóa khi chỉ hiển thị/tra cứu đơn giản.
- Dùng type mapping provider hoặc JDBC extension nếu cần phép toán subnet.
- Dùng cột/kiểu native và native SQL cho truy vấn IP range ở quy mô lớn.

Converter thành `String` không tự biến một điều kiện JPQL thành phép kiểm tra mạng như operator PostgreSQL chuyên dụng.

### 9.3. Vector và full-text

Một số database có extension cho vector embedding hoặc full-text index, ví dụ kiểu `vector` của pgvector hay `tsvector` của PostgreSQL. Những kiểu này thường có toán tử khoảng cách/tìm kiếm và chiến lược index riêng. Nếu một use case phụ thuộc các toán tử đó, dùng native SQL hoặc API của thư viện hỗ trợ chuyên biệt sẽ hợp lý hơn việc ép toàn bộ phép toán vào `AttributeConverter`.

### 9.4. Domain type và cấu trúc có ràng buộc riêng

SQL domain hoặc user-defined type có thể ràng buộc một ý nghĩa nghiệp vụ ở tầng database. JPA vẫn cần metadata/JDBC binder tương thích. Nếu chỉ lưu/đọc một giá trị chuyển được sang kiểu basic, converter có thể đủ; nếu cần operator, composite structure hay kiểu parameter native, cần provider extension hoặc truy cập SQL chuyên biệt.

## 10. Giới hạn thực sự của `AttributeConverter`

### 10.1. Converter chỉ xử lý một thuộc tính

Interface chuẩn:

```java
public interface AttributeConverter<X, Y> {

    Y convertToDatabaseColumn(X attribute);

    X convertToEntityAttribute(Y dbData);
}
```

`X` là kiểu Java muốn dùng trong entity, `Y` là kiểu đích mà JPA/JDBC có mapping basic thích hợp. Converter **không phải** bộ chuyển đổi tùy ý giữa một object và cả một object graph, nhiều cột hoặc toàn bộ SQL expression.

Những việc converter **không tự làm**:

1. Sinh ra hai cột `amount` và `currency` từ một property `Money`; dùng `@Embeddable` nếu cần nhiều cột.
2. Thiết lập SQL ARRAY/JSONB binder đặc thù chỉ vì nó trả về `String` hoặc `byte[]`.
3. Thêm SQL operators như `@>`, `&&` hay `ST_Contains` vào JPQL.
4. Tạo index, CHECK constraint, trigger hoặc migration cho dữ liệu.
5. Định nghĩa cơ chế dirty checking/mutability của kiểu phức tạp một cách đầy đủ cho mọi provider.

Trong JPA, converter không được áp dụng theo cách tiêu chuẩn tới những thuộc tính có loại mapping như `@Id`, `@Version`, relationship, `@Enumerated` hoặc `@Temporal`; cần đọc yêu cầu phiên bản đặc tả/provider trước khi cố cưỡng ép converter vào các trường hợp đó.

### 10.2. Chi phí của serialization

Serialize JSON, XML hoặc một binary format mang thêm:

- CPU khi đọc và ghi.
- Dung lượng kết quả truyền trên mạng.
- Khả năng lỗi dữ liệu cũ không tương thích với class mới.
- Chi phí đọc lại toàn bộ object khi chỉ cần một trường.
- Rủi ro mất dữ liệu nếu converter nuốt lỗi rồi ghi giá trị mặc định.

Nếu converter không hiểu payload, **nên phát sinh lỗi rõ** và xử lý migration, thay vì âm thầm thay bằng object rỗng. Với dữ liệu không đáng tin, tránh cơ chế deserialize đa hình cho phép tự chỉ định class tùy ý; dùng cấu trúc và kiểu đầu ra có kiểm soát.

## 11. Type system riêng của Hibernate: khi nào cần tới?

Khi `AttributeConverter` không đáp ứng nhu cầu, Hibernate có những extension cho phép điều khiển cách Java value được so sánh, snapshot, bind vào JDBC và trích xuất từ `ResultSet`.

Một số khái niệm:

| Khái niệm Hibernate | Trách nhiệm chính |
|---|---|
| `JavaType` | Cách hiểu một kiểu Java, equality/hash, unwrap/wrap và semantics giá trị |
| `JdbcType` | Cách bind/extract giá trị JDBC với SQL type tương ứng |
| `BasicType` | Phối hợp Java type và JDBC type |
| `MutabilityPlan` | Cách snapshot/copy trạng thái đối tượng mutable, hữu ích cho dirty checking/cache |
| `@JdbcTypeCode` | Chỉ định JDBC type code cho thuộc tính trong các phiên bản Hibernate hỗ trợ |
| `UserType` / custom type | Cơ chế tùy biến sâu hơn, phụ thuộc SPI/version của Hibernate |

Tên API và cách đăng ký có thể khác giữa các phiên bản Hibernate. Không nên sao chép mã custom type của Hibernate 5 vào Hibernate 6 mà cho rằng nó hoạt động nguyên vẹn.

### 11.1. Ví dụ vấn đề dirty checking

Giả sử một entity giữ:

```java
@JdbcTypeCode(SqlTypes.JSON)
private Map<String, Object> preferences;
```

Sau khi load:

```java
profile.getPreferences().put("theme", "light");
```

Đây là **thay đổi trong object hiện có**, không phải gán reference mới. Provider phải có cách biết trạng thái trước và sau khác nhau, thường thông qua snapshot, equality và mutability logic. Nếu mapping hoặc custom type không định nghĩa đúng, cập nhật có thể không được ghi hoặc bị ghi dư.

Một lựa chọn dễ kiểm soát hơn là value object bất biến:

```java
public record Preferences(String theme, boolean notificationsEnabled) {}

profile.setPreferences(new Preferences("light", true));
```

Kể cả như vậy, cần hiểu provider phát hiện thay đổi theo mapping hiện hành và xác nhận hành vi ở đường ghi/đọc thực tế.

### 11.2. Khi nào chọn custom type?

Chỉ nên đầu tư vào custom type khi **nhiều entity cùng phải dùng một kiểu SQL đặc thù** hoặc khi extension sẵn có không đảm bảo đúng semantics. Trường hợp chỉ có một báo cáo sử dụng operator PostgreSQL đặc biệt, native SQL tập trung ở repository có thể rẻ và minh bạch hơn việc xây Type SPI dùng toàn hệ thống.

Khi custom type trở thành thư viện nội bộ, cần quản lý tương thích phiên bản Hibernate, JDBC driver và database; định nghĩa rõ null, equality, mutability, binary/text representation và hành vi serialization.

## 12. Đánh giá hiệu năng và khả năng truy vấn

### 12.1. Không suy đoán từ kiểu cột

Một cột JSONB có index không đảm bảo mọi filter JSON đều nhanh. Index chỉ hữu ích khi operator, đường truy cập, dữ liệu và độ chọn lọc phù hợp. Một cột `TEXT` có thể nhanh khi chỉ đọc theo ID, nhưng kém phù hợp nếu phải lọc hàng triệu hàng theo trường con trong payload.

Cần quan sát:

- **Query count**: ORM có tạo nhiều SELECT khi truy cập association không?
- **Execution plan**: database dùng index, sequential scan, sort hay hash join?
- **Rows read vs rows returned**: lọc ở SQL hay tải lên Java rồi lọc?
- **Serialization cost**: phải parse/serialize bao nhiêu payload?
- **Write amplification**: sửa một phần JSON/array có khiến phải ghi lại cả giá trị không?
- **Index maintenance**: có quá nhiều index khiến insert/update chậm không?
- **Memory và cache**: object lớn có làm persistence context và second-level cache tăng đáng kể?

Ví dụ: nếu một màn hình chỉ cần tên và trạng thái khách hàng, không nhất thiết chọn entity kèm JSON lớn. Dùng projection DTO sẽ giảm dữ liệu truyền và công việc deserialize.

### 12.2. Cân nhắc schema và migration

Khi đổi từ cột `VARCHAR` lưu JSON sang `jsonb`, có thể cần:

1. Kiểm tra mọi giá trị cũ có là JSON hợp lệ hay không.
2. Dọn dữ liệu lỗi, null semantics và giá trị mặc định.
3. Tạo cột mới hoặc chuyển kiểu bằng migration có kiểm soát.
4. Tạo index mới đúng mục đích sử dụng.
5. Triển khai ứng dụng tương thích với cả schema cũ/mới nếu rolling deployment.
6. Đo thời gian khóa bảng, chi phí cập nhật và kế hoạch rollback.

Với enum native hoặc spatial type, migration còn liên quan đến extension, quyền database, thay đổi kiểu cột và cấu hình provider. Không nên để Hibernate tự động `create-drop` schema trên môi trường chứa dữ liệu thật.

## 13. Tiêu chí đánh giá tính portable

Một hệ thống “dùng JPA” không có nghĩa tất cả cách mapping và truy vấn của nó portable như nhau. Có thể đánh giá theo tầng:

| Tầng | Portability thường gặp |
|---|---|
| Java entity và API JPA cơ bản | Tương đối cao giữa các provider tương thích |
| `@Embeddable` / `@ElementCollection` | Tương đối cao, nhưng DDL, naming và SQL generator khác nhau |
| `AttributeConverter` đến basic type | Khá cao nếu đích là JDBC type phổ biến |
| `columnDefinition="jsonb"`, `geometry`, `tstzrange` | Phụ thuộc database |
| Hibernate `@JdbcTypeCode` và custom Type | Phụ thuộc provider/phiên bản/dialect |
| Native SQL với `->>`, `&&`, `ST_Contains` | Phụ thuộc database/extension |
| Index GIN/GiST, exclusion constraint | Phụ thuộc hệ CSDL, phải quản lý migration riêng |

Vì thế, yêu cầu “có thể đổi database” cần cụ thể: đổi PostgreSQL sang MySQL thật sự, hay chỉ chạy nhiều môi trường cùng PostgreSQL? Nếu đổi database là mục tiêu bắt buộc, hãy kiểm tra trên cả hai hệ sớm; tránh chọn extension bản địa chỉ vì tiện ở giai đoạn thử nghiệm.

## 14. Ví dụ ra quyết định trong ứng dụng bán hàng

Một hệ thống bán hàng có bốn thuộc tính mới:

1. `Customer.preferences`: theme, ngôn ngữ, tùy chọn nhận thông báo; thay đổi ít, thường đọc như một khối.
2. `Product.tags`: cần tìm kiếm theo tag, đặt unique theo sản phẩm, thỉnh thoảng thêm/xóa.
3. `DeliveryZone.boundary`: cần tìm cửa hàng phục vụ địa điểm của khách trong không gian địa lý.
4. `Shipment.status`: vài trạng thái có vòng đời ổn định, phải đảm bảo dữ liệu hợp lệ.

### 14.1. Phương án có cơ sở

| Thuộc tính | Phương án khởi đầu | Vì sao |
|---|---|---|
| `preferences` | `@Convert` sang chuỗi nếu chỉ lưu/đọc; JSONB native nếu query key/index quan trọng | Tránh phụ thuộc database không cần thiết; nâng mức hỗ trợ khi use case thực sự cần |
| `tags` | `@ElementCollection` hoặc entity `Tag` | JOIN, index và ràng buộc từng tag rõ ràng |
| `boundary` | PostGIS geometry và Hibernate Spatial/native SQL | Cần toán tử không gian và GiST index |
| `status` | `@Enumerated(EnumType.STRING)` hoặc code converter phù hợp schema | Dễ hiểu, kiểm soát migration khi đổi tên trạng thái |

**Không nên vội dùng một giải pháp cho mọi field đặc thù.** Một JSON converter duy nhất không phù hợp với vùng địa lý cần spatial operator; một kiểu SQL ARRAY không thay thế tốt quan hệ tags nếu cần khóa ngoại và metadata riêng.

### 14.2. Khi thiết kế thay đổi theo yêu cầu

Sau vài tháng, sản phẩm cần tìm khách theo `preferences.language` hàng nghìn lần mỗi phút. Có thể cần expression index, generated column hoặc chuyển thành cột quan hệ riêng, tùy khả năng database. Vì vậy thiết kế ban đầu cần dự liệu khả năng **di chuyển một field quan trọng từ JSON sang cột độc lập**.

Nếu đơn vị kinh doanh đổi vùng phục vụ thành polygon lớn phức tạp và truy vấn khoảng cách thường xuyên, spatial indexing và SRID trở nên quan trọng hơn việc Java code có ít annotation hay không.

Nếu trạng thái vận chuyển được thêm/sửa thường xuyên và phải có bản dịch, quyền chuyển trạng thái, thứ tự hiển thị, bảng `shipment_statuses` có thể phù hợp hơn cả enum Java và native enum.

## 15. Các nhận định dễ nhầm

| Nhận định | Cách hiểu phù hợp |
|---|---|
| “JPA không map được JSON” | JPA chuẩn có converter để lưu JSON như chuỗi; JSON type/query native thường cần provider/dialect extension. |
| “Chỉ cần `columnDefinition` là có JDBC binding đúng” | DDL type và binding/extraction là hai trách nhiệm riêng. |
| “Có `@Convert` là query được field lồng bên trong object” | Converter xử lý giá trị; không tự thêm JSON path/operator vào JPQL. |
| “`@Enumerated(STRING)` đồng nghĩa native enum trong database” | Nó mô tả cách biểu diễn enum, còn SQL type và binder tùy mapping/provider. |
| “Map thành JSONB thì mọi UPDATE chỉ sửa key đã đổi” | ORM có thể cập nhật toàn bộ cột; cần xem SQL thực tế và cú pháp partial update nếu bắt buộc. |
| “`List<String>` tự thành `text[]` vì Java có List” | Collection Java và SQL ARRAY không phải cùng đặc tả ánh xạ JPA. |
| “JSONB nên dùng cho mọi dữ liệu linh hoạt” | Query, constraint, update, schema evolution và index có thể khiến quan hệ chuẩn hóa phù hợp hơn. |
| “Native SQL làm hỏng kiến trúc ORM” | Dùng SQL trực tiếp ở đường truy vấn chuyên biệt là lựa chọn thực tế nếu được quản lý rõ ràng. |
| “Có type extension thì dirty checking mặc nhiên đúng” | Mutable object, snapshot và equality vẫn phải tương thích. |
| “Provider A chạy được thì provider B chắc chắn chạy” | Extension Hibernate, JDBC driver và dialect có thể khác biệt đáng kể. |

## 16. Bài thực hành đề xuất

### Bài 1: So sánh hai cách lưu Preferences

Tạo entity `CustomerProfile` và thử hai phương án độc lập:

- `PreferencesJsonConverter` sang `VARCHAR` hoặc `TEXT`.
- Hibernate 6 `@JdbcTypeCode(SqlTypes.JSON)` với cột `jsonb` của PostgreSQL.

Lưu cùng dữ liệu, đọc lại, thay `theme` rồi xem câu SQL phát ra. Thử lọc theo `theme` ở database và so sánh khả năng index. Không gộp cả hai annotation vào một field để “chắc ăn”; hãy chọn một cấu hình rõ ràng cho từng phương án.

### Bài 2: Đổi cấu trúc JSON

Lưu payload cũ có key `notificationsEnabled`. Sau đó đổi DTO sang tên `allowNotifications` và kiểm tra converter đọc dữ liệu cũ ra sao. Xây dựng chính sách backward compatibility hoặc migration rõ ràng.

### Bài 3: So sánh ARRAY với bảng phụ

Thiết kế bảng `products` chứa mảng tags trong PostgreSQL và thiết kế bảng `product_tags`. Cho mỗi cách:

1. Tìm mọi sản phẩm có tag `"java"`.
2. Ngăn một sản phẩm có tag trùng.
3. Đếm số sản phẩm theo tag.
4. Thêm/xóa một tag mà không đụng dữ liệu ngoài tag đó.
5. Ước lượng độ khó nếu đổi sang database khác.

### Bài 4: Chọn kiểu thời gian đúng nghiệp vụ

Một hệ thống đặt lịch cho phép chọn “9 giờ sáng tại TP. Hồ Chí Minh” và “9 giờ sáng tại Berlin”. Hãy xác định trường nào phải dùng `Instant`, trường nào phải giữ `ZoneId`, và điều gì xảy ra nếu chỉ lưu `LocalDateTime`.

### Bài 5: Đánh giá giới hạn spatial

Thiết kế vùng giao hàng theo bán kính đơn giản và theo polygon có lỗ. Giải thích vì sao một đôi `latitude/longitude` đủ cho vị trí điểm, nhưng polygon và truy vấn `ST_Contains` cần mô hình dữ liệu và index khác.

## 17. Nguyên tắc lựa chọn cuối cùng

Khi gặp một thuộc tính có kiểu dữ liệu đặc thù, hãy đi theo thứ tự:

1. **Xác định ý nghĩa và nhu cầu truy cập.** Chỉ lưu/đọc nguyên khối, hay truy vấn, index và ràng buộc từng thành phần?
2. **Ưu tiên mapping đơn giản và chuẩn nếu đáp ứng được.** Các cột basic, `@Embeddable`, bảng phụ hoặc `AttributeConverter` thường dễ bảo trì.
3. **Chọn kiểu SQL native khi database thực sự tạo lợi ích.** JSONB, ARRAY, geometry, range, vector... phát huy giá trị khi đi kèm operator/index/constraint chuyên dụng.
4. **Kết nối đúng cả Java–ORM–JDBC–SQL.** Annotation DDL không thay thế serialization và JDBC binder; converter không thay thế dialect extension.
5. **Đánh giá vòng đời dữ liệu.** Null, mutability, dirty checking, read/write round-trip, migration và provider upgrade đều quan trọng.
6. **Đo theo use case thực tế.** Số truy vấn, execution plan, serialization, dung lượng và độ trễ quyết định hơn giả định “kiểu native luôn nhanh”.
7. **Ghi rõ mức phụ thuộc công nghệ.** Khi dùng Hibernate extension hoặc PostgreSQL operator, để ranh giới đó nằm ở repository/mapping có chủ đích và được tài liệu hóa.

**Kết luận:** Điểm giới hạn của ánh xạ chuẩn JPA không phải là nơi ORM “hết tác dụng”, mà là nơi cần lựa chọn rõ ràng giữa **tính đơn giản/di động của mô hình Java–quan hệ** và **sức mạnh của kiểu dữ liệu đặc thù tại database**. Một thiết kế tốt chọn công cụ theo hành vi truy cập, bảo đảm đúng nghĩa dữ liệu và chấp nhận có kiểm soát những phụ thuộc mà hiệu năng hoặc nghiệp vụ thực sự cần.
