# Phân biệt Jackson và cơ chế tuần tự hóa đối tượng của Java

Trong Java, từ *serialization* thường được dùng cho hai việc có liên quan nhưng khác nhau:

- **Jackson** là thư viện giúp chuyển dữ liệu giữa đối tượng Java và các định dạng dữ liệu như JSON.
- **Java Object Serialization** là cơ chế có sẵn trong JDK để ghi và khôi phục đồ thị đối tượng Java thông qua luồng nhị phân.

Cả hai đều có thể biến trạng thái của một đối tượng thành dữ liệu để lưu trữ hoặc truyền đi, nhưng chúng tạo ra định dạng khác nhau, phục vụ mục đích khác nhau và có quy tắc tương thích khác nhau. Hiểu rõ ranh giới này giúp chọn đúng công cụ khi xây dựng REST API, lưu dữ liệu, trao đổi thông tin giữa các dịch vụ hoặc xử lý dữ liệu trong bộ nhớ.

## 1. Serialization và deserialization là gì?

**Serialization (tuần tự hóa)** là quá trình chuyển dữ liệu trong bộ nhớ thành một biểu diễn có thể ghi vào file, gửi qua mạng hoặc lưu trữ ở nơi khác.

**Deserialization (giải tuần tự hóa)** là quá trình đọc biểu diễn đó và khôi phục dữ liệu thành cấu trúc mà chương trình có thể sử dụng.

Ví dụ, một đối tượng có trạng thái:

```text
User
 ├── id   = 42
 └── name = "An"
```

Có thể được chuyển thành JSON:

```json
{
  "id": 42,
  "name": "An"
}
```

Hoặc được ghi thành một luồng nhị phân theo định dạng Java Object Serialization. Hai kết quả này không thể thay thế trực tiếp cho nhau: JSON là dữ liệu có cấu trúc theo quy ước JSON, còn luồng của Java Serialization chứa thông tin phục vụ việc khôi phục đồ thị đối tượng Java.

Vì vậy, khi nghe nói một lớp "có thể serialize", cần xác định người nói đang đề cập đến cách chuyển đổi nào.

## 2. Jackson là gì?

Jackson là một bộ thư viện Java để đọc và ghi dữ liệu. Trường hợp phổ biến nhất là ánh xạ giữa đối tượng Java và JSON.

Các thành phần thường gặp gồm:

- **Jackson Core** cung cấp API đọc và ghi JSON theo luồng, làm việc với từng token.
- **Jackson Databind** cung cấp data binding giữa JSON và đối tượng Java, đồng thời hỗ trợ mô hình cây dữ liệu như `JsonNode`.
- **Jackson Annotations** cung cấp annotation để điều khiển tên thuộc tính, trường bị bỏ qua, định dạng và những quy tắc ánh xạ khác.

Ứng dụng thường dùng `ObjectMapper` từ `jackson-databind` để thực hiện các thao tác ở mức cao.

### 2.1. Chuyển đối tượng Java thành JSON

Xét lớp `User`:

```java
public class User {
    private long id;
    private String name;

    public User() {
    }

    public User(long id, String name) {
        this.id = id;
        this.name = name;
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

Có thể chuyển một đối tượng thành chuỗi JSON như sau:

```java
import com.fasterxml.jackson.databind.ObjectMapper;

import java.io.IOException;

public class JacksonExample {
    public static void main(String[] args) throws IOException {
        User user = new User(42L, "An");

        ObjectMapper mapper = new ObjectMapper();
        String json = mapper.writeValueAsString(user);

        System.out.println(json);
    }
}
```

Kết quả JSON có dạng:

```json
{"id":42,"name":"An"}
```

Jackson đọc các thuộc tính mà nó nhận diện được theo quy tắc truy cập và cấu hình hiện hành. Trong ví dụ này, các getter cho phép Jackson nhận diện `id` và `name`.

Điểm cần nhớ: lớp `User` **không cần triển khai `Serializable`** để Jackson ghi nó thành JSON.

### 2.2. Chuyển JSON thành đối tượng Java

Chiều ngược lại được gọi là deserialization:

```java
String json = """
    {
      "id": 42,
      "name": "An"
    }
    """;

ObjectMapper mapper = new ObjectMapper();
User user = mapper.readValue(json, User.class);

System.out.println(user.getName());
```

Jackson phân tích JSON, tìm cách ánh xạ các thuộc tính vào lớp đích và tạo ra đối tượng `User`. Với JavaBean đơn giản như ví dụ trên, constructor không tham số cùng setter là một cách tạo đối tượng phổ biến. Jackson cũng hỗ trợ record, constructor có tham số và nhiều kiểu tạo đối tượng khác khi cấu hình hoặc metadata phù hợp.

Khi kiểu đích là kiểu generic, cần cung cấp thông tin kiểu đầy đủ vì `List.class` tự nó không cho biết kiểu phần tử:

```java
import com.fasterxml.jackson.core.type.TypeReference;

List<User> users = mapper.readValue(
    json,
    new TypeReference<List<User>>() {}
);
```

### 2.3. Điều khiển JSON bằng annotation

Jackson cho phép định nghĩa cách một thuộc tính xuất hiện trong JSON mà không phải đổi tên thuộc tính Java.

```java
import com.fasterxml.jackson.annotation.JsonIgnore;
import com.fasterxml.jackson.annotation.JsonProperty;

public class Account {
    private long id;

    @JsonProperty("display_name")
    private String displayName;

    @JsonIgnore
    private String password;

    // Constructor, getter và setter
}
```

Trong ví dụ này:

- `@JsonProperty("display_name")` ánh xạ thuộc tính Java `displayName` với khóa JSON `display_name`.
- `@JsonIgnore` yêu cầu Jackson bỏ qua thuộc tính `password` trong quá trình data binding theo annotation này.

Jackson còn có các annotation và cấu hình để xử lý giá trị null, định dạng ngày giờ, tên thuộc tính, kiểu đa hình và nhiều trường hợp khác. Quy tắc cuối cùng phụ thuộc vào annotation, module và cấu hình của `ObjectMapper`.

Jackson mặc định thường được dùng với JSON, nhưng hệ sinh thái Jackson còn có module cho một số định dạng dữ liệu khác. Do đó, Jackson là thư viện xử lý dữ liệu và ánh xạ đối tượng; nó không đồng nghĩa với riêng một lời gọi chuyển object thành chuỗi JSON.

## 3. Java Object Serialization là gì?

Java Object Serialization là cơ chế tuần tự hóa đối tượng được tích hợp trong JDK, chủ yếu nằm trong package `java.io`.

Hai lớp thường dùng là:

- `ObjectOutputStream`: ghi đối tượng vào một `OutputStream`.
- `ObjectInputStream`: đọc đối tượng từ một `InputStream`.

Để một lớp tham gia cơ chế mặc định, lớp đó triển khai interface đánh dấu `java.io.Serializable`.

### 3.1. Ghi đối tượng thành luồng nhị phân

Ví dụ lớp `User` triển khai `Serializable`:

```java
import java.io.Serializable;

public class User implements Serializable {
    private static final long serialVersionUID = 1L;

    private long id;
    private String name;

    public User(long id, String name) {
        this.id = id;
        this.name = name;
    }

    public long getId() {
        return id;
    }

    public String getName() {
        return name;
    }
}
```

Ghi đối tượng vào file:

```java
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.ObjectOutputStream;

public class WriteObjectExample {
    public static void main(String[] args) throws IOException {
        User user = new User(42L, "An");

        try (ObjectOutputStream output =
                 new ObjectOutputStream(new FileOutputStream("user.bin"))) {
            output.writeObject(user);
        }
    }
}
```

`ObjectOutputStream` ghi một biểu diễn nhị phân có cấu trúc của đối tượng và các đối tượng liên quan. File `user.bin` không phải file JSON và không được thiết kế để con người đọc trực tiếp.

### 3.2. Đọc và khôi phục đối tượng

Đọc lại file đã ghi:

```java
import java.io.FileInputStream;
import java.io.IOException;
import java.io.ObjectInputStream;

public class ReadObjectExample {
    public static void main(String[] args)
            throws IOException, ClassNotFoundException {

        try (ObjectInputStream input =
                 new ObjectInputStream(new FileInputStream("user.bin"))) {
            User user = (User) input.readObject();

            System.out.println(user.getId());
            System.out.println(user.getName());
        }
    }
}
```

`readObject()` trả về kiểu `Object`, vì vậy chương trình thường phải ép kiểu về lớp mong muốn. Lớp tương ứng cần có trên classpath và phải tương thích với thông tin lớp được ghi trong stream.

### 3.3. Những quy tắc quan trọng của Java Serialization

**Interface `Serializable` là interface đánh dấu.** Nó không khai báo phương thức mà lớp phải tự cài đặt. Việc triển khai interface này cho biết đối tượng được phép tham gia cơ chế tuần tự hóa mặc định.

**Đồ thị đối tượng phải có thể tuần tự hóa.** Nếu một đối tượng chứa tham chiếu đến đối tượng khác, đối tượng được tham chiếu cũng phải có khả năng tuần tự hóa, trừ khi trường đó được loại khỏi quá trình mặc định hoặc được xử lý bằng cơ chế tùy chỉnh. Nếu gặp một đối tượng không thể tuần tự hóa, thao tác có thể thất bại với `NotSerializableException`.

**Trường `static` không thuộc trạng thái riêng của từng instance.** Các trường instance không bị đánh dấu `transient` là phần dữ liệu mặc định được xem xét khi ghi đối tượng. Trường `transient` được bỏ qua bởi cơ chế tuần tự hóa mặc định:

```java
public class SessionData implements Serializable {
    private static final long serialVersionUID = 1L;

    private String username;
    private transient String temporaryToken;
}
```

Sau khi khôi phục theo cơ chế mặc định, `temporaryToken` không được khôi phục từ stream; nó nhận giá trị mặc định của kiểu dữ liệu nếu không có xử lý bổ sung.

**`serialVersionUID` hỗ trợ kiểm tra tương thích phiên bản.** Đây là mã phiên bản của lớp trong cơ chế serialization. Nếu không khai báo rõ, Java có thể tính một giá trị dựa trên cấu trúc lớp. Khi cấu trúc thay đổi, giá trị được tính có thể thay đổi và việc đọc stream cũ có thể thất bại với `InvalidClassException`. Khai báo `serialVersionUID` tường minh giúp kiểm soát mã phiên bản, nhưng không tự động bảo đảm mọi thay đổi cấu trúc đều tương thích.

**Có thể tùy chỉnh quá trình ghi và đọc.** Một lớp có thể định nghĩa các phương thức đặc biệt như `writeObject` và `readObject` để kiểm soát cách trạng thái được ghi hoặc khôi phục. `Externalizable` là một cơ chế khác, trong đó lớp tự chịu trách nhiệm triển khai `writeExternal` và `readExternal`.

Một điểm nâng cao cần biết: khi khôi phục đối tượng Serializable, constructor của chính các lớp Serializable không được gọi theo cách tạo đối tượng thông thường; constructor không tham số của lớp cha đầu tiên không triển khai Serializable được gọi. Vì vậy, không nên dựa vào constructor của lớp Serializable để thiết lập các bất biến quan trọng mà không hiểu rõ quy trình khôi phục.

## 4. So sánh trực tiếp

| Tiêu chí | Jackson (ví dụ data binding JSON) | Java Object Serialization |
|---|---|---|
| Bản chất | Thư viện Java bên ngoài JDK | Cơ chế có sẵn trong JDK |
| Biểu diễn phổ biến | JSON dạng văn bản; có thể mở rộng sang định dạng khác qua module | Luồng nhị phân theo định dạng Java Serialization |
| API thường dùng | `ObjectMapper`, `JsonNode`, `JsonParser`, `JsonGenerator` | `ObjectOutputStream`, `ObjectInputStream` |
| Điều kiện của lớp | Không bắt buộc triển khai `Serializable`; cần cấu hình/thuộc tính mà Jackson có thể ánh xạ | Lớp thường triển khai `Serializable`; các đối tượng trong đồ thị cũng phải đáp ứng quy tắc |
| Khả năng đọc bằng công cụ khác | JSON có thể được đọc bởi nhiều ngôn ngữ và hệ thống | Gắn chặt với hệ sinh thái Java và định dạng riêng |
| Cấu trúc dữ liệu | Ánh xạ thuộc tính thành object, array, string, number, boolean hoặc null | Ghi đồ thị đối tượng và thông tin lớp cần thiết để khôi phục |
| Tham chiếu dùng chung và vòng tham chiếu | Không tự động giữ nguyên identity của object graph theo cách Java Serialization làm; cần cấu hình hoặc annotation phù hợp khi có vòng tham chiếu | Có cơ chế tham chiếu trong stream để giữ quan hệ dùng chung và vòng tham chiếu |
| Thay đổi mô hình | Quản lý theo hợp đồng dữ liệu JSON, annotation và cấu hình tương thích | Phụ thuộc quy tắc tương thích lớp và `serialVersionUID` |
| Trường cần bỏ qua | Điều khiển bằng annotation hoặc cấu hình Jackson | `transient` và các hook tùy chỉnh |
| Mục đích thường gặp | REST API, trao đổi dữ liệu, cấu hình, file JSON | Một số luồng trao đổi nội bộ Java hoặc trường hợp tương thích hệ thống cũ |

Bảng trên so sánh Jackson khi dùng data binding với JSON, là tình huống phổ biến nhất. Jackson còn có streaming API và các module định dạng khác; không phải mọi cách sử dụng Jackson đều phải tạo một chuỗi JSON hoàn chỉnh trong bộ nhớ.

## 5. Khác biệt về cấu trúc và khả năng tương thích

### 5.1. JSON mô tả dữ liệu; Java Serialization mô tả đồ thị đối tượng

JSON biểu diễn dữ liệu bằng các kiểu cơ bản như object, array, string, number, boolean và null. Một JSON object có các khóa và giá trị. Hệ thống nhận dữ liệu có thể ánh xạ nó vào một DTO khác với lớp Java ban đầu, miễn là hai bên thống nhất hợp đồng dữ liệu.

Ví dụ, một dịch vụ Java có thể trả về:

```json
{
  "customer_id": 42,
  "customer_name": "An"
}
```

Một ứng dụng viết bằng JavaScript, Python hoặc ngôn ngữ khác vẫn có thể đọc dữ liệu này mà không cần biết lớp Java gốc.

Java Serialization ghi thông tin để Java khôi phục các instance và quan hệ tham chiếu của chúng. Nó phù hợp với mô hình đối tượng Java cụ thể hơn là một hợp đồng dữ liệu độc lập ngôn ngữ. Ứng dụng khác ngôn ngữ không thể mặc nhiên đọc luồng này như JSON.

### 5.2. Thay đổi lớp ảnh hưởng theo cách khác nhau

Giả sử ứng dụng thêm thuộc tính `email` vào `User`.

Với Jackson, JSON mới có thể chứa thêm khóa:

```json
{
  "id": 42,
  "name": "An",
  "email": "an@example.com"
}
```

Cách ứng dụng cũ xử lý khóa mới phụ thuộc cấu hình mapper. Có thể cấu hình bỏ qua thuộc tính không biết, dùng `@JsonIgnoreProperties(ignoreUnknown = true)`, hoặc chủ động xử lý để phát hiện hợp đồng dữ liệu sai. Khi thiết kế API, cần quy định rõ cách xử lý trường được thêm, trường bị bỏ và giá trị null.

Với Java Serialization, việc đọc stream cũ phụ thuộc quy tắc tương thích của lớp Serializable và `serialVersionUID`. Nếu mã phiên bản không khớp, Java có thể từ chối khôi phục. Nếu mã phiên bản được giữ nguyên, điều đó cũng không có nghĩa mọi thay đổi đều an toàn: ứng dụng vẫn phải kiểm tra ý nghĩa của các trường mới, trường bị bỏ và trạng thái mặc định sau khi khôi phục.

Do đó, JSON thường thuận lợi hơn khi cần tiến hóa hợp đồng dữ liệu giữa các dịch vụ độc lập. Java Serialization đòi hỏi kiểm soát chặt phiên bản lớp ở hai phía.

### 5.3. Đồ thị đối tượng và vòng tham chiếu

Giả sử hai đối tượng cùng trỏ đến một đối tượng địa chỉ:

```text
userA ──┐
        ├──> address
userB ──┘
```

Java Serialization có cơ chế tham chiếu trong stream để khôi phục quan hệ dùng chung này, đồng thời có thể biểu diễn vòng tham chiếu trong đồ thị đối tượng.

JSON cơ bản chỉ mô tả cây dữ liệu. Khi Jackson đi theo các thuộc tính của object, một quan hệ vòng có thể khiến quá trình ghi lặp vô hạn hoặc phát sinh lỗi. Nếu mô hình cần biểu diễn quan hệ tham chiếu, có thể thiết kế DTO theo hướng tránh vòng lặp, hoặc dùng các tính năng như `@JsonIdentityInfo`, `@JsonManagedReference` và `@JsonBackReference` tùy cấu trúc. Cần kiểm tra JSON đầu ra để chắc chắn nó phản ánh đúng hợp đồng mà bên nhận hiểu được.

## 6. Bảo mật khi deserialization

Deserialization là ranh giới đầu vào quan trọng: dữ liệu được đọc có thể ảnh hưởng đến đối tượng và hành vi của chương trình.

### 6.1. Java Object Serialization

Không nên dùng `ObjectInputStream` để đọc dữ liệu không đáng tin cậy. Việc khôi phục một đồ thị đối tượng có thể kích hoạt hành vi trong các lớp liên quan; trong một số cấu hình và classpath, dữ liệu được chế tạo có thể dẫn đến lỗ hổng nghiêm trọng.

Nếu hệ thống bắt buộc phải dùng Java Serialization, cần giới hạn nguồn dữ liệu và cấu hình bộ lọc lớp/đồ thị bằng `ObjectInputFilter` (cơ chế lọc được bổ sung từ Java 9). Bộ lọc cần giới hạn loại lớp được phép, độ sâu đồ thị, số tham chiếu và kích thước dữ liệu theo nhu cầu thực tế.

### 6.2. Jackson

JSON dễ quan sát và thường phù hợp hơn cho giao tiếp giữa dịch vụ, nhưng không có nghĩa mọi JSON đều an toàn. Ứng dụng vẫn cần:

- Cập nhật Jackson lên phiên bản đã được vá lỗi bảo mật.
- Kiểm tra và xác thực dữ liệu đầu vào theo quy tắc nghiệp vụ.
- Tránh bật polymorphic default typing một cách rộng rãi cho dữ liệu không đáng tin cậy.
- Nếu cần hỗ trợ kiểu đa hình, giới hạn subtype được phép bằng cấu hình allowlist phù hợp.
- Đặt giới hạn hợp lý cho kích thước payload, độ sâu và tài nguyên xử lý.

Không nên xem annotation hoặc việc dùng DTO là biện pháp thay thế hoàn toàn cho xác thực đầu vào và kiểm soát bảo mật.

## 7. Khi nào nên chọn công cụ nào?

**Chọn Jackson trong các trường hợp phổ biến sau:**

- Xây dựng REST API và cần trao đổi request/response bằng JSON.
- Đọc hoặc ghi file cấu hình, dữ liệu xuất/nhập hoặc thông điệp giữa các dịch vụ.
- Muốn hợp đồng dữ liệu có thể được tiêu thụ bởi nhiều ngôn ngữ.
- Muốn kiểm soát tên trường, định dạng, trường tùy chọn và phiên bản schema theo nhu cầu ứng dụng.

**Chỉ cân nhắc Java Object Serialization khi có lý do cụ thể:**

- Hệ thống hiện hữu đã dùng định dạng này và cần duy trì khả năng tương thích.
- Hai phía đều là ứng dụng Java và kiểm soát được phiên bản lớp, classpath cũng như nguồn dữ liệu.
- Có yêu cầu nội bộ cụ thể về việc khôi phục đồ thị đối tượng Java và đã đánh giá rủi ro vận hành, bảo mật.

Đối với lưu trữ lâu dài hoặc giao tiếp giữa các hệ thống độc lập, không nên mặc định chọn Java Object Serialization chỉ vì nó có sẵn trong JDK. Một định dạng dữ liệu có hợp đồng rõ ràng như JSON thường dễ kiểm tra, tích hợp và tiến hóa hơn. Nếu cần hiệu quả hoặc kích thước nhỏ, có thể đánh giá thêm các định dạng nhị phân có schema như Protocol Buffers, Avro hoặc CBOR theo yêu cầu của hệ thống.

## 8. Những nhầm lẫn thường gặp

**"Dùng Jackson thì lớp phải implements Serializable."** Sai. Jackson ánh xạ thuộc tính của đối tượng theo quy tắc của nó; interface `Serializable` không phải điều kiện để `ObjectMapper` chuyển POJO thành JSON.

**"JSON là Java Serialization ở dạng dễ đọc."** Sai. JSON và Java Object Serialization là hai định dạng có cấu trúc và quy tắc khôi phục khác nhau. Không thể lấy file được ghi bởi `ObjectOutputStream` rồi đưa trực tiếp vào `ObjectMapper.readValue()`.

**"Serializable có nghĩa là có thể lưu đối tượng an toàn ở mọi nơi."** Sai. Interface này chỉ tham gia cơ chế tuần tự hóa của Java. Nó không bảo đảm tương thích phiên bản, an toàn khi đọc dữ liệu không tin cậy hay phù hợp cho lưu trữ lâu dài.

**"Jackson chỉ làm việc với JSON."** Chưa đầy đủ. JSON là trường hợp phổ biến, nhưng Jackson có kiến trúc streaming/data binding và các module cho những định dạng khác.

**"Hai cơ chế đều serialize object nên hiệu năng và kết quả giống nhau."** Sai. Chúng tạo biểu diễn khác nhau, có chi phí xử lý, kích thước dữ liệu, khả năng nén, khả năng tương thích và mục tiêu sử dụng khác nhau. Muốn so sánh hiệu năng cần benchmark trên dữ liệu, cấu hình và workload thực tế.

## 9. Ghi nhớ

- **Jackson** là thư viện ánh xạ dữ liệu; thường chuyển Java object thành JSON và ngược lại.
- **Java Object Serialization** là cơ chế trong JDK để ghi và khôi phục đồ thị đối tượng Java qua luồng nhị phân.
- Jackson không yêu cầu `Serializable`; Java Object Serialization mặc định yêu cầu các đối tượng trong đồ thị đáp ứng quy tắc Serializable.
- JSON phù hợp hơn cho hợp đồng dữ liệu và tích hợp đa ngôn ngữ; Java Serialization gắn chặt với lớp Java và cần quản lý tương thích phiên bản.
- Cả hai đều cần kiểm soát dữ liệu đầu vào. Đặc biệt, không deserialize Java object stream từ nguồn không đáng tin cậy.

