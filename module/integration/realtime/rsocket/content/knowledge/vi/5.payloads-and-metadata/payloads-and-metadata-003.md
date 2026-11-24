# Mã hóa dữ liệu bằng JSON, CBOR, Protobuf hoặc định dạng tùy chỉnh

RSocket truyền dữ liệu dưới dạng các payload nhị phân. Ứng dụng cần thống nhất cách biến đối tượng Java thành byte để gửi đi và cách khôi phục byte thành đối tượng ở đầu nhận. Lựa chọn định dạng mã hóa ảnh hưởng trực tiếp đến kích thước payload, chi phí CPU, khả năng đọc khi debug, khả năng tương thích giữa các phiên bản và mức độ dễ tích hợp với hệ thống khác.

Các lựa chọn thường gặp là JSON, CBOR, Protocol Buffers (Protobuf) và định dạng nhị phân do ứng dụng tự định nghĩa. Không có định dạng nào tốt nhất cho mọi tình huống. Cần chọn dựa trên đặc điểm dữ liệu, tải thực tế, yêu cầu tương thích và công cụ của hệ sinh thái đang sử dụng.

## 1. Payload RSocket gồm data và metadata

Một `Payload` của RSocket có hai vùng byte độc lập:

- **Data** chứa nội dung nghiệp vụ, chẳng hạn yêu cầu tìm đơn hàng, trạng thái cảm biến hoặc kết quả xử lý.
- **Metadata** chứa thông tin mô tả hoặc điều khiển cách xử lý, chẳng hạn route, thông tin xác thực, tracing hay dữ liệu ngữ cảnh.

Hai vùng này đều là dữ liệu nhị phân. RSocket không tự hiểu một mảng byte là JSON, CBOR hay Protobuf; hai đầu kết nối phải thống nhất MIME type và codec để giải mã đúng.

```text
Ứng dụng phía gửi
    Đối tượng Java
         |
         v
       Encoder
         |
         v
    byte[] / ByteBuf
         |
         v
    RSocket Payload
      +--------+----------------+
      |  data  |    metadata    |
      +--------+----------------+
         |
         v
    RSocket transport
         |
         v
    Payload phía nhận
         |
         v
       Decoder
         |
         v
    Đối tượng Java
```

Data MIME type và metadata MIME type được khai báo trong quá trình thiết lập kết nối RSocket. Ví dụ, một kết nối có thể chọn `application/json` làm data MIME type. Khi đó hai bên dùng codec tương ứng để đọc và ghi phần data. Metadata có thể dùng một MIME type riêng; với composite metadata, mỗi mục metadata còn mang MIME type của chính mục đó.

Trong một kết nối, không nên giả định từng payload có thể tự chọn một data MIME type khác nhau. Nếu một kết nối dùng `application/cbor`, hai bên phải diễn giải data theo quy ước CBOR đã thống nhất. Nếu ứng dụng thực sự cần nhiều định dạng data trên cùng kết nối, cần có quy ước phân biệt ở cấp ứng dụng hoặc thiết kế các kết nối có MIME type tương ứng; không được chỉ đổi codec ở một phía.

## 2. JSON: dễ đọc và dễ tích hợp

JSON là định dạng văn bản dựa trên object, array, string, number, boolean và null. Đây là lựa chọn thuận tiện khi client và server dùng nhiều ngôn ngữ, khi cần quan sát payload bằng công cụ thông thường hoặc khi schema thay đổi tương đối linh hoạt.

Ví dụ nội dung JSON của một yêu cầu tìm đơn hàng:

```json
{
  "orderId": "ORD-2026-0018",
  "includeItems": true,
  "locale": "vi-VN"
}
```

Với Jackson, có thể mã hóa và giải mã đối tượng như sau:

```java
ObjectMapper mapper = new ObjectMapper();

byte[] encoded = mapper.writeValueAsBytes(command);
FindOrderCommand decoded = mapper.readValue(encoded, FindOrderCommand.class);
```

Trong Spring RSocket, `Jackson2JsonEncoder` và `Jackson2JsonDecoder` đảm nhiệm việc chuyển đổi giữa object và JSON khi codec được đăng ký trong `RSocketStrategies`.

**Ưu điểm:**

- Dễ đọc, dễ kiểm tra bằng log hoặc công cụ hỗ trợ JSON.
- Được hỗ trợ rộng rãi trong Java, JavaScript, Python, Go và nhiều nền tảng khác.
- Có thể thêm field mới mà client cũ vẫn tiếp tục hoạt động nếu chính sách giải mã cho phép bỏ qua field chưa biết.
- Dễ tạo fixture cho kiểm thử và ví dụ API.

**Hạn chế:**

- Tên field và dấu câu làm payload thường lớn hơn định dạng nhị phân.
- Việc parse văn bản có thể tiêu tốn CPU và tạo thêm object tạm.
- JSON không có kiểu byte riêng; dữ liệu nhị phân thường phải biểu diễn qua Base64 hoặc quy ước khác.
- Number không phân biệt rõ integer, long, decimal ở mọi hệ sinh thái; cần thống nhất cách biểu diễn tiền tệ, thời gian và số có độ chính xác cao.

JSON phù hợp với API công khai, tích hợp đa ngôn ngữ, hệ thống cần khả năng quan sát cao hoặc tải chưa đòi hỏi tối ưu byte ở mức chặt chẽ. Với tiền tệ, nên dùng kiểu decimal và quy ước scale rõ ràng; không dựa vào số thực dấu phẩy động của JSON để biểu diễn giá trị tài chính chính xác.

## 3. CBOR: biểu diễn nhị phân gọn hơn

CBOR (Concise Binary Object Representation) biểu diễn các cấu trúc dữ liệu tương tự JSON bằng định dạng nhị phân. CBOR hỗ trợ trực tiếp nhiều kiểu dữ liệu như byte string, integer, array, map và các giá trị số; vì vậy payload thường gọn hơn JSON, đặc biệt khi dữ liệu có nhiều field lặp lại hoặc chứa byte.

Với Jackson, có thể dùng `jackson-dataformat-cbor`:

```java
ObjectMapper cborMapper = new ObjectMapper(new CBORFactory());

byte[] encoded = cborMapper.writeValueAsBytes(command);
FindOrderCommand decoded =
        cborMapper.readValue(encoded, FindOrderCommand.class);
```

Trong Spring, `Jackson2CborEncoder` và `Jackson2CborDecoder` có thể được đăng ký làm codec. Data MIME type cần được hai phía thống nhất, thường dùng `application/cbor`.

**Ưu điểm:**

- Dữ liệu được biểu diễn nhị phân nên thường tiết kiệm băng thông hơn JSON.
- Có kiểu byte string và các kiểu số trực tiếp, không cần chuyển byte sang Base64.
- Giữ mô hình map/array quen thuộc, dễ ánh xạ với object trong ứng dụng.
- Hữu ích khi cần giảm kích thước thông điệp nhưng vẫn muốn cấu trúc dữ liệu linh hoạt.

**Hạn chế:**

- Không thể đọc trực tiếp bằng mắt; khi debug cần công cụ giải mã hoặc log ở dạng đã chuyển đổi.
- Hai bên vẫn phải thống nhất quy tắc ánh xạ kiểu, field, giá trị thiếu và thời gian.
- Kích thước nhỏ hơn không đồng nghĩa luôn nhanh hơn; kết quả phụ thuộc dữ liệu, codec và chi phí cấp phát.
- Nếu cần chữ ký hoặc hash ổn định trên byte, phải quy định cách mã hóa canonical phù hợp; hai cách mã hóa cùng một cấu trúc không nhất thiết tạo ra chuỗi byte giống nhau.

CBOR thích hợp cho thiết bị, mạng có băng thông hạn chế, dữ liệu có nhiều byte string hoặc hệ thống muốn giữ cấu trúc linh hoạt nhưng giảm overhead văn bản.

## 4. Protobuf: schema rõ ràng và hiệu quả

Protocol Buffers là định dạng nhị phân dựa trên schema. Nhóm phát triển định nghĩa message trong file `.proto`, sau đó dùng `protoc` sinh class cho ngôn ngữ cần thiết. Mỗi field có một số định danh (field number); wire format lưu số field và kiểu wire thay vì lặp lại tên field trong từng thông điệp.

Ví dụ schema cho sự kiện đơn hàng:

```protobuf
syntax = "proto3";

package example.orders;

message OrderEvent {
  string order_id = 1;
  int64 created_at_epoch_ms = 2;
  optional string source = 3;
}
```

Sau khi sinh class Java, ứng dụng có thể tuần tự hóa và phân tích message:

```java
OrderEvent event = OrderEvent.newBuilder()
        .setOrderId("ORD-2026-0018")
        .setCreatedAtEpochMs(System.currentTimeMillis())
        .setSource("checkout")
        .build();

byte[] encoded = event.toByteArray();
OrderEvent decoded = OrderEvent.parseFrom(encoded);
```

Spring cung cấp `ProtobufEncoder` và `ProtobufDecoder` cho message Protobuf. Ứng dụng cần thêm thư viện runtime Protobuf, sinh code từ schema và thống nhất MIME type, thường gặp là `application/x-protobuf`.

**Ưu điểm:**

- Payload thường nhỏ và giải mã nhanh với message có schema phù hợp.
- Schema định nghĩa kiểu và cấu trúc rõ ràng, giúp nhiều dịch vụ dùng chung hợp đồng.
- Có công cụ sinh code cho nhiều ngôn ngữ.
- Hỗ trợ tiến hóa schema nếu tuân thủ quy tắc tương thích.

**Hạn chế:**

- Cần quản lý file `.proto`, quy trình sinh code và phiên bản schema.
- Khó quan sát trực tiếp khi debug vì payload là nhị phân.
- Thêm hoặc thay đổi field cần tuân thủ quy tắc wire compatibility; thay đổi tùy tiện có thể làm client cũ đọc sai dữ liệu.
- Các kiểu dữ liệu trong schema cần được thiết kế cẩn thận, đặc biệt với tiền tệ, thời gian, giá trị optional và enum.

Khi thay đổi schema Protobuf, hãy tuân thủ các nguyên tắc sau:

1. Không đổi số field đã phát hành, kể cả khi đổi tên field.
2. Không tái sử dụng số field đã xóa; đánh dấu số đó bằng `reserved`.
3. Chỉ thêm field mới với số chưa từng dùng và có kiểu tương thích theo quy tắc Protobuf.
4. Khi xóa field, cân nhắc reserve cả tên để tránh vô tình dùng lại trong tương lai.
5. Không thay đổi wire type một cách tùy tiện; kiểm tra tương thích giữa schema cũ và mới bằng công cụ hoặc kiểm thử hợp đồng.
6. Thiết kế enum có giá trị mặc định an toàn, thường bắt đầu bằng một giá trị `UNSPECIFIED` hoặc tương đương.

Ví dụ khi bỏ field cũ:

```protobuf
message OrderEvent {
  reserved 4;
  reserved "legacy_status";

  string order_id = 1;
  int64 created_at_epoch_ms = 2;
  optional string source = 3;
}
```

Protobuf phù hợp với giao tiếp nội bộ giữa nhiều dịch vụ, hệ thống có schema được quản lý tập trung, thông điệp lớn hoặc tải cao cần tối ưu băng thông và CPU.

## 5. Định dạng tùy chỉnh: chỉ dùng khi có lý do cụ thể

Một số hệ thống cần định dạng riêng để đáp ứng yêu cầu về kích thước, tốc độ, thiết bị phần cứng hoặc cấu trúc dữ liệu đặc thù. Ví dụ, ứng dụng telemetry có thể dùng một bản ghi nhị phân cố định gồm mã thiết bị, timestamp, loại cảm biến và các giá trị đo.

Một định dạng tùy chỉnh cần mô tả rõ cấu trúc byte. Ví dụ một header minh họa:

```text
+------------+---------+----------+----------------+----------------+
| magic (2B) | version | flags    | length (4B)     | payload bytes  |
+------------+---------+----------+----------------+----------------+
```

Đây chỉ là ví dụ về bố cục; ứng dụng phải định nghĩa chính xác kích thước từng trường, thứ tự byte (*endianness*), cách mã hóa số, ý nghĩa của flags và giới hạn độ dài. Decoder cần kiểm tra header, phiên bản và độ dài trước khi cấp phát bộ nhớ hoặc đọc nội dung.

Nếu xây dựng định dạng riêng, cần có tối thiểu:

- **MIME type riêng:** ví dụ `application/vnd.example.telemetry-v1` để hai đầu chọn đúng codec.
- **Version:** quy định cách nhận biết phiên bản và chính sách tương thích.
- **Quy tắc byte:** xác định endianness, signed/unsigned, độ dài, encoding chuỗi, null và thứ tự field.
- **Giới hạn kích thước:** từ chối length âm, length vượt giới hạn hoặc cấu trúc gây cấp phát quá lớn.
- **Xử lý lỗi:** định nghĩa hành vi khi thiếu byte, sai magic, phiên bản không hỗ trợ hoặc field không hợp lệ.
- **Tài liệu và fixture:** lưu ví dụ byte chuẩn để các implementation Java và ngôn ngữ khác kiểm thử chéo.
- **Kiểm thử bảo mật:** thử dữ liệu bị cắt, dữ liệu ngẫu nhiên, giá trị biên và các trường hợp có thể gây tiêu thụ CPU hoặc bộ nhớ bất thường.

Không nên tự tạo định dạng chỉ vì JSON có vẻ dài. Chi phí thiết kế, bảo trì, debug và phối hợp nhiều phiên bản thường lớn hơn phần băng thông tiết kiệm được. Chỉ chọn định dạng tùy chỉnh khi benchmark hoặc ràng buộc thiết bị chứng minh các định dạng phổ biến không đáp ứng được yêu cầu.

## 6. So sánh và cách lựa chọn

| Tiêu chí | JSON | CBOR | Protobuf | Tùy chỉnh |
| --- | --- | --- | --- | --- |
| Biểu diễn | Văn bản | Nhị phân | Nhị phân theo schema | Theo thiết kế |
| Dễ đọc trực tiếp | Cao | Thấp | Thấp | Thường thấp |
| Kích thước thường gặp | Lớn hơn | Gọn hơn JSON | Thường rất gọn | Có thể tối ưu cao |
| Schema | Linh hoạt, thường ngầm định | Linh hoạt, thường ngầm định | Khai báo bằng `.proto` | Do ứng dụng định nghĩa |
| Đa ngôn ngữ | Rất rộng | Rộng | Rộng | Phải tự triển khai |
| Tiến hóa dữ liệu | Theo quy ước field | Theo quy ước field | Có quy tắc field number | Phải tự thiết kế |
| Công sức vận hành | Thấp | Trung bình | Trung bình | Cao |

Có thể bắt đầu lựa chọn theo các tình huống sau:

- Chọn **JSON** khi khả năng đọc, debug và tích hợp quan trọng hơn việc tối ưu byte.
- Chọn **CBOR** khi cần dữ liệu nhị phân gọn, cấu trúc linh hoạt và có codec hỗ trợ ở hai phía.
- Chọn **Protobuf** khi cần schema rõ ràng, code sinh tự động, nhiều dịch vụ cùng chia sẻ hợp đồng và hiệu suất ổn định.
- Chọn **định dạng tùy chỉnh** khi có yêu cầu đặc thù đã được đo lường, đội ngũ có thể duy trì codec và hợp đồng byte lâu dài.

Đừng chọn chỉ dựa trên benchmark tổng quát trên Internet. Hãy đo với payload thực tế: số field, độ dài chuỗi, tỷ lệ byte string, số lượng message mỗi giây, kích thước trung bình và phân vị lớn nhất. Đo cả thời gian encode/decode, allocation, CPU, kích thước frame và độ trễ đầu cuối.

## 7. Cấu hình codec trong Spring RSocket

Spring RSocket sử dụng `RSocketStrategies` để tập hợp encoder và decoder. Các codec được đăng ký phải phù hợp với kiểu object mà controller nhận/trả về và data MIME type mà kết nối sử dụng.

Ví dụ đăng ký codec JSON, CBOR và Protobuf:

```java
RSocketStrategies strategies = RSocketStrategies.builder()
        .encoders(encoders -> {
            encoders.add(new Jackson2JsonEncoder());
            encoders.add(new Jackson2CborEncoder());
            encoders.add(new ProtobufEncoder());
        })
        .decoders(decoders -> {
            decoders.add(new Jackson2JsonDecoder());
            decoders.add(new Jackson2CborDecoder());
            decoders.add(new ProtobufDecoder());
        })
        .build();
```

Các class CBOR cần module Jackson CBOR; codec Protobuf cần thư viện Protobuf tương ứng. Tùy phiên bản Spring, constructor và cấu hình codec có thể khác nhau; hãy dùng API của phiên bản Spring Framework đang có trong dự án.

Client chọn data MIME type khi tạo requester. Ví dụ dưới đây chọn CBOR cho kết nối:

```java
RSocketRequester requester = RSocketRequester.builder()
        .dataMimeType(MimeType.valueOf("application/cbor"))
        .rsocketStrategies(strategies)
        .connectTcp("localhost", 7000)
        .block();
```

Sau đó có thể gửi và nhận object qua route:

```java
Mono<OrderView> response = requester
        .route("orders.find")
        .data(new FindOrderCommand("ORD-2026-0018"))
        .retrieveMono(OrderView.class);
```

Phía server cần cấu hình codec tương thích và khai báo handler:

```java
@MessageMapping("orders.find")
Mono<OrderView> find(FindOrderCommand command) {
    return orderService.find(command.orderId());
}
```

Ví dụ này minh họa cách Spring ánh xạ object qua codec. Nếu client chọn `application/cbor` nhưng server chỉ có decoder JSON, request có thể không được giải mã. Tương tự, nếu server phát kiểu không có encoder phù hợp, response không thể được mã hóa đúng. Hãy cấu hình hai phía như một hợp đồng chung và kiểm thử kết nối thật.

Trong một hệ thống có nhiều client, cần công bố rõ data MIME type, metadata MIME type, schema hoặc DTO, và chính sách thay đổi. Đừng dựa vào việc hai phía tình cờ dùng cùng một class Java; hợp đồng truyền qua mạng phải độc lập với cách tổ chức package trong từng ứng dụng.

## 8. Metadata có phải cũng dùng JSON hoặc Protobuf không?

Metadata là vùng byte riêng trong `Payload`, không phải phần tiếp nối của data. Có thể dùng MIME type phù hợp để mã hóa metadata ứng dụng, nhưng metadata của RSocket còn có các định dạng đã được quy ước cho chức năng giao thức.

Khi dùng composite metadata, một payload có thể mang nhiều mục metadata, mỗi mục có MIME type và nội dung riêng. Ví dụ, một payload có thể kết hợp routing metadata với authentication metadata hoặc tracing metadata. Các mục này tuân theo định dạng metadata tương ứng; không nên thay thế chúng bằng một object JSON tùy ý nếu thư viện hoặc peer đang chờ định dạng chuẩn.

Hãy phân biệt ba lớp:

1. **Data MIME type:** cho biết cách giải mã vùng data của payload, ví dụ JSON, CBOR hoặc Protobuf.
2. **Metadata MIME type:** cho biết cách diễn giải vùng metadata. Nếu dùng composite metadata, từng entry có định danh MIME type riêng.
3. **Metadata nghiệp vụ:** thông tin do ứng dụng định nghĩa như tenant, correlation ID hoặc locale; cần quy ước tên, kiểu, giới hạn và chính sách tin cậy.

Thông tin xác thực hoặc định danh tenant trong metadata vẫn là dữ liệu đến từ peer. Server phải xác thực và kiểm tra quyền ở phía server; việc client gửi một giá trị `tenantId` không chứng minh client có quyền truy cập tenant đó. Tránh ghi token, mật khẩu và dữ liệu nhạy cảm vào log payload.

## 9. Kiểm thử codec và tương thích

Một codec không chỉ cần round-trip thành công trong cùng một phiên bản. Nó cần hoạt động với dữ liệu thật, dữ liệu cũ và các trường hợp đầu vào không hợp lệ.

Với mỗi định dạng, nên kiểm thử:

- **Round-trip:** object được encode rồi decode phải giữ nguyên các trường có ý nghĩa nghiệp vụ.
- **Golden fixture:** dùng bộ byte hoặc JSON mẫu đã lưu để phát hiện thay đổi không chủ ý trong codec.
- **Tương thích phiên bản:** client cũ và server mới, rồi client mới và server cũ, xử lý field được thêm hoặc bỏ như dự kiến.
- **Giá trị biên:** chuỗi rỗng, field vắng mặt, null, số âm, số rất lớn, timestamp và dữ liệu byte.
- **Dữ liệu lỗi:** byte bị cắt, JSON sai cú pháp, CBOR sai cấu trúc, Protobuf không hợp lệ và MIME type không được hỗ trợ.
- **Giới hạn tài nguyên:** payload quá lớn, chuỗi lồng sâu hoặc số lượng phần tử vượt giới hạn phải bị từ chối có kiểm soát.
- **Kiểm thử tích hợp RSocket:** xác minh data MIME type, metadata MIME type, route và codec trên kết nối TCP hoặc WebSocket thực tế.

Đối với Protobuf, kiểm thử schema cũ/mới là bắt buộc khi triển khai rolling deployment. Với JSON và CBOR, kiểm thử chính sách field lạ, field thiếu và kiểu dữ liệu thay đổi. Với định dạng tùy chỉnh, giữ fixture byte cho từng phiên bản và kiểm thử nhiều implementation nếu có nhiều ngôn ngữ.

Không nên bật giải mã kiểu đa hình tùy tiện với dữ liệu không tin cậy. Giới hạn kích thước payload trước khi parse, kiểm tra dữ liệu sau giải mã và tránh cơ chế deserialization có thể khởi tạo class tùy ý. Việc mã hóa nhị phân không tự làm payload an toàn; xác thực, phân quyền và bảo vệ kết nối vẫn cần được thực hiện riêng.

## 10. Quy trình đưa định dạng vào môi trường thực tế

Khi triển khai một định dạng mới trong hệ thống RSocket, có thể đi theo trình tự sau:

1. Xác định loại dữ liệu, kích thước message, tần suất gửi và các client/server cần hỗ trợ.
2. Chọn định dạng và thống nhất data MIME type; nếu có metadata ứng dụng, thống nhất metadata MIME type và cấu trúc entry.
3. Định nghĩa schema hoặc tài liệu byte format, bao gồm quy tắc versioning và giới hạn kích thước.
4. Cấu hình encoder/decoder ở cả client và server; kiểm tra dependency và phiên bản thư viện.
5. Viết kiểm thử round-trip, fixture, tương thích và dữ liệu lỗi.
6. Benchmark bằng tải đại diện, đo CPU, allocation, kích thước payload và độ trễ.
7. Triển khai theo giai đoạn để client và server có thể nâng cấp mà không làm gián đoạn kết nối đang hoạt động.

Định dạng mã hóa là một phần của hợp đồng giao tiếp. Khi thay đổi nó, cần xem xét đồng thời MIME type, codec, schema, metadata và vòng đời triển khai của các peer. Làm rõ các yếu tố này giúp RSocket truyền dữ liệu hiệu quả mà vẫn giữ được khả năng tương thích và vận hành an toàn qua TCP hoặc WebSocket.
