# Ghi JSON ra String, byte array, tệp và luồng đầu ra

Sau khi có một object Java, Jackson có thể chuyển object đó thành JSON và ghi kết quả ra nhiều loại đích: `String`, `byte[]`, `File`, `OutputStream` hoặc `Writer`. Các API này cùng dựa trên cơ chế serialization, nhưng khác nhau về kiểu kết quả, cách xử lý encoding, bộ nhớ và quyền sở hữu tài nguyên.

Trong bài này, các ví dụ dùng API Jackson 2.x với package `com.fasterxml.jackson`. Nếu dự án dùng major version khác, cần đối chiếu API và dependency của chính phiên bản đó trước khi áp dụng.

## 1. Chuẩn bị `ObjectMapper`

`ObjectMapper` thuộc Jackson Databind. Đây là API cấp cao thường dùng để chuyển object Java thành JSON. Ví dụ dưới đây dùng một `Map` để minh họa dữ liệu đầu vào:

```java
import com.fasterxml.jackson.databind.ObjectMapper;

import java.math.BigDecimal;
import java.util.Map;

ObjectMapper mapper = new ObjectMapper();

Map<String, Object> product = Map.of(
        "id", "P-100",
        "name", "Mechanical Keyboard",
        "price", new BigDecimal("89.90"),
        "available", true
);
```

`ObjectMapper` chịu trách nhiệm tìm serializer phù hợp cho từng kiểu dữ liệu, xử lý cấu trúc object lồng nhau và yêu cầu Jackson Core ghi các token JSON. Trong ứng dụng thực tế, nên cấu hình mapper hoàn chỉnh khi khởi tạo rồi tái sử dụng. Không thay đổi cấu hình của mapper sau khi đã chia sẻ nó cho nhiều luồng xử lý.

Với một ứng dụng cần cấu hình serialization riêng cho từng nhóm output, có thể tạo `ObjectWriter` từ mapper. `ObjectWriter` là đối tượng cấu hình ghi bất biến, phù hợp để tái sử dụng:

```java
ObjectWriter prettyWriter = mapper.writerWithDefaultPrettyPrinter();
```

Các ví dụ tiếp theo sử dụng cùng dữ liệu `product` và mapper này.

## 2. Ghi JSON ra `String`

Khi cần JSON dưới dạng chuỗi, dùng `writeValueAsString()`:

```java
String json = mapper.writeValueAsString(product);

System.out.println(json);
```

Kết quả là một chuỗi JSON tương đương:

```json
{"id":"P-100","name":"Mechanical Keyboard","price":89.90,"available":true}
```

Khoảng trắng và thứ tự field có thể thay đổi theo cấu hình serializer. JSON vẫn phải được hiểu theo cấu trúc và giá trị, không nên phụ thuộc vào cách trình bày nếu hợp đồng dữ liệu không quy định điều đó.

### 2.1. Ghi chuỗi có thụt lề

Mặc định, Jackson thường tạo JSON compact để giảm dung lượng. Nếu chuỗi cần dễ đọc khi log hoặc lưu làm dữ liệu kiểm tra, dùng pretty printer:

```java
String readableJson = mapper
        .writerWithDefaultPrettyPrinter()
        .writeValueAsString(product);
```

Ví dụ kết quả:

```json
{
  "id" : "P-100",
  "name" : "Mechanical Keyboard",
  "price" : 89.90,
  "available" : true
}
```

Pretty printing chỉ thay đổi cách trình bày JSON, không thay đổi ý nghĩa dữ liệu. Chuỗi có thụt lề sẽ chiếm nhiều ký tự hơn, vì vậy thường phù hợp với file cấu hình hoặc log phục vụ con người đọc hơn là payload cần tối ưu dung lượng.

### 2.2. Xử lý lỗi

`writeValueAsString()` có thể phát sinh `JsonProcessingException`, ví dụ khi Jackson không tìm được cách serialize một kiểu dữ liệu hoặc một serializer báo lỗi:

```java
import com.fasterxml.jackson.core.JsonProcessingException;

try {
    String json = mapper.writeValueAsString(product);
} catch (JsonProcessingException ex) {
    // Ghi nhận lỗi serialization hoặc chuyển thành lỗi nghiệp vụ phù hợp.
    throw new IllegalStateException("Cannot serialize product", ex);
}
```

Không nên bắt lỗi rồi trả về chuỗi rỗng hoặc JSON tự chế. Làm như vậy khiến phía nhận khó phân biệt dữ liệu hợp lệ với lỗi serialization.

## 3. Ghi JSON ra `byte[]`

Khi cần dữ liệu dạng byte để gửi qua API, ghi vào bộ đệm nhị phân, tính hash hoặc chuyển tiếp sang một tầng khác, dùng `writeValueAsBytes()`:

```java
byte[] jsonBytes = mapper.writeValueAsBytes(product);
```

Với JSON, Jackson sử dụng UTF-8 cho kết quả byte này. Khi cần xem nội dung dưới dạng chuỗi, chỉ rõ charset:

```java
import java.nio.charset.StandardCharsets;

String json = new String(jsonBytes, StandardCharsets.UTF_8);
```

Khi cần chuyển ngược một chuỗi JSON thành byte để gửi đi:

```java
byte[] bytes = json.getBytes(StandardCharsets.UTF_8);
```

Không dùng `new String(bytes)` hoặc `json.getBytes()` nếu muốn kết quả nhất quán giữa các máy, vì các overload không chỉ rõ charset phụ thuộc charset mặc định của môi trường.

### 3.1. Phân biệt byte JSON với Java serialization

`writeValueAsBytes()` tạo ra **byte của văn bản JSON được mã hóa UTF-8**. Đây không phải byte stream từ `ObjectOutputStream` và cũng không phải định dạng Java native serialization.

Ví dụ:

```text
Object Java
    |
    | ObjectMapper.writeValueAsBytes(...)
    v
JSON text encoded as UTF-8
    |
    v
byte[]
```

Vì là JSON, byte array có thể được đọc bởi hệ thống khác không chạy Java, miễn là hệ thống đó hiểu schema và kiểu dữ liệu trong payload.

### 3.2. Khi nào không nên dùng `byte[]`?

`byte[]` chứa toàn bộ kết quả trong bộ nhớ. Với JSON lớn, ứng dụng phải giữ cả object đầu vào và mảng byte đầu ra cùng lúc. Nếu tiếp tục tạo thêm một `String` từ byte array, bộ nhớ lại cần thêm vùng chứa cho chuỗi.

Nếu đích cuối cùng là file, HTTP response hoặc một stream khác, cân nhắc ghi trực tiếp ra đích đó thay vì tạo `byte[]` trung gian.

## 4. Ghi JSON ra tệp (`File`)

Để ghi object thành file JSON, có thể dùng `writeValue(File, Object)`:

```java
import java.io.File;

File outputFile = new File("build/output/product.json");
outputFile.getParentFile().mkdirs();

mapper.writeValue(outputFile, product);
```

Hoặc dùng `Path` của NIO để quản lý đường dẫn:

```java
import java.nio.file.Files;
import java.nio.file.Path;

Path outputPath = Path.of("build", "output", "product.json");
Files.createDirectories(outputPath.getParent());

mapper.writeValue(outputPath.toFile(), product);
```

Jackson ghi JSON ra file bằng UTF-8. API `writeValue(File, ...)` tự tạo và quản lý generator/stream bên trong, vì vậy ứng dụng không cần tự mở `FileOutputStream` cho trường hợp thông thường.

### 4.1. File đã tồn tại thì sao?

Khi ghi vào một file đã tồn tại, nội dung cũ sẽ bị thay thế; không nên xem API này là thao tác append JSON. Nếu ứng dụng cần lưu lịch sử nhiều bản ghi, hãy thiết kế định dạng và cơ chế append riêng, ví dụ JSON Lines, thay vì nối nhiều JSON document tùy tiện vào cùng một file.

Đường dẫn cha phải tồn tại hoặc được tạo trước. Cũng cần bảo đảm tiến trình có quyền ghi vào thư mục đích. Nếu thao tác ghi thất bại giữa chừng, file đích có thể đã bị tạo hoặc thay đổi một phần.

### 4.2. Ghi file an toàn hơn khi cần thay thế cấu hình quan trọng

Với file mà hệ thống khác đang đọc, có thể ghi vào file tạm trước rồi mới thay thế file đích. Mẫu dưới đây tạo file tạm trong cùng thư mục để có cơ hội dùng atomic move trên filesystem hỗ trợ:

```java
import java.nio.file.AtomicMoveNotSupportedException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;

Path target = Path.of("config", "settings.json");
Path parent = target.toAbsolutePath().getParent();
Files.createDirectories(parent);

Path temporary = Files.createTempFile(parent, "settings-", ".tmp");
boolean moved = false;

try {
    mapper.writeValue(temporary.toFile(), product);

    try {
        Files.move(temporary, target,
                StandardCopyOption.ATOMIC_MOVE,
                StandardCopyOption.REPLACE_EXISTING);
    } catch (AtomicMoveNotSupportedException ex) {
        Files.move(temporary, target, StandardCopyOption.REPLACE_EXISTING);
    }
    moved = true;
} finally {
    if (!moved) {
        Files.deleteIfExists(temporary);
    }
}
```

Atomic move phụ thuộc filesystem và môi trường triển khai. Nhánh fallback vẫn thay thế file nhưng không bảo đảm tính nguyên tử. Với dữ liệu quan trọng, cần xác định rõ hành vi khi tiến trình dừng đột ngột, quyền truy cập và chính sách backup.

## 5. Ghi JSON ra `OutputStream`

`OutputStream` cho phép ghi JSON đến nhiều loại đích: file stream, bộ đệm byte, network stream hoặc output stream do framework cung cấp.

```java
import java.io.OutputStream;
import java.nio.file.Files;
import java.nio.file.Path;

Path outputPath = Path.of("build", "output", "product.json");
Files.createDirectories(outputPath.getParent());

try (OutputStream output = Files.newOutputStream(outputPath)) {
    mapper.writeValue(output, product);
}
```

`ObjectMapper.writeValue(OutputStream, Object)` ghi JSON theo UTF-8. Phương thức này tạo generator và hoàn tất việc ghi. Với cấu hình mặc định của Jackson 2.x, generator đóng target khi được đóng; do đó output stream truyền vào thường cũng bị đóng sau thao tác. `try-with-resources` bên ngoài vẫn làm rõ quyền sở hữu và bảo đảm đóng tài nguyên nếu có lỗi xảy ra trước hoặc trong quá trình ghi.

### 5.1. Ghi vào `ByteArrayOutputStream`

`ByteArrayOutputStream` là một `OutputStream` tích lũy dữ liệu trong bộ nhớ. Có thể dùng nó khi một API yêu cầu stream nhưng kết quả cuối cùng vẫn cần là byte array:

```java
import java.io.ByteArrayOutputStream;

byte[] jsonBytes;
try (ByteArrayOutputStream output = new ByteArrayOutputStream()) {
    mapper.writeValue(output, product);
    jsonBytes = output.toByteArray();
}
```

`ByteArrayOutputStream.close()` không làm mất dữ liệu đã ghi; `toByteArray()` vẫn lấy được nội dung sau khi đóng. Tuy vậy, với mục tiêu đơn giản là lấy byte array từ object, `writeValueAsBytes()` ngắn gọn hơn và thường là lựa chọn trực tiếp.

### 5.2. Không đóng stream do framework quản lý

Một số output stream thuộc quyền quản lý của thành phần gọi, chẳng hạn HTTP response stream hoặc stream trong một pipeline lớn. Nếu truyền trực tiếp stream đó vào `mapper.writeValue(output, value)`, hành vi auto-close mặc định có thể đóng stream trước khi framework hoàn tất response hoặc ghi phần dữ liệu tiếp theo.

Trong trường hợp này, hãy tạo `JsonGenerator`, tắt `AUTO_CLOSE_TARGET` trước khi ghi, rồi để mapper ghi qua generator:

```java
import com.fasterxml.jackson.core.JsonEncoding;
import com.fasterxml.jackson.core.JsonGenerator;
import com.fasterxml.jackson.databind.ObjectMapper;

import java.io.IOException;
import java.io.OutputStream;

public void writeWithoutClosing(OutputStream output,
                                Object value,
                                ObjectMapper mapper) throws IOException {
    try (JsonGenerator generator = mapper.getFactory()
            .createGenerator(output, JsonEncoding.UTF8)) {

        generator.disable(JsonGenerator.Feature.AUTO_CLOSE_TARGET);
        mapper.writeValue(generator, value);
    }
}
```

Ở đây, `try-with-resources` đóng generator để hoàn tất và flush nội dung. Vì `AUTO_CLOSE_TARGET` đã tắt, thao tác đó không đóng `OutputStream` bên ngoài. Ứng dụng hoặc framework sở hữu stream vẫn chịu trách nhiệm đóng nó vào đúng thời điểm.

Hãy cấu hình feature trước khi generator ghi dữ liệu. Nếu cần hành vi này ở nhiều nơi, có thể tạo một factory riêng đã cấu hình thay vì thay đổi factory dùng chung một cách bất ngờ.

### 5.3. Phân biệt `flush()` và `close()`

- `flush()` đẩy dữ liệu đang được đệm xuống đích đầu ra, nhưng không kết thúc generator.
- `close()` hoàn tất generator và giải phóng tài nguyên mà generator sở hữu; theo feature `AUTO_CLOSE_TARGET`, nó có thể đóng cả stream đích.
- Đóng một generator chưa đóng object/array JSON đúng cách có thể dẫn đến output không hoàn chỉnh hoặc lỗi tùy trạng thái và implementation.

Không nên gọi `close()` trên một response stream chỉ để bảo đảm JSON đã được ghi. Hãy quản lý vòng đời generator và stream theo đúng chủ sở hữu.

## 6. Ghi JSON ra `Writer`

`Writer` là lựa chọn phù hợp khi ứng dụng đã có luồng ký tự và muốn tự quyết định charset ở lúc tạo writer:

```java
import java.io.BufferedWriter;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

Path outputPath = Path.of("build", "output", "product.json");
Files.createDirectories(outputPath.getParent());

try (BufferedWriter writer = Files.newBufferedWriter(
        outputPath, StandardCharsets.UTF_8)) {
    mapper.writeValue(writer, product);
}
```

Khác với `OutputStream`, `Writer` đã làm việc ở tầng ký tự. Charset được quyết định khi tạo writer; Jackson ghi ký tự JSON vào writer đó. Nếu writer dùng UTF-8 thì file kết quả là văn bản UTF-8.

Với một `Writer` do thành phần khác quản lý, cũng cần lưu ý hành vi auto-close target của generator. Có thể áp dụng cùng cách dùng `JsonGenerator` và tắt `AUTO_CLOSE_TARGET` trước khi truyền generator vào `mapper.writeValue(generator, value)`.

## 7. Dùng `JsonGenerator` khi muốn kiểm soát trực tiếp cấu trúc JSON

Các phương thức `ObjectMapper.writeValue...()` phù hợp khi dữ liệu đã nằm trong object Java. Nếu ứng dụng đang đọc dữ liệu từng phần hoặc muốn ghi một JSON document theo từng bước mà không tạo object trung gian, dùng `JsonGenerator` của Jackson Core.

```java
import com.fasterxml.jackson.core.JsonEncoding;
import com.fasterxml.jackson.core.JsonFactory;
import com.fasterxml.jackson.core.JsonGenerator;

import java.io.IOException;
import java.io.OutputStream;

public void writeManually(OutputStream output) throws IOException {
    JsonFactory factory = new JsonFactory();

    try (JsonGenerator generator =
                 factory.createGenerator(output, JsonEncoding.UTF8)) {
        generator.writeStartObject();
        generator.writeStringField("id", "P-100");
        generator.writeStringField("name", "Mechanical Keyboard");
        generator.writeNumberField("quantity", 12);
        generator.writeBooleanField("available", true);

        generator.writeArrayFieldStart("tags");
        generator.writeString("office");
        generator.writeString("hardware");
        generator.writeEndArray();

        generator.writeEndObject();
    }
}
```

Generator tự xử lý dấu ngoặc, dấu phẩy, dấu nháy và escape chuỗi. Không nên tự ghép JSON bằng toán tử `+` vì dữ liệu có thể chứa ký tự cần escape, giá trị null hoặc cấu trúc lồng nhau.

Với dữ liệu lớn, generator cho phép ghi từng phần. Ứng dụng không cần giữ toàn bộ JSON text hoặc toàn bộ cây dữ liệu trong bộ nhớ. Đổi lại, ứng dụng phải đảm bảo thứ tự mở/đóng object và array chính xác.

## 8. So sánh các cách ghi JSON

| API | Kiểu kết quả/đích | Encoding | Đặc điểm chính |
|---|---|---|---|
| `writeValueAsString(value)` | `String` | Chuỗi ký tự Java | Tiện cho API cần JSON text; giữ toàn bộ kết quả trong bộ nhớ |
| `writeValueAsBytes(value)` | `byte[]` | UTF-8 | Tiện cho giao tiếp nhị phân, hash hoặc API cần byte array; giữ toàn bộ kết quả trong bộ nhớ |
| `writeValue(file, value)` | `File` | UTF-8 | Ghi trực tiếp ra file, tự quản lý generator/stream |
| `writeValue(outputStream, value)` | `OutputStream` | UTF-8 | Ghi trực tiếp ra stream; mặc định đóng target khi hoàn tất |
| `writeValue(writer, value)` | `Writer` | Do writer quyết định | Ghi ký tự vào writer có sẵn |
| `JsonGenerator` | `OutputStream` hoặc `Writer` | Theo đích tạo generator | Kiểm soát trực tiếp token và thứ tự ghi |

Lựa chọn theo đích cuối cùng thường giúp tránh một bước chuyển đổi không cần thiết:

- Ứng dụng cần trả JSON text cho một API nội bộ: dùng `writeValueAsString()`.
- API cần byte payload UTF-8: dùng `writeValueAsBytes()`.
- Muốn lưu một object thành file: dùng `writeValue(File, ...)`.
- Đang có stream và muốn ghi tuần tự: dùng `writeValue(OutputStream, ...)`, đồng thời xác định rõ ai sở hữu stream.
- Cần tự điều khiển từng token hoặc xử lý dữ liệu rất lớn: dùng `JsonGenerator`.

## 9. Pretty printing và cấu hình serialization

Có thể tái sử dụng `ObjectWriter` để ghi JSON có thụt lề cho nhiều loại đích:

```java
import com.fasterxml.jackson.databind.ObjectWriter;

ObjectWriter prettyWriter = mapper.writerWithDefaultPrettyPrinter();

String jsonText = prettyWriter.writeValueAsString(product);
byte[] jsonData = prettyWriter.writeValueAsBytes(product);
```

`ObjectWriter` có các overload ghi ra file, stream và writer tương tự mapper. Việc tạo writer riêng giúp giữ cấu hình định dạng cho một mục đích mà không phải thay đổi cấu hình toàn cục của mapper.

Ngoài pretty printing, kết quả JSON còn chịu ảnh hưởng bởi serializer và cấu hình như:

- Tên property và annotation như `@JsonProperty`.
- Quy tắc đưa giá trị null vào output.
- Cách ghi ngày giờ và kiểu số.
- Thứ tự property nếu ứng dụng bật sắp xếp hoặc khai báo thứ tự rõ ràng.
- Module hỗ trợ kiểu dữ liệu bổ sung, chẳng hạn Java Time.

Nếu hợp đồng API yêu cầu định dạng ổn định, hãy cấu hình và kiểm thử các quy tắc đó rõ ràng. Không nên phụ thuộc vào default không được quy định hoặc thứ tự field tình cờ của một serializer.

Ví dụ, khi cần bỏ qua property có giá trị null, có thể cấu hình mapper bằng `JsonInclude`:

```java
import com.fasterxml.jackson.annotation.JsonInclude;
import com.fasterxml.jackson.databind.ObjectMapper;

ObjectMapper apiMapper = new ObjectMapper();
apiMapper.setSerializationInclusion(JsonInclude.Include.NON_NULL);
```

Đây là cấu hình mapper và cần hoàn tất trước khi dùng mapper cho nhiều request. Nếu chỉ một loại output cần quy tắc khác, cân nhắc tạo writer/configuration riêng hoặc dùng annotation phù hợp với model.

## 10. Các trường hợp dữ liệu đặc biệt

### 10.1. Giá trị `null`

Khi ghi một tham chiếu null ở cấp root:

```java
String json = mapper.writeValueAsString(null);
// Kết quả: "null"
```

Đây là JSON null hợp lệ, không phải chuỗi rỗng và cũng không phải không có output. Phân biệt ba trường hợp này khi thiết kế API:

```text
null   -> có một JSON value, giá trị null
""     -> JSON string rỗng nếu được quote thành ""
no body -> không có JSON document nào được gửi
```

### 10.2. Collection và mảng

Jackson có thể ghi collection hoặc array thành JSON array:

```java
List<String> names = List.of("An", "Binh", "Chi");
String json = mapper.writeValueAsString(names);
// ["An","Binh","Chi"]
```

Không cần tự tạo vòng lặp để nối dấu phẩy. Databind xử lý collection và phần tử theo serializer tương ứng.

### 10.3. Ngày giờ

Các kiểu `java.time` thường cần module Java Time của Jackson 2.x. Nếu dự án dùng `LocalDate`, `LocalDateTime` hoặc `Instant`, thêm module tương ứng và đăng ký nó trước khi serialization:

```java
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.datatype.jsr310.JavaTimeModule;

ObjectMapper mapper = new ObjectMapper();
mapper.registerModule(new JavaTimeModule());
```

Hình thức JSON của ngày giờ còn phụ thuộc cấu hình timestamp/format. Nếu hợp đồng cần chuỗi ISO hoặc pattern riêng, hãy cấu hình rõ ràng bằng feature hoặc annotation thay vì dựa vào default.

## 11. Các lỗi thường gặp khi ghi JSON

| Triệu chứng | Nguyên nhân cần kiểm tra | Hướng xử lý |
|---|---|---|
| Không tìm thấy serializer cho kiểu dữ liệu | Kiểu dữ liệu không có serializer phù hợp hoặc thiếu module | Kiểm tra kiểu property, module và annotation |
| File không được tạo | Thư mục cha không tồn tại hoặc tiến trình không có quyền ghi | Tạo thư mục và kiểm tra quyền truy cập |
| File chỉ có một phần nội dung sau lỗi | Serialization hoặc I/O thất bại trong lúc ghi | Xem exception; với file quan trọng, ghi file tạm rồi thay thế |
| HTTP response bị đóng sớm | `writeValue(OutputStream, ...)` đóng target theo mặc định | Dùng generator với `AUTO_CLOSE_TARGET` tắt và để framework sở hữu stream |
| Tiếng Việt bị lỗi khi đọc byte | Dùng charset mặc định hoặc charset không khớp | Dùng UTF-8 rõ ràng ở cả phía ghi và đọc |
| JSON quá lớn gây áp lực bộ nhớ | Giữ toàn bộ String/byte[] trong bộ nhớ | Ghi trực tiếp ra stream bằng mapper hoặc generator |
| Output có định dạng khác mong đợi | Pretty printer, annotation hoặc serialization feature | Kiểm tra cấu hình mapper/writer và hợp đồng JSON |
| Ngày giờ không đúng định dạng | Thiếu module hoặc cấu hình Java Time chưa phù hợp | Đăng ký module và quy định format rõ ràng |

Khi xử lý lỗi, giữ lại nguyên nhân gốc trong log hoặc exception chain. Tránh log toàn bộ payload nếu JSON có thể chứa token, thông tin cá nhân hoặc dữ liệu nhạy cảm.

## 12. Một ví dụ tổng hợp với nhiều đích ghi

Đoạn code sau cho thấy cùng một object có thể được ghi ra các đích khác nhau mà không cần thay đổi dữ liệu đầu vào:

```java
import com.fasterxml.jackson.databind.ObjectMapper;

import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Map;

public class JsonOutputExample {
    public static void main(String[] args) throws Exception {
        ObjectMapper mapper = new ObjectMapper();

        Map<String, Object> order = Map.of(
                "orderId", "ORD-2026-001",
                "customer", "An",
                "total", 125.50,
                "paid", true
        );

        // 1. String
        String jsonText = mapper.writeValueAsString(order);

        // 2. UTF-8 byte array
        byte[] jsonBytes = mapper.writeValueAsBytes(order);
        String decoded = new String(jsonBytes, StandardCharsets.UTF_8);

        // 3. File
        Path file = Path.of("build", "output", "order.json");
        Files.createDirectories(file.getParent());
        mapper.writeValue(file.toFile(), order);

        // 4. OutputStream
        Path streamFile = Path.of("build", "output", "order-stream.json");
        try (OutputStream output = Files.newOutputStream(streamFile)) {
            mapper.writeValue(output, order);
        }

        System.out.println(jsonText);
        System.out.println(decoded);
    }
}
```

Ví dụ dùng `throws Exception` để giữ phần minh họa ngắn. Trong code ứng dụng, nên khai báo và xử lý các loại lỗi cụ thể phù hợp với tầng đang thực hiện I/O. Nếu `OutputStream` do framework hoặc thành phần khác quản lý, áp dụng cách tạo generator và tắt auto-close như phần 5.2.

## 13. Ghi nhớ khi chọn API ghi JSON

`ObjectMapper` cung cấp API thuận tiện để ghi một object ra `String`, `byte[]`, file, stream hoặc writer. `String` và `byte[]` giữ toàn bộ kết quả trong bộ nhớ; file và stream cho phép ghi trực tiếp đến đích. `byte[]` của Jackson là JSON UTF-8, còn `Writer` sử dụng charset đã được quyết định khi tạo writer.

Điểm cần chú ý nhất khi ghi ra stream là quyền sở hữu tài nguyên: `writeValue(OutputStream, ...)` mặc định đóng target khi hoàn tất. Nếu stream thuộc framework hoặc cần dùng tiếp, hãy quản lý generator riêng và tắt `AUTO_CLOSE_TARGET`. Khi dữ liệu lớn hoặc cần kiểm soát từng token, `JsonGenerator` giúp ghi tuần tự mà không phải tạo toàn bộ JSON text trong bộ nhớ.
