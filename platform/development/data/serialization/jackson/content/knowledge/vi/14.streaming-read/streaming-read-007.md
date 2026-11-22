# Kết hợp đọc token và ánh xạ một phần sang đối tượng

Jackson có thể xử lý JSON ở nhiều mức: đọc token tuần tự bằng Streaming API, tạo cây dữ liệu bằng Tree Model hoặc ánh xạ trực tiếp sang lớp Java bằng Data Binding. Trong ứng dụng thực tế, không nhất thiết phải chọn duy nhất một cách cho toàn bộ tài liệu. Một thiết kế rất hữu ích là **dùng `JsonParser` để điều khiển luồng đọc ở cấp tài liệu, sau đó dùng `ObjectMapper` để ánh xạ từng phần dữ liệu cần thiết thành DTO**.

Cách kết hợp này đặc biệt phù hợp với tệp JSON lớn hoặc message có một mảng chứa rất nhiều bản ghi. Parser duyệt tài liệu theo thứ tự và bỏ qua những nhánh không cần thiết. Khi gặp một object cần xử lý, ứng dụng giao object hiện tại cho Jackson Databind để tạo DTO có kiểu rõ ràng. Sau khi xử lý bản ghi đó, parser tiếp tục đọc phần tiếp theo.

Nhờ vậy, code vẫn sử dụng được các lớp Java, annotation và custom deserializer quen thuộc, trong khi không phải tạo một `List` hoặc `JsonNode` chứa toàn bộ tài liệu trong bộ nhớ.

## 1. Vì sao cần kết hợp Streaming và Data Binding?

Giả sử một hệ thống nhận file import có cấu trúc:

```json
{
  "batchId": "BATCH-2026-001",
  "source": "partner-a",
  "createdAt": "2026-11-12T09:00:00Z",
  "records": [
    {
      "id": 101,
      "name": "Lan",
      "active": true
    },
    {
      "id": 102,
      "name": "Minh",
      "active": false
    }
  ]
}
```

File thực tế có thể chứa hàng trăm nghìn hoặc hàng triệu phần tử trong `records`. Ứng dụng chỉ cần đọc metadata ở đầu file, sau đó xử lý từng record.

Nếu dùng Data Binding để đọc toàn bộ tài liệu:

```java
ImportFile file = mapper.readValue(input, ImportFile.class);

for (StudentRecord record : file.getRecords()) {
    process(record);
}
```

Code ngắn và dễ đọc, nhưng toàn bộ `ImportFile`, danh sách record và các object con thường được tạo và giữ trong heap cho đến khi xử lý xong. Với file lớn, object graph có thể tiêu tốn bộ nhớ đáng kể.

Nếu dùng Streaming API hoàn toàn, ứng dụng phải tự đọc từng token và tự gán từng trường:

```java
while (parser.nextToken() != JsonToken.END_OBJECT) {
    // Tự nhận diện field, đọc giá trị và gán vào object.
}
```

Cách này kiểm soát tốt nhưng có thể tạo nhiều code xử lý trạng thái, đặc biệt khi record có object lồng nhau, collection, ngày giờ và quy tắc chuyển đổi riêng.

Kết hợp hai cách cho phép:

1. Parser đọc metadata và tìm đúng mảng `records`.
2. Parser duyệt từng object trong mảng.
3. `ObjectMapper.readValue(parser, StudentRecord.class)` ánh xạ object hiện tại thành DTO.
4. Ứng dụng validate và xử lý DTO.
5. Parser tiếp tục đọc phần tiếp theo.

## 2. Vai trò của JsonParser và ObjectMapper

Hai thành phần có trách nhiệm khác nhau:

| Thành phần | Trách nhiệm trong mô hình kết hợp |
|---|---|
| `JsonFactory` | Tạo parser/generator và quản lý cấu hình đọc/ghi ở mức JSON Core |
| `JsonParser` | Đọc token tuần tự, xác định vị trí, điều hướng object/array và bỏ qua nhánh không cần |
| `ObjectMapper` | Ánh xạ một phần JSON hiện tại thành DTO hoặc cây `JsonNode` |
| DTO / model | Biểu diễn dữ liệu đã được chọn để xử lý |
| Application/service layer | Validate nghiệp vụ, lưu trữ hoặc chuyển tiếp bản ghi |

`ObjectMapper` có `JsonFactory` riêng. Khi cần parser dùng cùng cấu hình factory với mapper, có thể tạo parser qua:

```java
JsonParser parser = mapper.getFactory().createParser(input);
```

Sau đó truyền chính parser đó vào `mapper.readValue(...)`. Jackson Databind sẽ đọc từ vị trí parser hiện tại và tạo đối tượng theo kiểu đích.

## 3. Ví dụ cơ bản: đọc array lớn, ánh xạ từng object

Giả sử file JSON có cấu trúc là một array các học viên:

```json
[
  {"id": 101, "name": "Lan", "active": true},
  {"id": 102, "name": "Minh", "active": false},
  {"id": 103, "name": "An", "active": true}
]
```

DTO:

```java
public class StudentRecord {
    private long id;
    private String name;
    private boolean active;

    public StudentRecord() {
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
}
```

Đọc từng object:

```java
import com.fasterxml.jackson.core.JsonParser;
import com.fasterxml.jackson.core.JsonToken;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;

public final class StudentImporter {
    public static void importFile(Path path, ObjectMapper mapper)
            throws IOException {

        try (InputStream input = Files.newInputStream(path);
             JsonParser parser = mapper.getFactory().createParser(input)) {

            if (parser.nextToken() != JsonToken.START_ARRAY) {
                throw new IOException("Expected a JSON array");
            }

            while (parser.nextToken() != JsonToken.END_ARRAY) {
                if (parser.currentToken() == null) {
                    throw new IOException("Unexpected end of JSON array");
                }

                if (parser.currentToken() != JsonToken.START_OBJECT) {
                    throw new IOException("Expected a student object");
                }

                StudentRecord student = mapper.readValue(
                    parser,
                    StudentRecord.class
                );

                process(student);
            }

            if (parser.nextToken() != null) {
                throw new IOException("Unexpected content after JSON array");
            }
        }
    }

    private static void process(StudentRecord student) {
        // Validate and persist one student.
    }
}
```

`ObjectMapper.readValue(parser, StudentRecord.class)` đọc object hiện tại và tạo DTO. Khi quá trình ánh xạ hoàn tất, parser đã tiêu thụ object đó; vòng lặp gọi `nextToken()` để đi tới token tiếp theo. Vì vậy, không gọi thêm `nextToken()` ngay sau `readValue()` để “đóng object” lần nữa, nếu không có thể bỏ qua phần tử kế tiếp.

Điểm quan trọng là chỉ một `StudentRecord` đang được ánh xạ ở mỗi vòng lặp. Nếu `process()` ghi bản ghi vào database rồi không giữ reference lâu dài, bộ nhớ cần cho các DTO có thể được giới hạn gần với một record đang xử lý cộng với buffer của parser và dữ liệu tạm của tầng lưu trữ.

## 4. Kết hợp Streaming và Binding trong một object envelope

Tài liệu thực tế thường có metadata và nhiều nhánh. Ví dụ:

```json
{
  "batchId": "B-2026-001",
  "createdBy": "import-service",
  "metadata": {
    "source": "partner-a",
    "schemaVersion": 2
  },
  "records": [
    {"id": 101, "name": "Lan", "active": true},
    {"id": 102, "name": "Minh", "active": false}
  ],
  "debug": {
    "trace": "large diagnostic payload"
  }
}
```

Ta có thể ánh xạ metadata nhỏ thành DTO, đọc từng record thành DTO, rồi bỏ qua nhánh `debug` nếu không cần:

```java
public class ImportMetadata {
    private String source;
    private int schemaVersion;

    public String getSource() {
        return source;
    }

    public void setSource(String source) {
        this.source = source;
    }

    public int getSchemaVersion() {
        return schemaVersion;
    }

    public void setSchemaVersion(int schemaVersion) {
        this.schemaVersion = schemaVersion;
    }
}
```

Ví dụ xử lý envelope:

```java
import com.fasterxml.jackson.core.JsonParser;
import com.fasterxml.jackson.core.JsonToken;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.IOException;
import java.io.InputStream;

public final class ImportEnvelopeReader {
    public static void read(InputStream input, ObjectMapper mapper)
            throws IOException {

        String batchId = null;
        ImportMetadata metadata = null;
        boolean recordsSeen = false;

        try (JsonParser parser = mapper.getFactory().createParser(input)) {
            if (parser.nextToken() != JsonToken.START_OBJECT) {
                throw new IOException("Expected an envelope object");
            }

            while (parser.nextToken() != JsonToken.END_OBJECT) {
                if (parser.currentToken() == null) {
                    throw new IOException("Unexpected end of envelope");
                }

                String fieldName = parser.currentName();
                JsonToken valueToken = parser.nextToken();

                if ("batchId".equals(fieldName)) {
                    if (valueToken != JsonToken.VALUE_STRING) {
                        throw new IOException("batchId must be a string");
                    }
                    batchId = parser.getText();
                } else if ("metadata".equals(fieldName)) {
                    if (valueToken != JsonToken.START_OBJECT) {
                        throw new IOException("metadata must be an object");
                    }
                    metadata = mapper.readValue(parser, ImportMetadata.class);
                } else if ("records".equals(fieldName)) {
                    if (valueToken != JsonToken.START_ARRAY) {
                        throw new IOException("records must be an array");
                    }
                    recordsSeen = true;

                    while (parser.nextToken() != JsonToken.END_ARRAY) {
                        if (parser.currentToken() == null) {
                            throw new IOException("Unexpected end of records");
                        }
                        if (parser.currentToken() != JsonToken.START_OBJECT) {
                            throw new IOException("Each record must be an object");
                        }

                        StudentRecord record = mapper.readValue(
                            parser,
                            StudentRecord.class
                        );
                        process(batchId, metadata, record);
                    }
                } else {
                    // Bỏ qua toàn bộ object/array con nếu field không cần xử lý.
                    parser.skipChildren();
                }
            }

            if (parser.nextToken() != null) {
                throw new IOException("Unexpected trailing JSON content");
            }
        }

        if (!recordsSeen) {
            throw new IOException("Required records array is missing");
        }
    }

    private static void process(
            String batchId,
            ImportMetadata metadata,
            StudentRecord record) {
        // Validate and process the current record.
    }
}
```

Ví dụ này minh họa cách parser điều khiển cấp tài liệu. Các field scalar được đọc trực tiếp; `metadata` được ánh xạ thành một DTO nhỏ; `records` được duyệt từng object; `debug` được bỏ qua bằng `skipChildren()`.

Nếu thứ tự field trong JSON không được bảo đảm, `records` có thể xuất hiện trước `batchId` hoặc `metadata`. Khi xử lý từng record, code trên có thể chưa biết metadata nếu field đó xuất hiện phía sau. Có một số cách giải quyết:

- Quy định metadata phải xuất hiện trước mảng records trong hợp đồng sinh dữ liệu, nếu producer kiểm soát được thứ tự và consumer chấp nhận quy ước này.
- Đọc metadata trước bằng một lượt streaming riêng nếu nguồn có thể đọc lại hoặc seek được.
- Tạm ghi record vào nơi lưu trữ trung gian rồi xử lý sau khi đã đọc metadata.
- Nếu metadata nhỏ nhưng thứ tự field không cố định, lưu các record đã parse trong batch giới hạn và xử lý sau khi gặp metadata; cách này chỉ phù hợp khi giới hạn batch rõ ràng.

JSON object về mặt ngữ nghĩa không nên dựa vào thứ tự khóa. Nếu logic cần metadata trước records, hãy thiết kế xử lý không phụ thuộc thứ tự hoặc quy định rõ giao thức ở tầng producer/consumer.

## 5. Kết hợp Streaming với Tree Model cho một phần dữ liệu

Không phải mọi record đều cần DTO. Có thể đọc một object cụ thể thành `JsonNode` để xử lý linh hoạt, trong khi vẫn stream tài liệu bên ngoài.

Ví dụ, một mảng event lớn có nhiều loại payload:

```json
[
  {"type": "student.created", "payload": {"id": 101, "name": "Lan"}},
  {"type": "student.disabled", "payload": {"id": 102, "reason": "inactive"}}
]
```

Ta dùng parser để duyệt từng event, ánh xạ mỗi event thành một cây nhỏ:

```java
while (parser.nextToken() != JsonToken.END_ARRAY) {
    if (parser.currentToken() != JsonToken.START_OBJECT) {
        throw new IOException("Expected an event object");
    }

    JsonNode event = mapper.readTree(parser);
    String type = event.path("type").asText();
    JsonNode payload = event.path("payload");

    switch (type) {
        case "student.created" -> {
            StudentCreated created = mapper.treeToValue(
                payload,
                StudentCreated.class
            );
            handle(created);
        }
        case "student.disabled" -> {
            StudentDisabled disabled = mapper.treeToValue(
                payload,
                StudentDisabled.class
            );
            handle(disabled);
        }
        default -> throw new IOException("Unsupported event type: " + type);
    }
}
```

Ở đây, toàn bộ tài liệu không được tạo thành một cây lớn. Mỗi lần chỉ có một event node tree. Cách này hữu ích khi payload nhỏ nhưng schema phụ thuộc vào event type.

Nếu event chứa một trường payload rất lớn và chỉ cần một vài thuộc tính, có thể dùng parser trực tiếp để đọc payload thay vì tạo cả cây event. Hãy chọn mức trừu tượng theo phần dữ liệu cần giữ.

## 6. Chỉ đọc một số trường của object bằng Streaming API

Nếu DTO quá lớn hoặc chỉ cần một vài trường, có thể đọc token thủ công. Ví dụ một record có nhiều thuộc tính nhưng pipeline chỉ cần `id` và `status`:

```java
long id = -1;
String status = null;

if (parser.nextToken() != JsonToken.START_OBJECT) {
    throw new IOException("Expected record object");
}

while (parser.nextToken() != JsonToken.END_OBJECT) {
    if (parser.currentToken() == null) {
        throw new IOException("Unexpected end of record");
    }

    String field = parser.currentName();
    JsonToken valueToken = parser.nextToken();

    if ("id".equals(field)) {
        if (valueToken != JsonToken.VALUE_NUMBER_INT) {
            throw new IOException("id must be an integer");
        }
        id = parser.getLongValue();
    } else if ("status".equals(field)) {
        if (valueToken != JsonToken.VALUE_STRING) {
            throw new IOException("status must be a string");
        }
        status = parser.getText();
    } else {
        parser.skipChildren();
    }
}
```

Đoạn code minh họa cách kiểm tra token trước khi lấy giá trị. Trong code thực tế, cần xác định trường bắt buộc, xử lý null, kiểm tra range và trường hợp khóa xuất hiện lặp lại theo chính sách của ứng dụng.

Nếu chỉ cần một số trường scalar và cấu trúc rất đơn giản, đọc token thủ công có thể hiệu quả. Nếu record có nhiều trường, object lồng nhau hoặc quy tắc ánh xạ phức tạp, Data Binding cho từng record thường dễ bảo trì hơn.

## 7. Quy tắc vị trí parser khi chuyển giữa token và databinding

Đây là phần quan trọng nhất khi kết hợp hai API. `JsonParser` có một token hiện tại. `ObjectMapper.readValue(parser, Type.class)` bắt đầu đọc từ token hiện tại và tiêu thụ giá trị JSON tương ứng.

Ví dụ parser đang ở `START_OBJECT` của record:

```text
START_ARRAY
    |
    +--> START_OBJECT  <-- parser hiện tại
    |       |
    |       +-- FIELD_NAME / VALUE ...
    |       +-- FIELD_NAME / VALUE ...
    |       |
    |       +--> END_OBJECT
    |
    +--> START_OBJECT  <-- record kế tiếp
```

Khi gọi:

```java
StudentRecord record = mapper.readValue(parser, StudentRecord.class);
```

Jackson tiêu thụ object hiện tại. Sau khi trả về, parser thường đang ở token kết thúc của giá trị đó, ví dụ `END_OBJECT`. Vòng lặp bên ngoài gọi `parser.nextToken()` để tiến tới giá trị kế tiếp.

Một số lỗi thường gặp:

- Gọi `nextToken()` trước khi `readValue()` trong khi parser đã ở đầu object, làm bỏ qua token cần ánh xạ.
- Gọi thêm `nextToken()` ngay sau `readValue()` và bỏ qua phần tử tiếp theo.
- Truyền parser khi nó đang ở `FIELD_NAME` thay vì token bắt đầu giá trị.
- Gọi `readValue()` ở token không phải đầu một giá trị phù hợp với kiểu đích.
- Không kiểm tra `null` khi stream kết thúc bất thường trước `END_ARRAY` hoặc `END_OBJECT`.
- Dùng `skipChildren()` khi parser đang ở scalar và giả định nó sẽ tự đọc tới token tiếp theo; phương thức này chỉ bỏ qua phần con của cấu trúc hiện tại và không thay thế logic điều khiển vòng lặp.

Khi code phức tạp, hãy ghi rõ trạng thái mong đợi trước và sau mỗi lần gọi parser hoặc databind. Điều này giúp tránh lỗi bỏ token và parse nhầm record.

## 8. Xử lý field không cần thiết bằng skipChildren()

Một trong những lợi ích của streaming là có thể bỏ qua nhánh dữ liệu mà ứng dụng không cần giữ:

```java
if ("records".equals(fieldName)) {
    // Đọc mảng records.
} else {
    parser.skipChildren();
}
```

Nếu field không cần xử lý là object hoặc array lồng nhau, `skipChildren()` chuyển parser đến token kết thúc cấu trúc con hiện tại. Nếu field là scalar, không có cấu trúc con để bỏ qua.

Ví dụ file có trường `diagnostics` chứa dữ liệu rất lớn nhưng import job không dùng đến. Thay vì tạo `JsonNode` hoặc map cho diagnostics, parser có thể bỏ qua toàn bộ nhánh đó. Điều này tránh cấp phát object graph không cần thiết.

Tuy nhiên, bỏ qua một nhánh không có nghĩa là bỏ qua mọi giới hạn đầu vào. Parser vẫn phải đọc qua byte/token để tiến tới phần tiếp theo, và ứng dụng vẫn cần giới hạn kích thước file, độ sâu lồng nhau, độ dài chuỗi/số và thời gian xử lý.

## 9. Ánh xạ từng phần tử bằng ObjectReader

Nếu cùng một kiểu record được đọc nhiều lần, có thể tạo `ObjectReader` một lần rồi tái sử dụng:

```java
ObjectReader studentReader = mapper.readerFor(StudentRecord.class);

while (parser.nextToken() != JsonToken.END_ARRAY) {
    if (parser.currentToken() != JsonToken.START_OBJECT) {
        throw new IOException("Expected student object");
    }

    StudentRecord student = studentReader.readValue(parser);
    process(student);
}
```

`ObjectReader` giữ kiểu đích và các tùy chọn deserialize. Nó phù hợp khi adapter có chính sách đọc riêng, chẳng hạn bật/tắt xử lý trường lạ hoặc dùng một cấu hình coercion cụ thể. Reader có thể được tạo khi adapter khởi tạo và dùng lại cho từng record.

Không thay đổi cấu hình `ObjectMapper` dùng chung trong từng vòng lặp. Nếu có chính sách khác nhau theo loại record, tạo reader phù hợp trước khi xử lý hoặc chọn reader theo loại đã xác định bằng một envelope nhỏ.

## 10. Xử lý record có kiểu generic

Nếu phần tử trong mảng là kiểu generic, có thể tạo `JavaType` hoặc `TypeReference` cho từng phần tử.

Ví dụ JSON chứa các wrapper:

```java
JavaType itemType = mapper.getTypeFactory()
    .constructParametricType(ApiResult.class, StudentRecord.class);

ObjectReader itemReader = mapper.readerFor(itemType);

while (parser.nextToken() != JsonToken.END_ARRAY) {
    if (parser.currentToken() != JsonToken.START_OBJECT) {
        throw new IOException("Expected result object");
    }

    ApiResult<StudentRecord> result = itemReader.readValue(parser);
    process(result);
}
```

Parser vẫn điều khiển mảng bên ngoài; Databind ánh xạ từng phần tử theo `JavaType` đầy đủ. Đây là cách kết hợp streaming với generic type mà không cần đọc toàn bộ danh sách.

## 11. Streaming đầu ra kết hợp với serialize từng object

Mô hình kết hợp cũng áp dụng khi ghi JSON. `JsonGenerator` tạo cấu trúc array/envelope bên ngoài, còn `ObjectWriter` hoặc `ObjectMapper` ghi từng DTO:

```java
import com.fasterxml.jackson.core.JsonGenerator;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.ObjectWriter;
import java.io.OutputStream;
import java.nio.file.Files;
import java.nio.file.Path;

public static void exportStudents(
        Path path,
        Iterable<StudentRecord> students,
        ObjectMapper mapper) throws IOException {

    ObjectWriter writer = mapper.writerFor(StudentRecord.class);

    try (OutputStream output = Files.newOutputStream(path);
         JsonGenerator generator = mapper.getFactory().createGenerator(output)) {

        generator.writeStartObject();
        generator.writeStringField("exportVersion", "1");
        generator.writeArrayFieldStart("records");

        for (StudentRecord student : students) {
            writer.writeValue(generator, student);
        }

        generator.writeEndArray();
        generator.writeEndObject();
    }
}
```

Generator quản lý dấu ngoặc và field ở cấp tài liệu; writer ghi nội dung từng object vào generator hiện tại. Ứng dụng không cần tạo một chuỗi JSON lớn rồi ghép vào envelope.

`Iterable` trong ví dụ cần cung cấp dữ liệu theo cách phù hợp với mục tiêu streaming. Nếu `students` là một `List` chứa hàng triệu object đã nạp sẵn, dữ liệu vẫn chiếm heap dù output được ghi tuần tự. Hãy dùng nguồn dữ liệu tuần tự hoặc cursor/stream có giới hạn, và đóng tài nguyên nguồn đúng cách.

## 12. Quản lý tài nguyên và quyền sở hữu stream

Parser và generator thường được quản lý bằng try-with-resources:

```java
try (InputStream input = Files.newInputStream(path);
     JsonParser parser = mapper.getFactory().createParser(input)) {
    // Đọc và ánh xạ từng phần.
}
```

Khi method nhận một `InputStream` do caller cung cấp, cần thống nhất ai chịu trách nhiệm đóng stream. Ví dụ trước tạo stream bên trong importer nên importer có thể đóng. Nếu caller truyền stream đã mở và còn cần dùng sau khi importer hoàn tất, cần cấu hình/thiết kế quyền sở hữu rõ ràng để parser không đóng nguồn ngoài ý muốn.

Jackson có các `JsonParser.Feature`/`StreamReadFeature` và `JsonGenerator.Feature`/`StreamWriteFeature` liên quan đến việc tự đóng nguồn/đích. API cụ thể thay đổi theo dòng phiên bản; hãy kiểm tra phiên bản Jackson của dự án trước khi cấu hình. Không nên bật/tắt các feature này tùy tiện ở mỗi request.

## 13. Kiểm soát bộ nhớ: streaming phải đi xuyên suốt pipeline

Streaming parser chỉ giúp giảm bộ nhớ nếu các tầng phía sau không tích lũy dữ liệu vô hạn.

Ví dụ vẫn tốn bộ nhớ:

```java
List<StudentRecord> all = new ArrayList<>();

while (parser.nextToken() != JsonToken.END_ARRAY) {
    StudentRecord record = mapper.readValue(parser, StudentRecord.class);
    all.add(record);
}
```

Parser đọc tuần tự nhưng `all` giữ mọi record trong heap. Nếu mục tiêu là xử lý file rất lớn, hãy xử lý/ghi từng record hoặc gom batch có giới hạn:

```java
List<StudentRecord> batch = new ArrayList<>(500);

while (parser.nextToken() != JsonToken.END_ARRAY) {
    StudentRecord record = mapper.readValue(parser, StudentRecord.class);
    batch.add(record);

    if (batch.size() == 500) {
        repository.saveBatch(batch);
        batch.clear();
    }
}

if (!batch.isEmpty()) {
    repository.saveBatch(batch);
}
```

Kích thước 500 chỉ là ví dụ. Cần chọn batch size dựa trên dung lượng record, heap, tốc độ database và giới hạn transaction. Batch quá nhỏ tăng số lần gọi downstream; batch quá lớn tăng lượng object được giữ và chi phí retry.

Nếu producer đọc nhanh hơn consumer, queue không giới hạn cũng có thể làm heap tăng liên tục. Hãy dùng queue có giới hạn, backpressure hoặc cơ chế đọc theo nhu cầu. Streaming ở parser không tự động tạo backpressure cho toàn bộ ứng dụng.

## 14. Xử lý lỗi khi đang đọc một phần tài liệu

Với một file lớn, lỗi có thể xuất hiện sau khi nhiều record đã được xử lý. Cần xác định chính sách:

- Dừng toàn bộ import khi có record lỗi.
- Bỏ qua record lỗi và ghi nhận lỗi theo record.
- Ghi record hợp lệ vào vùng staging rồi xác nhận batch sau khi hoàn tất.
- Cho phép resume từ checkpoint nếu nguồn dữ liệu và định dạng hỗ trợ định vị lại.

Parser có thể ném `JsonParseException` khi cú pháp JSON không hợp lệ. Databind có thể ném `JsonMappingException` khi một record không khớp kiểu DTO. Lỗi I/O có thể xảy ra khi file hoặc network stream bị gián đoạn. Các lỗi này nên được phân biệt ở tầng import adapter để có thông tin nguồn, vị trí và record liên quan.

Ví dụ bọc lỗi ánh xạ record:

```java
try {
    StudentRecord record = reader.readValue(parser);
    process(record);
} catch (JsonMappingException exception) {
    throw new InvalidImportRecordException(
        "Record does not match StudentRecord schema",
        exception
    );
}
```

`InvalidImportRecordException` là ngoại lệ ứng dụng minh họa. Trong thực tế, có thể ghi nhận `parser.currentLocation()` hoặc vị trí lỗi từ `JsonMappingException` để hỗ trợ chẩn đoán. Không ghi toàn bộ payload nếu nó chứa thông tin nhạy cảm.

Nếu đã ghi một số record vào database trước khi lỗi, không thể giả định toàn bộ import tự động rollback. Cần thiết kế transaction theo batch, staging table, idempotency key hoặc cơ chế bù trừ phù hợp với nghiệp vụ.

## 15. Giới hạn dữ liệu đầu vào

Streaming giúp tránh tạo cây lớn, nhưng parser vẫn phải đọc và xử lý toàn bộ token được yêu cầu. Với dữ liệu không tin cậy, cần giới hạn:

- Kích thước file/body sau giải nén.
- Độ sâu lồng nhau.
- Độ dài chuỗi và số.
- Số lượng record tối đa trong một batch hoặc một lần import.
- Thời gian xử lý và tốc độ đọc.
- Bộ nhớ của batch, queue và tầng downstream.

Các phiên bản Jackson mới hỗ trợ `StreamReadConstraints` để giới hạn độ sâu lồng nhau, độ dài chuỗi và số. Ví dụ:

```java
StreamReadConstraints constraints = StreamReadConstraints.builder()
    .maxNestingDepth(100)
    .maxStringLength(1_000_000)
    .maxNumberLength(1_000)
    .build();

JsonFactory factory = JsonFactory.builder()
    .streamReadConstraints(constraints)
    .build();

ObjectMapper mapper = new ObjectMapper(factory);
```

Các giới hạn trên chỉ minh họa. Hãy chọn theo hợp đồng và phiên bản Jackson thực tế. Giới hạn parser không thay thế giới hạn tổng kích thước request, số record hoặc thời gian xử lý ở tầng ứng dụng.

## 16. Khi nào nên dùng cách kết hợp?

| Tình huống | Cách tiếp cận phù hợp |
|---|---|
| JSON nhỏ, cấu trúc ổn định | Data Binding toàn bộ DTO |
| JSON lớn là array các object có schema ổn định | Streaming parser + Data Binding từng object |
| Envelope có metadata nhỏ và mảng record lớn | Streaming ở envelope, binding metadata và từng record |
| Event có payload khác nhau theo type | Streaming từng event + Tree Model cho event nhỏ hoặc binding theo type |
| Chỉ cần một vài trường trong object rất lớn | Streaming token thủ công |
| Cần xử lý một object lồng nhau phức tạp nhưng tài liệu ngoài lớn | Streaming bên ngoài + binding subtree hiện tại |
| Xuất array lớn từ nguồn dữ liệu tuần tự | JsonGenerator + ObjectWriter cho từng object |
| Cần truy cập ngẫu nhiên nhiều lần trên toàn bộ tài liệu | Tree Model hoặc lưu trữ/index trung gian, nếu bộ nhớ phù hợp |

Kết hợp Streaming và Databind thường là điểm cân bằng khi tài liệu lớn nhưng từng record có cấu trúc rõ ràng. Nếu toàn bộ payload nhỏ, dùng Data Binding trực tiếp thường đơn giản hơn. Nếu chỉ cần vài trường, đọc token thủ công có thể tiết kiệm cấp phát hơn. Hãy chọn theo dữ liệu và thao tác thực tế.

## 17. Các lỗi thường gặp

### Đọc toàn bộ danh sách rồi mới xử lý

Ánh xạ `List<Record>` giúp code ngắn nhưng giữ mọi phần tử trong heap. Với dữ liệu lớn, hãy stream từng object hoặc xử lý theo batch có giới hạn.

### Dùng readValue tại sai token

Trước khi gọi `mapper.readValue(parser, Record.class)`, parser phải đang ở token bắt đầu giá trị object phù hợp, thường là `START_OBJECT`. Nếu đang ở `FIELD_NAME` hoặc token scalar, kết quả sẽ không như mong muốn.

### Gọi nextToken quá nhiều lần

Databind đã tiêu thụ object hiện tại. Vòng lặp chỉ cần gọi `nextToken()` để tiến đến phần tử tiếp theo. Gọi thêm một lần sau khi readValue có thể bỏ qua record.

### Bỏ qua nhánh nhưng không kiểm tra cấu trúc

Nếu field `records` phải là array, hãy xác nhận token là `START_ARRAY`. Không coi một object hoặc scalar là danh sách hợp lệ.

### Metadata xuất hiện sau mảng records

Không dựa vào thứ tự khóa JSON nếu hợp đồng không quy định. Nếu xử lý record cần metadata, hãy thiết kế để không phụ thuộc thứ tự hoặc dùng bước trung gian.

### Parser streaming nhưng downstream vẫn tích lũy vô hạn

Danh sách kết quả, queue không giới hạn, cache hoặc batch quá lớn vẫn có thể làm hết heap. Streaming phải được duy trì đến tầng lưu trữ/consumer.

### Không xác định ai đóng stream

Đóng parser có thể đóng nguồn tùy cấu hình. Hãy quy định rõ quyền sở hữu stream và dùng try-with-resources ở đúng tầng.

## 18. Quy trình triển khai mô hình kết hợp

1. Xác định cấu trúc JSON ngoài cùng và phần nào có thể lớn không giới hạn.
2. Chọn các field cần đọc trực tiếp, field có thể bỏ qua và subtree cần ánh xạ.
3. Tạo `JsonParser` từ `JsonFactory` của mapper đã cấu hình.
4. Kiểm tra token bắt đầu của tài liệu và từng object/array quan trọng.
5. Dùng parser đọc metadata scalar hoặc bỏ qua nhánh không cần bằng `skipChildren()`.
6. Khi gặp một object cần xử lý, gọi `ObjectReader.readValue(parser)` hoặc `ObjectMapper.readValue(parser, Type.class)` ngay tại token bắt đầu object.
7. Validate DTO, xử lý hoặc lưu theo batch giới hạn.
8. Để parser tiến tới token tiếp theo đúng một lần sau mỗi giá trị đã tiêu thụ.
9. Xác nhận kết thúc cấu trúc và không còn nội dung thừa nếu hợp đồng yêu cầu một tài liệu JSON duy nhất.
10. Đóng tài nguyên đúng quyền sở hữu, xử lý lỗi và ghi nhận vị trí lỗi cần thiết.
11. Đo heap, throughput và thời gian xử lý trên dữ liệu đại diện; kiểm tra cả tốc độ downstream và backpressure.

## 19. Tổng kết

Kết hợp đọc token và ánh xạ một phần sang đối tượng giúp xử lý JSON lớn mà vẫn giữ được lợi ích của DTO có kiểu rõ ràng. `JsonParser` điều khiển luồng tài liệu, tìm phần cần xử lý và bỏ qua nhánh không cần; `ObjectMapper` hoặc `ObjectReader` ánh xạ object hiện tại thành DTO; ứng dụng xử lý record rồi tiếp tục đọc.

Điểm quan trọng nhất là giữ đúng vị trí parser khi chuyển giữa Streaming API và Databind. Parser phải ở token bắt đầu của giá trị cần ánh xạ, và sau khi `readValue()` tiêu thụ giá trị đó, vòng lặp chỉ tiến tiếp một lần. Đồng thời, hãy duy trì giới hạn bộ nhớ ở toàn pipeline bằng batch và backpressure, quản lý stream rõ ràng, xử lý lỗi theo chính sách import và kiểm tra giới hạn dữ liệu đầu vào. Khi từng phần dữ liệu có schema rõ ràng nhưng tài liệu tổng thể rất lớn, mô hình kết hợp này thường mang lại sự cân bằng tốt giữa hiệu quả và khả năng bảo trì.
