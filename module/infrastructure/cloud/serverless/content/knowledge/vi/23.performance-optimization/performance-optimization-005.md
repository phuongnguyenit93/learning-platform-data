# Tối ưu serialization, nén dữ liệu và kích thước payload

Trong ứng dụng serverless, một request hoặc event thường đi qua nhiều ranh giới: client, API Gateway, Java function, queue, event bus, database và service khác. Mỗi lần dữ liệu vượt qua ranh giới, hệ thống có thể phải serialize object thành bytes, truyền qua mạng, deserialize ở đầu nhận và cấp phát thêm bộ nhớ. Payload càng lớn thì thời gian truyền, CPU serialization, memory allocation và chi phí lưu trữ/truyền dữ liệu càng có thể tăng.

Tối ưu payload không chỉ là nén JSON. Đội phát triển cần chọn đúng dữ liệu cần gửi, định dạng phù hợp, cách serialize an toàn, phương thức truyền dữ liệu lớn và chính sách nén dựa trên số đo. Payload nhỏ hơn có thể giảm network latency nhưng nén quá mạnh lại tiêu tốn CPU, làm tăng invocation duration hoặc kéo dài thời gian xử lý.

Bài học này trình bày cách thiết kế DTO và event payload gọn, chọn JSON/Avro/Protobuf, tối ưu Jackson, dùng gzip hoặc Brotli đúng nơi, xử lý dữ liệu lớn qua object storage và đo hiệu quả trên Java serverless.

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích serialization, deserialization và tác động của payload size đến latency, CPU, memory và cost.
- Thiết kế DTO chỉ chứa dữ liệu cần thiết cho từng API hoặc event contract.
- Chọn JSON, Avro, Protobuf hoặc định dạng nhị phân theo yêu cầu tương tác và schema.
- Tối ưu Jackson có kiểm soát mà không làm mất semantics của dữ liệu.
- Nén HTTP request/response và message bằng gzip hoặc thuật toán phù hợp.
- Dùng content negotiation và header đúng cho HTTP compression.
- Biết khi nào không nên nén và cách đặt ngưỡng dựa trên benchmark.
- Xử lý binary/large payload bằng object storage và event reference pattern.
- Giới hạn kích thước, tỷ lệ giải nén và memory khi nhận payload không tin cậy.
- Đo serialization duration, compressed size, network time và end-to-end latency.
- Kiểm thử schema compatibility, backward compatibility và hiệu năng trước khi phát hành.

## 1. Serialization ảnh hưởng đến hiệu năng serverless như thế nào?

**Serialization** chuyển object trong bộ nhớ thành một dạng có thể truyền hoặc lưu trữ, thường là JSON, Protobuf, Avro hoặc bytes. **Deserialization** thực hiện chiều ngược lại để tạo object cho ứng dụng.

Một request HTTP có thể trải qua:

~~~mermaid
flowchart LR
    A["Java object / DTO"] --> B["Serialize"]
    B --> C["Payload bytes"]
    C --> D["Network / Gateway"]
    D --> E["Payload bytes"]
    E --> F["Deserialize"]
    F --> G["Java DTO"]
~~~

Thời gian xử lý một request có thể bao gồm:

- Chọn và ánh xạ dữ liệu sang DTO.
- Serialize DTO thành bytes.
- Nén payload nếu được cấu hình.
- Truyền bytes qua network hoặc broker.
- Giải nén ở consumer.
- Deserialize bytes thành DTO.
- Validate schema và chuyển sang model nghiệp vụ.

Payload lớn có thể gây ra các tác động sau:

| Tác động | Vì sao xảy ra |
|---|---|
| Network latency tăng | Nhiều bytes hơn phải truyền qua gateway, broker và service |
| CPU tăng | Serialize, parse và compression cần CPU |
| Memory pressure | Buffer, byte array và object graph chiếm heap |
| GC tăng | Nhiều object/string tạm được tạo và thu hồi |
| Cold start nặng hơn | Khởi tạo thư viện hoặc xử lý payload lớn làm tăng công việc lúc đầu |
| Retry tốn kém | Message lớn phải truyền/lưu lại nhiều lần |
| Chi phí tăng | Network egress, log, storage và request processing có thể tăng |

Không phải mọi payload lớn đều cần nén. Nếu dữ liệu là ảnh JPEG, video hoặc file ZIP, dữ liệu đã được nén và gzip lần nữa có thể chỉ làm tăng CPU mà gần như không giảm bytes.

### Một mô hình chi phí đơn giản

Thời gian truyền phụ thuộc kích thước payload và băng thông hữu dụng:

~~~text
Transfer time ≈ payload bytes / effective bandwidth
~~~

Đây chỉ là ước lượng lý tưởng; thực tế còn có TLS, round trip, congestion, queueing, gateway overhead và giới hạn throughput. Nén giảm số bytes nhưng thêm thời gian CPU để nén và giải nén.

Do đó, hãy so sánh tổng thời gian:

~~~text
Total time =
  serialization
  + compression
  + network transfer
  + decompression
  + deserialization
  + application processing
~~~

Đừng đánh giá tối ưu chỉ bằng phần trăm bytes giảm. Điều cần cải thiện là latency, throughput, memory và chi phí toàn luồng.

## 2. Thiết kế payload: chỉ gửi dữ liệu consumer cần

Cách giảm payload hiệu quả nhất thường là bỏ dữ liệu không cần thiết trước khi serialize.

Một lỗi thường gặp là serialize trực tiếp entity database hoặc domain aggregate. Object này có thể chứa:
- Quan hệ lồng nhau mà consumer không sử dụng.
- Lazy-loaded collection gây thêm truy vấn.
- Field nội bộ hoặc thông tin nhạy cảm.
- Audit metadata không cần truyền.
- Dữ liệu lớn như danh sách lịch sử, ảnh hoặc file.
- Cấu trúc phụ thuộc ORM hoặc framework.

Thay vào đó, tạo DTO theo mục đích sử dụng.

### Entity và DTO có trách nhiệm khác nhau

Ví dụ entity nội bộ có thể chứa thông tin chi tiết:

~~~java
public class OrderEntity {
    private String id;
    private String customerId;
    private String internalNote;
    private String paymentToken;
    private List<OrderLineEntity> lines;
    private List<OrderAuditEntity> auditHistory;
    private CustomerEntity customer;
    // ORM mapping and persistence methods
}
~~~

Không nên serialize object này trực tiếp cho API hoặc event. Một DTO công khai có thể chỉ giữ các field cần thiết:

~~~java
import java.util.List;

public record OrderSummaryResponse(
        String orderId,
        String status,
        long totalAmount,
        String currency,
        List<OrderLineResponse> lines) {
}

public record OrderLineResponse(
        String sku,
        int quantity) {
}
~~~

DTO giúp kiểm soát:
- Field nào được phép rời khỏi service.
- Field nào bắt buộc trong contract.
- Dữ liệu có cần flatten hay không.
- Version/schema evolution.
- Kích thước response và thông tin nhạy cảm.

Không tạo một DTO duy nhất cho mọi endpoint nếu mỗi consumer cần một tập dữ liệu khác nhau. API detail có thể cần nhiều field hơn API list; event `OrderPlaced` có thể cần snapshot tối thiểu để consumer thực hiện công việc.

### Dùng projection và pagination

Nếu API chỉ cần danh sách đơn hàng, không tải toàn bộ lịch sử và quan hệ rồi mới loại bỏ field ở mapper. Hãy dùng database projection/query chỉ lấy cột cần thiết.

Với collection lớn:
- Dùng pagination hoặc cursor.
- Đặt page size tối đa.
- Chỉ trả field cần thiết.
- Cung cấp endpoint detail cho dữ liệu cần tải riêng.
- Tránh trả một mảng hàng chục nghìn phần tử trong một response.

Pagination giảm kích thước mỗi response và giúp kiểm soát memory. Cursor pagination thường ổn định hơn offset pagination với tập dữ liệu thay đổi liên tục, tùy cách sort và index.

### Không làm payload ngắn đến mức khó hiểu

Rút tên field từ `customerId` thành `c` có thể giảm một ít bytes JSON nhưng làm contract khó đọc và khó tiến hóa. Compression thường giảm đáng kể phần lặp lại của key names. Ưu tiên schema rõ ràng, DTO phù hợp và compression có đo lường thay vì mã hóa tên field tùy tiện.

## 3. Chọn định dạng serialization

Không có một định dạng tốt nhất cho mọi luồng. Quyết định phụ thuộc vào khả năng tương tác, schema evolution, kích thước, tốc độ encode/decode và tooling.

| Định dạng | Ưu điểm | Hạn chế | Trường hợp phù hợp |
|---|---|---|---|
| JSON | Dễ đọc, phổ biến, hỗ trợ rộng | Field names lặp lại, payload thường lớn hơn binary | HTTP API, webhook, tích hợp đa ngôn ngữ |
| Protobuf | Binary gọn, schema rõ, code generation | Cần quản lý schema, khó đọc trực tiếp | Service-to-service, gRPC, event throughput cao |
| Avro | Schema evolution và writer/reader schema | Cần schema distribution hoặc registry | Event streaming, data pipeline |
| CBOR | Binary representation của cấu trúc dữ liệu | Ít phổ biến hơn JSON trong một số hệ sinh thái | IoT hoặc môi trường cần binary representation |
| Java native serialization | Tích hợp trực tiếp object Java cũ | Coupling Java, khó versioning, rủi ro deserialization | Tránh dùng cho API/message mới |

### JSON

JSON phù hợp khi API cần tương tác với browser, mobile app, webhook hoặc nhiều ngôn ngữ. Dùng JSON không có nghĩa phải serialize mọi field trong object nội bộ.

Ưu tiên DTO rõ ràng, kiểu dữ liệu có semantics ổn định, field optional được định nghĩa, schema validation tại ranh giới và không gửi thông tin bí mật.

### Protobuf

Protobuf dùng field number trong wire format, vì vậy payload thường nhỏ và decode hiệu quả. Tuy nhiên, cần giữ field number ổn định và không tái sử dụng số đã xóa. Consumer cần xử lý unknown fields theo runtime và contract.

Ví dụ:

~~~protobuf
syntax = "proto3";

message OrderSummary {
  string order_id = 1;
  string status = 2;
  int64 total_amount_minor = 3;
  string currency = 4;
}
~~~

Tên `total_amount_minor` thể hiện số tiền ở đơn vị nhỏ nhất của currency, ví dụ đồng hoặc xu theo contract. Không chỉ ghi `amount` nếu consumer có thể hiểu nhầm đơn vị. Với VND, cần quy định rõ có dùng đơn vị đồng nguyên hay đơn vị quy đổi.

### Avro

Avro dùng schema khi ghi và đọc; reader/writer schema resolution hỗ trợ tiến hóa dữ liệu. Nếu consumer cần đọc message cũ, schema cũ phải còn khả dụng và các default phải phản ánh đúng semantics.

### Tránh Java native serialization cho event contract

Java native serialization gắn payload với class structure và runtime Java, khó tương tác với hệ thống khác và dễ gây vấn đề khi class thay đổi. Deserializing object không tin cậy còn có thể tạo rủi ro bảo mật nghiêm trọng qua gadget chain. Với HTTP và message broker, dùng định dạng có schema rõ như JSON, Avro hoặc Protobuf và validate input.

## 4. Tối ưu JSON với Jackson

Jackson là thư viện phổ biến trong Java để serialize/deserialize JSON. Tối ưu nên tập trung vào DTO, cấu hình rõ ràng và reuse ObjectMapper.

### Reuse ObjectMapper

Không tạo ObjectMapper mới cho mỗi request. Cấu hình một mapper dùng chung sau khi khởi tạo và không thay đổi cấu hình trong lúc xử lý request.

~~~java
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.SerializationFeature;
import com.fasterxml.jackson.datatype.jsr310.JavaTimeModule;

public final class JsonSupport {
    private JsonSupport() {
    }

    public static ObjectMapper createMapper() {
        return new ObjectMapper()
                .registerModule(new JavaTimeModule())
                .disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS);
    }
}
~~~

ObjectMapper sau khi cấu hình hoàn tất có thể được tái sử dụng an toàn giữa các thread. Nếu dùng Spring Boot, framework thường quản lý mapper; không cần tự tạo mapper khác nếu không có yêu cầu serializer riêng.

### Chỉ serialize field cần thiết

Có thể dùng `@JsonInclude` để bỏ field null nếu contract cho phép:

~~~java
import com.fasterxml.jackson.annotation.JsonInclude;

@JsonInclude(JsonInclude.Include.NON_NULL)
public record CustomerSummary(
        String customerId,
        String displayName,
        String optionalPhone) {
}
~~~

Chỉ bỏ null khi consumer phân biệt được field vắng mặt với field có giá trị null. Trong một số contract, null có ý nghĩa rõ ràng như xóa giá trị hoặc chưa xác định; tự động loại bỏ có thể thay đổi semantics.

Không dùng `NON_EMPTY` toàn cục nếu chuỗi rỗng hoặc collection rỗng có ý nghĩa nghiệp vụ.

### Không serialize quan hệ ORM ngoài ý muốn

Entity có lazy relationship có thể kích hoạt truy vấn N+1 trong lúc serialize hoặc tạo vòng tham chiếu. Map sang DTO trong service/application layer bằng query có projection. Tránh để JSON serializer quyết định lúc nào truy cập database.

### Date, time và decimal

- Dùng ISO-8601/UTC cho timestamp nếu contract yêu cầu thời điểm.
- Phân biệt `Instant`, `LocalDate` và `LocalDateTime`; chúng không mang cùng semantics timezone.
- Với tiền, dùng integer minor units hoặc decimal string theo contract để tránh mất chính xác do floating point.
- Không chuyển tiền sang `double` chỉ để giảm payload.
- Quy định scale, rounding và currency rõ ràng.

### Streaming thay vì buffer toàn bộ payload

Với payload lớn nhưng vẫn phải xử lý trong một request, streaming có thể giảm peak memory so với serialize toàn bộ thành một byte array. Jackson hỗ trợ ghi JSON ra OutputStream:

~~~java
import com.fasterxml.jackson.core.JsonGenerator;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.OutputStream;

public final class JsonWriter {
    private final ObjectMapper mapper;

    public JsonWriter(ObjectMapper mapper) {
        this.mapper = mapper;
    }

    public void write(Object value, OutputStream output) throws Exception {
        try (JsonGenerator generator =
                     mapper.getFactory().createGenerator(output)) {
            mapper.writeValue(generator, value);
        }
    }
}
~~~

Đoạn code giả định output stream thuộc quyền quản lý của phương thức; nếu stream do framework quản lý, không đóng stream ở đây mà chỉ quản lý generator theo lifecycle phù hợp. Trong HTTP serverless, streaming response phụ thuộc khả năng của gateway/runtime và không phải tích hợp nào cũng hỗ trợ response streaming.

Streaming giảm việc giữ toàn bộ serialized payload trong heap, nhưng không loại bỏ giới hạn payload của gateway hoặc broker. Nếu consumer cần toàn bộ document trước khi xử lý, streaming ở producer chưa chắc làm giảm memory ở consumer.

## 5. Đo serialization trước khi tối ưu

Không đoán serializer nào nhanh hơn. Tạo benchmark với object và payload gần production.

Đo ít nhất:
- Serialization duration.
- Deserialization duration.
- Kích thước bytes trước compression.
- Kích thước bytes sau compression.
- Peak memory/allocation nếu có công cụ đo.
- CPU time hoặc CPU utilization dưới tải.
- End-to-end latency và throughput.

Có thể đo đơn giản trong Java:

~~~java
long started = System.nanoTime();
byte[] json = objectMapper.writeValueAsBytes(response);
long serializeNanos = System.nanoTime() - started;

long payloadBytes = json.length;
~~~

Đoạn code minh họa phép đo một lần; không dùng một sample duy nhất làm kết luận hiệu năng. Benchmark cần warm-up JVM, nhiều iteration, dữ liệu đại diện và tách benchmark micro khỏi network/load test. Với microbenchmark Java, JMH phù hợp hơn vòng lặp tự viết vì xử lý warm-up, dead-code elimination và measurement harness.

### Tính tỷ lệ giảm kích thước

~~~text
Compression ratio = compressed bytes / original bytes
Size reduction (%) = (1 - compression ratio) × 100
~~~

Ví dụ JSON 200 KB nén còn 40 KB:
- Compression ratio = 0,20.
- Size reduction = 80%.

Tỷ lệ giảm bytes không phản ánh chi phí CPU. Hãy đo cả thời gian nén/giải nén và p95/p99.

### So sánh trên cùng dữ liệu

Khi so JSON với Protobuf hoặc gzip với không nén:
- Dùng cùng logical data.
- Dùng cùng schema/semantics.
- Đo cả encode và decode.
- Dùng cùng hardware/runtime và JVM options.
- Chạy đủ vòng warm-up và iteration.
- Ghi kích thước payload và thời gian.
- Xác minh output tương đương về mặt dữ liệu.

Không so một JSON đã nén với Protobuf chưa nén rồi kết luận Protobuf luôn tốt hơn. So sánh phải phản ánh pipeline thật.

## 6. Nén dữ liệu: gzip, Brotli và lựa chọn thuật toán

Nén giảm số bytes phải truyền hoặc lưu. Các định dạng phổ biến:

| Thuật toán | Đặc điểm | Dùng khi |
|---|---|---|
| gzip/DEFLATE | Tương thích rộng, hỗ trợ tốt trong HTTP và Java | JSON/text API, message payload có tính lặp |
| Brotli | Thường nén text/web tốt, có nhiều mức chất lượng và tradeoff CPU | Response web khi client/gateway hỗ trợ |
| Zstandard (zstd) | Tốc độ và tỷ lệ nén linh hoạt, phổ biến trong data pipeline | Service-to-service hoặc event pipeline có hỗ trợ |
| Không nén | Không tốn CPU nén/giải nén | Payload nhỏ hoặc đã nén |

Không chọn thuật toán chỉ dựa trên tỷ lệ nén tối đa. Compression level cao thường tốn CPU hơn và có thể làm latency tăng. Hãy đo trên loại payload thực tế.

### Khi nén có lợi?

Nén thường có lợi với JSON lặp lại nhiều key/value, XML hoặc text log, payload lớn truyền qua mạng chậm và response lớn được tải thường xuyên.

Nén thường ít có lợi với JPEG, PNG, WebP, MP4, ZIP, gzip hoặc file đã nén; payload rất nhỏ; dữ liệu ngẫu nhiên hoặc đã mã hóa; hay luồng cần latency cực thấp nhưng CPU hạn chế.

### Đặt ngưỡng nén

Không có một ngưỡng bytes đúng cho mọi service. Có thể bắt đầu benchmark ở vài kích thước như 1 KB, 4 KB, 16 KB và 64 KB, sau đó xác định ngưỡng theo kích thước payload, CPU/memory allocation, tỷ lệ nén thực tế, latency budget, băng thông và chi phí network.

Chỉ nén khi lợi ích đo được vượt chi phí CPU và overhead. Có thể bỏ qua compression nếu payload dưới ngưỡng hoặc content type không nén hiệu quả.

## 7. Nén gzip trong Java

Java cung cấp `GZIPOutputStream` và `GZIPInputStream`. Ví dụ dưới đây nén một payload đã có sẵn trong bộ nhớ; chỉ dùng cho payload giới hạn kích thước.

~~~java
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.util.zip.GZIPOutputStream;

public final class GzipCompression {
    private GzipCompression() {
    }

    public static byte[] compress(byte[] input) throws IOException {
        ByteArrayOutputStream output = new ByteArrayOutputStream();

        try (GZIPOutputStream gzip = new GZIPOutputStream(output)) {
            gzip.write(input);
        }

        return output.toByteArray();
    }
}
~~~

Giải nén:

~~~java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.util.zip.GZIPInputStream;

public final class GzipDecompression {
    private GzipDecompression() {
    }

    public static byte[] decompress(byte[] compressed) throws IOException {
        try (GZIPInputStream gzip = new GZIPInputStream(
                     new ByteArrayInputStream(compressed));
             ByteArrayOutputStream output = new ByteArrayOutputStream()) {

            byte[] buffer = new byte[8192];
            int read;
            while ((read = gzip.read(buffer)) != -1) {
                output.write(buffer, 0, read);
            }

            return output.toByteArray();
        }
    }
}
~~~

Đây là ví dụ tối giản cho dữ liệu tin cậy và nhỏ. Với payload đến từ client hoặc broker không tin cậy, không giải nén không giới hạn vào memory. Cần giới hạn số bytes giải nén, thời gian xử lý và tỷ lệ giữa decompressed/compressed size để chống decompression bomb.

### Streaming compression

Với dữ liệu lớn, nối stream nén trực tiếp vào stream đích thay vì giữ cả input, compressed bytes và output trong heap cùng lúc.

~~~java
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.util.zip.GZIPOutputStream;

public final class GzipStreaming {
    private GzipStreaming() {
    }

    public static void compress(
            InputStream input,
            OutputStream destination) throws IOException {

        try (GZIPOutputStream gzip = new GZIPOutputStream(destination)) {
            input.transferTo(gzip);
        }
    }
}
~~~

Nếu destination do framework hoặc caller quản lý, việc đóng GZIPOutputStream sẽ đóng destination. Trong trường hợp cần giữ destination mở, dùng wrapper không đóng underlying stream hoặc quản lý lifecycle rõ ràng. Streaming chỉ hiệu quả nếu nguồn và đích thực sự hỗ trợ streaming; nếu SDK hoặc gateway buffer toàn bộ body, memory vẫn có thể tăng.

## 8. HTTP content negotiation và header

HTTP compression cần thống nhất giữa client và server. Client thông báo các encoding hỗ trợ bằng `Accept-Encoding`; server chọn encoding phù hợp và khai báo trong `Content-Encoding`.

Request từ client:

~~~http
GET /api/orders HTTP/1.1
Accept: application/json
Accept-Encoding: gzip, br
~~~

Response nén gzip:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Content-Encoding: gzip
Vary: Accept-Encoding
Content-Length: 842
~~~

Các header quan trọng:

| Header | Vai trò |
|---|---|
| `Accept-Encoding` | Client liệt kê content coding có thể nhận |
| `Content-Encoding` | Encoding đã áp dụng lên representation, ví dụ gzip |
| `Content-Type` | Kiểu dữ liệu sau khi giải nén, ví dụ application/json |
| `Vary: Accept-Encoding` | Cache phân biệt representation theo encoding |
| `Content-Length` | Số bytes của body được truyền sau content encoding, nếu biết trước |

Nếu response được nén, Content-Length phải là độ dài compressed bytes. Nếu dùng streaming và chưa biết độ dài, không tự đặt Content-Length cũ; để server/framework chọn cơ chế framing phù hợp.

### Client không hỗ trợ encoding

Server không nên gửi gzip nếu client không chấp nhận encoding đó. `Accept-Encoding` có thể có quality values như `gzip;q=1, br;q=0.8`. Thư viện/framework HTTP thường hỗ trợ negotiation; nếu tự triển khai, phải parse header đúng và có fallback identity khi được phép.

### Cache và Vary

Nếu cùng URL có response gzip và identity, cache trung gian cần biết representation phụ thuộc `Accept-Encoding`. Header `Vary: Accept-Encoding` giúp cache chọn đúng phiên bản. Nếu không, client có thể nhận bytes gzip mà không biết giải nén hoặc cache trả sai representation.

### Tránh nén hai lần

Nếu API Gateway, load balancer, CDN hoặc framework đã nén response, không tự nén lần nữa ở handler. Nén hai lần thường không giúp đáng kể và làm tăng CPU. Xác định thành phần nào sở hữu compression và kiểm tra header trên response cuối cùng.

## 9. Nén request và response trong Spring Boot

Spring Boot có thể cấu hình HTTP response compression bằng server settings. Ví dụ:

~~~yaml
server:
  compression:
    enabled: true
    mime-types:
      - application/json
      - application/xml
      - text/html
      - text/plain
    min-response-size: 2KB
~~~

Cấu hình cụ thể phụ thuộc embedded server và Spring Boot version. Kiểm tra server đang dùng, content type và response header thực tế. `min-response-size` là ngưỡng minh họa; benchmark để chọn giá trị.

Nếu gateway/CDN đã nén response, hãy quyết định compression ở một tầng duy nhất. Với request compression, server phải hỗ trợ đọc `Content-Encoding` và giải nén trước khi parse body; cấu hình response compression không tự động có nghĩa request body được giải nén.

### Xử lý Content-Encoding ở adapter

Adapter HTTP có thể:
1. Đọc `Content-Encoding`.
2. Chỉ chấp nhận encoding được hỗ trợ.
3. Giới hạn compressed body size trước khi giải nén.
4. Giải nén với giới hạn decompressed bytes và deadline.
5. Parse JSON và validate schema.
6. Trả lỗi 400/413/415 phù hợp nếu encoding hoặc payload không hợp lệ.

Không tin header `Content-Length` tuyệt đối vì request có thể chunked hoặc header có thể sai. Giới hạn thực tế cần áp dụng khi đọc stream.

## 10. Payload budget cho HTTP và serverless trigger

Mỗi nền tảng và integration có giới hạn riêng cho request/response, invocation payload, message hoặc event. Giới hạn có thể khác nhau theo loại API, trigger, region, account quota và phiên bản sản phẩm. Trước khi chọn payload contract, kiểm tra giới hạn hiện hành của chính đường đi: client → gateway → function, producer → broker → consumer và function → downstream service.

Không thiết kế dựa trên giả định rằng mọi service đều cho phép cùng một kích thước body. Một payload có thể hợp lệ ở API Gateway nhưng vượt giới hạn event source hoặc SDK downstream.

### Thiết lập payload budget

Ví dụ budget nội bộ:

| Loại payload | Mục tiêu thiết kế minh họa | Hành động khi vượt |
|---|---:|---|
| HTTP response list | ≤ 100 KB | Pagination hoặc field selection |
| HTTP request JSON | ≤ 256 KB | Từ chối 413 hoặc chuyển upload sang object storage |
| Event message | ≤ 64 KB | Rút gọn event hoặc gửi object reference |
| Metadata | ≤ 8 KB | Loại field lặp và dữ liệu không cần |

Đây là ngưỡng thiết kế minh họa, không phải giới hạn sản phẩm của AWS hoặc Google Cloud. Hãy chọn budget thấp hơn giới hạn platform đủ để dành chỗ cho envelope, encoding và thay đổi contract.

### Giới hạn ở nhiều tầng

Cần tính:
- HTTP body trước và sau compression.
- Envelope của API Gateway hoặc event source.
- Base64 expansion nếu binary được biểu diễn thành text.
- Message attributes/headers.
- Retry, batch và DLQ behavior.
- Response size sau serialization.
- Buffer và memory khi SDK đọc toàn bộ body.

Nếu trigger gửi batch nhiều message, tổng payload batch có thể vượt giới hạn dù từng message riêng lẻ vẫn nhỏ.

## 11. Base64 và binary payload

Base64 biểu diễn bytes thành ký tự ASCII để truyền qua kênh chỉ chấp nhận text. Nó làm kích thước tăng khoảng một phần ba trước khi tính envelope/JSON overhead.

Với input có kích thước N bytes, Base64 thường cần khoảng:

~~~text
Encoded size ≈ 4 × ceil(N / 3)
~~~

Ví dụ 3 MB binary trở thành khoảng 4 MB Base64, chưa tính JSON field names và metadata.

Không Base64 hóa file lớn chỉ để nhét vào JSON event. Có thể dùng binary HTTP upload nếu gateway/client hỗ trợ, multipart upload, presigned URL có thời hạn hoặc upload trực tiếp đến object storage. Sau khi upload, producer phát event chứa object reference.

Với API Gateway/Lambda hoặc các adapter serverless, binary payload handling có thể có quy tắc riêng. Kiểm tra cấu hình binary media type, encoding và giới hạn body của từng integration.

## 12. Large payload: object storage pointer pattern

Khi payload lớn vượt budget message, pattern phổ biến là lưu bytes vào object storage rồi gửi event nhỏ chứa tham chiếu.

~~~mermaid
sequenceDiagram
    participant P as Producer
    participant S as Object storage
    participant Q as Queue / Event bus
    participant C as Consumer function
    P->>S: Upload object
    S-->>P: Object key / version
    P->>Q: Publish event with reference
    Q->>C: Deliver small event
    C->>S: Get object using workload identity
    S-->>C: Stream object bytes
    C->>C: Process and record result
~~~

Event reference có thể chứa:

~~~json
{
  "eventId": "evt-1042",
  "eventType": "com.example.document.uploaded",
  "schemaVersion": "1.0",
  "data": {
    "bucket": "orders-documents",
    "objectKey": "prod/2026/11/doc-1042.json",
    "objectVersion": "v-17",
    "contentType": "application/json",
    "contentLength": 5242880,
    "checksumSha256": "..."
  }
}
~~~

Consumer dùng runtime identity để đọc đúng object. Nếu dùng object key, nên bảo đảm:
- Key hoặc version không bị ghi đè ngoài ý muốn.
- Có checksum để xác minh nội dung.
- IAM chỉ cho phép đọc đúng bucket/prefix.
- Object retention đủ dài cho retry/replay.
- Có lifecycle policy dọn object sau khi hết nhu cầu.
- Event và object được tạo theo thứ tự có kiểm soát.
- Xử lý object upload thành công nhưng publish event thất bại.

Không đưa access key hoặc credential dài hạn vào event. Nếu dùng presigned URL, giới hạn thời hạn và quyền, tránh ghi URL vào log; với consumer nội bộ, workload identity thường dễ audit hơn.

### Xử lý consistency và orphan object

Producer có thể upload object thành công nhưng không publish event được. Khi đó object mồ côi có thể tồn tại. Có thể ghi metadata trạng thái upload/publish trong database, dùng outbox để retry event, dùng lifecycle cleanup cho object chưa được tham chiếu sau một khoảng an toàn và đặt object key bất biến theo business operation.

Consumer có thể nhận event trước khi object đọc được nếu event được publish quá sớm hoặc integration cụ thể có behavior nhất quán khác dự kiến. Thiết kế retry có giới hạn và kiểm tra semantics storage; không giả định mọi lỗi GetObject đều là lỗi vĩnh viễn.

## 13. Nén event/message

Message compression có thể giảm bytes lưu và truyền, nhưng broker/consumer phải thống nhất encoding.

Một message envelope có thể có metadata:

~~~json
{
  "eventId": "evt-2001",
  "eventType": "com.example.report.generated",
  "schemaVersion": "1.0",
  "contentEncoding": "gzip",
  "contentType": "application/json",
  "payload": "<compressed bytes encoded according to transport contract>"
}
~~~

`payload` trong ví dụ là placeholder mô tả contract, không phải chuỗi literal nên publish. Nếu broker chỉ nhận text JSON, compressed bytes thường phải Base64 hóa, làm tăng kích thước khoảng một phần ba. Vì vậy, hãy kiểm tra tổng kích thước sau Base64 và envelope; nén trước rồi Base64 không có nghĩa payload cuối cùng nhỏ hơn JSON ban đầu trong mọi trường hợp.

Nếu broker hỗ trợ binary message body, có thể gửi bytes nén trực tiếp và lưu encoding/content type trong message attributes hoặc envelope ngoài. Tất cả consumer phải hiểu cùng contract. Không tự ý thay đổi encoding của event đang được consumer cũ đọc.

### Batching

Batching có thể giảm overhead mỗi message và tăng throughput, nhưng:
- Tổng batch size phải nằm trong giới hạn trigger/broker.
- Một message lỗi có thể ảnh hưởng cả batch tùy acknowledgment semantics.
- Cần partial batch response nếu platform hỗ trợ và consumer muốn retry riêng phần lỗi.
- Đo per-message processing và batch duration riêng.
- Tránh batch quá lớn làm tăng memory/cold start hoặc kéo dài thời gian ack.

Nén batch đôi khi hiệu quả hơn nén từng message do có nhiều field lặp lại, nhưng làm giảm khả năng xử lý/retry độc lập và yêu cầu consumer giải nén toàn batch. Chỉ dùng khi semantics và failure model cho phép.

## 14. An toàn khi nhận payload và giải nén

Payload đến từ client, webhook, queue hoặc event bus có thể sai định dạng hoặc được tạo có chủ đích để tiêu tốn tài nguyên.

### Giới hạn kích thước

- Đặt giới hạn compressed body trước khi nhận toàn bộ.
- Đặt giới hạn decompressed bytes sau khi giải nén.
- Giới hạn nesting depth, collection length và string length theo schema.
- Đặt timeout/deadline cho parse và validation.
- Giới hạn batch size và concurrency.
- Reject payload vượt giới hạn trước khi tạo object graph lớn.

### Decompression bomb

Một payload nén nhỏ có thể giải nén thành dữ liệu cực lớn. Không chỉ kiểm tra compressed length; phải đếm số bytes thực tế khi đọc decompressed stream và dừng khi vượt limit.

Ví dụ wrapper đếm bytes giải nén có thể dùng trong adapter:

~~~java
import java.io.FilterInputStream;
import java.io.IOException;
import java.io.InputStream;

public final class LimitedInputStream extends FilterInputStream {
    private final long maxBytes;
    private long count;

    public LimitedInputStream(InputStream input, long maxBytes) {
        super(input);
        if (maxBytes <= 0) {
            throw new IllegalArgumentException("maxBytes must be positive");
        }
        this.maxBytes = maxBytes;
    }

    @Override
    public int read() throws IOException {
        int value = super.read();
        if (value != -1) {
            add(1);
        }
        return value;
    }

    @Override
    public int read(byte[] buffer, int offset, int length)
            throws IOException {
        int read = super.read(buffer, offset, length);
        if (read > 0) {
            add(read);
        }
        return read;
    }

    private void add(int bytes) throws IOException {
        count += bytes;
        if (count > maxBytes) {
            throw new IOException("decompressed payload exceeds limit");
        }
    }
}
~~~

Dùng wrapper bên ngoài `GZIPInputStream` để đếm bytes đã giải nén:

~~~java
try (var file = Files.newInputStream(path);
     var gzip = new GZIPInputStream(file);
     var limited = new LimitedInputStream(gzip, 10L * 1024 * 1024)) {
    // Parse từ limited stream; dừng nếu vượt 10 MiB.
}
~~~

Đây là ví dụ giới hạn byte count; ứng dụng thật còn cần timeout, giới hạn nesting/object count và xử lý exception phù hợp. Nếu parser không đọc hết stream, không thể kết luận payload nằm trong giới hạn tổng; hãy đảm bảo đọc hết hoặc kiểm soát parser lifecycle.

### Không tin MIME type từ client

Client có thể khai báo `Content-Type: application/json` nhưng gửi bytes khác. Validate encoding, content type và schema thực tế. Với file upload, dùng allowlist loại file và kiểm tra nội dung theo yêu cầu nghiệp vụ.

### Compression side-channel

Nén response có thể tạo rủi ro side-channel trong một số tình huống khi response chứa secret và dữ liệu do attacker kiểm soát cùng một compression context. Nếu endpoint phản chiếu input và đồng thời phát secret trong cùng response, hãy đánh giá nguy cơ kiểu BREACH; có thể tắt compression cho response nhạy cảm hoặc tách dữ liệu/response theo thiết kế phù hợp.

Không log compressed body hoặc secret chỉ để debug. Dùng correlation ID và metadata đã được lọc.

## 15. Compression, CPU và serverless cost

Serverless thường tính phí dựa trên tài nguyên và thời gian thực thi theo mô hình của provider. Compression làm giảm network bytes nhưng tăng CPU và có thể kéo dài invocation duration.

| Trường hợp | Compression có thể giúp | Điều cần đo |
|---|---|---|
| JSON lớn, nhiều field lặp | Giảm network và message bytes | CPU nén/giải nén, p95 |
| Payload nhỏ | Lợi ích bytes thấp | Header/CPU overhead |
| Ảnh/video đã nén | Ít giảm thêm | CPU tăng nhưng bytes gần như không đổi |
| Function CPU-bound | Có thể làm duration tăng | CPU utilization và execution time |
| Network-bound | Có thể giảm end-to-end latency | Transfer duration và throughput |
| Queue backlog lớn | Có thể giảm storage/transfer | Consumer CPU và batch throughput |

Nếu function bị giới hạn CPU, compression level cao có thể làm p99 xấu hơn. Nếu đường truyền chậm và payload lớn, gzip có thể cải thiện end-to-end latency dù CPU tăng.

Không tối ưu riêng cost của một function nếu nó chuyển chi phí sang producer/consumer khác. Đo tổng producer + broker + consumer và network egress.

### Chọn compression level

Gzip có các mức nén với tradeoff tốc độ/tỷ lệ. Mức cao thường tốn CPU hơn. Hãy benchmark mức mặc định, mức thấp ưu tiên tốc độ và mức cao ưu tiên size. Không dùng mức cao nhất mặc định cho mọi request. Với response nhỏ, có thể bỏ nén; với batch lớn hoặc file text, mức cao có thể hợp lý nếu CPU còn dư và bandwidth là bottleneck.

## 16. Quan sát serialization và payload trong production

Các metric hữu ích:

| Metric | Ý nghĩa |
|---|---|
| `serialization.duration` | Thời gian serialize object |
| `deserialization.duration` | Thời gian parse payload |
| `payload.bytes` | Kích thước trước compression |
| `payload.compressed_bytes` | Kích thước sau compression |
| `compression.duration` | Thời gian nén |
| `decompression.duration` | Thời gian giải nén |
| `compression.ratio` | Compressed/original size |
| `payload.rejected_total` | Số payload vượt giới hạn hoặc sai format |
| `queue.message.age` | Tuổi message khi consumer nhận |
| `http.response.size` | Kích thước response |

Metric labels nên có cardinality thấp như content type, encoding, route template, event type và outcome. Không đưa object key, customer ID, request ID hoặc checksum đầy đủ vào label.

### Structured log

Log metadata cần thiết:
- Event type/schema version.
- Payload size và compressed size.
- Encoding.
- Duration.
- Correlation/trace ID.
- Kết quả validate hoặc error category.

Không log payload đầy đủ theo mặc định. Nếu cần debug, dùng fixture đã ẩn danh ở môi trường test.

### Tracing

Có thể tạo span riêng:
- `payload.serialize`
- `payload.compress`
- `http.client.send`
- `payload.decompress`
- `payload.deserialize`
- `object_storage.get`

Trace giúp biết CPU/serialization chiếm bao nhiêu trong root latency và có chồng lấn với network không. Đừng tạo span cho từng field; giữ span ở ranh giới có ý nghĩa.

## 17. Kiểm thử kích thước, tương thích và hiệu năng

Một test chỉ kiểm tra object deserialize thành công chưa đủ. Cần test payload ở nhiều kích thước và schema versions.

### Unit test

- DTO chỉ có field được phép.
- Null/empty field tuân theo contract.
- JSON serialization tạo đúng field name, type và timestamp format.
- Gzip output có thể giải nén và khôi phục dữ liệu tương đương.
- Payload vượt giới hạn bị reject.
- Unknown field/enum được xử lý theo policy.
- Binary/base64 không vượt payload budget sau encoding.

### Contract test

- Producer serialize theo schema version được công bố.
- Consumer mới đọc fixture schema cũ.
- Consumer cũ bỏ qua field mới nếu contract yêu cầu.
- Protobuf field number không bị tái sử dụng.
- Avro reader default có semantics hợp lệ.
- Event compression metadata khớp bytes thực tế.
- Object reference event có key/version/checksum hợp lệ.

### Performance test

Chạy các trường hợp:
- Payload 1 KB, 10 KB, 100 KB và kích thước gần budget.
- JSON không nén và gzip.
- JSON so với Protobuf/Avro nếu dùng.
- Warm JVM và cold start.
- Concurrency thấp/cao.
- Payload compressible và incompressible.
- Batch nhỏ/lớn.
- Consumer giải nén/parse dưới retry.

Ghi p50/p95/p99, throughput, CPU, memory allocation, GC và bytes truyền. Chạy cùng workload trước/sau thay đổi.

### Ví dụ test round-trip gzip

~~~java
import static org.junit.jupiter.api.Assertions.assertArrayEquals;

import org.junit.jupiter.api.Test;

class GzipCompressionTest {
    @Test
    void restoresOriginalBytes() throws Exception {
        byte[] original = ("orderId,status,currency\n"
                + "ord-1,CONFIRMED,VND\n").repeat(100).getBytes(
                        java.nio.charset.StandardCharsets.UTF_8);

        byte[] compressed = GzipCompression.compress(original);
        byte[] restored = GzipDecompression.decompress(compressed);

        assertArrayEquals(original, restored);
        org.junit.jupiter.api.Assertions.assertTrue(
                compressed.length < original.length);
    }
}
~~~

Assertion compressed nhỏ hơn original chỉ đúng với fixture có tính lặp cao như ví dụ. Không áp dụng kỳ vọng đó cho mọi payload; dữ liệu ngẫu nhiên hoặc đã nén có thể không nhỏ hơn.

## 18. Quy trình tối ưu payload

Một quy trình thực tế:

1. Đo baseline: payload bytes, serialization duration, network latency, CPU, memory và p95/p99.
2. Xác định field thừa: kiểm tra API/event contract và consumer thực sự sử dụng gì.
3. Tạo DTO/projection: chỉ lấy dữ liệu cần, áp dụng pagination.
4. Chọn format: giữ JSON nếu interoperability quan trọng; đánh giá Protobuf/Avro cho luồng phù hợp.
5. Benchmark compression: so gzip/Brotli/zstd theo payload và runtime.
6. Đặt threshold và payload budget: dựa trên giới hạn nền tảng cùng SLO.
7. Bổ sung validation/limits: compressed bytes, decompressed bytes, nesting, timeout.
8. Kiểm tra compatibility: consumer cũ/mới, DLQ và replay.
9. Canary release: quan sát bytes, CPU, p95/p99, error và cost.
10. Giữ rollback path: consumer có thể đọc message đã phát hành trước đó.

Không thay định dạng serialization và schema cùng lúc nếu không có migration plan. Khi đổi JSON sang Protobuf, cần content type/schema ID và consumer hỗ trợ cả hai định dạng trong thời gian chuyển đổi hoặc dùng route/topic version mới.

## 19. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách khắc phục |
|---|---|---|
| Serialize thẳng ORM entity | Payload lớn, lộ field nội bộ, query N+1 | DTO và projection |
| Nén mọi payload | CPU tăng, payload nhỏ không có lợi | Benchmark và threshold |
| Nén ảnh/ZIP lần nữa | Tốn CPU, ít giảm bytes | Detect content type/encoding |
| Tạo ObjectMapper mỗi request | Allocation và startup overhead | Reuse configured mapper |
| Buffer file lớn vào byte[] | Heap pressure và GC | Streaming hoặc object storage |
| Base64 hóa file lớn vào JSON | Tăng kích thước khoảng một phần ba | Binary upload/object reference |
| Gửi toàn bộ object qua queue | Chạm message limit, retry tốn kém | Metadata + object reference |
| Bỏ null/empty không theo contract | Thay đổi semantics | Xác định missing/null/empty |
| Nén hai lần ở handler và gateway | CPU tăng, response khó xử lý | Chọn một compression owner |
| Giải nén không giới hạn | Decompression bomb, OOM | Compressed/decompressed size limits |
| Dùng Java native serialization cho event | Coupling và rủi ro deserialization | JSON/Avro/Protobuf |
| Chỉ đo compression ratio | Không thấy CPU/latency tradeoff | Đo end-to-end và percentile |
| Đổi schema không có compatibility test | Consumer cũ lỗi hoặc sai nghiệp vụ | Registry, fixtures và expand-contract |

## 20. Checklist serialization, compression và payload

- [ ] API/event dùng DTO riêng, không serialize ORM entity hoặc domain aggregate trực tiếp.
- [ ] Chỉ gửi field cần thiết cho consumer.
- [ ] Có pagination/projection cho collection lớn.
- [ ] Schema mô tả required, optional, null, enum, units và time semantics.
- [ ] Định dạng JSON/Avro/Protobuf được chọn theo interoperability và throughput.
- [ ] Không dùng Java native serialization cho payload không tin cậy.
- [ ] ObjectMapper được cấu hình một lần và tái sử dụng.
- [ ] Null/empty handling không làm thay đổi contract ngoài ý muốn.
- [ ] Serialization/deserialization duration được đo.
- [ ] Compression được benchmark theo payload size và content type.
- [ ] HTTP dùng Accept-Encoding, Content-Encoding và Vary đúng.
- [ ] Không nén hai lần ở nhiều tầng.
- [ ] Compressed body và decompressed body đều có giới hạn.
- [ ] Có timeout và giới hạn parse/nesting cho payload không tin cậy.
- [ ] Binary payload không bị Base64 hóa không cần thiết.
- [ ] Payload lớn được lưu ở object storage và event chỉ mang reference.
- [ ] Object reference có key/version/checksum và lifecycle phù hợp.
- [ ] Queue batch/message size nằm trong budget của platform.
- [ ] Consumer hỗ trợ schema cũ/mới và encoding đã phát hành.
- [ ] Có unit, contract, load và cold-start tests.
- [ ] Theo dõi bytes, CPU, memory, p95/p99 và network cost sau rollout.

## Tự kiểm tra

1. Serialization và deserialization có thể làm tăng latency serverless qua những cơ chế nào?
2. Vì sao không nên serialize trực tiếp entity ORM thành API response hoặc event?
3. Khi nào JSON phù hợp hơn Protobuf và khi nào binary schema có lợi?
4. Vì sao không thể mặc định bỏ mọi field null hoặc empty?
5. Compression ratio tốt có đảm bảo end-to-end latency tốt hơn không?
6. HTTP client và server dùng những header nào để thương lượng compression?
7. Vì sao phải đặt cả compressed-size và decompressed-size limit?
8. Base64 làm payload tăng khoảng bao nhiêu và khi nào nên dùng object storage?
9. Event chứa object reference cần metadata nào để consumer đọc an toàn và xác minh nội dung?
10. Tại sao retry và DLQ cần giữ schema/encoding cũ?
11. Khi nào streaming giảm memory, và vì sao nó không tự loại bỏ giới hạn gateway?
12. Cần đo những chỉ số nào để quyết định có nên bật gzip cho một route?

Serialization và payload là một phần của đường đi dữ liệu, vì vậy tối ưu cần bắt đầu từ contract và nhu cầu thực tế của consumer. DTO gọn, định dạng phù hợp, compression có ngưỡng và streaming/object storage giúp giảm bytes và memory; giới hạn giải nén, schema compatibility và đo p95/p99 giúp thay đổi an toàn. Chỉ giữ một tối ưu khi số đo chứng minh tổng latency, throughput hoặc cost được cải thiện mà semantics nghiệp vụ vẫn nguyên vẹn.

