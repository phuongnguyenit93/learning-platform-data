# Xử lý tệp JSON lớn theo từng bản ghi với bộ nhớ giới hạn

## 1. Vì sao không nên đọc toàn bộ tệp vào heap?

Một cách đơn giản để đọc JSON là deserialize toàn bộ tài liệu thành List hoặc JsonNode:

~~~java
List<Event> events = mapper.readValue(
        input,
        new TypeReference<List<Event>>() {}
);

for (Event event : events) {
    process(event);
}
~~~

Cách này dễ viết và phù hợp với payload nhỏ. Nhưng khi tệp chứa hàng triệu bản ghi, toàn bộ object graph được tạo và giữ trong bộ nhớ cùng lúc. Heap cần đủ chỗ cho:

- Buffer đọc dữ liệu.
- Danh sách chứa các phần tử.
- Từng object Event và object con.
- String, collection và byte array bên trong mỗi record.
- Object trung gian do validation hoặc transformation tạo ra.
- Buffer hoặc queue của bước xử lý tiếp theo.

Một tệp JSON 500 MB không nhất thiết chỉ cần 500 MB heap. Object Java thường tốn nhiều bộ nhớ hơn phần JSON văn bản vì có header object, reference, capacity của collection và nội dung string. Một payload có nhiều field nhỏ có thể tạo ra lượng object rất lớn.

**Streaming theo từng bản ghi** giúp chỉ giữ một record hoặc một batch nhỏ trong bộ nhớ tại một thời điểm. Khi record đã được xử lý và không còn tham chiếu, nó trở thành đối tượng đủ điều kiện để garbage collector thu hồi.

Streaming không làm bộ nhớ bằng 0. Nó giới hạn lượng dữ liệu được giữ đồng thời. Nếu một record đơn lẻ rất lớn, hoặc ứng dụng giữ lại mọi kết quả đã xử lý, memory vẫn có thể tăng cao.

## 2. Chọn cấu trúc đầu vào có ranh giới record rõ ràng

Trước khi viết parser, cần xác định tệp đang dùng kiểu framing nào.

### JSON array chứa nhiều record

~~~json
[
  {"id": 1, "type": "created"},
  {"id": 2, "type": "updated"},
  {"id": 3, "type": "deleted"}
]
~~~

Toàn bộ array là một JSON document. Jackson có thể duyệt từng phần tử bằng JsonParser. Mỗi phần tử có thể được deserialize thành POJO rồi xử lý ngay.

### NDJSON: mỗi dòng là một JSON document

~~~text
{"id":1,"type":"created"}
{"id":2,"type":"updated"}
{"id":3,"type":"deleted"}
~~~

NDJSON (Newline Delimited JSON) đặt một JSON value trên mỗi dòng. Mỗi dòng có thể được parse độc lập, vì vậy việc cách ly một dòng sai cú pháp dễ hơn so với một JSON array lớn.

Producer phải tuân thủ quy ước: mỗi record nằm trên một dòng vật lý; newline bên trong string phải được escape. Một JSON object pretty-print nhiều dòng không phải một record NDJSON hợp lệ.

### Nhiều JSON value nối tiếp

Một số luồng chứa nhiều JSON value liên tiếp, được phân cách bằng whitespace:

~~~text
{"id":1} {"id":2} {"id":3}
~~~

Jackson có thể đọc các root value nối tiếp bằng parser. Tuy nhiên, nếu một value sai cú pháp, việc xác định ranh giới value tiếp theo không tự động an toàn. Cần framing protocol rõ ràng nếu muốn phục hồi sau lỗi.

| Cấu trúc | Ranh giới record | Khả năng cách ly record lỗi |
|---|---|---|
| JSON array | Phần tử trong array | Tốt với lỗi validation sau parse; lỗi cú pháp thường phải dừng document |
| NDJSON | Dòng vật lý | Có thể bỏ qua dòng sai và tiếp tục dòng kế |
| JSON values nối tiếp | Parser token/whitespace | Phụ thuộc khả năng parse hoàn chỉnh từng value và framing |

## 3. Vai trò của Jackson Streaming API

Jackson Core cung cấp JsonParser để đọc token tuần tự thay vì dựng toàn bộ cây JSON. Một số token thường gặp:

| Token | Ý nghĩa |
|---|---|
| START_ARRAY / END_ARRAY | Bắt đầu/kết thúc array |
| START_OBJECT / END_OBJECT | Bắt đầu/kết thúc object |
| FIELD_NAME | Tên property trong object |
| VALUE_STRING | Giá trị string |
| VALUE_NUMBER_INT | Số nguyên |
| VALUE_NUMBER_FLOAT | Số thập phân |
| VALUE_TRUE / VALUE_FALSE | Boolean |
| VALUE_NULL | Null |

Parser duy trì vị trí hiện tại trong tài liệu. Ứng dụng gọi nextToken() để tiến đến token kế tiếp và chỉ deserialize giá trị cần thiết.

Khi cần đọc một record thành POJO, có thể kết hợp Streaming API với Databind:

~~~java
Event event = mapper.readValue(parser, Event.class);
~~~

Nếu parser đang ở token bắt đầu record, ObjectMapper đọc value đó thành Event. Sau khi hoàn tất, parser đứng ở cuối value vừa đọc; vòng lặp tiếp tục gọi nextToken() để đến phần tử tiếp theo.

## 4. Chuẩn bị ObjectMapper dùng chung

Không tạo ObjectMapper cho từng record. Mapper có cache serializer/deserializer và nên được cấu hình một lần rồi tái sử dụng:

~~~java
private static final ObjectMapper MAPPER =
        JsonMapper.builder().build();
~~~

Trong ứng dụng framework-managed, inject mapper đã được cấu hình. Không tự tạo mapper mặc định nếu production đang dùng module, naming strategy, mix-in hoặc coercion policy riêng.

ObjectMapper đã cấu hình xong có thể được chia sẻ giữa nhiều thread. Tuy nhiên, một JsonParser cụ thể chỉ nên được một luồng sử dụng tại một thời điểm. Không dùng chung parser cho nhiều worker.

## 5. Đọc JSON array theo từng record

Ví dụ tệp records.json có một array các Event. Đọc từng object và xử lý ngay:

~~~java
import com.fasterxml.jackson.core.JsonParser;
import com.fasterxml.jackson.core.JsonToken;
import com.fasterxml.jackson.databind.ObjectMapper;

import java.io.IOException;
import java.nio.file.Path;

public class LargeArrayReader {
    private final ObjectMapper mapper;

    public LargeArrayReader(ObjectMapper mapper) {
        this.mapper = mapper;
    }

    public void process(Path path) throws IOException {
        try (JsonParser parser =
                     mapper.getFactory().createParser(path.toFile())) {

            if (parser.nextToken() != JsonToken.START_ARRAY) {
                throw new IOException("Expected a top-level JSON array");
            }

            long recordNumber = 0;
            JsonToken token;

            while ((token = parser.nextToken()) != JsonToken.END_ARRAY) {
                if (token == null) {
                    throw new IOException("Unexpected end of JSON array");
                }

                Event event = mapper.readValue(parser, Event.class);
                recordNumber++;
                processOne(event, recordNumber);
            }

            if (parser.nextToken() != null) {
                throw new IOException(
                        "Unexpected content after the top-level array"
                );
            }
        }
    }

    private void processOne(Event event, long recordNumber) {
        // Validate, transform and persist one record.
    }
}
~~~

Vòng lặp chỉ giữ Event hiện tại cùng dữ liệu mà processOne đang sử dụng. Khi xử lý xong và không còn tham chiếu, record có thể được GC thu hồi trước hoặc trong các chu kỳ GC tiếp theo.

Đoạn mã giả định mỗi phần tử array là một object tương thích với Event. Nếu phần tử là scalar, array con hoặc null, cần xác định hợp đồng và kiểm tra token trước khi deserialize.

## 6. Hiểu chính xác vị trí parser sau khi deserialize

Khi parser đang ở START_OBJECT, lời gọi:

~~~java
Event event = mapper.readValue(parser, Event.class);
~~~

đọc trọn object đó, bao gồm các object con và array con. Parser kết thúc ở token END_OBJECT của record. Lần gọi nextToken() kế tiếp sẽ tiến đến phần tử tiếp theo hoặc END_ARRAY.

Không gọi nextToken() thêm một lần ngay sau readValue() trước khi xử lý record nếu chưa hiểu trạng thái parser. Việc tiến quá một token có thể bỏ qua phần tử kế tiếp.

Nếu dùng readTree(parser), nguyên tắc tương tự: Jackson đọc một JSON value hoàn chỉnh thành JsonNode rồi parser đứng ở cuối value đó. Tree node chỉ nên được giữ trong phạm vi xử lý một record.

## 7. Cách ly lỗi mapping và validation theo từng record

Có hai loại lỗi cần phân biệt:

- **Lỗi cú pháp JSON:** parser không thể đọc token hoặc không biết chắc ranh giới record tiếp theo.
- **Lỗi mapping/validation:** JSON record đã được parse hoàn chỉnh nhưng không khớp DTO hoặc vi phạm nghiệp vụ.

Với JSON array thông thường, không nên bắt mọi JsonProcessingException rồi tiếp tục. Nếu mapping thất bại giữa object, parser có thể chưa ở cuối record; việc gọi nextToken() có thể tiếp tục từ vị trí không an toàn.

Nếu cần cách ly lỗi mapping riêng record, có thể parse từng phần tử thành JsonNode trước, sau đó chuyển node thành POJO:

~~~java
JsonNode rawRecord = mapper.readTree(parser);

try {
    Event event = mapper.treeToValue(rawRecord, Event.class);
    validate(event);
    processOne(event);
} catch (JsonProcessingException | InvalidRecordException error) {
    quarantine(rawRecord, error);
}
~~~

Ở đây readTree(parser) phải hoàn tất thành công trước khi bước mapping/validation chạy. Lỗi cú pháp trong readTree vẫn làm dừng document. Nếu treeToValue hoặc validation thất bại, parser đã tiêu thụ hết record và có thể tiếp tục phần tử sau.

Đánh đổi là mỗi record có một JsonNode tree tạm thời, nên memory peak bị giới hạn bởi kích thước record lớn nhất chứ không phải toàn tệp. Nếu một record đơn lẻ cũng rất lớn, cần streaming sâu hơn thay vì dựng tree.

## 8. NDJSON: xử lý từng dòng độc lập

Với NDJSON, có thể dùng BufferedReader để lấy một dòng, parse và xử lý trước khi đọc dòng kế:

~~~java
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;

import java.io.BufferedReader;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

public class NdjsonReader {
    private final ObjectMapper mapper;

    public NdjsonReader(ObjectMapper mapper) {
        this.mapper = mapper;
    }

    public void process(Path path) throws IOException {
        try (BufferedReader reader = Files.newBufferedReader(path)) {
            String line;
            long lineNumber = 0;

            while ((line = reader.readLine()) != null) {
                lineNumber++;

                if (line.isBlank()) {
                    continue;
                }

                try {
                    Event event = mapper.readValue(line, Event.class);
                    validate(event);
                    processOne(event);
                } catch (JsonProcessingException
                         | InvalidRecordException error) {
                    quarantineLine(lineNumber, line, error);
                }
            }
        }
    }

    private void validate(Event event) {
        // Domain validation.
    }

    private void processOne(Event event) {
        // Handle one event.
    }

    private void quarantineLine(
            long lineNumber,
            String rawLine,
            Exception error
    ) {
        // Persist safely with a size and retention limit.
    }
}
~~~

Mỗi dòng có một parser mới được tạo bên trong readValue(String, ...). Nếu một dòng sai cú pháp, parser của dòng đó kết thúc cùng exception; dòng tiếp theo vẫn có ranh giới độc lập.

BufferedReader.readLine() vẫn tạo một String cho toàn bộ dòng. Vì vậy memory bị giới hạn bởi dòng lớn nhất, không tự giới hạn kích thước dòng. Nếu mỗi record có thể rất lớn hoặc input không đáng tin cậy, cần giới hạn chiều dài record hoặc dùng framing/streaming phù hợp.

Không dùng Files.readAllLines() cho file lớn vì phương thức đó giữ tất cả dòng trong một List.

## 9. Streaming sâu hơn khi một record có array rất lớn

Đọc từng record không đủ nếu một record chứa một collection khổng lồ:

~~~json
{
  "batchId": "B-100",
  "events": [
    {"id": 1},
    {"id": 2},
    {"id": 3}
  ]
}
~~~

Nếu events có hàng triệu phần tử, deserialize cả object thành Batch sẽ tạo toàn bộ List trong heap. Có thể dùng parser duyệt field và stream riêng array đó:

~~~java
try (JsonParser parser =
        mapper.getFactory().createParser(path.toFile())) {

    if (parser.nextToken() != JsonToken.START_OBJECT) {
        throw new IOException("Expected a JSON object");
    }

    String batchId = null;
    JsonToken token;

    while ((token = parser.nextToken()) != JsonToken.END_OBJECT) {
        if (token == null) {
            throw new IOException("Unexpected end of input");
        }

        String fieldName = parser.currentName();
        JsonToken valueToken = parser.nextToken();

        if ("batchId".equals(fieldName)) {
            batchId = parser.getValueAsString();
        } else if ("events".equals(fieldName)
                && valueToken == JsonToken.START_ARRAY) {

            while (parser.nextToken() != JsonToken.END_ARRAY) {
                Event event = mapper.readValue(parser, Event.class);
                process(batchId, event);
            }
        } else {
            parser.skipChildren();
        }
    }
}
~~~

Đây là ví dụ minh họa với batchId xuất hiện trước events. Nếu thứ tự property không được bảo đảm, cần lưu batchId hoặc thiết kế luồng để xử lý được khi metadata xuất hiện sau array. Có thể dùng hai lượt đọc, staging tạm, hoặc định nghĩa schema yêu cầu metadata trước.

Nếu field events chứa object con lồng nhau cần giữ lại, chỉ dùng skipChildren() cho những field thực sự không cần. Parser phải đi qua đúng token để giữ trạng thái tài liệu.

## 10. Ghi JSON output theo từng record

Đọc streaming mà sau đó tích lũy mọi kết quả vào List rồi serialize một lần vẫn làm mất lợi ích memory. Có thể ghi từng record vào JsonGenerator:

~~~java
try (OutputStream output = Files.newOutputStream(outputPath);
     JsonGenerator generator =
        mapper.getFactory().createGenerator(output, JsonEncoding.UTF8)) {

    generator.writeStartArray();

    for (Event event : eventSource) {
        Event transformed = transform(event);
        mapper.writeValue(generator, transformed);
    }

    generator.writeEndArray();
}
~~~

Generator ghi array từng phần tử. Ứng dụng không cần giữ toàn bộ output object graph trong heap.

Nếu eventSource cũng là collection lớn đã được materialize trước đó, memory của nguồn vẫn còn. Để giới hạn memory từ đầu đến cuối, source phải cung cấp record tuần tự, ví dụ JsonParser, database cursor, paged API hoặc message stream.

Nếu generator gặp lỗi khi ghi, output có thể chỉ là một JSON array chưa đóng. Không công bố file dở dang như kết quả hoàn chỉnh.

## 11. Ghi file tạm rồi công bố output hoàn chỉnh

Với output file cần là một JSON document hợp lệ, nên ghi vào file tạm trong cùng thư mục/filesystem:

~~~java
Path target = Path.of("accepted.json").toAbsolutePath();
Path parent = target.getParent();
Path temporary = Files.createTempFile(
        parent,
        "accepted-",
        ".tmp"
);

boolean published = false;

try {
    try (OutputStream output = Files.newOutputStream(temporary);
         JsonGenerator generator =
            mapper.getFactory().createGenerator(output, JsonEncoding.UTF8)) {

        generator.writeStartArray();
        for (Event event : acceptedEvents) {
            mapper.writeValue(generator, event);
        }
        generator.writeEndArray();
    }

    Files.move(
            temporary,
            target,
            StandardCopyOption.ATOMIC_MOVE,
            StandardCopyOption.REPLACE_EXISTING
    );
    published = true;
} finally {
    if (!published) {
        // Giữ lại để điều tra hoặc xóa theo chính sách vận hành.
    }
}
~~~

Trong ví dụ này acceptedEvents chỉ là placeholder cho một nguồn record tuần tự; không nên tạo một List chứa toàn bộ kết quả trong ứng dụng thực tế. Thay vòng lặp bằng việc đọc và xử lý record trực tiếp từ parser.

ATOMIC_MOVE phụ thuộc filesystem và có thể không được hỗ trợ. Nếu tính nguyên tử là yêu cầu, hãy xác nhận filesystem đích hỗ trợ thao tác đó. File tạm nên nằm cùng filesystem với file đích để tránh khác biệt giữa volume.

## 12. Batch nhỏ để cân bằng memory và I/O

Một số downstream như database hoặc HTTP API xử lý hiệu quả hơn khi nhận batch. Có thể gom một số record cố định rồi xả:

~~~java
int batchSize = 200;
List<Event> batch = new ArrayList<>(batchSize);

while (hasNextRecord(parser)) {
    Event event = readNextRecord(parser);
    batch.add(event);

    if (batch.size() == batchSize) {
        persistBatch(batch);
        batch.clear();
    }
}

if (!batch.isEmpty()) {
    persistBatch(batch);
    batch.clear();
}
~~~

clear() loại bỏ tham chiếu từ danh sách để các record có thể đủ điều kiện GC nếu không còn tham chiếu ở nơi khác. Nó không buộc GC chạy ngay.

Chọn batch size theo:

- Kích thước trung bình và p99 của record.
- Memory budget của worker.
- Giới hạn transaction hoặc request downstream.
- Throughput và latency mục tiêu.
- Chi phí retry nếu một batch thất bại.

Batch 200 record nhỏ có thể nhẹ, nhưng 200 record chứa mỗi record một byte array lớn có thể chiếm hàng trăm MB. Nếu kích thước record biến động mạnh, cân nhắc giới hạn theo tổng byte ước lượng thay vì chỉ số lượng.

## 13. Bounded queue và backpressure khi xử lý song song

Có thể đọc tuần tự bằng một parser rồi gửi record sang worker pool:

~~~text
Input file
    |
    v
Single parser
    |
    v
Bounded queue
    |
    +------> Worker 1
    +------> Worker 2
    +------> Worker 3
    |
    v
Output
~~~

Queue phải có giới hạn:

~~~java
BlockingQueue<Event> queue = new ArrayBlockingQueue<>(500);
~~~

Khi queue đầy, producer cần chờ hoặc áp dụng backpressure. Nếu dùng queue không giới hạn, parser có thể đọc nhanh hơn worker và giữ hàng triệu object trong heap.

Số phần tử không phải thước đo memory chính xác. Nếu record có kích thước khác nhau, 500 record lớn có thể vượt memory budget. Có thể dùng semaphore hoặc weighted queue để giới hạn tổng kích thước in-flight theo ước lượng.

Chỉ một thread được thao tác với parser. Worker nhận POJO đã được deserialize và không được truy cập parser gốc.

## 14. Giữ thứ tự khi xử lý song song

Worker pool có thể hoàn thành record theo thứ tự khác với thứ tự trong file. Nếu thứ tự là một phần của hợp đồng, hãy gắn sequence number:

~~~java
record IndexedEvent(long index, Event event) {
}
~~~

Producer gửi IndexedEvent vào queue. Output writer có thể:

- Ghi theo thứ tự hoàn tất nếu thứ tự không quan trọng.
- Dùng buffer có giới hạn để chờ sequence tiếp theo.
- Chia input thành partition có thứ tự riêng.
- Chỉ xử lý song song các record độc lập và không cần giữ thứ tự.

Một reorder buffer không giới hạn cũng có thể làm memory tăng nếu một record đầu bị chậm còn các record sau hoàn tất nhanh. Cần giới hạn khoảng cách sequence hoặc áp dụng backpressure khi buffer đầy.

## 15. Xử lý lỗi mà không phá vỡ trạng thái parser

Với JSON array, phân loại lỗi theo thời điểm:

| Lỗi | Hành động thường phù hợp |
|---|---|
| Parser gặp JSON sai cú pháp | Dừng toàn document |
| EOF giữa object/array/string | Dừng; tài liệu không hoàn chỉnh |
| Mapping lỗi khi đọc trực tiếp POJO | Dừng trừ khi đã có cơ chế xác định ranh giới an toàn |
| Mapping lỗi sau khi JsonNode record đã đọc hoàn chỉnh | Quarantine record rồi tiếp tục |
| Validation nghiệp vụ sau khi POJO được tạo | Quarantine record rồi tiếp tục nếu hợp đồng cho phép |
| Output stream lỗi | Dừng pipeline và không publish output dở dang |
| Quarantine/DLQ không ghi được | Dừng hoặc backpressure; không âm thầm bỏ record |

NDJSON có lợi thế vì mỗi dòng là một parser session riêng. Một dòng sai cú pháp có thể được cách ly mà không làm mất parser state của dòng tiếp theo.

Không tìm dấu ngoặc đóng bằng regex hoặc quét chuỗi thô sau lỗi parse. Dấu ngoặc có thể xuất hiện trong string đã escape; parser cần hiểu trạng thái string, escape và nesting.

## 16. Lưu lỗi quarantine với giới hạn

Record lỗi nên có metadata đủ để điều tra và replay:

| Trường | Ý nghĩa |
|---|---|
| batchId | Nhận diện lần import |
| recordIndex/lineNumber | Vị trí trong nguồn |
| sourceFile | Tên hoặc ID nguồn |
| errorCategory | Syntax, mapping, validation hoặc dependency |
| errorCode | Mã lỗi ổn định |
| errorPath | Property path nếu Jackson cung cấp |
| rawPayload | Payload gốc nếu được phép lưu |
| occurredAt | Thời điểm lỗi |

Quarantine cần giới hạn dung lượng, retention và quyền truy cập. Payload có thể chứa thông tin cá nhân hoặc bí mật; không ghi nguyên văn vào log công khai.

Nếu một record quá lớn, không nên copy nó nhiều lần sang log, exception message và DLQ. Có thể lưu payload trong kho riêng và chỉ giữ reference cùng metadata trong DLQ.

## 17. Giới hạn kích thước và độ phức tạp đầu vào

Streaming giảm memory do không materialize toàn tệp, nhưng không ngăn một record đơn lẻ quá lớn. Cần đặt giới hạn:

- Tổng kích thước file/request.
- Kích thước tối đa một record.
- Độ sâu object lồng nhau.
- Độ dài string.
- Độ dài number.
- Số phần tử trong array.
- Thời gian parse và xử lý.

Jackson Core cung cấp StreamReadConstraints trong các phiên bản hỗ trợ:

~~~java
JsonFactory factory = JsonFactory.builder()
        .streamReadConstraints(
                StreamReadConstraints.builder()
                        .maxNestingDepth(100)
                        .maxStringLength(1_000_000)
                        .maxNumberLength(1_000)
                        .build()
        )
        .build();

ObjectMapper mapper = new ObjectMapper(factory);
~~~

Các con số chỉ là ví dụ. Chọn giới hạn dựa trên schema và workload. Một file lớn có thể hợp lệ nếu gồm nhiều record nhỏ; giới hạn tổng file và giới hạn record là hai chính sách khác nhau.

## 18. Memory thực tế của streaming

Với JSON array được xử lý tuần tự, memory peak có thể được hình dung:

~~~text
Peak memory
  ≈ parser buffers
    + largest record object graph
    + current transformation state
    + bounded batch
    + bounded queue
    + output buffers
    + shared application state
~~~

Đây là mô hình ước lượng, không phải công thức chính xác. Object header, String representation, collection capacity và JVM layout làm kích thước thật khác nhau.

Streaming thường làm bộ nhớ tăng theo kích thước record lớn nhất hoặc batch/queue giới hạn, thay vì tăng theo tổng số record trong file. Nhưng nếu processOne thêm mọi record vào static List, cache hoặc future chưa hoàn tất, memory vẫn tăng theo tổng số record.

Hãy đo retained heap sau khi queue đã drain và batch đã clear. Đừng chỉ nhìn heap ngay sau khi đọc file vì GC không nhất thiết chạy ngay khi object hết tham chiếu.

## 19. Tránh tạo bản sao payload lớn

Các cách sau có thể tạo bản sao lớn:

~~~java
byte[] bytes = Files.readAllBytes(path);
String json = new String(bytes, StandardCharsets.UTF_8);
List<Event> events = mapper.readValue(
        json,
        new TypeReference<List<Event>>() {}
);
~~~

Trong lúc xử lý, bytes, json và toàn bộ object graph có thể cùng tồn tại.

Đọc trực tiếp từ file:

~~~java
try (JsonParser parser =
        mapper.getFactory().createParser(path.toFile())) {
    // Parse tuần tự.
}
~~~

Tránh serialize toàn bộ output thành String rồi chuyển thành byte[] nếu có thể ghi trực tiếp qua JsonGenerator hoặc OutputStream.

Nếu input được gzip, có thể bọc GZIPInputStream và truyền vào parser. Giải nén theo luồng giúp tránh tạo file/byte array trung gian:

~~~java
try (InputStream file = Files.newInputStream(gzipPath);
     InputStream decompressed = new GZIPInputStream(file);
     JsonParser parser = mapper.getFactory().createParser(decompressed)) {
    // Parse tuần tự từ luồng đã giải nén.
}
~~~

Khi dùng nested try-with-resources, cần hiểu quyền sở hữu stream: parser mặc định có thể đóng source khi close. Có thể đơn giản hóa bằng cách để parser sở hữu stream hoặc cấu hình AUTO_CLOSE_SOURCE theo chính sách ứng dụng, tránh đóng tài nguyên nhiều nơi nếu không cần.

## 20. Checkpoint và khả năng chạy lại

Với tệp rất lớn, chạy lại từ đầu sau sự cố có thể tốn thời gian. Có thể lưu checkpoint:

- Record index đã commit.
- ID nghiệp vụ cuối cùng đã xử lý.
- Line number hoặc byte offset với NDJSON.
- Batch ID và trạng thái output.
- Số lượng accepted/rejected.

JSON array khó resume trực tiếp hơn NDJSON. Byte offset trong JSON array phụ thuộc encoding, compression và parser position; không nên tự lưu offset rồi seek vào giữa tài liệu mà không xác định đúng ranh giới token.

NDJSON thuận lợi hơn cho checkpoint vì mỗi dòng là một record độc lập. Có thể lưu line number hoặc byte offset tại ranh giới dòng, nhưng cần bảo đảm file không bị thay đổi và encoding/framing cố định.

Checkpoint chỉ được commit sau khi output tương ứng đã được ghi bền vững. Nếu đánh dấu record hoàn tất trước khi persist, sự cố có thể làm mất dữ liệu. Nếu persist xong nhưng crash trước checkpoint, replay có thể tạo duplicate; cần idempotent sink hoặc khóa duy nhất theo record ID.

## 21. Ghi metrics cho pipeline streaming

Một pipeline lớn cần số liệu để biết memory có thực sự được giới hạn:

- Tổng số record đã đọc.
- Số record thành công và bị quarantine.
- Thời gian parse và xử lý mỗi record.
- Throughput record/giây.
- Kích thước record trung bình và p95/p99.
- Queue depth và thời gian chờ queue.
- Batch size.
- Số record đang in-flight.
- Heap used, allocation rate và GC pause.
- Output bytes và thời gian ghi.

Không đưa record ID hoặc file path duy nhất vào metric label có cardinality cao. Đưa các định danh đó vào log hoặc trace có kiểm soát.

Gắn batchId/correlationId vào log giúp nối được sự kiện đọc, xử lý, quarantine và ghi output.

## 22. Profiling và xác nhận memory có giới hạn

Các công cụ hữu ích:

- Java Flight Recorder (JFR) để theo dõi allocation, GC, thread và latency.
- Java Mission Control để phân tích JFR.
- Heap dump và Eclipse MAT để tìm object đang giữ memory.
- async-profiler để đo CPU và allocation.
- JMH để đo chi phí parse một record hoặc serialize một record.

Một load test phù hợp nên:

1. Dùng file có số record lớn hơn nhiều lần so với memory budget nếu đọc toàn bộ.
2. Giữ kích thước record và phân bố dữ liệu gần production.
3. Chạy với concurrency và queue size dự kiến.
4. Theo dõi heap, allocation, queue depth và GC trong suốt quá trình.
5. Chờ pipeline drain rồi so sánh retained heap.
6. Lặp lại nhiều file để phát hiện memory tăng không giới hạn.

Nếu heap tăng theo tổng số record dù parser streaming, tìm nơi giữ reference: List, cache, queue, future, static collection, log buffer hoặc batch chưa clear.

## 23. Kiểm thử tính đúng đắn của streaming

Không chỉ kiểm tra rằng chương trình chạy hết file. Hãy xác nhận:

| Ca kiểm thử | Kết quả mong đợi |
|---|---|
| Array rỗng | Hoàn tất với 0 record |
| Một record | Xử lý đúng một lần |
| Nhiều record | Không bỏ sót hoặc xử lý lặp |
| Record có object/array con | Mapping đúng |
| JSON sai giữa array | Dừng theo chính sách document |
| Validation lỗi sau parse | Quarantine đúng record nếu được phép |
| NDJSON có một dòng sai | Dòng sau vẫn được xử lý |
| File bị cắt giữa record | Báo input không hoàn chỉnh |
| Queue đầy | Producer bị backpressure |
| Output lỗi giữa chừng | Không publish file dở dang |
| Record lớn vượt giới hạn | Từ chối theo constraint |
| File rất lớn | Memory không tăng tuyến tính theo tổng record |

Với parallel processing, thêm test thứ tự output, duplicate, retry và worker bị lỗi. Với checkpoint, test crash/restart ở trước và sau commit để xác nhận không mất hoặc nhân đôi dữ liệu.

## 24. Chọn JSON array hay NDJSON cho pipeline lớn?

| Tiêu chí | JSON array | NDJSON |
|---|---|---|
| Tính hợp lệ | Một JSON document duy nhất | Mỗi dòng là một JSON document |
| Đọc streaming | Có, qua token parser | Có, theo từng dòng hoặc record parser |
| Cách ly cú pháp lỗi | Khó sau lỗi giữa document | Dễ hơn vì ranh giới dòng rõ |
| Checkpoint | Cần parser position/framing cẩn thận | Dễ theo line/record boundary |
| Pretty-print | Có thể | Không phù hợp nếu object trải nhiều dòng |
| Công cụ xử lý dòng | Ít thuận tiện hơn | Dễ dùng grep/awk và pipeline dòng |
| Trao đổi API phổ biến | Rất phổ biến | Phù hợp log/event stream và import/export |

Chọn JSON array nếu hợp đồng yêu cầu một JSON document duy nhất và nguồn/đích hỗ trợ streaming. Chọn NDJSON nếu mỗi record độc lập, cần replay/checkpoint và muốn cách ly lỗi theo record.

## 25. Những lỗi thường gặp

### Dùng readValue thành List cho tệp rất lớn

Toàn bộ object graph được giữ trong heap. Duyệt JsonParser và deserialize từng record.

### Dùng readAllLines hoặc readAllBytes

Toàn bộ nội dung nguồn được materialize trước khi parse. Dùng InputStream/BufferedReader tuần tự.

### Streaming parser nhưng gom mọi record vào List

Parser không giữ toàn tệp nhưng ứng dụng vẫn giữ tất cả object. Xử lý, persist và bỏ tham chiếu từng record hoặc batch.

### Queue không giới hạn

Producer đọc nhanh hơn consumer làm backlog tăng theo thời gian. Dùng bounded queue và backpressure.

### Bắt mọi exception rồi tiếp tục trong JSON array

Parser có thể không ở ranh giới record. Chỉ tiếp tục khi record đã parse hoàn chỉnh hoặc framing độc lập như NDJSON bảo đảm ranh giới.

### Không giới hạn kích thước một record

Một record duy nhất vẫn có thể chiếm hết heap. Đặt request, string, number, nesting và record size constraints.

### Ghi output trực tiếp vào file đích

Sự cố giữa chừng để lại JSON không hoàn chỉnh. Ghi file tạm và chỉ publish sau khi đóng generator thành công.

### Dùng nhiều thread cùng đọc một parser

JsonParser là stateful và không thread-safe. Một producer đọc tuần tự rồi gửi POJO sang worker.

### Không giữ sequence khi xử lý song song

Worker có thể hoàn thành sai thứ tự. Gắn index và dùng reorder buffer có giới hạn nếu cần.

## 26. Quy trình triển khai thực tế

Khi xây dựng pipeline xử lý tệp JSON lớn:

1. Xác định framing: JSON array, NDJSON hay message stream.
2. Chọn ranh giới record và quy tắc xử lý lỗi.
3. Tái sử dụng ObjectMapper đã cấu hình.
4. Đọc trực tiếp từ InputStream/File bằng JsonParser hoặc từng dòng NDJSON.
5. Deserialize một record thành POJO; chỉ dùng JsonNode nếu cần cách ly lỗi mapping hoặc xử lý cấu trúc động.
6. Validate và xử lý ngay, không giữ mọi record.
7. Nếu cần batch, đặt giới hạn theo số lượng và kích thước.
8. Nếu cần parallelism, dùng bounded queue và backpressure.
9. Ghi output tuần tự bằng JsonGenerator hoặc NDJSON writer.
10. Ghi file tạm và publish sau khi hoàn tất.
11. Đặt parser constraints và giới hạn record size.
12. Thêm checkpoint/idempotency nếu cần resume.
13. Theo dõi metrics, JFR và heap trong load test.
14. Kiểm thử dữ liệu lớn, lỗi giữa chừng và restart.

## 27. Kết luận

Xử lý tệp JSON lớn với bộ nhớ giới hạn cần đọc và xử lý từng record thay vì deserialize toàn bộ file thành List hoặc JsonNode. Với JSON array, dùng JsonParser để duyệt phần tử và ObjectMapper để bind từng record; với NDJSON, parse từng dòng độc lập để dễ cách ly lỗi và checkpoint. Nếu một record có array rất lớn, cần streaming sâu đến chính array đó. Giữ batch và queue có giới hạn, áp dụng backpressure khi consumer chậm, chỉ dùng parser trên một thread và ghi output dần bằng JsonGenerator. Đặt giới hạn kích thước record, string, number và nesting; dùng file tạm để tránh publish output dở dang. Streaming chỉ thực sự giữ memory ổn định khi ứng dụng không giữ lại mọi object ở List, cache, queue hoặc future. Hãy đo heap, allocation, GC và queue depth bằng workload lớn để xác nhận memory phụ thuộc vào record/batch in-flight thay vì tổng số record trong tệp.
