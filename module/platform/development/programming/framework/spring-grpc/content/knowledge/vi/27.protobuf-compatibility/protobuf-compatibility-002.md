# Không tái sử dụng field number đã xóa

## 1. Vì sao field number đã xóa phải được giữ lại?

Trong **SPRING_GRPC**, Protobuf schema là hợp đồng wire giữa client, server và các thành phần trung gian. Các phiên bản có thể được triển khai lệch thời điểm; payload cũ cũng có thể tồn tại trong database, event log, cache, backup hoặc message queue lâu sau khi một field đã bị xóa khỏi source.

Khi xóa một field, **không được tái sử dụng field number của nó cho field khác trong cùng message**. Nếu tái sử dụng, payload được serialize từ schema cũ có thể được schema mới diễn giải thành dữ liệu của field mới. Trường hợp hai field dùng cùng wire type có thể parse thành công nhưng mang ý nghĩa sai, khiến lỗi dữ liệu khó phát hiện.

Ví dụ: phiên bản cũ dùng field number 4 cho tên hiển thị; phiên bản mới xóa trường đó rồi dùng number 4 cho mã thanh toán. Một payload cũ vẫn chứa chuỗi tên hiển thị ở tag 4. Khi đọc payload bằng schema mới, chuỗi đó có thể bị hiểu thành mã thanh toán. Parser không nhất thiết báo lỗi vì cấu trúc nhị phân vẫn hợp lệ.

Bài này tập trung vào:

- Quan hệ giữa field number, wire type và cách giải mã payload.
- Rủi ro khi tái sử dụng number, kể cả khi kiểu wire tương thích.
- Cách khai báo `reserved` cho field và enum đã xóa.
- Phạm vi của reserved declaration và những gì nó không bảo vệ.
- Ảnh hưởng tới payload lưu trữ, rolling deployment, JSON mapping và generated code.
- Kiểm thử để ngăn schema mới tái sử dụng field number cũ.

## 2. Field number là một phần của wire contract

Protobuf binary không gửi tên field. Mỗi field được mã hóa thành tag có dạng:

```text
tag = (field_number << 3) | wire_type
```

`field_number` xác định field trong message; `wire_type` cho parser biết cách đọc phần giá trị theo cấu trúc wire. Tên field không nằm trong binary tag, vì vậy đổi tên field không làm thay đổi tag nếu number được giữ nguyên.

Ví dụ schema phiên bản 1:

```proto
syntax = "proto3";

package billing.v1;

message Invoice {
  string invoice_id = 1;
  string display_name = 4;
  int64 amount_cents = 5;
}
```

Server v1 có thể serialize một `Invoice` chứa `display_name` vào tag mang field number 4. Tên `display_name` không được ghi vào payload binary; tag chỉ mang number và wire type.

Field number có phạm vi riêng **bên trong từng message**. Number 4 trong `Invoice` không phải cùng field với number 4 trong `Customer`. Khi xóa field, phải reserve number trong đúng message đã khai báo field đó.

Một số lưu ý về number:

- Field number hợp lệ nằm trong khoảng 1 đến 536.870.911.
- Dải 19.000 đến 19.999 được Protobuf dành riêng cho implementation; không dùng cho field.
- Number 1 đến 15 có tag encoding ngắn hơn, nhưng tối ưu kích thước không phải lý do để thay đổi number đã phát hành.
- Field number và wire semantics phải được xem là ổn định lâu dài sau khi schema đã được dùng để trao đổi hoặc lưu dữ liệu.

## 3. Tái sử dụng number có thể gây diễn giải sai dữ liệu

Giả sử phiên bản 2 xóa `display_name` rồi dùng lại number 4:

```proto
syntax = "proto3";

package billing.v1;

message Invoice {
  string invoice_id = 1;
  string payment_reference = 4;
  int64 amount_cents = 5;
}
```

Cả `display_name` và `payment_reference` đều là `string`, nên cùng dùng wire type length-delimited. Payload cũ chứa `display_name = "Priority customer"` có thể được parser của schema mới đọc thành:

```java
Invoice invoice = Invoice.parseFrom(oldPayload);

String reference = invoice.getPaymentReference();
// Có thể nhận "Priority customer" từ payload được tạo theo schema cũ.
```

Đây là lỗi nguy hiểm vì:

- Parse có thể thành công.
- Getter trả về giá trị có vẻ hợp lệ về kiểu dữ liệu.
- Ứng dụng có thể ghi chuỗi cũ vào cột hoặc gửi tiếp như một payment reference.
- Lỗi chỉ xuất hiện với payload cũ, nên test bằng message mới tạo có thể không phát hiện.

Nếu number được tái sử dụng với wire type khác, parser có thể coi tag đó là unknown, bỏ qua hoặc báo lỗi tùy cấu trúc và loại field. Dù hành vi cụ thể nào xảy ra, việc tái sử dụng vẫn phá vỡ hợp đồng và không được xem là tương thích.

**Không dựa vào việc đổi kiểu để làm number cũ “an toàn”.** Một số kiểu có cùng wire type nhưng ý nghĩa khác; một số trường hợp có thể được parser xử lý như unknown thay vì báo lỗi. Quy tắc an toàn là không tái sử dụng number đã phát hành.

## 4. Dùng reserved để khóa field number và tên đã xóa

Sau khi xóa field khỏi message, thêm reserved declaration ngay trong message đó:

```proto
syntax = "proto3";

package billing.v1;

message Invoice {
  string invoice_id = 1;
  int64 amount_cents = 5;

  reserved 4;
  reserved "display_name";
}
```

Khi ai đó vô tình khai báo lại field number 4 hoặc tên `display_name` trong message `Invoice`, `protoc` sẽ báo lỗi schema. Điều này biến quy tắc “không dùng lại” thành một ràng buộc có thể kiểm tra khi build.

Có thể reserve nhiều number hoặc một khoảng:

```proto
message Invoice {
  string invoice_id = 1;

  reserved 4, 7, 9 to 12;
  reserved "display_name", "legacy_note";
}
```

Khoảng `9 to 12` bao gồm cả hai đầu. Có thể dùng `to max` khi muốn reserve từ một number tới number lớn nhất hợp lệ, nhưng chỉ làm vậy khi thật sự muốn đóng toàn bộ phần còn lại của dải number.

Nên reserve cả:

- **Number:** ngăn dữ liệu binary cũ bị diễn giải thành field mới.
- **Tên:** ngăn tái sử dụng tên đã xóa trong schema, generated API và các công cụ dựa trên tên field.

Hai loại reservation có mục đích khác nhau; reserve tên không thay thế reserve number.

## 5. Reserved declaration bảo vệ điều gì và không bảo vệ điều gì?

`reserved` là quy tắc ở cấp schema/compiler. Nó giúp `protoc` từ chối schema mới nếu number hoặc tên đã reserve bị dùng lại trong cùng message. Nó không sửa payload cũ, không xóa dữ liệu đã lưu và không chặn một chương trình tự tạo binary tag bằng tay.

Vì vậy cần kết hợp:

1. Reserved declarations trong `.proto`.
2. Schema compatibility check trong CI.
3. Test parse dữ liệu được serialize từ schema đã phát hành.
4. Quy trình review thay đổi schema.
5. Quản lý version của contract artifact và generated code.

Reserved declaration có phạm vi cục bộ. Ví dụ `Invoice` reserve number 4 không cấm `Customer` dùng number 4; hai message có wire schema riêng. Ngược lại, nếu cùng một field number từng được dùng trong nhiều message khác nhau, phải quản lý reservation riêng trong từng message.

Không xóa reserved declaration chỉ vì đã qua một số lần release. Payload cũ có thể còn trong backup hoặc được khôi phục sau nhiều tháng/năm. Khi thời hạn lưu trữ dữ liệu không có giới hạn chắc chắn, reservation cũng nên được giữ vô thời hạn.

## 6. Enum cũng không được tái sử dụng number đã xóa

Enum Protobuf cũng có numeric value trên wire. Nếu xóa một enum value rồi gán lại number của nó cho ý nghĩa khác, client cũ hoặc dữ liệu lưu trữ có thể diễn giải numeric value cũ thành trạng thái mới.

Ví dụ schema cũ:

```proto
enum PaymentState {
  PAYMENT_STATE_UNSPECIFIED = 0;
  PAYMENT_STATE_PENDING = 1;
  PAYMENT_STATE_LEGACY_REVIEW = 4;
}
```

Nếu value 4 không còn dùng, schema mới nên reserve cả number lẫn tên:

```proto
enum PaymentState {
  PAYMENT_STATE_UNSPECIFIED = 0;
  PAYMENT_STATE_PENDING = 1;

  reserved 4;
  reserved "PAYMENT_STATE_LEGACY_REVIEW";
}
```

Không gán number 4 cho `PAYMENT_STATE_REFUNDED`. Nếu payload cũ có numeric value 4, client mới có thể hiểu nhầm một trạng thái review cũ thành refunded.

Quy tắc này áp dụng riêng cho enum: dùng `reserved` bên trong enum declaration. Reserved ở message không tự reserve numeric value của enum lồng hoặc enum được tham chiếu.

## 7. Xóa field trong oneof, đổi tên và JSON mapping

### 7.1. Field từng nằm trong oneof

Nếu xóa một member khỏi `oneof`, vẫn phải reserve field number và tên của member đó trong message:

```proto
message PaymentMethod {
  oneof method {
    string card_token = 1;
    string bank_account = 2;
  }

  reserved 3;
  reserved "legacy_wallet_token";
}
```

Trong ví dụ, number 3 và tên `legacy_wallet_token` là member cũ đã bị xóa. Reservation đặt ở cấp message, không đặt bên trong khối `oneof`.

Client cũ có thể gửi member đã bị xóa trong payload. Server mới sẽ không còn API generated để truy cập member đó; field trở thành unknown. Không tái dùng number của member đó cho một lựa chọn `oneof` khác, vì payload cũ có thể bị hiểu thành lựa chọn mới.

### 7.2. Đổi tên field nhưng giữ number

Đổi tên field trong `.proto` nhưng giữ nguyên number thường giữ tương thích binary, bởi tên không có trong tag. Tuy nhiên, việc đổi tên có thể ảnh hưởng:

- Tên getter/setter trong generated Java API.
- Tên property khi serialize sang Protobuf JSON.
- Client dùng reflection, descriptor hoặc mapping theo tên.
- Tài liệu và code sử dụng trực tiếp tên field.

Nếu chỉ muốn đổi tên source-level, hãy đánh giá các bề mặt JSON/API trước khi thay đổi. Nếu field đã bị xóa hoàn toàn, reserve tên cũ cùng number cũ để tránh tái sử dụng ngoài ý muốn.

### 7.3. JSON không có cùng quy tắc với binary tag

Protobuf JSON biểu diễn field bằng tên JSON, thường là lowerCamelCase của tên field hoặc tên được đặt trong `json_name`. Do đó, đổi tên có thể làm thay đổi JSON contract dù binary field number giữ nguyên.

Reserved name hữu ích để tránh tái sử dụng tên đã xóa trong schema, nhưng không tự bảo đảm mọi JSON gateway, mapper hoặc API consumer tương thích. Nếu message đi qua REST transcoding, kiểm thử JSON contract riêng.

## 8. Payload cũ có thể tồn tại lâu hơn vòng đời service

Không chỉ client đang chạy mới có thể giữ dữ liệu theo schema cũ. Một payload Protobuf có thể nằm trong:

- BLOB/byte array trong database.
- Event store hoặc audit log.
- Kafka, message broker hoặc dead-letter queue.
- Cache, file export và backup.
- Batch job hoặc dữ liệu được khôi phục từ snapshot.

Một service mới có thể đọc những bytes này rất lâu sau khi field đã bị xóa khỏi `.proto`. Vì vậy, “mọi replica đã nâng cấp” không phải lý do đủ để tái sử dụng number.

Nếu cần loại bỏ dữ liệu cũ, phải có migration riêng: xác định tất cả nguồn dữ liệu, chuyển đổi theo schema cũ, xác minh kết quả và quản lý backup/retention. Ngay cả khi dữ liệu chính đã migrate, backup cũ vẫn có thể được khôi phục trong tương lai. Reserved number là cách giữ schema an toàn trước những payload đó.

## 9. Kiểm thử để phát hiện tái sử dụng field number

### 9.1. Giữ schema cũ làm fixture

CI nên có một fixture hoặc module contract v1 chứa schema đã phát hành. Khi schema v2 được cập nhật:

1. Serialize một message theo schema v1 có field sắp bị xóa.
2. Parse payload bằng schema v2.
3. Xác nhận field cũ không bị gán nhầm vào field mới.
4. Kiểm tra schema v2 có reserved number/name.
5. Chạy schema breaking check để phát hiện thay đổi không tương thích.

Ví dụ message-level test minh họa:

```java
// Generated types được đặt ở hai package/module fixture riêng.
InvoiceV1 oldInvoice = InvoiceV1.newBuilder()
    .setInvoiceId("INV-42")
    .setDisplayName("Priority customer")
    .setAmountCents(2500)
    .build();

byte[] oldPayload = oldInvoice.toByteArray();

InvoiceV2 parsed = InvoiceV2.parseFrom(oldPayload);

assertEquals("INV-42", parsed.getInvoiceId());
assertEquals(2500, parsed.getAmountCents());

// Schema V2 không còn display_name và không tái dùng number 4.
// Number 4 được reserve nên không có payment_reference nhận chuỗi cũ.
```

Ví dụ giả định generated type v1/v2 đã được tạo trong package khác nhau để tránh trùng fully qualified class name. Nếu v2 tái sử dụng number 4 với kiểu string, test có thể phát hiện dữ liệu cũ xuất hiện ở getter của field mới; nhưng không nên chỉ dựa vào test runtime. `protoc` phải từ chối schema có number đã reserve.

### 9.2. Kiểm tra schema trong CI

Một pipeline có thể thực hiện các bước:

- Biên dịch tất cả `.proto` bằng đúng phiên bản `protoc`.
- Chạy schema linter để kiểm tra quy ước field/enum và reservation.
- So sánh schema mới với baseline đã phát hành bằng công cụ compatibility checker.
- Chạy test với serialized fixtures từ schema cũ.
- Sinh generated Java và compile các module client/server phụ thuộc contract.

Công cụ như Buf có thể hỗ trợ lint và breaking-change detection. Cần cấu hình baseline và rule set phù hợp với chính sách tương thích của tổ chức; không mặc định rằng mọi rule set đều phát hiện đúng mọi yêu cầu dữ liệu riêng của ứng dụng.

## 10. Quy trình xóa field an toàn

Khi một field không còn cần thiết:

1. **Xác định phạm vi sử dụng:** tìm client/server, consumer, persistence và các pipeline còn đọc hoặc ghi field.
2. **Ngừng phụ thuộc nghiệp vụ:** triển khai code không còn yêu cầu field trước khi xóa khỏi schema nếu các phiên bản cũ vẫn hoạt động.
3. **Xóa field khỏi message:** không thay đổi number của các field khác.
4. **Reserve number và tên:** thêm `reserved` trong đúng message.
5. **Với enum:** reserve numeric value và tên enum đã xóa trong chính enum đó.
6. **Sinh và kiểm tra code:** chạy `protoc`, compile các module contract/client/server.
7. **Kiểm thử payload cũ:** parse fixture từ schema trước đó bằng schema mới.
8. **Rollout:** triển khai theo thứ tự tương thích, quan sát parse errors và hành vi nghiệp vụ.
9. **Giữ reservation:** không xóa reservation ở các release sau chỉ vì field không còn xuất hiện trong code hiện tại.

Nếu cần thay thế một field, thường nên thêm field mới bằng number mới, triển khai logic đọc cả định dạng cũ và mới trong giai đoạn chuyển tiếp, migrate dữ liệu, rồi xóa field cũ và reserve number/name. Không “đổi nghĩa tại chỗ” bằng cách tái sử dụng number.

## 11. Các lỗi thường gặp

| Thay đổi | Rủi ro | Cách xử lý |
| --- | --- | --- |
| Xóa field nhưng không reserve number | Người khác có thể dùng lại number trong tương lai | Reserve number ngay trong cùng message |
| Chỉ reserve tên | Number cũ vẫn có thể bị tái sử dụng và diễn giải payload sai | Reserve cả number lẫn tên |
| Dùng lại number với cùng wire type | Payload cũ có thể parse thành field mới nhưng sai nghĩa | Dùng number mới; giữ reservation |
| Đổi kiểu field và giữ number | Parser có thể đọc sai semantics hoặc bỏ qua/error tùy wire type | Không đổi type/number đã phát hành |
| Xóa enum value nhưng không reserve | Numeric value cũ có thể mang nghĩa enum mới | Reserve enum number và tên |
| Xóa member oneof rồi dùng number đó | Payload cũ có thể được hiểu thành lựa chọn mới | Reserve ở cấp message |
| Chỉ test schema mới | Không phát hiện dữ liệu cũ bị diễn giải sai | Giữ serialized fixtures/schema baseline |
| Xóa reservation sau vài release | Backup hoặc event cũ vẫn có thể chứa tag | Giữ reservation lâu dài |

## 12. Checklist trước khi merge thay đổi schema

- Field number đã xóa được reserve trong đúng message.
- Tên field đã xóa cũng được reserve.
- Enum number và enum name đã xóa được reserve trong enum tương ứng.
- Member `oneof` đã xóa được reserve ở cấp message.
- Không có field mới nào dùng lại number đã phát hành.
- Các field còn lại giữ nguyên number, wire semantics và ý nghĩa nghiệp vụ.
- Test parse payload v1 bằng generated type v2 đã chạy.
- Schema lint/breaking check được thực hiện với baseline đúng.
- JSON mapping và API gateway đã được kiểm tra nếu có sử dụng.
- Reservation được giữ trong schema ở các release tiếp theo.

Trong **SPRING_GRPC**, field number là một phần lâu dài của hợp đồng binary. Xóa field khỏi source không làm các payload cũ biến mất. Giữ number và tên đã xóa trong `reserved`, kiểm thử bằng dữ liệu từ schema trước đó và duy trì kiểm tra schema trong CI giúp ngăn dữ liệu cũ bị diễn giải thành một field mới với ý nghĩa sai.
