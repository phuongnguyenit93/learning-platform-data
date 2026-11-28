# Đọc ghi JSON bằng thư viện ngoài JDK và ánh xạ sang record

Trong Java 27, **record** là lựa chọn gọn và rõ nghĩa để biểu diễn một nhóm dữ liệu có cấu trúc, chẳng hạn khách hàng, sản phẩm, đơn hàng hoặc một yêu cầu HTTP. Khi trao đổi dữ liệu với dịch vụ web, tệp cấu hình hoặc ứng dụng khác, dữ liệu thường được biểu diễn bằng **JSON** (*JavaScript Object Notation*). Để chuyển đổi giữa JSON và record, ta thường dùng một thư viện JSON bên ngoài JDK.

Bài này hướng dẫn cách đọc, ghi và kiểm tra JSON bằng **Jackson 3.3.0**, một nhánh Jackson hiện hành phù hợp với Java 27, đồng thời giới thiệu **Gson 2.15.0** như một lựa chọn khác. Các phiên bản này đã được phát hành tại thời điểm biên soạn (27/11/2026). Ví dụ chính dùng API của Jackson 3, có tên package **tools.jackson.***; không trộn với ví dụ Jackson 2 cũ.

Mục tiêu của bài là giúp bạn:

- Hiểu mối quan hệ giữa JSON, record và quá trình *serialization/deserialization*.
- Thêm thư viện JSON vào dự án bằng Gradle hoặc Maven.
- Chuyển JSON thành record và chuyển record thành JSON.
- Ánh xạ record lồng nhau, danh sách, tên trường khác nhau và ngày tháng.
- Đọc/ghi JSON UTF-8 trong tệp một cách rõ ràng.
- Phân biệt cú pháp JSON hợp lệ với dữ liệu hợp lệ theo quy tắc nghiệp vụ.
- Xử lý trường thiếu, **null**, trường không mong đợi, lỗi ánh xạ và dữ liệu không đáng tin cậy.
- Chọn công cụ phù hợp khi định dạng JSON thay đổi hoặc tập dữ liệu rất lớn.

## 1. JSON và record giải quyết hai việc khác nhau

**JSON** là định dạng văn bản biểu diễn dữ liệu độc lập với ngôn ngữ lập trình. JSON có sáu dạng giá trị cơ bản:

| Giá trị JSON | Ví dụ | Kiểu Java có thể ánh xạ |
|---|---|---|
| Object | **{"id":"P01","price":120000}** | **record**, class, **Map** |
| Array | **["A","B"]** | **List**, mảng |
| String | **"Java 27"** | **String** |
| Number | **125**, **19.95** | **int**, **long**, **BigDecimal**, **double** |
| Boolean | **true**, **false** | **boolean**, **Boolean** |
| Null | **null** | Thường là tham chiếu **null**, hoặc được xử lý theo cấu hình |

JSON không có kiểu Java như **LocalDate**, **UUID**, **record**, **enum** hay **BigDecimal**. Thư viện JSON phải có quy tắc để ánh xạ các giá trị JSON sang các kiểu phù hợp.

**Record** là một kiểu tham chiếu trong Java, khai báo trực tiếp các thành phần dữ liệu (*record components*):

~~~java
public record Product(String sku, String name, int quantity) {}
~~~

Trình biên dịch cung cấp constructor chuẩn (*canonical constructor*), các accessor **sku()**, **name()**, **quantity()**, cùng các phương thức **equals()**, **hashCode()** và **toString()**. Các field thành phần là **final**; sau khi tạo record, không có setter để thay đổi giá trị của chúng.

Ví dụ JSON tương ứng:

~~~json
{
  "sku": "BK-01",
  "name": "Sách Java",
  "quantity": 2
}
~~~

Thư viện JSON đọc object này và gọi constructor chuẩn của **Product** với các giá trị đã ánh xạ. Khi ghi JSON, thư viện lấy các thành phần của record để tạo cặp tên–giá trị trong object JSON.

**Cần phân biệt:** record giữ các tham chiếu đến đối tượng bên trong; nó không tự động làm các đối tượng lồng nhau trở nên bất biến. Nếu component là một **List** có thể thay đổi hoặc một đối tượng mutable, bạn cần tự bảo vệ dữ liệu khi thiết kế record.

## 2. Chọn thư viện JSON hiện hành

JDK cung cấp API xử lý chuỗi và tệp, nhưng không cung cấp bộ ánh xạ JSON-to-record tổng quát tương đương **JsonMapper** hoặc **Gson**. Vì vậy, ứng dụng cần một phụ thuộc bên ngoài hoặc một framework đã tích hợp sẵn thư viện JSON.

Hai lựa chọn thông dụng:

| Thư viện | Tọa độ và phiên bản dùng trong bài | Đặc điểm |
|---|---|---|
| **Jackson 3** | **tools.jackson.core:jackson-databind:3.3.0** | Data binding mạnh, record, generic collections, tree model, streaming API, nhiều tùy chọn kiểm soát dữ liệu |
| **Gson** | **com.google.code.gson:gson:2.15.0** | API nhỏ gọn để chuyển đổi object/JSON; hỗ trợ record và generic types; có tùy chọn strict JSON |

Bài sử dụng **Jackson 3** làm thư viện chính vì phù hợp với ví dụ ánh xạ record có cấu trúc phức tạp. Gson có thể dùng cho các trường hợp đơn giản; phần cuối bài đưa ra ví dụ riêng để tránh nhầm API.

Jackson 3 yêu cầu JDK tối thiểu là 17, vì vậy đáp ứng yêu cầu dùng Java 27. Nhánh 3.x thay đổi **groupId**, package và một số cấu hình so với Jackson 2.x. Chúng không phải hai phiên bản có thể thay thế trực tiếp mà không sửa mã.

## 3. Thêm Jackson 3 vào dự án Java 27

### 3.1. Gradle Kotlin DSL

Trong **build.gradle.kts** của một ứng dụng Java:

~~~kotlin
plugins {
    java
    application
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(27)
    }
}

dependencies {
    implementation("tools.jackson.core:jackson-databind:3.3.0")
}

application {
    mainClass.set("demo.JsonRecordDemo")
}
~~~

Gradle tự lấy **jackson-core**, **jackson-annotations** và các phụ thuộc cần thiết khác theo metadata của thư viện. Dự án phải sử dụng phiên bản Gradle hỗ trợ Java 27 và có JDK 27 trong cấu hình toolchain.

Sau khi tạo lớp có **main** như phần tiếp theo, chạy:

~~~bash
./gradlew run
~~~

Trên Windows, sử dụng wrapper:

~~~powershell
.\gradlew.bat run
~~~

### 3.2. Maven

Trong phần **dependencies** của **pom.xml**:

~~~xml
<dependencies>
    <dependency>
        <groupId>tools.jackson.core</groupId>
        <artifactId>jackson-databind</artifactId>
        <version>3.3.0</version>
    </dependency>
</dependencies>
~~~

Cấu hình biên dịch bằng Java 27, ví dụ trong phần **properties**:

~~~xml
<properties>
    <maven.compiler.release>27</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
</properties>
~~~

Dùng phiên bản Maven Compiler Plugin hỗ trợ **release 27** và bảo đảm Maven đang chạy với JDK thích hợp. Với nhiều module Jackson, có thể sử dụng **tools.jackson:jackson-bom:3.3.0** ở phần **dependencyManagement** để giữ các phiên bản đồng bộ.

### 3.3. Import đúng với Jackson 3

Các API được sử dụng trong bài:

~~~java
import tools.jackson.databind.json.JsonMapper;
import tools.jackson.databind.DeserializationFeature;
import tools.jackson.databind.SerializationFeature;
import tools.jackson.core.type.TypeReference;
import tools.jackson.core.JacksonException;
~~~

Riêng các annotation thông dụng như **JsonProperty** vẫn đến từ package **com.fasterxml.jackson.annotation** trong Jackson 3:

~~~java
import com.fasterxml.jackson.annotation.JsonProperty;
~~~

Phân biệt này rất quan trọng. Nhiều hướng dẫn dành cho Jackson 2 dùng **com.fasterxml.jackson.databind.ObjectMapper**; đó là package của nhánh 2.x, không phải package của Jackson 3.

Jackson 3 cũng dùng cấu hình thông qua builder khi tạo mapper. Hãy tạo một mapper đã cấu hình đầy đủ rồi tái sử dụng, thay vì dựa vào các phương thức cấu hình có thể thay đổi trên một **ObjectMapper** của Jackson 2.

## 4. Ví dụ đầy đủ: chuyển JSON thành record và ngược lại

Tạo tệp **src/main/java/demo/JsonRecordDemo.java**:

~~~java
package demo;

import java.math.BigDecimal;
import java.util.Objects;

import tools.jackson.databind.DeserializationFeature;
import tools.jackson.databind.json.JsonMapper;

public class JsonRecordDemo {

    public record Product(
            String sku,
            String name,
            BigDecimal price,
            int quantity
    ) {
        public Product {
            Objects.requireNonNull(sku, "sku không được null");
            Objects.requireNonNull(name, "name không được null");
            Objects.requireNonNull(price, "price không được null");

            if (sku.isBlank() || name.isBlank()) {
                throw new IllegalArgumentException(
                    "sku và name không được rỗng"
                );
            }

            if (price.signum() < 0 || quantity < 0) {
                throw new IllegalArgumentException(
                    "Giá và số lượng phải không âm"
                );
            }
        }
    }

    public static void main(String[] args) {
        JsonMapper mapper = JsonMapper.builder()
            .enable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES)
            .enable(DeserializationFeature.FAIL_ON_MISSING_CREATOR_PROPERTIES)
            .enable(DeserializationFeature.FAIL_ON_NULL_CREATOR_PROPERTIES)
            .build();

        String input = """
            {
              "sku": "BK-01",
              "name": "Sách Java",
              "price": 149000.50,
              "quantity": 2
            }
            """;

        Product product = mapper.readValue(input, Product.class);

        System.out.println("Mã: " + product.sku());
        System.out.println("Giá: " + product.price());
        System.out.println("Số lượng: " + product.quantity());

        String output = mapper.writeValueAsString(product);
        System.out.println(output);
    }
}
~~~

Khi chạy chương trình, các dòng đầu là:

~~~text
Mã: BK-01
Giá: 149000.50
Số lượng: 2
~~~

Dòng cuối là JSON được tạo từ record, về nội dung tương đương:

~~~json
{"sku":"BK-01","name":"Sách Java","price":149000.50,"quantity":2}
~~~

Thứ tự các thuộc tính JSON không nên được dùng làm điều kiện kiểm tra nghiệp vụ: ý nghĩa của JSON object không phụ thuộc vào thứ tự của các cặp tên–giá trị.

### 4.1. Các bước ánh xạ khi đọc JSON

1. **readValue(input, Product.class)** phân tích chuỗi JSON.
2. Jackson đối chiếu các tên trường JSON với thành phần của record.
3. Thư viện chuyển giá trị JSON sang **String**, **BigDecimal**, **int** tương ứng.
4. Jackson gọi canonical constructor của **Product**.
5. Khối constructor kiểm tra tính hợp lệ và trả về một record sau khi khởi tạo thành công.

Trong record có **compact canonical constructor**, tham số constructor có cùng tên với component, nên bạn có thể kiểm tra các giá trị ngay trong khối **public Product { ... }**. Nếu dữ liệu không hợp lệ, constructor ném ngoại lệ và không tạo ra record hợp lệ.

### 4.2. Các bước ghi JSON

**writeValueAsString(product)** chuyển record sang chuỗi JSON. Các accessor như **sku()**, **price()** cung cấp dữ liệu. Không cần viết getter kiểu **getSku()** hoặc setter chỉ để Jackson hoạt động với một record thông thường.

Dùng **BigDecimal** cho số tiền cần độ chính xác thập phân. Tránh xây dựng số tiền từ **double** nếu quy tắc nghiệp vụ yêu cầu tính chính xác số thập phân. Trong ví dụ record, Jackson ánh xạ JSON number sang component **BigDecimal**.

### 4.3. Vì sao cấu hình strict?

Trong ví dụ, builder bật:

| Tính năng | Mục đích |
|---|---|
| **FAIL_ON_UNKNOWN_PROPERTIES** | Báo lỗi nếu JSON chứa trường không có trong record |
| **FAIL_ON_MISSING_CREATOR_PROPERTIES** | Báo lỗi khi JSON thiếu tham số cần thiết của canonical constructor |
| **FAIL_ON_NULL_CREATOR_PROPERTIES** | Báo lỗi khi một tham số constructor được gán **null** |

Trong Jackson 3, **FAIL_ON_UNKNOWN_PROPERTIES** bị tắt theo mặc định: trường thừa thường được bỏ qua. Còn **FAIL_ON_NULL_FOR_PRIMITIVES** được bật theo mặc định; chẳng hạn truyền JSON **null** vào component **int** sẽ gây lỗi ánh xạ.

Việc bật kiểm tra thiếu và null trong ví dụ khiến định dạng đầu vào chặt chẽ hơn. Với hệ thống cần chấp nhận field mới hoặc field tùy chọn, hãy điều chỉnh chính sách tương thích có chủ đích, thay vì mặc định bật mọi giới hạn.

## 5. Ánh xạ record lồng nhau

Trong thực tế, JSON thường chứa object bên trong object:

~~~json
{
  "orderId": "ORD-100",
  "customer": {
    "id": "C-01",
    "name": "Lan"
  },
  "shipping": {
    "street": "12 Đường A",
    "city": "Hà Nội"
  }
}
~~~

Có thể biểu diễn bằng các record:

~~~java
record Customer(String id, String name) {}

record Address(String street, String city) {}

record Order(
    String orderId,
    Customer customer,
    Address shipping
) {}
~~~

Đọc JSON:

~~~java
JsonMapper mapper = JsonMapper.builder().build();

Order order = mapper.readValue(json, Order.class);

System.out.println(order.orderId());
System.out.println(order.customer().name());
System.out.println(order.shipping().city());
~~~

Jackson lần lượt dựng **Customer**, **Address** rồi **Order** theo các cấu trúc con. Record hỗ trợ thiết kế một mô hình dữ liệu có các thành phần rõ ràng mà không cần các lớp chứa field mutable.

### 5.1. Bảo vệ cấu trúc con

Khi một component lồng nhau bắt buộc phải có, hãy kiểm tra trong constructor:

~~~java
record Order(
    String orderId,
    Customer customer,
    Address shipping
) {
    public Order {
        if (orderId == null || orderId.isBlank()) {
            throw new IllegalArgumentException("orderId không hợp lệ");
        }

        Objects.requireNonNull(customer, "customer không được null");
        Objects.requireNonNull(shipping, "shipping không được null");
    }
}
~~~

Lệnh **Objects.requireNonNull** kiểm tra tham chiếu, nhưng không bảo đảm một chuỗi là không rỗng, một ID có đúng định dạng, hay một danh sách có dữ liệu. Kiểm tra các yêu cầu đó riêng theo quy tắc nghiệp vụ.

Trong dự án thực, nếu mô hình đã dùng một framework kiểm tra dữ liệu như Jakarta Validation, có thể tích hợp validator ở tầng tiếp nhận dữ liệu. Annotation validation không tự động được thực thi chỉ vì một record được Jackson tạo; cần gọi cơ chế validation tương ứng.

## 6. Ánh xạ mảng JSON và List record

JSON array thường là một danh sách các object cùng cấu trúc:

~~~json
[
  {"sku":"BK-01","name":"Java","price":100000,"quantity":1},
  {"sku":"BK-02","name":"SQL","price":95000,"quantity":3}
]
~~~

Có hai cách đọc phổ biến.

### 6.1. Đọc thành mảng record

~~~java
Product[] products = mapper.readValue(json, Product[].class);

for (Product product : products) {
    System.out.println(product.name());
}
~~~

Với mảng, **Product[].class** mang đủ thông tin kiểu phần tử.

### 6.2. Đọc thành List record

Với generic **List<Product>**, do *type erasure*, không thể chỉ dùng **List.class** để yêu cầu Jackson tạo các **Product**. Hãy dùng **TypeReference**:

~~~java
import tools.jackson.core.type.TypeReference;

List<Product> products = mapper.readValue(
    json,
    new TypeReference<List<Product>>() {}
);

for (Product product : products) {
    System.out.println(product.sku());
}
~~~

TypeReference giữ thông tin kiểu **List<Product>** để mapper biết loại record cần tạo cho từng phần tử. Nếu dùng **List.class**, phần tử object JSON thường được biểu diễn bằng cấu trúc **Map** mặc định, không phải kiểu **Product** như mong đợi.

### 6.3. Danh sách nằm trong một record

Khi **List** là một component của record, Jackson đọc trực tiếp kiểu generic đã được khai báo:

~~~java
record OrderLine(String sku, int quantity) {}

record PurchaseOrder(String orderId, List<OrderLine> lines) {
    public PurchaseOrder {
        Objects.requireNonNull(orderId, "orderId");
        Objects.requireNonNull(lines, "lines");
        lines = List.copyOf(lines);
    }
}
~~~

JSON tương ứng:

~~~json
{
  "orderId": "ORD-200",
  "lines": [
    {"sku":"BK-01","quantity":2},
    {"sku":"BK-02","quantity":1}
  ]
}
~~~

Trong compact constructor, **List.copyOf(lines)** tạo một danh sách không thể sửa bằng các method thêm/xóa, đồng thời từ chối phần tử **null**. Việc gán lại tham số **lines** trong compact constructor khiến field component nhận bản sao này khi record hoàn tất khởi tạo.

Tuy nhiên, nếu phần tử của danh sách là đối tượng mutable, **List.copyOf** không tạo bản sao sâu của từng phần tử. Với **OrderLine** là record, các thành phần của nó là kiểu bất biến đơn giản nên ví dụ phù hợp.

## 7. Khi tên thuộc tính JSON khác tên component Java

Tên trường do bên ngoài cung cấp có thể theo quy ước **snake_case**, trong khi tên biến Java thường theo **camelCase**.

Ví dụ JSON:

~~~json
{"order_id":"ORD-01","customer_name":"Mai"}
~~~

Dùng annotation **@JsonProperty** tại component để mô tả tên JSON:

~~~java
import com.fasterxml.jackson.annotation.JsonProperty;

record OrderInfo(
    @JsonProperty("order_id") String orderId,
    @JsonProperty("customer_name") String customerName
) {}
~~~

Jackson đọc:

~~~java
OrderInfo order = mapper.readValue(json, OrderInfo.class);

System.out.println(order.orderId());       // ORD-01
System.out.println(order.customerName());  // Mai
~~~

Khi ghi lại bằng cùng mapper, các tên trường JSON sẽ là **order_id** và **customer_name**.

**Chú ý import:** Với Jackson 3.x, annotation **JsonProperty** vẫn thuộc **com.fasterxml.jackson.annotation**; phần thư viện xử lý dữ liệu dùng **tools.jackson.***. Đây là quy tắc package hiện hành, không phải một chỉ dẫn dùng lại Jackson 2.

Nếu cả API dùng cùng một quy tắc đặt tên, bạn có thể cấu hình naming strategy ở mapper thay cho việc đặt annotation trên từng component. Nhưng khi một record chỉ có vài tên đặc biệt, **@JsonProperty** thường dễ đọc hơn.

## 8. Dữ liệu thiếu, null, kiểu sai và kiểm tra giá trị

Đọc JSON thành record không đồng nghĩa với việc dữ liệu đầu vào tự động hợp lệ. Cần phân biệt bốn tình huống:

| Tình huống | Ví dụ | Hành động hợp lý |
|---|---|---|
| Thiếu trường | **{"name":"Lan"}**, thiếu **id** | Quyết định trường có bắt buộc; bật kiểm tra missing creator hoặc kiểm tra constructor |
| Trường có giá trị null | **{"id":null}** | Từ chối nếu bắt buộc, hoặc biểu diễn rõ giá trị tùy chọn |
| Sai kiểu | **{"quantity":"abc"}** | Báo lỗi ánh xạ; không cố chuyển chuỗi tùy tiện |
| Đúng kiểu nhưng sai nghiệp vụ | **{"quantity":-5}** | Kiểm tra trong constructor hoặc tầng validation |

### 8.1. Kiểm tra trong compact constructor

~~~java
public record UserRegistration(
        String email,
        int age
) {
    public UserRegistration {
        if (email == null || email.isBlank() || !email.contains("@")) {
            throw new IllegalArgumentException("Email không hợp lệ");
        }

        if (age < 0 || age > 130) {
            throw new IllegalArgumentException("Tuổi không hợp lệ");
        }
    }
}
~~~

Đây chỉ là ví dụ kiểm tra đơn giản, không phải bộ xác thực email đầy đủ. Trong hệ thống thực, quy tắc xác thực phải phù hợp yêu cầu nghiệp vụ và nguồn dữ liệu.

### 8.2. Khi field tùy chọn được phép thiếu

Nếu API chủ ý cho phép **note** vắng mặt hoặc **null**, không nên dùng cấu hình toàn cục **FAIL_ON_MISSING_CREATOR_PROPERTIES** và **FAIL_ON_NULL_CREATOR_PROPERTIES** cho tất cả kiểu record rồi mong một component tùy chọn tự hoạt động.

Một lựa chọn là tách DTO nhận dữ liệu khỏi mô hình nghiệp vụ và cấu hình chính sách riêng cho DTO; hoặc dùng cách ánh xạ cho phép trường tùy chọn, sau đó chuẩn hóa trong constructor:

~~~java
record Message(String id, String note) {
    public Message {
        if (id == null || id.isBlank()) {
            throw new IllegalArgumentException("Thiếu id");
        }

        note = note == null ? "" : note;
    }
}
~~~

Ví dụ trên có thể dùng với mapper không bật kiểm tra missing/null cho mọi creator property. Nó biểu diễn **note** tùy chọn bằng chuỗi rỗng sau khi chuẩn hóa. Nếu cần phân biệt thực sự giữa “không gửi”, “gửi null” và “gửi chuỗi rỗng”, phải chọn mô hình DTO hoặc cơ chế ánh xạ có thể giữ được ba trạng thái đó.

**@JsonProperty(required = true)** và các cấu hình ánh xạ không thay thế việc kiểm tra giá trị thực tế. Ví dụ, một chuỗi có mặt trong JSON nhưng chỉ gồm khoảng trắng vẫn cần được kiểm tra nếu nghiệp vụ cấm.

### 8.3. Chính sách với trường JSON không biết trước

Jackson 3 mặc định bỏ qua trường không có trong kiểu đích. Ví dụ record **User(String name)** có thể đọc object chứa thêm trường **role** mà không dùng role đó.

Khi đầu vào phải tuân thủ hợp đồng chặt chẽ, bật:

~~~java
JsonMapper mapper = JsonMapper.builder()
    .enable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES)
    .build();
~~~

Khi cần tương thích tiến hóa, chấp nhận trường thừa có thể là một chủ đích hợp lý. Hãy ghi rõ hợp đồng API và có kiểm tra riêng cho những trường bắt buộc.

## 9. Đọc và ghi JSON từ tệp bằng UTF-8

Với tệp JSON nhỏ hoặc vừa, có thể kết hợp Java NIO với Jackson. Dùng **Files.readString** và **Files.writeString** để kiểm soát rõ bộ mã ký tự UTF-8.

Ví dụ đọc một record từ tệp:

~~~java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

static Product loadProduct(Path path, JsonMapper mapper) throws java.io.IOException {
    String json = Files.readString(path, StandardCharsets.UTF_8);
    return mapper.readValue(json, Product.class);
}
~~~

Ví dụ ghi record vào tệp:

~~~java
static void saveProduct(
        Path path,
        Product product,
        JsonMapper mapper
) throws java.io.IOException {
    String json = mapper.writeValueAsString(product);
    Files.writeString(path, json, StandardCharsets.UTF_8);
}
~~~

Sử dụng:

~~~java
Path inputPath = Path.of("data", "product.json");
Product product = loadProduct(inputPath, mapper);

Path outputPath = Path.of("data", "product-output.json");
saveProduct(outputPath, product, mapper);
~~~

**Files.readString** đọc toàn bộ tệp vào bộ nhớ. **Files.writeString** với các tùy chọn mặc định tạo tệp nếu chưa có và ghi đè nội dung nếu tệp đã tồn tại. Thư mục cha phải có sẵn; thao tác ghi có thể thất bại do thiếu quyền hoặc lỗi đĩa.

Nếu chương trình cần tránh mất dữ liệu khi ghi tệp cấu hình quan trọng, hãy cân nhắc ghi sang tệp tạm và thay thế tệp đích một cách có kiểm soát. Khi tệp có dung lượng lớn, không nên đọc tất cả vào một **String**; sử dụng API streaming của Jackson và giới hạn tài nguyên.

Jackson cũng cung cấp **readValue** và **writeValue** với tệp, nhưng ví dụ trên dùng Java NIO để thấy rõ hai bước: đọc/ghi **văn bản UTF-8** và chuyển đổi **JSON ↔ record**.

## 10. Ghi JSON dễ đọc và ngày tháng

### 10.1. Pretty-print JSON

Để JSON trong tệp dễ đọc hơn, tạo mapper với tùy chọn thụt lề:

~~~java
JsonMapper prettyMapper = JsonMapper.builder()
    .enable(SerializationFeature.INDENT_OUTPUT)
    .build();

String json = prettyMapper.writeValueAsString(product);
System.out.println(json);
~~~

Pretty printing chỉ thay đổi khoảng trắng và cách xuống dòng. Dữ liệu JSON không đổi về mặt ngữ nghĩa. Khi trao đổi qua mạng, định dạng gọn thường giảm dung lượng; khi lưu tệp phục vụ con người đọc, pretty printing có thể hữu ích.

### 10.2. java.time trong Jackson 3

Jackson 3 đã tích hợp khả năng xử lý các kiểu **java.time**, chẳng hạn **LocalDate** và **LocalDateTime**, vào databind. Với Jackson 3, không cần thêm mô-đun **jackson-datatype-jsr310** và đăng ký **JavaTimeModule** chỉ để dùng các kiểu này như trong nhiều hướng dẫn Jackson 2 cũ.

Ví dụ:

~~~java
import java.time.LocalDate;
import com.fasterxml.jackson.annotation.JsonFormat;

record Meeting(
    String topic,
    @JsonFormat(shape = JsonFormat.Shape.STRING, pattern = "yyyy-MM-dd")
    LocalDate date
) {}
~~~

JSON mong muốn:

~~~json
{"topic":"Học Java","date":"2026-11-27"}
~~~

**@JsonFormat** cho biết định dạng ngày theo hợp đồng JSON. Với dữ liệu ngày giờ có múi giờ, cần chọn kiểu **Instant**, **OffsetDateTime** hoặc **ZonedDateTime** phù hợp và thống nhất cách truyền múi giờ; không coi một chuỗi ngày tháng không có timezone là một thời điểm tuyệt đối.

## 11. Xử lý lỗi JSON và lỗi ánh xạ

Có ít nhất ba nhóm lỗi:

1. **Lỗi cú pháp JSON**: thiếu dấu nháy, dấu ngoặc, dấu phẩy hoặc định dạng số sai.
2. **Lỗi ánh xạ kiểu**: giá trị JSON không thể chuyển sang kiểu record yêu cầu, thiếu hoặc có trường không hợp lệ theo cấu hình.
3. **Lỗi nghiệp vụ**: dữ liệu có kiểu đúng nhưng không đáp ứng điều kiện trong constructor hoặc validator.

Trong Jackson 3, lỗi xử lý JSON dựa trên **tools.jackson.core.JacksonException**, một ngoại lệ **unchecked** (kế thừa **RuntimeException**). Khác với Jackson 2, không cần khai báo **throws IOException** chỉ vì gọi **readValue(String, ...)**.

Ví dụ xử lý ở ranh giới tiếp nhận:

~~~java
import tools.jackson.core.JacksonException;

static Product parseProduct(String json, JsonMapper mapper) {
    try {
        return mapper.readValue(json, Product.class);
    } catch (JacksonException exception) {
        throw new IllegalArgumentException(
            "JSON không đúng hợp đồng Product", exception
        );
    }
}
~~~

**Lưu ý:** Khi compact constructor của record ném **IllegalArgumentException**, Jackson có thể gói lỗi thành lỗi ánh xạ để cung cấp thông tin đường dẫn trường. Tùy kiểu lỗi, ứng dụng cũng cần xử lý lỗi validation từ tầng nghiệp vụ. Không nên bắt mọi **RuntimeException** rồi mặc định coi tất cả là “JSON sai”, vì có thể che giấu lỗi lập trình không liên quan.

Ở ranh giới HTTP, hệ thống thường biến lỗi dữ liệu đầu vào thành phản hồi 4xx có thông tin phù hợp, đồng thời ghi log chi tiết phía máy chủ. Không trả nguyên stack trace hoặc dữ liệu nhạy cảm cho bên gọi API.

### 11.1. Kiểm tra một lần trước khi dùng dữ liệu

Một cách tổ chức hợp lý:

~~~text
Chuỗi JSON từ client
         |
         v
Kiểm tra giới hạn kích thước và nguồn dữ liệu
         |
         v
Jackson parse và ánh xạ sang DTO record
         |
         v
Kiểm tra cấu trúc và giá trị nghiệp vụ
         |
         v
Chuyển sang mô hình domain / gọi dịch vụ
         |
         v
Trả kết quả hoặc phản hồi lỗi phù hợp
~~~

Nhờ tách các bước, việc chuyển đổi JSON không bị trộn với truy vấn cơ sở dữ liệu hoặc xử lý nghiệp vụ phức tạp.

## 12. Khi cấu trúc JSON không cố định: JsonNode

Nếu không biết trước chính xác cấu trúc JSON, hoặc chỉ cần đọc một vài trường, bạn có thể sử dụng **tree model** với **JsonNode**:

~~~java
import tools.jackson.databind.JsonNode;

JsonNode root = mapper.readTree("""
    {"event":"created","payload":{"id":"A-01"}}
    """);

String event = root.path("event").asText();
String id = root.path("payload").path("id").asText();

System.out.println(event + ": " + id);
~~~

**JsonNode** cho phép xem cấu trúc JSON dạng cây mà chưa bắt buộc khai báo record. Tuy nhiên, nếu dữ liệu có hợp đồng rõ ràng, record giúp kiểm tra kiểu tốt hơn tại thời điểm biên dịch và làm code dễ bảo trì.

Có thể kết hợp hai mô hình: đọc JSON vào **JsonNode**, kiểm tra một trường phân biệt **type**, rồi chuyển một phần cấu trúc sang record phù hợp. Không nên ánh xạ tùy tiện dữ liệu không tin cậy sang những lớp do client gửi tên lớp trong JSON.

## 13. Lựa chọn khác: Gson 2.15.0

Gson có API trực tiếp để chuyển object Java thành JSON và ngược lại. Phiên bản **2.15.0** đã phát hành trong năm 2026 và hỗ trợ record; Gson hỗ trợ record từ dòng 2.10 trở lên.

Thêm vào Gradle:

~~~kotlin
dependencies {
    implementation("com.google.code.gson:gson:2.15.0")
}
~~~

Hoặc Maven:

~~~xml
<dependency>
    <groupId>com.google.code.gson</groupId>
    <artifactId>gson</artifactId>
    <version>2.15.0</version>
</dependency>
~~~

Ví dụ với record:

~~~java
import com.google.gson.Gson;
import com.google.gson.GsonBuilder;
import com.google.gson.Strictness;

public class GsonRecordDemo {

    record Book(String isbn, String title, int pages) {}

    public static void main(String[] args) {
        Gson gson = new GsonBuilder()
            .setStrictness(Strictness.STRICT)
            .create();

        String json = """
            {"isbn":"978-01","title":"Java","pages":320}
            """;

        Book book = gson.fromJson(json, Book.class);

        System.out.println(book.title());
        System.out.println(gson.toJson(book));
    }
}
~~~

**setStrictness(Strictness.STRICT)** yêu cầu tuân thủ cú pháp JSON nghiêm ngặt. Tài liệu chính thức của Gson lưu ý rằng chế độ đọc mặc định có thể chấp nhận một số cú pháp không chuẩn vì lý do tương thích, nên với đầu vào ngoài hệ thống bạn cần chọn strictness có chủ đích.

Với generic list, Gson dùng **TypeToken**, không phải Jackson **TypeReference**:

~~~java
import com.google.gson.reflect.TypeToken;
import java.lang.reflect.Type;

Type type = new TypeToken<List<GsonRecordDemo.Book>>() {}.getType();
List<GsonRecordDemo.Book> books = gson.fromJson(jsonArray, type);
~~~

Gson phù hợp khi ứng dụng chỉ cần chuyển đổi cơ bản và không yêu cầu nhiều tính năng nâng cao của Jackson. Tuy vậy, cả hai thư viện đều cần kiểm tra ràng buộc dữ liệu nghiệp vụ. **Gson** được nhóm phát triển mô tả là đang trong chế độ bảo trì, vẫn sửa lỗi hiện hữu; nếu muốn các khả năng mới của data binding, cần đánh giá nhu cầu cụ thể trước khi chọn.

## 14. Những khác biệt quan trọng giữa Jackson 3 và hướng dẫn cũ

Một số tài liệu trên mạng được viết cho Jackson 2.x vẫn hữu ích về khái niệm nhưng code cấu hình/import không áp dụng nguyên xi cho Jackson 3:

| Chủ đề | Jackson 3.x hiện hành | Điều cần tránh khi sao chép hướng dẫn cũ |
|---|---|---|
| Maven artifact | **tools.jackson.core:jackson-databind** | Nhầm với groupId **com.fasterxml.jackson.core** của nhánh 2 |
| Package databind | **tools.jackson.databind** | Import nhầm **com.fasterxml.jackson.databind** |
| Annotation cơ bản | Vẫn là **com.fasterxml.jackson.annotation** | Đổi toàn bộ annotation sang **tools.jackson.annotation** không tồn tại |
| Cấu hình mapper | **JsonMapper.builder()...build()** | Dựa vào cấu hình mutable sau khi mapper đã tạo |
| Unknown properties | Mặc định **bỏ qua** ở Jackson 3 | Giả định mặc định luôn từ chối trường thừa |
| Null với primitive | Mặc định **FAIL_ON_NULL_FOR_PRIMITIVES** bật | Giả định JSON null được tự đổi thành số 0 |
| Ngoại lệ xử lý JSON | **JacksonException** là unchecked | Bắt **JsonProcessingException** kiểu IOException của Jackson 2 |
| Java time / Optional | Hỗ trợ được tích hợp trong Jackson 3 databind | Thêm module Java 8 bên ngoài theo hướng dẫn Jackson 2 chỉ để ánh xạ các kiểu cơ bản |

Nếu dự án đang dùng framework cấu hình sẵn Jackson 2.x, không tự ý thêm Jackson 3 và kỳ vọng framework lập tức sử dụng mapper mới. Cần xem framework hỗ trợ phiên bản nào và giữ cấu hình dependency nhất quán. Với dự án Java 27 mới, Jackson 3 là một lựa chọn cập nhật hợp lý.

## 15. Các lỗi thường gặp và cách khắc phục

| Lỗi | Nguyên nhân | Cách giải quyết |
|---|---|---|
| **ClassNotFoundException** hoặc lỗi import databind | Chưa có dependency hoặc dùng sai package Jackson 3 | Kiểm tra **tools.jackson.core** và **tools.jackson.databind** |
| JSON đọc ra **null** hoặc thiếu thuộc tính | Tên JSON không khớp component record | Soát tên trường, dùng **@JsonProperty** khi cần |
| Trường **int** nhận giá trị không hợp lệ | JSON null hoặc không thể chuyển sang số | Bật kiểm tra null/missing, dùng kiểu phù hợp, kiểm tra đầu vào |
| Record nhận chuỗi trống dù nghiệp vụ cấm | Jackson chỉ ánh xạ kiểu, không mặc định kiểm tra nội dung | Kiểm tra trong constructor/validator |
| Đọc **List.class** rồi cast phần tử sang record | Java mất thông tin generic | Dùng **TypeReference<List<Product>>** |
| JSON có trường thừa nhưng không báo lỗi | Jackson 3 mặc định bỏ qua unknown properties | Bật **FAIL_ON_UNKNOWN_PROPERTIES** nếu hợp đồng yêu cầu |
| Ghi ra số tiền sai kỳ vọng | Dùng **double** cho số thập phân cần độ chính xác cao | Dùng **BigDecimal** và thống nhất quy ước số tiền |
| File JSON tiếng Việt bị lỗi ký tự | Đọc/ghi sai charset | Dùng UTF-8 nhất quán |
| Cập nhật **List** component khiến dữ liệu record thay đổi | Record không bảo đảm bất biến sâu | Dùng **List.copyOf** và chọn phần tử bất biến |
| Ngày/giờ lệch múi giờ | Không thống nhất định dạng và timezone | Dùng kiểu **java.time** và giao kèo rõ ràng |
| Gặp dữ liệu JSON lớn làm đầy bộ nhớ | Đọc toàn bộ file bằng **readString** hoặc **readTree** | Đặt giới hạn kích thước, cân nhắc streaming |
| Nhầm **JsonProperty** của Jackson 3 | Import tất cả annotation từ package mới | Với annotation cơ bản dùng **com.fasterxml.jackson.annotation** |
| Đưa tên class tùy ý từ JSON vào cơ chế polymorphic mapping | Tin dữ liệu điều khiển kiểu đối tượng cần tạo | Dùng subtype được cho phép rõ ràng và giới hạn dữ liệu ngoài |

## 16. An toàn và hiệu năng khi xử lý JSON bên ngoài

JSON đến từ mạng hoặc tệp do bên ngoài cung cấp phải được coi là dữ liệu chưa đáng tin cậy.

**Giới hạn đầu vào.** Tránh tải tệp không giới hạn kích thước hoặc JSON lồng sâu quá mức vào bộ nhớ. Jackson Core có cơ chế giới hạn độ sâu và độ dài dữ liệu (*stream read constraints*); ứng dụng nên đặt giới hạn phù hợp với kích thước JSON thực tế và giới hạn request ở tầng HTTP.

**Không cho phép JSON chọn kiểu Java bất kỳ.** Khi cần xử lý nhiều loại message, mô hình hóa bằng một tập DTO/record và loại discriminator được phép. Tránh bật tính năng ánh xạ đa hình rộng cho dữ liệu không đáng tin cậy chỉ để tiết kiệm code.

**Không mặc định tin record vừa parse.** Record không tự kiểm tra email, giá tiền, mã định danh hay quyền truy cập. Xác thực và phân quyền vẫn thuộc trách nhiệm của tầng nghiệp vụ.

**Không lạm dụng tree model.** **JsonNode** linh hoạt nhưng không có hợp đồng kiểu tĩnh mạnh như record. Với API ổn định, DTO record giúp giảm lỗi cast và giúp người đọc biết rõ dữ liệu mong đợi.

**Dùng streaming khi khối lượng lớn.** Với dữ liệu có hàng triệu phần tử, không nhất thiết phải nạp toàn bộ thành **List<Product>**. Jackson hỗ trợ streaming parser/generator để xử lý dần; cách này phức tạp hơn và chỉ nên áp dụng khi nhu cầu về bộ nhớ, tốc độ hoặc kích thước dữ liệu thực sự cần thiết.

## 17. Tự kiểm tra kiến thức

Hãy tự trả lời các câu hỏi sau để chắc chắn đã hiểu nội dung:

1. Vì sao một record chỉ có component **String name** vẫn có thể nhận JSON **{"name":null}** nếu không cấu hình từ chối null và không kiểm tra constructor?
2. Khi JSON có mảng object, vì sao **new TypeReference<List<Product>>() {}** tốt hơn **List.class**?
3. Làm thế nào để ánh xạ **customer_id** trong JSON thành component **customerId**?
4. Khi nào nên bật **FAIL_ON_UNKNOWN_PROPERTIES**, và khi nào cần chấp nhận trường thừa?
5. Vì sao **BigDecimal** phù hợp hơn **double** cho các phép tính tiền cần chính xác thập phân?
6. Khi file JSON rất lớn, vì sao **Files.readString** hoặc **mapper.readTree** có thể không phù hợp?
7. Khác biệt giữa lỗi cú pháp JSON, lỗi ánh xạ và lỗi quy tắc nghiệp vụ là gì?
8. Vì sao import **JsonProperty** vẫn nằm trong **com.fasterxml.jackson.annotation** dù databind sử dụng **tools.jackson.databind**?

## 18. Ghi nhớ

- JSON là định dạng văn bản, còn record là cấu trúc dữ liệu Java; thư viện ngoài JDK thực hiện việc chuyển đổi qua lại.
- Jackson 3.3.0 là lựa chọn hiện hành cho Java 27 với **tools.jackson.databind.json.JsonMapper**.
- **readValue** dùng để chuyển JSON sang record; **writeValueAsString** chuyển record sang JSON.
- Record được khởi tạo qua canonical constructor; hãy dùng compact constructor để kiểm tra dữ liệu bắt buộc và quy tắc nghiệp vụ.
- JSON object lồng nhau có thể ánh xạ sang record lồng nhau; JSON array ánh xạ sang mảng hoặc **List<T>**.
- Dùng **TypeReference** khi đọc generic root collections để giữ kiểu phần tử.
- Dùng **@JsonProperty** khi tên JSON khác tên component Java.
- Trong Jackson 3, unknown properties mặc định được bỏ qua; có thể bật kiểm tra strict khi cần.
- Dùng UTF-8 cho JSON đọc/ghi bằng Java NIO và **BigDecimal** khi cần độ chính xác thập phân.
- Jackson 3 tích hợp hỗ trợ kiểu **java.time**; không cần áp dụng hướng dẫn đăng ký module Java 8 cũ.
- Với Gson 2.15.0, dùng **Gson**, **TypeToken** và tùy chọn **Strictness.STRICT** khi cần đọc JSON nghiêm ngặt.
- Luôn giới hạn dữ liệu đầu vào, kiểm tra business rules và chọn streaming khi quy mô dữ liệu yêu cầu.

## Tài liệu tham khảo

- [Jackson 3.3 release notes — FasterXML](https://github.com/FasterXML/jackson/wiki/Jackson-Release-3.3)
- [Jackson Databind 3.x — README và ví dụ API](https://github.com/FasterXML/jackson-databind/blob/3.x/README.md)
- [Jackson 3 migration guide — các thay đổi về package, cấu hình và ngoại lệ](https://github.com/FasterXML/jackson/blob/main/jackson3/MIGRATING_TO_JACKSON_3.md)
- [Jackson Databind 3.3.0 trên Maven Central](https://central.sonatype.com/artifact/tools.jackson.core/jackson-databind/3.3.0)
- [Jackson 3.3.0 API — JsonMapper](https://javadoc.io/doc/tools.jackson.core/jackson-databind/3.3.0/tools.jackson.databind/tools/jackson/databind/json/JsonMapper.html)
- [Jackson 3 API — DeserializationFeature](https://javadoc.io/static/tools.jackson.core/jackson-databind/3.2.2/tools.jackson.databind/tools/jackson/databind/DeserializationFeature.html)
- [Gson — trang dự án và dependency hiện hành](https://google.github.io/gson/)
- [Gson — Troubleshooting và JSON Strictness](https://google.github.io/gson/Troubleshooting.html)
- [Gson — Change Log (hỗ trợ record từ 2.10)](https://google.github.io/gson/CHANGELOG.html)
- [Gson 2.15.0 trên Maven Central](https://central.sonatype.com/artifact/com.google.code.gson/gson/2.15.0)
- [RFC 8259 — The JavaScript Object Notation (JSON) Data Interchange Format](https://www.rfc-editor.org/rfc/rfc8259)
