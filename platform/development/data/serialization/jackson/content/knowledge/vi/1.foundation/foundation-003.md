# Phân biệt JSON, mô hình Java và thư viện xử lý dữ liệu

Khi một ứng dụng Java gửi dữ liệu qua HTTP, đọc cấu hình hoặc lưu thông tin vào một hệ thống khác, dữ liệu thường phải đi qua nhiều dạng biểu diễn. Một đối tượng Java có thể được chuyển thành chuỗi JSON để truyền đi; ở phía nhận, chuỗi JSON được đọc và chuyển thành đối tượng Java tương ứng.

Trong quy trình đó có ba khái niệm dễ bị nhầm lẫn:

- **JSON** là định dạng văn bản dùng để biểu diễn và trao đổi dữ liệu.
- **Mô hình Java** là tập hợp các kiểu dữ liệu, lớp và đối tượng mà chương trình dùng để làm việc với dữ liệu trong bộ nhớ.
- **Thư viện xử lý dữ liệu**, chẳng hạn Jackson, là công cụ giúp chuyển đổi giữa JSON và các cấu trúc dữ liệu Java, cũng như đọc, ghi hoặc thao tác dữ liệu.

Ba khái niệm này có liên quan nhưng không thay thế cho nhau. JSON mô tả dữ liệu sẽ được biểu diễn ra sao; mô hình Java mô tả chương trình tổ chức và sử dụng dữ liệu như thế nào; thư viện đảm nhiệm việc chuyển đổi giữa các dạng đó.

## 1. JSON là định dạng biểu diễn dữ liệu

JSON (JavaScript Object Notation) là định dạng dữ liệu dạng văn bản, độc lập với ngôn ngữ lập trình. Dù tên gọi có chữ JavaScript, JSON được dùng rộng rãi trong Java, JavaScript, Python, Go, C#, PHP và nhiều nền tảng khác.

Một tài liệu JSON được xây dựng từ các kiểu giá trị cơ bản:

| Kiểu JSON | Ví dụ | Ý nghĩa |
|---|---|---|
| Object | `{"id": 23, "name": "Lan"}` | Tập hợp các cặp khóa và giá trị; khóa là chuỗi |
| Array | `["JAVA", "SQL"]` | Danh sách các giá trị theo thứ tự |
| String | `"Xin chào"` | Chuỗi ký tự, đặt trong dấu ngoặc kép |
| Number | `23`, `19.5` | Số nguyên hoặc số thập phân |
| Boolean | `true`, `false` | Giá trị đúng hoặc sai |
| Null | `null` | Giá trị rỗng được biểu diễn tường minh |

Ví dụ một bản ghi học viên:

```json
{
  "id": 23,
  "name": "Lan",
  "active": true,
  "courses": ["Java", "SQL"],
  "address": {
    "city": "Ho Chi Minh City",
    "district": "District 3"
  },
  "note": null
}
```

Trong ví dụ trên, dấu ngoặc nhọn tạo một object; mỗi thuộc tính gồm tên khóa và giá trị. `courses` là một array chứa các chuỗi. `address` là object lồng bên trong object bên ngoài. `note` có giá trị `null`.

JSON có một số quy tắc cú pháp cần nhớ:

- Tên khóa và giá trị kiểu chuỗi phải dùng dấu ngoặc kép (`"`).
- Các cặp khóa và giá trị trong object, cũng như các phần tử trong array, được ngăn cách bằng dấu phẩy.
- Không đặt dấu phẩy sau phần tử cuối cùng.
- JSON chuẩn không hỗ trợ comment, `undefined`, hàm hoặc các đối tượng đặc thù của một ngôn ngữ lập trình.
- JSON không có kiểu ngày giờ, kiểu tiền tệ hay kiểu nhị phân riêng. Các ứng dụng thường thống nhất quy ước biểu diễn, ví dụ ngày giờ bằng chuỗi ISO 8601 hoặc dữ liệu nhị phân bằng Base64.

JSON chỉ mô tả cấu trúc và giá trị. Nó không quy định một thuộc tính có hợp lệ về nghiệp vụ hay không. Chẳng hạn, JSON có thể chứa `"age": -5` đúng cú pháp, nhưng ứng dụng vẫn có thể từ chối tuổi âm.

## 2. Mô hình Java là cấu trúc dữ liệu của chương trình

Trong Java, chương trình thường biểu diễn dữ liệu bằng các kiểu nguyên thủy, lớp, record, enum và các cấu trúc tập hợp như `List`, `Set` hoặc `Map`. Một đối tượng Java tồn tại trong bộ nhớ và có thể chứa trạng thái cùng hành vi.

Ví dụ, ứng dụng có thể định nghĩa lớp `Student` để mô tả một học viên:

```java
import java.util.List;

public class Student {
    private long id;
    private String name;
    private boolean active;
    private List<String> courses;
    private Address address;
    private String note;

    public Student() {
    }

    public long getId() {
        return id;
    }

    public void setId(long id) {
        this.id = id;
    }

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }

    public boolean isActive() {
        return active;
    }

    public void setActive(boolean active) {
        this.active = active;
    }

    public List<String> getCourses() {
        return courses;
    }

    public void setCourses(List<String> courses) {
        this.courses = courses;
    }

    public Address getAddress() {
        return address;
    }

    public void setAddress(Address address) {
        this.address = address;
    }

    public String getNote() {
        return note;
    }

    public void setNote(String note) {
        this.note = note;
    }
}
```

Lớp `Address` có thể được định nghĩa riêng:

```java
public class Address {
    private String city;
    private String district;

    public Address() {
    }

    public String getCity() {
        return city;
    }

    public void setCity(String city) {
        this.city = city;
    }

    public String getDistrict() {
        return district;
    }

    public void setDistrict(String district) {
        this.district = district;
    }
}
```

Mô hình Java có các đặc điểm mà JSON không cung cấp:

- **Kiểu dữ liệu tĩnh:** trình biên dịch biết `id` là `long`, `active` là `boolean`, còn `courses` là `List<String>`. Nhờ đó, nhiều lỗi sử dụng sai kiểu có thể được phát hiện khi biên dịch.
- **Đóng gói:** trường có thể để `private` và chỉ được truy cập thông qua phương thức hoặc API được lớp công khai.
- **Hành vi:** lớp có thể chứa phương thức tính toán, kiểm tra điều kiện và thực thi quy tắc nghiệp vụ.
- **Quan hệ kiểu:** một lớp có thể kế thừa lớp khác, triển khai interface hoặc tham chiếu đến các đối tượng khác.
- **Cấu trúc phong phú:** Java có các kiểu như `LocalDate`, `BigDecimal`, `UUID`, enum và nhiều kiểu khác không có dạng tương ứng trực tiếp trong JSON.

Một mô hình Java không bắt buộc phải giống hệt cấu trúc JSON. Ví dụ, ứng dụng có thể dùng trường `fullName` trong Java nhưng trao đổi với hệ thống bên ngoài bằng khóa `name`. Một lớp cũng có thể chứa trường nội bộ không cần gửi ra ngoài, hoặc kết hợp nhiều thuộc tính JSON thành một cấu trúc tiện dụng hơn cho nghiệp vụ.

Ngoài lớp thông thường, Java còn có `record`, phù hợp với các đối tượng dữ liệu chủ yếu dùng để mang giá trị:

```java
public record StudentSummary(long id, String name, boolean active) {
}
```

Record tự cung cấp các thành phần truy cập và tính chất bất biến ở mức tham chiếu thành phần. Jackson hỗ trợ record trong các phiên bản phù hợp; khi dùng record, cần bảo đảm phiên bản thư viện tương thích với phiên bản Java của dự án.

## 3. Jackson là thư viện chuyển đổi và xử lý dữ liệu

Jackson là một bộ thư viện Java phổ biến để đọc và ghi JSON. Jackson không phải là JSON và cũng không phải mô hình dữ liệu của ứng dụng. Nó là lớp công cụ đứng giữa hai phía, giúp chương trình chuyển đổi dữ liệu theo các quy tắc đã cấu hình.

Các thành phần thường gặp trong hệ sinh thái Jackson gồm:

| Thành phần | Vai trò chính |
|---|---|
| `jackson-core` | Cung cấp API xử lý JSON ở mức luồng token, đọc và ghi tuần tự |
| `jackson-databind` | Ánh xạ dữ liệu JSON sang đối tượng Java và ngược lại; cung cấp tree model |
| `jackson-annotations` | Cung cấp annotation để tùy chỉnh tên thuộc tính, cách bỏ qua trường và định dạng dữ liệu |

Trong ứng dụng thông thường, `jackson-databind` là dependency được sử dụng trực tiếp nhiều nhất; các thành phần cần thiết khác thường được kéo vào thông qua dependency bắc cầu. Cần chọn phiên bản phù hợp với Java và các dependency của dự án, đồng thời quản lý phiên bản nhất quán bằng dependency management hoặc BOM nếu dự án có sử dụng.

### 3.1. Tuần tự hóa và giải tuần tự hóa

Hai thao tác cơ bản khi làm việc với JSON là:

- **Serialization (tuần tự hóa):** chuyển đối tượng Java thành chuỗi hoặc luồng JSON.
- **Deserialization (giải tuần tự hóa):** đọc JSON và tạo đối tượng Java tương ứng.

Với Jackson Databind, lớp thường được dùng để thực hiện hai thao tác này là `ObjectMapper`.

```java
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.List;

public class JacksonExample {
    public static void main(String[] args) throws JsonProcessingException {
        ObjectMapper mapper = new ObjectMapper();

        Student student = new Student();
        student.setId(23L);
        student.setName("Lan");
        student.setActive(true);
        student.setCourses(List.of("Java", "SQL"));

        String json = mapper.writeValueAsString(student);
        System.out.println(json);

        Student restored = mapper.readValue(json, Student.class);
        System.out.println(restored.getName());
    }
}
```

`writeValueAsString` nhận đối tượng Java và trả về chuỗi JSON. `readValue` nhận chuỗi JSON cùng kiểu đích, sau đó tạo đối tượng `Student`. Với lớp JavaBean như ví dụ, Jackson thường sử dụng constructor không tham số và các thuộc tính có thể truy cập được thông qua getter/setter hoặc cấu hình truy cập phù hợp.

Luồng chuyển đổi có thể hình dung như sau:

```text
Đối tượng Java
      |
      | ObjectMapper.writeValueAsString(...)
      v
  Chuỗi JSON
      |
      | ObjectMapper.readValue(...)
      v
Đối tượng Java
```

Đây là chuyển đổi giữa hai biểu diễn. Đối tượng sau khi đọc lại có cùng dữ liệu được biểu diễn trong JSON theo quy tắc ánh xạ, nhưng không nhất thiết là cùng một đối tượng trong bộ nhớ hoặc giữ nguyên mọi trạng thái nội bộ của đối tượng ban đầu.

### 3.2. Đọc và ghi collection, kiểu tổng quát

Khi đọc JSON thành một lớp cụ thể, có thể truyền `Student.class`. Với kiểu tổng quát như `List<Student>`, thông tin kiểu phần tử có thể bị mất do cơ chế type erasure của Java. Jackson cung cấp `TypeReference` để giữ thông tin kiểu cần thiết:

```java
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.List;

ObjectMapper mapper = new ObjectMapper();

String json = """
    [
      {"id": 23, "name": "Lan", "active": true},
      {"id": 24, "name": "Minh", "active": false}
    ]
    """;

List<Student> students = mapper.readValue(
    json,
    new TypeReference<List<Student>>() {}
);
```

Text block (`"""`) có trong các phiên bản Java hỗ trợ cú pháp này. Nếu dự án dùng Java cũ hơn, có thể thay bằng chuỗi thông thường. Với kiểu tổng quát lồng nhau như `Map<String, List<Student>>`, `TypeReference` cũng giúp mô tả đầy đủ kiểu đích.

## 4. Ba cách Jackson làm việc với cấu trúc JSON

Jackson cung cấp nhiều mức trừu tượng. Chọn cách phù hợp phụ thuộc vào kích thước dữ liệu và mục đích xử lý.

### 4.1. Data Binding: ánh xạ trực tiếp vào mô hình Java

Data Binding là cách thường dùng nhất trong ứng dụng nghiệp vụ. Chương trình xác định lớp đích, Jackson đọc JSON rồi ánh xạ các giá trị vào thuộc tính tương ứng.

```java
Student student = mapper.readValue(json, Student.class);
String output = mapper.writeValueAsString(student);
```

Cách này phù hợp khi cấu trúc dữ liệu đã biết và ứng dụng có mô hình Java rõ ràng. Code nghiệp vụ có thể làm việc trực tiếp với `Student`, thay vì phải tự tìm từng khóa trong JSON.

### 4.2. Tree Model: thao tác JSON như một cây nút

Khi cấu trúc JSON chưa biết trước hoàn toàn hoặc chỉ cần đọc một vài trường, có thể dùng `JsonNode`:

```java
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

ObjectMapper mapper = new ObjectMapper();
JsonNode root = mapper.readTree(json);

long id = root.path("id").asLong();
String name = root.path("name").asText();
String city = root.path("address").path("city").asText();
```

`readTree` tạo cây biểu diễn JSON. `path` trả về một nút an toàn hơn khi đường dẫn không tồn tại: nó trả về nút thiếu thay vì ném lỗi ngay như một số cách truy cập trực tiếp. Tuy vậy, chương trình vẫn cần kiểm tra sự hiện diện và kiểu của dữ liệu khi các trường là bắt buộc hoặc có ý nghĩa nghiệp vụ.

Tree Model hữu ích khi xử lý JSON có cấu trúc thay đổi, viết công cụ chuyển đổi dữ liệu hoặc chỉ cần trích xuất một phần tài liệu. Đổi lại, code phải tự kiểm tra kiểu và chuyển giá trị ở nhiều vị trí hơn.

### 4.3. Streaming API: xử lý JSON theo luồng token

Streaming API của Jackson Core cho phép đọc hoặc ghi từng token theo thứ tự. Cách này phù hợp với tài liệu rất lớn, khi không muốn nạp toàn bộ JSON hoặc toàn bộ cây đối tượng vào bộ nhớ.

Ví dụ về ý tưởng đọc token:

```java
import com.fasterxml.jackson.core.JsonFactory;
import com.fasterxml.jackson.core.JsonParser;
import com.fasterxml.jackson.core.JsonToken;
import java.io.StringReader;

JsonFactory factory = new JsonFactory();

try (JsonParser parser = factory.createParser(new StringReader(json))) {
    while (parser.nextToken() != null) {
        JsonToken token = parser.currentToken();
        System.out.println(token);

        if (token == JsonToken.FIELD_NAME) {
            System.out.println("Tên trường: " + parser.currentName());
        }
    }
}
```

Streaming API cho phép kiểm soát chi tiết quá trình đọc và thường tiết kiệm bộ nhớ hơn khi xử lý dữ liệu lớn. Tuy nhiên, lập trình viên phải tự quản lý trạng thái parser và logic xây dựng kết quả, vì vậy code có thể dài và phức tạp hơn Data Binding.

## 5. Ánh xạ giữa tên trường JSON và thuộc tính Java

Trong trường hợp đơn giản, Jackson có thể dựa vào tên thuộc tính để ánh xạ tự động. Nhưng tên JSON và tên trong Java không phải lúc nào cũng giống nhau.

Giả sử hệ thống bên ngoài gửi:

```json
{
  "student_id": 23,
  "full_name": "Lan"
}
```

Trong Java, ứng dụng muốn dùng tên `id` và `name`. Có thể dùng `@JsonProperty`:

```java
import com.fasterxml.jackson.annotation.JsonProperty;

public class StudentIdentity {
    @JsonProperty("student_id")
    private long id;

    @JsonProperty("full_name")
    private String name;

    public StudentIdentity() {
    }

    public long getId() {
        return id;
    }

    public void setId(long id) {
        this.id = id;
    }

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }
}
```

Một số annotation thường gặp:

| Annotation | Công dụng |
|---|---|
| `@JsonProperty("...")` | Chỉ định tên thuộc tính trong JSON |
| `@JsonAlias({"..."})` | Chấp nhận thêm tên khác khi đọc JSON, hữu ích khi tương thích dữ liệu cũ |
| `@JsonIgnore` | Bỏ qua thuộc tính trong quá trình ánh xạ theo cấu hình mặc định |
| `@JsonInclude(...)` | Quy định khi nào thuộc tính được đưa vào JSON khi ghi |
| `@JsonFormat(...)` | Tùy chỉnh cách biểu diễn hoặc đọc một số kiểu dữ liệu, thường gặp ở ngày giờ |

Ví dụ, nếu không muốn đưa trường nội bộ `passwordHash` vào JSON trả về:

```java
import com.fasterxml.jackson.annotation.JsonIgnore;

public class Account {
    private String username;

    @JsonIgnore
    private String passwordHash;

    // Constructor, getter và setter được lược bỏ.
}
```

Không nên xem annotation là cơ chế phân quyền hoặc bảo vệ dữ liệu duy nhất. Với API công khai, nên thiết kế DTO chỉ chứa những trường được phép nhận hoặc trả về, đồng thời kiểm tra quyền truy cập ở tầng nghiệp vụ.

## 6. Những điểm cần chú ý khi chuyển JSON sang Java

### 6.1. Trường bị thiếu, trường có giá trị null và giá trị mặc định

Ba trường hợp sau không hoàn toàn giống nhau:

```json
{}
```

```json
{"name": null}
```

```json
{"name": "Lan"}
```

Trường hợp đầu không có khóa `name`; trường hợp thứ hai có khóa nhưng giá trị là `null`; trường hợp thứ ba có chuỗi cụ thể. Khi ánh xạ vào một lớp Java thông thường, trường bị thiếu hoặc được gán `null` có thể dẫn đến cùng giá trị trường sau khi tạo đối tượng, tùy constructor, setter và cấu hình. Nếu ứng dụng cần phân biệt rõ ba trạng thái, cần thiết kế kiểu nhận dữ liệu và logic kiểm tra phù hợp thay vì giả định rằng một trường Java đơn lẻ luôn giữ được sự khác biệt đó.

Với kiểu nguyên thủy như `int` hoặc `boolean`, Java không thể gán `null`; giá trị mặc định của trường chưa được gán lần lượt là `0` và `false`. Nếu cần biểu diễn trạng thái chưa có giá trị, có thể cân nhắc kiểu bao `Integer`, `Boolean` hoặc một kiểu dữ liệu thể hiện rõ trạng thái.

### 6.2. Trường JSON không có trong lớp Java

Một JSON có thể chứa trường mà phiên bản lớp Java hiện tại chưa khai báo. Cách Jackson xử lý phụ thuộc vào cấu hình. Với cấu hình mặc định phổ biến của `ObjectMapper`, trường không nhận diện được có thể làm quá trình đọc thất bại bằng lỗi `UnrecognizedPropertyException`.

Trong một số API cần khả năng tương thích tiến, ứng dụng có thể chọn bỏ qua trường lạ:

```java
import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.ObjectMapper;

ObjectMapper mapper = new ObjectMapper();
mapper.disable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES);
```

Đây là quyết định về hợp đồng dữ liệu. Bỏ qua trường lạ giúp client cũ đọc được phản hồi có thêm trường mới, nhưng cũng có thể che giấu lỗi chính tả hoặc thay đổi cấu trúc ngoài dự kiến. Hãy chọn chính sách dựa trên yêu cầu tương thích của hệ thống.

### 6.3. Sai khác kiểu dữ liệu

Giả sử lớp Java khai báo `id` là `long`, nhưng JSON lại chứa:

```json
{"id": "hai-muoi-ba"}
```

Jackson không thể chuyển chuỗi này thành số theo cách thông thường và sẽ báo lỗi ánh xạ. Tương tự, dữ liệu có thể sai kiểu phần tử trong array, sai cấu trúc object lồng nhau hoặc vượt giới hạn của kiểu số đích.

Không nên mặc định rằng parse JSON thành công đồng nghĩa dữ liệu hợp lệ. Sau khi ánh xạ, ứng dụng còn cần kiểm tra các ràng buộc như trường bắt buộc, độ dài chuỗi, miền giá trị và quan hệ giữa các trường.

### 6.4. Ngày giờ và kiểu dữ liệu đặc thù

JSON không có kiểu ngày giờ chuẩn riêng. Một ứng dụng thường gửi ngày giờ dưới dạng chuỗi, ví dụ:

```json
{
  "createdAt": "2026-11-12T08:30:00Z"
}
```

Nếu mô hình Java dùng `Instant`, `LocalDate` hoặc `LocalDateTime`, dự án thường cần module hỗ trợ Java Time của Jackson (`jackson-datatype-jsr310`) và đăng ký module đó với `ObjectMapper`:

```java
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.datatype.jsr310.JavaTimeModule;

ObjectMapper mapper = new ObjectMapper();
mapper.registerModule(new JavaTimeModule());
```

Định dạng cụ thể cần được thống nhất giữa các hệ thống. Ví dụ, `Instant` thể hiện một thời điểm trên dòng thời gian, còn `LocalDateTime` không chứa múi giờ hoặc độ lệch UTC. Chọn sai kiểu có thể làm thời điểm bị hiểu khác nhau giữa các môi trường.

### 6.5. Số thập phân và độ chính xác

JSON có kiểu number nhưng không phân biệt kiểu `float`, `double` hay `BigDecimal` của Java. Nếu dữ liệu cần độ chính xác thập phân, chẳng hạn số tiền, nên cân nhắc `BigDecimal` thay vì `double`, đồng thời thống nhất quy tắc làm tròn và định dạng với hệ thống trao đổi dữ liệu.

## 7. Cấu hình và sử dụng ObjectMapper hợp lý

`ObjectMapper` là đối tượng cấu hình và thực hiện ánh xạ. Trong một ứng dụng, thường nên tạo và cấu hình mapper ở giai đoạn khởi tạo, sau đó tái sử dụng. `ObjectMapper` an toàn khi dùng đồng thời nếu toàn bộ cấu hình được hoàn tất trước khi bắt đầu các thao tác đọc/ghi; tránh thay đổi cấu hình của mapper sau khi đã đưa vào sử dụng.

Ví dụ cấu hình module ngày giờ và chính sách trường lạ:

```java
ObjectMapper mapper = new ObjectMapper();
mapper.registerModule(new JavaTimeModule());
mapper.disable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES);
```

Đối với từng thao tác cần chính sách riêng, có thể dùng `ObjectReader` hoặc `ObjectWriter` được tạo từ mapper thay vì liên tục sửa cấu hình dùng chung. Cách này giúp cấu hình theo từng luồng xử lý rõ ràng hơn.

Khi tích hợp Jackson vào dự án, cần chú ý:

1. **Quản lý dependency:** dùng phiên bản tương thích với Java và framework đang chạy; tránh để các module Jackson lệch phiên bản.
2. **Xử lý ngoại lệ:** thao tác đọc/ghi có thể phát sinh `JsonProcessingException` hoặc các ngoại lệ I/O. Hãy xử lý ở đúng tầng, bổ sung ngữ cảnh cần thiết và không làm lộ dữ liệu nhạy cảm trong log.
3. **Kiểm tra dữ liệu:** xác thực đầu vào sau khi ánh xạ. Jackson kiểm tra cú pháp và thực hiện chuyển đổi kiểu, nhưng không tự hiểu toàn bộ quy tắc nghiệp vụ của ứng dụng.
4. **Giới hạn tài nguyên:** với đầu vào không tin cậy hoặc tài liệu lớn, cần cân nhắc giới hạn kích thước, độ sâu lồng nhau và thời gian xử lý; dùng Streaming API khi phù hợp.
5. **An toàn kiểu đa hình:** không bật cơ chế polymorphic default typing một cách tùy tiện cho JSON không tin cậy. Nếu cần kiểu đa hình, hãy dùng cấu hình có kiểm soát và danh sách kiểu được phép.
6. **Thiết kế DTO:** dùng các lớp truyền dữ liệu phù hợp với API để kiểm soát chính xác trường được nhận và trả về; không nhất thiết tuần tự hóa trực tiếp toàn bộ entity hoặc đối tượng nội bộ.

## 8. So sánh nhanh ba khái niệm

| Tiêu chí | JSON | Mô hình Java | Thư viện xử lý dữ liệu (Jackson) |
|---|---|---|---|
| Bản chất | Định dạng văn bản | Kiểu, lớp và đối tượng trong chương trình | Bộ công cụ và API |
| Mục đích | Trao đổi hoặc lưu dữ liệu theo cấu trúc thống nhất | Tổ chức dữ liệu và hỗ trợ logic ứng dụng | Đọc, ghi, phân tích và chuyển đổi dữ liệu |
| Phụ thuộc ngôn ngữ | Không | Có, gắn với hệ sinh thái Java | Có, dành cho Java/JVM |
| Kiểu dữ liệu | Object, array, string, number, boolean, null | Kiểu nguyên thủy, class, record, enum, collection và kiểu thư viện | Ánh xạ giữa các biểu diễn; có thể mở rộng bằng module và cấu hình |
| Nơi thường xuất hiện | API HTTP, file cấu hình, message, dữ liệu tích hợp | Bộ nhớ ứng dụng, tầng nghiệp vụ, DTO | Trong code Java thực hiện chuyển đổi hoặc xử lý |
| Ví dụ | `{"id": 23, "name": "Lan"}` | `Student student` | `mapper.readValue(json, Student.class)` |

Có thể ghi nhớ bằng ba câu hỏi:

- **JSON:** Dữ liệu được biểu diễn và trao đổi dưới dạng nào?
- **Mô hình Java:** Chương trình Java tổ chức và sử dụng dữ liệu đó bằng kiểu nào?
- **Jackson:** Làm thế nào để chuyển đổi hoặc thao tác giữa JSON và dữ liệu Java?

## 9. Ví dụ tổng hợp: nhận JSON từ API

Giả sử một API trả về nội dung:

```json
{
  "student_id": 23,
  "full_name": "Lan",
  "active": true
}
```

Ứng dụng có thể định nghĩa DTO tương ứng:

```java
import com.fasterxml.jackson.annotation.JsonProperty;

public class StudentResponse {
    @JsonProperty("student_id")
    private long id;

    @JsonProperty("full_name")
    private String name;

    private boolean active;

    public StudentResponse() {
    }

    public long getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public boolean isActive() {
        return active;
    }

    public void setId(long id) {
        this.id = id;
    }

    public void setName(String name) {
        this.name = name;
    }

    public void setActive(boolean active) {
        this.active = active;
    }
}
```

Sau đó dùng Jackson để chuyển JSON thành DTO:

```java
ObjectMapper mapper = new ObjectMapper();
StudentResponse response = mapper.readValue(json, StudentResponse.class);

System.out.println(response.getId());
System.out.println(response.getName());
System.out.println(response.isActive());
```

Trong ví dụ này:

1. JSON quy định cấu trúc dữ liệu mà API gửi qua mạng.
2. `StudentResponse` là mô hình Java mà ứng dụng chọn để tiếp nhận dữ liệu đó.
3. `@JsonProperty` mô tả quan hệ giữa khóa JSON và thuộc tính Java.
4. `ObjectMapper` thực hiện việc đọc JSON và tạo đối tượng `StudentResponse`.
5. Code nghiệp vụ sử dụng getter của đối tượng sau khi chuyển đổi; nếu cần, ứng dụng tiếp tục xác thực dữ liệu trước khi xử lý.

Khi gửi dữ liệu đi, quy trình diễn ra theo chiều ngược lại: ứng dụng chuẩn bị đối tượng Java, Jackson tuần tự hóa đối tượng thành JSON, rồi tầng HTTP hoặc message broker gửi nội dung đó đến hệ thống khác.

## 10. Cách chọn cách xử lý phù hợp

Trong thực tế, có thể chọn theo đặc điểm của dữ liệu:

| Tình huống | Cách tiếp cận phù hợp |
|---|---|
| Cấu trúc JSON ổn định, đã có DTO Java | Data Binding với `ObjectMapper` |
| Chỉ cần đọc một số trường hoặc cấu trúc thay đổi | Tree Model với `JsonNode` |
| Tệp JSON rất lớn hoặc cần xử lý tuần tự | Streaming API của Jackson Core |
| Cần đổi tên khóa JSON so với thuộc tính Java | Annotation như `@JsonProperty` hoặc cấu hình naming strategy |
| Cần đọc collection có kiểu phần tử cụ thể | `TypeReference` hoặc `JavaType` |
| Cần xử lý ngày giờ Java | Module Java Time và quy ước định dạng thống nhất |

Khi thiết kế hệ thống, hãy xem JSON là hợp đồng trao đổi dữ liệu, mô hình Java là cách ứng dụng biểu diễn dữ liệu để làm việc, còn Jackson là một lựa chọn công cụ để thực hiện chuyển đổi. Giữ rõ ranh giới này giúp thay đổi API, thay đổi lớp Java hoặc thay thế thư viện xử lý dữ liệu dễ kiểm soát hơn.
