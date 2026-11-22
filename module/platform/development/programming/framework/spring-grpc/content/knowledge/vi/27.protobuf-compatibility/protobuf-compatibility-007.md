# oneof thay đổi và tác động

## 1. oneof giải quyết vấn đề gì?

Trong **SPRING_GRPC**, Protobuf message thường có các field độc lập. Nhưng có những mô hình mà tại một thời điểm chỉ được chọn một trong nhiều cách biểu diễn, ví dụ phương thức thanh toán là thẻ, chuyển khoản hoặc ví điện tử. Protobuf cung cấp **`oneof`** để mô tả nhóm field loại trừ lẫn nhau.

Khi một member của `oneof` được đặt, các member khác trong cùng nhóm sẽ bị clear trong object đang được tạo. Cơ chế này giúp generated API biểu diễn lựa chọn hiện tại rõ ràng và tránh trạng thái có nhiều nhánh cùng được chọn trong cùng một message instance.

Thay đổi `oneof` sau khi schema đã phát hành cần được xem xét cẩn thận. Nhóm `oneof` không tạo một tag riêng trên wire; mỗi member vẫn được mã hóa bằng field number và wire type của chính nó. Vì vậy, một số thay đổi có thể giữ binary parsing nhưng làm thay đổi cách ứng dụng hiểu message.

Bài tập trung vào cách `oneof` được biểu diễn trong schema, binary wire và Java generated API; tác động khi thêm, xóa, đổi tên member; rủi ro khi chuyển field vào hoặc ra khỏi nhóm; presence, default value, unknown member; và kiểm thử/rollout an toàn khi client/server chạy lệch phiên bản.

## 2. Cấu trúc oneof trên wire

Ví dụ một message thanh toán:

```proto
syntax = "proto3";

package payment.v1;

option java_multiple_files = true;
option java_package = "dev.example.payment.v1";

message BankTransfer {
  string iban = 1;
}

message WalletPayment {
  string wallet_id = 1;
}

message PaymentMethod {
  oneof method {
    string card_token = 1;
    BankTransfer bank_transfer = 2;
    WalletPayment wallet = 3;
  }
}
```

`oneof method` là nhóm logic trong schema. Binary payload không gửi tên nhóm `method`; nếu chọn `bank_transfer`, wire message chứa field number 2 với wire encoding của message `BankTransfer`.

Điều này dẫn đến hai nguyên tắc:

- Đổi tên nhóm `oneof` không tự thay đổi binary tag của các member.
- Đổi field number hoặc kiểu của một member là thay đổi wire contract của field đó, dù member vẫn nằm trong cùng nhóm.

Các member của `oneof` không được là `repeated` hoặc `map`. Nếu cần một nhánh chứa nhiều phần tử, hãy dùng một message con có field repeated/map bên trong.

## 3. Java generated API và trạng thái lựa chọn

Protobuf Java sinh API cho từng member và cho cả nhóm. Ví dụ:

```java
PaymentMethod method = PaymentMethod.newBuilder()
    .setCardToken("card-token-123")
    .build();

assertEquals(
    PaymentMethod.MethodCase.CARD_TOKEN,
    method.getMethodCase()
);
```

Nếu builder đặt member khác sau đó, member trước bị clear:

```java
PaymentMethod method = PaymentMethod.newBuilder()
    .setCardToken("card-token-123")
    .setWallet(
        WalletPayment.newBuilder()
            .setWalletId("wallet-42")
            .build()
    )
    .build();

assertEquals(
    PaymentMethod.MethodCase.WALLET,
    method.getMethodCase()
);
```

Trong ví dụ, `WALLET` là member đang được chọn; `card_token` không còn được set. Generated API thường cung cấp getter/setter cho từng member, `getMethodCase()` để biết member nào đang được chọn, case enum với một giá trị cho mỗi member và `METHOD_NOT_SET`, cùng `clearMethod()` để xóa lựa chọn hiện tại.

Không nên chỉ đọc getter của member để xác định lựa chọn. Getter của scalar có thể trả giá trị mặc định khi member không được chọn. Dùng `getMethodCase()` hoặc presence accessor để phân biệt rõ trạng thái.

Một scalar member được set thành giá trị mặc định, ví dụ chuỗi rỗng, vẫn là member đang được chọn. `oneof` có explicit presence cho member: `getMethodCase()` vẫn trả `CARD_TOKEN`, dù `getCardToken()` là chuỗi rỗng. Đây là khác biệt quan trọng so với scalar proto3 dùng implicit presence bên ngoài `oneof`.

## 4. Thêm member mới vào oneof

Giả sử schema v1 có hai lựa chọn:

```proto
message PaymentMethod {
  oneof method {
    string card_token = 1;
    BankTransfer bank_transfer = 2;
  }
}
```

Schema v2 bổ sung ví điện tử bằng number mới:

```proto
message PaymentMethod {
  oneof method {
    string card_token = 1;
    BankTransfer bank_transfer = 2;
    WalletPayment wallet = 3;
  }
}
```

Với binary Protobuf, đây thường là thay đổi có thể parse tương thích nếu giữ nguyên các member cũ và dùng field number chưa từng dùng. Nhưng client cũ chưa biết member `wallet`:

- Khi client v1 parse payload có field 3, parser coi field đó là unknown.
- `getMethodCase()` của client v1 trả `METHOD_NOT_SET`, vì không member nào mà generated code v1 biết được đang được chọn.
- Java Protobuf runtime thường giữ unknown field khi parse rồi serialize lại message; tuy nhiên, mapping sang DTO, dựng message mới hoặc chuyển qua JSON có thể làm mất field đó.
- Client v1 không thể gọi getter để đọc `wallet_id` hoặc biết chắc lựa chọn mới có ý nghĩa gì.

Điều này tạo ra một trường hợp dễ nhầm: `METHOD_NOT_SET` có thể có nghĩa sender không chọn phương thức nào, hoặc sender đã chọn một member mới mà client cũ không biết. Không nên tự động coi hai tình huống là giống nhau trong logic nghiệp vụ.

### Chiều request và response

| Luồng phiên bản | Hành vi |
| --- | --- |
| Server mới gửi member mới → client cũ | Client cũ thấy `METHOD_NOT_SET`; member mới là unknown field |
| Server cũ gửi member cũ → client mới | Client mới nhận diện member cũ bình thường |
| Client mới gửi member mới → server cũ | Server cũ không nhận diện lựa chọn; handler có thể thấy `METHOD_NOT_SET` |
| Client cũ gửi member cũ → server mới | Server mới nhận diện lựa chọn cũ bình thường |

Nếu member mới xuất hiện trong response, client cũ cần fallback an toàn. Nếu member mới được gửi trong request, phải triển khai server hỗ trợ trước khi bật client gửi member đó. Với nhiều replica, chỉ bật tính năng khi mọi server có thể nhận request đã được nâng cấp.

## 5. Xóa member khỏi oneof

Nếu một lựa chọn không còn được hỗ trợ, xóa khai báo member nhưng reserve cả field number và tên trong message chứa `oneof`:

```proto
message PaymentMethod {
  oneof method {
    string card_token = 1;
    BankTransfer bank_transfer = 2;
  }

  reserved 3;
  reserved "wallet";
}
```

Reservation nằm ở cấp message, bên ngoài khối `oneof`. Không đặt `reserved` bên trong `oneof`.

Lý do cần reserve:

- Payload cũ có thể vẫn chứa field number 3.
- Client/server cũ có thể tiếp tục gửi member đã xóa trong giai đoạn rollout.
- Nếu number 3 được gán cho member khác, payload cũ có thể bị diễn giải thành lựa chọn mới.
- Tên cũ cũng không nên được dùng lại cho field khác trong cùng message.

Khi member bị xóa, parser mới có thể giữ field cũ như unknown field, nhưng generated API mới không còn getter hoặc case cho member đó. Không dựa vào unknown-field preservation để duy trì tính năng nghiệp vụ đã bị loại bỏ.

Nếu cần thay thế lựa chọn cũ, thêm member mới bằng number mới, hỗ trợ cả hai trong giai đoạn chuyển tiếp, migrate consumer rồi mới xóa member cũ và reserve định danh cũ.

## 6. Chuyển field độc lập vào oneof

Đây là thay đổi có rủi ro cao vì schema cũ cho phép nhiều field cùng được set, còn schema mới chỉ cho phép một member trong nhóm.

Schema v1:

```proto
message Contact {
  string email = 1;
  string phone = 2;
}
```

Schema v2 đưa hai field vào cùng `oneof`:

```proto
message Contact {
  oneof contact_method {
    string email = 1;
    string phone = 2;
  }
}
```

Một payload cũ có thể chứa cả field 1 và field 2 vì schema v1 cho phép điều đó. Khi parser v2 đọc message, hai field đều là member của cùng `oneof`; theo quy tắc parse, member xuất hiện sau cùng trên wire sẽ là lựa chọn được giữ lại. Giá trị của member còn lại không còn truy cập được qua API generated.

Do đó, dữ liệu email và phone cùng tồn tại trong payload cũ có thể bị mất một phần khi đọc bằng schema mới. Thay đổi này chỉ có thể xem xét khi hệ thống đã bảo đảm không có producer nào gửi nhiều field cùng lúc và dữ liệu lưu trữ cũ cũng tuân theo invariant đó.

Trước khi chuyển field vào `oneof`:

1. Kiểm tra tất cả producer và stored payload.
2. Đo/kiểm tra xem có message nào chứa nhiều field cùng lúc không.
3. Triển khai code chỉ ghi tối đa một member trong giai đoạn chuyển tiếp.
4. Xử lý hoặc migrate dữ liệu cũ chứa nhiều field.
5. Chỉ chuyển schema sau khi invariant được chứng minh và có test bảo vệ.

Không chỉ dựa vào việc generated builder mới tự clear member trước đó; producer cũ có thể đã serialize payload chứa cả hai field.

## 7. Chuyển field ra khỏi oneof

Chuyển member ra khỏi `oneof` làm các field trở thành độc lập trong schema mới:

Schema v1:

```proto
message Contact {
  oneof contact_method {
    string email = 1;
    string phone = 2;
  }
}
```

Schema v2:

```proto
message Contact {
  string email = 1;
  string phone = 2;
}
```

Payload được tạo bởi schema v1 chỉ có tối đa một member được chọn, nên parser v2 có thể đọc field đó thành field độc lập. Nhưng trong thời gian mixed-version, producer v2 có thể bắt đầu gửi cả email và phone. Consumer v1 vẫn xem hai field là một `oneof`; nếu cả hai xuất hiện trên wire, nó chỉ giữ member được parse sau cùng.

Vì vậy, việc chuyển field ra khỏi `oneof` chỉ an toàn cho hệ thống mixed-version khi producer mới vẫn duy trì invariant chỉ gửi tối đa một field cho tới khi mọi consumer cũ đã được nâng cấp. Nếu muốn gửi đồng thời nhiều field, phải đợi loại bỏ hoàn toàn consumer hiểu schema cũ hoặc dùng một message/version mới có semantics rõ ràng.

Ngoài wire behavior, generated API cũng thay đổi: client v2 có getter/setter độc lập thay cho `getContactMethodCase()` và các method của nhóm cũ. Code gọi API generated phải được cập nhật.

## 8. Đổi tên member hoặc tên nhóm oneof

Tên `oneof` và tên member không được mã hóa trực tiếp vào binary tag. Nếu chỉ đổi tên member nhưng giữ nguyên field number, kiểu và semantics, binary wire encoding của member đó vẫn giữ nguyên.

Ví dụ:

```proto
message PaymentMethod {
  oneof method {
    string card_credential = 1;
    BankTransfer bank_transfer = 2;
  }

  reserved "card_token";
}
```

Đổi `card_token` thành `card_credential` với number 1 giữ binary tag, nhưng làm thay đổi generated Java API như `getCardToken()` thành `getCardCredential()`, và case enum tương ứng cũng đổi. Nên reserve tên cũ để ngăn tái sử dụng.

Đổi tên nhóm `method` cũng không đổi tag của các member, nhưng có thể làm thay đổi tên accessor/case enum được sinh cho nhóm. Đây vẫn là source/API change đối với code dùng generated class.

JSON mapping sử dụng tên field member, không sử dụng tên nhóm `oneof` như một wrapper mặc định. Vì vậy, đổi tên member có thể đổi JSON key. Nếu cần giữ JSON key cũ, cân nhắc `json_name` và kiểm thử với Protobuf JSON printer/parser hoặc gateway thực tế.

## 9. Presence, unknown member và xử lý an toàn

Có ba tình huống ứng dụng cần phân biệt:

1. Không member nào được gửi.
2. Member đã biết được gửi nhưng mang giá trị mặc định, ví dụ chuỗi rỗng.
3. Member mới được gửi bởi phiên bản khác nhưng client hiện tại không biết.

Trong generated API, trường hợp 1 thường trả `METHOD_NOT_SET`; trường hợp 2 trả case tương ứng như `CARD_TOKEN` dù getter là chuỗi rỗng. Trường hợp 3 cũng có thể trả `METHOD_NOT_SET` ở client cũ, nhưng binary payload chứa unknown field.

Nếu cần chẩn đoán trường hợp 3 trong Java, có thể kiểm tra unknown fields của message theo field number đã biết từ schema mới, nhưng không nên biến việc đọc unknown field thành hợp đồng nghiệp vụ chính. Cách ổn định hơn là dùng capability/version negotiation hoặc thiết kế fallback rõ ràng.

Với lựa chọn thanh toán, quyền truy cập hoặc loại giao dịch, không diễn giải `METHOD_NOT_SET` thành một phương thức mặc định có thể thực hiện giao dịch. Hãy trả lỗi domain phù hợp hoặc yêu cầu client/server đồng bộ phiên bản.

Unknown fields có thể bị mất khi:

- Chuyển Protobuf message sang DTO rồi tạo message khác.
- Map thủ công chỉ các member được generated code hiện tại biết.
- Serialize qua JSON với parser không cho phép/không giữ field lạ.
- Một gateway hoặc intermediary dùng schema cũ để dựng lại message.

Nếu service hoạt động như proxy, cần test round-trip qua đúng intermediary và định dạng thực tế.

## 10. Kiểm thử thay đổi oneof giữa schema cũ và mới

Chỉ compile schema mới không đủ. Giữ generated type từ schema v1 làm fixture và kiểm thử các hướng tương thích.

| Kịch bản | Điều cần xác nhận |
| --- | --- |
| v2 thêm member → v1 parse | v1 thấy `METHOD_NOT_SET`, không crash; unknown field được xử lý theo chính sách |
| v1 member cũ → v2 parse | v2 nhận đúng member cũ |
| v1 có hai field độc lập → v2 chuyển vào oneof | Xác định rõ member nào thắng và có mất dữ liệu không |
| v2 bỏ oneof và gửi cả hai field → v1 parse | v1 chỉ giữ member cuối; test chứng minh producer không gửi cả hai khi còn reader cũ |
| v2 đổi tên member → v1 parse | Binary field number/type vẫn được đọc đúng |
| v1 parse rồi serialize lại | Unknown member có được giữ qua đúng runtime/intermediary hay không |
| JSON/gateway | Key cũ/mới và unknown-field policy có đúng không |

Ví dụ kiểm thử thêm member mới:

```java
// PaymentMethodV2 có member wallet = 3.
// PaymentMethodV1 chỉ biết card_token và bank_transfer.
PaymentMethodV2 newMessage = PaymentMethodV2.newBuilder()
    .setWallet(
        WalletPayment.newBuilder()
            .setWalletId("wallet-42")
            .build()
    )
    .build();

byte[] payload = newMessage.toByteArray();

PaymentMethodV1 oldMessage = PaymentMethodV1.parseFrom(payload);

assertEquals(
    PaymentMethodV1.MethodCase.METHOD_NOT_SET,
    oldMessage.getMethodCase()
);
```

Tên class v1/v2 là tên minh họa. Để giữ cùng Protobuf package/message identity nhưng compile đồng thời generated Java cũ và mới, đặt fixture trong module/package Java riêng hoặc artifact riêng. Không thay đổi wire package chỉ để né trùng class trong test.

Ngoài message-level test, chạy integration test với old client/new server và new client/old server. Kiểm tra cả status RPC, fallback nghiệp vụ và việc server cũ xử lý request có member mới.

## 11. Quy trình rollout thay đổi oneof

Một quy trình an toàn cần tách thay đổi schema khỏi thời điểm bật tính năng:

1. **Xác định thay đổi:** thêm, xóa, đổi tên, chuyển vào hay chuyển ra `oneof`; liệt kê member number/type bị ảnh hưởng.
2. **Kiểm tra producer/consumer:** tìm mọi client, server, job, queue consumer và stored payload.
3. **Bảo vệ wire identity:** giữ number/type cho member hiện có; member mới dùng number chưa từng dùng.
4. **Chuẩn bị fallback:** client cũ phải xử lý member chưa biết; server cũ không được nhận request member mới trước khi hỗ trợ.
5. **Rollout reader/server:** triển khai code có thể đọc schema mới và xử lý các lựa chọn cần thiết.
6. **Rollout writer/client:** chỉ sau khi reader hỗ trợ mới bật gửi member mới hoặc gửi nhiều field sau khi bỏ oneof.
7. **Migrate dữ liệu:** xử lý payload cũ chứa nhiều field nếu chuyển field độc lập vào oneof.
8. **Xóa member cũ:** reserve number và tên ở cấp message; giữ reservation lâu dài.
9. **Quan sát:** theo dõi `METHOD_NOT_SET`, unknown fields, lỗi domain, parse errors và các trường hợp fallback.

Nếu không thể bảo đảm invariant chỉ có một field được gửi, không chuyển các field độc lập vào cùng `oneof`. Có thể tạo message mới hoặc thêm field/nhánh mới bằng number mới để biểu diễn trạng thái mà không làm mất dữ liệu cũ.

## 12. Checklist review

- Các member hiện tại giữ nguyên field number, type và semantics.
- Member mới dùng number chưa từng được sử dụng.
- Member đã xóa được reserve number và tên ở cấp message.
- Không có member `repeated` hoặc `map` trực tiếp trong `oneof`.
- Chuyển field vào `oneof` đã kiểm tra payload cũ có nhiều member cùng lúc.
- Chuyển field ra khỏi `oneof` vẫn giữ invariant khi consumer cũ còn tồn tại.
- Code xử lý `METHOD_NOT_SET`, member default và unknown member an toàn.
- Generated Java API change đã được cập nhật trong consumer.
- JSON key, FieldMask, reflection và intermediary đã được rà soát nếu có dùng.
- Có fixture v1/v2 và integration test hai chiều.
- Rollout reader trước writer khi request mới hoặc semantics mới phụ thuộc hỗ trợ phía server.
- Schema lint/breaking check chạy với baseline đã phát hành.

Trong **SPRING_GRPC**, `oneof` vừa là quy tắc lựa chọn trong generated API vừa ảnh hưởng cách parser xử lý nhiều field trên wire. Thêm member có thể khiến client cũ thấy `METHOD_NOT_SET`; chuyển các field độc lập vào `oneof` có thể làm mất giá trị nếu payload cũ chứa nhiều field; chuyển ra ngoài có thể khiến reader cũ chỉ giữ member cuối. Đánh giá cả wire behavior, source API, dữ liệu đã lưu và thứ tự rollout trước khi thay đổi schema.
