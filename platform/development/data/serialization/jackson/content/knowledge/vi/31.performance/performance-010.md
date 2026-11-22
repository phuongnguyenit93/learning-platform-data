# Phân biệt tối ưu định dạng và tối ưu quá trình truyền dữ liệu

Khi một ứng dụng dùng Jackson để gửi dữ liệu qua HTTP, message broker hoặc file stream, hiệu năng phụ thuộc vào nhiều bước nối tiếp nhau: tạo object, serialize, đóng gói message, nén, truyền qua mạng, giải nén và deserialize. Hai hướng tối ưu thường bị gộp làm một là **tối ưu định dạng dữ liệu** và **tối ưu quá trình truyền dữ liệu**.

Tối ưu định dạng tập trung vào representation và codec: JSON, CBOR, Smile hoặc một định dạng schema-based có thể tạo ra payload lớn nhỏ khác nhau và có chi phí encode/decode khác nhau. Tối ưu truyền dữ liệu tập trung vào cách payload đi qua hệ thống: compression, connection reuse, protocol, batching, streaming, buffering, backpressure và framing.

Hai hướng này có thể bổ trợ nhau nhưng không thay thế nhau. Đổi JSON sang CBOR có thể giảm số byte nhưng không tự tạo connection pooling hoặc giảm số round trip. Bật gzip có thể giảm byte truyền nhưng không làm object model nhỏ hơn hoặc loại bỏ chi phí serialize. Muốn chọn đúng giải pháp, cần đo riêng chi phí codec, kích thước payload, thời gian mạng và tổng latency end-to-end.

## 1. Nhìn toàn bộ đường đi của dữ liệu

Một request/response thường đi qua các bước sau:

```text
Java object
    |
    v
Jackson serializer
    |
    v
JSON / CBOR / Smile bytes
    |
    v
Compression (optional)
    |
    v
HTTP / broker framing and headers
    |
    v
Connection, TLS, network and queues
    |
    v
Receiver reads and decompresses
    |
    v
Jackson parser/deserializer
    |
    v
Java object at consumer
```

Mỗi bước có thể trở thành nút thắt khác nhau:

- Serializer tốn CPU hoặc tạo nhiều object tạm.
- Payload lớn khiến network transfer chậm.
- Compression giảm byte nhưng tiêu tốn CPU.
- Kết nối mới cho từng request làm tăng handshake và latency.
- Quá nhiều request nhỏ tạo nhiều round trip và header overhead.
- Receiver đọc toàn bộ body vào một byte array lớn, gây áp lực bộ nhớ.
- Consumer xử lý chậm nhưng producer không có backpressure, làm queue phình ra.

Nếu chỉ đo tổng thời gian request, rất khó biết bước nào cần tối ưu. Trước tiên hãy tách các thành phần và đo chúng bằng cùng một bộ dữ liệu đại diện.

## 2. Tối ưu định dạng dữ liệu là gì?

Tối ưu định dạng là chọn cách biểu diễn dữ liệu và cách codec chuyển đổi giữa object với byte stream. Với Jackson, những lựa chọn phổ biến gồm:

| Format | Đặc điểm | Tác động thường cần đo |
|---|---|---|
| JSON text | Dễ đọc, công cụ hỗ trợ rộng, thuận tiện debug | Kích thước text, parse/serialize CPU, chi phí số và string |
| CBOR | Binary representation theo data model CBOR, hỗ trợ nhiều kiểu dữ liệu | Kích thước binary, encode/decode CPU, interoperability |
| Smile | Binary JSON format trong hệ sinh thái Jackson | Kích thước, tốc độ codec, khả năng hỗ trợ của consumer/tool |
| Avro/Protobuf | Schema/IDL và runtime riêng, thường có generated type hoặc schema resolution | Schema management, encoding cost, compatibility và tooling |

Đổi format có thể làm thay đổi:

- Số byte của payload trước compression.
- CPU dùng để encode và decode.
- Allocation và garbage collection.
- Khả năng biểu diễn byte string, decimal, timestamp, enum và map key.
- Khả năng debug và hỗ trợ của client/tool bên ngoài.
- Cách schema được version hóa và tương thích giữa producer/consumer.

Không có format nhanh nhất trong mọi trường hợp. Kết quả phụ thuộc shape của dữ liệu, độ dài field name, tỷ lệ string/số/binary, mức lặp lại của key, cấu hình mapper, thư viện consumer và phần cứng.

### 2.1. JSON không nhất thiết chậm hơn binary trong mọi workload

JSON có thể tạo payload lớn hơn CBOR/Smile khi dữ liệu có nhiều tên field lặp lại hoặc số biểu diễn bằng text. Nhưng JSON parser được tối ưu tốt, các proxy và tool đều hiểu JSON, và compression có thể loại bỏ nhiều redundancy trong payload.

Một JSON body gzip có thể nhỏ hơn CBOR không nén. Trong trường hợp đó, so sánh “JSON với CBOR” mà bỏ qua compression là không phản ánh đường truyền production.

### 2.2. Binary không tự động nhanh hơn

Binary format có thể giảm số byte nhưng tốn CPU hơn khi encode/decode, hoặc yêu cầu consumer chuyển đổi kiểu phức tạp. Nếu hệ thống bị giới hạn CPU và mạng đang rất nhanh, giảm payload có thể không cải thiện latency.

Ngược lại, nếu ứng dụng gửi lượng lớn dữ liệu qua mạng chậm hoặc trả phí theo byte, giảm payload có thể đáng giá dù codec tốn thêm một ít CPU.

### 2.3. Format là contract, không chỉ là một flag hiệu năng

Thay đổi JSON thành CBOR/Smile ảnh hưởng cả producer và consumer. Cần thống nhất content type/format identifier, schema, version, null, enum, timestamp, decimal và framing. Không thể chỉ đổi `ObjectMapper` ở một phía rồi kỳ vọng mọi client tiếp tục đọc được payload.

## 3. Tạo mapper cho các format Jackson

JSON:

```java
ObjectMapper jsonMapper = new ObjectMapper();
```

CBOR:

```java
CBORFactory cborFactory = new CBORFactory();
ObjectMapper cborMapper = new ObjectMapper(cborFactory);
```

Smile:

```java
SmileFactory smileFactory = new SmileFactory();
ObjectMapper smileMapper = new ObjectMapper(smileFactory);
```

Các module `jackson-dataformat-cbor` và `jackson-dataformat-smile` cần cùng dòng version tương thích với `jackson-core` và `jackson-databind`. Nếu dự án dùng Jackson BOM, để BOM quản lý version.

Serialize thành byte array:

```java
byte[] jsonBytes = jsonMapper.writeValueAsBytes(event);
byte[] cborBytes = cborMapper.writeValueAsBytes(event);
byte[] smileBytes = smileMapper.writeValueAsBytes(event);
```

Các byte array này có thể được dùng để so sánh payload trước compression. Khi đo, hãy dùng cùng object, cùng semantics và cùng phiên bản thư viện tương thích.

### 3.1. Không so sánh các mapper với cấu hình khác nhau

Nếu JSON mapper có Java Time module, custom serializer và naming strategy nhưng CBOR mapper không có, kết quả có thể khác cả về semantics lẫn chi phí. Trước khi benchmark, hãy bảo đảm các mapper biểu diễn cùng dữ liệu theo cùng contract.

Các yếu tố cần cố định:

- Module và custom serializer/deserializer.
- Property naming strategy và annotation.
- Null/inclusion policy.
- Enum representation.
- Timestamp format và timezone.
- Polymorphic type configuration.
- Parser constraints và các feature liên quan.

Nếu một format không hỗ trợ một kiểu theo cùng cách, hãy định nghĩa conversion rõ ràng trước khi so sánh.

## 4. Đo kích thước payload trước khi tối ưu

Kích thước payload là một phép đo đơn giản nhưng cần phân biệt các lớp:

- **Serialized size:** số byte sau khi Jackson encode, trước compression.
- **Compressed size:** số byte sau gzip/zstd hoặc thuật toán compression khác.
- **Application body size:** số byte body mà HTTP/broker gửi.
- **Wire bytes:** byte thực tế đi qua network, có thể gồm protocol headers, TLS records, framing và retransmission.

Ví dụ:

```java
byte[] json = jsonMapper.writeValueAsBytes(event);
byte[] cbor = cborMapper.writeValueAsBytes(event);
byte[] smile = smileMapper.writeValueAsBytes(event);

System.out.printf("JSON:  %d bytes%n", json.length);
System.out.printf("CBOR:  %d bytes%n", cbor.length);
System.out.printf("Smile: %d bytes%n", smile.length);
```

Đoạn code trên chỉ so sánh kích thước serialization. Nó không đo compression, HTTP headers, TLS hoặc thời gian truyền.

### 4.1. Tính tỷ lệ giảm kích thước

Nếu payload ban đầu có kích thước (S_0), payload mới có kích thước (S_1), phần trăm giảm là:

\[
\text{Reduction}(\%) = \frac{S_0-S_1}{S_0}\times 100
\]

Ví dụ JSON 100 KB và CBOR 72 KB:

\[
\frac{100-72}{100}\times100=28\%
\]

CBOR nhỏ hơn 28% trong mẫu đó. Kết quả không có nghĩa latency giảm 28%, vì thời gian còn phụ thuộc compression, network, queue, CPU và cách client đọc dữ liệu.

### 4.2. Dùng payload đại diện

Một benchmark chỉ dùng một object nhỏ có thể dẫn đến quyết định sai. Hãy chọn corpus gần production:

- Object nhỏ gửi thường xuyên.
- Response lớn có nhiều field lặp lại.
- Danh sách nhiều record.
- Payload có nhiều string/Unicode.
- Payload nhiều số và decimal.
- Payload có byte array hoặc nội dung ít nén được.
- Payload sparse với nhiều field null/absent.

Ghi lại phân bố kích thước thực tế, không chỉ một payload trung bình. P95/P99 có thể quan trọng hơn average khi hệ thống có response lớn.

## 5. Compression là tối ưu representation hay truyền tải?

Compression nằm giữa codec và transport. Nó nhận byte stream đã serialize và tạo byte stream nhỏ hơn để truyền. Vì vậy, compression có thể được xem là tối ưu payload trên đường truyền, nhưng không thay thế lựa chọn data format.

Ví dụ gzip JSON:

```java
byte[] jsonBytes = jsonMapper.writeValueAsBytes(event);

ByteArrayOutputStream compressed = new ByteArrayOutputStream();
try (GZIPOutputStream gzip = new GZIPOutputStream(compressed)) {
    gzip.write(jsonBytes);
}

byte[] gzipBytes = compressed.toByteArray();
```

Giải nén:

```java
byte[] restoredJson;
try (GZIPInputStream gzip = new GZIPInputStream(
        new ByteArrayInputStream(gzipBytes))) {
    restoredJson = gzip.readAllBytes();
}

Event event = jsonMapper.readValue(restoredJson, Event.class);
```

Trong HTTP production, framework/client/server thường hỗ trợ `Content-Encoding: gzip` tự động. Khi dùng compression ở tầng HTTP, để HTTP stack quản lý header và body; không tự gzip body rồi lại bật auto-compression lần nữa.

### 5.1. So sánh format có và không compression

Nên đo tối thiểu:

| Biến thể | Payload trước nén | Payload sau nén | Encode/decode + compression CPU |
|---|---:|---:|---:|
| JSON | Có | Có | Có |
| JSON + gzip | Có | Có | Có |
| CBOR | Có | Có | Có |
| CBOR + gzip | Có | Có | Có |
| Smile | Có | Có | Có |
| Smile + gzip | Có | Có | Có |

Một binary format có thể nhỏ hơn JSON trước nén nhưng giảm lợi thế sau gzip vì JSON vốn có nhiều redundancy dễ nén. Ngược lại, với payload chứa binary data đã nén, compression thêm có thể gần như không giảm được kích thước.

### 5.2. Compression có chi phí CPU và latency

Compression thường tạo trade-off:

- Ít byte hơn, giảm thời gian network và chi phí băng thông.
- Thêm CPU ở producer để nén.
- Thêm CPU ở consumer để giải nén.
- Có thể thêm buffering và latency trước khi byte đầu tiên được gửi.
- Có thể làm tăng memory nếu tạo thêm byte array trung gian.

Compression có lợi khi thời gian tiết kiệm do truyền ít byte lớn hơn chi phí nén/giải nén. Với payload nhỏ, compression có thể tốn nhiều hơn phần tiết kiệm. Có thể đặt ngưỡng kích thước hoặc dùng compression policy theo endpoint/message type.

### 5.3. Không nén dữ liệu đã nén nếu không cần

JPEG, PNG, ZIP, gzip, zstd và nhiều định dạng media đã có compression. Nén thêm có thể gần như không giảm dung lượng nhưng vẫn tốn CPU và thêm framing. Đo trên dữ liệu thật trước khi bật compression toàn cục.

### 5.4. Chọn compression algorithm theo workload

Gzip phổ biến và được hỗ trợ rộng. Zstandard (zstd) có thể cung cấp trade-off tốc độ/tỷ lệ nén tốt trong một số workload nhưng cần xác nhận support ở mọi consumer và proxy. Không chọn chỉ dựa trên benchmark tổng quát; hãy đo với corpus thực tế, mức compression, CPU và network của hệ thống.

## 6. Tối ưu quá trình truyền dữ liệu là gì?

Transport optimization thay đổi cách dữ liệu được đưa từ producer đến consumer, không nhất thiết thay đổi representation bên trong payload.

Các hướng thường gặp:

- Tái sử dụng connection và connection pool.
- HTTP/2 hoặc giao thức multiplexing phù hợp.
- Giảm số round trip bằng batching hoặc API bulk.
- Streaming thay vì buffer toàn bộ body.
- Buffering có giới hạn để gom các lần ghi nhỏ.
- Async I/O và backpressure để producer không vượt consumer.
- Framing và message boundary rõ ràng.
- Compression ở tầng transport.
- Điều chỉnh timeout, retry và concurrency.

Ví dụ, một service gửi 1.000 request nhỏ tuần tự có thể tốn thời gian do round trip. Gộp chúng thành một batch request có thể cải thiện throughput đáng kể mà không cần đổi JSON sang CBOR.

Ngược lại, nếu một response đơn lẻ nặng 20 MB và chỉ cần truyền 5 MB sau khi đổi representation/compression, batching không giải quyết vấn đề chính.

## 7. Tái sử dụng kết nối và giảm handshake

Mở kết nối mới cho mỗi request có thể tạo thêm chi phí:

- TCP connection establishment.
- TLS handshake và certificate processing.
- DNS lookup nếu cache không hiệu quả.
- Authentication/session negotiation tùy giao thức.
- Tài nguyên socket và ephemeral port.

HTTP client có connection pool và keep-alive có thể tái sử dụng kết nối. Điều này là transport optimization; nó không phụ thuộc JSON hay CBOR.

Nguyên tắc:

- Dùng HTTP client được thiết kế để tái sử dụng connection.
- Cấu hình pool size theo concurrency và năng lực server.
- Đặt connect/read/request timeout rõ ràng.
- Tránh tạo HTTP client mới trong mỗi method call.
- Theo dõi connection reuse, pending acquisition và connection churn.

Không tăng pool size một cách mù quáng. Quá nhiều connection đồng thời có thể làm server, database hoặc proxy quá tải và tăng tail latency.

## 8. HTTP/2, multiplexing và số round trip

HTTP/2 cho phép nhiều stream dùng chung một connection, giúp giảm chi phí mở nhiều connection và hỗ trợ multiplexing. Nó có thể cải thiện workload có nhiều request đồng thời, nhưng không tự làm payload JSON nhỏ hơn.

Khi cân nhắc HTTP/2:

- Xác nhận client, server, load balancer và proxy đều hỗ trợ.
- Đo concurrency thực tế và số request trên mỗi connection.
- Kiểm tra flow control và stream-level behavior.
- Theo dõi tail latency khi một stream truyền response lớn.
- Đảm bảo không nhầm multiplexing với batching: chúng giải quyết các chi phí khác nhau.

HTTP/2 có thể giảm connection overhead nhưng không bảo đảm mọi workload nhanh hơn HTTP/1.1. Một request đơn lẻ nhỏ trên kết nối đã ấm có thể không thấy khác biệt đáng kể.

## 9. Batching để giảm overhead cho nhiều message nhỏ

Nếu producer gửi nhiều record nhỏ, batching có thể giảm số lần gọi API, header và round trip.

Ví dụ thay vì gửi từng event:

```java
for (Event event : events) {
    httpClient.send(buildRequest(event));
}
```

có thể gửi một batch:

```java
byte[] payload = jsonMapper.writeValueAsBytes(events);
sendBatch(payload);
```

Batching có trade-off:

- Ít request hơn và amortize header/connection overhead.
- Throughput có thể tăng.
- Một batch lớn có thể tăng latency cho record đầu tiên phải chờ gom batch.
- Lỗi một phần tử có thể làm phức tạp retry và idempotency.
- Batch lớn làm tăng memory và thời gian parse/validate.

Nên giới hạn batch theo cả số record và tổng byte. Có thể flush khi đạt ngưỡng record, byte hoặc thời gian chờ tối đa.

### 9.1. Batch không đồng nghĩa với một mảng JSON bắt buộc

Batch có thể là JSON array, CBOR array, Smile sequence hoặc envelope riêng. Chọn representation phù hợp với contract và khả năng xử lý từng record. Nếu consumer cần xử lý độc lập, envelope có record IDs và error results có thể phù hợp hơn một mảng không có metadata.

### 9.2. Thiết kế retry cho batch

Nếu batch có 100 event và 3 event lỗi, retry cả batch có thể xử lý lặp 97 event đã thành công. Cần idempotency key, per-record result hoặc cơ chế retry subset. Transport optimization không được làm mất semantics delivery.

## 10. Streaming thay vì buffer toàn bộ payload

`writeValueAsBytes()` tạo toàn bộ output thành một byte array trong bộ nhớ. Cách này tiện với payload nhỏ và cần biết body trước khi gửi, nhưng với payload lớn có thể tạo allocation đáng kể.

Jackson có thể ghi trực tiếp ra `OutputStream`:

```java
try (OutputStream output = connection.getOutputStream()) {
    jsonMapper.writeValue(output, largeReport);
}
```

Đối với HTTP client hiện đại, có thể dùng body publisher/streaming API của client để cung cấp `InputStream` hoặc `OutputStream` tùy framework. Điểm cần đạt là serializer ghi dữ liệu theo luồng đến transport mà không phải giữ toàn bộ serialized body trong một `byte[]` lớn.

### 10.1. Streaming giảm memory nhưng không tự giảm byte

Streaming thay đổi cách dữ liệu được tạo và tiêu thụ. Nếu payload và format giữ nguyên, tổng số byte có thể không đổi. Lợi ích chính là:

- Giảm peak memory.
- Có thể bắt đầu truyền trước khi toàn bộ object được serialize xong, tùy transport.
- Tránh copy nhiều lần giữa String, byte array và buffer.
- Hỗ trợ xử lý dữ liệu lớn theo từng phần.

Streaming không nhất thiết giảm CPU encode/decode; nó tối ưu memory và pipeline behavior.

### 10.2. Đọc streaming với Jackson

Với JSON array lớn, có thể dùng `MappingIterator`:

```java
try (MappingIterator<Event> iterator = jsonMapper
        .readerFor(Event.class)
        .readValues(inputStream)) {

    while (iterator.hasNextValue()) {
        Event event = iterator.nextValue();
        process(event);
    }
}
```

Với sequence output, có thể dùng `SequenceWriter`:

```java
ObjectWriter writer = jsonMapper.writerFor(Event.class);
try (SequenceWriter sequence = writer.writeValues(outputStream)) {
    for (Event event : events) {
        sequence.write(event);
    }
}
```

`SequenceWriter` ghi chuỗi root values theo quy tắc của generator/format. Hãy xác nhận framing mà consumer mong đợi; nhiều JSON root values nối tiếp không tự động trở thành một JSON array duy nhất. Nếu consumer yêu cầu một JSON array, dùng writer cho collection hoặc một generator ghi array start/end.

### 10.3. Streaming và backpressure

Streaming chỉ có hiệu quả khi producer tôn trọng tốc độ tiêu thụ. Nếu producer tạo dữ liệu nhanh hơn consumer, buffer/queue vẫn có thể tăng vô hạn.

Backpressure giới hạn tốc độ upstream dựa trên năng lực downstream. Tùy stack, có thể dùng reactive streams, bounded queue, demand signaling hoặc flow control của transport. Không nên đổi sang reactive API chỉ vì nó có vẻ nhanh; hãy xác định vấn đề là memory, concurrency hay throughput.

## 11. Buffering và flush policy

Ghi từng byte nhỏ có thể tạo nhiều system call hoặc nhiều frame nhỏ. Buffering gom các lần ghi lại:

```java
try (OutputStream buffered = new BufferedOutputStream(outputStream, 32 * 1024)) {
    jsonMapper.writeValue(buffered, event);
}
```

Buffer có thể giảm số lần ghi nhỏ, nhưng kích thước buffer lớn làm tăng memory theo số connection/request đồng thời. Ngoài ra, flush quá thường xuyên có thể làm mất lợi ích batching; flush quá muộn có thể tăng latency.

Chọn buffer size bằng benchmark và theo dõi:

- Throughput.
- Số lần write/flush.
- Peak memory theo concurrency.
- Time-to-first-byte.
- End-to-end latency.

Nếu HTTP framework đã quản lý buffering, không thêm một tầng buffer lớn mà không đo tác dụng.

## 12. Compression, streaming và Jackson generator

Có thể kết hợp streaming và compression để tránh tạo byte array trung gian:

```java
try (GZIPOutputStream gzip = new GZIPOutputStream(outputStream)) {
    jsonMapper.writeValue(gzip, largeReport);
}
```

Luồng dữ liệu:

```text
Java object
   |
   v
Jackson JsonGenerator
   |
   v
GZIPOutputStream
   |
   v
Network OutputStream
```

Đối với HTTP, nếu tự nén body, phải đặt `Content-Encoding: gzip` và bảo đảm server/client không tự nén hoặc giải nén lần nữa. Nếu HTTP framework có hỗ trợ compression, ưu tiên dùng một cơ chế thống nhất ở tầng đó.

### 12.1. Streaming compression có thể trì hoãn byte đầu tiên

Compression stream có buffer và cần ghi header/trailer. Một số compressor giữ dữ liệu để tìm block phù hợp. Vì vậy, dù streaming, time-to-first-byte có thể tăng. Đo cả TTFB và tổng thời gian hoàn tất.

### 12.2. Flush trong compression stream

Gọi `flush()` quá thường xuyên có thể làm compressor kết thúc block hoặc giảm hiệu quả nén tùy implementation. Không flush sau từng field hoặc từng byte. Flush theo batch/chunk có ý nghĩa hoặc để framework quản lý.

## 13. Tránh chuyển đổi không cần thiết giữa String và byte[]

Một pipeline kém hiệu quả có thể làm:

```java
String json = mapper.writeValueAsString(event);
byte[] bytes = json.getBytes(StandardCharsets.UTF_8);
```

Nếu transport cần bytes UTF-8, có thể dùng:

```java
byte[] bytes = mapper.writeValueAsBytes(event);
```

Hoặc ghi trực tiếp vào output stream:

```java
mapper.writeValue(outputStream, event);
```

Tương tự ở chiều đọc, nếu đã có `InputStream`, tránh đọc hết thành `String` rồi gọi `readValue(String, ...)` khi không cần inspect text. Dùng `readValue(InputStream, Type.class)` để parser đọc trực tiếp từ stream.

Các lần chuyển đổi String/byte[] có thể tạo bản sao lớn, tăng allocation và GC. Tuy nhiên, đừng thay đổi API chỉ để tránh một allocation nhỏ mà không đo được tác động.

## 14. HTTP compression và content negotiation

HTTP có cơ chế thương lượng compression qua header:

```http
Accept-Encoding: gzip
```

Server có thể trả:

```http
Content-Encoding: gzip
Content-Type: application/json
```

`Content-Type` mô tả format của representation sau khi giải nén; `Content-Encoding` mô tả encoding bổ sung trên body truyền đi. Ví dụ body JSON gzip vẫn là JSON được gzip, không phải một JSON format mới.

Nếu dùng CBOR:

```http
Content-Type: application/cbor
Content-Encoding: gzip
```

Consumer cần giải nén rồi decode CBOR. Tên media type cụ thể cần tuân theo contract và hạ tầng đang dùng.

### 14.1. Không nhầm Content-Type với Content-Encoding

- `Content-Type`: payload là JSON, CBOR, XML hay format khác.
- `Content-Encoding`: payload được nén hoặc biến đổi thế nào trên đường truyền, ví dụ gzip.

Nếu server gửi CBOR nhưng header lại báo `application/json`, client có thể gọi sai parser. Nếu body đã gzip nhưng thiếu `Content-Encoding`, client không biết phải giải nén.

### 14.2. Compression threshold

Compression cho body rất nhỏ có thể tăng overhead. Nhiều server cho phép đặt threshold để chỉ nén body lớn hơn một ngưỡng. Hãy chọn ngưỡng dựa trên kích thước payload, CPU và network thực tế.

### 14.3. Cẩn thận với dữ liệu bí mật và compression side-channel

Trong một số giao thức, nén dữ liệu bí mật cùng dữ liệu do attacker kiểm soát rồi quan sát kích thước ciphertext có thể tạo side-channel. Với response có secret và input không tin cậy cùng xuất hiện, cần đánh giá rủi ro compression side-channel và áp dụng chính sách phù hợp. Không bật compression cho mọi response một cách máy móc nếu threat model có rủi ro này.

## 15. Message broker và transport batching

Với message broker, format serialization là một lớp trong message body; broker transport có các chi phí riêng:

- Batch publish và batch fetch.
- Compression ở batch/message level.
- Message size limit.
- Acknowledgement mode.
- Prefetch/consumer concurrency.
- Retry và dead-letter routing.
- Partition/key distribution.

Nếu producer gửi nhiều message nhỏ, batch publish có thể tăng throughput. Nhưng batch lớn làm tăng memory và có thể kéo dài thời gian chờ trước khi gửi.

Nếu consumer xử lý chậm, tăng prefetch có thể làm queue nội bộ phình ra và tăng thời gian chờ. Cần đo consumer lag, unacked message count và xử lý per-message.

Không gộp tất cả event thành một binary blob lớn nếu broker cần định tuyến, retry, audit hoặc xử lý độc lập từng message. Transport optimization phải giữ semantics delivery và observability.

## 16. Framing: ranh giới message phải rõ ràng

Một `byte[]` từ `writeValueAsBytes()` thường đại diện một payload. Nhưng nếu nhiều payload được ghi nối tiếp vào cùng stream, consumer phải biết mỗi payload kết thúc ở đâu.

Các lựa chọn framing:

- Một HTTP body hoặc broker message chứa đúng một document.
- Length prefix trước mỗi payload.
- Container/sequence format được contract quy định.
- Record boundary do transport cung cấp.

Không giả định mọi binary format tự tìm được boundary trong một TCP byte stream. TCP là byte stream, không phải message protocol. Nếu gửi nhiều message qua TCP, ứng dụng phải định nghĩa framing.

Framing cũng là một phần của performance: length prefix có thể giúp allocate/read chính xác, nhưng cần kiểm tra giới hạn length trước khi cấp phát. Nếu length prefix không tin cậy, attacker có thể khai báo kích thước cực lớn và gây áp lực bộ nhớ.

## 17. Đo CPU, network và latency riêng biệt

Một benchmark hữu ích cần đo ít nhất:

| Metric | Điều nó cho biết |
|---|---|
| Serialize time | CPU/latency để tạo payload |
| Deserialize time | CPU/latency để parse và tạo object |
| Uncompressed bytes | Kích thước do format tạo ra |
| Compressed bytes | Kích thước thực sau compression |
| Compression/decompression time | Chi phí CPU của compression |
| Time-to-first-byte | Thời điểm byte đầu tiên được gửi/nhận |
| Network transfer time | Thời gian chuyển body qua transport |
| End-to-end latency | Tổng thời gian từ producer đến consumer |
| Throughput | Message/record/byte mỗi giây |
| Allocation/GC | Áp lực bộ nhớ do encode, buffer và decode |
| p50/p95/p99 | Phân bố latency, đặc biệt tail latency |

Không chỉ nhìn average. Một thay đổi có thể cải thiện p50 nhưng làm p99 xấu đi do batch lớn, GC hoặc queueing.

### 17.1. Dùng cùng payload và cùng semantics

So sánh format cần dùng cùng dataset, cùng object semantics và cùng điều kiện runtime. Nếu JSON output chứa field mà CBOR output bỏ qua, kích thước nhỏ hơn không phải tối ưu hợp lệ.

### 17.2. Tách benchmark codec khỏi benchmark transport

Benchmark codec trong process giúp đo serialize/deserialize và allocation mà không bị network làm nhiễu.

Integration/load test đo transport cần chạy qua connection, compression, proxy, broker và consumer gần production. Không dùng kết quả microbenchmark để dự đoán trực tiếp network latency.

## 18. Benchmark Jackson với JMH

JMH phù hợp để benchmark các thao tác codec trong JVM. Ví dụ khung benchmark:

```java
@State(Scope.Thread)
@BenchmarkMode(Mode.AverageTime)
@OutputTimeUnit(TimeUnit.MICROSECONDS)
public class SerializationBenchmark {
    private final ObjectMapper jsonMapper = new ObjectMapper();
    private final ObjectMapper cborMapper = new ObjectMapper(new CBORFactory());
    private final ObjectMapper smileMapper = new ObjectMapper(new SmileFactory());

    private Event event;
    private byte[] jsonBytes;
    private byte[] cborBytes;
    private byte[] smileBytes;

    @Setup(Level.Trial)
    public void setup() throws Exception {
        event = TestData.largeRepresentativeEvent();
        jsonBytes = jsonMapper.writeValueAsBytes(event);
        cborBytes = cborMapper.writeValueAsBytes(event);
        smileBytes = smileMapper.writeValueAsBytes(event);
    }

    @Benchmark
    public byte[] serializeJson() throws Exception {
        return jsonMapper.writeValueAsBytes(event);
    }

    @Benchmark
    public Event deserializeJson() throws Exception {
        return jsonMapper.readValue(jsonBytes, Event.class);
    }

    @Benchmark
    public byte[] serializeCbor() throws Exception {
        return cborMapper.writeValueAsBytes(event);
    }

    @Benchmark
    public Event deserializeCbor() throws Exception {
        return cborMapper.readValue(cborBytes, Event.class);
    }

    @Benchmark
    public byte[] serializeSmile() throws Exception {
        return smileMapper.writeValueAsBytes(event);
    }

    @Benchmark
    public Event deserializeSmile() throws Exception {
        return smileMapper.readValue(smileBytes, Event.class);
    }
}
```

Đây là skeleton cần được bổ sung dependency JMH, benchmark runner và test data thực tế. JMH cần warmup, measurement iterations, forks và JVM settings phù hợp. Tránh tự viết vòng lặp `System.nanoTime()` đơn giản rồi xem kết quả là benchmark đáng tin cậy.

### 18.1. Tránh benchmark sai

- Không tạo `ObjectMapper` mới trong mỗi invocation nếu production tái sử dụng mapper.
- Không benchmark một payload duy nhất nếu production có nhiều loại message.
- Không bỏ kết quả trả về; JMH cần tiêu thụ kết quả để tránh dead-code elimination.
- Không benchmark khi máy đang bị tải không kiểm soát.
- Không so sánh một format đã warm với format chưa warm.
- Không dùng cùng một byte array đã cache để đo serialize.
- Không bỏ qua allocation/GC và chỉ nhìn average time.

### 18.2. Đo compression trong benchmark riêng

Compression benchmark nên đo cả output size và thời gian nén/giải nén. Có thể dùng JMH method riêng cho gzip, zstd hoặc algorithm đã chọn. Giữ nguyên input bytes để tách chi phí compression khỏi chi phí Jackson codec.

## 19. Load test end-to-end

Sau microbenchmark, chạy load test qua đường đi thực tế:

1. Producer dùng cùng client/connection pool như production.
2. Gửi payload qua gateway/server hoặc broker thật trong môi trường test.
3. Bật compression/protocol tương ứng.
4. Consumer dùng decoder thực tế và xử lý payload.
5. Thu thập latency, throughput, error rate, CPU, memory, network bytes và queue lag.

Kịch bản cần có:

- Warm connection và cold connection.
- Một request đơn lẻ và concurrency cao.
- Payload nhỏ, trung bình, lớn.
- Compression bật/tắt.
- Batch size nhỏ/lớn.
- Consumer chậm để quan sát backpressure.
- Network latency/bandwidth bị giới hạn gần môi trường production.

Đo ít nhất p50, p95, p99 và throughput ổn định. Một thử nghiệm ngắn có thể chưa bộc lộ GC pressure hoặc queue growth khi chạy lâu.

## 20. Chọn tối ưu theo nút thắt thực tế

| Triệu chứng | Hướng kiểm tra trước | Hướng tối ưu có thể phù hợp |
|---|---|---|
| CPU producer cao khi serialize | Profiling serializer, allocation, custom serializer | Tối ưu object mapping, giảm conversion thừa, benchmark format khác |
| CPU consumer cao khi parse | Profiling parser/deserializer và object creation | Tối ưu DTO, custom deserializer, thử codec khác |
| Payload lớn nhưng CPU còn dư | Đo byte trước/sau compression | Compression hoặc binary format |
| Network bandwidth là bottleneck | Wire bytes, throughput link, retransmission | Compression, format nhỏ hơn, batch hoặc giảm field |
| Nhiều request nhỏ và latency cao | Round trips, connection churn, header overhead | Connection pooling, HTTP/2, batching |
| Peak memory cao | Byte array/String copy, body buffering, queue | Streaming, bounded buffer, backpressure |
| Consumer lag tăng | Processing rate, prefetch, queue depth | Batch/concurrency có kiểm soát, scale consumer |
| p99 tăng mạnh khi batch lớn | Queue wait, batch flush time, GC | Giảm batch, flush theo deadline, bounded queue |

Không áp dụng mọi tối ưu cùng lúc. Thay đổi từng yếu tố để biết yếu tố nào tạo ra cải thiện và yếu tố nào gây regression.

## 21. Ví dụ chọn giữa JSON, CBOR và JSON gzip

Giả sử benchmark trên một corpus đại diện cho kết quả:

| Phương án | Serialized bytes | Bytes sau compression | Serialize + compress CPU |
|---|---:|---:|---:|
| JSON | 500 KB | 90 KB | 2.0 ms |
| JSON + gzip | 500 KB | 90 KB | 3.1 ms |
| CBOR | 360 KB | 105 KB | 2.4 ms |
| CBOR + gzip | 360 KB | 95 KB | 3.6 ms |

Các số trên chỉ là ví dụ minh họa. Trong trường hợp giả định này:

- CBOR nhỏ hơn JSON trước nén.
- JSON gzip lại nhỏ hơn CBOR gzip.
- CBOR cần thêm CPU nhưng không giảm bytes trên đường truyền sau compression.

Nếu network là bottleneck và consumer hỗ trợ gzip JSON sẵn có, đổi sang CBOR có thể không mang lại lợi ích. Nếu CPU encode là bottleneck hoặc cần CBOR native types, quyết định có thể khác. Kết luận phải dựa trên end-to-end load test và semantics contract.

## 22. Các tối ưu thường không nên làm trước khi đo

**Đổi JSON sang binary chỉ vì binary “nhanh hơn”.** Đo payload, CPU và consumer support trước.

**Bật compression cho mọi body.** Body nhỏ hoặc đã nén có thể không được lợi.

**Tạo mapper mới cho mỗi request.** Mapper có chi phí khởi tạo và cache metadata; tái sử dụng mapper đã cấu hình.

**Chuyển object thành String rồi mới UTF-8 encode.** Dùng `writeValueAsBytes()` hoặc ghi trực tiếp ra stream nếu phù hợp.

**Buffer toàn bộ payload lớn chỉ để gọi một API tiện lợi.** Cân nhắc streaming và giới hạn memory.

**Gom batch không giới hạn.** Batch lớn có thể tăng latency, memory và chi phí retry.

**Tăng concurrency mà không theo dõi queue.** Nhiều request hơn có thể làm consumer/server quá tải và p99 xấu đi.

**Tối ưu format nhưng bỏ qua framing.** Binary payload nối không có boundary rõ ràng vẫn có thể khiến consumer đọc sai.

**So sánh benchmark không cùng semantics.** Payload nhỏ hơn do mất field hoặc precision không phải cải thiện hợp lệ.

## 23. Quy trình tối ưu có kiểm soát

1. Vẽ đường đi thực tế từ object producer đến object consumer.
2. Đo serialize, deserialize, payload bytes, compressed bytes, CPU, network, queue và end-to-end latency.
3. Xác định nút thắt chính: codec, payload size, connection, round trip, buffering hay consumer throughput.
4. Nếu codec/payload là nút thắt, benchmark JSON, CBOR, Smile hoặc schema-based format với cùng semantics.
5. Nếu byte truyền là nút thắt, đo compression algorithm và threshold trên payload thật.
6. Nếu connection/round trip là nút thắt, xem connection pooling, keep-alive, HTTP/2 và batching.
7. Nếu memory là nút thắt, loại bỏ String/byte[] copy thừa, dùng streaming và bounded buffers.
8. Nếu consumer chậm, thiết kế backpressure, bounded queue và concurrency phù hợp.
9. Giữ framing, content type, schema version và error handling rõ ràng.
10. Chạy integration/load test với p50/p95/p99, throughput, CPU, memory và network.
11. Thay đổi từng yếu tố, so sánh với baseline và kiểm tra không làm thay đổi semantics.
12. Ghi kết quả, điều kiện benchmark và trade-off để lần tối ưu sau có thể tái lập.

## Kết luận

Tối ưu định dạng tập trung vào cách Jackson biểu diễn object thành bytes và ngược lại: JSON, CBOR, Smile hoặc format schema-based có thể khác về kích thước, CPU, allocation và interoperability. Tối ưu truyền dữ liệu tập trung vào đường đi của bytes: compression, connection reuse, HTTP/2, batching, streaming, buffering, framing và backpressure. Compression nằm giữa hai lớp vì nó thay đổi payload truyền đi nhưng cũng tiêu tốn CPU. Không có một lựa chọn luôn nhanh nhất; hãy đo codec riêng, sau đó chạy load test end-to-end với cùng semantics và payload đại diện. Chọn tối ưu theo nút thắt thực tế, giữ contract rõ ràng và theo dõi cả throughput lẫn tail latency, memory và chi phí vận hành.

## Tài liệu tham khảo

- [Jackson Databind](https://github.com/FasterXML/jackson-databind) — API `ObjectMapper`, `ObjectWriter`, streaming và data binding.
- [Jackson Dataformats Binary](https://github.com/FasterXML/jackson-dataformats-binary) — các module CBOR và Smile.
- [JMH — Java Microbenchmark Harness](https://github.com/openjdk/jmh) — framework benchmark JVM với warmup, fork và measurement iteration.
- [HTTP Semantics — RFC 9110](https://www.rfc-editor.org/rfc/rfc9110) — semantics của HTTP representation và content negotiation.
- [HTTP/2 — RFC 9113](https://www.rfc-editor.org/rfc/rfc9113) — multiplexed streams, framing và flow control.
