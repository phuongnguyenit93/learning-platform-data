# Chi phí serialization và deserialization

Trong gRPC, object Java không được gửi trực tiếp qua mạng. Client chuyển message thành dãy byte theo Protobuf wire format (**serialization**); server đọc byte và dựng lại message (**deserialization**). Với chiều trả lời, quá trình diễn ra ngược lại. Hai bước này tiêu thụ CPU và bộ nhớ trên mỗi RPC, vì vậy có thể trở thành nút thắt khi request nhỏ nhưng tần suất rất cao, hoặc payload lớn và nhiều trường lồng nhau.

Trong Spring gRPC, generated stub và Protobuf marshaller thực hiện phần chuyển đổi cho ứng dụng. Muốn tối ưu đúng cần hiểu chi phí đến từ schema, kích thước payload, object allocation, sao chép buffer và compression. Đo riêng codec và đo toàn bộ RPC là hai việc khác nhau; không thể suy hiệu năng production chỉ từ thời gian gọi `toByteArray()`.

## 1. Serialization và deserialization diễn ra ở đâu?

Với một unary RPC, luồng khái quát:

```text
Client application
   Java request object
          |
          v
   Protobuf serialization
          |
          v
   gRPC framing / optional compression
          |
          v
   HTTP/2 transport -> network
          |
          v
   gRPC framing / optional decompression
          |
          v
   Protobuf deserialization
          |
          v
Server application
   Java request object
```

Response đi theo chiều ngược lại. Trong grpc-java, generated stub sử dụng marshaller gắn với message type để ghi và đọc message. Ứng dụng thường chỉ cần tạo request, gọi stub và xử lý response; không nên tự serialize thành byte rồi gửi như một RPC khác nếu không có yêu cầu đặc biệt.

Chi phí cần phân biệt:

- **Serialization CPU:** duyệt field, ghi tag, length và value vào output.
- **Deserialization CPU:** đọc tag, giải mã value, dựng message và collection.
- **Allocation:** tạo builder, message, list/map, string và buffer.
- **Copying:** chuyển dữ liệu giữa object, byte array, buffer và transport layer.
- **Compression:** thêm CPU để nén/giải nén, có thể giảm byte truyền trên mạng.
- **Network:** truyền byte, chịu ảnh hưởng latency, bandwidth và congestion.

Các thành phần có thể chồng lấp hoặc được thực hiện qua buffer nội bộ tùy implementation. Khi profiling, cần đo đúng ranh giới thay vì cộng các con số không độc lập.

## 2. Protobuf wire format ảnh hưởng kích thước và CPU

Protobuf mã hóa từng field thành tag và value. Tag chứa field number cùng wire type; giá trị có thể là varint, fixed-width hoặc length-delimited. Tên field và khoảng trắng trong file `.proto` không được gửi trên wire, nên message binary thường nhỏ hơn JSON có tên field lặp lại.

Ví dụ:

```proto
syntax = "proto3";

message OrderSummary {
  int64 order_id = 1;
  string status = 2;
  int32 item_count = 3;
  repeated int64 item_ids = 4;
  bytes receipt = 5;
}
```

Kích thước phụ thuộc giá trị thực tế, không chỉ số lượng field:

- Field có giá trị mặc định trong proto3 thường không được serialize nếu không có presence semantics cần giữ.
- Varint dùng số byte thay đổi theo độ lớn của giá trị.
- Field number từ 1 đến 15 có tag một byte; field number lớn hơn có thể cần nhiều byte hơn.
- `string`, `bytes`, nested message và packed repeated fields là length-delimited, cần thêm length prefix.
- `fixed32`/`sfixed32` luôn dùng 4 byte value; `fixed64`/`sfixed64` dùng 8 byte.

Với số nguyên có thể âm, `int32` âm thường tốn 10 byte do sign extension trong varint. Nếu miền dữ liệu có nhiều số âm và cần biểu diễn hiệu quả, `sint32` dùng ZigZag encoding có thể nhỏ hơn. Chỉ đổi kiểu khi semantics của dữ liệu cho phép.

Không tối ưu field number hoặc kiểu số một cách máy móc. Khác biệt wire size cần được so với độ phức tạp schema, tương thích và dữ liệu thực tế.

## 3. Thiết kế message để giảm chi phí không cần thiết

Schema ảnh hưởng cả số byte lẫn số object được tạo khi parse:

| Thiết kế | Tác động có thể có | Cân nhắc |
| --- | --- | --- |
| Lặp nhiều field nhỏ trong message | Nhiều tag/value và accessor/object state | Gộp dữ liệu hợp lý, tránh tạo field chỉ để bọc một giá trị không cần thiết |
| Nested message sâu | Nhiều lần parse và object con | Giữ cấu trúc phản ánh domain, tránh nesting không có giá trị |
| `repeated` lớn | Tạo collection và phần tử khi parse | Giới hạn kích thước/count; dùng streaming nếu dữ liệu tự nhiên chia thành nhiều phần |
| `map` lớn | Tạo map entries và hash structures | Chỉ dùng map khi cần tra cứu theo key; repeated entry hoặc cấu trúc khác có thể phù hợp hơn tùy access pattern |
| `string` cho dữ liệu nhị phân | UTF-8 encode/decode và kiểm tra chuỗi | Dùng `bytes` cho nội dung binary |
| Lặp lại metadata trong mỗi item | Tăng payload và parse work | Đưa metadata chung lên message envelope nếu semantics cho phép |
| Field number rất lớn | Tag có thể dài hơn | Chọn field number hợp lý ngay từ đầu; không đổi số field đã public chỉ để tiết kiệm vài byte |

Với `repeated` numeric, Protobuf proto3 mặc định dùng packed encoding cho các kiểu scalar đủ điều kiện, giúp giảm tag lặp. Tuy nhiên parse vẫn phải tạo giá trị cho từng phần tử. Một list hàng trăm nghìn phần tử có thể tốn nhiều CPU và heap ngay cả khi wire payload tương đối gọn.

`oneof` có thể mô tả các lựa chọn loại trừ nhau và tránh gửi nhiều nhánh không dùng. `optional` hoặc presence semantics hữu ích khi cần phân biệt “không được cung cấp” với “được cung cấp giá trị mặc định”; không nên bỏ presence chỉ để tiết kiệm byte nếu làm thay đổi ý nghĩa nghiệp vụ.

Schema cần được thiết kế cho cả tương thích tiến/lùi và hiệu năng. Không tái sử dụng field number đã xóa; đánh dấu `reserved` khi loại field để tránh diễn giải nhầm dữ liệu cũ.

## 4. Kích thước payload và allocation trong Java

Message lớn không chỉ tốn byte truyền. Khi parse, Protobuf tạo object message và có thể tạo thêm:

- `String` cho field chuỗi.
- `ByteString` cho field `bytes`.
- collection cho `repeated` và `map`.
- nested message cho cấu trúc lồng nhau.
- builder hoặc buffer trung gian trong quá trình dựng/ghi message.

Nhiều RPC nhỏ có thể tạo áp lực allocation lớn hơn một RPC lớn có cùng tổng số byte, vì mỗi call còn có framing, metadata, callback và object lifecycle riêng. Ngược lại, một message khổng lồ có thể gây peak heap, GC pause và latency tail.

Ví dụ kiểm tra kích thước serialized message:

```java
OrderSummary summary = OrderSummary.newBuilder()
    .setOrderId(1042L)
    .setStatus("CONFIRMED")
    .setItemCount(3)
    .addItemIds(11L)
    .addItemIds(12L)
    .addItemIds(13L)
    .build();

int encodedSize = summary.getSerializedSize();
byte[] encoded = summary.toByteArray();

OrderSummary decoded = OrderSummary.parseFrom(encoded);
```

`getSerializedSize()` hữu ích để quan sát wire size. `toByteArray()` tạo một byte array mới; nếu gọi trong đường nóng chỉ để đo hoặc log thì sẽ phát sinh allocation và copy thêm. Trong RPC bình thường, hãy để generated marshaller quản lý serialization. `parseFrom(byte[])` phù hợp cho codec test hoặc dữ liệu byte đã có; không cần gọi nó thủ công cho response nhận từ generated stub.

Không giữ cả object graph, byte array và bản sao `ByteString` của cùng payload lâu hơn cần thiết. Với upload/download lớn, cân nhắc streaming hoặc chia batch có giới hạn thay vì tích lũy toàn bộ nội dung trong heap.

## 5. String, bytes và chuyển đổi dữ liệu

`string` trong Protobuf là UTF-8. Nếu ứng dụng bắt đầu với `byte[]` rồi chuyển sang `String`, sau đó lại encode thành UTF-8, có thể tạo thêm object và copy không cần thiết. Nếu nội dung là ảnh, file, compressed blob hoặc binary token, dùng `bytes`.

Ví dụ:

```proto
message DocumentChunk {
  string file_name = 1;
  bytes content = 2;
  int32 sequence = 3;
}
```

Trong Java, generated API dùng `ByteString` cho `bytes`. `ByteString` immutable, phù hợp khi cần chia sẻ dữ liệu an toàn; nhưng tạo nó từ `byte[]` vẫn có thể cần copy để bảo đảm immutability. Không mặc định rằng dùng `ByteString` đồng nghĩa zero-copy.

Đối với dữ liệu lớn, thiết kế RPC streaming theo chunk có kích thước hữu hạn, có backpressure/flow control và giới hạn tổng dung lượng. Chunk quá nhỏ làm tăng số message, framing và callback; chunk quá lớn làm tăng peak memory và thời gian chờ mỗi message. Chọn kích thước bằng benchmark trên payload thực.

## 6. Compression: giảm network bytes, tăng CPU

Compression có thể giảm số byte truyền, đặc biệt với text hoặc payload có tính lặp. Nhưng client/server phải tốn CPU để nén/giải nén và có thể phát sinh buffer mới.

| Đặc điểm payload | Compression có thể có lợi khi | Cần thận trọng khi |
| --- | --- | --- |
| JSON/text hoặc field lặp nhiều | Payload đủ lớn và bandwidth là nút thắt | CPU đã bão hòa hoặc latency budget rất thấp |
| Dữ liệu binary đã nén | Ít khi giảm thêm đáng kể | Nén lại chỉ tăng CPU và đôi khi tăng kích thước |
| Message nhỏ | Thường không đáng kể | Framing/compression overhead lớn so với payload |
| Streaming nhiều message | Có thể giảm network traffic | CPU nén trên mỗi message làm tăng latency và giảm throughput |

Không bật compression cho mọi RPC theo mặc định mà không đo. Có thể chọn compressor ở client call hoặc stub theo API grpc-java đang dùng; server phải hỗ trợ cơ chế tương ứng. Cũng cần xem xét rủi ro tài nguyên khi giải nén payload không tin cậy: giới hạn message size và tài nguyên xử lý.

Đánh giá compression bằng ít nhất ba chỉ số: CPU time, bytes on wire và end-to-end latency. Payload giảm 70% không phải thắng lợi nếu CPU tăng gấp đôi và p99 latency xấu đi.

## 7. Unary và streaming có profile chi phí khác nhau

Unary RPC gửi một request và nhận một response. Với payload nhỏ, chi phí mỗi call như tạo call, metadata, serialization và scheduling có thể chiếm tỷ trọng đáng kể. Batch nhiều item trong một request có thể giảm số call nhưng làm tăng payload và latency chờ batch.

Streaming RPC gửi nhiều message trong cùng một call. Nó có thể amortize chi phí thiết lập call, nhưng mỗi message vẫn cần serialize/deserialize và chịu flow control. Streaming không tự động tiết kiệm CPU; lợi ích thường đến từ giảm số call, pipeline dữ liệu và giới hạn bộ nhớ theo chunk.

| Kiểu trao đổi | Điểm nóng thường gặp | Cách đo |
| --- | --- | --- |
| Unary, payload nhỏ, QPS cao | Allocation/call overhead và scheduling | Throughput, CPU/request, allocation/request |
| Unary, payload lớn | Encode/decode, copy, network và GC | CPU/message, serialized bytes, heap/GC |
| Server streaming | Parse nhiều response, consumer chậm | Message rate, queue depth, flow-control wait |
| Client/bidi streaming | Buffering và lifecycle callback | In-flight messages, memory per stream, cancellation |

Không gom mọi message của một stream vào list chỉ để xử lý sau nếu có thể xử lý từng phần. Cách đó làm mất lợi ích giới hạn bộ nhớ của streaming và có thể gây `OutOfMemoryError`.

## 8. Đo riêng codec và đo end-to-end

Benchmark codec trả lời câu hỏi “Protobuf encode/decode tốn bao nhiêu CPU và allocation?”. Benchmark RPC trả lời “Client-server hoàn thành request trong điều kiện thực tế mất bao lâu?”. Hai phép đo cần tách biệt.

Một benchmark JMH tối giản:

```java
import org.openjdk.jmh.annotations.*;
import java.util.concurrent.TimeUnit;

@State(Scope.Thread)
@BenchmarkMode(Mode.AverageTime)
@OutputTimeUnit(TimeUnit.MICROSECONDS)
public class ProtobufCodecBenchmark {

    private OrderSummary message;
    private byte[] payload;

    @Setup
    public void setup() throws Exception {
        message = OrderSummary.newBuilder()
            .setOrderId(1042L)
            .setStatus("CONFIRMED")
            .setItemCount(3)
            .addItemIds(11L)
            .addItemIds(12L)
            .addItemIds(13L)
            .build();
        payload = message.toByteArray();
    }

    @Benchmark
    public byte[] serialize() {
        return message.toByteArray();
    }

    @Benchmark
    public OrderSummary deserialize() throws Exception {
        return OrderSummary.parseFrom(payload);
    }

    @Benchmark
    public int serializedSize() {
        return message.getSerializedSize();
    }
}
```

Đây là benchmark minh họa; cần cấu hình JMH forks, warmup, measurement iterations và profiler phù hợp. Dùng payload đại diện cho production, không chỉ một message nhỏ cố định. Benchmark trả về kết quả để JMH tiêu thụ, tránh dead-code elimination. Không đưa `toByteArray()` vào `@Setup` nếu mục tiêu là đo serialization; với deserialize, chuẩn bị byte array trước để chỉ đo parse.

Đo thêm:

- Allocation rate và bytes allocated/op.
- GC count, pause và heap occupancy.
- CPU profile để xác định method encode/decode chiếm bao nhiêu thời gian.
- Kích thước payload ở p50/p95/p99, không chỉ một mẫu trung bình.

Đối với end-to-end, gọi generated stub tới server test qua transport tương ứng, giữ riêng thời gian client serialization, network, server deserialization và business handler nếu tracing/benchmark harness cho phép. Đo cả latency p50/p95/p99, throughput và error rate. Chạy với TLS/compression/payload size giống môi trường mục tiêu.

## 9. Cách tối ưu dựa trên số liệu

Một quy trình thực tế:

1. **Lập baseline:** ghi throughput, latency percentiles, CPU, allocation, GC và bytes/message.
2. **Tách payload:** đo theo method và nhóm kích thước; tìm message có serialized size hoặc allocation bất thường.
3. **Profile CPU/heap:** dùng JFR hoặc profiler tương đương để xác định encode/decode, copy, builder, string conversion hay compression là nút thắt.
4. **Thay đổi một yếu tố:** schema, batch size, chunk size, compression hoặc cách dựng message.
5. **Đo lại trên cùng workload:** giữ số client, concurrency, payload distribution và runtime settings.
6. **Kiểm tra tương thích:** thay đổi schema phải giữ field number, wire compatibility và semantics.
7. **Theo dõi production:** xác nhận cải thiện không làm p99, error rate hoặc heap xấu đi.

Các lựa chọn thường đáng thử:

- Dùng `bytes` cho binary thay vì chuyển qua `String`.
- Tránh lặp metadata chung trong từng phần tử.
- Giới hạn `repeated` size và chunk size.
- Chọn `sint32` khi dữ liệu signed nhỏ/âm thường xuyên và schema cho phép.
- Dùng compression chỉ khi giảm network bytes đáng giá hơn CPU.
- Xử lý stream theo từng chunk để giữ bounded memory.
- Tránh gọi `toByteArray()` chỉ để log hoặc đo size trên hot path.

Không thay đổi contract public chỉ để giảm vài byte nếu lợi ích không đáng kể. Tối ưu phải được cân bằng với khả năng đọc schema, tương thích client cũ và chi phí vận hành.

## 10. Giới hạn message và bảo vệ tài nguyên

Payload quá lớn có thể gây áp lực heap ở cả client lẫn server, đặc biệt khi nhiều request đồng thời. Cần đặt giới hạn message inbound/outbound phù hợp với nghiệp vụ và phiên bản grpc-java, ví dụ `maxInboundMessageSize` trên builder hoặc cấu hình tương đương của starter.

Giới hạn không nên được chọn tùy tiện:

- Quá thấp: request hợp lệ bị từ chối.
- Quá cao: một số ít client có thể chiếm nhiều heap và làm tăng GC pause.
- Không giới hạn số phần tử: message nhỏ vừa phải vẫn có thể tạo nhiều object khi parse.
- Không giới hạn concurrent streams: tổng memory có thể tăng theo số stream đang hoạt động.

Với upload/download lớn, dùng chunking có giới hạn, quota theo caller và deadline/cancellation. Kiểm tra kích thước trước khi parse sâu nếu có lớp gateway hoặc admission control phù hợp; không chỉ dựa vào kiểm tra sau khi object graph đã được tạo.

## 11. Ma trận đo và kiểm thử hiệu năng

| Kịch bản | Biến cần thay đổi | Chỉ số cần quan sát |
| --- | --- | --- |
| Payload nhỏ vs lớn | 1 KB, 64 KB, 1 MB hoặc mức đại diện | CPU, latency, serialized bytes |
| Schema phẳng vs nested | Số field và độ sâu message | Encode/decode time, allocation |
| Repeated count | Số phần tử tăng dần | Parse time, heap, GC |
| String vs bytes | Cùng dữ liệu ở dạng text/binary | Allocation, conversion CPU |
| Compression on/off | Payload compressible và incompressible | CPU, wire bytes, p99 |
| Unary vs streaming | Số call, chunk size, số message | Throughput, memory/stream, latency |
| Concurrency | Số client và RPC đồng thời | CPU saturation, GC, queueing |
| TLS/compression thực tế | Cấu hình production | End-to-end latency và CPU |

Test hiệu năng phải warm up JVM và connection trước khi lấy mẫu; chạy đủ lâu để giảm ảnh hưởng JIT/GC ban đầu. Dùng cùng payload distribution, số call và môi trường cho các lần so sánh. Đừng so một lần chạy local với một lần chạy cluster rồi quy toàn bộ khác biệt cho Protobuf.

## 12. Bài tập vận dụng

`OrderService` nhận request chứa danh sách 5.000 item, mô tả sản phẩm dạng `string` và ảnh receipt dạng Base64. CPU server cao, GC pause tăng và p99 latency vượt mục tiêu. Nhóm đang cân nhắc bật compression và chuyển sang streaming.

**Yêu cầu:**

1. Đo serialized size và allocation của request hiện tại; tách chi phí encode, decode và RPC end-to-end.
2. Đánh giá chuyển ảnh receipt từ Base64 `string` sang `bytes`; xác định nơi còn tạo copy.
3. Phân tích `repeated` 5.000 item và khả năng xử lý theo batch hoặc stream chunk.
4. Benchmark compression với payload thực tế, so sánh CPU, wire bytes và p99 latency.
5. Dùng JMH cho codec và JFR/profiler cho server; giữ workload và payload distribution ổn định.
6. Đặt giới hạn message size, số phần tử, chunk size và concurrency để bảo vệ heap.
7. Kiểm tra wire compatibility và client cũ trước khi thay schema.

**Câu hỏi tự kiểm tra:**

- Serialization/deserialization khác network latency thế nào?
- Vì sao Protobuf message có cùng số field nhưng kích thước wire khác nhau?
- Khi nào `sint32` có thể hiệu quả hơn `int32`?
- Vì sao `toByteArray()` trong hot path có thể làm tăng allocation?
- Compression giảm byte truyền nhưng có thể làm CPU tăng ra sao?
- Streaming có tự động giảm chi phí parse không?
- Vì sao cần đo p95/p99 và allocation chứ không chỉ average time?
- JMH codec benchmark không thể thay thế end-to-end RPC benchmark ở điểm nào?

**Ghi nhớ:** Chi phí serialization/deserialization phụ thuộc schema, giá trị field, payload size, allocation và copy trong Java. Protobuf thường gọn nhưng không miễn phí; compression đổi CPU lấy network bytes, còn streaming đổi cách chia tải và quản lý memory. Trong Spring gRPC, đo codec riêng và RPC end-to-end bằng payload thực, profile CPU/GC, rồi tối ưu từng yếu tố trong khi giữ wire compatibility và giới hạn tài nguyên.
