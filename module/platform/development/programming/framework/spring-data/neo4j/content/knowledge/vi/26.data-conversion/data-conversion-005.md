# Ánh xạ value object và dữ liệu nhiều property qua cơ chế composite

Trong mô hình hướng đối tượng, một value object thường gom nhiều giá trị có liên quan thành một kiểu có ý nghĩa nghiệp vụ. Ví dụ, `Address` gồm đường, thành phố và mã bưu chính; `Price` gồm số tiền và loại tiền tệ. Trong Neo4j, property của node hoặc relationship phải là kiểu dữ liệu mà database hỗ trợ. Một object Java tùy ý không tự động trở thành một property lồng nhau trên node.

Spring Data Neo4j (SDN) cung cấp `@CompositeProperty` để ánh xạ một giá trị dạng map thành nhiều property trên cùng node hoặc relationship. Nếu domain model muốn giữ một value object như `Address`, ta có thể viết `Neo4jPersistentPropertyToMapConverter` để phân rã object thành map khi ghi và dựng lại object khi đọc. Nhờ vậy, Java vẫn biểu diễn một khái niệm thống nhất, còn Neo4j lưu từng thành phần dưới dạng property độc lập có thể truy vấn bằng Cypher.

## 1. Composite property giải quyết vấn đề gì?

Giả sử một `Person` có địa chỉ liên hệ. Trong Java, địa chỉ là một value object:

```java
public record Address(
    String street,
    String city,
    String postalCode
) {
}
```

Ta muốn code nghiệp vụ dùng `person.getAddress().city()` thay vì quản lý ba field rời rạc `addressStreet`, `addressCity`, `addressPostalCode`. Tuy nhiên, node Neo4j không có cấu trúc object lồng nhau giống JSON document. Các property của node là phẳng.

Composite mapping phân rã địa chỉ thành những property riêng trên node:

```text
(:Person {
    name: "An",
    address_street: "12 Nguyen Hue",
    address_city: "Ho Chi Minh City",
    address_postalCode: "700000"
})
```

Khi SDN đọc node, converter gom các property có cùng prefix thành một `Address`. Khi ghi node, converter phân rã `Address` thành các key/value tương ứng.

Composite property có các đặc điểm:

- Các thành phần được lưu trên chính node hoặc relationship đang chứa field được đánh dấu.
- Các property thành phần dùng chung một prefix để SDN nhận biết chúng thuộc cùng một field Java.
- Không tạo node mới và không tạo relationship mới.
- Các thành phần vẫn là property Neo4j độc lập, có thể lọc, sắp xếp hoặc index riêng.
- `@CompositeProperty` được hỗ trợ từ Spring Data Neo4j 6.0.

## 2. Phân biệt composite value object với relationship

Không phải object Java nào chứa nhiều field cũng nên ánh xạ bằng composite. Hãy chọn cấu trúc theo ý nghĩa của dữ liệu:

| Đặc điểm | Composite property | Node và relationship |
|---|---|---|
| Bản chất | Giá trị thuộc về node/relationship cha | Thực thể có danh tính riêng |
| Lưu trữ | Nhiều property phẳng trên cùng node/relationship | Node riêng và cạnh nối trong graph |
| Vòng đời | Thường phụ thuộc object chứa nó | Có thể được tham chiếu từ nhiều node và quản lý riêng |
| Truy vấn | Lọc trực tiếp theo property thành phần | Traversal qua relationship và lọc node liên quan |
| Ví dụ | Địa chỉ giao hàng, khoảng thời gian, thông tin tiền tệ | Khách hàng, đơn hàng, sản phẩm, tổ chức |

`Address` thường là composite nếu chỉ mô tả địa chỉ của `Person` và không cần identity riêng. Nếu địa chỉ được chia sẻ bởi nhiều người, có lịch sử thay đổi riêng hoặc cần relationship tới địa chỉ, hãy cân nhắc mô hình hóa `Address` thành node.

## 3. Dùng @CompositeProperty trực tiếp với Map

SDN hỗ trợ sẵn composite mapping cho `Map<String, Object>` và `Map` có key là enum. Mỗi entry trong map trở thành một property trên node hoặc relationship chứa field đó.

Ví dụ entity có một nhóm metadata linh hoạt:

```java
import java.util.LinkedHashMap;
import java.util.Map;

import org.springframework.data.neo4j.core.schema.GeneratedValue;
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;
import org.springframework.data.neo4j.core.schema.CompositeProperty;

@Node("Person")
public class Person {
    @Id
    @GeneratedValue
    private Long id;

    private String code;
    private String name;

    @CompositeProperty(prefix = "metadata", delimiter = "_")
    private Map<String, Object> metadata = new LinkedHashMap<>();

    protected Person() {
    }

    public Person(String code, String name) {
        this.code = code;
        this.name = name;
    }

    public String getCode() {
        return code;
    }

    public Map<String, Object> getMetadata() {
        return metadata;
    }
}
```

Khi `metadata` có các entry `source`, `externalId` và `syncVersion`, node có thể chứa:

```text
(:Person {
    name: "An",
    metadata_source: "crm",
    metadata_externalId: "C-100",
    metadata_syncVersion: 4
})
```

Prefix `metadata` và delimiter `_` tạo tên property theo dạng `metadata_key`. Nếu không khai báo `prefix`, SDN dùng tên field Java làm prefix. Nếu không khai báo `delimiter`, delimiter mặc định là dấu chấm (`.`). Có thể thay đổi hai giá trị này để tương thích với schema Neo4j hiện có.

Các key trong map phải là `String` hoặc enum. Giá trị phải có kiểu mà Neo4j/SDN có thể chuyển đổi thành property hợp lệ, hoặc có converter phù hợp đã đăng ký. Composite mapping mặc định không hỗ trợ nested map.

## 4. Truy vấn các thành phần composite bằng Cypher

Composite mapping không làm các property thành phần biến mất khỏi schema Neo4j. Chúng vẫn là các property phẳng và có thể truy vấn trực tiếp:

```cypher
MATCH (p:Person)
WHERE p.metadata_source = $source
RETURN p.name AS name,
       p.metadata_externalId AS externalId,
       p.metadata_syncVersion AS syncVersion;
```

Có thể cập nhật một entry bằng Cypher:

```cypher
MATCH (p:Person {code: $personCode})
SET p.metadata_syncVersion = $version
RETURN p;
```

Khi SDN đọc node sau đó, entry `syncVersion` được gom lại vào map `metadata`. Nếu ứng dụng ghi dữ liệu bằng Cypher trực tiếp, tên property phải tuân theo cùng quy tắc prefix và delimiter mà entity đang sử dụng.

Nếu cần lọc thường xuyên theo một key động, hãy xem xét tạo index cho property thực tế được truy vấn. Không thể tạo một index chung cho mọi key động nếu mỗi key được lưu thành một property Neo4j khác nhau.

## 5. Dùng enum làm key và chuẩn hóa tên key

SDN cũng hỗ trợ map có key là enum:

```java
public enum IntegrationField {
    SOURCE,
    EXTERNAL_ID,
    SYNC_VERSION
}
```

```java
@CompositeProperty(prefix = "integration", delimiter = "_")
private Map<IntegrationField, Object> integration = new LinkedHashMap<>();
```

Enum key được chuyển thành tên property theo cơ chế key transformation của `@CompositeProperty`. Annotation có thuộc tính `transformKeysWith` để cấu hình việc chuyển đổi key ở pha đọc và ghi. Nếu cần tên key theo quy ước khác, hãy dùng một transformation xác định, ổn định và có thể đảo ngược; tránh phụ thuộc vào tên hiển thị có thể thay đổi theo locale.

Khi đổi tên enum constant hoặc quy tắc transform, các property đã tồn tại trong Neo4j không tự động đổi tên. Cần có kế hoạch migration dữ liệu để tránh việc SDN không còn gom được key cũ vào map.

## 6. Ánh xạ một value object bằng converter tùy chỉnh

Map mặc định phù hợp với metadata linh hoạt. Với value object có cấu trúc cố định như `Address`, ta có thể cung cấp converter riêng cho `@CompositeProperty`.

Đầu tiên, khai báo value object:

```java
public record Address(
    String street,
    String city,
    String postalCode
) {
}
```

Converter phải thực hiện hai chiều:

- `decompose`: chuyển `Address` thành `Map<String, Value>` để ghi các property thành phần.
- `compose`: nhận map các `Value` từ Neo4j Driver và dựng lại `Address`.

Ví dụ:

```java
import java.util.LinkedHashMap;
import java.util.Map;

import org.neo4j.driver.Value;
import org.springframework.data.neo4j.core.convert.Neo4jConversionService;
import org.springframework.data.neo4j.core.convert.Neo4jPersistentPropertyToMapConverter;
import org.springframework.data.util.TypeInformation;

public final class AddressToMapConverter
        implements Neo4jPersistentPropertyToMapConverter<String, Address> {

    @Override
    public Map<String, Value> decompose(
            Address address,
            Neo4jConversionService conversionService) {

        Map<String, Value> values = new LinkedHashMap<>();

        if (address == null) {
            return values;
        }

        values.put("street", conversionService.writeValue(
            address.street(), TypeInformation.of(String.class), null));
        values.put("city", conversionService.writeValue(
            address.city(), TypeInformation.of(String.class), null));
        values.put("postalCode", conversionService.writeValue(
            address.postalCode(), TypeInformation.of(String.class), null));

        return values;
    }

    @Override
    public Address compose(
            Map<String, Value> source,
            Neo4jConversionService conversionService) {

        String street = (String) conversionService.readValue(
            source.get("street"), TypeInformation.of(String.class), null);
        String city = (String) conversionService.readValue(
            source.get("city"), TypeInformation.of(String.class), null);
        String postalCode = (String) conversionService.readValue(
            source.get("postalCode"), TypeInformation.of(String.class), null);

        return new Address(street, city, postalCode);
    }
}
```

`Neo4jConversionService` được truyền vào converter để ủy quyền việc chuyển các giá trị thành kiểu Neo4j Driver `Value` và ngược lại. Nhờ vậy, converter không phải tự xử lý mọi kiểu scalar và có thể tận dụng các conversion đã đăng ký trong SDN.

Gắn converter vào field:

```java
import org.springframework.data.neo4j.core.schema.CompositeProperty;

@CompositeProperty(
    prefix = "address",
    delimiter = "_",
    converter = AddressToMapConverter.class
)
private Address address;
```

Khi ghi, `Address` được phân rã thành các property `address_street`, `address_city` và `address_postalCode`. Khi đọc, SDN thu thập các property theo prefix, gọi `compose` và gán một object `Address` vào field.

Converter cần xử lý rõ trường hợp thiếu key hoặc giá trị null. Ví dụ trên cho phép `compose` nhận key không tồn tại và tạo thành field `null`; nếu địa chỉ bắt buộc có đủ ba thành phần, hãy kiểm tra và báo lỗi dữ liệu không hợp lệ thay vì âm thầm tạo object thiếu dữ liệu. Cách xử lý `address == null` trong `decompose` cũng cần được kiểm thử với chính sách cập nhật của ứng dụng, đặc biệt khi cần xóa các property composite đã lưu trước đó.

## 7. Converter tùy chỉnh có thể tái sử dụng

Nếu cùng một value object xuất hiện trong nhiều entity, converter có thể được dùng lại bằng cách tham chiếu bean. `@CompositeProperty` cung cấp cả `converter` để chỉ định class và `converterRef` để tham chiếu Spring bean triển khai `Neo4jPersistentPropertyToMapConverter`.

Ví dụ khai báo bean:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class Neo4jMappingConfiguration {

    @Bean
    AddressToMapConverter addressToMapConverter() {
        return new AddressToMapConverter();
    }
}
```

Sau đó dùng bean reference:

```java
@CompositeProperty(
    prefix = "billingAddress",
    delimiter = "_",
    converterRef = "addressToMapConverter"
)
private Address billingAddress;
```

Sử dụng `converterRef` khi converter cần dependency được quản lý bởi Spring hoặc cần cấu hình dùng chung. Nếu converter không có dependency và có thể khởi tạo trực tiếp, thuộc tính `converter` thường đơn giản hơn.

## 8. Composite property trên relationship properties

Composite mapping không chỉ dùng cho node. Nó cũng có thể được khai báo trên field của lớp `@RelationshipProperties`.

Ví dụ một quan hệ `MEMBER_OF` có thêm thông tin phân loại do hệ thống ngoài cung cấp:

```java
import java.util.Map;

import org.springframework.data.neo4j.core.schema.RelationshipId;
import org.springframework.data.neo4j.core.schema.RelationshipProperties;
import org.springframework.data.neo4j.core.schema.TargetNode;
import org.springframework.data.neo4j.core.schema.CompositeProperty;

@RelationshipProperties
public class Membership {
    @RelationshipId
    private Long id;

    private String role;

    @CompositeProperty(prefix = "external", delimiter = "_")
    private Map<String, Object> externalMetadata;

    @TargetNode
    private Team team;
}
```

Các entry của `externalMetadata` trở thành property của relationship, ví dụ `external_source` hoặc `external_reference`. Chúng không trở thành property của node `Person` hoặc `Team`.

Khi truy vấn bằng Cypher, cần truy cập property trên relationship:

```cypher
MATCH (p:Person)-[r:MEMBER_OF]->(t:Team)
WHERE r.external_source = $source
RETURN p.name, t.name, r.external_reference;
```

Điều này hữu ích khi dữ liệu thuộc về chính mối quan hệ, ví dụ nguồn đồng bộ, mã tham chiếu hoặc metadata của lần tham gia nhóm.

## 9. CompositeProperty, ConvertWith và Neo4jConversions

SDN có nhiều điểm mở rộng conversion. Chọn đúng API theo hình dạng dữ liệu cần lưu:

| Cơ chế | Hình dạng dữ liệu trong Neo4j | Phạm vi |
|---|---|---|
| `@CompositeProperty` mặc định | Một map được phân rã thành nhiều property phẳng | Một field cụ thể của node/relationship |
| `@CompositeProperty` với `Neo4jPersistentPropertyToMapConverter` | Một value object được phân rã thành nhiều property phẳng | Một field cụ thể của node/relationship |
| `@ConvertWith` với `Neo4jPersistentPropertyConverter` | Một field được chuyển thành một Driver `Value` | Một field cụ thể |
| `Neo4jConversions` với `GenericConverter` | Kiểu Java được chuyển đổi toàn cục sang/đến Driver `Value` | Các thuộc tính hoặc tham số query dùng kiểu đó |

### @ConvertWith cho một property đơn

Nếu `Money` được lưu thành một giá trị chuỗi duy nhất như `"125.50 USD"`, converter một property phù hợp hơn composite. `Neo4jPersistentPropertyConverter<Money>` định nghĩa `write(Money)` trả về một `Value` và `read(Value)` dựng lại `Money`.

### Neo4jConversions cho kiểu dùng chung

Nếu muốn converter áp dụng cho một kiểu Java ở nhiều entity hoặc làm tham số cho `@Query`, có thể triển khai `GenericConverter` và đăng ký trong bean `Neo4jConversions`:

```java
import java.util.Collections;
import java.util.Set;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.convert.converter.GenericConverter;
import org.springframework.data.neo4j.core.convert.Neo4jConversions;

@Configuration
public class Neo4jConversionConfiguration {

    @Bean
    Neo4jConversions neo4jConversions() {
        Set<GenericConverter> converters =
            Collections.singleton(new MoneyValueConverter());
        return new Neo4jConversions(converters);
    }
}
```

Ví dụ chỉ thể hiện cách đăng ký. `MoneyValueConverter` phải khai báo các cặp chuyển đổi phù hợp giữa `Money` và `org.neo4j.driver.Value`, đồng thời xử lý cả chiều đọc và ghi nếu được dùng cho entity property. Nếu chỉ dùng làm tham số đầu vào của custom query, converter một chiều từ `Money` sang `Value` là đủ.

Không đăng ký một kiểu vừa như một scalar `Value` vừa như một composite map cho cùng một field. Hai cơ chế có hình dạng lưu trữ khác nhau; hãy chọn một cơ chế rõ ràng cho từng property.

## 10. Giới hạn và quy tắc thiết kế

Khi dùng composite mapping, cần lưu ý:

1. Key map chỉ hỗ trợ `String` hoặc enum; không dùng object tùy ý làm tên property.
2. Nested maps không được hỗ trợ bởi composite mapping mặc định. Nếu value object có cấu trúc lồng nhau, converter tùy chỉnh phải tự làm phẳng cấu trúc thành các key cấp một.
3. Mỗi property thành phần phải chuyển đổi được thành kiểu property hợp lệ của Neo4j. Dùng `Neo4jConversionService` để tận dụng conversion đã đăng ký.
4. Prefix và delimiter phải ổn định. Thay đổi chúng có thể làm SDN đọc không còn khớp với các property đã ghi.
5. Tránh trùng tên key với property khác trên cùng node hoặc relationship. Ví dụ `address_city` không nên đồng thời là field độc lập khác.
6. Đặt tên key phù hợp với truy vấn Cypher và quy ước schema. Nếu key chứa ký tự đặc biệt, việc truy vấn có thể cần cú pháp truy cập property phù hợp.
7. Giá trị `null` không được lưu như property Neo4j có giá trị null; gán null sẽ loại bỏ property. Xác định rõ việc thiếu key và xóa key trong nghiệp vụ.
8. Composite property không thay thế node/relationship nếu thành phần cần identity, lifecycle hoặc liên kết graph riêng.
9. Khi dùng converter tùy chỉnh, phải kiểm tra cả hai chiều `decompose` và `compose`, bao gồm dữ liệu thiếu key, null và dữ liệu được tạo ngoài SDN.

## 11. Kiểm tra dữ liệu composite

Sau khi lưu `Person` có `Address`, xác minh property phẳng:

```cypher
MATCH (p:Person {name: $name})
RETURN p.address_street AS street,
       p.address_city AS city,
       p.address_postalCode AS postalCode;
```

Kiểm tra các key có prefix:

```cypher
MATCH (p:Person)
RETURN keys(p) AS propertyKeys;
```

Khi thử nghiệm converter, cần kiểm tra ít nhất:

- Ghi một value object đầy đủ và đọc lại thành object có cùng giá trị.
- Ghi value object có một field tùy chọn là null.
- Cập nhật một thành phần và xác nhận các thành phần còn lại được giữ đúng.
- Xóa hoặc đặt value object thành null theo chính sách đã chọn.
- Đọc node được tạo bằng Cypher trực tiếp, trong đó một hoặc nhiều property composite bị thiếu.
- Kiểm tra property prefix không bị xung đột với field độc lập trên entity.

Một kiểm tra round-trip nên so sánh theo giá trị của value object, không dựa vào identity Java vì converter có thể tạo instance mới khi đọc.

## 12. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| SDN không ánh xạ một POJO lồng nhau thành property | Neo4j không lưu object tùy ý như nested object | Dùng `@CompositeProperty` và converter to-map hoặc mô hình hóa node/relationship |
| `@CompositeProperty` không nhận `Address` | Converter mặc định chỉ xử lý map | Cung cấp `Neo4jPersistentPropertyToMapConverter` |
| Field map không được đọc đủ | Prefix hoặc delimiter không khớp tên property trong graph | Kiểm tra `prefix`, `delimiter` và key đã ghi |
| Converter lỗi khi đọc property thiếu | `compose` giả định mọi key luôn tồn tại | Xử lý giá trị null/thiếu key hoặc xác thực dữ liệu |
| Dữ liệu cũ không còn được gom vào composite | Đổi prefix, delimiter hoặc key transformation mà không migration | Giữ quy ước ổn định hoặc migration các property cũ |
| Không truy vấn được nested map | Composite mapping mặc định không hỗ trợ nested maps | Làm phẳng map bằng converter tùy chỉnh |
| Property của relationship xuất hiện sai vị trí | Đặt composite field ở node sai hoặc nhầm `@RelationshipProperties` | Xác định dữ liệu thuộc node hay thuộc cạnh rồi đặt field tương ứng |
| Custom converter không được sử dụng | Chưa gắn `converter`/`converterRef` hoặc đăng ký `Neo4jConversions` sai phạm vi | Kiểm tra annotation và bean configuration |

## 13. Quy trình chọn cơ chế mapping

1. Xác định dữ liệu là value object hay thực thể có identity riêng.
2. Nếu chỉ là một giá trị đơn có thể biểu diễn bằng kiểu Neo4j, dùng conversion mặc định hoặc custom converter một `Value`.
3. Nếu dữ liệu gồm nhiều thành phần cần truy vấn riêng trên cùng node/relationship, chọn composite mapping.
4. Nếu cấu trúc là map linh hoạt, dùng `@CompositeProperty` mặc định.
5. Nếu cấu trúc là POJO/record cố định, viết `Neo4jPersistentPropertyToMapConverter` và gắn qua `@CompositeProperty`.
6. Chọn prefix, delimiter và key naming ổn định.
7. Kiểm tra converter theo cả hai chiều, null, key thiếu và dữ liệu ghi bằng Cypher.
8. Nếu nhiều entity dùng cùng một kiểu scalar custom, cân nhắc `Neo4jConversions`.
9. Nếu value object cần identity, quan hệ hoặc vòng đời riêng, mô hình hóa nó thành node và relationship.

## 14. Tự kiểm tra

1. Vì sao một value object Java không tự động được lưu thành object lồng nhau trong Neo4j?
2. `@CompositeProperty` mặc định hỗ trợ những kiểu map nào?
3. Prefix và delimiter ảnh hưởng ra sao tới tên property được ghi trong graph?
4. Khi nào cần triển khai `Neo4jPersistentPropertyToMapConverter`?
5. Hai phương thức `decompose` và `compose` chịu trách nhiệm gì?
6. Vì sao nested map không được hỗ trợ bởi composite mapping mặc định?
7. Khác biệt giữa `@CompositeProperty` và `@ConvertWith` là gì?
8. Khi nào nên đăng ký `GenericConverter` trong `Neo4jConversions`?
9. Nếu metadata thuộc về relationship thay vì node, nên đặt composite field ở đâu?
10. Khi nào nên chuyển một value object thành node riêng?

## Tài liệu tham khảo

- [Spring Data Neo4j — Conversions và Composite properties](https://docs.spring.io/spring-data/neo4j/reference/appendix/conversions.html)
- [Spring Data Neo4j — Metadata-based Mapping](https://docs.spring.io/spring-data/neo4j/reference/object-mapping/metadata-based-mapping.html)
- [Spring Data Neo4j — CompositeProperty API](https://docs.spring.io/spring-data/neo4j/reference/api/java/org/springframework/data/neo4j/core/schema/CompositeProperty.html)
- [Spring Data Neo4j — Neo4jPersistentPropertyToMapConverter API](https://docs.spring.io/spring-data/neo4j/docs/current/api/org/springframework/data/neo4j/core/convert/Neo4jPersistentPropertyToMapConverter.html)
- [Spring Data Neo4j — Neo4jConversionService API](https://docs.spring.io/spring-data/neo4j/reference/api/java/org/springframework/data/neo4j/core/convert/Neo4jConversionService.html)
