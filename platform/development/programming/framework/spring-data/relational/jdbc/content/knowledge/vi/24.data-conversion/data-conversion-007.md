# Chuyển đổi JSON, UUID hoặc kiểu đặc thù của driver

Trong **Spring Data Relational JDBC**, dữ liệu của entity được ánh xạ sang các giá trị mà JDBC driver có thể ghi và đọc. Những kiểu phổ biến như chuỗi, số, boolean và ngày giờ thường đã có chuyển đổi mặc định. Nhưng ứng dụng thực tế còn gặp kiểu JSON/JSONB, UUID, enum riêng của database hoặc object do JDBC driver cung cấp.

Để xử lý các kiểu này, Spring Data JDBC dùng **custom conversions**. Một converter đọc chuyển giá trị JDBC thành kiểu Java của domain; một converter ghi chuyển kiểu Java thành giá trị mà JDBC driver có thể bind vào câu SQL. Với một số driver, chỉ chuyển sang String hoặc byte[] là chưa đủ: cần chỉ định JDBC type hoặc tạo đúng object đặc thù của driver.

Bài này dùng PostgreSQL làm ví dụ chính, vì driver cung cấp PGobject để biểu diễn các kiểu như jsonb và enum tùy chỉnh. Các nguyên tắc cũng áp dụng cho database khác, nhưng kiểu Java/driver wrapper và JDBC type cần điều chỉnh theo driver thực tế.

## 1. Luồng chuyển đổi trong Spring Data JDBC

Khi ghi aggregate, Spring Data JDBC đọc mapping metadata của entity, chuyển từng property sang giá trị JDBC rồi bind vào statement. Khi đọc, nó nhận các giá trị từ ResultSet, chuyển chúng về kiểu property Java và tạo object.

```text
Ghi dữ liệu
Domain object
    │
    ▼
Mapping metadata
    │
    ▼
Writing converter
    │
    ▼
JDBC value / driver-specific object
    │
    ▼
PreparedStatement ─────► Database

Đọc dữ liệu
Database ─────► ResultSet
                  │
                  ▼
             JDBC value / driver object
                  │
                  ▼
             Reading converter
                  │
                  ▼
             Domain object
```

Ví dụ một property Java kiểu EventPayload có thể được lưu vào cột PostgreSQL jsonb. Spring Data JDBC cần biết:

- Khi ghi, cách serialize EventPayload thành JSON và gửi cho driver như một giá trị JSONB.
- Khi đọc, cách lấy nội dung JSON từ object driver trả về và deserialize thành EventPayload.

Custom converter xử lý việc chuyển đổi kiểu. Nó không tự tạo cột, thêm constraint hoặc thay đổi schema. Database schema vẫn phải được quản lý bằng migration/DDL.

## 2. Converter đọc và converter ghi

Spring Data dùng hai annotation để xác định hướng chuyển đổi:

| Annotation | Hướng | Ví dụ |
| --- | --- | --- |
| `@WritingConverter` | Kiểu domain Java → kiểu JDBC/driver | EventPayload → PGobject |
| `@ReadingConverter` | Kiểu JDBC/driver → kiểu domain Java | PGobject → EventPayload |

Khai báo hướng rõ ràng đặc biệt quan trọng khi hai kiểu đều đơn giản, chẳng hạn String và UUID. Nếu không đánh dấu, Spring có thể khó xác định converter dùng cho đọc hay ghi.

Ví dụ tổng quát:

```java
@WritingConverter
public class DomainValueWritingConverter
        implements Converter<DomainValue, String> {

    @Override
    public String convert(DomainValue source) {
        return source.value();
    }
}

@ReadingConverter
public class DomainValueReadingConverter
        implements Converter<String, DomainValue> {

    @Override
    public DomainValue convert(String source) {
        return new DomainValue(source);
    }
}
```

Converter<S, T> của Spring Core mô tả chuyển đổi từ S sang T. Converter nên tập trung vào chuyển đổi dữ liệu; validation nghiệp vụ, quyền truy cập và logic transaction thuộc tầng domain/service.

## 3. Đăng ký custom conversion với Spring Data JDBC

Một cách tiêu chuẩn là kế thừa AbstractJdbcConfiguration và override userConverters():

```java
import java.util.List;

import com.fasterxml.jackson.databind.ObjectMapper;
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
                new EventPayloadWritingConverter(objectMapper),
                new EventPayloadReadingConverter(objectMapper)
        );
    }
}
```

Spring Data JDBC dùng các converter này để xây dựng JdbcCustomConversions và tích hợp với mapping converter. Trong ứng dụng Spring Boot, ObjectMapper thường được cấu hình sẵn khi có Jackson trên classpath; nếu dự án tự cấu hình JDBC infrastructure, hãy bảo đảm chỉ có một cấu hình mapping/conversion nhất quán.

Nếu dự án đã có class kế thừa AbstractJdbcConfiguration, hãy thêm converter vào userConverters() hiện tại. Tránh tạo nhiều cấu hình cạnh tranh cùng định nghĩa mapping context/conversions. Cũng không cần tạo repository implementation chỉ để đăng ký converter.

## 4. Chuyển đổi JSON/JSONB với PostgreSQL

PostgreSQL có hai kiểu cột JSON thường gặp:

- json: lưu văn bản JSON và giữ nguyên biểu diễn đầu vào.
- jsonb: lưu dạng nhị phân đã phân tích, hỗ trợ các toán tử và index JSONB hiệu quả hơn trong nhiều truy vấn.

JDBC không định nghĩa một kiểu Java chuẩn chung cho JSON. PostgreSQL JDBC driver cung cấp org.postgresql.util.PGobject để biểu diễn kiểu dữ liệu đặc thù của PostgreSQL. Với cột jsonb, có thể tạo PGobject có type là jsonb và value là chuỗi JSON.

### 4.1. Domain type và schema

Một kiểu dữ liệu domain:

```java
import java.util.Map;

public record EventPayload(
        String eventType,
        Map<String, Object> attributes
) {}
```

Entity:

```java
import java.util.UUID;

import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Table;

@Table("event_record")
public record EventRecord(
        @Id Long id,
        UUID correlationId,
        EventPayload payload
) {}
```

DDL PostgreSQL:

```sql
CREATE TABLE event_record (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    correlation_id UUID NOT NULL,
    payload JSONB NOT NULL
);
```

EventPayload là kiểu Java riêng của ứng dụng; payload là cột JSONB. correlation_id dùng kiểu UUID native của PostgreSQL.

### 4.2. Converter ghi JSONB

Converter serialize domain object thành JSON rồi đóng gói vào PGobject:

```java
import java.sql.JDBCType;
import java.sql.SQLException;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.postgresql.util.PGobject;
import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.WritingConverter;
import org.springframework.data.jdbc.core.mapping.JdbcValue;

@WritingConverter
public class EventPayloadWritingConverter
        implements Converter<EventPayload, JdbcValue> {

    private final ObjectMapper objectMapper;

    public EventPayloadWritingConverter(ObjectMapper objectMapper) {
        this.objectMapper = objectMapper;
    }

    @Override
    public JdbcValue convert(EventPayload source) {
        try {
            PGobject json = new PGobject();
            json.setType("jsonb");
            json.setValue(objectMapper.writeValueAsString(source));

            return JdbcValue.of(json, JDBCType.OTHER);
        } catch (JsonProcessingException | SQLException ex) {
            throw new IllegalArgumentException(
                    "Cannot serialize EventPayload as PostgreSQL jsonb",
                    ex
            );
        }
    }
}
```

Converter dùng hai thành phần:

- PGobject đặt kiểu PostgreSQL là jsonb và chứa chuỗi JSON đã serialize.
- JdbcValue.of(value, JDBCType.OTHER) cung cấp cả giá trị và JDBC type để Spring bind đúng loại tham số. OTHER thường được dùng cho kiểu riêng của database; xác nhận driver/dialect thực tế nếu driver yêu cầu cách bind khác.

PGobject.setValue có thể ném SQLException; Jackson có thể ném lỗi serialize. Ví dụ chuyển lỗi thành unchecked exception để thao tác ghi thất bại rõ ràng. Không nên âm thầm trả JSON rỗng hoặc null khi serialize lỗi, vì điều đó có thể làm mất dữ liệu.

### 4.3. Converter đọc JSONB

PostgreSQL JDBC driver thường trả PGobject khi đọc cột JSON/JSONB bằng getObject. Converter đọc lấy nội dung rồi deserialize:

```java
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.postgresql.util.PGobject;
import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.ReadingConverter;

@ReadingConverter
public class EventPayloadReadingConverter
        implements Converter<PGobject, EventPayload> {

    private final ObjectMapper objectMapper;

    public EventPayloadReadingConverter(ObjectMapper objectMapper) {
        this.objectMapper = objectMapper;
    }

    @Override
    public EventPayload convert(PGobject source) {
        String json = source.getValue();
        if (json == null) {
            return null;
        }

        try {
            return objectMapper.readValue(json, EventPayload.class);
        } catch (JsonProcessingException ex) {
            throw new IllegalArgumentException(
                    "Cannot deserialize PostgreSQL jsonb as EventPayload",
                    ex
            );
        }
    }
}
```

Converter đọc và ghi phải được đăng ký cùng nhau để mapping hoạt động theo cả hai chiều. Nếu dữ liệu trong database không phải JSON hợp lệ hoặc không khớp schema domain hiện tại, lỗi deserialize cần được thể hiện rõ để nhóm phát triển xử lý migration/compatibility.

### 4.4. Lưu và đọc qua repository

Repository:

```java
import org.springframework.data.repository.CrudRepository;

public interface EventRecordRepository
        extends CrudRepository<EventRecord, Long> {
}
```

Ghi:

```java
EventPayload payload = new EventPayload(
        "ORDER_CONFIRMED",
        Map.of("source", "checkout", "priority", 2)
);

EventRecord event = new EventRecord(
        null,
        UUID.randomUUID(),
        payload
);

EventRecord saved = repository.save(event);
```

Đọc:

```java
EventRecord loaded = repository.findById(saved.id())
        .orElseThrow();

String eventType = loaded.payload().eventType();
```

Repository vẫn làm việc với entity và aggregate như bình thường. Converter đảm nhiệm phần chuyển đổi EventPayload ↔ PGobject; service không cần tự serialize JSON trong mọi lần gọi repository.

### 4.5. Truy vấn thuộc tính JSONB

PostgreSQL có toán tử để truy vấn JSONB. Ví dụ:

```sql
SELECT id, correlation_id, payload
FROM event_record
WHERE payload ->> 'eventType' = 'ORDER_CONFIRMED';
```

Hoặc truy vấn theo thuộc tính lồng:

```sql
SELECT id
FROM event_record
WHERE payload -> 'attributes' ->> 'source' = 'checkout';
```

Nếu dùng Spring Data JDBC @Query, SQL phải theo cú pháp PostgreSQL và mapping result phải trả các cột phù hợp entity/DTO. Converter chỉ chuyển kiểu cột JSONB; nó không tự tạo predicate JSON hoặc biến tên thuộc tính JSON thành query method property.

Nếu một thuộc tính JSON được lọc/sắp xếp thường xuyên, cân nhắc expression index hoặc cột quan hệ riêng. Không nên chuyển toàn bộ dữ liệu có cấu trúc quan hệ sang JSON chỉ để tránh khai báo entity.

## 5. UUID: dùng kiểu native hay biểu diễn chuỗi?

UUID có thể được lưu theo nhiều cách:

| Database representation | Ví dụ kiểu cột | Java representation |
| --- | --- | --- |
| UUID native | PostgreSQL UUID | java.util.UUID |
| Chuỗi có dấu gạch nối | CHAR(36) hoặc VARCHAR(36) | UUID ↔ String |
| 16 byte nhị phân | BINARY(16) hoặc kiểu binary tương ứng | UUID ↔ byte[] |

### 5.1. PostgreSQL UUID native

PostgreSQL có kiểu uuid, và PostgreSQL JDBC driver hỗ trợ chuyển đổi giữa kiểu này với java.util.UUID. Khi dùng driver tương thích, thường không cần custom converter:

```sql
CREATE TABLE api_request (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    request_id UUID NOT NULL UNIQUE
);
```

Entity:

```java
@Table("api_request")
public record ApiRequest(
        @Id Long id,
        UUID requestId
) {}
```

Nên ưu tiên kiểu UUID native nếu database hỗ trợ và ứng dụng không có yêu cầu tương thích đặc biệt. Cách này tránh tự định nghĩa định dạng chuỗi hoặc thứ tự byte.

### 5.2. UUID lưu dưới dạng VARCHAR(36)

Nếu schema hiện có lưu UUID dưới dạng chuỗi, có thể dùng converter:

```java
import java.util.UUID;

import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.WritingConverter;

@WritingConverter
public class UuidWritingConverter
        implements Converter<UUID, String> {

    @Override
    public String convert(UUID source) {
        return source.toString();
    }
}
```

Converter đọc:

```java
import java.util.UUID;

import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.ReadingConverter;

@ReadingConverter
public class UuidReadingConverter
        implements Converter<String, UUID> {

    @Override
    public UUID convert(String source) {
        return UUID.fromString(source);
    }
}
```

Schema:

```sql
CREATE TABLE api_request (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    request_id VARCHAR(36) NOT NULL UNIQUE
);
```

Đăng ký cả hai converter trong userConverters(). Không đăng ký converter chuỗi này nếu cùng property đang dùng UUID native và driver đã hỗ trợ đúng kiểu. Một converter toàn cục UUID ↔ String sẽ tác động tới mọi property UUID được mapping, nên chỉ dùng khi schema của ứng dụng thống nhất theo dạng chuỗi.

Nếu cần chỉ áp dụng cho một property hoặc một loại UUID cụ thể, có thể tạo domain wrapper như ExternalRequestId rồi viết converter cho wrapper đó. Cách này tránh thay đổi mapping của mọi UUID trong ứng dụng.

### 5.3. UUID lưu dưới dạng BINARY(16)

Một số schema lưu UUID thành 16 byte để giảm dung lượng so với chuỗi 36 ký tự. Khi đó cần thống nhất cách chuyển hai phần 64-bit của UUID thành byte:

```java
import java.nio.ByteBuffer;
import java.util.UUID;

public final class UuidBytes {

    private UuidBytes() {
    }

    public static byte[] toBytes(UUID uuid) {
        return ByteBuffer.allocate(16)
                .putLong(uuid.getMostSignificantBits())
                .putLong(uuid.getLeastSignificantBits())
                .array();
    }

    public static UUID fromBytes(byte[] bytes) {
        if (bytes.length != 16) {
            throw new IllegalArgumentException(
                    "A UUID must contain exactly 16 bytes");
        }

        ByteBuffer buffer = ByteBuffer.wrap(bytes);
        return new UUID(buffer.getLong(), buffer.getLong());
    }
}
```

Có thể bọc các hàm này trong @WritingConverter và @ReadingConverter. Nếu cần ép JDBC type khi ghi:

```java
import java.sql.JDBCType;
import java.util.UUID;
import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.WritingConverter;
import org.springframework.data.jdbc.core.mapping.JdbcValue;

@WritingConverter
public class UuidBinaryWritingConverter
        implements Converter<UUID, JdbcValue> {

    @Override
    public JdbcValue convert(UUID source) {
        return JdbcValue.of(
                UuidBytes.toBytes(source),
                JDBCType.BINARY
        );
    }
}
```

Đọc có thể dùng converter byte[] → UUID:

```java
import java.util.UUID;
import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.ReadingConverter;

@ReadingConverter
public class UuidBinaryReadingConverter
        implements Converter<byte[], UUID> {

    @Override
    public UUID convert(byte[] source) {
        return UuidBytes.fromBytes(source);
    }
}
```

Thứ tự byte phải thống nhất với mọi ứng dụng ghi/đọc cùng cột. Một số hệ thống cũ có thể dùng byte order khác hoặc hoán đổi nhóm byte; không thể chỉ nhìn thấy cột 16 byte rồi giả định nó dùng cùng quy ước ByteBuffer ở trên. Trước khi chuyển đổi schema, hãy kiểm tra dữ liệu thực tế bằng các UUID đã biết.

## 6. Kiểu enum riêng của PostgreSQL

PostgreSQL cho phép định nghĩa enum type trong schema:

```sql
CREATE TYPE order_state AS ENUM (
    'DRAFT',
    'CONFIRMED',
    'CANCELLED'
);

CREATE TABLE purchase_order (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    state order_state NOT NULL
);
```

Trong Java:

```java
public enum OrderState {
    DRAFT,
    CONFIRMED,
    CANCELLED
}
```

PostgreSQL JDBC driver có thể biểu diễn enum database qua PGobject. Converter ghi:

```java
import java.sql.JDBCType;
import java.sql.SQLException;

import org.postgresql.util.PGobject;
import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.WritingConverter;
import org.springframework.data.jdbc.core.mapping.JdbcValue;

@WritingConverter
public class OrderStateWritingConverter
        implements Converter<OrderState, JdbcValue> {

    @Override
    public JdbcValue convert(OrderState source) {
        try {
            PGobject value = new PGobject();
            value.setType("order_state");
            value.setValue(source.name());
            return JdbcValue.of(value, JDBCType.OTHER);
        } catch (SQLException ex) {
            throw new IllegalArgumentException(
                    "Cannot convert OrderState to PostgreSQL enum",
                    ex
            );
        }
    }
}
```

Converter đọc:

```java
import org.postgresql.util.PGobject;
import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.ReadingConverter;

@ReadingConverter
public class OrderStateReadingConverter
        implements Converter<PGobject, OrderState> {

    @Override
    public OrderState convert(PGobject source) {
        return OrderState.valueOf(source.getValue());
    }
}
```

Tên type order_state phải khớp với enum type trong schema. Nếu enum database được đổi tên hoặc đổi literal, converter và dữ liệu phải được cập nhật đồng bộ qua migration. Với enum đơn giản lưu dưới dạng VARCHAR, converter Enum ↔ String có thể phù hợp hơn và không cần PGobject.

## 7. JdbcValue: chỉ định JDBC type khi driver cần

Đôi khi converter đã tạo đúng Java value nhưng driver vẫn cần biết rõ JDBC type để bind. Spring Data JDBC cung cấp JdbcValue để mang cả giá trị và java.sql.JDBCType:

```java
import java.sql.JDBCType;
import org.springframework.data.jdbc.core.mapping.JdbcValue;

JdbcValue value = JdbcValue.of(
        "550e8400-e29b-41d4-a716-446655440000",
        JDBCType.VARCHAR
);
```

Ví dụ converter UUID → JdbcValue:

```java
import java.sql.JDBCType;
import java.util.UUID;
import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.WritingConverter;
import org.springframework.data.jdbc.core.mapping.JdbcValue;

@WritingConverter
public class UuidAsVarcharConverter
        implements Converter<UUID, JdbcValue> {

    @Override
    public JdbcValue convert(UUID source) {
        return JdbcValue.of(source.toString(), JDBCType.VARCHAR);
    }
}
```

Phân biệt:

- **Java target type** cho biết object nào converter trả về.
- **JDBC type** cho biết kiểu tham số JDBC cần dùng khi bind.
- **Driver-specific object** như PGobject có thể mang thêm thông tin kiểu riêng của database.

JdbcValue không tự biến một chuỗi thành JSONB hoặc một mảng byte thành UUID native. Giá trị bên trong vẫn phải tương thích với driver và kiểu cột. Dùng JDBC type phù hợp với schema, ví dụ VARCHAR, BINARY hoặc OTHER; không chọn OTHER cho mọi property theo thói quen.

## 8. Kiểu đặc thù của driver khác

Mỗi JDBC driver có thể có wrapper riêng cho các kiểu database không nằm trong JDBC chuẩn:

| Database/driver | Kiểu đặc thù có thể gặp | Hướng xử lý |
| --- | --- | --- |
| PostgreSQL | PGobject cho JSON/JSONB và một số kiểu riêng | Converter đọc/ghi với PGobject, có thể kết hợp JdbcValue |
| PostgreSQL | UUID native | Ưu tiên java.util.UUID nếu driver/version hỗ trợ |
| MySQL | BINARY(16) UUID hoặc JSON | Chọn byte[]/String hoặc wrapper phù hợp driver |
| SQL Server | uniqueidentifier | Xác nhận mapping UUID tương ứng của driver Java |
| Oracle | RAW(16), STRUCT, object type | Dùng kiểu JDBC/Oracle driver phù hợp và converter hoặc DAO riêng |

Không đưa class driver-specific như PGobject vào domain model. Domain nên biểu diễn dữ liệu theo ý nghĩa nghiệp vụ (EventPayload, UUID, OrderState); adapter/converter chịu trách nhiệm giao tiếp với driver. Như vậy domain ít phụ thuộc vào PostgreSQL hoặc một driver cụ thể.

Với kiểu như SQL ARRAY, STRUCT hoặc object type cần Connection để tạo, một converter thuần không phải lúc nào cũng đủ. Có thể cần JdbcTemplate, ConnectionCallback, custom DAO hoặc một cơ chế mapping chuyên biệt có quyền truy cập JDBC connection. Không tạo java.sql.Array giả hoặc giữ object JDBC phụ thuộc connection bên ngoài vòng đời connection.

## 9. Kiểm thử converter và round-trip persistence

Một converter có thể đúng khi gọi trực tiếp nhưng vẫn bind sai JDBC type hoặc không tương thích với schema/driver. Nên kiểm thử cả hai mức:

### 9.1. Unit test cho converter

Ví dụ kiểm tra serialize/deserialize JSON:

```java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.Map;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.postgresql.util.PGobject;
import org.springframework.data.jdbc.core.mapping.JdbcValue;

class EventPayloadConverterTest {

    private final ObjectMapper mapper = new ObjectMapper();

    @Test
    void convertsPayloadToJsonbAndBack() throws Exception {
        EventPayload original = new EventPayload(
                "ORDER_CONFIRMED",
                Map.of("source", "checkout")
        );

        EventPayloadWritingConverter writer =
                new EventPayloadWritingConverter(mapper);
        EventPayloadReadingConverter reader =
                new EventPayloadReadingConverter(mapper);

        JdbcValue jdbcValue = writer.convert(original);
        PGobject json = (PGobject) jdbcValue.getValue();

        assertThat(json.getType()).isEqualTo("jsonb");
        assertThat(reader.convert(json)).isEqualTo(original);
    }
}
```

Test trên minh họa round-trip qua hai converter, không kiểm tra database thật. Tùy phiên bản JdbcValue, dùng accessor tương ứng để lấy giá trị đã bọc.

### 9.2. Integration test với database mục tiêu

Với JSONB/UUID native PostgreSQL, nên chạy integration test trên PostgreSQL cùng driver và migration của ứng dụng. Test có thể:

1. Tạo EventRecord với payload và UUID.
2. Gọi repository save.
3. Đọc lại bằng findById.
4. So sánh UUID và các trường trong payload.
5. Chạy truy vấn JSONB để xác nhận kiểu cột thực tế.
6. Thử dữ liệu JSON không hợp lệ hoặc enum literal không còn tồn tại để xác nhận lỗi được báo rõ.

H2 hoặc database khác không mô phỏng đầy đủ PGobject, JSONB operator, enum type và JDBC type OTHER của PostgreSQL. Test bằng database thay thế có thể hữu ích cho logic chung nhưng không thay thế integration test với driver thật khi dùng kiểu đặc thù.

### 9.3. Kiểm tra schema bằng SQL

PostgreSQL:

```sql
SELECT
    id,
    correlation_id,
    payload,
    pg_typeof(payload) AS payload_type
FROM event_record
ORDER BY id DESC;
```

Kết quả pg_typeof(payload) giúp xác nhận cột là jsonb như mong đợi. Với UUID:

```sql
SELECT
    request_id,
    pg_typeof(request_id) AS request_id_type
FROM api_request;
```

Kiểm tra cả DDL và dữ liệu; một chuỗi có hình dạng UUID không đồng nghĩa cột đang dùng kiểu UUID native.

## 10. Quản lý schema và tương thích dữ liệu

Custom converter là một phần hợp đồng giữa Java model và database schema. Khi thay đổi biểu diễn dữ liệu, cần phối hợp migration:

- Chuyển UUID từ VARCHAR(36) sang UUID native cần chuyển dữ liệu và cập nhật converter tương ứng.
- Đổi JSON schema cần giữ tương thích với dữ liệu cũ hoặc viết migration chuyển đổi.
- Đổi tên PostgreSQL enum/type hoặc literal phải cập nhật converter và các hàng đang lưu.
- Đổi json sang jsonb có thể cần kiểm tra index, constraint, operator và cách ứng dụng truy vấn.
- Chuyển UUID từ chuỗi sang BINARY(16) cần thống nhất byte order với mọi ứng dụng ghi/đọc.

Không thay đổi converter trong code mà bỏ qua dữ liệu đã tồn tại. Nếu converter mới không đọc được dữ liệu cũ, ứng dụng có thể lỗi ngay khi tải aggregate.

## 11. Lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Can't convert ... hoặc không tìm thấy converter | Chưa đăng ký converter hoặc hướng converter không rõ | Đăng ký trong userConverters() và đánh dấu reading/writing |
| PostgreSQL báo không thể bind JSON | Driver nhận String như VARCHAR thay vì JSONB | Dùng PGobject type jsonb, có thể kết hợp JdbcValue với JDBCType.OTHER |
| Đọc JSONB trả về PGobject nhưng property vẫn lỗi | Thiếu converter PGobject → domain type | Đăng ký reading converter |
| Ghi JSON thành chuỗi có quote lồng nhau | Serialize JSON hai lần hoặc bind string sai kiểu | Serialize đúng một lần và bind như JSONB |
| UUID không map được | Driver/schema dùng representation khác với kiểu Java | Kiểm tra kiểu cột và driver; thêm converter phù hợp |
| UUID binary đọc ra giá trị khác | Byte order không thống nhất | Xác nhận quy ước 16 byte giữa tất cả hệ thống |
| PostgreSQL enum báo type mismatch | PGobject.setType() không khớp tên enum trong schema hoặc JDBC type sai | Kiểm tra type name, literal và JDBCType.OTHER |
| Converter không được dùng | Đăng ký sai configuration hoặc tạo nhiều mapping configuration | Kiểm tra AbstractJdbcConfiguration và runtime wiring |
| Test H2 qua nhưng PostgreSQL lỗi | H2 không có kiểu/driver behavior tương ứng | Integration test trên PostgreSQL thật |
| Dữ liệu cũ không deserialize được | Domain JSON hoặc enum đã thay đổi mà không migration | Duy trì tương thích hoặc chuyển dữ liệu bằng migration |

Khi debug, kiểm tra lần lượt: kiểu property Java, converter source/target, converter direction, danh sách converter đã đăng ký, JDBC type, driver version, kiểu cột thật và exception gốc. Không chỉ đổi String thành Object để che lỗi mapping.

## 12. Nguyên tắc thiết kế converter

1. **Giữ domain độc lập với driver.** Domain dùng UUID, record/value object và enum Java; chỉ converter biết PGobject hoặc wrapper của vendor.
2. **Định nghĩa cả hai chiều.** Nếu cần ghi và đọc, triển khai writing và reading converter phù hợp.
3. **Đánh dấu hướng rõ ràng.** Dùng @WritingConverter và @ReadingConverter khi có thể mơ hồ.
4. **Chỉ định JDBC type khi cần.** Dùng JdbcValue khi driver cần biết rõ kiểu bind.
5. **Không nuốt lỗi dữ liệu.** JSON lỗi hoặc enum không hợp lệ phải tạo lỗi có nguyên nhân rõ.
6. **Giữ converter đơn nhiệm.** Không truy vấn repository hoặc gọi service từ converter.
7. **Migration cùng converter.** Thay đổi representation phải có kế hoạch cho dữ liệu hiện hữu.
8. **Kiểm thử với driver thật.** Đặc biệt với JSONB, enum, binary UUID và vendor-specific types.
9. **Chỉ dùng JSON cho dữ liệu phù hợp.** Các trường cần join, constraint hoặc lọc thường xuyên có thể nên là cột quan hệ riêng.

## 13. Bài tập thực hành

**Bài 1 — JSONB round-trip.** Tạo EventPayload, hai converter dùng PGobject, đăng ký qua userConverters() và lưu/đọc EventRecord trên PostgreSQL. So sánh object trước và sau khi đọc.

**Bài 2 — JSON query.** Viết query PostgreSQL lọc payload ->> 'eventType'. Xác nhận converter đọc payload vẫn hoạt động khi query trả về entity.

**Bài 3 — UUID native.** Lưu java.util.UUID vào cột PostgreSQL UUID. Xác nhận driver hỗ trợ trực tiếp và kiểm tra pg_typeof.

**Bài 4 — UUID dạng chuỗi.** Tạo schema dùng VARCHAR(36), đăng ký reading/writing converter và kiểm thử giá trị round-trip.

**Bài 5 — UUID nhị phân.** Chuyển UUID thành 16 byte theo một quy ước đã định nghĩa. Ghi/đọc BINARY(16) và xác nhận cùng một UUID được khôi phục chính xác.

**Bài 6 — PostgreSQL enum.** Tạo type order_state, viết converter OrderState ↔ PGobject, rồi thử ghi một literal không tồn tại để quan sát lỗi constraint/type.

**Bài 7 — Kiểm tra migration.** Thay đổi JSON schema hoặc representation UUID. Viết migration dữ liệu và kiểm thử đọc cả dữ liệu được tạo trước lẫn sau migration.

### Tài liệu tham khảo

- [Spring Data Relational — Custom Conversions](https://docs.spring.io/spring-data/relational/reference/jdbc/mapping.html#jdbc.custom-conversions): đăng ký reading/writing converters và JDBC-specific values.
- [Spring Data JDBC — AbstractJdbcConfiguration API](https://docs.spring.io/spring-data/relational/reference/api/java/org/springframework/data/jdbc/repository/config/AbstractJdbcConfiguration.html): extension point userConverters() và JDBC infrastructure.
- [PostgreSQL JDBC — Advanced Data Types](https://jdbc.postgresql.org/documentation/server-prepare/): cách PostgreSQL JDBC xử lý các kiểu dữ liệu và object riêng của driver.
- [PostgreSQL — JSON Types](https://www.postgresql.org/docs/current/datatype-json.html): khác biệt giữa json và jsonb, toán tử và cách lưu trữ.
- [PostgreSQL — UUID Type](https://www.postgresql.org/docs/current/datatype-uuid.html): kiểu dữ liệu UUID native.
