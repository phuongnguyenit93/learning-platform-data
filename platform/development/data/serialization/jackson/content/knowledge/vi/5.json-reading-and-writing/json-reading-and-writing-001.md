# Đọc JSON từ String, byte array, tệp và luồng đầu vào

Jackson cung cấp nhiều cách đọc JSON thông qua `ObjectMapper.readValue(...)`. Dữ liệu có thể đã nằm trong một chuỗi Java, một mảng byte, một file hoặc một `InputStream` đang nhận dữ liệu từ mạng hay nguồn khác. Các overload này đều có thể tạo cùng một kiểu đối tượng đích, nhưng khác nhau về cách dữ liệu được đưa vào bộ phân tích, cách xử lý encoding, chi phí bộ nhớ và quyền sở hữu tài nguyên.

Chọn đúng nguồn đầu vào giúp tránh tạo bản sao dữ liệu không cần thiết, xử lý file lớn tốt hơn và quản lý việc đóng stream rõ ràng.

## 1. Chuẩn bị ObjectMapper

Ví dụ trong bài sử dụng lớp `User` làm kiểu đích:

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

Một JSON tương ứng:

```json
{
  "id": 42,
  "name": "An"
}
```

Tạo mapper:

```java
import com.fasterxml.jackson.databind.ObjectMapper;

ObjectMapper mapper = new ObjectMapper();
```

Trong ứng dụng thực tế, nên cấu hình mapper và đăng ký các module cần thiết ngay khi khởi tạo, sau đó tái sử dụng mapper. Không cần tạo một `ObjectMapper` mới cho mỗi request. Sau khi đã dùng mapper trong nhiều luồng, tránh thay đổi cấu hình toàn cục của nó một cách tùy tiện; nếu mỗi luồng cần cách đọc khác nhau, có thể tạo `ObjectReader` với cấu hình riêng.

## 2. Đọc JSON từ String

Khi JSON đã là một chuỗi Java, dùng overload nhận `String`:

```java
String json = """
    {
      "id": 42,
      "name": "An"
    }
    """;

User user = mapper.readValue(json, User.class);

System.out.println(user.getId());
System.out.println(user.getName());
```

`readValue(String, Class<T>)` nhận nội dung JSON dưới dạng ký tự và ánh xạ nó vào kiểu đích. Cách này tiện khi:

- JSON được tạo trong chương trình.
- Test cần truyền một payload ngắn trực tiếp.
- Ứng dụng đã nhận JSON dưới dạng chuỗi từ một API hoặc tầng xử lý phía trước.
- Nội dung cần được log hoặc kiểm tra như văn bản trước khi ánh xạ.

### 2.1. String đã là văn bản, không phải byte

Một `String` Java chứa chuỗi ký tự. Nếu dữ liệu ban đầu đến từ byte của HTTP request, file hoặc message broker, một tầng trước đó đã phải giải mã byte thành ký tự.

Khi tự chuyển byte thành String, hãy chỉ rõ charset:

```java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

byte[] bytes = Files.readAllBytes(Path.of("user.json"));
String json = new String(bytes, StandardCharsets.UTF_8);

User user = mapper.readValue(json, User.class);
```

Không nên viết `new String(bytes)` mà bỏ qua charset, vì chương trình sẽ dùng charset mặc định của môi trường. Cùng một dãy byte có thể bị diễn giải thành văn bản khác nhau trên các máy có cấu hình khác nhau.

Nếu đã có byte array, thường nên truyền trực tiếp byte array cho Jackson thay vì tạo thêm một String trung gian.

## 3. Đọc JSON từ byte array

Dùng overload nhận `byte[]` khi dữ liệu đã được đọc vào bộ nhớ dưới dạng byte:

```java
import java.nio.charset.StandardCharsets;

byte[] jsonBytes = """
    {
      "id": 42,
      "name": "An"
    }
    """.getBytes(StandardCharsets.UTF_8);

User user = mapper.readValue(jsonBytes, User.class);
```

Byte array phù hợp khi:

- Một HTTP client hoặc message consumer đã cung cấp payload dạng byte.
- Ứng dụng cần giữ dữ liệu thô để tính checksum, lưu trữ hoặc xử lý thêm.
- Payload có kích thước vừa phải và đã nằm trong bộ nhớ.

### 3.1. Jackson xử lý encoding của byte như thế nào?

Khi nhận byte array hoặc một nguồn byte như `InputStream`, Jackson có thể nhận diện encoding Unicode của JSON từ BOM hoặc mẫu byte ban đầu. Các encoding được hỗ trợ trong parser bao gồm UTF-8, UTF-16 và UTF-32 với thứ tự byte tương ứng.

Tuy nhiên, đối với JSON trao đổi giữa các hệ thống, **UTF-8 là lựa chọn nên dùng**. Đây là encoding được JSON interoperability yêu cầu cho dữ liệu trao đổi giữa các hệ thống. Vì vậy, khi tạo byte array:

```java
byte[] bytes = json.getBytes(StandardCharsets.UTF_8);
```

Khi ghi file hoặc gửi request, cũng nên thống nhất UTF-8 thay vì dựa vào charset mặc định của máy.

### 3.2. Không cần chuyển byte array thành String trước khi đọc

Hai cách sau có thể tạo cùng kết quả:

```java
User first = mapper.readValue(jsonBytes, User.class);

String json = new String(jsonBytes, StandardCharsets.UTF_8);
User second = mapper.readValue(json, User.class);
```

Cách thứ nhất tránh bước giải mã byte thành String trung gian. Với payload lớn, bước chuyển đổi này có thể làm tăng bộ nhớ cần dùng và tạo thêm bản sao dữ liệu.

## 4. Đọc JSON trực tiếp từ File

Nếu dữ liệu nằm trong file, có thể truyền trực tiếp một đối tượng `File`:

```java
import java.io.File;
import java.io.IOException;

File file = new File("data/user.json");

User user = mapper.readValue(file, User.class);
```

Hoặc dùng `Path` để biểu diễn đường dẫn và chuyển sang `InputStream`:

```java
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;

Path path = Path.of("data/user.json");

try (InputStream input = Files.newInputStream(path)) {
    User user = mapper.readValue(input, User.class);
    System.out.println(user.getName());
}
```

Overload nhận `File` giúp mã nguồn ngắn gọn. Cách dùng `Path` và `InputStream` linh hoạt hơn khi ứng dụng cần mở file theo một quy trình riêng, kiểm tra quyền truy cập hoặc phối hợp với các API NIO.

Khi đọc file dưới dạng byte, Jackson thực hiện việc phân tích encoding trên nguồn byte. Không cần tự đọc toàn bộ file thành String trước khi gọi `readValue`.

## 5. Đọc JSON từ InputStream

`InputStream` đại diện cho nguồn byte. Nó có thể đến từ file, HTTP response, socket, tài nguyên trong classpath, bộ nhớ hoặc một dịch vụ lưu trữ.

Ví dụ đọc từ một stream:

```java
import java.io.ByteArrayInputStream;
import java.nio.charset.StandardCharsets;

String json = """
    {
      "id": 42,
      "name": "An"
    }
    """;

byte[] bytes = json.getBytes(StandardCharsets.UTF_8);

try (ByteArrayInputStream input = new ByteArrayInputStream(bytes)) {
    User user = mapper.readValue(input, User.class);
    System.out.println(user.getName());
}
```

Trong ứng dụng thực tế, nguồn thường là một file hoặc response body:

```java
try (InputStream input = httpResponse.body()) {
    User user = mapper.readValue(input, User.class);
}
```

Ví dụ trên minh họa việc đọc body từ một API; kiểu cụ thể của `httpResponse` phụ thuộc HTTP client mà ứng dụng sử dụng.

### 5.1. Vì sao dùng InputStream?

So với việc đọc toàn bộ file thành byte array hoặc String trước, `InputStream` cho phép Jackson nhận dữ liệu từ nguồn byte trực tiếp. Ứng dụng không cần tạo thêm một bản sao đầy đủ của nội dung chỉ để bắt đầu parse.

Tuy nhiên, cần phân biệt hai khái niệm:

- **Đọc nguồn theo luồng:** parser lấy byte từ InputStream khi cần.
- **Data binding thành object:** Jackson vẫn phải tạo đối tượng Java đích và các đối tượng con theo dữ liệu đã ánh xạ.

Vì vậy, truyền một file lớn bằng InputStream không có nghĩa toàn bộ quá trình data binding luôn dùng bộ nhớ hằng số. Nếu JSON chứa một mảng hàng triệu phần tử và ứng dụng ánh xạ cả mảng vào `List<User>`, danh sách cùng các đối tượng vẫn chiếm bộ nhớ tương ứng.

Khi cần xử lý dữ liệu rất lớn mà không giữ toàn bộ kết quả trong bộ nhớ, hãy cân nhắc Jackson Core streaming API để đọc từng token và xử lý từng bản ghi.

### 5.2. Quản lý vòng đời InputStream

Khi đọc bằng `ObjectMapper.readValue`, Jackson tạo parser để đọc nguồn. Parser được đóng sau thao tác đọc; việc parser có đóng nguồn bên dưới hay không phụ thuộc cấu hình `AUTO_CLOSE_SOURCE` của `JsonFactory`. Tính năng này được bật mặc định trong cấu hình thông thường, nên InputStream truyền vào thường được đóng cùng parser.

Cách viết rõ ràng về quyền sở hữu tài nguyên là dùng try-with-resources:

```java
try (InputStream input = Files.newInputStream(path)) {
    User user = mapper.readValue(input, User.class);
}
```

Cấu trúc này thể hiện rằng đoạn code đang sở hữu stream và bảo đảm stream được đóng khi thoát khỏi block, kể cả khi parse phát sinh exception. Việc đóng lần nữa sau khi parser đã đóng thường an toàn với các stream chuẩn.

Nếu API của ứng dụng truyền vào một stream mà bên gọi cần tiếp tục sử dụng sau khi đọc, cần thống nhất rõ quyền sở hữu. Có thể cấu hình `StreamReadFeature.AUTO_CLOSE_SOURCE` trên `JsonFactory` để parser không tự đóng nguồn, hoặc dùng một wrapper ngăn thao tác close lan xuống nguồn gốc. Chỉ tắt auto-close khi hợp đồng giữa bên gọi và bên đọc đã quy định ai chịu trách nhiệm đóng stream; nếu không, rất dễ rò rỉ tài nguyên.

## 6. Đọc JSON từ Reader

`Reader` cung cấp ký tự đã được giải mã, khác với `InputStream` cung cấp byte. Dùng overload nhận `Reader` khi ứng dụng đã có nguồn ký tự hoặc muốn tự kiểm soát charset ở bước mở file:

```java
import java.io.Reader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

Path path = Path.of("data/user.json");

try (Reader reader = Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
    User user = mapper.readValue(reader, User.class);
}
```

Điểm khác biệt quan trọng:

| Nguồn | Dữ liệu Jackson nhận | Encoding do ai xử lý? |
|---|---|---|
| `String` | Ký tự Java | Đã được giải mã trước khi gọi Jackson |
| `Reader` | Ký tự Java | Reader quyết định charset khi đọc byte |
| `byte[]` | Byte | Jackson nhận diện encoding từ dữ liệu |
| `InputStream` | Byte | Jackson nhận diện encoding từ dữ liệu |
| `File` | Byte từ file | Parser của Jackson xử lý encoding |

Nếu dùng `Reader`, Jackson không thể suy ra encoding gốc của file vì Reader đã chuyển byte thành ký tự. Do đó, hãy chọn charset rõ ràng khi tạo Reader, ví dụ `StandardCharsets.UTF_8`.

## 7. Đọc kiểu generic và collection từ mọi nguồn

Một điểm dễ gặp khi đọc JSON là kiểu đích có generic:

```json
[
  {"id": 1, "name": "An"},
  {"id": 2, "name": "Bình"}
]
```

Nếu gọi:

```java
List<User> users = mapper.readValue(json, List.class);
```

thì Java type erasure khiến Jackson chỉ biết kiểu đích là `List`, không biết phần tử cần là `User`. Các phần tử thường được tạo thành kiểu map tổng quát thay vì `User`.

Dùng `TypeReference` để giữ thông tin kiểu generic:

```java
import com.fasterxml.jackson.core.type.TypeReference;
import java.util.List;

List<User> users = mapper.readValue(
    json,
    new TypeReference<List<User>>() {}
);
```

Cách này cũng dùng được với byte array hoặc InputStream:

```java
List<User> usersFromBytes = mapper.readValue(
    jsonBytes,
    new TypeReference<List<User>>() {}
);

try (InputStream input = Files.newInputStream(path)) {
    List<User> usersFromFile = mapper.readValue(
        input,
        new TypeReference<List<User>>() {}
    );
}
```

Nếu kiểu đích được xác định động tại runtime, có thể tạo `JavaType`:

```java
import com.fasterxml.jackson.databind.JavaType;

JavaType userListType = mapper.getTypeFactory()
    .constructCollectionType(List.class, User.class);

List<User> users = mapper.readValue(json, userListType);
```

Với map có kiểu khóa và giá trị cụ thể:

```java
JavaType userMapType = mapper.getTypeFactory()
    .constructMapType(Map.class, String.class, User.class);

Map<String, User> usersByCode = mapper.readValue(json, userMapType);
```

Có thể kết hợp các kiểu lồng nhau bằng `TypeReference` hoặc `JavaType`, ví dụ `Map<String, List<User>>`. Điều quan trọng là cung cấp đầy đủ kiểu đích để Jackson tạo đúng cấu trúc đối tượng.

## 8. Đọc vào JsonNode khi chưa muốn xác định lớp Java

Không phải lúc nào ứng dụng cũng biết trước cấu trúc JSON. Khi cần kiểm tra một vài trường, xử lý dữ liệu không đồng nhất hoặc lựa chọn kiểu đích sau khi đọc metadata, có thể dùng mô hình cây `JsonNode`:

```java
import com.fasterxml.jackson.databind.JsonNode;

JsonNode root = mapper.readTree(json);

long id = root.path("id").asLong();
String name = root.path("name").asText();

System.out.println(id + " - " + name);
```

`path("field")` trả về node rỗng khi trường không tồn tại, giúp tránh lỗi null khi truy cập theo chuỗi. Tuy vậy, `asLong()` hoặc `asText()` có thể trả về giá trị mặc định nếu node không có kiểu mong đợi; khi dữ liệu cần được xác thực chặt, hãy kiểm tra `isNumber()`, `isTextual()`, `isMissingNode()` hoặc `isNull()` trước khi chuyển đổi.

Có thể đọc tree từ byte array hoặc stream theo cùng ý tưởng:

```java
JsonNode fromBytes = mapper.readTree(jsonBytes);

try (InputStream input = Files.newInputStream(path)) {
    JsonNode fromFile = mapper.readTree(input);
}
```

Tree model linh hoạt nhưng giữ toàn bộ cây JSON trong bộ nhớ. Với tài liệu rất lớn, hãy cân nhắc streaming parser thay vì dựng một `JsonNode` cho toàn bộ nội dung.

## 9. Chọn overload theo nguồn dữ liệu

| Nguồn hiện có | Cách gọi | Khi nên dùng |
|---|---|---|
| Chuỗi JSON | `readValue(json, User.class)` | Payload đã ở dạng String, thường dùng trong test hoặc dữ liệu nhỏ |
| Mảng byte | `readValue(bytes, User.class)` | HTTP/message payload đã có sẵn dưới dạng byte |
| File | `readValue(file, User.class)` | Đọc file trực tiếp bằng API tiện dụng |
| InputStream | `readValue(input, User.class)` | Đọc từ mạng, file, socket hoặc nguồn byte khác |
| Reader | `readValue(reader, User.class)` | Đã có nguồn ký tự và charset được kiểm soát |
| JsonParser | `readValue(parser, User.class)` | Đang tự điều khiển parser/token hoặc đọc một phần của luồng |
| Bất kỳ nguồn phù hợp nào | `readTree(source)` | Muốn đọc JSON thành cây thay vì bind vào lớp cụ thể |

Một quy tắc thực dụng:

- Payload nhỏ đã có sẵn dưới dạng văn bản: dùng String.
- Payload đã có dưới dạng byte: truyền byte array trực tiếp.
- Đọc file thông thường: dùng File hoặc InputStream.
- Đọc từ mạng hoặc nguồn liên tục: dùng InputStream.
- Cần kiểm soát charset trước khi parse: dùng Reader.
- JSON có cấu trúc động: dùng JsonNode.
- Dữ liệu lớn cần xử lý từng phần: dùng streaming API.

## 10. Lỗi thường gặp khi đọc JSON

### 10.1. JSON sai cú pháp

Ví dụ JSON có dấu phẩy thừa:

```json
{
  "id": 42,
  "name": "An",
}
```

JSON chuẩn không cho phép dấu phẩy sau phần tử cuối. Jackson có thể phát sinh `JsonParseException`, thường kèm thông tin vị trí như dòng và cột để hỗ trợ tìm lỗi.

### 10.2. JSON hợp lệ nhưng không ánh xạ được vào kiểu đích

Ví dụ trường `id` chứa chuỗi không thể chuyển thành số theo cấu hình:

```json
{
  "id": "not-a-number",
  "name": "An"
}
```

Đây là vấn đề data binding và có thể dẫn đến `JsonMappingException` hoặc một subtype tương ứng. JSON có thể đúng cú pháp nhưng không phù hợp với kiểu Java mong đợi.

### 10.3. Sai kiểu generic

Đọc một JSON array bằng `List.class` làm mất kiểu phần tử. Dùng `TypeReference<List<User>>` hoặc `JavaType` để cung cấp kiểu đầy đủ.

### 10.4. Dùng charset mặc định

Chuyển byte thành String bằng `new String(bytes)` có thể gây lỗi ký tự trên môi trường khác. Dùng `StandardCharsets.UTF_8` hoặc để Jackson đọc trực tiếp byte.

### 10.5. Đọc nguồn quá lớn vào bộ nhớ

`Files.readAllBytes` và `Files.readString` tải toàn bộ nội dung vào bộ nhớ trước khi parse. Nếu file lớn, ưu tiên File/InputStream. Nếu cả cấu trúc kết quả cũng rất lớn, hãy xử lý theo token thay vì bind toàn bộ thành một collection.

### 10.6. Quên quản lý tài nguyên

Không đóng stream có thể làm rò rỉ file descriptor hoặc kết nối. Dùng try-with-resources khi đoạn code mở và sở hữu stream; nếu stream do tầng khác quản lý, thống nhất rõ ai chịu trách nhiệm đóng và cấu hình auto-close phù hợp.

### 10.7. Nuốt exception rồi trả về null

Không nên bắt mọi exception rồi âm thầm trả về `null`. Điều đó biến lỗi cú pháp, lỗi IO và lỗi cấu trúc thành trạng thái thiếu dữ liệu khó chẩn đoán. Hãy xử lý exception ở đúng tầng, bổ sung ngữ cảnh nguồn dữ liệu và giữ nguyên nguyên nhân gốc.

## 11. Lưu ý khi đọc JSON không đáng tin cậy

JSON là định dạng trao đổi phổ biến nhưng vẫn là đầu vào bên ngoài. Ứng dụng cần:

- Giới hạn kích thước request/file và thời gian xử lý theo yêu cầu hệ thống.
- Xác thực dữ liệu sau khi bind, đặc biệt với trường bắt buộc, giới hạn số và dữ liệu nghiệp vụ.
- Không bật polymorphic default typing một cách rộng rãi cho dữ liệu không đáng tin cậy.
- Nếu hỗ trợ kiểu đa hình, giới hạn subtype được phép bằng allowlist.
- Cập nhật Jackson lên phiên bản được vá lỗi bảo mật phù hợp với major line của framework.

Việc parse thành công chỉ chứng minh dữ liệu có thể được đọc theo cấu hình hiện tại; nó không chứng minh dữ liệu hợp lệ về nghiệp vụ hoặc an toàn để sử dụng.

## 12. Ghi nhớ

- `readValue(String, ...)` dùng khi JSON đã ở dạng ký tự; `readValue(byte[], ...)` dùng khi dữ liệu đã có ở dạng byte.
- `readValue(File, ...)` và `readValue(InputStream, ...)` cho phép đọc nguồn byte mà không phải tạo trước một chuỗi hoặc byte array đầy đủ trong mã ứng dụng.
- `Reader` cung cấp ký tự đã giải mã; hãy chỉ rõ charset khi mở nguồn, thường là UTF-8.
- Dùng `TypeReference` hoặc `JavaType` để đọc collection/map có generic.
- Dùng `readTree` khi cần kiểm tra JSON linh hoạt; dùng Core streaming khi phải xử lý dữ liệu rất lớn theo từng phần.
- Quản lý rõ vòng đời stream, phân biệt lỗi cú pháp với lỗi ánh xạ và luôn xác thực dữ liệu sau khi đọc.
