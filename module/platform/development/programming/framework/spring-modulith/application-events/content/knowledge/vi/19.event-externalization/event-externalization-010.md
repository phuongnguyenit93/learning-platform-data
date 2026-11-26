# Tắt hoặc thay đổi externalization

Trong module **SPRING_MODULITH_APPLICATION_EVENTS**, application events cho phép các module trao đổi thông tin qua hợp đồng sự kiện. Khi một sự kiện cần được chuyển ra ngoài ứng dụng, Spring Modulith hỗ trợ đánh dấu sự kiện bằng metadata externalization, chẳng hạn annotation **@Externalized**, rồi giao việc chuyển tiếp cho cơ chế externalization và integration tương ứng.

Externalization tạo ra một ranh giới giữa event nội bộ và thông điệp mà hệ thống bên ngoài nhận được. Ranh giới này có thể cần thay đổi khi một consumer ngừng sử dụng dữ liệu, một môi trường cần tạm dừng outbound, destination được di chuyển, broker được thay thế hoặc hợp đồng event cần nâng version. Mỗi thay đổi phải giữ được khả năng theo dõi publication và tránh làm mất hoặc nhân đôi hiệu ứng nghiệp vụ.

## 1. Hiểu đúng phạm vi của externalization

Một application event có thể phục vụ listener bên trong ứng dụng, đồng thời được externalize để chuyển tới hệ thống khác. Ví dụ:

~~~java
import java.time.Instant;
import java.util.UUID;

import org.springframework.modulith.events.Externalized;

@Externalized("inventory.stock-reserved.v1")
public record StockReserved(
    UUID eventId,
    UUID reservationId,
    Instant occurredAt,
    int quantity
) {}
~~~

Giá trị trong **@Externalized** biểu thị target logic mà cơ chế externalization sử dụng để định tuyến sự kiện. Destination vật lý như topic, queue hoặc endpoint còn phụ thuộc vào integration và cấu hình của ứng dụng. Giữ target logic ổn định giúp event contract ít phụ thuộc vào chi tiết hạ tầng.

Một listener nội bộ vẫn có thể xử lý cùng application event:

~~~java
@Component
class ReservationProjectionListener {

    @ApplicationModuleListener
    void on(StockReserved event) {
        // Cập nhật projection nội bộ.
    }
}
~~~

Vì vậy, cần phân biệt các hành động sau:

| Hành động | Phạm vi ảnh hưởng |
|---|---|
| Bỏ metadata externalization khỏi một loại event | Ngăn các publication mới của loại event đó được externalize; listener nội bộ vẫn có thể nhận event |
| Tạm dừng outbound adapter | Giữ event ở phía ứng dụng trong thời gian tạm dừng nếu cơ chế lưu và retry được thiết kế đúng |
| Đổi target logic | Chuyển publication mới sang logical destination khác |
| Đổi destination vật lý | Thay đổi mapping từ target logic sang topic, queue hoặc endpoint |
| Đổi broker hoặc giao thức | Thay integration vận chuyển, đồng thời phải giữ hợp đồng event tương thích |
| Ngừng consumer bên ngoài | Consumer ngừng nhận hoặc xử lý; việc producer vẫn gửi event có thể tiếp tục tạo backlog |

Tắt consumer không đồng nghĩa đã tắt externalization ở producer. Tương tự, bỏ annotation khỏi một event type không tự giải quyết các publication đã được ghi nhận trước thời điểm thay đổi.

## 2. Chọn đúng cách tắt

Trước khi thay đổi, xác định rõ phạm vi cần tắt:

- Một event type không còn cần gửi ra ngoài.
- Một target hoặc consumer cụ thể cần dừng nhận.
- Một môi trường như local hoặc test không cần outbound thật.
- Toàn bộ outbound cần tạm dừng trong thời gian bảo trì.
- Một destination cũ cần ngừng sau khi chuyển sang destination mới.

Phạm vi càng hẹp thì ảnh hưởng tới các consumer khác càng dễ kiểm soát.

### Tắt vĩnh viễn một event type

Nếu event không còn là hợp đồng tích hợp với hệ thống ngoài, có thể bỏ **@Externalized** khỏi event type:

~~~java
import java.time.Instant;
import java.util.UUID;

public record StockReserved(
    UUID eventId,
    UUID reservationId,
    Instant occurredAt,
    int quantity
) {}
~~~

Event vẫn là application event. Các listener nội bộ tiếp tục nhận event theo cơ chế publish và listener hiện có. Chỉ metadata yêu cầu externalization được loại bỏ cho những publication mới sau khi phiên bản ứng dụng chứa thay đổi được triển khai.

Trước khi bỏ annotation, xác nhận consumer bên ngoài đã ngừng phụ thuộc vào event, hoặc đã có kế hoạch chuyển consumer sang hợp đồng khác. Nếu event được dùng bởi nhiều consumer, kiểm tra từng consumer thay vì suy ra rằng một consumer ngừng dùng đồng nghĩa mọi consumer đều không còn cần event.

Các publication đã được tạo trước khi triển khai thay đổi có thể vẫn còn trong Event Publication Registry. Cần xử lý chúng theo quyết định cutover: gửi hết tới target cũ, chuyển tiếp có kiểm soát hoặc đưa vào quy trình xử lý thủ công. Không xóa bản ghi incomplete chỉ để làm sạch trạng thái.

### Tạm dừng outbound

Tạm dừng phù hợp khi bảo trì broker, thay đổi credential, điều tra sự cố hoặc kiểm soát lưu lượng. Đây là trạng thái vận hành có thời hạn, vì vậy cần giữ khả năng tiếp tục giao event sau khi hệ thống sẵn sàng.

Có thể khai báo một cấu hình do ứng dụng sở hữu:

~~~yaml
app:
  events:
    externalization:
      enabled: true
~~~

Tên **app.events.externalization.enabled** trong ví dụ là property của ứng dụng, không phải một property mặc định mà Spring Modulith tự động hiểu. Ứng dụng phải nối property này vào đúng outbound adapter hoặc listener thực hiện việc gửi external event.

Nếu publication đang được Event Publication Registry theo dõi, đường đi khi tạm dừng cần bảo đảm publication không bị đánh dấu hoàn tất trong khi thông điệp chưa được gửi. Một cách thiết kế là để outbound listener báo lỗi tạm dừng có chủ đích, giữ publication ở trạng thái incomplete và cấu hình retry coordinator không resubmit liên tục trong thời gian cờ đang tắt. Khi bật lại, coordinator mới gửi các publication đến hạn.

Ví dụ về cổng kiểm tra trong một adapter do ứng dụng quản lý:

~~~java
@Component
class ExternalEventSender {

    private final ExternalizationProperties properties;
    private final MessageTransport transport;

    ExternalEventSender(
            ExternalizationProperties properties,
            MessageTransport transport) {
        this.properties = properties;
        this.transport = transport;
    }

    void send(ExternalMessage message) {
        if (!properties.isEnabled()) {
            throw new ExternalizationPausedException(
                "Outbound event externalization is paused"
            );
        }

        transport.send(message);
    }
}
~~~

**ExternalizationProperties**, **MessageTransport** và **ExternalizationPausedException** là abstraction của ứng dụng trong ví dụ, không phải tên API cấu hình mặc định của Spring Modulith. Nếu lời gọi gửi event nằm trong listener được registry theo dõi, exception phải được truyền ra ngoài listener để publication không bị đánh dấu thành công. Retry coordinator cần nhận biết trạng thái tạm dừng và không liên tục thử lại trong lúc outbound vẫn bị khóa.

Không dùng một implementation no-op trả về thành công khi cờ tắt. Cách đó khiến registry có thể đánh dấu publication hoàn tất dù message chưa tới hệ thống ngoài, dẫn đến mất thông điệp mà không có dấu vết phục hồi.

Cũng cần phân biệt property chỉ đọc lúc ứng dụng khởi động và cờ có thể thay đổi lúc runtime. Với cấu hình Spring Boot thông thường, thay đổi file cấu hình thường cần restart hoặc cơ chế refresh được ứng dụng hỗ trợ. Không giả định thay đổi YAML sẽ tự động cập nhật bean đang chạy.

## 3. Đổi target mà không làm hỏng hợp đồng

Target xác định nơi một loại event được chuyển đến ở mức logic. Khi đổi target, hãy xác định lý do:

- Consumer được chuyển sang một nhóm xử lý mới.
- Destination cũ cần đổi tên hoặc tách theo domain.
- Hệ thống ngoài có phiên bản contract mới.
- Nhiều môi trường cần mapping khác nhau tới cùng một logical target.

Nếu chỉ thay đổi topic hoặc queue vật lý, nên giữ target logic của event ổn định và thay mapping trong integration configuration. Cách này giúp domain event không chứa tên broker, cluster hoặc môi trường.

Nếu hợp đồng với consumer thực sự thay đổi, có thể dùng target có version mới:

~~~java
@Externalized("inventory.stock-reserved.v2")
public record StockReservedV2(
    UUID eventId,
    UUID reservationId,
    Instant occurredAt,
    int quantity,
    String warehouseCode
) {}
~~~

Việc đổi từ **inventory.stock-reserved.v1** sang **inventory.stock-reserved.v2** là thay đổi hợp đồng. Consumer của v1 không tự hiểu payload v2. Cần triển khai consumer tương thích trước hoặc đồng thời theo kế hoạch rollout đã thống nhất.

Với thay đổi tương thích ngược, ưu tiên thêm trường tùy chọn có default hoặc quy tắc xử lý rõ ràng. Tránh đổi ý nghĩa trường hiện có, đổi đơn vị đo, đổi timezone hoặc đổi cách diễn giải trạng thái mà không version hóa. Một payload vẫn parse được về mặt cú pháp nhưng thay đổi ý nghĩa nghiệp vụ vẫn có thể gây lỗi nghiêm trọng.

Không tạo event ID mới chỉ vì target thay đổi. Nếu cùng một sự kiện nghiệp vụ được chuyển qua hai destination trong giai đoạn migration, giữ định danh ổn định để consumer có thể deduplicate. Đồng thời ghi rõ destination nào là nguồn chính để tránh xử lý hai lần ở hai pipeline.

## 4. Đổi destination vật lý hoặc broker

Logical target và destination vật lý nên được xem là hai lớp riêng:

~~~text
Application event
    |
    v
Externalization metadata
    |
    v
Logical target: inventory.stock-reserved
    |
    v
Integration mapping
    |
    +--> Broker topic / queue
    |
    +--> HTTP endpoint
    |
    +--> Hệ thống nhận sự kiện khác
~~~

Ví dụ, event vẫn khai báo target **inventory.stock-reserved**, trong khi cấu hình integration ánh xạ target này tới topic của môi trường hiện tại. Mỗi môi trường có thể dùng destination khác nhau mà không phải thay đổi event type.

Khi chuyển broker hoặc transport, kiểm tra các yếu tố:

| Thành phần | Cần xác minh |
|---|---|
| Serialization | Payload mới có giữ tên trường, kiểu dữ liệu và quy tắc tương thích không |
| Headers | Event ID, correlation ID, content type và metadata định tuyến có được chuyển đủ không |
| Ordering | Consumer có yêu cầu thứ tự theo aggregate hoặc partition key không |
| Delivery semantics | Broker mới có thay đổi cách xác nhận, retry hoặc redelivery không |
| Security | Credential, TLS, ACL và quyền publish đã được cấp cho ứng dụng chưa |
| Retry | Lỗi kết nối, timeout và throttling được phân loại và retry ra sao |
| Monitoring | Có metric, log và cảnh báo cho destination mới không |

Nếu thay broker nhưng vẫn giữ target logic và external event contract, consumer có thể được chuyển theo từng bước. Tuy nhiên, không nên coi hai broker là tương đương về thứ tự, xác nhận giao hàng hoặc semantics của message. Các đặc tính đó phải được xác minh theo integration thực tế.

## 5. Quy trình chuyển destination an toàn

Một lần chuyển destination thường có các bước sau:

1. **Kiểm kê hợp đồng:** liệt kê event type, target logic, destination hiện tại, consumer, owner và chính sách lưu giữ.
2. **Chuẩn bị destination mới:** tạo topic hoặc queue, cấp quyền publish/consume, cấu hình schema và dashboard.
3. **Chuẩn bị consumer:** triển khai consumer có thể đọc contract hiện tại và deduplicate theo event ID.
4. **Chọn chiến lược cutover:** chuyển thẳng khi có thể dừng và drain an toàn, hoặc dual-publish trong giai đoạn chuyển tiếp nếu yêu cầu không gián đoạn.
5. **Chuyển producer:** cập nhật mapping hoặc target theo đúng chiến lược đã chọn.
6. **Theo dõi backlog:** kiểm tra publication incomplete, số message ở destination cũ và mới, tỷ lệ lỗi cùng độ trễ.
7. **Drain destination cũ:** chỉ dừng consumer hoặc xóa hạ tầng cũ sau khi xác nhận không còn message cần xử lý.
8. **Kết thúc migration:** ghi lại target và destination mới, cập nhật runbook và quyền vận hành.

Trong giai đoạn dual-publish, cùng một event có thể xuất hiện ở cả hai destination. Consumer cần dùng event ID hoặc idempotency key để ngăn hiệu ứng nghiệp vụ bị áp dụng hai lần. Nếu có nhiều consumer độc lập, mỗi consumer nên có namespace deduplication riêng để một consumer không vô tình chặn consumer khác.

Không nên đổi target và xóa destination cũ trong cùng một thao tác không có bước quan sát. Một số publication đã được tạo trước cutover có thể vẫn mang thông tin định tuyến cũ hoặc đang chờ retry. Cần xem xét chúng trước khi quyết định resubmit, drain hoặc chuyển thủ công.

## 6. Xử lý publication đang chờ khi thay đổi

Event Publication Registry theo dõi trạng thái publication để ứng dụng có thể nhận biết publication đã hoàn tất hay còn incomplete. Đây là phần quan trọng khi tắt hoặc đổi externalization, vì thay đổi mã nguồn chỉ tác động đến các publication mới theo phiên bản mới; nó không tự giải quyết mọi publication đã tồn tại.

Trước cutover, phân loại publication đang chờ:

| Trạng thái | Hướng xử lý |
|---|---|
| Chưa gửi tới destination cũ | Gửi theo target cũ hoặc chuyển hướng có kiểm soát |
| Đã gửi nhưng chưa xác nhận hoàn tất | Kiểm tra khả năng consumer đã nhận; dùng event ID để deduplicate trước khi gửi lại |
| Thất bại do destination tạm thời không sẵn sàng | Giữ incomplete và retry sau khi destination phục hồi |
| Destination cũ đã ngừng hoạt động | Chuyển sang quy trình migration/replay có kiểm soát |
| Event không còn được consumer sử dụng | Đánh giá chính sách bỏ qua hoặc xử lý thủ công; lưu dấu vết quyết định |

Không tự sửa trạng thái registry bằng SQL hoặc xóa hàng loạt bản ghi incomplete. Những thao tác đó có thể làm mất khả năng phục hồi hoặc khiến hệ thống không còn biết event nào đã được giao. Dùng API phục hồi được cung cấp bởi phiên bản Spring Modulith đang triển khai và quy trình vận hành của ứng dụng.

Khi chuyển target, không mặc định rằng publication cũ sẽ tự động dùng mapping mới. Hãy xác định target được ghi nhận ở thời điểm nào trong integration đang dùng và kiểm tra hành vi của publication đã lưu. Nếu không chắc, xử lý một publication mẫu trong môi trường kiểm thử tích hợp trước khi migration hàng loạt.

## 7. Phân biệt tắt externalization với tắt event nội bộ

Một lỗi cấu hình thường gặp là tắt quá rộng. Ví dụ, loại bỏ toàn bộ cơ chế xử lý application events để ngừng gửi ra broker có thể đồng thời làm ngừng listener nội bộ, projection hoặc các bước nghiệp vụ sau commit.

Giữ rõ các lớp:

- **Event producer** tạo application event sau khi nghiệp vụ thay đổi.
- **Internal listener** xử lý event bên trong ranh giới ứng dụng hoặc module.
- **Externalization listener/adapter** chuyển event đã đánh dấu ra hệ thống ngoài.
- **Transport** gửi message tới broker hoặc endpoint.
- **External consumer** nhận và xử lý message.

Nếu mục tiêu chỉ là dừng outbound, thay đổi nên nằm ở externalization listener, adapter hoặc mapping tương ứng. Giữ producer và internal listener hoạt động để các module trong ứng dụng không mất luồng nghiệp vụ của chúng.

Nếu muốn ngừng hẳn một event, cần đánh giá cả producer lẫn internal listener. Đó là một thay đổi nghiệp vụ rộng hơn và cần được triển khai theo kế hoạch riêng.

## 8. Retry, idempotency và compensation trong thời gian tạm dừng

Khi outbound bị tạm dừng, publication có thể tích lũy. Sau khi bật lại, không nên gửi toàn bộ backlog cùng lúc nếu broker hoặc consumer có năng lực xử lý giới hạn.

Một kế hoạch phục hồi cần:

- Giới hạn số publication resubmit trong mỗi lượt.
- Dùng backoff cho lỗi tạm thời và jitter khi nhiều instance cùng retry.
- Tôn trọng giới hạn tốc độ hoặc thời điểm retry do dịch vụ đích yêu cầu.
- Theo dõi tuổi publication lâu nhất và thời gian backlog dự kiến được drain.
- Giữ event ID ổn định để consumer xử lý lặp an toàn.
- Chuyển publication hết ngân sách retry sang xử lý thủ công có cảnh báo.

Externalization thường phải chấp nhận khả năng message được giao lại. Consumer cần idempotent: lưu event ID đã xử lý cùng cập nhật nghiệp vụ trong một transaction phù hợp, hoặc dùng idempotency key mà hệ thống đích hỗ trợ. Không giả định một lần publish thành công có nghĩa consumer đã hoàn tất nghiệp vụ.

Compensation cũng không phải cách mặc định để xử lý backlog. Chỉ chạy compensation khi trạng thái nghiệp vụ yêu cầu một hành động bù trừ. Nếu message bị trễ nhưng nghiệp vụ vẫn hợp lệ, tiếp tục giao event thường phù hợp hơn. Nếu thao tác ngoài đã thành công nhưng phản hồi bị mất, cần đối soát theo event ID trước khi thử lại hoặc bù trừ.

## 9. Kiểm thử thay đổi externalization

Kiểm thử nên xác nhận cả hành vi nội bộ và hành vi outbound. Một bộ kiểm thử hữu ích bao gồm:

1. **Tắt một event type:** event vẫn được publish nội bộ và internal listener vẫn chạy; không phát sinh external publication mới cho event type đã bỏ metadata.
2. **Tạm dừng outbound:** listener/adapter không gửi message; publication không bị đánh dấu hoàn tất giả; trạng thái incomplete có thể phục hồi.
3. **Bật lại outbound:** publication đến hạn được gửi lại và hoàn tất khi listener thực sự xử lý thành công.
4. **Đổi target:** publication mới dùng target đã chọn; consumer cũ và mới xử lý đúng contract trong giai đoạn chuyển tiếp.
5. **Đổi destination:** message có đủ payload, headers và event ID; quyền truy cập và serialization hoạt động.
6. **Publication cũ:** publication được tạo trước cutover được xử lý theo chính sách migration, không bị gửi nhầm hoặc mất.
7. **Redelivery:** gửi lại cùng event không tạo hiệu ứng nghiệp vụ trùng lặp.
8. **Restart:** publication incomplete vẫn có thể được phục hồi sau khi ứng dụng khởi động lại nếu registry được cấu hình với kho lưu trữ bền vững.
9. **Rollback:** có thể khôi phục mapping cũ hoặc tiếp tục drain destination cũ mà không phá hủy dấu vết publication.

Trong kiểm thử tích hợp, dùng transport test hoặc broker test phù hợp để xác nhận message thực sự tới destination. Chỉ kiểm tra rằng method gửi message được gọi là chưa đủ nếu lỗi có thể xảy ra ở serialization, kết nối, xác nhận giao hàng hoặc consumer.

## 10. Quan sát và điều hành thay đổi

Trước và sau khi thay đổi, theo dõi ít nhất các chỉ số:

| Chỉ số | Ý nghĩa vận hành |
|---|---|
| External publication count | Số publication được tạo hoặc gửi theo target |
| Incomplete publication count | Khối lượng outbound chưa hoàn tất |
| Oldest incomplete age | Thời gian publication bị chờ lâu nhất |
| Retry count by target | Target hoặc destination có lỗi lặp lại |
| Delivery latency | Thời gian từ lúc event được tạo đến lúc gửi thành công |
| Consumer lag | Khoảng cách giữa message đã publish và message đã xử lý |
| Exhausted/manual-review count | Publication cần con người can thiệp |

Log nên có event ID, publication ID, logical target, destination, listener, attempt, correlation ID và mã lỗi. Không ghi credential, token hoặc payload nhạy cảm. Khi migration, thêm một mã change/cutover để có thể truy vấn log của cùng đợt triển khai.

Cảnh báo nên dựa trên tuổi publication và xu hướng backlog, không chỉ dựa vào một lần gửi thất bại. Một lỗi đơn lẻ có thể tự phục hồi; backlog tăng liên tục hoặc publication cũ vượt SLA mới là dấu hiệu cần hành động.

## 11. Checklist trước khi tắt hoặc thay đổi

Trước khi triển khai, hãy xác nhận:

- Phạm vi thay đổi là một event type, một target, một destination, một môi trường hay toàn bộ outbound.
- Consumer nào đang phụ thuộc vào event và ai chịu trách nhiệm cho mỗi consumer.
- Publication incomplete hiện tại được xử lý theo cách nào.
- Event ID và idempotency key có đủ để chống redelivery không.
- Target logic và destination vật lý có đang bị ghép cứng trong event contract không.
- Thay đổi có làm dừng internal listener hoặc luồng nghiệp vụ sau commit không.
- Retry coordinator có biết trạng thái tạm dừng và tránh retry liên tục không.
- Có metric, cảnh báo, runbook và phương án rollback không.
- Điều kiện để kết thúc migration và dừng destination cũ đã rõ ràng chưa.

Tắt hoặc thay đổi externalization là thay đổi ở ranh giới tích hợp. Khi giữ event nội bộ ổn định, quản lý target và destination có chủ đích, bảo toàn publication chưa hoàn tất và yêu cầu consumer xử lý lặp an toàn, ứng dụng có thể thay đổi hệ thống nhận event mà vẫn duy trì tính nhất quán và khả năng phục hồi của giao tiếp giữa các module Spring Modulith.

