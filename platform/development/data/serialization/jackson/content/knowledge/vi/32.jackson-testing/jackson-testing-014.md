# Kiểm thử tài nguyên được đóng khi thành công, hủy và thất bại

Jackson thường làm việc với các tài nguyên có vòng đời rõ ràng: InputStream, Reader, JsonParser, OutputStream, Writer, JsonGenerator, MappingIterator và SequenceWriter. Khi xử lý hoàn tất, dừng sớm hoặc phát sinh lỗi, các tài nguyên này cần được đóng đúng cách để giải phóng buffer, file handle, socket và các tài nguyên bên dưới.

Một luồng đọc/ghi có thể chạy đúng trong happy path nhưng vẫn rò rỉ tài nguyên khi có exception hoặc cancellation. Ví dụ, một import lớn dừng ở record thứ mười vì người dùng hủy thao tác; nếu MappingIterator và parser không được đóng, file handle có thể còn mở. Tương tự, export bị lỗi giữa chừng có thể để lại generator và output stream chưa được giải phóng.

Bài học này tập trung vào cách quản lý và kiểm thử vòng đời tài nguyên của Jackson trong ba tình huống: **thành công, hủy giữa chừng và thất bại**. Trọng tâm là xác định ai sở hữu stream, dùng try-with-resources đúng chỗ và viết test chứng minh các đường thoát đều đóng tài nguyên.

## 1. Vì sao phải kiểm thử vòng đời tài nguyên?

Tài nguyên I/O không giống object Java thông thường. Chúng có thể giữ tài nguyên của hệ điều hành hoặc tài nguyên dùng chung bên ngoài heap:

- File handle.
- Socket và kết nối mạng.
- Buffer nội bộ của parser/generator.
- Reader/writer có bộ đệm.
- Stream do framework HTTP hoặc thư viện khác quản lý.
- Tài nguyên của parser không blocking hoặc async.

Nếu không đóng đúng cách, ứng dụng có thể gặp:
- File không thể xóa hoặc ghi đè trên một số hệ điều hành.
- Số lượng socket/file descriptor tăng dần.
- Bộ nhớ bị giữ lâu hơn cần thiết.
- Dữ liệu ghi chưa được flush.
- Kết nối hoặc request bị treo.
- Test chạy riêng thành công nhưng suite lớn thất bại do tài nguyên còn mở.

Một test chỉ kiểm tra object đã deserialize đúng chưa chưa đủ. Cần kiểm tra cả tài nguyên nguồn và đích đã được đóng theo chính sách ownership.

## 2. Các tài nguyên Jackson thường gặp

| Thành phần | Vai trò | Cách quản lý thường dùng |
|---|---|---|
| InputStream | Cung cấp bytes JSON/CSV/YAML | Đóng theo owner của stream |
| Reader | Cung cấp ký tự cho parser | Đóng theo owner của reader |
| JsonParser | Đọc token tuần tự | Đóng bằng try-with-resources |
| MappingIterator | Đọc nhiều value/record tuần tự | Đóng khi hết dữ liệu hoặc dừng sớm |
| OutputStream | Nhận bytes được serialize | Đóng theo owner của stream |
| Writer | Nhận ký tự được serialize | Đóng theo owner của writer |
| JsonGenerator | Ghi token JSON | Đóng bằng try-with-resources |
| SequenceWriter | Ghi nhiều value tuần tự | Đóng sau khi hoàn tất hoặc dừng |
| CsvMapper/YAML mapper | Data binding theo định dạng | Quản lý parser/generator và iterator tương ứng |

Mapper thường là object cấu hình dùng lại lâu dài; không đóng ObjectMapper sau mỗi request. Parser, generator, iterator, reader/writer và stream mới là các tài nguyên có vòng đời gắn với một lần xử lý.

## 3. Phân biệt đóng parser với đóng stream nguồn

Khi tạo parser từ InputStream:

~~~java
JsonParser parser = mapper.getFactory().createParser(inputStream);
~~~

Parser đọc dữ liệu từ stream. Khi parser được đóng, Jackson có thể đóng cả source stream tùy cấu hình AUTO_CLOSE_SOURCE.

Trong Jackson, JsonParser.Feature.AUTO_CLOSE_SOURCE (hoặc StreamReadFeature.AUTO_CLOSE_SOURCE trong API builder mới) thường được bật mặc định. Điều đó có nghĩa đóng parser sẽ đóng source mà parser đang đọc.

Tương tự, khi đóng JsonGenerator, Jackson có thể đóng output target nếu AUTO_CLOSE_TARGET được bật.

Đây là điểm cần hiểu rõ: **đóng parser/generator và đóng stream bên dưới là hai hành vi có liên quan nhưng có thể cấu hình riêng**.

### 3.1. Ownership mặc định

Với mapper/factory mặc định của Jackson, các feature auto-close thường được bật:

- AUTO_CLOSE_SOURCE: parser đóng source khi parser đóng.
- AUTO_CLOSE_TARGET: generator đóng target khi generator đóng.

Do đó, một lời gọi như:

~~~java
Order order = mapper.readValue(inputStream, Order.class);
~~~

thường đóng parser nội bộ sau khi đọc xong; parser đóng source theo AUTO_CLOSE_SOURCE.

Tương tự:

~~~java
mapper.writeValue(outputStream, order);
~~~

mapper tạo generator, ghi dữ liệu rồi đóng generator; generator đóng target theo AUTO_CLOSE_TARGET.

Hành vi này thuận tiện khi mapper là owner thực tế của stream. Nhưng nếu stream do servlet container, HTTP client, framework hoặc một thành phần khác sở hữu, ứng dụng cần cân nhắc không để Jackson đóng tài nguyên của bên ngoài.

### 3.2. Khi caller muốn giữ stream mở

Có thể cấu hình JsonFactory trước khi dùng:

~~~java
import com.fasterxml.jackson.core.JsonFactory;
import com.fasterxml.jackson.core.StreamReadFeature;
import com.fasterxml.jackson.core.StreamWriteFeature;
import com.fasterxml.jackson.databind.ObjectMapper;

JsonFactory factory = JsonFactory.builder()
        .disable(StreamReadFeature.AUTO_CLOSE_SOURCE)
        .disable(StreamWriteFeature.AUTO_CLOSE_TARGET)
        .build();

ObjectMapper mapper = new ObjectMapper(factory);
~~~

Khi đó:
- Đóng parser không tự đóng source stream.
- Đóng generator không tự đóng target stream.
- Caller phải chịu trách nhiệm đóng stream theo vòng đời của nó.

Các feature builder này có trong những phiên bản Jackson Core hiện đại. Với phiên bản cũ, có thể gặp cấu hình tương ứng qua JsonParser.Feature.AUTO_CLOSE_SOURCE và JsonGenerator.Feature.AUTO_CLOSE_TARGET. Hãy dùng API phù hợp với phiên bản dependency thực tế.

### 3.3. Chỉ nên có một owner rõ ràng

Một quy tắc dễ áp dụng:
- Nếu Jackson tạo và sở hữu stream/parser/generator cho một thao tác độc lập, để Jackson đóng theo mặc định.
- Nếu framework hoặc caller sở hữu stream, cấu hình Jackson không đóng source/target và để owner bên ngoài đóng.
- Nếu tự tạo parser/generator, dùng try-with-resources để đóng parser/generator.
- Tránh để nhiều tầng cùng nghĩ mình là owner rồi đóng tài nguyên không theo hợp đồng.

Đóng hai lần thường không gây lỗi với nhiều stream chuẩn của JDK, nhưng không nên dựa vào giả định đó. Custom stream, wrapper hoặc tài nguyên từ thư viện khác có thể có hành vi close riêng.

## 4. Dùng try-with-resources cho JsonParser

Khi tự tạo parser, nên đặt parser trong try-with-resources:

~~~java
try (JsonParser parser = mapper.getFactory().createParser(inputStream)) {
    if (parser.nextToken() != JsonToken.START_OBJECT) {
        throw new JsonParseException(parser, "Expected an object");
    }

    while (parser.nextToken() != JsonToken.END_OBJECT) {
        // Đọc field và value.
    }
}
~~~

Khối try-with-resources đảm bảo parser.close() được gọi khi:
- Đọc thành công.
- Code chủ động ném exception.
- Parser phát sinh IOException hoặc lỗi mapping.
- Code return sớm.
- Có break/throw ra khỏi khối.

Nếu AUTO_CLOSE_SOURCE bật, source stream cũng được đóng cùng parser. Nếu feature bị tắt, caller vẫn cần đóng InputStream riêng.

### 4.1. Khi parser được tạo từ factory, ai đóng InputStream?

Có hai mẫu hợp lệ, tùy ownership.

**Mẫu A — Parser sở hữu source theo cấu hình mặc định:**

~~~java
JsonParser parser = mapper.getFactory().createParser(inputStream);

try (parser) {
    readDocument(parser);
}
~~~

Parser đóng source khi AUTO_CLOSE_SOURCE bật.

**Mẫu B — Caller sở hữu source:**

~~~java
try (InputStream input = Files.newInputStream(path);
     JsonParser parser = mapper.getFactory().createParser(input)) {

    readDocument(parser);
}
~~~

Nếu dùng mẫu này, có thể cấu hình AUTO_CLOSE_SOURCE tắt để parser không đóng source trước owner. Nếu không tắt, cả parser và khối ngoài có thể gọi close; với stream chuẩn điều đó thường idempotent, nhưng ownership không còn rõ ràng.

Không mở một stream trong một tầng rồi âm thầm để tầng khác đóng nó nếu hợp đồng tài nguyên không cho phép.

## 5. ObjectMapper.readValue tự quản lý parser nội bộ

Với lời gọi trực tiếp:

~~~java
Order order = mapper.readValue(inputStream, Order.class);
~~~

ObjectMapper tạo parser nội bộ, thực hiện data binding và đóng parser khi thao tác kết thúc. Nếu AUTO_CLOSE_SOURCE bật, InputStream cũng được đóng.

Vì vậy, khi dùng readValue(InputStream, Class), caller cần biết rằng stream có thể không còn dùng được sau lời gọi. Nếu muốn giữ stream mở để đọc tiếp hoặc để một framework khác quản lý, cấu hình source auto-close phù hợp hoặc dùng parser được quản lý theo ownership rõ ràng.

Đọc từ String không có external stream để caller đóng:

~~~java
Order order = mapper.readValue(jsonText, Order.class);
~~~

Tuy nhiên, String vẫn là một biểu diễn dữ liệu nằm trong heap; việc không có stream cần đóng không có nghĩa parse không cấp phát bộ nhớ.

## 6. MappingIterator: đóng khi đọc hết và khi dừng sớm

Khi đọc nhiều JSON value hoặc CSV record, Jackson thường trả về MappingIterator<T>. Iterator này có thể giữ parser đang mở trong suốt quá trình duyệt.

Ví dụ đọc nhiều root JSON object:

~~~java
ObjectReader reader = mapper.readerFor(Event.class);

try (MappingIterator<Event> iterator =
        reader.readValues(inputStream)) {

    while (iterator.hasNextValue()) {
        Event event = iterator.nextValue();
        process(event);
    }
}
~~~

MappingIterator triển khai Closeable, vì vậy có thể dùng trực tiếp trong try-with-resources.

Khi đọc hết dữ liệu, iterator có thể tự nhận biết EOF và đóng parser theo hành vi của nó. Tuy nhiên, vẫn nên gọi close tường minh qua try-with-resources. Điều này bảo đảm tài nguyên được đóng cả khi:
- Vòng lặp kết thúc sớm.
- process() ném exception.
- Người dùng hủy import.
- Code return giữa chừng.

### 6.1. Hủy khi đang đọc

Ví dụ một tác vụ import có thể bị hủy:

~~~java
try (MappingIterator<Event> iterator =
        mapper.readerFor(Event.class).readValues(inputStream)) {

    while (iterator.hasNextValue()) {
        if (cancellationToken.isCancelled()) {
            break;
        }

        Event event = iterator.nextValue();
        process(event);
    }
}
~~~

Khi break, khối try kết thúc và iterator được đóng. Việc đóng iterator đóng parser; source stream cũng được đóng nếu auto-close được bật.

Nếu xử lý diễn ra trong một thread bị interrupt, không nên giả định interrupt luôn tự đóng InputStream hoặc dừng mọi thao tác I/O đang block. Cơ chế cancellation cần phối hợp với owner của stream: hủy tác vụ, đóng stream nếu phù hợp và để try-with-resources hoàn tất cleanup.

### 6.2. Không return trước khi iterator được đóng

Tránh:

~~~java
MappingIterator<Event> iterator =
        mapper.readerFor(Event.class).readValues(inputStream);

while (iterator.hasNextValue()) {
    Event event = iterator.nextValue();

    if (shouldStop(event)) {
        return;
    }
}
~~~

Đường return làm bỏ qua việc đóng iterator. Dùng try-with-resources để mọi đường thoát đều thực hiện cleanup.

## 7. SequenceWriter: đóng sau khi ghi xong hoặc dừng

Khi ghi nhiều object tuần tự, SequenceWriter giúp không phải gom toàn bộ dữ liệu thành một List hoặc String trước khi serialize.

~~~java
try (SequenceWriter writer = mapper
        .writer()
        .writeValues(outputStream)) {

    for (Event event : events) {
        writer.write(event);
    }
}
~~~

Đóng SequenceWriter hoàn tất writer và generator theo ownership được thiết lập khi writer được tạo. Việc generator có đóng OutputStream bên dưới hay không còn chịu ảnh hưởng của AUTO_CLOSE_TARGET.

Hãy đóng writer khi:
- Ghi xong tất cả record.
- Chủ động hủy export.
- Có lỗi khi serialize một record.
- Có lỗi khi ghi ra stream.

Không để SequenceWriter ở field dùng chung lâu dài nếu nó gắn với một output stream riêng của một tác vụ.

### 7.1. Hủy export giữa chừng

~~~java
try (SequenceWriter writer = mapper
        .writer()
        .writeValues(outputStream)) {

    for (Event event : events) {
        if (cancellationToken.isCancelled()) {
            break;
        }

        writer.write(event);
    }
}
~~~

Khi break, writer được đóng. Việc đóng có thể flush phần dữ liệu đã ghi và đóng generator/target theo cấu hình. Vì vậy, một file output sau khi hủy có thể chứa một phần record đã được ghi. Đóng tài nguyên không đồng nghĩa rollback nội dung.

Nếu không chấp nhận file một phần, hãy ghi vào file tạm và chỉ công bố file cuối sau khi toàn bộ thao tác thành công.

## 8. JsonGenerator và OutputStream

Khi tự tạo generator:

~~~java
try (JsonGenerator generator =
        mapper.getFactory().createGenerator(outputStream)) {

    generator.writeStartObject();
    generator.writeStringField("status", "completed");
    generator.writeEndObject();
}
~~~

Khối try bảo đảm generator được đóng trong cả success và failure. Nếu AUTO_CLOSE_TARGET bật, generator đóng output stream.

Nếu stream do caller/framework sở hữu, có thể tắt AUTO_CLOSE_TARGET và để owner ngoài đóng stream. Generator vẫn cần được đóng để giải phóng buffer và hoàn tất trạng thái ghi.

### 8.1. ObjectMapper.writeValue cũng đóng generator nội bộ

Khi gọi:

~~~java
mapper.writeValue(outputStream, value);
~~~

ObjectMapper tạo generator, serialize value và đóng generator sau thao tác. Với cấu hình mặc định, output stream thường cũng được đóng do AUTO_CLOSE_TARGET.

Nếu muốn giữ stream mở:

~~~java
JsonFactory factory = JsonFactory.builder()
        .disable(StreamWriteFeature.AUTO_CLOSE_TARGET)
        .build();

ObjectMapper mapper = new ObjectMapper(factory);
~~~

Sau đó caller vẫn phải flush/close stream theo ownership của mình.

### 8.2. Không nhầm flush với close

- flush() đẩy dữ liệu đang buffer ra target.
- close() hoàn tất generator, giải phóng tài nguyên và có thể đóng target.
- close() thường thực hiện flush trước khi kết thúc, nhưng ứng dụng không nên dùng flush thay cho close.

Gọi flush rồi bỏ quên generator vẫn có thể giữ tài nguyên. Hãy dùng try-with-resources để close.

## 9. Close khi thành công, hủy và thất bại

Ba tình huống cần kiểm thử riêng:

| Tình huống | Ví dụ | Điều cần chứng minh |
|---|---|---|
| Thành công | Đọc hết file hoặc ghi hết object | Parser/iterator/generator/writer được đóng |
| Hủy | Dừng sau vài record hoặc cancellation token được bật | Tài nguyên được đóng dù chưa đọc/ghi hết |
| Thất bại | JSON sai, serializer ném lỗi, stream I/O lỗi | Tài nguyên được đóng và lỗi gốc không bị che |

Một bài test chỉ chạy happy path sẽ không phát hiện rò rỉ trên đường exception hoặc cancellation. Các đường thoát này cần test độc lập.

## 10. Tạo stream theo dõi close trong test

Để kiểm tra tài nguyên đã được đóng, có thể tạo test stream ghi nhận lời gọi close().

~~~java
final class TrackingInputStream extends FilterInputStream {

    private boolean closed;

    TrackingInputStream(byte[] data) {
        super(new ByteArrayInputStream(data));
    }

    @Override
    public void close() throws IOException {
        closed = true;
        super.close();
    }

    boolean isClosed() {
        return closed;
    }
}
~~~

Output stream tương tự:

~~~java
final class TrackingOutputStream extends FilterOutputStream {

    private final ByteArrayOutputStream buffer;
    private boolean closed;

    TrackingOutputStream() {
        this(new ByteArrayOutputStream());
    }

    private TrackingOutputStream(ByteArrayOutputStream buffer) {
        super(buffer);
        this.buffer = buffer;
    }

    @Override
    public void close() throws IOException {
        closed = true;
        super.close();
    }

    boolean isClosed() {
        return closed;
    }

    byte[] toByteArray() {
        return buffer.toByteArray();
    }
}
~~~

Các stream này cho phép test quan sát việc đóng mà không cần file thật hoặc socket thật. Chúng phù hợp để kiểm tra contract của code với Jackson.

Một lưu ý: các wrapper trên chỉ ghi nhận lời gọi close. Chúng không mô phỏng mọi hành vi của file/socket thật, vì vậy test tích hợp vẫn có thể cần thiết ở những hệ thống có ownership phức tạp.

## 11. Test đọc thành công có đóng source

Với ObjectMapper mặc định, parser nội bộ được đóng sau khi đọc xong; source thường cũng được đóng vì AUTO_CLOSE_SOURCE bật.

~~~java
@Test
void closesInputAfterSuccessfulRead() throws Exception {
    byte[] json = """
            {"id": 10, "name": "An"}
            """.getBytes(StandardCharsets.UTF_8);

    TrackingInputStream input = new TrackingInputStream(json);

    Person person = mapper.readValue(input, Person.class);

    assertEquals("An", person.getName());
    assertTrue(input.isClosed());
}
~~~

Test này kiểm tra cả kết quả data binding và side effect đóng stream.

Nếu mapper được cấu hình không auto-close source, assertion về isClosed() cần thay đổi theo ownership contract. Không nên viết test kỳ vọng stream luôn đóng bất kể cấu hình.

## 12. Test khi deserialize thất bại vẫn đóng source

Dữ liệu sai kiểu hoặc JSON sai cú pháp cần làm thao tác thất bại, nhưng parser vẫn phải được cleanup.

~~~java
@Test
void closesInputWhenMappingFails() {
    byte[] json = """
            {"id": "not-a-number", "name": "An"}
            """.getBytes(StandardCharsets.UTF_8);

    TrackingInputStream input = new TrackingInputStream(json);

    assertThrows(
            JsonProcessingException.class,
            () -> mapper.readValue(input, Person.class)
    );

    assertTrue(input.isClosed());
}
~~~

Test này xác nhận cleanup trong failure path. Nếu code tự tạo parser thay vì dùng readValue(InputStream, Type), hãy bảo đảm parser nằm trong try-with-resources.

Không bắt exception rồi trả object mặc định chỉ để test không thất bại. Exception mapping là kết quả đúng khi input không đáp ứng contract.

## 13. Test cancellation khi đọc MappingIterator

Đọc nhiều root JSON value, sau đó dừng sau record đầu tiên:

~~~java
@Test
void closesInputWhenIterationStopsEarly() throws Exception {
    String sequence = """
            {"id": 1, "name": "An"}
            {"id": 2, "name": "Binh"}
            {"id": 3, "name": "Chi"}
            """;

    TrackingInputStream input = new TrackingInputStream(
            sequence.getBytes(StandardCharsets.UTF_8)
    );

    try (MappingIterator<Person> iterator = mapper
            .readerFor(Person.class)
            .readValues(input)) {

        assertTrue(iterator.hasNextValue());

        Person first = iterator.nextValue();
        assertEquals(1L, first.getId());

        // Mô phỏng người dùng hủy sau record đầu tiên.
    }

    assertTrue(input.isClosed());
}
~~~

Điểm cần kiểm tra là khối try kết thúc và iterator được đóng dù còn dữ liệu chưa đọc. Đây là test đại diện cho break, cancellation hoặc return sớm trong import.

Nếu hệ thống đọc một root JSON array duy nhất thay vì một sequence các root value, có thể dùng parser loop hoặc một kiểu wrapper phù hợp. Hãy viết test theo đúng framing mà ứng dụng thực sự nhận.

## 14. Test khi một record giữa sequence bị lỗi

Lỗi có thể xuất hiện sau khi một số record đã được xử lý:

~~~java
@Test
void closesInputWhenAnIteratedRecordFails() throws Exception {
    String sequence = """
            {"id": 1, "name": "An"}
            {"id": "invalid", "name": "Binh"}
            """;

    TrackingInputStream input = new TrackingInputStream(
            sequence.getBytes(StandardCharsets.UTF_8)
    );

    assertThrows(
            JsonMappingException.class,
            () -> {
                try (MappingIterator<Person> iterator = mapper
                        .readerFor(Person.class)
                        .readValues(input)) {

                    assertEquals(1L, iterator.nextValue().getId());
                    iterator.nextValue();
                }
            }
    );

    assertTrue(input.isClosed());
}
~~~

Test này chứng minh rằng lỗi ở record thứ hai không làm parser còn mở sau khi exception thoát ra. Dùng try-with-resources ngay cả khi MappingIterator có cơ chế tự đóng ở EOF; lỗi không phải EOF và caller cần bảo đảm cleanup.

## 15. Test ghi thành công có đóng target

Với ObjectMapper mặc định, generator nội bộ được đóng sau khi serialize và target thường được đóng do AUTO_CLOSE_TARGET bật.

~~~java
@Test
void closesOutputAfterSuccessfulWrite() throws Exception {
    TrackingOutputStream output = new TrackingOutputStream();

    mapper.writeValue(
            output,
            new Person(10L, "An", 28)
    );

    assertTrue(output.isClosed());

    String json = new String(
            output.toByteArray(),
            StandardCharsets.UTF_8
    );
    assertTrue(json.contains("\"name\":\"An\""));
}
~~~

Nếu stream được caller sở hữu và mapper đã tắt auto-close target, test nên xác nhận stream vẫn mở sau write và chỉ đóng khi caller đóng nó.

## 16. Test lỗi khi ghi vẫn đóng target

Có thể tạo OutputStream cố ý ném IOException:

~~~java
final class FailingOutputStream extends OutputStream {

    private boolean closed;

    @Override
    public void write(int value) throws IOException {
        throw new IOException("simulated write failure");
    }

    @Override
    public void close() {
        closed = true;
    }

    boolean isClosed() {
        return closed;
    }
}
~~~

Test:

~~~java
@Test
void closesOutputWhenWriteFails() {
    FailingOutputStream output = new FailingOutputStream();

    assertThrows(
            IOException.class,
            () -> mapper.writeValue(
                    output,
                    new Person(10L, "An", 28)
            )
    );

    assertTrue(output.isClosed());
}
~~~

Tùy phiên bản và đường serialize, lỗi I/O có thể được bọc trong một exception Jackson là subclass của IOException. Vì vậy, test có thể bắt IOException hoặc kiểu exception cụ thể đã được xác nhận trên dependency của dự án.

Điều cần chứng minh là target được cleanup dù write không hoàn tất.

## 17. Test giữ stream mở khi caller sở hữu

Nếu stream được framework hoặc caller quản lý, hãy cấu hình Jackson không đóng source/target và kiểm tra contract đó.

~~~java
JsonFactory factory = JsonFactory.builder()
        .disable(StreamReadFeature.AUTO_CLOSE_SOURCE)
        .disable(StreamWriteFeature.AUTO_CLOSE_TARGET)
        .build();

ObjectMapper nonClosingMapper = new ObjectMapper(factory);
~~~

Test đọc:

~~~java
@Test
void doesNotCloseCallerOwnedInput() throws Exception {
    TrackingInputStream input = new TrackingInputStream(
            """
            {"id": 1, "name": "An"}
            """.getBytes(StandardCharsets.UTF_8)
    );

    try (input) {
        nonClosingMapper.readValue(input, Person.class);
        assertFalse(input.isClosed());
    }

    assertTrue(input.isClosed());
}
~~~

Test ghi:

~~~java
@Test
void doesNotCloseCallerOwnedOutput() throws Exception {
    TrackingOutputStream output = new TrackingOutputStream();

    try (output) {
        nonClosingMapper.writeValue(
                output,
                new Person(1L, "An", 28)
        );

        assertFalse(output.isClosed());
    }

    assertTrue(output.isClosed());
}
~~~

Hai test này kiểm tra rõ ownership:
- Jackson hoàn tất parser/generator.
- Caller vẫn giữ quyền sở hữu stream.
- Caller đóng stream ở đúng ranh giới vòng đời của mình.

Không nên dùng một mapper với cấu hình ownership không phù hợp cho mọi nguồn/đích. Nếu ứng dụng có nhiều loại stream owner, có thể tạo mapper/factory hoặc reader/writer riêng theo contract và cấu hình từ đầu.

## 18. Try-with-resources giữ lỗi gốc khi close cũng thất bại

Giả sử phần xử lý trong try ném exception, và close() cũng ném IOException. Java try-with-resources giữ exception xảy ra trong body làm primary exception; lỗi khi close được thêm vào danh sách suppressed exceptions.

Ví dụ:

~~~java
try (JsonParser parser = factory.createParser(inputStream)) {
    readAndValidate(parser);
} catch (IOException exception) {
    logger.error("JSON processing failed", exception);

    for (Throwable suppressed : exception.getSuppressed()) {
        logger.warn(
                "Resource cleanup also failed: {}",
                suppressed.getClass().getSimpleName()
        );
    }

    throw exception;
}
~~~

Trong production, cần kiểm soát message/stack trace theo chính sách log dữ liệu nhạy cảm. Ví dụ trên minh họa việc không làm mất thông tin cleanup failure.

Đừng viết finally rồi vô tình thay thế exception gốc bằng exception từ close:

~~~java
JsonParser parser = factory.createParser(inputStream);
try {
    readAndValidate(parser);
} finally {
    parser.close(); // Nếu close ném lỗi, có thể che lỗi trong body.
}
~~~

Nếu phải dùng try/finally thủ công, cần xử lý suppressed exception đúng cách. Với Java hiện đại, try-with-resources thường là lựa chọn rõ và an toàn hơn.

## 19. Output một phần khi hủy hoặc thất bại

Đóng generator không thể hoàn tác những bytes đã ghi. Khi export lớn, nếu tác vụ bị hủy sau 500 record hoặc disk đầy ở record 501, output có thể chứa một file một phần.

Đây là vấn đề về tính toàn vẹn của output, khác với vấn đề đóng tài nguyên.

### 19.1. Ghi file tạm rồi publish sau khi thành công

Một chiến lược thường dùng:

~~~java
Path temporary = target.resolveSibling(
        target.getFileName() + ".tmp"
);

try {
    try (OutputStream output = Files.newOutputStream(temporary)) {
        mapper.writeValue(output, report);
    }

    Files.move(
            temporary,
            target,
            StandardCopyOption.REPLACE_EXISTING,
            StandardCopyOption.ATOMIC_MOVE
    );
} catch (Exception exception) {
    Files.deleteIfExists(temporary);
    throw exception;
}
~~~

Trong hệ thống thực tế, cần xử lý trường hợp filesystem không hỗ trợ ATOMIC_MOVE, chính sách ghi đè file đích và cleanup khi process bị kill. Có thể cần đặt temp file trong cùng filesystem với target để atomic move có thể thực hiện.

Với SequenceWriter, chỉ move file sau khi writer đã close thành công và toàn bộ record đã được ghi.

### 19.2. HTTP response không dễ rollback

Khi bytes đã gửi đến client, server không thể thu hồi chúng. Nếu serialize response bị lỗi giữa chừng, kết nối có thể kết thúc với body không đầy đủ.

Để giảm rủi ro:
- Validate dữ liệu trước khi bắt đầu stream.
- Không thực hiện các bước có thể thất bại muộn nếu có thể làm trước.
- Dùng error handling phù hợp với protocol.
- Không giả định có thể gửi JSON error body mới sau khi response đã commit.
- Đảm bảo generator và stream được cleanup khi client disconnect.

## 20. Tài nguyên trong CSV và các định dạng Jackson khác

Nguyên tắc quản lý tài nguyên không chỉ áp dụng cho JSON.

CsvMapper và YAMLMapper cũng dùng mô hình parser/generator và data binding của Jackson. Các API đọc nhiều record có thể trả MappingIterator; API ghi nhiều value có thể dùng SequenceWriter.

Ví dụ CSV:

~~~java
CsvMapper csvMapper = new CsvMapper();

try (MappingIterator<Person> iterator = csvMapper
        .readerFor(Person.class)
        .with(schema)
        .readValues(inputStream)) {

    while (iterator.hasNextValue()) {
        Person person = iterator.nextValue();
        importOne(person);
    }
}
~~~

Ví dụ YAML:

~~~java
ObjectMapper yamlMapper = new ObjectMapper(new YAMLFactory());

try (JsonParser parser = yamlMapper.getFactory()
        .createParser(inputStream)) {

    Config config = yamlMapper.readValue(parser, Config.class);
}
~~~

Ở ví dụ YAML, nếu đã tự tạo parser, hãy để một nơi rõ ràng chịu trách nhiệm đóng parser và source theo cấu hình. Tránh vừa đóng parser vừa đóng stream ở nhiều tầng mà không hiểu ownership.

Dù format là JSON, CSV hay YAML, vẫn cần test:
- Đọc thành công.
- Đọc hết hoặc dừng sớm.
- Parser/deserializer ném lỗi.
- Ghi thành công.
- Generator/serializer hoặc output stream ném lỗi.
- Caller-owned stream có được giữ mở theo contract hay không.

## 21. Async và non-blocking parser: cancellation phải đi cùng cleanup

Jackson Core có API non-blocking parser cho dữ liệu đến theo từng phần. Ở chế độ này, parser có thể yêu cầu thêm input qua feeder trước khi có thể phát token tiếp theo.

Vòng đời phức tạp hơn parser blocking:
- Ứng dụng hoặc framework quản lý input feeder.
- Parser giữ buffer và trạng thái token.
- Khi request bị hủy, cần dừng việc cấp thêm input.
- Parser cần được đóng để giải phóng trạng thái và buffer.
- Nguồn mạng/socket được owner tương ứng đóng hoặc cancel.

Không nên giả định Thread.interrupt() tự động đóng parser, feeder hoặc socket. Cancellation phải được nối với lifecycle của framework hoặc tác vụ async.

Một thiết kế an toàn cần có một đường cleanup duy nhất, thường qua finally, resource scope hoặc hook cancellation của framework. Test nên mô phỏng:
- Cancel trước khi có token đầu tiên.
- Cancel giữa một object.
- Input kết thúc bất thường.
- Parser phát lỗi.
- Close được gọi đúng một lần theo contract.

API cụ thể phụ thuộc loại non-blocking parser và phiên bản Jackson Core; hãy kiểm tra API của phiên bản đang dùng thay vì áp dụng mẫu blocking trực tiếp.

## 22. Không đóng ObjectMapper sau mỗi thao tác

ObjectMapper không phải tài nguyên I/O gắn với một request. Mapper thường được cấu hình một lần và tái sử dụng.

Không nên tạo mapper mới rồi bỏ đi sau mỗi thao tác:

~~~java
ObjectMapper mapper = new ObjectMapper();
return mapper.readValue(inputStream, Order.class);
~~~

ObjectMapper không được dùng như một parser hoặc stream. Cấu hình mapper trước khi chia sẻ, sau đó tái sử dụng mapper, ObjectReader và ObjectWriter. Đóng parser/generator/iterator/stream theo từng thao tác.

Tách rõ:
- **Cấu hình dùng chung**: ObjectMapper, JsonFactory, module, reader/writer đã tạo.
- **Tài nguyên theo thao tác**: parser, generator, iterator, sequence writer, stream và reader/writer I/O.

## 23. Những lỗi quản lý tài nguyên thường gặp

| Cách làm | Vấn đề | Cách xử lý |
|---|---|---|
| Không đóng MappingIterator khi break | Parser và source có thể còn mở | Dùng try-with-resources |
| Tạo JsonParser rồi return sớm | Bỏ qua cleanup | Đặt parser trong resource scope |
| Chỉ đóng stream mà quên generator | Buffer và trạng thái generator chưa được hoàn tất | Đóng generator/writer |
| Gọi flush rồi bỏ quên close | Tài nguyên vẫn còn mở | Dùng try-with-resources |
| Giả định cancel tự đóng stream | Nhiều I/O blocking không phản ứng với interrupt | Nối cancellation với owner và đóng resource |
| Để Jackson đóng stream do framework sở hữu | Có thể phá vòng đời của framework | Tắt AUTO_CLOSE_SOURCE/TARGET phù hợp |
| Tắt auto-close nhưng không đóng ở caller | Rò rỉ stream | Ghi rõ owner và đóng ở tầng sở hữu |
| Bắt exception rồi bỏ qua | Lỗi xử lý và cleanup bị che | Giữ exception gốc, xử lý suppressed |
| Ghi output trực tiếp vào file đích rồi hủy | Để lại file một phần | Ghi temp và publish sau success |
| Đóng stream ở nhiều tầng | Ownership mơ hồ, có thể double-close | Chọn một owner |
| Đóng ObjectMapper sau mỗi request | Nhầm mapper với tài nguyên I/O | Tái sử dụng mapper; đóng resource theo thao tác |

## 24. Bộ test vòng đời nên có

Một test suite quản lý tài nguyên nên có ít nhất các nhóm sau:

| Nhóm | Test cần có |
|---|---|
| Read success | Đọc đúng object và xác nhận source được đóng/giữ mở theo cấu hình |
| Read failure | JSON sai cú pháp hoặc sai kiểu, source vẫn được cleanup |
| Read cancellation | Dừng MappingIterator sớm, parser/source được đóng |
| Iterator failure | Record ở giữa sequence gây lỗi, iterator vẫn được đóng |
| Write success | Ghi đúng output và target được xử lý theo ownership |
| Write failure | OutputStream hoặc serializer ném lỗi, generator/target được cleanup |
| Write cancellation | Dừng SequenceWriter, writer được đóng và output partial được xử lý |
| Caller-owned stream | Jackson đóng parser/generator nhưng không đóng source/target bên ngoài |
| Close failure | Lỗi close không che exception chính |
| Async cancellation | Parser/feeder/stream được cleanup khi tác vụ bị hủy |

Không phải mọi project đều cần test cho tất cả loại stream và format. Hãy chọn các test tương ứng với cách ứng dụng thực sự sử dụng Jackson, đặc biệt các đường cancellation và failure đang tồn tại trong production.

## 25. Quy trình viết code và test an toàn

Khi thêm một thao tác đọc/ghi Jackson:

1. Xác định nguồn/đích là stream do ai tạo và ai sở hữu.
2. Chọn overload trực tiếp phù hợp: InputStream, Reader, OutputStream hoặc Writer.
3. Nếu tự tạo parser/generator, dùng try-with-resources.
4. Nếu dùng MappingIterator/SequenceWriter, đóng chúng khi đọc/ghi xong hoặc dừng sớm.
5. Kiểm tra AUTO_CLOSE_SOURCE và AUTO_CLOSE_TARGET theo ownership.
6. Không giả định cancellation tự đóng tài nguyên blocking.
7. Khi output cần atomic, ghi file tạm và publish sau khi thành công.
8. Giữ exception gốc và kiểm tra suppressed exception khi close thất bại.
9. Dùng stream theo dõi close trong test.
10. Kiểm tra success, early stop/cancel và failure.
11. Test cả trường hợp Jackson được phép đóng stream lẫn trường hợp caller sở hữu stream nếu ứng dụng dùng cả hai.
12. Không tạo ObjectMapper mới cho từng thao tác chỉ để quản lý vòng đời.

## 26. Những điểm cần nhớ

- Parser, generator, MappingIterator và SequenceWriter cần được đóng đúng vòng đời.
- Mapper thường được cấu hình và tái sử dụng; không đóng ObjectMapper sau mỗi request.
- AUTO_CLOSE_SOURCE quyết định parser có đóng source hay không.
- AUTO_CLOSE_TARGET quyết định generator có đóng target hay không.
- ObjectMapper.readValue(InputStream, Type) và writeValue(OutputStream, value) quản lý parser/generator nội bộ; stream có thể được đóng theo auto-close feature.
- MappingIterator phải được đóng khi dừng sớm, hủy hoặc gặp lỗi.
- SequenceWriter phải được đóng khi ghi xong, hủy hoặc gặp lỗi.
- Try-with-resources bảo đảm cleanup trên success, exception, return và break.
- Cancellation không đồng nghĩa rollback output; file export có thể chỉ chứa một phần dữ liệu.
- Dùng file tạm nếu chỉ muốn công bố output hoàn chỉnh sau success.
- Khi caller/framework sở hữu stream, tắt auto-close tương ứng và để owner đóng.
- Try-with-resources giữ exception trong body làm lỗi chính và đưa lỗi close vào suppressed list.
- Dùng test stream theo dõi close() để kiểm tra vòng đời thực tế.
- Kiểm thử cả success, cancellation/early stop và failure.
- Nguyên tắc tương tự áp dụng cho Jackson CSV/YAML và parser/generator non-blocking, nhưng lifecycle của async cần phối hợp với framework.

Quản lý tài nguyên đúng không chỉ là gọi close() ở cuối happy path. Ứng dụng cần xác định owner của từng stream, đóng parser/iterator/generator/writer trên mọi đường thoát và kiểm thử cả khi thao tác bị hủy hoặc thất bại. Khi ownership được quy định rõ và cleanup được đặt trong try-with-resources hoặc lifecycle scope phù hợp, các luồng Jackson dễ dự đoán hơn, giảm nguy cơ rò rỉ file/socket và tránh để lại output dở dang mà hệ thống tưởng là hoàn chỉnh.

