# Chuyển đổi event giữa phiên bản

Khi application event được nhiều module hoặc hệ thống bên ngoài tiêu thụ, cấu trúc và ý nghĩa của event trở thành một hợp đồng cần được duy trì qua nhiều lần triển khai. Nghiệp vụ thay đổi có thể khiến payload V1 không còn đủ dữ liệu, một field đổi kiểu hoặc ý nghĩa cũ cần được diễn đạt chính xác hơn. Chuyển đổi event giữa phiên bản là quá trình đưa publisher và consumer từ hợp đồng cũ sang hợp đồng mới mà không làm mất event, xử lý trùng hoặc khiến các phiên bản đang chạy hiểu sai dữ liệu.

Trong Spring Modulith, application events có thể được dùng trong nội bộ ứng dụng và được externalize sang broker. Khi migration, cần xem xét cả listener nội bộ, Event Publication Registry, serializer, integration adapter, consumer bên ngoài và các message cũ còn nằm trong broker.

## 1. Vì sao phải chuyển đổi event?

Một hợp đồng event thường sống lâu hơn một lần deploy. Consumer có thể được triển khai chậm hơn publisher; message có thể nằm trong broker hoặc retry topic nhiều giờ; publication chưa hoàn tất có thể được phục hồi sau khi ứng dụng restart. Vì vậy, thay đổi event cần có giai đoạn chuyển tiếp.

Ví dụ V1 chỉ công bố mã đơn hàng và thời điểm xác nhận:

~~~java
public record OrderConfirmedV1(
        UUID eventId,
        UUID orderId,
        Instant confirmedAt) {
}
~~~

Sau này, consumer cần kênh bán hàng và phiên bản aggregate để cập nhật read model đúng thứ tự. V2 có thể bổ sung hai trường đó:

~~~java
public record OrderConfirmedV2(
        UUID eventId,
        UUID orderId,
        Instant confirmedAt,
        String salesChannel,
        long aggregateVersion) {
}
~~~

Consumer chỉ hiểu V1 sẽ không tự động biết cách xử lý V2. Migration phải cho consumer thời gian nâng cấp và xác định cách xử lý message V1 còn tồn tại.

## 2. Xác định ranh giới phiên bản

Trước khi chuyển đổi, cần phân biệt các loại version:

| Loại | Ý nghĩa |
| --- | --- |
| Event contract version | Phiên bản hợp đồng nghiệp vụ mà consumer nhận, ví dụ `OrderConfirmedV2` |
| Schema version | Cấu trúc dữ liệu dùng để serialize/deserialize payload |
| Aggregate version | Thứ tự thay đổi của một đơn hàng, ví dụ `aggregateVersion=42` |
| Application version | Phiên bản phần mềm đang triển khai |

Migration event contract không đồng nghĩa với nâng phiên bản ứng dụng. Một ứng dụng mới có thể tiếp tục phát V1; một consumer mới có thể hỗ trợ cả V1 và V2. Aggregate version cũng không được dùng thay event contract version: V2 không có nghĩa đây là thay đổi nghiệp vụ thứ hai.

Cần xác định rõ phần nào thay đổi: tên event, field, kiểu dữ liệu, đơn vị đo, nullability, quy tắc nghiệp vụ hay cách diễn giải. Thay đổi ngữ nghĩa có thể phá vỡ tương thích ngay cả khi JSON vẫn parse được.

## 3. Đánh giá mức độ tương thích

Không phải thay đổi nào cũng cần tạo event type mới. Đánh giá tác động trên tất cả consumer đang được hỗ trợ:

| Thay đổi | Tác động thường gặp | Hướng migration |
| --- | --- | --- |
| Thêm field tùy chọn có default rõ ràng | Consumer cũ thường có thể bỏ qua | Có thể giữ version nếu schema policy cho phép |
| Thêm field bắt buộc mà consumer cũ không biết | Consumer cũ có thể không xử lý đúng | Tạo version mới hoặc giai đoạn chuyển tiếp có default hợp lệ |
| Đổi kiểu field hoặc cấu trúc lồng nhau | Có thể lỗi deserialize | Tạo version mới và chuyển đổi rõ ràng |
| Đổi đơn vị hoặc ý nghĩa field | Payload vẫn đọc được nhưng kết quả nghiệp vụ sai | Tạo version mới hoặc field mới với ngữ nghĩa riêng |
| Xóa field đang được sử dụng | Consumer cũ có thể lỗi hoặc mất dữ liệu | Chỉ xóa sau khi consumer đã chuyển đổi |
| Đổi quy tắc nghiệp vụ | Consumer có thể diễn giải sai dù schema không đổi | Công bố contract/event type mới nếu ngữ nghĩa khác |

Backward compatibility nghĩa là consumer mới vẫn đọc được dữ liệu cũ. Forward compatibility nghĩa là consumer cũ có thể bỏ qua hoặc xử lý an toàn dữ liệu mới. Hai thuộc tính phụ thuộc serializer, schema policy và cách consumer được viết; không thể suy ra chỉ từ việc thêm một field.

## 4. Dùng adapter để cô lập phiên bản

Một cách tổ chức dễ bảo trì là chuyển từng wire version thành một mô hình nội bộ chuẩn (canonical model). Business logic chỉ làm việc với mô hình nội bộ; adapter chịu trách nhiệm đọc V1, V2 và ánh xạ chúng.

~~~java
record ConfirmedOrder(
        UUID businessEventId,
        UUID orderId,
        Instant confirmedAt,
        String salesChannel,
        long aggregateVersion) {
}

final class OrderEventMapper {

    ConfirmedOrder toCanonical(OrderConfirmedV1 event) {
        return new ConfirmedOrder(
                event.eventId(),
                event.orderId(),
                event.confirmedAt(),
                "UNKNOWN",
                0);
    }

    ConfirmedOrder toCanonical(OrderConfirmedV2 event) {
        return new ConfirmedOrder(
                event.eventId(),
                event.orderId(),
                event.confirmedAt(),
                event.salesChannel(),
                event.aggregateVersion());
    }
}
~~~

Giá trị `UNKNOWN` và version `0` chỉ minh họa việc chuyển đổi. Trong nghiệp vụ thật, chỉ dùng default khi nó có ý nghĩa và không làm sai quyết định. Nếu không thể suy ra dữ liệu mới từ V1, consumer cần biểu diễn rõ trạng thái thiếu thông tin, tra cứu nguồn chuẩn hoặc từ chối xử lý theo quy trình có quan sát.

Adapter giúp các handler không phải rải điều kiện `if (version == 1)` trong toàn bộ business logic. Khi V1 hết vòng đời, có thể loại bỏ adapter V1 mà không phải thay đổi phần xử lý canonical.

## 5. Chiến lược expand-and-contract

Expand-and-contract là cách triển khai theo nhiều giai đoạn để publisher và consumer không cần nâng cấp cùng lúc.

~~~mermaid
flowchart TD
    A[1. Công bố hợp đồng V2] --> B[2. Nâng consumer hiểu V1 và V2]
    B --> C[3. Bắt đầu phát V2 hoặc dual-publish]
    C --> D[4. Theo dõi consumer và message tồn đọng]
    D --> E[5. Chuyển toàn bộ consumer sang V2]
    E --> F[6. Ngừng phát V1]
    F --> G[7. Chờ hết replay/retention window]
    G --> H[8. Gỡ handler và schema V1]
~~~

**Giai đoạn expand:** thêm V2 và cập nhật consumer để nhận cả V1 lẫn V2. Publisher vẫn giữ khả năng phát V1. Triển khai consumer mới trước để không có message V2 nào đến một consumer chưa hiểu nó.

**Giai đoạn chuyển đổi:** publisher bắt đầu phát V2. Tùy yêu cầu, publisher có thể chỉ phát V2 sau khi tất cả consumer sẵn sàng, hoặc dual-publish trong thời gian ngắn. Theo dõi lỗi deserialize, số message theo version và trạng thái các consumer.

**Giai đoạn contract:** dừng phát V1 khi consumer bắt buộc đã chuyển đổi và message V1 tồn đọng đã được xử lý. Sau khi hết thời hạn retention, retry và replay, mới gỡ handler V1, schema cũ và code chuyển đổi không còn cần thiết.

Không xóa V1 ngay khi V2 chạy thành công ở môi trường thử nghiệm. Message cũ có thể vẫn nằm trong broker, DLT, backup hoặc Event Publication Registry.

## 6. Dual-publish khi cần giai đoạn tương thích

Dual-publish nghĩa là publisher phát cả V1 và V2 cho cùng một thay đổi nghiệp vụ. Cách này hữu ích khi có consumer chưa thể chuyển đổi đồng thời, nhưng tạo hai message đại diện cho cùng một sự thật.

Ví dụ, use case có thể tạo hai biểu diễn từ cùng dữ liệu nghiệp vụ:

~~~java
@Transactional
public void confirm(UUID orderId) {
    Order order = orders.findRequired(orderId);
    order.confirm();

    UUID businessEventId = UUID.randomUUID();
    Instant confirmedAt = clock.instant();

    events.publishEvent(new OrderConfirmedV1(
            businessEventId, order.id(), confirmedAt));

    events.publishEvent(new OrderConfirmedV2(
            businessEventId, order.id(), confirmedAt,
            order.salesChannel(), order.version()));
}
~~~

Ví dụ giả định hai event được publish trong cùng transaction và persistence publication được cấu hình phù hợp. Nếu V1 và V2 được externalize độc lập, cần bảo đảm cả hai publication được ghi nhận trong cùng ranh giới transaction/outbox để tránh chỉ gửi được một phiên bản.

Khi dual-publish:

- Dùng một `businessEventId` ổn định để liên kết hai biểu diễn của cùng sự kiện nghiệp vụ.
- Nếu cần định danh message riêng, dùng thêm `messageId`; không nhầm message ID với business event ID.
- Xác định consumer nào nhận V1, consumer nào nhận V2.
- Ngăn consumer xử lý cả hai phiên bản như hai thay đổi nghiệp vụ độc lập.
- Đặt thời điểm kết thúc dual-publish và đo adoption của V1.

Dual-publish không phải lựa chọn mặc định. Nó làm tăng lưu lượng, publication cần theo dõi và khả năng side effect trùng. Nếu tất cả consumer có thể nâng cấp trước khi publisher chuyển, chỉ phát V2 sau giai đoạn expand thường đơn giản hơn.

## 7. Consumer hỗ trợ song song nhiều phiên bản

Trong Spring Modulith, listener có thể nhận các kiểu event khác nhau và ánh xạ chúng về cùng service:

~~~java
@Component
class OrderProjectionListener {

    private final OrderEventMapper mapper;
    private final OrderProjectionService projection;

    OrderProjectionListener(
            OrderEventMapper mapper,
            OrderProjectionService projection) {
        this.mapper = mapper;
        this.projection = projection;
    }

    @ApplicationModuleListener
    void on(OrderConfirmedV1 event) {
        projection.apply(mapper.toCanonical(event));
    }

    @ApplicationModuleListener
    void on(OrderConfirmedV2 event) {
        projection.apply(mapper.toCanonical(event));
    }
}
~~~

Đây là ví dụ về listener nội bộ; cần import `ApplicationModuleListener`, `Component` và các kiểu event/service tương ứng trong ứng dụng. Với external consumer, cùng ý tưởng được triển khai ở message deserializer/router: đọc type identifier, chọn DTO tương ứng rồi chuyển về mô hình nội bộ.

Consumer cần từ chối version không hỗ trợ theo cách có thể quan sát, chẳng hạn ghi nhận lỗi schema và đưa message vào quarantine/DLT theo chính sách. Không deserialize một payload lạ thành `Object` rồi đoán kiểu bằng chuỗi hoặc ép kiểu tùy tiện.

## 8. Upcasting và chuyển đổi message cũ

Upcasting là bước chuyển đổi event cũ sang cấu trúc mà code hiện tại hiểu, thường khi replay hoặc đọc dữ liệu event đã lưu. Upcaster nên là hàm xác định: cùng payload V1 luôn tạo cùng kết quả canonical, không gọi dependency ngoài và không tạo side effect.

Luồng có thể là:

~~~mermaid
flowchart LR
    A[Stored V1 payload] --> B[Deserialize V1]
    B --> C[Upcaster / mapper]
    C --> D[Canonical event]
    D --> E[Current projection handler]
~~~

Upcasting phù hợp khi:

- Cần replay event lịch sử bằng code mới.
- Muốn gom logic tương thích cũ tại một ranh giới.
- Có thể chuyển đổi đầy đủ từ dữ liệu V1 sang mô hình hiện tại.

Nếu V1 thiếu dữ liệu không thể suy ra, upcaster không nên bịa giá trị. Có thể giữ field ở trạng thái unknown, tra cứu nguồn dữ liệu chuẩn hoặc yêu cầu xử lý thủ công tùy quy tắc nghiệp vụ.

Giữ payload lịch sử gốc nếu cần audit. Upcaster tạo biểu diễn mới để xử lý, không nhất thiết phải ghi đè event cũ. Với Event Publication Registry, phải phân biệt publication chưa hoàn tất cần deserialize để retry với event history dài hạn; registry không mặc nhiên là event store.

## 9. Xử lý publication cũ trong Spring Modulith

Event Publication Registry theo dõi publication tới listener. Nếu ứng dụng lưu publication bền vững, event chưa hoàn tất có thể cần được deserialize sau khi code đã chuyển sang version mới.

Trong giai đoạn migration:

- Giữ class V1 và serializer cần thiết khi còn publication V1 chưa hoàn tất.
- Không đổi tên hoặc xóa type V1 khi registry vẫn có thể cần đọc payload cũ.
- Xác định cách consumer/listener xử lý publication V1 sau khi logic nội bộ đã thay đổi.
- Theo dõi publication incomplete theo listener và tuổi của publication.
- Chỉ dọn publication completed theo retention policy; không coi registry là nơi lưu toàn bộ lịch sử để replay lâu dài.

Nếu cần chuyển đổi dữ liệu publication đã lưu, thực hiện migration có kiểm soát, có backup và cách quay lui. Không sửa trực tiếp dữ liệu persistence nội bộ của registry nếu chưa có cơ chế migration được hỗ trợ bởi adapter đang dùng.

## 10. Externalization và broker trong quá trình migration

Khi event được externalize, migration có thêm các yếu tố:

- Wire type/header phải cho consumer biết message là V1 hay V2.
- Serializer và schema registry phải hỗ trợ schema tương ứng.
- Topic, routing key và partition key cần giữ quy tắc tương thích.
- Retry topic và DLT có thể còn message V1 sau khi publisher đã phát V2.
- Consumer cần giữ khả năng đọc V1 ít nhất trong thời gian message cũ có thể được replay.

`@Externalized` trong Spring Modulith đánh dấu event cần externalize và cung cấp target logic cho adapter. Nó không tự định nghĩa chiến lược versioning, schema registry hoặc tạo topic riêng cho V1/V2. Cần kiểm tra adapter và cấu hình tích hợp để bảo đảm type information được truyền qua message theo hợp đồng đã chọn.

Không đổi topic chỉ vì đổi event version nếu không có lý do về routing hoặc vận hành. Có thể cùng một topic chứa nhiều event type/version nếu consumer phân biệt được type; nếu tách topic, cần kế hoạch chuyển subscription và xử lý backlog cũ.

## 11. Ordering, idempotency và side effect trùng

Migration có thể khiến một aggregate phát V1 và V2, hoặc message cũ và mới cùng tồn tại trong broker. Consumer phải phân biệt:

- `businessEventId`: định danh sự thật nghiệp vụ, dùng để nhận biết các biểu diễn V1/V2 của cùng một sự kiện.
- `messageId`: định danh một message cụ thể trên transport nếu cần.
- `aggregateVersion`: thứ tự thay đổi của aggregate.
- `eventType/version`: hợp đồng payload cần deserialize.

Projection có thể lưu `lastAppliedAggregateVersion` và chỉ áp dụng event phù hợp với version tiếp theo. Với event dạng delta, nếu phát hiện gap thì cần chờ hoặc lấy lại dữ liệu; với event snapshot đầy đủ, có thể áp dụng snapshot mới nhất theo version.

Idempotency phải tồn tại ở nơi side effect được thực hiện. Ghi event ID vào database của consumer có thể ngăn cập nhật database trùng, nhưng không tự ngăn API ngoài tạo hai vận đơn nếu server đã thực hiện request rồi response bị mất. Với side effect từ xa, dùng idempotency key mà hệ thống đích hiểu hoặc tra cứu trạng thái trước khi gửi lại.

## 12. Rollback và xử lý khi migration gặp lỗi

Rollback event contract không đơn giản là deploy lại binary cũ. Sau khi publisher đã phát V2, message V2 có thể đã nằm trong broker hoặc được consumer xử lý.

Trước khi migration, xác định:

- Consumer cũ có thể đọc V2 hay không.
- Có thể quay publisher về phát V1 mà không mất dữ liệu mới hay không.
- V1 có biểu diễn được thông tin chỉ tồn tại trong V2 không.
- Message V2 đã phát có thể tiếp tục được consumer mới xử lý hay phải giữ lại.
- Publication V1/V2 nào đang pending trong registry.

Nếu V2 chứa dữ liệu không thể biểu diễn trong V1, rollback publisher về V1 có thể làm mất thông tin. Khi đó, lựa chọn an toàn hơn có thể là giữ publisher V2, sửa consumer bằng forward fix hoặc tạm dừng xử lý message có kiểm soát. Không chuyển đổi ngược bằng cách bỏ field mà không đánh giá tác động nghiệp vụ.

Với dual-publish, có thể dừng phát V2 nếu consumer V1 vẫn hoạt động và V1 vẫn đủ dữ liệu. Nhưng cần xử lý V2 đã gửi hoặc đã được consumer nhận; không xóa message đang tồn tại chỉ để quay về trạng thái trước migration.

## 13. Kế hoạch migration thực tế

Một checklist theo thứ tự triển khai:

1. **Inventory:** liệt kê publisher, consumer, event type, destination, schema, retry/DLT và retention.
2. **Contract design:** định nghĩa V2, trường mới, ý nghĩa, default, type identifier và quy tắc tương thích.
3. **Consumer expand:** triển khai handler V1/V2 hoặc adapter/upcaster trước khi publisher phát V2.
4. **Test fixtures:** chuẩn bị payload V1/V2 đã loại bỏ dữ liệu nhạy cảm và contract test cho từng consumer.
5. **Publisher rollout:** phát V2; chỉ dual-publish nếu cần, cùng business event ID và transaction boundary phù hợp.
6. **Observe:** theo dõi message count, parse error, consumer lag, pending publication, retry và DLT theo version.
7. **Drain old messages:** xử lý backlog, retry topic và DLT V1; xác nhận không còn consumer phụ thuộc V1.
8. **Stop V1:** dừng dual-publish hoặc dừng phát V1 sau khi các điều kiện migration đạt.
9. **Retention window:** giữ code/schema V1 đủ lâu cho publication pending, broker retention, replay và backup.
10. **Contract:** gỡ handler/upcaster V1 và schema cũ khi không còn dữ liệu hoặc consumer cần chúng.

Migration cần owner cho publisher và từng consumer, thời điểm cutover, tiêu chí thành công và kế hoạch xử lý nếu một consumer chưa sẵn sàng.

## 14. Kiểm thử chuyển đổi giữa các phiên bản

Kiểm thử cần chứng minh publisher và consumer tương thích trong mọi giai đoạn:

- Consumer mới deserialize và xử lý được payload V1 cũ.
- Consumer mới deserialize và xử lý đúng payload V2.
- Publisher không phát V2 trước khi consumer bắt buộc đã hỗ trợ.
- Dual-publish tạo hai biểu diễn nhưng chỉ một side effect nghiệp vụ.
- Upcaster chuyển V1 sang canonical model một cách xác định.
- Event cũ trong retry topic/DLT có thể được xử lý sau deploy mới.
- Publication V1 pending trong registry vẫn deserialize và resubmit được.
- Aggregate ordering được giữ khi V1 và V2 cùng tồn tại.
- Rollback publisher không làm mất dữ liệu chỉ có ở V2.
- Version không hỗ trợ được ghi nhận và chuyển theo quy trình lỗi rõ ràng.

Ưu tiên contract test với payload mẫu thực tế của từng version và integration test qua serializer/adapter đang dùng. Unit test mapper không chứng minh wire type, header hoặc broker converter được cấu hình đúng.

## 15. Quan sát migration

Dashboard và log cần phân biệt version trong toàn bộ giai đoạn chuyển đổi:

| Chỉ số | Mục đích |
| --- | --- |
| Published count theo event type/version | Biết publisher đang phát V1 hay V2 |
| Consumer success/failure theo version | Xác định consumer chưa hỗ trợ version mới |
| Deserialization/schema errors | Phát hiện lỗi contract hoặc serializer |
| Pending publication theo event type | Phát hiện publication cũ chưa hoàn tất |
| Retry/DLT count theo version | Theo dõi message cũ còn tồn đọng |
| Consumer lag theo destination | Xác định consumer có bắt kịp backlog không |

Event type/version là tag có tập giá trị giới hạn. Không dùng event ID, order ID hoặc correlation ID làm metric label; dùng structured log và trace để tìm từng message. Chỉ kết thúc V1 khi metrics và kiểm kê consumer cùng xác nhận không còn nhu cầu.

## 16. Những sai lầm cần tránh

- Chỉ đổi tên class mà không xác định wire type và serializer.
- Nhầm event contract version với aggregate version hoặc application version.
- Triển khai publisher V2 trước khi consumer sẵn sàng.
- Dual-publish mà không có business event ID chung và idempotency.
- Xóa handler V1 trong khi broker, DLT hoặc registry còn message cũ.
- Giả định schema registry tự giải quyết thay đổi ý nghĩa nghiệp vụ.
- Dùng default giả tạo khi V1 không có dữ liệu cần thiết cho V2.
- Coi Event Publication Registry là event store lưu lịch sử vô hạn.
- Rollback publisher về V1 dù V2 đã phát dữ liệu không thể biểu diễn trong V1.
- Bỏ qua ordering và side effect trùng khi replay.

## Kết luận

Chuyển đổi event giữa phiên bản cần một kế hoạch phối hợp publisher, consumer, serializer, broker và dữ liệu đã lưu. Dùng expand-and-contract để consumer hiểu V2 trước khi publisher chuyển đổi; dùng adapter/upcaster để cô lập V1; chỉ dual-publish khi có lý do và phải bảo đảm idempotency. Với Spring Modulith, giữ khả năng deserialize publication cũ trong thời gian retry/recovery, đồng thời theo dõi externalization và consumer riêng biệt. Chỉ loại bỏ V1 sau khi backlog, retention và replay window đã được xử lý, nhờ đó migration không làm mất event hoặc tạo side effect trùng.
