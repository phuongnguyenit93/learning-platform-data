# Đánh giá JSON, CBOR và Protobuf theo chi phí mã hóa và kích thước

Định dạng payload ảnh hưởng trực tiếp tới số byte truyền qua mạng, CPU dành cho encode/decode, số object được cấp phát và khả năng tương thích giữa client với server. JSON dễ đọc và có hệ sinh thái rộng; CBOR biểu diễn dữ liệu theo dạng nhị phân nhưng vẫn giữ mô hình dữ liệu linh hoạt; Protobuf dùng schema và field number để tạo payload gọn, phù hợp với contract được quản lý chặt.

Trong module `INTEGRATION_REALTIME_RSOCKET`, client và server có thể trao đổi các payload qua Request-Response, Fire-and-Forget, Request-Stream và Request-Channel. Chọn JSON, CBOR hay Protobuf cần xét toàn bộ workload realtime: payload nhỏ hay lớn, tần suất gửi, số subscriber, khả năng dùng chung schema, browser/native client, CPU, memory và yêu cầu tiến hóa contract. Không có định dạng luôn nhanh nhất hoặc nhỏ nhất trong mọi trường hợp.

## 1. Định dạng dữ liệu ảnh hưởng tới RSocket ở đâu?

RSocket truyền data và metadata trong payload. Trước khi gửi, ứng dụng chuyển DTO hoặc object nghiệp vụ thành bytes; phía nhận giải mã bytes thành kiểu dữ liệu tương ứng. Quá trình này nằm ở tầng codec, bên trên RSocket framing và transport.

```text
Application DTO
      |
      v
Encoder (JSON / CBOR / Protobuf)
      |
      v
Encoded data bytes + RSocket metadata
      |
      v
RSocket frames
      |
      v
TCP hoặc WebSocket
      |
      v
RSocket frames
      |
      v
Decoder (cùng MIME type / schema contract)
      |
      v
Application DTO
```

Định dạng data không thay đổi interaction model. Request-Stream vẫn là một request mở đầu và nhiều response; Request-Channel vẫn trao đổi payload hai chiều. Codec chỉ quyết định cách biểu diễn nội dung của payload.

RSocket SETUP có thông tin MIME type mặc định cho data và metadata của kết nối. Với Spring `RSocketRequester`, `dataMimeType(...)` khai báo MIME type của data; metadata MIME type là một cấu hình riêng. Client và server phải thống nhất MIME type và có codec tương ứng. Không đặt MIME type của data thành JSON/CBOR/Protobuf rồi nhầm nó với MIME type định tuyến hoặc composite metadata.

## 2. JSON: dễ đọc, dễ tích hợp

JSON là định dạng text biểu diễn object, array, string, number, boolean và null. Một payload telemetry có thể trông như sau:

```json
{
  "deviceId": "device-42",
  "sequence": 1200,
  "temperature": 23.5,
  "active": true
}
```

### 2.1. Chi phí mã hóa và kích thước

JSON thường có một số chi phí:

- Tên field được gửi lặp lại trong mỗi message.
- Dấu ngoặc, dấu phẩy, dấu hai chấm và dấu nháy chiếm thêm byte.
- Số được biểu diễn dưới dạng text, cần parse thành kiểu số ở phía nhận.
- Binary data thường phải encode Base64 hoặc một biểu diễn text khác, làm tăng kích thước.
- Decoder phải phân tích cú pháp và ánh xạ tên field vào thuộc tính object.

Với message nhỏ và ít field, phần overhead có thể không đáng kể so với chi phí kết nối, TLS và RSocket framing. Với stream có hàng triệu message lặp cùng cấu trúc, việc gửi tên field ở mỗi message có thể làm tổng byte tăng đáng kể.

### 2.2. Điểm mạnh và giới hạn

| Điểm mạnh | Giới hạn |
|---|---|
| Con người đọc và debug dễ dàng. | Thường lớn hơn định dạng nhị phân tương đương. |
| Hỗ trợ rộng ở browser, Java, mobile và hệ thống bên ngoài. | Parse text và chuyển kiểu có thể tốn CPU. |
| Không bắt buộc có schema compiler. | Contract field/type phải được quản lý bằng quy ước hoặc schema riêng. |
| Dễ tích hợp REST API, log và công cụ quan sát. | Binary data, số nguyên lớn và độ chính xác số cần chú ý. |

JSON thường là lựa chọn tốt khi tính tương thích, khả năng debug và tốc độ phát triển quan trọng hơn việc giảm tối đa từng byte.

### 2.3. Những lưu ý về kiểu dữ liệu

- JavaScript `Number` không biểu diễn chính xác mọi số nguyên lớn hơn `2^53 - 1`. ID hoặc sequence 64-bit cần đi qua browser nên cân nhắc biểu diễn bằng string hoặc quy ước protobuf JSON phù hợp.
- Tiền tệ không nên dùng floating point nhị phân tùy tiện; dùng integer theo đơn vị nhỏ nhất hoặc decimal có quy tắc rõ.
- Phân biệt field bị thiếu, `null`, giá trị mặc định và giá trị rỗng.
- Quy định format timestamp, timezone, enum và naming convention.
- Đặt giới hạn kích thước body, độ sâu object và số phần tử array khi decode dữ liệu không tin cậy.

## 3. CBOR: biểu diễn nhị phân của mô hình dữ liệu linh hoạt

CBOR (Concise Binary Object Representation) biểu diễn các kiểu dữ liệu như integer, floating point, byte string, text string, array, map, boolean và null dưới dạng binary. Nó giữ mô hình dữ liệu tổng quát tương tự JSON nhưng không phải serialize thành text JSON.

Với cùng dữ liệu ví dụ, một map CBOR có thể chứa các key dạng text như `deviceId`, `sequence`, `temperature` và `active`; giá trị số được biểu diễn theo kiểu nhị phân thay vì chuỗi ký tự. CBOR cũng hỗ trợ key dạng integer, nhưng ứng dụng phải thống nhất schema/contract nếu muốn tận dụng cách này.

### 3.1. Chi phí và kích thước

- Integer nhỏ có thể được biểu diễn rất gọn bằng mã hóa độ dài biến thiên.
- Floating point được biểu diễn theo dạng binary; độ dài phụ thuộc kiểu được chọn.
- Byte string mang dữ liệu nhị phân trực tiếp, tránh Base64.
- Map dùng key text vẫn phải gửi tên key, dù encoding của chúng có thể gọn hơn JSON.
- Nếu dùng integer key theo schema, có thể giảm thêm kích thước nhưng giảm tính tự mô tả và khả năng debug.

CBOR thường giảm kích thước so với JSON cho payload có nhiều số, boolean hoặc binary data. Tuy nhiên, kết quả phụ thuộc cấu trúc map, key, kiểu số, thư viện và cấu hình. Không mặc định mọi CBOR message đều nhỏ hơn hoặc encode nhanh hơn JSON.

### 3.2. Điểm mạnh và giới hạn

| Điểm mạnh | Giới hạn |
|---|---|
| Binary, thường gọn hơn JSON cho dữ liệu có cấu trúc. | Khó đọc trực tiếp khi debug. |
| Có byte string native cho dữ liệu nhị phân. | Map key dạng text vẫn tạo overhead lặp lại. |
| Không bắt buộc dùng schema compiler. | Contract và cách xử lý field tùy chọn vẫn cần quy ước. |
| Hỗ trợ nhiều kiểu dữ liệu hơn JSON thuần. | Cần kiểm tra codec hỗ trợ và tính tương thích giữa các client. |

CBOR phù hợp khi cần giảm overhead so với JSON nhưng vẫn muốn giữ mô hình dữ liệu linh hoạt, đặc biệt với thiết bị, gateway hoặc client có payload nhị phân.

## 4. Protobuf: schema-first và wire format gọn

Protocol Buffers (Protobuf) dùng schema `.proto` để định nghĩa message. Mỗi field có số hiệu (field number) và kiểu wire; tên field không được gửi lặp lại trong từng message. Code được sinh từ schema giúp client/server có kiểu dữ liệu rõ ràng.

Ví dụ schema:

```protobuf
syntax = "proto3";

package telemetry.v1;

option java_multiple_files = true;
option java_package = "com.example.telemetry.v1";

message TelemetryReading {
  string device_id = 1;
  int64 sequence = 2;
  double temperature = 3;
  bool active = 4;
  bytes raw_sample = 5;
}
```

Sau khi sinh Java class, ứng dụng tạo message:

```java
TelemetryReading reading = TelemetryReading.newBuilder()
    .setDeviceId("device-42")
    .setSequence(1200L)
    .setTemperature(23.5)
    .setActive(true)
    .setRawSample(ByteString.copyFrom(sampleBytes))
    .build();

byte[] encoded = reading.toByteArray();
TelemetryReading decoded = TelemetryReading.parseFrom(encoded);
```

### 4.1. Vì sao Protobuf thường gọn?

- Field được nhận diện bằng số thay vì tên chuỗi.
- Tag kết hợp field number và wire type.
- Integer có thể dùng varint, nên giá trị nhỏ thường chiếm ít byte.
- String và bytes dùng dạng length-delimited.
- Repeated scalar có thể được mã hóa packed.
- Field mặc định trong proto3 thường được lược bỏ khỏi wire khi không có presence riêng.

Protobuf đặc biệt hiệu quả với message có nhiều field lặp, số nguyên, enum và cấu trúc đã được schema hóa. Tuy nhiên, không phải mọi field đều rất nhỏ: `double`/`fixed64` chiếm 8 byte, `fixed32` chiếm 4 byte, string/bytes cần length prefix, còn nested message cần tag và length. Với message cực nhỏ hoặc schema phức tạp, overhead vẫn cần được đo.

### 4.2. Điểm mạnh và giới hạn

| Điểm mạnh | Giới hạn |
|---|---|
| Wire format thường nhỏ và decode hiệu quả. | Cần quản lý schema và sinh code. |
| Kiểu dữ liệu và contract rõ ràng. | Khó đọc trực tiếp nếu không có schema/tooling. |
| Có quy tắc tương thích schema khi thêm/bỏ field đúng cách. | Thay đổi field number hoặc tái sử dụng field number có thể phá tương thích. |
| Hỗ trợ bytes, repeated, nested message, oneof và enum. | Client browser cần runtime/generated code tương ứng. |

Protobuf phù hợp với service-to-service hoặc hệ thống có nhiều message lặp tần suất cao, schema được quản lý theo version và các team có quy trình code generation.

## 5. So sánh cùng một payload

Giả sử ứng dụng gửi một telemetry record gồm `deviceId`, `sequence`, `temperature`, `active` và `rawSample`.

| Thuộc tính | JSON | CBOR | Protobuf |
|---|---|---|---|
| Tên field trên wire | Có, thường lặp lại | Có nếu dùng text map key; có thể dùng integer key | Không; dùng field number |
| Integer | Text decimal | Binary integer | Varint hoặc fixed-width theo kiểu/schema |
| Floating point | Text decimal | Binary float | `float`/`double` theo wire type |
| Binary data | Thường Base64 | Byte string native | `bytes` length-delimited |
| Schema compiler | Không bắt buộc | Không bắt buộc | Thường có `.proto` và code generation |
| Debug bằng mắt | Dễ | Cần decoder/tool | Cần schema/tool |
| Evolution | Linh hoạt nhưng phụ thuộc contract | Linh hoạt nhưng phụ thuộc contract | Có quy tắc field number/presence/unknown field |
| Tính tương thích browser | Rất rộng | Cần CBOR library | Cần Protobuf runtime/generated code |

Xu hướng thường gặp:

- JSON có kích thước lớn hơn do key và cú pháp text, nhưng có thể nén rất tốt khi key lặp lại.
- CBOR giảm overhead text và hỗ trợ binary native; lợi ích phụ thuộc key và cấu trúc map.
- Protobuf thường rất gọn khi schema có nhiều field với tên dài/lặp lại, integer nhỏ dùng varint, repeated scalar hoặc binary field. Với `double`/`fixed64`, mỗi giá trị vẫn cần 8 byte; CBOR có thể dùng float ngắn hơn nếu giá trị và encoder cho phép, nên không thể mặc định Protobuf nhỏ nhất cho mọi payload numeric.

Đây là xu hướng, không phải kết quả benchmark cố định. Một payload JSON rất nhỏ có thể cạnh tranh với CBOR/Protobuf; một payload JSON nén gzip tốt có thể gần kích thước wire của định dạng nhị phân. Chỉ số quyết định phải đến từ payload thực tế và cấu hình production.

## 6. Cấu hình MIME type và codec trong Spring RSocket

`RSocketRequester.Builder` cho phép cấu hình `RSocketStrategies` và data MIME type. Server cũng cần decoder/encoder tương ứng. MIME type của data phải khớp với định dạng bytes mà hai bên sử dụng.

| Định dạng | MIME type thường dùng | Codec Spring thường gặp |
|---|---|---|
| JSON | `application/json` | `Jackson2JsonEncoder` / `Jackson2JsonDecoder` |
| CBOR | `application/cbor` | `Jackson2CborEncoder` / `Jackson2CborDecoder` |
| Protobuf | `application/x-protobuf` | `ProtobufEncoder` / `ProtobufDecoder` |

Tên class/package và MIME type được hỗ trợ cần được xác nhận theo phiên bản Spring Framework và codec dependency của dự án. Hai phía phải dùng cùng MIME contract; chỉ đổi MIME string mà không đăng ký codec phù hợp sẽ khiến encode/decode thất bại.

### 6.1. JSON

Với Spring Boot có Jackson trên classpath, JSON thường đã được hỗ trợ bởi strategies mặc định:

```java
RSocketRequester requester = RSocketRequester.builder()
    .dataMimeType(MimeTypeUtils.APPLICATION_JSON)
    .connectTcp("rsocket-service", 7000)
    .block();
```

Ví dụ gọi route:

```java
Mono<DeviceStatus> status = requester
    .route("devices.{deviceId}.status.get", deviceId)
    .data(new StatusQuery())
    .retrieveMono(DeviceStatus.class);
```

### 6.2. CBOR

Khi Spring version và dependency hỗ trợ Jackson CBOR codec, đăng ký encoder/decoder và chọn `application/cbor`:

```java
RSocketStrategies cborStrategies = RSocketStrategies.builder()
    .encoders(encoders -> encoders.add(new Jackson2CborEncoder()))
    .decoders(decoders -> decoders.add(new Jackson2CborDecoder()))
    .build();

RSocketRequester requester = RSocketRequester.builder()
    .rsocketStrategies(cborStrategies)
    .dataMimeType(MimeTypeUtils.parseMimeType("application/cbor"))
    .connectTcp("rsocket-service", 7000)
    .block();
```

Phía server cần có CBOR decoder/encoder tương ứng trong `RSocketStrategies`. Nếu dùng WebSocket, chỉ thay transport URI; codec và MIME contract vẫn giữ nguyên.

### 6.3. Protobuf

Với Spring Protobuf codec và class được sinh từ `.proto`, có thể đăng ký encoder/decoder:

```java
RSocketStrategies protobufStrategies = RSocketStrategies.builder()
    .encoders(encoders -> encoders.add(new ProtobufEncoder()))
    .decoders(decoders -> decoders.add(new ProtobufDecoder()))
    .build();

RSocketRequester requester = RSocketRequester.builder()
    .rsocketStrategies(protobufStrategies)
    .dataMimeType(MimeTypeUtils.parseMimeType("application/x-protobuf"))
    .connectTcp("rsocket-service", 7000)
    .block();
```

Ví dụ gửi message đã sinh:

```java
Mono<DeviceAck> ack = requester
    .route("devices.telemetry.publish")
    .data(reading)
    .retrieveMono(DeviceAck.class);
```

Nếu dùng Fire-and-Forget, thay `retrieveMono(...)` bằng `.send()` theo hợp đồng nghiệp vụ. Protobuf encoder/decoder phải nhận đúng kiểu generated message; DTO Java tùy ý không tự động trở thành Protobuf message.

### 6.4. MIME type của metadata là cấu hình riêng

Route của Spring RSocket thường nằm trong routing metadata/composite metadata. Data MIME type `application/json`, `application/cbor` hoặc `application/x-protobuf` không thay đổi MIME type của routing metadata. Khi tùy chỉnh metadata, giữ nguyên contract route/authentication và chỉ đổi data codec nếu có lý do.

## 7. Tiến hóa schema và tương thích client/server

Hiệu năng không phải tiêu chí duy nhất. Một định dạng tốt phải cho phép client và server triển khai khác version mà vẫn hiểu dữ liệu.

### 7.1. JSON

- Thêm field tùy chọn thường dễ tương thích nếu decoder bỏ qua field không biết.
- Xóa hoặc đổi tên field có thể làm client cũ mất dữ liệu hoặc decode sai.
- Thay kiểu dữ liệu, ví dụ number thành string, cần versioning hoặc migration.
- Cần quy định xử lý field thiếu, null, default và unknown property.

### 7.2. CBOR

CBOR không bắt buộc schema, nhưng ứng dụng vẫn cần contract về key, kiểu dữ liệu và ý nghĩa field. Thêm key có thể tương thích nếu decoder bỏ qua key không biết; đổi key hoặc thay kiểu vẫn có thể phá client cũ. Nếu dùng integer key để tiết kiệm byte, cần quản lý bảng key ổn định.

### 7.3. Protobuf

- Không thay đổi field number đã phát hành.
- Không tái sử dụng field number của field đã xóa; dùng `reserved` cho number/name đã bỏ.
- Thêm field mới thường tương thích nếu field được thiết kế optional/default phù hợp.
- Cẩn thận với presence: trong proto3, scalar mặc định có thể không phân biệt được “không gửi” và “gửi giá trị mặc định” nếu không dùng `optional`, `oneof` hoặc message wrapper phù hợp.
- Không đổi kiểu field tùy tiện chỉ vì hai kiểu có wire type tương tự; tương thích wire không đồng nghĩa tương thích ngữ nghĩa.
- Thêm enum value cần xử lý unknown enum ở client cũ.

Ví dụ dành chỗ field đã xóa:

```protobuf
message TelemetryReading {
  string device_id = 1;
  int64 sequence = 2;

  reserved 3;
  reserved "legacy_temperature";

  double temperature_celsius = 4;
}
```

Không tái dùng số `3` cho một field mới. Schema registry hoặc quy trình review `.proto` có thể tự động kiểm tra breaking change trước khi publish.

## 8. Compression có thể thay đổi kết quả so sánh

Kích thước sau serialization không nhất thiết là số byte cuối cùng trên mạng. TLS, RSocket framing, WebSocket framing và compression có thể thêm hoặc giảm byte.

- JSON có key và cú pháp lặp lại nên thường nén tốt bằng gzip/deflate.
- CBOR và Protobuf đã gọn hơn ở nhiều cấu trúc; compression bổ sung có thể đem lại lợi ích nhỏ hơn nhưng vẫn phụ thuộc dữ liệu.
- Với message rất nhỏ, header và chi phí compression có thể lớn hơn phần byte tiết kiệm.
- Compression tốn CPU và có thể tăng latency; không bật cho mọi payload theo mặc định.
- Compression ở proxy, WebSocket per-message compression và compression ở application layer là các lớp khác nhau; xác nhận chính xác lớp nào được bật.

Đo riêng ba con số: bytes sau codec, bytes sau compression và bytes trên transport. Không so JSON đã nén với Protobuf chưa nén rồi kết luận định dạng nào tốt hơn.

## 9. Thiết kế benchmark công bằng

Benchmark cần dùng cùng một tập dữ liệu và cùng yêu cầu ngữ nghĩa cho ba định dạng. Nếu JSON bỏ field còn Protobuf gửi đủ field, kết quả kích thước không thể so sánh công bằng.

### 9.1. Chuẩn bị payload đại diện

Tạo corpus gồm nhiều nhóm:

- **Message nhỏ:** vài field scalar, giống status/ack.
- **Message điển hình:** payload thực tế trung bình của telemetry hoặc command.
- **Message lớn:** nested object, array hoặc nhiều field.
- **Binary-heavy:** bytes/image/chunk hoặc dữ liệu nhị phân.
- **Numeric-heavy:** sequence, timestamp, metric và repeated values.
- **Sparse/optional:** nhiều field không có hoặc dùng giá trị mặc định.
- **Worst case:** payload gần giới hạn kích thước và độ sâu được cho phép.

Mỗi nhóm cần có dữ liệu giống nhau về giá trị và semantics. Với Protobuf, tạo message từ schema; với JSON/CBOR, tạo object tương đương. Xác nhận round-trip cho kết quả nghiệp vụ giống nhau trước khi đo tốc độ.

### 9.2. Đo encode/decode riêng bằng JMH

JMH phù hợp để đo chi phí codec trong JVM. Ví dụ khung benchmark:

```java
@State(Scope.Thread)
@BenchmarkMode({Mode.Throughput, Mode.AverageTime})
@OutputTimeUnit(TimeUnit.MICROSECONDS)
@Warmup(iterations = 5)
@Measurement(iterations = 8)
@Fork(3)
public class SerializationBenchmark {

    private ObjectMapper jsonMapper;
    private ObjectMapper cborMapper;
    private TelemetryDto dto;
    private byte[] jsonBytes;
    private byte[] cborBytes;
    private TelemetryReading protobufMessage;
    private byte[] protobufBytes;

    @Setup(Level.Trial)
    public void setup() throws Exception {
        jsonMapper = new ObjectMapper();
        cborMapper = new ObjectMapper(new CBORFactory());
        dto = sampleDto();
        jsonBytes = jsonMapper.writeValueAsBytes(dto);
        cborBytes = cborMapper.writeValueAsBytes(dto);
        protobufMessage = toProtobuf(dto);
        protobufBytes = protobufMessage.toByteArray();
    }

    @Benchmark
    public byte[] jsonEncode() throws Exception {
        return jsonMapper.writeValueAsBytes(dto);
    }

    @Benchmark
    public TelemetryDto jsonDecode() throws Exception {
        return jsonMapper.readValue(jsonBytes, TelemetryDto.class);
    }

    @Benchmark
    public byte[] cborEncode() throws Exception {
        return cborMapper.writeValueAsBytes(dto);
    }

    @Benchmark
    public TelemetryDto cborDecode() throws Exception {
        return cborMapper.readValue(cborBytes, TelemetryDto.class);
    }

    @Benchmark
    public byte[] protobufEncode() {
        return protobufMessage.toByteArray();
    }

    @Benchmark
    public TelemetryReading protobufDecode() throws Exception {
        return TelemetryReading.parseFrom(protobufBytes);
    }
}
```

`TelemetryDto`, `sampleDto()` và `toProtobuf(...)` là phần fixture của benchmark. Cần khai báo dependency JMH, Jackson CBOR và Protobuf tương ứng trong project benchmark. Ví dụ trên chỉ là khung; hãy kiểm tra compiler, generated class và phiên bản codec đang sử dụng.

Không tạo `ObjectMapper`, `CBORFactory` hoặc schema descriptor trong mỗi lần benchmark. Khởi tạo chúng ở setup để đo encode/decode thay vì đo chi phí tạo cấu hình. Dùng JMH Blackhole hoặc trả kết quả để tránh dead-code elimination; chạy profiler GC để đo allocation.

### 9.3. Các chỉ số cần thu thập

| Chỉ số | Ý nghĩa |
|---|---|
| Encoded bytes/message | Kích thước sau serialization. |
| Encode time/op | CPU/thời gian chuyển object thành bytes. |
| Decode time/op | CPU/thời gian chuyển bytes thành object. |
| Throughput | Số message xử lý mỗi giây. |
| Allocation bytes/op | Lượng bộ nhớ cấp phát mỗi message. |
| GC frequency/pause | Tác động của allocation tới garbage collection. |
| p50/p95/p99 end-to-end | Độ trễ thật qua RSocket và transport. |
| CPU và memory ở tải đồng thời | Chi phí khi nhiều stream/subscriber hoạt động. |

Không chỉ báo cáo trung bình. Realtime thường nhạy với tail latency và GC pause; p95/p99 có thể quan trọng hơn throughput tối đa.

## 10. Benchmark tích hợp qua RSocket

JMH chỉ đo codec trong JVM, chưa đo toàn bộ đường truyền. Sau benchmark micro, chạy load test qua RSocket TCP và/hoặc WebSocket với cùng server, route, payload và concurrency.

Một kế hoạch kiểm thử:

1. Chạy JSON, CBOR và Protobuf trên cùng phiên bản JVM, CPU, heap và network.
2. Dùng cùng tập payload và cùng số field có ý nghĩa.
3. Dùng cùng transport, TLS, compression và RSocket interaction model.
4. Tạo số lượng client/stream đồng thời gần production.
5. Đo bytes trên wire, CPU, heap/direct memory, GC và latency p50/p95/p99.
6. Chạy riêng Request-Response và Request-Stream/Channel vì pattern gửi/nhận khác nhau.
7. Kiểm tra backpressure khi producer nhanh hơn consumer.
8. Chạy warm-up đủ lâu, lặp nhiều lần và so sánh cùng điều kiện.
9. Ghi lại phiên bản Spring, RSocket, Jackson, CBOR library, Protobuf runtime, JDK và cấu hình compression.

Không so một JSON codec reflection chưa tối ưu với Protobuf generated code đã warm-up rồi kết luận khác biệt chỉ đến từ định dạng. Cần tối ưu hợp lý cả ba implementation và giữ semantics tương đương.

### 10.1. Ví dụ bảng kết quả để điền sau khi đo

| Định dạng | Bytes/message | Encode µs/op | Decode µs/op | Allocation B/op | p99 end-to-end |
|---|---:|---:|---:|---:|---:|
| JSON | Đo thực tế | Đo thực tế | Đo thực tế | Đo thực tế | Đo thực tế |
| CBOR | Đo thực tế | Đo thực tế | Đo thực tế | Đo thực tế | Đo thực tế |
| Protobuf | Đo thực tế | Đo thực tế | Đo thực tế | Đo thực tế | Đo thực tế |

Không điền số benchmark giả định vào tài liệu. Kết quả cần được tạo từ payload và môi trường triển khai của hệ thống.

## 11. Ảnh hưởng của payload tới lựa chọn

| Đặc điểm workload | Lựa chọn nên thử trước | Lý do |
|---|---|---|
| API nội bộ, payload nhỏ, cần debug nhanh | JSON | Đơn giản và dễ quan sát; overhead có thể không đáng kể. |
| Browser client đa dạng, contract thay đổi thường xuyên | JSON | Hệ sinh thái parser rộng và không cần code generation. |
| Payload có binary data hoặc số liệu nhiều | CBOR hoặc Protobuf | Binary native, tránh Base64 và giảm text parsing. |
| Nhiều service dùng schema ổn định, message rate cao | Protobuf | Field number, generated code và wire format gọn. |
| Gateway/IoT cần format linh hoạt nhưng gọn | CBOR | Binary và không bắt buộc schema compiler. |
| Đối tác bên ngoài cần khả năng đọc trực tiếp | JSON | Dễ tích hợp và debug qua nhiều nền tảng. |
| Cần browser và backend dùng cùng Protobuf contract | Protobuf nếu có generated JS/runtime phù hợp | Giảm khác biệt schema nhưng tăng yêu cầu tooling ở browser. |

Đây là các lựa chọn để benchmark trước, không phải quy tắc cứng. Nếu JSON đã đáp ứng SLO và chi phí mạng thấp, chuyển sang binary có thể không đáng với chi phí schema, debug và tương thích.

## 12. Các sai lầm khi tối ưu serialization

- **Chọn Protobuf vì nghĩ luôn nhanh nhất:** kết quả phụ thuộc message shape, runtime và codec.
- **Chỉ đo kích thước payload:** bỏ qua CPU, allocation, GC, TLS, framing và compression.
- **So dữ liệu không tương đương:** field bị thiếu hoặc precision khác làm kết quả vô nghĩa.
- **Tạo mapper mỗi request:** đo chi phí khởi tạo thay vì codec và tạo allocation không cần thiết.
- **Bỏ qua field presence:** JSON `null`, field thiếu và Protobuf default có thể mang ý nghĩa khác nhau.
- **Đổi field number Protobuf:** phá contract với client cũ.
- **Dùng integer key CBOR không có schema quản lý:** giảm byte nhưng làm contract khó hiểu và dễ xung đột.
- **Nén mọi message:** CPU và framing compression có thể lớn hơn lợi ích với payload nhỏ.
- **Chỉ benchmark localhost:** bỏ qua proxy, TLS, WebSocket và concurrency production.
- **Quên MIME type:** client gửi CBOR nhưng server decode JSON sẽ lỗi dù bytes được truyền thành công.

## 13. Bảo mật và giới hạn khi decode

JSON, CBOR và Protobuf đều là định dạng dữ liệu, không phải cơ chế bảo mật. Dùng TLS để bảo vệ dữ liệu trên đường truyền và authentication/authorization để bảo vệ quyền truy cập. Binary không có nghĩa là dữ liệu được mã hóa hoặc đáng tin cậy.

Đối với payload không tin cậy:

- Giới hạn kích thước message và số phần tử lặp.
- Giới hạn độ sâu nested object và số lượng map/array entry.
- Đặt timeout cho decode/validation khi cần.
- Kiểm tra range, enum, string length và business invariant sau decode.
- Không deserialize thành class tùy ý hoặc bật polymorphic typing không kiểm soát.
- Kiểm tra unknown field/unknown enum theo chính sách tương thích.
- Theo dõi lỗi decode và tỷ lệ payload bị từ chối mà không log raw payload nhạy cảm.

Protobuf schema giúp xác định kiểu và field nhưng không thay thế validation nghiệp vụ. JSON/CBOR linh hoạt cũng cần giới hạn parser và input.

## 14. Checklist trước khi chọn định dạng

- Đã xác định payload thực tế và tần suất gửi theo từng interaction model.
- Đã đo kích thước sau codec và sau compression riêng biệt.
- Đã đo encode/decode CPU, allocation, GC và p95/p99 latency.
- Client và server thống nhất data MIME type trong RSocket SETUP.
- `RSocketStrategies` có encoder/decoder tương ứng ở cả hai phía.
- Metadata MIME type và routing metadata được giữ đúng contract riêng.
- Schema/field evolution có quy tắc tương thích và kiểm thử version.
- Browser client có parser/runtime phù hợp nếu dùng CBOR hoặc Protobuf.
- Có giới hạn payload và parser cho dữ liệu không tin cậy.
- Đã kiểm thử qua TCP/WebSocket và hạ tầng thực tế.
- Chỉ chuyển định dạng khi lợi ích đo được đáp ứng mục tiêu hiệu năng hoặc vận hành.

## 15. Kết luận

JSON ưu tiên khả năng đọc, tích hợp và phát triển nhanh; CBOR cung cấp biểu diễn nhị phân linh hoạt với byte string native; Protobuf dùng schema và field number để tạo wire format gọn, phù hợp với contract ổn định và message rate cao. Kích thước và tốc độ thực tế phụ thuộc cấu trúc payload, codec, runtime, compression và transport. Trong RSocket, hãy cấu hình đúng data MIME type và codec ở cả client/server, giữ metadata MIME type riêng, rồi benchmark công bằng bằng JMH và load test qua transport thực. Chọn định dạng đáp ứng SLO với chi phí tương thích và vận hành thấp nhất, thay vì mặc định một định dạng luôn thắng.
