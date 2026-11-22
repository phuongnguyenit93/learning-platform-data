# Kiểm tra backward compatibility

Trong Spring gRPC, backward compatibility là khả năng phiên bản mới tiếp tục phục vụ consumer đang dùng contract cũ. Khi triển khai rolling update, client và server không được nâng cấp đồng thời: một server mới có thể nhận request từ client cũ, trong khi server cũ vẫn đang nhận traffic từ client mới. Vì vậy, việc proto compile thành công hoặc hai module Java cùng build được không đủ để chứng minh API tương thích.

Kiểm tra backward compatibility cần xem cả protobuf wire format, generated Java API, gRPC method path và cardinality, status, metadata cùng semantics nghiệp vụ. Bài này tập trung vào hai chiều tương tác giữa client/server cũ và mới, cách thiết kế thay đổi additive, kiểm thử bằng artifact đã phát hành và rollout an toàn trong hệ sinh thái Spring gRPC.

## 1. Xác định compatibility đang cần bảo vệ

Compatibility có nhiều lớp và có thể cho kết quả khác nhau:

| Lớp | Câu hỏi |
| --- | --- |
| Wire compatibility | Client cũ có parse được message do server mới gửi và ngược lại không? |
| Source compatibility | Consumer có tiếp tục compile với generated Java API mới không? |
| JSON compatibility | Tên field, enum và quy tắc JSON mapping có giữ được không? |
| RPC compatibility | Full method path và loại RPC có còn như trước không? |
| Behavioral compatibility | Status, metadata, ordering, validation và side effect có giữ semantics không? |
| Operational compatibility | Deadline, retry, TLS, authentication và rollout có hoạt động với phiên bản đang chạy không? |

Một thay đổi có thể tương thích wire nhưng phá source API. Ví dụ đổi tên field nhưng giữ nguyên field number và type thường không làm binary protobuf reader mất dữ liệu, nhưng generated Java getter/setter và JSON field name có thể thay đổi.

Trước khi review một thay đổi, xác định consumer được hỗ trợ, phiên bản baseline và loại compatibility mà module cam kết. Với API công khai, thường phải xét đồng thời wire, RPC và behavior; source compatibility cũng quan trọng nếu consumer compile trực tiếp từ proto artifact.

## 2. Kiểm tra cả hai chiều client/server

Gọi phiên bản đang chạy là v1 và phiên bản chuẩn bị phát hành là v2:

| Client | Server | Điều cần xác minh |
| --- | --- | --- |
| v1 | v2 | Server mới vẫn hiểu request cũ và trả response mà client cũ xử lý được |
| v2 | v1 | Client mới chịu được field mới vắng mặt và không gọi method chưa có |
| v2 | v2 | Tính năng mới hoạt động đúng contract mới |
| v1 | v1 | Baseline cũ vẫn chạy để đối chiếu hành vi |

Backward compatibility thường nhấn mạnh v1 client với v2 server. Tuy nhiên, trong rolling deployment, chiều v2 client với v1 server cũng quan trọng. Client mới có thể được phát hành khi một phần server pool chưa nâng cấp; nếu client lập tức gọi method mới, server cũ có thể trả UNIMPLEMENTED.

Không phải mọi thay đổi đều phải hỗ trợ mọi cặp version vô thời hạn. Hãy ghi rõ support window, ví dụ server mới phải hỗ trợ hai phiên bản client gần nhất. Chính sách này quyết định artifact nào phải được giữ làm fixture và ma trận nào phải chạy trong CI.

## 3. Giữ ổn định protobuf field number và wire semantics

Protocol Buffers dùng field number cùng wire type để mã hóa field trên wire. Tên field chủ yếu ảnh hưởng source API, descriptor và JSON mapping. Đổi field number khiến reader có thể diễn giải bytes theo field khác.

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

Thay đổi additive ở v2 có thể thêm field number mới:

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

Client v1 không biết field mới sẽ bỏ qua chúng khi parse. Server v2 nhận request từ client v1 phải xử lý locale vắng mặt bằng default hoặc policy đã công bố. Client v2 gọi server v1 có thể nhận response không có description; client mới phải chấp nhận absent/default theo semantics của field.

Các quy tắc cần giữ:

- Không đổi field number đã phát hành.
- Không tái sử dụng number hoặc tên field đã xóa.
- Khi xóa field, reserve cả number và name.
- Không giả định field mới luôn được client/server cũ hiểu.
- Không dùng default value để biểu thị trạng thái nghiệp vụ nếu cần phân biệt absent với explicit default.

Ví dụ loại bỏ field cũ:

```proto
message Product {
  string product_id = 1;
  reserved 2;
  reserved "legacy_name";
  int32 available_quantity = 3;
}
```

Reserve giữ slot cũ khỏi bị dùng lại trong tương lai. Nếu client cũ vẫn gửi field number 2, việc tái sử dụng số đó có thể làm server mới hiểu dữ liệu cũ thành một ý nghĩa khác.

## 4. Đánh giá field type, cardinality, presence và enum

Không phải mọi thay đổi giữ field number đều tương thích đầy đủ:

| Thay đổi | Rủi ro |
| --- | --- |
| Đổi field name, giữ number/type | Có thể giữ binary wire nhưng phá generated Java API và JSON mapping |
| Thêm field number mới | Thường additive; client mới phải chấp nhận field vắng mặt từ server cũ |
| Đổi scalar type | Phải xét wire type, encoding, range và semantics; không suy ra an toàn chỉ từ wire type |
| Singular thành repeated hoặc ngược lại | Thay đổi cardinality và generated API; xem là breaking nếu consumer phụ thuộc |
| Chuyển field vào/ra oneof | Có thể đổi presence và hành vi khi nhiều nhánh được set |
| Thay đổi implicit/explicit presence | Có thể giữ bytes nhưng thay đổi cách generated API phân biệt absent/default |

Ví dụ proto3 scalar implicit presence:

```proto
message SearchRequest {
  string query = 1;
  optional int32 page_size = 2;
}
```

Client có thể phân biệt page_size không được gửi với page_size được gửi bằng 0 nhờ hasPageSize(). Server cũ có thể không biết field này; client mới phải xác định default policy khi field vắng mặt.

Thêm enum value thường tương thích wire, nhưng consumer cũ có thể nhận numeric value chưa biết. Giữ nguyên số enum đã phát hành và có giá trị zero trung tính:

```proto
enum ProductState {
  PRODUCT_STATE_UNSPECIFIED = 0;
  PRODUCT_STATE_ACTIVE = 1;
  PRODUCT_STATE_ARCHIVED = 2;
}
```

Nếu v2 thêm PRODUCT_STATE_PENDING = 3, consumer Java cũ cần xử lý UNRECOGNIZED và có thể dùng getStateValue() khi cần giữ numeric value. Không mặc định mọi enum chưa biết là trạng thái thành công. Khi xóa enum value, reserve cả số và tên.

## 5. Giữ ổn định RPC identity và cardinality

Protobuf package, service name và method name tạo full gRPC method path. Đổi một trong các thành phần đó có thể khiến client cũ gọi vào path mà server mới không đăng ký.

Ví dụ:

```text
/shop.catalog.v1.CatalogService/GetProduct
```

Các thay đổi thường phá compatibility gồm đổi package/service, rename hoặc xóa method đang được consumer dùng, thay request/response type và đổi unary thành streaming hoặc ngược lại.

Không sửa một method unary đã phát hành thành streaming ngay tại chỗ. Hãy thêm method mới với tên rõ ràng, giữ method cũ trong giai đoạn chuyển đổi và phát hành package/service version mới nếu cần thay đổi lớn.

Thêm RPC method mới thường không phá client cũ vì client cũ không gọi method đó. Nhưng client mới gọi method mới trên server cũ có thể nhận UNIMPLEMENTED. Nếu tính năng mới bắt buộc, client cần capability/version negotiation hoặc chỉ được phát hành sau khi provider tương thích đã sẵn sàng.

## 6. Giữ status, metadata và behavior đã công bố

Schema không mô tả toàn bộ contract. Consumer có thể phụ thuộc vào:

- Status code như NOT_FOUND, INVALID_ARGUMENT, RESOURCE_EXHAUSTED hoặc UNAVAILABLE.
- Metadata key như x-request-id, x-tenant-id và kiểu ASCII/binary.
- Initial response headers và trailers.
- Ordering, pagination, idempotency và side effect.
- Deadline, cancellation và retry semantics.

Ví dụ, đổi NOT_FOUND thành INTERNAL cho cùng trường hợp không tìm thấy sản phẩm có thể khiến client hiển thị lỗi hệ thống hoặc retry sai. Đổi tên metadata key có thể làm mất correlation ID hoặc security context. Server mới cần giữ status và metadata semantics cũ trên method v1 trong thời gian consumer v1 còn được hỗ trợ.

Nếu cần thay đổi behavior, ưu tiên thêm khả năng theo hướng additive. Giữ contract cũ ổn định và cung cấp method/version mới cho semantics khác biệt. Không thêm credential hoặc dữ liệu nhạy cảm vào trailers để thay thế cơ chế authentication.

## 7. Kiểm thử compatibility bằng artifact version hóa

Contract test chỉ có ý nghĩa nếu client và server được build từ đúng phiên bản schema mà chúng đại diện. Giữ generated client v1 hoặc proto artifact v1 đã phát hành làm fixture; build provider v2 và gọi provider đó bằng stub v1.

| Test | Client artifact | Provider artifact | Điều cần xác minh |
| --- | --- | --- | --- |
| Backward wire test | v1 | v2 | Request cũ được parse, response mới vẫn đọc được |
| Forward rollout test | v2 | v1 | Client xử lý field mới vắng mặt và method chưa có |
| Current contract test | v2 | v2 | Field, status, metadata và behavior mới đúng |
| Removed API guard | v1 | v2 | Method v1 vẫn tồn tại trong support window |
| Unknown enum test | v1 | v2 | Client cũ không crash khi nhận enum value mới |

Provider test có thể dùng in-process server để chạy service implementation v2, nhưng stub client phải thực sự được generate từ proto v1. Nếu cả client và server test cùng dùng proto v2, test chỉ xác minh phiên bản mới với chính nó và không phát hiện vấn đề của consumer cũ.

Với v2 client/v1 server, xác minh client không phụ thuộc vào field response mới luôn có mặt. Nếu client gọi method chỉ có ở v2, kiểm tra fallback hoặc status UNIMPLEMENTED và quyết định rõ cách rollout. Đừng biến UNIMPLEMENTED thành retry vô hạn.

## 8. Dùng Buf và descriptor artifact trong CI

Buf cung cấp lint và breaking-change detection cho protobuf. Ví dụ:

```bash
buf lint
buf breaking --against '.git#branch=main'
```

Baseline phải là contract ổn định hoặc đã phát hành, không phải output tạm của cùng build. Chọn breaking rule theo policy của tổ chức: public API, package versioning hay compatibility target. Nếu thay đổi breaking là có chủ đích, phát hành API version mới và review migration; không tắt checker chỉ để pipeline xanh.

Có thể tạo descriptor set để lưu schema đã build:

```bash
protoc \
  -I src/main/proto \
  --include_imports \
  --descriptor_set_out=build/contracts/catalog-v2.pb \
  src/main/proto/shop/catalog/v1/catalog.proto
```

Descriptor artifact giúp truy vết schema mà client/server đã dùng và cung cấp đầu vào cho công cụ phân tích contract. Không so sánh raw descriptor bytes như tiêu chí duy nhất; dùng descriptor-aware diff hoặc Buf để đánh giá semantics protobuf.

CI nên chạy schema check trước khi compile/test, sau đó chạy provider verification bằng generated client v1 và v2. Lưu proto/descriptor artifact cùng release version để khi có sự cố có thể xác định hai phía đang dùng schema nào.

## 9. Rollout theo expand-migrate-contract

Một migration an toàn thường có ba giai đoạn:

1. **Expand:** triển khai server hiểu request cũ và mới; field mới có default rõ ràng, response mới chỉ thêm field theo hướng additive.
2. **Migrate consumers:** phát hành client mới, theo dõi số client cũ và việc sử dụng field/method cũ.
3. **Contract:** chỉ loại bỏ API cũ sau support window và khi telemetry xác nhận không còn consumer phụ thuộc; reserve field number/name đã xóa.

Ví dụ thêm locale vào GetProductRequest:

- Server được cập nhật trước để nhận locale nếu có và dùng default khi client cũ không gửi.
- Client mới bắt đầu gửi locale sau khi server pool tương thích đã sẵn sàng.
- Theo dõi tỷ lệ request có locale và xác minh không còn traffic tới server cũ chưa hiểu semantics mới.
- Nếu sau này bỏ field cũ, reserve number/name và đánh giá lại consumer còn được hỗ trợ.

Không dựa vào deploy atomic trong hệ thống nhiều instance. Trong rolling deployment, load balancer có thể đưa request tới bất kỳ server version nào. Kiểm tra cả rollback: server mới có thể đã ghi dữ liệu theo semantics mới mà server cũ không hiểu. Schema compatibility không tự bảo đảm database/storage migration tương thích; áp dụng expand-contract cho cả dữ liệu lưu trữ.

## 10. Checklist backward compatibility

- [ ] Xác định compatibility target: wire, source, JSON, RPC và behavior.
- [ ] Kiểm tra v1 client/v2 server và v2 client/v1 server khi rollout cần.
- [ ] Giữ nguyên field number; reserve number và name đã xóa.
- [ ] Thêm field theo hướng additive và xử lý absent/default.
- [ ] Consumer xử lý enum value chưa biết.
- [ ] Đánh giá field rename/type/cardinality/oneof/presence như thay đổi API.
- [ ] Giữ ổn định package, service, method path và RPC cardinality.
- [ ] Không xóa method cũ khi còn consumer trong support window.
- [ ] Giữ status, metadata, ordering và idempotency semantics đã công bố.
- [ ] Buf breaking check dùng baseline đã phát hành.
- [ ] Provider test dùng generated client từ artifact v1 thực sự.
- [ ] Rollout theo expand-migrate-contract và có kế hoạch rollback.
- [ ] Version hóa proto/descriptor artifact để truy vết release.

**Tự kiểm tra**

**Câu 1.** Vì sao thêm field protobuf thường tương thích với client cũ?

*Đáp án:* Field mới dùng number mới; client cũ không biết field đó sẽ bỏ qua khi parse. Client mới vẫn phải chấp nhận trường hợp server cũ không gửi field và trả absent/default.

**Câu 2.** Đổi tên field nhưng giữ number có phá binary compatibility không?

*Đáp án:* Thường không phá binary wire format nếu number và type giữ nguyên, nhưng có thể phá generated Java source API, descriptor consumer và JSON field name. Cần xác định compatibility target.

**Câu 3.** Vì sao không đổi unary method thành server-streaming tại chỗ?

*Đáp án:* RPC cardinality là một phần contract và thay đổi generated stub/client interaction. Hãy thêm method mới, giữ method cũ trong giai đoạn chuyển đổi hoặc phát hành API version mới.

**Câu 4.** Vì sao test v1 client với v2 server phải dùng generated artifact v1?

*Đáp án:* Nếu generate cả hai phía từ proto v2, test chỉ xác minh phiên bản mới với chính nó và không phát hiện client cũ có thể parse hoặc gọi API mới như thế nào.

**Câu 5.** Khi nào có thể xóa field hoặc method cũ?

*Đáp án:* Sau khi support window kết thúc, consumer đã chuyển đổi và telemetry xác nhận không còn sử dụng. Với field đã xóa, vẫn reserve number và name để không tái sử dụng trong tương lai.

Kiểm tra backward compatibility phải mô phỏng các phiên bản cùng tồn tại trong production. Giữ ổn định wire identity và RPC shape, thêm thay đổi theo hướng additive, kiểm thử bằng client artifact cũ, rồi rollout theo expand-migrate-contract. Nhờ vậy Spring gRPC có thể phát hành server/client mới mà không làm gián đoạn consumer chưa nâng cấp.
