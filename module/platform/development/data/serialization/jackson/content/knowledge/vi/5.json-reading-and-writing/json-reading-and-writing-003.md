# Đọc ghi POJO đơn giản với thuộc tính cơ bản

Jackson chuyển đổi dữ liệu giữa object Java và JSON. Với một POJO đơn giản, ứng dụng có thể ghi object thành JSON hoặc đọc JSON thành object Java bằng các method của ObjectMapper. Đây là thao tác nền tảng trước khi làm việc với collection, object lồng nhau, generic type và custom serializer.

POJO (Plain Old Java Object) là một class Java thông thường dùng để biểu diễn dữ liệu. Class thường có field, constructor, getter và setter. Jackson dựa vào cấu trúc class, quy tắc nhận diện property và cấu hình mapper để quyết định dữ liệu nào được ghi ra JSON hoặc gán vào object khi đọc JSON.

## 1. Luồng chuyển đổi

Hai thao tác chính có hướng chuyển đổi ngược nhau:

- **Serialization**: chuyển object Java thành JSON.
- **Deserialization**: đọc JSON và tạo object Java.

~~~mermaid
flowchart LR
    A[POJO trong Java] -->|writeValueAsString / writeValue| B[JSON]
    B -->|readValue| C[POJO mới]
~~~

Ví dụ, object Java có id, name và age có thể được ghi thành:

~~~json
{
  "id": "CUS-001",
  "name": "An",
  "age": 25
}
~~~

Khi đọc JSON, Jackson cần biết kiểu Java đích. JSON không tự chứa thông tin rằng nó phải trở thành class Customer. Ứng dụng cung cấp kiểu đích trong lời gọi readValue.

API trung tâm của Jackson Databind là **ObjectMapper**:

~~~java
ObjectMapper mapper = new ObjectMapper();

String json = mapper.writeValueAsString(customer);
Customer restored = mapper.readValue(json, Customer.class);
~~~

## 2. Chuẩn bị một POJO đơn giản

### 2.1. Field và property

Field là biến thành viên lưu trạng thái của object. Property là thuộc tính mà Jackson nhận diện thông qua field, getter, setter, constructor hoặc annotation theo quy tắc introspection và visibility.

Một JavaBean đơn giản thường có field, constructor không tham số, getter và setter:

~~~java
public class Customer {

    private String id;
    private String name;
    private int age;
    private boolean active;

    public Customer() {
    }

    public Customer(String id, String name, int age, boolean active) {
        this.id = id;
        this.name = name;
        this.age = age;
        this.active = active;
    }

    public String getId() {
        return id;
    }

    public void setId(String id) {
        this.id = id;
    }

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }

    public int getAge() {
        return age;
    }

    public void setAge(int age) {
        this.age = age;
    }

    public boolean isActive() {
        return active;
    }

    public void setActive(boolean active) {
        this.active = active;
    }
}
~~~

Tên getter và setter tuân theo quy ước JavaBean:

| Property | Getter | Setter |
|---|---|---|
| id | getId() | setId(String id) |
| name | getName() | setName(String name) |
| age | getAge() | setAge(int age) |
| active | isActive() | setActive(boolean active) |

Với boolean primitive, getter thường dùng tiền tố is. Với kiểu khác, getter thường dùng get. Setter thường dùng set và nhận một tham số.

Các field trong ví dụ là private. Jackson vẫn có thể nhận diện property thông qua public getter và setter. Không cần chuyển tất cả field thành public chỉ để serialize hoặc deserialize.

### 2.2. Constructor không tham số

Với JavaBean thông thường, quá trình deserialization có thể hình dung như sau:

1. Jackson tạo object bằng constructor không tham số.
2. Jackson phân tích các khóa và giá trị trong JSON.
3. Jackson tìm property Java tương ứng.
4. Jackson chuyển giá trị JSON sang kiểu Java phù hợp.
5. Jackson gọi setter hoặc gán field theo cấu hình.

Vì vậy, constructor không tham số và setter là cách phổ biến để Jackson tạo POJO. Nếu class chỉ có constructor nhận tham số, không có setter và không có creator phù hợp, Jackson có thể không biết cách tạo object.

Không phải mọi kiểu Java đều bắt buộc có constructor không tham số. Jackson còn hỗ trợ constructor/factory method được chỉ định, immutable class và record. Tuy nhiên, JavaBean với constructor không tham số là cách dễ học nhất khi bắt đầu.

### 2.3. Field không tự động luôn trở thành JSON property

Jackson nhận diện property theo cấu hình visibility và metadata. Trong cách dùng thông thường:

- Public getter có thể làm property xuất hiện trong JSON khi serialization.
- Public setter có thể được dùng để gán property khi deserialization.
- Field có thể được nhận diện trực tiếp tùy visibility và cấu hình.
- Annotation có thể đổi tên, bỏ qua hoặc điều chỉnh cách xử lý property.

Một field private không có getter có thể không được ghi ra JSON theo cấu hình mặc định thông thường. Nếu cần dùng field đó làm property, có thể bổ sung getter hoặc cấu hình/annotation phù hợp.

## 3. Serialization: ghi POJO thành JSON

### 3.1. Ghi thành JSON string

Khi dữ liệu đang ở trong bộ nhớ và cần JSON string, dùng **writeValueAsString**:

~~~java
ObjectMapper mapper = new ObjectMapper();

Customer customer = new Customer(
        "CUS-001",
        "An",
        25,
        true
);

String json = mapper.writeValueAsString(customer);
System.out.println(json);
~~~

Kết quả có dạng:

~~~json
{"id":"CUS-001","name":"An","age":25,"active":true}
~~~

Thứ tự property trong output không nên được xem là hợp đồng mặc định nếu ứng dụng chưa quy định rõ. JSON object được xử lý theo tên khóa. Nếu cần thứ tự ổn định cho một yêu cầu cụ thể, có thể dùng annotation hoặc cấu hình sắp xếp property.

Khi gọi writeValueAsString, Jackson xác định kiểu runtime, tìm property có thể serialize, đọc giá trị từ getter hoặc field được nhận diện, chuyển từng giá trị sang JSON rồi tạo chuỗi kết quả.

### 3.2. Ghi JSON có thụt lề

JSON compact phù hợp để truyền tải. Khi debug hoặc lưu file để con người đọc, có thể tạo output dễ nhìn:

~~~java
String prettyJson = mapper
        .writerWithDefaultPrettyPrinter()
        .writeValueAsString(customer);

System.out.println(prettyJson);
~~~

Ví dụ kết quả:

~~~json
{
  "id" : "CUS-001",
  "name" : "An",
  "age" : 25,
  "active" : true
}
~~~

Pretty printer chỉ thay đổi cách trình bày JSON, không làm thay đổi ý nghĩa dữ liệu.

### 3.3. Ghi object ra file

Nếu cần lưu JSON vào file, dùng overload writeValue nhận File hoặc OutputStream:

~~~java
Path path = Path.of("data", "customer.json");

try {
    Files.createDirectories(path.getParent());
    mapper.writeValue(path.toFile(), customer);
} catch (IOException e) {
    throw new UncheckedIOException("Cannot write customer JSON", e);
}
~~~

Jackson tạo JSON và ghi dữ liệu vào file. Khi ghi file, cần xử lý lỗi I/O như đường dẫn không hợp lệ, thiếu quyền hoặc thiết bị lưu trữ gặp sự cố.

Nếu tự mở OutputStream, hãy dùng try-with-resources để đóng tài nguyên:

~~~java
try (OutputStream output = Files.newOutputStream(path)) {
    mapper.writeValue(output, customer);
}
~~~

### 3.4. Giá trị null khi serialization

Theo chính sách mặc định thường gặp của Jackson Databind, property có giá trị null vẫn có thể được ghi ra JSON:

~~~json
{
  "name": "An",
  "email": null
}
~~~

Nếu muốn bỏ qua property null, có thể đặt annotation:

~~~java
@JsonInclude(JsonInclude.Include.NON_NULL)
public class Customer {
    private String name;
    private String email;

    // Constructor, getter và setter.
}
~~~

Annotation này yêu cầu Jackson chỉ đưa property có giá trị khác null vào JSON theo điều kiện đã chọn. Cũng có thể đặt chính sách inclusion ở cấp mapper. Annotation có phạm vi model/property, còn cấu hình mapper có thể ảnh hưởng nhiều model.

## 4. Deserialization: đọc JSON thành POJO

### 4.1. Đọc từ JSON string

Dùng **readValue** và truyền kiểu Java đích:

~~~java
String json = """
        {
          "id": "CUS-001",
          "name": "An",
          "age": 25,
          "active": true
        }
        """;

ObjectMapper mapper = new ObjectMapper();

Customer customer = mapper.readValue(json, Customer.class);

System.out.println(customer.getId());
System.out.println(customer.getName());
System.out.println(customer.getAge());
System.out.println(customer.isActive());
~~~

Với JavaBean ở phần trước, Jackson tạo Customer bằng constructor không tham số, tìm property tương ứng với khóa JSON, chuyển đổi giá trị và gọi setter hoặc gán field theo cấu hình. Cuối cùng, readValue trả về object đã được tạo.

### 4.2. Đọc từ file hoặc stream

Có thể truyền File trực tiếp:

~~~java
Path path = Path.of("data", "customer.json");

try {
    Customer customer = mapper.readValue(path.toFile(), Customer.class);
    System.out.println(customer.getName());
} catch (IOException e) {
    throw new UncheckedIOException("Cannot read customer JSON", e);
}
~~~

Hoặc mở InputStream:

~~~java
try (InputStream input = Files.newInputStream(path)) {
    Customer customer = mapper.readValue(input, Customer.class);
}
~~~

Với dữ liệu lớn hoặc dữ liệu đến từ mạng, truyền stream trực tiếp có thể tránh phải giữ toàn bộ JSON string trong bộ nhớ. Stream là nguồn byte; Jackson chịu trách nhiệm phân tích JSON và ánh xạ vào object.

### 4.3. Đổi tên property bằng annotation

Jackson ánh xạ tên property JSON với property Java mà nó nhận diện. Nếu tên không trùng, có thể chỉ định tên JSON bằng **@JsonProperty**:

~~~java
public class Customer {

    @JsonProperty("customer_name")
    private String name;

    public Customer() {
    }

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }
}
~~~

JSON lúc này dùng khóa customer_name, còn code Java vẫn truy cập property bằng name:

~~~json
{
  "customer_name": "An"
}
~~~

Annotation giúp tách tên trong hợp đồng JSON khỏi tên nội bộ trong Java.

## 5. Ánh xạ các thuộc tính cơ bản

### 5.1. String

JSON string được ánh xạ vào String:

~~~java
private String name;
~~~

~~~json
{
  "name": "An"
}
~~~

String phù hợp với tên, mã định danh, mô tả và dữ liệu văn bản. JSON string phải dùng dấu ngoặc kép; số viết trong dấu ngoặc kép vẫn là string, không phải JSON number.

### 5.2. Số nguyên

Các kiểu Java thường dùng gồm int, Integer, long và Long:

~~~java
private int age;
private Integer rewardPoints;
private long totalViews;
~~~

JSON number tương ứng:

~~~json
{
  "age": 25,
  "rewardPoints": 120,
  "totalViews": 9000000
}
~~~

Chọn kiểu dựa trên miền giá trị và ý nghĩa nghiệp vụ. int và long là primitive; Integer và Long là wrapper object và có thể mang null.

### 5.3. Số thập phân

Có thể dùng double cho dữ liệu dấu phẩy động thông thường. Với số thập phân cần độ chính xác, chẳng hạn giá trị tiền tệ, nên cân nhắc BigDecimal:

~~~java
private BigDecimal unitPrice;
~~~

~~~json
{
  "unitPrice": 125000.50
}
~~~

JSON không ghi rõ giá trị này phải trở thành double hay BigDecimal. Kiểu của field Java quyết định kiểu đích mà Jackson sử dụng. BigDecimal tránh sai số biểu diễn nhị phân thường gặp ở float/double, nhưng ứng dụng vẫn cần quy định scale và cách làm tròn theo nghiệp vụ.

### 5.4. Boolean

JSON boolean dùng true hoặc false, không đặt trong dấu ngoặc kép:

~~~java
private boolean active;
private Boolean verified;
~~~

~~~json
{
  "active": true,
  "verified": false
}
~~~

Với boolean primitive, getter JavaBean thường có dạng isActive(). Với Boolean wrapper, có thể dùng getter getVerified(). Wrapper Boolean còn có thể biểu diễn trạng thái chưa biết bằng null.

### 5.5. Enum cơ bản

Enum dùng để biểu diễn một tập giá trị hữu hạn:

~~~java
public enum AccountStatus {
    ACTIVE,
    LOCKED,
    CLOSED
}
~~~

~~~java
private AccountStatus status;
~~~

JSON thường biểu diễn enum bằng string tương ứng với tên hằng:

~~~json
{
  "status": "ACTIVE"
}
~~~

Nếu JSON gửi một giá trị không khớp enum, Jackson có thể báo lỗi tùy cấu hình. Nếu hợp đồng bên ngoài dùng mã khác tên hằng Java, hãy khai báo quy tắc ánh xạ rõ ràng thay vì phụ thuộc vào việc đổi tên enum trong source code.

## 6. Phân biệt thuộc tính vắng mặt, null và giá trị mặc định

Đây là điểm quan trọng khi đọc JSON vào POJO.

### 6.1. Property không xuất hiện

JSON:

~~~json
{
  "name": "An"
}
~~~

Class:

~~~java
public class Customer {
    private String name;
    private int age;

    // Constructor, getter và setter.
}
~~~

Nếu JSON không có age, Jackson không có giá trị mới để gán cho property đó. Với object mới được tạo bằng constructor không tham số, age thường giữ giá trị mặc định của Java là 0.

Nếu constructor chủ động gán giá trị ban đầu, giá trị đó có thể được giữ lại khi JSON không chứa property tương ứng:

~~~java
public Customer() {
    this.age = 18;
}
~~~

### 6.2. Property có giá trị null

JSON:

~~~json
{
  "name": "An",
  "age": null
}
~~~

Với field reference như String hoặc Integer, null có thể được gán vào field theo cấu hình và cơ chế setter. Với primitive như int, Java không có giá trị null. Cách Jackson xử lý null cho primitive phụ thuộc feature/configuration; cấu hình thông thường có thể chuyển thành giá trị mặc định, còn khi bật FAIL_ON_NULL_FOR_PRIMITIVES thì thao tác đọc có thể thất bại.

Nếu thuộc tính có thể không có giá trị, wrapper thường diễn đạt đúng hơn:

~~~java
private Integer age;
~~~

### 6.3. Chuỗi rỗng và số 0

Các JSON sau mang ý nghĩa khác nhau:

~~~json
{
  "name": ""
}
~~~

~~~json
{
  "age": 0
}
~~~

Chuỗi rỗng là một giá trị string có độ dài bằng 0; số 0 là một giá trị number. Cả hai đều khác property bị thiếu hoặc property có giá trị null.

| Trạng thái JSON | Ý nghĩa | Ví dụ Java thường gặp |
|---|---|---|
| Không có khóa | Không gửi property | Field giữ giá trị hiện tại/default |
| Khóa có giá trị null | Gửi giá trị null | Reference có thể nhận null |
| String rỗng | Gửi chuỗi không có ký tự | Chuỗi rỗng |
| Number 0 | Gửi số không | 0, 0L, BigDecimal.ZERO |
| Boolean false | Gửi giá trị false | false |

Khi xây dựng API cập nhật, cần xác định ý nghĩa của từng trạng thái. Không nên dùng một primitive nếu nghiệp vụ cần phân biệt chưa gửi và gửi giá trị 0.

## 7. Các trường hợp JSON không khớp POJO

### 7.1. JSON có property không tồn tại trong class

Nếu class Customer không có property department nhưng JSON gửi thêm department, mapper Jackson Databind tạo trực tiếp theo cấu hình thông thường có thể ném lỗi unknown property. Có thể bổ sung property, dùng @JsonIgnoreProperties(ignoreUnknown = true), hoặc cấu hình DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES theo chính sách ứng dụng.

Không nên tự động bỏ qua mọi property lạ trong tất cả API. Với một số hợp đồng, từ chối dữ liệu ngoài schema giúp phát hiện lỗi từ client.

### 7.2. JSON có kiểu dữ liệu không tương thích

Nếu field Java khai báo int nhưng JSON gửi một object hoặc một string không thể chuyển đổi, Jackson có thể ném lỗi ánh xạ. Cần sửa dữ liệu đầu vào hoặc mô hình Java theo hợp đồng đã thống nhất. Không nên bắt exception rồi gán một giá trị bất kỳ để che giấu dữ liệu sai.

### 7.3. Tên property không khớp

Nếu JSON dùng customer_name còn class có property customerName, mapper cần naming strategy hoặc annotation tương ứng. Có thể dùng @JsonProperty trên property hoặc đặt naming strategy chung cho mapper khi toàn bộ hợp đồng JSON cần cùng quy tắc.

### 7.4. Getter hoặc setter không đúng quy ước

Các method sai tên hoặc sai chữ ký có thể không được Jackson nhận diện như property mong muốn. Khi một field không được ghi hoặc không được gán, hãy kiểm tra getter, setter, visibility, annotation và naming strategy trên mapper.

## 8. Ví dụ hoàn chỉnh: ghi rồi đọc lại một POJO

Ví dụ dưới đây có thể đặt trong project Java đã thêm dependency Jackson Databind:

~~~java
import com.fasterxml.jackson.databind.ObjectMapper;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

public class CustomerJsonDemo {

    public static class Customer {
        private String id;
        private String name;
        private int age;
        private boolean active;

        public Customer() {
        }

        public Customer(String id, String name, int age, boolean active) {
            this.id = id;
            this.name = name;
            this.age = age;
            this.active = active;
        }

        public String getId() {
            return id;
        }

        public void setId(String id) {
            this.id = id;
        }

        public String getName() {
            return name;
        }

        public void setName(String name) {
            this.name = name;
        }

        public int getAge() {
            return age;
        }

        public void setAge(int age) {
            this.age = age;
        }

        public boolean isActive() {
            return active;
        }

        public void setActive(boolean active) {
            this.active = active;
        }
    }

    public static void main(String[] args) throws IOException {
        ObjectMapper mapper = new ObjectMapper();

        Customer original = new Customer(
                "CUS-001",
                "An",
                25,
                true
        );

        // Serialization: POJO -> JSON string.
        String json = mapper
                .writerWithDefaultPrettyPrinter()
                .writeValueAsString(original);

        System.out.println("JSON:");
        System.out.println(json);

        // Deserialization: JSON string -> POJO mới.
        Customer restored = mapper.readValue(json, Customer.class);

        System.out.println("Restored customer:");
        System.out.println(restored.getId());
        System.out.println(restored.getName());
        System.out.println(restored.getAge());
        System.out.println(restored.isActive());

        // Ghi JSON vào file.
        Path file = Path.of("customer.json");
        Files.writeString(file, json);

        // Đọc JSON từ file thành POJO.
        Customer fromFile = mapper.readValue(
                file.toFile(),
                Customer.class
        );

        System.out.println("Read from file: " + fromFile.getName());
    }
}
~~~

Quá trình gồm bốn thao tác: tạo object Customer, ghi object thành JSON string, đọc JSON thành object mới, rồi ghi và đọc lại file. Object sau khi đọc là object mới; nó có dữ liệu tương ứng nhưng không phải cùng tham chiếu với object ban đầu.

### 8.1. Kiểm tra bằng unit test

~~~java
@Test
void serializesAndDeserializesCustomer() throws Exception {
    ObjectMapper mapper = new ObjectMapper();

    Customer original = new Customer(
            "CUS-001",
            "An",
            25,
            true
    );

    String json = mapper.writeValueAsString(original);
    Customer restored = mapper.readValue(json, Customer.class);

    assertEquals(original.getId(), restored.getId());
    assertEquals(original.getName(), restored.getName());
    assertEquals(original.getAge(), restored.getAge());
    assertEquals(original.isActive(), restored.isActive());
}
~~~

Test xác nhận các thuộc tính cơ bản được giữ qua vòng serialize/deserialize. Khi class có thêm property, bổ sung assertion tương ứng hoặc dùng equality phù hợp với model.

## 9. Lưu ý khi sử dụng ObjectMapper

### 9.1. Cấu hình trước khi dùng chung

Thông thường, ứng dụng nên tạo và cấu hình ObjectMapper một lần rồi tái sử dụng. Hoàn tất đăng ký module và feature trước khi chia sẻ mapper cho nhiều luồng. Tránh thay đổi cấu hình mapper trong lúc các thao tác serialize/deserialize đang diễn ra.

Trong Spring Boot, nên inject mapper do framework quản lý nếu muốn dùng chung chính sách JSON của ứng dụng. Nếu tự tạo mapper riêng, cần chủ động đăng ký module và cấu hình cần thiết.

### 9.2. Không tự nối chuỗi JSON

Không nên tạo JSON bằng cách nối chuỗi:

~~~java
String json = "{\"name\":\"" + customer.getName() + "\"}";
~~~

Nếu tên có dấu ngoặc kép, dấu gạch chéo hoặc ký tự xuống dòng, chuỗi có thể không còn là JSON hợp lệ. Hãy để Jackson xử lý escape và chuyển đổi kiểu:

~~~java
String json = mapper.writeValueAsString(customer);
~~~

### 9.3. Xử lý exception có ngữ cảnh

Các thao tác đọc/ghi có thể thất bại vì JSON sai cú pháp, dữ liệu không tương thích, file không tồn tại hoặc lỗi quyền truy cập. Hãy giữ nguyên nguyên nhân exception và bổ sung ngữ cảnh phù hợp:

~~~java
try {
    Customer customer = mapper.readValue(json, Customer.class);
} catch (JsonProcessingException e) {
    throw new IllegalArgumentException("Customer JSON is invalid", e);
}
~~~

Với thao tác file, cần xử lý thêm IOException. Không nên bắt exception rồi bỏ qua, vì chương trình có thể tiếp tục với object chưa được tạo đúng.

### 9.4. Chọn kiểu Java đúng với dữ liệu

| Dữ liệu | Kiểu Java phù hợp |
|---|---|
| Văn bản, mã định danh | String |
| Số nguyên trong phạm vi int | int hoặc Integer |
| Số nguyên lớn hơn | long hoặc Long |
| Giá trị logic bắt buộc | boolean |
| Giá trị logic có thể chưa biết | Boolean |
| Số thập phân cần độ chính xác | BigDecimal |
| Tập giá trị hữu hạn | enum |

Kiểu Java là một phần của hợp đồng dữ liệu. Chọn kiểu phù hợp giúp Jackson ánh xạ rõ ràng và giảm nhu cầu ép kiểu hoặc xử lý ngoại lệ sau khi đọc.

## 10. Trình tự thực hành

Khi làm việc với một POJO cơ bản:

1. Xác định property cần trao đổi và kiểu Java của từng property.
2. Tạo class có field, constructor và getter/setter theo quy ước.
3. Tạo hoặc nhận ObjectMapper đã được cấu hình.
4. Dùng writeValueAsString để ghi object thành JSON string.
5. Dùng readValue và truyền đúng class đích để đọc JSON.
6. Kiểm tra tên property và kiểu dữ liệu trong JSON.
7. Thử trường hợp property bị thiếu, null, rỗng và có kiểu không tương thích.
8. Khi cần file, dùng writeValue/readValue với File hoặc stream và quản lý tài nguyên.
9. Viết test để xác nhận dữ liệu quan trọng được giữ qua vòng serialize/deserialize.

Khi đã làm chủ việc đọc ghi POJO với String, số, boolean và enum, có thể học tiếp object lồng nhau, collection, generic type, annotation nâng cao, custom serializer và custom deserializer.
