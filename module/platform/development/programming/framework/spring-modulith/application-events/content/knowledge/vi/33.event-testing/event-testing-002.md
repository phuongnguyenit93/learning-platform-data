# Kiểm thử publish

Kiểm thử publish xác nhận một use case phát đúng application event khi thay đổi nghiệp vụ đạt điều kiện, với payload và số lần phát phù hợp. Trong Spring Modulith, event là hợp đồng giao tiếp giữa các module: module nguồn công bố sự kiện đã xảy ra, còn module nhận phản ứng qua listener. Kiểm thử cần làm rõ publisher đã phát event, listener có nhận và hoàn tất xử lý hay không, và transaction nguồn có commit trước khi listener sau commit chạy hay không.

Không nên gộp mọi bước thành một khẳng định “event thành công”. `publishEvent` được gọi, listener được kích hoạt, listener commit thay đổi riêng và message được gửi qua broker là các mốc khác nhau. Mỗi loại kiểm thử cần xác nhận đúng mốc mà nó chịu trách nhiệm.

## 1. Xác định điều cần kiểm thử

Một use case publish event thường có các điều kiện cần xác nhận:

- Event chỉ được phát khi nghiệp vụ đạt điều kiện, ví dụ đơn hàng chuyển sang `CONFIRMED`.
- Event có đúng loại và chứa các trường cần thiết, như event ID, aggregate ID, version và thời điểm xảy ra.
- Event được phát đúng số lần; một lần xác nhận không phát trùng do nhánh code hoặc retry trong cùng use case.
- Trường hợp validation thất bại hoặc transaction rollback không kích hoạt listener chỉ chạy sau commit.
- Các listener phù hợp nhận event và tạo ra tác động mong đợi.
- Publication chưa hoàn tất có thể được phát hiện và phục hồi theo cơ chế Event Publication Registry.
- Nếu event được externalize, adapter gửi đúng message và metadata đến broker theo hợp đồng riêng.

Trước khi viết test, hãy xác định ranh giới của event:

| Mốc | Điều được xác nhận |
| --- | --- |
| Publisher gọi `publishEvent` | Use case đã phát application event với payload cụ thể. |
| Transaction nguồn commit | Thay đổi nghiệp vụ của module nguồn đã được lưu bền vững. |
| Transactional listener được kích hoạt | Event được giao ở transaction phase đã cấu hình. |
| Listener hoàn tất | Tác động của module nhận đã commit theo transaction của listener. |
| Event được externalize | Adapter đã chuyển event thành message gửi ra hệ thống bên ngoài. |
| Broker xác nhận publish | Broker đã xác nhận nhận message theo cấu hình giao thức. |

Một unit test kiểm tra publisher không chứng minh listener đã xử lý. Một test listener không chứng minh broker đã nhận message. Chọn đúng cấp kiểm thử để kết luận chính xác.

## 2. Thiết kế event contract có thể kiểm thử

Event nên mô tả một sự kiện nghiệp vụ đã xảy ra, bất biến và có định danh ổn định. Ví dụ:

```java
public record OrderConfirmed(
        UUID eventId,
        UUID orderId,
        long orderVersion,
        BigDecimal totalAmount,
        Instant occurredAt
) {}
```

`eventId` giúp nhận diện cùng một event qua retry hoặc redelivery. `orderVersion` hỗ trợ consumer phát hiện event cũ hoặc sai thứ tự. Payload chỉ nên chứa dữ liệu consumer cần; không truyền entity đang được quản lý bởi persistence context hoặc thông tin bí mật không cần thiết.

Publisher phát event trong use case:

```java
@Service
public class ConfirmOrderService {

    private final OrderRepository orders;
    private final ApplicationEventPublisher events;
    private final Clock clock;

    public ConfirmOrderService(
            OrderRepository orders,
            ApplicationEventPublisher events,
            Clock clock) {
        this.orders = orders;
        this.events = events;
        this.clock = clock;
    }

    @Transactional
    public void confirm(UUID orderId) {
        Order order = orders.findById(orderId)
                .orElseThrow(() -> new OrderNotFoundException(orderId));

        order.confirm();
        orders.save(order);

        events.publishEvent(new OrderConfirmed(
                UUID.randomUUID(),
                order.id(),
                order.version(),
                order.totalAmount(),
                clock.instant()
        ));
    }
}
```

`ApplicationEventPublisher` chỉ phát application event trong process hiện tại. Nếu event cần được giao đến module khác trong cùng ứng dụng, listener Spring có thể nhận event đó. Nếu cần gửi ra broker, phải kiểm thử riêng phần externalization và adapter.

## 3. Unit test publisher bằng Mockito

Unit test phù hợp để xác nhận logic của use case mà không khởi động Spring context. Mock `ApplicationEventPublisher`, gọi service và kiểm tra event được phát đúng một lần với payload mong đợi.

```java
@ExtendWith(MockitoExtension.class)
class ConfirmOrderServiceTests {

    @Mock OrderRepository orders;
    @Mock ApplicationEventPublisher events;
    @Captor ArgumentCaptor<OrderConfirmed> eventCaptor;

    private ConfirmOrderService service;

    @BeforeEach
    void setUp() {
        service = new ConfirmOrderService(
                orders,
                events,
                Clock.fixed(
                        Instant.parse("2026-01-10T09:00:00Z"),
                        ZoneOffset.UTC
                )
        );
    }

    @Test
    void publishesOrderConfirmedAfterConfirmingOrder() {
        UUID orderId = UUID.randomUUID();
        Order order = Order.pending(orderId, new BigDecimal("125.00"));
        when(orders.findById(orderId)).thenReturn(Optional.of(order));

        service.confirm(orderId);

        verify(orders).save(order);
        verify(events, times(1)).publishEvent(eventCaptor.capture());

        OrderConfirmed event = eventCaptor.getValue();
        assertThat(event.orderId()).isEqualTo(orderId);
        assertThat(event.totalAmount()).isEqualByComparingTo("125.00");
        assertThat(event.occurredAt())
                .isEqualTo(Instant.parse("2026-01-10T09:00:00Z"));
        assertThat(event.eventId()).isNotNull();
    }

    @Test
    void doesNotPublishWhenOrderDoesNotExist() {
        UUID orderId = UUID.randomUUID();
        when(orders.findById(orderId)).thenReturn(Optional.empty());

        assertThatThrownBy(() -> service.confirm(orderId))
                .isInstanceOf(OrderNotFoundException.class);

        verify(events, never()).publishEvent(any(Object.class));
    }
}
```

Đây là unit test cho quyết định publish của use case. Mockito xác nhận lời gọi publisher và payload, nhưng không kiểm tra transaction Spring, listener discovery, Event Publication Registry hoặc việc event được gửi ra broker. Các phần đó cần integration test phù hợp.

Để test dễ ổn định, inject `Clock` thay vì gọi trực tiếp `Instant.now()` trong logic cần so sánh thời gian. Dữ liệu đầu vào nên được dựng rõ ràng để test chỉ thất bại khi hành vi publish thay đổi.

## 4. Kiểm tra event được phát trong Spring context

Khi muốn xác nhận event thực sự được publish qua application context, có thể dùng `@RecordApplicationEvents` cùng `ApplicationEvents` của Spring Test:

```java
@SpringBootTest
@RecordApplicationEvents
class ConfirmOrderPublishIntegrationTests {

    @Autowired ConfirmOrderService service;
    @Autowired ApplicationEvents applicationEvents;

    @Test
    void recordsOneOrderConfirmedEvent() {
        UUID orderId = createPendingOrder();

        service.confirm(orderId);

        assertThat(applicationEvents.stream(OrderConfirmed.class))
                .singleElement()
                .satisfies(event -> {
                    assertThat(event.orderId()).isEqualTo(orderId);
                    assertThat(event.eventId()).isNotNull();
                });
    }
}
```

`@RecordApplicationEvents` ghi nhận application event được phát trong phạm vi test. Cách này xác nhận event đã được publish trong Spring context và có payload phù hợp. Nó không tự chứng minh listener bất đồng bộ đã hoàn tất hoặc transaction listener đã commit thành công.

Test trên không nên đặt `@Transactional` ở cấp test nếu mục tiêu là quan sát hành vi sau commit. Test transaction do Spring Test quản lý thường rollback khi kết thúc; khi đó `AFTER_COMMIT` listener không được kích hoạt theo cách mà test mong đợi. Hãy để use case tự mở và commit transaction, hoặc điều khiển commit/rollback tường minh bằng `TransactionTemplate` hay `TestTransaction` khi cần.

## 5. Kiểm thử publish và listener bằng Scenario API

Spring Modulith cung cấp `@ApplicationModuleTest` và `Scenario` API để kiểm tra giao tiếp event trong phạm vi module. `Scenario` có thể kích hoạt một hành động của ứng dụng, chờ event được phát hoặc chờ trạng thái do listener cập nhật.

Ví dụ kiểm tra use case thực sự phát event:

```java
@ApplicationModuleTest
class OrderModuleEventTests {

    @Autowired ConfirmOrderService confirmOrder;

    @Test
    void publishesOrderConfirmed(Scenario scenario) {
        UUID orderId = createPendingOrder();

        scenario.stimulate(() -> confirmOrder.confirm(orderId))
                .andWaitForEventOfType(OrderConfirmed.class)
                .toArrive();
    }
}
```

Nếu mục tiêu là kiểm tra listener đã cập nhật read model, hãy chờ trạng thái thay đổi thay vì chỉ chờ event đến:

```java
@ApplicationModuleTest
class OrderProjectionTests {

    @Autowired ConfirmOrderService confirmOrder;
    @Autowired OrderSummaryRepository summaries;

    @Test
    void updatesSummaryAfterOrderConfirmed(Scenario scenario) {
        UUID orderId = createPendingOrder();

        scenario.stimulate(() -> confirmOrder.confirm(orderId))
                .andWaitForStateChange(() -> summaries.findById(orderId))
                .andWaitAtMost(Duration.ofSeconds(3))
                .toMatch(summary -> summary
                        .map(OrderSummary::status)
                        .filter(OrderStatus.CONFIRMED::equals)
                        .isPresent());
    }
}
```

Scenario API giúp chờ theo điều kiện với timeout giới hạn, tránh `Thread.sleep()` tùy ý. Kiểm tra đúng API và package của `Scenario`, `@ApplicationModuleTest` theo phiên bản Spring Modulith mà dự án đang dùng.

Phân biệt hai assertion:

- `andWaitForEventOfType(...).toArrive()` kiểm tra event mong đợi đã được phát trong scenario.
- `andWaitForStateChange(...).toMatch(...)` kiểm tra tác động quan sát được sau khi listener xử lý.

Một event có thể được publish đúng nhưng listener thất bại; ngược lại, trạng thái có thể thay đổi qua một đường xử lý khác. Test nên khẳng định đúng nguyên nhân và kết quả mà use case yêu cầu.

## 6. Kiểm thử chỉ publish khi transaction commit

Với `@TransactionalEventListener(phase = AFTER_COMMIT)` hoặc `@ApplicationModuleListener`, listener chỉ được xử lý sau khi transaction nguồn commit theo semantics tương ứng. Khi transaction rollback, listener sau commit không được chạy.

Có thể dùng `TransactionTemplate` để kiểm soát tình huống rollback:

```java
@SpringBootTest
class OrderEventTransactionTests {

    @Autowired PlatformTransactionManager transactionManager;
    @Autowired ApplicationEventPublisher events;
    @Autowired InventoryRepository inventory;

    @Test
    void doesNotRunAfterCommitListenerWhenTransactionRollsBack() {
        UUID orderId = UUID.randomUUID();
        TransactionTemplate tx = new TransactionTemplate(transactionManager);

        tx.executeWithoutResult(status -> {
            events.publishEvent(new OrderConfirmed(
                    UUID.randomUUID(),
                    orderId,
                    1L,
                    new BigDecimal("50.00"),
                    Instant.now()
            ));
            status.setRollbackOnly();
        });

        assertThat(inventory.existsReservationFor(orderId)).isFalse();
    }
}
```

Ví dụ giả định `InventoryRepository` chỉ được cập nhật bởi listener sau commit. Event có thể đã được phát vào application event multicaster bên trong transaction; điều cần xác nhận là listener transaction-bound không thực hiện side effect sau khi transaction rollback. Không khẳng định rằng lời gọi `publishEvent` chưa từng xảy ra.

Với test commit, để transaction thực sự commit rồi chờ listener hoàn tất bằng Scenario API hoặc một điều kiện có timeout. Không dùng test transaction mặc định rollback nếu mục tiêu là kiểm tra `AFTER_COMMIT`.

## 7. Kiểm tra không publish khi nghiệp vụ không hợp lệ

Publisher chỉ nên phát event khi trạng thái nghiệp vụ đã thỏa điều kiện. Các trường hợp nên kiểm thử:

| Tình huống | Kết quả publish mong đợi |
| --- | --- |
| Đơn hàng hợp lệ chuyển sang `CONFIRMED` | Phát đúng một `OrderConfirmed`. |
| Không tìm thấy đơn hàng | Không phát event. |
| Đơn hàng đã bị hủy và không thể xác nhận | Không phát event xác nhận. |
| Thiếu dữ liệu bắt buộc | Validation thất bại trước publish. |
| Lưu trạng thái nghiệp vụ thất bại và transaction rollback | Listener sau commit không chạy. |
| Gọi lại command theo idempotency key đã xử lý | Không tạo thêm event nghiệp vụ ngoài hợp đồng đã định nghĩa. |

Đối với command idempotent, cần quyết định rõ lần gọi lặp trả về kết quả cũ, phát event mới hay không phát gì. Test phải phản ánh chính sách đó, tránh chỉ kiểm tra `times(1)` mà không xét trạng thái nghiệp vụ.

## 8. Kiểm tra nhiều listener nhận cùng event

Một application event có thể được nhiều listener quan tâm. Ví dụ `OrderConfirmed` được Inventory dùng để giữ hàng và Billing dùng để tạo hóa đơn. Mỗi listener có trách nhiệm và transaction riêng.

Kiểm thử nên xác nhận:

- Các listener dự kiến đều được đăng ký trong module/application context.
- Mỗi listener nhận đúng event và tạo tác động đúng phạm vi.
- Listener không liên quan không tạo side effect.
- Một listener thất bại không bị che giấu bởi listener khác thành công.
- Việc retry publication của listener lỗi không làm lặp tác động đã commit ở listener khác.

Không nên viết một test quá lớn chỉ xác nhận toàn bộ hệ thống khởi động và mọi listener chạy. Tách test theo module/consumer để lỗi chỉ ra đúng trách nhiệm bị vi phạm; thêm một số integration test ở cấp ứng dụng cho các luồng quan trọng.

## 9. Kiểm thử payload và hợp đồng event

Test publisher nên kiểm tra các trường có ý nghĩa hợp đồng:

- Event type đúng với sự kiện đã xảy ra.
- `eventId` không null và ổn định trong phạm vi lần phát.
- Aggregate ID tham chiếu đúng đối tượng nghiệp vụ.
- Version/sequence tăng theo quy tắc nếu event cần kiểm soát thứ tự.
- Timestamp dùng clock/timezone thống nhất.
- Amount, currency và trạng thái có giá trị hợp lệ.
- Payload không chứa entity persistence, token, password hoặc dữ liệu không cần thiết.

Không kiểm tra mọi chi tiết implementation như thứ tự gọi từng repository nếu thứ tự đó không phải hợp đồng. Hãy ưu tiên kiểm tra event và kết quả nghiệp vụ quan sát được.

Khi event được serialize để externalize, bổ sung contract test cho serializer/deserializer và schema version. Consumer cũ cần xử lý được payload theo chính sách tương thích đã thống nhất. Test publish trong Spring context không thay thế test serialization qua adapter.

## 10. Kiểm thử Event Publication Registry và phục hồi

Event Publication Registry theo dõi publication đến transactional listener và ghi nhận listener hoàn tất. Khi listener lỗi hoặc tiến trình dừng trước khi trạng thái hoàn tất được lưu, publication có thể còn incomplete và được phục hồi theo cấu hình persistence cùng cơ chế của phiên bản Spring Modulith.

Một bộ kiểm thử phục hồi có thể xác nhận:

1. Listener thành công thì publication được ghi nhận hoàn tất.
2. Listener thất bại thì publication chưa được đánh dấu hoàn tất.
3. Publication incomplete có thể được phát hiện qua API công khai của registry.
4. Sau khi nguyên nhân được khắc phục và publication được gửi lại theo cơ chế hỗ trợ, listener hoàn tất.
5. Consumer xử lý lặp an toàn nhờ idempotency/inbox nếu side effect đã commit trước sự cố.

Không truy vấn hoặc cập nhật trực tiếp bảng nội bộ của registry để làm test pass. Dùng API công khai và cơ chế phục hồi được hỗ trợ bởi phiên bản Spring Modulith. Registry tracking và listener effect là hai kết quả cần quan sát riêng.

## 11. Kiểm thử externalized event và broker

Nếu event được đánh dấu externalize hoặc chuyển qua adapter, kiểm thử publish nội bộ chưa đủ. Cần một lớp integration test riêng cho chặng broker:

- Event được ánh xạ đúng destination/topic/exchange.
- Message key, header, event ID và correlation metadata được truyền đúng.
- Serializer tạo payload tương thích với consumer.
- Adapter xử lý publish failure và acknowledgement theo cấu hình.
- Retry/redelivery không tạo message ID mới cho cùng event.
- Consumer ngoài có thể xử lý message và commit theo delivery semantics đã chọn.

Có thể dùng broker embedded hoặc Testcontainers tùy hạ tầng dự án. Với Kafka, kiểm tra record trong topic và key/header; với RabbitMQ, kiểm tra routing, queue và publisher confirm phù hợp. Không dùng mock `KafkaTemplate` hoặc `RabbitTemplate` để kết luận broker thực đã nhận message.

Spring Modulith externalization và broker adapter có API/cấu hình khác nhau theo phiên bản và loại broker. Test cần khởi động đúng adapter mà ứng dụng triển khai, không suy ra broker delivery chỉ từ việc event được publish trong application context.

## 12. Kiểm thử ranh giới module

Event là hợp đồng giao tiếp giữa module. Ngoài kiểm thử hành vi publish, nên có kiểm tra cấu trúc để bảo đảm module nguồn không phụ thuộc vào implementation nội bộ của consumer.

```java
class ModuleStructureTests {

    @Test
    void moduleDependenciesAreValid() {
        ApplicationModules.of(Application.class).verify();
    }
}
```

Kiểm tra này xác nhận các quy tắc phụ thuộc module theo cấu hình Spring Modulith. Nó không chứng minh publisher đã phát event hoặc listener đã chạy; cần kết hợp với unit/integration test ở trên.

## 13. Những lỗi thường gặp khi kiểm thử publish

| Lỗi | Vì sao sai | Cách khắc phục |
| --- | --- | --- |
| Chỉ verify `publishEvent` rồi kết luận listener chạy | Mock publisher không có Spring event dispatch. | Dùng Spring context hoặc Scenario API để kiểm tra listener. |
| Dùng `Thread.sleep()` chờ listener | Test chậm và không ổn định theo tải máy. | Chờ event/state với timeout có giới hạn. |
| Đánh dấu test `@Transactional` rồi đợi `AFTER_COMMIT` | Test transaction thường rollback khi kết thúc. | Để command commit thật hoặc điều khiển commit tường minh. |
| Bắt exception trong listener để test không fail | Có thể khiến publication bị xem là hoàn tất dù nghiệp vụ lỗi. | Ghi nhận lỗi rồi truyền exception về framework. |
| Chỉ test publisher, bỏ qua payload | Event có thể được phát với ID hoặc dữ liệu sai. | Capture event và assert các trường hợp đồng. |
| Dùng mock broker để xác nhận externalization | Mock không chứng minh message được broker nhận. | Dùng integration test với broker thật/embedded. |
| Test quá nhiều module trong một context | Khó xác định listener nào gây lỗi và test dễ chậm. | Dùng `@ApplicationModuleTest` theo module, thêm ít test cấp ứng dụng. |
| Dùng timestamp hiện tại trực tiếp | Test phụ thuộc thời gian chạy và khó so sánh. | Inject `Clock` và dùng clock cố định trong test. |

## 14. Checklist cho một bài kiểm thử publish

- [ ] Xác định rõ đang kiểm tra publisher, listener, registry hay broker adapter.
- [ ] Kiểm tra event type, event ID, aggregate ID, version và payload cần thiết.
- [ ] Xác nhận publish đúng một lần theo hợp đồng command.
- [ ] Kiểm tra nhánh validation thất bại không phát event.
- [ ] Kiểm tra transaction rollback không kích hoạt listener sau commit.
- [ ] Dùng `@RecordApplicationEvents` hoặc Mockito cho đúng cấp kiểm thử.
- [ ] Dùng `@ApplicationModuleTest` và Scenario API cho luồng module bất đồng bộ.
- [ ] Chờ bằng điều kiện và timeout, không dùng sleep tùy ý.
- [ ] Kiểm tra side effect của listener và khả năng xử lý lặp an toàn.
- [ ] Kiểm tra publication incomplete/recovery nếu luồng cần độ tin cậy cao.
- [ ] Kiểm tra serializer, destination và broker riêng khi event externalize.
- [ ] Kiểm tra cấu trúc module bằng `ApplicationModules.verify()` như lớp bảo vệ bổ sung.

Kiểm thử publish cần đi từ hợp đồng của use case đến đúng ranh giới giao event. Mockito xác nhận quyết định phát event trong unit test; `@RecordApplicationEvents` xác nhận event được publish trong Spring context; `@ApplicationModuleTest` cùng Scenario API xác nhận event và tác động của listener; broker integration test xác nhận chặng externalization. Khi mỗi test kiểm tra đúng một bảo đảm, lỗi publish, lỗi transaction và lỗi delivery được phân biệt rõ, giúp các module Spring Modulith giao tiếp đáng tin cậy hơn.
