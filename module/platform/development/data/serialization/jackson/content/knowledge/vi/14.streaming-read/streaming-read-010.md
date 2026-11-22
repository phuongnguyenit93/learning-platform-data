# Theo dõi vị trí lỗi trong luồng đầu vào

Khi đọc JSON từ file, HTTP request hoặc một nguồn dữ liệu lớn, Jackson thường làm việc trực tiếp với InputStream hoặc Reader. Nếu dữ liệu bị sai cú pháp, không đúng kiểu hoặc bị cắt giữa chừng, việc biết lỗi xảy ra ở đâu giúp tìm nhanh vị trí cần kiểm tra.

Jackson cung cấp thông tin vị trí thông qua JsonLocation. Khi lỗi xảy ra trong quá trình parse hoặc data binding, các exception của Jackson có thể mang theo vị trí này. Với lỗi ánh xạ vào object lồng nhau, JsonMappingException còn cung cấp đường dẫn property để biết lỗi thuộc trường nào.

Cần phân biệt ba loại thông tin:

- **Vị trí trong luồng**: dòng, cột, byte offset hoặc character offset.
- **Đường dẫn trong cấu trúc JSON/Java**: property và index dẫn đến giá trị gây lỗi.
- **Nguyên nhân lỗi**: JSON sai cú pháp, kiểu dữ liệu không phù hợp, thiếu creator hoặc lỗi I/O từ nguồn.

Các thông tin này bổ sung cho nhau. Vị trí cho biết lỗi nằm gần đâu trong dữ liệu đầu vào; path cho biết lỗi liên quan đến thuộc tính nào; nguyên nhân cho biết cần sửa cú pháp, dữ liệu, mô hình Java hay nguồn I/O.

## 1. Jackson đọc dữ liệu theo luồng như thế nào?

Jackson Core cung cấp JsonParser để đọc JSON theo từng token. Khi đọc từ InputStream, parser nhận byte; khi đọc từ Reader, parser nhận ký tự đã được decode.

Ví dụ JSON:

~~~json
{
  "orderId": "ORD-100",
  "customer": {
    "name": "An",
    "age": 25
  },
  "items": [
    {"sku": "KB-01", "quantity": 2},
    {"sku": "MS-02", "quantity": 1}
  ]
}
~~~

Parser đọc các token như:
- Bắt đầu object.
- Tên field orderId.
- Giá trị string ORD-100.
- Tên field customer.
- Bắt đầu object lồng nhau.
- Tên field name, giá trị string.
- Tên field age, giá trị number.
- Bắt đầu array items.
- Các object và giá trị bên trong array.
- Kết thúc các cấu trúc.

Jackson Databind dùng parser cùng kiểu Java đích để tạo object. Nếu token không đúng cú pháp hoặc không thể ánh xạ vào kiểu đích, exception có thể chứa thông tin vị trí.

~~~mermaid
flowchart TD
    A[InputStream hoặc Reader] --> B[JsonParser]
    B --> C[Đọc token]
    C --> D{Token hợp lệ?}
    D -->|Không| E[JsonParseException / vị trí parse]
    D -->|Có| F[Jackson Databind]
    F --> G{Ánh xạ được kiểu Java?}
    G -->|Không| H[JsonMappingException / path và location]
    G -->|Có| I[Java object]
~~~

Khi làm việc với stream, parser có thể đã đọc một phần dữ liệu trước khi phát hiện lỗi. Vì vậy, cần sử dụng location gắn với exception hoặc location của token, thay vì chỉ nhìn vị trí hiện tại của stream bên ngoài.

## 2. JsonLocation chứa những thông tin gì?

JsonLocation là kiểu dữ liệu của Jackson Core mô tả vị trí trong nguồn JSON.

Các thông tin thường dùng:

| Method | Ý nghĩa |
|---|---|
| getLineNr() | Số dòng tại vị trí |
| getColumnNr() | Số cột tại vị trí |
| getByteOffset() | Offset byte nếu parser có thông tin |
| getCharOffset() | Offset ký tự nếu parser có thông tin |
| getSourceRef() | Tham chiếu nguồn đầu vào, nếu có |

Dòng và cột thường bắt đầu từ 1. Offset là vị trí tính từ đầu nguồn; nếu parser không thể cung cấp một loại offset, giá trị có thể là -1.

Ví dụ thông tin log:

~~~text
JSON error at line 8, column 17, byte offset 143
~~~

Thông tin này giúp mở file hoặc payload tại khu vực gần lỗi.

### 2.1. Byte offset và character offset khác nhau

Byte và ký tự không phải một đơn vị giống nhau.

Ví dụ string tiếng Việt:

~~~text
Xin chào
~~~

Khi mã hóa UTF-8, các ký tự có dấu có thể chiếm nhiều byte. Vì vậy, byte offset có thể khác character offset.

- Byte offset đếm vị trí trong dữ liệu byte đầu vào.
- Character offset đếm vị trí theo ký tự mà parser nhận diện.
- Với InputStream, byte offset thường hữu ích nếu cần định vị trong file hoặc payload byte.
- Với Reader, parser nhận ký tự đã decode nên character offset thường phù hợp hơn.
- Giá trị -1 biểu thị loại offset đó không có sẵn.

Không nên lấy byte offset rồi dùng làm chỉ số substring của Java String. Hai đơn vị này có thể khác nhau, đặc biệt với UTF-8 và Unicode.

### 2.2. Vị trí dòng/cột và offset có mục đích khác nhau

Dòng/cột thuận tiện cho con người đọc log và mở editor. Offset thuận tiện cho công cụ xử lý file hoặc payload nhị phân.

Nếu đầu vào có nhiều dòng, line/column giúp định vị nhanh. Nếu đầu vào là một dòng JSON rất dài, offset có thể hữu ích hơn.

Không phải nguồn đầu vào nào cũng hỗ trợ đầy đủ cả hai loại thông tin. Hãy kiểm tra giá trị trả về trước khi hiển thị.

## 3. Lấy vị trí từ JsonProcessingException

Các exception xử lý JSON của Jackson thường kế thừa JsonProcessingException. Có thể lấy vị trí thông qua getLocation().

Ví dụ đọc JSON từ InputStream:

~~~java
import com.fasterxml.jackson.core.JsonLocation;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;

import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;

public class JsonLocationExample {

    public static void main(String[] args) throws Exception {
        ObjectMapper mapper = new ObjectMapper();
        Path path = Path.of("data", "order.json");

        try (InputStream input = Files.newInputStream(path)) {
            Order order = mapper.readValue(input, Order.class);
            System.out.println(order.getOrderId());
        } catch (JsonProcessingException e) {
            JsonLocation location = e.getLocation();

            System.err.println("Cannot process JSON: " + e.getOriginalMessage());

            if (location != null) {
                System.err.println("Line: " + location.getLineNr());
                System.err.println("Column: " + location.getColumnNr());
                System.err.println("Byte offset: " + location.getByteOffset());
                System.err.println("Character offset: " + location.getCharOffset());
            }

            throw e;
        }
    }
}
~~~

getOriginalMessage() trả về phần thông điệp gốc của exception. getLocation() có thể trả về null tùy loại exception hoặc ngữ cảnh lỗi, vì vậy nên kiểm tra trước khi đọc line, column và offset.

Không nên giả định mọi IOException đều là JsonProcessingException. Nếu file không tồn tại, quyền đọc bị từ chối hoặc kết nối bị ngắt, lỗi có thể là IOException thông thường và không có JsonLocation.

### 3.1. Phân biệt parse exception và mapping exception

Hai nhóm lỗi thường gặp:

- JsonParseException: parser không thể đọc cấu trúc JSON theo cú pháp hiện hành.
- JsonMappingException: JSON đã được parse đến mức cần thiết nhưng Jackson không thể ánh xạ dữ liệu vào kiểu Java đích hoặc gặp vấn đề trong quá trình ánh xạ.

Ví dụ JSON sai cú pháp:

~~~json
{
  "name": "An",
  "age": 25,
}
~~~

Dấu phẩy cuối object không hợp lệ theo JSON chuẩn. Lỗi xuất hiện trong parser.

Ví dụ JSON đúng cú pháp nhưng sai kiểu:

~~~json
{
  "name": "An",
  "age": {
    "value": 25
  }
}
~~~

Nếu field age trong Java là int, JSON object không thể ánh xạ thành int theo quy tắc thông thường. Đây là lỗi mapping.

Có thể phân loại khi bắt exception:

~~~java
try {
    Customer customer = mapper.readValue(input, Customer.class);
} catch (JsonParseException e) {
    // Lỗi cú pháp hoặc cấu trúc JSON ở tầng parser.
} catch (JsonMappingException e) {
    // Lỗi ánh xạ JSON vào kiểu Java.
} catch (JsonProcessingException e) {
    // Lỗi xử lý JSON khác.
}
~~~

Trong ví dụ thực tế, JsonParseException và JsonMappingException đều là nhánh của JsonProcessingException. Có thể bắt riêng hai nhóm trước để xử lý khác nhau, sau đó mới bắt lớp cha.

## 4. Lấy đường dẫn property từ JsonMappingException

Vị trí dòng/cột cho biết nơi lỗi xuất hiện trong luồng. Với object lồng nhau, cần biết property nào trong Java đang được ánh xạ.

JsonMappingException cung cấp path information:

- getPath(): danh sách các thành phần đường dẫn.
- getPathReference(): biểu diễn đường dẫn dạng chuỗi để log.
- getMessage(): thông điệp lỗi, thường có thêm thông tin path/location tùy exception.

Ví dụ kiểu Java:

~~~java
public class Order {
    private String orderId;
    private Customer customer;

    // Constructor, getter và setter.
}

public class Customer {
    private String name;
    private int age;

    // Constructor, getter và setter.
}
~~~

JSON đầu vào:

~~~json
{
  "orderId": "ORD-100",
  "customer": {
    "name": "An",
    "age": "not-a-number"
  }
}
~~~

Field age yêu cầu int nhưng JSON gửi string không chuyển đổi được. Exception có thể chứa path tương ứng với customer rồi đến age.

~~~java
try {
    Order order = mapper.readValue(json, Order.class);
} catch (JsonMappingException e) {
    System.err.println("Mapping path: " + e.getPathReference());
    System.err.println("Reason: " + e.getOriginalMessage());

    JsonLocation location = e.getLocation();
    if (location != null) {
        System.err.println(
                "At line " + location.getLineNr()
                        + ", column " + location.getColumnNr()
        );
    }
}
~~~

Path reference thường có dạng mô tả object/property hoặc index. Không nên phụ thuộc chính xác vào format chuỗi đó để làm logic nghiệp vụ; nó chủ yếu phục vụ chẩn đoán.

### 4.1. Path có thể chứa index của array

Ví dụ JSON:

~~~json
{
  "orders": [
    {"quantity": 2},
    {"quantity": "many"}
  ]
}
~~~

Nếu quantity là int, lỗi ở phần tử thứ hai có thể có path bao gồm:
- Property orders.
- Index 1.
- Property quantity.

Path cho biết cấu trúc lồng nhau gây lỗi. Location cho biết vị trí trong nguồn văn bản. Hai thông tin bổ sung nhau khi log.

### 4.2. Đọc từng phần tử path

Nếu cần tạo log có cấu trúc thay vì chỉ in chuỗi:

~~~java
for (JsonMappingException.Reference reference : e.getPath()) {
    if (reference.getFieldName() != null) {
        System.err.println("Field: " + reference.getFieldName());
    } else if (reference.getIndex() >= 0) {
        System.err.println("Index: " + reference.getIndex());
    }
}
~~~

Một reference có thể đại diện cho field name hoặc array index. Không phải mọi reference đều có cả hai. Đối tượng nguồn cũng có thể có sẵn nhưng không cần thiết cho log thông thường.

## 5. Theo dõi vị trí token bằng JsonParser

Khi dùng Streaming API trực tiếp, có thể lấy vị trí token hiện tại hoặc vị trí parser đang đọc.

Trong Jackson 2.13 trở lên, các method được khuyến nghị là:
- currentTokenLocation(): vị trí bắt đầu token hiện tại.
- currentLocation(): vị trí parser hiện đang đọc đến.

Ở các phiên bản cũ hơn, có thể gặp getTokenLocation() và getCurrentLocation(); các method getter này được thay thế dần bởi tên không có tiền tố get trong API mới.

Ví dụ:

~~~java
try (JsonParser parser = mapper.getFactory().createParser(input)) {
    while (parser.nextToken() != null) {
        JsonToken token = parser.currentToken();

        JsonLocation tokenLocation = parser.currentTokenLocation();
        JsonLocation currentLocation = parser.currentLocation();

        System.out.printf(
                "Token=%s, starts at line=%d column=%d%n",
                token,
                tokenLocation.getLineNr(),
                tokenLocation.getColumnNr()
        );
    }
}
~~~

Sự khác nhau:

| API | Thông tin |
|---|---|
| currentTokenLocation() | Vị trí bắt đầu token đang được parser chọn |
| currentLocation() | Vị trí hiện tại của parser sau khi đọc/tiến hành xử lý token |
| JsonProcessingException.getLocation() | Vị trí gắn với lỗi được ném ra |

Khi muốn ghi log vị trí của một value, hãy lấy currentTokenLocation() ngay sau khi parser chuyển tới token đó. Nếu đợi đến khi đã đọc nhiều token tiếp theo, currentLocation() sẽ trỏ tới vị trí mới hơn.

### 5.1. Ví dụ log từng token

~~~java
JsonFactory factory = mapper.getFactory();

try (JsonParser parser = factory.createParser(input)) {
    JsonToken token;

    while ((token = parser.nextToken()) != null) {
        JsonLocation location = parser.currentTokenLocation();

        System.out.printf(
                "%s at line %d, column %d%n",
                token,
                location.getLineNr(),
                location.getColumnNr()
        );

        if (token == JsonToken.FIELD_NAME) {
            System.out.println("Field: " + parser.currentName());
        } else if (token == JsonToken.VALUE_STRING) {
            System.out.println("Text: " + parser.getText());
        } else if (token == JsonToken.VALUE_NUMBER_INT) {
            System.out.println("Integer: " + parser.getLongValue());
        }
    }
}
~~~

Cách này hữu ích khi xử lý file lớn, message stream hoặc khi muốn tự xây dựng pipeline đọc dữ liệu. Không cần tạo toàn bộ JsonNode tree nếu chỉ cần xử lý tuần tự từng record.

## 6. Theo dõi lỗi khi đọc từ InputStream

Khi parser nhận InputStream, nó đọc byte và giải mã JSON theo encoding được xác định. JSON trao đổi qua mạng thông thường nên dùng UTF-8.

Ví dụ:

~~~java
Path path = Path.of("data", "orders.json");

try (InputStream input = Files.newInputStream(path);
     JsonParser parser = mapper.getFactory().createParser(input)) {

    while (parser.nextToken() != null) {
        // Xử lý token theo nhu cầu.
    }

} catch (JsonProcessingException e) {
    JsonLocation location = e.getLocation();

    if (location != null) {
        System.err.printf(
                "JSON error at line %d, column %d, byte offset %d%n",
                location.getLineNr(),
                location.getColumnNr(),
                location.getByteOffset()
        );
    }

    throw e;
}
~~~

Khi đọc InputStream:
- Byte offset thường hữu ích để định vị trong file hoặc payload byte.
- Character offset có thể được cung cấp tùy parser và nguồn.
- UTF-8 có ký tự chiếm nhiều byte nên byte offset không nhất thiết bằng character offset.
- Nếu nguồn là stream mạng, offset tính từ đầu phần dữ liệu mà parser nhận, không phải vị trí toàn bộ kết nối hoặc toàn bộ HTTP message nếu có framing khác.

Nếu stream được nén hoặc đã qua một lớp giải mã, offset thường phản ánh dữ liệu mà parser thực sự nhận. Nó không nhất thiết tương ứng offset trong file nén ban đầu.

## 7. Theo dõi lỗi khi đọc từ Reader

Reader cung cấp character đã được decode. Khi mở Reader từ file, nên chỉ định charset rõ ràng:

~~~java
Path path = Path.of("data", "orders.json");

try (Reader reader = Files.newBufferedReader(
        path,
        StandardCharsets.UTF_8
)) {
    Order order = mapper.readValue(reader, Order.class);
}
~~~

Khi cần báo vị trí:

~~~java
try (Reader reader = Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
    Order order = mapper.readValue(reader, Order.class);
} catch (JsonProcessingException e) {
    JsonLocation location = e.getLocation();

    if (location != null) {
        System.err.printf(
                "JSON error at line %d, column %d, character offset %d%n",
                location.getLineNr(),
                location.getColumnNr(),
                location.getCharOffset()
        );
    }

    throw e;
}
~~~

Vì Reader đã thực hiện bước decode byte thành ký tự, byte offset có thể không khả dụng. Nếu cần byte offset chính xác để đối chiếu với file, cân nhắc đọc trực tiếp InputStream và để Jackson xử lý byte stream.

Không dùng charset mặc định của hệ điều hành cho JSON file nếu file được trao đổi giữa nhiều môi trường. Dùng UTF-8 tường minh giúp kết quả nhất quán.

## 8. Vị trí lỗi không phải lúc nào cũng là ký tự gây lỗi chính xác

Khi parser phát hiện lỗi, vị trí báo cáo thường chỉ ra vị trí hiện tại hoặc khu vực token nơi lỗi được nhận diện. Trong một số tình huống, lỗi chỉ được phát hiện sau khi parser đọc thêm ký tự.

Ví dụ:
- Thiếu dấu đóng ngoặc: parser chỉ biết lỗi khi gặp EOF.
- String chưa đóng: lỗi được phát hiện khi đến cuối nguồn.
- Giá trị số sai định dạng: parser có thể đọc một phần token trước khi báo lỗi.
- Object/array lồng nhau không đóng đúng: lỗi có thể xuất hiện tại token tiếp theo hoặc cuối file.

Vì vậy, location là chỉ dẫn chẩn đoán rất hữu ích nhưng không phải lúc nào cũng là byte đầu tiên của nguyên nhân. Hãy đọc một vùng dữ liệu xung quanh offset hoặc dòng/cột để hiểu ngữ cảnh.

### 8.1. Parser có thể đọc trước dữ liệu

Parser thường dùng buffer để đọc hiệu quả. Vị trí của stream bên ngoài hoặc số byte đã đọc từ InputStream có thể đi xa hơn token cuối cùng mà ứng dụng đã xử lý.

Nếu cần location gắn với token, dùng currentTokenLocation(). Nếu cần location parser đang đứng, dùng currentLocation(). Nếu lỗi đã xảy ra, ưu tiên getLocation() trên exception.

Không dùng InputStream.available() để suy ra vị trí lỗi. Method này chỉ cho biết ước lượng số byte có thể đọc mà không chặn; nó không phải tổng độ dài nguồn hay offset parser.

### 8.2. EOF và stream bị cắt

Nếu JSON bị cắt giữa chừng:

~~~json
{
  "orderId": "ORD-100",
  "customer": {
    "name": "An"
~~~

Parser có thể báo unexpected end-of-input. Location thường nằm ở cuối nguồn hoặc vị trí parser nhận ra cấu trúc chưa hoàn chỉnh.

Tuy nhiên, EOF cũng có thể do stream mạng bị đóng bất thường. Nếu exception là IOException từ socket hoặc nguồn dữ liệu, đó có thể là lỗi truyền tải chứ không phải lỗi cú pháp JSON. Cần giữ nguyên nguyên nhân exception để phân biệt.

## 9. Ghi log lỗi một cách có ích

Một log tốt nên ghi:
- Tên nguồn hoặc mã request để tìm lại payload.
- Loại exception.
- Original message.
- Line và column nếu có.
- Byte/character offset nếu có.
- Mapping path nếu exception là JsonMappingException.

Ví dụ helper:

~~~java
public final class JsonErrorLogger {

    private JsonErrorLogger() {
    }

    public static void log(JsonProcessingException exception) {
        JsonLocation location = exception.getLocation();

        System.err.println("JSON processing failed");
        System.err.println("Reason: " + exception.getOriginalMessage());

        if (location != null) {
            System.err.println("Line: " + location.getLineNr());
            System.err.println("Column: " + location.getColumnNr());
            System.err.println("Byte offset: " + location.getByteOffset());
            System.err.println("Character offset: " + location.getCharOffset());
        }

        if (exception instanceof JsonMappingException) {
            JsonMappingException mappingException =
                    (JsonMappingException) exception;

            System.err.println(
                    "Mapping path: " + mappingException.getPathReference()
            );
        }
    }
}
~~~

Không nên log toàn bộ payload mặc định nếu payload có thông tin cá nhân, token hoặc dữ liệu nhạy cảm. Thay vào đó, log request ID, nguồn, vị trí và path; chỉ lưu payload đã được kiểm soát hoặc che dữ liệu theo chính sách hệ thống.

## 10. Phân biệt lỗi JSON với lỗi I/O

Không phải mọi lỗi khi đọc stream đều có JsonLocation.

| Loại lỗi | Ví dụ | Thông tin vị trí |
|---|---|---|
| Parse error | Dấu phẩy thừa, string chưa đóng | Thường có JsonLocation |
| Mapping error | String không ánh xạ được vào int | Thường có location và mapping path |
| Object creation error | Creator không phù hợp hoặc constructor từ chối | Có thể có location/path tùy nguyên nhân |
| I/O error | File không tồn tại, socket bị ngắt | Thường không có JsonLocation |
| Validation error sau mapping | Email sai định dạng, số lượng âm | Không phải lỗi parser; cần property path của validation |

Ví dụ xử lý riêng:

~~~java
try (InputStream input = Files.newInputStream(path)) {
    Order order = mapper.readValue(input, Order.class);

    Set<ConstraintViolation<Order>> violations =
            validator.validate(order);

    if (!violations.isEmpty()) {
        // Xử lý lỗi validation sau khi object đã được tạo.
    }
} catch (JsonProcessingException e) {
    JsonErrorLogger.log(e);
    throw e;
} catch (IOException e) {
    // Lỗi mở hoặc đọc nguồn I/O.
    throw new UncheckedIOException("Cannot read order input", e);
}
~~~

Ở đây JsonProcessingException được xử lý riêng để lấy location. IOException còn lại được xem là lỗi I/O. Tùy phiên bản Jackson, hệ thống exception có thể có các lớp con khác; cần giữ thứ tự catch từ lớp cụ thể đến lớp tổng quát.

## 11. Ví dụ tổng hợp: đọc stream và báo lỗi có path/location

Giả sử class:

~~~java
public class Order {
    private String orderId;
    private Customer customer;

    public Order() {
    }

    public String getOrderId() {
        return orderId;
    }

    public void setOrderId(String orderId) {
        this.orderId = orderId;
    }

    public Customer getCustomer() {
        return customer;
    }

    public void setCustomer(Customer customer) {
        this.customer = customer;
    }
}

public class Customer {
    private String name;
    private int age;

    public Customer() {
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
}
~~~

File orders.json có dữ liệu:

~~~json
{
  "orderId": "ORD-100",
  "customer": {
    "name": "An",
    "age": "twenty-five"
  }
}
~~~

Chương trình đọc và báo lỗi:

~~~java
import com.fasterxml.jackson.core.JsonLocation;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.JsonMappingException;
import com.fasterxml.jackson.databind.ObjectMapper;

import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;

public class OrderReader {

    public static void main(String[] args) throws IOException {
        ObjectMapper mapper = new ObjectMapper();
        Path path = Path.of("orders.json");

        try (InputStream input = Files.newInputStream(path)) {
            Order order = mapper.readValue(input, Order.class);
            System.out.println(order.getOrderId());

        } catch (JsonMappingException e) {
            logMappingError(e);
            throw e;

        } catch (JsonProcessingException e) {
            logJsonError(e);
            throw e;
        }
    }

    private static void logMappingError(JsonMappingException e) {
        System.err.println("Cannot map JSON to Order");
        System.err.println("Path: " + e.getPathReference());
        logLocation(e);
    }

    private static void logJsonError(JsonProcessingException e) {
        System.err.println("Cannot parse/process JSON");
        System.err.println("Reason: " + e.getOriginalMessage());
        logLocation(e);
    }

    private static void logLocation(JsonProcessingException e) {
        JsonLocation location = e.getLocation();

        if (location == null) {
            System.err.println("Location unavailable");
            return;
        }

        System.err.printf(
                "Line %d, column %d, byte offset %d%n",
                location.getLineNr(),
                location.getColumnNr(),
                location.getByteOffset()
        );
    }
}
~~~

Với JSON trên, lỗi thuộc property age bên trong customer. Log path giúp xác định property; location giúp mở file tại vùng dữ liệu tương ứng. Nếu file bị lỗi cú pháp, nhánh parse/process sẽ cung cấp lý do và vị trí parser phát hiện lỗi.

Trong code production, có thể chuyển các thông tin này thành structured log thay vì in trực tiếp ra stderr. Hãy giữ request ID hoặc file identifier để liên kết lỗi với nguồn đầu vào.

## 12. Những lưu ý khi theo dõi vị trí lỗi

### 12.1. Đọc bằng InputStream hay Reader?

| Nhu cầu | Lựa chọn |
|---|---|
| Cần xử lý byte stream trực tiếp | InputStream |
| Cần byte offset để đối chiếu file/payload | Ưu tiên InputStream |
| Đã có dữ liệu dạng ký tự | Reader |
| Muốn tự kiểm soát charset khi decode | Reader với charset rõ ràng |
| File lớn hoặc dữ liệu mạng | Streaming parser từ InputStream |
| Chỉ cần ánh xạ một object | ObjectMapper.readValue(stream, Type.class) |

Với JSON trao đổi giữa hệ thống, UTF-8 là lựa chọn phổ biến và nên được quy định rõ. Không chuyển byte thành String bằng charset mặc định rồi mới đọc nếu không có lý do cụ thể.

### 12.2. Dùng đúng loại location

- Dùng exception.getLocation() khi thao tác đã thất bại.
- Dùng parser.currentTokenLocation() để biết vị trí bắt đầu token đang xử lý.
- Dùng parser.currentLocation() để biết parser hiện đang ở đâu.
- Dùng JsonMappingException.getPathReference() để bổ sung property/index path.
- Kiểm tra null và -1 trước khi ghi log các trường vị trí.

### 12.3. Không nhầm path với pointer

Mapping path của JsonMappingException mô tả đường dẫn Jackson đi qua khi ánh xạ object Java. Nó không nhất thiết là chuỗi JSON Pointer theo RFC 6901.

Nếu cần JSON Pointer cho một node trong JsonNode tree, hãy tạo pointer riêng bằng cú pháp RFC 6901. Không lấy getPathReference() rồi truyền trực tiếp cho JsonNode.at() như thể hai định dạng giống nhau.

### 12.4. Không dùng vị trí parser hiện tại sau khi đã tiếp tục đọc

Nếu ứng dụng đọc token rồi gọi nextToken() thêm nhiều lần, currentLocation() sẽ tiến lên. Muốn giữ vị trí của một token quan trọng, hãy lưu JsonLocation ngay khi parser đang ở token đó.

### 12.5. Không coi mọi lỗi là lỗi JSON

File không tồn tại, stream bị ngắt hoặc charset decode thất bại có thể phát sinh exception I/O. Cần phân loại nguyên nhân trước khi báo cho client rằng JSON sai cú pháp.

## 13. Trình tự xử lý khi điều tra lỗi đầu vào

Khi Jackson báo lỗi trong lúc đọc stream, hãy thực hiện theo trình tự:

1. Xác định nguồn đầu vào là InputStream hay Reader.
2. Xác định exception cụ thể: parse, mapping, object creation hay I/O.
3. Nếu là JsonProcessingException, lấy getLocation() và kiểm tra null.
4. Ghi line, column và loại offset có sẵn; không nhầm byte offset với character offset.
5. Nếu là JsonMappingException, lấy getPathReference() hoặc duyệt getPath().
6. Nếu đọc streaming thủ công, lưu currentTokenLocation() tại thời điểm xử lý token.
7. Mở vùng dữ liệu xung quanh vị trí để hiểu ngữ cảnh, nhất là lỗi EOF hoặc lỗi token.
8. Giữ request/file identifier trong log và tránh ghi payload nhạy cảm.
9. Sau khi mapping thành công, tiếp tục validation dữ liệu ở tầng phù hợp.

Theo dõi vị trí lỗi trong luồng đầu vào không chỉ là lấy số dòng và cột. Cần kết hợp JsonLocation, mapping path và loại exception để biết parser dừng ở đâu, property nào gây lỗi và nguyên nhân thuộc tầng nào. Khi lưu đúng các thông tin này, việc tìm lỗi trong file lớn, request HTTP hoặc message stream sẽ nhanh và có căn cứ hơn.
