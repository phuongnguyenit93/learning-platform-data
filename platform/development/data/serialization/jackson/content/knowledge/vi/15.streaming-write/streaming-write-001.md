# Mô hình ghi token bằng `JsonGenerator`

`JsonGenerator` là API ghi JSON theo mô hình streaming của Jackson Core. Ứng dụng chủ động gọi các phương thức như `writeStartObject()`, `writeFieldName()`, `writeString()`, `writeNumber()` và `writeEndObject()` theo đúng thứ tự cấu trúc mong muốn. Mỗi lời gọi tương ứng với một thao tác ghi token; generator chuyển chuỗi thao tác đó thành JSON và gửi dần tới `OutputStream` hoặc `Writer`.

Khác với cách tạo một `Map`, POJO hoặc cây `JsonNode` rồi serialize toàn bộ, generator cho phép ghi từng phần khi dữ liệu được tạo ra. Cách làm này hữu ích với file lớn, kết quả truy vấn nhiều bản ghi, HTTP response hoặc pipeline chuyển đổi dữ liệu. Đổi lại, ứng dụng phải tổ chức đúng thứ tự token và đóng đầy đủ các object/array.

Các ví dụ trong bài dùng Jackson 2.x với package `com.fasterxml.jackson`. `JsonGenerator` thuộc Jackson Core, không yêu cầu phải dựng một `JsonNode` hoặc POJO trước khi ghi.

## 1. Mô hình ghi token là gì?

JSON có một số cấu trúc cơ bản: object, array và các giá trị scalar như string, number, boolean, null. Khi ghi JSON theo streaming, ứng dụng phát ra các token theo thứ tự thể hiện cấu trúc đó.

Ví dụ JSON:

```json
{
  "id": "O-100",
  "total": 125.50,
  "paid": true,
  "items": [
    {
      "sku": "KB-01",
      "quantity": 2
    }
  ]
}
```

Luồng token logic tương ứng:

```text
START_OBJECT
  FIELD_NAME       "id"
  VALUE_STRING     "O-100"
  FIELD_NAME       "total"
  VALUE_NUMBER     125.50
  FIELD_NAME       "paid"
  VALUE_TRUE
  FIELD_NAME       "items"
  START_ARRAY
    START_OBJECT
      FIELD_NAME   "sku"
      VALUE_STRING "KB-01"
      FIELD_NAME   "quantity"
      VALUE_NUMBER_INT 2
    END_OBJECT
  END_ARRAY
END_OBJECT
```

Tên token ở đây mô tả loại sự kiện JSON. Với `JsonGenerator`, ứng dụng không cần tự tạo một danh sách `JsonToken`; thay vào đó, ứng dụng gọi method tương ứng để phát ra từng sự kiện:

| Ý nghĩa token | Method ghi thường dùng |
|---|---|
| Bắt đầu object | `writeStartObject()` |
| Kết thúc object | `writeEndObject()` |
| Tên field | `writeFieldName(name)` |
| Bắt đầu array | `writeStartArray()` |
| Kết thúc array | `writeEndArray()` |
| String | `writeString(value)` |
| Number | `writeNumber(value)` |
| Boolean | `writeBoolean(value)` |
| Null | `writeNull()` |

Generator ghi theo thứ tự lời gọi. Nếu ứng dụng ghi sai thứ tự, cấu trúc sẽ không hợp lệ hoặc generator báo lỗi trạng thái.

## 2. Vai trò của `JsonFactory` và `JsonGenerator`

`JsonFactory` tạo ra generator phù hợp với loại đích ghi. `JsonGenerator` quản lý phiên ghi cụ thể và trạng thái cấu trúc hiện tại.

```java
import com.fasterxml.jackson.core.JsonFactory;
import com.fasterxml.jackson.core.JsonGenerator;
import com.fasterxml.jackson.core.JsonEncoding;

import java.io.OutputStream;

JsonFactory factory = new JsonFactory();

try (JsonGenerator generator =
         factory.createGenerator(output, JsonEncoding.UTF8)) {
    // Ghi các token JSON tại đây.
}
```

Trong ví dụ này:

- `JsonFactory` là đối tượng tạo generator.
- `createGenerator(...)` liên kết generator với đích đầu ra.
- `JsonGenerator` giữ ngữ cảnh hiện tại, ví dụ đang ở trong object hay array.
- Các lệnh `write...()` phát ra token và tạo JSON.
- `close()` hoàn tất generator và giải phóng tài nguyên mà generator sở hữu.

Có thể tái sử dụng một factory đã cấu hình để tạo nhiều generator độc lập. Mỗi generator nên gắn với một thao tác ghi cụ thể; không dùng chung một generator cho nhiều luồng ghi đồng thời.

## 3. Tạo generator từ `OutputStream` hoặc `Writer`

### 3.1. Ghi ra `OutputStream`

Khi đích là byte stream, có thể chỉ rõ encoding:

```java
JsonFactory factory = new JsonFactory();

try (JsonGenerator generator =
         factory.createGenerator(outputStream, JsonEncoding.UTF8)) {
    generator.writeStartObject();
    generator.writeStringField("message", "Xin chào Jackson");
    generator.writeEndObject();
}
```

JSON được mã hóa UTF-8. Đây là lựa chọn phổ biến khi ghi file, response body hoặc dữ liệu gửi qua network.

### 3.2. Ghi ra `Writer`

Nếu ứng dụng đã có một `Writer`, truyền trực tiếp writer cho factory:

```java
try (JsonGenerator generator = factory.createGenerator(writer)) {
    generator.writeStartObject();
    generator.writeStringField("message", "Xin chào Jackson");
    generator.writeEndObject();
}
```

`Writer` đã làm việc ở tầng ký tự. Charset được quyết định khi tạo writer, không phải bằng `JsonEncoding` trong generator. Nếu ghi file, nên tạo writer với charset rõ ràng, chẳng hạn `StandardCharsets.UTF_8`.

### 3.3. Chọn đích phù hợp

| Đích | Cách tạo generator | Lưu ý |
|---|---|---|
| `OutputStream` | `createGenerator(output, JsonEncoding.UTF8)` | Ghi byte; có thể chỉ rõ UTF-8 |
| `Writer` | `createGenerator(writer)` | Ghi ký tự; charset do writer quyết định |
| File | Mở `OutputStream` của file rồi tạo generator | Ứng dụng kiểm soát đường dẫn và quyền ghi |
| HTTP response stream | Tạo generator từ stream response | Cần chú ý ai sở hữu và đóng stream |

Không cần chuyển JSON thành `String` hoặc `byte[]` trung gian nếu đích cuối cùng đã là stream. Ghi trực tiếp giúp tránh giữ toàn bộ nội dung JSON trong bộ nhớ.

## 4. Ghi một object đơn giản

Ví dụ ghi object có các field scalar:

```java
import com.fasterxml.jackson.core.JsonFactory;
import com.fasterxml.jackson.core.JsonGenerator;
import com.fasterxml.jackson.core.JsonEncoding;

import java.io.IOException;
import java.io.OutputStream;
import java.math.BigDecimal;

public class ProductJsonWriter {
    public void write(OutputStream output) throws IOException {
        JsonFactory factory = new JsonFactory();

        try (JsonGenerator generator =
                 factory.createGenerator(output, JsonEncoding.UTF8)) {
            generator.writeStartObject();
            generator.writeStringField("sku", "KB-01");
            generator.writeStringField("name", "Mechanical Keyboard");
            generator.writeNumberField("price", new BigDecimal("89.90"));
            generator.writeBooleanField("available", true);
            generator.writeEndObject();
        }
    }
}
```

Kết quả JSON có dạng:

```json
{
  "sku": "KB-01",
  "name": "Mechanical Keyboard",
  "price": 89.90,
  "available": true
}
```

`writeStartObject()` và `writeEndObject()` đánh dấu ranh giới object. Các method như `writeStringField()` và `writeNumberField()` là cách viết gọn cho thao tác ghi tên field rồi ghi giá trị tương ứng.

Với tiền hoặc số thập phân cần giữ chính xác, dùng `BigDecimal` thay vì chuyển qua `double`. Generator ghi số theo kiểu JSON number, không thêm dấu nháy như một chuỗi.

## 5. Ghi tên field và giá trị riêng biệt

Các method tiện ích như `writeStringField()` phù hợp với field đơn giản. Khi cần quyết định loại giá trị tại runtime, có thể ghi tên và value riêng:

```java
generator.writeFieldName("status");
generator.writeString("processing");

generator.writeFieldName("retryCount");
generator.writeNumber(3);
```

Trong object, thứ tự thao tác phải là:

1. Ghi tên field bằng `writeFieldName()`.
2. Ghi đúng một JSON value cho field đó.
3. Chuyển sang field tiếp theo hoặc đóng object.

Ví dụ sai:

```java
generator.writeStartObject();
generator.writeString("processing"); // Không có field name trước value
generator.writeEndObject();
```

Một object JSON cần tên property trước mỗi value. Generator theo dõi ngữ cảnh và thường ném lỗi khi ứng dụng cố ghi value ở vị trí đang chờ field name.

## 6. Ghi các kiểu scalar

Các method scalar tương ứng với các kiểu JSON cơ bản:

```java
generator.writeString("hello");
generator.writeNumber(42);
generator.writeNumber(1234567890123L);
generator.writeNumber(new BigDecimal("125.50"));
generator.writeBoolean(true);
generator.writeNull();
```

Khi ghi field trong object, có các method tiện ích:

```java
generator.writeStringField("name", "An");
generator.writeNumberField("age", 28);
generator.writeBooleanField("active", true);
generator.writeNullField("middleName");
```

Không tự thêm dấu nháy, dấu phẩy hoặc dấu hai chấm. Generator chịu trách nhiệm tạo cú pháp JSON và escape giá trị chuỗi. Ví dụ, nếu string có dấu nháy kép hoặc ký tự xuống dòng, `writeString()` sẽ escape phù hợp để kết quả vẫn là JSON hợp lệ.

### 6.1. Null và field bị bỏ qua

Hai cách ghi sau tạo kết quả khác nhau:

```java
generator.writeNullField("nickname");
```

```java
// Không gọi bất kỳ write method nào cho field nickname.
```

Trường hợp đầu tạo `"nickname": null`; trường hợp sau không có field `nickname`. Đây là khác biệt về hợp đồng JSON, đặc biệt với API cập nhật dữ liệu. Hãy quyết định rõ nên ghi null hay bỏ field.

Ví dụ field tùy chọn:

```java
if (email == null) {
    generator.writeNullField("email");
} else {
    generator.writeStringField("email", email);
}
```

Nếu hợp đồng yêu cầu bỏ field khi null, chỉ gọi `writeStringField()` trong nhánh `email != null`.

## 7. Ghi object lồng nhau

Một object có thể chứa object khác. Dùng `writeObjectFieldStart(name)` để ghi tên field và mở object con:

```java
generator.writeStartObject();
generator.writeStringField("id", "U-100");

generator.writeObjectFieldStart("profile");
generator.writeStringField("city", "Ho Chi Minh City");
generator.writeStringField("language", "vi");
generator.writeEndObject(); // Đóng profile

generator.writeEndObject(); // Đóng root
```

JSON:

```json
{
  "id": "U-100",
  "profile": {
    "city": "Ho Chi Minh City",
    "language": "vi"
  }
}
```

Mỗi `writeStartObject()` phải có một `writeEndObject()` tương ứng. Các object lồng nhau phải đóng theo thứ tự ngược với thứ tự mở, giống nguyên tắc stack.

Có thể viết tường minh bằng `writeFieldName("profile")` rồi `writeStartObject()`. `writeObjectFieldStart()` chỉ là method tiện ích giúp gộp hai thao tác đó.

## 8. Ghi array và các phần tử của array

Dùng `writeStartArray()` và `writeEndArray()` để mở/đóng array:

```java
generator.writeStartArray();
generator.writeString("java");
generator.writeString("jackson");
generator.writeString("streaming");
generator.writeEndArray();
```

Kết quả:

```json
["java", "jackson", "streaming"]
```

Trong array, mỗi lời gọi ghi value tạo ra một phần tử kế tiếp. Không cần ghi tên field hoặc dấu phẩy thủ công.

Khi array là property của object, dùng `writeArrayFieldStart(name)`:

```java
generator.writeStartObject();
generator.writeArrayFieldStart("tags");
generator.writeString("java");
generator.writeString("jackson");
generator.writeEndArray();
generator.writeEndObject();
```

JSON:

```json
{
  "tags": ["java", "jackson"]
}
```

Array có thể chứa scalar, object, array lồng nhau hoặc null. Kiểu của mỗi phần tử do method ghi quyết định.

## 9. Ghi danh sách object theo kiểu streaming

Một trường hợp thực tế là ghi nhiều bản ghi từ iterator hoặc kết quả truy vấn. Không cần gom tất cả bản ghi thành một `List` trước khi serialize:

```java
import com.fasterxml.jackson.core.JsonFactory;
import com.fasterxml.jackson.core.JsonGenerator;
import com.fasterxml.jackson.core.JsonEncoding;

import java.io.IOException;
import java.io.OutputStream;
import java.math.BigDecimal;
import java.util.Iterator;

public class OrderExport {
    public void writeOrders(Iterator<Order> orders, OutputStream output)
            throws IOException {
        JsonFactory factory = new JsonFactory();

        try (JsonGenerator generator =
                 factory.createGenerator(output, JsonEncoding.UTF8)) {
            generator.writeStartArray();

            while (orders.hasNext()) {
                Order order = orders.next();

                generator.writeStartObject();
                generator.writeStringField("id", order.getId());
                generator.writeNumberField("total", order.getTotal());
                generator.writeBooleanField("paid", order.isPaid());
                generator.writeEndObject();
            }

            generator.writeEndArray();
        }
    }
}
```

Ví dụ giả định `Order` cung cấp các accessor có kiểu phù hợp, trong đó `getTotal()` trả về `BigDecimal`. Generator ghi từng order khi iterator cung cấp dữ liệu. Bộ nhớ cần cho generator và bản ghi hiện tại, không cần giữ toàn bộ JSON output dưới dạng một chuỗi lớn.

Nếu nguồn là JDBC cursor hoặc stream dữ liệu, hãy quản lý vòng đời của nguồn riêng. Generator không tự đóng iterator hoặc repository cursor; nó chỉ quản lý đích JSON mà nó được tạo ra.

## 10. Ngữ cảnh ghi và thứ tự token

Generator theo dõi vị trí hiện tại để biết đang ở root, object hay array. Điều đó giúp nó tự thêm dấu phẩy và dấu phân cách cần thiết, đồng thời phát hiện nhiều thao tác không hợp lệ.

### 10.1. Trong object

Mỗi property cần một field name rồi một value:

```text
START_OBJECT
FIELD_NAME -> VALUE
FIELD_NAME -> VALUE
END_OBJECT
```

Không ghi hai field name liên tiếp mà không có value ở giữa. Không ghi một value tùy ý trong object khi chưa có field name.

### 10.2. Trong array

Array chỉ cần các value theo thứ tự:

```text
START_ARRAY
VALUE
VALUE
START_OBJECT ... END_OBJECT
VALUE
END_ARRAY
```

Không ghi field name trong array. Nếu một phần tử là object, mở object, ghi các property bên trong, đóng object rồi tiếp tục phần tử kế tiếp.

### 10.3. Ở root

Một JSON document thông thường có một root value: object, array hoặc scalar. Có thể ghi một object ở root, hoặc một array ở root. Nếu ứng dụng ghi nhiều root value liên tiếp, dữ liệu đó không còn là một JSON document thông thường; chỉ làm vậy khi giao thức đích quy định rõ một chuỗi JSON value hoặc JSON Lines.

Generator quản lý dấu phân cách giữa các value theo context. Ứng dụng không nên tự ghi dấu phẩy giữa field hoặc phần tử array.

## 11. Generator tự escape chuỗi và quản lý cú pháp

Khi ghi string, truyền nội dung nguyên bản cho `writeString()`:

```java
String text = "The device says: \"ready\"\\offline";
generator.writeStringField("message", text);
```

Generator tự escape dấu nháy kép, dấu gạch chéo ngược và các ký tự điều khiển theo quy tắc JSON. Không cần tự thay `"` bằng `\\\"` trước khi gọi `writeString()`; tự escape hai lần có thể làm thay đổi dữ liệu thực tế.

Tương tự, không nên tự nối dấu phẩy, dấu ngoặc hoặc dấu hai chấm vào chuỗi. Việc ghi thủ công cú pháp làm mất lợi ích kiểm soát cấu trúc của generator và dễ tạo JSON lỗi.

## 12. Ghi dữ liệu động và chọn method theo kiểu

Khi kiểu dữ liệu chỉ được biết tại runtime, có thể dùng nhánh theo kiểu Java:

```java
public static void writeScalar(JsonGenerator generator,
                               String fieldName,
                               Object value) throws IOException {
    generator.writeFieldName(fieldName);

    if (value == null) {
        generator.writeNull();
    } else if (value instanceof String text) {
        generator.writeString(text);
    } else if (value instanceof Integer number) {
        generator.writeNumber(number);
    } else if (value instanceof Long number) {
        generator.writeNumber(number);
    } else if (value instanceof BigDecimal number) {
        generator.writeNumber(number);
    } else if (value instanceof Boolean flag) {
        generator.writeBoolean(flag);
    } else {
        throw new IllegalArgumentException(
                "Unsupported scalar type: " + value.getClass().getName());
    }
}
```

Phương thức này chỉ xử lý scalar đã liệt kê. Không nên gọi `value.toString()` cho mọi kiểu rồi ghi bằng `writeString()`, vì như vậy số và boolean sẽ biến thành JSON string thay vì JSON number/boolean. Với object hoặc collection, cần có quy tắc ghi cấu trúc tương ứng.

Nếu cần ghi POJO bằng serializer Databind thay vì tự phát token, có thể dùng `ObjectMapper`/`ObjectCodec` đã cấu hình. Đó là một tầng tiện ích cao hơn; generator thuần Core tập trung vào các lệnh token.

## 13. Dùng `ObjectMapper` hoặc `ObjectCodec` cùng generator

Khi generator có một `ObjectCodec` phù hợp, `writeObject(value)` có thể ủy quyền việc serialize một object Java cho codec:

```java
ObjectMapper mapper = new ObjectMapper();
JsonFactory factory = mapper.getFactory();

try (JsonGenerator generator = factory.createGenerator(output, JsonEncoding.UTF8)) {
    generator.writeStartObject();
    generator.writeStringField("source", "export");
    generator.writeFieldName("customer");
    generator.writeObject(customer);
    generator.writeEndObject();
}
```

Vì factory lấy từ `ObjectMapper`, codec của mapper có thể được dùng để ghi `customer` theo serializer đã đăng ký. Nếu tạo generator từ một `JsonFactory` thuần không có codec, không nên giả định `writeObject()` biết cách serialize mọi POJO.

Khi mục tiêu là kiểm soát hoàn toàn từng token, hãy ghi object con bằng các lệnh `writeStartObject()`/`write...()`/`writeEndObject()`. Khi muốn kết hợp ghi token thủ công với serialization POJO, dùng generator có codec được cấu hình rõ ràng.

## 14. Pretty printing

Mặc định, generator thường ghi JSON compact. Có thể bật pretty printer để thêm khoảng trắng và xuống dòng:

```java
try (JsonGenerator generator = factory.createGenerator(output, JsonEncoding.UTF8)) {
    generator.useDefaultPrettyPrinter();

    generator.writeStartObject();
    generator.writeStringField("name", "An");
    generator.writeArrayFieldStart("roles");
    generator.writeString("admin");
    generator.writeString("editor");
    generator.writeEndArray();
    generator.writeEndObject();
}
```

Pretty printing thay đổi cách trình bày, không thay đổi kiểu dữ liệu hoặc ý nghĩa JSON. Nó hữu ích với file phục vụ con người đọc hoặc debug; output compact thường phù hợp hơn với payload cần tiết kiệm dung lượng.

## 15. `flush()`, `close()` và quyền sở hữu stream

Generator thường ghi qua bộ đệm. Hai thao tác quan trọng là:

- `flush()` đẩy dữ liệu đang đệm xuống đích đầu ra nhưng không kết thúc generator.
- `close()` hoàn tất generator, flush dữ liệu còn lại và giải phóng tài nguyên generator sở hữu.

Ví dụ:

```java
generator.writeEndObject();
generator.flush();
```

Sau `flush()`, generator vẫn có thể tiếp tục ghi nếu trạng thái cấu trúc cho phép. Sau `close()`, không tiếp tục ghi bằng generator đó.

### 15.1. `AUTO_CLOSE_TARGET`

Trong Jackson 2.x, `JsonGenerator.Feature.AUTO_CLOSE_TARGET` mặc định được bật. Khi generator đóng, target `OutputStream` hoặc `Writer` thường cũng bị đóng.

Nếu stream thuộc framework hoặc thành phần gọi và cần tiếp tục sử dụng sau khi generator kết thúc, có thể tắt feature trước khi ghi:

```java
public void writeResponse(OutputStream responseBody) throws IOException {
    JsonFactory factory = new JsonFactory();

    try (JsonGenerator generator =
             factory.createGenerator(responseBody, JsonEncoding.UTF8)) {
        generator.disable(JsonGenerator.Feature.AUTO_CLOSE_TARGET);

        generator.writeStartObject();
        generator.writeStringField("status", "ok");
        generator.writeEndObject();
    }

    // responseBody vẫn thuộc quyền quản lý của framework/caller.
}
```

Generator vẫn được đóng để hoàn tất JSON nhưng không đóng stream đích. Thành phần sở hữu `responseBody` chịu trách nhiệm đóng stream vào đúng thời điểm.

### 15.2. `AUTO_CLOSE_JSON_CONTENT`

`JsonGenerator.Feature.AUTO_CLOSE_JSON_CONTENT` mặc định cũng được bật trong Jackson 2.x. Khi đóng generator, feature này cho phép generator tự đóng các object/array còn đang mở để hoàn tất nội dung JSON.

Đây là cơ chế bảo vệ trong một số tình huống, không nên dùng thay cho việc đóng cấu trúc có chủ đích. Hãy luôn gọi `writeEndObject()` và `writeEndArray()` đúng vị trí. Nếu generator phải tự đóng cấu trúc vì luồng xử lý bị lỗi hoặc code quên đóng, output có thể hợp lệ về cú pháp nhưng không đầy đủ theo ý định nghiệp vụ.

### 15.3. Dùng `try-with-resources`

`JsonGenerator` triển khai `Closeable`, nên `try-with-resources` là cách rõ ràng để bảo đảm generator được đóng cả khi ghi thành công lẫn khi có exception:

```java
try (JsonGenerator generator = factory.createGenerator(output, JsonEncoding.UTF8)) {
    generator.writeStartArray();
    // Ghi các phần tử.
    generator.writeEndArray();
}
```

Nếu ứng dụng cũng sở hữu `OutputStream`, có thể đặt cả hai tài nguyên trong cùng `try` theo thứ tự phù hợp. Khi `AUTO_CLOSE_TARGET` bật, việc đóng generator có thể đóng stream trước; thao tác đóng lại trong `try-with-resources` thường an toàn với stream chuẩn nhưng cần lưu ý với custom stream.

## 16. Ghi file lớn và kiểm soát bộ nhớ

Giả sử ứng dụng xuất hàng triệu bản ghi. Nếu tạo một `List` chứa tất cả object, sau đó gọi `writeValueAsString()` và ghi chuỗi ra file, bộ nhớ phải giữ list và JSON output. Với generator, có thể mở array ở đầu file, đọc từng bản ghi từ nguồn rồi ghi từng object ngay khi có:

```java
try (OutputStream output = Files.newOutputStream(path);
     JsonGenerator generator = factory.createGenerator(output, JsonEncoding.UTF8)) {
    generator.writeStartArray();

    while (cursor.hasNext()) {
        Record record = cursor.next();
        generator.writeStartObject();
        generator.writeNumberField("id", record.id());
        generator.writeStringField("name", record.name());
        generator.writeEndObject();
    }

    generator.writeEndArray();
}
```

Đoạn code giả định `cursor` cung cấp dữ liệu tuần tự. Bộ nhớ dùng cho generator và record hiện tại, ngoài bộ đệm của nguồn dữ liệu. Nếu nguồn dữ liệu tự tải toàn bộ kết quả vào RAM, lợi ích streaming ở đầu ra vẫn có thể bị giới hạn bởi nguồn.

Với file rất quan trọng, hãy cân nhắc ghi vào file tạm rồi thay thế file đích sau khi ghi thành công. Nếu quá trình ghi thất bại giữa chừng, file đang ghi trực tiếp có thể chứa JSON chưa hoàn chỉnh.

## 17. Ghi binary và các giá trị đặc biệt

JSON không có kiểu byte array riêng. `writeBinary()` ghi dữ liệu nhị phân dưới dạng Base64 string trong JSON:

```java
byte[] imageBytes = loadImageBytes();
generator.writeFieldName("content");
generator.writeBinary(imageBytes);
```

Kết quả là một JSON string chứa văn bản Base64. Phía đọc cần giải mã Base64 để lấy lại byte ban đầu. Không nên ghi binary bằng cách chuyển từng byte sang ký tự.

Với số đặc biệt như `NaN` hoặc vô cực, cần nhớ JSON chuẩn không định nghĩa chúng như number thông thường. Hãy tránh ghi những giá trị này vào hợp đồng JSON hoặc quy định rõ chính sách xử lý. Với số thập phân nghiệp vụ, ưu tiên kiểu có độ chính xác phù hợp như `BigDecimal`.

## 18. Vì sao nên tránh `writeRaw()` trong luồng thông thường?

`writeRaw()` ghi nội dung thô mà không áp dụng đầy đủ các quy tắc tạo token JSON. Nếu dùng để nối chuỗi do người dùng cung cấp, ứng dụng có thể tạo JSON sai cú pháp hoặc làm thay đổi cấu trúc tài liệu.

Ví dụ không nên làm:

```java
generator.writeRaw(", \"admin\": true");
```

Thay vào đó, ghi cấu trúc bằng API có kiểu:

```java
generator.writeBooleanField("admin", true);
```

`writeRawValue()` có thể hữu ích khi ứng dụng đã có một JSON value được xác thực và muốn ghi nguyên văn, nhưng nó vẫn yêu cầu người gọi chịu trách nhiệm về tính hợp lệ của nội dung. Với dữ liệu không tin cậy, hãy parse thành node hoặc deserialize rồi ghi bằng các method có kiểu.

## 19. Lỗi thường gặp khi ghi token

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Generator báo lỗi khi ghi value | Đang ở object context nhưng chưa ghi field name | Ghi `writeFieldName()` trước value |
| JSON có object/array chưa đóng | Thiếu `writeEndObject()` hoặc `writeEndArray()` | Đóng đúng từng container theo thứ tự ngược |
| Output bị đóng sớm | `AUTO_CLOSE_TARGET` đóng stream thuộc framework | Tắt feature và để caller quản lý stream |
| JSON bị lặp dấu phẩy hoặc sai dấu ngoặc | Tự ghi punctuation hoặc dùng `writeRaw()` không đúng | Dùng các method token của generator |
| Số bị ghi thành chuỗi | Dùng `writeString(number.toString())` | Dùng `writeNumber()` |
| String bị escape hai lần | Tự escape trước khi gọi `writeString()` | Truyền string nguyên bản |
| File lớn tiêu tốn nhiều RAM | Tạo toàn bộ String/byte[] trước khi ghi | Ghi trực tiếp từng phần bằng generator |
| POJO không được serialize bằng `writeObject()` | Generator không có codec phù hợp | Dùng factory từ mapper hoặc ghi token thủ công |
| JSON hợp lệ nhưng thiếu dữ liệu | Dựa vào auto-close khi lỗi hoặc kết thúc luồng sớm | Kiểm soát hoàn tất nghiệp vụ và chỉ công bố output khi ghi thành công |

Các method ghi thường ném `IOException`; lỗi cấu trúc do generator phát hiện có thể được biểu diễn bằng exception Jackson cụ thể. Nên giữ nguyên nguyên nhân gốc khi chuyển lỗi lên tầng ứng dụng.

## 20. Một ví dụ hoàn chỉnh: ghi đơn hàng có object và array lồng nhau

Ví dụ sau tạo một JSON document gồm thông tin đơn hàng, khách hàng và danh sách mặt hàng:

```java
import com.fasterxml.jackson.core.JsonEncoding;
import com.fasterxml.jackson.core.JsonFactory;
import com.fasterxml.jackson.core.JsonGenerator;

import java.io.IOException;
import java.io.OutputStream;
import java.math.BigDecimal;

public class OrderJsonGeneratorExample {
    public void write(OutputStream output) throws IOException {
        JsonFactory factory = new JsonFactory();

        try (JsonGenerator generator =
                 factory.createGenerator(output, JsonEncoding.UTF8)) {
            generator.useDefaultPrettyPrinter();

            generator.writeStartObject();
            generator.writeStringField("orderId", "ORD-2026-001");
            generator.writeStringField("status", "processing");

            generator.writeObjectFieldStart("customer");
            generator.writeStringField("customerId", "C-100");
            generator.writeStringField("name", "An Nguyen");
            generator.writeEndObject();

            generator.writeArrayFieldStart("items");

            generator.writeStartObject();
            generator.writeStringField("sku", "KB-01");
            generator.writeNumberField("quantity", 2);
            generator.writeNumberField("unitPrice", new BigDecimal("89.90"));
            generator.writeEndObject();

            generator.writeStartObject();
            generator.writeStringField("sku", "MS-02");
            generator.writeNumberField("quantity", 1);
            generator.writeNumberField("unitPrice", new BigDecimal("25.00"));
            generator.writeEndObject();

            generator.writeEndArray();

            generator.writeNumberField("total", new BigDecimal("204.80"));
            generator.writeNullField("shippedAt");
            generator.writeEndObject();
        }
    }
}
```

JSON kết quả có cấu trúc:

```json
{
  "orderId": "ORD-2026-001",
  "status": "processing",
  "customer": {
    "customerId": "C-100",
    "name": "An Nguyen"
  },
  "items": [
    {
      "sku": "KB-01",
      "quantity": 2,
      "unitPrice": 89.90
    },
    {
      "sku": "MS-02",
      "quantity": 1,
      "unitPrice": 25.00
    }
  ],
  "total": 204.80,
  "shippedAt": null
}
```

Ví dụ thể hiện các nguyên tắc chính: mở root object, ghi field theo cặp tên/value, mở object con và array con, ghi từng item, đóng container theo đúng thứ tự và dùng method scalar có kiểu. `shippedAt` được ghi thành JSON null; nếu muốn bỏ field khi chưa giao hàng, chỉ cần không gọi `writeNullField()`.

## 21. Chọn `JsonGenerator` hay `ObjectMapper`?

| Nhu cầu | Lựa chọn phù hợp |
|---|---|
| Đã có POJO và muốn ghi nhanh thành JSON | `ObjectMapper.writeValue(...)` |
| Muốn tạo JSON từng phần theo thứ tự runtime | `JsonGenerator` |
| Ghi dữ liệu rất lớn từ cursor/iterator | `JsonGenerator` streaming |
| Muốn chỉnh sửa JSON hiện có theo cấu trúc | Tree Model (`JsonNode`/`ObjectNode`) rồi serialize |
| Muốn tự kiểm soát field nào xuất hiện và kiểu của từng value | `JsonGenerator` |
| Muốn dùng serializer của Databind trong một phần output | Generator có `ObjectCodec` phù hợp và `writeObject()` |

`JsonGenerator` không tự làm cho dữ liệu hợp lệ về nghiệp vụ. Nó bảo đảm việc tạo cú pháp JSON theo các lệnh ghi và trạng thái cấu trúc. Ứng dụng vẫn cần quyết định dữ liệu nào được ghi, kiểu nào được dùng, field nào bị bỏ qua và cách xử lý lỗi nguồn.

## 22. Ghi nhớ

`JsonGenerator` là API push-based: ứng dụng gọi các method `write...()` để phát token theo đúng thứ tự JSON. Generator quản lý ngữ cảnh object/array, dấu phân cách, escape string và ghi dữ liệu dần ra `OutputStream` hoặc `Writer`. Object cần field name trước value; array nhận các value theo thứ tự; container phải được đóng đúng cấp.

Hãy dùng method có kiểu cho string, number, boolean và null; tránh tự ghép cú pháp hoặc ghi raw từ dữ liệu không tin cậy. Quản lý `flush()`, `close()` và `AUTO_CLOSE_TARGET` theo quyền sở hữu stream. Với dữ liệu lớn, ghi từng bản ghi bằng generator giúp tránh tạo toàn bộ JSON trong bộ nhớ. Khi nắm rõ mô hình token và ngữ cảnh ghi, ứng dụng có thể tạo JSON linh hoạt, hiệu quả và giữ đúng cấu trúc hợp đồng.
