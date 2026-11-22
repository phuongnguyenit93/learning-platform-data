# Theo dõi kích thước đầu vào, độ trễ và mức sử dụng bộ nhớ

Jackson thường nằm trên đường xử lý request, message, event hoặc file dữ liệu. Một thay đổi nhỏ trong payload, DTO, custom serializer hay cấu hình mapper có thể làm thời gian đọc/ghi tăng lên, số object được cấp phát nhiều hơn hoặc heap tăng mạnh khi nhiều request chạy đồng thời. Vì vậy, vận hành Jackson cần theo dõi ba nhóm tín hiệu gắn trực tiếp với serialization: kích thước dữ liệu, độ trễ và mức sử dụng bộ nhớ.

Ba nhóm này liên hệ với nhau nhưng không thay thế nhau. Payload lớn thường tốn nhiều CPU và bộ nhớ hơn, nhưng một payload nhỏ vẫn có thể gây chậm nếu chứa cấu trúc lồng sâu, nhiều token, custom deserializer đắt hoặc truy cập tài nguyên bên ngoài. Heap tăng có thể do giữ nhiều request đồng thời, giữ object sau deserialize, buffering toàn bộ output hoặc do một cây JsonNode lớn. Một timer đơn lẻ không chỉ ra được nguyên nhân.

Mục tiêu quan sát là đo được chi phí tại đúng ranh giới đọc/ghi, phân biệt chi phí Jackson với thời gian mạng và nghiệp vụ, nhận biết xu hướng trước khi hệ thống quá tải, đồng thời cung cấp đủ thông tin để điều tra mà không ghi nội dung payload nhạy cảm vào log.

## 1. Ba tín hiệu vận hành cốt lõi

Khi theo dõi một luồng Jackson, nên bắt đầu từ ba câu hỏi:

| Tín hiệu | Câu hỏi | Ví dụ metric |
|---|---|---|
| Kích thước đầu vào/đầu ra | Mỗi lần đọc hoặc ghi xử lý bao nhiêu byte? | **serialization.payload.bytes** |
| Độ trễ | Jackson mất bao lâu để parse, bind hoặc ghi dữ liệu? | **serialization.duration** |
| Bộ nhớ | JVM đang dùng bao nhiêu heap, cấp phát bao nhiêu object và GC ra sao? | **jvm.memory.used**, allocation rate, GC pause |

Nên tách riêng chiều đọc và chiều ghi:

- Deserialize: wire bytes hoặc text được parse và bind thành Java object.
- Serialize: Java object được chuyển thành wire bytes hoặc text.

Hai chiều có profile chi phí khác nhau. Deserialize có thể tốn thời gian tạo object graph và convert kiểu. Serialize có thể tốn CPU cho getter, custom serializer, format ngày giờ, escape string và ghi output.

Ngoài ba tín hiệu chính, nên quan sát số lần thành công/thất bại, số request đang xử lý, hàng đợi và tỷ lệ payload bị từ chối bởi giới hạn kích thước.

## 2. Đặt ranh giới đo đúng chỗ

Một request HTTP có thể bao gồm nhiều giai đoạn:

~~~text
Client
  |
  v
Nhận byte từ mạng
  |
  v
Giải nén / giải mã transport
  |
  v
Đọc JSON/XML/binary bằng Jackson
  |
  v
Validate và xử lý nghiệp vụ
  |
  v
Serialize response bằng Jackson
  |
  v
Nén / ghi byte ra mạng
  |
  v
Client
~~~

Nếu chỉ đo thời gian từ lúc nhận request đến lúc gửi response, metric đó là end-to-end latency. Nó không cho biết Jackson chiếm bao nhiêu thời gian.

Hãy đo riêng:

1. Thời gian nhận body hoặc đọc message từ broker.
2. Thời gian giải nén nếu có.
3. Thời gian Jackson deserialize.
4. Thời gian validation và nghiệp vụ.
5. Thời gian Jackson serialize.
6. Thời gian nén và ghi output.

Đo tại ranh giới thực tế mà ứng dụng gọi ObjectMapper, ObjectReader, ObjectWriter, XmlMapper hoặc parser/generator. Không đặt timer chỉ quanh toàn bộ controller rồi gắn nhãn đó là thời gian Jackson.

## 3. Phân biệt thời gian parse với thời gian bind

Một lần gọi:

~~~java
Order order = mapper.readValue(inputStream, Order.class);
~~~

thường thực hiện cả parsing và databinding trong cùng một thao tác. Parser đọc token, còn databind tạo object, gọi constructor/setter, chuyển đổi scalar và xử lý collection.

Nếu cần phân tích sâu, có thể dùng JsonParser để đo từng phần:

~~~java
try (JsonParser parser = factory.createParser(inputStream)) {
    while (parser.nextToken() != null) {
        // Đọc hoặc xử lý token theo cấu trúc ứng dụng.
    }
}
~~~

Tuy nhiên, streaming parser tự viết có thể thay đổi semantics so với databinding, nên không nên thay code production chỉ để có một timer tách parse/bind. Thường nên đo tổng thời gian deserialize ở production, rồi dùng profiler hoặc benchmark chuyên biệt để phân tích parser và binding.

## 4. Đo kích thước theo byte, không chỉ theo số ký tự

Kích thước payload trên mạng và trong bộ nhớ có thể khác nhau:

- UTF-8 dùng số byte khác nhau tùy ký tự.
- Java String lưu theo representation nội bộ của JVM, không phải luôn bằng số byte UTF-8.
- JSON có thể được nén gzip hoặc brotli khi truyền.
- Một InputStream có thể là dữ liệu đã giải nén.
- Binary format như Smile/CBOR không có độ dài ký tự tương đương.

Nên ghi rõ metric đang đo loại kích thước nào:

| Metric | Ý nghĩa |
|---|---|
| Compressed bytes | Số byte nhận từ mạng trước giải nén |
| Decompressed bytes | Số byte sau giải nén, đưa vào parser |
| Text characters | Số ký tự nếu ứng dụng thực sự cần đo text |
| Serialized bytes | Số byte Jackson ghi ra trước hoặc sau compression tùy vị trí đo |

Không đặt tên chung là payload size nếu không nói rõ đó là byte nén hay byte parser nhìn thấy.

## 5. Đo kích thước của byte array

Nếu ứng dụng đã có body dưới dạng byte array:

~~~java
byte[] payload = requestBody;
int payloadBytes = payload.length;

Order order = mapper.readValue(payload, Order.class);
~~~

Có thể ghi kích thước trước khi deserialize. Không cần tạo thêm bản sao chỉ để đo.

Nếu payload có thể lớn hơn giới hạn int của Java array thì bản thân cách giữ toàn bộ dữ liệu trong byte[] đã không phù hợp. Với dữ liệu lớn, dùng InputStream và giới hạn kích thước ở tầng transport/parser.

## 6. Đo kích thước của String

String.length() trả số UTF-16 code units, không phải số byte UTF-8. Ví dụ:

~~~java
String json = "{\"name\":\"Nguyễn\"}";

int utf16Units = json.length();
int utf8Bytes = json.getBytes(StandardCharsets.UTF_8).length;
~~~

Nếu metric cần phản ánh kích thước text được truyền theo UTF-8, đo byte ở tầng encode hoặc từ byte body thực tế. Không gọi getBytes() trên mọi request chỉ để đo nếu việc tạo byte array mới làm tăng allocation và CPU.

Nếu ứng dụng chỉ có String mà không còn byte gốc, có thể ước lượng UTF-8 bằng encoder hoặc tính khi serialize vào một counting stream. Ghi rõ metric là kích thước UTF-8 được tính lại, không phải số byte mạng đã nhận.

## 7. Đo kích thước InputStream

InputStream không có length tổng quát. Không gọi available() để suy ra kích thước toàn bộ payload; available() chỉ cho biết số byte có thể đọc ngay mà không bị block theo contract của stream.

Có thể đếm byte khi parser đọc qua một counting stream:

~~~java
final class CountingInputStream extends FilterInputStream {
    private long count;

    CountingInputStream(InputStream input) {
        super(input);
    }

    @Override
    public int read() throws IOException {
        int value = super.read();
        if (value != -1) {
            count++;
        }
        return value;
    }

    @Override
    public int read(byte[] buffer, int offset, int length)
            throws IOException {
        int read = super.read(buffer, offset, length);
        if (read > 0) {
            count += read;
        }
        return read;
    }

    long getCount() {
        return count;
    }
}
~~~

Sử dụng:

~~~java
CountingInputStream counted = new CountingInputStream(input);
try {
    Order order = mapper.readValue(counted, Order.class);
    recordPayloadSize(counted.getCount());
    return order;
}
finally {
    // Xử lý đóng stream theo ownership của tầng gọi.
}
~~~

Ví dụ minh họa cách đếm byte parser đã tiêu thụ. Cần kiểm tra Jackson có đọc trước một phần dữ liệu ngoài document hay không và ai chịu trách nhiệm đóng stream. Nếu stream có thể chứa nhiều message liên tiếp, số byte parser tiêu thụ có thể không bằng tổng kích thước transport frame.

Trong production, có thể dùng counting wrapper đã được thư viện chuẩn hóa hoặc bộ đếm ở tầng HTTP/message broker. Tránh tạo wrapper chồng nhiều lớp nếu framework đã cung cấp byte count chính xác.

## 8. Đo output bằng counting OutputStream

Khi Jackson ghi trực tiếp ra OutputStream, có thể đếm số byte đã phát:

~~~java
final class CountingOutputStream extends FilterOutputStream {
    private long count;

    CountingOutputStream(OutputStream output) {
        super(output);
    }

    @Override
    public void write(int value) throws IOException {
        out.write(value);
        count++;
    }

    @Override
    public void write(byte[] buffer, int offset, int length)
            throws IOException {
        out.write(buffer, offset, length);
        count += length;
    }

    long getCount() {
        return count;
    }
}
~~~

Sử dụng:

~~~java
CountingOutputStream counted = new CountingOutputStream(output);
mapper.writeValue(counted, response);
recordSerializedSize(counted.getCount());
~~~

Counting stream minh họa việc đo byte Jackson ghi vào stream. Nếu stream phía dưới là compressor, vị trí wrapper quyết định metric:

- Wrapper bên trong compressor đo byte trước nén.
- Wrapper bên ngoài compressor đo byte sau nén.

Đặt tên metric theo đúng vị trí để tránh so sánh hai đại lượng khác nhau.

## 9. Không buffer toàn bộ chỉ để biết kích thước

Một cách đơn giản nhưng tốn bộ nhớ:

~~~java
byte[] bytes = mapper.writeValueAsBytes(response);
int size = bytes.length;
output.write(bytes);
~~~

Nó giữ toàn bộ output trong byte array rồi mới ghi tiếp. Với payload lớn và nhiều request đồng thời, các byte array này có thể tạo áp lực heap đáng kể.

Nếu tầng tiếp theo nhận stream, ghi trực tiếp:

~~~java
CountingOutputStream counted = new CountingOutputStream(output);
mapper.writeValue(counted, response);
~~~

Chỉ buffer khi cần replay, tính chữ ký trên toàn bộ payload, retry hoặc truyền cho API chỉ nhận byte array. Nếu cần buffer, hãy đặt giới hạn kích thước và đo bộ nhớ/latency thực tế.

## 10. Phân biệt kích thước payload với kích thước object graph

Payload JSON 1 MB không có nghĩa Java object sau deserialize cũng chiếm 1 MB. Object graph thường có overhead:

- Header và alignment của object.
- Reference giữa object.
- Array/list backing storage.
- String object và character/byte storage.
- HashMap table và entry/node.
- Wrapper object cho primitive.
- Object lồng nhau và collection element.

Một payload chứa nhiều property nhỏ có thể tạo rất nhiều object. Một payload có một chuỗi dài có thể tạo ít object hơn nhưng chiếm nhiều bộ nhớ cho string/array.

Do đó, payload bytes là tín hiệu đầu vào hữu ích, nhưng không phải phép đo heap size. Muốn biết object graph tiêu thụ bao nhiêu bộ nhớ, cần profiling hoặc phép đo chuyên biệt trên representative objects.

## 11. Đo độ trễ bằng Timer

Không nên tự ghi timestamp ở nhiều chỗ bằng System.currentTimeMillis() nếu cần độ chính xác và tích hợp metric. Micrometer Timer là một lựa chọn phổ biến trong ứng dụng Spring và JVM.

Ví dụ:

~~~java
Timer.Sample sample = Timer.start(registry);
String outcome = "success";

try {
    return mapper.readValue(payload, Order.class);
}
catch (IOException ex) {
    outcome = "error";
    throw ex;
}
finally {
    sample.stop(registry.timer(
        "serialization.duration",
        "format", "json",
        "operation", "deserialize",
        "message_type", "order",
        "outcome", outcome
    ));
}
~~~

Timer thu thập số lần đo và tổng thời gian; tùy cấu hình registry có thể xuất histogram/percentiles. Đặt timer quanh đúng thao tác Jackson, không bao gồm việc nhận request hoặc xử lý nghiệp vụ nếu muốn đo riêng serialization.

Tên metric và tag cần ổn định. Không tạo tên metric mới theo từng class name tùy ý hoặc theo URL/request id.

## 12. Đo riêng serialize và deserialize

Không gộp cả hai chiều vào một timer:

~~~text
serialization.duration
  format=json
  operation=deserialize

serialization.duration
  format=json
  operation=serialize
~~~

Hai chiều có thể có xu hướng khác nhau. Ví dụ:

- Deserialize chậm sau khi thêm nhiều nested DTO.
- Serialize chậm sau khi custom serializer format một trường lớn.
- Một endpoint đọc payload nhỏ nhưng trả response rất lớn.

Metric riêng giúp xác định chiều nào gây ra độ trễ và nhóm message type nào có vấn đề.

## 13. Đo latency theo phân vị

Average latency có thể che giấu tail latency. Ví dụ:

| Chỉ số | Thời gian |
|---|---:|
| p50 | 4 ms |
| p90 | 9 ms |
| p95 | 18 ms |
| p99 | 240 ms |

Phần lớn request nhanh, nhưng 1% request chậm hơn rất nhiều. Với hệ thống có nhiều request, tail latency có thể ảnh hưởng đáng kể đến trải nghiệm và thời gian chờ của các service phía sau.

Nên theo dõi:

- p50 để hiểu trải nghiệm điển hình.
- p90/p95 để thấy nhóm request chậm.
- p99 để thấy tail latency.
- Max để điều tra spike, nhưng không dùng max đơn lẻ làm SLO.

Histogram thường phù hợp khi cần tổng hợp percentile giữa nhiều instance. Percentile tính riêng ở từng instance không thể luôn được gộp chính xác thành percentile toàn cụm.

## 14. Histogram và bucket

Với Micrometer, có thể bật percentile histogram cho Timer:

~~~java
Timer.builder("serialization.duration")
    .publishPercentileHistogram()
    .serviceLevelObjectives(
        Duration.ofMillis(5),
        Duration.ofMillis(10),
        Duration.ofMillis(25),
        Duration.ofMillis(50),
        Duration.ofMillis(100)
    )
    .register(registry);
~~~

Các bucket nên dựa trên SLO và phân phối thực tế. Không đặt quá nhiều bucket hoặc histogram cho hàng trăm metric không cần thiết vì sẽ tăng số time series và chi phí monitoring.

Hãy thống nhất bucket cho cùng metric giữa các instance. Nếu mỗi instance có cấu hình khác nhau, việc tổng hợp histogram sẽ khó diễn giải.

## 15. Đo kích thước bằng DistributionSummary

Kích thước payload là phân phối số, không phải thời gian. Micrometer DistributionSummary phù hợp hơn Timer:

~~~java
DistributionSummary.builder("serialization.payload.bytes")
    .baseUnit("bytes")
    .publishPercentileHistogram()
    .register(registry)
    .record(payloadBytes);
~~~

Có thể tag theo format và operation:

~~~java
DistributionSummary.builder("serialization.payload.bytes")
    .tag("format", "json")
    .tag("operation", "deserialize")
    .tag("message_type", "order")
    .register(registry)
    .record(payloadBytes);
~~~

Theo dõi p50/p95/p99 kích thước giúp thấy payload đang lớn dần. Một giá trị trung bình có thể che giấu một số ít payload cực lớn gây áp lực bộ nhớ.

## 16. Đo số lần thành công và thất bại

Timer có thể đếm số lần dừng, nhưng một Counter riêng có thể giúp biểu diễn outcome rõ ràng:

~~~java
Counter.builder("serialization.operations")
    .tag("format", "json")
    .tag("operation", "deserialize")
    .tag("outcome", "success")
    .register(registry)
    .increment();
~~~

Có thể ghi outcome error khi parser hoặc databind thất bại. Không nên dùng exception message làm tag vì message có thể chứa tên property động, giá trị đầu vào hoặc chuỗi khác nhau, tạo cardinality rất lớn.

Phân nhóm lỗi bằng một tập hữu hạn:

- syntax_error
- mapping_error
- input_too_large
- timeout
- unsupported_type
- validation_error
- other_error

Giữ loại lỗi có thể được xác định ổn định. Đừng cố parse mọi exception thành nhãn quá chi tiết nếu điều đó làm metric khó quản lý.

## 17. Một wrapper đo read/write có thể tái sử dụng

Có thể gom instrumentation vào một component để các service không tự viết timer khác nhau:

~~~java
public final class InstrumentedJackson {
    private final ObjectMapper mapper;
    private final MeterRegistry registry;

    public InstrumentedJackson(
            ObjectMapper mapper,
            MeterRegistry registry) {
        this.mapper = mapper;
        this.registry = registry;
    }

    public <T> T read(
            byte[] payload,
            Class<T> type,
            String messageType) throws IOException {

        Timer.Sample sample = Timer.start(registry);
        String outcome = "success";
        recordSize(payload.length, "deserialize", messageType);

        try {
            return mapper.readValue(payload, type);
        }
        catch (IOException | RuntimeException ex) {
            outcome = "error";
            throw ex;
        }
        finally {
            sample.stop(operationTimer(
                "deserialize", messageType, outcome
            ));
        }
    }

    private void recordSize(
            long bytes,
            String operation,
            String messageType) {
        DistributionSummary.builder("serialization.payload.bytes")
            .tag("format", "json")
            .tag("operation", operation)
            .tag("message_type", messageType)
            .register(registry)
            .record(bytes);
    }

    private Timer operationTimer(
            String operation,
            String messageType,
            String outcome) {
        return Timer.builder("serialization.duration")
            .tag("format", "json")
            .tag("operation", operation)
            .tag("message_type", messageType)
            .tag("outcome", outcome)
            .register(registry);
    }
}
~~~

Đây là ví dụ minh họa cho byte[] và JSON. Trong ứng dụng thực tế, nên cache Timer/DistributionSummary hoặc dùng registry cache theo bộ tag hữu hạn thay vì dựng builder ở mỗi request nếu profiling cho thấy chi phí lookup đáng kể. Cũng cần thêm phương thức write và xử lý InputStream/OutputStream theo ownership của caller.

## 18. Không tạo metric tag có cardinality cao

Tag tốt là tập giá trị nhỏ và ổn định:

- format: json, xml, cbor, smile.
- operation: serialize, deserialize.
- message_type: order, user, payment.
- outcome: success, error.

Tag không tốt:

- request_id.
- user_id.
- email.
- raw URL có path id.
- exception message.
- payload hash nếu mỗi request khác nhau.
- tên tenant không giới hạn nếu hệ thống có hàng trăm nghìn tenant.

Mỗi tổ hợp tag tạo một time series. Cardinality cao làm tăng bộ nhớ, CPU và chi phí lưu trữ của hệ thống monitoring, đôi khi chính hệ thống metrics trở thành nguồn tải lớn.

Nếu cần truy vết một request cụ thể, dùng trace/span id trong tracing hoặc log có kiểm soát, không đưa nó vào metric label.

## 19. Theo dõi bộ nhớ ở cấp JVM

Jackson chạy trong JVM nên cần quan sát:

- Heap used.
- Heap committed.
- Heap max.
- Non-heap memory.
- Garbage collection count và pause duration.
- Allocation rate.
- Thread count.
- Direct buffer/native memory nếu dùng NIO hoặc transport có buffer ngoài heap.

Micrometer thường tích hợp các JVM metrics như:

- jvm.memory.used
- jvm.memory.committed
- jvm.memory.max
- jvm.gc.pause
- jvm.threads.live

Các tên và tag chính xác phụ thuộc Micrometer version/registry. Cần kiểm tra dashboard đang nhận metric gì thay vì giả định mọi runtime có cùng bộ metric.

Heap used là số liệu toàn JVM. Nó không cho biết một lần deserialize cụ thể đã tạo ra bao nhiêu byte object.

## 20. Đừng đo heap trước và sau mỗi request rồi quy toàn bộ chênh lệch cho Jackson

Một cách đo không đáng tin:

~~~java
long before = runtime.totalMemory() - runtime.freeMemory();
Order order = mapper.readValue(payload, Order.class);
long after = runtime.totalMemory() - runtime.freeMemory();
long difference = after - before;
~~~

Chênh lệch có thể bị ảnh hưởng bởi:

- Thread khác đang cấp phát object.
- GC chạy giữa hai lần đọc.
- JIT compiler và class loading.
- Buffer hoặc cache được tạo lần đầu.
- Object được giữ lại hoặc giải phóng ngay sau thao tác.
- JVM mở rộng hoặc co heap.

Số chênh lệch này không phải memory allocation của Jackson và không nên được ghi như một metric chính xác theo request.

Để đo allocation, dùng JFR, profiler hoặc benchmark chuyên dụng. Để vận hành, theo dõi heap/GC ở cấp JVM và liên hệ với throughput, payload size, concurrency.

## 21. Allocation rate và garbage collection

Jackson có thể tạo nhiều object trong quá trình bind:

- DTO và nested DTO.
- String.
- ArrayList, HashMap và backing array.
- Wrapper cho scalar.
- BigDecimal/BigInteger.
- JsonNode tree.
- Token buffer hoặc intermediate representation.

Nếu throughput tăng, allocation rate có thể tăng ngay cả khi heap used trung bình không đổi vì GC thu gom nhanh. Khi GC phải chạy thường xuyên hơn, CPU dành cho application giảm và tail latency có thể tăng.

Theo dõi cùng nhau:

| Tín hiệu | Điều có thể cho biết |
|---|---|
| Allocation rate tăng | Nhiều object được tạo hơn mỗi giây |
| Young GC tăng | Tạo nhiều object sống ngắn |
| Old generation tăng liên tục | Object được giữ lâu, cache hoặc leak có thể xảy ra |
| GC pause p99 tăng | Request có thể bị dừng lâu hơn |
| Heap occupancy sau GC tăng | Live set đang tăng |

Không kết luận memory leak chỉ từ heap used tăng trong một khoảng ngắn. Cần xem xu hướng sau GC và live set qua thời gian.

## 22. Đo allocation bằng Java Flight Recorder

JFR có thể thu thập thông tin allocation, GC, thread và CPU với overhead thường phù hợp cho điều tra production nếu cấu hình hợp lý.

Ví dụ bắt đầu recording bằng JDK tooling:

~~~text
jcmd <pid> JFR.start name=jackson-profile settings=profile duration=60s filename=jackson-profile.jfr
~~~

Tên option và khả năng ghi file phụ thuộc JDK/runtime. Có thể dùng JFR recording liên tục với cấu hình phù hợp hoặc bắt đầu recording khi phát hiện spike.

Trong JDK Mission Control, xem:

- Allocation in new TLAB.
- Allocation outside TLAB.
- Hot methods.
- Garbage collection pauses.
- Thread contention.
- CPU samples.

Tìm stack trace có Jackson parser, databind, serializer hoặc custom converter. Đối chiếu với message type và thời điểm tải cao.

JFR giúp xác định nơi cấp phát; nó không tự cho biết mọi allocation thuộc một request cụ thể nếu ứng dụng không có trace/context phù hợp.

## 23. Profiling allocation bằng công cụ chuyên dụng

Khi cần phân tích sâu, có thể dùng:

- Java Flight Recorder/JDK Mission Control.
- Async-profiler.
- YourKit hoặc JProfiler.
- VisualVM trong môi trường phù hợp.
- Heap dump và dominator tree.

Một quy trình điều tra:

1. Tái hiện với payload đại diện.
2. Ghi CPU/allocation profile.
3. Tìm hot path trong Jackson và custom serializer.
4. Xem loại object chiếm allocation lớn.
5. Kiểm tra object nào còn được giữ lại sau request.
6. So sánh trước/sau khi thay đổi DTO hoặc cấu hình.

Đừng tối ưu chỉ dựa trên số lượng object trong một snapshot. Allocation rate, object lifetime và retained heap là ba khái niệm khác nhau.

## 24. Kích thước payload ảnh hưởng memory thế nào?

Một lần deserialize từ byte[] có thể đồng thời giữ:

- Byte array gốc.
- Buffer nội bộ của parser.
- String/number token tạm thời.
- Java object graph được tạo.
- Một số buffer hoặc cache khác.

Nếu body đã được copy qua nhiều wrapper, có thể tồn tại nhiều bản sao byte. Nếu đọc vào JsonNode, toàn bộ cây JSON cũng được giữ trong heap.

Với một số luồng, peak memory có thể lớn hơn nhiều lần kích thước payload. Tỷ lệ này không cố định; nó phụ thuộc nội dung, encoding, target class, collection, String và parser.

Hãy đo với payload đại diện thay vì dùng một hệ số chung như JSON luôn tốn gấp ba lần.

## 25. ObjectMapper.readValue không đồng nghĩa với streaming object graph

Gọi:

~~~java
Order order = mapper.readValue(inputStream, Order.class);
~~~

giúp parser đọc từ stream mà không bắt buộc ứng dụng phải giữ một byte[] toàn bộ payload. Nhưng Databind vẫn tạo object graph hoàn chỉnh theo kiểu Order trước khi trả kết quả.

Nếu Order có hàng triệu dòng item, danh sách đó vẫn chiếm bộ nhớ dù input được đọc từ InputStream.

Streaming parser:

~~~java
try (JsonParser parser = factory.createParser(inputStream)) {
    // Xử lý từng token và chỉ giữ dữ liệu cần thiết.
}
~~~

có thể giảm lượng object trung gian và tránh materialize toàn bộ collection, nhưng yêu cầu code xử lý token. Chỉ chuyển byte[] thành InputStream không tự động biến việc bind một collection lớn thành streaming processing.

## 26. JsonNode tree thường giữ nhiều dữ liệu trong bộ nhớ

Đọc:

~~~java
JsonNode root = mapper.readTree(inputStream);
~~~

thường tạo một cây node đại diện cho document. Sau đó, nếu convert tree thành POJO:

~~~java
Order order = mapper.treeToValue(root, Order.class);
~~~

ứng dụng có thể giữ cả cây JsonNode và object graph trong cùng thời gian. Với payload lớn, peak heap có thể tăng đáng kể.

Tree model hữu ích khi cần truy cập field động hoặc chỉnh sửa cấu trúc. Nếu chỉ cần bind một DTO đã biết, đọc trực tiếp vào DTO thường tránh một cây trung gian.

Nếu phải giữ JsonNode để forward hoặc inspect, hãy xác định thời điểm giải phóng reference và tránh lưu cả tree trong cache lâu hơn cần thiết.

## 27. Streaming từng phần tử của collection lớn

Giả sử JSON có một array lớn:

~~~json
{
  "items": [
    {"id": 1, "amount": 10},
    {"id": 2, "amount": 20}
  ]
}
~~~

Nếu bind vào:

~~~java
OrderBatch batch = mapper.readValue(input, OrderBatch.class);
~~~

toàn bộ List item sẽ được tạo.

Nếu nghiệp vụ có thể xử lý từng item độc lập, dùng streaming parser để đọc từng object, xử lý rồi loại reference trước khi đọc phần tiếp theo. Cần đảm bảo logic giao dịch, lỗi giữa chừng, thứ tự và retry được thiết kế phù hợp.

Streaming giúp giảm peak memory khi không cần giữ tất cả phần tử. Nó không miễn phí: code phức tạp hơn, khó random access và có thể làm thay đổi cách validation toàn document.

## 28. Ghi output lớn theo stream

Serialize thành String:

~~~java
String json = mapper.writeValueAsString(largeResponse);
response.getWriter().write(json);
~~~

có thể giữ đồng thời String lớn và buffer của HTTP response.

Nếu framework cho phép, ghi trực tiếp:

~~~java
mapper.writeValue(responseOutputStream, largeResponse);
~~~

Điều này tránh tạo String trung gian. Tuy nhiên, object graph largeResponse vẫn nằm trong heap; streaming output chỉ giảm buffering của serialized bytes.

Nếu response được nén, theo dõi cả byte trước nén và sau nén. Một output nhỏ sau gzip có thể cần nhiều bộ nhớ/CPU để tạo và nén dữ liệu.

## 29. Đo concurrency và số thao tác đang chạy

Một request deserialize 5 MB có thể chấp nhận được khi chỉ có một request. Cùng payload đó có thể gây áp lực khi 100 request chạy đồng thời.

Theo dõi:

- Số thao tác Jackson đang chạy.
- Số request đang chờ đọc body.
- Số request đang chờ slot xử lý.
- Thread pool active/queue size.
- Throughput theo format/message type.
- Payload size p95/p99.

Một gauge đơn giản có thể dùng AtomicInteger:

~~~java
AtomicInteger inFlight = new AtomicInteger();

Gauge.builder(
    "serialization.in_flight",
    inFlight,
    AtomicInteger::get
).register(registry);
~~~

Bao quanh thao tác:

~~~java
inFlight.incrementAndGet();
try {
    return mapper.readValue(payload, Order.class);
}
finally {
    inFlight.decrementAndGet();
}
~~~

Gauge chỉ phản ánh số thao tác đồng thời trong vùng code được instrument. Nếu cần queue wait hoặc concurrency toàn request, đo riêng ở tầng executor/server.

## 30. Giới hạn kích thước đầu vào ở tầng transport

Không nên chờ Jackson parse xong mới phát hiện body quá lớn. Đặt giới hạn tại tầng nhận dữ liệu:

- HTTP server request body limit.
- API gateway hoặc reverse proxy.
- Message broker max message size.
- File upload limit.
- Application-level bounded stream.

Nếu ứng dụng đọc body vào byte[] trước khi kiểm tra length, nó đã phải cấp phát bộ nhớ cho toàn bộ payload. Giới hạn nên được thực thi trong lúc đọc hoặc trước khi buffer toàn bộ.

Hãy xác định giới hạn theo use case và theo message type nếu chúng có kích thước khác nhau. Một endpoint upload file có thể cần giới hạn khác endpoint nhận event nhỏ.

## 31. Phân biệt giới hạn compressed và decompressed

Một payload nén có thể rất nhỏ nhưng giải nén thành dữ liệu rất lớn. Vì vậy, giới hạn byte trên mạng chưa đủ.

Ví dụ:

~~~text
Compressed body:   200 KB
Decompressed body: 80 MB
~~~

Theo dõi:

- compressed bytes.
- decompressed bytes.
- decompression ratio.
- thời gian giải nén.
- thời gian Jackson parse sau giải nén.

Đặt giới hạn cho cả hai kích thước và tỷ lệ nén khi phù hợp. Đừng chỉ đo body sau giải nén rồi không biết network đã nhận bao nhiêu byte.

## 32. Giới hạn parser cho cấu trúc quá sâu hoặc token quá lớn

Ngoài tổng kích thước, một payload có thể gây tốn tài nguyên do:

- Object/array lồng nhau quá sâu.
- String token rất dài.
- Number token rất dài.
- Nhiều field hoặc phần tử nhỏ.
- Cấu trúc khó parse hoặc khó bind.

Các phiên bản Jackson Core hiện đại cung cấp StreamReadConstraints để giới hạn một số đặc điểm của input. Ví dụ:

~~~java
StreamReadConstraints constraints =
    StreamReadConstraints.builder()
        .maxNestingDepth(100)
        .maxStringLength(1_000_000)
        .maxNumberLength(1_000)
        .build();

JsonFactory factory = JsonFactory.builder()
    .streamReadConstraints(constraints)
    .build();

ObjectMapper mapper = new ObjectMapper(factory);
~~~

API và giới hạn có thể khác theo Jackson version. Kiểm tra Javadoc của phiên bản đang dùng; không copy cấu hình từ phiên bản khác mà không xác nhận method có tồn tại.

Các giới hạn này bổ sung cho body size limit. Chúng không thay thế giới hạn request, timeout hoặc giới hạn số phần tử theo nghiệp vụ.

## 33. Đo số token hoặc số phần tử khi cần

Byte size không thể diễn tả đầy đủ độ phức tạp cấu trúc. Hai payload cùng 1 MB có thể rất khác:

- Một payload có một field string dài.
- Một payload có hàng chục nghìn object nhỏ.

Nếu cần điều tra, có thể đo số token hoặc số phần tử bằng parser instrumentation trong benchmark/diagnostic path. Tuy nhiên, không nên thêm một vòng parse thứ hai vào mọi request chỉ để đếm token; việc đó có thể gần như nhân đôi CPU.

Có thể lấy số lượng từ nghiệp vụ sau khi bind, ví dụ số item trong List. Nếu cần token count chính xác, thực hiện trong cùng một lượt streaming parser hoặc lấy từ profile/sample.

## 34. Theo dõi cấu trúc lồng nhau và kích thước collection

Một DTO có thể có collection lớn:

~~~java
public class Order {
    private List<OrderLine> lines;
}
~~~

Theo dõi số item có thể giúp giải thích latency:

- payload bytes tăng.
- số lines tăng.
- deserialize duration tăng.
- allocation/GC tăng.

Metric số item nên được đo bằng DistributionSummary hoặc histogram riêng nếu thực sự cần. Không gắn giá trị item count vào tag vì mỗi giá trị tạo time series mới.

Nếu có nhiều collection, chỉ theo dõi các collection quan trọng với hiệu năng. Đừng instrument mọi field trong DTO nếu không có câu hỏi vận hành cụ thể.

## 35. Phân biệt latency do Jackson và latency do I/O

Khi gọi:

~~~java
mapper.readValue(inputStream, Order.class);
~~~

thời gian đo bao gồm việc parser đọc stream. Nếu stream lấy từ network hoặc storage, timer có thể chứa thời gian chờ I/O.

Nếu mục tiêu là đo CPU/binding của Jackson:

- Dùng payload đã có trong memory ở benchmark.
- Hoặc đo thời gian đọc body riêng trước khi deserialize.
- Hoặc dùng profiler để tách CPU time khỏi wall-clock time.

Trong production, vẫn nên có timer bao quanh thao tác end-to-end với InputStream vì đó là latency mà service trải nghiệm. Nhưng đặt tên và diễn giải đúng: đây là thời gian đọc và bind từ stream, có thể bao gồm I/O.

## 36. Phân biệt wall-clock latency và CPU time

Wall-clock time đo thời gian trôi qua:

- Có thể bao gồm I/O wait.
- Có thể bị ảnh hưởng bởi thread scheduling.
- Có thể tăng khi GC pause.
- Có thể tăng khi CPU bị tranh chấp.

CPU time đo lượng thời gian CPU thực sự dùng cho thread/process. Nó giúp xác định thao tác compute-bound hay chờ tài nguyên, nhưng không thay thế latency mà client quan sát.

Micrometer Timer thường đo wall-clock duration. Để phân tích CPU, dùng JFR, profiler hoặc ThreadMXBean phù hợp.

## 37. Không ghi payload vào log để điều tra latency

Ghi toàn bộ JSON/XML giúp tái hiện lỗi nhưng có thể:

- Làm lộ dữ liệu cá nhân hoặc bí mật.
- Tăng I/O log và chi phí lưu trữ.
- Tạo thêm String allocation.
- Làm request chậm hơn.
- Tạo log event rất lớn.

Thay vào đó, log metadata có giới hạn:

- format.
- operation.
- message type.
- payload size.
- duration.
- outcome/error category.
- trace id.
- schema version nếu có.

Không ghi raw payload, token, password, email hoặc giá trị field nhạy cảm. Nếu cần sample để debug, dùng cơ chế sampling có redaction và retention được kiểm soát.

## 38. Log lỗi có cấu trúc và giới hạn kích thước

Một log event hữu ích:

~~~text
event=serialization_failed
format=json
operation=deserialize
message_type=order
payload_bytes=1048576
duration_ms=32
error_category=mapping_error
trace_id=...
~~~

Không nối toàn bộ exception message vào metric tag. Log stack trace theo policy và tránh để parser exception in nguyên payload nếu thư viện/cấu hình có thể chứa input snippet.

Với lỗi do payload quá lớn, log size và giới hạn đã áp dụng. Không cần log toàn bộ nội dung bị từ chối.

## 39. Dùng tracing để nối latency với request

Metrics cho xu hướng tổng thể; tracing giúp điều tra một request cụ thể.

Có thể tạo span:

~~~text
HTTP request
  ├── request body read
  ├── jackson deserialize
  ├── validation
  ├── business service
  ├── jackson serialize
  └── response write
~~~

Span attributes có thể gồm:

- serialization.format.
- serialization.operation.
- serialization.message_type.
- serialization.payload_bytes.
- serialization.outcome.

Chỉ thêm attribute có giá trị hữu hạn hoặc số liệu cần thiết. Không đưa payload, customer identifier hoặc giá trị field nhạy cảm vào span.

Sampling tracing phải được cấu hình để giữ đủ request lỗi/chậm nếu hệ thống hỗ trợ tail-based sampling. Không tạo span riêng cho mọi field hoặc mọi token.

## 40. Dashboard nên đặt các tín hiệu cạnh nhau

Một dashboard vận hành Jackson có thể có:

| Panel | Metric | Cách đọc |
|---|---|---|
| Payload input | p50/p95/p99 bytes | Payload đang lớn lên hay xuất hiện outlier |
| Payload output | p50/p95/p99 bytes | Response/event có đang phình to |
| Deserialize latency | p50/p95/p99 | Chi phí đọc/bind |
| Serialize latency | p50/p95/p99 | Chi phí ghi |
| Error rate | success/error counters | Mapping/parser failure |
| In-flight | gauge | Mức concurrency |
| JVM heap | used/committed/max | Áp lực heap tổng thể |
| GC pause | count/time/percentiles | Tác động dọn rác |
| Allocation rate | bytes per second | Áp lực object creation |
| Throughput | operations per second | Tải thực tế |

Một panel đơn lẻ hiếm khi đủ. Ví dụ latency tăng cùng payload size tăng có thể là tải dữ liệu lớn hơn; latency tăng trong khi payload ổn định và GC pause tăng có thể liên quan memory pressure hoặc allocation.

## 41. Đọc tương quan giữa payload, latency và memory

Một số mẫu hình thường gặp:

| Quan sát | Khả năng cần điều tra |
|---|---|
| Payload p95 tăng, latency p95 tăng | Payload lớn hơn hoặc cấu trúc phức tạp hơn |
| Payload ổn định, latency tăng | Mapper config, custom serializer, CPU contention hoặc GC |
| Throughput tăng, allocation rate tăng | Nhiều object được tạo theo tải |
| Heap sau GC tăng dần | Live object set tăng, cache hoặc object retention |
| Latency p99 tăng cùng GC pause | GC có thể góp phần vào tail latency |
| Output bytes tăng sau release | Serializer thêm field, format hoặc dữ liệu lồng nhau |
| Chỉ một message type chậm | DTO/custom handler hoặc payload riêng của loại đó |
| Chỉ deserialize chậm | Parser, conversion hoặc object creation |
| Chỉ serialize chậm | Getter, custom serializer, output buffering hoặc escaping |

Đây là giả thuyết để điều tra, không phải kết luận tự động. Dùng trace/profile và dữ liệu đại diện để xác nhận.

## 42. Đo baseline trước khi tối ưu

Trước một thay đổi:

1. Chọn payload đại diện cho p50, p95 và trường hợp lớn.
2. Đo deserialize latency.
3. Đo serialize latency.
4. Đo throughput.
5. Ghi allocation rate và GC.
6. Ghi kích thước output.
7. Ghi phiên bản JDK, Jackson và module.
8. Cố định cấu hình mapper và phần cứng benchmark.

Không so sánh hai kết quả nếu một bên dùng payload nhỏ hơn, JDK khác, GC khác hoặc mapper config khác.

## 43. Benchmark Jackson bằng JMH

JMH phù hợp để benchmark micro-level:

- Deserialize payload vào DTO.
- Serialize DTO ra bytes.
- Đọc JsonNode so với POJO.
- Streaming parser so với databind.
- Custom serializer A so với B.

Ví dụ khung:

~~~java
@State(Scope.Thread)
@BenchmarkMode(Mode.AverageTime)
@OutputTimeUnit(TimeUnit.MICROSECONDS)
public class JacksonBenchmark {

    private ObjectMapper mapper;
    private byte[] payload;
    private Order order;

    @Setup
    public void setup() throws Exception {
        mapper = new ObjectMapper();
        payload = Files.readAllBytes(
            Path.of("src/test/resources/order.json")
        );
        order = mapper.readValue(payload, Order.class);
    }

    @Benchmark
    public Order deserialize() throws Exception {
        return mapper.readValue(payload, Order.class);
    }

    @Benchmark
    public byte[] serialize() throws Exception {
        return mapper.writeValueAsBytes(order);
    }
}
~~~

Đây là skeleton; cần cấu hình JMH dependencies, fork, warmup, measurement iterations và profiler phù hợp. Không dùng một lần chạy trong IDE để kết luận hiệu năng.

## 44. Tránh benchmark sai do warmup và dead-code elimination

Benchmark JVM cần:

- Warmup để JIT compile code nóng.
- Nhiều measurement iterations.
- Fork JVM để giảm ảnh hưởng trạng thái trước đó.
- Consume kết quả để tránh dead-code elimination.
- Không tạo fixture hoặc mapper ngoài mục tiêu đo trong benchmark method.

JMH xử lý nhiều vấn đề này nếu dùng đúng annotation/runner. Đừng viết vòng lặp nanoTime thủ công rồi so sánh hai phương án bằng một lần chạy.

## 45. Đo allocation trong JMH

JMH có thể kết hợp profiler để quan sát allocation. Ví dụ dùng GC profiler của JMH:

~~~text
java -jar benchmarks.jar JacksonBenchmark -prof gc
~~~

Các kết quả như allocation rate hoặc bytes/op giúp so sánh hai cách xử lý. Chú ý benchmark có thể bị ảnh hưởng bởi payload, object reuse và mapper warmup.

Nếu benchmark serialize cùng một object immutable, nó không đại diện cho trường hợp mỗi request tạo object mới. Hãy tạo state phù hợp với workload thật.

## 46. Benchmark phải dùng payload đại diện

Tạo nhiều profile dữ liệu:

- Payload nhỏ, phổ biến.
- Payload trung bình.
- Payload gần giới hạn.
- Payload có nhiều nested object.
- Payload có collection lớn.
- Payload có String dài/Unicode.
- Payload có BigDecimal hoặc date/time conversion.
- Payload có polymorphic subtype.

Một payload synthetic chỉ chứa vài field scalar có thể khiến benchmark quá lạc quan. Hãy dùng cấu trúc tương tự production nhưng không chứa dữ liệu nhạy cảm.

## 47. Load test để thấy ảnh hưởng concurrency

JMH đo thao tác cô lập. Load test kiểm tra service trong tải đồng thời:

- Nhiều request deserialize cùng lúc.
- Nhiều response serialize cùng lúc.
- Payload size có phân phối gần production.
- Compression bật/tắt như production.
- Thread pool và connection pool tương tự.
- GC/JVM flags tương tự môi trường triển khai.

Theo dõi throughput, p95/p99, heap, allocation, GC pause và error rate. Một cách serialize nhanh hơn ở một thread có thể tạo allocation cao hơn và giảm throughput khi concurrency tăng.

## 48. Không benchmark bằng dữ liệu hoàn toàn nằm trong cache nếu production khác

Payload byte[] được giữ sẵn trong heap có thể cho kết quả khác so với:

- Đọc từ network.
- Đọc từ file.
- Đọc từ message broker.
- Giải nén trước khi parse.
- Dữ liệu được copy qua nhiều buffer.

Tách benchmark mapper thuần với integration/load test của đường đi thực tế. Hai loại trả lời hai câu hỏi khác nhau.

## 49. Theo dõi sau khi nâng cấp Jackson

Khi nâng Jackson Core, Databind hoặc dataformat module:

- Ghi lại version cũ/mới.
- Giữ cùng tập fixture.
- Chạy read/write contract tests.
- Chạy benchmark cùng JDK và payload.
- So sánh payload bytes, latency và allocation.
- Kiểm tra error rate và log exception mới.
- Theo dõi production canary sau rollout.

Một bản nâng cấp có thể thay đổi parser behavior, buffer strategy, coercion, serializer hoặc binary encoding. Không nên kết luận chỉ từ release notes; hãy đo trên workload ứng dụng.

## 50. So sánh cấu hình mapper như một biến hiệu năng

Một số lựa chọn có thể ảnh hưởng chi phí:

- Đọc vào POJO hay JsonNode.
- Sử dụng Afterburner/Blackbird nếu phù hợp phiên bản và runtime.
- Custom serializer/deserializer.
- Naming strategy và annotation introspection.
- Date/time module.
- Pretty printing.
- Buffering output.
- Streaming so với databinding.

Không bật module tối ưu chỉ vì tên gọi. Benchmark và contract tests phải chứng minh cả hiệu năng lẫn wire compatibility.

Pretty printing tăng kích thước output và có thể tăng chi phí encode. Với payload gửi qua mạng, thường chỉ bật cho debug hoặc file người dùng cần đọc, không bật mặc định cho message throughput cao nếu không có lý do.

## 51. Tái sử dụng ObjectMapper

ObjectMapper được thiết kế để cấu hình rồi tái sử dụng. Tạo mapper mới cho mỗi request có thể gây chi phí cấu hình, cache introspection và module registration.

Mô hình thường dùng:

~~~java
@Bean
ObjectMapper objectMapper() {
    return JsonMapper.builder()
        .addModule(new JavaTimeModule())
        .build();
}
~~~

Sau khi đã dùng mapper, tránh thay đổi cấu hình toàn cục. Nếu cần nhiều profile, tạo nhiều mapper được cấu hình riêng từ đầu hoặc dùng ObjectReader/ObjectWriter cho tùy chọn theo thao tác.

Không tạo một ObjectMapper mới trong mỗi lần gọi service nếu không có yêu cầu isolation cụ thể.

## 52. Tái sử dụng JsonFactory và buffer recycler

Jackson Core có cơ chế quản lý buffer để giảm allocation trong quá trình parse/generate. Cách recycler hoạt động phụ thuộc version và cấu hình factory.

Nên:

- Tái sử dụng factory/mapper theo hướng dẫn của Jackson.
- Không tự giữ buffer nội bộ ngoài API công khai.
- Không chia sẻ JsonParser hoặc JsonGenerator đang hoạt động giữa thread.
- Đóng parser/generator đúng ownership.
- Kiểm tra cấu hình recycler nếu ứng dụng có nhiều classloader hoặc môi trường container đặc thù.

Đừng viết code phụ thuộc vào implementation detail của buffer recycler chỉ để giảm vài allocation mà chưa có profile chứng minh.

## 53. Parser và generator không nên được chia sẻ đồng thời

ObjectMapper có thể được chia sẻ giữa nhiều thread sau khi cấu hình hoàn tất. Nhưng JsonParser và JsonGenerator đại diện cho một luồng đọc/ghi cụ thể, không nên dùng chung đồng thời giữa request.

Mỗi thao tác tạo parser/generator riêng từ factory hoặc để ObjectMapper quản lý parser/generator trong API read/write. Đóng tài nguyên theo ownership.

Một lỗi chia sẻ parser có thể gây dữ liệu lẫn nhau, lỗi token hoặc race condition khó tái hiện.

## 54. Backpressure và giới hạn concurrency

Nếu payload lớn khiến deserialize tiêu tốn nhiều CPU/heap, tăng thread pool vô hạn không làm hệ thống khỏe hơn. Nhiều thao tác cùng lúc có thể tạo peak memory:

~~~text
Peak memory xấp xỉ
  số thao tác đồng thời
  x payload memory amplification
  + live application state
  + buffer và runtime overhead
~~~

Đây chỉ là mô hình tư duy, không phải công thức dự đoán chính xác. Hãy đo mức tiêu thụ ở tải thực tế.

Các biện pháp:

- Giới hạn request/message size.
- Giới hạn số thao tác parse nặng đồng thời.
- Dùng bounded queue.
- Áp dụng backpressure ở broker/reactive pipeline.
- Timeout cho việc đọc stream.
- Từ chối payload quá lớn sớm.
- Tách luồng xử lý file lớn khỏi request latency-sensitive.

Không tăng concurrency chỉ để cải thiện throughput nếu heap/GC đang là bottleneck.

## 55. Theo dõi queue wait và execution time riêng

Một thao tác có thể chậm vì chờ slot executor chứ không phải Jackson:

~~~text
Request arrives
   |
   v
Queue wait
   |
   v
Jackson deserialize
   |
   v
Business processing
~~~

Đo:

- Queue wait duration.
- Jackson duration.
- Business duration.
- End-to-end duration.

Nếu queue wait tăng nhưng Jackson duration ổn định, tăng worker hoặc tối ưu mapper có thể không giải quyết đúng nguyên nhân. Hãy xem CPU saturation, thread pool và downstream dependency.

## 56. Timeout cho stream và xử lý payload

Một payload không lớn vẫn có thể đến rất chậm nếu stream bị chậm hoặc producer gửi dữ liệu nhỏ giọt. Đo wall-clock time quanh InputStream có thể bao gồm thời gian chờ.

Đặt timeout ở tầng transport/stream, không dựa vào Jackson parser để tự quản lý mọi timeout mạng.

Nếu parser đọc file local, timeout có thể ít quan trọng hơn nhưng vẫn cần giới hạn tổng thời gian cho job lớn. Phân biệt:

- Read timeout.
- Decompression timeout.
- Deserialize execution time.
- Overall request deadline.

## 57. Cảnh báo theo SLO thay vì một ngưỡng tùy ý

Một số cảnh báo hữu ích:

- p95/p99 deserialize latency vượt SLO trong một khoảng thời gian.
- Error rate tăng đột biến.
- p99 payload bytes vượt baseline hoặc hard limit.
- Heap sau GC tiến gần ngưỡng nguy hiểm.
- GC pause p99 tăng.
- Allocation rate tăng kéo dài cùng throughput ổn định.
- In-flight serialization vượt concurrency budget.

Đặt ngưỡng dựa trên baseline, capacity và SLO. Một payload lớn đơn lẻ có thể là bình thường; cảnh báo nên phân biệt spike ngắn với xu hướng kéo dài.

Không cảnh báo chỉ dựa trên heap used cao tức thời nếu GC chưa có cơ hội chạy. Quan sát heap sau GC và xu hướng live set hữu ích hơn.

## 58. Tách hard limit khỏi performance alert

Hard limit bảo vệ tài nguyên:

- Body vượt kích thước tối đa.
- Nesting depth vượt giới hạn.
- String/number token vượt giới hạn.
- Số phần tử vượt giới hạn nghiệp vụ.
- Stream vượt deadline.

Performance alert phát hiện hệ thống đang chậm hơn baseline:

- p95 latency tăng.
- GC pause tăng.
- Throughput giảm.
- Queue wait tăng.

Hard limit thường phải từ chối request ngay theo policy. Performance alert thường kích hoạt điều tra hoặc scale/rollback tùy tình hình.

## 59. Metric theo message type cần danh sách hữu hạn

Nếu hệ thống có nhiều loại message, tag message_type có thể hữu ích:

~~~text
serialization.duration{message_type="order"}
serialization.duration{message_type="payment"}
serialization.duration{message_type="user"}
~~~

Chỉ dùng type name đã được kiểm soát. Không dùng class name từ input hoặc header tùy ý nếu client có thể tạo vô hạn loại.

Với generic event envelope, có thể map event type bên ngoài vào một tập nhóm metric hữu hạn, còn tên event chi tiết nằm trong log/tracing có kiểm soát.

## 60. Theo dõi format và content encoding riêng

Nếu service nhận JSON, XML, Smile hoặc CBOR, tách format:

- json.
- xml.
- smile.
- cbor.
- avro.
- protobuf.

Content encoding là chiều khác:

- identity.
- gzip.
- br.

Không gộp content encoding vào format. Một payload JSON gzip vẫn là JSON ở tầng serialization và gzip ở tầng transport.

Có thể theo dõi:

~~~text
serialization.payload.bytes{format="json", operation="deserialize"}
transport.body.bytes{content_encoding="gzip"}
~~~

Điều này giúp phát hiện payload tăng do schema hay do compression ratio thay đổi.

## 61. Theo dõi lỗi kích thước và parser constraints

Khi từ chối input:

- Ghi error category như input_too_large hoặc nesting_limit.
- Ghi byte count nếu biết.
- Ghi giới hạn áp dụng.
- Ghi format và message type.
- Ghi trace id.

Không ghi toàn bộ payload. Nếu body vượt giới hạn, có thể dừng đọc sớm; không cố đọc hết chỉ để có kích thước chính xác nếu việc đó làm tăng tải.

Đối với stream bị dừng sớm, metric byte count là số byte đã đọc đến thời điểm từ chối, không phải tổng kích thước message. Đặt tên/description metric cho đúng semantics.

## 62. Kích thước đầu vào và output cần được so sánh theo cùng điều kiện

Nếu đo input sau gzip nhưng output trước gzip, tỷ lệ input/output không có ý nghĩa trực tiếp.

Hãy ghi:

- Input compressed bytes.
- Input decompressed bytes.
- Jackson output bytes.
- Output compressed bytes.

Nếu cần tính compression ratio:

~~~text
compression_ratio =
    compressed_bytes / decompressed_bytes
~~~

Xác định rõ tỷ lệ đang dùng chiều nào. Một số dashboard thường dùng decompressed/compressed để biểu diễn mức nở; hãy đặt tên metric rõ ràng.

## 63. Theo dõi output size để phát hiện schema phình to

Output bytes có thể tăng sau khi:

- Thêm field response.
- Thêm metadata hoặc trace context.
- Chuyển enum thành object.
- Bật pretty printing.
- Ghi null/default field.
- Thay đổi date format.
- Thêm collection hoặc nested object.

Theo dõi p95/p99 output bytes theo message type giúp phát hiện thay đổi wire contract trước khi client hoặc broker bị ảnh hưởng.

Nếu output size tăng mạnh sau một release, so sánh fixture/golden output và trace để tìm field mới hoặc cấu trúc bị lặp.

## 64. Đo hiệu năng custom serializer và deserializer

Custom handler có thể gọi:

- Formatter theo locale.
- Database hoặc service bên ngoài.
- Reflection.
- Regex.
- Crypto/hash.
- Parser phụ.
- Chuyển đổi BigDecimal hoặc date/time.

Không nên thực hiện I/O mạng hoặc database query bên trong serializer/deserializer. Jackson mapping nên là chuyển đổi dữ liệu thuần và có thời gian thực thi dự đoán được.

Nếu custom handler có chi phí đáng kể, benchmark riêng và profile stack trace. Có thể thêm span hoặc timer riêng cho handler quan trọng nhưng tránh instrument từng property nhỏ.

## 65. Đừng đặt metric cho từng field

Một DTO có hàng trăm field. Metric riêng cho mỗi property thường:

- Tạo quá nhiều time series.
- Tăng overhead instrumentation.
- Khó duy trì khi schema thay đổi.
- Không trả lời câu hỏi vận hành tổng thể.

Theo dõi theo message type, operation, format và outcome trước. Nếu một field cụ thể là bottleneck, dùng profiler hoặc diagnostic benchmark tập trung thay vì metric luôn bật cho mọi request.

## 66. Quan sát cache và mapper initialization

ObjectMapper có thể cache metadata về serializer/deserializer và introspection. Tạo mapper mới liên tục có thể làm mất lợi ích cache và tăng CPU/allocation.

Nếu latency chỉ cao ở request đầu tiên sau startup hoặc sau khi gặp một kiểu mới, hãy kiểm tra:

- Class loading.
- Serializer/deserializer resolution.
- Module registration.
- Cache warmup.
- JIT warmup.

Đừng warm up toàn bộ DTO bằng cách phát request giả vào production nếu có side effect. Nếu cần warmup, gọi đường đi serialization an toàn với object mẫu không gây ghi dữ liệu ra ngoài.

## 67. Đo startup và thời gian khởi tạo mapper

Trong service có nhiều mapper/module, startup có thể tăng do:

- Module scanning/registration.
- Reflection và annotation introspection.
- Schema loading.
- Custom serializer construction.
- Class initialization.

Đo startup riêng với request latency. Không cộng startup time vào p95 deserialize.

Nếu Avro schema hoặc Protobuf descriptor được nạp theo request, hãy xem xét cache/load một lần nếu lifecycle cho phép. Không tải schema từ network ở mỗi lần serialize.

## 68. Tách thời gian compile schema khỏi thời gian encode/decode

Một số định dạng có schema hoặc serializer được sinh:

- Avro schema parsing.
- Protobuf descriptor loading.
- SpecificRecord generated code.
- XML schema validation.

Nếu schema được parse hoặc validator được tạo mỗi request, chi phí có thể rất lớn. Tạo/cached object dùng chung theo lifecycle phù hợp, đồng thời không mutate object không thread-safe.

Benchmark encode/decode phải dùng schema đã được chuẩn bị nếu mục tiêu là đo serialization thuần. Nếu muốn đo cold start/schema load, tạo benchmark riêng.

## 69. Theo dõi file và batch processing

Với batch/file:

- Tổng file bytes.
- Số record/item.
- Thời gian parse.
- Thời gian xử lý từng batch.
- Peak heap.
- Số lỗi/record bị bỏ qua.
- Số byte đọc được trước lỗi.

Một file lớn có thể khiến heap tăng nếu đọc toàn bộ thành String/byte[] hoặc JsonNode. Với file nhiều record, cân nhắc streaming và commit theo batch.

Nếu cần retry, xác định checkpoint và semantics khi lỗi giữa file. Không chỉ tối ưu memory mà bỏ qua khả năng khôi phục.

## 70. Theo dõi queue consumer và message broker

Trong consumer:

- Message bytes.
- Deserialize duration.
- Processing duration.
- Serialize duration nếu có output event.
- Consumer lag.
- In-flight messages.
- Retry/DLQ count.

Nếu deserialize chậm, lag tăng dù business logic nhanh. Nếu payload lớn, broker fetch batch có thể làm tăng memory vì nhiều message được giữ cùng lúc.

Điều chỉnh fetch size, batch size và concurrency dựa trên memory budget, không chỉ throughput. Một batch quá lớn có thể tạo peak heap dù mỗi message riêng lẻ nằm trong giới hạn.

## 71. Theo dõi buffer và direct memory

Một số transport/client dùng direct ByteBuffer ngoài heap. Heap dashboard không hiển thị toàn bộ native/direct memory.

Nếu process RSS tăng nhưng heap used ổn định, xem:

- Direct buffer pool.
- Native memory tracking.
- Thread stack.
- Metaspace.
- Mapped file.
- TLS/compression buffers.

Jackson chủ yếu tạo object Java và buffer qua parser/generator, nhưng đường đi transport có thể giữ direct buffer. Đừng quy mọi memory growth cho Jackson chỉ vì xảy ra cùng lúc với deserialize.

## 72. Phân biệt heap leak với cache tăng có chủ đích

Nếu heap sau GC tăng:

- Xem heap histogram.
- Chụp heap dump khi an toàn.
- Dùng dominator tree tìm retained objects.
- Xem Map/cache/list nào giữ reference.
- Kiểm tra request/DTO có bị lưu vào static collection, session hoặc queue.

Jackson object graph có thể bị giữ lại bởi ứng dụng sau khi deserialize. Thường nguyên nhân nằm ở lifecycle của object, không phải parser.

Không bật heap dump tự động với mọi lỗi trong môi trường có dữ liệu nhạy cảm nếu chưa đánh giá nơi lưu, quyền truy cập và retention. Heap dump có thể chứa payload và thông tin cá nhân.

## 73. Alert và runbook khi latency tăng

Khi p95/p99 deserialize tăng:

1. Kiểm tra payload size distribution.
2. Kiểm tra message type/format bị ảnh hưởng.
3. Kiểm tra throughput và in-flight.
4. Kiểm tra CPU saturation và queue wait.
5. Kiểm tra GC pause/allocation.
6. So sánh release/configuration gần nhất.
7. Dùng trace để tìm request chậm đại diện.
8. Profile một payload synthetic tương đương.
9. Kiểm tra custom deserializer và nested collection.
10. Chọn rollback hoặc tối ưu sau khi xác định nguyên nhân.

Không tăng thread pool hoặc heap ngay lập tức nếu chưa biết bottleneck. Tăng heap có thể giảm GC tạm thời nhưng cũng che giấu object retention hoặc payload không giới hạn.

## 74. Runbook khi heap và GC tăng

Khi heap occupancy hoặc GC pause tăng:

1. Xem heap used, committed, max và sau-GC occupancy.
2. So sánh throughput và số thao tác in-flight.
3. Xem payload size p95/p99.
4. Kiểm tra allocation rate.
5. Kiểm tra batch size và queue depth.
6. Xác định có JsonNode/tree hoặc byte[] buffer lớn không.
7. Dùng JFR hoặc profiler để xem allocation hot spots.
8. Nếu cần, chụp heap dump và tìm retained object.
9. Kiểm tra release gần đây có thêm field/list/copy không.
10. Áp dụng limit/backpressure hoặc rollback khi cần.

Đừng dùng System.gc() như một cách chữa memory pressure. Nó không giải quyết nguyên nhân và có thể gây pause.

## 75. Runbook khi payload tăng bất thường

Khi p99 payload bytes tăng:

- So sánh input với output.
- So sánh compressed/decompressed bytes.
- Xem schema version và message type.
- Kiểm tra field mới hoặc nested collection.
- Kiểm tra client có gửi field lặp/metadata bất thường không.
- Kiểm tra có bật pretty printing hoặc ghi null/default không.
- Kiểm tra compression ratio.
- Kiểm tra hard body limit và parser constraints.

Nếu payload tăng từ một client hoặc message type cụ thể, phân nhóm theo metadata hữu hạn. Không log payload nguyên bản để tìm thủ phạm.

## 76. Runbook khi output size tăng sau release

So sánh:

- Golden fixture trước và sau.
- Số property được serialize.
- Null inclusion.
- Collection cardinality.
- Naming strategy/root wrapping.
- Date/number format.
- Pretty printing.
- Compression ratio.

Nếu thay đổi output là có chủ đích, đánh giá tác động tới bandwidth, broker limits và client parsing. Nếu không chủ đích, rollback hoặc sửa serializer.

## 77. Đặt ngưỡng vận hành theo message type

Không phải mọi message có cùng kích thước và latency budget. Ví dụ:

| Message type | Giới hạn đầu vào minh họa | Mục tiêu latency minh họa |
|---|---:|---:|
| UserUpdated | 64 KB | p95 dưới 10 ms |
| OrderCreated | 256 KB | p95 dưới 20 ms |
| BulkImportRowBatch | 5 MB | Đo theo batch, không dùng SLO request nhỏ |

Đây chỉ là ví dụ cách phân loại, không phải giá trị khuyến nghị chung. Ngưỡng thật phải được xác định từ schema, tải, hạ tầng, SLO và kiểm thử capacity.

Một endpoint xử lý file lớn không nên bị so với endpoint JSON nhỏ. Dùng metric và alert theo workload phù hợp.

## 78. Định nghĩa SLO cho serialization

SLO có thể mô tả:

- Tỷ lệ thao tác deserialize thành công dưới một ngưỡng latency.
- Tỷ lệ thao tác serialize thành công dưới một ngưỡng latency.
- Tỷ lệ payload hợp lệ được xử lý trong giới hạn tài nguyên.
- Tỷ lệ lỗi mapping do hệ thống, tách khỏi input invalid của client.

Phân biệt lỗi input của client với lỗi nội bộ:

- JSON malformed từ client có thể là 4xx.
- Schema mismatch do producer nội bộ có thể là lỗi contract.
- OOM hoặc timeout do service quá tải là lỗi vận hành.

Không gộp mọi exception thành một error rate nếu muốn hiểu độ tin cậy của mapper.

## 79. Không dùng percentile từ từng instance để suy ra percentile toàn cụm

Giả sử instance A xử lý 10 request và instance B xử lý 10. p99 riêng từng instance không thể cộng hoặc lấy trung bình để có p99 của cụm.

Nếu cần percentile toàn hệ thống, dùng histogram bucket có thể tổng hợp hoặc hệ thống telemetry hỗ trợ aggregation đúng. Cấu hình histogram nhất quán giữa các instance.

Percentile client-side của từng instance vẫn hữu ích để tìm node nóng, nhưng cần phân biệt với fleet-wide percentile.

## 80. Giữ overhead instrumentation thấp

Instrumentation cũng tiêu tốn CPU và memory:

- Timer lookup và tag allocation.
- DistributionSummary record.
- Trace span creation.
- Counting stream wrapper.
- Payload hash hoặc checksum.
- Logging.

Đo overhead bằng benchmark/load test. Cache meter theo tag set hữu hạn, tránh tạo object tag mới không cần thiết, không parse payload thêm một lần chỉ để đo.

Sampling có thể phù hợp với trace hoặc profiling nặng. Các counter/timer cơ bản thường nên được ghi đầy đủ nếu overhead thấp và metric cardinality được kiểm soát.

## 81. Kiểm tra metrics có thực sự được xuất

Sau khi thêm instrumentation:

- Xác nhận meter được đăng ký đúng registry.
- Xác nhận scrape endpoint có metric.
- Kiểm tra tag values.
- Kiểm tra histogram bucket/percentile.
- Kiểm tra đơn vị ms/seconds/bytes.
- Kiểm tra dashboard không nhân đôi series.
- Kiểm tra metric khi lỗi và khi success.

Một timer chỉ xuất count mà không có histogram có thể không đáp ứng nhu cầu p95/p99. Một DistributionSummary ghi byte nhưng dashboard hiển thị như kilobyte có thể gây hiểu nhầm nếu unit conversion không rõ.

## 82. Tài liệu hóa metric contract

Mỗi metric nên có:

- Tên.
- Unit.
- Loại meter (counter/timer/summary/gauge).
- Ý nghĩa chính xác.
- Vị trí bắt đầu/kết thúc đo.
- Tags và miền giá trị hợp lệ.
- Có đo compressed hay decompressed bytes không.
- Có bao gồm I/O không.
- Owner hoặc dashboard liên quan.

Ví dụ:

~~~text
Name: serialization.payload.bytes
Type: DistributionSummary
Unit: bytes
Meaning: bytes consumed by Jackson parser
Tags: format, operation, message_type
Excludes: compressed network bytes, unless parser reads compressed stream
~~~

Tài liệu này ngăn các service dùng cùng metric name nhưng đo những đại lượng khác nhau.

## 83. Kết hợp metrics với version và deployment metadata

Khi hiệu năng thay đổi, cần biết bản nào đang chạy:

- application version.
- Jackson Core/Databind version.
- dataformat module version.
- JDK version.
- container/resource limit.
- mapper profile/config revision.

Thông tin version thường nên được gắn vào deployment metadata hoặc dashboard variable, không nhất thiết trở thành tag trên mọi metric nếu làm tăng cardinality.

Sau upgrade, so sánh canary với stable ở cùng payload distribution và traffic profile.

## 84. Checklist vận hành

Khi đưa một luồng Jackson vào production:

- Đo riêng deserialize và serialize.
- Đo input/output bytes tại ranh giới rõ ràng.
- Phân biệt compressed và decompressed bytes.
- Theo dõi p50/p95/p99 latency.
- Theo dõi success/error count.
- Theo dõi in-flight, queue wait và throughput.
- Theo dõi heap, allocation và GC pause ở cấp JVM.
- Đặt body size limit ở tầng transport.
- Đặt parser constraints phù hợp version.
- Dùng streaming cho collection/file lớn khi nghiệp vụ cho phép.
- Tránh buffering/copy toàn payload không cần thiết.
- Không đo heap delta từng request như allocation chính xác.
- Không ghi payload nhạy cảm vào log/metric/trace.
- Tránh high-cardinality tags.
- Benchmark bằng JMH và load test theo payload thật.
- Đo lại sau mỗi lần nâng cấp Jackson/JDK.
- Có runbook cho latency, memory và payload growth.

## 85. Quy trình điều tra một lần tăng latency

Một quy trình ngắn gọn nhưng có thể lặp lại:

1. Xác định metric nào tăng: deserialize, serialize hay end-to-end.
2. Xem payload size p50/p95/p99 có đổi không.
3. Phân nhóm theo format và message type.
4. Kiểm tra concurrency, queue wait và CPU.
5. Kiểm tra GC pause, heap sau GC và allocation rate.
6. Dùng trace tìm một số request chậm đại diện.
7. Profile payload synthetic tương đương bằng JFR/JMH.
8. Xác định nguyên nhân thuộc I/O, parser, databind, custom handler hay object retention.
9. Thử thay đổi trên benchmark/load test.
10. Rollout canary và so sánh metrics trước/sau.

~~~text
Latency tăng
    |
    v
Payload size có tăng?
    | yes                    | no
    v                        v
Kiểm tra schema,        Kiểm tra CPU, GC,
collection, limit       queue và mapper config
    |                        |
    +-----------+------------+
                |
                v
          Profile/JFR
                |
                v
       Xác nhận nguyên nhân
                |
                v
       Benchmark và canary
~~~

## 86. Nguyên tắc thực hành

- Đo đúng ranh giới Jackson thay vì gắn nhãn toàn request là serialization latency.
- Tách deserialize và serialize.
- Ghi rõ kích thước là compressed bytes, decompressed bytes hay UTF-8 bytes.
- Không dùng String.length() thay cho byte count.
- Không dùng InputStream.available() để đo tổng kích thước.
- Dùng counting stream hoặc byte count từ transport khi phù hợp.
- Tránh buffer toàn output chỉ để lấy length.
- Nhớ payload bytes không bằng object graph size.
- Theo dõi p50/p95/p99 thay vì chỉ average.
- Dùng histogram có bucket theo SLO.
- Theo dõi heap, allocation rate, GC và concurrency cùng nhau.
- Không đo heap delta trước/sau request như memory allocation chính xác.
- Dùng JFR/profiler để tìm allocation và retained objects.
- Phân biệt readValue(InputStream) với streaming từng object.
- Giới hạn request size, decompressed size và parser constraints.
- Áp dụng backpressure cho workload nặng.
- Không ghi payload nhạy cảm hoặc tag có cardinality cao.
- Dùng JMH cho microbenchmark và load test cho concurrency.
- Theo dõi thay đổi sau upgrade bằng fixture, benchmark và canary.
- Tài liệu hóa metric unit, semantics và vị trí đo.

Theo dõi kích thước đầu vào, độ trễ và mức sử dụng bộ nhớ giúp nhìn thấy cả chi phí của từng thao tác Jackson lẫn áp lực tổng thể lên JVM. Kích thước cho biết lượng dữ liệu đi qua, timer cho biết thời gian xử lý, còn heap/allocation/GC cho biết tác động lên runtime. Khi đo đúng ranh giới, dùng percentile và histogram, giới hạn payload, phân biệt buffering với streaming và kết hợp profiling khi cần, nhóm vận hành có thể xác định nguyên nhân thay vì chỉ phản ứng với một con số latency hoặc heap đơn lẻ.
