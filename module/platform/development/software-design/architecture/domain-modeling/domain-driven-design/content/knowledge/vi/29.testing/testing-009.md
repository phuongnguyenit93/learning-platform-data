# Kiểm thử sự kiện và hợp đồng tích hợp xuyên ngữ cảnh

Trong một hệ thống Domain-Driven Design (DDD), mỗi Bounded Context sở hữu mô hình, dữ liệu và quy tắc riêng. Khi một context cần thông báo điều đã xảy ra cho context khác, nó thường phát Integration Event qua message broker hoặc một cơ chế truyền thông điệp tương đương. Hai context có thể triển khai, phát hành và mở rộng độc lập, nhưng vẫn phải giữ đúng cam kết giao tiếp.

Kiểm thử tích hợp xuyên ngữ cảnh vì vậy cần trả lời hai câu hỏi:

- Producer có phát đúng thông điệp mà hợp đồng đã cam kết không?
- Consumer có thể hiểu và xử lý thông điệp đó theo đúng ý nghĩa mà nó phụ thuộc không?

Một bài test chỉ kiểm tra rằng JSON serialize thành công chưa chứng minh hai context hiểu cùng một ý nghĩa. Ngược lại, một bài end-to-end chạy qua toàn bộ hệ thống có thể phát hiện lỗi nhưng thường khó xác định chính xác contract nào bị phá vỡ. Cần kết hợp kiểm thử contract, kiểm thử consumer, kiểm thử producer, kiểm thử adapter và một số kiểm thử tích hợp thực tế có chọn lọc.

## 1. Vì sao cần kiểm thử hợp đồng xuyên ngữ cảnh?

Giả sử Order Management phát sự kiện OrderPlaced để Inventory giữ hàng và Payment khởi tạo thanh toán:

~~~mermaid
flowchart LR
    O[Order Management] -->|OrderPlaced| B[(Message Broker)]
    B --> I[Inventory]
    B --> P[Payment]
~~~

Mỗi context có thể triển khai bằng một ứng dụng, một database hoặc một nhóm khác nhau. Chúng không chia sẻ transaction và không nhất thiết phát hành cùng thời điểm.

Những thay đổi tưởng như nhỏ có thể phá vỡ tích hợp:

- Producer đổi tên trường orderId thành id.
- Producer thay amount từ số tiền theo đơn vị nhỏ nhất sang chuỗi decimal nhưng không thông báo.
- Consumer giả định currency luôn là VND trong khi producer bắt đầu phát nhiều loại tiền.
- Producer đổi ý nghĩa của OrderConfirmed từ “đơn đã được xác nhận” thành “đơn đã sẵn sàng giao”.
- Consumer không xử lý được một event version mới có thêm enum value.
- Producer commit Order nhưng không ghi được message để publish.
- Consumer xử lý message thành công nhưng lỗi trước khi acknowledge, khiến broker giao lại.

Contract testing giúp phát hiện sớm những sai lệch về cấu trúc và kỳ vọng giao tiếp. Các kiểm thử khác cần xác nhận ngữ nghĩa, trạng thái và hành vi khi message được giao trễ, lặp hoặc sai thứ tự.

## 2. Phân biệt Domain Event và Integration Event

Domain Event mô tả điều có ý nghĩa trong một Bounded Context. Nó thuộc ngôn ngữ và mô hình nội bộ của context đó.

Integration Event là contract được công bố để context khác có thể tiêu thụ. Nó thường được tạo từ một hoặc nhiều Domain Event, nhưng không nhất thiết có cùng cấu trúc hoặc tên gọi.

Ví dụ trong Order Management:

~~~java
public record OrderId(String value) {}

public record OrderPlaced(
        UUID eventId,
        OrderId orderId,
        Instant occurredAt,
        Money total,
        List<OrderLine> lines
) {}
~~~

OrderPlaced là Domain Event nội bộ trong ví dụ này. Khi công bố cho Inventory, producer có thể tạo Integration Event:

~~~java
public record OrderPlacedV1(
        String orderId,
        Instant occurredAt,
        String totalAmount,
        String currency,
        List<OrderLineV1> lines
) {}

public record OrderLineV1(
        String productReference,
        int quantity
) {}
~~~

Integration Event chỉ chứa dữ liệu mà consumer cần để thực hiện trách nhiệm của nó. Không nên công bố toàn bộ Aggregate hoặc các object nội bộ chỉ vì chúng đang có sẵn trong memory.

### 2.1. Contract là ranh giới ngôn ngữ

Producer và consumer có thể gọi cùng một khái niệm bằng tên khác nhau. Ví dụ, Order Management dùng Order, còn Inventory dùng Fulfillment Request. Contract cần xác định rõ ý nghĩa tại ranh giới.

Không nên bắt consumer hiểu toàn bộ mô hình nội bộ của producer. Một Anti-Corruption Layer (ACL) ở phía consumer có thể chuyển Integration Event thành command hoặc khái niệm miền cục bộ.

## 3. Contract của một Integration Event gồm những gì?

Một contract không chỉ là danh sách field JSON. Nó còn bao gồm:

- Tên và ý nghĩa event.
- Định danh duy nhất của message.
- Schema và phiên bản schema.
- Ý nghĩa của từng field, đơn vị đo và quy ước null.
- Quy tắc thời gian và timezone.
- Ngữ nghĩa về thứ tự và quan hệ nhân quả nếu có.
- Điều kiện phát event và thời điểm event được xem là đã xảy ra.
- Chính sách tương thích khi schema thay đổi.
- Cam kết giao nhận và retry mà consumer cần biết.

Ví dụ envelope:

~~~json
{
  "eventId": "e9f3a7d4-6a0a-4d6f-8a4e-123456789abc",
  "eventType": "OrderPlaced",
  "schemaVersion": 1,
  "producer": "order-management",
  "aggregateType": "Order",
  "aggregateId": "order-123",
  "aggregateVersion": 4,
  "correlationId": "checkout-456",
  "causationId": "place-order-command-789",
  "payload": {
    "orderId": "order-123",
    "occurredAt": "2026-11-18T10:15:00Z",
    "currency": "VND",
    "totalAmount": "1250000",
    "lines": [
      {
        "productReference": "SKU-001",
        "quantity": 2
      }
    ]
  }
}
~~~

Đây là ví dụ minh họa. Một hệ thống có thể đặt metadata ở message header thay vì body. Điều quan trọng là producer và consumer thống nhất vị trí, kiểu dữ liệu và ý nghĩa.

Trong các ví dụ Java tiếp theo, OrderPlacedV1 là payload; eventId, eventType và schemaVersion thuộc envelope hoặc message header do publisher/adapter quản lý. occurredAt là thời điểm nghiệp vụ nên thuộc payload trong contract này. Broker adapter unwrap payload trước khi gọi listener.

### 3.1. Phân biệt thời điểm nghiệp vụ và thời điểm xử lý

Không nên chỉ có một trường timestamp mơ hồ. Các khái niệm có thể khác nhau:

| Trường | Ý nghĩa |
|---|---|
| occurredAt | Thời điểm sự kiện nghiệp vụ xảy ra |
| publishedAt | Thời điểm producer/bộ phát công bố message |
| receivedAt | Thời điểm consumer nhận message |
| processedAt | Thời điểm consumer hoàn tất xử lý |

Consumer cần biết event xảy ra khi nào để áp dụng quy tắc nghiệp vụ. Hệ thống vận hành cần biết message bị trễ bao lâu. Hai mục tiêu này không nên bị trộn lẫn.

### 3.2. Đơn vị và định dạng phải rõ ràng

Các field như amount, quantity, percentage và duration cần có đơn vị hoặc quy ước rõ. Ví dụ, amount là chuỗi decimal theo major currency unit hay số nguyên theo minor unit? Quantity là số nguyên hay cho phép phần thập phân? Một thay đổi đơn vị có thể vẫn hợp lệ về schema nhưng làm sai kết quả nghiệp vụ.

## 4. Consumer contract và producer contract

Hai phía có trách nhiệm khác nhau.

| Phía | Cam kết | Câu hỏi kiểm thử |
|---|---|---|
| Producer | Phát đúng event và schema đã công bố | Message thực tế có khớp contract không? |
| Consumer | Chấp nhận và xử lý đúng contract mà nó phụ thuộc | Consumer có parse và diễn giải message hợp lệ không? |
| Contract owner | Quản lý định nghĩa, version và compatibility | Thay đổi có được thông báo và kiểm tra không? |

Producer contract thường được xác minh bằng cách lấy message thực tế được tạo ra và so với schema/expectation đã công bố.

Consumer contract thường được xác minh bằng cách cung cấp message mẫu theo contract cho consumer và kiểm tra adapter có giải mã đúng, tạo command đúng và thực hiện hành vi mong đợi không.

### 4.1. Consumer không nên yêu cầu mọi field producer có

Consumer chỉ nên phụ thuộc vào phần contract cần thiết cho use case của nó. Nếu consumer cần orderId và lines, nó không nên thất bại chỉ vì producer thêm một field optional như salesChannel.

Điều này làm producer và consumer ít coupling hơn, đồng thời giúp schema có thể tiến hóa.

### 4.2. Producer không được giả định mọi consumer đã nâng cấp

Producer có thể triển khai trước hoặc sau consumer. Khi có nhiều consumer độc lập, producer cần tuân thủ chính sách tương thích đã thống nhất. Không nên phát hành một breaking change chỉ vì consumer trong cùng repository đã được cập nhật.

## 5. Schema test khác semantic contract test

Schema test kiểm tra hình dạng dữ liệu:

- Field bắt buộc có mặt.
- Kiểu dữ liệu đúng.
- Enum và format hợp lệ.
- Cấu trúc nested object đúng.
- Version được hỗ trợ.

Semantic contract test kiểm tra ý nghĩa:

- OrderPlaced chỉ phát sau khi đơn thực sự được tạo thành công.
- totalAmount biểu diễn tổng tiền theo currency đã khai báo.
- Quantity trong event phản ánh lượng hàng consumer cần giữ.
- OrderCancelled không đồng nghĩa với PaymentRefunded.
- Event không nói rằng hàng đã giao nếu chỉ mới xác nhận đơn.

Schema hợp lệ không bảo đảm ngữ nghĩa đúng. Ví dụ, producer có thể phát totalAmount bằng giá trước chiết khấu thay vì giá cuối cùng mà contract đã định nghĩa. JSON vẫn parse được nhưng consumer sẽ xử lý sai.

## 6. Kiểm thử producer

Producer cần được kiểm tra ở ít nhất ba điểm:

1. Quy tắc nghiệp vụ quyết định khi nào phát event.
2. Mapping từ Domain Event sang Integration Event.
3. Serialization và publish contract.

### 6.1. Kiểm thử điều kiện phát event

Ví dụ, Order Management chỉ phát OrderPlaced sau khi thao tác đặt hàng thành công:

~~~java
@Test
void publishesOrderPlacedAfterOrderIsCreated() {
    PlaceOrderResult result = placeOrderService.handle(validCommand());

    assertEquals(OrderStatus.PLACED, result.status());
    assertThat(outbox.findPendingEvents())
            .extracting(OutboxMessage::eventType)
            .contains("OrderPlaced");
}
~~~

Một test khác cần xác nhận thao tác thất bại không tạo event:

~~~java
@Test
void doesNotPublishOrderPlacedWhenOrderCannotBeCreated() {
    assertThrows(
            InvalidOrder.class,
            () -> placeOrderService.handle(invalidCommand())
    );

    assertThat(outbox.findPendingEvents()).isEmpty();
}
~~~

Các ví dụ dùng repository/outbox giả định được inject vào service. Mục tiêu là kiểm tra hành vi use case, không phụ thuộc broker thật ở unit test.

### 6.2. Kiểm thử mapping Domain Event sang Integration Event

Domain Event không nên bị serialize trực tiếp nếu nó chứa chi tiết nội bộ hoặc kiểu miền không thuộc contract công khai.

~~~java
public record IntegrationEventEnvelope<T>(
        UUID eventId,
        String eventType,
        int schemaVersion,
        T payload
) {}

public final class OrderEventMapper {
    public OrderPlacedV1 toIntegrationEvent(OrderPlaced event) {
        return new OrderPlacedV1(
                event.orderId().value(),
                event.occurredAt(),
                event.total().amount().toPlainString(),
                event.total().currency().getCurrencyCode(),
                event.lines().stream()
                        .map(line -> new OrderLineV1(
                                line.productReference(),
                                line.quantity()
                        ))
                        .toList()
        );
    }

    public IntegrationEventEnvelope<OrderPlacedV1> toEnvelope(
            OrderPlaced event
    ) {
        return new IntegrationEventEnvelope<>(
                event.eventId(),
                "OrderPlaced",
                1,
                toIntegrationEvent(event)
        );
    }
}
~~~

Publisher dùng envelope để mang event ID ổn định và phiên bản contract, còn payload mapper chỉ chuyển dữ liệu miền sang schema công khai. Test mapping:

~~~java
@Test
void mapsDomainEventToPublishedContract() {
    OrderPlaced domainEvent = sampleOrderPlaced();

    OrderPlacedV1 integrationEvent =
            mapper.toIntegrationEvent(domainEvent);

    assertEquals("order-123", integrationEvent.orderId());
    assertEquals("1250000", integrationEvent.totalAmount());
    assertEquals("VND", integrationEvent.currency());
    assertEquals(1, integrationEvent.lines().size());
    assertEquals("SKU-001", integrationEvent.lines().get(0).productReference());
}
~~~

~~~java
@Test
void wrapsPayloadWithStableEventMetadata() {
    OrderPlaced domainEvent = sampleOrderPlaced();

    IntegrationEventEnvelope<OrderPlacedV1> envelope =
            mapper.toEnvelope(domainEvent);

    assertEquals(domainEvent.eventId(), envelope.eventId());
    assertEquals("OrderPlaced", envelope.eventType());
    assertEquals(1, envelope.schemaVersion());
    assertEquals("order-123", envelope.payload().orderId());
}
~~~

Test nên xác nhận đơn vị, format và ngữ nghĩa, không chỉ xác nhận các field được copy.

### 6.3. Kiểm thử serialization

~~~java
@Test
void serializesOrderPlacedAccordingToContract() throws Exception {
    OrderPlacedV1 event = sampleOrderPlacedV1();

    String json = objectMapper.writeValueAsString(event);
    JsonNode root = objectMapper.readTree(json);

    assertEquals("order-123", root.get("orderId").asText());
    assertEquals("VND", root.get("currency").asText());
    assertTrue(root.hasNonNull("lines"));
}
~~~

Nếu sử dụng JSON Schema, Avro, Protobuf hoặc AsyncAPI, hãy validate message được serialize bằng đúng schema/version được công bố. Cần kiểm tra serializer thực tế và cấu hình naming, date/time, decimal, enum.

## 7. Kiểm thử consumer

Consumer thường gồm adapter nhận message, mapper/ACL, Application Service và Domain Model. Không nên chỉ test rằng listener được gọi.

Một test consumer có thể xác nhận:

- Message hợp lệ được deserialize.
- Contract được chuyển thành command đúng.
- ID và đơn vị được map chính xác.
- Application gọi đúng hành vi.
- Aggregate giữ bất biến.
- Duplicate hoặc event không hợp lệ được xử lý theo policy.

### 7.1. Test mapping Integration Event sang command

~~~java
public record ReservationLine(
        String productReference,
        int quantity
) {}

public record ReserveInventoryCommand(
        OrderReference orderReference,
        List<ReservationLine> lines,
        Instant orderPlacedAt
) {}
~~~

ACL chuyển contract sang kiểu cục bộ:

~~~java
public final class InventoryOrderEventMapper {
    public ReserveInventoryCommand toCommand(OrderPlacedV1 event) {
        return new ReserveInventoryCommand(
                new OrderReference(event.orderId()),
                event.lines().stream()
                        .map(line -> new ReservationLine(
                                line.productReference(),
                                line.quantity()
                        ))
                        .toList(),
                event.occurredAt()
        );
    }
}
~~~

Consumer có thể dùng ProductLine hoặc các dữ liệu khác phù hợp hơn cho việc giữ hàng; ví dụ trên chỉ minh họa cách chuyển contract sang kiểu miền của Inventory.

Test mapper cần kiểm tra định danh và các dòng hàng được chuyển đổi:

~~~java
@Test
void mapsExternalOrderEventToInventoryCommand() {
    ReserveInventoryCommand command =
            mapper.toCommand(sampleOrderPlacedV1());

    assertEquals("order-123", command.orderReference().value());
    assertEquals(
            List.of(new ReservationLine("SKU-001", 2)),
            command.lines()
    );
}
~~~

### 7.2. Test consumer không phụ thuộc broker

Một test gọi trực tiếp application handler hoặc message handler bằng event fixture có thể kiểm tra mapping và nghiệp vụ mà không cần Kafka/RabbitMQ.

~~~java
@Test
void handlesOrderPlacedEvent() {
    OrderPlacedV1 event = sampleOrderPlacedV1();

    orderPlacedHandler.handle(event);

    verify(reservationService).reserve(
            argThat(command ->
                    command.orderReference().value().equals("order-123")
            )
    );
}
~~~

Test này kiểm tra consumer adapter gọi đúng use case. Nó chưa chứng minh cấu hình broker, serializer, consumer group hoặc transaction thực tế hoạt động; những phần đó cần integration test riêng.

## 8. Consumer-driven contract testing

Trong mô hình Consumer-Driven Contract (CDC), consumer mô tả những tương tác và phần dữ liệu mà nó cần. Producer xác minh rằng message của mình đáp ứng các kỳ vọng đó.

Luồng khái quát:

~~~mermaid
flowchart TD
    C[Consumer test định nghĩa expectation] --> K[Contract được lưu/chia sẻ]
    K --> P[Producer verification]
    P --> R{Contract hợp lệ?}
    R -->|Có| G[Cho phép triển khai theo policy]
    R -->|Không| F[Phát hiện breaking change]
~~~

CDC hữu ích khi nhiều consumer độc lập sử dụng cùng một event. Nó giúp producer biết consumer đang phụ thuộc vào phần nào của contract.

### 8.1. Consumer chỉ khai báo điều nó cần

Ví dụ Inventory cần:

- eventType là OrderPlaced.
- orderId là định danh đơn.
- lines chứa productReference và quantity.
- quantity lớn hơn 0.

Inventory không cần phụ thuộc vào:

- Tên người mua để hiển thị.
- Email marketing.
- Ngôn ngữ giao diện.
- Metadata nội bộ của Order Management.

Contract test nên tập trung vào những trường có ảnh hưởng tới consumer.

### 8.2. Producer verification

Producer chạy verification với contract của consumer để bảo đảm message được tạo ra thỏa kỳ vọng. Nếu producer đổi field bắt buộc, đổi kiểu hoặc bỏ một giá trị mà consumer cần, verification sẽ thất bại trước khi phát hành.

CDC không thay thế schema governance. Một contract chung vẫn cần owner, version, chính sách tương thích và quy trình deprecation.

### 8.3. CDC không nên biến consumer thành người sở hữu producer

Consumer có thể yêu cầu dữ liệu cần thiết cho use case của nó, nhưng producer vẫn sở hữu ngữ nghĩa và quyết định dữ liệu nào được công bố. Nếu nhiều consumer có yêu cầu xung đột, cần thảo luận contract thay vì thêm mọi field vào event.

## 9. Kiểm thử schema và schema evolution

Integration Event là hợp đồng có vòng đời. Schema sẽ thay đổi khi nghiệp vụ và consumer tiến hóa.

Một thay đổi có thể tương thích:

- Thêm field optional có default hoặc quy ước xử lý rõ.
- Thêm metadata không ảnh hưởng consumer cũ.
- Thêm một field mà consumer cũ bỏ qua được.

Một thay đổi thường phá vỡ tương thích:

- Xóa field bắt buộc.
- Đổi tên field.
- Đổi kiểu dữ liệu.
- Đổi đơn vị hoặc ý nghĩa field.
- Thay đổi enum khiến consumer cũ không thể parse.
- Chuyển field optional thành bắt buộc mà không có migration.

Tính tương thích còn phụ thuộc format và serializer. Không nên kết luận một thay đổi an toàn chỉ dựa trên việc JSON parser vẫn chạy.

### 9.1. Backward compatibility

Backward compatibility thường có nghĩa consumer mới có thể đọc message cũ. Ví dụ consumer version 2 vẫn đọc event schema version 1.

### 9.2. Forward compatibility

Forward compatibility thường có nghĩa consumer cũ có thể xử lý message mới trong giới hạn đã thống nhất, chẳng hạn bỏ qua field chưa biết. Điều này không đảm bảo nếu consumer dùng strict enum parsing hoặc yêu cầu tất cả field.

### 9.3. Full compatibility

Một số schema registry hoặc quy trình governance kiểm tra cả hai chiều. Cần thống nhất định nghĩa tương thích theo format, registry và cách triển khai của tổ chức.

### 9.4. Kiểm thử tương thích

Một bộ kiểm thử schema evolution có thể gồm:

| Consumer | Producer schema | Kỳ vọng |
|---|---|---|
| Consumer v1 | Event v1 | PASS |
| Consumer v2 | Event v1 | PASS nếu hỗ trợ dữ liệu cũ |
| Consumer v1 | Event v2 | PASS chỉ khi forward-compatible theo contract |
| Consumer v2 | Event v2 | PASS |
| Consumer v1 | Event v3 breaking | FAIL hoặc cần version route riêng |

Hãy lưu một số message fixture đại diện cho các schema đã phát hành và chạy chúng qua consumer mới. Đây là cách phát hiện lỗi khi code consumer thay đổi.

## 10. Versioning Integration Event

Khi schema thay đổi không tương thích, cần một chiến lược version rõ ràng.

Có thể version trong tên type:

~~~text
OrderPlaced.v1
OrderPlaced.v2
~~~

Hoặc trong envelope:

~~~json
{
  "eventType": "OrderPlaced",
  "schemaVersion": 2,
  "payload": {}
}
~~~

Không có cách đặt version duy nhất. Điều quan trọng là consumer biết cách chọn decoder và producer biết phiên bản nào đang được hỗ trợ.

### 10.1. Tăng version không tự giải quyết semantic change

Nếu field totalAmount đổi từ “tổng trước thuế” sang “tổng sau thuế”, việc đổi schemaVersion không đủ. Contract phải mô tả rõ ý nghĩa mới, consumer cần xác nhận nó phù hợp với use case và có thể cần event type mới để tránh hiểu sai.

### 10.2. Không sửa ý nghĩa event cũ

Event đã phát hành là một phần lịch sử giao tiếp. Nếu ý nghĩa nghiệp vụ thay đổi, hãy tạo contract mới hoặc event mới. Đừng âm thầm thay cách diễn giải của event cũ vì message cũ có thể được replay trong tương lai.

## 11. Kiểm thử null, optional và enum

Một số lỗi contract xuất hiện ở các giá trị biên:

- Field không có mặt.
- Field có giá trị null.
- Field là chuỗi rỗng.
- Field chứa enum value chưa biết.
- Danh sách rỗng.
- Decimal có scale khác dự kiến.
- Timestamp có timezone khác.

Contract phải nói rõ sự khác nhau giữa “không có field”, “field null” và “field có giá trị mặc định”.

Consumer cần có chiến lược với enum mới. Nếu enum là trạng thái nghiệp vụ quan trọng, không nên tự động map giá trị lạ thành trạng thái mặc định có thể gây side effect. Có thể reject, quarantine hoặc xử lý theo policy tương thích.

## 12. Kiểm thử Outbox ở producer

Transactional Outbox giúp bảo đảm thay đổi dữ liệu nghiệp vụ và bản ghi message được ghi trong cùng local database transaction.

~~~mermaid
flowchart TD
    A[Place Order use case] --> T[Local DB transaction]
    T --> O[Save Order]
    T --> B[Insert Outbox message]
    O --> C[Commit]
    B --> C
    C --> P[Outbox Publisher]
    P --> M[(Message Broker)]
~~~

Các test quan trọng:

- Khi Order commit thành công, outbox record được tạo.
- Khi transaction rollback, outbox record không được commit.
- Publisher lấy record pending và publish đúng payload.
- Khi publish thành công, record được đánh dấu theo policy.
- Nếu publisher crash sau khi broker nhận message nhưng trước khi đánh dấu published, message có thể được publish lại; consumer phải idempotent.

### 12.1. Test rollback

~~~java
@Test
void orderAndOutboxAreRolledBackTogether() {
    assertThrows(
            RuntimeException.class,
            () -> placeOrderService.handle(commandThatFailsBeforeCommit())
    );

    assertThat(orderJpaRepository.findAll()).isEmpty();
    assertThat(outboxJpaRepository.findAll()).isEmpty();
}
~~~

Test này cần chạy trong transaction integration test với database phù hợp. Một mock repository không chứng minh được tính nguyên tử của transaction.

### 12.2. Test publisher redelivery

Giả lập publisher publish thành công nhưng chưa ghi nhận trạng thái published. Khi publisher chạy lại, event có thể được gửi lại với cùng eventId. Test nên xác nhận eventId không bị tạo mới cho mỗi lần retry.

## 13. Kiểm thử Inbox và idempotency ở consumer

Inbox lưu dấu vết message đã xử lý. Khi cùng event được giao lại, consumer có thể phát hiện duplicate và không lặp side effect.

Một transaction consumer điển hình:

~~~text
BEGIN
  insert inbox(consumer, eventId)
  apply local domain change
  save local state
COMMIT
ACK broker message
~~~

Các test quan trọng:

- Cùng eventId được giao hai lần chỉ tạo một side effect cục bộ.
- Hai consumer độc lập có thể xử lý cùng event nếu mỗi consumer có inbox riêng.
- Nếu domain update thất bại, inbox record rollback để message có thể retry.
- Nếu commit thành công nhưng ACK thất bại, lần giao lại bị nhận diện duplicate.
- Event có eventId khác nhưng cùng business key vẫn phải bảo vệ bất biến nghiệp vụ.

### 13.1. Kiểm thử bằng database thật

Unique constraint của Inbox và transaction behavior cần được kiểm tra với database engine tương thích môi trường triển khai. Mock không tái hiện đầy đủ race condition hoặc unique constraint.

## 14. Kiểm thử duplicate, retry và out-of-order

Một contract event thường phải nói rõ các thuộc tính metadata cần thiết để consumer phát hiện duplicate hoặc ordering:

- eventId ổn định.
- aggregateId hoặc business key.
- aggregateVersion nếu thứ tự trong aggregate có ý nghĩa.
- occurredAt để hiểu thời điểm nghiệp vụ.
- correlationId và causationId để truy vết.

Các test:

| Kịch bản | Kỳ vọng |
|---|---|
| Cùng eventId được giao hai lần | Side effect chỉ xảy ra một lần |
| Version cũ đến sau | Bỏ qua hoặc xử lý theo policy |
| Version mới đến trước version cũ | Buffer, retry hoặc cập nhật snapshot theo policy |
| Thiếu version ở giữa | Phát hiện gap và có đường phục hồi |
| Retry sau timeout | Không tạo side effect kép |
| Cùng business key nhưng eventId khác | Bất biến nghiệp vụ vẫn được bảo vệ |

Không phải consumer nào cũng cần xử lý tuần tự. Ví dụ audit log có thể chấp nhận out-of-order; projection trạng thái cuối có thể bỏ event cũ; Inventory reservation có thể cần ordering theo Order. Test phải phản ánh yêu cầu thực tế của consumer.

## 15. Kiểm thử ACL và mapping giữa hai ngôn ngữ

Anti-Corruption Layer chuyển Integration Event sang command hoặc mô hình cục bộ. Đây là nơi dễ xảy ra lỗi ngữ nghĩa:

- External status được map nhầm sang internal status.
- External amount được hiểu sai currency.
- Một event cancellation bị map thành refund.
- Product reference của producer bị dùng như ProductId nội bộ mà chưa tra cứu/ánh xạ.

Test ACL nên có fixture thể hiện các trường hợp:

- Event hợp lệ.
- Field optional vắng mặt.
- Giá trị enum chưa biết.
- Currency không được hỗ trợ.
- ID không hợp lệ.
- Schema version cũ.

ACL nên chuyển lỗi không thể hiểu thành một lỗi tích hợp có thể quan sát, không được âm thầm thay giá trị thành default nguy hiểm.

## 16. Kiểm thử message broker và adapter

Unit test không cần broker thật. Tuy nhiên, cần integration test cho những phần phụ thuộc vào broker:

- Topic/queue name và routing key.
- Serialization/deserialization thực tế.
- Consumer group và subscription.
- Header và metadata.
- Acknowledgement mode.
- Retry/backoff và dead-letter routing.
- Transaction hoặc offset commit nếu có.

Với Spring Boot, có thể kiểm tra listener và publisher bằng test support của broker hoặc Testcontainers. Chọn cách phù hợp với broker thật mà hệ thống sử dụng.

### 16.1. Test với broker container

Một integration test có thể:

1. Khởi động broker container.
2. Khởi động producer adapter và consumer adapter trong test context.
3. Gửi event đã serialize.
4. Chờ consumer xử lý bằng Awaitility hoặc cơ chế đồng bộ phù hợp.
5. Xác nhận trạng thái local hoặc side effect.
6. Dọn dữ liệu và container sau test.

Không nên dùng sleep cố định dài để đợi message nếu có thể dùng điều kiện chờ có timeout. Test bất đồng bộ cần timeout rõ ràng để tránh treo pipeline.

### 16.2. Test không nên phụ thuộc thứ tự toàn cục

Broker có thể bảo đảm thứ tự trong một partition hoặc một queue theo cấu hình, nhưng không nên giả định có thứ tự toàn cục giữa nhiều partition, topic hoặc producer. Test cần xác định ordering domain và key thực tế.

## 17. Kiểm thử contract với message fixture đã phát hành

Lưu một tập message mẫu đại diện cho các phiên bản contract được hỗ trợ:

~~~text
contracts/
  order-placed/
    v1/
      basic-order.json
      order-with-discount.json
    v2/
      basic-order.json
  order-cancelled/
    v1/
      customer-cancelled.json
      system-cancelled.json
~~~

Các fixture này giúp:

- Kiểm tra consumer mới đọc được message cũ.
- Kiểm tra producer không vô tình đổi format.
- Làm ví dụ rõ ràng cho đội tích hợp.
- Hỗ trợ replay và điều tra lỗi.

Fixture không nên trở thành dữ liệu mẫu tùy tiện. Mỗi file cần gắn với event type, schema version, ý nghĩa tình huống và nguồn tạo. Tránh đưa dữ liệu cá nhân hoặc bí mật production vào repository.

## 18. Kiểm thử event replay và rebuild projection

Một số consumer là read projection có thể được rebuild bằng cách replay event. Cần test:

- Replay cùng tập event tạo ra cùng kết quả projection.
- Replay không gây side effect ngoài ý muốn như gửi email hoặc thu tiền lần nữa.
- Consumer có thể bắt đầu từ checkpoint hoặc snapshot hợp lệ.
- Event schema cũ vẫn được giải mã hoặc được chuyển đổi qua upcaster.
- Replay nhiều lần không làm tăng tổng tiền hoặc số lượng sai.

Projection handler nên tách khỏi side effect không idempotent. Nếu cùng một handler vừa cập nhật read model vừa gửi email, replay có thể gửi email nhiều lần.

## 19. Kiểm thử Dead Letter và poison message

Một message sai schema hoặc vi phạm contract không nên bị retry vô hạn.

Test cần xác nhận:

- Lỗi tạm thời được retry theo policy.
- Lỗi không thể phục hồi được đưa vào DLQ hoặc quarantine.
- Message gốc, eventId, lỗi và metadata được giữ để điều tra.
- Alert/metric được ghi nhận.
- Reprocess sau khi sửa lỗi không tạo duplicate side effect.

Không phải mọi out-of-order event đều là poison message. Nếu thiếu version trước, consumer có thể chờ, yêu cầu replay hoặc xử lý theo policy thay vì đưa ngay vào DLQ.

## 20. Kiểm thử tính bảo mật của contract

Integration Event có thể đi qua broker, log, tracing và nhiều hệ thống. Contract test nên xem xét:

- Không phát mật khẩu, token, secret hoặc dữ liệu xác thực.
- Chỉ công bố dữ liệu cá nhân cần thiết cho consumer.
- Có chính sách masking/redaction trong log.
- Consumer kiểm tra quyền và ownership ở context của mình.
- Không tin event chỉ vì nó đến từ broker; cần xác thực producer hoặc bảo vệ kênh theo kiến trúc.
- Message có thể được truy vết nhưng không lộ payload nhạy cảm.

Một event hợp lệ về schema vẫn có thể vi phạm chính sách dữ liệu nếu chứa thông tin không cần thiết.

## 21. Consumer contract và nhiều consumer

Một event có thể được nhiều context tiêu thụ:

~~~mermaid
flowchart TD
    P[Order Management] --> T[(OrderPlaced)]
    T --> I[Inventory]
    T --> Pay[Payment]
    T --> N[Notification]
    T --> A[Analytics]
~~~

Mỗi consumer có nhu cầu khác nhau:

| Consumer | Dữ liệu có thể cần |
|---|---|
| Inventory | Product reference, quantity, fulfillment location |
| Payment | Order reference, amount, currency, payment terms |
| Notification | Customer contact reference, locale, order summary |
| Analytics | Event time, category, amount, channel |

Không nên làm event quá lớn để đáp ứng mọi nhu cầu. Cần xác định contract cốt lõi, event chuyên biệt hoặc query/API phù hợp. Dữ liệu nhạy cảm cũng không nên phát rộng chỉ vì một consumer cần.

### 21.1. Khi consumer cần thêm dữ liệu

Có thể:

- Bổ sung field optional nếu phù hợp và tương thích.
- Tạo event chuyên biệt cho use case.
- Cho consumer truy vấn một API/read model theo quyền.
- Dùng reference để consumer lấy dữ liệu authoritative.

Quyết định cần dựa trên coupling, latency, consistency và ownership. Không nên thêm field vào event mà không xem xét tất cả consumer hiện có.

## 22. Kiểm thử tính nhất quán giữa event và source of truth

Event nên phản ánh thay đổi đã commit theo contract. Một consumer không nên nhận event nói OrderPlaced trong khi Order transaction đã rollback.

Kiểm thử cần bao phủ:

- Event chỉ được publish sau khi local transaction commit.
- Payload phản ánh snapshot hoặc dữ kiện theo định nghĩa contract.
- Event version phù hợp với aggregate version nếu contract yêu cầu.
- Consumer không coi event là nguồn sự thật cho dữ liệu mà context khác sở hữu.
- Khi cần dữ liệu authoritative mới nhất, consumer truy vấn qua contract/API phù hợp.

Outbox giúp gắn local state change với message record. Nó không tạo distributed transaction giữa producer và consumer; consumer vẫn xử lý eventual consistency.

## 23. Contract test trong CI/CD

Một pipeline tích hợp có thể có các bước:

~~~mermaid
flowchart TD
    A[Build producer/consumer] --> B[Unit và mapping tests]
    B --> C[Schema validation]
    C --> D[Consumer contract verification]
    D --> E[Producer contract verification]
    E --> F[Persistence/adapter integration tests]
    F --> G[Broker integration tests]
    G --> H[Compatibility report]
    H --> I{Tương thích?}
    I -->|Có| J[Cho phép bước release tiếp theo]
    I -->|Không| K[Chặn và yêu cầu xử lý contract]
~~~

Không phải pipeline nào cũng cần chạy mọi integration test cho từng commit. Có thể phân tầng:

- Mỗi commit: unit, mapping, schema và contract test nhanh.
- Pull request hoặc merge: database/broker integration test phù hợp.
- Trước release: compatibility verification với các contract version đang hỗ trợ.
- Sau deploy: smoke test và monitoring event flow.

CI nên lưu kết quả contract verification để nhóm biết consumer nào bị ảnh hưởng bởi thay đổi.

## 24. Kiểm thử contract khi triển khai độc lập

Khi producer và consumer release độc lập, cần tránh kiểm tra chỉ với code của cùng một commit.

Một quy trình hữu ích:

1. Consumer công bố contract expectation và version.
2. Producer verification chạy với các contract consumer đang hỗ trợ.
3. Kết quả được lưu cùng build/version.
4. Deployment policy kiểm tra tổ hợp producer-consumer được phép.
5. Consumer mới được deploy khi producer version tương thích đã có hoặc được bảo đảm.
6. Producer chỉ loại bỏ contract cũ sau khi consumer cũ đã ngừng sử dụng theo quy trình deprecation.

Điều này giúp giảm tình trạng “producer đã deploy nhưng consumer chưa sẵn sàng”.

## 25. Test chiến lược deprecation

Khi muốn bỏ một field hoặc event version:

- Đánh dấu deprecated trong tài liệu contract.
- Theo dõi consumer nào còn sử dụng.
- Cung cấp thời gian chuyển đổi.
- Phát hành consumer tương thích trước.
- Chỉ xóa field/version khi không còn consumer phụ thuộc hoặc đã có migration được phê duyệt.

Test có thể xác nhận producer mới vẫn phát field cũ trong giai đoạn chuyển tiếp và consumer mới hiểu cả hai dạng. Sau khi bỏ, compatibility suite phải phản ánh đúng tập version còn được hỗ trợ.

## 26. Phân biệt contract test, integration test và end-to-end test

| Loại test | Phạm vi | Điều chứng minh |
|---|---|---|
| Unit test | Mapper, policy, handler nhỏ | Logic cục bộ đúng |
| Schema test | Message so với schema | Cấu trúc đúng |
| Consumer contract test | Consumer so với expectation | Consumer chỉ phụ thuộc contract đã khai báo |
| Producer contract test | Message producer so với contract | Producer phát đúng điều đã cam kết |
| Adapter integration test | Spring/JPA/broker adapter | Cấu hình và chuyển đổi thực tế hoạt động |
| Cross-context integration test | Hai ứng dụng hoặc adapter thật | Luồng message thực tế đi qua được |
| End-to-end test | Một hành trình nghiệp vụ qua nhiều context | Hành vi tổng thể của một số kịch bản quan trọng |

Không nên dùng một loại test để thay thế tất cả. Contract test nhanh và tập trung hơn E2E; E2E vẫn cần cho một số luồng quan trọng nhưng không nên là cách duy nhất để phát hiện mọi lỗi mapping.

## 27. Một ví dụ kiểm thử contract với Spring

Giả sử Inventory có listener nhận OrderPlacedV1:

~~~java
@Component
public class OrderPlacedListener {
    private final InventoryOrderHandler handler;

    public OrderPlacedListener(InventoryOrderHandler handler) {
        this.handler = handler;
    }

    @KafkaListener(topics = "order-placed")
    public void onMessage(OrderPlacedV1 event) {
        handler.handle(event);
    }
}
~~~

Test handler bằng fixture:

~~~java
@Test
void consumesPublishedOrderPlacedContract() {
    InventoryOrderHandler handler = mock(InventoryOrderHandler.class);
    OrderPlacedListener listener = new OrderPlacedListener(handler);
    OrderPlacedV1 event = new OrderPlacedV1(
            "order-123",
            Instant.parse("2026-11-18T10:15:00Z"),
            "1250000",
            "VND",
            List.of(new OrderLineV1("SKU-001", 2))
    );

    listener.onMessage(event);

    verify(handler).handle(event);
}
~~~

Test này xác nhận wiring ở mức gọi method, chưa xác nhận Kafka deserializer. Một test serialization/deserialization riêng có thể dùng ObjectMapper hoặc serializer cấu hình thật:

~~~java
@Test
void roundTripsOrderPlacedMessage() throws Exception {
    OrderPlacedV1 original = sampleOrderPlacedV1();

    byte[] bytes = objectMapper.writeValueAsBytes(original);
    OrderPlacedV1 restored =
            objectMapper.readValue(bytes, OrderPlacedV1.class);

    assertEquals(original, restored);
}
~~~

Với record chứa List hoặc nested object, test equality cần xác nhận toàn bộ payload. Nếu dùng Avro/Protobuf hoặc serializer riêng, test phải chạy qua serializer đó thay vì thay thế bằng Jackson.

## 28. Những sai lầm thường gặp

### Chỉ kiểm tra JSON parse được

Message có thể parse nhưng sai đơn vị, ý nghĩa hoặc thời điểm nghiệp vụ. Hãy kiểm tra semantic contract.

### Chỉ test producer hoặc chỉ test consumer

Producer có thể phát đúng schema nhưng consumer map sai; consumer có thể đúng với fixture nhưng producer thực tế phát field khác. Cần xác minh cả hai phía.

### Dùng Domain Event nội bộ làm public contract

Thay đổi nội bộ có thể vô tình phá consumer. Hãy tạo Integration Event có schema và ownership rõ.

### Chia sẻ một Java class giữa producer và consumer

Shared library có thể che giấu lỗi serialization/version và tạo coupling build-time. Dùng contract schema/fixture và kiểm thử tương thích độc lập.

### Chỉ chạy E2E

E2E chậm, khó chẩn đoán và có thể không bao phủ mọi schema version. Bổ sung contract và adapter test.

### Bỏ qua event cũ

Consumer mới có thể cần replay message cũ. Giữ fixture cho các version được hỗ trợ.

### Không test duplicate và retry

Message broker có thể giao lại. Consumer cần idempotency và test crash/retry.

### Thay đổi ý nghĩa mà không đổi contract

Schema không đổi nhưng semantics đổi vẫn là breaking change. Cần version hoặc event mới và kiểm thử theo nghiệp vụ.

### Đưa dữ liệu nhạy cảm vào event

Event có thể được lưu và chuyển tiếp qua nhiều hệ thống. Chỉ công bố dữ liệu consumer thực sự cần.

### Consumer phụ thuộc mọi field

Điều này làm producer khó tiến hóa. Consumer chỉ nên yêu cầu phần contract cần cho use case.

## 29. Quy trình thiết kế và kiểm thử contract

Khi tạo một Integration Event mới:

1. Xác định producer và owner của ngữ nghĩa event.
2. Xác định consumer và use case mà event phục vụ.
3. Đặt tên event theo điều đã xảy ra.
4. Định nghĩa envelope, payload, field meaning, unit và nullability.
5. Xác định event ID, aggregate ID/version, correlation và causation nếu cần.
6. Viết schema/contract và ví dụ message.
7. Viết consumer test với fixture.
8. Viết producer mapping và serialization test.
9. Xác minh compatibility với schema/version được hỗ trợ.
10. Kiểm thử Outbox, Inbox, retry, duplicate và ordering theo nhu cầu.
11. Chạy adapter/broker integration test.
12. Công bố contract, owner và chính sách deprecation.
13. Theo dõi metrics và lỗi contract sau triển khai.

## 30. Checklist

- [ ] Event có tên và ý nghĩa nghiệp vụ rõ ràng.
- [ ] Producer và owner của contract được xác định.
- [ ] Domain Event nội bộ được phân biệt với Integration Event.
- [ ] Envelope có event ID ổn định và metadata cần thiết.
- [ ] Field có kiểu, đơn vị, nullability và semantics rõ.
- [ ] Consumer chỉ phụ thuộc vào dữ liệu cần cho use case.
- [ ] Có schema validation và semantic contract test.
- [ ] Producer test xác nhận điều kiện phát, mapping và serialization.
- [ ] Consumer test xác nhận deserialization, ACL và hành vi.
- [ ] Có fixture cho các contract version còn hỗ trợ.
- [ ] Schema evolution có compatibility policy.
- [ ] Breaking semantic change được version hoặc phát event mới.
- [ ] Outbox được test cùng transaction của producer.
- [ ] Inbox, duplicate và retry được test ở consumer.
- [ ] Ordering/gap được kiểm thử nếu use case yêu cầu.
- [ ] Broker adapter, routing, acknowledgement và DLQ có integration test.
- [ ] Replay không lặp side effect ngoài ý muốn.
- [ ] Event không chứa dữ liệu nhạy cảm không cần thiết.
- [ ] CI xác minh producer-consumer compatibility.
- [ ] Có owner, deprecation policy và monitoring cho contract.

## 31. Kết luận

Kiểm thử sự kiện và hợp đồng tích hợp xuyên ngữ cảnh bảo vệ cam kết giao tiếp giữa các Bounded Context độc lập. Producer cần chứng minh nó phát đúng sự kiện, đúng schema và đúng ngữ nghĩa sau khi thay đổi nghiệp vụ được commit. Consumer cần chứng minh nó hiểu contract, chuyển dữ liệu qua ACL và bảo vệ bất biến của mô hình cục bộ.

Một chiến lược đáng tin cậy kết hợp schema validation, semantic contract test, consumer-driven contract, producer verification, fixture cho schema cũ, kiểm thử Outbox/Inbox, retry, duplicate, ordering và adapter broker thực tế. End-to-end test vẫn có vai trò với những hành trình quan trọng, nhưng không thể thay thế các kiểm tra tập trung ở từng ranh giới.

Khi contract có owner, version, chính sách tương thích và bộ test chạy trong CI/CD, các context có thể tiến hóa độc lập hơn mà vẫn phát hiện sớm thay đổi phá vỡ tích hợp. Đó là mục tiêu của kiểm thử trong DDD: bảo vệ ngôn ngữ và cam kết giữa các mô hình, không chỉ xác nhận message đã đi qua broker.
