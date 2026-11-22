# Migration schema theo giai đoạn

## 1. Vì sao cần migration schema theo giai đoạn?

Trong **SPRING_GRPC**, Protobuf schema là hợp đồng giữa client, server và các thành phần xử lý dữ liệu. Những thành phần này thường không được nâng cấp đồng thời: server chạy rolling deployment trên nhiều replica, client mobile/desktop phát hành theo lịch riêng, batch job có thể chạy nhiều ngày, còn message đã serialize có thể nằm trong database, event log, queue hoặc backup.

Nếu đổi schema một lần rồi triển khai toàn bộ, hệ thống dễ rơi vào trạng thái một bên ghi dữ liệu theo định dạng mới trong khi bên kia chỉ hiểu định dạng cũ. **Migration schema theo giai đoạn** chia thay đổi thành các bước có thể cùng tồn tại: mở rộng schema, triển khai reader tương thích, chuyển writer và consumer, di chuyển dữ liệu, rồi mới loại bỏ phần cũ.

Cách tiếp cận này thường gọi là **expand–migrate–contract**:

1. **Expand:** thêm cấu trúc mới nhưng giữ cấu trúc cũ.
2. **Migrate:** triển khai code, chuyển traffic và dữ liệu sang cấu trúc mới.
3. **Contract:** ngừng dùng rồi xóa cấu trúc cũ, giữ reservation để ngăn tái sử dụng.

Bài tập trung vào cách tổ chức từng giai đoạn cho Protobuf và Spring gRPC, đặc biệt là thứ tự triển khai reader/writer, dual-read/dual-write, backfill dữ liệu, rollback và điều kiện kết thúc migration.

## 2. Kiểm kê producer, consumer và dữ liệu

Trước khi sửa schema, cần biết ai đang ghi và ai đang đọc field sẽ thay đổi. Producer/consumer không chỉ là client và server trực tiếp:

- Client gửi request và server đọc request.
- Server tạo response và client đọc response.
- Service trung gian parse rồi forward message.
- Consumer của event, queue, database snapshot hoặc cache đọc payload đã lưu.
- Batch job, công cụ vận hành và integration bên ngoài có thể dùng generated code cũ.
- Gateway hoặc adapter có thể chuyển Protobuf sang JSON rồi tạo message mới.

Lập bảng cho từng RPC/message:

| Đối tượng | Phiên bản | Ghi field cũ? | Đọc field cũ? | Lịch nâng cấp |
| --- | --- | --- | --- | --- |
| Mobile client | v1 | Có | Có | Theo đợt phát hành |
| Spring gRPC server | v1 | Có thể | Có | Rolling deployment |
| Event consumer | v1 | Không | Có | Theo lịch batch |
| Data backfill job | Tool riêng | Có thể | Có | Theo cửa sổ bảo trì |

Cần xác định cả **live traffic** lẫn dữ liệu tồn tại lâu dài. Traffic v1 về 0 không chứng minh backup, event log hoặc payload trong database không còn chứa field cũ.

Ghi lại baseline schema đã phát hành, field number, tên, type, presence, semantics và các version runtime đang được hỗ trợ. Không dựa vào tên Java getter để suy ra wire identity.

## 3. Nguyên tắc expand–migrate–contract

Mỗi giai đoạn phải duy trì một invariant có thể kiểm chứng:

| Giai đoạn | Schema | Reader | Writer | Mục tiêu |
| --- | --- | --- | --- | --- |
| Expand | Có field cũ và mới | Đọc được cả hai | Vẫn ghi field cũ | Mở rộng mà chưa đổi hành vi |
| Migrate | Có field cũ và mới | Ưu tiên field mới, fallback field cũ | Dual-write hoặc chuyển dần | Chuyển consumer và dữ liệu |
| Contract | Chỉ còn field mới; field cũ được reserve | Chỉ cần field mới | Chỉ ghi field mới | Loại bỏ đường cũ |

Không chuyển sang giai đoạn tiếp theo chỉ vì code mới đã merge. Cần có bằng chứng từ deployment, metrics, dữ liệu và compatibility tests.

Nguyên tắc quan trọng là **triển khai khả năng đọc trước khi bắt đầu ghi dữ liệu mới**. Trong rolling deployment, request mới có thể được định tuyến tới replica cũ; response mới có thể được đọc bởi client cũ. Nếu một tổ hợp version chưa hỗ trợ, cần giữ feature flag tắt hoặc kiểm soát routing để tránh tổ hợp đó.

## 4. Ví dụ: chuyển quantity từ int32 sang int64

Giả sử contract v1 dùng int32 cho số lượng:

```proto
syntax = "proto3";

package inventory.v1;

message InventoryItem {
  string sku = 1;
  int32 quantity = 2;
}
```

Sau này số lượng có thể vượt giới hạn int32. Không đổi trực tiếp type tại field number 2. Thay vào đó, thêm field mới với number chưa từng dùng và explicit presence:

```proto
syntax = "proto3";

package inventory.v1;

message InventoryItem {
  string sku = 1;
  int32 quantity = 2 [deprecated = true];
  optional int64 quantity_v2 = 5;
}
```

Trong giai đoạn chuyển tiếp:

- Field 2 giữ nguyên wire contract cũ.
- Field 5 mang giá trị mới và có presence để phân biệt absent với giá trị 0.
- Reader mới ưu tiên field 5 khi hasQuantityV2() là true; nếu không có thì fallback sang field 2.
- Writer mới có thể ghi cả hai field khi giá trị nằm trong miền int32.
- Writer cũ không biết field 5 và tiếp tục ghi field 2.

Tùy chọn deprecated là tín hiệu cho compiler/tooling và người phát triển; nó không tự ngăn client cũ gửi field hoặc xóa getter khỏi generated API.

Không ép giá trị vượt giới hạn int32 vào field cũ bằng truncation hoặc cast. Trong thời gian còn reader v1, cần giữ giá trị trong miền cũ hoặc có cơ chế đảm bảo request có giá trị lớn chỉ đi tới server đã hỗ trợ v2.

## 5. Giai đoạn Expand: thêm field nhưng giữ contract cũ

Ở giai đoạn đầu, chỉ mở rộng schema và triển khai reader có khả năng hiểu cả field cũ lẫn mới. Chưa bật writer gửi dữ liệu chỉ biểu diễn được bằng field mới.

Ví dụ logic đọc trong Spring service:

```java
long quantity;

if (request.hasQuantityV2()) {
    quantity = request.getQuantityV2();
} else {
    quantity = request.getQuantity();
}
```

Đây là mapping minh họa; nên đặt trong adapter riêng để mọi RPC dùng cùng một quy tắc. Nếu field mới dùng implicit presence, không thể kiểm tra absent bằng hasQuantityV2(); hãy chọn optional hoặc cấu trúc có presence rõ ràng nếu migration cần phân biệt absent và zero.

Trình tự expand:

1. Thêm field mới bằng number chưa từng dùng; giữ nguyên field cũ.
2. Đánh dấu field cũ deprecated nếu chính sách dự án cho phép.
3. Sinh generated Java code và compile tất cả module phụ thuộc.
4. Triển khai server reader mới tới toàn bộ replica.
5. Cập nhật event consumer, batch job và gateway để hiểu field mới.
6. Giữ writer cũ hoặc chế độ chỉ ghi field cũ.
7. Chạy test request/response từ generated client v1.

Sau bước này, server mới phải đọc được payload do writer cũ tạo ra. Chưa có lý do để client bắt đầu gửi giá trị chỉ biểu diễn được bằng field mới.

## 6. Giai đoạn Migrate: dual-read và dual-write

Khi mọi reader cần thiết đã hiểu field mới, có thể bắt đầu chuyển writer. Trong một thời gian, writer mới có thể ghi đồng thời field cũ và field mới để reader v1 vẫn sử dụng được.

Ví dụ tạo message response:

```java
InventoryItem.Builder builder = InventoryItem.newBuilder()
    .setSku(item.sku())
    .setQuantityV2(item.quantity());

if (item.quantity() >= Integer.MIN_VALUE
        && item.quantity() <= Integer.MAX_VALUE) {
    builder.setQuantity((int) item.quantity());
}

return builder.build();
```

Ví dụ này chỉ dual-write field cũ khi giá trị biểu diễn được chính xác trong int32. Nếu giá trị vượt miền cũ, không thể bảo đảm client v1 đọc đúng. Vì vậy, trước khi cho phép dữ liệu vượt giới hạn, phải xác nhận không còn consumer v1 hoặc route loại request đó tới phiên bản hỗ trợ.

### Quy tắc ưu tiên khi cả hai field cùng có mặt

Reader mới phải có quy tắc xác định:

- Nếu field mới present, dùng field mới.
- Nếu field mới absent, fallback sang field cũ.
- Nếu cả hai present nhưng giá trị khác nhau, phát hiện conflict và xử lý theo chính sách rõ ràng.

Không âm thầm chọn một giá trị khi hai field mâu thuẫn. Có thể từ chối request, ghi metric và log có kiểm soát để phát hiện producer lỗi. Trong migration, conflict là tín hiệu chất lượng dữ liệu cần xử lý.

Dual-write chỉ nên tồn tại trong khoảng thời gian có mục đích. Ghi hai field vô thời hạn làm tăng độ phức tạp, tạo thêm nguồn sai lệch và khiến việc loại bỏ field cũ khó hơn.

## 7. Chuyển consumer và dữ liệu đã lưu

Dữ liệu Protobuf đã serialize có thể tồn tại lâu hơn phiên bản service tạo ra nó. Cần phân loại:

- **Dữ liệu mutable:** có thể backfill bằng cách đọc payload cũ, bổ sung field mới và ghi lại theo schema mới.
- **Event bất biến:** thường không nên sửa event lịch sử tại chỗ; consumer có thể đọc event cũ qua adapter hoặc rebuild projection.
- **Cache:** có thể xóa và tái tạo nếu nguồn dữ liệu chuẩn còn tồn tại.
- **Backup/archive:** cần giữ schema cũ hoặc decoder tương ứng trong thời gian lưu trữ.
- **Any và descriptor:** phải giữ khả năng resolve type URL cũ nếu dữ liệu còn tham chiếu type đó.

Một backfill cần có checkpoint, khả năng chạy lại và kiểm tra số lượng bản ghi. Quy trình thường là:

1. Đọc payload bằng schema có thể hiểu định dạng đang lưu.
2. Chuyển sang domain model chuẩn.
3. Tạo message mới với field mới.
4. Kiểm tra invariant và giá trị biên.
5. Ghi bản mới theo chiến lược atomic/transaction phù hợp.
6. Lưu tiến độ và số liệu lỗi để có thể tiếp tục.

Không parse rồi serialize mọi payload bằng một schema mới nếu bước chuyển đổi có thể làm mất unknown fields hoặc thông tin mà phiên bản hiện tại chưa biết. Với event bất biến, giữ nguyên bytes gốc và chuyển đổi ở projection/consumer thường an toàn hơn.

## 8. Giai đoạn Contract: ngừng field cũ và reserve

Chỉ contract khi đã chứng minh:

- Không còn writer v1 trong live traffic.
- Không còn reader v1 cần field cũ.
- Batch job, gateway, integration và queue consumer đã chuyển.
- Dữ liệu mutable đã backfill; dữ liệu bất biến vẫn có decoder phù hợp.
- Không còn rollback về binary chỉ hiểu field cũ.
- Metrics về old-field usage và fallback đã về mức chấp nhận được trong khoảng quan sát đã định.

Sau đó xóa khai báo field cũ và reserve cả field number lẫn tên:

```proto
message InventoryItem {
  string sku = 1;
  optional int64 quantity_v2 = 5;

  reserved 2;
  reserved "quantity";
}
```

Reservation nằm trong message chứa field. Không reserve field number 5 vì field mới vẫn đang sử dụng nó. Giữ reservation trong các phiên bản schema sau để không tái sử dụng định danh cũ.

Việc xóa field là thay đổi source/API đối với consumer cũ. Parser mới sẽ coi tag cũ là unknown; server không còn getter để đọc giá trị đó. Vì vậy, contract chỉ an toàn khi writer cũ và consumer phụ thuộc field cũ đã được loại bỏ hoặc được giữ trong một API version riêng.

## 9. Rollback trong từng giai đoạn

Rollback cần được thiết kế trước khi bắt đầu ghi dữ liệu mới.

| Giai đoạn | Rollback khả thi? | Điều kiện |
| --- | --- | --- |
| Expand | Thường dễ | Chưa bật writer mới; có thể quay lại server cũ nếu schema additive |
| Dual-read/dual-write | Có điều kiện | Field cũ vẫn được ghi và giá trị mới còn biểu diễn được trong miền cũ |
| New-only write | Khó hơn | Reader cũ không đọc được dữ liệu mới; cần giữ server tương thích hoặc khôi phục từ dữ liệu chuyển đổi |
| Contract | Thường cần forward-fix | Field cũ đã bị xóa khỏi generated API và number/name đã reserve |

Nếu rollback yêu cầu server cũ đọc được dữ liệu vừa ghi, dual-write phải bảo đảm field cũ có giá trị chính xác. Với giá trị vượt miền cũ, rollback về server v1 không còn an toàn.

Không xóa field cũ trong cùng release đầu tiên chuyển writer sang field mới. Tách contract thành release sau để có thời gian quan sát và giữ đường rollback.

## 10. Kiểm thử migration theo ma trận version

Kiểm thử schema mới với chính generated code mới không đủ. Giữ fixture/artifact từ schema cũ và test mọi tổ hợp có thể xuất hiện trong rollout:

| Writer | Reader | Điều cần xác nhận |
| --- | --- | --- |
| v1 | v2 | Reader mới fallback đúng khi field mới absent |
| v2 dual-write | v1 | Reader cũ dùng field cũ với giá trị chính xác |
| v2 dual-write | v2 | Reader mới ưu tiên field mới và phát hiện conflict |
| v2 new-only | v1 | Phải bị chặn nếu reader cũ còn được hỗ trợ |
| Stored payload cũ | Backfill v2 | Dữ liệu được chuyển đổi không mất mát |
| Event/backup cũ | Consumer hiện tại | Decoder cũ vẫn được giữ khi cần |

Ví dụ test fallback:

```java
InventoryItem oldPayload = InventoryItem.newBuilder()
    .setSku("SKU-10")
    .setQuantity(25)
    .build();

long resolved = oldPayload.hasQuantityV2()
    ? oldPayload.getQuantityV2()
    : oldPayload.getQuantity();

assertEquals(25L, resolved);
```

Test bổ sung cần bao gồm:

- Giá trị 0, âm và biên Integer.MIN_VALUE/Integer.MAX_VALUE.
- Giá trị lớn hơn miền int32.
- Cả hai field present nhưng mâu thuẫn.
- Field mới absent và field cũ absent.
- Parse/serialize round-trip qua proxy hoặc gateway.
- Old client/new server và new client/old server qua gRPC integration test.
- Backfill chạy lại sau khi bị gián đoạn.

## 11. Quan sát migration bằng metrics và logs

Không thể quyết định contract chỉ dựa vào việc deploy đã hoàn tất. Cần đo xem field cũ còn được sử dụng ở đâu.

Một số chỉ số hữu ích:

- Số request chỉ có field cũ.
- Số request có field mới.
- Số request có cả hai field.
- Số conflict khi hai field cùng có nhưng khác giá trị.
- Số fallback từ field mới sang field cũ.
- Số client gọi RPC/service version cũ.
- Số payload lịch sử chưa backfill hoặc backfill thất bại.
- Parse error và lỗi domain liên quan migration.

Dùng metric labels có cardinality giới hạn như API version, service và trạng thái migration. Không đưa ID người dùng, payload hoặc giá trị field tùy ý vào labels. Log nên ghi context đủ để truy vết nhưng tránh dữ liệu nhạy cảm.

Đặt tiêu chí kết thúc trước khi migration bắt đầu, ví dụ: không còn old writer trong một khoảng thời gian lớn hơn chu kỳ batch/job dài nhất; fallback bằng 0; không có consumer v1 đã biết; backfill hoàn tất và được đối soát.

## 12. CI và kiểm soát schema

CI cần kiểm tra cả schema và migration logic:

- Lint/format Protobuf schema.
- Breaking check so với baseline đã phát hành.
- Xác nhận field mới dùng number chưa từng dùng.
- Xác nhận field cũ được deprecate trong giai đoạn migrate và reserve khi contract.
- Sinh code bằng phiên bản protoc/plugin đã pin.
- Compile server/client adapters.
- Chạy compatibility tests với generated fixture v1/v2.
- Chạy integration tests cho các tổ hợp client/server được hỗ trợ.
- Test backfill và conflict handling trên fixture dữ liệu đại diện.

Breaking check tĩnh không thể chứng minh không còn writer cũ trong production. Điều kiện đó cần metrics, inventory consumer và phê duyệt release. Tương tự, CI pass không chứng minh dữ liệu lịch sử đã được migrate; backfill cần báo cáo và đối soát riêng.

## 13. Khi nào nên dùng versioned service thay vì migration field?

Expand–migrate–contract phù hợp khi có thể giữ contract cũ và mới cùng tồn tại trong một message, đồng thời xác định được fallback và mapping rõ ràng.

Nên cân nhắc versioned service/message khi:

- Semantics request/response thay đổi sâu, không thể dual-read/write an toàn.
- Nhiều field phụ thuộc nhau và không thể mở rộng độc lập.
- Client cũ sẽ hiểu sai payload mới dù parser vẫn thành công.
- Cần thay đổi RPC path, authorization boundary hoặc workflow.
- Có nhiều nhóm consumer với lịch nâng cấp không thể điều phối bằng một field migration.

Trong trường hợp đó, giữ service v1 và tạo service v2; server có thể dual-register hai service và dùng adapter chuyển về domain logic chung. Migration field trong v1 và versioned service v2 là hai công cụ khác nhau; chọn theo mức độ thay đổi contract.

## 14. Checklist hoàn tất migration

- Đã kiểm kê producer, consumer, intermediary và dữ liệu đã lưu.
- Baseline schema và compatibility matrix được ghi nhận.
- Field mới dùng number mới; field cũ giữ nguyên trong giai đoạn expand.
- Reader mới hỗ trợ field cũ và mới trước khi writer chuyển đổi.
- Presence/default và precedence giữa hai field được định nghĩa.
- Dual-write chỉ thực hiện khi chuyển đổi không mất dữ liệu.
- Giá trị vượt miền field cũ bị chặn cho tới khi không còn reader cũ.
- Backfill có checkpoint, retry, đối soát và xử lý unknown fields.
- Metrics xác nhận old writer/reader và fallback đã hết theo tiêu chí đặt trước.
- Rollback được kiểm tra trước khi ngừng ghi field cũ.
- Field cũ chỉ bị xóa khi không còn consumer phụ thuộc.
- Number và tên cũ được reserve; CI breaking check vẫn dùng baseline đúng.

Trong **SPRING_GRPC**, migration schema theo giai đoạn giúp client, server và consumer dữ liệu nâng cấp lệch thời điểm mà vẫn giữ được hợp đồng hoạt động. Mở rộng trước, triển khai reader tương thích, chuyển writer và dữ liệu có kiểm soát, rồi mới contract field cũ. Chỉ kết thúc migration khi metrics, fixture, dữ liệu lưu trữ và compatibility tests chứng minh không còn phụ thuộc vào schema cũ.
