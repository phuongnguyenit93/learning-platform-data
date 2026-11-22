# Lựa chọn JSON gọn và JSON được định dạng dễ đọc

Jackson có thể ghi cùng một object Java thành JSON gọn (compact JSON) hoặc JSON được định dạng để con người dễ đọc (pretty-printed JSON). Hai dạng này biểu diễn cùng dữ liệu JSON; điểm khác biệt chủ yếu là khoảng trắng, xuống dòng và thụt lề được thêm vào quanh object, array và dấu phân cách.

JSON gọn phù hợp với trao đổi dữ liệu giữa các hệ thống, lưu trữ và những nơi ưu tiên giảm kích thước nội dung. JSON được định dạng dễ đọc hữu ích khi kiểm tra thủ công, xem log trong môi trường phát triển, tạo fixture hoặc xuất file cấu hình cho con người chỉnh sửa. Với Jackson, có thể chọn định dạng ngay trên `ObjectWriter`, hoặc cấu hình `SerializationFeature.INDENT_OUTPUT` ở cấp `ObjectMapper`.

## 1. Hai cách trình bày của cùng một dữ liệu JSON

Giả sử ứng dụng có object:

```java
public record Address(String city, String country) {
}

public record User(
        Long id,
        String name,
        boolean active,
        Address address,
        List<String> roles
) {
}

User user = new User(
        101L,
        "An",
        true,
        new Address("Ho Chi Minh City", "Vietnam"),
        List.of("STUDENT", "AUTHOR")
);
```

JSON gọn có thể được ghi như sau:

```json
{"id":101,"name":"An","active":true,"address":{"city":"Ho Chi Minh City","country":"Vietnam"},"roles":["STUDENT","AUTHOR"]}
```

JSON được định dạng dễ đọc:

```json
{
  "id" : 101,
  "name" : "An",
  "active" : true,
  "address" : {
    "city" : "Ho Chi Minh City",
    "country" : "Vietnam"
  },
  "roles" : [ "STUDENT", "AUTHOR" ]
}
```

Hai nội dung trên có cùng cấu trúc và giá trị: cùng một object gốc, cùng các thuộc tính, cùng kiểu dữ liệu và cùng thứ tự phần tử trong array. Dạng thứ hai thêm khoảng trắng và xuống dòng để thể hiện cấu trúc lồng nhau rõ hơn.

Theo cú pháp JSON, khoảng trắng bên ngoài string có thể xuất hiện quanh các dấu ngoặc, dấu hai chấm và dấu phẩy mà không làm thay đổi giá trị được parse. Khoảng trắng nằm bên trong string vẫn là dữ liệu. Ví dụ, `"Ho Chi Minh City"` không thể bị đổi thành `"HoChiMinhCity"` chỉ vì muốn tạo JSON gọn.

## 2. Jackson mặc định ghi JSON gọn

Khi tạo `ObjectMapper` thông thường và không bật pretty printing, Jackson ghi JSON không có khoảng trắng định dạng không cần thiết:

```java
import com.fasterxml.jackson.databind.ObjectMapper;

ObjectMapper mapper = new ObjectMapper();

String json = mapper.writeValueAsString(user);
```

`writeValueAsString(...)` trả về chuỗi JSON. Các phương thức `writeValue(...)` có thể ghi kết quả ra `File`, `OutputStream`, `Writer` hoặc `JsonGenerator`.

Ví dụ ghi ra file:

```java
try (OutputStream output = Files.newOutputStream(Path.of("user.json"))) {
    mapper.writeValue(output, user);
}
```

Với mapper chưa bật `SerializationFeature.INDENT_OUTPUT`, output thường ở dạng gọn. Đây là lựa chọn phù hợp cho API response hoặc dữ liệu được chương trình khác đọc, vì không cần mang theo các ký tự định dạng chỉ phục vụ hiển thị.

Lưu ý: compact JSON không có nghĩa Jackson xóa mọi ký tự khoảng trắng khỏi dữ liệu. Jackson vẫn phải escape các ký tự cần escape bên trong string theo quy tắc JSON, chẳng hạn dấu ngoặc kép, dấu gạch chéo ngược và ký tự điều khiển. Nó chỉ tránh thêm khoảng trắng định dạng quanh cấu trúc JSON.

## 3. Ghi JSON dễ đọc bằng ObjectWriter

Khi chỉ một số thao tác cần output dễ đọc, cách linh hoạt là tạo `ObjectWriter` có pretty printer mặc định:

```java
ObjectWriter prettyWriter = mapper.writerWithDefaultPrettyPrinter();

String prettyJson = prettyWriter.writeValueAsString(user);
```

`writerWithDefaultPrettyPrinter()` tạo writer sử dụng pretty printer mặc định của Jackson. Writer đó có thể được dùng lại cho nhiều object cùng chính sách ghi:

```java
ObjectWriter prettyUserWriter = mapper.writerFor(User.class)
        .withDefaultPrettyPrinter();

String first = prettyUserWriter.writeValueAsString(firstUser);
String second = prettyUserWriter.writeValueAsString(secondUser);
```

Trong ví dụ này, `writerFor(User.class)` khai báo kiểu gốc mà writer dùng khi serialize; `withDefaultPrettyPrinter()` chọn cách trình bày có thụt lề và xuống dòng. Có thể dùng `mapper.writerWithDefaultPrettyPrinter()` nếu không cần cố định kiểu gốc.

### 3.1. Dùng ObjectWriter để chọn định dạng theo từng mục đích

Một ứng dụng có thể cần hai dạng output cho cùng object:

```java
ObjectWriter compactWriter = mapper.writer();
ObjectWriter prettyWriter = mapper.writerWithDefaultPrettyPrinter();

String apiPayload = compactWriter.writeValueAsString(user);
String diagnosticPayload = prettyWriter.writeValueAsString(user);
```

`compactWriter` dùng cấu hình serialize hiện tại của mapper. Với mapper mặc định chưa bật indent output, kết quả là JSON gọn. `prettyWriter` có pretty printer riêng cho lần ghi đó. Việc tạo writer không làm thay đổi cấu hình của mapper.

Nếu mapper nền có thể được cấu hình `INDENT_OUTPUT` ở nơi khác và yêu cầu compact phải được bảo đảm rõ ràng, có thể tắt feature trên writer:

```java
ObjectWriter compactWriter = mapper.writer()
        .without(SerializationFeature.INDENT_OUTPUT);
```

Như vậy, chính sách compact được thể hiện ngay trên writer. Một writer khác vẫn có thể dùng pretty printer mà không phải bật/tắt feature trên mapper dùng chung.

## 4. Bật INDENT_OUTPUT trên ObjectMapper

Jackson cung cấp `SerializationFeature.INDENT_OUTPUT` để bật pretty printing làm cấu hình mặc định cho hoạt động serialize của mapper:

```java
ObjectMapper prettyMapper = new ObjectMapper()
        .enable(SerializationFeature.INDENT_OUTPUT);

String json = prettyMapper.writeValueAsString(user);
```

Khi feature này được bật, các thao tác ghi sử dụng cấu hình của mapper sẽ dùng pretty printer mặc định, trừ khi writer hoặc thao tác cụ thể cung cấp chính sách khác.

Cũng có thể tắt feature:

```java
prettyMapper.disable(SerializationFeature.INDENT_OUTPUT);
```

Tuy nhiên, không nên bật/tắt feature trên một `ObjectMapper` dùng chung theo từng request:

```java
// Tránh thay đổi cấu hình mapper dùng chung theo từng lần gọi.
mapper.enable(SerializationFeature.INDENT_OUTPUT);
String pretty = mapper.writeValueAsString(user);
mapper.disable(SerializationFeature.INDENT_OUTPUT);
```

Nếu các luồng chạy đồng thời, một request có thể quan sát cấu hình mà request khác vừa thay đổi. Ngoài ra, việc thay đổi mapper sau khi đã bắt đầu sử dụng làm vòng đời cấu hình khó kiểm soát.

Nên chọn một trong hai hướng:

- Cấu hình `INDENT_OUTPUT` một lần trong giai đoạn khởi tạo nếu toàn bộ output của mapper đều cần pretty printing.
- Giữ mapper với chính sách chung ổn định và tạo `ObjectWriter` riêng cho compact hoặc pretty output nếu từng luồng xử lý có yêu cầu khác nhau.

## 5. Tạo pretty printer tùy chỉnh

Pretty printer mặc định đã đủ cho phần lớn nhu cầu. Khi cần quy tắc thụt lề riêng, Jackson cho phép truyền một `PrettyPrinter` vào writer. Ví dụ dưới đây dùng `DefaultPrettyPrinter` và `DefaultIndenter` để đặt cách thụt lề hai khoảng trắng cho object và array:

```java
import com.fasterxml.jackson.core.util.DefaultIndenter;
import com.fasterxml.jackson.core.util.DefaultPrettyPrinter;
import com.fasterxml.jackson.databind.ObjectWriter;

DefaultPrettyPrinter printer = new DefaultPrettyPrinter();
DefaultIndenter indenter = new DefaultIndenter("  ", "\n");

printer.indentObjectsWith(indenter);
printer.indentArraysWith(indenter);

ObjectWriter customPrettyWriter = mapper.writer(printer);
String json = customPrettyWriter.writeValueAsString(user);
```

Việc cấu hình này ảnh hưởng cách Jackson xuống dòng và thụt lề trong object/array. Nó không thay đổi tên thuộc tính, giá trị, kiểu dữ liệu hoặc quy tắc deserialize.

Nếu ứng dụng cần định dạng đặc biệt, nên đóng gói writer đã cấu hình thành một thành phần có tên rõ ràng, ví dụ `prettyAuditWriter` hoặc `prettyExportWriter`. Tránh tạo một pretty printer khác nhau ở mọi nơi khiến định dạng output không nhất quán.

## 6. So sánh JSON gọn và JSON dễ đọc

| Tiêu chí | JSON gọn | JSON dễ đọc |
|---|---|---|
| Khoảng trắng định dạng | Tối thiểu | Có khoảng trắng, xuống dòng, thụt lề |
| Kích thước văn bản | Thường nhỏ hơn | Thường lớn hơn |
| Khả năng parse | Có | Có |
| Khả năng biểu diễn dữ liệu | Không đổi | Không đổi |
| Dễ kiểm tra thủ công | Khó hơn với object lớn/lồng nhau | Dễ hơn |
| Phù hợp | API, trao đổi máy-máy, lưu trữ compact | Debug, fixture, export cho người đọc |

Kích thước thực tế phụ thuộc nội dung. Pretty printing thêm ký tự định dạng, nhưng mức chênh lệch có thể nhỏ với JSON ngắn hoặc bị giảm đáng kể khi nội dung được nén bằng gzip/Brotli. Nếu tối ưu băng thông là yêu cầu quan trọng, hãy đo payload thực tế sau cả bước nén thay vì chỉ suy luận từ số dòng.

Pretty printing cũng không tự làm output an toàn hơn. Nó không che mật khẩu, token, thông tin cá nhân hoặc field nội bộ. Nếu output được ghi log, cần chính sách loại bỏ hoặc che dữ liệu nhạy cảm độc lập với cách trình bày.

## 7. Chọn định dạng theo nơi sử dụng

### 7.1. API response và trao đổi giữa các dịch vụ

Với response gửi qua HTTP, compact JSON thường là lựa chọn hợp lý vì consumer là chương trình khác. Ví dụ:

```java
ObjectWriter apiWriter = mapper.writer()
        .without(SerializationFeature.INDENT_OUTPUT);

byte[] responseBody = apiWriter.writeValueAsBytes(response);
```

Nếu framework web tự serialize object trả về từ controller, hãy cấu hình Jackson tại integration point của framework thay vì tự serialize thành chuỗi trong từng controller. Ví dụ trên chỉ minh họa khi ứng dụng chủ động tạo payload byte.

### 7.2. Log và dữ liệu chẩn đoán

Trong môi trường phát triển, JSON dễ đọc giúp tìm nhanh field sai hoặc cấu trúc lồng nhau. Có thể dùng writer riêng:

```java
private final ObjectWriter diagnosticWriter =
        mapper.writerWithDefaultPrettyPrinter();

public String toDiagnosticJson(Object value) throws JsonProcessingException {
    return diagnosticWriter.writeValueAsString(value);
}
```

Trong production, cần cân nhắc kích thước log, chi phí lưu trữ, khả năng tìm kiếm và dữ liệu nhạy cảm. Pretty printing làm log nhiều dòng hơn, có thể gây khó khăn cho hệ thống thu thập log vốn kỳ vọng một event trên một dòng. Khi đó compact JSON theo kiểu structured logging thường phù hợp hơn.

### 7.3. File cấu hình hoặc dữ liệu cần chỉnh sửa thủ công

Nếu JSON được lưu để con người xem và chỉnh sửa, pretty printing giúp cấu trúc rõ ràng:

```java
Path configPath = Path.of("export", "settings.json");

try (OutputStream output = Files.newOutputStream(configPath)) {
    mapper.writerWithDefaultPrettyPrinter().writeValue(output, settings);
}
```

Hãy xác định rõ charset và quy trình ghi file theo yêu cầu ứng dụng. API ghi ra `OutputStream` ghi byte; với file JSON trao đổi, UTF-8 là lựa chọn thông dụng.

### 7.4. Test fixture và ví dụ tài liệu

JSON dễ đọc thuận tiện khi lưu fixture trong repository, vì reviewer có thể đọc diff theo từng thuộc tính. Nếu fixture được sinh tự động, hãy dùng cùng một cấu hình writer để tránh diff chỉ do cách xuống dòng hoặc thụt lề thay đổi.

Với test chỉ cần xác nhận dữ liệu, không nên phụ thuộc vào chuỗi JSON đã định dạng nếu khoảng trắng không phải yêu cầu đang kiểm thử. Có thể parse cả hai chuỗi thành `JsonNode` rồi so sánh cấu trúc:

```java
JsonNode compactTree = mapper.readTree(compactJson);
JsonNode prettyTree = mapper.readTree(prettyJson);

assertEquals(compactTree, prettyTree);
```

So sánh cây JSON giúp test tập trung vào cấu trúc và giá trị. Thứ tự phần tử trong array vẫn có ý nghĩa; còn khoảng trắng định dạng bên ngoài string không phải dữ liệu của cây JSON.

## 8. Định dạng không đồng nghĩa với thứ tự thuộc tính hoặc canonical JSON

Pretty printer quyết định cách trình bày cấu trúc, không phải một cơ chế chuẩn hóa JSON hoàn chỉnh.

Các lựa chọn sau là những vấn đề độc lập:

- **Indentation:** xuống dòng và thụt lề object/array.
- **Property order:** thứ tự thuộc tính khi serialize.
- **Null inclusion:** có ghi thuộc tính có giá trị `null` hay không.
- **Value formatting:** cách biểu diễn ngày giờ, số, enum hoặc kiểu tùy chỉnh.
- **Canonicalization:** quy tắc chuẩn hóa byte JSON để phục vụ chữ ký số hoặc hash ổn định.

Ví dụ, bật pretty printing không bảo đảm các key của `Map` được sắp xếp theo alphabet. Nếu thứ tự key là yêu cầu, cần cấu hình riêng cho kiểu dữ liệu phù hợp, chẳng hạn `SerializationFeature.ORDER_MAP_ENTRIES_BY_KEYS` cho map. Thứ tự property của POJO cũng có cơ chế cấu hình riêng.

Tương tự, không dùng pretty JSON làm đầu vào cho chữ ký số hoặc hash với giả định rằng mọi lần serialize đều tạo cùng byte. Hai JSON có cùng dữ liệu có thể khác khoảng trắng, thứ tự key, cách biểu diễn số hoặc cách escape. Nếu cần chữ ký/hash ổn định, phải dùng một quy tắc canonical JSON được xác định rõ và áp dụng nhất quán ở cả bên tạo lẫn bên kiểm tra.

## 9. Tránh thay đổi cấu hình mapper để chuyển qua lại giữa hai định dạng

Một `ObjectMapper` thường được chia sẻ trong toàn ứng dụng. Cấu hình mapper nên được hoàn tất trước khi bắt đầu serialize/deserialize và giữ ổn định sau đó.

Không nên viết helper thay đổi `INDENT_OUTPUT` rồi khôi phục sau mỗi lần gọi. Cách làm đó tạo trạng thái dùng chung có thể bị quan sát bởi request khác. Thay vào đó, tạo writer riêng:

```java
public final class JsonWriters {
    private final ObjectWriter compactWriter;
    private final ObjectWriter prettyWriter;

    public JsonWriters(ObjectMapper mapper) {
        this.compactWriter = mapper.writer()
                .without(SerializationFeature.INDENT_OUTPUT);

        this.prettyWriter = mapper.writerWithDefaultPrettyPrinter();
    }

    public String compact(Object value) throws JsonProcessingException {
        return compactWriter.writeValueAsString(value);
    }

    public String pretty(Object value) throws JsonProcessingException {
        return prettyWriter.writeValueAsString(value);
    }
}
```

`ObjectWriter` là đối tượng cấu hình bất biến và có thể tái sử dụng giữa nhiều luồng. Mỗi phương thức chọn đúng chính sách ghi mà không cần thay đổi mapper nền. Ví dụ giả định mapper đã được cấu hình hoàn chỉnh trước khi truyền vào `JsonWriters`.

## 10. Một số hiểu lầm thường gặp

### 10.1. Nghĩ rằng JSON gọn là JSON không có khoảng trắng ở bất cứ đâu

Khoảng trắng bên trong string là một phần của giá trị. Compact output chỉ bỏ khoảng trắng định dạng quanh token JSON; nó không được phép thay đổi nội dung string.

### 10.2. Nghĩ rằng pretty JSON dễ đọc hơn nên luôn tốt hơn

Pretty JSON thuận tiện cho con người nhưng làm output dài hơn và nhiều dòng hơn. Với API, log tập trung hoặc dữ liệu trao đổi khối lượng lớn, cần cân nhắc kích thước và cách hệ thống downstream xử lý.

### 10.3. Bật INDENT_OUTPUT trên mapper theo từng request

Mapper dùng chung không nên bị thay đổi cấu hình theo từng request. Hãy tạo `ObjectWriter` riêng để chọn compact hoặc pretty output.

### 10.4. Nghĩ rằng pretty printing sắp xếp thuộc tính

Indentation không quyết định thứ tự key. Nếu cần thứ tự ổn định, cấu hình property/map ordering riêng; nếu cần canonical bytes, dùng chuẩn canonicalization phù hợp.

### 10.5. So sánh chuỗi JSON trong test khi chỉ quan tâm dữ liệu

Hai chuỗi có thể khác khoảng trắng nhưng parse thành cùng cấu trúc. Nếu test không kiểm tra định dạng văn bản, hãy so sánh `JsonNode` hoặc object Java sau deserialize. Chỉ so sánh chuỗi nguyên văn khi whitespace, line break hoặc thứ tự output thực sự là một phần của hợp đồng.

## 11. Bảng chọn API Jackson

| Nhu cầu | Cách làm |
|---|---|
| Ghi nhanh JSON gọn với mapper mặc định | `mapper.writeValueAsString(value)` |
| Ghi JSON dễ đọc cho một lần gọi | `mapper.writerWithDefaultPrettyPrinter().writeValueAsString(value)` |
| Tái sử dụng chính sách pretty output | Tạo `ObjectWriter` bằng `writerWithDefaultPrettyPrinter()` |
| Tái sử dụng chính sách compact rõ ràng | `mapper.writer().without(SerializationFeature.INDENT_OUTPUT)` |
| Mọi output của mapper đều cần indent | Bật `SerializationFeature.INDENT_OUTPUT` trước khi mapper được sử dụng |
| Cần indentation riêng | Tạo `PrettyPrinter` và truyền vào `mapper.writer(prettyPrinter)` |
| Cần thứ tự key hoặc byte canonical | Cấu hình ordering/canonicalization riêng; pretty printer không giải quyết việc này |

## 12. Ghi nhớ

JSON gọn và JSON được định dạng dễ đọc biểu diễn cùng dữ liệu, khác nhau chủ yếu ở khoảng trắng định dạng. Jackson mặc định thường ghi JSON gọn; `writerWithDefaultPrettyPrinter()` tạo writer cho output dễ đọc, còn `SerializationFeature.INDENT_OUTPUT` có thể bật chính sách pretty printing ở cấp mapper.

Khi một ứng dụng cần cả hai định dạng, hãy giữ cấu hình `ObjectMapper` ổn định và tạo `ObjectWriter` riêng cho từng mục đích. Dùng compact JSON cho luồng máy-máy khi ưu tiên payload nhỏ; dùng pretty JSON cho fixture, file export hoặc chẩn đoán khi con người cần xem cấu trúc. Đừng nhầm indentation với thứ tự thuộc tính, bảo vệ dữ liệu nhạy cảm hoặc canonicalization phục vụ chữ ký số.
