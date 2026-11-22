# Reserved field để ngăn tái sử dụng

## 1. Vai trò của reserved trong Protobuf

Trong **SPRING_GRPC**, file `.proto` là hợp đồng được dùng để sinh Java message, client stub và service base class. Khi một field không còn được dùng, xóa dòng khai báo khỏi message chưa đủ để bảo vệ hợp đồng trong tương lai. Một người phát triển khác có thể vô tình dùng lại field number hoặc tên đã xóa cho một ý nghĩa mới.

Protobuf cung cấp khai báo **`reserved`** để đánh dấu những number và tên không được dùng lại trong cùng message hoặc enum. Compiler sẽ từ chối schema khai báo field/value xung đột với reservation. Nhờ đó, quy tắc tương thích được lưu ngay trong schema và có thể kiểm tra mỗi lần build.

Bài này tập trung vào cách khai báo và vận hành `reserved`:

- Reserve field number và tên sau khi xóa field.
- Reserve một number, nhiều number hoặc một dải number.
- Reserve enum number và enum name.
- Đặt reservation đúng phạm vi khi field thuộc `oneof` hoặc message lồng.
- Hiểu compiler kiểm tra điều gì và những gì vẫn cần CI/review kiểm tra.
- Áp dụng quy trình xóa field an toàn trong module Protobuf dùng chung.

## 2. Reserve cả number và tên

Xét message ban đầu:

```proto
syntax = "proto3";

package catalog.v1;

message Product {
  string sku = 1;
  string legacy_label = 4;
  int64 price_cents = 5;
}
```

Sau một thời gian, ứng dụng không còn dùng `legacy_label`. Khi xóa field, schema mới nên giữ lại cả number 4 và tên `legacy_label`:

```proto
syntax = "proto3";

package catalog.v1;

message Product {
  string sku = 1;
  int64 price_cents = 5;

  reserved 4;
  reserved "legacy_label";
}
```

Hai khai báo bảo vệ hai định danh khác nhau:

| Reservation | Ngăn điều gì? |
| --- | --- |
| `reserved 4;` | Ngăn field mới sử dụng lại number 4 |
| `reserved "legacy_label";` | Ngăn field mới sử dụng lại tên `legacy_label` |

Nên khai báo cả hai khi xóa field khỏi schema đã phát hành. Number là định danh trong binary wire format; tên ảnh hưởng schema source, generated API và một số bề mặt dựa trên tên như JSON mapping.

`reserved` không phải một field mới, không tạo dữ liệu trên wire và không sinh getter/setter Java. Đây là ràng buộc ở cấp schema/compiler.

## 3. Cú pháp reserve number và range

Trong message, có thể reserve một number, nhiều number hoặc một khoảng:

```proto
message Order {
  string order_id = 1;

  reserved 2;
  reserved 4, 7, 9 to 12;
}
```

`9 to 12` bao gồm cả 9 và 12. Có thể gom các number và range trong cùng một khai báo:

```proto
message Order {
  reserved 2, 4, 7, 9 to 12;
}
```

Khi muốn reserve từ một number đến giới hạn lớn nhất, Protobuf hỗ trợ `to max`:

```proto
message HistoricalRecord {
  string id = 1;

  reserved 2 to max;
}
```

Dùng `to max` chỉ khi chủ đích là đóng toàn bộ phần còn lại của dải field number. Nếu message vẫn cần mở rộng trong tương lai, reserve đúng các number đã dùng sẽ linh hoạt hơn.

Field number hợp lệ nằm trong khoảng 1 đến 536.870.911, ngoại trừ dải 19.000 đến 19.999 được Protobuf dành riêng cho implementation. Không khai báo field mới trong dải bị cấm. Reservation không phải cách để hợp thức hóa một number vốn không được phép dùng.

### Quy tắc khi khai báo range

- Hai đầu range phải theo thứ tự tăng dần.
- Không khai báo range chồng lấn hoặc number lặp lại.
- Không reserve number đang được field khác trong cùng message sử dụng.
- Không giả định reservation của một message áp dụng cho message khác.
- Giữ reservation trong các phiên bản schema sau, kể cả khi field đã biến mất khỏi code nhiều release.

## 4. Reserve tên field

Tên field cũng có thể được reserve:

```proto
message Customer {
  string customer_id = 1;

  reserved "old_name", "legacy_status";
}
```

Tên trong `reserved` là tên field theo cú pháp `.proto`, phân biệt với tên Java getter. Ví dụ field `legacy_status` có thể sinh getter Java `getLegacyStatus()`, nhưng tên cần reserve trong schema là `"legacy_status"`.

Có thể kết hợp reserve tên và number:

```proto
message Customer {
  string customer_id = 1;

  reserved 3, 8 to 10;
  reserved "old_name", "legacy_status";
}
```

Không chỉ reserve tên mà quên number. Nếu chỉ reserve `"legacy_status"`, người khác vẫn có thể dùng number cũ cho một field tên khác và khiến payload cũ bị diễn giải theo nghĩa mới.

Cũng cần phân biệt tên field với `json_name` tùy chỉnh. Reservation tên field ngăn tái sử dụng identifier trong `.proto`; nó không tự tạo một chính sách kiểm soát mọi alias JSON do gateway hoặc adapter bên ngoài định nghĩa. Nếu hợp đồng JSON có alias riêng, cần kiểm tra và quản lý nó như một bề mặt tương thích riêng.

## 5. Reserve enum number và enum name

Enum có numeric value được truyền trên wire. Khi xóa một enum value, phải reserve cả number và tên **bên trong enum declaration**.

Schema cũ:

```proto
enum ShipmentState {
  SHIPMENT_STATE_UNSPECIFIED = 0;
  SHIPMENT_STATE_CREATED = 1;
  SHIPMENT_STATE_LEGACY_HOLD = 4;
}
```

Schema mới:

```proto
enum ShipmentState {
  SHIPMENT_STATE_UNSPECIFIED = 0;
  SHIPMENT_STATE_CREATED = 1;

  reserved 4;
  reserved "SHIPMENT_STATE_LEGACY_HOLD";
}
```

Không tái gán number 4 cho `SHIPMENT_STATE_DELIVERED`. Một payload cũ có numeric value 4 có thể bị client mới hiểu nhầm thành `DELIVERED`, dù dữ liệu ban đầu mang nghĩa `LEGACY_HOLD`.

Enum có cú pháp reserve range tương tự:

```proto
enum LegacyCode {
  CODE_UNSPECIFIED = 0;
  CODE_ACTIVE = 1;

  reserved 4, 7 to 9;
  reserved "CODE_RETIRED", "CODE_OLD_PENDING";
}
```

Reservation của enum không nằm trong message chứa field enum đó. Ví dụ `Shipment.state` dùng `ShipmentState` thì number/name của enum phải được reserve bên trong `ShipmentState`, không phải bên trong message `Shipment`.

## 6. Field thuộc oneof và message lồng

### Field đã xóa khỏi oneof

Nếu một member của `oneof` bị xóa, đặt `reserved` ở **cấp message chứa oneof**, không đặt bên trong khối `oneof`:

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

Ở đây number 3 và tên `legacy_wallet_token` đại diện cho member cũ đã bị loại bỏ. Khi payload cũ chứa tag 3, message mới không còn API generated cho member đó; field trở thành unknown. Reservation ngăn một member tương lai dùng lại number đó.

### Message lồng có phạm vi reservation riêng

Mỗi message có namespace field number riêng:

```proto
message Envelope {
  string request_id = 1;

  reserved 2;
  reserved "legacy_header";

  message Header {
    string source = 1;
    string trace_id = 2;
  }
}
```

`Envelope` reserve number 2 trong chính `Envelope`; nó không cấm `Header` sử dụng number 2. Nếu xóa field trong `Header`, phải thêm reservation bên trong `Header`.

Tương tự, một enum lồng có reservation riêng bên trong enum đó. Hãy đặt reservation tại nơi field hoặc enum value từng được khai báo; không đặt ở message ngoài chỉ vì message ngoài chứa nó.

## 7. Những lỗi khai báo thường gặp

| Lỗi | Vì sao không đúng | Cách sửa |
| --- | --- | --- |
| Chỉ reserve tên, không reserve number | Number cũ vẫn có thể được gán cho field khác | Reserve cả number và tên |
| Chỉ reserve number, bỏ tên | Identifier cũ có thể được tái sử dụng trong source/schema | Reserve cả hai khi xóa field |
| Đặt `reserved` bên trong `oneof` | Reservation là khai báo ở cấp message | Đưa `reserved` ra ngoài khối `oneof` |
| Reserve number đang được field hiện tại dùng | Schema tự mâu thuẫn | Chỉ reserve number của field đã xóa |
| Đặt enum reservation trong message chứa enum | Không đúng phạm vi enum | Đặt trong enum declaration |
| Nghĩ reservation toàn cục cho mọi message | Number được quản lý theo từng message | Reserve riêng ở mỗi message đã dùng number đó |
| Xóa reservation sau vài release | Payload cũ/backup vẫn có thể được đọc lại | Giữ reservation lâu dài |
| Dùng `reserved` để đổi nghĩa field hiện có | Reservation chỉ cấm tái sử dụng định danh đã bỏ | Thêm field mới bằng number mới và migrate |

Một thay đổi schema có thể compile nhưng vẫn phá semantics nếu reservation bị quên. Compiler chỉ có thể ngăn xung đột với những number/name đã được khai báo `reserved`; nó không thể tự biết một field đã bị xóa trong lịch sử nếu schema hiện tại không lưu lại reservation.

## 8. Quy trình xóa field và thêm reservation

Khi một field không còn cần thiết trong contract dùng chung, thực hiện theo trình tự:

1. **Xác định lịch sử field:** ghi nhận message, field number, tên, kiểu và các client/server đang dùng.
2. **Ngừng phụ thuộc nghiệp vụ:** triển khai code không còn yêu cầu field trước khi loại bỏ nó khỏi schema nếu các phiên bản cũ vẫn hoạt động.
3. **Xóa khai báo field:** bỏ field khỏi message, giữ nguyên number của mọi field còn lại.
4. **Reserve number và tên:** thêm cả hai vào đúng message.
5. **Xử lý enum/oneof:** reserve enum number/name trong enum; reserve member oneof ở cấp message.
6. **Sinh lại code:** chạy `protoc` và compile các module phụ thuộc generated artifact.
7. **Kiểm tra payload cũ:** parse fixture được serialize từ schema trước đó để xác nhận không có field cũ bị hiểu nhầm.
8. **Kiểm tra tương thích:** so sánh schema mới với baseline đã phát hành và review diff `.proto`.
9. **Giữ reservation:** không xóa các khai báo này ở những release sau.

Nếu muốn thay thế một field cũ, hãy thêm field mới bằng number chưa từng dùng, triển khai logic đọc/ghi tương thích trong giai đoạn chuyển tiếp, migrate dữ liệu rồi mới loại bỏ field cũ và reserve định danh cũ.

## 9. Buộc compiler và CI kiểm tra reservation

`protoc` kiểm tra reservation khi biên dịch schema. Ví dụ, nếu message đã có `reserved 4;` mà ai đó thêm `string payment_reference = 4;`, compiler sẽ báo lỗi vì field dùng number đã reserve. Tương tự, khai báo field có tên đã reserve cũng bị từ chối.

Một bước compile schema tối thiểu có thể chạy:

```bash
protoc \
  --proto_path=src/main/proto \
  --descriptor_set_out=build/catalog-descriptors.pb \
  src/main/proto/catalog.proto
```

Đường dẫn là ví dụ; CI cần dùng đúng include paths và import dependencies của dự án. Khi sinh Java, bước code generation hiện có cũng sẽ chạy protoc và phát hiện xung đột reservation.

Để ngăn quên thêm reservation sau khi xóa field, chỉ chạy `protoc` là chưa đủ: schema mới không còn biết field cũ từng tồn tại. CI nên so sánh với schema baseline đã phát hành bằng công cụ breaking-change detection, kết hợp lint rule và review thay đổi `.proto`. Ví dụ dùng Buf:

```bash
buf lint
buf breaking --against ".git#branch=main"
```

Cấu hình Buf và rule set cần phù hợp với chính sách của repository. Hãy giữ baseline đúng với schema đã phát hành; nếu so sánh nhầm branch hoặc chỉ so với working tree không có lịch sử, kiểm tra breaking change có thể không phát hiện việc xóa field.

Nên có hai lớp kiểm soát:

- **Compiler:** từ chối schema tái sử dụng number/name đã reserve.
- **Schema diff/CI:** phát hiện field bị xóa nhưng chưa được reserve so với baseline cũ.

## 10. Checklist review

Trước khi merge thay đổi `.proto`, kiểm tra:

- Field đã xóa được reserve number trong đúng message.
- Tên field đã xóa được reserve trong cùng message.
- Enum value đã xóa được reserve number và tên trong enum tương ứng.
- Member `oneof` đã xóa được reserve ở cấp message.
- Reservation range không chồng lấn hoặc bao gồm number đang được dùng.
- Không có khai báo field/value mới trùng với reservation.
- Các message lồng có reservation riêng đúng phạm vi.
- CI chạy `protoc`, schema lint và breaking-change check với baseline đúng.
- Có test hoặc fixture cho payload từ schema cũ nếu dữ liệu được lưu trữ/forward.
- Reservation được giữ trong schema ở các release sau.

Trong **SPRING_GRPC**, `reserved` là hàng rào ngay tại nguồn schema để bảo vệ field number và tên đã ngừng sử dụng. Khai báo đúng phạm vi, reserve cả number lẫn tên, và kết hợp compiler check với schema diff trong CI giúp ngăn một field mới vô tình nhận lại định danh cũ và diễn giải sai payload đã phát hành.
