# Rollback di trú

Trong module **SPRING_MODULITH_APPLICATION_EVENTS**, application events giúp các module Spring Modulith giao tiếp qua sự kiện nghiệp vụ, giảm phụ thuộc trực tiếp và bảo vệ ranh giới nghiệp vụ. Khi thay đổi event contract, schema lưu trữ, publisher hoặc consumer, một bản phát hành mới có thể gây lỗi sau khi đã ghi dữ liệu hoặc phát event theo định dạng mới. **Rollback di trú** là kế hoạch đưa hệ thống về trạng thái vận hành an toàn khi một thay đổi di trú gặp sự cố, đồng thời bảo toàn dữ liệu và tính nhất quán của các luồng event đã phát sinh.

Rollback di trú không chỉ là deploy lại phiên bản code cũ. Trong hệ thống event-driven, message có thể đã được broker lưu, consumer đã commit offset, listener đã tạo side effect và database đã chuyển đổi dữ liệu. Một binary cũ có thể không đọc được schema mới; một migration database có thể không thể đảo ngược sau khi dữ liệu cũ bị xóa. Vì vậy, cần thiết kế khả năng quay lui trước khi triển khai thay đổi.

## 1. Xác định rollback đang quay lui điều gì

Một đợt di trú event thường thay đổi nhiều lớp. Cần tách chúng để chọn hành động phù hợp:

| Lớp | Ví dụ thay đổi | Hướng rollback |
| --- | --- | --- |
| Application code | Publisher/consumer mới, handler hoặc mapping mới. | Deploy lại artifact cũ hoặc tắt feature flag nếu code cũ còn tương thích dữ liệu. |
| Event contract | Đổi tên field, kiểu dữ liệu, event type hoặc schema version. | Khôi phục producer/consumer tương thích; tiếp tục đọc version cũ và mới trong giai đoạn chuyển tiếp. |
| Database schema | Thêm, đổi tên hoặc xóa cột/bảng/index. | Dùng migration tương thích ngược; chỉ chạy down migration khi dữ liệu và dependency cho phép. |
| Database data | Backfill, chuyển đổi giá trị hoặc gộp bản ghi. | Chạy migration ngược có kiểm chứng, restore/PITR hoặc forward-fix tùy khả năng đảo ngược. |
| Broker topology | Đổi topic, partition, ACL hoặc retry route. | Khôi phục cấu hình/topic routing và bảo toàn record/offset. |
| Consumer progress | Chuyển group, commit offset hoặc replay. | Dùng checkpoint/offset đã lưu và replay có kiểm soát; không reset offset tùy tiện. |
| Side effect nghiệp vụ | Giữ hàng, thu tiền, gửi thông báo hoặc tạo shipment. | Dùng compensation hoặc quy trình đối soát; không thể hoàn tác bằng cách deploy code cũ. |

Trước khi rollback, ghi rõ phạm vi: phiên bản code nào, migration nào, topic nào, consumer group nào, khoảng thời gian dữ liệu nào và side effect nào đã xảy ra. Nếu không xác định được phạm vi, dừng thao tác phá hủy và ưu tiên giữ nguyên bằng chứng để điều tra.

## 2. Vì sao rollback event khó hơn rollback ứng dụng đồng bộ?

Trong lời gọi đồng bộ, lỗi thường được trả về trong cùng request và transaction có thể rollback trước khi commit. Với event, publisher có thể đã commit và message được giao sau đó. Consumer có thể xử lý độc lập, chậm hơn publisher hoặc chạy ở phiên bản khác.

Ví dụ, phiên bản mới phát CustomerAddressChangedV2 với field regionCode. Consumer mới xử lý thành công và cập nhật projection. Sau đó phát hiện lỗi, đội vận hành deploy lại consumer cũ chỉ hiểu CustomerAddressChangedV1. Các event V2 vẫn nằm trong topic hoặc sẽ tiếp tục được phát. Nếu consumer cũ không tương thích, backlog có thể bị kẹt hoặc message bị đưa vào DLT.

Một rollback an toàn cần trả lời:

- Publisher nào đã phát event mới và trong khoảng thời gian nào?
- Consumer nào đã đọc event mới và commit offset đến đâu?
- Event nào đã tạo side effect không thể tự đảo ngược?
- Consumer cũ có đọc được event mới không?
- Database schema sau migration còn tương thích với code cũ không?
- Có thể replay event mà không tạo duplicate không?
- Có thể tạm dừng producer/consumer hoặc chuyển traffic trong khi phục hồi không?

## 3. Thiết kế di trú theo hướng expand-contract

Chiến lược expand-contract giảm nhu cầu rollback phá hủy. Thay vì đổi schema hoặc contract trong một lần, chia thành các bước tương thích:

1. **Expand:** thêm field/cột/topic mới mà phiên bản cũ vẫn hoạt động được.
2. **Deploy compatible readers:** consumer đọc được cả dạng cũ và mới; chưa yêu cầu producer phát dạng mới.
3. **Switch writers:** chuyển publisher sang ghi field hoặc event version mới.
4. **Backfill:** chuyển dữ liệu cũ theo batch, có checkpoint và khả năng tiếp tục.
5. **Observe:** xác minh consumer, projection, lỗi và tỷ lệ dữ liệu cũ/mới.
6. **Contract:** chỉ xóa field/cột cũ sau khi không còn consumer hoặc dữ liệu cần nó và thời hạn tương thích đã hết.

Ví dụ thêm region_code vào bảng địa chỉ:

~~~sql
ALTER TABLE customer_address
    ADD COLUMN region_code VARCHAR(32);
~~~

Ở giai đoạn expand, code cũ tiếp tục đọc cột cũ. Code mới có thể ghi cả region và region_code, hoặc dùng adapter để đọc cả hai. Sau khi backfill và tất cả reader chuyển sang cột mới, mới cân nhắc ngừng ghi cột cũ. Việc drop cột cũ là contract và cần một quyết định triển khai riêng.

Với event contract, áp dụng cùng nguyên tắc: thêm field optional trước, cập nhật consumer để chấp nhận field mới, rồi mới để producer phụ thuộc vào field đó. Tránh đổi tên hoặc đổi nghĩa field đang được consumer sử dụng.

## 4. Tương thích ngược của event contract

Rollback code cũ chỉ an toàn nếu code cũ có thể đọc dữ liệu/event được tạo bởi phiên bản mới. Cần đánh giá tương thích ở cả hai chiều:

| Thay đổi | Consumer cũ đọc event mới? | Consumer mới đọc event cũ? |
| --- | --- | --- |
| Thêm field optional có default | Thường có thể, nếu parser bỏ qua field lạ. | Có thể nếu field mới có default hoặc được xử lý thiếu. |
| Thêm field bắt buộc | Có thể thất bại nếu consumer cũ không biết field. | Có thể thất bại khi event cũ thiếu field. |
| Đổi tên field | Thường không tương thích nếu không giữ alias. | Cần đọc cả tên cũ và mới trong giai đoạn chuyển tiếp. |
| Đổi kiểu dữ liệu | Có thể lỗi deserialize hoặc thay đổi ý nghĩa. | Cần converter/upcaster có quy tắc rõ ràng. |
| Xóa field | Có thể làm consumer cũ thiếu dữ liệu cần thiết. | Reader mới cần hỗ trợ event cũ không có field. |
| Đổi ý nghĩa field | Có thể parse thành công nhưng sai nghiệp vụ. | Rất nguy hiểm nếu không đổi event type/version. |

Parse thành công không chứng minh tương thích nghiệp vụ. Ví dụ amount đổi từ đơn vị đồng sang đơn vị xu vẫn là số nguyên hợp lệ nhưng ý nghĩa thay đổi. Với thay đổi semantics, nên tạo event version/type mới và ghi rõ quy tắc chuyển đổi.

## 5. Giữ event version cũ và mới trong thời gian rollback

Khi consumer cần hỗ trợ nhiều version, có thể dùng adapter hoặc upcaster để chuyển payload cũ về mô hình nội bộ hiện tại. Ví dụ:

~~~java
sealed interface AddressChangedPayload {
    record V1(String customerId, String address)
        implements AddressChangedPayload {}
    record V2(String customerId, String address, String regionCode)
        implements AddressChangedPayload {}
}

record AddressChanged(
    String customerId,
    String address,
    String regionCode
) {}

AddressChanged normalize(AddressChangedPayload payload) {
    return switch (payload) {
        case AddressChangedPayload.V1 old ->
            new AddressChanged(old.customerId(), old.address(), null);
        case AddressChangedPayload.V2 current ->
            new AddressChanged(
                current.customerId(),
                current.address(),
                current.regionCode()
            );
    };
}
~~~

Đây là ví dụ mô hình hóa trong code; cách deserialize thực tế phụ thuộc serializer, schema registry và event envelope của ứng dụng. Không ép consumer cũ đọc version mới bằng cách âm thầm gán default sai nghĩa. Nếu thiếu field khiến không thể xử lý an toàn, đưa record vào quarantine/DLT và giữ metadata để điều tra.

Trong giai đoạn rollback, có thể tạm dừng producer phát version mới, nhưng không xóa event đã phát. Consumer tương thích có thể tiếp tục xử lý backlog; nếu phải quay về consumer cũ, cần chuyển đổi event mới sang dạng cũ một cách tường minh và kiểm thử trước.

## 6. Rollback database migration

Migration database có thể chia thành hai nhóm:

- **Reversible:** có thể đảo ngược mà không mất thông tin, ví dụ thêm index hoặc thêm nullable column chưa có dữ liệu phụ thuộc.
- **Irreversible hoặc lossy:** xóa cột, gộp dữ liệu, cắt ngắn giá trị, đổi kiểu làm mất độ chính xác hoặc loại bỏ bản ghi.

Không phải migration nào cũng nên có down migration. Một lệnh DROP COLUMN không thể phục hồi dữ liệu chỉ bằng cách tạo lại cột rỗng. Nếu migration có tính mất dữ liệu, cần backup, snapshot hoặc lưu dữ liệu cũ trước khi thực hiện.

Ví dụ đổi tên cột không nên thực hiện trực tiếp nếu cần hỗ trợ code cũ:

~~~sql
-- Expand: thêm cột mới.
ALTER TABLE customer_address
    ADD COLUMN address_line VARCHAR(500);

-- Backfill theo batch ở một migration/job có checkpoint.
UPDATE customer_address
SET address_line = legacy_address
WHERE address_line IS NULL;
~~~

Sau khi mọi reader/writer dùng address_line và đã qua thời gian quan sát, mới xem xét contract:

~~~sql
ALTER TABLE customer_address
    DROP COLUMN legacy_address;
~~~

Lệnh drop ở bước cuối là ví dụ destructive. Không đưa nó vào cùng đợt deploy với code switch nếu còn khả năng cần rollback về code cũ.

## 7. Khi nào dùng down migration, restore hay forward-fix?

Chọn phương án dựa trên khả năng đảo ngược và lượng dữ liệu đã phát sinh:

| Tình huống | Phương án phù hợp |
| --- | --- |
| Migration chỉ thêm cấu trúc chưa được dùng | Down migration có thể an toàn sau khi xác minh không có dependency. |
| Backfill có mapping ngược chính xác và chưa có write mới | Chạy migration ngược theo batch, có kiểm tra trước/sau. |
| Dữ liệu đã bị gộp hoặc mất thông tin | Restore từ backup/PITR hoặc phục hồi từ nguồn sự thật. |
| Code mới lỗi nhưng schema vẫn tương thích | Rollback artifact hoặc tắt feature flag; giữ schema mở rộng. |
| Schema mới không tương thích code cũ | Deploy bridge version hoặc forward-fix để khôi phục tương thích. |
| Event đã tạo side effect bên ngoài | Compensation hoặc reconciliation; không chỉ reset database. |

**Forward-fix** là triển khai một thay đổi mới để sửa trạng thái hiện tại. Với migration đã làm mất thông tin, forward-fix thường an toàn hơn việc cố chạy down migration giả tạo dữ liệu cũ. Backup/PITR cần được cân nhắc kỹ vì restore toàn database có thể xóa các giao dịch hợp lệ phát sinh sau thời điểm backup.

## 8. Backfill có checkpoint và khả năng tiếp tục

Backfill lớn nên chia batch và lưu tiến độ. Mỗi batch cần idempotent để có thể chạy lại sau lỗi:

~~~java
public void migrateBatch(long afterId, int batchSize) {
    List<CustomerAddress> batch =
        repository.findNextBatch(afterId, batchSize);

    for (CustomerAddress address : batch) {
        if (address.getAddressLine() == null) {
            address.setAddressLine(address.getLegacyAddress());
        }
    }

    repository.saveAll(batch);
    checkpointRepository.save(
        new MigrationCheckpoint("address-line-v2", lastId(batch))
    );
}
~~~

Đoạn code là pseudo-example; transaction của batch và checkpoint phải được thiết kế để commit cùng nhau hoặc có cơ chế phát hiện batch đã hoàn tất. Nếu checkpoint commit trước dữ liệu, một crash có thể làm bỏ sót batch. Nếu dữ liệu commit trước checkpoint, batch có thể chạy lại, vì vậy thao tác phải idempotent.

Khi rollback, checkpoint giúp xác định phạm vi đã chuyển đổi. Có thể dừng job, giữ nguyên dữ liệu đã chuyển và tiếp tục sau khi sửa; hoặc chạy migration ngược cho các batch đã xác nhận. Không giả định chỉ cần reset checkpoint về 0 là có thể đảo ngược dữ liệu.

## 9. Dual-write và nguồn sự thật

Trong thời gian chuyển đổi, hệ thống có thể phải ghi cả field cũ và mới hoặc phát cả event cũ và mới. Dual-write giúp consumer cũ và mới cùng hoạt động nhưng tạo nguy cơ hai bản ghi không nhất quán.

Nếu dùng dual-write:

- Xác định một nguồn sự thật cho mỗi field hoặc event.
- Thực hiện hai thay đổi trong cùng transaction khi cùng database.
- Nếu ghi ra broker và database, dùng outbox hoặc cơ chế phối hợp bền vững.
- Gắn cùng eventId/correlationId để đối chiếu hai luồng.
- Theo dõi chênh lệch giữa dữ liệu cũ và mới.
- Có thời điểm dừng dual-write và điều kiện rollback rõ ràng.

Không để hai consumer cùng áp dụng một nghiệp vụ như hai lệnh độc lập nếu không có idempotency. Nếu phát cả V1 và V2, cần phân biệt chúng là hai biểu diễn của cùng một sự kiện hay hai sự kiện nghiệp vụ khác nhau; eventId và deduplication policy phải phản ánh điều đó.

## 10. Rollback publisher và consumer theo thứ tự

Thứ tự rollback phụ thuộc vào nguồn gây lỗi. Một quy trình thường dùng khi producer mới phát event không tương thích:

1. Tạm dừng hoặc tắt feature flag khiến producer phát event version mới.
2. Giữ nguyên topic và record đã phát; không xóa message.
3. Xác định consumer nào đã đọc và consumer nào còn backlog.
4. Nếu consumer mới lỗi, chuyển sang bridge consumer có thể đọc cả version cũ và mới.
5. Khôi phục phiên bản publisher tương thích với consumer đang hoạt động.
6. Xác minh retry/DLT, offset và side effect trước khi tiếp tục traffic.

Không nhất thiết rollback publisher trước consumer trong mọi tình huống. Nếu consumer mới có lỗi nhưng producer cũ vẫn phát event hợp lệ, có thể khôi phục consumer trước. Điều quan trọng là tránh tạo thêm dữ liệu mà reader hiện tại không thể hiểu.

Với Spring Modulith nội bộ, publisher và listener thường nằm trong cùng ứng dụng hoặc cùng release. Tuy vậy, event publication có thể được xử lý bất đồng bộ sau commit; rollback code không xóa publication record đã commit. Cần xác minh listener cũ có thể xử lý publication đang incomplete và event đã lưu trong persistence hay không.

## 11. Offset, replay và consumer group khi rollback

Kafka offset là tiến độ consumer group, không phải bản sao dữ liệu nghiệp vụ. Reset offset có thể khiến record được giao lại hoặc bỏ qua record, nhưng không đảo ngược side effect đã commit.

Trước khi thay đổi offset:

- Lưu lại offset hiện tại theo từng partition.
- Xác định record đã xử lý thành công và side effect tương ứng.
- Xác định retention còn giữ đủ event để replay hay không.
- Kiểm tra idempotency của consumer.
- Thử replay trên môi trường riêng hoặc từ checkpoint.
- Chọn rõ reset to earliest, specific offset hoặc timestamp; tránh thao tác hàng loạt không có phạm vi.

Nếu consumer mới đã xử lý event sai, reset offset rồi chạy consumer cũ có thể tạo duplicate hoặc áp dụng sai thứ tự. Cần sửa/đối soát trạng thái dữ liệu trước hoặc dùng consumer có logic bù trừ. Với projection có thể tái tạo, có thể xây dựng lại projection từ event log vào storage mới rồi chuyển traffic sau khi xác minh.

## 12. Event Publication Registry, outbox và inbox khi rollback

Các bảng điều phối event có vòng đời riêng:

| Thành phần | Điều cần giữ khi rollback |
| --- | --- |
| Event Publication Registry | Publication incomplete, listener identifier và trạng thái cần recovery. |
| Outbox | Event chưa được gửi, event đã gửi và metadata để retry không mất record. |
| Inbox/deduplication | Event ID đã xử lý để ngăn side effect lặp khi replay. |
| Consumer offset | Checkpoint tiến độ theo partition/group. |
| Saga/process manager | Trạng thái quy trình, step đã hoàn tất và compensation đang chờ. |

Không xóa registry hoặc inbox chỉ vì deploy lại code. Xóa inbox có thể khiến event đã xử lý bị áp dụng lần nữa; xóa outbox có thể làm mất event chưa phát; xóa publication incomplete có thể loại bỏ dấu vết cần recovery.

Nếu cấu trúc bảng thay đổi, giữ migration tương thích với phiên bản code rollback. Với Spring Modulith Event Publication Registry, kiểm tra khả năng tương thích giữa phiên bản thư viện, schema registry và API recovery trước khi thay đổi dependency. Registry theo dõi publication đến transactional listener; nó không thay thế Kafka offset, outbox hay trạng thái nghiệp vụ của saga.

## 13. Rollback side effect bằng compensation

Một event có thể kích hoạt hành động bên ngoài database: thu tiền, gửi email, giữ hàng hoặc tạo vận đơn. Những side effect này không biến mất khi rollback transaction hoặc deploy lại code cũ.

Phân loại:

- **Có thể đảo ngược trực tiếp:** xóa reservation chưa sử dụng hoặc hủy một bản ghi chưa được công bố.
- **Cần compensation:** hoàn tiền, giải phóng hàng, hủy shipment theo API nghiệp vụ.
- **Không thể đảo ngược:** email đã gửi, thông báo đã hiển thị hoặc hành động vật lý đã xảy ra; cần ghi nhận và xử lý tiếp theo thay vì giả vờ hoàn tác.

Ví dụ saga đặt hàng đã giữ hàng và thu tiền. Nếu migration làm sai bước xác nhận đơn, quy trình compensation có thể hoàn tiền và giải phóng hàng theo thứ tự được domain quy định. Mỗi compensation cần idempotency key, trạng thái, retry policy và audit.

Không dùng một câu SQL cập nhật trạng thái đơn hàng về PENDING để thay thế hoàn tiền hoặc hủy reservation. Trạng thái database phải phản ánh side effect thực tế đã xảy ra.

## 14. Feature flag và canary như điểm dừng rollback

Feature flag cho phép tắt luồng mới mà không phải deploy ngay. Canary rollout giúp giới hạn số publisher/consumer hoặc tỷ lệ traffic dùng contract mới.

Một rollout có thể gồm:

1. Deploy code có khả năng đọc cả V1 và V2 nhưng chưa phát V2.
2. Bật V2 cho một nhóm nhỏ publisher.
3. Theo dõi deserialize failure, consumer lag, DLT, publication incomplete và business metrics.
4. Tăng dần phạm vi nếu các chỉ số ổn định.
5. Nếu có sự cố, tắt flag phát V2 và dừng mở rộng canary.
6. Khôi phục publisher/consumer tương thích, giữ event đã phát để xử lý hoặc replay.
7. Chỉ contract schema cũ sau khi hết thời hạn rollback.

Feature flag không xóa event đã phát và không hoàn tác dữ liệu đã ghi. Nó chỉ ngăn luồng mới tiếp tục tạo thêm thay đổi. Cần kiểm tra flag có hiệu lực trên tất cả instance và không tạo ra trạng thái mixed behavior ngoài dự kiến.

## 15. Quy trình rollback có kiểm soát

Một runbook rollback nên có các bước:

### Bước 1: Phát hiện và khoanh vùng

- Ghi nhận thời điểm bắt đầu, release, migration ID và consumer group bị ảnh hưởng.
- Xác định lỗi nằm ở publisher, schema, consumer, broker, database hay side effect.
- Đánh giá mức độ ảnh hưởng và các event đang nằm trong main/retry/DLT topic.
- Tạm dừng thay đổi tiếp theo và hạn chế phát thêm event version lỗi.

### Bước 2: Bảo toàn bằng chứng

- Lưu offset, checkpoint, migration version và trạng thái publication.
- Ghi lại số lượng event theo topic, partition và retry stage.
- Snapshot/backup dữ liệu cần thiết trước thao tác destructive.
- Không xóa DLT, registry, inbox, outbox hoặc dữ liệu gốc để làm sạch trạng thái.

### Bước 3: Chọn phương án

- Rollback artifact nếu schema/event contract còn tương thích.
- Tắt feature flag hoặc chuyển traffic về phiên bản ổn định.
- Deploy bridge version nếu code cũ không đọc được event mới.
- Restore/PITR hoặc chạy forward-fix nếu dữ liệu đã biến đổi không thể đảo ngược.
- Dùng compensation và reconciliation cho side effect đã phát sinh.

### Bước 4: Thực hiện trong phạm vi nhỏ

- Thử trên một consumer group hoặc một canary instance.
- Xác minh schema, event parsing, offset và idempotency.
- Theo dõi lỗi, lag và side effect trước khi mở rộng.
- Giữ khả năng dừng ngay nếu xuất hiện lỗi mới.

### Bước 5: Xác minh phục hồi

- Publisher chỉ phát contract được consumer hỗ trợ.
- Consumer xử lý backlog theo đúng version và không tạo duplicate.
- Publication incomplete và DLT có kế hoạch recovery.
- Dữ liệu cũ/mới khớp theo invariant nghiệp vụ.
- Compensation hoàn tất hoặc được chuyển sang trạng thái cần can thiệp.
- Metrics và cảnh báo trở về ngưỡng chấp nhận được.

## 16. Kiểm thử rollback trước khi triển khai

Rollback plan cần được diễn tập trong staging hoặc môi trường gần production. Không đợi sự cố thật mới xác minh down migration hoặc replay.

| Kịch bản | Điều cần xác minh |
| --- | --- |
| Deploy code mới rồi quay lại code cũ | Code cũ đọc được schema/database đã expand. |
| Producer đã phát V2 | Consumer bridge hoặc consumer cũ xử lý theo compatibility policy. |
| Consumer mới tạo projection sai | Có thể rebuild projection hoặc phục hồi từ event/checkpoint. |
| Backfill dừng giữa chừng | Job tiếp tục được từ checkpoint hoặc đảo ngược đúng phạm vi. |
| Down migration thất bại | Dữ liệu nguồn còn được bảo toàn và có phương án forward-fix. |
| Retry/DLT có backlog | Không mất record và replay không tạo duplicate. |
| Offset đã commit | Có checkpoint để quyết định replay mà không bỏ sót. |
| Side effect ngoài hệ thống | Compensation và reconciliation hoạt động idempotent. |
| Mixed application versions | Producer/consumer cũ và mới cùng chạy không phá contract. |
| Database restore | Dữ liệu phát sinh sau thời điểm backup được xử lý theo kế hoạch. |

Test migration ngược trên bản sao dữ liệu đại diện, không chỉ trên database rỗng. Kiểm tra row count, checksum hoặc business invariant trước và sau rollback. Với event, xác minh cả payload, key, header, schema version và trạng thái consumer.

## 17. Theo dõi tín hiệu trong lúc rollback

Trong quá trình rollback, theo dõi:

- Tỷ lệ lỗi deserialize/schema compatibility theo event version.
- Consumer lag và tuổi record lâu nhất.
- Số publication incomplete theo listener.
- Retry topic backlog và DLT volume.
- Outbox chưa gửi, inbox duplicate và số lần replay.
- Số side effect đã thực hiện và compensation đang chờ.
- Tỷ lệ dữ liệu cũ/mới sau backfill.
- Database lock, connection pool, migration duration và replication lag.

Log cần có migrationId, release version, eventId, eventType/schemaVersion, correlationId, topic/partition/offset, consumer group và rollback action. Không ghi payload nhạy cảm hoặc secret.

Đặt ngưỡng dừng rollout trước khi triển khai. Ví dụ, nếu lỗi deserialize vượt ngưỡng, DLT tăng nhanh hoặc consumer lag vượt SLA, dừng canary và kích hoạt runbook. Ngưỡng cụ thể phải dựa trên SLO và tải thực tế.

## 18. Checklist chuẩn bị rollback di trú

- Phân biệt rollback code, schema, data, broker, offset và side effect.
- Dùng expand-contract để code cũ và mới cùng tồn tại trong thời gian chuyển tiếp.
- Kiểm tra compatibility hai chiều của event schema và semantics.
- Giữ consumer bridge/upcaster nếu cần đọc nhiều event version.
- Không chạy destructive contract migration khi còn cửa sổ rollback.
- Backfill có checkpoint, batch và tính idempotent.
- Có backup/PITR và đã diễn tập restore trên bản sao dữ liệu.
- Lưu offset/checkpoint trước khi đổi consumer group hoặc replay.
- Bảo toàn Event Publication Registry, outbox, inbox và DLT.
- Có idempotency cho consumer, replay và compensation.
- Feature flag/canary có điều kiện dừng và cách tắt đã kiểm thử.
- Runbook nêu rõ owner, thứ tự thao tác, điều kiện tiếp tục và điều kiện dừng.
- Xác minh dữ liệu và business invariant sau rollback.
- Theo dõi backlog, publication incomplete, DLT và side effect cho đến khi ổn định.

Rollback di trú event cần được thiết kế như một phần của quá trình di trú, không phải thao tác cứu hộ được nghĩ ra sau sự cố. Khi schema và event contract duy trì tương thích trong giai đoạn chuyển tiếp, backfill có checkpoint, offset và publication được bảo toàn, còn side effect có compensation hoặc reconciliation riêng, đội phát triển có thể quay lui có kiểm soát mà không làm mất event hoặc tạo trạng thái nghiệp vụ sai.
