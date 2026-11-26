# Checkpoint projection trong Spring Modulith

Một read model thường được xây dựng bằng cách nhận các application event rồi cập nhật dữ liệu phục vụ truy vấn. Khi số lượng event tăng hoặc ứng dụng phải khởi động lại, projection cần biết mình đã xử lý đến đâu để tiếp tục mà không bỏ sót hoặc áp dụng một event nhiều lần. **Checkpoint projection** là cách lưu lại vị trí xử lý đã hoàn tất của từng projection trong một luồng event, sau đó dùng vị trí này để tiếp tục xử lý hoặc khôi phục read model.

Trong module `SPRING_MODULITH_APPLICATION_EVENTS`, checkpoint kết nối giao tiếp bằng application event với quá trình xây dựng read model. Spring Modulith cung cấp cơ chế publish/listen và Event Publication Registry để theo dõi việc giao event tới listener. Checkpoint là trạng thái tiến độ của chính projection: nó cho biết projection đã áp dụng dữ liệu nguồn tới vị trí nào. Hai loại trạng thái này hỗ trợ nhau nhưng có trách nhiệm khác nhau.

## 1. Vì sao projection cần checkpoint?

Giả sử module đơn hàng phát các event `OrderCreated`, `OrderLineAdded` và `OrderCompleted`. Một projection lắng nghe các event này để duy trì bảng `order_summary`, phục vụ màn hình danh sách đơn hàng. Khi ứng dụng xử lý liên tục, projection có thể cập nhật từng event theo thứ tự.

Nếu tiến trình dừng giữa chừng, projection cần biết event cuối cùng đã được áp dụng thành công. Nếu không lưu vị trí đó, ứng dụng khó xác định nên tiếp tục từ đâu. Nếu đọc lại toàn bộ event mà không có cơ chế chống lặp, tổng tiền hoặc số lượng trong read model có thể bị cộng hai lần.

Checkpoint giải quyết câu hỏi: **projection này đã xử lý liên tục tới vị trí nào trong nguồn event?** Vị trí có thể là sequence number của aggregate, offset của partition trong broker, hoặc một cursor do nguồn event cung cấp. Cần chọn một vị trí có thứ tự và có ý nghĩa rõ ràng trong phạm vi luồng đang xử lý.

Ví dụ một luồng event có sequence:

```text
OrderCreated       aggregateVersion = 1
OrderLineAdded     aggregateVersion = 2
OrderLineAdded     aggregateVersion = 3
OrderCompleted     aggregateVersion = 4
```

Nếu projection đã commit đến version `3`, checkpoint lưu `lastPosition = 3`. Sau khi restart, projection có thể tiếp tục từ version `4`. Nếu event version `3` được giao lại, projection nhận ra vị trí đó đã được xử lý và không áp dụng lần nữa.

## 2. Checkpoint là gì và lưu ở đâu?

Checkpoint là bản ghi tiến độ xử lý của một projection. Một checkpoint thường cần các thông tin:

- **Projection name:** tên ổn định của read model hoặc projector.
- **Stream identity:** định danh nguồn hoặc luồng mà checkpoint theo dõi, chẳng hạn aggregate ID hay partition ID.
- **Last position:** vị trí cuối cùng đã được áp dụng thành công.
- **Projection revision:** phiên bản logic hoặc schema của projection.
- **Updated at:** thời điểm checkpoint được cập nhật.

Ví dụ bảng checkpoint:

```sql
CREATE TABLE projection_checkpoint (
    projection_name   VARCHAR(120) NOT NULL,
    stream_id         VARCHAR(200) NOT NULL,
    last_position     BIGINT NOT NULL,
    projection_revision INTEGER NOT NULL,
    updated_at        TIMESTAMP NOT NULL,
    PRIMARY KEY (projection_name, stream_id)
);
```

Đây là schema minh họa; kiểu dữ liệu và cú pháp thời gian cần điều chỉnh theo database. Khóa chính kết hợp projection và stream giúp mỗi projection có tiến độ độc lập trên từng luồng.

Checkpoint thường được lưu bền vững trong database. Nếu chỉ giữ vị trí trong RAM, ứng dụng sẽ mất tiến độ sau restart. Nếu checkpoint nằm ở một kho khác với read model, việc cập nhật hai nơi có thể không nguyên tử: read model đã đổi nhưng checkpoint chưa đổi, hoặc ngược lại. Với projection lưu trong database, cách đơn giản và an toàn thường là lưu checkpoint cùng database và cập nhật trong cùng transaction với read model.

## 3. Chọn đơn vị checkpoint

Vị trí checkpoint phải tương ứng với đơn vị mà nguồn event có thể đảm bảo thứ tự.

| Đơn vị | Ví dụ vị trí | Khi phù hợp |
| --- | --- | --- |
| Theo aggregate | `orderId` + `aggregateVersion` | Nguồn bảo đảm thứ tự event trong từng aggregate |
| Theo partition | `partitionId` + `offset` | Broker chia luồng thành partition và bảo đảm thứ tự trong partition |
| Theo toàn bộ stream | `streamId` + `position` | Event store cung cấp một sequence toàn cục có thứ tự |
| Theo tenant hoặc shard | `tenantId`/`shardId` + cursor | Projection xử lý nhiều luồng độc lập được phân vùng |

Không nên dùng một checkpoint toàn cục nếu nguồn chỉ bảo đảm thứ tự theo từng aggregate. Ví dụ, `Order-100` có version `5` và `Order-200` cũng có version `5`; hai con số này không thể so sánh như vị trí của cùng một stream. Khi đó, checkpoint cần có `stream_id` là aggregate ID.

Với Kafka, offset chỉ có ý nghĩa trong một partition. Nếu projection đọc nhiều partition, cần checkpoint riêng cho từng partition. Offset `100` ở partition `0` không có quan hệ thứ tự với offset `100` ở partition `1`.

Thời điểm `occurredAt` và `eventId` không phải cursor đáng tin cậy để xác định tiến độ. Nhiều event có thể có cùng timestamp; đồng hồ giữa các máy có thể lệch; UUID không thể hiện thứ tự xử lý. Hãy dùng sequence hoặc offset do nguồn cấp.

## 4. Cập nhật read model và checkpoint trong cùng transaction

Quy tắc quan trọng nhất là: **chỉ tiến checkpoint sau khi thay đổi read model đã được commit thành công**. Với read model và checkpoint nằm trong cùng database, hãy cập nhật cả hai trong một transaction.

Ví dụ event có version theo aggregate:

```java
public record OrderLineAdded(
        UUID eventId,
        UUID orderId,
        long aggregateVersion,
        String productCode,
        int quantity,
        BigDecimal unitPrice
) {}
```

Projector áp dụng event và cập nhật checkpoint:

```java
@Service
class OrderSummaryProjector {

    private final OrderSummaryRepository summaries;
    private final ProjectionCheckpointRepository checkpoints;

    OrderSummaryProjector(
            OrderSummaryRepository summaries,
            ProjectionCheckpointRepository checkpoints
    ) {
        this.summaries = summaries;
        this.checkpoints = checkpoints;
    }

    @Transactional
    public void project(OrderLineAdded event) {
        ProjectionCheckpoint checkpoint = checkpoints
                .lockOrCreate("order-summary", event.orderId().toString());

        long current = checkpoint.lastPosition();

        if (event.aggregateVersion() <= current) {
            return; // duplicate hoặc event cũ đã được áp dụng
        }

        if (event.aggregateVersion() != current + 1) {
            throw new ProjectionGapException(
                    event.orderId(), current + 1, event.aggregateVersion()
            );
        }

        summaries.addLine(
                event.orderId(),
                event.productCode(),
                event.quantity(),
                event.unitPrice()
        );

        checkpoints.advance(
                "order-summary",
                event.orderId().toString(),
                event.aggregateVersion()
        );
    }
}
```

Các repository trong ví dụ là abstraction minh họa. `lockOrCreate` cần được triển khai bằng cơ chế khóa hoặc cập nhật có kiểm soát; trường hợp tạo checkpoint đầu tiên đồng thời phải được bảo vệ bằng unique constraint. Nếu event có version bắt đầu từ `1`, checkpoint mới cần có vị trí ban đầu `0`.

Do phương thức `project` có `@Transactional`, cập nhật read model và checkpoint cùng commit hoặc cùng rollback, với điều kiện cả hai repository tham gia cùng transaction manager. Nếu `summaries.addLine` thất bại, checkpoint không được tiến lên. Nếu cập nhật checkpoint thất bại, thay đổi read model cũng phải rollback.

## 5. Kết hợp listener Spring Modulith với projector

Listener có thể nhận application event rồi chuyển công việc cập nhật read model sang một service có transaction riêng:

```java
@Component
class OrderSummaryListener {

    private final OrderSummaryProjector projector;

    OrderSummaryListener(OrderSummaryProjector projector) {
        this.projector = projector;
    }

    @ApplicationModuleListener
    void on(OrderLineAdded event) {
        projector.project(event);
    }
}
```

Trong ví dụ, listener nhận event và gọi projector. Transaction được đặt trên service cập nhật read model để việc ghi projection và checkpoint có cùng ranh giới. Cần cấu hình listener phase và transaction theo yêu cầu nghiệp vụ; với event phát trong transaction nguồn, listener sau commit giúp projection chỉ phản ứng với thay đổi đã commit. Cơ chế chính xác của `@ApplicationModuleListener` cần được hiểu theo phiên bản Spring Modulith đang dùng.

Event Publication Registry theo dõi publication tới listener. Khi listener hoàn tất thành công, registry ghi nhận publication đã hoàn tất. Checkpoint trong ví dụ lại theo dõi vị trí mà `order-summary` đã áp dụng. Nếu listener được giao lại một event đã xử lý, checkpoint giúp projector nhận ra event cũ và bỏ qua việc áp dụng lần nữa.

### Event Publication Registry không phải checkpoint projection

Hai cơ chế giải quyết hai câu hỏi khác nhau:

| Cơ chế | Câu hỏi được trả lời |
| --- | --- |
| Event Publication Registry | Event đã được giao tới listener này hoàn tất chưa? |
| Projection checkpoint | Read model này đã áp dụng nguồn event tới vị trí nào? |

Registry theo dõi publication theo listener và hỗ trợ xử lý publication chưa hoàn tất. Nó không mặc định là event store có thể phát lại mọi event đã hoàn tất từ một vị trí tùy ý, cũng không tự tạo một cursor toàn cục cho mọi projection. Nếu cần rebuild từ đầu, ứng dụng phải có nguồn event có thể replay, snapshot phù hợp hoặc cơ chế xuất dữ liệu khác.

## 6. Xử lý duplicate, gap và event sai thứ tự

Checkpoint chỉ an toàn khi projector hiểu thứ tự của nguồn event. Với sequence liên tục trong một stream, có thể phân loại event như sau:

| Điều kiện | Diễn giải | Hành động |
| --- | --- | --- |
| `eventPosition <= lastPosition` | Event đã được xử lý hoặc là event cũ | Bỏ qua như duplicate/stale event |
| `eventPosition == lastPosition + 1` | Event kế tiếp đúng thứ tự | Áp dụng projection rồi tiến checkpoint |
| `eventPosition > lastPosition + 1` | Có khoảng trống trong stream | Không tiến checkpoint; chờ hoặc tìm event bị thiếu |

Ví dụ checkpoint đang ở `12` nhưng event `15` tới trước `13` và `14`. Nếu projector áp dụng event `15` rồi ghi checkpoint `15`, hai event bị thiếu có thể bị bỏ qua khi khôi phục. Cách an toàn là giữ event `15` chờ xử lý, yêu cầu nguồn phát lại khoảng thiếu, hoặc lưu nó vào bảng pending/inbox trong khi checkpoint liên tục vẫn ở `12`.

Không phải mọi nguồn event đều có sequence không có khoảng trống. Nếu sequence chỉ tăng cho những event thuộc một loại cụ thể hoặc có thể bị lọc, điều kiện `lastPosition + 1` sẽ không đúng. Hãy định nghĩa rõ cursor liên tục trên tập dữ liệu mà projection thực sự nhận. Nếu không thể có cursor liên tục, cần dùng một cơ chế khác như inbox theo event ID, watermark hoặc tập hợp vị trí đã hoàn tất.

Với event theo aggregate, có thể dùng `aggregateVersion` để phát hiện gap. Tuy nhiên, projector chỉ nên yêu cầu version liên tiếp nếu mọi thay đổi làm tăng version đều phát event mà projection cần thấy. Nếu aggregate phát nhiều loại event và projector chỉ nhận một loại, hãy dùng sequence riêng cho stream projection hoặc lưu cách xác định version đã quan sát.

## 7. Đồng thời và khóa checkpoint

Hai instance ứng dụng có thể nhận event của cùng một stream gần như đồng thời. Nếu cả hai cùng đọc checkpoint `10`, chúng có thể cùng áp dụng event `11`, làm read model bị cập nhật hai lần. Cần bảo vệ việc đọc, áp dụng và tiến checkpoint.

Một số cách triển khai:

- **Pessimistic locking:** khóa dòng checkpoint trong transaction, chẳng hạn `SELECT ... FOR UPDATE`, để chỉ một projector cập nhật stream tại một thời điểm.
- **Optimistic locking:** dùng version column và cập nhật có điều kiện; nếu có xung đột, rollback rồi đọc lại trạng thái và xử lý lại.
- **Partition ownership:** phân phối mỗi stream hoặc partition cho một consumer tại một thời điểm, đồng thời vẫn giữ idempotency vì rebalance có thể giao lại event.
- **Unique constraint:** bảo vệ việc tạo checkpoint và inbox entry khi có xử lý đồng thời.

Khóa cần được giữ trong phạm vi transaction cập nhật projection và checkpoint. Tránh giữ lock trong khi gọi dịch vụ mạng hoặc thực hiện công việc lâu. Nếu một projection có lưu lượng lớn, có thể phân vùng theo aggregate hoặc partition để nhiều stream được xử lý song song mà không tranh chấp cùng một checkpoint.

## 8. Checkpoint với Kafka hoặc AMQP

Khi projection tiêu thụ event từ broker, broker thường có cơ chế tiến độ riêng. Với Kafka, consumer group quản lý offset theo partition. Với AMQP, consumer acknowledgement cho broker biết message đã được xử lý theo semantics của queue.

Nếu read model và checkpoint lưu trong database, cần phối hợp commit database với offset/acknowledgement của broker:

1. Nhận message.
2. Mở transaction database.
3. Cập nhật read model và checkpoint/inbox.
4. Commit database.
5. Sau khi commit thành công, commit Kafka offset hoặc acknowledge message AMQP theo cơ chế consumer.

Nếu ứng dụng commit offset hoặc acknowledge trước khi database commit, tiến trình có thể dừng sau acknowledgement và trước khi lưu read model. Broker sẽ không giao lại message đó, dẫn đến mất cập nhật projection. Nếu database commit xong nhưng tiến trình dừng trước acknowledgement, broker có thể giao lại message; checkpoint hoặc inbox phải nhận diện duplicate.

Vì vậy, thứ tự thường dùng cho xử lý at-least-once là commit read model trước, sau đó mới acknowledge broker. Cách này chấp nhận khả năng giao lặp và dựa vào idempotency. Nếu dùng Kafka offset làm checkpoint duy nhất, phải hiểu rõ semantics offset, partition assignment, rebalance và cách offset commit phối hợp với transaction xử lý. Không dùng một offset đơn lẻ cho nhiều partition.

Với application event nội bộ của Spring Modulith, không có Kafka offset hay AMQP delivery tag. Projection có thể dùng sequence/version của event nghiệp vụ hoặc cursor của nguồn replay mà ứng dụng quản lý.

## 9. Khôi phục projection sau restart

Khi ứng dụng khởi động lại, projector đọc checkpoint đã lưu rồi tiếp tục từ vị trí kế tiếp trong nguồn event. Quá trình này chỉ hoạt động nếu nguồn event vẫn cung cấp được dữ liệu từ vị trí đó trở đi.

Một quy trình resume thường gồm:

1. Đọc checkpoint theo projection và stream.
2. Xác định vị trí kế tiếp cần xử lý.
3. Đọc event từ nguồn theo cursor đã lưu.
4. Áp dụng event và cập nhật checkpoint trong transaction.
5. Tiếp tục cho tới khi projection theo kịp nguồn.

Nếu nguồn là broker có retention, event cũ có thể đã bị xóa trước khi projection phục hồi. Nếu nguồn là event store, cần bảo đảm event stream vẫn được lưu. Event Publication Registry chỉ có thể hỗ trợ phát lại publication còn dang dở theo cơ chế của nó; nó không tự cung cấp toàn bộ lịch sử event đã hoàn tất để rebuild read model.

Khi checkpoint bị mất hoặc không còn tương thích với nguồn, cần xác định có thể rebuild từ đầu hay phục hồi từ snapshot. Không nên tự đặt checkpoint về `0` trong khi giữ nguyên read model hiện tại: event cũ sẽ được áp dụng lại trên dữ liệu đã có và có thể làm sai số liệu.

## 10. Snapshot và checkpoint

Với stream dài, replay từ đầu có thể tốn thời gian. Có thể tạo snapshot của projection tại một vị trí đã biết, rồi tiếp tục replay event sau vị trí đó.

Snapshot cần đi cùng vị trí mà nó đại diện:

```text
Projection: order-summary
Snapshot generation: 2026-11-25T10:00Z
Snapshot position: 850000
Projection revision: 3

Read model snapshot: trạng thái đã áp dụng tới position 850000
Checkpoint: lastPosition = 850000
Replay tiếp: 850001 trở đi
```

Snapshot và checkpoint phải nhất quán. Nếu snapshot chứa dữ liệu tới `850000` nhưng checkpoint chỉ ghi `849999`, event `850000` có thể bị áp dụng lặp. Nếu checkpoint ghi `850001` nhưng snapshot mới chỉ tới `850000`, event `850001` có thể bị bỏ qua. Hãy tạo snapshot và checkpoint trong cùng transaction hoặc dùng một quy trình tạo snapshot có manifest/version để xác nhận cặp dữ liệu khớp nhau.

Với projection lớn, có thể xây dựng read model mới ở bảng hoặc generation riêng. Khi rebuild xong và đã bắt kịp nguồn, chuyển traffic đọc sang generation mới bằng một thao tác chuyển đổi có kiểm soát. Cách này tránh để người dùng đọc dữ liệu đang được xóa và dựng lại.

## 11. Rebuild khi logic projection thay đổi

Checkpoint phản ánh tiến độ của một phiên bản logic projection cụ thể. Nếu thay đổi cách tính tổng tiền, quy tắc lọc hoặc cách diễn giải event, checkpoint cũ không chứng minh read model đã được xây dựng theo logic mới.

Hãy quản lý `projection_revision` hoặc generation. Khi thay đổi logic không tương thích, có thể:

- Tạo projection mới với tên/generation mới, replay từ nguồn event rồi chuyển người đọc sang projection mới.
- Xây dựng snapshot mới bằng logic mới và lưu checkpoint tương ứng.
- Chạy migration dữ liệu nếu thay đổi có thể chuyển đổi an toàn mà không cần replay.

Không chỉ tăng revision của checkpoint trong khi giữ nguyên dữ liệu cũ nếu logic mới yêu cầu tính lại các trường đã tồn tại. Revision mới phải gắn với một read model đã được xây dựng lại hoặc chuyển đổi đầy đủ.

Khi đổi cấu trúc event, serializer hoặc tên class, cần bảo đảm nguồn replay vẫn deserialize được event cũ. Đây là lý do projection rebuild phải được phối hợp với chiến lược versioning của event payload.

## 12. Theo dõi độ trễ projection

Checkpoint không chỉ phục vụ restart; nó còn là tín hiệu để đo read model đang theo kịp nguồn tới đâu.

Các chỉ số nên quan sát:

- **Checkpoint position:** vị trí cuối cùng đã commit cho từng projection/stream.
- **Source head:** vị trí mới nhất có thể đọc từ nguồn.
- **Projection lag:** khoảng cách giữa source head và checkpoint, nếu hai vị trí cùng một miền thứ tự.
- **Processing rate:** số event projection xử lý trong một khoảng thời gian.
- **Oldest pending event:** tuổi của event cũ nhất chưa được áp dụng.
- **Gap count:** số stream phát hiện thiếu sequence hoặc event sai thứ tự.
- **Failure/retry count:** số lần projector thất bại và số lần event được giao lại.
- **Rebuild duration:** thời gian dựng lại projection hoặc generation mới.

Không tính lag bằng cách trừ timestamp tùy ý nếu event time và processing time có ý nghĩa khác nhau. Với Kafka, so sánh offset phải theo từng partition. Với sequence theo aggregate, không có một source head toàn cục nếu không tổng hợp rõ ràng.

Read model có thể nhất quán cuối cùng thay vì nhất quán ngay lập tức. Màn hình hoặc API cần biết độ trễ này có thể hiển thị thời điểm cập nhật gần nhất hoặc trạng thái projection đang bắt kịp. Nếu nghiệp vụ yêu cầu read-your-writes, có thể trả về trạng thái tạm thời từ command result hoặc chờ projection đạt một version cụ thể trước khi đọc.

## 13. Kiểm thử checkpoint projection

Kiểm thử một listener được gọi chưa đủ để xác nhận checkpoint hoạt động đúng. Cần kiểm tra sự nhất quán giữa read model, checkpoint và nguồn event trong các tình huống lỗi.

| Tình huống | Điều cần xác nhận |
| --- | --- |
| Event đầu tiên | Checkpoint được tạo đúng với vị trí khởi đầu và tiến lên sau khi projection commit |
| Event kế tiếp | Read model và checkpoint cùng được cập nhật |
| Duplicate event | Event cũ không làm thay đổi read model lần nữa |
| Gap trong sequence | Checkpoint không nhảy qua vị trí bị thiếu |
| Projection ném exception | Read model và checkpoint cùng rollback |
| Lỗi khi ghi checkpoint | Thay đổi read model cũng rollback |
| Hai event đồng thời cùng stream | Lock/version ngăn cập nhật kép hoặc sai thứ tự |
| Restart | Projection tiếp tục từ checkpoint đã commit |
| Snapshot/rebuild | Snapshot position và checkpoint khớp nhau |
| Projection revision mới | Read model được rebuild hoặc migrate theo logic mới |
| Broker ack/offset | Database commit trước acknowledgement; giao lặp không gây sai dữ liệu |

Nên có integration test với database thực tế hoặc loại database tương đương môi trường triển khai để kiểm tra transaction, unique constraint và locking. Test chỉ dùng repository giả không chứng minh hai thay đổi có rollback nguyên tử.

## 14. Những lỗi thiết kế thường gặp

| Lỗi | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Lưu checkpoint trong RAM | Restart làm mất tiến độ | Lưu checkpoint bền vững |
| Cập nhật read model và checkpoint ở hai transaction riêng | Có thể lệch trạng thái sau crash | Cập nhật cùng transaction |
| Dùng timestamp hoặc UUID làm vị trí thứ tự | Không thể xác định event kế tiếp đáng tin cậy | Dùng sequence/offset có thứ tự |
| Dùng một checkpoint cho nhiều partition không có thứ tự chung | Bỏ sót hoặc áp dụng sai thứ tự | Lưu checkpoint riêng cho từng partition |
| Bỏ qua gap rồi tiến checkpoint | Event bị thiếu có thể bị bỏ qua vĩnh viễn | Chặn tiến độ và khôi phục event thiếu |
| Chỉ kiểm tra duplicate bằng event ID trong bộ nhớ | Duplicate sau restart vẫn có thể được áp dụng | Dùng checkpoint hoặc inbox bền vững |
| Commit broker offset trước database | Message bị coi là xong dù read model chưa cập nhật | Commit database trước rồi acknowledge |
| Reset checkpoint nhưng giữ read model | Event cũ bị áp dụng lặp lên dữ liệu hiện tại | Rebuild/migrate read model đồng bộ với checkpoint |
| Giữ checkpoint cũ sau khi đổi logic projection | Read model mang logic cũ nhưng bị coi là mới | Quản lý revision và rebuild |
| Coi Event Publication Registry là event store | Không thể replay lịch sử event đã hoàn tất tùy ý | Dùng nguồn event/snapshot có khả năng replay |

## 15. Quy trình triển khai checkpoint projection

Khi xây dựng một read model cần khả năng resume và rebuild, hãy thực hiện theo thứ tự:

1. Xác định projection, nguồn event và đơn vị thứ tự mà nguồn bảo đảm.
2. Chọn cursor phù hợp: aggregate version, broker partition offset hoặc stream position.
3. Thiết kế bảng checkpoint với khóa theo projection và stream, có revision/generation khi cần.
4. Tạo projector idempotent, xử lý duplicate, gap và event sai thứ tự.
5. Cập nhật read model và checkpoint trong cùng transaction database.
6. Kết nối listener Spring Modulith với projector và chọn transaction phase phù hợp.
7. Nếu tiêu thụ từ broker, chỉ acknowledge/commit offset sau khi transaction read model thành công.
8. Thiết kế resume, snapshot và quy trình rebuild khi checkpoint hoặc logic projection thay đổi.
9. Kiểm thử duplicate, gap, concurrency, rollback, restart và replay.
10. Theo dõi checkpoint lag, event lỗi, backlog và thời gian rebuild.

Checkpoint làm cho tiến độ của read model trở nên bền vững và có thể quan sát. Khi vị trí checkpoint phản ánh đúng thứ tự nguồn, được commit nguyên tử cùng dữ liệu projection và đi kèm logic xử lý duplicate/gap, ứng dụng có thể tiếp tục xây dựng read model sau lỗi hoặc restart mà vẫn giữ được tính nhất quán của dữ liệu truy vấn.
