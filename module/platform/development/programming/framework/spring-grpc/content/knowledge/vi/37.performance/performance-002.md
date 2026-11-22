# Kích thước protobuf message

Kích thước Protobuf message quyết định lượng dữ liệu ứng dụng phải serialize, parse, giữ trong bộ nhớ và chuyển qua gRPC. Message quá lớn làm tăng băng thông, allocation, GC pressure và thời gian xử lý; message quá nhỏ nhưng gửi với tần suất rất cao lại có thể chịu nhiều overhead trên mỗi RPC. Vì vậy cần đo kích thước theo wire format và theo payload thực tế, thay vì ước lượng từ số field hoặc kích thước object Java.

Trong Spring gRPC, generated stub và Protobuf marshaller đảm nhiệm việc chuyển đổi. Người phát triển kiểm soát phần lớn kích thước thông qua schema, kiểu dữ liệu, số phần tử, nội dung `string`/`bytes`, cách chia batch và giới hạn message. Bài này tập trung vào cách tính wire size, đọc số đo trong Java và đặt giới hạn an toàn cho client/server.

## 1. Phân biệt kích thước object, Protobuf và gRPC

Một request có nhiều khái niệm kích thước khác nhau:

| Khái niệm | Bao gồm | Dùng để trả lời |
| --- | --- | --- |
| Java object size | Object header, reference, field, collection và dữ liệu được cấp phát trong heap | Request chiếm bao nhiêu bộ nhớ trong JVM? |
| Protobuf serialized size | Byte theo Protobuf wire format | Message cần bao nhiêu byte sau serialization? |
| gRPC message envelope | Cờ compression 1 byte và độ dài message 4 byte, cùng payload | Message được đóng khung thế nào trong gRPC stream? |
| HTTP/2 transport bytes | DATA frame headers, stream/connection framing, TLS và các overhead liên quan | Bao nhiêu byte thực sự đi qua transport/network? |

Các số đo này không thể thay thế lẫn nhau. `getSerializedSize()` trả kích thước Protobuf payload, không phải kích thước object Java hay tổng byte trên network. gRPC còn có framing và HTTP/2; TLS, proxy và TCP tiếp tục tạo overhead ở các lớp dưới.

Với streaming RPC, mỗi Protobuf message được đóng khung riêng trong cùng một HTTP/2 stream. Tổng dữ liệu của stream là tổng payload các message cộng framing/transport overhead, không phải kích thước của một message đơn lẻ.

## 2. Quy tắc tính kích thước wire format

Protobuf không gửi tên field. Mỗi field xuất hiện trên wire dưới dạng tag và value. Tag được tính:

```text
tag = (field_number << 3) | wire_type
field_size = tag_size + value_size
message_size = sum(field_size của các field được serialize)
```

Tag thường được mã hóa bằng varint. Các wire type thường gặp:

| Wire type | Kiểu dữ liệu tiêu biểu | Phần value |
| --- | --- | --- |
| `0` | `int32`, `int64`, `uint32`, `uint64`, `bool`, enum | Varint |
| `1` | `fixed64`, `sfixed64`, `double` | 8 byte |
| `2` | `string`, `bytes`, nested message, packed repeated | Varint length + nội dung |
| `5` | `fixed32`, `sfixed32`, `float` | 4 byte |

Field number từ 1 đến 15 thường có tag một byte; field number từ 16 trở lên có thể cần nhiều byte hơn. Với message có nhiều field xuất hiện thường xuyên, chọn số field nhỏ cho field quan trọng ngay khi thiết kế schema. Không đổi field number đã công bố chỉ để tiết kiệm một byte vì điều đó phá vỡ wire compatibility.

## 3. Varint, length-delimited và packed fields

**Varint** dùng số byte thay đổi theo giá trị. Số nhỏ thường tốn ít byte hơn số lớn. `int32`/`int64` mã hóa số âm theo dạng signed varint nên giá trị âm thường cần nhiều byte; `sint32`/`sint64` dùng ZigZag encoding và có thể hiệu quả hơn khi miền dữ liệu thường có số âm.

**Length-delimited** dùng một varint biểu diễn độ dài, theo sau là dữ liệu. Nó áp dụng cho `string`, `bytes`, nested message và packed repeated field. Ví dụ một chuỗi UTF-8 dài 5 byte có phần value gồm 1 byte length (nếu length nhỏ) và 5 byte nội dung.

**Packed repeated numeric** gom nhiều scalar vào một vùng length-delimited, chỉ trả tag một lần cho cả nhóm. Proto3 mặc định dùng packed encoding cho các repeated scalar type đủ điều kiện. Dù vậy, parse vẫn phải tạo và lưu từng phần tử trong collection; wire size nhỏ không đồng nghĩa chi phí heap thấp.

## 4. Tính thử kích thước một message

Xét schema:

```proto
syntax = "proto3";

message UploadMeta {
  int32 id = 1;
  string name = 2;
  repeated int32 parts = 3;
  bytes digest = 4;
}
```

Với dữ liệu `id = 150`, `name = "abc"`, `parts = [1, 2, 300]` và `digest` có 2 byte, có thể tính như sau:

| Field | Thành phần | Số byte |
| --- | --- | ---: |
| `id = 150` | Tag 1 byte + varint value 2 byte | 3 |
| `name = "abc"` | Tag 1 + length 1 + UTF-8 data 3 | 5 |
| `parts` packed | Tag 1 + length 1 + varint values (1 + 1 + 2) | 6 |
| `digest` | Tag 1 + length 1 + data 2 | 4 |
| **Tổng** | Protobuf serialized payload | **18** |

Ví dụ này cho thấy kích thước phụ thuộc giá trị, không chỉ khai báo kiểu. Nếu `id` lớn hơn, varint có thể dài hơn; nếu `name` có ký tự Unicode, số byte UTF-8 có thể lớn hơn số ký tự; nếu `parts` có thêm phần tử, cả length prefix và dữ liệu đều thay đổi.

Không cần tính tay trong ứng dụng. Phần tính trên giúp hiểu vì sao payload thay đổi và kiểm tra tính hợp lý của số đo.

## 5. Những yếu tố làm message lớn lên

| Yếu tố | Ảnh hưởng tới wire size | Điều cần cân nhắc |
| --- | --- | --- |
| Giá trị varint lớn | Dùng thêm byte cho value | Chọn `sint` khi semantics và phân bố số liệu phù hợp |
| Field number lớn | Tag có thể dài hơn | Dành field number nhỏ cho field thường dùng khi thiết kế mới |
| `string` dài | Length prefix và UTF-8 bytes tăng | Đặt giới hạn độ dài; không dùng string cho binary |
| `bytes` lớn | Kích thước gần bằng số byte nội dung cộng tag/length | Giới hạn upload; cân nhắc streaming |
| Nested message | Thêm tag, length prefix và toàn bộ nội dung message con | Tránh wrapper/nesting không mang ý nghĩa |
| `repeated` nhiều phần tử | Mỗi phần tử cần biểu diễn; packed chỉ giảm tag lặp | Giới hạn count hoặc chia chunk |
| `map` nhiều entry | Mỗi entry là một message con length-delimited | Chỉ dùng map khi cần semantics tra cứu theo key |
| Nhiều field có presence | Field được serialize kể cả khi giá trị là default nếu presence được đặt | Chỉ giữ presence khi semantics cần phân biệt absent/default |
| Unknown fields | Có thể được giữ lại và serialize tiếp tùy API/runtime | Lưu ý khi proxy message qua phiên bản schema khác |

Field proto3 scalar có giá trị mặc định thường không xuất hiện trên wire nếu không dùng presence semantics hoặc cơ chế tương ứng. `optional` có thể phân biệt “không được gửi” với “được gửi giá trị 0/empty”; điều này hữu ích về nghiệp vụ nhưng có thể làm field xuất hiện trên wire.

`oneof` chỉ biểu diễn nhánh đang được chọn. Với `map`, mỗi entry có key/value và overhead của một message con; một map lớn vì thế có thể tốn nhiều byte hơn dự kiến. Hãy đo bằng dữ liệu thật trước khi thay đổi schema.

Schema cần được thiết kế cho cả tương thích tiến/lùi và hiệu năng. Không tái sử dụng field number đã xóa; đánh dấu `reserved` khi loại field để tránh diễn giải nhầm dữ liệu cũ.

## 6. Đo kích thước bằng generated Java API

Generated Protobuf message cung cấp `getSerializedSize()` để lấy kích thước payload mà không cần tự tính từng field:

```java
UploadMeta message = UploadMeta.newBuilder()
    .setId(150)
    .setName("abc")
    .addParts(1)
    .addParts(2)
    .addParts(300)
    .setDigest(ByteString.copyFrom(new byte[] {0x01, 0x02}))
    .build();

int protobufBytes = message.getSerializedSize();
```

Với message ví dụ, kết quả dự kiến là 18 byte. Có thể kiểm tra bằng serialization trong unit test:

```java
byte[] encoded = message.toByteArray();

assertEquals(message.getSerializedSize(), encoded.length);
UploadMeta decoded = UploadMeta.parseFrom(encoded);
assertEquals(message, decoded);
```

`toByteArray()` tạo byte array mới, nên phù hợp với test hoặc công cụ đo nhưng không nên gọi trên hot path chỉ để ghi log kích thước. Trong RPC thông thường, generated marshaller tự serialize message. Nếu cần metric về payload, lấy kích thước từ message trước khi gửi hoặc instrument tại codec boundary theo cách tránh serialize lần thứ hai.

## 7. Kích thước message và giới hạn gRPC

Client/server cần đặt giới hạn message inbound phù hợp với workload. grpc-java cung cấp cấu hình như `maxInboundMessageSize(...)` trên builder; Spring gRPC starter có thể cung cấp property/customizer tương ứng tùy phiên bản.

Ví dụ với grpc-java:

```java
int maxMessageBytes = 8 * 1024 * 1024;

Server server = ServerBuilder.forPort(8443)
    .maxInboundMessageSize(maxMessageBytes)
    .addService(new OrdersService())
    .build();

ManagedChannel channel = ManagedChannelBuilder
    .forTarget("dns:///orders.default.svc.cluster.local:8443")
    .maxInboundMessageSize(maxMessageBytes)
    .useTransportSecurity()
    .build();
```

Giá trị 8 MiB chỉ là ví dụ, không phải mặc định hay khuyến nghị cho mọi hệ thống. Kiểm tra API và property của phiên bản grpc-java/starter đang dùng. Giới hạn inbound bảo vệ phía nhận; ứng dụng vẫn nên kiểm tra outbound payload trước khi gửi và công bố giới hạn contract cho caller.

Giới hạn thường áp dụng cho từng gRPC message, không phải tổng dung lượng của cả streaming call. Một stream có thể chứa nhiều message hợp lệ nhưng tổng cộng rất lớn. Vì vậy cần thêm quota theo stream/caller, giới hạn số chunk, deadline, cancellation và giới hạn concurrent streams.

Không nâng giới hạn vô hạn để xử lý một payload lỗi. Message lớn có thể tạo nhiều object sau parse; nhiều message đồng thời có thể làm heap tăng nhanh hơn kích thước wire.

## 8. Message lớn: batch, chunk hay streaming?

Khi payload vượt giới hạn hợp lý, chọn cách truyền theo bản chất dữ liệu:

| Cách | Khi phù hợp | Đánh đổi |
| --- | --- | --- |
| Một unary message | Payload nhỏ/vừa, cần xử lý nguyên tử và giới hạn rõ | Đơn giản nhưng toàn bộ message phải được buffer/parse |
| Batch nhiều record | Nhiều item nhỏ có thể xử lý theo lô | Giảm số RPC nhưng tăng payload và thời gian chờ gom batch |
| Client/server streaming | File, event hoặc danh sách lớn có thể chia phần | Cần quản lý thứ tự, backpressure, retry/resume và cancellation |
| Tham chiếu object ngoài băng | File rất lớn đã nằm ở object storage | Giảm payload gRPC nhưng thêm bước upload/download và quyền truy cập |

Ví dụ chunk:

```proto
message FileChunk {
  string upload_id = 1;
  int64 sequence = 2;
  bytes data = 3;
  bool last = 4;
}

service FileService {
  rpc Upload(stream FileChunk) returns (UploadResult);
}
```

Mỗi chunk cần có giới hạn kích thước, sequence và cơ chế xác nhận/hoàn tất phù hợp. Không gom toàn bộ chunk vào một list ở server nếu mục tiêu là truyền dữ liệu lớn với memory bounded. Streaming giảm kích thước từng message nhưng không tự giới hạn tổng dữ liệu hay bảo đảm backpressure nếu ứng dụng tự tạo queue không giới hạn.

## 9. Compression không làm thay đổi Protobuf serialized size

Compression có thể giảm số byte payload truyền qua gRPC nhưng không thay đổi kết quả `getSerializedSize()` của message Protobuf gốc. gRPC framing đánh dấu message có nén hay không và transport gửi phần payload đã nén.

Nén phù hợp khi payload đủ lớn và có tính lặp, chẳng hạn text hoặc cấu trúc JSON-like. Dữ liệu đã nén, ảnh JPEG/PNG hoặc archive thường không giảm đáng kể khi nén lần nữa. Compression cũng tiêu thụ CPU và có thể tăng latency.

Khi benchmark, ghi riêng:

- Protobuf serialized size trước compression.
- Compressed payload bytes nếu đo được tại transport/codec boundary.
- CPU time cho encode/decode và compression/decompression.
- End-to-end latency, throughput và p95/p99.

Không kết luận message đã “nhỏ hơn” chỉ từ số byte trên network nếu chưa phân biệt payload gốc và compressed bytes.

## 10. Bảo vệ bộ nhớ và tránh payload bất thường

Message size là một phần của resource control. Cần đặt giới hạn theo service/method và kiểm tra các trường có thể tăng không giới hạn:

- Độ dài string, bytes và số phần tử repeated/map.
- Số chunk và tổng byte trong một stream.
- Số RPC/stream đồng thời trên mỗi caller.
- Thời gian giữ message/stream và deadline.
- Queue giữa network callback và business worker.
- Số lần copy và giữ đồng thời object, byte array, buffer.

Một message 4 MiB không chỉ chiếm 4 MiB heap. Parse có thể tạo object graph và collection lớn hơn nhiều; nhiều call đồng thời nhân mức tiêu thụ đó. Chọn giới hạn từ heap budget, concurrency mục tiêu và payload distribution, sau đó xác minh bằng load test.

Không log toàn bộ message để debug. Với payload lớn hoặc chứa dữ liệu nhạy cảm, log kích thước, method, correlation ID và một số metadata không nhạy cảm; tránh tạo thêm bản serialized chỉ để ghi log.

## 11. Kiểm thử kích thước và ranh giới

Test nên bao phủ kích thước bình thường, sát giới hạn và vượt giới hạn:

| Ca kiểm thử | Điều cần xác minh |
| --- | --- |
| Message rỗng/default | Serialized size đúng với presence semantics |
| Varint nhỏ/lớn/âm | Kích thước thay đổi đúng theo kiểu mã hóa |
| String ASCII/Unicode | Đo theo UTF-8 bytes, không theo số ký tự |
| Bytes payload | Size bằng nội dung cộng tag/length |
| Repeated packed | Tag/length và phần tử được mã hóa đúng |
| Nested/map/oneof | Kích thước theo nhánh và số entry thực tế |
| Ngay dưới giới hạn | Server nhận và xử lý thành công |
| Đúng/vượt giới hạn | Xác minh boundary behavior và status thực tế của runtime |
| Nhiều message trong stream | Mỗi message tuân giới hạn; tổng stream có quota riêng |
| Compression on/off | Phân biệt serialized size với compressed bytes |
| Concurrent large calls | Heap, GC và latency vẫn trong budget |

Unit test dùng `getSerializedSize()` và round-trip `toByteArray()`/`parseFrom()` để khóa hành vi codec. Integration test gọi qua channel/server thật để xác minh giới hạn inbound và status do runtime trả. Test load cần dùng payload distribution giống production, không chỉ lặp một message cố định.

## 12. Bài tập vận dụng

`OrderService` nhận một unary request chứa 20.000 dòng hàng và ảnh biên nhận dạng `bytes`. Một số request bị từ chối do message size, trong khi nâng giới hạn khiến heap và GC tăng mạnh.

**Yêu cầu:**

1. Dùng `getSerializedSize()` để đo payload thực tế và phân tích field nào đóng góp nhiều byte nhất.
2. Tách Protobuf serialized size, gRPC envelope và network bytes khi compression được bật.
3. Đặt giới hạn cho số dòng hàng, kích thước receipt và tổng inbound message.
4. Đánh giá batch, client streaming hoặc object storage reference cho receipt lớn.
5. Xác định giới hạn theo từng message và quota tổng cho streaming call.
6. Viết test dưới/sát/vượt giới hạn, Unicode string, repeated packed và concurrent large calls.
7. Dùng load test để chọn giới hạn theo heap budget, concurrency và p99 latency.

**Câu hỏi tự kiểm tra:**

- `getSerializedSize()` đo lớp dữ liệu nào?
- Vì sao số field không đủ để dự đoán kích thước message?
- Tag Protobuf được tạo từ field number và wire type như thế nào?
- Khi nào `sint32` có thể nhỏ hơn `int32`?
- Vì sao string Unicode cần đo UTF-8 bytes?
- Packed repeated giảm overhead nào và không giảm chi phí nào?
- Giới hạn per-message khác quota toàn stream ra sao?
- Compression có làm thay đổi `getSerializedSize()` không?

**Ghi nhớ:** Kích thước Protobuf message được quyết định bởi tag, wire type, giá trị và số phần tử thực tế. Dùng `getSerializedSize()` để đo payload gốc; phân biệt nó với gRPC framing và network bytes. Đặt giới hạn inbound cùng quota cho stream/concurrency, cân nhắc batch/chunk khi payload lớn và kiểm thử các ranh giới trước khi nâng message limit trong production.
