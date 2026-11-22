# Lựa chọn định dạng theo khả năng tương tác và nhu cầu lưu trữ

Jackson không chỉ xử lý JSON. Hệ sinh thái Jackson có các module cho nhiều định dạng, trong đó có những định dạng nhị phân như CBOR, Smile, Avro, Protobuf và Ion. BSON cũng thường xuất hiện trong các hệ thống dùng MongoDB. Mỗi định dạng có mô hình dữ liệu, mức độ phụ thuộc schema, khả năng tương tác và cách tổ chức dữ liệu trên wire hoặc trong file khác nhau.

Không có định dạng nhị phân nào luôn tốt hơn JSON. Một payload nhị phân có thể nhỏ hơn hoặc nhanh hơn trong một workload cụ thể, nhưng cũng có thể khó debug, cần schema riêng, khó tích hợp với client phổ thông hoặc tốn chi phí chuyển đổi ở hệ thống khác. Định dạng phù hợp phụ thuộc vào ai sẽ đọc dữ liệu, dữ liệu được truyền hay lưu trữ, schema thay đổi ra sao, cần query/index hay không và chi phí vận hành có thể chấp nhận.

Khi chọn định dạng, hãy bắt đầu từ hợp đồng giữa producer và consumer. Nếu nhiều ngôn ngữ, công cụ và con người cần đọc trực tiếp, JSON thường là lựa chọn đơn giản. Nếu cần binary representation chuẩn, có thể xem xét CBOR. Nếu hệ thống chủ yếu dùng Jackson và muốn một dạng binary gần JSON, Smile có thể phù hợp. Nếu dữ liệu được quản lý bằng schema và cần evolution rõ ràng, Avro hoặc Protobuf thường đáng cân nhắc. Nếu dữ liệu thuộc hệ sinh thái MongoDB, BSON có lợi thế tự nhiên. Sau đó mới đo kích thước, tốc độ, CPU và chi phí lưu trữ trên dữ liệu thực tế.

## 1. Định dạng dữ liệu và encoding nhị phân là hai quyết định liên quan

JSON, XML và YAML là các định dạng văn bản. CBOR, Smile, Avro, Protobuf, BSON và binary Ion là các định dạng có representation nhị phân. Tuy nhiên, binary không tự động có nghĩa là dữ liệu đã được nén, mã hóa bảo mật hoặc tự mô tả đầy đủ.

Phân biệt các khái niệm:

| Khái niệm | Vai trò | Ví dụ |
|---|---|---|
| Data format | Quy định cấu trúc và kiểu dữ liệu | JSON, CBOR, Avro, Protobuf |
| Serialization | Chuyển object thành representation của format | Jackson serializer |
| Compression | Giảm số byte bằng thuật toán nén | gzip, zstd, lz4 |
| Encryption | Bảo vệ tính bí mật | TLS khi truyền, AES-GCM khi lưu |
| Framing | Xác định ranh giới message trong stream | HTTP body, length prefix, record container |
| Schema | Mô tả cấu trúc và kiểu field | Avro schema, .proto, JSON Schema, XSD |

Ví dụ, CBOR là binary data format; nó không tự nén toàn bộ payload như gzip. Protobuf là wire format dựa trên schema; nó không tự mã hóa dữ liệu khi truyền qua mạng. Một file Smile vẫn cần quy tắc framing nếu ghép nhiều document vào cùng một stream. Những quyết định này phải được thiết kế riêng.

## 2. Các tiêu chí cần xác định trước khi chọn format

### 2.1. Khả năng tương tác

Hãy xác định consumer thực tế:

- Chỉ có Java service dùng Jackson?
- Có client JavaScript, Python, Go, .NET hoặc mobile không?
- Có hệ thống bên ngoài cần đọc dữ liệu mà không dùng Jackson không?
- Có công cụ vận hành, người dùng hoặc analyst cần mở payload trực tiếp không?
- Có cần trao đổi qua một giao thức hoặc tiêu chuẩn đã công bố không?

Một định dạng có thư viện tốt trong một ngôn ngữ chưa chắc có trải nghiệm tương đương ở các ngôn ngữ khác. Khả năng tương tác còn phụ thuộc việc các bên thống nhất schema, type mapping, timestamp, decimal, enum, unknown fields và framing.

### 2.2. Nhu cầu lưu trữ

Với dữ liệu lưu lâu dài, hãy hỏi:

- Có cần đọc lại sau nhiều năm và qua nhiều phiên bản ứng dụng không?
- Có cần giữ schema hoặc schema ID cùng dữ liệu không?
- Có cần query từng field mà không deserialize toàn bộ record không?
- Có cần append nhiều record vào một file không?
- Có cần random access, partitioning hoặc block compression không?
- Có cần con người kiểm tra trực tiếp khi xảy ra sự cố không?

Format phù hợp cho RPC giữa hai service chưa chắc phù hợp cho kho lưu trữ lâu dài. Ngược lại, format tối ưu cho data lake không nhất thiết phù hợp cho request/response nhỏ.

### 2.3. Hiệu năng và kích thước

Đo ít nhất:

- Kích thước payload trước compression.
- Kích thước sau compression nếu hệ thống có nén.
- Throughput serialize và deserialize.
- Latency p50/p95/p99 ở kích thước message thực tế.
- CPU, allocation rate và peak memory.
- Chi phí tạo/đọc schema và framing.

JSON thường nặng hơn một số binary format do tên field và biểu diễn số dạng text. Tuy nhiên, gzip hoặc zstd có thể nén JSON rất tốt, đặc biệt khi nhiều record lặp lại cùng tên property. Vì vậy, so sánh chỉ dựa trên kích thước chưa nén có thể dẫn đến quyết định sai.

### 2.4. Schema evolution

Producer và consumer có thể được deploy ở thời điểm khác nhau. Hãy xác định:

- Consumer cũ có đọc được field mới không?
- Field mới có default không?
- Có được đổi tên hoặc xóa field không?
- Enum mới được xử lý thế nào?
- Field number hoặc type ID có được tái sử dụng không?
- Có cần schema registry và compatibility checks không?

Một format schema-first như Avro hoặc Protobuf có quy tắc evolution rõ, nhưng chỉ an toàn nếu nhóm tuân thủ các quy tắc đó. Một format schema-less như JSON hoặc CBOR linh hoạt hơn, nhưng ứng dụng phải tự định nghĩa policy unknown/missing/null.

## 3. So sánh nhanh các lựa chọn

| Format | Đặc điểm | Khả năng tương tác | Khi phù hợp |
|---|---|---|---|
| JSON | Văn bản, phổ biến, dễ đọc | Rất rộng | Public API, debug, tích hợp nhiều công cụ |
| CBOR | Binary data model chuẩn hóa, gần JSON nhưng có thêm type/tag | Rộng hơn format riêng của một framework; cần kiểm tra hỗ trợ tag | IoT, message nhỏ, giao thức cần binary chuẩn |
| Smile | Binary format của Jackson, gần mô hình JSON | Tốt trong hệ thống có thư viện Smile; ít phổ biến hơn JSON/CBOR | Java/Jackson service-to-service, log hoặc message nội bộ |
| Avro | Binary encoding dựa trên schema | Rộng trong hệ sinh thái dữ liệu có Avro | Event pipeline, data platform, lưu trữ record có schema evolution |
| Protobuf | Wire format compact dựa trên field number và schema | Rộng trong hệ thống dùng Protocol Buffers/gRPC | RPC, service-to-service, mobile và hệ thống đa ngôn ngữ |
| BSON | Document binary với type mở rộng, gắn với MongoDB | Tốt trong hệ sinh thái MongoDB | Trao đổi/lưu document có kiểu BSON |
| Ion | Data model typed, có text và binary representation | Tốt trong hệ sinh thái hỗ trợ Amazon Ion | Dữ liệu cần decimal, timestamp, symbol và type richness |

Bảng này là định hướng, không phải benchmark. Khả năng tương tác thực tế còn tùy ngôn ngữ, library version và phần con của format mà từng implementation hỗ trợ.

## 4. JSON: lựa chọn mặc định khi tính dễ tích hợp quan trọng

JSON là lựa chọn phổ biến cho REST API, webhook, cấu hình và message có nhiều loại consumer. Payload có thể đọc bằng trình duyệt, curl, log viewer và hầu hết ngôn ngữ lập trình.

Ví dụ:

`````````json
{
  "eventId": "evt-104",
  "eventType": "OrderCreated",
  "occurredAt": "2026-11-12T09:30:00Z",
  "order": {
    "id": "ord-17",
    "total": 129.50,
    "currency": "USD"
  }
}
`````````

Ưu điểm:

- Dễ đọc và debug.
- Hệ sinh thái thư viện rộng.
- Không bắt buộc phải phân phối schema compiler cho consumer.
- Dễ tích hợp với browser, API gateway và công cụ vận hành.
- Có thể thêm field mới nếu consumer được thiết kế để bỏ qua unknown property.

Hạn chế:

- Field name lặp lại trong mọi object làm tăng kích thước.
- Number và timestamp cần quy ước biểu diễn rõ.
- JSON không có kiểu date, decimal, bytes hoặc enum riêng ở mức cú pháp.
- Không tự bảo đảm schema compatibility hay validation nghiệp vụ.

Jackson Databind dùng JSON qua ObjectMapper:

`````````java
ObjectMapper mapper = new ObjectMapper();

byte[] jsonBytes = mapper.writeValueAsBytes(event);
Event restored = mapper.readValue(jsonBytes, Event.class);
`````````

Nếu JSON đã đủ nhanh và kích thước sau compression chấp nhận được, chuyển sang binary format có thể làm tăng độ phức tạp vận hành mà không đem lại lợi ích đủ lớn.

## 5. CBOR: binary format chuẩn hóa gần với mô hình JSON

CBOR (Concise Binary Object Representation) được chuẩn hóa trong RFC 8949. Nó biểu diễn map, array, string, byte string, integer, floating-point, boolean, null và tag bằng cấu trúc nhị phân. CBOR phù hợp khi cần payload nhỏ gọn nhưng vẫn muốn một data model linh hoạt, không bắt buộc phải có schema ngoài cho mọi message.

Ví dụ cấu trúc tương đương JSON:

`````````json
{
  "deviceId": "sensor-7",
  "temperature": 23.75,
  "active": true,
  "sample": "AQID"
}
`````````

Trong CBOR, byte string có thể được biểu diễn như binary value thay vì phải base64 hóa thành JSON string. CBOR còn có tag cho một số kiểu dữ liệu mở rộng; producer và consumer phải thống nhất cách diễn giải tag.

### 5.1. Dùng CBOR với Jackson

Thêm module jackson-dataformat-cbor cùng version tương thích với Jackson Databind:

`````````xml
<dependency>
  <groupId>com.fasterxml.jackson.dataformat</groupId>
  <artifactId>jackson-dataformat-cbor</artifactId>
  <version>VERSION_FROM_JACKSON_BOM</version>
</dependency>
`````````

Sau đó tạo mapper bằng CBORFactory:

`````````java
import com.fasterxml.jackson.dataformat.cbor.CBORFactory;
import com.fasterxml.jackson.databind.ObjectMapper;

CBORFactory factory = new CBORFactory();
ObjectMapper cborMapper = new ObjectMapper(factory);

byte[] payload = cborMapper.writeValueAsBytes(event);
Event restored = cborMapper.readValue(payload, Event.class);
`````````

Các annotation Databind như JsonProperty, JsonIgnore, custom serializer và module khác có thể tiếp tục tham gia tùy cấu hình. Điểm thay đổi chính là factory/parser/generator tạo representation CBOR thay vì JSON text.

### 5.2. Khi nào chọn CBOR?

CBOR đáng xem xét khi:

- Payload cần binary representation nhưng các consumer muốn dùng nhiều ngôn ngữ.
- Thiết bị IoT hoặc client có băng thông/memory hạn chế.
- Cần biểu diễn byte string hoặc tag có kiểu.
- Không muốn phụ thuộc schema registry cho mọi message.
- Các bên có thể thống nhất CBOR profile và quy tắc type mapping.

CBOR không tự giải quyết schema evolution. Nếu producer thêm key, consumer vẫn cần quy tắc xử lý key lạ, missing và default. Việc hỗ trợ CBOR tag cũng có thể khác giữa library; test interoperability giữa implementation thật, không chỉ test Jackson đọc lại dữ liệu Jackson đã ghi.

## 6. Smile: binary JSON trong hệ sinh thái Jackson

Smile là định dạng nhị phân được thiết kế cho mô hình dữ liệu JSON và hệ sinh thái Jackson. Nó lưu cấu trúc object/array và các scalar theo binary token; một số tên field hoặc string lặp lại có thể được tham chiếu qua bảng chia sẻ trong stream.

Smile phù hợp khi producer và consumer kiểm soát được thư viện hỗ trợ Smile. Nó có thể giảm kích thước và chi phí parse so với JSON trong một số workload, nhưng không phổ biến rộng bằng JSON và không nên giả định mọi ngôn ngữ có support tương đương.

### 6.1. Dùng Smile với Jackson

Thêm module jackson-dataformat-smile cùng version Jackson:

`````````xml
<dependency>
  <groupId>com.fasterxml.jackson.dataformat</groupId>
  <artifactId>jackson-dataformat-smile</artifactId>
  <version>VERSION_FROM_JACKSON_BOM</version>
</dependency>
`````````

Tạo mapper:

`````````java
import com.fasterxml.jackson.dataformat.smile.SmileFactory;
import com.fasterxml.jackson.databind.ObjectMapper;

SmileFactory factory = new SmileFactory();
ObjectMapper smileMapper = new ObjectMapper(factory);

byte[] payload = smileMapper.writeValueAsBytes(event);
Event restored = smileMapper.readValue(payload, Event.class);
`````````

Đây là cách dùng tương tự ObjectMapper JSON nhưng output là Smile bytes. Không chuyển byte array thành String bằng charset UTF-8 để log hoặc gửi như text; payload có thể chứa byte không hợp lệ với encoding văn bản. Nếu cần debug, decode bằng Smile-aware tool hoặc tạo JSON diagnostic representation riêng.

### 6.2. Interoperability của Smile

Smile là lựa chọn tốt khi các service đều dùng Jackson hoặc có thư viện Smile tương thích. Khi có consumer ngoài hệ sinh thái đó, cần kiểm tra:

- Có implementation Smile cho ngôn ngữ đó không?
- Implementation có hỗ trợ đúng version/features không?
- Có đọc được shared string references và type metadata không?
- Có test fixture chung để xác nhận byte-level interoperability không?
- Có công cụ vận hành để xem payload khi xảy ra sự cố không?

Nếu phần lớn consumer không hỗ trợ Smile, lợi ích kích thước có thể không bù được chi phí adapter và debugging.

## 7. Avro: schema-first cho record và event pipeline

Avro là một hệ thống serialization dựa trên schema. Schema mô tả record, field, type, union, array, map và các default. Binary encoding thường không cần lặp tên field cho từng record vì schema đã xác định cấu trúc.

Avro có hai cách lưu trữ thường gặp:

- Raw datum encoding: dữ liệu được encode theo một schema đã biết từ bên ngoài.
- Object Container File (OCF): file có header chứa schema và metadata, tiếp theo là các block record; container có thể dùng codec nén.

Hai cách này không thể thay thế nhau. Một byte array raw Avro datum không tự chứa đầy đủ schema để consumer bất kỳ có thể decode. OCF mang schema trong file header nên thuận tiện hơn cho file lưu trữ và batch processing.

### 7.1. Schema writer và reader

Avro hỗ trợ schema resolution. Producer ghi dữ liệu theo writer schema; consumer đọc bằng reader schema. Avro có thể resolve một số thay đổi tương thích, chẳng hạn field mới có default trong reader schema hoặc field không còn được reader dùng.

Ví dụ schema:

`````````json
{
  "type": "record",
  "name": "OrderCreated",
  "namespace": "example.events",
  "fields": [
    {"name": "eventId", "type": "string"},
    {"name": "orderId", "type": "string"},
    {"name": "source", "type": ["null", "string"], "default": null}
  ]
}
`````````

Field source là union giữa null và string. Default null có ý nghĩa khi reader schema cần xử lý record được ghi từ schema cũ không có field đó. Thứ tự branch của union và quy tắc default phải tuân theo Avro schema rules.

### 7.2. Jackson Avro

Jackson có module jackson-dataformat-avro và mapper chuyên dụng AvroMapper. Module này giúp dùng cơ chế Databind cho các kiểu Java được hỗ trợ cùng Avro schema. Tuy nhiên, Avro là schema-first; cần xác định writer/reader schema rõ ràng và không coi raw Avro bytes là tự mô tả.

Ví dụ minh họa tạo schema từ kiểu Java và dùng schema cho writer/reader:

`````````java
AvroMapper avroMapper = new AvroMapper();
AvroSchema schema = avroMapper.schemaFor(OrderCreated.class);

byte[] datum = avroMapper.writer(schema)
    .writeValueAsBytes(event);

OrderCreated restored = avroMapper.readerFor(OrderCreated.class)
    .with(schema)
    .readValue(datum);
`````````

API chi tiết phụ thuộc version của jackson-dataformat-avro; với schema được quản lý độc lập, dùng schema tương ứng do ứng dụng/registry cung cấp thay vì sinh lại tùy tiện từ class.

Nếu cần Object Container File, dùng Avro container writer/reader tương ứng. Đừng giả định writeValueAsBytes tự tạo OCF header và schema registry metadata. Hãy xác nhận loại payload mà producer phát ra.

### 7.3. Khi nào chọn Avro?

Avro phù hợp khi:

- Dữ liệu là record/event trong pipeline.
- Producer và consumer cần schema evolution có quy tắc.
- Nhiều record được lưu thành file/container.
- Hệ thống có schema registry hoặc cơ chế phân phối schema.
- Consumer cần đọc dữ liệu theo writer schema và reader schema khác nhau.

Nếu chỉ có một REST API nhỏ với vài consumer và không có nhu cầu quản lý schema, chi phí schema lifecycle của Avro có thể lớn hơn lợi ích.

## 8. Protobuf: wire format compact cho message có schema

Protocol Buffers (Protobuf) là định dạng serialization dựa trên schema .proto. Mỗi field có number ổn định; binary wire format mang field number và wire type thay vì tên field. Điều này giúp message compact và hỗ trợ nhiều ngôn ngữ qua code generation.

Ví dụ:

`````````protobuf
syntax = "proto3";

message OrderCreated {
  string event_id = 1;
  string order_id = 2;
  int64 occurred_at_epoch_ms = 3;
  optional string source = 4;
}
`````````

Consumer cần schema/descriptor tương thích để diễn giải field. Không được tái sử dụng field number đã phát hành cho ý nghĩa khác; khi xóa field, nên reserve number/name theo quy tắc Protobuf để tránh schema cũ/mới diễn giải nhầm.

### 8.1. Schema evolution

Protobuf cho phép thêm field với number mới mà consumer cũ thường có thể bỏ qua. Tuy nhiên, cần tuân thủ quy tắc:

- Không đổi field number của field đã phát hành.
- Không tái sử dụng number hoặc tên đã reserve.
- Chọn scalar type tương thích với wire type và semantics.
- Cân nhắc presence khi phân biệt default value với field không được gửi.
- Thay đổi enum phải tính tới giá trị mới mà consumer cũ chưa biết.
- Dùng oneof khi các field loại trừ lẫn nhau theo contract.

Các runtime Protobuf có thể giữ hoặc bỏ unknown fields khác nhau tùy API và thao tác chuyển đổi. Không giả định Jackson mapping hoặc chuyển qua POJO sẽ giữ mọi unknown field. Nếu cần forward unknown fields, test trực tiếp với runtime Protobuf được chọn.

### 8.2. Jackson và Protobuf

Jackson có module jackson-dataformat-protobuf hỗ trợ ánh xạ theo Protobuf schema. Module này có API và giới hạn riêng; với hệ thống đã dùng generated Protobuf Message và gRPC, thư viện Protobuf chính thức thường là con đường tự nhiên để serialize message. Chỉ thêm Jackson Protobuf khi cần tích hợp với Databind/POJO hoặc pipeline hiện có và đã xác nhận kiểu/schema được hỗ trợ.

Không nhầm JSON mapping của Protobuf với binary wire format. Protobuf JSON mapping có quy tắc tên field, enum, bytes và special well-known types riêng; nó không phải đơn giản là JSON serializer tùy ý cho POJO.

### 8.3. Khi nào chọn Protobuf?

Protobuf phù hợp khi:

- Giao tiếp service-to-service cần schema rõ và payload compact.
- Có nhiều ngôn ngữ và code generation được chấp nhận.
- Dùng gRPC hoặc hệ sinh thái Protocol Buffers.
- Cần contract field number ổn định và evolution có kiểm soát.

Nó kém thuận tiện hơn JSON khi cần xem payload trực tiếp hoặc khi consumer muốn tự do xử lý field mà không có schema. Tooling như protoc, descriptor và schema compatibility checks là một phần của vận hành.

## 9. BSON: document format cho hệ sinh thái MongoDB

BSON (Binary JSON) là representation nhị phân của document, được thiết kế cho hệ sinh thái MongoDB. BSON hỗ trợ các kiểu như ObjectId, Date, binary subtype, Decimal128 và một số kiểu đặc thù ngoài JSON cơ bản.

Ví dụ document JSON:

`````````json
{
  "_id": "65f1...",
  "createdAt": "2026-11-12T09:30:00Z",
  "total": 129.50
}
`````````

Trong BSON, các trường tương ứng có thể dùng BSON ObjectId, Date và Decimal128 thay vì string/number JSON thông thường. Đây là khác biệt kiểu dữ liệu thực, không chỉ là JSON được nén.

BSON phù hợp khi dữ liệu đi vào hoặc ra khỏi MongoDB và cần giữ semantics của BSON. Với API public đa nền tảng, JSON thường dễ tích hợp hơn. Khi dùng Jackson để map BSON, cần chọn module/implementation BSON tương thích với phiên bản và kiểu BSON đang sử dụng; đừng giả định mọi Jackson module đều hỗ trợ đầy đủ mọi BSON special type hoặc behavior của MongoDB driver.

BSON document có cấu trúc và độ dài riêng, nhưng nếu lưu nhiều document trong một file/stream thì vẫn cần framing/container phù hợp. BSON không tự cung cấp schema evolution đầy đủ như Avro hoặc Protobuf.

## 10. Ion: typed data model có cả text và binary

Amazon Ion là một data format có typed value model, hỗ trợ text representation và binary representation. Ngoài các kiểu cơ bản, Ion có decimal, timestamp, symbol, blob/clob, list, s-expression và struct. Điều này có ích khi dữ liệu cần semantics phong phú hơn JSON.

Ion có thể phù hợp trong hệ sinh thái dùng Amazon Ion hoặc khi producer/consumer cần các kiểu như decimal chính xác, timestamp và symbol. Jackson có module jackson-dataformat-ion cho tích hợp Databind, nhưng cần kiểm tra version và feature support của implementation.

Ion không nên được chọn chỉ vì tên gọi binary. Nếu consumer không có Ion library, công cụ inspect hoặc contract chung, chi phí tương tác có thể lớn. Nếu dữ liệu chỉ gồm object/array/string/number/boolean/null, CBOR hoặc JSON có thể đơn giản hơn.

## 11. So sánh theo mục tiêu sử dụng

### 11.1. API công khai và tích hợp nhiều hệ thống

Ưu tiên JSON khi:

- Client có thể là bất kỳ ngôn ngữ nào.
- Người dùng cần debug request/response.
- API gateway, proxy và observability tools cần đọc payload.
- Kích thước/latency đã đạt yêu cầu.

CBOR có thể là lựa chọn nếu hợp đồng công khai chấp nhận binary, client libraries đủ rộng và payload nhỏ là yêu cầu quan trọng. Smile chỉ nên dùng khi các client được xác nhận có hỗ trợ.

### 11.2. RPC nội bộ

Nếu toàn bộ service có schema và code generation, Protobuf thường là ứng viên mạnh, đặc biệt cùng gRPC. Nếu các service đã dựa trên Jackson và muốn chuyển đổi ít thay đổi, Smile hoặc CBOR có thể là bước phù hợp hơn.

Đừng đổi format chỉ vì một benchmark micro cho thấy nhanh hơn. Hãy đo end-to-end gồm network, compression, parser, validation, allocation và thời gian xử lý nghiệp vụ.

### 11.3. Event streaming và data pipeline

Avro thường phù hợp với event record và pipeline có schema registry. Protobuf cũng có thể phù hợp khi hệ thống đã dùng Protobuf schema/descriptor. JSON vẫn có ưu điểm khi cần consumer linh hoạt và debug đơn giản.

Khi lưu event lâu dài, cần giữ schema ID hoặc writer schema và chính sách compatibility. Không thể dựa vào class Java hiện tại để diễn giải dữ liệu được ghi từ nhiều năm trước.

### 11.4. IoT và thiết bị hạn chế tài nguyên

CBOR là lựa chọn đáng xem xét khi cần binary format chuẩn và payload nhỏ. Protobuf cũng phù hợp nếu schema/code generation được quản lý. Cần đo trên thiết bị thực tế, bao gồm bộ nhớ parser, pin/CPU, kích thước frame và khả năng nâng cấp firmware.

### 11.5. Lưu trữ lâu dài và archive

Avro OCF có lợi thế khi lưu nhiều record cùng schema và block compression. JSON/JSONL dễ inspect và có thể nén tốt. CBOR/Smile phù hợp khi consumer lưu trữ đã biết format và có tool đọc. Với truy vấn phân tích theo cột, cân nhắc định dạng columnar như Parquet thay vì ép một Jackson object serialization format làm nhiệm vụ của analytical storage.

### 11.6. Lưu document trong MongoDB

BSON là format tự nhiên của MongoDB. Nếu cần giữ ObjectId, Date, Decimal128 hoặc binary subtype, dùng BSON-aware driver/mapping. Không chuyển qua JSON trung gian nếu việc đó làm mất kiểu hoặc precision.

## 12. Schema-less và schema-first: chọn theo cách quản lý contract

Một cách phân nhóm hữu ích:

| Schema-less hoặc schema-optional | Schema-first |
|---|---|
| JSON | Avro |
| CBOR | Protobuf |
| Smile | |
| BSON ở tầng document | |
| Ion có thể dùng schema ngoài nhưng không bắt buộc cho mọi document | |

Schema-less không có nghĩa không cần contract. Nó chỉ có nghĩa format không bắt buộc một schema ngoài cho mọi lần decode. Ứng dụng vẫn cần quy tắc field, type, version, null và unknown property.

Schema-first không có nghĩa mọi thay đổi đều an toàn. Avro và Protobuf có quy tắc compatibility riêng. Cần kiểm tra schema trước khi deploy và xác nhận producer/consumer tương thích theo chiều backward/forward mà hệ thống yêu cầu.

## 13. Versioning và schema evolution

### 13.1. Với JSON, CBOR và Smile

Những format này có thể biểu diễn các property tương tự nhau. Quy tắc evolution thường nằm trong application contract:

- Thêm field optional và quy định default.
- Consumer cũ bỏ qua field mới nếu policy cho phép.
- Không đổi type của field đang sử dụng.
- Dùng version hoặc event type mới khi semantics thay đổi lớn.
- Phân biệt missing, null và empty nếu chúng có ý nghĩa khác nhau.

Với Smile/CBOR, binary encoding không loại bỏ nhu cầu versioning. Consumer vẫn phải hiểu tên key, type và semantics.

### 13.2. Với Avro

Giữ writer schema và reader schema. Thêm field cần default phù hợp để reader cũ/mới resolve theo compatibility direction mong muốn. Xóa/đổi tên field cần alias hoặc migration theo Avro schema rules. Đừng thay đổi schema registry subject compatibility mà chưa hiểu tác động tới các consumer đang chạy.

### 13.3. Với Protobuf

Field number là một phần của wire contract. Không tái sử dụng number đã dùng; reserve number/name khi xóa field. Thêm field mới thường an toàn hơn đổi type hoặc đổi semantics của field cũ. Kiểm tra enum unknown value và field presence trên runtime thực tế.

### 13.4. Với BSON và Ion

BSON document thường cần application-level version field hoặc contract riêng để quản lý evolution. Ion có type system phong phú nhưng producer/consumer vẫn cần thống nhất schema và semantics. Một data format linh hoạt không tự giải quyết migration.

## 14. Jackson: dùng mapper/factory theo format

Jackson Core cung cấp parser/generator; Databind cung cấp ObjectMapper. Các dataformat module thường cung cấp factory hoặc mapper chuyên dụng để tạo parser/generator cho representation tương ứng.

Ví dụ hai mapper:

`````````java
ObjectMapper jsonMapper = new ObjectMapper();
ObjectMapper cborMapper = new ObjectMapper(new CBORFactory());
ObjectMapper smileMapper = new ObjectMapper(new SmileFactory());
`````````

Không dùng một ObjectMapper JSON rồi mong output tự trở thành CBOR hoặc Smile. Format được quyết định bởi factory/parser/generator gắn với mapper.

### 14.1. Dùng cùng DTO nếu semantics tương thích

Một DTO đơn giản có thể được serialize bằng nhiều mapper:

`````````java
byte[] json = jsonMapper.writeValueAsBytes(event);
byte[] cbor = cborMapper.writeValueAsBytes(event);
byte[] smile = smileMapper.writeValueAsBytes(event);
`````````

Tuy nhiên, cùng DTO không đảm bảo byte representation hoặc semantics giống nhau. Module có thể hỗ trợ kiểu dữ liệu, tag, number, binary hoặc polymorphism khác nhau. Hãy test contract trên từng format và từng consumer.

### 14.2. Dùng module và version tương thích

Các dependency như jackson-dataformat-cbor, jackson-dataformat-smile, jackson-dataformat-avro, jackson-dataformat-protobuf và jackson-dataformat-ion nên được quản lý cùng version line với Jackson Core/Databind, thường thông qua Jackson BOM.

Ví dụ Maven quản lý version bằng BOM:

`````````xml
<dependencyManagement>
  <dependencies>
    <dependency>
      <groupId>com.fasterxml.jackson</groupId>
      <artifactId>jackson-bom</artifactId>
      <version>VERSION_FROM_JACKSON_BOM</version>
      <type>pom</type>
      <scope>import</scope>
    </dependency>
  </dependencies>
</dependencyManagement>
`````````

Sau đó khai báo module mà không đặt version riêng:

`````````xml
<dependency>
  <groupId>com.fasterxml.jackson.dataformat</groupId>
  <artifactId>jackson-dataformat-cbor</artifactId>
</dependency>
`````````

Tên artifact và khả năng phát hành có thể phụ thuộc module/version. Kiểm tra repository chính thức và dependency tree của dự án trước khi thêm. Không nâng riêng một module lên version khác với core/databind nếu không xác nhận compatibility.

### 14.3. Tách mapper theo format và boundary

Nếu ứng dụng cần nhiều format, đặt mapper trong cấu hình rõ ràng:

`````````java
@Configuration
public class SerializationConfiguration {

    @Bean
    ObjectMapper jsonMapper() {
        return JsonMapper.builder()
            .findAndAddModules()
            .build();
    }

    @Bean
    ObjectMapper cborMapper() {
        return new ObjectMapper(new CBORFactory());
    }

    @Bean
    ObjectMapper smileMapper() {
        return new ObjectMapper(new SmileFactory());
    }
}
`````````

Đây là ví dụ cấu hình khái niệm; ứng dụng thực tế cần thống nhất module date/time, naming, null policy, polymorphism và security settings trên các mapper cần chia sẻ contract. Cấu hình mapper trước khi sử dụng đồng thời và tái sử dụng instance đã cấu hình.

## 15. Binary payload qua HTTP

Nếu endpoint hỗ trợ nhiều format, dùng content negotiation:

- Client gửi Content-Type để khai báo format request.
- Client gửi Accept để khai báo format response mong muốn.
- Server chỉ chấp nhận media type được công bố và trả lỗi rõ nếu format không hỗ trợ.

Ví dụ minh họa:

`````````http
POST /events
Content-Type: application/cbor
Accept: application/json

[binary request body]
`````````

application/cbor là media type đã đăng ký cho CBOR. Với Smile, Avro, Protobuf hoặc BSON, media type được dùng có thể phụ thuộc quy ước và hệ sinh thái; hãy công bố một giá trị nhất quán trong API contract thay vì tự đoán.

Không gửi binary payload dưới dạng chuỗi UTF-8 thông thường. HTTP body là bytes; giữ nguyên byte array hoặc stream. Nếu phải nhúng binary vào JSON, cần base64:

`````````java
String encoded = Base64.getEncoder().encodeToString(binaryPayload);
`````````

Base64 làm tăng kích thước dữ liệu khoảng một phần ba trước overhead JSON. Nếu giao thức cho phép, truyền binary trực tiếp sẽ tránh bước encode/decode này.

## 16. Framing: một payload kết thúc ở đâu?

Một byte stream có thể chứa nhiều message liên tiếp. Parser cần biết ranh giới của từng message.

Các cách phổ biến:

- Một HTTP request/response body cho mỗi message.
- Length-prefix: ghi độ dài trước payload.
- Delimiter/framing riêng nếu format và contract hỗ trợ.
- Container format có header/block/record boundary, như Avro OCF.
- Message broker cung cấp boundary cho từng message.

Không ghép nhiều CBOR hoặc Smile document tùy ý vào một stream rồi giả định consumer biết vị trí kết thúc từng document. Hãy dùng parser sequence support nếu có, hoặc framing được định nghĩa rõ. Với Avro raw datum, schema và boundary cần được cung cấp riêng; OCF là container có cấu trúc record/block.

## 17. Lưu trữ: file format, record format và query

Khi ghi file, cần phân biệt:

| Nhu cầu | Điều cần chọn |
|---|---|
| Một object trong file | Serialization format và schema/version metadata |
| Nhiều record append liên tục | Framing/container và recovery khi ghi dở |
| Nén block | Codec, kích thước block, CPU và khả năng đọc từng block |
| Query theo field | Index hoặc storage engine hỗ trợ query |
| Archive lâu dài | Schema retention, compatibility, checksum và migration |
| Debug/incident response | Tool inspect hoặc bản diagnostic text |

Một file CBOR/Smile chứa object không tự trở thành database có thể query theo field. Nếu cần query document, dùng storage engine phù hợp. Nếu cần analytics scan theo cột, định dạng columnar như Parquet có thể phù hợp hơn Avro/Protobuf object serialization.

Với archive, lưu kèm metadata cần thiết:

- Format và version/profile.
- Schema hoặc schema ID nếu format phụ thuộc schema.
- Application/event version.
- Compression codec và framing/container version.
- Timestamp và checksum nếu yêu cầu integrity.

Không dựa vào tên class Java hoặc phiên bản code hiện tại để diễn giải binary file cũ. Lưu schema/contract độc lập với implementation.

## 18. Compression: benchmark cả dữ liệu đã nén

Binary format có thể giảm kích thước nhờ không lặp tên field và dùng binary number. Nhưng JSON text thường nén rất tốt vì tên property lặp lại nhiều lần. CBOR/Smile cũng có cấu trúc lặp, còn Avro/Protobuf có thể tiết kiệm tên field nhờ schema.

Hãy so sánh các cấu hình giống nhau:

| Đo lường | Câu hỏi |
|---|---|
| Raw bytes | Format nào tạo payload nhỏ hơn trước compression? |
| Compressed bytes | Format nào nhỏ hơn sau gzip/zstd? |
| Encode CPU | Tốn bao nhiêu CPU để serialize và compress? |
| Decode CPU | Tốn bao nhiêu CPU để decompress và deserialize? |
| Latency | End-to-end p95/p99 thay đổi thế nào? |
| Memory | Peak heap và allocation rate ra sao? |

Nếu network đã dùng compression ở HTTP/broker, đừng cộng thêm compression lần nữa mà không đo. Nén hai lần có thể tăng CPU và latency nhưng giảm rất ít bytes.

## 19. Debugging và observability với binary format

Binary payload không thể đọc trực tiếp bằng text editor. Khi chuyển từ JSON sang binary, cần chuẩn bị cách điều tra:

- Tool decode payload theo format.
- Log correlation ID, event type, schema ID và byte length.
- Có thể lưu JSON diagnostic view đã loại dữ liệu nhạy cảm.
- Có test fixture binary để so sánh giữa các version.
- Có quy trình replay message cũ bằng schema tương ứng.

Không log raw binary dưới dạng UTF-8. Byte không hợp lệ có thể bị thay thế hoặc làm log khó đọc. Không log toàn bộ payload nếu có thông tin cá nhân, token hoặc dữ liệu nhạy cảm.

Binary format cũng không phải encryption. Nếu cần bảo mật khi truyền, dùng TLS; nếu cần bảo vệ file lưu trữ, dùng encryption at rest với key management phù hợp.

## 20. Những lưu ý về type mapping

Các định dạng không có cùng type system:

| Java type/semantics | JSON | CBOR/Smile | Avro/Protobuf | BSON/Ion |
|---|---|---|---|---|
| String | String | Text string | String/bytes theo schema | String/symbol |
| byte[] | Thường base64 string | Binary byte string hoặc format-specific | Bytes | Binary/blob |
| BigDecimal | Thường number hoặc string theo policy | Có thể cần tag/representation theo implementation | Avro decimal logical type; Protobuf thường cần convention/message | BSON Decimal128; Ion decimal |
| Date/time | Thường string/number theo convention | Tag hoặc convention | Logical type/convention | BSON Date; Ion timestamp |
| Enum | Thường tên string | Tên hoặc representation được cấu hình | Avro enum; Protobuf enum number/name mapping | Phụ thuộc format/mapper |
| Null/optional | null hoặc field missing | null hoặc field missing | Union/default/presence semantics | Null type hoặc missing field |

Đặc biệt chú ý:

- BigDecimal có thể mất precision nếu bị chuyển qua floating-point.
- Timestamp cần thống nhất timezone, unit và precision.
- byte[] có thể thành base64 trong JSON nhưng là binary trong CBOR/BSON/Ion.
- Enum mới có thể không được consumer cũ biết.
- Missing và explicit null không giống nhau ở mọi format.
- Polymorphic type metadata cần allowlist và contract ổn định.

Không dùng một test JSON làm bằng chứng mọi format sẽ giữ cùng semantics. Hãy kiểm tra từng kiểu quan trọng bằng từng mapper.

## 21. Bảo mật khi deserialize binary

Binary không đồng nghĩa an toàn. Input vẫn có thể chứa:

- Message quá lớn hoặc nesting quá sâu.
- Số lượng collection/map entry quá lớn.
- String hoặc byte string vượt giới hạn.
- Type ID hoặc schema không được phép.
- Payload sai framing hoặc bị cắt giữa chừng.
- Giá trị gây overflow hoặc allocation quá lớn.

Đặt giới hạn request bytes ở transport, giới hạn parser/token nếu module hỗ trợ, giới hạn số phần tử ở custom deserializer và kiểm tra domain invariant. Với schema-first format, chỉ chấp nhận schema ID/descriptor được tin cậy; không tải schema tùy ý từ địa chỉ do client cung cấp.

Không bật polymorphic typing rộng cho input không tin cậy chỉ vì chuyển sang binary. Các rủi ro về class selection, custom deserializer và side effect vẫn tồn tại.

## 22. Thiết kế benchmark công bằng

Tạo benchmark từ dữ liệu đại diện:

1. Message nhỏ thường xuyên gửi.
2. Message lớn có nhiều nested object.
3. Collection dài với field lặp lại.
4. String dài hoặc nội dung Unicode.
5. Decimal, timestamp, binary bytes và enum.
6. Payload có field optional/unknown để đo compatibility path.

Chạy cùng semantics trên từng format. Đừng so sánh JSON chứa base64 với CBOR byte string nếu ứng dụng không cần base64 ở JSON contract; đó là một khác biệt thực tế nhưng phải được ghi rõ. Cũng đừng so Avro raw datum với JSON object container có metadata rồi kết luận chỉ dựa trên bytes; phải so đúng kiểu framing mà production dùng.

Một bảng kết quả nên ghi:

| Format | Raw size | Compressed size | Encode ops/s | Decode ops/s | p95 latency | Allocation/op |
|---|---:|---:|---:|---:|---:|---:|
| JSON | đo | đo | đo | đo | đo | đo |
| CBOR | đo | đo | đo | đo | đo | đo |
| Smile | đo | đo | đo | đo | đo | đo |
| Avro | đo | đo | đo | đo | đo | đo |
| Protobuf | đo | đo | đo | đo | đo | đo |

Không điền số liệu từ benchmark chung trên Internet thay cho workload của ứng dụng. Kết quả phụ thuộc model, library version, JVM, schema, compression, payload distribution và phần cứng.

## 23. Quy trình chọn format

1. Liệt kê producer, consumer, ngôn ngữ và công cụ cần đọc dữ liệu.
2. Xác định dữ liệu dùng cho API, RPC, event streaming, archive hay query/analytics.
3. Quyết định schema có bắt buộc và ai quản lý schema/version.
4. Nếu ưu tiên tương tác phổ thông và debug, bắt đầu với JSON.
5. Nếu cần binary chuẩn, linh hoạt và nhiều implementation, đánh giá CBOR.
6. Nếu các bên chủ yếu dùng Jackson và cần binary JSON-like, đánh giá Smile.
7. Nếu cần schema resolution cho event/file record, đánh giá Avro.
8. Nếu cần generated contract và RPC đa ngôn ngữ, đánh giá Protobuf.
9. Nếu cần giữ BSON types trong MongoDB, dùng BSON-aware integration.
10. Nếu cần typed data model của Ion, xác nhận hệ sinh thái consumer hỗ trợ Ion.
11. Định nghĩa media type, framing, schema ID, compression và versioning.
12. Đo raw/compressed size, CPU, latency và memory bằng payload đại diện.
13. Kiểm thử interoperability giữa implementation khác nhau, không chỉ Jackson ghi rồi Jackson đọc.
14. Chuẩn bị công cụ debug, replay, schema retention và migration trước khi rollout.

Lựa chọn định dạng là quyết định về hợp đồng dữ liệu và vòng đời vận hành. JSON tối ưu cho tính phổ biến và khả năng quan sát; CBOR cung cấp binary representation chuẩn; Smile phù hợp với hệ sinh thái Jackson; Avro và Protobuf đặt schema vào trung tâm; BSON phục vụ document trong hệ sinh thái MongoDB; Ion cung cấp type model phong phú. Hãy chọn theo consumer, schema evolution và nhu cầu lưu trữ trước, rồi dùng benchmark thực tế để xác nhận lợi ích về kích thước và hiệu năng.
