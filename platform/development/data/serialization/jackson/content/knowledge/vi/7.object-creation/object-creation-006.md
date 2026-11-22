# Ánh xạ Java record theo khả năng hỗ trợ của phiên bản

## 1. Java record và nhu cầu ánh xạ JSON

Java `record` là một dạng khai báo lớp tập trung vào việc mang dữ liệu. Các component được khai báo ngay trên phần đầu của record; từ đó Java cung cấp constructor chính tắc (canonical constructor), accessor cho từng component, cùng các phương thức `equals`, `hashCode` và `toString`.

Ví dụ:

```java
public record Customer(String id, String name, int age) {
}
```

Khai báo trên tương đương một kiểu dữ liệu có ba thành phần dữ liệu `id`, `name` và `age`. Accessor của record có tên đúng bằng component, chẳng hạn `customer.name()`, thay vì getter theo quy ước JavaBean như `getName()`. Các component cũng được lưu trong những field final và không có setter thông thường.

Đặc điểm này khiến record phù hợp với DTO, message và các đối tượng dữ liệu bất biến. Khi dùng Jackson, ứng dụng thường cần thực hiện hai thao tác:

- **Serialization:** chuyển một record thành JSON dựa trên giá trị các component.
- **Deserialization:** đọc JSON rồi tạo record bằng constructor chính tắc với các giá trị component tương ứng.

Khả năng ánh xạ phụ thuộc vào phiên bản Jackson Databind. Không thể suy ra rằng mọi phiên bản Jackson đều nhận diện record giống nhau chỉ vì mã nguồn Java biên dịch thành công.

## 2. Mốc hỗ trợ record trong Jackson

Record được đưa vào Java dưới dạng preview ở Java 14 và Java 15, sau đó trở thành tính năng chính thức từ Java 16. Jackson Databind bổ sung hỗ trợ native cho Java record từ dòng **2.12**.

| Môi trường | Khả năng và lưu ý |
|---|---|
| Java 14–15 | Record là tính năng preview. Cần bật preview tương ứng khi biên dịch và chạy; đây không phải lựa chọn phù hợp cho ví dụ mới nếu có thể dùng Java đã phát hành chính thức. |
| Java 16 trở lên + Jackson Databind 2.12 trở lên | Có hỗ trợ native cho record. Jackson nhận diện record component và dùng canonical constructor để tạo đối tượng khi deserialization. |
| Jackson Databind 2.11 trở về trước | Chưa có hỗ trợ native record như từ 2.12. Không nên giả định record accessor và constructor sẽ được nhận diện đầy đủ theo cơ chế dành riêng cho record. Nên nâng Jackson hoặc dùng một lớp Java thông thường với creator/parameter được annotation tường minh và kiểm tra trên đúng phiên bản đang chạy. |
| Jackson 2.x mới hơn | Tiếp tục dùng cơ chế hỗ trợ record của dòng 2.x; vẫn cần căn chỉnh phiên bản các artifact Jackson và kiểm tra module cho kiểu dữ liệu bổ sung. |

Mốc 2.12 nói về hỗ trợ record của **Jackson Databind**. Cần phân biệt điều này với hỗ trợ một kiểu Java cụ thể khác. Ví dụ, Jackson hiểu cấu trúc record không có nghĩa mọi kiểu component đều tự động được hỗ trợ. Nếu component là `Instant`, ứng dụng vẫn cần module Java Time tương ứng.

Với dự án mới, một tổ hợp dễ triển khai là Java 17 hoặc mới hơn cùng một phiên bản Jackson 2.x có hỗ trợ record. Java 17 là LTS và record đã là tính năng chính thức, nên không cần bật preview feature.

## 3. Căn chỉnh phiên bản các artifact Jackson

Một ứng dụng dùng record thường cần `jackson-databind`. Artifact này kéo theo các thành phần nền tảng như `jackson-core` và `jackson-annotations`. Nếu record có component thuộc Java Time, cần thêm `jackson-datatype-jsr310`.

Hãy quản lý các artifact Jackson bằng một phiên bản thống nhất. Với Maven, Jackson BOM giúp chọn phiên bản cho các dependency thuộc cùng bộ phát hành:

```xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
    <jackson.version>2.17.2</jackson.version>
</properties>

<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>com.fasterxml.jackson</groupId>
            <artifactId>jackson-bom</artifactId>
            <version>${jackson.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>com.fasterxml.jackson.core</groupId>
        <artifactId>jackson-databind</artifactId>
    </dependency>
    <dependency>
        <groupId>com.fasterxml.jackson.datatype</groupId>
        <artifactId>jackson-datatype-jsr310</artifactId>
    </dependency>
</dependencies>
```

`2.17.2` là phiên bản minh họa được ghim cố định để ví dụ có môi trường xác định, không phải tuyên bố về phiên bản mới nhất. Khi áp dụng vào dự án, chọn phiên bản đã được dự án phê duyệt và cập nhật property đó; BOM sẽ giữ các artifact liên quan đồng bộ.

Nếu dùng Gradle Kotlin DSL, có thể quản lý tương tự:

```kotlin
dependencies {
    implementation(platform("com.fasterxml.jackson:jackson-bom:2.17.2"))
    implementation("com.fasterxml.jackson.core:jackson-databind")
    implementation("com.fasterxml.jackson.datatype:jackson-datatype-jsr310")
}
```

Không nên khai báo `jackson-databind` ở một phiên bản nhưng tự chọn `jackson-datatype-jsr310` ở một phiên bản không tương thích. Nếu có dependency bắc cầu kéo một phiên bản khác vào, hãy kiểm tra dependency tree hoặc dependency insight để xác định artifact thực tế trên runtime classpath.

## 4. Jackson tạo record bằng canonical constructor

Với một lớp Java thông thường, Jackson thường có thể tạo đối tượng qua constructor không tham số rồi gán thuộc tính bằng setter hoặc field. Record được thiết kế bất biến và không có setter thông thường, vì vậy cách tạo đối tượng tự nhiên là gọi canonical constructor.

Với record:

```java
public record Customer(String id, String name, int age) {
}
```

canonical constructor có các tham số tương ứng với thứ tự component:

```java
public Customer(String id, String name, int age) {
    this.id = id;
    this.name = name;
    this.age = age;
}
```

Khi Jackson đọc JSON thành `Customer`, nó ánh xạ các thuộc tính JSON sang component rồi gọi constructor này. Sau khi được tạo, các component không thể được gán lại bằng setter như một POJO mutable thông thường.

```text
JSON object
    |
    v
Nhận diện các record component
    |
    v
Ánh xạ giá trị cho từng component
    |
    v
Gọi canonical constructor
    |
    v
Customer record (đối tượng đã được tạo)
```

Vì record không có setter, nếu JSON thiếu component hoặc có giá trị không tương thích, kết quả phụ thuộc vào kiểu component, cấu hình deserialization và kiểm tra trong canonical constructor. Không nên giả định mọi trường hợp thiếu hoặc null đều tự động bị từ chối.

## 5. Ví dụ cơ bản với record và `ObjectMapper`

Ví dụ sau dùng Java 17 và Jackson Databind 2.12 trở lên. Record chỉ có các kiểu dữ liệu cơ bản để tập trung vào cơ chế record mapping:

```java
import com.fasterxml.jackson.databind.ObjectMapper;

public class BasicRecordMapping {

    public record Customer(String id, String name, int age) {
    }

    public static void main(String[] args) throws Exception {
        ObjectMapper mapper = new ObjectMapper();

        String input = """
                {
                  "id": "C-100",
                  "name": "An",
                  "age": 28
                }
                """;

        Customer customer = mapper.readValue(input, Customer.class);
        System.out.println(customer.name());

        String output = mapper.writeValueAsString(customer);
        System.out.println(output);
    }
}
```

Khi deserialization, Jackson đọc `id`, `name` và `age`, sau đó tạo `Customer` qua canonical constructor. Khi serialization, Jackson đọc giá trị từ các record component để tạo JSON.

Không cần thêm setter, cũng không cần tự viết một constructor không tham số cho record. Constructor chính tắc là điểm tạo đối tượng của record.

## 6. Đổi tên thuộc tính JSON bằng annotation trên record component

Tên component trong Java không nhất thiết phải trùng với tên thuộc tính JSON của API. Có thể đặt `@JsonProperty` trực tiếp trên component:

```java
import com.fasterxml.jackson.annotation.JsonProperty;

public record Customer(
        @JsonProperty("customer_id") String id,
        @JsonProperty("full_name") String name,
        int age
) {
}
```

Với định nghĩa trên, JSON dùng `customer_id` và `full_name`, còn mã Java tiếp tục truy cập bằng `customer.id()` và `customer.name()`.

```json
{
  "customer_id": "C-100",
  "full_name": "An Nguyen",
  "age": 28
}
```

Các annotation Jackson thường dùng cho property như `@JsonProperty`, `@JsonAlias`, `@JsonFormat` hoặc `@JsonInclude` có thể được áp dụng cho record component khi mục tiêu và kiểu annotation tương ứng cho phép. Hãy dùng annotation ở component để thể hiện rõ metadata gắn với dữ liệu nào.

Ví dụ, `@JsonAlias` có thể cho phép nhận thêm tên cũ khi đọc JSON trong giai đoạn chuyển đổi API:

```java
public record Customer(
        @JsonProperty("customer_id")
        @JsonAlias("id")
        String id,
        @JsonProperty("full_name") String name
) {
}
```

Ở đây, `customer_id` là tên chuẩn được dùng khi serialization; `id` là bí danh có thể được nhận khi deserialization. Cần xác định rõ thời gian duy trì alias để tránh hỗ trợ vô thời hạn những tên API đã ngừng sử dụng.

## 7. Record có component thuộc Java Time

Record mapping và hỗ trợ kiểu dữ liệu Java Time là hai khả năng riêng. Jackson Databind 2.12+ hiểu cấu trúc record, nhưng để xử lý `Instant`, `LocalDate` hoặc `LocalDateTime`, ứng dụng cần đăng ký `JavaTimeModule` từ artifact `jackson-datatype-jsr310`.

```java
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.SerializationFeature;
import com.fasterxml.jackson.databind.json.JsonMapper;
import com.fasterxml.jackson.datatype.jsr310.JavaTimeModule;

import java.time.Instant;

public class RecordWithTime {

    public record AuditEvent(String eventId, Instant occurredAt) {
    }

    public static void main(String[] args) throws Exception {
        ObjectMapper mapper = JsonMapper.builder()
                .addModule(new JavaTimeModule())
                .disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS)
                .build();

        String input = """
                {
                  "eventId": "EV-42",
                  "occurredAt": "2025-03-08T10:15:30Z"
                }
                """;

        AuditEvent event = mapper.readValue(input, AuditEvent.class);
        String output = mapper.writeValueAsString(event);

        System.out.println(event.occurredAt());
        System.out.println(output);
    }
}
```

Tắt `WRITE_DATES_AS_TIMESTAMPS` để ví dụ ghi `Instant` thành chuỗi ngày giờ ISO-8601. Nếu không đăng ký module Java Time, mapper có thể báo lỗi không tìm được serializer hoặc deserializer phù hợp cho `Instant`, dù record mapping đã được phiên bản Jackson hỗ trợ.

## 8. Kiểm tra dữ liệu trong canonical constructor

Một lợi ích của record là có thể đặt quy tắc bất biến ngay trong compact canonical constructor. Jackson gọi constructor khi tạo record, vì vậy các kiểm tra này cũng được thực hiện khi đọc JSON.

```java
import java.math.BigDecimal;

public record Product(String sku, BigDecimal price, int quantity) {
    public Product {
        if (sku == null || sku.isBlank()) {
            throw new IllegalArgumentException("sku is required");
        }
        if (price == null || price.signum() < 0) {
            throw new IllegalArgumentException("price must be non-negative");
        }
        if (quantity < 0) {
            throw new IllegalArgumentException("quantity must be non-negative");
        }
    }
}
```

Compact constructor cho phép kiểm tra và chuẩn hóa tham số trước khi các field record được gán tự động. Nếu dữ liệu JSON tạo ra một tổ hợp component không hợp lệ, constructor có thể ném ngoại lệ và Jackson sẽ báo lỗi deserialization (thường được bọc trong ngoại lệ mapping của Jackson).

Hãy đặt validation có tính bất biến của kiểu dữ liệu trong constructor, chẳng hạn mã định danh bắt buộc hoặc số lượng không âm. Những quy tắc cần truy cập database, quyền người dùng hoặc trạng thái hệ thống nên được thực hiện ở tầng dịch vụ, vì constructor của record không nên phụ thuộc vào hạ tầng ứng dụng.

## 9. Xử lý component bị thiếu, null hoặc sai kiểu

Record không có setter để bổ sung giá trị sau khi khởi tạo. Vì thế, dữ liệu đầu vào cần được kiểm soát trước hoặc trong lúc Jackson gọi canonical constructor.

Với component tham chiếu như `String`, `BigDecimal` hoặc `Instant`:

- Nếu JSON không có thuộc tính tương ứng, giá trị truyền vào constructor phụ thuộc vào cấu hình creator-property và cách Jackson xử lý thuộc tính thiếu.
- Nếu JSON có thuộc tính với giá trị `null`, Jackson truyền giá trị null cho component tham chiếu, trừ khi cấu hình hoặc kiểu đích áp dụng quy tắc khác.
- Nếu JSON có kiểu không tương thích, chẳng hạn chuỗi không thể chuyển thành số theo cấu hình hiện tại, quá trình ánh xạ có thể thất bại.

Với component primitive như `int` hoặc `boolean`, Java không có giá trị null. Nếu muốn từ chối JSON null cho primitive, có thể bật `FAIL_ON_NULL_FOR_PRIMITIVES`. Với creator properties, có thể bật các feature như `FAIL_ON_MISSING_CREATOR_PROPERTIES` và `FAIL_ON_NULL_CREATOR_PROPERTIES` khi hợp đồng dữ liệu yêu cầu mọi component phải được cung cấp và không được null.

Ví dụ cấu hình chặt hơn:

```java
ObjectMapper strictMapper = JsonMapper.builder()
        .enable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES)
        .enable(DeserializationFeature.FAIL_ON_MISSING_CREATOR_PROPERTIES)
        .enable(DeserializationFeature.FAIL_ON_NULL_CREATOR_PROPERTIES)
        .enable(DeserializationFeature.FAIL_ON_NULL_FOR_PRIMITIVES)
        .build();
```

Không nên bật tất cả các feature này một cách máy móc. Chọn chúng theo hợp đồng API: một component có thể là tùy chọn hợp lệ, trong khi component khác là bắt buộc. Nếu constructor đã kiểm tra `null` hoặc giá trị không hợp lệ, cần thống nhất thông báo lỗi và cách ánh xạ ngoại lệ ở tầng API.

## 10. Khi nào cần `@JsonCreator` và `@JsonProperty`?

Với record và Jackson Databind 2.12+, cơ chế native record support nhận diện canonical constructor, nên trường hợp thông thường không cần tự thêm `@JsonCreator` chỉ để Jackson tạo record.

`@JsonProperty` vẫn hữu ích để đổi tên component JSON hoặc làm rõ tên property. `@JsonCreator` thường quan trọng hơn với lớp Java thông thường có nhiều constructor hoặc constructor không tham số không phù hợp. Khi dùng creator tường minh cho một lớp không phải record, có thể khai báo:

```java
public class LegacyCustomer {
    private final String id;
    private final String name;

    @JsonCreator
    public LegacyCustomer(
            @JsonProperty("id") String id,
            @JsonProperty("name") String name
    ) {
        this.id = id;
        this.name = name;
    }

    public String getId() {
        return id;
    }

    public String getName() {
        return name;
    }
}
```

Đây là một kiểu immutable class thông thường, không phải record. Ví dụ cho thấy cách ánh xạ constructor tường minh có thể dùng khi phải duy trì mã nguồn tương thích với phiên bản Jackson chưa có hỗ trợ native record. Cần kiểm tra đúng phiên bản thư viện, compiler parameter metadata và cấu hình annotation của dự án; `ParameterNamesModule` không nên được xem là sự thay thế tự động cho native record support.

## 11. Kiểm soát thuộc tính không biết và thay đổi schema

Record có tập component được khai báo cố định. Khi JSON từ hệ thống khác bổ sung thuộc tính mới, mapper có thể xử lý theo chính sách `FAIL_ON_UNKNOWN_PROPERTIES`:

- Bật feature: thuộc tính không được record khai báo có thể làm deserialization thất bại.
- Tắt feature: thuộc tính lạ thường được bỏ qua, giúp consumer cũ tiếp tục đọc payload có thêm trường.

Chọn chính sách dựa trên yêu cầu tương thích. Nếu API cần tiến hóa theo hướng thêm trường mà consumer cũ vẫn hoạt động, bỏ qua thuộc tính mới có thể phù hợp. Nếu payload phải tuân thủ schema nghiêm ngặt, bật lỗi thuộc tính không biết có thể giúp phát hiện sai lệch sớm.

Có thể đặt `@JsonIgnoreProperties(ignoreUnknown = true)` trên record để chỉ định hành vi bỏ qua thuộc tính lạ cho kiểu đó. Hãy tránh vừa bật/tắt feature toàn cục vừa đặt annotation ở nhiều lớp mà không có quy ước rõ ràng, vì chính sách ở cấp lớp và cấp mapper có thể làm người đọc khó dự đoán kết quả.

Khi đổi tên component JSON, cân nhắc `@JsonAlias` để nhận tên cũ trong giai đoạn chuyển đổi. Serialization vẫn dùng tên chuẩn được chỉ định bởi `@JsonProperty`; alias chủ yếu hỗ trợ chiều đọc. Sau thời gian tương thích, có thể loại bỏ alias cùng với phiên bản API cũ.

## 12. Thiết kế thử nghiệm tương thích theo phiên bản

Khi kiểm tra một dự án có nhiều phiên bản Jackson, hãy tách câu hỏi “Java có biên dịch record không?” khỏi câu hỏi “Jackson có ánh xạ record không?”. Compiler xác nhận cú pháp Java; Jackson Databind quyết định khả năng mapping lúc chạy.

Một ma trận thử nghiệm thực tế có thể như sau:

| Ca thử | Java | Jackson Databind | Mục tiêu |
|---|---|---|---|
| R01 | 17 | 2.11.x | Xác nhận đây là mốc trước native record support; không kỳ vọng mapping record tự động như dòng mới |
| R02 | 17 | 2.12.x | Kiểm tra mốc đầu tiên có hỗ trợ record |
| R03 | 17 | 2.17.2 | Kiểm tra serialization và canonical-constructor deserialization trên phiên bản đã ghim trong ví dụ |
| R04 | 21 | Phiên bản Jackson dự án đang dùng | Xác nhận tương thích trong runtime JDK mục tiêu của ứng dụng |

Mỗi lượt cần ghi lại:

- Phiên bản JDK thực tế khi chạy chương trình.
- Phiên bản `jackson-databind`, `jackson-core`, `jackson-annotations` và các module Jackson liên quan.
- Kết quả serialization của một record mẫu.
- Kết quả deserialization từ JSON về record.
- Cách xử lý component thiếu, null, sai kiểu và thuộc tính lạ.

Nếu một phiên bản cũ không ánh xạ record như mong đợi, không nên chỉ đổi annotation rồi kết luận nguyên nhân. Trước hết xác nhận dependency runtime có đúng phiên bản dự định không, sau đó kiểm tra khả năng native support của dòng Jackson đó. Cách giải quyết bền vững thường là nâng lên phiên bản có hỗ trợ record hoặc dùng DTO/class thông thường với constructor được annotation rõ ràng trong thời gian chuyển tiếp.

## 13. Lựa chọn record hay POJO thông thường

Record phù hợp khi dữ liệu có cấu trúc cố định, component được xác định ngay khi tạo và đối tượng nên bất biến. Ví dụ gồm response DTO, sự kiện, kết quả truy vấn hoặc cấu trúc dữ liệu trung gian.

POJO thông thường có thể phù hợp hơn khi:

- Cần tạo đối tượng rỗng rồi gán thuộc tính qua nhiều bước.
- Cần setter để hỗ trợ một framework hoặc quy trình binding cụ thể.
- Có vòng đời mutable rõ ràng.
- Cần tương thích với phiên bản Jackson cũ chưa có native record support.
- Mô hình có hành vi phức tạp và không chỉ là một tập giá trị bất biến.

Không nên chuyển mọi lớp DTO sang record chỉ vì cú pháp ngắn hơn. Hãy xét vòng đời đối tượng, validation, khả năng tương thích thư viện và hợp đồng JSON trước khi lựa chọn.

## 14. Các nguyên tắc triển khai

- Dùng Java 16 trở lên để sử dụng record như tính năng ngôn ngữ chính thức; Java 17 là lựa chọn LTS phổ biến.
- Dùng Jackson Databind 2.12 trở lên nếu muốn native record mapping trong dòng Jackson 2.x.
- Căn chỉnh phiên bản `jackson-databind`, `jackson-core`, `jackson-annotations` và module liên quan bằng BOM.
- Đăng ký module riêng cho component đặc biệt như Java Time; record support không thay thế datatype module.
- Dùng `@JsonProperty` trên component khi tên JSON khác tên Java.
- Đặt validation bất biến trong compact canonical constructor; đặt kiểm tra phụ thuộc hệ thống ở tầng service.
- Quy định rõ cách xử lý component thiếu, null, sai kiểu và thuộc tính không biết.
- Thử nghiệm serialization và deserialization trên đúng JDK cùng phiên bản Jackson của môi trường triển khai.

## 15. Kết luận

Jackson Databind hỗ trợ native Java record từ phiên bản 2.12. Với Java 16 trở lên, Jackson có thể nhận diện record component, đọc JSON và gọi canonical constructor để tạo đối tượng; khi serialization, nó lấy giá trị từ các component để tạo JSON. `@JsonProperty` giúp đổi tên thuộc tính và các module riêng như `JavaTimeModule` vẫn cần thiết cho kiểu dữ liệu tương ứng. Khi làm việc với phiên bản cũ hơn, không nên giả định record mapping tự động hoạt động; hãy nâng Jackson hoặc dùng lớp Java thông thường với creator và property được annotation tường minh. Việc khóa phiên bản, kiểm tra cả hai chiều chuyển đổi và quy định rõ dữ liệu thiếu/null giúp chương trình ánh xạ record ổn định theo môi trường chạy.
