# Kiểm thử giới hạn tài nguyên bằng dữ liệu được kiểm soát

Khi một ứng dụng nhận JSON từ file, HTTP request, message broker hoặc hệ thống đối tác, kích thước và cấu trúc dữ liệu không hoàn toàn nằm trong tầm kiểm soát. Payload có thể chứa chuỗi rất dài, số có hàng nghìn chữ số, object lồng nhau quá sâu hoặc array có hàng triệu phần tử. Nếu không có giới hạn, parser và tầng ứng dụng có thể tiêu thụ quá nhiều bộ nhớ, CPU, thời gian hoặc tài nguyên downstream.

Kiểm thử giới hạn tài nguyên cần chứng minh rằng ứng dụng chấp nhận dữ liệu nằm trong ngưỡng đã công bố và từ chối dữ liệu vượt ngưỡng theo cách có thể dự đoán. Với Jackson, có thể cấu hình các giới hạn đọc qua `StreamReadConstraints`. Những giới hạn khác như kích thước toàn request, số record, batch size, queue capacity, thời gian xử lý và concurrency thường phải được kiểm soát ở tầng bao quanh parser hoặc trong logic ứng dụng.

Một nguyên tắc quan trọng là dùng **dữ liệu được tạo có kiểm soát**. Unit test không cần cấp phát một chuỗi hàng gigabyte hay cố tình làm JVM hết heap. Hãy đặt ngưỡng nhỏ trong test, tạo input ngay tại ngưỡng và vượt ngưỡng một đơn vị, rồi xác nhận hành vi. Kiểm thử tải và profiling bộ nhớ là hoạt động riêng, dùng dataset lớn hơn nhưng vẫn có giới hạn rõ ràng.

## 1. Vì sao cần kiểm thử giới hạn tài nguyên?

Jackson có thể parse JSON linh hoạt, nhưng điều đó không có nghĩa mọi payload đều an toàn để xử lý vô hạn. Một số trường hợp có thể gây áp lực tài nguyên:

- Một chuỗi có hàng chục hoặc hàng trăm megabyte.
- Một số nguyên hoặc số thập phân có rất nhiều chữ số.
- Object hoặc array lồng sâu khiến parser phải duy trì trạng thái nesting.
- Một array có số lượng record rất lớn.
- Một object có rất nhiều property.
- Một request có kích thước lớn dù từng token riêng lẻ vẫn hợp lệ.
- Một file nén nhỏ nhưng giải nén thành dữ liệu rất lớn.
- Nhiều request hợp lệ cùng lúc làm tổng bộ nhớ hoặc CPU vượt khả năng hệ thống.
- Producer đọc nhanh hơn consumer, làm queue hoặc danh sách task tăng liên tục.

Nếu chỉ kiểm tra JSON đúng cú pháp, ứng dụng vẫn có thể bị quá tải bởi một JSON hợp lệ nhưng quá lớn. Vì vậy, test cần bao phủ cú pháp, giới hạn parser và giới hạn ở tầng ứng dụng.

## 2. Phân biệt giới hạn parser và giới hạn ứng dụng

Không phải mọi giới hạn đều thuộc Jackson. Cần đặt mỗi giới hạn tại tầng có đủ thông tin để kiểm soát nó.

| Loại giới hạn | Ví dụ | Tầng kiểm soát phù hợp |
|---|---|---|
| Độ sâu cấu trúc | Object lồng 30 cấp | Jackson Core parser |
| Độ dài string token | Một field có 2 MB text | Jackson Core parser |
| Độ dài number token | Một số có 5.000 chữ số | Jackson Core parser |
| Tổng byte request/file | Payload 100 MB | HTTP server, upload layer hoặc bounded stream |
| Số record | Array có 5 triệu phần tử | Logic streaming của ứng dụng |
| Số property mỗi object | Object có quá nhiều key | Parser/token counter hoặc schema/domain validation |
| Kích thước batch | 50.000 object trong một batch | Application service |
| Queue/concurrency | 10.000 task đang chờ | Executor, bounded queue hoặc backpressure |
| Dữ liệu sau giải nén | GZIP nở thành nhiều GB | Giới hạn ở stream sau decompression |
| Thời gian xử lý | Một import chạy quá lâu | Job deadline, timeout hoặc cancellation |
| Kích thước JSON đầu ra | Export vượt quota | Output stream có giới hạn hoặc quota ở tầng lưu trữ |

`StreamReadConstraints` giúp giới hạn một số đặc tính của token và cấu trúc JSON. Nó không thay thế giới hạn request ở reverse proxy, web server hoặc application gateway. Nó cũng không tự giới hạn số record mà business service xử lý hoặc số byte cuối cùng được ghi ra file.

## 3. StreamReadConstraints trong Jackson

Trong Jackson Core 2.15 trở lên, `StreamReadConstraints` cung cấp các ngưỡng cho parser. Các giới hạn thường dùng gồm:

- `maxNestingDepth`: độ sâu nesting tối đa của object/array.
- `maxStringLength`: độ dài string token tối đa.
- `maxNumberLength`: độ dài number token tối đa.

API và giá trị mặc định có thể thay đổi giữa các phiên bản Jackson. Hãy đối chiếu Javadoc của đúng phiên bản dependency mà dự án sử dụng. Ví dụ sau dùng API của Jackson Core có hỗ trợ `StreamReadConstraints`:

~~~java
import com.fasterxml.jackson.core.JsonFactory;
import com.fasterxml.jackson.core.StreamReadConstraints;
import com.fasterxml.jackson.databind.ObjectMapper;

StreamReadConstraints constraints = StreamReadConstraints.builder()
    .maxNestingDepth(8)
    .maxStringLength(128)
    .maxNumberLength(32)
    .build();

JsonFactory factory = JsonFactory.builder()
    .streamReadConstraints(constraints)
    .build();

ObjectMapper mapper = new ObjectMapper(factory);
~~~

Mapper này dùng parser factory với các giới hạn đã đặt. Có thể tạo mapper khác với giới hạn khác cho một hợp đồng khác. Cấu hình mapper/factory nên hoàn tất trước khi sử dụng và chia sẻ cho nhiều thread.

Không nên tùy tiện thay đổi giới hạn mặc định toàn JVM trong test. Một số phiên bản có API override default constraints mang tính global; việc thay đổi này có thể ảnh hưởng test khác hoặc mapper khác trong cùng tiến trình. Ưu tiên cấu hình riêng trên `JsonFactory` của mapper đang kiểm thử.

## 4. Kiểm thử tại ngưỡng và vượt ngưỡng

Một test giới hạn tốt thường có ít nhất hai trường hợp:

1. Input nằm trong giới hạn, phải được chấp nhận.
2. Input vượt giới hạn, phải bị từ chối bằng exception phù hợp.

Nếu giới hạn string là 8 ký tự, hãy kiểm tra chuỗi dài đúng 8 và chuỗi dài 9. Nếu giới hạn number là 12 ký tự, kiểm tra token 12 và 13 ký tự. Cách này giúp xác nhận boundary rõ ràng hơn một test chỉ dùng dữ liệu rất lớn.

Mẫu test:

~~~java
@Test
void acceptsStringAtConfiguredLimit() throws Exception {
    ObjectMapper mapper = mapperWithStringLimit(8);

    String value = mapper.readValue("\"12345678\"", String.class);

    assertEquals("12345678", value);
}

@Test
void rejectsStringAboveConfiguredLimit() {
    ObjectMapper mapper = mapperWithStringLimit(8);

    assertThrows(
        StreamConstraintsException.class,
        () -> mapper.readValue("\"123456789\"", String.class)
    );
}
~~~

Helper tạo mapper:

~~~java
private ObjectMapper mapperWithStringLimit(int maxLength) {
    JsonFactory factory = JsonFactory.builder()
        .streamReadConstraints(
            StreamReadConstraints.builder()
                .maxStringLength(maxLength)
                .build()
        )
        .build();

    return new ObjectMapper(factory);
}
~~~

Các ví dụ giả định phiên bản Jackson hỗ trợ builder và exception `StreamConstraintsException`. Nếu phiên bản dự án khác, hãy điều chỉnh import/API theo Javadoc. Test nên assert loại exception hoặc lớp cha ổn định theo version contract; không phụ thuộc toàn bộ message vì nội dung message có thể thay đổi giữa các phiên bản.

## 5. Kiểm thử độ dài string token

Một string token dài có thể gây áp lực bộ nhớ khi parser tạo nội dung của token. Đặt ngưỡng phù hợp với field lớn nhất mà hợp đồng cho phép.

~~~java
private ObjectMapper mapperWithStringLimit(int maxLength) {
    JsonFactory factory = JsonFactory.builder()
        .streamReadConstraints(
            StreamReadConstraints.builder()
                .maxStringLength(maxLength)
                .build()
        )
        .build();

    return new ObjectMapper(factory);
}
~~~

Test boundary:

~~~java
@Test
void stringLengthBoundaryIsEnforced() throws Exception {
    ObjectMapper mapper = mapperWithStringLimit(16);

    assertEquals(
        "abcdefghijklmnop",
        mapper.readValue("\"abcdefghijklmnop\"", String.class)
    );

    assertThrows(
        StreamConstraintsException.class,
        () -> mapper.readValue(
            "\"abcdefghijklmnopq\"",
            String.class
        )
    );
}
~~~

Giới hạn string token không phải giới hạn tổng kích thước JSON. Một document có thể chứa nhiều string, mỗi string đều nhỏ hơn ngưỡng nhưng tổng số byte vẫn rất lớn. Vì vậy, cần kiểm soát tổng request/file ở tầng khác.

Khi kiểm thử Unicode, hãy xác định rõ cách API của phiên bản Jackson đo độ dài token và chọn input ASCII để test boundary cơ bản. Có thể thêm test Unicode riêng để kiểm tra dữ liệu đa byte và ký tự surrogate, nhưng không nên giả định số byte UTF-8 luôn bằng số đơn vị ký tự mà parser dùng.

## 6. Kiểm thử độ dài number token

Một số JSON có thể chứa number token cực dài:

~~~json
{
  "accountNumber": 1234567890123456789012345678901234567890
}
~~~

Ngay cả khi ứng dụng không cần độ chính xác lớn như vậy, parser vẫn phải xử lý token. Dùng `maxNumberLength` để giới hạn số ký tự của number token trước khi chuyển sang kiểu Java.

~~~java
private ObjectMapper mapperWithNumberLimit(int maxLength) {
    JsonFactory factory = JsonFactory.builder()
        .streamReadConstraints(
            StreamReadConstraints.builder()
                .maxNumberLength(maxLength)
                .build()
        )
        .build();

    return new ObjectMapper(factory);
}
~~~

Test:

~~~java
@Test
void rejectsNumberTokenAboveConfiguredLimit() {
    ObjectMapper mapper = mapperWithNumberLimit(12);

    assertThrows(
        StreamConstraintsException.class,
        () -> mapper.readValue(
            "1234567890123",
            BigInteger.class
        )
    );
}
~~~

Đừng nhầm giới hạn token với giới hạn nghiệp vụ. Một number token ngắn vẫn có thể biểu diễn giá trị vượt giới hạn tài khoản hoặc số lượng đơn hàng. Sau khi parse, domain vẫn cần kiểm tra range, scale, sign và invariant.

Nếu API yêu cầu số tiền có scale cụ thể, hãy kiểm tra `BigDecimal.scale()` hoặc áp dụng validation tương ứng. `maxNumberLength` không thay thế quy tắc tiền tệ.

## 7. Kiểm thử độ sâu nesting

JSON cho phép object và array lồng nhau:

~~~json
{
  "a": {
    "b": {
      "c": {
        "value": 1
      }
    }
  }
}
~~~

Nesting quá sâu có thể làm tăng trạng thái parser và gây áp lực lên các bước xử lý tiếp theo. Dùng `maxNestingDepth` để đặt giới hạn.

Helper tạo JSON lồng array với độ sâu xác định:

~~~java
private String nestedArray(int depth) {
    return "[".repeat(depth) + "0" + "]".repeat(depth);
}
~~~

Test boundary:

~~~java
@Test
void nestingDepthLimitIsEnforced() throws Exception {
    ObjectMapper mapper = mapperWithNestingLimit(8);

    assertDoesNotThrow(
        () -> mapper.readTree(nestedArray(8))
    );

    assertThrows(
        StreamConstraintsException.class,
        () -> mapper.readTree(nestedArray(9))
    );
}
~~~

Một số cách đếm độ sâu có thể khiến người đọc nhầm root structure là cấp 0 hay cấp 1. Hãy tạo input có cấu trúc đơn giản, xác nhận semantics của phiên bản Jackson đang dùng và đặt test ở đúng boundary thực tế. Không dựa vào một ví dụ nested phức tạp khó đếm cấp.

Nên test cả object và array nếu ứng dụng nhận cả hai. Giới hạn nesting thuộc parser, không phải chỉ thuộc một kiểu DTO.

## 8. Dùng một factory riêng cho từng chính sách

Không phải mọi endpoint đều cần cùng một ngưỡng. Ví dụ webhook nhỏ có thể dùng giới hạn string 8 KB, trong khi file import cho phép field mô tả dài hơn. Có thể tạo các mapper riêng:

~~~java
ObjectMapper smallPayloadMapper = mapperWithLimits(
    16,
    8_192,
    64
);

ObjectMapper importMapper = mapperWithLimits(
    32,
    65_536,
    128
);
~~~

Helper:

~~~java
private ObjectMapper mapperWithLimits(
        int maxDepth,
        int maxStringLength,
        int maxNumberLength) {

    JsonFactory factory = JsonFactory.builder()
        .streamReadConstraints(
            StreamReadConstraints.builder()
                .maxNestingDepth(maxDepth)
                .maxStringLength(maxStringLength)
                .maxNumberLength(maxNumberLength)
                .build()
        )
        .build();

    return new ObjectMapper(factory);
}
~~~

Test xác nhận hai chính sách độc lập:

~~~java
@Test
void resourcePoliciesAreScopedToTheirMapper() throws Exception {
    ObjectMapper strict = mapperWithLimits(8, 8, 8);
    ObjectMapper import = mapperWithLimits(16, 32, 16);

    String input = "\"a-string-longer-than-eight\"";

    assertThrows(
        StreamConstraintsException.class,
        () -> strict.readValue(input, String.class)
    );

    assertEquals(
        "a-string-longer-than-eight",
        import.readValue(input, String.class)
    );
}
~~~

Cấu hình riêng giúp test không phải thay đổi global state. Nó cũng phản ánh rõ ranh giới hợp đồng của từng luồng dữ liệu. Tránh tạo mapper mới cho từng record; hãy tạo một lần cho mỗi policy và tái sử dụng.

## 9. Tạo dữ liệu kiểm thử có kiểm soát

Không nên lưu một file test khổng lồ trong repository chỉ để kiểm tra giới hạn. Có thể tạo input theo tham số:

~~~java
private String repeatedJsonString(int length) {
    return "\"" + "x".repeat(length) + "\"";
}

private String repeatedNumber(int digits) {
    return "7".repeat(digits);
}

private String nestedArray(int depth) {
    return "[".repeat(depth) + "0" + "]".repeat(depth);
}
~~~

Các helper này tạo input xác định và dễ hiểu. Test có thể thay đổi `length`, `digits` hoặc `depth` để kiểm tra ngay tại ngưỡng và vượt ngưỡng.

Với dataset có nhiều record, dùng `JsonGenerator` ghi ra file tạm thay vì nối toàn bộ JSON vào một `StringBuilder`. Cách đó tránh tạo thêm một bản sao lớn trong heap của test.

~~~java
private void writeOrders(Path path, int count) throws IOException {
    try (OutputStream output = Files.newOutputStream(path);
         JsonGenerator generator = mapper.getFactory().createGenerator(output)) {

        generator.writeStartArray();

        for (int i = 0; i < count; i++) {
            generator.writeStartObject();
            generator.writeStringField("id", "ORD-" + i);
            generator.writeNumberField("amount", i * 100L);
            generator.writeEndObject();
        }

        generator.writeEndArray();
    }
}
~~~

Helper này có thể tạo 10.000, 100.000 hoặc số record phù hợp với test. Không cần tạo hàng triệu object Java cùng lúc; generator phát từng object vào file.

## 10. Kiểm thử số lượng record ở tầng ứng dụng

`StreamReadConstraints` không phải bộ đếm tổng số phần tử array cho mọi use case. Nếu hợp đồng cho phép tối đa 100.000 record, ứng dụng cần đếm khi streaming:

~~~java
long processed = 0;
long maxRecords = 100_000;

try (MappingIterator<Order> iterator = reader.readValues(input)) {
    while (iterator.hasNextValue()) {
        if (processed >= maxRecords) {
            throw new TooManyRecordsException(maxRecords);
        }

        Order order = iterator.nextValue();
        validate(order);
        process(order);
        processed++;
    }
}
~~~

Kiểm tra ngưỡng trước khi bind phần tử kế tiếp giúp ứng dụng tránh tạo object vượt giới hạn. Parser vẫn cần tiến thêm để xác định có phần tử tiếp theo; điều đó không đồng nghĩa nó đã materialize toàn bộ record tiếp theo.

Test có thể dùng giới hạn nhỏ, ví dụ 3 record:

~~~java
@Test
void stopsBeforeProcessingRecordAboveApplicationLimit() throws Exception {
    Path file = tempDir.resolve("orders.json");
    writeOrders(file, 4);

    AtomicInteger processed = new AtomicInteger();

    assertThrows(
        TooManyRecordsException.class,
        () -> importOrders(file, 3, order -> processed.incrementAndGet())
    );

    assertEquals(3, processed.get());
}
~~~

Test này xác nhận ứng dụng không xử lý record thứ tư. Nếu yêu cầu là từ chối toàn bộ file trước khi tạo bất kỳ side effect nào, cần một bước staging/validation trước commit; streaming trực tiếp vào business service không tự cung cấp tính atomic.

## 11. Kiểm thử batch size có giới hạn

Một pipeline có thể đọc streaming nhưng vẫn tạo batch quá lớn. Hãy kiểm tra invariant batch không vượt ngưỡng:

~~~java
@Test
void neverSendsBatchLargerThanConfiguredSize() throws Exception {
    Path file = tempDir.resolve("orders.json");
    writeOrders(file, 1_003);

    List<Integer> observedSizes = new ArrayList<>();

    importInBatches(file, 100, batch -> {
        observedSizes.add(batch.size());
    });

    assertEquals(
        List.of(100, 100, 100, 100, 100, 100, 100, 100, 100, 100, 3),
        observedSizes
    );
}
~~~

Ví dụ này giả định `importInBatches` flush batch đầy đủ và gửi batch cuối nhỏ hơn. Trong test thực tế, có thể kiểm tra thêm:

- Batch không rỗng.
- Tổng record đã gửi bằng số record đọc thành công.
- Không có record bị lặp hoặc bỏ sót.
- Batch được clear sau khi downstream hoàn tất.
- Khi downstream ném lỗi, pipeline dừng hoặc retry theo chính sách.
- Không có task bất đồng bộ giữ reference tới batch đã bị tái sử dụng.

Nếu pipeline dùng queue hoặc executor, kiểm tra cả số task in-flight và queue capacity, không chỉ kích thước list batch.

## 12. Kiểm thử giới hạn tổng byte đầu vào

Một JSON document có thể có nhiều field nhỏ nhưng tổng kích thước rất lớn. Cần giới hạn tổng byte ở tầng HTTP/upload/file. `Content-Length` hữu ích để từ chối sớm nhưng không nên là cơ chế duy nhất, vì request streaming hoặc header không đáng tin cậy có thể không cung cấp kích thước đúng.

Có thể dùng một counting/bounded stream ở tầng ứng dụng để theo dõi số byte thực tế. Ý tưởng:

~~~text
HTTP upload / file
       |
       v
Byte-counting boundary
       |
       +--> bytes within quota --> Jackson parser
       |
       +--> quota exceeded --> reject and close
~~~

Một wrapper có giới hạn cần xử lý đúng trường hợp stream chạm ngưỡng: nếu nguồn còn byte tiếp theo, phải báo vượt giới hạn; nếu đã EOF đúng tại ngưỡng, input vẫn hợp lệ. Khi parser không đọc đến EOF, ứng dụng cũng phải bảo đảm lớp upload đã áp dụng quota hoặc kiểm tra toàn bộ nguồn theo hợp đồng.

Không dùng `maxStringLength` thay cho giới hạn tổng byte. Một array có hàng triệu field nhỏ vẫn có thể chiếm nhiều dung lượng.

Test tổng byte nên dùng stream nhỏ với quota nhỏ, ví dụ 64 byte. Không cần tạo file nhiều gigabyte để chứng minh wrapper từ chối byte thứ 65.

## 13. Kiểm thử dữ liệu sau giải nén

Nếu ứng dụng nhận JSON nén bằng GZIP, cần phân biệt:

- Kích thước compressed input.
- Kích thước decompressed stream.
- Kích thước token và cấu trúc JSON.

Một file nén 1 MB có thể giải nén thành hàng trăm MB. Đặt giới hạn ở compressed upload không đủ. Quota cần được áp dụng sau `GZIPInputStream` để giới hạn byte thực tế parser nhận được.

~~~java
try (InputStream file = Files.newInputStream(path);
     InputStream gzip = new GZIPInputStream(file);
     InputStream bounded = new DecompressedByteLimitInputStream(gzip, maxBytes)) {

    parseJson(bounded);
}
~~~

`DecompressedByteLimitInputStream` là wrapper của ứng dụng, không phải lớp có sẵn trong Jackson. Nó cần đếm byte trả về cho parser và ném lỗi khi vượt quota.

Test tạo dữ liệu nén nhỏ nhưng có output giải nén vượt ngưỡng. Dùng một payload ngắn vừa đủ để test logic quota, không cần tạo compression bomb thực sự. Đồng thời test input hợp lệ có kích thước giải nén đúng bằng quota.

## 14. Kiểm thử số property và token count

Một object có thể chứa rất nhiều property dù mỗi property nhỏ:

~~~json
{
  "field0001": 1,
  "field0002": 2,
  "field0003": 3
}
~~~

Không phải mọi phiên bản Jackson đều cung cấp một giới hạn `StreamReadConstraints` trực tiếp cho tổng số property hoặc tổng token của một document. Nếu hợp đồng cần giới hạn này, có thể đếm token khi duyệt bằng `JsonParser`, hoặc kiểm soát schema và kích thước byte ở tầng ứng dụng.

Ví dụ bộ đếm token đơn giản:

~~~java
long tokenCount = 0;
long maxTokens = 100_000;

try (JsonParser parser = factory.createParser(input)) {
    JsonToken token;

    while ((token = parser.nextToken()) != null) {
        tokenCount++;

        if (tokenCount > maxTokens) {
            throw new JsonTokenLimitException(maxTokens);
        }

        // Chỉ bind các nhánh cần thiết.
    }
}
~~~

Đếm token là giới hạn ở tầng xử lý của ứng dụng. Parser vẫn phải đọc token để đếm; do đó nó không thay thế giới hạn byte hoặc giới hạn thời gian. Nếu chỉ cần giới hạn số property của từng object, hãy đếm field name trong phạm vi từng object và reset counter khi object kết thúc.

Test với object có số field nhỏ, ví dụ giới hạn 10 và input có 11 field. Xác nhận parser từ chối trước khi application xử lý object đó. Nếu đang bind trực tiếp qua Databind, có thể cần custom deserializer hoặc lớp token-level để áp dụng chính sách này.

## 15. Kiểm thử giới hạn đầu ra

Giới hạn đọc và giới hạn ghi là hai vấn đề khác nhau. Một ứng dụng có thể nhận input hợp lệ nhưng tạo ra output vượt quota lưu trữ hoặc response size.

Có thể bọc `OutputStream` để đếm byte ghi ra. Khi số byte vượt quota, wrapper ném `IOException`; writer phải được đóng và file tạm không được công bố.

~~~text
SequenceWriter
     |
     v
Byte-counting output stream
     |
     +--> within quota --> file temporary
     |
     +--> over quota --> fail export
~~~

Không nên giả định `StreamWriteConstraints` giới hạn tổng byte của output. Các phiên bản Jackson có thể cung cấp giới hạn độ sâu khi ghi, nhưng quota tổng byte, số phần tử array và kích thước file vẫn thường là trách nhiệm của ứng dụng hoặc storage layer.

Nếu cần giới hạn nesting khi serialize và phiên bản Jackson hỗ trợ `StreamWriteConstraints`, cấu hình trên factory riêng và kiểm tra Javadoc phiên bản đang dùng. Đừng nhầm giới hạn độ sâu ghi với giới hạn tổng output size.

## 16. Kiểm thử giới hạn nesting khi ghi

Một object graph có thể được tạo từ code nội bộ và sâu hơn giới hạn mong muốn. Nếu ứng dụng cần giới hạn này, kiểm tra hỗ trợ `StreamWriteConstraints` trong phiên bản Jackson đang dùng.

Ví dụ cấu hình trên phiên bản có API tương ứng:

~~~java
StreamWriteConstraints writeConstraints =
    StreamWriteConstraints.builder()
        .maxNestingDepth(8)
        .build();

JsonFactory factory = JsonFactory.builder()
    .streamWriteConstraints(writeConstraints)
    .build();

ObjectMapper mapper = new ObjectMapper(factory);
~~~

Tạo một nested object/collection ở độ sâu kiểm soát và assert serialize ở trong ngưỡng thành công, vượt ngưỡng thất bại. Cấu trúc test nên nhỏ để không dựa vào stack exhaustion của JVM.

Nếu version hiện tại chưa có ~StreamWriteConstraints`, không tự giả định API có sẵn. Có thể kiểm tra độ sâu object graph ở tầng domain trước khi serialize hoặc nâng cấp Jackson theo quy trình dependency của dự án.

## 17. Không kiểm thử bằng cách chờ OutOfMemoryError

Một test kiểu sau không ổn định:

~~~java
@Test
void hugeJsonEventuallyRunsOutOfMemory() {
    String huge = "x".repeat(Integer.MAX_VALUE);
    mapper.readValue(huge, String.class);
}
~~~

Nó có thể làm hỏng toàn bộ test JVM trước khi tới assertion. Kết quả phụ thuộc heap size, garbage collector, JDK, máy CI và thời điểm chạy test. `OutOfMemoryError` cũng có thể khiến các test sau không còn môi trường sạch để chạy.

Không nên dùng OOM làm tiêu chí pass/fail cho unit test. Hãy:

- Đặt parser limit nhỏ trong test.
- Tạo input tại ngưỡng và vượt ngưỡng.
- Assert exception cụ thể.
- Kiểm tra ứng dụng không xử lý record vượt giới hạn.
- Đo peak heap ở performance test riêng.
- Chạy benchmark trong process/JVM có heap và timeout được kiểm soát.

Mục tiêu của unit test là xác nhận chính sách được áp dụng, không phải làm JVM cạn bộ nhớ.

## 18. Kiểm thử streaming mà không tạo một List khổng lồ

Để xác nhận ứng dụng xử lý nhiều record theo luồng, có thể tạo file tạm bằng `JsonGenerator`, sau đó đọc bằng `MappingIterator` và chỉ giữ bộ đếm hoặc batch nhỏ.

~~~java
@Test
void streamsGeneratedArrayWithoutCollectingAllRows() throws Exception {
    Path file = tempDir.resolve("orders.json");
    int expected = 20_000;
    writeOrders(file, expected);

    long processed = 0;
    int batchSize = 250;
    List<Order> batch = new ArrayList<>(batchSize);

    try (InputStream input = Files.newInputStream(file);
         MappingIterator<Order> rows =
             mapper.readerFor(Order.class).readValues(input)) {

        while (rows.hasNextValue()) {
            batch.add(rows.nextValue());

            if (batch.size() == batchSize) {
                processed += batch.size();
                batch.clear();
            }
        }

        processed += batch.size();
    }

    assertEquals(expected, processed);
}
~~~

Test này không chứng minh peak heap tuyệt đối, nhưng chứng minh code path đọc tuần tự và batch không cần một collection chứa toàn bộ record. Nếu cần xác nhận memory profile, chạy performance test riêng với dataset lớn hơn, heap cap rõ ràng và công cụ đo.

Không viết test mà bên trong lại gọi ~readAll()` hoặc tích lũy mọi record vào một list rồi chỉ khẳng định đã dùng ~MappingIterator~. Khi kiểm tra streaming, chính test harness cũng phải giữ bộ nhớ có giới hạn.

## 19. Kiểm thử InputStream trả dữ liệu thành chunk nhỏ

Network và file stream không nhất thiết trả đủ số byte mà parser yêu cầu trong một lần ~read()~. Một ~InputStream~ hợp lệ có thể trả về một vài byte rồi mới tiếp tục.

Có thể tạo wrapper test trả tối đa một hoặc vài byte mỗi lần đọc để xác nhận parser xử lý đúng buffer boundary:

~~~java
final class SmallChunkInputStream extends FilterInputStream {
    private final int maxChunk;

    SmallChunkInputStream(InputStream delegate, int maxChunk) {
        super(delegate);
        this.maxChunk = maxChunk;
    }

    @Override
    public int read(byte[] buffer, int offset, int length)
            throws IOException {
        return super.read(
            buffer,
            offset,
            Math.min(length, maxChunk)
        );
    }
}
~~~

Dùng test:

~~~java
@Test
void parserHandlesInputDeliveredInSmallChunks() throws Exception {
    byte[] json = """
        [{"id":"ORD-1","amount":100.00},
         {"id":"ORD-2","amount":200.00}]
        """.getBytes(StandardCharsets.UTF_8);

    try (InputStream source = new ByteArrayInputStream(json);
         InputStream chunked = new SmallChunkInputStream(source, 2);
         MappingIterator<Order> rows =
             mapper.readerFor(Order.class).readValues(chunked)) {

        assertEquals("ORD-1", rows.nextValue().getId());
        assertEquals("ORD-2", rows.nextValue().getId());
        assertFalse(rows.hasNextValue());
    }
}
~~~

Đây là test về khả năng đọc qua buffer boundary, không phải test throughput hoặc memory limit. Nó cũng giúp phát hiện code tự viết giả định ~read()~ luôn trả đủ số byte yêu cầu.

## 20. Kiểm thử nhiều request đồng thời

Một payload riêng lẻ có thể nằm trong giới hạn, nhưng nhiều payload cùng lúc vẫn làm hệ thống quá tải. Cần kiểm tra concurrency policy ở tầng service/executor.

Ví dụ giới hạn số job import đồng thời bằng semaphore:

~~~java
private final Semaphore permits = new Semaphore(4);

public ImportResult importFile(Path path) {
    if (!permits.tryAcquire()) {
        throw new ImportCapacityExceededException();
    }

    try {
        return doImport(path);
    } finally {
        permits.release();
    }
}
~~~

Test dùng latch để giữ các job đang chạy, xác nhận chỉ tối đa bốn job được vào vùng xử lý và job tiếp theo bị từ chối hoặc chờ theo policy. Không dùng ~Thread.sleep()~ tùy tiện để đo race condition; dùng ~CountDownLatch`, ~CyclicBarrier` hoặc test executor có kiểm soát.

Nếu service chạy trên nhiều instance, semaphore trong một JVM chỉ giới hạn từng instance. Quota toàn hệ thống cần được đặt ở gateway, distributed limiter, queue hoặc scheduler tương ứng.

## 21. Kiểm thử property-based và fuzzing có giới hạn

Ngoài các test boundary viết tay, có thể dùng property-based testing để tạo nhiều input có cấu trúc:

- String có độ dài từ 0 đến ngưỡng + một khoảng nhỏ.
- Number token với dấu âm, dấu thập phân và exponent.
- Object/array với nesting thay đổi.
- Array chứa record hợp lệ xen kẽ record sai.
- Field tên lạ, field lặp hoặc field thiếu.
- Unicode, escape sequence và ký tự điều khiển hợp lệ.

Dùng seed cố định hoặc ghi lại seed khi test thất bại để tái hiện lỗi. Giới hạn kích thước sinh dữ liệu và số lần chạy để test ổn định trên CI.

Fuzzing không nên chạy vô hạn trong unit-test suite thông thường. Có thể tách thành job nightly hoặc security test riêng với timeout, memory limit và lưu corpus các input gây lỗi.

## 22. Kiểm thử thời gian xử lý

Một payload có thể không vượt bất kỳ giới hạn token nào nhưng vẫn khiến business logic chạy rất lâu. Ví dụ, mỗi record thực hiện một truy vấn database hoặc gọi dịch vụ bên ngoài.

Jackson không phải nơi duy nhất để đặt timeout. Cần giới hạn:

- Tổng thời gian import/export.
- Thời gian đọc stream.
- Thời gian xử lý một record hoặc batch.
- Thời gian chờ downstream.
- Thời gian chờ queue hoặc semaphore.
- Thời gian retry.

Test timeout nên dùng dependency giả có thể chủ động block bằng latch hoặc trả kết quả trễ theo điều khiển. Không dựa vào network thật hoặc sleep dài trong unit test. Khi timeout/cancellation xảy ra, xác nhận stream, parser, writer và transaction được đóng/rollback theo policy.

## 23. Kiểm tra exception và log khi vượt giới hạn

Khi input vượt `StreamReadConstraints`, Jackson có thể ném `StreamConstraintsException` trong quá trình đọc. Application boundary có thể chuyển lỗi này thành exception ổn định cho client:

~~~java
try {
    return mapper.readValue(input, RequestDto.class);
} catch (StreamConstraintsException exception) {
    throw new PayloadLimitExceededException(
        "The JSON payload exceeds an allowed structural limit",
        exception
    );
} catch (JsonProcessingException exception) {
    throw new InvalidPayloadException(
        "The JSON payload is invalid",
        exception
    );
}
~~~

Exception gốc nên được giữ làm cause để log nội bộ có thể truy vết. HTTP response chỉ nên trả mã lỗi và thông điệp công khai, không trả stack trace hay message chi tiết của parser.

Không log toàn bộ payload khi gặp lỗi giới hạn. Log request ID, endpoint, loại giới hạn, ngưỡng cấu hình và parser location nếu có. Cần tránh ghi raw value của token quá dài vì log có thể trở thành một nguồn tiêu thụ tài nguyên hoặc rò rỉ dữ liệu.

Test có thể xác nhận exception ứng dụng có cause là `StreamConstraintsException`, và response không chứa tên class nội bộ hoặc stack trace.

## 24. Performance test và profiling bộ nhớ

Unit test boundary không chứng minh ứng dụng xử lý 10 triệu record trong giới hạn 512 MB heap. Đó là mục tiêu của performance/integration test.

Một bài test hiệu năng nên quy định trước:

- Số record và kích thước trung bình mỗi record.
- Phân bố field lớn/nhỏ.
- Độ sâu object lồng nhau.
- Tỷ lệ record lỗi.
- Kích thước batch và queue.
- Tốc độ downstream.
- Heap limit của JVM.
- Thời gian chạy tối đa.
- Throughput và peak memory mong đợi.

Có thể dùng JFR, Java Mission Control, VisualVM hoặc benchmark harness như JMH tùy mục tiêu. JMH phù hợp để benchmark thao tác nhỏ và tránh một số sai lệch đo lường; kiểm thử end-to-end file import cần quan sát cả I/O, database và downstream.

Không so sánh chỉ bằng thời gian wall-clock của một lần chạy. Warm-up, filesystem cache, GC, CPU contention và môi trường CI đều ảnh hưởng kết quả. Ghi lại cấu hình JDK, Jackson version, heap, GC và dataset để so sánh có ý nghĩa.

## 25. Một bộ test minh họa cho các giới hạn parser

Có thể gom các test parser vào một class:

~~~java
class JacksonResourceLimitTest {
    private ObjectMapper mapperWithLimits(
            int depth,
            int stringLength,
            int numberLength) {

        JsonFactory factory = JsonFactory.builder()
            .streamReadConstraints(
                StreamReadConstraints.builder()
                    .maxNestingDepth(depth)
                    .maxStringLength(stringLength)
                    .maxNumberLength(numberLength)
                    .build()
            )
            .build();

        return new ObjectMapper(factory);
    }

    @Test
    void acceptsStringWithinLimit() throws Exception {
        ObjectMapper mapper = mapperWithLimits(8, 8, 8);

        assertEquals(
            "12345678",
            mapper.readValue("\"12345678\"", String.class)
        );
    }

    @Test
    void rejectsStringOverLimit() {
        ObjectMapper mapper = mapperWithLimits(8, 8, 8);

        assertThrows(
            StreamConstraintsException.class,
            () -> mapper.readValue("\"123456789\"", String.class)
        );
    }

    @Test
    void rejectsNumberOverLimit() {
        ObjectMapper mapper = mapperWithLimits(8, 8, 8);

        assertThrows(
            StreamConstraintsException.class,
            () -> mapper.readValue("123456789", BigInteger.class)
        );
    }

    @Test
    void rejectsNestingOverLimit() {
        ObjectMapper mapper = mapperWithLimits(4, 64, 16);

        String nested = "[[[[[0]]]]]";

        assertThrows(
            StreamConstraintsException.class,
            () -> mapper.readTree(nested)
        );
    }
}
~~~

Class này dùng ngưỡng nhỏ để test nhanh và không phụ thuộc heap máy CI. Khi áp dụng, bổ sung import JUnit/Jackson và kiểm tra API theo version dự án. Nếu test độ sâu ở đúng boundary, hãy tạo helper `nestedArray(depth)` để biểu diễn số cấp rõ ràng thay vì đếm thủ công dấu ngoặc.

## 26. Các lỗi thường gặp khi kiểm thử giới hạn

### Dùng payload khổng lồ để gây OOM

Test có thể làm sập cả JVM và không ổn định giữa các máy. Dùng ngưỡng nhỏ và input đúng ngưỡng/vượt ngưỡng.

### Chỉ test dữ liệu rất nhỏ

Không chứng minh parser từ chối khi vượt giới hạn. Thêm boundary test tại N và N+1.

### Nghĩ StreamReadConstraints giới hạn toàn bộ request

Nó giới hạn một số đặc tính parser/token, không thay thế request byte quota, record count, queue size hay timeout.

### Tạo input lớn bằng StringBuilder

Bản thân test đã materialize toàn bộ payload và có thể làm sai kết quả memory profiling. Với dataset lớn, dùng JsonGenerator ghi ra file hoặc stream sinh dữ liệu.

### Gọi readAll() trong test streaming

Test giữ toàn bộ collection nên không còn chứng minh pipeline bounded-memory. Chỉ giữ counter hoặc batch nhỏ.

### Thay đổi global default trong test

Có thể làm test khác phụ thuộc thứ tự chạy. Cấu hình factory/mapper riêng cho từng policy.

### Assert message exception quá chi tiết

Message có thể thay đổi giữa phiên bản Jackson. Ưu tiên loại exception, cause và thông tin ổn định mà hợp đồng công bố.

### Không kiểm tra dữ liệu sau giải nén

Compressed size nhỏ không đảm bảo decompressed size nhỏ. Đặt quota trên stream sau giải nén.

### Không giới hạn concurrency

Mỗi request riêng lẻ hợp lệ nhưng tổng số request có thể làm cạn tài nguyên. Test admission control và bounded queue.

### Chỉ đo thời gian, không đo heap

Một luồng nhanh có thể tiêu thụ bộ nhớ quá lớn. Đo cả allocation, peak heap, GC và throughput.

### Nhầm lỗi parser với lỗi nghiệp vụ

Một record sai kiểu, một lỗi validation và một lỗi database cần được phân loại riêng. Không đổi mọi lỗi thành payload-too-large.

## 27. Quy trình kiểm thử giới hạn tài nguyên

1. Liệt kê tài nguyên cần bảo vệ: byte, string, number, nesting, record, field, batch, queue, concurrency và thời gian.
2. Xác định tầng sở hữu mỗi giới hạn.
3. Đặt ngưỡng nhỏ, tường minh trong test để không phụ thuộc cấu hình máy.
4. Tạo input tại ngưỡng và vượt ngưỡng một đơn vị.
5. Cấu hình `StreamReadConstraints` trên `JsonFactory` riêng cho parser test.
6. Kiểm tra string length, number length và nesting depth.
7. Dùng `JsonGenerator` để tạo dataset nhiều record ra file/stream thay vì giữ toàn bộ payload trong String.
8. Kiểm tra record count, batch size và queue capacity ở tầng ứng dụng.
9. Kiểm tra byte quota cả trước và sau decompression.
10. Kiểm tra output quota và file tạm khi ghi thất bại.
11. Xác nhận exception/cause và response công khai ổn định.
12. Dùng latch/barrier để test concurrency và cancellation có kiểm soát.
13. Tách unit boundary tests khỏi performance/profiling tests.
14. Ghi lại Jackson version, JDK, heap và dataset cho benchmark.
15. Giữ test deterministic, có giới hạn thời gian và không dựa vào OOM.

## 28. Bảng ghi nhớ

| Nhu cầu | Cách làm |
|---|---|
| Giới hạn nesting khi đọc | ~StreamReadConstraints.maxNestingDepth(...)~ |
| Giới hạn string token | ~StreamReadConstraints.maxStringLength(...)~ |
| Giới hạn number token | ~StreamReadConstraints.maxNumberLength(...)~ |
| Cấu hình parser riêng | ~JsonFactory.builder().streamReadConstraints(...)~ |
| Kiểm tra boundary | Test N và N+1 |
| Giới hạn tổng byte request | HTTP/upload boundary hoặc bounded stream |
| Giới hạn byte sau GZIP | Wrapper trên decompressed stream |
| Giới hạn số phần tử | Counter trong vòng lặp streaming |
| Giới hạn field/token | Token counter hoặc custom parsing policy |
| Giới hạn batch | Application service và test batch invariant |
| Giới hạn queue/concurrency | Bounded queue, semaphore hoặc admission control |
| Giới hạn output | Counting/bounded OutputStream hoặc storage quota |
| Giới hạn nesting khi ghi | ~StreamWriteConstraints~ nếu version hỗ trợ |
| Kiểm thử dataset lớn | ~JsonGenerator~ ghi file/stream tổng hợp |
| Đo memory thực tế | JFR/profiling/performance test |
| Tránh test OOM | Ngưỡng nhỏ, deterministic boundary assertions |

## 29. Kết luận

Kiểm thử giới hạn tài nguyên với Jackson cần kết hợp giới hạn parser và giới hạn của ứng dụng. ~StreamReadConstraints~ giúp kiểm soát nesting depth, string length và number length trong các phiên bản Jackson hỗ trợ. Tổng byte request, số record, số field, batch, queue, concurrency, dữ liệu sau giải nén, thời gian xử lý và kích thước output cần được bảo vệ ở tầng phù hợp.

Hãy tạo dữ liệu kiểm thử bằng helper có tham số, test tại ngưỡng và vượt ngưỡng một đơn vị, dùng ~JsonGenerator~ khi cần dataset nhiều record và giữ cho test harness cũng có bộ nhớ giới hạn. Không dùng ~OutOfMemoryError~ làm assertion của unit test. Tách boundary tests xác định khỏi performance/profiling tests, rồi đo heap, GC, throughput và latency với dataset đại diện. Cách làm này giúp chính sách tài nguyên có thể tái hiện, dễ kiểm tra trên CI và ít phụ thuộc môi trường chạy.
