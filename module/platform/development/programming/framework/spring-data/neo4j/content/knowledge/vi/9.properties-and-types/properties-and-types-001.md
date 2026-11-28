# Kiểu Cypher, kiểu Java và chuyển đổi mặc định của driver

Bài học này thuộc chương **Thuộc tính và kiểu** của module **SPRING_DATA_NEO4J**. Khi xây dựng tầng dữ liệu đồ thị với Spring Data Neo4j, dữ liệu đi qua nhiều lớp: thuộc tính của node và relationship được lưu trong Neo4j, câu lệnh Cypher xử lý các giá trị, Neo4j Java Driver chuyển đổi chúng thành kiểu Java, rồi Spring Data Neo4j ánh xạ vào entity. Hiểu rõ các lớp kiểu này giúp tránh mất độ chính xác, lỗi chuyển đổi và mô hình dữ liệu không thể lưu được.

Điểm cần phân biệt đầu tiên là **kiểu giá trị Cypher** rộng hơn **kiểu thuộc tính có thể lưu trong đồ thị**. Một truy vấn có thể tạo và trả về map, list lồng nhau hoặc `null`, nhưng không phải mọi giá trị như vậy đều có thể gán trực tiếp thành property của node hay relationship. Driver cũng có quy tắc ánh xạ riêng: Cypher `INTEGER` được đọc thành Java `Long`, `FLOAT` thành `Double`, còn các kiểu thời gian và không gian có các kiểu Java chuyên biệt.

## 1. Ba lớp kiểu dữ liệu

Trong một ứng dụng Spring Data Neo4j, cùng một giá trị có thể xuất hiện ở ba lớp khác nhau:

1. **Kiểu trong Neo4j/Cypher:** định nghĩa giá trị mà truy vấn xử lý, ví dụ `INTEGER`, `FLOAT`, `STRING`, `LIST`, `MAP`, `DATE`, `POINT`.
2. **Kiểu Java Driver:** định nghĩa cách driver biểu diễn giá trị khi gửi tham số hoặc đọc kết quả, ví dụ `Long`, `Double`, `String`, `List`, `Map`, `LocalDate`, `Point`.
3. **Kiểu trong entity:** định nghĩa thuộc tính Java của domain model, ví dụ `long`, `String`, `LocalDate`, `List<String>` hoặc một kiểu nghiệp vụ riêng được chuyển đổi bằng converter.

Các lớp này có quan hệ với nhau nhưng không đồng nhất. Ví dụ, một thuộc tính Java khai báo `int` vẫn có thể được lưu thành Cypher `INTEGER`; khi đọc bằng Driver, giá trị được biểu diễn mặc định bằng `Long`. Spring Data Neo4j có thể chuyển giá trị đó sang trường entity `int` nếu nằm trong phạm vi hợp lệ. Khi đọc trực tiếp bằng Driver, ứng dụng phải chủ động gọi phương thức chuyển đổi thích hợp.

## 2. Các kiểu giá trị cơ bản của Cypher

Cypher hỗ trợ các nhóm kiểu thường gặp sau:

| Nhóm | Kiểu Cypher | Ví dụ |
|---|---|---|
| Logic | `BOOLEAN` | `true`, `false` |
| Số nguyên | `INTEGER` | `0`, `42`, `-9000000000` |
| Số thực | `FLOAT` | `3.14`, `-0.5` |
| Chuỗi | `STRING` | `'Neo4j'`, `'Spring Data'` |
| Danh sách | `LIST` | `[1, 2, 3]`, `['neo4j', 'java']` |
| Bản đồ | `MAP` | `{name: 'Lan', active: true}` |
| Thời gian | `DATE`, `TIME`, `LOCAL TIME`, `DATETIME`, `LOCAL DATETIME`, `DURATION` | `date('2026-11-26')`, `datetime()` |
| Không gian | `POINT` | `point({longitude: 106.7, latitude: 10.8})` |
| Giá trị đồ thị | `NODE`, `RELATIONSHIP`, `PATH` | node, relationship và đường đi được truy vấn trả về |
| Giá trị đặc biệt | `NULL` | `null` |

`INTEGER` trong Neo4j là số nguyên có dấu 64 bit; `FLOAT` là số thực dấu phẩy động 64 bit. Đây là điểm quan trọng khi ánh xạ với Java: không nên giả định một giá trị `INTEGER` trong kết quả Driver luôn là `Integer` chỉ vì dữ liệu nhỏ.

### Giá trị trong truy vấn và property được lưu

Cypher có thể tạo map và list để truyền tham số, xây dựng kết quả, gom nhóm hoặc xử lý trung gian. Tuy nhiên, property của node và relationship chỉ hỗ trợ một tập kiểu dữ liệu có thể lưu. Các kiểu scalar, temporal, spatial và list phù hợp của chúng có thể được lưu làm property. Một số giới hạn quan trọng:

- Property không thể lưu `null`. Gán `null` cho property bằng `SET` có nghĩa là xóa property đó.
- Property không thể lưu một map như một giá trị đơn lẻ.
- Property không thể lưu list lồng nhau hoặc list chứa các giá trị không thuộc nhóm property được hỗ trợ.
- List được lưu làm property phải có các phần tử cùng kiểu tương thích; list hỗn hợp có thể dùng trong biểu thức Cypher nhưng không phải mọi list đều lưu được thành property.
- Node, relationship và path là giá trị đồ thị trong truy vấn, không phải kiểu property để gán vào một property khác.

Ví dụ, truy vấn dưới đây hợp lệ vì map được dùng làm tham số và các trường của map được gán riêng thành property:

```cypher
WITH {name: 'Lan', age: 28, active: true} AS input
CREATE (c:Customer)
SET c.name = input.name,
    c.age = input.age,
    c.active = input.active
RETURN c;
```

Trong khi đó, không thể dùng `SET c.profile = input` để lưu toàn bộ map `input` thành một property. Nếu cần lưu cấu trúc lồng nhau, hãy cân nhắc tách thành các property phẳng, mô hình hóa thành node liên quan, hoặc serialize thành chuỗi theo một định dạng có phiên bản rõ ràng.

## 3. Chuyển đổi mặc định của Neo4j Java Driver

Khi đọc kết quả, Java Driver cung cấp `Value` để truy cập từng giá trị trong `Record`. Phương thức `asObject()` chuyển giá trị sang kiểu Java mặc định. Bảng sau tóm tắt các ánh xạ thường gặp:

| Kiểu Cypher | Kiểu Java mặc định khi đọc |
|---|---|
| `BOOLEAN` | `Boolean` |
| `INTEGER` | `Long` |
| `FLOAT` | `Double` |
| `STRING` | `String` |
| `LIST` | `List<Object>` |
| `MAP` | `Map<String, Object>` |
| `NODE` | `org.neo4j.driver.types.Node` |
| `RELATIONSHIP` | `org.neo4j.driver.types.Relationship` |
| `PATH` | `org.neo4j.driver.types.Path` |
| `DATE` | `java.time.LocalDate` |
| `TIME` | `java.time.OffsetTime` |
| `LOCAL TIME` | `java.time.LocalTime` |
| `DATETIME` | `java.time.ZonedDateTime` |
| `LOCAL DATETIME` | `java.time.LocalDateTime` |
| `DURATION` | `org.neo4j.driver.types.IsoDuration` |
| `POINT` | `org.neo4j.driver.types.Point` |
| `NULL` | `null` |

Các kiểu trong bảng là cách Driver biểu diễn giá trị khi đọc trực tiếp. Spring Data Neo4j có thêm tầng mapping và conversion để chuyển kết quả thành thuộc tính entity. Không nên nhầm bảng chuyển đổi của Driver với kiểu field bắt buộc trong entity.

### INTEGER luôn được đọc thành Long

Ví dụ truy vấn:

```cypher
RETURN 42 AS quantity;
```

Khi đọc bằng Driver:

```java
Record record = result.single();
long quantity = record.get("quantity").asLong();
```

`asLong()` là lựa chọn tự nhiên cho `INTEGER`. Nếu cần `int`, có thể gọi `asInt()` khi chắc chắn giá trị nằm trong phạm vi của Java `int`. Nếu giá trị vượt phạm vi, việc chuyển đổi sẽ thất bại. Với dữ liệu số lượng, bộ đếm hoặc ID dạng số, nên chọn kiểu Java theo miền giá trị thực tế.

### FLOAT được đọc thành Double

Cypher `FLOAT` tương ứng với Java `Double`. Ví dụ:

```cypher
RETURN 19.75 AS unitPrice;
```

```java
double unitPrice = record.get("unitPrice").asDouble();
```

Không nên dùng số thực nhị phân để lưu số tiền cần độ chính xác thập phân tuyệt đối. Phép toán dấu phẩy động có thể tạo sai số làm tròn. Với tiền tệ, thường lưu số nguyên theo đơn vị nhỏ nhất (ví dụ xu) cùng mã tiền tệ; hoặc dùng converter để biểu diễn một kiểu tiền tệ thành chuỗi/giá trị có quy ước rõ ràng.

Cypher không có kiểu property decimal chuyên biệt tương đương `BigDecimal`. Nếu domain dùng `BigDecimal`, hãy xác định quy tắc scale và rounding rồi chuyển sang số nguyên theo đơn vị nhỏ nhất hoặc định dạng chuỗi có quy ước. Không chuyển tùy tiện sang `double` nếu cần giữ chính xác thập phân.

### LIST và MAP

Driver trả list thành `List<Object>` và map thành `Map<String, Object>`. Có thể đọc kiểu phần tử cụ thể bằng các phương thức chuyển đổi:

```cypher
RETURN ['neo4j', 'spring', 'java'] AS tags,
       {name: 'Lan', age: 28} AS profile;
```

```java
List<String> tags = record.get("tags")
    .asList(Value::asString);

Map<String, Object> profile = record.get("profile").asMap();
```

Map và list rất hữu ích cho dữ liệu trung gian hoặc kết quả tổng hợp. Việc đọc được chúng qua Driver không có nghĩa có thể lưu nguyên cấu trúc đó thành một property trên node.

## 4. Đọc kết quả bằng Value và Record

Một `Record` chứa các cột mà truy vấn trả về. Mỗi cột được truy cập bằng tên hoặc vị trí và trả về một `Value`. Hãy dùng phương thức chuyển đổi có kiểu rõ ràng để tránh ép kiểu không an toàn:

```java
import java.time.LocalDate;
import java.util.List;

import org.neo4j.driver.Record;
import org.neo4j.driver.Value;

Record record = result.single();

String name = record.get("name").asString();
long age = record.get("age").asLong();
LocalDate birthday = record.get("birthday").asLocalDate();
List<String> tags = record.get("tags").asList(Value::asString);
```

Tên cột phải khớp với alias trong `RETURN`. Ví dụ `RETURN c.name AS name` tạo cột `name`; nếu truy vấn đổi alias thành `customerName`, code đọc cũng phải đổi theo.

Khi kiểu dữ liệu không chắc chắn, kiểm tra `Value` trước khi chuyển đổi:

```java
Value nicknameValue = record.get("nickname");

String nickname = nicknameValue.isNull()
    ? null
    : nicknameValue.asString();
```

Không gọi `asString()`, `asLong()` hoặc phương thức chuyển đổi khác trước khi xác định giá trị có thể null và có kiểu tương thích. Nếu truy vấn trả node hoặc relationship, dùng `asNode()` hoặc `asRelationship()` thay vì cố đọc nó như map property thông thường.

## 5. Truyền tham số Java vào Cypher

Driver cũng chuyển đổi giá trị Java thành tham số Cypher. Những kiểu thông dụng như `String`, `Boolean`, `Long`, `Double`, `Map`, `Iterable`, các kiểu `java.time` được hỗ trợ, `IsoDuration` và `Point` có thể được bind trực tiếp.

Ví dụ tạo khách hàng với ngày sinh và danh sách nhãn:

```java
import java.time.LocalDate;
import java.util.List;
import java.util.Map;

Map<String, Object> parameters = Map.of(
    "name", "Lan",
    "age", 28L,
    "birthday", LocalDate.of(1998, 4, 12),
    "tags", List.of("neo4j", "java")
);

session.run("""
    CREATE (c:Customer {
        name: $name,
        age: $age,
        birthday: $birthday,
        tags: $tags
    })
    """, parameters);
```

Tham số giúp tách dữ liệu khỏi câu Cypher và cho phép Driver xử lý kiểu dữ liệu. Không ghép chuỗi đầu vào vào câu lệnh truy vấn. Các tham số dạng map có thể chứa map hoặc list lồng nhau cho mục đích xử lý truy vấn; nhưng nếu cuối cùng gán một giá trị vào property, giá trị đó vẫn phải thuộc tập kiểu property Neo4j hỗ trợ.

Node, relationship và path trả về từ một truy vấn không phải là kiểu tham số để gửi ngược vào một truy vấn khác. Khi cần tham chiếu một node ở truy vấn tiếp theo, hãy dùng thuộc tính ID do ứng dụng quản lý hoặc một khóa nghiệp vụ duy nhất để tìm node lại. Tránh phụ thuộc vào ID nội bộ cho tham chiếu bền vững.

## 6. Kiểu thời gian và cách chọn ngữ nghĩa

Neo4j hỗ trợ nhiều kiểu temporal. Hãy chọn kiểu dựa trên ý nghĩa nghiệp vụ, đặc biệt là việc thời điểm có gắn với múi giờ hay không.

| Kiểu Cypher | Kiểu Java Driver | Ý nghĩa thường dùng |
|---|---|---|
| `DATE` | `LocalDate` | Ngày lịch, không có giờ hoặc múi giờ |
| `LOCAL TIME` | `LocalTime` | Giờ trong ngày, không có ngày và múi giờ |
| `TIME` | `OffsetTime` | Giờ trong ngày kèm UTC offset |
| `LOCAL DATETIME` | `LocalDateTime` | Ngày giờ địa phương, không gắn múi giờ |
| `DATETIME` | `ZonedDateTime` | Thời điểm có thông tin múi giờ/offset |
| `DURATION` | `IsoDuration` | Khoảng thời gian theo thành phần tháng, ngày và thời lượng |

Ví dụ:

```java
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.ZonedDateTime;

LocalDate birthday = LocalDate.of(1998, 4, 12);
LocalDateTime localAppointment = LocalDateTime.of(2026, 11, 26, 9, 30);
ZonedDateTime createdAt = ZonedDateTime.now(ZoneId.of("Asia/Ho_Chi_Minh"));
```

`LocalDateTime` không chứa múi giờ, do đó không thể tự xác định một thời điểm tuyệt đối nếu thiếu ngữ cảnh. Với thời điểm diễn ra trên toàn hệ thống như lúc tạo đơn hoặc nhận sự kiện, hãy dùng kiểu có offset/múi giờ hoặc quy ước UTC nhất quán. Với ngày sinh, ngày hết hạn theo lịch hoặc ngày nghỉ, `DATE` thường phù hợp hơn.

`DURATION` trong Cypher có thể biểu diễn tháng, ngày và thời lượng nhỏ hơn giây. Driver dùng `IsoDuration` để giữ được các thành phần này. `java.time.Duration` chỉ biểu diễn khoảng thời gian theo giây và nano giây, không biểu diễn được khái niệm tháng theo lịch; vì vậy không nên tự động thay thế `IsoDuration` bằng `Duration` nếu dữ liệu có thành phần tháng.

## 7. Kiểu không gian POINT

Neo4j hỗ trợ `POINT` cho tọa độ địa lý và tọa độ Cartesian. Driver biểu diễn giá trị này bằng `org.neo4j.driver.types.Point`. Trong Cypher có thể tạo điểm địa lý như sau:

```cypher
CREATE (office:Office {
    location: point({longitude: 106.7009, latitude: 10.7769})
})
RETURN office.location AS location;
```

Điểm địa lý WGS-84 dùng SRID `4326`; tọa độ được truyền theo thứ tự kinh độ rồi vĩ độ trong map dùng `longitude` và `latitude`. Với tọa độ Cartesian, ý nghĩa trục và hệ quy chiếu phải được xác định rõ theo miền nghiệp vụ.

Khi đọc `POINT` bằng Driver:

```java
import org.neo4j.driver.types.Point;

Point location = record.get("location").asPoint();
double longitude = location.x();
double latitude = location.y();
```

Hãy kiểm tra hệ tọa độ/SRID trước khi diễn giải `x()` và `y()` thành kinh độ, vĩ độ. Không phải mọi `POINT` đều là tọa độ địa lý WGS-84.

## 8. Null và sự vắng mặt của property

Trong Cypher, `null` biểu diễn giá trị không xác định hoặc không có. Với property của node và relationship, không có giá trị null được lưu trữ. Lệnh sau xóa property `nickname` khỏi node:

```cypher
MATCH (c:Customer {id: $id})
SET c.nickname = null;
```

Sau đó, biểu thức `c.nickname` trả về `null`. Có thể kiểm tra bằng `IS NULL` hoặc `IS NOT NULL`:

```cypher
MATCH (c:Customer)
WHERE c.nickname IS NULL
RETURN c;
```

Không dùng phép so sánh `= null` để kiểm tra giá trị thiếu. Trong logic ba giá trị của Cypher, biểu thức như `c.nickname = null` cho kết quả `null`, không phải `true`. Dùng `IS NULL` sẽ diễn đạt đúng ý định.

Khi đọc kết quả bằng Java Driver, giá trị null được biểu diễn thành `null` khi gọi `asObject()`, hoặc kiểm tra qua `Value.isNull()`. Trong entity, thuộc tính reference có thể nhận `null` nếu property không tồn tại; kiểu primitive như `int` hoặc `boolean` không thể biểu diễn null. Nếu cần phân biệt “không có dữ liệu” với giá trị mặc định `0` hoặc `false`, dùng kiểu wrapper (`Integer`, `Boolean`) hoặc kiểu reference phù hợp.

## 9. Ánh xạ kiểu vào entity Spring Data Neo4j

Spring Data Neo4j dùng metadata của entity để ánh xạ property. Các kiểu Java phổ biến như `String`, `Long`, `Double`, `Boolean`, `LocalDate`, `LocalDateTime`, `ZonedDateTime` và các collection phù hợp được hỗ trợ thông qua conversion mặc định.

Ví dụ entity:

```java
import java.time.LocalDate;
import java.util.List;

import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;
import org.springframework.data.neo4j.core.schema.Property;

@Node("Customer")
public class Customer {

    @Id
    private String id;

    @Property("full_name")
    private String name;

    private Long age;

    private LocalDate birthday;

    private List<String> tags;
}
```

`@Property("full_name")` ánh xạ trường `name` vào property `full_name` trong Neo4j. Kiểu Java phải tương thích với giá trị có thể lưu trong property. Nếu cần map hoặc cấu trúc lồng nhau, hãy thiết kế rõ cách lưu thay vì giả định Spring Data Neo4j có thể lưu trực tiếp mọi kiểu Java.

### Kiểu nghiệp vụ riêng và custom converter

Khi domain model có kiểu riêng như `Money`, `AddressCode` hoặc `EmailAddress`, có thể đăng ký converter đọc và ghi để chuyển kiểu đó sang một kiểu property Neo4j hỗ trợ. Ví dụ lưu `Money` dưới dạng chuỗi có quy ước `CURRENCY:minorUnits`:

```java
public record Money(String currency, long minorUnits) {
}
```

Converter ghi:

```java
import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.WritingConverter;

@WritingConverter
public class MoneyWriteConverter implements Converter<Money, String> {

    @Override
    public String convert(Money source) {
        return source.currency() + ":" + source.minorUnits();
    }
}
```

Converter đọc:

```java
import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.ReadingConverter;

@ReadingConverter
public class MoneyReadConverter implements Converter<String, Money> {

    @Override
    public Money convert(String source) {
        String[] parts = source.split(":", 2);
        return new Money(parts[0], Long.parseLong(parts[1]));
    }
}
```

Đăng ký các converter trong `Neo4jConversions`:

```java
import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.neo4j.core.convert.Neo4jConversions;

@Configuration
public class Neo4jConversionConfiguration {

    @Bean
    Neo4jConversions neo4jConversions() {
        return new Neo4jConversions(List.of(
            new MoneyWriteConverter(),
            new MoneyReadConverter()
        ));
    }
}
```

Converter ghi phải chuyển thành kiểu mà Neo4j có thể lưu làm property; converter đọc phải khôi phục được kiểu domain. Với dữ liệu tiền tệ, ví dụ này giữ số tiền dưới dạng số nguyên theo đơn vị nhỏ nhất trong chuỗi và tránh sai số dấu phẩy động. Trong hệ thống thực tế, cần xác thực mã tiền tệ, định dạng chuỗi và xử lý dữ liệu cũ trước khi thay đổi quy ước.

## 10. Những lỗi chuyển đổi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Ép `INTEGER` thành `Integer` thất bại | Driver biểu diễn mặc định thành `Long`, hoặc giá trị vượt giới hạn `int` | Dùng `Long`/`long`; chỉ dùng `asInt()` khi giới hạn được bảo đảm |
| Giá trị tiền bị sai số | Dùng `FLOAT`/`Double` cho phép tính thập phân | Lưu đơn vị nhỏ nhất bằng integer hoặc dùng converter có quy ước rõ |
| Lưu map thành property thất bại | Map không phải kiểu property Neo4j | Tách map thành property, node liên quan hoặc serialize thành chuỗi |
| Lưu list lồng nhau thất bại | Cấu trúc list không thuộc tập property được hỗ trợ | Làm phẳng dữ liệu hoặc mô hình hóa thành node |
| Đọc chuỗi từ giá trị null gây lỗi | Gọi `asString()` trước khi kiểm tra null | Kiểm tra `isNull()` và xử lý trường hợp thiếu |
| Thời điểm lệch múi giờ | Dùng `LocalDateTime` cho một thời điểm tuyệt đối | Dùng `ZonedDateTime`/kiểu có offset hoặc quy ước UTC |
| Không chuyển đổi được kiểu domain riêng | Chưa đăng ký converter đọc/ghi tương ứng | Đăng ký converter trong `Neo4jConversions` |

## 11. Nguyên tắc thiết kế kiểu dữ liệu

- Chọn kiểu Cypher theo ý nghĩa dữ liệu và chọn kiểu Java tương ứng, không chỉ dựa trên giá trị mẫu đang nhỏ.
- Ghi nhớ `INTEGER` được Driver đọc thành `Long` và `FLOAT` thành `Double`.
- Phân biệt giá trị Cypher có thể dùng trong truy vấn với kiểu property có thể lưu trên node hoặc relationship.
- Dùng kiểu temporal có hoặc không có múi giờ theo đúng ý nghĩa nghiệp vụ.
- Dùng `IsoDuration` khi cần giữ đủ thành phần của Cypher `DURATION`.
- Không dùng `Double` cho số tiền cần độ chính xác thập phân.
- Kiểm tra null trước khi gọi phương thức chuyển đổi trên `Value`.
- Dùng custom converter cho kiểu domain riêng và bảo đảm kiểu lưu cuối cùng thuộc tập property được Neo4j hỗ trợ.
- Dùng tham số Cypher thay vì ghép chuỗi để truyền dữ liệu từ Java.

Khi dữ liệu đi từ Cypher qua Java Driver rồi vào entity, mỗi tầng có quy tắc kiểu riêng. Nắm được chuyển đổi mặc định và giới hạn property của Neo4j giúp mô hình dữ liệu rõ ràng, giảm lỗi runtime và giữ nguyên ý nghĩa của dữ liệu trong toàn bộ tầng persistence.
