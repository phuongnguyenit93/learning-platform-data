# JSON và kiểu đặc thù: lựa chọn converter cùng kiểu cột phù hợp

Spring Data JDBC ánh xạ thuộc tính Java sang cột quan hệ thông qua metadata và hệ thống chuyển đổi dữ liệu. Với các kiểu phổ biến như `String`, `Long`, `BigDecimal` hoặc `LocalDate`, framework và JDBC driver thường đã có cách chuyển đổi phù hợp. Nhưng khi domain dùng kiểu riêng, dữ liệu JSON, UUID, enum đặc thù, tiền tệ hoặc kiểu do database cung cấp, cần quyết định rõ **Java type nào được lưu, converter nào chịu trách nhiệm và SQL column type nào biểu diễn dữ liệu đó**.

Ba lựa chọn phải khớp nhau:

1. **Kiểu domain:** ứng dụng muốn thao tác với dữ liệu dưới dạng nào và bảo vệ quy tắc gì?
2. **Converter:** chuyển đổi giữa kiểu domain, kiểu Java trung gian và giá trị JDBC như thế nào?
3. **Kiểu cột:** database lưu dữ liệu bằng kiểu SQL nào, với giới hạn, ràng buộc và khả năng truy vấn gì?

Ví dụ, một thuộc tính `OrderMetadata` có thể là một record Java nhưng được lưu trong cột PostgreSQL `jsonb`. Spring Data JDBC cần converter để chuyển record thành giá trị mà PostgreSQL JDBC driver có thể ghi, và converter đọc để dựng lại record từ giá trị driver trả về.

Không phải mọi dữ liệu phức tạp đều nên lưu thành JSON. Nếu một dữ liệu cần khóa ngoại, join, ràng buộc hoặc cập nhật độc lập, mô hình quan hệ thường phù hợp hơn. JSON hữu ích khi cấu trúc thực sự linh hoạt hoặc được xem như một tài liệu gắn với một aggregate.

## 1. Ba lớp cần phân biệt

Xét một aggregate đơn hàng:

~~~java
@Table("sales_orders")
public class SalesOrder {

    @Id
    private Long id;

    private OrderStatus status;

    private OrderMetadata metadata;
}
~~~

Ở đây có ba lớp khác nhau:

| Lớp | Ví dụ | Câu hỏi cần trả lời |
|---|---|---|
| Domain Java | `OrderMetadata` | Ứng dụng muốn biểu diễn và kiểm soát dữ liệu ra sao? |
| Spring Data JDBC conversion | `OrderMetadata ↔ JdbcValue/PGobject` | Làm sao biến giá trị domain thành dữ liệu JDBC và ngược lại? |
| Database schema | `metadata JSONB` | Database lưu, kiểm tra, lập chỉ mục và truy vấn dữ liệu bằng kiểu nào? |

Một converter đúng nhưng schema sai vẫn gây lỗi. Ví dụ converter ghi chuỗi JSON bằng JDBC type `VARCHAR` trong khi cột PostgreSQL là `jsonb` có thể khiến driver/database từ chối kiểu tham số. Ngược lại, cột `TEXT` có thể nhận chuỗi JSON nhưng database không cung cấp đầy đủ toán tử và index dành cho JSON.

**Converter không tự thay đổi schema.** Việc chọn kiểu cột, độ dài, precision, nullability, constraint và index thuộc về thiết kế schema và migration.

## 2. Khi nào dùng kiểu quan hệ, khi nào dùng JSON?

Hãy bắt đầu từ cách dữ liệu được sử dụng.

| Đặc điểm của dữ liệu | Lựa chọn thường phù hợp |
|---|---|
| Có định danh riêng, được nhiều aggregate tham chiếu | Bảng riêng và khóa ngoại |
| Có vòng đời riêng, cần cập nhật độc lập | Aggregate/bảng riêng |
| Có nhiều quan hệ cần join và ràng buộc | Mô hình quan hệ |
| Có cấu trúc ổn định, ít thuộc tính và thường truy vấn trực tiếp | Các cột quan hệ thông thường |
| Là metadata linh hoạt, ít cần join, luôn thuộc về một aggregate | Cân nhắc JSON column |
| Là snapshot hoặc payload bên ngoài cần giữ nguyên cấu trúc | JSON hoặc TEXT tùy yêu cầu |
| Cần kiểm tra từng trường bằng constraint/index SQL | Cột riêng hoặc JSON với hỗ trợ native phù hợp |

Ví dụ metadata của đơn hàng:

~~~json
{
  "source": "mobile-app",
  "campaign": "summer-2026",
  "attributes": {
    "device": "tablet",
    "locale": "vi-VN"
  }
}
~~~

Nếu `source`, `campaign` và `attributes` chỉ là thông tin bổ sung phục vụ phân tích, thay đổi theo từng kênh tích hợp và không có vòng đời riêng, một cột JSON có thể hợp lý.

Ngược lại, nếu `customerId`, `status`, `createdAt` hoặc `totalAmount` là các trường cốt lõi được lọc, join, ràng buộc và báo cáo thường xuyên, nên giữ chúng thành cột quan hệ rõ ràng.

### 2.1. JSON không phải cách thay thế mọi bảng con

Không nên serialize toàn bộ aggregate thành một chuỗi JSON chỉ để tránh thiết kế bảng:

~~~text
Không nên mặc định:

sales_orders
    id
    entire_order_json   <- customer, products, lines, payments...

Cấu trúc thường rõ hơn:

sales_orders
    id
    customer_id
    status
    metadata_json

sales_order_lines
    order_id
    product_id
    quantity
    unit_price
~~~

Trong Spring Data JDBC, các thành phần con thuộc aggregate có thể được ánh xạ bằng `@MappedCollection` vào bảng riêng. Đây là lựa chọn phù hợp khi cần khóa ngoại, kiểm tra dữ liệu và truy vấn từng dòng. JSON metadata có thể cùng tồn tại với mô hình quan hệ đó.

## 3. Chọn SQL column type theo database

Cùng một nội dung JSON có thể được lưu bằng kiểu cột khác nhau tùy database. Không nên lấy tên kiểu của PostgreSQL rồi áp dụng nguyên xi cho MySQL, SQL Server hoặc Oracle.

| Database | Lựa chọn thường gặp | Điểm cần cân nhắc |
|---|---|---|
| PostgreSQL | `jsonb` hoặc `json` | `jsonb` hỗ trợ toán tử và index tốt cho truy vấn; `json` giữ văn bản JSON đầu vào |
| MySQL | `JSON` | Kiểu native có validation JSON và các hàm truy vấn; khả năng index trường JSON phụ thuộc cách tạo generated column/multi-valued index và phiên bản |
| SQL Server | Thường dùng `NVARCHAR(MAX)` cùng hàm kiểm tra/truy vấn JSON | JSON được biểu diễn bằng văn bản trong các phiên bản truyền thống; cần xem tính năng cụ thể của phiên bản SQL Server |
| Oracle Database | Kiểu JSON tùy phiên bản, thường có thể dùng `VARCHAR2`, `CLOB` hoặc kiểu JSON native ở các bản hỗ trợ | Cú pháp DDL và cách JDBC driver trả dữ liệu phụ thuộc phiên bản |

### 3.1. PostgreSQL: json và jsonb

Hai kiểu thường gặp:

- `json` lưu văn bản JSON đầu vào và giữ định dạng văn bản của nó.
- `jsonb` lưu biểu diễn nhị phân đã phân tích, hỗ trợ truy vấn và index JSON hiệu quả hơn trong nhiều tình huống.

`jsonb` thường là lựa chọn mặc định tốt cho metadata cần truy vấn bằng toán tử JSONB. Nó không bảo toàn thứ tự key hoặc khoảng trắng như văn bản ban đầu; nếu cần lưu payload nguyên bản byte-for-byte, hãy lưu riêng dưới dạng văn bản/binary.

DDL ví dụ:

~~~sql
CREATE TABLE sales_orders (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    status VARCHAR(20) NOT NULL,
    metadata JSONB
);

CREATE INDEX idx_sales_orders_metadata
    ON sales_orders USING GIN (metadata);
~~~

GIN index có thể hỗ trợ các kiểu truy vấn JSONB phù hợp. Không nên tạo index chỉ vì cột có kiểu JSON; hãy dựa trên điều kiện lọc thực tế và kế hoạch thực thi truy vấn.

Ví dụ truy vấn:

~~~sql
-- Lấy giá trị scalar từ JSON
SELECT metadata ->> 'source'
FROM sales_orders
WHERE id = :orderId;

-- Tìm các đơn có metadata chứa một cấu trúc
SELECT id
FROM sales_orders
WHERE metadata @> '{"source":"mobile-app"}'::jsonb;
~~~

Toán tử `->>` trả về text; `->` trả về JSON/JSONB; `@>` kiểm tra containment. Đây là cú pháp PostgreSQL, không phải cú pháp SQL portable cho mọi database.

### 3.2. Lưu JSON dưới dạng TEXT

Có thể lưu JSON trong `TEXT` hoặc `CLOB` nếu ứng dụng chỉ cần ghi/đọc toàn bộ payload:

~~~sql
CREATE TABLE integration_messages (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    payload TEXT NOT NULL
);
~~~

Ưu điểm là đơn giản và dễ tương thích. Nhưng database không nhất thiết kiểm tra JSON hợp lệ, không có cùng toán tử/index native, và ứng dụng phải đảm nhận việc parse/validation. Nếu dùng TEXT, cần xác định rõ lỗi dữ liệu hỏng được phát hiện ở thời điểm nào.

### 3.3. Đừng chọn kiểu cột chỉ dựa trên kiểu Java

Một `String` có thể được lưu vào `VARCHAR(100)`, `TEXT`, `CLOB` hoặc một kiểu vendor-specific. Một object Java có thể được chuyển thành JSON, binary hoặc nhiều cột. Kiểu Java không tự quyết định chính sách lưu trữ.

Schema migration cần là nguồn xác định rõ kiểu cột cuối cùng. Với dự án dùng Flyway/Liquibase, hãy sửa migration theo schema đã chọn thay vì chờ annotation Java tự tạo ra một kiểu SQL mong muốn.

## 4. Converter trong Spring Data JDBC là gì?

Converter là thành phần biến đổi một kiểu dữ liệu sang kiểu khác. Spring Data JDBC sử dụng hệ thống conversion trong quá trình đọc và ghi:

~~~text
Đọc:
Database column
    -> JDBC driver trả Java/JDBC value
    -> ReadingConverter
    -> Domain property

Ghi:
Domain property
    -> WritingConverter
    -> JDBC value
    -> JDBC driver
    -> Database column
~~~

Ví dụ một domain value object:

~~~java
public record EmailAddress(String value) {

    public EmailAddress {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("Email is required");
        }
    }
}
~~~

Nếu lưu trong cột `VARCHAR(320)`, có thể dùng converter:

~~~java
@WritingConverter
public class EmailAddressWritingConverter
        implements Converter<EmailAddress, String> {

    @Override
    public String convert(EmailAddress source) {
        return source.value();
    }
}
~~~

~~~java
@ReadingConverter
public class EmailAddressReadingConverter
        implements Converter<String, EmailAddress> {

    @Override
    public EmailAddress convert(String source) {
        return new EmailAddress(source);
    }
}
~~~

Cặp converter này làm rõ ranh giới giữa domain và database. Trong domain, service nhận `EmailAddress` đã có validation; trong database, giá trị vẫn là một chuỗi thông thường.

### 4.1. Vì sao cần phân biệt ReadingConverter và WritingConverter?

Một converter có thể có hai kiểu nguồn/đích đều là kiểu đơn giản. Spring không phải lúc nào cũng suy ra được hướng chuyển đổi mà ta muốn.

- `@ReadingConverter` đánh dấu chuyển đổi từ giá trị database/JDBC sang kiểu domain.
- `@WritingConverter` đánh dấu chuyển đổi từ kiểu domain sang giá trị được ghi.

Dùng đúng annotation giúp tránh trường hợp converter bị hiểu nhầm chiều hoặc áp dụng cho những chuyển đổi không mong muốn.

Với các cặp converter có kiểu nguồn/đích rõ ràng và không mơ hồ, annotation vẫn là cách thể hiện ý định tốt trong cấu hình Spring Data JDBC.

## 5. Đăng ký custom converter

Trong cấu hình Spring Data JDBC, có thể kế thừa `AbstractJdbcConfiguration` và khai báo danh sách converter tùy chỉnh thông qua `userConverters()`.

~~~java
package com.example.shop.config;

import com.example.shop.order.persistence.OrderMetadataReadingConverter;
import com.example.shop.order.persistence.OrderMetadataWritingConverter;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.List;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.jdbc.repository.config.AbstractJdbcConfiguration;

@Configuration
public class JdbcConfiguration extends AbstractJdbcConfiguration {

    private final ObjectMapper objectMapper;

    public JdbcConfiguration(ObjectMapper objectMapper) {
        this.objectMapper = objectMapper;
    }

    @Override
    protected List<?> userConverters() {
        return List.of(
                new OrderMetadataReadingConverter(objectMapper),
                new OrderMetadataWritingConverter(objectMapper)
        );
    }
}
~~~

Spring Boot thường đã cung cấp `ObjectMapper` nếu ứng dụng dùng Jackson auto-configuration. Nếu dự án không dùng Boot hoặc có cấu hình Jackson riêng, cần cung cấp bean tương ứng.

`AbstractJdbcConfiguration` cung cấp hạ tầng cấu hình Spring Data JDBC và tích hợp các converter do ứng dụng khai báo. Khi ứng dụng đã có một cấu hình JDBC tùy chỉnh khác, nên hợp nhất cấu hình converter vào đó để tránh tạo nhiều nguồn cấu hình khó theo dõi.

Một cách khác là tự khai báo bean `JdbcCustomConversions` khi kiến trúc yêu cầu kiểm soát trực tiếp. Không nên đồng thời override cơ chế mặc định và tạo bean trùng lặp mà không hiểu cách cấu hình của phiên bản đang dùng.

## 6. Ví dụ hoàn chỉnh: lưu domain object vào PostgreSQL jsonb

Ta muốn lưu metadata đơn hàng dưới dạng JSONB, nhưng trong Java vẫn thao tác bằng kiểu domain có cấu trúc.

### 6.1. Domain type

~~~java
package com.example.shop.order.domain;

import java.util.Map;

public record OrderMetadata(
        String source,
        String campaign,
        Map<String, String> attributes
) {
}
~~~

Record này là một giá trị thuộc aggregate đơn hàng. Nó không có ID độc lập và không cần repository riêng.

### 6.2. Aggregate mapping

~~~java
package com.example.shop.order.domain;

import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Column;
import org.springframework.data.relational.core.mapping.Table;

@Table("sales_orders")
public class SalesOrder {

    @Id
    private Long id;

    private String status;

    @Column("metadata")
    private OrderMetadata metadata;

    private SalesOrder() {
    }

    public SalesOrder(String status, OrderMetadata metadata) {
        this.status = status;
        this.metadata = metadata;
    }

    public OrderMetadata getMetadata() {
        return metadata;
    }

    public void updateMetadata(OrderMetadata metadata) {
        this.metadata = metadata;
    }
}
~~~

`@Column("metadata")` chỉ định tên cột. Annotation này **không khai báo rằng cột phải là JSONB**. DDL migration phải tạo đúng kiểu cột.

### 6.3. Converter đọc từ PostgreSQL

PostgreSQL JDBC driver thường biểu diễn `json/jsonb` bằng `org.postgresql.util.PGobject`. Reading converter có thể nhận PGobject và parse nội dung bằng Jackson:

~~~java
package com.example.shop.order.persistence;

import com.example.shop.order.domain.OrderMetadata;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.postgresql.util.PGobject;
import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.ReadingConverter;

@ReadingConverter
public class OrderMetadataReadingConverter
        implements Converter<PGobject, OrderMetadata> {

    private final ObjectMapper objectMapper;

    public OrderMetadataReadingConverter(ObjectMapper objectMapper) {
        this.objectMapper = objectMapper;
    }

    @Override
    public OrderMetadata convert(PGobject source) {
        try {
            return objectMapper.readValue(
                    source.getValue(),
                    OrderMetadata.class
            );
        } catch (Exception exception) {
            throw new IllegalArgumentException(
                    "Cannot read order metadata JSON",
                    exception
            );
        }
    }
}
~~~

Converter này phụ thuộc kiểu của PostgreSQL driver. Nếu dùng database khác hoặc driver trả về `String`/kiểu khác, cần viết converter nhận kiểu thực tế mà driver cung cấp. Không nên giả định mọi JDBC driver đều trả `PGobject`.

### 6.4. Converter ghi sang PostgreSQL

Khi ghi, cần báo cho JDBC rằng giá trị thuộc kiểu SQL `OTHER` để PostgreSQL driver xử lý kiểu vendor-specific. `JdbcValue` cho phép gắn giá trị với JDBC type cụ thể:

~~~java
package com.example.shop.order.persistence;

import com.example.shop.order.domain.OrderMetadata;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.sql.JDBCType;
import org.postgresql.util.PGobject;
import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.WritingConverter;
import org.springframework.data.jdbc.core.mapping.JdbcValue;

@WritingConverter
public class OrderMetadataWritingConverter
        implements Converter<OrderMetadata, JdbcValue> {

    private final ObjectMapper objectMapper;

    public OrderMetadataWritingConverter(ObjectMapper objectMapper) {
        this.objectMapper = objectMapper;
    }

    @Override
    public JdbcValue convert(OrderMetadata source) {
        try {
            PGobject json = new PGobject();
            json.setType("jsonb");
            json.setValue(objectMapper.writeValueAsString(source));

            return JdbcValue.of(json, JDBCType.OTHER);
        } catch (Exception exception) {
            throw new IllegalArgumentException(
                    "Cannot write order metadata JSON",
                    exception
            );
        }
    }
}
~~~

Ở đây:

- Jackson chuyển object Java thành chuỗi JSON.
- `PGobject` mang giá trị cùng tên kiểu PostgreSQL `jsonb`.
- `JdbcValue.of(..., JDBCType.OTHER)` chỉ rõ JDBC type cho giá trị được ghi.
- PostgreSQL driver gửi tham số phù hợp với cột JSONB.

Việc dùng `PGobject` là lựa chọn gắn với PostgreSQL. Với database khác, hãy dùng kiểu tham số và converter tương ứng với driver/database đó.

### 6.5. Dependency và schema

Ví dụ Gradle:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-jdbc'
    implementation 'com.fasterxml.jackson.core:jackson-databind'
    implementation 'org.postgresql:postgresql'
}
~~~

Trong ví dụ này converter tham chiếu trực tiếp `PGobject`, vì vậy driver PostgreSQL phải có mặt trên compile classpath. Nếu chỉ khai báo `runtimeOnly`, mã nguồn converter không thể biên dịch tham chiếu tới lớp đó.

Migration:

~~~sql
CREATE TABLE sales_orders (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    status VARCHAR(20) NOT NULL,
    metadata JSONB
);
~~~

Sau khi đăng ký converter, khi repository đọc aggregate, Spring Data JDBC chuyển giá trị cột thành `OrderMetadata`. Khi lưu aggregate, converter biến `OrderMetadata` thành giá trị JDBC tương thích với JSONB.

### 6.6. Repository và cách sử dụng

~~~java
public interface SalesOrderRepository
        extends CrudRepository<SalesOrder, Long> {
}
~~~

~~~java
OrderMetadata metadata = new OrderMetadata(
        "mobile-app",
        "summer-2026",
        Map.of(
                "device", "tablet",
                "locale", "vi-VN"
        )
);

SalesOrder order = new SalesOrder("DRAFT", metadata);
SalesOrder saved = repository.save(order);

SalesOrder loaded = repository.findById(saved.getId())
        .orElseThrow();

String source = loaded.getMetadata().source();
~~~

Code nghiệp vụ làm việc với kiểu domain; chi tiết PGobject, JSON serialization và JDBC type nằm trong lớp persistence.

## 7. JSON converter không thay thế domain validation

Converter có trách nhiệm chuyển đổi biểu diễn. Nó không nên trở thành nơi duy nhất thực thi mọi quy tắc nghiệp vụ.

Ví dụ:

~~~java
public record OrderMetadata(
        String source,
        String campaign,
        Map<String, String> attributes
) {
    public OrderMetadata {
        if (source == null || source.isBlank()) {
            throw new IllegalArgumentException("Source is required");
        }
        attributes = attributes == null ? Map.of() : Map.copyOf(attributes);
    }
}
~~~

Khi Jackson dựng record, constructor validation có thể được áp dụng. Tuy nhiên, validation quan trọng vẫn nên được tổ chức ở domain/application layer sao cho cả dữ liệu mới lẫn dữ liệu đọc từ persistence đều tuân thủ cùng quy tắc.

Cũng cần quyết định cách xử lý JSON cũ khi schema/domain thay đổi:

- Trường mới có giá trị mặc định hay được phép null?
- Trường cũ không còn dùng có được bỏ qua không?
- Giá trị không hợp lệ làm fail toàn bộ lần đọc hay được chuyển sang trạng thái cần sửa?
- Có cần version trong JSON để hỗ trợ nhiều cấu trúc payload?

Không nên để một thay đổi nhỏ trong record khiến mọi aggregate cũ không thể đọc mà không có kế hoạch migration hoặc tương thích ngược.

## 8. Lựa chọn converter cho các kiểu đặc thù khác

JSON chỉ là một trường hợp. Các kiểu domain đặc thù thường gặp gồm tiền tệ, mã định danh, giá trị enum, UUID và kiểu database-specific.

### 8.1. Value object lưu trong một cột

Ví dụ `OrderCode`:

~~~java
public record OrderCode(String value) {
    public OrderCode {
        if (value == null || !value.matches("ORD-[0-9]{8}")) {
            throw new IllegalArgumentException("Invalid order code");
        }
    }
}
~~~

Có thể chuyển đổi sang `VARCHAR(12)` bằng converter tương tự `EmailAddress`. Lợi ích là domain không truyền chuỗi tự do qua toàn bộ hệ thống; validation được đóng gói trong value object.

Không phải value object nào cũng cần converter. Nếu Spring Data JDBC đã có conversion phù hợp hoặc kiểu Java có thể được ánh xạ trực tiếp, thêm converter chỉ làm tăng cấu hình không cần thiết.

### 8.2. BigDecimal và kiểu DECIMAL/NUMERIC

Tiền hoặc số đo cần độ chính xác thập phân thường dùng `BigDecimal` và cột `DECIMAL(p,s)`/`NUMERIC(p,s)`.

~~~sql
CREATE TABLE invoices (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    total_amount NUMERIC(18, 2) NOT NULL
);
~~~

Chọn `precision` và `scale` theo giới hạn nghiệp vụ. Ví dụ `NUMERIC(18,2)` cho tối đa 18 chữ số tổng cộng và 2 chữ số sau dấu thập phân. Cần quy định cách làm tròn và đơn vị tiền tệ ở domain. Không nên dùng `double`/`float` cho tiền chỉ vì chúng tiện.

### 8.3. UUID

`UUID` có thể được lưu bằng kiểu UUID native của PostgreSQL, binary hoặc chuỗi tùy database. Nếu JDBC driver và Spring Data JDBC đã hỗ trợ conversion trực tiếp, hãy dùng mapping mặc định. Chỉ viết converter khi cần định dạng riêng, tương thích hệ thống cũ hoặc kiểu cột không được hỗ trợ theo cách mong muốn.

Tránh chuyển UUID sang chuỗi tùy tiện rồi quên chuẩn hóa độ dài, chữ hoa/thường hoặc dấu gạch ngang khi tích hợp nhiều hệ thống.

### 8.4. Enum

Enum có thể được lưu bằng tên:

~~~java
public enum OrderStatus {
    DRAFT,
    CONFIRMED,
    CANCELLED
}
~~~

Với cột:

~~~sql
status VARCHAR(20) NOT NULL
~~~

Lưu tên enum dễ đọc, nhưng đổi tên hằng Java có thể ảnh hưởng dữ liệu đã lưu. Nếu cần mã lưu trữ ổn định khác tên enum, hãy dùng converter rõ ràng và quy định migration khi thêm/đổi giá trị.

Với PostgreSQL native enum, cần kiểm soát DDL và kiểu JDBC tương ứng. Không nên cho rằng một enum Java tự động trở thành native enum của mọi database.

### 8.5. Ngày giờ

Các kiểu Java như `LocalDate`, `LocalDateTime`, `Instant` và `OffsetDateTime` biểu diễn những ý nghĩa thời gian khác nhau. Chọn kiểu cột phù hợp với ý nghĩa:

- Ngày lịch không có giờ: `DATE`.
- Thời điểm địa phương không mang offset: `TIMESTAMP`.
- Thời điểm tuyệt đối: thường cân nhắc `Instant` và kiểu timestamp có semantics timezone phù hợp với database.
- Thời gian có offset được giữ như một phần dữ liệu nghiệp vụ: cân nhắc `OffsetDateTime` và khả năng lưu offset của database.

Đừng tự thêm converter chỉ vì tên Java và SQL khác nhau. Kiểm tra hỗ trợ mặc định của phiên bản Spring Data JDBC và driver trước; converter chỉ cần khi mapping mặc định không diễn đạt đúng semantics.

### 8.6. Kiểu nhị phân và nội dung lớn

Ảnh, file hoặc payload nhị phân có thể được lưu bằng `BLOB`/`BYTEA`/kiểu binary tương ứng, nhưng cần cân nhắc kích thước, backup, streaming và hiệu năng. Với file lớn, object storage thường phù hợp hơn; database giữ metadata và URI/ID tham chiếu.

Không nên serialize dữ liệu nhị phân thành Base64 trong JSON nếu không có lý do cụ thể, vì nó làm tăng kích thước và khiến truy vấn nội dung khó khăn.

## 9. Khi nào cần JdbcValue?

Thông thường converter chỉ cần trả về một kiểu Java mà JDBC driver hiểu. Nhưng có lúc cùng một Java value có thể tương ứng với nhiều SQL type khác nhau, hoặc driver cần biết chính xác JDBC type.

`JdbcValue` cho phép trả về **giá trị cùng JDBC type**:

~~~java
return JdbcValue.of(value, JDBCType.OTHER);
~~~

Ví dụ:

| Tình huống | Vì sao cần chỉ rõ JDBC type? |
|---|---|
| PostgreSQL JSONB | Cần xử lý kiểu vendor-specific thay vì tham số VARCHAR thông thường |
| Kiểu database đặc thù | Driver cần biết kiểu SQL cụ thể để bind tham số |
| Một kiểu Java dùng cho nhiều SQL type | Cần phân biệt cách bind tại thời điểm ghi |

Không nên bọc mọi giá trị trong `JdbcValue` nếu mapping mặc định đã hoạt động đúng. Chỉ dùng khi có yêu cầu thực tế về JDBC type hoặc driver.

Cũng cần phân biệt:

- **SQL column type** là kiểu đã khai báo trong DDL.
- **JDBC type** là loại tham số mà JDBC dùng khi bind/đọc dữ liệu.
- **Java type** là kiểu đối tượng trong ứng dụng.

Ba loại có liên quan nhưng không phải lúc nào cũng cùng tên hoặc cùng hệ phân loại. PostgreSQL `jsonb` là ví dụ: kiểu SQL vendor-specific, JDBC thường được xử lý qua `Types.OTHER` và Java driver value có thể là `PGobject`.

## 10. Truy vấn JSON và converter là hai vấn đề khác nhau

Converter giúp ánh xạ thuộc tính khi Spring Data JDBC đọc/ghi aggregate. Nó không tự tạo ra một API truy vấn JSON portable.

Nếu cần truy vấn một thuộc tính JSON trong PostgreSQL, có thể dùng SQL tường minh:

~~~java
@Repository
public class SalesOrderMetadataQueries {

    private final NamedParameterJdbcTemplate jdbc;

    public SalesOrderMetadataQueries(NamedParameterJdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public List<Long> findMobileOrders() {
        String sql = """
            SELECT id
            FROM sales_orders
            WHERE metadata ->> 'source' = :source
            """;

        return jdbc.query(
                sql,
                Map.of("source", "mobile-app"),
                (rs, rowNum) -> rs.getLong("id")
        );
    }
}
~~~

Đoạn SQL sử dụng cú pháp JSONB PostgreSQL. Khi chạy trên MySQL hoặc SQL Server, cần viết truy vấn theo hàm JSON của database tương ứng.

Nếu truy vấn JSON là phần quan trọng của nghiệp vụ, hãy thiết kế index và query từ đầu. Đừng giả định rằng chỉ cần converter là Spring Data JDBC có thể tự suy ra mọi truy vấn JSON cần thiết.

## 11. Null, giá trị thiếu và JSON schema evolution

Một thuộc tính JSON có thể rơi vào nhiều trạng thái khác nhau:

1. Cột SQL là `NULL`: không có tài liệu metadata.
2. Cột có JSON `null`: tài liệu tồn tại nhưng giá trị JSON là null.
3. Object JSON không có một key: trường đó chưa được cung cấp.
4. Key tồn tại với giá trị rỗng: ví dụ chuỗi `""` hoặc object `{}`.

Các trạng thái này không nhất thiết tương đương. Cần quyết định semantics trong domain và DDL.

Ví dụ:

~~~sql
metadata JSONB NULL
~~~

Nếu metadata là bắt buộc:

~~~sql
metadata JSONB NOT NULL
    DEFAULT '{}'::jsonb
~~~

Giá trị mặc định `{}` chỉ phù hợp khi object rỗng mang ý nghĩa hợp lệ. Không nên dùng default để che việc hệ thống chưa cung cấp dữ liệu bắt buộc.

Khi cấu trúc JSON thay đổi theo thời gian, có thể thêm trường version:

~~~json
{
  "schemaVersion": 2,
  "source": "mobile-app",
  "campaign": "summer-2026"
}
~~~

Converter có thể đọc nhiều phiên bản và chuyển thành domain model hiện tại. Với payload lớn hoặc nhiều producer, cân nhắc tách bước deserialize/version migration thành một thành phần chuyên trách thay vì dồn mọi logic vào converter.

## 12. Kiểm tra converter với database thật

Converter có thể chạy tốt trong unit test nhưng vẫn sai khi JDBC driver thực sự bind kiểu cột. Đặc biệt với JSONB, cần kiểm tra bằng database và driver đúng loại.

Một số kiểm tra có giá trị:

- Ghi một object domain rồi đọc lại, so sánh giá trị sau round-trip.
- Kiểm tra cột SQL có kiểu đúng trong schema.
- Kiểm tra null, JSON rỗng và dữ liệu có ký tự Unicode.
- Kiểm tra JSON không hợp lệ hoặc thiếu trường bắt buộc.
- Kiểm tra query native JSON và index trên database mục tiêu.
- Kiểm tra migration khi JSON schema thay đổi.
- Kiểm tra ứng dụng khởi động với đúng dependency scope của JDBC driver.

Integration test với Testcontainers PostgreSQL có thể giúp xác minh chính xác cách PG JDBC driver trả `PGobject` và bind `JDBCType.OTHER`. H2 hoặc mock JDBC không nhất thiết mô phỏng được hành vi JSONB của PostgreSQL.

Không nên chỉ kiểm tra rằng `ObjectMapper.writeValueAsString(...)` sinh chuỗi hợp lệ. Mục tiêu là xác nhận **database nhận đúng kiểu, lưu được và đọc lại thành đúng domain value**.

## 13. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| PostgreSQL báo cột JSONB nhưng tham số là VARCHAR | Converter bind chuỗi bằng JDBC type không phù hợp | Dùng kiểu JDBC/PGobject phù hợp như `JdbcValue` với `JDBCType.OTHER` |
| Không đọc được cột JSON | Driver trả `PGobject` nhưng converter chỉ nhận `String` | Viết converter theo kiểu thực tế driver trả về |
| Không biên dịch được import `PGobject` | PostgreSQL driver chỉ nằm ở runtime classpath | Đưa driver vào compile classpath khi converter tham chiếu lớp đó |
| Converter không được áp dụng | Chưa đăng ký trong JDBC custom conversions hoặc sai hướng | Kiểm tra `userConverters()` và annotation reading/writing |
| JSON parse lỗi sau khi deploy | Dữ liệu cũ không còn tương thích với domain mới | Xác định version, migration và chiến lược tương thích ngược |
| Query JSON chậm | Thiếu index hoặc truy vấn không tận dụng index | Xem execution plan, chọn GIN/expression index phù hợp |
| JSON chứa nhiều quan hệ nghiệp vụ | Đang dùng JSON thay cho mô hình relational | Tách thành bảng/aggregate và tham chiếu bằng ID |
| Converter hoạt động ở test nhưng lỗi production | Database/driver khác nhau | Test với đúng database và driver mục tiêu |

### 13.1. Một số nguyên tắc bảo trì

- Giữ converter nhỏ, chỉ chuyển đổi biểu diễn dữ liệu.
- Đưa validation nghiệp vụ vào domain object hoặc application layer.
- Đặt tên converter theo cả kiểu domain và hướng đọc/ghi.
- Đăng ký converter ở một nơi cấu hình JDBC rõ ràng.
- Dùng kiểu SQL có semantics đúng với dữ liệu, không chỉ kiểu dễ bind nhất.
- Có migration khi thay đổi column type, JSON shape hoặc enum code.
- Kiểm tra driver thật cho kiểu vendor-specific.
- Không serialize toàn bộ aggregate graph vào một JSON column để né thiết kế quan hệ.

## 14. Quy trình quyết định từ domain type đến column type

Khi thêm một kiểu dữ liệu mới, hãy lần lượt trả lời:

**Bước 1 — Dữ liệu có phải một entity/aggregate riêng?**

Nếu có ID, vòng đời độc lập, được tham chiếu hoặc cần truy vấn/join riêng, hãy cân nhắc bảng riêng. Đừng bắt đầu bằng JSON converter.

**Bước 2 — Nếu là value object, có thể ánh xạ trực tiếp không?**

Nếu kiểu Java và JDBC driver đã hỗ trợ, dùng mapping mặc định. Nếu cần bảo vệ semantics hoặc lưu thành một kiểu đơn giản khác, viết converter.

**Bước 3 — Dữ liệu có thực sự cần JSON?**

Chọn JSON khi cấu trúc linh hoạt, thuộc về một aggregate và truy vấn quan hệ sâu không phải nhu cầu chính. Nếu cần constraint và join trên từng thuộc tính, ưu tiên cột riêng.

**Bước 4 — Database mục tiêu có kiểu phù hợp nào?**

Chọn `jsonb`, `JSON`, `TEXT`, `CLOB`, `DECIMAL`, `UUID` hoặc kiểu vendor-specific theo database, phiên bản và yêu cầu query.

**Bước 5 — Driver trả/nhận kiểu Java nào?**

Xem tài liệu driver và kiểm tra integration. Đừng mặc định mọi database đều trả JSON dưới dạng `String`.

**Bước 6 — Converter có cần chỉ rõ JDBC type không?**

Nếu driver cần kiểu bind đặc biệt, dùng `JdbcValue`. Nếu không, giữ converter đơn giản.

**Bước 7 — Schema và converter được triển khai cùng nhau ra sao?**

Migration tạo cột đúng kiểu; converter đăng ký cùng phiên bản code; dữ liệu cũ được xử lý theo kế hoạch tương thích.

Luồng tổng hợp:

~~~text
Domain requirement
       |
       v
Chọn entity / aggregate / value object
       |
       v
Dữ liệu cần quan hệ hay JSON/binary?
       |
       +---- Relational columns / child table
       |             |
       |             v
       |       SQL types + keys + constraints
       |
       +---- JSON / vendor-specific type
                     |
                     v
              Chọn SQL column type
                     |
                     v
             Kiểm tra JDBC driver value
                     |
                     v
          ReadingConverter / WritingConverter
                     |
                     v
          JdbcValue nếu cần JDBC type rõ ràng
                     |
                     v
          Migration + integration verification
~~~

## 15. Bài tập tự suy luận

**Tình huống A — EmailAddress:** Ứng dụng muốn domain dùng `EmailAddress`, database có cột `VARCHAR(320)`. Có cần lưu JSON không?

**Gợi ý:** Không. Đây là value object biểu diễn một giá trị đơn; converter sang/về `String` thường phù hợp.

**Tình huống B — Metadata chiến dịch:** Mỗi đơn có các thuộc tính bổ sung khác nhau theo kênh bán hàng; ít join và cần giữ snapshot. Nên chọn gì?

**Gợi ý:** Cân nhắc JSON column. Nếu dùng PostgreSQL và cần query theo key, `jsonb` thường phù hợp hơn `TEXT`.

**Tình huống C — Dòng hàng:** Mỗi dòng có product, quantity, unit price; cần foreign key, constraint và báo cáo. Có nên serialize toàn bộ danh sách vào JSON?

**Gợi ý:** Thông thường không. Đây là cấu trúc quan hệ cốt lõi, có thể ánh xạ bằng `@MappedCollection` và bảng con.

**Tình huống D — PostgreSQL JSONB:** Converter ghi JSON string nhưng database báo tham số có kiểu VARCHAR. Cần xem phần nào?

**Gợi ý:** Kiểm tra JDBC type khi bind và giá trị driver-specific. Có thể dùng `PGobject` với type `jsonb` và `JdbcValue.of(..., JDBCType.OTHER)`.

**Tình huống E — Đổi cấu trúc metadata:** Bản mới đổi tên key nhưng các đơn cũ vẫn còn dữ liệu theo key cũ. Có nên chỉ sửa record Java?

**Gợi ý:** Cần chính sách tương thích/migration hoặc converter đọc nhiều phiên bản. Schema JSON linh hoạt không có nghĩa dữ liệu lịch sử tự chuyển đổi.

## 16. Ghi nhớ

| Thành phần | Trách nhiệm |
|---|---|
| Domain type/value object | Diễn đạt ý nghĩa và validation trong ứng dụng |
| `@ReadingConverter` | Chuyển giá trị từ JDBC/database thành domain type |
| `@WritingConverter` | Chuyển domain type thành giá trị để ghi |
| `JdbcValue` | Mang giá trị cùng JDBC type khi cần chỉ định rõ |
| JDBC driver | Chuyển đổi và bind kiểu theo database cụ thể |
| SQL column type | Quyết định cách database lưu, kiểm tra và truy vấn |
| Migration | Tạo/thay đổi schema theo thiết kế |
| Integration test | Xác nhận round-trip với database và driver thật |

**Lựa chọn tốt bắt đầu từ semantics của dữ liệu.** Hãy giữ entity và quan hệ nghiệp vụ ở mô hình relational; dùng JSON cho metadata hoặc payload thực sự linh hoạt; dùng converter để bảo toàn kiểu domain; và chọn SQL/JDBC type phù hợp với database cùng driver. Khi ba lớp domain, converter và schema được thiết kế đồng bộ, Spring Data JDBC có thể giữ code nghiệp vụ rõ ràng mà vẫn tận dụng đúng khả năng của database.
