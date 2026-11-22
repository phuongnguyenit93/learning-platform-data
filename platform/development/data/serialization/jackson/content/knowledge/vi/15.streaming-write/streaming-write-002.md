# Ghi đối tượng, mảng, tên trường và giá trị đúng cấu trúc

Jackson Core cung cấp `JsonGenerator` để ghi JSON theo luồng. Thay vì tạo toàn bộ object tree rồi serialize, ứng dụng lần lượt phát ra các token như bắt đầu object, tên field, giá trị, bắt đầu array và kết thúc cấu trúc. Cách này phù hợp khi tạo payload lớn, xuất dữ liệu tuần tự hoặc khi ứng dụng đã biết cấu trúc đầu ra và không cần giữ cả tài liệu JSON trong bộ nhớ.

Để ghi JSON đúng, cần phân biệt ba thao tác: **mở/đóng cấu trúc**, **ghi tên trường** và **ghi giá trị**. Tên trường chỉ xuất hiện bên trong object; giá trị có thể là scalar, object hoặc array. `JsonGenerator` theo dõi ngữ cảnh hiện tại và kiểm tra thứ tự token, giúp tránh nhiều lỗi cú pháp khi xây dựng JSON thủ công.

## 1. JSON được tạo từ những cấu trúc nào?

JSON có hai loại container:

- **Object** dùng cặp tên trường và giá trị, đặt trong `{` và `}`.
- **Array** chứa một dãy giá trị có thứ tự, đặt trong `[` và `]`.

Giá trị JSON có thể là string, number, boolean, null, object hoặc array. Một object gồm các cặp field/value; một array gồm các giá trị. Tên field của JSON object luôn là string.

Ví dụ:

```json
{
  "id": 101,
  "name": "An",
  "active": true,
  "address": {
    "city": "Ho Chi Minh City",
    "country": "Vietnam"
  },
  "roles": ["STUDENT", "AUTHOR"],
  "manager": null
}
```

Để tạo tài liệu này bằng streaming API, ứng dụng phải:

1. Mở object gốc.
2. Ghi tên field `id`, sau đó ghi number `101`.
3. Ghi tên field `name`, sau đó ghi string `An`.
4. Ghi các field scalar còn lại.
5. Khi đến `address`, mở object con, ghi các field bên trong rồi đóng object con.
6. Khi đến `roles`, mở array, ghi từng phần tử rồi đóng array.
7. Ghi `manager` với giá trị null.
8. Đóng object gốc.

## 2. Tạo JsonGenerator

`JsonGenerator` thuộc Jackson Core (`com.fasterxml.jackson.core`). Có thể tạo generator từ `JsonFactory` hoặc từ `ObjectMapper`.

Ví dụ dùng `JsonFactory` và ghi ra byte stream:

```java
import com.fasterxml.jackson.core.JsonFactory;
import com.fasterxml.jackson.core.JsonGenerator;

JsonFactory factory = new JsonFactory();

try (OutputStream output = Files.newOutputStream(Path.of("result.json"));
     JsonGenerator generator = factory.createGenerator(output)) {
    // Ghi các token JSON tại đây.
}
```

Ví dụ dùng `ObjectMapper`:

```java
ObjectMapper mapper = new ObjectMapper();

try (OutputStream output = Files.newOutputStream(Path.of("result.json"));
     JsonGenerator generator = mapper.createGenerator(output)) {
    // Generator được gắn codec của mapper để có thể ghi POJO hoặc JsonNode.
}
```

`ObjectMapper.createGenerator(...)` hữu ích khi cần kết hợp streaming với cơ chế serialize POJO hoặc tree của Databind. Nếu tạo generator trực tiếp từ `JsonFactory`, generator không nhất thiết biết `ObjectMapper`; muốn dùng `writeObject(...)` hoặc `writeTree(...)`, hãy gắn codec phù hợp bằng `generator.setCodec(mapper)`.

Trong các ví dụ dưới đây, giả sử đã có:

```java
ObjectMapper mapper = new ObjectMapper();
```

và generator được tạo qua `mapper.createGenerator(output)`.

## 3. Ghi một JSON object

Object bắt đầu bằng `writeStartObject()` và kết thúc bằng `writeEndObject()`. Mỗi thuộc tính được ghi bằng một tên field rồi đến đúng một giá trị.

```java
try (JsonGenerator gen = mapper.createGenerator(output)) {
    gen.writeStartObject();

    gen.writeFieldName("id");
    gen.writeNumber(101);

    gen.writeFieldName("name");
    gen.writeString("An");

    gen.writeFieldName("active");
    gen.writeBoolean(true);

    gen.writeEndObject();
}
```

Kết quả JSON tương đương:

```json
{"id":101,"name":"An","active":true}
```

`writeFieldName("id")` chỉ ghi tên field. Nó chưa ghi giá trị `101`. Lệnh tiếp theo phải ghi một giá trị hợp lệ. Nếu gọi tiếp `writeFieldName("name")` trước khi ghi value cho `id`, thứ tự token không hợp lệ và generator sẽ báo lỗi trong các chế độ kiểm tra tương ứng.

### 3.1. Dùng các phương thức tiện ích cho field

Jackson có các phương thức kết hợp tên field và giá trị scalar, giúp code ngắn hơn:

```java
gen.writeStartObject();
gen.writeNumberField("id", 101);
gen.writeStringField("name", "An");
gen.writeBooleanField("active", true);
gen.writeEndObject();
```

Một số phương thức tiện ích thường dùng:

| Phương thức | JSON được ghi |
|---|---|
| `writeStringField(name, value)` | Field có giá trị string |
| `writeNumberField(name, value)` | Field có giá trị number |
| `writeBooleanField(name, value)` | Field có giá trị boolean |
| `writeNullField(name)` | Field có giá trị null |
| `writeObjectFieldStart(name)` | Field có object value và mở object đó |
| `writeArrayFieldStart(name)` | Field có array value và mở array đó |

Các phương thức tiện ích không thay đổi cấu trúc JSON; chúng chỉ gộp thao tác `writeFieldName(...)` với việc ghi giá trị hoặc mở container.

## 4. Ghi array và các phần tử

Array bắt đầu bằng `writeStartArray()` và kết thúc bằng `writeEndArray()`. Bên trong array, generator ghi các giá trị theo đúng thứ tự. Không ghi tên field trực tiếp trong array.

```java
gen.writeStartArray();

gen.writeNumber(10);
gen.writeNumber(20);
gen.writeNumber(30);

gen.writeEndArray();
```

Kết quả:

```json
[10,20,30]
```

Một array có thể chứa các kiểu giá trị khác nhau về mặt cú pháp JSON:

```java
gen.writeStartArray();
gen.writeString("An");
gen.writeNumber(25);
gen.writeBoolean(true);
gen.writeNull();
gen.writeEndArray();
```

Kết quả:

```json
["An",25,true,null]
```

Trong một hợp đồng API, thông thường nên chọn một kiểu phần tử nhất quán nếu array đại diện cho một collection có kiểu, ví dụ `List<User>` hoặc `List<Integer>`. Ví dụ nhiều kiểu ở trên chỉ minh họa những giá trị mà JSON cho phép.

## 5. Ghi object và array lồng nhau

Một giá trị của field có thể là object hoặc array. Generator hỗ trợ mở container ngay sau tên field.

### 5.1. Ghi object con

```java
gen.writeStartObject();

gen.writeNumberField("id", 101);

gen.writeObjectFieldStart("address");
gen.writeStringField("city", "Ho Chi Minh City");
gen.writeStringField("country", "Vietnam");
gen.writeEndObject(); // Kết thúc address

gen.writeEndObject(); // Kết thúc object gốc
```

Kết quả:

```json
{
  "id": 101,
  "address": {
    "city": "Ho Chi Minh City",
    "country": "Vietnam"
  }
}
```

Mỗi `writeStartObject()` phải có một `writeEndObject()` tương ứng. Đóng object con trước khi tiếp tục ghi các field tiếp theo của object cha.

### 5.2. Ghi array con

```java
gen.writeStartObject();

gen.writeArrayFieldStart("roles");
gen.writeString("STUDENT");
gen.writeString("AUTHOR");
gen.writeEndArray();

gen.writeEndObject();
```

Kết quả:

```json
{"roles":["STUDENT","AUTHOR"]}
```

### 5.3. Ghi array chứa object

```java
gen.writeStartObject();
gen.writeArrayFieldStart("users");

gen.writeStartObject();
gen.writeNumberField("id", 101);
gen.writeStringField("name", "An");
gen.writeEndObject();

gen.writeStartObject();
gen.writeNumberField("id", 102);
gen.writeStringField("name", "Binh");
gen.writeEndObject();

gen.writeEndArray();
gen.writeEndObject();
```

Kết quả:

```json
{
  "users": [
    {"id": 101, "name": "An"},
    {"id": 102, "name": "Binh"}
  ]
}
```

Đây là mẫu thường dùng khi xuất dữ liệu theo batch: mở array một lần, đọc từng record từ nguồn dữ liệu, ghi một object, rồi chuyển sang record kế tiếp. Ứng dụng không cần tạo một `List` chứa toàn bộ kết quả trước khi ghi.

## 6. Ghi đúng kiểu giá trị

Jackson cung cấp các phương thức riêng cho từng kiểu JSON scalar. Chọn phương thức tương ứng để output giữ đúng kiểu dữ liệu.

### 6.1. String

```java
gen.writeStringField("name", "An");
```

`writeString(...)` tự escape dấu ngoặc kép, dấu gạch chéo ngược và các ký tự điều khiển theo quy tắc JSON. Ví dụ:

```java
gen.writeStringField("message", "He said: \"Hello\"\\done");
```

Jackson tạo một JSON string hợp lệ. Không cần tự thêm dấu ngoặc kép hoặc tự thay thế các ký tự escape trước khi truyền string vào generator.

### 6.2. Number

Có thể ghi các kiểu số phổ biến:

```java
gen.writeNumberField("count", 12);
gen.writeNumberField("total", 9_000_000_000L);
gen.writeNumberField("ratio", 0.85d);
gen.writeNumberField("amount", new BigDecimal("1250.75"));
```

`BigDecimal` phù hợp khi cần giữ giá trị thập phân chính xác, chẳng hạn số tiền. Với `double` và `float`, cần nhớ rằng biểu diễn nhị phân có thể có sai số làm tròn.

JSON không có giá trị số chuẩn cho `NaN`, `Infinity` hoặc `-Infinity`. Hãy kiểm tra các giá trị dấu phẩy động trước khi ghi và quyết định cách biểu diễn theo hợp đồng, ví dụ từ chối, ghi null nếu được phép, hoặc dùng một string có quy ước riêng. Không giả định mọi consumer JSON đều chấp nhận các giá trị không hữu hạn.

### 6.3. Boolean và null

```java
gen.writeBooleanField("enabled", true);
gen.writeNullField("deletedAt");
```

`false` và `null` khác nhau. `false` là một giá trị boolean; `null` thể hiện không có giá trị theo hợp đồng JSON. Nếu field không được phép null, ứng dụng cần kiểm tra trước khi ghi hoặc bỏ field theo đúng chính sách đã thống nhất.

### 6.4. Field có giá trị null

Có thể ghi null bằng hai cách:

```java
gen.writeFieldName("middleName");
gen.writeNull();
```

hoặc:

```java
gen.writeNullField("middleName");
```

Không nhầm việc ghi field với giá trị null và bỏ hẳn field. Hai payload sau có thể mang ý nghĩa khác nhau với consumer:

```json
{"middleName":null}
```

```json
{}
```

Hãy quyết định rõ API cần biểu diễn “không có giá trị” bằng null hay bằng việc không xuất field.

## 7. Ghi tên field và giá trị đúng ngữ cảnh

Generator theo dõi trạng thái hiện tại: đang ở root, trong object hay trong array; object đang chờ tên field hay đang chờ giá trị. Một số quy tắc quan trọng:

| Ngữ cảnh | Token hợp lệ tiếp theo |
|---|---|
| Sau `writeStartObject()` | Tên field hoặc `writeEndObject()` |
| Sau `writeFieldName(name)` | Một giá trị: scalar, object hoặc array |
| Sau `writeStartArray()` | Một giá trị hoặc `writeEndArray()` |
| Sau một giá trị trong array | Giá trị tiếp theo hoặc `writeEndArray()` |
| Sau khi đóng container con | Tiếp tục trong container cha |

Ví dụ sai về thứ tự:

```java
gen.writeStartObject();
gen.writeFieldName("id");
gen.writeFieldName("name"); // Sai: field id chưa có giá trị
gen.writeString("An");
gen.writeEndObject();
```

Ví dụ đúng:

```java
gen.writeStartObject();
gen.writeFieldName("id");
gen.writeNumber(101);
gen.writeFieldName("name");
gen.writeString("An");
gen.writeEndObject();
```

Nếu bật chế độ kiểm tra cấu trúc của generator, lỗi thứ tự token thường được phát hiện ngay tại lời gọi gây sai. Dù vậy, hãy viết code theo đúng grammar JSON thay vì dựa vào việc một cấu hình runtime có phát hiện lỗi hay không.

## 8. Ghi POJO hoặc JsonNode bên trong luồng

Không phải mọi phần của tài liệu đều cần được ghi thủ công. Có thể kết hợp token streaming với Databind để ghi một object Java hoặc một cây `JsonNode`.

### 8.1. Dùng writeObject cho POJO

Khi generator có codec là `ObjectMapper`, `writeObject(...)` ủy quyền phần serialize object cho Databind:

```java
ObjectMapper mapper = new ObjectMapper();

try (JsonGenerator gen = mapper.createGenerator(output)) {
    gen.writeStartObject();
    gen.writeStringField("source", "batch-job");

    gen.writeFieldName("payload");
    gen.writeObject(user);

    gen.writeEndObject();
}
```

`user` được serialize theo serializer, annotation và module mà mapper đã cấu hình. Generator tiếp tục quản lý cấu trúc JSON bên ngoài.

Nếu generator được tạo trực tiếp từ `JsonFactory` và chưa gắn codec, `writeObject(...)` có thể không hoạt động như mong đợi. Khi cần Databind, tạo generator qua `mapper.createGenerator(...)` hoặc gọi `gen.setCodec(mapper)` trước khi dùng.

### 8.2. Dùng writeTree cho JsonNode

Nếu một phần payload đã có sẵn dưới dạng cây:

```java
JsonNode metadata = mapper.readTree(metadataJson);

try (JsonGenerator gen = mapper.createGenerator(output)) {
    gen.writeStartObject();
    gen.writeStringField("event", "USER_UPDATED");

    gen.writeFieldName("metadata");
    gen.writeTree(metadata);

    gen.writeEndObject();
}
```

`writeTree(...)` ghi nội dung của node vào vị trí value hiện tại. Nó cần codec phù hợp để chuyển tree thành token. Nếu payload có thể được xử lý trực tiếp bằng streaming, không cần tạo `JsonNode` chỉ để ghi lại ngay sau đó.

## 9. Ghi một array lớn theo từng phần tử

Một ưu điểm quan trọng của streaming là có thể xuất dữ liệu lớn mà không cần xây dựng một collection kết quả khổng lồ.

```java
public void writeUsers(
        Iterable<User> users,
        ObjectMapper mapper,
        OutputStream output
) throws IOException {
    try (JsonGenerator gen = mapper.createGenerator(output)) {
        gen.writeStartArray();

        for (User user : users) {
            gen.writeStartObject();
            gen.writeNumberField("id", user.id());
            gen.writeStringField("name", user.name());
            gen.writeBooleanField("active", user.active());
            gen.writeEndObject();
        }

        gen.writeEndArray();
    }
}
```

Nếu `users` lấy dữ liệu theo cursor hoặc iterator từ database, ứng dụng có thể ghi từng bản ghi ngay khi đọc. Bộ nhớ dùng cho kết quả JSON khi đó chủ yếu là buffer của generator và dữ liệu của record hiện tại, thay vì phải giữ cả danh sách.

Trong ví dụ trên, generator được đóng khi kết thúc. Cần xác định rõ ai sở hữu `OutputStream`: tùy cấu hình mặc định, đóng generator có thể đóng stream đích. Nếu stream do caller quản lý và cần tiếp tục sử dụng sau khi ghi, hãy cấu hình hành vi auto-close target phù hợp trước khi tạo generator hoặc dùng API quản lý tài nguyên theo quy ước của ứng dụng. Tránh đóng cùng một tài nguyên từ nhiều tầng mà không có quy ước rõ ràng.

## 10. Định dạng dễ đọc bằng PrettyPrinter

Mặc định, generator thường ghi JSON compact. Nếu cần output có xuống dòng và thụt lề, gọi `useDefaultPrettyPrinter()` trước khi ghi token:

```java
try (JsonGenerator gen = mapper.createGenerator(output)) {
    gen.useDefaultPrettyPrinter();

    gen.writeStartObject();
    gen.writeNumberField("id", 101);
    gen.writeStringField("name", "An");
    gen.writeEndObject();
}
```

Kết quả có thể có dạng:

```json
{
  "id" : 101,
  "name" : "An"
}
```

Pretty printer chỉ thay đổi khoảng trắng định dạng quanh cấu trúc JSON. Nó không thay đổi kiểu dữ liệu, tên field hoặc giá trị. Nếu cần định dạng riêng, có thể cung cấp một `PrettyPrinter` tùy chỉnh cho generator.

Đối với API response hoặc payload lớn truyền giữa các dịch vụ, compact output thường tiết kiệm byte hơn. Pretty output hữu ích cho file export, fixture hoặc dữ liệu cần kiểm tra bằng mắt.

## 11. Escape string và tránh ghi raw JSON tùy tiện

Luôn ưu tiên các API có kiểu như `writeString`, `writeFieldName`, `writeNumber`, `writeBoolean` và `writeNull`. Jackson chịu trách nhiệm escape chuỗi và tạo dấu phân cách hợp lệ.

Không nên ghép JSON bằng nối chuỗi:

```java
// Không an toàn nếu name chứa dấu ngoặc kép hoặc ký tự điều khiển.
String json = "{\"name\":\"" + name + "\"}";
```

Hãy dùng generator:

```java
gen.writeStartObject();
gen.writeStringField("name", name);
gen.writeEndObject();
```

`writeRaw(...)` ghi nội dung thô mà không áp dụng đầy đủ quy tắc cấu trúc/escape như các API typed. `writeRawValue(...)` cũng yêu cầu đoạn nội dung đưa vào đã là JSON hợp lệ. Chỉ dùng các phương thức raw khi ứng dụng kiểm soát và xác thực chính xác chuỗi JSON; không truyền trực tiếp dữ liệu người dùng vào raw output.

## 12. Thứ tự field, field trùng tên và hợp đồng JSON

Generator ghi field theo đúng thứ tự lời gọi. Điều này hữu ích khi muốn output dễ đọc hoặc tạo fixture ổn định. Tuy nhiên, thứ tự member của JSON object thường không nên được dùng làm ý nghĩa nghiệp vụ; consumer nên truy cập field theo tên.

Tránh ghi cùng một tên field nhiều lần:

```java
gen.writeStartObject();
gen.writeNumberField("status", 1);
gen.writeStringField("status", "ACTIVE");
gen.writeEndObject();
```

JSON object với duplicate member name có thể được các parser xử lý khác nhau. Một số consumer giữ giá trị đầu, số khác giữ giá trị cuối hoặc báo lỗi. Nếu cần nhiều giá trị, dùng array hoặc đổi tên field theo đúng schema thay vì lặp tên.

Hãy bảo đảm mỗi object có cấu trúc field/value đúng hợp đồng, kiểu value ổn định và cách biểu diễn null nhất quán. Nếu API có schema hoặc DTO rõ ràng, generator cần tuân thủ schema đó.

## 13. Nhiều root value và một tài liệu JSON

Một generator có thể ghi các root value liên tiếp theo một số định dạng streaming, nhưng một JSON document thông thường chỉ có một root value. Ví dụ hai object liên tiếp:

```text
{"id":1}{"id":2}
```

không phải một JSON document đơn theo hợp đồng API thông thường. Nếu cần xuất nhiều record trong một tài liệu, hãy đặt chúng trong array:

```json
[
  {"id": 1},
  {"id": 2}
]
```

Nếu hệ thống thực sự dùng JSON Lines (mỗi dòng là một JSON value độc lập) hoặc JSON text sequence, hãy xem đó là một định dạng truyền tải riêng và ghi rõ framing/newline separator trong contract. Đừng vô tình ghi nhiều root value rồi gọi kết quả là một JSON object/array duy nhất.

## 14. Đóng cấu trúc và quản lý tài nguyên

Khi ghi JSON, mọi container đã mở phải được đóng đúng thứ tự:

```java
gen.writeStartObject();
gen.writeArrayFieldStart("items");
gen.writeStartObject();
gen.writeStringField("code", "A1");
gen.writeEndObject();
gen.writeEndArray();
gen.writeEndObject();
```

Trình tự đóng là ngược với trình tự mở: object con đóng trước, array cha đóng sau, cuối cùng object gốc đóng. Không đóng object gốc trước khi array hoặc object con kết thúc.

Dùng try-with-resources để generator được đóng ngay cả khi một thao tác ghi ném exception:

```java
try (JsonGenerator gen = mapper.createGenerator(output)) {
    gen.writeStartArray();
    // Ghi các phần tử.
    gen.writeEndArray();
}
```

Nếu ghi lỗi giữa chừng, output stream có thể chứa JSON chưa hoàn chỉnh. Không nên công bố file hoặc payload đó như một tài liệu hoàn tất. Với file cần tính nguyên tử, có thể ghi ra file tạm rồi đổi tên sau khi ghi thành công và đóng generator.

## 15. Ví dụ tổng hợp: ghi event theo cấu trúc cố định

Ví dụ sau kết hợp object, array, field name, scalar value và một POJO được serialize bằng Databind:

```java
public void writeEvent(
        Event event,
        List<String> tags,
        ObjectMapper mapper,
        OutputStream output
) throws IOException {
    try (JsonGenerator gen = mapper.createGenerator(output)) {
        gen.useDefaultPrettyPrinter();

        gen.writeStartObject();
        gen.writeStringField("eventType", "ORDER_CREATED");
        gen.writeNumberField("eventId", event.id());
        gen.writeStringField("occurredAt", event.occurredAt().toString());

        gen.writeArrayFieldStart("tags");
        for (String tag : tags) {
            gen.writeString(tag);
        }
        gen.writeEndArray();

        gen.writeFieldName("payload");
        gen.writeObject(event.order());

        if (event.note() == null) {
            gen.writeNullField("note");
        } else {
            gen.writeStringField("note", event.note());
        }

        gen.writeEndObject();
    }
}
```

Ví dụ minh họa cách phối hợp streaming với Databind. Trong ứng dụng thực tế, `occurredAt` nên được khai báo theo kiểu ngày giờ phù hợp trong DTO và serialize bằng Java Time module nếu hợp đồng yêu cầu định dạng chuẩn; việc gọi `toString()` ở đây chỉ làm rõ rằng giá trị đang được ghi như một string.

## 16. Những lỗi thường gặp

| Lỗi | Nguyên nhân | Cách xử lý |
|---|---|---|
| Ghi field name trong array | Array chỉ nhận value | Ghi value trực tiếp hoặc mở object bên trong array |
| Ghi hai field name liên tiếp | Field trước chưa có value | Ghi đúng một value sau mỗi field name |
| Quên đóng object/array | Cấu trúc JSON chưa hoàn chỉnh | Đóng container theo thứ tự ngược với lúc mở |
| Ghi string bằng cách tự nối dấu ngoặc kép | Không escape ký tự đúng cách | Dùng `writeString` hoặc `writeStringField` |
| Dùng `writeObject` nhưng không có codec | Generator không biết Databind mapper | Tạo generator qua mapper hoặc gọi `setCodec` |
| Ghi nhiều root object trong một JSON document | Không có container root chung | Đặt các object trong một array |
| Ghi cùng field name nhiều lần | Duplicate object member | Dùng tên riêng hoặc array theo schema |
| Đóng stream ngoài ý muốn | Generator đóng target theo cấu hình | Xác định ownership và cấu hình auto-close phù hợp |
| Output bị cắt khi có exception | Ghi dở dang rồi công bố file | Chỉ publish sau khi ghi/đóng thành công; cân nhắc file tạm |

## 17. Quy trình ghi JSON bằng JsonGenerator

Khi triển khai một writer, có thể đi theo trình tự:

1. Xác định root JSON là object hay array.
2. Liệt kê field và kiểu value theo hợp đồng.
3. Mở generator từ `JsonFactory` hoặc `ObjectMapper` với encoding/target phù hợp.
4. Mở container root.
5. Với object, ghi từng field name rồi đúng một value; với array, ghi từng value theo thứ tự.
6. Với dữ liệu lồng nhau, mở và đóng container con đúng vị trí.
7. Dùng typed write methods để Jackson tự escape và tạo token hợp lệ.
8. Dùng `writeObject`/`writeTree` cho phần POJO/tree nếu generator đã có codec phù hợp.
9. Đóng container và generator; chỉ xem output là hoàn tất khi ghi thành công.
10. Kiểm tra payload bằng parser hoặc test contract khi đây là một đường ghi quan trọng.

## 18. Ghi nhớ

`JsonGenerator` ghi JSON theo thứ tự token. `writeStartObject`/`writeEndObject` tạo object; `writeStartArray`/`writeEndArray` tạo array; `writeFieldName` ghi tên thuộc tính trong object; các phương thức `writeString`, `writeNumber`, `writeBoolean`, `writeNull` ghi giá trị. Sau mỗi field name phải có đúng một value, và mọi container đã mở phải được đóng đúng thứ tự.

Dùng typed API để Jackson tự xử lý dấu phân cách và escape string. Dùng `writeObject` hoặc `writeTree` khi cần phối hợp Databind và bảo đảm generator có codec. Với dữ liệu lớn, ghi array theo từng phần tử giúp tránh giữ toàn bộ kết quả trong heap. Cuối cùng, quản lý rõ vòng đời generator/output stream và chỉ phát hành tài liệu sau khi cấu trúc đã được ghi hoàn chỉnh.
