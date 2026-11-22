# Thêm enum value và client cũ

## 1. Vì sao thêm enum value cần kiểm tra client cũ?

Trong **SPRING_GRPC**, enum Protobuf biểu diễn một tập giá trị có số định danh ổn định. Khi thêm một trạng thái mới như `PAYMENT_STATE_REVERSED`, server mới có thể gửi numeric value này trong response trong khi nhiều client vẫn đang chạy code được sinh từ schema cũ.

Ở mức binary, enum được mã hóa bằng numeric value. Vì vậy, thêm một enum value với number mới thường giữ được khả năng parse message. Tuy nhiên, **parse được không đồng nghĩa client cũ hiểu đúng ý nghĩa**. Client có thể gặp một giá trị enum mà generated code chưa biết; nếu logic cũ giả định chỉ có các trạng thái đã khai báo, nó có thể bỏ qua nhánh xử lý, trả sai kết quả hoặc gây lỗi nghiệp vụ.

Bài này tập trung vào numeric enum value và tính ổn định trên wire, hành vi của client cũ khi nhận enum value mới, khác biệt giữa proto3 open enum và proto2 closed enum, cách Java generated code biểu diễn giá trị chưa biết, thứ tự rollout và kiểm thử bằng generated client cũ.

## 2. Enum được truyền bằng numeric value

Ví dụ schema v1:

```proto
syntax = "proto3";

package payment.v1;

option java_multiple_files = true;
option java_package = "dev.example.payment.v1";

enum PaymentState {
  PAYMENT_STATE_UNSPECIFIED = 0;
  PAYMENT_STATE_PENDING = 1;
  PAYMENT_STATE_CAPTURED = 2;
  PAYMENT_STATE_FAILED = 3;
}

message PaymentReply {
  string payment_id = 1;
  PaymentState state = 2;
}
```

Tên `PAYMENT_STATE_CAPTURED` giúp code dễ đọc, nhưng binary payload mang numeric value `2`. Tên enum không được gửi như một chuỗi trong binary message.

Schema v2 có thể thêm value:

```proto
enum PaymentState {
  PAYMENT_STATE_UNSPECIFIED = 0;
  PAYMENT_STATE_PENDING = 1;
  PAYMENT_STATE_CAPTURED = 2;
  PAYMENT_STATE_FAILED = 3;
  PAYMENT_STATE_REVERSED = 4;
}
```

Việc thêm `PAYMENT_STATE_REVERSED = 4` không thay đổi number của các value cũ. Một client v1 vẫn nhận được numeric value 4 trên wire; điều cần quan tâm là runtime và generated code v1 biểu diễn numeric value chưa biết như thế nào, và logic ứng dụng xử lý ra sao.

Các quy tắc cơ bản:

- Mỗi enum value có numeric value riêng trong enum, trừ trường hợp chủ động dùng alias với `allow_alias`.
- Không thay number của enum value đã phát hành.
- Không tái sử dụng number của value đã xóa; reserve cả number và tên.
- Với proto3, value đầu tiên phải có number 0 và nên biểu diễn trạng thái mặc định/unspecified.
- Không dùng numeric value 0 như một trạng thái nghiệp vụ thành công nếu field có thể vắng mặt hoặc chưa được bên gửi thiết lập.

## 3. Client proto3 cũ nhận enum value chưa biết

Proto3 dùng **open enum semantics**: parser giữ numeric value enum chưa biết thay vì loại bỏ nó khỏi field. Generated Java API cung cấp cả getter enum và getter số nguyên.

Giả sử client v1 chỉ biết các value 0 đến 3 nhưng server v2 trả state number 4. Với Java generated code proto3:

- `getStateValue()` trả numeric value thực nhận, trong ví dụ là `4`.
- `getState()` trả `PaymentState.UNRECOGNIZED` vì generated enum v1 không có constant cho number 4.
- Client cũ không có constant `PAYMENT_STATE_REVERSED`, nhưng vẫn có thể phát hiện và ghi nhận numeric value chưa biết.

Ví dụ:

```java
PaymentReply reply = paymentStub.getPayment(
    GetPaymentRequest.newBuilder()
        .setPaymentId("PAY-42")
        .build()
);

PaymentState state = reply.getState();
int rawState = reply.getStateValue();

if (state == PaymentState.UNRECOGNIZED) {
    log.warn("Unknown payment state value: {}", rawState);
    return mapToSafeFallback(rawState);
}

return mapKnownState(state);
```

`mapToSafeFallback` là logic của ứng dụng, cần được định nghĩa theo nghiệp vụ. Không gọi `state.getNumber()` khi `state` là `UNRECOGNIZED`; dùng `getStateValue()` để giữ numeric value gốc.

Cách xử lý phụ thuộc vào ý nghĩa của enum. Với trạng thái chỉ dùng để hiển thị, client có thể hiển thị “Trạng thái mới” và ghi log. Với trạng thái ảnh hưởng đến tiền, quyền truy cập hoặc workflow, fallback phải an toàn: không tự suy đoán rằng trạng thái chưa biết là thành công, đã thanh toán hoặc được phép tiếp tục.

## 4. Vì sao switch trên enum phải có nhánh fallback?

Code client cũ thường được viết khi chỉ có một tập enum value đã biết:

```java
switch (reply.getState()) {
    case PAYMENT_STATE_PENDING:
        return "Đang chờ";
    case PAYMENT_STATE_CAPTURED:
        return "Đã thanh toán";
    case PAYMENT_STATE_FAILED:
        return "Thất bại";
    case UNRECOGNIZED:
        return "Trạng thái chưa được hỗ trợ";
    case PAYMENT_STATE_UNSPECIFIED:
    default:
        return "Chưa xác định";
}
```

Nhánh `UNRECOGNIZED` xử lý numeric value mà generated code chưa biết. Nhánh `UNSPECIFIED` xử lý giá trị 0, thường là mặc định hoặc chưa được thiết lập. Hai trường hợp này khác nhau:

- `UNSPECIFIED`: một enum constant có thật trong schema.
- `UNRECOGNIZED`: numeric value không có constant tương ứng trong generated code đang chạy.

Không nên gộp mọi trường hợp vào nhánh thành công mặc định. Với logic quan trọng, nên fail closed hoặc chuyển sang trạng thái không xác định để yêu cầu xử lý tiếp, thay vì cho phép thao tác nhạy cảm dựa trên một giá trị chưa biết.

Nếu client dùng switch expression, phải đảm bảo có nhánh `UNRECOGNIZED`/default phù hợp với generated API và ngôn ngữ Java đang dùng. Mục tiêu là code cũ vẫn có hành vi an toàn khi server mở rộng enum.

## 5. Proto2 closed enum khác proto3 open enum

Không phải mọi schema Protobuf đều xử lý enum chưa biết giống nhau.

| Đặc điểm | proto3 open enum | proto2 closed enum |
| --- | --- | --- |
| Numeric value chưa khai báo | Được giữ như giá trị enum chưa biết | Thường được lưu vào unknown fields thay vì trở thành giá trị enum đã biết của field |
| Java getter enum | Có thể trả `UNRECOGNIZED` | Thường trả default enum value nếu field không có giá trị đã biết |
| Presence | Proto3 enum scalar mặc định thường dùng implicit presence, trừ khi dùng optional | Enum field có presence theo quy tắc proto2 |
| Truy cập numeric chưa biết | Java generated API proto3 có `getXValue()` | Cách quan sát phụ thuộc generated API/runtime; unknown value thường nằm trong unknown fields |

Với proto2 closed enum, một client cũ có thể không nhìn thấy value mới qua getter enum; field có thể được coi là chưa được set, trong khi numeric tag được giữ trong unknown fields. Khi message được serialize lại, runtime có thể bảo toàn unknown data, nhưng logic ứng dụng vẫn không hiểu trạng thái mới.

Vì vậy, không thể áp dụng máy móc ví dụ `UNRECOGNIZED` của proto3 cho proto2. Nếu hệ thống có proto2 schema hoặc mixed syntax, hãy kiểm tra generated API và runtime cụ thể bằng test với numeric value chưa biết.

## 6. Thêm enum value có wire-compatible nhưng vẫn có thể phá nghiệp vụ

Thêm một enum value mới thường được xem là thay đổi tương thích ở binary wire level vì các value cũ giữ nguyên numeric number và parser có thể xử lý numeric value chưa biết theo syntax/runtime. Nhưng code ứng dụng có thể không tương thích.

Một số ví dụ:

- Client cũ dùng `switch` và mặc định mọi trạng thái không nằm trong ba case đã biết là lỗi lập trình.
- Client cũ ánh xạ `UNRECOGNIZED` thành `PAYMENT_STATE_UNSPECIFIED`, khiến dashboard mất khả năng phân biệt trạng thái mới với dữ liệu thiếu.
- Một workflow coi mọi trạng thái khác `FAILED` là `CAPTURED`, dẫn tới xử lý sai khi xuất hiện `REVERSED`.
- Client cũ gửi enum mới trong request nhưng server cũ không hiểu ý nghĩa và tiếp tục xử lý theo default.

Đây là khác biệt giữa **wire compatibility** và **behavioral compatibility**. Schema có thể parse được nhưng quyết định nghiệp vụ vẫn sai.

## 7. Chiều client mới gửi value mới tới server cũ

Tình huống ngược lại cũng cần được kiểm soát. Client v2 có constant `PAYMENT_STATE_REVERSED` và gửi numeric value 4 trong request tới server v1.

Với proto3 open enum, server v1 có thể parse message và giữ numeric value chưa biết. Nhưng generated code/server logic v1 không có constant để thực hiện hành vi mới. Nó có thể nhận `UNRECOGNIZED` và raw number 4; nếu code cũ không có nhánh an toàn, có thể bỏ qua hoặc xử lý sai.

Với proto2 closed enum, value chưa biết thường được giữ trong unknown fields và field enum được quan sát như chưa có giá trị đã biết. Server v1 có thể dùng default value nếu code không kiểm tra presence.

Vì vậy:

- Không để client mới gửi value mới tới server cũ trước khi server có khả năng xử lý.
- Nếu request mang enum mới, cần rollout server hỗ trợ trước rồi mới bật client gửi value đó.
- Nếu server có nhiều replica, bảo đảm mọi replica nhận traffic đã hỗ trợ value mới trước khi bật feature flag.
- Nếu cần, dùng capability RPC hoặc feature negotiation để xác nhận server hỗ trợ tính năng.

## 8. Thêm enum value an toàn

Khi cần thêm trạng thái mới, thực hiện theo trình tự:

1. Chọn numeric value chưa từng được dùng trong enum.
2. Giữ nguyên number và ý nghĩa của mọi enum value cũ.
3. Thêm value mới với tên có prefix rõ ràng, nhất quán với enum hiện tại.
4. Cập nhật server để nhận diện và xử lý value mới.
5. Rà soát client cũ: bảo đảm có fallback cho unknown value, nhất là logic bảo mật/tài chính/workflow.
6. Triển khai server trước nếu client sẽ gửi value mới trong request.
7. Chỉ bật việc gửi/tiêu thụ trạng thái mới sau khi các server và consumer liên quan đã sẵn sàng.
8. Khi xóa một enum value trong tương lai, reserve cả number và tên trong enum.

Ví dụ enum v2:

```proto
enum PaymentState {
  PAYMENT_STATE_UNSPECIFIED = 0;
  PAYMENT_STATE_PENDING = 1;
  PAYMENT_STATE_CAPTURED = 2;
  PAYMENT_STATE_FAILED = 3;
  PAYMENT_STATE_REVERSED = 4;
}
```

Không đổi number của `PENDING`, `CAPTURED` hoặc `FAILED` để “sắp xếp lại” danh sách. Thứ tự khai báo không phải cơ chế versioning; numeric value là một phần của wire contract.

## 9. Kiểm thử bằng generated client cũ

Kiểm thử quan trọng nhất là dùng code được sinh từ schema cũ để parse message chứa enum number mới.

Với proto3, có thể kiểm tra:

```java
// Generated class từ schema v1, chỉ biết enum values 0..3.
PaymentReply oldClientReply = PaymentReply.parseFrom(
    newServerPayload
);

assertEquals(4, oldClientReply.getStateValue());
assertEquals(
    PaymentState.UNRECOGNIZED,
    oldClientReply.getState()
);
```

Trong test thực tế, generated code v1 và v2 có thể cùng fully qualified class name. Đặt chúng trong module/package fixture riêng hoặc artifact version riêng để tránh trùng class; không đổi Protobuf wire package chỉ để né xung đột test.

Bộ test nên bao gồm:

| Test | Điều cần xác nhận |
| --- | --- |
| v2 serialize → v1 parse | Client proto3 cũ giữ được numeric value và nhận `UNRECOGNIZED` |
| v1 serialize → v2 parse | Server/client mới đọc đúng enum value cũ |
| v2 client → v1 server | Server cũ xử lý value chưa biết theo fallback an toàn |
| v1 client → v2 server | Client cũ không crash khi response có enum mới |
| Unknown numeric value ngoài dự kiến | Không được mặc định thành success hoặc quyền truy cập |
| Proto2 nếu còn sử dụng | Kiểm tra presence và unknown-field behavior bằng generated runtime thực tế |

Ngoài message-level test, nên có integration test qua gRPC stub thật để xác minh serialization, server method và status end-to-end. Test riêng logic mapping của client để chứng minh `UNRECOGNIZED` không dẫn tới hành động nguy hiểm.

## 10. Giữ number enum ổn định và reserve value đã xóa

Không tái sử dụng numeric value đã xóa. Ví dụ:

```proto
enum PaymentState {
  PAYMENT_STATE_UNSPECIFIED = 0;
  PAYMENT_STATE_PENDING = 1;
  PAYMENT_STATE_CAPTURED = 2;

  reserved 3;
  reserved "PAYMENT_STATE_FAILED";

  PAYMENT_STATE_REVERSED = 4;
}
```

Reservation nằm bên trong enum. Nó ngăn người phát triển khác gán number 3 hoặc tên `PAYMENT_STATE_FAILED` cho một trạng thái mới. Không xóa reservation chỉ vì trạng thái đã ngừng xuất hiện trong code; payload cũ, event và backup có thể vẫn chứa numeric value đó.

Với enum có alias (`allow_alias = true`), nhiều tên có thể dùng chung number theo chủ đích. Tuy nhiên, alias không phải cách thay thế cho migration và cần được kiểm soát rõ; không gán lại number lịch sử cho ý nghĩa khác.

## 11. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Client cũ không nhận ra trạng thái mới | Generated enum không có constant mới | Xử lý `UNRECOGNIZED`, log raw numeric value và fallback |
| Client coi trạng thái mới là unspecified | Logic gộp unknown với giá trị 0 | Phân biệt `UNSPECIFIED` và unknown numeric |
| `switch` bỏ sót enum mới | Không có nhánh fallback | Thêm `UNRECOGNIZED`/default và test |
| Server cũ xử lý sai request | Client gửi value mới quá sớm | Rollout server trước, dùng capability/feature flag |
| Proto2 client không thấy enum value mới | Closed enum lưu numeric value trong unknown fields | Kiểm tra presence và unknown fields theo runtime |
| Dashboard hiển thị sai trạng thái | Metric mapping chỉ biết enum constants cũ | Thêm bucket unknown và giữ raw number an toàn |
| Enum value cũ bị hiểu thành trạng thái mới | Tái sử dụng numeric value | Reserve number/name và chạy schema breaking check |

Không log dữ liệu nhạy cảm cùng raw enum value nếu payload chứa thông tin có thể nhận diện người dùng. Raw numeric value hữu ích cho chẩn đoán, nhưng cần giới hạn cardinality nếu đưa vào metrics label; không tạo một time series mới cho mọi giá trị tùy ý.

## 12. Checklist trước khi phát hành enum value mới

- Numeric value mới chưa từng được dùng và không nằm trong vùng reserved.
- Number/ý nghĩa của enum value cũ không thay đổi.
- Value 0 vẫn là trạng thái unspecified/default phù hợp.
- Client proto3 cũ xử lý `UNRECOGNIZED` và raw numeric value an toàn.
- Client proto2 cũ, nếu còn tồn tại, đã được kiểm tra closed-enum/presence behavior.
- Server cũ không nhận request value mới trước khi có logic hỗ trợ.
- Server mới đã được rollout đủ trước khi bật client gửi value mới.
- Các switch/mapping/dashboard/workflow có fallback unknown.
- Có test generated client cũ parse response mới và test chiều request ngược lại.
- Enum value đã xóa được reserve number và tên.

Với **SPRING_GRPC**, thêm enum value thường giữ được binary parsing khi numeric values cũ không đổi, nhưng client cũ vẫn có thể không hiểu ý nghĩa của value mới. Cần xử lý unknown enum một cách an toàn, kiểm soát thứ tự rollout theo chiều request/response, và kiểm thử bằng generated code từ schema đã phát hành.
