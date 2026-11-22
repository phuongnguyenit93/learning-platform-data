# Nén, tuần tự hóa và lựa chọn kích thước thông điệp trong Microservices

Một hệ thống Microservices giao tiếp liên tục qua HTTP, gRPC, message broker và các cơ chế trao đổi dữ liệu khác. Ngay cả khi mã nghiệp vụ chạy nhanh, thời gian truyền và xử lý payload vẫn có thể làm tăng độ trễ, CPU, bộ nhớ, chi phí mạng và tải lên hàng đợi. Ngược lại, nén mọi payload ở mức cao nhất chưa chắc giúp hệ thống nhanh hơn: nén cần CPU, giải nén cần bộ nhớ, và những thông điệp rất nhỏ đôi khi còn lớn hơn sau khi nén.

Bài viết này giải thích ba quyết định liên quan nhưng khác nhau:

1. **Tuần tự hóa (serialization):** chuyển mô hình dữ liệu trong bộ nhớ thành một định dạng trao đổi có thể truyền/lưu, chẳng hạn JSON, Protocol Buffers hoặc Avro.
2. **Nén (compression):** giảm kích thước biểu diễn đã được tuần tự hóa bằng một thuật toán như gzip, Zstandard, Snappy hoặc LZ4.
3. **Thiết kế kích thước thông điệp:** chọn lượng dữ liệu hợp lý mỗi request, response, event hoặc batch; không gửi dư dữ liệu và không đẩy tất cả nghiệp vụ vào một thông điệp khổng lồ.

Trong Microservices, cần xét đồng thời **chi phí encode/decode, băng thông, latency, heap, schema compatibility, giới hạn giao thức và hành vi khi lỗi**. Đây là nội dung thuộc chủ đề *Hiệu năng và bộ nhớ đệm* trong kiến trúc hệ thống Microservices.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt byte payload trước nén, sau nén và số byte thực sự đi qua mạng.
- So sánh JSON, Protocol Buffers, Avro và một số định dạng nhị phân trong các bối cảnh API/event.
- Hiểu tỷ lệ nén và đánh đổi CPU–latency–bandwidth của gzip, Brotli, Zstandard, Snappy, LZ4.
- Chọn chính sách nén theo kích thước thông điệp, loại nội dung và điều kiện mạng.
- Thiết kế request/response hoặc event không chứa dữ liệu thừa và có khả năng tiến hóa schema.
- Xử lý thông điệp lớn bằng pagination, stream, batching hoặc tham chiếu object storage khi phù hợp.
- Giới hạn rủi ro decompression bomb, unbounded allocation, timeout và ghi log dữ liệu nhạy cảm.
- Đo lường bằng p50/p95/p99, throughput, CPU, heap, network, broker lag và lỗi thực tế.
- Áp dụng ví dụ Java/Spring Boot và một số cấu hình messaging theo phạm vi phù hợp.

## 2. Đường đi của một thông điệp

Một request phổ biến có thể được nhìn như:

~~~text
Domain object
    |
    | Serialize
    v
JSON / Protobuf / Avro bytes
    |
    | Compress (nếu bật)
    v
Compressed payload bytes
    |
    | HTTP/gRPC/message broker + TLS + framing
    v
Bytes over the wire
    |
    | Decompress (nếu có)
    v
Serialized bytes
    |
    | Deserialize + validate
    v
Domain input / business command
~~~

Ở chiều trả về, quá trình diễn ra ngược lại. Mỗi bước có thời gian, bộ nhớ tạm, cách báo lỗi và giới hạn riêng. Nén payload **không thay thế** tuần tự hóa; thuật toán nén không hiểu một bản ghi là Order hay Payment. Ngược lại, dùng định dạng nhị phân nhỏ hơn có thể giúp giảm lượng byte truyền ngay cả khi không bật compression.

Trong hệ thống bất đồng bộ, producer thường serialize và có thể compress một batch record; broker lưu trữ/chuyển tiếp, consumer giải nén rồi deserialize. Tùy công nghệ, nén có thể áp dụng ở cấp record, batch, frame hoặc transport. Cần biết chính xác tầng nén để tránh đo nhầm.

## 3. Kích thước phải tính bằng byte, không chỉ số ký tự

Khi thiết kế API, nhiều nhóm kiểm tra "body có 10.000 ký tự" rồi suy rằng nó tương đương 10 KB. Điều này không chính xác với UTF-8: một ký tự ASCII có thể chiếm 1 byte, một ký tự tiếng Việt thường có thể chiếm nhiều byte, emoji có thể chiếm 4 byte. Cách mã hóa, escape JSON và metadata đều ảnh hưởng đến kích thước.

Cần phân biệt:

| Đại lượng | Mô tả | Dùng khi nào |
|---|---|---|
| Số ký tự | Độ dài văn bản theo cách đếm đã chọn | Giới hạn UI hoặc nội dung |
| Serialized size | Byte sau JSON/Proto/Avro encode | Ước lượng bộ nhớ và payload gốc |
| Compressed size | Byte sau nén | Chọn codec và ngưỡng nén |
| Wire size | Byte truyền gồm protocol/frame/headers và overhead liên quan | Theo dõi băng thông thực tế |
| Decoded object footprint | Bộ nhớ object/array/string được tạo sau deserialize | Phân tích GC và heap |
| Batch size | Tổng byte và số record trong một batch | Điều chỉnh throughput, queue latency |

Ví dụ:

~~~java
String text = "Thông điệp tiếng Việt có dấu";
int javaChars = text.length();
int utf8Bytes = text.getBytes(StandardCharsets.UTF_8).length;
System.out.println("UTF-16 code units: " + javaChars);
System.out.println("UTF-8 bytes: " + utf8Bytes);
~~~

Trong Java, String.length() đếm đơn vị mã UTF-16, không phải số byte UTF-8 gửi đi. Đối với JSON, phải đo **byte của body đã serialize**, vì tên trường, dấu ngoặc, escape và định dạng số đều có thể làm payload thay đổi.

### 3.1. Ví dụ minh họa kích thước

Giả sử một event OrderCreated có cấu trúc như sau:

~~~json
{
  "eventId": "evt-001",
  "orderId": "order-101",
  "customerId": "customer-202",
  "occurredAt": "2026-11-12T02:00:00Z",
  "items": [
    {"sku": "A-01", "quantity": 2, "unitPriceMinor": 19900},
    {"sku": "B-03", "quantity": 1, "unitPriceMinor": 5000}
  ],
  "totalMinor": 44800,
  "currency": "VND"
}
~~~

Event này đủ để một consumer theo dõi đơn hàng, nhưng không nên nhúng cả hồ sơ khách hàng, hàng trăm ảnh, HTML biên lai hoặc lịch sử thao tác nếu consumer không cần. Một hình ảnh 2 MB được mã hóa base64 trong JSON còn làm payload lớn hơn dữ liệu ảnh gốc do overhead của base64, trước cả khi tính JSON framing.

**Quy tắc:** chọn trường dữ liệu từ nhu cầu và hợp đồng nghiệp vụ trước, sau đó mới tối ưu định dạng và nén.

## 4. Serialization: lựa chọn định dạng

**Tuần tự hóa** ánh xạ object sang biểu diễn nhị phân/văn bản có thể đọc bởi các tiến trình khác. Lựa chọn serializer ảnh hưởng đến kích thước, tốc độ, ngôn ngữ hỗ trợ, khả năng quan sát, schema evolution và chi phí duy trì.

| Định dạng | Đặc điểm | Phù hợp | Đánh đổi |
|---|---|---|---|
| JSON | Văn bản UTF-8 phổ biến, dễ đọc/debug | Public REST API, tích hợp nhiều loại client | Tên trường lặp, parsing và kích thước có thể lớn |
| Protocol Buffers | Nhị phân dựa trên schema .proto, field number | gRPC, giao tiếp nội bộ cần schema chặt | Cần quản lý schema/code generation, khó đọc trực tiếp |
| Avro | Nhị phân gắn với writer/reader schema, thuận tiện trong hệ sinh thái dữ liệu | Kafka/event streaming, data pipeline | Cần chiến lược lưu/tra cứu schema và version |
| MessagePack / CBOR | Biểu diễn nhị phân gọn cho dữ liệu dạng object | Hệ thống cần binary nhưng không muốn schema kiểu .proto | Tùy thư viện, quy ước interoperability/schema phải tự quản lý |
| XML | Văn bản cấu trúc có namespace/schema | Hệ thống legacy hoặc hợp đồng có sẵn | Thường nhiều ký tự cấu trúc, parser cần cấu hình an toàn |
| Java native serialization | Format gắn vào object Java | Ít phù hợp làm public wire contract | Coupling phiên bản/class, rủi ro bảo mật khi deserialize dữ liệu không tin cậy |

Không có định dạng luôn nhanh hơn trong mọi tình huống. Payload shape, thư viện, cấu hình, JIT, bộ nhớ và workload quyết định kết quả. Với API công khai, JSON thường có lợi về hỗ trợ client; giữa hai service cùng kiểm soát, Protobuf có thể phù hợp nếu chi phí schema và vận hành được chấp nhận.

### 4.1. JSON có điểm mạnh gì?

JSON phổ biến, dễ đọc trong log và có hệ sinh thái tooling lớn. Thêm field optional có thể tương thích với consumer bỏ qua trường lạ. Tuy nhiên, một consumer dùng parser strict, enum exhaustive hoặc validation quá chặt vẫn có thể bị phá bởi thay đổi tưởng như chỉ thêm field.

Các điểm cần lưu ý:

- Không tự động chuyển tiền tệ sang kiểu floating point thiếu chính xác khi biểu diễn giá trị cần chính xác tuyệt đối.
- Quy định timezone/timestamp rõ ràng; ưu tiên ISO-8601 có offset hoặc UTC theo contract.
- Phân biệt trường **không xuất hiện**, trường bằng **null**, và trường bằng giá trị mặc định.
- Quy định tên field, casing, enum và xử lý trường không biết.
- Tránh object graph lồng nhau quá sâu gây tốn bộ nhớ và có thể lỗi parser.
- Không serialize toàn bộ entity persistence trực tiếp ra API nếu kéo theo quan hệ, dữ liệu nhạy cảm hoặc lazy-loading ngoài ý muốn.

### 4.2. Protocol Buffers

Ví dụ một thông điệp gRPC:

~~~proto
syntax = "proto3";

package orders.v1;

message OrderCreated {
  string event_id = 1;
  string order_id = 2;
  int64 total_minor = 3;
  string currency = 4;
  repeated LineItem items = 5;
}

message LineItem {
  string sku = 1;
  int32 quantity = 2;
  int64 unit_price_minor = 3;
}
~~~

Protobuf sử dụng field number và wire type để định nghĩa dữ liệu. Không tùy tiện tái sử dụng field number cũ sau khi xóa; cần dùng reserved khi loại bỏ một field theo thiết kế schema. Trường mới phải xét behavior của consumer cũ và quy tắc default/presence. Protobuf giúp loại bỏ tên field lặp trong mỗi message, nhưng vẫn cần kiểm thử kích thước với dữ liệu thực tế; một chuỗi rất dài hoặc bytes ảnh lớn vẫn chiếm không gian đáng kể.

### 4.3. Avro và schema registry

Với Kafka event streaming, Avro thường đi cùng schema registry hoặc cơ chế quản lý schema. Producer ghi dữ liệu theo một writer schema; consumer cần có khả năng đọc phiên bản dữ liệu tương ứng. Schema registry hỗ trợ kiểm tra tính tương thích cấu trúc theo chính sách, nhưng không tự bảo đảm các thay đổi ngữ nghĩa như đổi đơn vị tiền hoặc đổi cách hiểu enum là an toàn.

Các nguyên tắc chung:

1. Gắn schema version/revision rõ ràng với topic/event.
2. Kiểm tra consumer cũ đọc dữ liệu mới nếu có thể nhận.
3. Kiểm tra consumer mới đọc dữ liệu lịch sử nếu có replay.
4. Bổ sung default/nullable có chủ đích, không đổi ý nghĩa field.
5. Khi breaking change thực sự, dùng versioned event/adapter hoặc kế hoạch migrate rõ ràng.

## 5. Khi nào format nhị phân thực sự có lợi?

Giả sử có 100.000 event/giây, mỗi event JSON chứa nhiều key name lặp. Biểu diễn nhị phân dựa trên schema có thể giảm băng thông và chi phí parse, nhưng cần đo mức tiết kiệm thực tế.

Khi chọn định dạng, hãy hỏi:

- Các client có hỗ trợ format không hay cần proxy chuyển đổi?
- Một service sai schema version sẽ báo lỗi có chẩn đoán được không?
- Khả năng tiến hóa schema quan trọng đến mức nào?
- Có cần con người đọc payload trực tiếp trong quá trình điều tra sự cố không?
- Có dữ liệu tùy chọn, polymorphic hoặc field có thể biến động mạnh không?
- Có library/tooling, generator và test compatibility đáng tin cậy không?

Đổi từ JSON sang Protobuf chỉ để tiết kiệm vài trăm byte ở một endpoint 1 request/giây có thể tạo chi phí duy trì lớn hơn lợi ích. Ngược lại, với streaming lưu lượng lớn, tiết kiệm vài chục byte mỗi message có thể thành khoản đáng kể.

## 6. Compression: giảm bytes để đổi lấy CPU và bộ nhớ

Nén thường có hai bước: compressor nhận serialized bytes và sinh ra compressed bytes; decompressor tạo lại serialized bytes ở đầu nhận. Có thể đo tỷ lệ nén theo hai cách:

~~~text
Compression ratio = Original_bytes / Compressed_bytes

Savings (%) = (Original_bytes - Compressed_bytes)
              / Original_bytes × 100
~~~

Ví dụ 100 KB giảm còn 25 KB:

~~~text
Compression ratio = 100 / 25 = 4:1
Savings = (100 - 25) / 100 × 100 = 75%
~~~

Đây chỉ là ví dụ tính toán. Tỷ lệ thực tế phụ thuộc dữ liệu. Văn bản JSON nhiều key lặp thường nén tốt; dữ liệu đã nén như JPEG, PNG, ZIP hoặc ciphertext thường khó nén thêm đáng kể và đôi khi còn tăng kích thước vì header của codec.

### 6.1. So sánh các codec phổ biến

| Codec | Đặc điểm thường gặp | Ngữ cảnh sử dụng |
|---|---|---|
| gzip / DEFLATE | Phổ biến, hỗ trợ HTTP rộng, mức nén có thể điều chỉnh | JSON/HTML/text qua HTTP |
| Brotli | Hiệu quả tốt với nhiều loại nội dung web, đặc biệt nội dung tĩnh | Phân phối tài nguyên web khi client/proxy hỗ trợ |
| Zstandard (zstd) | Cân bằng tốc độ và tỷ lệ nén, có các level khác nhau | Streaming, file/data pipeline, một số broker |
| Snappy | Ưu tiên encode/decode nhanh, tỷ lệ nén thường thấp hơn codec nén mạnh | Event/log/batch throughput cao |
| LZ4 | Tốc độ cao, phù hợp dữ liệu cần giải nén nhanh | Streaming/cache/storage tùy hỗ trợ |
| Không nén | Không có chi phí codec, payload có thể lớn hơn | Message nhỏ, dữ liệu nén sẵn, CPU bottleneck |

Bảng phản ánh xu hướng khái quát, không xếp hạng tuyệt đối. Với codec nào cũng cần đo trên dataset đại diện, cùng cấu hình level, cùng phần cứng và cùng tỷ lệ request lớn/nhỏ.

### 6.2. Compression level

Nhiều codec cho phép điều chỉnh độ mạnh nén. Mức nén cao thường tốn CPU hơn và có thể tăng thời gian chờ trước khi gửi bytes. Lợi ích kích thước có thể giảm dần khi tăng level.

Nếu một service xử lý request nhạy latency, mức nén vừa phải có thể hợp lý hơn mức mạnh nhất. Nếu tạo snapshot lớn một lần và truyền qua mạng chậm, nén mạnh có thể đáng giá. Cần xem cả **thời gian compress** lẫn **decompress**, đặc biệt khi số consumer lớn.

## 7. Tổng latency: nén có làm nhanh hơn không?

Có thể phân rã gần đúng:

~~~text
End-to-end time
≈ serialize
 + compress
 + network transport
 + decompress
 + deserialize
 + queueing
 + application processing
~~~

Không phải mọi bước đều tuần tự tuyệt đối: stream có thể truyền và giải nén từng phần, transport có thể pipeline, nhưng mô hình trên giúp định vị chi phí.

Ví dụ minh họa:

| Thành phần | Không nén | Nén |
|---|---:|---:|
| Serialize | 1 ms | 1 ms |
| Compress | 0 ms | 4 ms |
| Network | 14 ms | 3 ms |
| Decompress | 0 ms | 2 ms |
| Deserialize | 2 ms | 2 ms |
| Tổng các bước liệt kê | 17 ms | 12 ms |

Ở đường truyền này, nén có lợi. Nhưng với mạng nội bộ rất nhanh, thời gian network chưa nén có thể chỉ 2 ms, làm tổng thời gian nén lớn hơn. Các số liệu chỉ là **giả định để giải thích**, không phải benchmark.

Cần chú ý latency p95/p99: một payload lớn hoặc CPU spike có thể làm tail latency tăng dù throughput trung bình cải thiện.

### 7.1. Nén với payload rất nhỏ

Một JSON 60 byte có thể thành 80 byte khi bọc vào định dạng nén có header và metadata. Chi phí khởi tạo codec cũng đáng kể so với thời gian gửi. Vì vậy, nhiều stack có khái niệm **minimum response size** hoặc chỉ nén khi vượt ngưỡng.

Ngưỡng hợp lý phải dựa vào phân bố kích thước thật. Có thể bắt đầu bằng việc đo bucket: dưới 1 KiB, 1–8 KiB, 8–64 KiB, 64 KiB–1 MiB, trên 1 MiB. Sau đó kiểm chứng CPU, ratio và latency cho mỗi bucket.

## 8. Nén trên HTTP: Content-Encoding và Accept-Encoding

Với HTTP, hai header thường gặp:

- **Accept-Encoding:** phía nhận công bố các content codings mà họ chấp nhận cho response, ví dụ gzip.
- **Content-Encoding:** phía gửi thông báo body đã được mã hóa bằng codec nào.

Ví dụ:

~~~http
GET /api/catalog HTTP/1.1
Host: catalog.internal
Accept-Encoding: gzip, br
~~~

Server có thể trả:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Content-Encoding: gzip
Vary: Accept-Encoding

[binary gzip body]
~~~

Body thực tế là bytes nén, dù ví dụ trình bày dưới dạng ký hiệu. Client phải biết giải nén trước khi parse JSON.

### 8.1. Những quy tắc triển khai

1. Server chỉ chọn encoding mà client và đường truyền hỗ trợ.
2. Khi không thể nén phù hợp, trả response không nén nếu contract và negotiation cho phép.
3. Cấu hình proxy/CDN/gateway nhất quán; tránh nén cùng payload hai lần không cần thiết.
4. Đối với nội dung cache theo encoding, cần thiết kế cache key và header Vary chính xác.
5. Đừng áp dụng gzip mù cho ảnh/video/file đã nén.
6. Khi đọc request nén, server phải hỗ trợ rõ Content-Encoding và giới hạn kích thước **sau khi giải nén**.
7. Kiểm tra Content-Length và giới hạn request trên từng proxy, vì kích thước wire và decoded có thể khác nhau.
8. Khi streaming, xem codec có làm tăng buffering và chậm byte đầu tiên không.

**Lưu ý:** bật response compression trên server không có nghĩa server tự động chấp nhận request body nén. Đây là hai tính năng khác nhau; phải kiểm chứng framework, filter và gateway đang dùng.

### 8.2. Cấu hình ví dụ với Spring Boot

Một cấu hình có thể dùng trong ứng dụng Spring Boot hỗ trợ server response compression:

~~~yaml
server:
  compression:
    enabled: true
    min-response-size: 2KB
    mime-types:
      - application/json
      - application/xml
      - text/plain
      - text/html
~~~

Ngưỡng 2 KB chỉ là lựa chọn minh họa. Cách áp dụng thực tế phụ thuộc web stack, phiên bản server/container, client negotiation và proxy phía trước. Cần kiểm tra header và số byte nhận thực tế sau khi cấu hình. Không bật nén response rồi mặc nhiên kết luận ứng dụng nhanh hơn.

### 8.3. Nén ở gateway hay tại service?

Nén tại gateway có thể giảm băng thông Internet và giữ logic ứng dụng đơn giản; nén tại service có thể giảm lưu lượng giữa các service nếu network nội bộ là nút thắt. Đổi lại, nếu proxy giải nén rồi service nén lại, tổng CPU có thể tăng mà không giảm toàn bộ quãng đường truyền.

Sơ đồ cần xem:

~~~text
Client <--(compressed?)--> Gateway <--(compressed?)--> Service
                                 |
                                 +--> downstream service
~~~

Phải đo **từng hop**. Một response được nén tốt trên hop client–gateway chưa chắc tiết kiệm băng thông trong mạng giữa gateway và backend.

## 9. Nén trong gRPC

gRPC thường dùng Protocol Buffers cho payload, nhưng codec serializer và compression là hai bước khác nhau. Một protobuf message nhỏ có thể không cần nén; message lớn vẫn có thể nén nếu phía gửi và nhận hỗ trợ codec tương ứng.

Cần xét:

- Compression method được peer/server hỗ trợ và negotiation phù hợp.
- Chi phí compression/decompression trên request/response hoặc streaming message.
- Giới hạn kích thước message trên cả sender và receiver.
- Deadline, flow control và backpressure của stream.
- Sự khác nhau giữa payload protobuf gốc, compressed message và các frame của HTTP/2.

**Không nhầm** khả năng truyền message gRPC lớn với quyền dùng vô hạn bộ nhớ; nhiều implementation có default message size limit hoặc cơ chế bảo vệ. Nếu gửi blob vài trăm MB, thường nên cân nhắc cơ chế stream hoặc object storage được quản lý riêng.

## 10. Nén trên Kafka và các message broker

Kafka có cơ chế nén batch record ở producer và hệ sinh thái codec tùy phiên bản client/broker. Nén các record có mẫu lặp lại trong batch thường hiệu quả hơn nén từng record rất nhỏ độc lập.

Một producer configuration minh họa:

~~~properties
# Minh họa; codec cần được hỗ trợ bởi Kafka client/broker đang chạy
compression.type=zstd

# Số byte mục tiêu producer gom thành một batch theo partition
batch.size=65536

# Thời gian chờ tối đa để gom thêm record vào batch, đơn vị mili giây
linger.ms=5
~~~

Giá trị trên là ví dụ, không phải cấu hình tối ưu chung. Kafka có nhiều giới hạn ở producer, broker, topic, replica fetch và consumer fetch. Nếu một record quá lớn, tăng một tham số riêng lẻ thường không đủ; cần xem toàn bộ đường ghi/đọc và ảnh hưởng đến memory, disk, replication, rebalance.

### 10.1. Batching và nén

Batching gom nhiều record thành nhóm lớn hơn để tối ưu transport và compression. Tuy nhiên, tăng linger/batch target có thể tăng độ trễ chờ gom dữ liệu ở lưu lượng thấp. Khi tải cao, batch có thể đầy trước khi hết thời gian chờ.

Trade-off:

| Tăng yếu tố | Lợi ích tiềm năng | Rủi ro |
|---|---|---|
| batch.size | Nén tốt hơn, ít request hơn | Bộ nhớ producer tăng; không bảo đảm batch luôn đầy |
| linger.ms | Gom thêm record để cải thiện throughput | Tăng latency ở traffic thấp |
| Compression mạnh hơn | Ít byte qua mạng/broker | CPU cao, ảnh hưởng tail latency |
| Số partition | Tăng song song khi workload phù hợp | Overhead broker/consumer và ordering phức tạp |
| Message lớn hơn | Ít message hơn khi gộp | Retry, memory, replication và xử lý lỗi nặng hơn |

### 10.2. Khác biệt giữa record, batch và consumer

Giới hạn kích thước record/batch của Kafka không đơn giản là độ dài của một object Java. Có thể có overhead của record format, headers, keys, serialized values và compression. Consumer vẫn cần đủ khả năng fetch, giải nén và deserialize dữ liệu khi batch lớn.

Nếu một event có payload vài chục MB, đặt mặc định vào Kafka không phải cách tốt chỉ vì tăng limit được. Message lớn có thể kéo dài replication, tăng memory pressure và làm chậm những event nhỏ khác trong cùng pipeline.

### 10.3. RabbitMQ và các broker khác

Các message broker khác nhau về limit, framing, ack, TTL và cơ chế truyền nội dung. Không thể áp dụng nguyên xi config Kafka sang RabbitMQ hoặc cloud queue. Dù dùng broker nào, cần khảo sát:

- Message size limit và cách broker xử lý khi vượt ngưỡng.
- Policy retry, DLQ, delivery guarantee.
- Có nén sẵn ở transport/broker hay payload tự nén.
- Chi phí giải nén với nhiều consumer.
- Quan sát backlog theo **số lượng** và **tổng số byte**.
- Cơ chế chunk/reassemble có giữ được idempotency, ordering và timeout hay không.

## 11. Lựa chọn kích thước thông điệp

"Message càng nhỏ càng tốt" không phải quy tắc đầy đủ. Message quá nhỏ tạo nhiều header, round trip, per-message overhead và số lần ack. Message quá lớn tạo memory spike, trễ xử lý, khó retry và rủi ro vượt limit.

Cần chọn **granularity** phù hợp với đơn vị nghiệp vụ:

- **Một business event:** mô tả một sự kiện đã xảy ra với dữ liệu cần thiết cho consumer.
- **Một command:** yêu cầu thực hiện một thao tác có danh tính và kết quả kiểm chứng được.
- **Một batch:** gom nhiều phần tử để xử lý hiệu quả khi có thể tách lỗi từng phần hoặc retry an toàn.
- **Một stream:** truyền liên tục có flow control khi tập dữ liệu lớn.
- **Một reference:** thông điệp nhỏ chứa ID/URI đến blob đã lưu ở nơi phù hợp hơn.

### 11.1. Cần có ngân sách kích thước

Không có một con số byte chuẩn áp dụng cho mọi Microservice. Nhóm nên quy định ngân sách theo *boundary*:

| Boundary | Câu hỏi |
|---|---|
| Public HTTP API | Client/mobile có băng thông yếu không? Gateway/CDN giới hạn body bao nhiêu? |
| Service-to-service HTTP/gRPC | Độ trễ nội bộ, memory, deadline và retry thế nào? |
| Event broker | Producer, broker, consumer có giới hạn byte/batch nào? |
| Cache | Value lớn có gây eviction/hot key/network amplification không? |
| Object storage | Có phù hợp cho blob lớn, checksum và quyền truy cập không? |
| Log/trace | Có tránh ghi payload lớn hoặc dữ liệu nhạy cảm vào observability không? |

Một nguyên tắc thiết kế là nêu rõ **p50, p95, p99 và maximum payload size**, cùng hành vi khi vượt ngưỡng. Chỉ dùng trung bình có thể bỏ sót một nhóm payload cực lớn gây OOM hoặc timeout.

### 11.2. Sự khác nhau giữa giá trị trung bình và đuôi phân bố

Giả sử 99% event nhỏ hơn 4 KiB nhưng 1% event chứa danh sách 10.000 item. Average có thể vẫn chấp nhận được, song những event lớn gây pause GC và tạo độ trễ ở consumer. Vì vậy, dashboard cần histogram kích thước theo endpoint/event type, không chỉ tổng băng thông.

## 12. Batching: gộp có chủ đích

Ví dụ Inventory Service nhận 1.000 request cập nhật tồn kho, mỗi request chỉ gồm một SKU và delta. Nếu giao thức/semantics hỗ trợ, batch 100 item có thể giảm số lần round trip so với 1.000 request độc lập.

Request minh họa:

~~~json
{
  "batchId": "inventory-batch-123",
  "updates": [
    {"sku": "SKU-A", "delta": -1},
    {"sku": "SKU-B", "delta": 3}
  ]
}
~~~

Trước khi batch, phải quyết định:

1. Batch là **atomic** (thất bại một item thì rollback toàn bộ) hay chấp nhận **partial success**?
2. Nếu retry, có thể áp dụng lại item thành công không?
3. Có cần giữ ordering giữa các update của cùng SKU không?
4. Batch quá lớn được chia ở client hay server? Giới hạn item và byte là bao nhiêu?
5. Nếu 1 item mất nhiều thời gian, có làm cả batch bị timeout không?
6. Cách trả lỗi có liên kết với từng item không?

Batch cải thiện throughput khi overhead mỗi lần gọi đáng kể, nhưng không nhất thiết phù hợp với API cần latency thấp cho từng thao tác.

## 13. Pagination, filtering và projection cho API

Một lỗi phổ biến là endpoint GET /orders trả toàn bộ lịch sử đặt hàng của khách trong một response, rồi nhóm cố nén JSON để xử lý. Nén có thể giảm bytes nhưng không loại bỏ việc đọc, serialize và giữ hàng nghìn entity trong heap.

Cách tốt hơn:

- **Pagination:** giới hạn số bản ghi và hỗ trợ lấy trang tiếp theo.
- **Cursor-based pagination:** hữu ích với tập dữ liệu biến động, nếu cần thứ tự ổn định.
- **Filtering:** chỉ lấy trạng thái, thời gian hoặc loại dữ liệu thực sự cần.
- **Field projection:** chỉ trả những trường client sử dụng.
- **Aggregation endpoint:** trả kết quả tổng hợp thay vì toàn bộ bản ghi nếu UI chỉ hiển thị số.
- **Streaming:** truyền từng phần khi cần xuất dữ liệu lớn.

Ví dụ:

~~~http
GET /orders?status=PAID&limit=50&cursor=next-token
~~~

Response nên có danh sách tối đa số item đã thỏa thuận và metadata/cursor. Cursor phải được validate, bảo vệ khỏi sửa đổi không hợp lệ khi cần, và không làm lộ cấu trúc dữ liệu nội bộ nhạy cảm.

### 13.1. Tránh vấn đề N+1

Một response 2 KB vẫn có thể tốn 2 giây nếu để tạo nó service gọi database 100 lần. Tối ưu payload cần đi cùng tối ưu truy vấn, cache và số lời gọi downstream. Kích thước nhỏ không đồng nghĩa xử lý rẻ.

## 14. Large payload: dùng object storage reference

Với ảnh, video, báo cáo PDF hoặc file xuất dữ liệu lớn, thường phù hợp hơn nếu lưu blob vào object storage rồi gửi metadata qua API/event.

~~~text
Producer
   |
   | 1. Upload object + checksum
   v
Object Storage
   ^
   |
   | 3. Download when authorized
   |
Consumer <--- 2. Event { objectId, version, size, checksum, type }
~~~

Ví dụ event tham chiếu:

~~~json
{
  "eventId": "export-ready-123",
  "eventType": "ReportReady",
  "reportId": "report-123",
  "objectKey": "reports/report-123/v2.csv.gz",
  "objectVersion": "v2",
  "contentType": "text/csv",
  "compressed": true,
  "sizeBytes": 5823451,
  "sha256": "<checksum-value>"
}
~~~

Các trường là minh họa. Consumer cần quyền đọc object, xác thực checksum, theo dõi version và thực hiện retry nếu upload chưa hiển thị hoặc đã hết quyền. Đừng đưa URL công khai lâu dài chứa dữ liệu nhạy cảm vào message; dùng cơ chế cấp quyền có hạn và đúng danh tính.

### 14.1. Lifecycle của object tham chiếu

- Producer phải ghi object thành công rồi mới phát sự kiện phù hợp, hoặc có outbox/quy trình bù trừ khi phát event thất bại.
- Object phải còn tồn tại đủ lâu cho retry/replay/consumer chậm.
- Event có thể bị xử lý lại; checksum và version giúp tránh đọc nhầm nội dung.
- Khi object hết hạn, consumer cần báo lỗi có thể chẩn đoán và chính sách retry rõ ràng.
- Cleanup object phải xét retention, audit và trạng thái các consumer còn cần dữ liệu.
- Nếu object chứa dữ liệu nhạy cảm, phải có encryption, authorization và logging truy cập.

## 15. Chunking và streaming: không phải giải pháp miễn phí

Nếu bắt buộc chuyển một payload lớn qua message broker, có thể chia thành nhiều chunk nhỏ:

~~~text
File 100 MB
   |
   +--> Chunk 1: {jobId, index=0, count=100, checksum}
   +--> Chunk 2: {jobId, index=1, count=100, checksum}
   ...
   +--> Chunk 100
~~~

Nhưng consumer phải giải quyết:

- Chunk thiếu hoặc đến trễ.
- Chunk trùng do retry.
- Thứ tự không bảo đảm theo mọi cấu hình partition/queue.
- Thời gian giữ state để lắp lại và giới hạn memory/disk.
- Kiểm tra integrity của từng chunk và toàn bộ dữ liệu.
- Timeout, DLQ và cleanup job chưa hoàn tất.
- Mối quan hệ giữa chunk và version của dữ liệu.

Khi yêu cầu là tải file hoặc truyền luồng byte lớn, object storage hoặc giao thức streaming có flow control thường đơn giản hơn tự thiết kế protocol chunking trên queue. Nếu dùng stream, vẫn cần xử lý backpressure và giới hạn số byte đồng thời.

## 16. CPU, allocation và garbage collection

Nén và serialize không chỉ dùng CPU. Chúng có thể tạo byte array, string, buffer và object trung gian.

Một luồng xử lý chưa tối ưu:

~~~text
Object graph
   -> JSON String
   -> UTF-8 byte[]
   -> gzip byte[]
   -> HTTP client buffer
   -> TLS/network buffer
~~~

Ở đường xử lý này, có thể tồn tại đồng thời nhiều bản sao dữ liệu trong heap. Với hàng trăm request lớn song song, memory spike và GC pressure có thể đáng kể.

Một số cách tối ưu:

- Dùng streaming serializer/parser khi payload lớn và thư viện hỗ trợ.
- Tránh chuyển qua String rồi về byte[] không cần thiết.
- Hạn chế log toàn bộ request/response hoặc event lớn.
- Giới hạn concurrency của compression và số message decode đồng thời.
- Kiểm soát buffer pool để không giữ memory quá lâu khi traffic giảm.
- Kiểm tra heap, direct memory, thread stacks và memory ngoài heap theo container limit.
- Thử nghiệm với payload đại diện và quan sát GC pause, allocation rate và RSS, không chỉ heap committed.

**Lưu ý:** streaming không loại bỏ mọi buffering. Một số codec cần gom dữ liệu trước khi đạt tỷ lệ nén tốt, và thư viện/proxy có thể buffer toàn bộ body. Cần xác minh thực tế.

## 17. Bảo mật khi deserialize và giải nén

Payload nhận từ mạng là dữ liệu không tin cậy, kể cả khi xuất phát từ dịch vụ nội bộ. Cần giới hạn ở nhiều tầng:

1. **Compressed byte limit:** chặn request/frame vượt ngưỡng trước hoặc trong khi nhận.
2. **Decompressed byte limit:** tránh một payload nén rất nhỏ bung thành hàng GB dữ liệu.
3. **Tỷ lệ nén bất thường:** cảnh báo hoặc chặn khi decompressed/compressed ratio vượt ngưỡng phù hợp.
4. **Schema/field validation:** chặn kiểu dữ liệu, độ sâu, array length, số item và string quá dài.
5. **Timeout và CPU budget:** tránh request độc chiếm CPU để decompress/parse.
6. **Allocation/concurrency limit:** tránh nhiều payload lớn cùng giải nén gây OOM.
7. **Trusted serializer:** không deserialize object native Java từ nguồn không tin cậy bằng cơ chế cho phép kích hoạt gadget/class bất kỳ.
8. **Content type/encoding validation:** không tin mù vào Content-Encoding hoặc declared schema version.
9. **Quản lý thông tin nhạy cảm:** không đưa secret vào log/body dump, thiết kế auth và encryption phù hợp.

### 17.1. Decompression bomb

Giả sử attacker gửi 10 KB dữ liệu nén nhưng nội dung giải nén vượt 500 MB. Một server chỉ kiểm tra Content-Length 10 KB rồi giải nén toàn bộ vào RAM có thể bị mất khả năng phục vụ.

Biện pháp là **giải nén theo stream có bộ đếm byte và giới hạn cứng**, kết hợp timeout và giới hạn concurrency. Không chỉ dựa vào số byte nén hoặc tin header kích thước do client cung cấp.

### 17.2. Nén và thông tin nhạy cảm

Trong một số mô hình tấn công side-channel, kích thước ciphertext thay đổi theo nội dung nén có thể tiết lộ thông tin khi payload chứa secret trộn với đầu vào có thể bị attacker thao túng. Đây là lý do các hệ thống cần xem xét kỹ việc nén phản hồi có dữ liệu bí mật và phần dữ liệu do người dùng kiểm soát trong cùng compression context. Không được đánh đổi bảo mật để lấy tỷ lệ nén cao hơn một cách tự động.

## 18. Một số yêu cầu về tương thích

Đổi JSON sang Protobuf hoặc thêm compression có thể làm hỏng consumer nếu chưa thống nhất contract:

- Client cũ chỉ hỗ trợ JSON nhưng service đột ngột trả protobuf.
- Producer nén event payload thủ công nhưng consumer vẫn parse như JSON gốc.
- Gateway giải nén response nhưng giữ nhầm Content-Encoding header.
- Consumer nhận enum mới mà code switch không có nhánh xử lý an toàn.
- Một request được decode qua nhiều lớp nhưng chỉ một lớp áp dụng byte limit.
- Schema registry PASS nhưng ngữ nghĩa currency/amount thay đổi.

Đối với HTTP, content negotiation và versioned endpoint/media type có thể giúp chuyển đổi. Đối với event, cần schema evolution và kế hoạch consumer migration. Chuyển format nên có ma trận active producer/consumer versions, contract tests, khả năng rollback và telemetry.

### 18.1. Tính xác định của serialization

Nếu payload được dùng để ký, hash, deduplicate hoặc làm idempotency key, cần quy định byte representation chuẩn. JSON object key order hoặc whitespace khác nhau có thể làm hai payload cùng nghĩa có hash khác nhau. Không giả định serialize object bằng hai thư viện sẽ tạo cùng byte. Tùy nhu cầu, dùng canonical serialization hoặc tính hash theo trường nghiệp vụ đã chuẩn hóa.

## 19. Thiết kế một thí nghiệm nén

Một bài benchmark tốt phải dùng tập payload đại diện:

- Event nhỏ nhiều lần, ví dụ 100–500 B.
- JSON trung bình, ví dụ 5–20 KiB.
- JSON có danh sách dài và field lặp, ví dụ 100–500 KiB.
- Payload đã nén sẵn hoặc entropy cao.
- Payload chứa tiếng Việt/Unicode.
- Các trường hợp biên: string dài, array lớn, null/missing và nested object.

Ghi nhận ít nhất:

| Chỉ số | Ý nghĩa |
|---|---|
| Original bytes | Kích thước trước compression |
| Compressed bytes | Kích thước sau compression |
| Ratio / savings | Hiệu quả nén |
| Serialize/deserialize latency | Chi phí định dạng |
| Compress/decompress latency | Chi phí codec |
| End-to-end p50/p95/p99 | Tác động người dùng và tail latency |
| CPU utilization | Chi phí compute toàn hệ thống |
| Allocation/GC | Tác động bộ nhớ tạm |
| Throughput và error rate | Năng lực khi cùng SLO |
| Broker lag/network egress | Tác động downstream và chi phí |

Không nên dùng một payload cố định lặp đi lặp lại duy nhất để suy ra hiệu quả production; data entropy, kích thước và distribution thực tế mới quyết định.

### 19.1. Quy trình đo

1. Chuẩn bị dataset có phân bố kích thước/kiểu dữ liệu giống production nhưng không chứa thông tin nhạy cảm.
2. Dùng cùng phần cứng, JVM, dataset, codec level và concurrency cho các lựa chọn.
3. Warm up nếu benchmark trong JVM, tránh lấy kết quả JIT cold start làm hiệu suất ổn định.
4. Đo riêng serialize, compress, transport, decompress, deserialize và end-to-end.
5. Quan sát cả khi CPU rảnh và khi gần mức bão hòa.
6. Lặp lại ở nhiều mức tải, có khoảng tin cậy hoặc ít nhất trung vị và phân bố.
7. Đặt tiêu chí thành công bằng SLO/chi phí chứ không chỉ compression ratio.
8. Kiểm thử đường lỗi, retry, payload quá lớn và fallback no-compression.

### 19.2. Ví dụ bảng kết quả cần điền

| Dạng payload | Format | Codec | Raw bytes | Wire bytes | p95 latency | CPU% | Kết luận |
|---|---|---|---:|---:|---:|---:|---|
| Small event | JSON | None | Đo thực tế | Đo thực tế | Đo | Đo | Theo số đo |
| Small event | JSON | gzip | Đo thực tế | Đo thực tế | Đo | Đo | Theo số đo |
| Order batch | JSON | gzip | Đo thực tế | Đo thực tế | Đo | Đo | Theo số đo |
| Order batch | Protobuf | None | Đo thực tế | Đo thực tế | Đo | Đo | Theo số đo |
| Order batch | Protobuf | zstd nếu hỗ trợ | Đo thực tế | Đo thực tế | Đo | Đo | Theo số đo |

Trước khi so sánh, phải bảo đảm các biến thể mang **cùng ý nghĩa nghiệp vụ** và được validate bằng nội dung decode lại.

## 20. Ví dụ Java: đo byte và gzip round trip

Đoạn Java sau minh họa trực tiếp việc nén một chuỗi JSON đã serialize, đo kích thước và xác nhận dữ liệu giải nén trùng tuyệt đối với đầu vào.

~~~java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;
import java.util.zip.GZIPInputStream;
import java.util.zip.GZIPOutputStream;

public class CompressionDemo {

    static byte[] gzip(byte[] input) throws IOException {
        ByteArrayOutputStream out = new ByteArrayOutputStream();
        try (GZIPOutputStream zip = new GZIPOutputStream(out)) {
            zip.write(input);
        }
        return out.toByteArray();
    }

    static byte[] gunzip(byte[] encoded, int maxBytes)
            throws IOException {

        ByteArrayOutputStream out = new ByteArrayOutputStream();
        byte[] buffer = new byte[8192];

        try (GZIPInputStream zip =
                 new GZIPInputStream(new ByteArrayInputStream(encoded))) {
            int read;
            int total = 0;

            while ((read = zip.read(buffer)) != -1) {
                total += read;
                if (total > maxBytes) {
                    throw new IOException("Decompressed size limit exceeded");
                }
                out.write(buffer, 0, read);
            }
        }

        return out.toByteArray();
    }

    public static void main(String[] args) throws Exception {
        String json = """
            {
              "eventType": "OrderCreated",
              "orderId": "order-123",
              "customerId": "customer-456",
              "currency": "VND"
            }
            """;

        byte[] raw = json.getBytes(StandardCharsets.UTF_8);

        long start = System.nanoTime();
        byte[] compressed = gzip(raw);
        long encodedNs = System.nanoTime() - start;

        byte[] restored = gunzip(compressed, 1024 * 1024);
        boolean same = Arrays.equals(raw, restored);

        System.out.println("Raw: " + raw.length + " bytes");
        System.out.println("Compressed: " + compressed.length + " bytes");
        System.out.println("Encode ns: " + encodedNs);
        System.out.println("Round trip exact: " + same);
    }
}
~~~

Ví dụ này dùng Java có hỗ trợ text blocks. Kích thước của JSON mẫu rất nhỏ nên gzip có thể không giảm được bao nhiêu; **đó là kết quả hợp lý**. Đoạn mã không phải microbenchmark chuẩn: thời gian một lần chạy bị ảnh hưởng bởi JIT, allocation và scheduling. Nếu cần kết luận về hiệu năng Java, dùng benchmark có warm-up/iterations phù hợp, chẳng hạn JMH, và đo end-to-end trong dịch vụ thật.

Hàm gunzip dùng byte limit giúp minh họa phòng ngừa giải nén vượt ngân sách. Hệ thống thực tế còn cần giới hạn thời gian, concurrency, input byte, content type và cách xử lý lỗi.

## 21. Ví dụ Java: tránh serialize object graph quá lớn

Một controller có thể vô tình trả toàn bộ danh sách Order và mọi quan hệ:

~~~java
@GetMapping("/orders")
List<OrderEntity> listAllOrders() {
    return orderRepository.findAll();
}
~~~

Đây là ví dụ mẫu anti-pattern trong API có tập dữ liệu lớn. Vấn đề gồm:

- Không phân trang, rủi ro load nhiều row vào heap.
- Entity persistence có thể chứa trường nhạy cảm hoặc quan hệ lồng nhau.
- Serialization có thể kích hoạt lazy loading/N+1 tùy cách ORM hoạt động.
- Thời gian GC và nén tăng mạnh ở peak traffic.
- Response khó retry và không có giới hạn byte đáng tin cậy.

Định hướng phù hợp hơn là trả DTO có trường cần thiết và pagination có ngân sách:

~~~java
record OrderSummary(
    String orderId,
    String status,
    long totalMinor,
    String currency
) {}

record OrderPage(
    List<OrderSummary> items,
    String nextCursor
) {}
~~~

API phải implement query phân trang thực tế, xác định ordering ổn định và giới hạn limit; record ở trên chỉ thể hiện hợp đồng output, không phải toàn bộ mã chạy được.

## 22. Ví dụ xuyên suốt: tối ưu OrderCreated event

Giả sử Order Service hiện phát event JSON 150 KiB do nhúng toàn bộ thông tin sản phẩm, ảnh và thông tin khách hàng. Có 3 consumer:

- Inventory cần orderId, sku, quantity.
- Analytics cần orderId, timestamp, tổng tiền và danh sách item tối thiểu.
- Notification cần orderId, customerId và thông tin để lấy template hoặc sở hữu luồng thông báo.

**Giai đoạn 1 — Định nghĩa nội dung cần thiết**

Cắt các field không được consumer cần hoặc không thuộc responsibility của event. Thông tin có thể thay đổi như mô tả sản phẩm dài cần quyết định là snapshot nghiệp vụ hay reference; ảnh có thể lưu ngoài broker. Sau khi thiết kế event hợp lý, mới đo lại byte.

**Giai đoạn 2 — Đánh giá format**

Giữ JSON nếu các consumer đa dạng và overhead chưa lớn, hoặc cân nhắc Avro/Protobuf với schema registry nếu volume cao và các team có năng lực quản lý schema. Kiểm thử consumer cũ khi thay đổi format; không đổi serializer đột ngột.

**Giai đoạn 3 — Đánh giá compression**

Đo nhóm event nhỏ và event có nhiều item. So sánh no compression, gzip và codec broker hỗ trợ. Nếu dùng Kafka, thử nén theo batch producer và ảnh hưởng của linger/batch size. Không nén thêm các file đã nén.

**Giai đoạn 4 — Chọn giới hạn**

Định nghĩa giới hạn số item trong event, kích thước serialized bytes và hành vi khi order có nhiều item bất thường. Nếu event vượt ngân sách, có thể sử dụng sự kiện tham chiếu tới snapshot dữ liệu nhất quán hoặc workflow xuất dữ liệu riêng, tùy contract consumer.

**Giai đoạn 5 — Kiểm chứng**

Theo dõi broker ingress/egress, producer CPU, consumer decode latency, p99 processing, consumer lag và số lỗi schema/oversize. Kiểm tra retry, duplicate event và replay lịch sử.

**Giai đoạn 6 — Rollout**

Triển khai consumer có khả năng đọc format mới trước khi producer bắt đầu phát, nếu bắt buộc bởi hướng tương thích. Với breaking change, có version/translator và chiến lược sunset rõ ràng. Chỉ gỡ format cũ khi tất cả consumer còn được hỗ trợ đã chuyển.

## 23. Anti-pattern thường gặp

| Anti-pattern | Triệu chứng | Điều chỉnh |
|---|---|---|
| Gzip mọi response dù chỉ vài byte | CPU tăng, payload nhỏ không giảm | Ngưỡng nén theo size và content type |
| Chỉ đo tỷ lệ nén | Codec mạnh có ratio tốt nhưng p99 xấu | Đo end-to-end latency, CPU và SLO |
| Đổi JSON sang Protobuf không có migration | Consumer cũ không deserialize được | Contract/version/canary và fallback rõ |
| Nhúng ảnh/file lớn trong JSON event | Broker lag, retry tốn kém | Object storage reference kèm checksum |
| API trả toàn bộ bảng | OOM, timeout, băng thông lớn | Pagination, filter, DTO/projection |
| Dùng base64 cho binary không cần thiết | Body tăng đáng kể | Truyền binary trực tiếp hoặc reference |
| Bật nén nhiều lần trên cùng payload | Tốn CPU, hiếm khi giảm kích thước | Xác định compression boundary |
| Bỏ qua kích thước sau giải nén | Rủi ro decompression bomb | Byte limit khi stream decode |
| Tăng broker max size liên tục | Memory/replication/retry phình to | Thiết kế lại event hoặc lưu blob ngoài broker |
| Không kiểm soát retry batch | Side effect trùng hoặc bỏ sót item | Idempotency, partial result, correlation |
| Cache payload nhị phân không version | Client cũ đọc sai format | Gắn schema/content type/version vào key |
| Dựa vào average payload | Bỏ sót p99 event rất lớn | Histogram và max guardrail |
| Log nguyên payload | Tăng chi phí và lộ dữ liệu | Log metadata, IDs, sizes, hashes phù hợp |
| Cho rằng serializer nhanh nhất trên mọi workload | Kết luận sai khi shape/size đổi | Benchmark trên dataset đại diện |

## 24. Bộ câu hỏi lựa chọn công nghệ

Khi thiết kế một giao diện giữa hai Microservice, hãy lần lượt trả lời:

1. **Thông điệp chứa gì?** Dữ liệu nào thực sự cần cho nghiệp vụ?
2. **Có thể giảm dữ liệu ngay từ model không?** Projection, DTO, cursor, business event nhỏ?
3. **Số byte và phân bố?** p50/p95/p99/max serialized size là bao nhiêu?
4. **Ai là consumer?** Ngôn ngữ, SDK, schema evolution, yêu cầu debugging?
5. **Đường truyền nào?** HTTP công khai, service-to-service, gRPC, broker, cache?
6. **Giới hạn nào áp dụng?** Proxy, frame, broker, request/response, heap, queue retention?
7. **Đã có codec/format nào?** Tránh chuyển đổi hoặc nén lặp vô ích.
8. **Độ trễ và throughput quan trọng đến đâu?** p99 latency hay tối ưu chi phí mạng?
9. **CPU và memory còn dư không?** Codec mạnh có gây GC hoặc bão hòa CPU?
10. **Có dữ liệu nhạy cảm không?** Auth, logging, compression side channel, encryption?
11. **Khả năng lỗi và retry?** Duplicate, timeout, chunk mất, partial batch?
12. **Có cần rollback/consumer cũ không?** Contract version và rollout order ra sao?

Không cần lựa chọn codec trước khi trả lời được những câu hỏi cơ bản về dữ liệu, giới hạn và nhu cầu người dùng.

## 25. Bài tập thực hành

### Bài tập A — Nhận diện giải pháp

Với mỗi trường hợp, đề xuất ưu tiên thiết kế payload, đổi serializer, bật nén, batching hay object storage:

1. API trả 1.000 order nhưng màn hình chỉ hiển thị 20 order mỗi trang.
2. JSON event 200 byte gửi 100 lần/giây qua mạng nội bộ tốc độ cao.
3. Kafka batch chứa hàng nghìn JSON event có field lặp, broker egress là nút thắt.
4. Producer gửi tệp video MP4 trong event body.
5. Consumer fail do JSON có enum mới dù payload nhỏ.
6. Server OOM khi giải nén request 50 KB thành dữ liệu hàng trăm MB.
7. Mobile client mạng yếu thường tải catalog JSON 500 KB.
8. API đơn hàng hoạt động chậm do truy vấn N+1 mặc dù response đã gzip còn 5 KB.

Giải thích cả **lợi ích** và **rủi ro** cho lựa chọn của mình. Một vài trường hợp không được giải quyết bằng compression.

### Bài tập B — Tính toán tỉ lệ nén

Một payload JSON có 120.000 byte. gzip còn 36.000 byte; zstd còn 30.000 byte. Tính:

~~~text
gzip ratio = 120000 / 36000 = 3.33:1
gzip savings = (120000 - 36000)/120000 = 70%

zstd ratio = 120000 / 30000 = 4:1
zstd savings = (120000 - 30000)/120000 = 75%
~~~

Nếu zstd dùng thêm 8 ms CPU nhưng chỉ giảm thêm 6 KB qua mạng nội bộ nhanh, có chắc zstd tốt hơn gzip về độ trễ không? Không. Cần benchmark end-to-end và tài nguyên trên đúng workload.

### Bài tập C — Thực nghiệm Spring Boot

1. Tạo endpoint trả về danh sách DTO có thể thay đổi số item.
2. Đo response raw bytes và p95 latency khi tắt compression.
3. Bật server response compression với một ngưỡng xác định.
4. Đo qua client có/không có Accept-Encoding phù hợp.
5. So sánh body size, latency, CPU, GC, request count và cache behavior.
6. Thử payload 100 B, 2 KB, 20 KB và 200 KB.
7. Kiểm tra các response có Content-Encoding thích hợp và sau giải nén parse JSON đúng.
8. Thử response chứa ảnh hoặc binary xem có bị nén thừa.
9. Ghi kết quả, không suy đoán chỉ từ code config.

### Bài tập D — Thiết kế event không vượt broker limit

Một service xuất báo cáo 50 MB và muốn thông báo cho ba consumer. Hãy thiết kế event chỉ mang metadata, tham chiếu object, checksum/version, quyền truy cập có hạn, retry, retention và cleanup. Nêu cách consumer phát hiện file thiếu, hết hạn hoặc bị thay đổi sau khi nhận event.

## 26. Checklist triển khai

- [ ] Đã xác định serializer, content type và schema/version cho từng interface.
- [ ] Đã đo byte thực tế sau serialization, compression và transport nếu cần.
- [ ] Có histogram payload p50/p95/p99 và hard maximum.
- [ ] Không chứa field thừa, object graph không giới hạn hoặc blob lớn trong event.
- [ ] Format được chọn phù hợp client, schema evolution và khả năng debug.
- [ ] Contract test kiểm tra cả producer/consumer còn được hỗ trợ.
- [ ] Compression chỉ áp dụng ở tầng và content type có lợi; có ngưỡng cho message nhỏ.
- [ ] Đã đo codec trên dữ liệu đại diện; đánh giá CPU, heap, GC và tail latency.
- [ ] HTTP/gRPC có negotiation/Content-Encoding đúng, bao gồm qua gateway/proxy.
- [ ] Broker config phù hợp producer, topic, replication và consumer; không chỉ tăng một limit.
- [ ] Batching có giới hạn bytes/items và định nghĩa rõ partial success/idempotency.
- [ ] Các payload lớn được phân trang, stream hoặc dùng object storage reference khi phù hợp.
- [ ] Có hard limit cho request nén và dữ liệu sau giải nén; parser validation an toàn.
- [ ] Có timeout, backpressure, rate limiting và memory/concurrency budget.
- [ ] Log/trace không chứa toàn bộ payload nhạy cảm; có metadata kích thước đủ debug.
- [ ] Đã thử payload bất thường, retry, duplicate, chunk thiếu, version cũ và rollback.
- [ ] Đã cập nhật dashboard/alert cho oversize event, latency, CPU và broker lag.
- [ ] Đã đánh giá chi phí băng thông/lưu trữ cùng chi phí compute và vận hành.

## 27. Kết luận

Để tối ưu thông điệp giữa các Microservices, thứ tự tư duy hiệu quả là **giảm dữ liệu không cần thiết → chọn cách biểu diễn phù hợp → chọn granularity truyền → chỉ nén khi đo thấy có lợi → kiểm tra tính tương thích và an toàn**. Tuần tự hóa quyết định cách mô tả dữ liệu; compression quyết định giảm byte với chi phí CPU; thiết kế message size quyết định độ lớn của công việc mà hệ thống phải xử lý, lưu, retry và quan sát.

JSON phù hợp khi cần khả năng đọc và tương thích công cụ rộng; Protobuf hoặc Avro có thể hỗ trợ hệ thống nội bộ/streaming có schema rõ ràng và lưu lượng cao. gzip, zstd, Snappy hay LZ4 đều có ưu điểm trong bối cảnh khác nhau. Không có con số ngưỡng kích thước hoặc codec tối ưu chung cho mọi tổ chức.

Với Microservices, thành công không phải là đạt tỷ lệ nén cao nhất, mà là **giữ đúng hợp đồng nghiệp vụ, đáp ứng SLO về latency và throughput, sử dụng tài nguyên hợp lý và xử lý an toàn khi dữ liệu lớn hoặc bất thường**. Quyết định cuối cùng nên dựa trên phép đo với workload đại diện và có thể kiểm chứng lại sau mỗi thay đổi hệ thống.