# Lựa chọn cách xử lý theo kích thước dữ liệu và yêu cầu kiểm soát

Trong Jackson, cùng một tài liệu JSON có thể được xử lý bằng Data Binding, Tree Model hoặc Streaming API. Không có cách nào luôn tốt nhất cho mọi tình huống. Lựa chọn phù hợp phụ thuộc vào lượng dữ liệu, cấu trúc có ổn định hay không, phần dữ liệu cần truy cập và mức độ kiểm soát mà ứng dụng cần đối với bộ nhớ, luồng đọc/ghi và lỗi.

Một request API chỉ chứa vài thuộc tính thường có thể ánh xạ thẳng vào DTO. Một tệp JSON chứa hàng triệu bản ghi lại cần cách xử lý khác: nếu đọc toàn bộ thành một `List` hoặc một cây `JsonNode`, ứng dụng có thể phải giữ toàn bộ dữ liệu trong heap cùng lúc. Khi đó, Streaming API hoặc cách kết hợp streaming với ánh xạ từng bản ghi sẽ phù hợp hơn.

Chủ đề này tập trung vào việc chọn cách xử lý trong kiến trúc Jackson theo hai trục chính: **kích thước và hình dạng dữ liệu**, cùng với **mức kiểm soát cần thiết**.

## 1. Ba cách xử lý chính trong Jackson

Jackson cung cấp ba mức làm việc thường gặp với JSON:

| Cách xử lý | API tiêu biểu | Cách chương trình nhìn dữ liệu | Đặc điểm chính |
|---|---|---|---|
| Data Binding | `ObjectMapper`, `ObjectReader`, `ObjectWriter` | Đối tượng Java có kiểu rõ ràng | Thuận tiện khi cấu trúc đã biết; thường tạo toàn bộ object graph của giá trị được đọc |
| Tree Model | `JsonNode`, `ObjectNode`, `ArrayNode` | Cây nút JSON | Linh hoạt khi cấu trúc thay đổi hoặc cần truy cập, sửa nhiều vị trí |
| Streaming API | `JsonParser`, `JsonGenerator` | Chuỗi token được đọc hoặc ghi tuần tự | Kiểm soát chi tiết, có thể xử lý từng phần mà không giữ toàn bộ tài liệu trong bộ nhớ |

Các cách này không loại trừ nhau. Data Binding và Tree Model của Jackson Databind cũng được xây dựng trên nền parser/generator của Jackson Core. Một ứng dụng có thể dùng Streaming API để duyệt một mảng rất lớn, sau đó dùng Data Binding để chuyển từng object trong mảng thành DTO. Đây thường là lựa chọn cân bằng giữa khả năng kiểm soát và độ dễ đọc của code.

## 2. Kích thước dữ liệu không chỉ là số byte của tệp

Trước khi chọn API, cần hiểu dữ liệu thực sự tiêu tốn tài nguyên ở đâu. Kích thước tệp JSON trên đĩa hoặc kích thước body HTTP không đồng nghĩa với lượng heap mà ứng dụng cần.

Khi đọc JSON, dữ liệu có thể tồn tại qua nhiều dạng:

```text
Body HTTP / tệp JSON
        |
        v
Byte đầu vào và bộ đệm đọc
        |
        v
Token JSON hoặc cây JsonNode
        |
        v
Đối tượng Java, String, List, Map và các object lồng nhau
        |
        v
Xử lý nghiệp vụ / lưu trữ / phản hồi
```

Một chuỗi JSON ngắn có thể tạo ra nhiều đối tượng Java, chuỗi ký tự và phần tử collection. Object graph trong heap thường lớn hơn kích thước văn bản đầu vào do chi phí header đối tượng, tham chiếu, cấu trúc collection và cách lưu chuỗi. Nếu dữ liệu được nén khi truyền, kích thước sau giải nén còn có thể lớn hơn đáng kể kích thước trên mạng.

Vì vậy, khi đánh giá quy mô dữ liệu, hãy xem xét:

- Số byte sau giải nén và số ký tự cần xử lý.
- Số lượng phần tử trong array hoặc số object cần tạo.
- Độ sâu lồng nhau và số thuộc tính trong mỗi object.
- Độ dài tối đa của chuỗi, số và tên trường.
- Số lượng object Java được giữ đồng thời trong heap.
- Dữ liệu có cần truy cập ngẫu nhiên, sắp xếp hoặc tổng hợp toàn cục hay chỉ cần duyệt một lần.
- Tốc độ dữ liệu đến và khả năng xử lý của tầng phía sau.

Không nên đặt một ngưỡng byte cố định để kết luận khi nào phải dùng Streaming API. Cùng một kích thước JSON, danh sách nhiều object nhỏ có thể có chi phí khác với một object chứa các chuỗi rất dài hoặc cây lồng sâu. Hãy đo trên dữ liệu đại diện và trong giới hạn bộ nhớ thực tế của ứng dụng.

## 3. Data Binding: chọn khi cấu trúc rõ ràng và object graph có thể giữ trong bộ nhớ

Data Binding phù hợp khi ứng dụng biết trước cấu trúc dữ liệu và muốn làm việc với các lớp Java có kiểu cụ thể. Đây là lựa chọn phổ biến cho request/response API, DTO, cấu hình nhỏ và message có kích thước vừa phải.

Ví dụ, JSON mô tả một học viên:

```json
{
  "id": 23,
  "name": "Lan",
  "active": true
}
```

Mô hình Java:

```java
public class Student {
    private long id;
    private String name;
    private boolean active;

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
}
```

Đọc một object:

```java
ObjectMapper mapper = new ObjectMapper();

try (InputStream input = Files.newInputStream(path)) {
    Student student = mapper.readValue(input, Student.class);
    process(student);
}
```

Truyền `InputStream` giúp tránh bước tự đọc toàn bộ tệp vào một `String` trước khi parse. Tuy nhiên, Jackson vẫn tạo object graph tương ứng với giá trị được ánh xạ. Nếu giá trị gốc là một array lớn được ánh xạ thành `List<Student>`, toàn bộ danh sách thường vẫn được giữ trong bộ nhớ sau khi đọc xong.

Ví dụ đọc toàn bộ danh sách:

```java
List<Student> students;

try (InputStream input = Files.newInputStream(path)) {
    students = mapper.readValue(
        input,
        new TypeReference<List<Student>>() {}
    );
}

for (Student student : students) {
    process(student);
}
```

Đoạn code trên ngắn và dễ hiểu. Nó phù hợp khi số phần tử được giới hạn ở mức ứng dụng có thể chứa an toàn. Nhưng nếu tệp có hàng triệu phần tử, `List<Student>` cùng các object con có thể chiếm nhiều heap, gây tăng thời gian garbage collection hoặc dẫn đến `OutOfMemoryError`.

**Nên chọn Data Binding trực tiếp khi:**

- Cấu trúc JSON ổn định, có DTO hoặc mô hình Java tương ứng.
- Dữ liệu mỗi request hoặc message có giới hạn kích thước hợp lý.
- Logic nghiệp vụ cần dùng nhiều trường và quan hệ kiểu của đối tượng.
- Việc giữ object graph trong bộ nhớ không vượt ngân sách heap.
- Code rõ ràng và khả năng bảo trì quan trọng hơn việc tự kiểm soát từng token.

Data Binding không đồng nghĩa với việc phải nạp toàn bộ tệp thành chuỗi. Dùng `InputStream` hoặc `Reader` vẫn cho phép Jackson đọc từ nguồn tuần tự; điểm cần phân biệt là **đối tượng kết quả có được giữ toàn bộ trong bộ nhớ hay không**.

## 4. Tree Model: chọn khi cần linh hoạt và truy cập cấu trúc động

Tree Model biểu diễn JSON thành cây nút. `ObjectNode` đại diện object, `ArrayNode` đại diện array, còn `JsonNode` là kiểu cơ sở để làm việc với các loại nút khác nhau.

Ví dụ đọc một tài liệu:

```java
JsonNode root;

try (InputStream input = Files.newInputStream(path)) {
    root = mapper.readTree(input);
}

String eventType = root.path("eventType").asText();
JsonNode payload = root.path("payload");
```

Tree Model hữu ích khi:

- JSON có cấu trúc thay đổi giữa các loại message.
- Chỉ một phần tài liệu có schema ổn định.
- Chương trình cần duyệt, tìm kiếm hoặc sửa nhiều vị trí trong JSON.
- Cần giữ nguyên phần dữ liệu chưa biết trong khi cập nhật một số trường.
- Cần xây dựng JSON động trước khi ghi ra ngoài.

Ví dụ thay đổi một thuộc tính:

```java
ObjectNode root = (ObjectNode) mapper.readTree(json);
root.put("processed", true);
root.put("source", "import-job");

String updatedJson = mapper.writeValueAsString(root);
```

Tree Model giúp thao tác thuận tiện vì chương trình có thể truy cập một nút nhiều lần. Đổi lại, toàn bộ cây thường phải tồn tại trong bộ nhớ. Với một JSON khổng lồ, việc tạo cây có thể tốn nhiều heap hơn cả việc ánh xạ trực tiếp sang một mô hình Java gọn, do cây cần các đối tượng nút và cấu trúc tham chiếu cho từng phần tử.

Một lưu ý khác: `path("field")` trả về `MissingNode` nếu không tìm thấy đường dẫn; `get("field")` có thể trả về `null` khi trường không tồn tại. Dù dùng cách nào, cần phân biệt trường bị thiếu, trường JSON có giá trị `null` và giá trị sai kiểu khi hợp đồng dữ liệu yêu cầu phân biệt các trạng thái đó.

**Nên chọn Tree Model khi** tính linh hoạt và khả năng thao tác theo cấu trúc JSON quan trọng hơn việc tiết kiệm bộ nhớ ở mức tối đa, và tài liệu đủ nhỏ để giữ trong heap.

## 5. Streaming API: chọn khi cần xử lý tuần tự và kiểm soát tài nguyên

Streaming API của Jackson Core làm việc với các token như `START_OBJECT`, `FIELD_NAME`, `VALUE_STRING`, `START_ARRAY` và `END_ARRAY`. Parser đọc lần lượt từ nguồn dữ liệu; generator ghi JSON theo từng phần.

Ưu điểm chính là chương trình có thể xử lý một phần rồi giải phóng hoặc chuyển tiếp phần đó, thay vì giữ toàn bộ tài liệu trong bộ nhớ. Cách này đặc biệt hữu ích với tệp lớn, luồng dữ liệu liên tục hoặc pipeline cần xử lý từng bản ghi.

### 5.1. Đọc một array lớn theo từng object

Giả sử tệp JSON có cấu trúc array gồm nhiều object `Student`:

```json
[
  {"id": 23, "name": "Lan", "active": true},
  {"id": 24, "name": "Minh", "active": false},
  {"id": 25, "name": "An", "active": true}
]
```

Có thể dùng parser để duyệt từng phần tử, sau đó nhờ `ObjectMapper` ánh xạ riêng từng object:

```java
import com.fasterxml.jackson.core.JsonParser;
import com.fasterxml.jackson.core.JsonToken;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;

public class LargeStudentImport {
    public static void importStudents(Path path, ObjectMapper mapper)
            throws IOException {
        try (InputStream input = Files.newInputStream(path);
             JsonParser parser = mapper.getFactory().createParser(input)) {

            if (parser.nextToken() != JsonToken.START_ARRAY) {
                throw new IOException("Expected a JSON array");
            }

            JsonToken token;
            while ((token = parser.nextToken()) != JsonToken.END_ARRAY) {
                if (token == null) {
                    throw new IOException("Unexpected end of JSON array");
                }
                if (token != JsonToken.START_OBJECT) {
                    throw new IOException("Expected a student object");
                }

                Student student = mapper.readValue(parser, Student.class);
                process(student);
            }

            if (parser.nextToken() != null) {
                throw new IOException("Unexpected content after JSON array");
            }
        }
    }

    private static void process(Student student) {
        // Validate and persist one record, or pass it to the next stage.
    }
}
```

Parser dừng ở đầu array, sau đó vòng lặp đi tới từng `START_OBJECT`. `mapper.readValue(parser, Student.class)` tiêu thụ object hiện tại và trả về một `Student`. Vòng lặp tiếp tục với token kế tiếp. Nhờ vậy, ứng dụng chỉ cần giữ bản ghi đang xử lý và những dữ liệu mà tầng nghiệp vụ chủ động tích lũy.

Đây là mô hình kết hợp: Streaming API điều khiển việc duyệt tài liệu lớn, còn Data Binding xử lý cấu trúc của từng phần tử. Code vẫn làm việc với DTO có kiểu rõ ràng mà không phải tạo `List<Student>` cho toàn bộ tệp.

### 5.2. Đọc thủ công các trường cần thiết

Nếu chỉ cần một vài trường từ mỗi object, có thể đọc token trực tiếp thay vì tạo đầy đủ DTO:

```java
try (JsonParser parser = mapper.getFactory().createParser(input)) {
    while (parser.nextToken() != null) {
        if (parser.currentToken() == JsonToken.FIELD_NAME
                && "eventType".equals(parser.currentName())) {
            parser.nextToken();
            String eventType = parser.getValueAsString();
            handleEventType(eventType);
        }
    }
}
```

Đây chỉ là minh họa cho việc tìm một trường trong luồng token. Với cấu trúc lồng nhau, code thực tế phải theo dõi vị trí object/array và xử lý đúng phạm vi của từng trường. Nếu cần bỏ qua toàn bộ một object hoặc array con mà không đọc từng token bên trong, `parser.skipChildren()` có thể giúp chuyển tới cuối cấu trúc con đó.

Đọc token thủ công đem lại quyền kiểm soát cao, nhưng dễ phát sinh code phức tạp nếu cấu trúc có nhiều nhánh, trường tùy chọn hoặc kiểu lồng nhau. Khi phần tử có mô hình ổn định, ánh xạ từng object thường dễ bảo trì hơn.

### 5.3. Ghi JSON theo luồng

Khi tạo một kết quả lớn, tránh ghép toàn bộ JSON thành một chuỗi nếu không cần thiết. Có thể dùng `JsonGenerator` để ghi array và từng object lần lượt:

```java
import com.fasterxml.jackson.core.JsonGenerator;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.OutputStream;
import java.nio.file.Files;
import java.nio.file.Path;

public static void exportStudents(
        Path path,
        Iterable<Student> students,
        ObjectMapper mapper) throws IOException {

    try (OutputStream output = Files.newOutputStream(path);
         JsonGenerator generator = mapper.getFactory().createGenerator(output)) {

        generator.writeStartArray();
        for (Student student : students) {
            generator.writeObject(student);
        }
        generator.writeEndArray();
    }
}
```

Generator ghi dấu bắt đầu array, từng object và dấu kết thúc array ra output stream. `Iterable<Student>` ở đây cần cung cấp dữ liệu theo cách phù hợp với mục tiêu tiết kiệm bộ nhớ; nếu nó đã là một `List` rất lớn được nạp sẵn, phần lưu trữ danh sách vẫn tiêu tốn heap. Streaming ở tầng JSON không tự động làm cho toàn bộ pipeline trở thành streaming.

**Nên chọn Streaming API khi:**

- Tài liệu lớn đến mức không thể hoặc không nên giữ toàn bộ object graph trong heap.
- Có thể xử lý dữ liệu theo thứ tự, từng bản ghi hoặc từng đoạn.
- Cần dừng sớm khi gặp điều kiện, bỏ qua nhánh không cần thiết hoặc kiểm soát thứ tự đọc/ghi.
- Cần giới hạn lượng dữ liệu được đưa vào từng bước của pipeline.
- Cần đọc/ghi liên tục từ file, network stream hoặc nguồn dữ liệu khác.

## 6. Chọn cách kết hợp: streaming bên ngoài, binding bên trong

Trong nhiều hệ thống nhập/xuất dữ liệu, phương án thực tế nhất là không chọn một API duy nhất cho mọi cấp cấu trúc.

Ví dụ một tệp chứa hàng triệu đơn hàng:

```text
InputStream
    |
    v
JsonParser đọc array theo thứ tự
    |
    +--> ObjectMapper ánh xạ một order thành Order DTO
    |        |
    |        v
    |     Validate bản ghi
    |        |
    |        v
    |     Ghi theo batch vào database
    |
    +--> Đọc object tiếp theo
    |
    v
Kết thúc array và xác nhận không còn nội dung thừa
```

Cách kết hợp này có một số lợi ích:

- Parser kiểm soát phạm vi tài liệu lớn và vị trí hiện tại.
- Data Binding chuyển từng phần tử thành kiểu Java có cấu trúc.
- Validation và ghi dữ liệu có thể thực hiện theo batch để cân bằng chi phí I/O.
- Bộ nhớ được giới hạn gần với kích thước một bản ghi cộng với batch đang xử lý, nếu các tầng phía sau cũng không tích lũy vô hạn.

Nếu mỗi batch có `B` bản ghi và mỗi bản ghi có object graph trung bình chiếm `M` byte, phần dữ liệu bản ghi được giữ trong bộ nhớ có thể tỷ lệ với `B × M`, cộng thêm parser buffer, batch metadata và các cấu trúc khác. Đây chỉ là mô hình ước lượng; cần đo heap thực tế vì kích thước object thay đổi theo nội dung và JVM.

Batch nhỏ giảm lượng heap và thời gian giữ dữ liệu, nhưng có thể tăng số lần gọi database. Batch lớn giảm số lần ghi nhưng tăng bộ nhớ và chi phí khi phải rollback hoặc retry. Hãy chọn kích thước batch dựa trên throughput, giới hạn bộ nhớ và khả năng giao dịch của hệ thống đích.

## 7. Chọn theo yêu cầu kiểm soát

Kích thước dữ liệu chỉ là một phần của quyết định. Mức kiểm soát cần thiết cũng ảnh hưởng đến API nên dùng.

| Yêu cầu | Data Binding | Tree Model | Streaming API |
|---|---|---|---|
| Schema ổn định, cần DTO có kiểu | Rất phù hợp | Có thể dùng nhưng phải tự lấy giá trị | Có thể kết hợp binding từng object |
| Schema động hoặc có nhiều biến thể | Cần nhiều kiểu hoặc custom deserializer | Phù hợp | Phù hợp nếu xử lý tuần tự và tự quản lý cấu trúc |
| Truy cập cùng một trường nhiều lần, ở nhiều vị trí | Qua thuộc tính Java | Thuận tiện bằng đường dẫn node | Khó hơn vì luồng chủ yếu tiến về phía trước |
| Chỉnh sửa nhiều vị trí trong tài liệu | Thường chỉnh trên object rồi serialize | Rất thuận tiện | Cần xây dựng luồng ghi mới hoặc logic chuyển đổi |
| Xử lý một lần, bỏ qua phần không cần | Có thể đọc cả object | Thường tạo cả cây | Rất phù hợp |
| Giới hạn heap khi tài liệu rất lớn | Khó nếu ánh xạ toàn bộ tài liệu | Khó nếu giữ toàn bộ cây | Phù hợp nhất nếu downstream cũng xử lý tăng dần |
| Kiểm soát token, thứ tự và cấu trúc cú pháp | Ít chi tiết hơn | Thể hiện qua cây đã parse | Kiểm soát trực tiếp nhất |
| Độ đơn giản của code nghiệp vụ | Thường cao nhất | Trung bình | Thấp hơn nếu phải tự quản lý trạng thái |

Hãy đặt câu hỏi cụ thể trước khi chọn:

1. Ứng dụng có cần toàn bộ dữ liệu cùng lúc không? Nếu có, Data Binding hoặc Tree Model có thể phù hợp, miễn là bộ nhớ đủ.
2. Có thể xử lý từng object độc lập không? Nếu có, streaming từng phần tử thường là phương án tốt.
3. Cấu trúc có ổn định và được mô tả bằng DTO không? Nếu có, Data Binding giảm code chuyển đổi thủ công.
4. Có cần giữ hoặc sửa những trường không biết trước không? Nếu có, Tree Model có thể thuận tiện khi tài liệu vừa bộ nhớ.
5. Có cần truy cập ngược, sắp xếp hoặc tham chiếu chéo giữa các phần tử không? Nếu có, streaming có thể cần thêm chỉ mục, bộ lưu tạm hoặc một bước xử lý khác.
6. Có yêu cầu giới hạn độ sâu, độ dài chuỗi, số phần tử hoặc thời gian xử lý không? Nếu có, phải thiết kế giới hạn ở cả parser lẫn các tầng phía sau.

## 8. Kiểm soát bộ nhớ và tài nguyên ở toàn bộ pipeline

Streaming API giúp tránh giữ toàn bộ tài liệu, nhưng chỉ đạt hiệu quả khi các tầng tiếp theo cũng xử lý theo luồng. Một số lỗi thiết kế thường làm mất lợi ích này:

- Đọc toàn bộ tệp bằng `Files.readString` hoặc `readAllBytes` trước khi tạo parser.
- Dùng parser streaming nhưng thêm tất cả DTO vào một `ArrayList` không giới hạn.
- Đọc từng bản ghi nhưng giữ toàn bộ kết quả trong cache hoặc log.
- Ghi output bằng cách ghép một chuỗi JSON rất lớn trong bộ nhớ.
- Đưa dữ liệu vào queue không giới hạn nhanh hơn tốc độ consumer xử lý.
- Dùng một batch quá lớn hoặc giữ nhiều batch đồng thời trong khi chờ I/O.

Một pipeline streaming cần có cơ chế điều tiết tốc độ. Nếu tầng ghi database chậm hơn tầng đọc JSON, producer phải chờ hoặc dùng queue có giới hạn. Nếu queue không giới hạn, lượng dữ liệu chờ có thể tăng đến khi hết heap dù parser đọc từng token.

Ngoài heap, cần tính đến:

- **Tài nguyên I/O:** đóng stream, parser và generator đúng lúc; xử lý timeout và lỗi đọc/ghi.
- **Giới hạn đầu vào:** giới hạn kích thước body hoặc tệp sau giải nén, số bản ghi, độ sâu lồng nhau, độ dài chuỗi và độ dài số.
- **Áp lực CPU:** JSON lồng sâu, chuỗi lớn, biểu thức chuyển đổi hoặc validation tốn kém đều ảnh hưởng throughput.
- **Backpressure:** giới hạn tốc độ đọc hoặc số phần tử đang chờ khi downstream không theo kịp.
- **Dừng và hủy:** khi request bị hủy hoặc deadline hết, pipeline cần ngừng đọc và giải phóng tài nguyên.
- **Tính nhất quán:** xử lý từng bản ghi có thể đã ghi một phần dữ liệu trước khi gặp lỗi ở bản ghi sau; cần xác định transaction, checkpoint, retry và idempotency phù hợp.

### 8.1. Giới hạn cấu trúc khi đọc dữ liệu không tin cậy

Với dữ liệu từ client hoặc nguồn bên ngoài, không nên mặc định tài liệu có kích thước và độ sâu hợp lý. Các phiên bản Jackson mới có `StreamReadConstraints` để đặt giới hạn cho một số đặc điểm của nội dung, chẳng hạn độ sâu lồng nhau, độ dài chuỗi và độ dài số.

Ví dụ với phiên bản Jackson có hỗ trợ API này:

```java
import com.fasterxml.jackson.core.JsonFactory;
import com.fasterxml.jackson.core.StreamReadConstraints;
import com.fasterxml.jackson.databind.ObjectMapper;

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

Các con số trên chỉ minh họa cách cấu hình, không phải giới hạn phù hợp cho mọi ứng dụng. Cần chọn giá trị theo hợp đồng API, kích thước dữ liệu hợp lệ và phiên bản Jackson đang dùng. Giới hạn parser cũng không thay thế giới hạn request ở HTTP server, giới hạn tổng số bản ghi hoặc validation nghiệp vụ.

Đối với JSON không tin cậy, tránh bật cơ chế polymorphic default typing một cách tùy tiện. Nếu cần giải tuần tự hóa kiểu đa hình, hãy khai báo rõ các kiểu được phép và thiết kế hợp đồng dữ liệu có kiểm soát.

### 8.2. Đóng tài nguyên đúng cách

Parser và generator thường được quản lý bằng try-with-resources:

```java
try (InputStream input = Files.newInputStream(inputPath);
     JsonParser parser = mapper.getFactory().createParser(input)) {
    // Đọc token hoặc ánh xạ từng phần tử.
}
```

```java
try (OutputStream output = Files.newOutputStream(outputPath);
     JsonGenerator generator = mapper.getFactory().createGenerator(output)) {
    // Ghi JSON tuần tự.
}
```

Mặc định, parser/generator có thể đóng nguồn hoặc đích theo cấu hình của Jackson. Khi nguồn hoặc đích được chia sẻ và vòng đời do thành phần khác quản lý, cần kiểm tra các tùy chọn auto-close phù hợp để tránh đóng tài nguyên ngoài ý muốn. Dù chọn cấu hình nào, quyền sở hữu và thời điểm đóng stream phải rõ ràng.

## 9. Hiệu năng: đo theo workload thay vì chọn theo cảm tính

Streaming thường giảm bộ nhớ đỉnh khi có thể xử lý từng phần, nhưng không đảm bảo luôn nhanh hơn. Data Binding có thể nhanh và gọn code cho DTO ổn định. Tree Model có chi phí tạo node nhưng thuận tiện khi phải truy cập nhiều lần. Streaming thủ công có thể giảm allocation nhưng tăng số nhánh và thao tác trong code.

Khi so sánh, cần dùng cùng dữ liệu và cùng công việc nghiệp vụ. Nếu một phương án chỉ parse còn phương án khác parse, validate và ghi database, kết quả thời gian không thể so sánh trực tiếp.

Một phép đo có ý nghĩa nên theo dõi:

| Chỉ số | Cho biết điều gì |
|---|---|
| Thời gian xử lý toàn bộ | Tổng độ trễ của tác vụ |
| Throughput (bản ghi/giây hoặc MB/giây) | Tốc độ xử lý ổn định |
| Heap đỉnh và allocation rate | Áp lực bộ nhớ và lượng đối tượng được tạo |
| GC pause và tần suất GC | Ảnh hưởng của cấp phát đến độ trễ |
| CPU time | Chi phí parse, chuyển đổi và validation |
| Số lần gọi downstream và batch size | Chi phí ghi dữ liệu và khả năng điều tiết |
| Hành vi khi dữ liệu lỗi | Khả năng dừng, phục hồi và giới hạn tác động |

Nên đo với nhiều trường hợp: payload nhỏ và lớn, object phẳng và lồng sâu, chuỗi ngắn và dài, dữ liệu hợp lệ và dữ liệu lỗi, cũng như các mức concurrency đại diện. Chạy đủ lâu để quan sát GC và trạng thái ổn định; một lần chạy ngắn có thể chỉ phản ánh tác động của JIT hoặc cache.

Nếu cần benchmark vi mô, có thể dùng JMH để đo riêng chi phí parse hoặc ánh xạ. Với tác vụ thực tế, hãy đo end-to-end trên pipeline gần với môi trường triển khai, bao gồm I/O và downstream. Đừng tối ưu parser khi thời gian thực tế chủ yếu nằm ở database hoặc network.

## 10. Một số tình huống lựa chọn cụ thể

### Tình huống A: request REST chứa một object nhỏ

Một endpoint nhận thông tin tài khoản với vài chục trường và payload có giới hạn. Dùng Data Binding vào request DTO là lựa chọn tự nhiên. Controller hoặc tầng service có thể xác thực và xử lý bằng các thuộc tính Java.

```java
AccountRequest request = mapper.readValue(body, AccountRequest.class);
validate(request);
accountService.update(request);
```

Nếu framework web đã tự tích hợp Jackson, thường không cần gọi `ObjectMapper` thủ công trong controller; khai báo DTO ở tham số request giúp framework thực hiện ánh xạ theo cấu hình chung.

### Tình huống B: tệp import có hàng triệu bản ghi

Không nên đọc toàn bộ thành `List<Record>`. Dùng `JsonParser` duyệt array, ánh xạ từng object thành DTO, validate và ghi theo batch. Giới hạn số bản ghi, kích thước payload và batch đang chờ. Nếu cần retry, thiết kế checkpoint hoặc khóa idempotency để không nhập trùng khi chạy lại.

### Tình huống C: gateway nhận nhiều loại event

Các event có trường chung như `type`, `timestamp`, nhưng payload khác nhau. Có thể đọc phần envelope bằng Tree Model hoặc dùng Data Binding cho một lớp envelope có trường `JsonNode payload`. Sau khi xác định `type`, chuyển payload thành DTO tương ứng. Nếu mỗi message nhỏ, Tree Model tiện dụng; nếu là một luồng event khổng lồ trong một tệp, nên dùng streaming để duyệt từng message trước khi xử lý payload.

Ví dụ mô hình envelope:

```java
public class EventEnvelope {
    private String type;
    private JsonNode payload;

    public String getType() {
        return type;
    }

    public void setType(String type) {
        this.type = type;
    }

    public JsonNode getPayload() {
        return payload;
    }

    public void setPayload(JsonNode payload) {
        this.payload = payload;
    }
}
```

Sau khi đọc envelope, chương trình có thể chọn kiểu đích theo danh sách loại event đã cho phép:

```java
switch (envelope.getType()) {
    case "student.created" -> {
        StudentCreated event = mapper.treeToValue(
            envelope.getPayload(), StudentCreated.class);
        handle(event);
    }
    case "student.disabled" -> {
        StudentDisabled event = mapper.treeToValue(
            envelope.getPayload(), StudentDisabled.class);
        handle(event);
    }
    default -> throw new IllegalArgumentException("Unsupported event type");
}
```

Việc chọn kiểu theo danh sách rõ ràng giúp hợp đồng event dễ kiểm soát hơn. Không lấy tên lớp tùy ý từ dữ liệu đầu vào để nạp hoặc khởi tạo kiểu Java.

### Tình huống D: sửa một vài trường trong file cấu hình

Một file cấu hình JSON có kích thước nhỏ, chứa nhiều nhóm thuộc tính và cần cập nhật vài node mà không muốn tạo hàng loạt DTO. Tree Model phù hợp vì có thể đọc cây, sửa node và ghi lại tài liệu. Nếu file rất lớn, cần cân nhắc một bước chuyển đổi streaming tạo tài liệu đầu ra mới, vì Tree Model giữ toàn bộ cây trong bộ nhớ.

### Tình huống E: xuất báo cáo có số lượng dòng lớn

Nếu nguồn dữ liệu trả về từng dòng hoặc từng trang, dùng `JsonGenerator` để ghi array hoặc chuỗi JSON theo từng phần. Tránh gom mọi dòng vào `List` rồi mới serialize. Cần xác định cách xử lý khi nguồn dữ liệu lỗi giữa chừng: file đầu ra có thể chưa phải JSON hoàn chỉnh, vì vậy có thể ghi vào file tạm và chỉ đổi tên sang file chính sau khi hoàn tất thành công.

## 11. Quy trình ra quyết định

Có thể áp dụng quy trình sau khi thiết kế một luồng JSON mới:

```text
Bắt đầu: xác định kích thước và cấu trúc dữ liệu
                    |
                    v
       Có cần toàn bộ tài liệu cùng lúc?
             /               \
           Có                 Không
           |                    |
           v                    v
  Payload có vừa heap?    Có thể xử lý tuần tự?
      /       \              /       \
    Có         Không        Có         Không
    |            |           |           |
    v            v           v           v
 Data Binding  Thiết kế lại  Streaming  Bổ sung lưu tạm,
 hoặc Tree     theo batch,   hoặc kết   chỉ mục hay bước
 Model         streaming     hợp binding xử lý trung gian
                    |
                    v
       Đo heap, latency, throughput,
       GC và hành vi khi lỗi trên dữ liệu thật
```

Diễn giải quy trình:

1. Xác định nguồn dữ liệu, kích thước sau giải nén, số phần tử và cấu trúc lồng nhau.
2. Xác định ứng dụng có thật sự cần truy cập toàn bộ tài liệu cùng lúc hay không.
3. Nếu không cần, kiểm tra liệu từng phần tử có thể xử lý độc lập hoặc theo batch không.
4. Nếu schema ổn định, ưu tiên ánh xạ từng phần tử vào DTO; nếu cấu trúc động và cần chỉnh sửa, cân nhắc Tree Model cho phần dữ liệu vừa bộ nhớ.
5. Nếu cần truy cập ngược, sắp xếp toàn cục hoặc tham chiếu chéo, xác định nơi lưu trữ bổ sung thay vì cố giữ mọi thứ trong heap.
6. Đặt giới hạn tài nguyên, cách xử lý lỗi và chính sách retry trước khi đưa vào production.
7. Đo bằng dữ liệu đại diện và concurrency thực tế, sau đó điều chỉnh lựa chọn hoặc batch size theo kết quả.

## 12. Bảng quyết định tham khảo

| Đặc điểm bài toán | Lựa chọn khởi đầu | Lý do |
|---|---|---|
| JSON nhỏ, schema ổn định, cần làm việc với DTO | Data Binding | Code ngắn, kiểu dữ liệu rõ |
| JSON nhỏ/vừa, schema động, cần sửa nhiều node | Tree Model | Dễ truy cập và biến đổi cấu trúc |
| JSON rất lớn, chỉ cần duyệt một lần | Streaming API | Không cần giữ toàn bộ tài liệu |
| Array lớn gồm các record có schema ổn định | Streaming + Data Binding từng record | Kết hợp tiết kiệm bộ nhớ với DTO dễ dùng |
| Luồng đầu vào cần bỏ qua nhiều nhánh không liên quan | Streaming API | Có thể skip phần không cần xử lý |
| JSON động nhưng mỗi message nhỏ | Tree Model hoặc envelope + `JsonNode` | Linh hoạt theo từng loại payload |
| Cần ghi output lớn từ nguồn tuần tự | `JsonGenerator` | Ghi tăng dần, tránh chuỗi kết quả khổng lồ |
| Cần sắp xếp hoặc tham chiếu chéo trên toàn bộ dữ liệu lớn | Streaming kết hợp storage/index | Streaming đơn thuần không cung cấp truy cập ngẫu nhiên |

Không coi bảng này là luật cứng. Một payload được gọi là “lớn” trong môi trường có heap nhỏ có thể vẫn phù hợp với Data Binding ở môi trường khác. Ngược lại, một API nhận payload vừa phải nhưng có concurrency cao cũng có thể cần giới hạn và xử lý theo luồng để tránh tổng lượng object đang sống vượt ngân sách.

## 13. Những nhầm lẫn thường gặp

### “Dùng InputStream nghĩa là đã streaming tiết kiệm bộ nhớ”

Không hẳn. `ObjectMapper.readValue(input, new TypeReference<List<Item>>() {})` đọc từ stream nhưng vẫn tạo và trả về toàn bộ danh sách. Cần phân biệt nguồn đọc tuần tự với cách ứng dụng giữ kết quả.

### “Streaming parser luôn nhanh hơn Data Binding”

Không. Streaming có thể giảm allocation và heap đỉnh, nhưng logic token thủ công có thể tốn CPU và làm code phức tạp. Hãy đo trên cùng workload.

### “Dữ liệu JSON nhỏ trên mạng thì chắc chắn nhỏ trong heap”

Không. Giải nén, chuỗi, object header, collection và tham chiếu làm lượng heap khác với số byte truyền đi.

### “Đã xử lý từng bản ghi thì pipeline không thể hết bộ nhớ”

Không. Queue, cache, batch, log hoặc danh sách kết quả không giới hạn vẫn có thể tích lũy dữ liệu. Cần điều tiết tốc độ từ đầu vào đến nơi lưu trữ.

### “Tree Model tiết kiệm bộ nhớ hơn DTO”

Không có bảo đảm như vậy. Tree Model thuận tiện và linh hoạt, nhưng mỗi node có cấu trúc đối tượng riêng. Với schema ổn định, ánh xạ sang DTO gọn có thể phù hợp hơn; với tài liệu lớn, cả hai đều có thể quá tốn bộ nhớ nếu giữ toàn bộ.

### “Streaming giải quyết luôn việc truy cập ngẫu nhiên và sắp xếp”

Streaming chủ yếu hỗ trợ xử lý tuần tự. Nếu nghiệp vụ cần truy cập ngược, sắp xếp toàn cục hoặc liên kết các bản ghi cách xa nhau, phải bổ sung storage, index, partition hoặc một bước xử lý riêng.

## 14. Kết luận về lựa chọn kiến trúc

Hãy bắt đầu từ yêu cầu của luồng dữ liệu. Khi schema ổn định và payload nằm trong giới hạn bộ nhớ, Data Binding thường đem lại code nghiệp vụ rõ ràng. Khi cấu trúc động và cần truy cập hoặc biến đổi nhiều node, Tree Model thuận tiện nếu tài liệu đủ nhỏ để giữ trong heap. Khi dữ liệu lớn, cần xử lý tuần tự hoặc cần kiểm soát chi tiết tài nguyên, Streaming API là lựa chọn phù hợp; kết hợp parser với Data Binding từng bản ghi thường cân bằng giữa hiệu quả và khả năng bảo trì.

Điểm quyết định cuối cùng là toàn bộ pipeline. Parser có thể đọc từng token, nhưng nếu ứng dụng tích lũy mọi kết quả, queue không giới hạn hoặc tạo một chuỗi output khổng lồ thì áp lực bộ nhớ vẫn còn. Hãy thiết kế giới hạn đầu vào, batch, backpressure, xử lý lỗi và vòng đời tài nguyên cùng với cách parse JSON, rồi xác nhận lựa chọn bằng số đo trên dữ liệu thực tế.
