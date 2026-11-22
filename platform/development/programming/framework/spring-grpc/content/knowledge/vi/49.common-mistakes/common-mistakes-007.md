# Đổi field number đã phát hành

## 1. Field number là một phần của wire contract

Trong **SPRING_GRPC**, Protocol Buffers định nghĩa cấu trúc request và response giữa các phiên bản client/server. Mỗi field trong message có một tên, một kiểu dữ liệu và một field number. Khi serialize sang binary, Protobuf không gửi tên field; nó ghi field number cùng wire type vào tag để parser nhận biết dữ liệu.

Ví dụ:

```proto
message Order {
  string order_id = 1;
  int64 total_cents = 2;
  string customer_id = 3;
}
```

Nếu đổi order_id từ field number 1 sang 4, code mới vẫn compile và có thể chạy khi cả client lẫn server cùng được build từ schema mới. Nhưng binary payload do client cũ gửi vẫn mang tag số 1. Server mới sẽ không đọc byte đó vào field order_id số 4; nó có thể coi đó là unknown field và trả về order_id rỗng/default. Ngược lại, server mới gửi field 4 thì client cũ không hiểu field đó.

Đây là lỗi tương thích ở wire format, không phải lỗi đặt tên trong Java. **Field number đã phát hành là định danh lâu dài của field trong binary contract. Không đổi số và không tái sử dụng số đã xóa.**

## 2. Wire tag gồm field number và wire type

Mỗi field được mã hóa bằng tag:

```text
tag = (field_number << 3) | wire_type
```

Wire type cho parser biết cách đọc phần payload tiếp theo, ví dụ:

| Wire type | Nhóm dữ liệu thường gặp |
| ---: | --- |
| 0 | varint: int32, int64, bool, enum |
| 1 | fixed 64-bit: fixed64, double, sfixed64 |
| 2 | length-delimited: string, bytes, embedded message, packed repeated |
| 5 | fixed 32-bit: fixed32, float, sfixed32 |

Tên field không xuất hiện trong binary tag. Parser dựa vào field number để tìm field tương ứng trong schema và wire type để đọc dữ liệu.

Khi đổi field number, parser không còn ánh xạ dữ liệu cũ vào field mới dù kiểu dữ liệu vẫn giống nhau. Khi đổi kiểu dữ liệu tại cùng field number, wire type có thể thay đổi hoặc semantics có thể khác dù wire type tình cờ giống nhau. Cả hai trường hợp đều cần compatibility review.

## 3. Ví dụ lỗi khi đổi field number

Schema đã phát hành:

```proto
message CreateOrderRequest {
  string customer_id = 1;
  int64 amount_cents = 2;
}
```

Một phiên bản sau đổi số field:

```proto
message CreateOrderRequest {
  string customer_id = 7;
  int64 amount_cents = 2;
}
```

Client cũ serialize customer_id với field number 1. Server mới chỉ khai báo customer_id ở số 7, nên dữ liệu số 1 không được gán vào customer_id. Client mới gửi số 7 tới server cũ thì server cũ cũng không biết field đó.

Hậu quả có thể không phải lỗi parse rõ ràng. Protobuf thường bỏ qua unknown field ở phía ứng dụng, khiến request được xử lý với giá trị mặc định. Với customer_id, amount, account_id hoặc quyền truy cập, lỗi này có thể dẫn đến sai dữ liệu nghiệp vụ hoặc lỗi khó phát hiện.

Đừng đánh giá compatibility chỉ bằng việc code mới compile hoặc test giữa hai process cùng phiên bản. Cần kiểm tra giao tiếp giữa schema cũ và schema mới theo các hướng client cũ/server mới và client mới/server cũ.

## 4. Không tái sử dụng field number đã xóa

Giả sử schema cũ từng có:

```proto
message Customer {
  string customer_id = 1;
  string legacy_code = 2;
  string display_name = 3;
}
```

Sau khi bỏ legacy_code, không được gán số 2 cho một field khác như phone_number. Client cũ có thể vẫn gửi field 2 với dữ liệu legacy_code. Server mới sẽ diễn giải bytes đó thành phone_number nếu kiểu wire tương thích, gây hiểu sai dữ liệu.

Cách đúng là reserve số và tên đã xóa:

```proto
message Customer {
  string customer_id = 1;
  string display_name = 3;

  reserved 2;
  reserved "legacy_code";
}
```

Reserved bảo vệ schema tương lai khỏi vô tình sử dụng lại số hoặc tên cũ. Nó không làm server mới tự hiểu dữ liệu cũ; nó chỉ ngăn tái sử dụng gây xung đột. Field đã phát hành cần được xem như lịch sử bất biến.

Nếu xóa nhiều field, có thể reserve một range:

```proto
message Customer {
  string customer_id = 1;
  reserved 2 to 5;
  reserved "legacy_code", "old_phone", "old_status";
}
```

Tên field cũng nên được reserve vì ProtoJSON và một số công cụ/schema mapping sử dụng tên field, dù binary wire format chủ yếu dựa trên number.

## 5. Quy tắc đặt field number ngay từ đầu

Chọn số có chủ đích trước khi phát hành:

- Dùng số nhỏ cho field thường xuyên xuất hiện nếu muốn encoding gọn; field number 1 đến 15 có tag ngắn hơn.
- Dành range theo nhóm nếu schema có quy ước rõ, nhưng không tạo khoảng trống quá lớn tùy tiện.
- Tránh range 19000 đến 19999 vì Protobuf dành riêng cho implementation.
- Field number hợp lệ tối đa là 2^29 - 1.
- Không dùng số âm.
- Không thay số sau khi schema đã được client/server sử dụng.
- Ghi chú rõ field deprecated và reserved khi xóa.

Field number nhỏ hơn giúp tiết kiệm một ít byte cho tag; đây là tối ưu thứ yếu so với ổn định contract. Đừng đổi number đã phát hành chỉ để sắp xếp schema đẹp hơn.

## 6. Đổi tên field khác với đổi field number

Đổi tên field nhưng giữ nguyên number thường tương thích binary wire:

```proto
// Version 1
message Order {
  string customer_id = 1;
}

// Version 2
message Order {
  string buyer_id = 1;
}
```

Binary payload vẫn mang field number 1 và server/client Protobuf có thể đọc cùng wire data. Tuy nhiên, đổi tên có thể phá ProtoJSON, generated source API, reflection, descriptor-based tooling hoặc code đang truy cập theo tên field.

Vì vậy, đổi tên không phải lúc nào cũng an toàn. Nếu API được dùng qua ProtoJSON, REST transcoding, dynamic message, JSON config hoặc codegen client, hãy kiểm tra tên JSON (bao gồm json_name), tên field và migration của consumer.

Không đổi field number chỉ vì muốn đổi tên cho đúng thuật ngữ. Nếu chỉ cần rename, giữ nguyên number và đánh giá riêng các contract dựa trên tên.

## 7. Đổi kiểu dữ liệu cũng không được suy luận chỉ từ wire type

Một số kiểu Protobuf chia sẻ wire type, nhưng điều đó không có nghĩa đổi kiểu luôn tương thích về semantics.

Ví dụ int32, int64, uint32, uint64 và bool đều dùng varint wire type. Nếu đổi int32 thành int64, parser có thể đọc wire data nhưng giá trị, range, sign semantics và client behavior có thể khác. String và embedded message đều là length-delimited nhưng bytes của chúng không thể tùy tiện diễn giải thay thế.

Các thay đổi cần review cẩn thận:

- int32 sang int64: wire type tương thích nhưng semantics/range thay đổi.
- string sang bytes: cùng length-delimited nhưng API và validation khác.
- message A sang message B: cùng wire type nhưng field bên trong có thể bị diễn giải sai.
- singular sang repeated: encoding/semantics có thể thay đổi; không giả định tương thích.
- packed/unpacked repeated numeric: Protobuf hỗ trợ một số dạng tương thích, nhưng cần kiểm tra generated/runtime và schema policy.
- map và repeated entry message: wire representation có quy tắc riêng; thay đổi vẫn cần kiểm tra semantics.

Không đổi type tại field number đã phát hành chỉ vì một compatibility checker không báo breaking. Compatibility wire-level không đảm bảo application semantics.

## 8. Thêm field mới thay vì đổi số field cũ

Nếu cần thêm dữ liệu, dùng field number chưa từng được sử dụng:

```proto
message CreateOrderRequest {
  string customer_id = 1;
  int64 amount_cents = 2;
  string source_channel = 3;
}
```

Client cũ không gửi source_channel; server mới nhận default value theo semantics Protobuf. Client mới gửi source_channel; server cũ không biết field này và thường bỏ qua ở tầng ứng dụng. Đây là kiểu additive evolution thường tương thích wire, nhưng chỉ an toàn nếu server có default behavior hợp lý và không bắt buộc client cũ phải gửi field mới.

Khi thêm field:

- Chọn field number mới.
- Xác định rõ default/absence semantics.
- Không làm server mới phụ thuộc bắt buộc vào field mà client cũ không gửi.
- Kiểm tra authorization, validation và business behavior khi field absent.
- Đảm bảo proxy/adapter không làm mất unknown fields nếu cần forward message.

Thêm field không tự động bảo đảm API behavior tương thích. Nếu field mới làm thay đổi ý nghĩa của operation, có thể cần RPC/version mới.

## 9. Migration khi thật sự cần thay một field

Không thể thay number của field đang dùng tại chỗ. Hãy thêm field mới rồi chuyển dần:

Schema chuyển tiếp:

```proto
message Customer {
  string customer_id = 1;

  string legacy_reference = 2 [deprecated = true];
  string external_reference = 7;
}
```

Một lộ trình có kiểm soát:

1. Thêm external_reference với number mới; giữ legacy_reference.
2. Deploy server đọc cả hai field, có quy tắc ưu tiên rõ ràng.
3. Server có thể tạm ghi cả hai field nếu cần hỗ trợ client cũ; bảo đảm chúng luôn nhất quán.
4. Deploy client mới đọc/ghi field mới.
5. Theo dõi usage của field cũ và phiên bản client còn gửi field cũ.
6. Khi không còn consumer cũ, ngừng ghi field cũ và deprecate/remove theo policy.
7. Xóa field cũ khỏi schema ở release sau và reserve number/name cũ.

Dual-write chỉ nên là bước migration có thời hạn. Nếu ghi hai field mà không có một nguồn sự thật hoặc quy tắc đồng bộ, dữ liệu có thể lệch. Cần xác định field nào authoritative, cách xử lý khi hai giá trị khác nhau và thời điểm dừng dual-write.

## 10. Rolling deployment và thứ tự nâng cấp

Trong môi trường có nhiều replica, phiên bản client và server không đổi cùng lúc. Một deployment có thể có client cũ gọi server mới, hoặc client mới gọi server cũ.

Khi thêm field mới có default behavior tương thích:

- Server mới thường có thể nhận request từ client cũ.
- Client mới có thể gửi field mới tới server cũ; field có thể bị bỏ qua.
- Nếu client mới yêu cầu server phải hiểu field đó để xử lý đúng, không thể dựa vào unknown-field behavior; cần capability negotiation hoặc API version mới.

Khi thay đổi semantics không tương thích, triển khai theo expand-and-contract:

1. Expand schema/server để hỗ trợ cả contract cũ và mới.
2. Deploy consumer/client mới.
3. Chuyển traffic và theo dõi usage.
4. Contract bằng cách ngừng dùng field/API cũ sau khi đã xác nhận không còn consumer.
5. Chỉ sau đó mới remove và reserve field cũ.

Không deploy client mới yêu cầu field mới trước khi toàn bộ server hỗ trợ semantics đó.

## 11. Unknown fields và proxy/adapter

Protobuf binary có thể mang unknown fields mà schema hiện tại chưa biết. Parser thường giữ unknown fields trong UnknownFieldSet của message generated, nhưng một số thao tác chuyển đổi có thể làm mất chúng, ví dụ:

- Map message sang DTO/domain object rồi dựng message mới chỉ từ field đã biết.
- Convert qua JSON mà không giữ unknown fields.
- Dùng custom serializer chỉ copy field được khai báo.
- Tạo message mới thay vì sửa builder từ message gốc.

Nếu một gateway hoặc service chỉ đóng vai trò proxy và phải forward dữ liệu tương lai, cần kiểm thử unknown-field preservation. Nếu service là boundary nghiệp vụ, việc loại bỏ field không biết có thể là chủ đích; đừng mặc định phải giữ trong mọi trường hợp.

Unknown field preservation không cứu được việc tái sử dụng field number. Nếu cùng số được gán ý nghĩa mới, bytes cũ có thể bị hiểu nhầm là dữ liệu mới thay vì unknown.

## 12. Field number trong message lồng nhau, oneof và map

Field number thuộc phạm vi của từng message, không phải toàn file .proto. Hai message khác nhau có thể cùng dùng number 1 mà không xung đột:

```proto
message Customer {
  string id = 1;
}

message Order {
  string id = 1;
  Customer customer = 2;
}
```

Tuy nhiên, trong cùng một message, number phải duy nhất và không được tái sử dụng sau khi xóa.

Với oneof, mỗi member vẫn có field number riêng; không tái sử dụng số member đã xóa. Với map, Protobuf mã hóa map như repeated entry message; field number của map field trong message cha vẫn là một định danh cần giữ ổn định.

Không di chuyển field từ message này sang message khác rồi nghĩ number cũ tự đi theo. Wire path thay đổi theo cấu trúc lồng nhau; compatibility cần đánh giá theo toàn bộ message hierarchy.

## 13. Kiểm thử schema compatibility

Không chỉ compile .proto và chạy unit test cùng phiên bản. Cần kiểm tra tương thích giữa schema versions:

| Kiểm thử | Điều cần xác nhận |
| --- | --- |
| Payload v1 đọc bằng code v2 | Field cũ vẫn ánh xạ đúng |
| Payload v2 đọc bằng code v1 | Field mới được xử lý như unknown/default an toàn |
| Client cũ gọi server mới | Request không mất ý nghĩa |
| Client mới gọi server cũ | Không phụ thuộc field server cũ không hiểu |
| Rename giữ number | Binary vẫn đọc; ProtoJSON/source API được đánh giá |
| Xóa field | Number và name được reserved |
| Enum/field evolution | Không tái sử dụng số |
| Proxy forward message | Unknown fields được giữ nếu yêu cầu |
| Rolling deploy | Mixed versions hoạt động theo compatibility matrix |

Lưu golden binary fixtures từ schema đã phát hành. Khi nâng cấp compiler/runtime hoặc schema, đọc fixture cũ bằng generated code mới và ngược lại khi có thể.

Dùng Buf breaking change detection hoặc công cụ tương đương trong CI để chặn thay đổi schema phá vỡ compatibility. Công cụ cần cấu hình baseline/version đúng; nó hỗ trợ phát hiện thay đổi cấu trúc nhưng không thay thế review semantics và runtime tests.

## 14. Checklist review

- Field number đã phát hành không bị đổi.
- Field number đã xóa không được tái sử dụng.
- Field đã xóa được khai báo reserved number và reserved name.
- Không dùng range 19000–19999.
- Field number được chọn trong giới hạn Protobuf.
- Thêm field mới bằng number mới và default/absence semantics rõ.
- Không đổi type tại cùng number nếu chưa có compatibility review.
- Rename giữ number nhưng kiểm tra ProtoJSON, reflection và generated source API.
- Migration dùng expand-and-contract; dual-write có nguồn sự thật và thời hạn.
- Rolling deployment hỗ trợ client/server mixed versions.
- Proxy preservation của unknown fields được kiểm thử nếu cần.
- Có Buf breaking check và golden wire compatibility tests.
- RPC/version mới được tạo khi semantics không thể giữ tương thích.

Trong **SPRING_GRPC**, đổi field number đã phát hành làm thay đổi wire tag mà client/server dùng để nhận diện dữ liệu, nên payload cũ có thể bị bỏ qua hoặc hiểu sai. Giữ number bất biến, reserve số và tên khi xóa, và thêm field mới khi cần mở rộng. Nếu phải thay semantics, triển khai expand-and-contract hoặc version API; xác minh bằng compatibility checks và test giữa các phiên bản client/server.
