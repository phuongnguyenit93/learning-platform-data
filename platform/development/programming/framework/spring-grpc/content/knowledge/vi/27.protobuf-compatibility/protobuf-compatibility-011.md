# Backward compatibility và forward compatibility

## 1. Hai hướng tương thích trong tiến hóa schema

Trong **SPRING_GRPC**, client và server có thể được build, phát hành và triển khai ở những thời điểm khác nhau. Một server mới có thể đang phục vụ client cũ; trong lúc rolling deployment, một client mới cũng có thể tạm thời gọi tới replica server cũ. Vì vậy, đánh giá một thay đổi Protobuf phải xét cả hai hướng đọc dữ liệu.

Hai khái niệm thường dùng:

- **Backward compatibility:** reader mới đọc được dữ liệu do writer cũ tạo ra. Phiên bản mới tiếp tục hiểu payload cũ.
- **Forward compatibility:** reader cũ đọc được dữ liệu do writer mới tạo ra. Phiên bản cũ có thể bỏ qua phần mở rộng mà nó chưa biết và vẫn xử lý phần dữ liệu quen thuộc.

Trong sơ đồ writer/reader:

| Hướng | Writer | Reader | Câu hỏi |
| --- | --- | --- | --- |
| Backward | v1 (cũ) | v2 (mới) | Schema mới có đọc được payload cũ không? |
| Forward | v2 (mới) | v1 (cũ) | Schema cũ có xử lý được payload mới không? |
| Full compatibility | v1 và v2 theo cả hai chiều | v1 và v2 | Các phiên bản có thể trao đổi dữ liệu theo cả hai hướng không? |

Các thuật ngữ này nói về hướng tương thích giữa writer và reader. Chúng không tự bảo đảm logic nghiệp vụ đúng. Một payload có thể parse thành công nhưng ứng dụng vẫn hiểu sai trạng thái, dùng giá trị mặc định không phù hợp hoặc bỏ qua một yêu cầu bắt buộc.

## 2. Ánh xạ hai hướng vào giao tiếp gRPC

Trong RPC, client và server đều có lúc là writer, lúc là reader:

| Tình huống | Writer → Reader | Hướng tương thích |
| --- | --- | --- |
| Client cũ gửi request tới server mới | Request v1 → server v2 | Backward |
| Client mới gửi request tới server cũ | Request v2 → server v1 | Forward |
| Server cũ trả response cho client mới | Response v1 → client v2 | Backward |
| Server mới trả response cho client cũ | Response v2 → client v1 | Forward |

Điều này giải thích vì sao câu “schema v2 tương thích” chưa đủ rõ. Cần nói rõ v2 có đọc payload v1 không, v1 có đọc payload v2 không, và đang xét request hay response.

Ví dụ, khi thêm field request mới:

- Server v2 có thể nhận request v1 không có field đó: đây là backward compatibility.
- Server v1 nhận request v2 có field mới: parser thường bỏ qua field unknown; đây là forward compatibility ở mức wire.
- Nhưng nếu client v2 cần field mới để server thực hiện đúng nghiệp vụ, server v1 bỏ qua field đó có thể trả kết quả sai. Wire compatibility không đủ để cho phép client v2 gửi request trước khi server hỗ trợ tính năng.

Trong triển khai Spring gRPC, hãy xác định hướng writer/reader cho từng RPC trước khi chọn thứ tự rollout.

## 3. Ví dụ cơ bản: thêm field mới

Schema v1:

```proto
syntax = "proto3";

package inventory.v1;

message StockRequest {
  string sku = 1;
}

message StockReply {
  string sku = 1;
  int32 available = 2;
}
```

Schema v2 bổ sung thời điểm cập nhật:

```proto
syntax = "proto3";

package inventory.v1;

message StockReply {
  string sku = 1;
  int32 available = 2;
  int64 updated_at_epoch_ms = 3;
}
```

**Backward:** reader v2 parse response được tạo bởi writer v1. Field number 3 không xuất hiện; generated field có giá trị mặc định theo kiểu và presence rule. Ứng dụng v2 phải hiểu rằng timestamp có thể chưa được cung cấp.

**Forward:** reader v1 parse response do writer v2 tạo. Field number 3 là unknown đối với schema v1. Parser binary có thể bỏ qua nó và vẫn đọc sku/available. Client v1 không thể dùng timestamp mới, nhưng vẫn có thể sử dụng các field cũ.

Đây là mẫu mở rộng phổ biến, với điều kiện:

- Không thay đổi field number hoặc wire semantics của field cũ.
- Field mới là tùy chọn về mặt tương thích; reader cũ không cần nó để hiểu các field cũ.
- Reader mới có fallback rõ ràng khi field mới vắng mặt.
- Producer không gửi field mới như điều kiện bắt buộc cho một consumer cũ.
- Các intermediary và gateway được kiểm tra nếu chúng parse rồi dựng lại message.

## 4. Giá trị mặc định và presence ảnh hưởng backward compatibility

Khi reader mới đọc payload cũ, field mới thường không xuất hiện. Ứng dụng sẽ quan sát giá trị mặc định hoặc trạng thái absent tùy kiểu field và cách khai báo.

Với proto3 scalar dùng implicit presence, getter có thể trả 0, false hoặc chuỗi rỗng khi field không được gửi. Ứng dụng không thể chỉ từ getter phân biệt “writer cũ không biết field” với “writer mới chủ động gửi giá trị mặc định”.

Nếu phân biệt absent với giá trị mặc định là quan trọng, hãy dùng explicit presence như `optional`, message field hoặc một cấu trúc phù hợp như `oneof`.

Ví dụ:

```proto
message UpdateStockRequest {
  string sku = 1;
  optional int32 reorder_level = 2;
}
```

Java generated API có thể cung cấp presence accessor như `hasReorderLevel()`. Khi request đến từ client cũ, server mới có thể kiểm tra field có được gửi hay không rồi áp dụng policy phù hợp.

Không tự coi giá trị mặc định là một quyết định nghiệp vụ. Ví dụ `reorder_level = 0` có thể có nghĩa “không cần bổ sung hàng”, trong khi field absent có thể có nghĩa “giữ cấu hình hiện tại”. Nếu hai ý nghĩa khác nhau, schema và application mapping phải biểu diễn được sự khác biệt.

## 5. Unknown fields và giới hạn của forward compatibility

Khi parser cũ gặp field number mà schema không biết, binary Protobuf runtime xử lý nó như unknown field thay vì đọc bằng một getter không tồn tại. Điều này giúp parser tiếp tục đọc các field đã biết.

Trong Java Protobuf, unknown fields thường được giữ trong message object và có thể được serialize lại. Tuy nhiên, không nên giả định dữ liệu unknown luôn sống sót qua mọi đường đi:

- Code chuyển Protobuf message sang DTO rồi tạo message mới có thể bỏ field unknown.
- Mapping thủ công chỉ copy field đã biết sẽ làm mất phần mở rộng.
- Gateway hoặc intermediary parse rồi serialize bằng JSON có thể không giữ unknown fields.
- Một service chuyển đổi sang model nội bộ rồi phát message khác cần chủ động quyết định có forward dữ liệu unknown không.

Nếu service đóng vai trò proxy, relay hoặc event forwarder, hãy kiểm tra round-trip bằng đúng runtime và adapter thực tế. Forward compatibility ở parser không đồng nghĩa mọi tầng trung gian đều bảo toàn payload mới.

## 6. Những thay đổi thường phá cả hai hướng

Một số thay đổi không an toàn dù chỉ xét backward hoặc forward:

| Thay đổi | Rủi ro |
| --- | --- |
| Tái sử dụng field number đã xóa | Payload cũ có thể bị diễn giải thành field mới |
| Đổi field number | Writer và reader gắn dữ liệu với tag khác nhau |
| Đổi type hoặc encoding tại chỗ | Cùng wire type vẫn có thể khác cách giải mã và semantics |
| Đổi ý nghĩa field nhưng giữ nguyên type/number | Parser thành công nhưng nghiệp vụ hiểu sai |
| Xóa enum number rồi gán cho ý nghĩa mới | Numeric value cũ bị hiểu thành trạng thái khác |
| Chuyển các field độc lập vào cùng oneof | Payload cũ có thể chứa nhiều member; parser mới chỉ giữ member xuất hiện sau |
| Đổi service/package/RPC identity | Client có thể gọi method path không còn được đăng ký |

Khi loại bỏ field, giữ reservation trong đúng message:

```proto
message StockReply {
  string sku = 1;
  int32 available = 2;

  reserved 3;
  reserved "legacy_timestamp";
}
```

Không tái sử dụng number hoặc tên đã phát hành. Với enum, reserve number và tên bên trong enum declaration.

## 7. Backward và forward compatibility không giống behavioral compatibility

Giả sử server v2 thêm enum value `ORDER_STATE_REVERSED`. Client proto3 v1 có thể parse response, giữ numeric value và trả `UNRECOGNIZED` qua generated Java enum API. Như vậy, payload có thể tương thích ở mức wire. Nhưng nếu client v1 ánh xạ mọi trạng thái không phải `FAILED` thành `CONFIRMED`, nghiệp vụ sẽ sai.

Tương tự, client v2 có thể gửi `idempotency_key` trong request. Server v1 bỏ qua field unknown và vẫn parse message. Nhưng nếu server v1 không có cơ chế idempotency, retry có thể tạo đơn hàng trùng. Parser thành công không có nghĩa server cũ hỗ trợ semantics mới.

Vì vậy cần đánh giá ba lớp riêng:

1. **Wire/schema compatibility:** bytes có parse được và field cũ có giữ đúng định danh không?
2. **Application compatibility:** code generated và mapping có xử lý absent/unknown values an toàn không?
3. **Behavioral compatibility:** các bên có thực hiện cùng quy tắc nghiệp vụ không?

Một thay đổi chỉ nên được bật khi cả các lớp cần thiết cho luồng đó đã được bảo đảm.

## 8. Chọn thứ tự rollout theo hướng tương thích

Thứ tự triển khai phụ thuộc bên nào sẽ bắt đầu ghi dữ liệu mới.

### Trường hợp A: server mới trả thêm response field

Có thể triển khai server mới trước. Client cũ thường bỏ qua field unknown; client mới đọc được field khi có mặt. Tuy nhiên, client mới cần fallback khi còn gọi server cũ và nhận response thiếu field.

### Trường hợp B: client mới gửi request field mới

Triển khai server hỗ trợ field mới trước. Chỉ bật client gửi field khi mọi server replica có thể nhận traffic đã hiểu và xử lý field đó. Nếu client mới gửi field tới server cũ, server có thể bỏ qua field và thực hiện hành vi cũ.

### Trường hợp C: đổi semantics hoặc thêm workflow mới

Dùng versioned service/message hoặc capability negotiation. Server phải công bố khả năng hỗ trợ trước khi client dùng semantics mới. Không suy ra capability chỉ từ việc parser chấp nhận field.

Một rollout phổ biến:

1. Mở rộng schema và code server để đọc cả request cũ lẫn mới.
2. Triển khai server tới toàn bộ replica.
3. Xác nhận health, metrics và capability.
4. Phát hành client mới theo nhóm, bật tính năng có kiểm soát.
5. Theo dõi lỗi, fallback và dữ liệu phát sinh.
6. Chỉ ngừng đường cũ sau khi không còn consumer phụ thuộc.

## 9. Compatibility matrix cho rolling deployment

Trong rolling deployment, không phải mọi request đều đi tới cùng một version. Hãy lập ma trận trước khi phát hành:

| Client | Server | Request | Response | Kết luận cần kiểm tra |
| --- | --- | --- | --- | --- |
| v1 | v1 | v1 ↔ v1 | v1 ↔ v1 | Baseline hiện tại |
| v1 | v2 | Writer cũ → reader mới | Writer mới → reader cũ | Backward request; forward response |
| v2 | v1 | Writer mới → reader cũ | Writer cũ → reader mới | Forward request; backward response |
| v2 | v2 | v2 ↔ v2 | v2 ↔ v2 | Hành vi mới đầy đủ |

Ma trận cho thấy vì sao test riêng client v2 với server v2 là chưa đủ. Trong rollout, cặp v1/v2 có thể tồn tại cùng lúc. Nếu một tổ hợp không được hỗ trợ, phải bảo đảm routing/deployment không tạo ra tổ hợp đó hoặc client có thể fallback an toàn.

Với service có nhiều replica, kiểm tra readiness và version distribution trước khi bật client mới. Một replica v1 còn nhận request mới có thể tạo lỗi không ổn định chỉ xuất hiện theo routing.

## 10. Kiểm thử hai hướng bằng generated code cũ và mới

Giữ schema hoặc generated artifact v1 làm fixture. Không chỉ compile schema v2 rồi test với chính generated code v2.

Các test cốt lõi:

- **Backward:** serialize message v1 rồi parse bằng generated type v2.
- **Forward:** serialize message v2 rồi parse bằng generated type v1.
- Test absent/default/presence của field mới.
- Test unknown enum value và oneof member mới.
- Test unknown-field round-trip qua các intermediary nếu cần bảo toàn payload.
- Test old client/new server và new client/old server qua gRPC thật.
- Test các giá trị biên và semantics nghiệp vụ, không chỉ assert parse thành công.

Ví dụ message-level test:

```java
// ProductV1 và ProductV2 được sinh từ hai schema fixture.
ProductV1 oldWriter = ProductV1.newBuilder()
    .setSku("SKU-100")
    .setAvailable(12)
    .build();

byte[] oldPayload = oldWriter.toByteArray();

// Backward: reader mới đọc payload cũ.
ProductV2 newReader = ProductV2.parseFrom(oldPayload);
assertEquals("SKU-100", newReader.getSku());
assertEquals(12, newReader.getAvailable());

// Forward: writer mới thêm field; reader cũ vẫn đọc field quen thuộc.
ProductV2 newWriter = ProductV2.newBuilder()
    .setSku("SKU-200")
    .setAvailable(8)
    .setUpdatedAtEpochMs(1730000000000L)
    .build();

ProductV1 oldReader = ProductV1.parseFrom(newWriter.toByteArray());
assertEquals("SKU-200", oldReader.getSku());
assertEquals(8, oldReader.getAvailable());
```

Ví dụ giả định v2 thêm `updated_at_epoch_ms = 3` và v1 không khai báo field đó. Đặt generated fixture ở module hoặc Java package riêng để tránh trùng fully-qualified class name. Parser pass chỉ là bước đầu; test adapter/service phải xác nhận default, fallback và kết quả nghiệp vụ.

## 11. Kiểm tra schema và contract trong CI

Một pipeline nên kiểm tra cả cấu trúc lẫn hành vi:

- Chạy formatter và lint cho toàn bộ Protobuf module.
- Chạy breaking-change detection với baseline đã phát hành.
- Pin phiên bản `protoc`, plugin và Buf để kết quả tái lập.
- Sinh Java code và compile các module client/server.
- Chạy test backward và forward bằng generated fixture v1/v2.
- Chạy integration tests cho các tổ hợp client/server được hỗ trợ.
- Kiểm tra JSON/gateway, `Any`, reflection và stored payload nếu hệ thống dùng chúng.

Rule set cần phù hợp với contract. Một số rule kiểm tra wire compatibility, một số rule chặt hơn kiểm tra JSON hoặc source API. Kết quả pass không thể chứng minh behavioral compatibility; test domain mapping và review semantics vẫn cần thiết.

Baseline cũng phải đúng: PR thường so với target branch; release nên so với schema version đang được consumers sử dụng. Không cập nhật baseline chỉ để bỏ qua một breaking change chưa được xử lý.

## 12. Checklist trước khi phát hành

- Đã xác định writer và reader ở từng luồng request/response.
- Đã nói rõ thay đổi cần backward, forward hay cả hai hướng.
- Field number và wire semantics cũ được giữ nguyên.
- Field mới có fallback khi reader mới nhận payload cũ.
- Reader cũ có thể bỏ qua field mới mà không làm sai nghiệp vụ.
- Unknown enum/oneof được xử lý an toàn.
- Không tái sử dụng field/enum number hoặc tên đã xóa.
- Presence và default value không bị hiểu nhầm.
- Intermediary/proxy có test round-trip nếu phải giữ unknown fields.
- Có generated fixture v1/v2 và test hai chiều.
- Có integration test cho rolling deployment và mọi tổ hợp version được hỗ trợ.
- CI breaking check dùng baseline đúng; generated code compile thành công.
- Thứ tự rollout phù hợp với hướng client/server bắt đầu gửi dữ liệu mới.

Với **SPRING_GRPC**, backward compatibility bảo vệ reader mới khi nhận payload cũ; forward compatibility bảo vệ reader cũ khi nhận payload mới. Trong giao tiếp gRPC, hai hướng xuất hiện ở cả request và response tùy bên nào ghi dữ liệu. Thiết kế schema phải giữ field identity, fallback cho absent/unknown values và semantics rõ ràng; kiểm thử cả bốn tổ hợp client/server giúp phát hiện lỗi chỉ xuất hiện trong rolling deployment.
