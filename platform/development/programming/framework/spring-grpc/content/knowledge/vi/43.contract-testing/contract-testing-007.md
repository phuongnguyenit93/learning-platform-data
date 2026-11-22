# Kiểm tra backward compatibility

Trong Spring gRPC, backward compatibility là khả năng phiên bản mới tiếp tục phục vụ client cũ theo contract đã phát hành. Trong quá trình rolling deployment, server và client không được nâng cấp cùng một thời điểm: server mới có thể nhận request từ client cũ, còn server cũ vẫn có thể nhận traffic từ client mới. Vì vậy, một thay đổi compile thành công chưa đủ để kết luận API tương thích.

Kiểm tra compatibility cần xem cả protobuf wire format, generated Java API, gRPC method path/cardinality, status và metadata semantics. Bài này tập trung vào cách đánh giá hai chiều old-client/new-server và new-client/old-server, thiết kế thay đổi additive, tổ chức rollout và đưa kiểm tra vào CI.

## 1. Hai chiều tương thích phải được kiểm tra

Gọi phiên bản đang chạy là v1 và phiên bản sắp triển khai là v2:

| Client | Server | Câu hỏi cần trả lời |
| --- | --- | --- |
| v1 | v2 | Server mới có tiếp tục hiểu request và trả response mà client cũ xử lý được không? |
| v2 | v1 | Client mới có hoạt động khi server cũ chưa biết field/method mới không? |
| v2 | v2 | Tính năng mới hoạt động đúng theo contract mới không? |

Backward compatibility thường nhấn mạnh v1 client với v2 server. Nhưng trong rolling deployment, chiều v2 client với v1 server cũng quan trọng: client mới có thể được phát hành trước một số instance server mới hoặc kết nối nhầm vào vùng chưa nâng cấp.

Không phải mọi thay đổi đều phải tương thích theo cả hai chiều. Chính sách cần xác định rõ compatibility target: wire compatibility, source compatibility, JSON compatibility hay behavior compatibility. Một field rename có thể giữ binary wire format nhưng phá generated Java source hoặc JSON name.

## 2. Protobuf wire contract và field number

Protocol Buffers dùng field number cùng wire type để mã hóa field trên wire. Tên field chủ yếu ảnh hưởng source API, descriptor và JSON mapping; đổi number làm reader diễn giải bytes theo field khác.

Ví dụ v1:

```proto
syntax = "proto3";

package shop.catalog.v1;

message GetProductRequest {
  string product_id = 1;
}

message Product {
  string product_id = 1;
  string display_name = 2;
  int32 available_quantity = 3;
}
```

Một thay đổi additive ở v2 có thể thêm field number mới:

```proto
message GetProductRequest {
  string product_id = 1;
  string locale = 2;
}

message Product {
  string product_id = 1;
  string display_name = 2;
  int32 available_quantity = 3;
  optional string description = 4;
}
```

Client v1 không biết field 2/4 sẽ bỏ qua field mới khi parse. Server v2 nhận request từ client v1 sẽ thấy locale vắng mặt và phải dùng default hoặc policy tương thích. Client v2 gọi server v1 có thể nhận response không có description; client mới phải xử lý trường hợp absent/default theo contract.

Quy tắc bắt buộc:

- Không đổi field number đã phát hành.
- Không tái sử dụng number hoặc tên field đã xóa.
- Khi xóa field, reserve cả number và name.
- Không giả định field mới luôn được client/server cũ hiểu.
- Không dựa vào giá trị default để biểu thị một trạng thái nghiệp vụ nếu cần phân biệt absent với explicit default.

Ví dụ xóa field cũ:

```proto
message Product {
  string product_id = 1;
  reserved 2;
  reserved "legacy_name";
  int32 available_quantity = 3;
}
```

Nếu field cũ đã được phát hành, giữ slot reserved trong các phiên bản sau. Điều này ngăn một field mới vô tình dùng lại number mà client cũ vẫn gửi.

## 3. Field name, type, cardinality và presence

Không phải mọi thay đổi giữ field number đều tương thích đầy đủ:

| Thay đổi | Binary wire | Source/API và behavior |
| --- | --- | --- |
| Đổi field name, giữ number/type | Thường vẫn parse được | Có thể phá generated Java getter/setter, descriptor consumer và JSON field name |
| Thêm field mới với number mới | Thường tương thích | Consumer mới phải chấp nhận absent từ server cũ |
| Xóa field và reserve | Reader cũ bỏ qua field nếu còn nhận bytes | Client/server dùng field đó không còn behavior tương đương |
| Đổi scalar type | Phụ thuộc wire type và encoding | Có thể đổi semantics dù wire type giống nhau; mặc định xem là breaking |
| Singular thành repeated hoặc ngược lại | Không nên giả định tương thích | Generated API và semantics cardinality thay đổi |
| Đổi field sang oneof hoặc chuyển field giữa oneof | Có thể làm mất/đổi presence semantics | Thường là thay đổi behavior cần xem như breaking |
| Đổi implicit presence thành explicit presence | Có thể giữ bytes | Generated API và cách phân biệt absent/default thay đổi |

Ví dụ, đổi tên product_name thành display_name nhưng giữ number 2 thường không làm protobuf binary reader mất dữ liệu. Tuy vậy generated Java API đổi từ getProductName sang getDisplayName; client source cũ có thể không compile nếu generate lại từ schema mới. JSON transcoding cũng có thể dùng tên JSON khác. Do đó, wire compatibility không đồng nghĩa source hay JSON compatibility.

Thay đổi kiểu phải được đánh giá theo quy tắc protobuf cụ thể, không chỉ so sánh wire type. Hai kiểu cùng wire type vẫn có thể diễn giải bytes khác nhau. Với API công khai, cách an toàn là thêm field mới, migrate dữ liệu và consumer, sau đó reserve field cũ khi loại bỏ.

## 4. Presence, default và enum value mới

Proto3 scalar mặc định dùng implicit presence. Nếu field không được gửi, getter trả default value; client mới gọi server cũ vì thế không thể giả định field mới luôn có giá trị. Khi contract cần phân biệt absent với explicit default, dùng optional hoặc message wrapper phù hợp.

Ví dụ:

```proto
message SearchRequest {
  string query = 1;
  optional int32 page_size = 2;
}
```

Server có thể phân biệt client không gửi page_size với client chủ động gửi 0 bằng hasPageSize(). Contract test nên bao phủ cả hai trường hợp và xác định default policy cho server cũ.

Thêm enum value thường tương thích wire, nhưng consumer cũ có thể nhận numeric value chưa biết. Enum cần giá trị zero có nghĩa trung tính/unspecified và không được đổi số đã phát hành:

```proto
enum ProductState {
  PRODUCT_STATE_UNSPECIFIED = 0;
  PRODUCT_STATE_ACTIVE = 1;
  PRODUCT_STATE_ARCHIVED = 2;
}
```

Khi v2 thêm PRODUCT_STATE_PENDING = 3, code Java của consumer cũ phải xử lý enum chưa biết. Với generated Java enum, kiểm tra UNRECOGNIZED và dùng getStateValue() nếu cần giữ numeric value. Không dùng switch mặc định coi mọi giá trị chưa biết là ACTIVE hoặc trạng thái thành công.

## 5. RPC identity và cardinality cũng là contract

Protobuf package, service name và method name tạo full gRPC method path. Đổi một trong các thành phần này có thể khiến client cũ gọi vào path không còn được server đăng ký.

Ví dụ method path:

```text
/shop.catalog.v1.CatalogService/GetProduct
```

Các thay đổi sau thường phá compatibility:

- Đổi package hoặc service name.
- Rename method.
- Xóa method đang được consumer sử dụng.
- Đổi unary thành server/client/bidirectional streaming hoặc ngược lại.
- Đổi request/response message type mà không giữ method cũ.

Không chuyển một method unary đã phát hành thành streaming chỉ bằng cách sửa chữ ký proto. Hãy thêm method mới với tên rõ ràng, ví dụ WatchProducts, giữ method cũ trong giai đoạn chuyển đổi và phát hành version package/service mới nếu cần thay đổi contract lớn.

Thêm một RPC method mới thường không phá client cũ vì client cũ không gọi method đó. Nhưng client mới gọi method mới trên server cũ có thể nhận UNIMPLEMENTED. Đây là tình huống cần xử lý trong rollout và capability/version negotiation, không phải lỗi wire của message.

## 6. Status, metadata và behavior cũng phải ổn định

Protobuf schema không mô tả hết contract. Consumer có thể phụ thuộc vào:

- Status code như NOT_FOUND, INVALID_ARGUMENT, RESOURCE_EXHAUSTED hoặc UNAVAILABLE.
- Metadata key như x-request-id, x-tenant-id và kiểu ASCII/binary.
- Initial response headers và trailers.
- Ordering, pagination, idempotency và side effect.
- Deadline, cancellation và retry semantics.

Ví dụ, đổi NOT_FOUND thành INTERNAL cho cùng trường hợp không tìm thấy sản phẩm có thể khiến client hiển thị lỗi hệ thống hoặc retry sai. Đổi tên metadata key có thể làm mất correlation ID hoặc security context. Một server mới cần giữ status/metadata semantics cũ cho method v1 trong thời gian consumer v1 còn tồn tại.

Nếu cần thay đổi behavior, hãy bổ sung status/detail hoặc metadata mới theo hướng additive và giữ client cũ hoạt động. Không thêm dữ liệu nhạy cảm vào trailers để thay thế cơ chế authentication.

## 7. Kiểm thử compatibility bằng ma trận artifact

Contract test có giá trị nhất khi dùng generated code từ hai phiên bản thực tế. Giữ proto/generated client v1 làm fixture hoặc artifact version hóa; build provider v2 và chạy test với client v1.

| Test | Client artifact | Provider artifact | Điều cần xác minh |
| --- | --- | --- | --- |
| Backward wire test | v1 | v2 | Request cũ được parse, response mới vẫn đọc được |
| Forward rollout test | v2 | v1 | Client xử lý field mới vắng mặt và method chưa có |
| Current contract test | v2 | v2 | Field, status, metadata và behavior mới đúng |
| Removed API guard | v1 | v2 | Method v1 vẫn tồn tại nếu còn trong support window |
| Unknown enum test | v1 | v2 | Client cũ không crash khi nhận enum value mới |

Một provider test với in-process server có thể dùng generated stub v1 để gọi provider v2. Điều quan trọng là client stub phải thực sự được generate từ proto v1; nếu cả client và server test đều build từ proto mới thì test không kiểm tra backward compatibility.

Với new-client/old-server, chạy client v2 hướng tới server v1 và xác minh fallback hoặc status UNIMPLEMENTED cho method mới. Nếu tính năng mới bắt buộc phải có, client cần kiểm tra capability hoặc chỉ phát hành sau khi toàn bộ server pool đã nâng cấp.

## 8. Buf breaking check và descriptor artifact trong CI

Buf hỗ trợ lint và breaking-change detection. Ví dụ pipeline:

```bash
buf lint
buf breaking --against '.git#branch=main'
```

Baseline phải là contract ổn định/đã phát hành, không phải output tạm của cùng build. Chọn breaking rule theo policy của tổ chức: package versioning, public API hay compatibility target. Nếu thay đổi breaking là có chủ đích, tạo version API mới và review migration; không tắt checker chỉ để pipeline xanh.

Có thể tạo descriptor set để lưu contract đã build:

```bash
protoc \
  -I src/main/proto \
  --include_imports \
  --descriptor_set_out=build/contracts/catalog-v2.pb \
  src/main/proto/shop/catalog/v1/catalog.proto
```

Descriptor artifact giúp truy vết schema mà client/server dùng và cho phép tool phân tích contract. Không so sánh raw descriptor bytes như tiêu chí duy nhất; dùng descriptor-aware diff hoặc Buf để hiểu semantics protobuf.

CI nên chạy schema check trước khi compile/test, sau đó chạy provider tests với generated client v1 và v2. Lưu contract artifact cùng release version để khi có sự cố có thể xác định chính xác hai phía đang dùng schema nào.

## 9. Rollout theo expand-contract

Một migration an toàn thường có ba giai đoạn:

1. **Expand:** triển khai server hiểu cả request cũ và mới; response mới chỉ thêm field tùy chọn/additive, không đổi semantics cũ.
2. **Migrate consumers:** phát hành client mới, theo dõi số client cũ và việc sử dụng field/method cũ.
3. **Contract:** chỉ loại bỏ API cũ sau khi support window kết thúc và không còn consumer phụ thuộc; reserve field number/name đã xóa.

Ví dụ thêm locale vào GetProductRequest:
- Server trước tiên được cập nhật để nhận locale nếu có và dùng default khi client cũ không gửi.
- Client mới bắt đầu gửi locale.
- Theo dõi tỷ lệ request có locale và xác minh server cũ không còn nhận traffic từ client mới nếu không hiểu field.
- Nếu sau này bỏ field cũ, reserve number/name và đánh giá lại compatibility với các consumer còn được hỗ trợ.

Không dựa vào một đợt deploy atomic trong hệ thống nhiều instance. Trong thời gian rollout, load balancer có thể đưa request tới bất kỳ server version nào. Kiểm tra cả rollback: server mới có thể đã ghi dữ liệu theo semantics mới mà server cũ không hiểu. Schema compatibility không tự bảo đảm database/storage migration tương thích; cần expand-contract cho cả dữ liệu lưu trữ.

## 10. Checklist backward compatibility

- [ ] Xác định compatibility target: wire, source, JSON và behavior.
- [ ] Test cả v1 client/v2 server và v2 client/v1 server nếu rollout cần.
- [ ] Giữ nguyên field number; reserve number và name đã xóa.
- [ ] Thêm field theo hướng additive và xử lý absent/default.
- [ ] Consumer xử lý unknown enum value.
- [ ] Đánh giá field rename/type/cardinality/oneof/presence như thay đổi API.
- [ ] Giữ ổn định package, service, method path và RPC cardinality.
- [ ] Không xóa method cũ khi còn consumer được hỗ trợ.
- [ ] Giữ status, metadata, ordering và idempotency semantics đã công bố.
- [ ] Buf breaking check dùng baseline đã phát hành.
- [ ] Provider test dùng generated client từ artifact v1 thực sự.
- [ ] Rollout theo expand-migrate-contract và có kế hoạch rollback.
- [ ] Version hóa descriptor/proto artifact để truy vết release.

**Tự kiểm tra**

**Câu 1.** Vì sao thêm field protobuf thường tương thích với client cũ?

*Đáp án:* Field mới dùng number mới; client cũ không biết field đó sẽ bỏ qua khi parse. Tuy nhiên, client mới phải chấp nhận trường hợp server cũ không gửi field và trả default/absent.

**Câu 2.** Đổi tên field nhưng giữ number có phá binary compatibility không?

*Đáp án:* Thường không phá protobuf binary wire format nếu number và type giữ nguyên, nhưng có thể phá generated Java source API, descriptor consumer và JSON field name. Vì vậy cần xác định compatibility target.

**Câu 3.** Vì sao không đổi unary method thành server-streaming tại chỗ?

*Đáp án:* RPC cardinality là một phần contract và thay đổi generated stub/client interaction. Hãy thêm method mới, giữ method cũ trong giai đoạn chuyển đổi hoặc phát hành API version mới.

**Câu 4.** Vì sao test v1 client với v2 server phải dùng generated artifact v1?

*Đáp án:* Nếu generate cả hai phía từ proto v2, test chỉ xác minh phiên bản mới với chính nó và không phát hiện client cũ có thể parse hoặc gọi API mới như thế nào.

**Câu 5.** Khi nào có thể xóa field hoặc method cũ?

*Đáp án:* Sau khi support window kết thúc, consumer đã chuyển đổi và telemetry xác nhận không còn sử dụng. Với field đã xóa, vẫn reserve number và name để không tái sử dụng trong tương lai.

Kiểm tra backward compatibility phải mô phỏng các phiên bản cùng tồn tại trong production. Giữ ổn định wire identity và RPC shape, thêm thay đổi theo hướng additive, kiểm thử bằng client artifact cũ, rồi rollout theo expand-contract. Nhờ vậy Spring gRPC có thể phát hành server/client mới mà không làm gián đoạn consumer chưa nâng cấp.

