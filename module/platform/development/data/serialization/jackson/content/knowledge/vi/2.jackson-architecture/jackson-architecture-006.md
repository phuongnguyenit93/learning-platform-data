# Vai trò của module kiểu dữ liệu và module định dạng

Trong Jackson, việc chuyển một đối tượng Java thành dữ liệu để gửi qua HTTP, ghi xuống file hoặc trao đổi với hệ thống khác gồm hai câu hỏi riêng:

1. **Jackson hiểu giá trị Java này như thế nào?** Ví dụ `Optional`, `LocalDate`, kiểu của thư viện Guava hoặc một kiểu nghiệp vụ do ứng dụng tự định nghĩa cần được chuyển thành cấu trúc dữ liệu ra sao.
2. **Cấu trúc dữ liệu đó được biểu diễn trên đường truyền bằng định dạng nào?** Ví dụ JSON, XML, YAML, CSV hoặc một định dạng nhị phân.

Các module kiểu dữ liệu và module định dạng giải quyết hai câu hỏi ở hai phần khác nhau của kiến trúc Jackson. Module kiểu dữ liệu bổ sung cách Jackson đọc và ghi các kiểu Java. Module định dạng bổ sung cách Jackson đọc và ghi một định dạng dữ liệu. Hiểu ranh giới này giúp chọn đúng dependency, cấu hình đúng mapper và tránh nhầm lẫn giữa việc hỗ trợ một kiểu Java với việc hỗ trợ một định dạng đầu ra.

## 1. Đặt hai loại module vào kiến trúc Jackson

Jackson thường được sử dụng thông qua ba thành phần nền tảng:

| Thành phần | Trách nhiệm chính |
|---|---|
| `jackson-annotations` | Cung cấp metadata qua các annotation như `@JsonProperty`, `@JsonIgnore`, `@JsonFormat` và `@JsonCreator`. |
| `jackson-core` | Cung cấp API xử lý luồng dữ liệu ở mức thấp, gồm parser đọc token, generator ghi token và factory tạo parser/generator. |
| `jackson-databind` | Ánh xạ qua lại giữa cấu trúc token và đối tượng Java; cung cấp `ObjectMapper`, serializer, deserializer và cơ chế introspection. |

Hai nhóm module đang xét mở rộng các phần khác nhau quanh `jackson-databind` và `jackson-core`:

- **Module kiểu dữ liệu** bổ sung serializer, deserializer và các quy tắc binding để `databind` hiểu thêm những kiểu Java hoặc quy ước của một ngôn ngữ lập trình.
- **Module định dạng** cung cấp khả năng đọc và ghi một định dạng cụ thể. Chúng thường bổ sung factory, parser, generator và mapper chuyên biệt để nối định dạng đó với API streaming và, khi được hỗ trợ, với `databind`.

Có thể hình dung luồng serialize như sau:

```text
Đối tượng Java
     |
     v
Jackson Databind (ObjectMapper)
     |
     +---- Serializer có sẵn
     |
     +---- Serializer từ module kiểu dữ liệu
     |
     v
Các token qua API streaming của Jackson
     |
     v
Factory / Generator của định dạng được chọn
     |
     v
JSON, XML, YAML, CSV, Smile, CBOR, ...
```

Luồng deserialize đi theo chiều ngược lại: factory tạo parser cho định dạng đầu vào, parser đọc token, rồi `databind` và các deserializer tạo lại đối tượng Java. Cách chia lớp này cho phép cùng một kiểu Java được dùng với nhiều định dạng khi các module tương ứng tương thích với nhau.

Với JSON, `jackson-core` đã cung cấp parser và generator mặc định. Vì vậy, ứng dụng JSON thông thường không cần cài thêm một artifact `jackson-dataformat-json`. Các định dạng khác thường cần module riêng.

## 2. Module kiểu dữ liệu giải quyết vấn đề gì?

Các kiểu dữ liệu Java không phải lúc nào cũng tương ứng trực tiếp với những kiểu JSON cơ bản như object, array, string, number, boolean và null. Một số kiểu cần quy tắc chuyển đổi riêng; một số kiểu phụ thuộc vào metadata của ngôn ngữ hoặc thư viện bên ngoài.

Nếu Jackson không có serializer hoặc deserializer phù hợp, thao tác có thể thất bại với lỗi kiểu `InvalidDefinitionException`, hoặc dữ liệu được biểu diễn không đúng ý nghĩa mà ứng dụng mong muốn. Module kiểu dữ liệu cung cấp các quy tắc còn thiếu.

### 2.1. Bổ sung serializer và deserializer

Serializer quyết định cách một giá trị Java được ghi thành token. Deserializer quyết định cách đọc token để tạo lại giá trị Java. Module kiểu dữ liệu có thể đăng ký các bộ xử lý này cho một hoặc nhiều kiểu.

Ví dụ, `java.time.LocalDate` biểu diễn một ngày lịch, nhưng Jackson không thể suy ra mọi quy ước định dạng mà ứng dụng mong muốn chỉ từ tên kiểu. `JavaTimeModule` bổ sung hỗ trợ cho các kiểu ngày giờ thuộc Java Time API.

Tương tự, `Optional<T>` biểu diễn một giá trị có thể hiện diện hoặc vắng mặt. `Jdk8Module` bổ sung hỗ trợ cho `Optional` và một số kiểu thuộc JDK 8. Khi serialize, module quyết định cách biểu diễn giá trị có mặt hoặc rỗng; khi deserialize, module chuyển dữ liệu đầu vào thành `Optional` tương ứng.

Module không làm thay đổi bản chất của kiểu Java. Nó định nghĩa cách kiểu đó được chuyển qua ranh giới serialization. Quy tắc biểu diễn cụ thể vẫn có thể chịu ảnh hưởng từ cấu hình của mapper, chẳng hạn cấu hình timestamp, timezone hoặc inclusion.

### 2.2. Hỗ trợ quy ước của ngôn ngữ và thư viện

Không phải module kiểu dữ liệu nào cũng chỉ xử lý một lớp Java. Một số module hiểu thêm quy tắc khởi tạo object, constructor hoặc nullability của một ngôn ngữ:

| Module tiêu biểu | Khả năng được bổ sung |
|---|---|
| `jackson-datatype-jdk8` | Hỗ trợ `Optional`, `OptionalInt`, `OptionalLong`, `OptionalDouble` và các kiểu liên quan trong JDK 8. |
| `jackson-datatype-jsr310` | Hỗ trợ các kiểu ngày giờ trong `java.time`, như `LocalDate`, `LocalDateTime`, `Instant` và `ZonedDateTime`. |
| `jackson-datatype-guava` | Hỗ trợ các kiểu dữ liệu thuộc thư viện Guava. |
| `jackson-module-kotlin` | Hỗ trợ binding cho class Kotlin, constructor, tham số mặc định và một số quy tắc nullability của Kotlin. |
| `jackson-module-parameter-names` | Cho phép Jackson sử dụng tên tham số constructor được lưu trong bytecode khi tạo object trong những trường hợp phù hợp. |

Tên artifact giúp nhận diện mục đích nhưng không phải là quy tắc tuyệt đối. Chẳng hạn, `jackson-module-kotlin` và `jackson-module-parameter-names` cũng mở rộng khả năng binding, dù tên không bắt đầu bằng `jackson-datatype-`.

### 2.3. Hỗ trợ kiểu nghiệp vụ do ứng dụng định nghĩa

Ứng dụng có thể có các kiểu như `Money`, `PhoneNumber`, `GeoPoint` hoặc `EncryptedValue`. Nếu biểu diễn mặc định của Jackson không phù hợp với hợp đồng dữ liệu, ứng dụng có thể tạo một module riêng để đăng ký serializer và deserializer.

Ví dụ dưới đây minh họa cách đăng ký bộ xử lý cho một kiểu nghiệp vụ. `MoneySerializer` và `MoneyDeserializer` là các lớp do ứng dụng triển khai:

```java
SimpleModule moneyModule = new SimpleModule("money-module");
moneyModule.addSerializer(Money.class, new MoneySerializer());
moneyModule.addDeserializer(Money.class, new MoneyDeserializer());

ObjectMapper mapper = JsonMapper.builder()
        .addModule(moneyModule)
        .build();
```

Module tùy chỉnh giúp gom quy tắc chuyển đổi của một nhóm kiểu vào một đơn vị có tên, có thể đăng ký trên các mapper phù hợp. Cách này hữu ích khi cùng một quy tắc được sử dụng ở nhiều nơi hoặc cần được kiểm thử độc lập.

## 3. Module định dạng giải quyết vấn đề gì?

Module định dạng mở rộng khả năng đọc và ghi dữ liệu theo một giao thức hoặc cấu trúc biểu diễn cụ thể. Nó quyết định cách các giá trị được thể hiện thành văn bản hoặc byte, cách parser nhận diện cấu trúc đầu vào và những quy tắc riêng của định dạng.

Một số module phổ biến:

| Artifact | Mapper hoặc thành phần thường dùng | Đặc điểm |
|---|---|---|
| `jackson-dataformat-xml` | `XmlMapper` | Ánh xạ object thành phần tử, thuộc tính và cấu trúc XML. |
| `jackson-dataformat-yaml` | `YAMLMapper` | Đọc và ghi cấu trúc YAML. |
| `jackson-dataformat-csv` | `CsvMapper`, `CsvSchema` | Đọc và ghi dữ liệu dạng hàng/cột; thường cần schema để xác định cột và header. |
| `jackson-dataformat-smile` | `SmileFactory` | Đọc và ghi Smile, một định dạng nhị phân thuộc hệ sinh thái Jackson. |
| `jackson-dataformat-cbor` | `CBORFactory` | Đọc và ghi dữ liệu theo CBOR, một định dạng nhị phân. |

Các module trên không có cùng mức độ hỗ trợ mọi tính năng của `databind`. Khi chọn một định dạng cụ thể, cần kiểm tra khả năng hỗ trợ, schema và giới hạn của chính module đó.

### 3.1. Thay đổi cách biểu diễn dữ liệu trên đường truyền

Giả sử ứng dụng có object:

```java
public class Person {
    private long id;
    private String name;

    // Constructor, getter và setter được lược bỏ.
}
```

Cùng một object có thể được biểu diễn bằng nhiều định dạng. Ví dụ minh họa:

JSON:

```json
{
  "id": 1,
  "name": "An"
}
```

XML:

```xml
<Person>
    <id>1</id>
    <name>An</name>
</Person>
```

YAML:

```yaml
id: 1
name: An
```

CSV:

```csv
id,name
1,An
```

Object Java và ý nghĩa của hai thuộc tính vẫn như cũ, nhưng cách đóng gói trên đường truyền thay đổi. Hệ thống nhận dữ liệu phải hiểu đúng định dạng đã được chọn.

### 3.2. Cung cấp parser, generator và mapper phù hợp

Ở mức streaming, Jackson sử dụng parser để đọc và generator để ghi dữ liệu. `JsonFactory` tạo parser/generator JSON. Module định dạng khác cung cấp factory tương ứng hoặc thành phần tích hợp tương đương cho định dạng của nó.

Ở mức binding, các module định dạng thường cung cấp mapper chuyên biệt:

- `XmlMapper` làm việc với XML.
- `YAMLMapper` làm việc với YAML.
- `CsvMapper` làm việc với CSV và có thể kết hợp với `CsvSchema`.

Mapper chuyên biệt giúp ứng dụng không phải tự triển khai parser và generator cho từng định dạng. Nó vẫn tận dụng được các cơ chế binding quen thuộc của Jackson trong phạm vi định dạng hỗ trợ.

### 3.3. Định dạng có thể đặt ra quy tắc riêng

Không phải định dạng nào cũng có cấu trúc giống JSON. Vì vậy, đổi mapper không bảo đảm dữ liệu sẽ được chuyển đổi mà không cần cấu hình bổ sung.

- XML có phần tử, thuộc tính, namespace, phần tử lặp và quy tắc bao mảng. Ứng dụng có thể cần annotation hoặc cấu hình XML để xác định cấu trúc mong muốn.
- CSV có hàng và cột phẳng. Với `CsvMapper`, schema xác định tên cột, thứ tự cột và việc có header hay không. Cấu trúc object lồng nhau không tự nhiên như trong JSON.
- YAML hỗ trợ cấu trúc lồng nhau và kiểu scalar, nhưng cú pháp và cách xử lý một số giá trị khác JSON.
- Smile và CBOR là định dạng nhị phân. Dữ liệu đầu ra không nhằm đọc trực tiếp như văn bản thông thường.

Do đó, module định dạng không chỉ đổi phần mở rộng file. Nó xác định hợp đồng biểu diễn mà bên gửi và bên nhận phải cùng tuân thủ.

## 4. Hai nhóm module phối hợp như thế nào?

Module kiểu dữ liệu và module định dạng là hai chiều mở rộng độc lập về mặt khái niệm:

| Câu hỏi | Module kiểu dữ liệu | Module định dạng |
|---|---|---|
| Mở rộng điều gì? | Cách Jackson hiểu và chuyển đổi kiểu Java. | Cách Jackson đọc và ghi định dạng dữ liệu. |
| Tác động chủ yếu | Serializer, deserializer và quy tắc binding. | Factory, parser, generator, mapper và quy tắc riêng của định dạng. |
| Ví dụ | `LocalDate`, `Optional`, kiểu Guava, Kotlin data class. | XML, YAML, CSV, Smile, CBOR. |
| Khi nào cần? | Khi kiểu Java chưa được hỗ trợ hoặc cần quy tắc chuyển đổi riêng. | Khi hệ thống trao đổi dữ liệu bằng định dạng khác JSON hoặc cần API streaming tương ứng. |

Ví dụ, ứng dụng cần xuất một `Person` có trường `LocalDate` thành XML. Hai yêu cầu xuất hiện đồng thời:

1. Jackson cần biết cách chuyển `LocalDate` thành dữ liệu: vai trò của module kiểu dữ liệu `JavaTimeModule`.
2. Jackson cần biết cách ghi cấu trúc đó thành XML: vai trò của `XmlMapper` từ module định dạng XML.

Ví dụ cấu hình:

```java
import com.fasterxml.jackson.dataformat.xml.XmlMapper;
import com.fasterxml.jackson.datatype.jsr310.JavaTimeModule;

public class XmlSerializationExample {
    public static void main(String[] args) throws Exception {
        XmlMapper xmlMapper = new XmlMapper();
        xmlMapper.registerModule(new JavaTimeModule());

        Person person = new Person(/* dữ liệu của ứng dụng */);
        String xml = xmlMapper.writeValueAsString(person);

        Person restored = xmlMapper.readValue(xml, Person.class);
    }
}
```

Trong ví dụ, `XmlMapper` chọn cơ chế đọc/ghi XML; `JavaTimeModule` bổ sung cách xử lý `LocalDate`. Nếu bỏ module kiểu dữ liệu trong khi object chứa `LocalDate`, Jackson có thể không biết cách xử lý trường đó tùy phiên bản và cấu hình. Nếu bỏ mapper định dạng XML, ứng dụng không có cơ chế XML tương ứng để tạo chuỗi XML.

Nguyên tắc tương tự áp dụng khi ghi YAML hoặc CSV: chọn mapper theo định dạng, sau đó đăng ký các module kiểu dữ liệu cần thiết nếu mapper và định dạng đó hỗ trợ chúng.

## 5. Ví dụ cấu hình theo từng nhu cầu

### 5.1. JSON với `Optional` và Java Time

Khi chỉ làm việc với JSON, ứng dụng có thể dùng `JsonMapper` và đăng ký các module kiểu dữ liệu:

```java
import com.fasterxml.jackson.databind.SerializationFeature;
import com.fasterxml.jackson.databind.json.JsonMapper;
import com.fasterxml.jackson.datatype.jdk8.Jdk8Module;
import com.fasterxml.jackson.datatype.jsr310.JavaTimeModule;

ObjectMapper mapper = JsonMapper.builder()
        .addModule(new Jdk8Module())
        .addModule(new JavaTimeModule())
        .disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS)
        .build();
```

Ở đây:

- `Jdk8Module` bổ sung hỗ trợ cho `Optional` và các kiểu JDK 8 liên quan.
- `JavaTimeModule` bổ sung hỗ trợ cho các kiểu `java.time`.
- `WRITE_DATES_AS_TIMESTAMPS` được tắt để chọn cách ghi ngày giờ dạng văn bản thay vì dạng timestamp/array đối với những kiểu chịu ảnh hưởng của feature này.

Ví dụ dependency Gradle khi dự án đã có BOM quản lý phiên bản Jackson:

```kotlin
dependencies {
    implementation("com.fasterxml.jackson.datatype:jackson-datatype-jdk8")
    implementation("com.fasterxml.jackson.datatype:jackson-datatype-jsr310")
}
```

### 5.2. XML với kiểu ngày giờ

Để ghi XML, thêm module định dạng XML và tạo `XmlMapper`. Nếu object chứa `LocalDate` hoặc kiểu `java.time` khác, đăng ký thêm module kiểu dữ liệu tương ứng:

```kotlin
dependencies {
    implementation("com.fasterxml.jackson.dataformat:jackson-dataformat-xml")
    implementation("com.fasterxml.jackson.datatype:jackson-datatype-jsr310")
}
```

```java
XmlMapper xmlMapper = new XmlMapper();
xmlMapper.registerModule(new JavaTimeModule());

String xml = xmlMapper.writeValueAsString(person);
Person restored = xmlMapper.readValue(xml, Person.class);
```

`jackson-dataformat-xml` giải quyết phần XML; `jackson-datatype-jsr310` giải quyết phần Java Time. Hai dependency có thể cùng xuất hiện vì chúng phục vụ hai lớp khác nhau.

### 5.3. CSV với schema

CSV thường cần xác định cột trước khi đọc hoặc ghi. Ví dụ ghi danh sách `Person` với header:

```java
CsvMapper csvMapper = new CsvMapper();
CsvSchema schema = csvMapper.schemaFor(Person.class).withHeader();

String csv = csvMapper.writer(schema).writeValueAsString(people);
```

Khi đọc, sử dụng schema tương ứng:

```java
MappingIterator<Person> iterator = csvMapper
        .readerFor(Person.class)
        .with(schema)
        .readValues(csv);

List<Person> people = iterator.readAll();
```

Ví dụ cho thấy việc hỗ trợ định dạng CSV bao gồm cả quy tắc schema. Nếu producer và consumer không thống nhất tên hoặc thứ tự cột, dữ liệu có thể bị ánh xạ sai dù cả hai phía đều dùng Jackson.

## 6. Phân biệt tên gọi `Module` trong Jackson

Từ “module” trong hệ sinh thái Jackson có thể chỉ nhiều khái niệm gần nhau nhưng không hoàn toàn giống nhau.

### 6.1. `com.fasterxml.jackson.databind.Module`

Đây là abstraction ở tầng `databind` dùng để đăng ký các phần mở rộng với mapper. Các module kiểu dữ liệu thường sử dụng cơ chế này để cung cấp serializer, deserializer, modifier, annotation introspector hoặc các thành phần binding khác.

Ví dụ, `JavaTimeModule` có thể được đăng ký bằng `registerModule(...)` hoặc builder `addModule(...)`.

### 6.2. Artifact `jackson-datatype-*` và `jackson-module-*`

Đây là cách đặt tên artifact cho các thư viện mở rộng kiểu dữ liệu hoặc quy tắc binding. Nhiều artifact trong nhóm này cung cấp một implementation của `databind.Module` để mapper đăng ký.

### 6.3. Artifact `jackson-dataformat-*`

Đây là nhóm thư viện cung cấp hỗ trợ cho định dạng. Chúng thường cung cấp factory và mapper chuyên biệt. Không nên suy luận rằng mọi artifact có chữ “module” trong tên đều là một `databind.Module`, hoặc rằng thêm dependency định dạng sẽ tự động làm cho `ObjectMapper` JSON hiện có chuyển sang định dạng mới.

Ví dụ, thêm `jackson-dataformat-xml` vào classpath không có nghĩa mọi lời gọi `new ObjectMapper()` sẽ tự ghi XML. Ứng dụng cần tạo và sử dụng `XmlMapper` hoặc cấu hình factory XML phù hợp.

## 7. Quản lý dependency và đăng ký module

Một module chỉ có thể được sử dụng khi artifact tương ứng có trên runtime classpath. Tuy nhiên, có dependency không phải lúc nào cũng đồng nghĩa mapper đã đăng ký module.

### 7.1. Khai báo đúng dependency

Chọn dependency theo nhu cầu thực tế:

- Cần `Optional`: thêm `jackson-datatype-jdk8`.
- Cần `java.time`: thêm `jackson-datatype-jsr310`.
- Cần XML: thêm `jackson-dataformat-xml`.
- Cần YAML: thêm `jackson-dataformat-yaml`.
- Cần CSV: thêm `jackson-dataformat-csv`.

Các artifact Jackson nên dùng những phiên bản tương thích với nhau. Nếu dự án dùng Spring Boot hoặc một BOM quản lý dependency, nên để dependency management chọn phiên bản đồng bộ. Nếu tự quản lý phiên bản, cần kiểm tra sự tương thích giữa `jackson-core`, `jackson-databind`, các module datatype và các module dataformat.

### 7.2. Đăng ký rõ ràng khi tự tạo mapper

Khi ứng dụng tự tạo mapper, có thể đăng ký module trực tiếp:

```java
ObjectMapper mapper = JsonMapper.builder()
        .addModule(new Jdk8Module())
        .addModule(new JavaTimeModule())
        .build();
```

Hoặc với mapper đã được tạo:

```java
ObjectMapper mapper = new ObjectMapper();
mapper.registerModule(new JavaTimeModule());
```

Jackson cũng có cơ chế khám phá module qua `findAndRegisterModules()` trong những cấu hình phù hợp. Cơ chế tự khám phá phụ thuộc vào metadata service provider và classpath hiện tại. Đăng ký tường minh thường dễ đọc, dễ kiểm soát và dễ xác định module nào đang được sử dụng hơn.

Với ứng dụng Spring Boot, auto-configuration có thể tự phát hiện và đăng ký một số module có mặt trên classpath vào mapper do framework quản lý. Hành vi này phụ thuộc phiên bản và cấu hình; cần phân biệt mapper do Spring quản lý với mapper được tạo thủ công bằng `new ObjectMapper()`.

### 7.3. Cấu hình mapper trước khi dùng đồng thời

Nên hoàn tất việc đăng ký module và cấu hình serialization/deserialization trước khi mapper được sử dụng trong nhiều luồng. Sau khi cấu hình xong, mapper thường được tái sử dụng thay vì tạo mới cho từng request. Nếu một định dạng cần cấu hình riêng, nên tạo mapper tương ứng cho định dạng đó để cấu hình dễ hiểu và không vô tình dùng nhầm factory.

## 8. Những nhầm lẫn thường gặp

**Nhầm rằng module kiểu dữ liệu là module định dạng.** `JavaTimeModule` giúp Jackson xử lý `LocalDate`; nó không biến JSON thành XML. `jackson-dataformat-xml` giúp Jackson đọc/ghi XML; nó không tự định nghĩa toàn bộ quy tắc cho mọi kiểu Java bên thứ ba.

**Nhầm rằng thêm dependency là đủ.** Với mapper tự tạo, module kiểu dữ liệu thường cần được đăng ký. Với định dạng khác JSON, ứng dụng cần dùng mapper hoặc factory đúng định dạng. Framework có thể tự cấu hình một số trường hợp, nhưng không nên mặc định điều đó áp dụng cho mọi mapper.

**Cho rằng cùng object sẽ luôn có cùng cấu trúc ở mọi định dạng.** XML có phần tử và thuộc tính; CSV có cột; định dạng nhị phân có quy tắc mã hóa riêng. Annotation hoặc cấu hình phù hợp với JSON chưa chắc tạo ra cấu trúc tương đương ở định dạng khác.

**Cho rằng module kiểu dữ liệu bảo đảm mọi định dạng đều hỗ trợ kiểu đó.** Module datatype và dataformat chỉ phối hợp được khi tích hợp của định dạng hỗ trợ các cơ chế binding cần thiết. Với định dạng có giới hạn riêng, cần thử serialize và deserialize trên đúng mapper sẽ dùng trong ứng dụng.

**Trộn phiên bản Jackson.** Một module có phiên bản không tương thích với `jackson-databind` hoặc `jackson-core` có thể gây lỗi runtime khó hiểu. Hãy để BOM quản lý phiên bản hoặc đồng bộ các artifact theo cùng dòng phát hành.

**Dùng một mapper cho mọi mục đích mà không xét factory.** Mapper được tạo cho JSON sẽ dùng factory JSON mặc định. Muốn đọc/ghi XML, YAML hoặc CSV, phải chọn mapper/factory tương ứng. Cấu hình kiểu dữ liệu có thể được chia sẻ khi tương thích, nhưng factory định dạng vẫn phải đúng.

## 9. Cách chọn module trong một tình huống thực tế

Khi một trường hợp serialization phát sinh, có thể lần lượt xác định:

1. **Kiểu Java nào đang được chuyển đổi?** Kiểm tra kiểu chuẩn của JDK, kiểu từ thư viện ngoài hay kiểu nghiệp vụ riêng. Nếu Jackson thiếu quy tắc chuyển đổi, tìm module datatype/binding hoặc viết serializer và deserializer riêng.
2. **Đầu ra hoặc đầu vào dùng định dạng nào?** JSON thường dùng mapper mặc định; XML, YAML, CSV và các định dạng khác cần mapper/factory tương ứng.
3. **Mapper có đăng ký đủ module không?** Kiểm tra mapper thực tế được dùng trong đường đi của ứng dụng, đặc biệt khi có nhiều mapper hoặc framework auto-configuration.
4. **Định dạng có yêu cầu schema hoặc cấu hình riêng không?** CSV thường cần schema; XML có thể cần cấu hình tên phần tử, thuộc tính và cách bao collection.
5. **Có thể đọc lại dữ liệu đã ghi không?** Kiểm tra cả chiều serialize và deserialize bằng cùng cấu hình hoặc cấu hình tương thích với hợp đồng dữ liệu của hệ thống nhận.

Ví dụ, nếu `LocalDate` không serialize được thành JSON, trước tiên kiểm tra dependency và việc đăng ký `JavaTimeModule`. Nếu cùng object cần xuất XML, tiếp tục kiểm tra `jackson-dataformat-xml` và việc sử dụng `XmlMapper`. Nếu dữ liệu cần xuất CSV, kiểm tra `CsvMapper` cùng schema cột. Mỗi bước xử lý một lớp nguyên nhân khác nhau.

## 10. Kết luận kiến trúc

Module kiểu dữ liệu mở rộng **ý nghĩa của việc ánh xạ giữa kiểu Java và dữ liệu**. Module định dạng mở rộng **cách dữ liệu được đọc và ghi theo một biểu diễn cụ thể**. `jackson-databind` điều phối việc binding; các module kiểu dữ liệu bổ sung quy tắc binding; các module định dạng kết nối quá trình đó với parser, generator và factory của định dạng tương ứng.

Khi phân tích một lỗi Jackson, hãy xác định lỗi nằm ở kiểu Java, ở cấu hình binding hay ở định dạng đầu vào/đầu ra. Xác định đúng lớp sẽ giúp chọn dependency và mapper cần thiết, đồng thời giữ cho mô hình Java của ứng dụng độc lập tương đối với định dạng trao đổi dữ liệu.
