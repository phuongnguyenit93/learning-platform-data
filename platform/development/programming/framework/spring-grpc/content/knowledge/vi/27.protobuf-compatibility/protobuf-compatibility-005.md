# Đổi kiểu field có thể phá tương thích

## 1. Vì sao đổi kiểu field là thay đổi rủi ro?

Trong **SPRING_GRPC**, Protobuf schema là hợp đồng nhị phân giữa client, server và các thành phần trung gian. Một field đã phát hành có thể được dùng bởi nhiều phiên bản ứng dụng cùng lúc; payload cũ còn có thể nằm trong database, event log, queue hoặc backup.

Đổi kiểu một field có thể làm parser đọc sai bytes, bỏ qua field, báo lỗi parse hoặc tạo ra giá trị hợp lệ về mặt Java nhưng sai ý nghĩa nghiệp vụ. Đặc biệt, **hai kiểu có cùng wire type vẫn chưa chắc tương thích**: wire type chỉ mô tả cách parser tìm và đọc vùng dữ liệu, không đảm bảo cùng cách mã hóa hay cùng miền giá trị.

Bài này tập trung vào wire type, các cặp kiểu có cùng wire type nhưng khác semantics, thay đổi cardinality/presence, migration bằng field number mới và kiểm thử giữa schema cũ/mới.

## 2. Wire type cho biết parser đọc dữ liệu như thế nào

Binary Protobuf không ghi tên kiểu Java hay tên field vào tag. Mỗi field bắt đầu bằng một tag:

```text
tag = (field_number << 3) | wire_type
```

`field_number` xác định field; `wire_type` cho biết cách đọc phần value. Các wire type thường gặp:

| Wire type | Cấu trúc value | Các kiểu thường dùng |
| --- | --- | --- |
| 0 — Varint | Số nguyên biến độ dài | `int32`, `int64`, `uint32`, `uint64`, `sint32`, `sint64`, `bool`, enum |
| 1 — 64-bit | 8 bytes cố định | `fixed64`, `sfixed64`, `double` |
| 2 — Length-delimited | Độ dài theo sau bởi một dãy bytes | `string`, `bytes`, embedded message, packed repeated scalar |
| 5 — 32-bit | 4 bytes cố định | `fixed32`, `sfixed32`, `float` |

Wire type 3 và 4 từng được dùng cho group trong Protobuf đời cũ; không nên chọn group cho schema mới.

Các kiểu trong cùng một hàng chỉ chia sẻ cách đóng khung dữ liệu trên wire. Parser có thể biết vùng value dài bao nhiêu, nhưng cách diễn giải bytes thành giá trị vẫn do kiểu field quyết định.

Ví dụ, `float` và `fixed32` đều dùng wire type 5. Cả hai đều có 4 bytes, nhưng `float` diễn giải chúng theo IEEE 754, còn `fixed32` diễn giải như số nguyên không dấu 32-bit. Cùng độ dài không có nghĩa cùng giá trị.

## 3. Cùng wire type không có nghĩa cùng semantics

Một số cặp kiểu có cùng wire type nhưng không thể đổi tùy tiện:

| Kiểu cũ | Kiểu mới | Cùng wire type? | Rủi ro chính |
| --- | --- | --- | --- |
| `int32` | `sint32` | Có, varint | `sint32` dùng ZigZag encoding; giá trị âm được mã hóa khác |
| `int32` | `uint32` | Có, varint | Miền signed/unsigned khác; giá trị âm và giá trị lớn có thể bị hiểu sai |
| `int32` | `bool` | Có, varint | Số nguyên bị diễn giải như false/true; mọi giá trị khác 0 thành true |
| `int32` | enum | Có, varint | Numeric value có thể không thuộc enum; generated API và semantics khác |
| `float` | `fixed32` | Có, 32-bit | Bit pattern IEEE 754 bị đọc như số nguyên |
| `double` | `fixed64` | Có, 64-bit | Bit pattern IEEE 754 bị đọc như số nguyên |
| `string` | `bytes` | Có, length-delimited | Chuỗi UTF-8 và dãy bytes tùy ý có quy tắc khác nhau |
| `string` | embedded message | Có, length-delimited | Bytes văn bản bị diễn giải thành các tag/field của message |
| `bytes` | embedded message | Có, length-delimited | Payload bytes có thể không phải message hợp lệ hoặc mang schema khác |

Với những thay đổi như `int32` sang `int64`, wire type vẫn là varint và một số giá trị có thể đọc được. Tuy nhiên, miền giá trị thay đổi; dữ liệu vượt phạm vi kiểu cũ không thể được biểu diễn đầy đủ bởi client cũ. Phải đánh giá cả giá trị âm, giới hạn số và hành vi của mọi phiên bản consumer.

**Không dùng “cùng wire type” làm tiêu chí duy nhất để duyệt đổi kiểu.** Cần xét encoding cụ thể, miền giá trị, presence, cardinality và ý nghĩa nghiệp vụ.

## 4. Ví dụ: đổi int32 sang sint32 làm sai cách đọc số âm

Schema v1:

```proto
syntax = "proto3";

package telemetry.v1;

message Reading {
  int32 offset = 1;
}
```

Schema v2 nếu đổi kiểu tại chỗ:

```proto
syntax = "proto3";

package telemetry.v1;

message Reading {
  sint32 offset = 1;
}
```

Cả hai field đều dùng wire type 0, nhưng encoding khác nhau:

- `int32` dùng varint theo biểu diễn integer của Protobuf; số âm thường cần encoding dài.
- `sint32` dùng ZigZag để ánh xạ số âm/dương sang các số không âm nhỏ hơn trước khi mã hóa varint.
- Khi một phiên bản parse bytes do phiên bản kia tạo, parser áp dụng cách giải mã của kiểu mà nó biết.

Vì vậy, cùng field number và cùng wire type không bảo đảm số âm giữ nguyên giá trị. Nếu dữ liệu có thể âm, lỗi có thể xuất hiện dù message parse thành công.

Tương tự, đổi `float` thành `fixed32` có thể làm giá trị như 1.5 trở thành một số nguyên lớn khi được diễn giải theo bit pattern. Đổi `string` thành `bytes` có thể làm thay đổi validation UTF-8 và API generated. Những thay đổi này cần được coi là breaking change trong hợp đồng đã phát hành.

## 5. Khác wire type thường làm field không được đọc như mong đợi

Nếu kiểu mới có wire type khác, parser không tự chuyển đổi giá trị sang kiểu mới.

Ví dụ, schema cũ có:

```proto
message Product {
  int32 quantity = 1;
}
```

Nếu schema mới đổi `quantity` thành `string` nhưng giữ number 1, wire type thay đổi từ varint sang length-delimited. Client cũ và mới không có quy tắc tự chuyển integer thành chuỗi. Tùy payload và parser, field có thể bị coi là unknown hoặc parse thất bại do cấu trúc không phù hợp.

Không nên dựa vào unknown-field handling như một cơ chế migration. Việc một parser bỏ qua field không có nghĩa consumer vẫn hiểu đúng nghiệp vụ; giá trị quan trọng có thể biến mất khỏi API ứng dụng.

Nếu thay đổi kiểu có chủ đích, hãy thêm field mới với number mới và giữ field cũ trong giai đoạn chuyển tiếp. Không thay kiểu của field đang được client/server hoặc dữ liệu lưu trữ sử dụng.

## 6. Cardinality và packed encoding cũng là một phần của hợp đồng

Đổi từ scalar đơn sang `repeated`, hoặc ngược lại, không chỉ là đổi kiểu Java.

Ví dụ:

```proto
// Schema cũ
message Score {
  int32 value = 1;
}
```

```proto
// Schema mới
message Score {
  repeated int32 value = 1;
}
```

Với repeated numeric field, Protobuf có thể dùng packed encoding: nhiều giá trị được đặt trong một payload length-delimited. Parser Protobuf hỗ trợ packed/unpacked cho các repeated scalar kiểu có thể pack theo quy tắc chuẩn, nhưng điều đó không làm thay đổi cardinality thành tương thích hoàn toàn.

Các rủi ro:

- Client mới đọc payload scalar cũ như danh sách có một phần tử, nhưng logic mới có thể kỳ vọng nhiều giá trị.
- Client cũ đọc nhiều occurrence unpacked của field scalar có thể chỉ giữ giá trị cuối cùng.
- Client cũ không thể diễn giải một packed list như một scalar thông thường chỉ nhờ cùng field number.
- Generated Java API đổi từ getter scalar sang list getter; source code cần thay đổi.

`map<K,V>` cũng được mã hóa như repeated entry message. Đổi giữa map, repeated message và scalar có thể giữ một số cấu trúc length-delimited nhưng thay đổi semantics và API. Hãy coi thay đổi cardinality/map là một thay đổi hợp đồng cần migration riêng.

## 7. Presence, enum và oneof

### Presence

Đổi giữa scalar implicit presence và explicit presence có thể không đổi wire tag, nhưng thay đổi cách ứng dụng phân biệt field vắng mặt với field mang giá trị mặc định. Ví dụ, `optional int32 count` có API presence như `hasCount()`, trong khi scalar proto3 không optional thường chỉ cho getter trả 0 khi không có giá trị.

Nếu code nghiệp vụ dựa vào `hasX()`, đổi presence có thể làm thay đổi hành vi dù payload vẫn parse.

### Enum

Enum dùng varint. Đổi field enum sang `int32` hoặc ngược lại có thể giữ wire type nhưng làm thay đổi generated API và cách xử lý numeric value chưa biết. Với Java Protobuf, enum có thể có sentinel `UNRECOGNIZED`; code cần có nhánh xử lý thay vì giả định mọi số đều map thành một enum constant đã biết.

Không đổi enum sang kiểu số chỉ để “dễ mở rộng”. Nếu cần giá trị mới, cân nhắc thêm enum value mới với number chưa dùng và kiểm tra logic client cũ.

### Oneof

Đưa field vào hoặc ra `oneof` làm thay đổi semantics về việc các field có thể cùng tồn tại hay không. Payload binary vẫn có thể parse, nhưng generated API và trạng thái lựa chọn thay đổi. Không thay đổi membership của `oneof` mà không kiểm tra dữ liệu có nhiều field cùng xuất hiện và cách các phiên bản xử lý.

## 8. Generated Java API và domain semantics

Ngay cả khi binary payload parse được, thay đổi kiểu vẫn có thể phá source compatibility:

- Getter/setter đổi kiểu trả về hoặc tham số.
- `string`/`bytes` dùng API Java khác nhau (`String` và `ByteString`).
- Scalar chuyển thành list làm thay đổi cấu trúc getter.
- Enum chuyển thành số nguyên làm mất enum-specific API.
- Optional/presence làm xuất hiện hoặc thay đổi các method kiểm tra presence.

Ngoài generated API, kiểu mới có thể làm đổi ý nghĩa nghiệp vụ. Ví dụ `quantity` đổi từ `int32` sang `string` để nhận giá trị như `"unknown"` sẽ trộn dữ liệu số với trạng thái văn bản. Một model domain có thể cần biểu diễn rõ trường hợp quantity đã biết và chưa biết bằng message/oneof hoặc field trạng thái riêng, thay vì dùng kiểu chuỗi cho tiện.

Ở ranh giới Spring service, gateway/endpoint nên chuyển đổi Protobuf DTO sang domain model. Điều đó giúp ứng dụng kiểm soát validation và fallback, nhưng adapter không thể sửa được một wire contract đã bị đổi nghĩa nếu dữ liệu cũ đã được parse sai.

## 9. Cách thay đổi kiểu an toàn bằng field number mới

Giả sử field cũ là `int32 quantity = 4` nhưng phiên bản mới cần hỗ trợ giá trị lớn hơn. Không đổi trực tiếp thành `int64` trên number 4 nếu contract đã được phát hành và cần bảo đảm mọi consumer.

Có thể thêm field mới:

```proto
message InventoryItem {
  string sku = 1;

  int32 quantity = 4 [deprecated = true];
  int64 quantity_v2 = 7;
}
```

Một lộ trình migration:

1. **Mở rộng schema:** thêm field mới bằng number chưa từng dùng; giữ field cũ.
2. **Nâng server:** đọc field cũ và mới theo quy tắc ưu tiên rõ ràng; trong giai đoạn chuyển tiếp, có thể ghi cả hai nếu giá trị nằm trong miền field cũ.
3. **Nâng client:** đọc field mới trước; dùng field cũ làm fallback khi server cũ chưa cung cấp field mới.
4. **Kiểm tra dữ liệu:** xác định giá trị cũ có nằm trong miền mới và có thể chuyển đổi không mất mát không.
5. **Chuyển consumer:** cập nhật mọi client, batch job, event consumer và persistence adapter.
6. **Ngừng ghi field cũ:** chỉ sau khi xác minh không còn consumer cần nó.
7. **Xóa field cũ và reserve number/name:** thực hiện trong một thay đổi schema riêng sau giai đoạn chuyển tiếp.

Nếu cả hai field cùng xuất hiện trong request, phải quy định rõ precedence hoặc từ chối trường hợp hai giá trị mâu thuẫn. Không để mỗi server replica tự chọn quy tắc khác nhau. Với response, ghi song song hai field chỉ khi có thể biểu diễn cùng một ý nghĩa và việc chuyển đổi không mất dữ liệu.

Nếu không thể biểu diễn dữ liệu mới trong field cũ, không ép giá trị mới vào field cũ bằng truncation, saturation hoặc chuỗi giả. Giữ hai field song song cho tới khi toàn bộ consumer đã chuyển.

## 10. Kiểm thử compatibility giữa schema cũ và mới

Giữ generated source hoặc contract artifact từ schema v1 làm fixture. Đừng chỉ biên dịch schema v2 rồi test client v2 với server v2; cách đó không kiểm tra phiên bản đang tồn tại ngoài production.

Một bộ kiểm thử nên bao gồm:

| Kiểm thử | Điều cần xác nhận |
| --- | --- |
| v1 serialize → v2 parse | Server/client mới đọc payload cũ theo fallback đã thiết kế |
| v2 serialize → v1 parse | Consumer cũ không bị lỗi ngoài dự kiến; field mới được xử lý theo compatibility policy |
| Old client → new server | RPC và semantics của request/response cũ còn đúng |
| New client → old server | Client mới xử lý field absent/default và capability cũ |
| Boundary values | 0, số âm, min/max, giá trị vượt miền cũ, empty string/bytes |
| Repeated/oneof/presence | Không mất phần tử hoặc thay đổi lựa chọn ngoài ý muốn |
| Stored payload fixtures | Dữ liệu đã lưu vẫn đọc được hoặc được migrate có kiểm soát |

Ví dụ test message-level khi chuyển từ schema v1 sang v2 bằng field mới:

```java
// Generated types v1 và v2 được đặt trong fixture/module riêng.
InventoryItemV1 oldItem = InventoryItemV1.newBuilder()
    .setSku("SKU-100")
    .setQuantity(120)
    .build();

byte[] payload = oldItem.toByteArray();

InventoryItemV2 newItem = InventoryItemV2.parseFrom(payload);

assertEquals("SKU-100", newItem.getSku());
// quantity_v2 không có trong payload cũ; ứng dụng phải fallback
// sang quantity theo chính sách migration.
```

Đây là ví dụ minh họa; adapter v2 phải tự áp dụng fallback từ `quantity` sang `quantity_v2` nếu cần. Protobuf parser không tự copy giá trị giữa hai field có number khác nhau.

Với thay đổi kiểu tại cùng field number, hãy tạo test chứng minh cụ thể cách parser cũ và mới diễn giải payload; nếu kết quả không đúng semantics, coi thay đổi là không tương thích và chuyển sang field number mới.

## 11. Dùng schema compatibility checks trong CI

`protoc` kiểm tra cú pháp và một số xung đột schema, nhưng không thể tự hiểu mọi thay đổi có làm sai nghiệp vụ hay không. Một schema mới vẫn có thể compile dù đổi `int32` thành `sint32`, `float` thành `fixed32` hoặc đổi semantics của một field.

CI nên có:

- Lint schema để kiểm tra quy ước field, type và naming.
- Breaking-change detection so với baseline schema đã phát hành.
- Generated code compile cho các module client/server.
- Test fixtures serialize từ schema cũ.
- Integration test cho các tổ hợp phiên bản quan trọng.
- Review bắt buộc khi field number/type/cardinality/presence thay đổi.

Công cụ như Buf có thể chạy lint và breaking checks:

```bash
buf lint
buf breaking --against ".git#branch=main"
```

Rule set cần phù hợp chính sách của hệ thống. Một nhóm rule thiên về wire compatibility có thể cho phép một số thay đổi cùng wire type, trong khi nhóm rule strict hơn còn kiểm tra source/API compatibility. Đọc chi tiết rule đã kích hoạt; không xem một kết quả pass là bằng chứng rằng semantics nghiệp vụ không đổi.

## 12. Checklist review khi đổi kiểu field

- Field number cũ có được giữ nguyên chỉ khi kiểu và semantics thực sự không đổi?
- Wire type trước và sau là gì?
- Nếu cùng wire type, encoding cụ thể có giống nhau không?
- Miền giá trị, signedness, precision và validation có thay đổi không?
- Cardinality, packed behavior, presence và oneof membership có thay đổi không?
- Generated Java API có đổi kiểu hoặc tên method không?
- Có consumer JSON, reflection, FieldMask, database hoặc event log phụ thuộc schema không?
- Payload từ schema cũ đã được dùng làm fixture kiểm thử chưa?
- Nếu cần thay đổi semantics, field mới đã dùng number mới chưa?
- Có migration, fallback, dual-read/write và quy tắc xử lý xung đột rõ ràng không?
- Field cũ có được reserve number/name sau khi loại bỏ không?
- CI chạy schema compatibility checks với baseline đã phát hành chưa?

Với **SPRING_GRPC**, thay đổi kiểu field không thể được đánh giá chỉ bằng việc hai kiểu có cùng wire type. Wire type quyết định cách tìm và đọc vùng bytes; encoding, miền giá trị, presence, cardinality và semantics mới quyết định dữ liệu có còn đúng hay không. Khi cần đổi ý nghĩa hoặc kiểu dữ liệu, thêm field number mới, migrate theo giai đoạn và kiểm thử bằng schema đã phát hành sẽ bảo vệ client/server đang chạy lệch phiên bản.
