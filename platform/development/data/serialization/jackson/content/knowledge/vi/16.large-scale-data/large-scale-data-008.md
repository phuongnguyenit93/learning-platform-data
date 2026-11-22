# Giới hạn bộ nhớ khi đọc mảng lớn

Khi một API hoặc file JSON chứa hàng trăm nghìn hay hàng triệu phần tử trong một array, cách đọc dữ liệu ảnh hưởng trực tiếp đến lượng heap mà ứng dụng cần. Nếu dùng `ObjectMapper.readValue()` để ánh xạ toàn bộ array thành `List<T>`, Jackson phải tạo object cho tất cả phần tử và danh sách giữ các object đó trong bộ nhớ. Với payload lớn hoặc nhiều request chạy đồng thời, cách này có thể gây áp lực garbage collection, tăng độ trễ hoặc dẫn đến `OutOfMemoryError`.

Jackson Streaming API cho phép đọc array tuần tự bằng `JsonParser`. Ứng dụng có thể ánh xạ từng object hiện tại thành DTO bằng `ObjectReader` hoặc `ObjectMapper`, xử lý xong rồi chuyển sang phần tử tiếp theo. Kết hợp với batch có giới hạn, queue có giới hạn và cơ chế backpressure, cách đọc này giúp lượng dữ liệu đang sống trong heap được kiểm soát.

Điểm quan trọng là streaming phải đi xuyên suốt pipeline. Parser đọc tuần tự nhưng nếu code vẫn thêm mọi DTO vào một `ArrayList`, đưa dữ liệu vào queue không giới hạn hoặc giữ entity trong persistence context của ORM, bộ nhớ vẫn tăng theo tổng số phần tử.

## 1. Vì sao đọc toàn bộ array có thể tốn nhiều bộ nhớ?

Giả sử một endpoint trả về JSON:

```json
{
  "total": 4,
  "items": [
    {"id": 101, "name": "Lan", "active": true},
    {"id": 102, "name": "Minh", "active": false},
    {"id": 103, "name": "An", "active": true},
    {"id": 104, "name": "Hoa", "active": true}
  ]
}
```

Với dữ liệu nhỏ, ánh xạ cả response vào DTO rất thuận tiện:

```java
public class ImportResponse {
    private long total;
    private List<StudentDto> items;

    // Getter và setter.
}

ImportResponse response = mapper.readValue(
    input,
    ImportResponse.class
);

for (StudentDto item : response.getItems()) {
    process(item);
}
```

Đối với array lớn, `List<StudentDto>` giữ tham chiếu đến mọi DTO. Mỗi DTO có thể chứa các chuỗi, collection và object lồng nhau. Ngoài dữ liệu JSON gốc, JVM còn phải cấp phát object header, tham chiếu, cấu trúc backing array của `ArrayList`, đối tượng chuỗi và các object con.

Vì vậy, kích thước file JSON trên đĩa không phải là lượng heap cần thiết. Ví dụ, một file 100 MB không có nghĩa ứng dụng chỉ cần thêm 100 MB heap. Object graph sau khi parse có thể lớn hơn nhiều lần, tùy cấu trúc và số lượng object.

### 1.1. Các nguồn tiêu thụ bộ nhớ

Trong một luồng đọc JSON, heap có thể được sử dụng bởi:

- Chuỗi JSON hoặc byte array nếu ứng dụng đọc toàn bộ body vào `String`, `byte[]` trước khi parse.
- Buffer nội bộ của stream, parser và decoder.
- `JsonNode` tree nếu ứng dụng gọi `readTree()` cho toàn bộ tài liệu.
- DTO và object con được tạo bởi Data Binding.
- Collection giữ các phần tử, chẳng hạn `ArrayList`, `HashMap` hoặc `LinkedHashMap`.
- Batch đang chờ ghi xuống database.
- Queue giữa producer và consumer.
- Entity và trạng thái theo dõi trong persistence context của ORM.
- Buffer của HTTP client, compression, logging và các tầng xử lý khác.

Một thiết kế tốt cần tính đến toàn bộ các phần này, không chỉ parser.

## 2. Tránh đọc toàn bộ nội dung vào String hoặc byte array

Ngay cả khi cuối cùng muốn dùng Data Binding, hãy ưu tiên truyền `InputStream` trực tiếp cho Jackson thay vì tự đọc toàn bộ file thành chuỗi.

Không nên làm với file lớn:

```java
String json = Files.readString(path);
List<StudentDto> students = mapper.readValue(
    json,
    new TypeReference<List<StudentDto>>() {}
);
```

Đoạn code này có thể giữ đồng thời:

1. Chuỗi JSON đầy đủ.
2. Danh sách DTO đã tạo.
3. Các object con và chuỗi Java của từng DTO.

Đọc từ stream giảm nhu cầu giữ bản sao chuỗi JSON:

```java
try (InputStream input = Files.newInputStream(path)) {
    List<StudentDto> students = mapper.readValue(
        input,
        new TypeReference<List<StudentDto>>() {}
    );
}
```

Tuy nhiên, ví dụ thứ hai vẫn tạo và giữ toàn bộ `List<StudentDto>`. Nó giảm một phần bộ nhớ đầu vào nhưng chưa giải quyết việc giữ toàn bộ object graph.

Để giới hạn bộ nhớ theo số lượng phần tử đang xử lý, cần đọc array theo từng object.

## 3. Đọc array tuần tự bằng JsonParser

Streaming API của Jackson Core đọc JSON theo token. Với một array ở cấp gốc, các token chính có dạng:

```text
START_ARRAY
  START_OBJECT
    FIELD_NAME
    VALUE_NUMBER_INT
    FIELD_NAME
    VALUE_STRING
  END_OBJECT
  START_OBJECT
    ...
  END_OBJECT
END_ARRAY
```

Parser không cần tạo toàn bộ array thành một cấu trúc Java. Ứng dụng có thể dừng ở từng `START_OBJECT`, nhờ Databind ánh xạ object đó thành DTO rồi xử lý ngay.

Ví dụ DTO:

```java
public class StudentDto {
    private long id;
    private String name;
    private boolean active;

    public StudentDto() {
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

Hàm đọc từng phần tử:

```java
import com.fasterxml.jackson.core.JsonParser;
import com.fasterxml.jackson.core.JsonToken;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.ObjectReader;
import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;

public final class StudentFileReader {
    private final ObjectReader studentReader;

    public StudentFileReader(ObjectMapper mapper) {
        this.studentReader = mapper.readerFor(StudentDto.class);
    }

    public void read(Path path) throws IOException {
        try (InputStream input = Files.newInputStream(path);
             JsonParser parser = studentReader.getFactory().createParser(input)) {

            if (parser.nextToken() != JsonToken.START_ARRAY) {
                throw new IOException("Expected a JSON array");
            }

            while (true) {
                JsonToken token = parser.nextToken();

                if (token == JsonToken.END_ARRAY) {
                    break;
                }
                if (token == null) {
                    throw new IOException("Unexpected end of JSON array");
                }
                if (token != JsonToken.START_OBJECT) {
                    throw new IOException("Each item must be an object");
                }

                StudentDto student = studentReader.readValue(parser);
                process(student);
            }

            if (parser.nextToken() != null) {
                throw new IOException("Unexpected content after the array");
            }
        }
    }

    private void process(StudentDto student) {
        // Validate and handle one student.
    }
}
```

`ObjectReader` được tạo một lần cho kiểu `StudentDto` và dùng lại. Khi parser ở `START_OBJECT`, `readValue(parser)` đọc object hiện tại. Sau khi ánh xạ xong, parser đã tiêu thụ object đó; vòng lặp gọi `nextToken()` để đến phần tử kế tiếp.

Không gọi thêm `nextToken()` ngay sau `readValue()` để tìm `END_OBJECT`, vì Databind đã đọc hết object. Làm như vậy có thể bỏ qua token đầu tiên của phần tử tiếp theo.

## 4. Đọc một array nằm trong object lớn

Nhiều API không trả về array ở cấp gốc mà bọc nó trong một envelope:

```json
{
  "batchId": "B-2026-001",
  "source": "partner-a",
  "items": [
    {"id": 101, "name": "Lan", "active": true},
    {"id": 102, "name": "Minh", "active": false}
  ],
  "diagnostics": {
    "trace": "large optional metadata"
  }
}
```

Có thể dùng parser đọc các field ở cấp ngoài, stream `items` và bỏ qua `diagnostics`:

```java
public void readEnvelope(InputStream input, ObjectMapper mapper)
        throws IOException {

    ObjectReader itemReader = mapper.readerFor(StudentDto.class);
    String batchId = null;
    boolean itemsSeen = false;

    try (JsonParser parser = mapper.getFactory().createParser(input)) {
        if (parser.nextToken() != JsonToken.START_OBJECT) {
            throw new IOException("Expected an object envelope");
        }

        while (true) {
            JsonToken token = parser.nextToken();
            if (token == JsonToken.END_OBJECT) {
                break;
            }
            if (token == null) {
                throw new IOException("Unexpected end of envelope");
            }
            if (token != JsonToken.FIELD_NAME) {
                throw new IOException("Expected a field name");
            }

            String fieldName = parser.currentName();
            JsonToken valueToken = parser.nextToken();

            if ("batchId".equals(fieldName)) {
                if (valueToken != JsonToken.VALUE_STRING) {
                    throw new IOException("batchId must be a string");
                }
                batchId = parser.getText();
            } else if ("items".equals(fieldName)) {
                if (valueToken != JsonToken.START_ARRAY) {
                    throw new IOException("items must be an array");
                }
                itemsSeen = true;
                readItems(parser, itemReader, batchId);
            } else {
                parser.skipChildren();
            }
        }

        if (parser.nextToken() != null) {
            throw new IOException("Unexpected trailing content");
        }
    }

    if (!itemsSeen) {
        throw new IOException("Required items array is missing");
    }
}

private void readItems(
        JsonParser parser,
        ObjectReader itemReader,
        String batchId) throws IOException {

    while (true) {
        JsonToken token = parser.nextToken();
        if (token == JsonToken.END_ARRAY) {
            return;
        }
        if (token == null) {
            throw new IOException("Unexpected end of items array");
        }
        if (token != JsonToken.START_OBJECT) {
            throw new IOException("Each item must be an object");
        }

        StudentDto item = itemReader.readValue(parser);
        process(batchId, item);
    }
}
```

Ví dụ minh họa cách duyệt envelope, nhưng cũng cho thấy một vấn đề thiết kế: JSON object không nên được xem là có thứ tự field cố định. Nếu `items` xuất hiện trước `batchId`, biến `batchId` lúc đó vẫn null. Với giao thức mà metadata cần có trước khi xử lý record, hãy thiết kế để không phụ thuộc thứ tự khóa, chẳng hạn ghi metadata ở một header riêng, dùng bước staging, hoặc quy định và kiểm soát thứ tự ở producer nếu giao thức nội bộ cho phép.

Nếu metadata chỉ cần gắn vào từng record nhưng thứ tự không bảo đảm, có thể lưu batch nhỏ vào vùng đệm rồi xử lý khi đã có đủ metadata. Không giữ vô hạn mọi record chỉ để chờ một field ở cuối tài liệu.

## 5. Ước lượng bộ nhớ đang sử dụng

Với Data Binding toàn bộ array, lượng heap tăng theo tổng số phần tử và kích thước object graph:

```text
Heap cho danh sách toàn bộ
  ~ ArrayList + tất cả DTO + tất cả field/collection/string con
```

Với streaming và xử lý từng record:

```text
Heap cho xử lý tuần tự
  ~ parser buffers
  + DTO hiện tại
  + dữ liệu tạm khi xử lý DTO
  + bộ đệm downstream có giới hạn
```

Với batch size `B` và kích thước object graph trung bình mỗi record `M`, phần dữ liệu record đang được giữ có thể ước lượng gần với `B × M`, cộng thêm buffer, metadata và overhead của các tầng khác. Đây chỉ là mô hình khái quát; kích thước thực tế phụ thuộc JVM, class layout, số field, độ dài chuỗi, collection và cách xử lý.

Ví dụ, nếu mỗi record sau khi ánh xạ chiếm trung bình 4 KB và batch có 500 record, dữ liệu record trong batch có thể xấp xỉ 2 MB, chưa tính overhead khác. Nếu giữ 500.000 record, phần dữ liệu tương ứng có thể tăng lên hàng GB. Không nên dùng kích thước JSON trên đĩa để suy ra chính xác heap.

Ngoài batch, concurrency cũng nhân lượng bộ nhớ cần thiết. Nếu mỗi request có thể giữ 20 MB và hệ thống xử lý đồng thời 100 request, chỉ phần dữ liệu đó đã có thể chiếm khoảng 2 GB. Vì vậy, giới hạn đồng thời, queue và batch phải được thiết kế cùng nhau.

## 6. Xử lý từng phần tử ngay sau khi đọc

Cách đơn giản nhất để giới hạn bộ nhớ là xử lý record ngay sau khi ánh xạ:

```java
StudentDto item = itemReader.readValue(parser);
validate(item);
repository.save(item);
```

Ưu điểm:

- Không cần giữ toàn bộ array.
- Dễ xác định record nào gây lỗi.
- Có thể dừng sớm khi gặp điều kiện hoặc lỗi nghiêm trọng.
- Bộ nhớ ứng dụng chủ yếu phụ thuộc vào record hiện tại và tầng lưu trữ.

Nhược điểm là ghi từng record có thể tạo nhiều round-trip đến database hoặc dịch vụ bên ngoài. Nếu mỗi thao tác lưu có chi phí cố định lớn, batch thường hiệu quả hơn.

## 7. Dùng batch có giới hạn

Batch gom một số record trước khi ghi. Sau khi batch được xử lý xong, danh sách được giải phóng hoặc tái sử dụng.

```java
private static final int BATCH_SIZE = 500;

List<StudentDto> batch = new ArrayList<>(BATCH_SIZE);

while (true) {
    JsonToken token = parser.nextToken();

    if (token == JsonToken.END_ARRAY) {
        break;
    }
    if (token == null) {
        throw new IOException("Unexpected end of array");
    }
    if (token != JsonToken.START_OBJECT) {
        throw new IOException("Expected an object item");
    }

    StudentDto item = itemReader.readValue(parser);
    batch.add(item);

    if (batch.size() == BATCH_SIZE) {
        repository.saveBatch(batch);
        batch.clear();
    }
}

if (!batch.isEmpty()) {
    repository.saveBatch(batch);
    batch.clear();
}
```

Batch size là giới hạn số phần tử đang chờ xử lý. Chọn giá trị phù hợp bằng cách đo:

- Kích thước object graph trung bình và trường hợp lớn nhất.
- Heap khả dụng và mức concurrency dự kiến.
- Chi phí mỗi lần gọi database hoặc service.
- Kích thước transaction và giới hạn của driver/database.
- Thời gian retry nếu một batch thất bại.

Batch quá nhỏ có thể làm tăng số lần gọi database và giảm throughput. Batch quá lớn làm tăng heap, thời gian giữ transaction và chi phí xử lý lại khi lỗi. Một giá trị cố định không phù hợp với mọi hệ thống.

Lưu ý `batch.clear()` chỉ xóa tham chiếu khỏi danh sách. Nó không buộc JVM thu gom rác ngay lập tức. Khi không còn reference đến DTO, garbage collector có thể thu hồi chúng ở thời điểm phù hợp.

## 8. Giới hạn persistence context khi dùng JPA/Hibernate

Một lỗi phổ biến là streaming JSON theo từng record nhưng vẫn tạo entity và giữ chúng trong persistence context của ORM. Hibernate thường theo dõi entity đã được load hoặc persist trong một `Session`/`EntityManager`. Nếu import hàng triệu entity trong một transaction mà không flush/clear, bộ nhớ vẫn có thể tăng theo tổng số entity.

Với batch insert/update, có thể dùng chu kỳ flush và clear:

```java
int batchSize = 500;
int count = 0;

for (StudentDto dto : batch) {
    StudentEntity entity = mapper.toEntity(dto);
    entityManager.persist(entity);
    count++;

    if (count % batchSize == 0) {
        entityManager.flush();
        entityManager.clear();
    }
}

entityManager.flush();
entityManager.clear();
```

`flush()` đẩy các thay đổi đang chờ xuống database. `clear()` detach các entity khỏi persistence context, giúp giảm số object ORM tiếp tục theo dõi. Cần hiểu rằng `clear()` ảnh hưởng mọi entity đang managed trong persistence context đó; không gọi tùy tiện nếu cùng transaction còn cần thao tác với các entity khác.

Ngoài ra, transaction quá lớn vẫn có thể giữ lock, transaction log hoặc tài nguyên database trong thời gian dài. Chia transaction theo batch có thể giảm tài nguyên, nhưng thay đổi semantics atomicity: nếu batch thứ năm lỗi, bốn batch trước có thể đã commit. Cần quyết định rõ import phải atomic toàn bộ hay chấp nhận commit từng batch với cơ chế retry/idempotency.

## 9. Backpressure và queue có giới hạn

Trong pipeline bất đồng bộ, parser có thể đọc nhanh hơn consumer ghi database. Nếu producer đẩy DTO vào queue không giới hạn, queue sẽ giữ ngày càng nhiều object và làm heap tăng.

Ví dụ không an toàn:

```java
BlockingQueue<StudentDto> queue = new LinkedBlockingQueue<>();
```

Constructor không truyền capacity tạo queue gần như không giới hạn theo thực tế bộ nhớ. Khi consumer chậm, producer vẫn tiếp tục đọc và thêm phần tử.

Dùng queue có giới hạn:

```java
BlockingQueue<StudentDto> queue = new ArrayBlockingQueue<>(1_000);
```

Producer dùng `put()` sẽ chờ khi queue đầy:

```java
StudentDto item = itemReader.readValue(parser);
queue.put(item);
```

Consumer lấy phần tử để xử lý:

```java
while (running || !queue.isEmpty()) {
    StudentDto item = queue.poll(100, TimeUnit.MILLISECONDS);
    if (item != null) {
        process(item);
    }
}
```

Queue có giới hạn tạo backpressure tự nhiên: khi downstream chậm, producer bị chặn và tốc độ đọc giảm theo. Cần bổ sung cơ chế dừng, truyền lỗi, timeout và đóng queue đúng cách cho ứng dụng thực tế; ví dụ trên chỉ minh họa nguyên tắc.

Nếu xử lý tuần tự trong cùng thread, lời gọi `process(item)` đã tạo backpressure đơn giản: parser chỉ đọc record tiếp theo sau khi record hiện tại xử lý xong. Chỉ dùng concurrency khi throughput thực sự cần và đã kiểm soát được số phần tử đang chờ.

## 10. Giới hạn kích thước đầu vào và cấu trúc JSON

Streaming không có nghĩa là có thể nhận dữ liệu lớn vô hạn. Parser vẫn phải đọc token và có thể gặp chuỗi rất dài, số rất lớn hoặc cấu trúc lồng sâu.

Nên giới hạn:

- Kích thước body/file sau giải nén.
- Số lượng phần tử tối đa trong một lần import nếu nghiệp vụ có giới hạn.
- Độ sâu lồng nhau.
- Độ dài chuỗi và số.
- Thời gian xử lý và tốc độ nhận dữ liệu.
- Kích thước batch và queue.
- Số tác vụ import chạy đồng thời.

Các phiên bản Jackson mới hỗ trợ `StreamReadConstraints`:

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

Các giá trị trong ví dụ chỉ mang tính minh họa; chọn giới hạn theo hợp đồng và phiên bản Jackson thực tế. Parser constraint không thay thế giới hạn request ở HTTP server, giới hạn giải nén, giới hạn tổng số record hoặc timeout của job.

Nếu file được nén, hãy chú ý kích thước sau giải nén. Một file nén nhỏ có thể mở rộng thành dữ liệu rất lớn. Giới hạn byte trước và sau giải nén để tránh tiêu thụ tài nguyên ngoài dự kiến.

## 11. Quản lý stream và tài nguyên

Đọc file bằng try-with-resources:

```java
try (InputStream input = Files.newInputStream(path);
     JsonParser parser = mapper.getFactory().createParser(input)) {
    // Đọc array và xử lý từng phần tử.
}
```

Nếu method nhận `InputStream` từ caller, cần xác định ai sở hữu stream và ai đóng nó. Khi parser đóng nguồn theo cấu hình mặc định, caller có thể không dùng stream tiếp được. Nếu nguồn do caller quản lý vòng đời, hãy cấu hình auto-close phù hợp với phiên bản Jackson hoặc bọc stream để kiểm soát việc đóng.

Với HTTP response body, nên đọc và đóng body đúng cách để giải phóng connection. Không giữ parser hoặc stream mở lâu hơn thời gian xử lý cần thiết.

## 12. Xử lý lỗi giữa chừng và khả năng chạy lại

Khi đọc mảng lớn, lỗi có thể xuất hiện sau khi nhiều phần tử đã được lưu. Cần chọn chính sách trước khi triển khai:

- **Fail fast:** dừng toàn bộ job khi gặp record sai.
- **Skip record lỗi:** ghi nhận lỗi theo index/ID và tiếp tục nếu nghiệp vụ cho phép.
- **Staging:** ghi dữ liệu vào vùng tạm, chỉ công bố sau khi toàn bộ file hợp lệ.
- **Commit theo batch:** mỗi batch là một đơn vị giao dịch; lỗi sau đó không tự rollback các batch đã commit.
- **Checkpoint:** lưu vị trí hoặc khóa cuối cùng đã xử lý để có thể tiếp tục, nếu nguồn và định dạng cho phép.

Không nên coi byte offset trong file là checkpoint ổn định nếu parser đang đọc stream có buffering, compression hoặc encoding phức tạp. Một checkpoint theo khóa nghiệp vụ hoặc record index có thể dễ quản lý hơn, nhưng cần bảo đảm nguồn không thay đổi giữa các lần chạy.

Để retry an toàn, có thể dùng idempotency key hoặc unique key theo batch/record. Nếu job chạy lại từ đầu, những record đã được xử lý cần được nhận diện để tránh tạo dữ liệu trùng.

## 13. Ví dụ hoàn chỉnh: đọc file lớn và ghi theo batch

Ví dụ sau kết hợp parser, ObjectReader và batch giới hạn. Phần repository là interface ứng dụng minh họa; cách transaction cụ thể phụ thuộc hệ thống lưu trữ.

```java
import com.fasterxml.jackson.core.JsonParser;
import com.fasterxml.jackson.core.JsonToken;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.ObjectReader;
import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;

public final class LargeArrayImporter {
    private static final int BATCH_SIZE = 500;

    private final ObjectReader itemReader;
    private final StudentRepository repository;

    public LargeArrayImporter(
            ObjectMapper mapper,
            StudentRepository repository) {
        this.itemReader = mapper.readerFor(StudentDto.class);
        this.repository = repository;
    }

    public long importFile(Path path) throws IOException {
        long processed = 0;
        List<StudentDto> batch = new ArrayList<>(BATCH_SIZE);

        try (InputStream input = Files.newInputStream(path);
             JsonParser parser = itemReader.getFactory().createParser(input)) {

            if (parser.nextToken() != JsonToken.START_ARRAY) {
                throw new IOException("Expected a JSON array at root");
            }

            while (true) {
                JsonToken token = parser.nextToken();

                if (token == JsonToken.END_ARRAY) {
                    break;
                }
                if (token == null) {
                    throw new IOException("Unexpected end of JSON array");
                }
                if (token != JsonToken.START_OBJECT) {
                    throw new IOException("Every array item must be an object");
                }

                StudentDto item = itemReader.readValue(parser);
                validate(item);
                batch.add(item);
                processed++;

                if (batch.size() == BATCH_SIZE) {
                    repository.saveBatch(batch);
                    batch.clear();
                }
            }

            if (parser.nextToken() != null) {
                throw new IOException("Unexpected trailing JSON content");
            }

            if (!batch.isEmpty()) {
                repository.saveBatch(batch);
                batch.clear();
            }
        }

        return processed;
    }

    private void validate(StudentDto item) {
        if (item.getId() <= 0) {
            throw new IllegalArgumentException("Student id must be positive");
        }
        if (item.getName() == null || item.getName().isBlank()) {
            throw new IllegalArgumentException("Student name is required");
        }
    }
}
```

Trong thiết kế này:

1. `ObjectReader` được tạo một lần và tái sử dụng.
2. Parser đọc từ file stream, không cần tạo `String` chứa toàn bộ JSON.
3. Mỗi phần tử được ánh xạ thành một `StudentDto`.
4. DTO được validate trước khi đưa vào batch.
5. Khi đủ 500 phần tử, repository lưu batch rồi danh sách được clear.
6. Batch cuối cùng nhỏ hơn 500 cũng được lưu sau khi parser kết thúc array.
7. Parser kiểm tra không còn nội dung thừa sau array.

`saveBatch()` cần xử lý dữ liệu đồng bộ hoặc có cơ chế ownership rõ ràng. Nếu phương thức chỉ đưa reference của danh sách vào một tác vụ bất đồng bộ rồi trả về, `batch.clear()` có thể xóa dữ liệu trước khi consumer sử dụng. Trong trường hợp bất đồng bộ, phải chuyển một bản sao bất biến của batch hoặc chuyển quyền sở hữu một collection mới cho consumer, đồng thời dùng queue có giới hạn.

## 14. Đọc array theo trang từ API thay vì một response khổng lồ

Nếu API nguồn hỗ trợ pagination, thường nên lấy dữ liệu theo trang thay vì tải một array khổng lồ trong một request. Ví dụ:

```text
GET /students?page=0&size=500
GET /students?page=1&size=500
GET /students?page=2&size=500
...
```

Lợi ích:

- Giới hạn kích thước mỗi response.
- Có thể retry một trang thay vì tải lại toàn bộ.
- Dễ theo dõi tiến độ và checkpoint theo page/cursor.
- Có thể điều chỉnh tốc độ gọi API theo khả năng xử lý downstream.

Tuy nhiên, pagination cần quy tắc sắp xếp ổn định. Offset pagination có thể bỏ sót hoặc lặp record khi dữ liệu nguồn thay đổi giữa các lần gọi. Với dữ liệu biến động lớn, cursor/keyset pagination thường đáng cân nhắc. Dù mỗi page nhỏ, ứng dụng vẫn nên xử lý page theo batch và không tích lũy mọi trang vào một danh sách tổng.

## 15. Đo và theo dõi bộ nhớ

Không nên chọn batch size hoặc concurrency chỉ bằng cảm tính. Hãy đo trên payload đại diện và môi trường gần production.

Các chỉ số hữu ích:

| Chỉ số | Ý nghĩa |
|---|---|
| Heap used / peak heap | Lượng heap đang sử dụng và mức đỉnh |
| Allocation rate | Tốc độ cấp phát object |
| GC frequency và pause | Áp lực garbage collection và ảnh hưởng đến độ trễ |
| Số record/giây | Throughput xử lý |
| Thời gian mỗi batch | Chi phí ghi và khả năng downstream |
| Queue depth | Số phần tử đang chờ consumer |
| Số import đồng thời | Mức nhân tải bộ nhớ |
| Kích thước payload sau giải nén | Lượng dữ liệu parser thực sự phải đọc |

Hãy thử nhiều trường hợp: record nhỏ và lớn, object phẳng và lồng sâu, chuỗi dài, batch size khác nhau, concurrency khác nhau và downstream nhanh/chậm. Một benchmark chỉ parse không phản ánh đầy đủ import thực tế nếu công việc thật còn validate, mapping entity và ghi database.

## 16. Các lỗi thường gặp

### Dùng InputStream nhưng vẫn đọc toàn bộ List

`mapper.readValue(input, new TypeReference<List<T>>() {})` đọc từ stream nhưng vẫn tạo toàn bộ danh sách. InputStream tránh một bản sao chuỗi JSON, không tự biến Data Binding thành xử lý từng phần tử.

### Dùng parser nhưng vẫn giữ mọi DTO

Nếu thêm từng record vào `allRecords`, heap vẫn tăng theo tổng số record. Xử lý ngay hoặc dùng batch có giới hạn.

### Tạo queue không giới hạn

Producer có thể đọc nhanh hơn consumer và tích lũy object trong queue. Dùng queue có capacity và backpressure.

### Không clear persistence context

Hibernate có thể giữ entity trong session dù danh sách DTO đã clear. Với batch ORM, cân nhắc `flush()` và `clear()` theo chu kỳ.

### Dùng batch quá lớn

Batch lớn làm tăng heap và chi phí retry. Chọn batch dựa trên đo đạc và giới hạn transaction.

### Gọi nextToken sai vị trí

Sau khi `readValue(parser, Type.class)` đọc object hiện tại, không gọi thêm một lần để tìm token kết thúc. Vòng lặp ngoài tiến tiếp bằng một lần `nextToken()`.

### Quên xử lý batch cuối

Sau khi array kết thúc, batch còn ít hơn kích thước quy định vẫn phải được lưu.

### Đóng stream sai tầng

Parser có thể đóng nguồn theo cấu hình. Xác định rõ caller hay importer sở hữu stream.

### Không giới hạn dữ liệu đã giải nén

File nén nhỏ có thể mở rộng thành payload lớn. Đặt giới hạn ở cả tầng truyền tải và tầng sau giải nén.

## 17. Quy trình thiết kế luồng đọc mảng lớn

1. Xác định kích thước dữ liệu tối đa, số phần tử và kích thước record điển hình/lớn nhất.
2. Kiểm tra nguồn có hỗ trợ pagination hoặc cursor hay không; ưu tiên chia nguồn nếu hợp đồng cho phép.
3. Tránh `readString`, `readAllBytes` và ánh xạ toàn bộ array thành `List<T>` khi dữ liệu lớn.
4. Dùng `JsonParser` để duyệt array và `ObjectReader` để ánh xạ từng object.
5. Validate và xử lý từng phần tử ngay khi có thể.
6. Nếu cần batch, đặt giới hạn số phần tử và cân nhắc kích thước byte thực tế.
7. Nếu dùng ORM, quản lý persistence context bằng flush/clear phù hợp.
8. Nếu xử lý bất đồng bộ, dùng queue có giới hạn và backpressure.
9. Giới hạn file/body sau giải nén, độ sâu, độ dài chuỗi/số, thời gian và concurrency.
10. Xác định transaction, checkpoint, idempotency và cách xử lý lỗi giữa chừng.
11. Đo heap, allocation, GC, queue depth và throughput trên dữ liệu đại diện.

## 18. Bảng chọn cách đọc

| Tình huống | Cách tiếp cận |
|---|---|
| Array nhỏ, có giới hạn rõ | Data Binding thành `List<T>` |
| Array lớn, phần tử có schema ổn định | `JsonParser` + `ObjectReader` cho từng phần tử |
| Array lớn, cần ghi database theo nhóm | Streaming + batch có giới hạn |
| File lớn nhưng API nguồn hỗ trợ cursor/page | Đọc từng page/cursor và xử lý độc lập |
| Event có payload khác nhau theo loại | Streaming từng event, binding theo type hoặc Tree Model cho event nhỏ |
| Downstream chậm hơn parser | Queue giới hạn và backpressure |
| Dùng Hibernate/JPA cho hàng loạt entity | Batch + `flush()`/`clear()` và transaction có chủ đích |
| Cần giữ toàn bộ dữ liệu để sắp xếp/tổng hợp | Dùng storage/index trung gian hoặc partition thay vì cố giữ mọi object trong heap |

## 19. Kết luận

Đọc một mảng JSON lớn thành `List<T>` rất thuận tiện nhưng giữ toàn bộ object graph trong heap. Khi dữ liệu có thể tăng lớn, hãy dùng `JsonParser` để duyệt array tuần tự và `ObjectReader` để ánh xạ từng object. Xử lý ngay hoặc gom batch có giới hạn rồi giải phóng tham chiếu sau khi ghi thành công.

Hãy kiểm soát cả những tầng phía sau parser: persistence context, queue, batch, concurrency và dữ liệu tạm. Đặt giới hạn cho payload sau giải nén, cấu trúc lồng nhau và thời gian xử lý. Cuối cùng, xác định rõ cách xử lý lỗi và transaction để job có thể dừng hoặc chạy lại an toàn. Streaming chỉ thực sự giới hạn bộ nhớ khi toàn bộ pipeline không tích lũy dữ liệu vô hạn.
