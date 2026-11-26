# Dual consume

Dual consume là chiến lược di trú trong đó hệ thống mới tiếp nhận cùng một luồng sự kiện nghiệp vụ từ hai đường tiêu thụ trong một giai đoạn chuyển tiếp. Hai đường này có thể là broker cũ và broker mới, event contract cũ và mới, hoặc consumer cũ và consumer thay thế. Mục tiêu là kiểm chứng khả năng đọc, so sánh kết quả và chuyển quyền xử lý mà không làm gián đoạn nghiệp vụ.

Dual consume không có nghĩa hai consumer đều được tự do thực hiện side effect trên cùng dữ liệu. Nếu cả hai cùng ghi sổ, trừ tồn kho hoặc capture thanh toán, một event có thể tạo tác động hai lần. Vì vậy, chiến lược phải xác định rõ consumer nào đang có quyền ghi, consumer nào chỉ chạy shadow, cách nhận diện cùng một event qua hai nguồn và điều kiện để chuyển quyền sở hữu.

Trong Spring Modulith, application events giúp các module trao đổi qua contract nghiệp vụ. Khi di trú nguồn event hoặc adapter messaging, có thể đặt adapter cũ và mới ở hai đầu vào, chuẩn hóa payload về cùng mô hình nội bộ rồi đưa vào application service. Event Publication Registry hỗ trợ theo dõi publication trong ứng dụng; nó không tự điều phối offset giữa hai broker, không so sánh hai consumer và không thay thế cơ chế idempotency.

## 1. Vì sao dùng dual consume?

Một lần chuyển đổi trực tiếp từ consumer cũ sang consumer mới có rủi ro: contract có thể khác, routing có thể sai, consumer mới có thể chậm hơn hoặc một nhóm event có thể bị bỏ sót. Dual consume tạo một giai đoạn quan sát để kiểm tra đường mới trước khi nó trở thành đường xử lý chính.

Các mục tiêu thường gặp:

- Di chuyển từ broker cũ sang broker mới mà vẫn duy trì xử lý nghiệp vụ.
- Thay consumer cũ bằng implementation mới trong khi so sánh kết quả.
- Chuyển từ payload phiên bản cũ sang contract mới.
- Đổi cách externalize application event mà vẫn tiếp nhận message đang tồn tại trong queue cũ.
- Chuyển một nhóm event từ ứng dụng monolith sang service chuyên trách.
- Kiểm tra năng lực xử lý, độ trễ và hành vi lỗi của consumer mới trước cutover.

Dual consume đặc biệt hữu ích khi event có thể được replay và consumer có thể chạy song song trong thời gian giới hạn. Tuy nhiên, nó cần một kế hoạch rõ về quyền ghi, identity, ordering, checkpoint và rollback. Nếu không, giai đoạn chuyển tiếp có thể tạo ra hai nguồn dữ liệu cạnh tranh.

## 2. Phân biệt dual consume, dual publish và shadow consume

Các thuật ngữ này thường được dùng gần nhau nhưng mô tả các hành vi khác nhau:

| Chiến lược | Hành vi | Mục đích |
|---|---|---|
| Dual publish | Producer phát cùng logical event tới hai đích | Cấp dữ liệu cho cả đường cũ và mới |
| Dual consume | Hệ thống đọc từ hai nguồn hoặc hai contract | Tiếp nhận song song trong giai đoạn di trú |
| Shadow consume | Consumer mới đọc và tính kết quả nhưng không tạo side effect nghiệp vụ | So sánh độ đúng và hiệu năng |
| Active dual consume | Hai đường đều được đọc, nhưng quyền ghi được điều phối hoặc deduplicate | Chuyển đổi có kiểm soát khi cần cả hai đường hoạt động |

Dual publish là quyết định ở phía producer; dual consume là quyết định ở phía consumer. Có thể dùng cả hai trong một migration, nhưng phải tránh bridge tạo vòng lặp: consumer đọc broker cũ, publish sang broker mới, rồi consumer mới lại publish ngược về broker cũ.

Shadow consume là cách an toàn để bắt đầu: consumer mới nhận bản sao event, deserialize và chạy logic tính toán trong môi trường cô lập, nhưng không gửi thanh toán, cập nhật tồn kho hay tạo thông báo thật. Khi kết quả đã được so sánh đủ lâu, có thể chuyển consumer mới sang active mode.

Không nên gọi hai consumer cùng ghi vào một database là shadow. Nếu consumer mới ghi dữ liệu nghiệp vụ thật, nó đang tạo side effect và cần cơ chế ownership/idempotency như mọi consumer active khác.

## 3. Mô hình hai đường tiêu thụ

Ví dụ hệ thống đang chuyển event OrderPaid từ broker cũ sang broker mới. Producer có thể gửi event vào nguồn cũ; một replication/bridge hoặc producer mới cũng đưa logical event sang nguồn mới. Hai adapter tiếp nhận message và chuẩn hóa về một contract nội bộ.

~~~mermaid
flowchart TD
    P["Producer / source event"] --> L["Legacy broker"]
    P --> N["New broker"]
    L --> LA["Legacy consumer adapter"]
    N --> NA["New consumer adapter"]
    LA --> C["Canonical event"]
    NA --> C
    C --> H["Application service"]
    NA -. "shadow mode" .-> S["Shadow result store"]
    S --> D["Result comparison"]
    H --> DB["Business database"]
~~~

Sơ đồ thể hiện hai đầu vào có thể cùng đại diện cho một logical event. Trong giai đoạn shadow, đường mới có thể ghi kết quả vào shadow store hoặc phát trace/metric để so sánh, trong khi đường cũ vẫn giữ quyền cập nhật nghiệp vụ.

Một thiết kế khác là cả hai adapter gọi cùng application service nhưng service có inbox và unique constraint. Cách này phù hợp khi cần active dual consume, song phải xác định idempotency key chung cho hai bản sao. Nếu hai broker cấp message ID khác nhau, chỉ dùng broker message ID sẽ không loại được duplicate xuyên nguồn.

## 4. Xác định nguồn sự thật và quyền ghi

Trước khi chạy hai consumer, cần trả lời câu hỏi: trong mỗi giai đoạn, thành phần nào được phép tạo side effect nghiệp vụ?

Có thể dùng ma trận ownership:

| Giai đoạn | Consumer cũ | Consumer mới | Quyền ghi nghiệp vụ |
|---|---|---|---|
| Baseline | Active | Chưa chạy | Consumer cũ |
| Shadow | Active | Read-only/shadow | Consumer cũ |
| Cutover | Dừng hoặc drain | Active | Consumer mới |
| Rollback | Active lại theo checkpoint | Dừng hoặc shadow | Consumer cũ |
| Hoàn tất | Tắt | Active | Consumer mới |

Không nên để ownership chỉ tồn tại trong tài liệu hoặc một biến cấu hình rời rạc ở mỗi instance. Cần có cơ chế triển khai và vận hành rõ: feature flag, consumer group, routing policy, lease hoặc một trạng thái cutover được lưu và kiểm soát.

Nếu buộc phải để hai consumer cùng active trong một khoảng ngắn, mọi side effect phải được bảo vệ bằng idempotency xuyên cả hai đường. Với thao tác không thể lặp như capture thanh toán, nên ưu tiên một writer duy nhất và chỉ cho consumer còn lại chạy shadow.

## 5. Chuẩn hóa hai contract về một mô hình nội bộ

Trong migration contract, payload cũ và mới có thể khác tên trường, kiểu dữ liệu hoặc cấu trúc envelope. Không nên để business service biết chi tiết của cả hai phiên bản. Mỗi adapter nên chuyển payload nguồn về một canonical event hoặc command nội bộ.

Ví dụ:

~~~java
public record CanonicalOrderPaid(
    String logicalEventId,
    String orderId,
    BigDecimal amount,
    String currency,
    Instant occurredAt,
    String source,
    int sourceSchemaVersion
) {}
~~~

Adapter cũ và mới thực hiện mapping riêng:

~~~java
@Component
class LegacyOrderPaidMapper {

    CanonicalOrderPaid map(LegacyOrderPaidV1 payload) {
        return new CanonicalOrderPaid(
            payload.eventKey(),
            payload.orderNumber(),
            new BigDecimal(payload.totalAmount()),
            payload.currencyCode(),
            payload.paidAt(),
            "legacy",
            1
        );
    }
}

@Component
class NewOrderPaidMapper {

    CanonicalOrderPaid map(OrderPaidV2 payload) {
        return new CanonicalOrderPaid(
            payload.eventId(),
            payload.orderId(),
            payload.amount(),
            payload.currency(),
            payload.occurredAt(),
            "new",
            2
        );
    }
}
~~~

logicalEventId phải nhận diện cùng một hành động nghiệp vụ trên cả hai đường. Nếu event cũ và mới không chia sẻ ID, cần một mapping ID được tạo ở bridge/producer hoặc một business key ổn định đã được contract xác nhận. Không tự ghép ID từ các trường có thể thay đổi như timestamp nhận message hoặc giá trị hiển thị.

Trường source và sourceSchemaVersion hữu ích cho log, trace và so sánh, nhưng không nên biến thành idempotency scope nếu mục tiêu là chặn cùng logical event từ hai nguồn. Nếu đưa source vào unique key, bản sao legacy và new sẽ bị coi là hai công việc khác nhau.

## 6. Thiết kế identity và deduplication xuyên nguồn

Trong dual consume, cùng một event có thể xuất hiện ở broker cũ và broker mới với delivery tag, offset hoặc message ID khác nhau. Các định danh transport chỉ có ý nghĩa trong nguồn của chúng. Cần một logical event identity ổn định để nhận ra hai bản sao.

Một khóa chống xử lý trùng có thể gồm:

~~~text
(consumer_id, logical_event_id)
~~~

Nếu event ID chỉ duy nhất trong một producer, thêm producer identity vào logical key. Nếu một logical event được phép tạo nhiều loại side effect, consumer_id cần phân biệt từng consumer/handler.

Ví dụ bảng inbox:

~~~sql
CREATE TABLE consumed_events (
    consumer_id       VARCHAR(120) NOT NULL,
    logical_event_id  VARCHAR(180) NOT NULL,
    processed_at      TIMESTAMP WITH TIME ZONE NOT NULL,
    PRIMARY KEY (consumer_id, logical_event_id)
);
~~~

Consumer cố gắng insert key bằng thao tác nguyên tử. Nếu insert thành công, nó có quyền thực hiện side effect trong cùng transaction; nếu key đã tồn tại, lần giao từ đường còn lại được nhận diện là duplicate.

Inbox marker và cập nhật nghiệp vụ cần commit cùng nhau khi chúng ở cùng database. Nếu marker commit trước nhưng nghiệp vụ thất bại, lần giao sau sẽ bị bỏ qua dù công việc chưa hoàn tất. Nếu side effect nằm ở hệ thống ngoài, truyền cùng idempotency key sang hệ thống đích hoặc xây dựng workflow đối soát.

Nếu hai payload cùng logicalEventId nhưng nội dung khác nhau, không được âm thầm coi bản thứ hai là duplicate hợp lệ. Hãy so sánh payload hash hoặc các trường nghiệp vụ quan trọng, ghi nhận contract conflict và cách ly event để điều tra.

## 7. Shadow consume và so sánh kết quả

Shadow consume giúp xác minh consumer mới trước khi cấp quyền ghi. Consumer mới nhận cùng event, chạy mapping và logic tính toán, nhưng ghi kết quả vào một vùng shadow riêng hoặc chỉ phát metric/trace.

Ví dụ so sánh kết quả giữ tồn kho:

| Thuộc tính | Consumer cũ | Consumer mới |
|---|---|---|
| orderId | ORD-42 | ORD-42 |
| sku | SKU-7 | SKU-7 |
| quantity reserved | 2 | 2 |
| reservation outcome | RESERVED | RESERVED |
| resulting available stock | 8 | 8 |

Kết quả so sánh cần phân biệt:
- **Match:** hai đường tạo cùng kết quả nghiệp vụ.
- **Mismatch:** cùng input nhưng kết quả khác nhau.
- **Missing:** một đường chưa xử lý hoặc không có kết quả trong cửa sổ chờ.
- **Invalid comparison:** thiếu logical ID hoặc payload không thể chuẩn hóa.

Không chỉ so sánh số lượng message nhận được. Hai consumer có thể nhận cùng số message nhưng khác tập event, khác thứ tự hoặc khác kết quả nghiệp vụ. Hãy so sánh theo logicalEventId và business key.

Shadow handler không được gọi API bên ngoài có side effect thật. Nếu cần kiểm tra tích hợp downstream, hãy dùng sandbox hoặc fake service được kiểm soát. Kết quả shadow phải được lưu riêng và có TTL/cleanup để không bị nhầm với dữ liệu production.

## 8. Đồng bộ dữ liệu và bắt kịp luồng event

Khi consumer mới bắt đầu đọc, nó có thể chưa có state nền mà consumer cũ đã tích lũy. Chỉ bật consumer mới từ event hiện tại có thể khiến projection hoặc workflow thiếu dữ liệu lịch sử.

Một migration thường cần kết hợp snapshot/backfill với event stream:

1. Xác định snapshot nhất quán của dữ liệu nền.
2. Ghi lại watermark hoặc checkpoint của nguồn event tại thời điểm snapshot.
3. Nạp snapshot vào state của consumer mới.
4. Đọc event sau watermark để cập nhật phần thay đổi.
5. So sánh kết quả với consumer cũ.
6. Xử lý khoảng trống hoặc event trùng do ranh giới snapshot/stream.

Watermark phải có ý nghĩa theo nguồn. Offset của Kafka topic không thể so trực tiếp với sequence của RabbitMQ hoặc timestamp ở database. Khi hai nguồn khác nhau, dùng logical event ID, aggregate sequence hoặc một mapping checkpoint được ghi nhận bởi bridge.

Không chỉ dựa vào timestamp để chứng minh đã bắt kịp. Đồng hồ giữa producer và consumer có thể lệch, event có thể đến trễ và nhiều event có cùng timestamp. Nên có sequence/version theo aggregate hoặc một cơ chế checkpoint có semantics rõ.

## 9. Ordering khi đọc từ hai nguồn

Hai broker hoặc hai consumer group không đảm bảo cùng một thứ tự quan sát. Event OrderPaid có thể đến từ broker mới trước OrderPlaced được replay từ broker cũ, hoặc hai đường có độ trễ khác nhau.

Nếu nghiệp vụ phụ thuộc thứ tự, event nên mang aggregate ID và sequence/version tăng đơn điệu. Consumer kiểm tra version trước khi áp dụng:

- Version bằng version hiện tại + 1: có thể áp dụng.
- Version nhỏ hơn hoặc bằng version đã xử lý: duplicate/stale theo chính sách.
- Version lớn hơn version kế tiếp: phát hiện gap, chờ event thiếu hoặc đồng bộ lại.

Không dùng offset riêng của hai broker để quyết định thứ tự chung. Cũng không dùng thời gian nhận message làm thứ tự nghiệp vụ. Nếu hai event cùng aggregate được xử lý song song, cần partitioning, serialization theo aggregate hoặc optimistic locking để bảo vệ state.

Khi dual consume chỉ chạy shadow, consumer mới vẫn cần kiểm tra ordering để so sánh đúng. Nếu bỏ qua gap trong shadow, mismatch có thể bị quy nhầm cho logic business thay vì thứ tự giao nhận.

## 10. Chuyển quyền xử lý (cutover)

Cutover là thời điểm chuyển quyền tạo side effect từ consumer cũ sang consumer mới. Cần một quy trình có checkpoint và điều kiện dừng rõ ràng.

Một trình tự tham khảo:

1. Đảm bảo consumer mới đọc được payload và contract hiện tại.
2. Chạy shadow đủ lâu để quan sát các nhóm event, tải cao điểm và nhánh lỗi.
3. Xử lý mismatch, missing event và backlog.
4. Chọn checkpoint/watermark có thể đối chiếu.
5. Ngừng nhận event mới ở consumer cũ hoặc chuyển routing theo cơ chế đã thiết kế.
6. Drain các delivery đang xử lý và xác nhận publication/offset đã hoàn tất tới checkpoint.
7. Bật quyền ghi cho consumer mới từ vị trí tiếp nối.
8. Theo dõi duplicate, gap, latency, error rate và kết quả nghiệp vụ.
9. Giữ đường cũ ở trạng thái có thể khôi phục trong cửa sổ rollback đã định.

Không bật active mode cho consumer mới chỉ vì dashboard shadow đang xanh. Cần xác minh nó đã bắt kịp, có state nền đầy đủ và đã xử lý các event quan trọng tới checkpoint.

Nếu broker không hỗ trợ một giao dịch nguyên tử giữa việc dừng consumer cũ và bật consumer mới, có thể có một cửa sổ overlap hoặc gap. Overlap cần deduplication; gap cần checkpoint/replay. Hãy chọn rủi ro có thể kiểm soát và ghi rõ trong runbook.

## 11. Rollback sau cutover

Rollback không chỉ là bật lại consumer cũ. Trong thời gian consumer mới đã ghi dữ liệu, consumer cũ có thể không biết những thay đổi đó. Nếu cả hai tiếp tục từ checkpoint khác nhau, state có thể lệch.

Trước cutover cần xác định:
- Cách ghi lại event mà consumer mới đã xử lý.
- Cách consumer cũ bắt kịp các event sau checkpoint.
- Khả năng đọc state do phiên bản mới tạo.
- Cách ngăn consumer cũ và mới cùng ghi trong lúc rollback.
- Điều kiện nào buộc phải replay hoặc rebuild projection.

Nếu consumer mới chỉ chạy shadow, rollback thường đơn giản vì chưa tạo side effect nghiệp vụ. Nếu đã active, cần chuyển ownership có kiểm soát, drain consumer mới, xác định checkpoint cuối, đưa consumer cũ bắt kịp rồi mới cấp quyền ghi lại.

Không xóa inbox/deduplication record khi rollback. Các record đó có thể là lớp bảo vệ để tránh event đã xử lý bị áp dụng lần nữa. Retention cần bao phủ toàn bộ thời gian retry, replay và rollback.

## 12. Dual consume trong Spring Modulith

Trong ứng dụng Spring Modulith, có thể giữ adapter nhận event cũ và thêm adapter nhận event mới. Hai adapter chuyển payload về canonical event rồi gọi một application service chung.

~~~java
@Component
class LegacyOrderPaidListener {

    private final OrderPaidMapper mapper;
    private final OrderPaidApplicationService service;

    LegacyOrderPaidListener(
            OrderPaidMapper mapper,
            OrderPaidApplicationService service) {
        this.mapper = mapper;
        this.service = service;
    }

    @RabbitListener(queues = "legacy.orders.paid")
    void on(LegacyOrderPaidV1 payload) {
        service.handle(mapper.fromLegacy(payload));
    }
}

@Component
class NewOrderPaidListener {

    private final OrderPaidMapper mapper;
    private final OrderPaidApplicationService service;

    NewOrderPaidListener(
            OrderPaidMapper mapper,
            OrderPaidApplicationService service) {
        this.mapper = mapper;
        this.service = service;
    }

    @KafkaListener(
        topics = "orders.paid.v2",
        groupId = "accounting-v2"
    )
    void on(OrderPaidV2 payload) {
        service.handle(mapper.fromNew(payload));
    }
}
~~~

Ví dụ minh họa hai transport adapter; cấu hình container, acknowledgement và dependency Kafka/RabbitMQ cần phù hợp ứng dụng thực tế. Cả hai adapter không nên chứa business rule riêng. Chúng chịu trách nhiệm nhận, xác thực envelope, map về canonical model và chuyển lỗi đúng cách.

Application service là nơi áp dụng idempotency và transaction:

~~~java
@Service
class OrderPaidApplicationService {

    private final ConsumedEventRepository inbox;
    private final AccountingRepository accounting;

    OrderPaidApplicationService(
            ConsumedEventRepository inbox,
            AccountingRepository accounting) {
        this.inbox = inbox;
        this.accounting = accounting;
    }

    @Transactional
    public void handle(CanonicalOrderPaid event) {
        if (!inbox.registerIfAbsent(
                "accounting",
                event.logicalEventId())) {
            return;
        }

        accounting.record(
            event.orderId(),
            event.amount(),
            event.currency()
        );
    }
}
~~~

registerIfAbsent là abstraction do ứng dụng triển khai bằng unique constraint và thao tác insert nguyên tử. Ví dụ giả định inbox và accounting dùng cùng database transaction manager. Nếu side effect nằm ở hệ thống khác, cần idempotency key phía dịch vụ đích hoặc workflow bền vững.

Nếu listener chạy qua Spring Modulith @ApplicationModuleListener, đó là listener của application event trong ứng dụng. @RabbitListener và @KafkaListener là adapter nhận message từ broker. Không nhầm ba loại listener này hoặc giả định chúng có cùng acknowledgement, transaction phase và retry semantics.

## 13. Vai trò của Event Publication Registry

Event Publication Registry theo dõi publication của application event tới các listener mà Spring Modulith quản lý. Nó hỗ trợ nhận diện publication chưa hoàn tất và phục hồi theo cơ chế được cấu hình.

Trong dual consume, cần tách ba trạng thái:

| Trạng thái | Thành phần sở hữu | Ý nghĩa |
|---|---|---|
| Local event publication | Spring Modulith registry | Event nội bộ đã được giao tới listener tương ứng chưa |
| Broker delivery/offset | Broker và consumer adapter | Message đã được giao/ack hoặc offset đã commit chưa |
| Business processing | Application service/inbox | Side effect nghiệp vụ đã được áp dụng cho logical event chưa |

Registry không hợp nhất offset giữa Kafka và RabbitMQ. Nó cũng không biết hai message từ hai nguồn có cùng logical event nếu adapter không cung cấp identity và inbox. Nếu producer externalize event qua broker, cần hiểu riêng publisher confirm, broker delivery và consumer acknowledgement.

Một local publication được đánh dấu complete không chứng minh consumer ngoài broker đã hoàn tất nghiệp vụ. Tương tự, broker ack không chứng minh toàn bộ saga hoặc workflow đã kết thúc. Hãy đo và lưu trạng thái tại đúng ranh giới.

## 14. Vòng lặp bridge và nguồn phát

Khi dùng bridge để chuyển event giữa broker cũ và mới, có nguy cơ tạo vòng lặp:

~~~mermaid
flowchart LR
    A["Legacy broker"] --> B["Bridge A to B"]
    B --> C["New broker"]
    C --> D["Bridge B to A"]
    D --> A
~~~

Một message có thể bị publish qua lại nếu bridge không biết message đã đi qua nó. Để ngăn vòng lặp, envelope nên có source/origin, migration ID hoặc danh sách hop được kiểm soát. Bridge phải bỏ qua message có origin là chính đích của nó hoặc đã được chuyển trong cùng migration path.

Các trường như origin và hop count phục vụ routing và quan sát, không thay thế logicalEventId. Một message đi qua bridge nhiều lần vẫn cần identity ổn định để consumer deduplicate.

Không chỉ kiểm tra vòng lặp trong happy path. Test cần mô phỏng message đã được bridge, message quay lại từ broker đích và message có metadata thiếu hoặc sai. Nếu không xác định được nguồn, hãy cách ly thay vì publish tiếp một cách mù quáng.

## 15. Xử lý lỗi, retry và dead-letter trong hai đường

Hai nguồn có thể có retry policy khác nhau. Consumer cũ có thể dùng RabbitMQ DLQ; consumer mới có thể dùng Kafka retry topic hoặc cơ chế khác. Nếu không chuẩn hóa vận hành, một event có thể được retry ở cả hai đường và tạo tải hoặc side effect trùng.

Cần thống nhất:
- Nhóm lỗi tạm thời và lỗi không thể phục hồi.
- Số lần thử và backoff theo từng nguồn.
- Logical event ID được giữ qua retry.
- Cách ghi nhận source, attempt và dead-letter reason.
- Cách quyết định đường nào có quyền redrive.
- Cách xử lý khi cùng logical event vào DLQ ở cả hai nguồn.

Khi shadow consumer gặp lỗi, không nên để nó làm thay đổi kết quả active consumer. Ghi nhận mismatch/failure riêng và đặt ngưỡng cảnh báo. Khi active consumer gặp lỗi, exception phải được truyền tới container hoặc cơ chế retry phù hợp; không nuốt lỗi rồi đánh dấu message hoàn tất.

Nếu redrive message từ DLQ cũ sang broker mới, hãy giữ logicalEventId và ghi audit về nguồn redrive. Đừng tạo event identity mới chỉ để vượt qua inbox deduplication.

## 16. Quan sát giai đoạn dual consume

Dual consume tạo thêm luồng message và trạng thái, vì vậy dashboard cần phân biệt source, consumer mode và kết quả so sánh.

Các metric hữu ích:

- Số message nhận từ legacy và new source.
- Lag/offset hoặc queue depth theo từng nguồn.
- Số logical event đã xử lý ở mỗi đường.
- Số match, mismatch, missing và duplicate.
- Handler duration và event age theo source.
- Retry, dead-letter và publication incomplete.
- Thời gian bắt kịp watermark.
- Tỷ lệ side effect bị chặn bởi inbox deduplication.
- Số event có payload hash khác nhau nhưng cùng logicalEventId.

Log và trace nên chứa logicalEventId, transport message ID, source, schema version, consumer mode (shadow/active), aggregate ID, sequence, correlation ID và migration ID. Không đưa những ID có cardinality cao vào metric tag; dùng log/trace để điều tra từng event.

Một dashboard chỉ hiển thị throughput tổng hợp có thể che giấu việc một nguồn đang lag hoặc thiếu event. Luôn tách số liệu theo source và so sánh cùng một cửa sổ thời gian hoặc checkpoint logic.

## 17. Kiểm thử chiến lược dual consume

Kiểm thử cần bao phủ cả tính đúng của payload lẫn hành vi khi hai đường cùng nhận một logical event.

| Scenario | Given | When | Then |
|---|---|---|---|
| Cùng event hai nguồn | Legacy và new payload cùng logicalEventId | Cả hai adapter nhận | Một side effect nghiệp vụ |
| Payload khác version | V1 và V2 cùng biểu diễn một event | Map về canonical model | Giá trị nghiệp vụ tương đương |
| Shadow mode | Consumer cũ active, mới shadow | Cùng event được phát tới hai đường | Consumer mới không tạo side effect thật |
| Mismatch | Cùng ID nhưng amount khác | Comparator so sánh | Ghi conflict và cảnh báo |
| Event thiếu | Một nguồn chưa nhận event tới watermark | So sánh checkpoint | Đánh dấu missing, không cutover |
| Event sai thứ tự | Sequence 8 đến trước 7 | Consumer xử lý | Phát hiện gap hoặc chờ theo policy |
| Duplicate đồng thời | Hai adapter xử lý cùng ID song song | Inbox insert cạnh tranh | Chỉ một transaction thắng |
| Rollback | Consumer mới active rồi cần quay lại | Chuyển ownership | Consumer cũ bắt kịp trước khi ghi |
| Bridge loop | Message quay về nguồn đã phát | Bridge nhận message | Không publish vòng lặp |
| Redrive | Event lỗi được phát lại từ DLQ | Consumer active nhận lại | Side effect không bị nhân đôi |

Integration test nên dùng broker hoặc transport thật cho phần cần xác minh routing, acknowledgement và offset. Unit test phù hợp cho mapper, comparator và state transition. Test concurrency cần database thật hoặc môi trường tương thích để xác minh unique constraint và transaction isolation.

Không dùng sleep cố định để đợi hai nguồn bắt kịp. Hãy chờ theo logical event ID, sequence hoặc watermark với timeout có giới hạn. Khi timeout, test phải báo nguồn nào thiếu event và checkpoint nào chưa đạt.

## 18. Điều kiện kết thúc migration

Không giữ dual consume vô thời hạn. Giai đoạn này làm tăng chi phí broker, storage, quan sát và khả năng xảy ra duplicate. Cần tiêu chí kết thúc được thống nhất trước khi bắt đầu.

Một số điều kiện có thể gồm:

- Consumer mới đã đọc được toàn bộ event contract đang được hỗ trợ.
- Không còn mismatch chưa giải thích trong cửa sổ quan sát đại diện.
- Consumer mới bắt kịp checkpoint và backlog ổn định.
- Error rate, retry, DLQ và latency nằm trong SLO.
- Quyền ghi đã chuyển sang consumer mới và idempotency hoạt động.
- Runbook rollback đã được kiểm chứng.
- Producer/bridge cũ đã ngừng phát hoặc nguồn cũ đã được drain.
- Các queue, topic, adapter và metric migration không còn cần thiết đã được lên kế hoạch dọn.

Sau khi migration hoàn tất, gỡ adapter cũ, bridge và cấu hình không còn dùng theo một release có kiểm soát. Không xóa ngay dữ liệu checkpoint hoặc inbox record nếu chúng vẫn cần cho replay, audit hay rollback.

## 19. Lỗi thường gặp khi triển khai dual consume

**Cho cả hai consumer cùng ghi nghiệp vụ.** Một event có thể tạo hai side effect. Hãy dùng shadow mode hoặc một writer duy nhất, kèm inbox khi cần overlap.

**Dùng broker message ID làm logical identity.** Hai nguồn thường có ID transport khác nhau. Hãy giữ logicalEventId xuyên migration.

**Đưa source vào unique key deduplication.** Bản legacy và new sẽ bị coi là hai event khác nhau. Chỉ đưa source vào key khi nghiệp vụ thật sự muốn xử lý riêng từng nguồn.

**So sánh offset của hai broker.** Offset không có cùng miền giá trị hoặc semantics. Hãy dùng logical event ID, aggregate sequence hoặc checkpoint mapping.

**Cutover trước khi consumer mới bắt kịp.** Event trong backlog có thể bị bỏ sót. Hãy xác minh watermark và drain trước khi chuyển quyền ghi.

**Chỉ so sánh số message.** Hai nguồn có thể thiếu hoặc thừa các event khác nhau. Hãy so sánh theo logicalEventId và kết quả nghiệp vụ.

**Shadow consumer tạo side effect thật.** Việc kiểm thử có thể gửi email hoặc capture thanh toán hai lần. Hãy cô lập side effect hoặc dùng sandbox.

**Không ngăn bridge loop.** Message có thể đi qua lại giữa broker. Hãy dùng origin/hop metadata và kiểm thử vòng lặp.

**Xóa inbox khi rollback.** Event cũ có thể được áp dụng lại. Hãy giữ deduplication record theo retention policy.

**Coi Event Publication Registry là công cụ điều phối hai broker.** Registry quản lý local publication của Spring Modulith; offset, retry và deduplication xuyên nguồn cần cơ chế riêng.

## Kết luận

Dual consume cho phép hệ thống đọc song song từ nguồn event cũ và mới để kiểm chứng contract, so sánh kết quả và chuyển quyền xử lý có kiểm soát. Chiến lược chỉ an toàn khi xác định rõ nguồn sự thật, consumer nào được ghi, logical event identity, ordering, checkpoint, retry và kế hoạch rollback.

Trong Spring Modulith, hãy đặt adapter theo từng nguồn ở ranh giới tích hợp, chuẩn hóa payload về canonical event và để application service giữ quy tắc nghiệp vụ cùng idempotency. Bắt đầu bằng shadow consume, đo mismatch và lag, sau đó cutover khi consumer mới đã bắt kịp. Event Publication Registry hỗ trợ publication nội bộ; inbox, broker checkpoint và quy trình vận hành chịu trách nhiệm cho tính đúng của dual consume xuyên nguồn.

