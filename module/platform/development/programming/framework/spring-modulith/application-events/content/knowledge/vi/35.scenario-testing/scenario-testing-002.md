# Given event

Trong kiểm thử theo kịch bản (scenario testing), **Given event** là sự kiện đầu vào được chuẩn bị để mô phỏng một tình huống nghiệp vụ. Nó xác định điều gì đã xảy ra trước khi phần hệ thống đang kiểm thử phản ứng. Từ event này, test quan sát listener, module hoặc process manager thực hiện hành động nào và phát ra kết quả gì.

Ví dụ, khi kiểm thử module Kho phản ứng với **OrderPlaced**, Given event chính là một event OrderPlaced hợp lệ. Test chuẩn bị tồn kho ban đầu, phát event, chờ **InventoryReserved** hoặc **InventoryRejected**, rồi xác minh cả event kết quả lẫn trạng thái reservation.

Trong Spring Modulith, application events là ranh giới giao tiếp giữa các module. Scenario testing giúp kiểm tra chuỗi phản ứng thực tế, kể cả listener bất đồng bộ. Given event cần có dữ liệu rõ ràng, định danh ổn định và trạng thái nền phù hợp để kết quả test phản ánh đúng hành vi nghiệp vụ.

## 1. Given event trong cấu trúc Given–When–Then

Một scenario thường được tổ chức theo ba phần:

- **Given:** chuẩn bị dữ liệu, trạng thái ban đầu và event đầu vào.
- **When:** kích hoạt hành động hoặc phát event để bắt đầu kịch bản.
- **Then:** chờ và xác minh event đầu ra, thay đổi trạng thái hoặc side effect mong đợi.

Ví dụ với luồng đặt hàng:

~~~text
GIVEN:
  Kho có 5 sản phẩm SKU-42
  Đơn hàng ORD-100 yêu cầu 2 sản phẩm
  Event OrderPlaced có eventId và orderId xác định

WHEN:
  Event OrderPlaced được publish

THEN:
  InventoryReserved được phát cho ORD-100
  Reservation chứa đúng 2 sản phẩm
  Số lượng có thể bán giảm từ 5 xuống 3
~~~

Given event mô tả đầu vào của scenario, không phải kết quả mà test đang chờ. Hãy phân biệt event khởi đầu với event kết quả để test không vô tình xác minh chính dữ liệu mà nó vừa gửi.

Một test tốt đọc được như một câu chuyện nghiệp vụ. Người review cần nhìn thấy trạng thái ban đầu, sự kiện kích hoạt và kết quả cần đạt mà không phải lần theo quá nhiều chi tiết mock.

## 2. Chọn event đầu vào đúng với hành vi cần kiểm thử

Event được chọn làm Given phải là tín hiệu mà module thực sự có trách nhiệm tiếp nhận. Không nên phát một event bất kỳ chỉ để kích hoạt code nội bộ.

Ví dụ:

| Module được kiểm thử | Given event | Hành vi cần quan sát |
|---|---|---|
| Kho | OrderPlaced | Giữ hàng hoặc từ chối do thiếu tồn |
| Thanh toán | InventoryReserved | Ủy quyền thanh toán |
| Giao hàng | PaymentAuthorized | Tạo yêu cầu giao hàng |
| Thông báo | OrderConfirmed | Tạo thông báo cho khách |
| Process manager | PaymentDeclined | Bắt đầu nhánh hủy và compensation |

Event cần đúng schema và mang các trường cần thiết cho listener. Nếu listener dùng orderId, sagaId, occurredAt hoặc version để quyết định, fixture phải cung cấp giá trị có ý nghĩa cho những trường đó.

Không nên dùng event giả thiếu trường rồi bổ sung mock ở sâu trong listener. Test như vậy không phản ánh hợp đồng event thật và có thể bỏ qua lỗi mapping hoặc validation.

## 3. Chuẩn bị trạng thái nền trước Given event

Event thường chỉ có ý nghĩa trong một trạng thái nghiệp vụ cụ thể. Trước khi phát event, hãy chuẩn bị dữ liệu nền để điều kiện xử lý rõ ràng.

Ví dụ với OrderPlaced, module Kho cần có sản phẩm và số lượng tồn phù hợp. Với PaymentAuthorized, module Giao hàng có thể cần đơn hàng ở trạng thái đã thanh toán và địa chỉ giao hàng hợp lệ.

Các nguyên tắc chuẩn bị:

- Tạo dữ liệu tối thiểu mà listener cần.
- Dùng ID xác định trong từng test để liên kết event với dữ liệu.
- Thiết lập rõ trạng thái ban đầu thay vì dựa vào dữ liệu còn sót từ test trước.
- Tạo các trường hợp biên có chủ đích như tồn kho bằng 0, đơn đã hủy hoặc phiên bản event cũ.
- Commit dữ liệu nền trước khi kích hoạt listener nếu listener chạy trong transaction khác.

Một fixture builder có thể giúp tạo event dễ đọc:

~~~java
final class OrderEvents {

    static OrderPlaced orderPlaced(
            UUID orderId,
            int quantity) {
        return new OrderPlaced(
            UUID.randomUUID(),
            orderId,
            "SKU-42",
            quantity,
            Instant.parse("2026-11-25T10:15:30Z")
        );
    }
}
~~~

Trong test, có thể dùng builder với giá trị xác định:

~~~java
UUID orderId = UUID.fromString(
    "8a4d3e2f-5b6c-4d7e-9f10-123456789abc"
);

inventoryRepository.save(
    InventoryItem.available("SKU-42", 5)
);

OrderPlaced givenEvent =
    OrderEvents.orderPlaced(orderId, 2);
~~~

Event ID có thể được sinh mới trong test nếu không cần so sánh cụ thể, nhưng orderId và các giá trị liên kết nên ổn định để assertion dễ hiểu. Nếu test retry hoặc idempotency, hãy cố định cả event ID để mô phỏng đúng lần giao lặp.

## 4. Phân biệt Given state và Given event

Không phải mọi scenario đều bắt đầu bằng một event. Có test cần Given state rồi gọi command hoặc application service; test khác dùng Given event để mô phỏng một module khác đã phát tín hiệu.

| Cách chuẩn bị | Khi phù hợp | Ví dụ |
|---|---|---|
| Given state | Kiểm thử command hoặc service thay đổi trạng thái | Đơn đang ở trạng thái PENDING |
| Given event | Kiểm thử listener phản ứng với event từ module khác | OrderPlaced được publish tới module Kho |
| Given event history | Kiểm thử process manager ở giữa quy trình | Đã nhận InventoryReserved, đang chờ thanh toán |
| Given external message | Kiểm thử consumer adapter hoặc deserialize | Message JSON được chuyển thành event |

Nếu muốn kiểm thử listener, phát event qua cơ chế application event của Spring hoặc Scenario API thay vì gọi trực tiếp method listener. Việc gọi method trực tiếp bỏ qua event multicaster, transaction phase, async executor và một phần cấu hình mà hệ thống dùng khi chạy thật.

Nếu muốn kiểm thử logic thuần của service, gọi service trực tiếp là phù hợp. Hãy đặt đúng mục tiêu cho mỗi test để biết ranh giới nào đang được bảo vệ.

## 5. Dùng Scenario API của Spring Modulith

Spring Modulith cung cấp Scenario trong test support để viết kịch bản dựa trên application event. API này có thể phát event đầu vào, chờ event kết quả hoặc chờ trạng thái thay đổi mà không cần tự quản lý thread và sleep.

Một ví dụ kiểm thử module Kho:

~~~java
@ApplicationModuleTest
class InventoryScenarioTests {

    @Autowired
    Scenario scenario;

    @Autowired
    InventoryRepository inventoryRepository;

    @Test
    void reservesInventory_whenOrderPlacedEventArrives() {
        UUID orderId = UUID.fromString(
            "8a4d3e2f-5b6c-4d7e-9f10-123456789abc"
        );

        inventoryRepository.save(
            InventoryItem.available("SKU-42", 5)
        );

        OrderPlaced givenEvent = new OrderPlaced(
            UUID.randomUUID(),
            orderId,
            "SKU-42",
            2,
            Instant.parse("2026-11-25T10:15:30Z")
        );

        scenario.publish(givenEvent)
            .andWaitForEventOfType(InventoryReserved.class)
            .toArrive()
            .matchingMappedValue(
                InventoryReserved::orderId,
                orderId
            );
    }
}
~~~

Kịch bản này chuẩn bị trạng thái kho, publish Given event và chờ event InventoryReserved có cùng orderId. Scenario API hữu ích khi listener bất đồng bộ vì test chờ kết quả theo điều kiện thay vì đoán thời gian xử lý.

Các tên phương thức và overload cụ thể cần khớp phiên bản Spring Modulith đang dùng. Hãy dùng API từ dependency test của dự án và giữ assertion tập trung vào event contract. Không tự tạo một executor hoặc thread riêng chỉ để thay thế cơ chế chờ của Scenario.

## 6. Given event và event kết quả

Một scenario thường có ít nhất một event đầu vào và một event kết quả. Assertion nên xác minh loại event, định danh liên kết và các trường quan trọng.

Ví dụ InventoryReserved:

~~~java
public record InventoryReserved(
    UUID eventId,
    UUID orderId,
    String sku,
    int quantity,
    UUID reservationId
) {}
~~~

Những điều nên xác minh:

- Event kết quả có đúng loại mà contract quy định.
- orderId khớp Given event.
- SKU và quantity phản ánh đúng yêu cầu ban đầu.
- reservationId được tạo và không rỗng.
- Không phát event thành công nếu điều kiện nghiệp vụ không được đáp ứng.

Không chỉ assert rằng có một event cùng type. Một listener khác có thể phát cùng loại event cho dữ liệu khác. Luôn lọc theo business ID hoặc correlation ID của scenario.

Nếu event có nhiều trường, ưu tiên assert các trường thuộc hợp đồng và có ý nghĩa nghiệp vụ. Không cần khóa mọi trường kỹ thuật như thứ tự JSON property nếu đó không phải contract.

## 7. Kiểm thử nhánh từ chối với Given event

Một Given event hợp lệ không nhất thiết dẫn đến thành công. Test cần bao phủ cả nhánh từ chối hoặc thất bại nghiệp vụ.

Ví dụ kho chỉ còn một sản phẩm nhưng đơn yêu cầu hai sản phẩm. Given vẫn là OrderPlaced; kết quả mong đợi là InventoryRejected.

~~~java
@Test
void rejectsOrder_whenInventoryIsInsufficient() {
    UUID orderId = UUID.randomUUID();

    inventoryRepository.save(
        InventoryItem.available("SKU-42", 1)
    );

    OrderPlaced givenEvent = new OrderPlaced(
        UUID.randomUUID(),
        orderId,
        "SKU-42",
        2,
        Instant.now()
    );

    scenario.publish(givenEvent)
        .andWaitForEventOfType(InventoryRejected.class)
        .toArrive()
        .matchingMappedValue(
            InventoryRejected::orderId,
            orderId
        );

    assertThat(
        inventoryRepository.availableQuantity("SKU-42")
    ).isEqualTo(1);
}
~~~

Test vừa kiểm tra event kết quả vừa kiểm tra tồn kho không bị trừ. Đây là cách phát hiện listener phát event từ chối nhưng vẫn cập nhật dữ liệu sai, hoặc cập nhật dữ liệu trước khi xác minh điều kiện.

Các nhánh thường nên có:

| Given event / trạng thái nền | Kết quả mong đợi |
|---|---|
| OrderPlaced, đủ tồn | InventoryReserved |
| OrderPlaced, thiếu tồn | InventoryRejected |
| OrderPlaced, SKU không tồn tại | Từ chối theo contract |
| OrderPlaced, event trùng | Không tạo reservation thứ hai |
| OrderPlaced, đơn đã hủy | Bỏ qua hoặc phát kết quả stale theo quy tắc |

## 8. Given event trong quy trình nhiều bước

Với process manager hoặc saga, Given event có thể biểu diễn một điểm giữa của quy trình. Test cần khởi tạo saga state tương ứng rồi phát event để kiểm tra bước tiếp theo.

Ví dụ process manager đang chờ kết quả thanh toán sau khi đã giữ tồn kho. Given event là InventoryReserved; kết quả mong đợi là command ủy quyền thanh toán.

~~~java
@Test
void requestsPayment_whenInventoryWasReserved() {
    UUID sagaId = UUID.randomUUID();
    UUID orderId = UUID.randomUUID();

    sagaRepository.save(
        OrderSaga.waitingForInventory(sagaId, orderId)
    );

    InventoryReserved givenEvent =
        new InventoryReserved(
            UUID.randomUUID(),
            sagaId,
            orderId,
            UUID.randomUUID()
        );

    scenario.publish(givenEvent)
        .andWaitForStateChange(
            () -> sagaRepository.findById(sagaId)
        )
        .andVerify(state ->
            assertThat(state)
                .get()
                .extracting(OrderSaga::state)
                .isEqualTo(SagaState.PAYMENT_PENDING)
        );
}
~~~

Ví dụ minh họa cách dùng trạng thái saga để xác minh phản ứng. API andWaitForStateChange cần được sử dụng theo đúng kiểu trả về và overload của phiên bản Scenario đang có. Nếu lệnh tiếp theo được gửi qua outbox, có thể xác minh outbox record thay vì gọi trực tiếp participant khác.

Khi kiểm thử saga, hãy tạo state trước Given event và kiểm tra đúng chuyển trạng thái. Không khởi tạo saga ở trạng thái PAYMENT_PENDING rồi lại mong event InventoryReserved kích hoạt cùng một chuyển trạng thái; fixture phải phản ánh trạng thái trước khi event đến.

## 9. Event bất đồng bộ và chờ kết quả

Listener bất đồng bộ có thể chạy sau khi publisher đã trả về. Test không nên dùng Thread.sleep() để đợi một khoảng thời gian tùy ý vì máy chậm có thể làm test flaky, còn máy nhanh thì test lãng phí thời gian.

Nên dùng cơ chế chờ theo điều kiện:

- Spring Modulith Scenario để chờ event hoặc state change.
- Awaitility khi test cần chờ một điều kiện bên ngoài Scenario API.
- Đồng bộ hóa test rõ ràng nếu kiểm thử executor hoặc worker riêng.

Ví dụ dùng Awaitility để chờ state:

~~~java
await()
    .atMost(Duration.ofSeconds(5))
    .untilAsserted(() ->
        assertThat(inventoryRepository.findReservation(orderId))
            .isPresent()
    );
~~~

Timeout phải đủ cho môi trường CI nhưng không quá dài để che giấu deadlock hoặc listener bị treo. Khi timeout, assertion nên hiển thị ID của event, module và điều kiện đang chờ để việc điều tra dễ dàng.

Scenario API có thể chờ event type cụ thể; nếu có nhiều event cùng loại, hãy match bằng orderId hoặc sagaId. Không dùng một event bất kỳ đầu tiên làm bằng chứng scenario đã hoàn tất.

## 10. Given event và transaction boundary

Event có thể được publish trong transaction nghiệp vụ nhưng listener được xử lý sau khi transaction commit. Khi kiểm thử, cần phân biệt trạng thái trước commit, sau commit và thời điểm listener thực sự chạy.

Nếu listener yêu cầu dữ liệu đã commit, test phải tạo dữ liệu nền trong transaction đã hoàn tất trước khi phát Given event. Với listener chạy trong transaction riêng, thay đổi từ listener có thể chưa nhìn thấy ngay trong transaction test của publisher.

Không giả định việc publishEvent() trả về đồng nghĩa listener đã xử lý xong. Với async listener, cần chờ event kết quả hoặc state change.

Một số điểm cần kiểm tra:

- Event không được xử lý khi transaction phát event rollback nếu listener được cấu hình chạy sau commit.
- Listener nhìn thấy dữ liệu đã commit theo đúng transaction boundary.
- Exception trong listener không làm test hiểu nhầm transaction phát event đã rollback.
- Publication chưa hoàn tất được giữ trạng thái phù hợp nếu listener thất bại.
- Test cleanup không rollback hoặc xóa dữ liệu trước khi async listener dùng tới.

Với test dùng @Transactional, hãy kiểm tra cách transaction test được commit hoặc rollback. Một test transaction mặc định rollback khi kết thúc có thể khiến listener sau commit không được kích hoạt như mong đợi. Nếu cần kiểm tra after-commit behavior, hãy điều khiển commit rõ ràng theo cách phù hợp với test setup.

## 11. Given event trùng và idempotency

Event có thể được giao lại do retry hoặc phục hồi. Given event trong scenario idempotency nên giữ nguyên event ID qua hai lần publish.

Ví dụ kịch bản:

~~~text
GIVEN:
  Kho có 5 sản phẩm SKU-42
  Event OrderPlaced có eventId = E-100, quantity = 2

WHEN:
  Publish OrderPlaced(E-100)
  Publish lại đúng OrderPlaced(E-100)

THEN:
  Chỉ có một reservation cho orderId
  Số lượng khả dụng còn 3
  Không có reservation thứ hai
~~~

Test cần xác minh side effect và dấu mốc inbox hoặc idempotency store nếu đó là một phần của thiết kế. Không chỉ kiểm tra listener được gọi một hay hai lần; mục tiêu là kết quả nghiệp vụ không bị nhân đôi.

Nếu hai event có event ID khác nhau nhưng cùng đại diện cho một giao dịch nghiệp vụ, cần kiểm tra thêm unique constraint theo business key như paymentTransactionId hoặc orderId tùy contract. Event ID chỉ nhận diện một event, không tự loại được mọi duplicate nghiệp vụ.

## 12. Cô lập scenario và tránh phụ thuộc giữa các test

Mỗi scenario nên độc lập. Một test không được phụ thuộc event hoặc dữ liệu do test khác tạo ra.

Các thực hành hữu ích:

- Dùng business ID riêng cho từng test.
- Chuẩn bị dữ liệu qua repository hoặc fixture factory.
- Xóa dữ liệu hoặc dùng database test cô lập.
- Không chia sẻ mutable event object giữa các test song song.
- Không phụ thuộc thứ tự chạy test.
- Chờ listener hoàn tất trước khi cleanup dữ liệu mà listener cần.
- Đặt timeout rõ ràng cho các bước async.

Nếu test chạy song song, UUID ngẫu nhiên hoặc ID namespace theo test giúp tránh xung đột. Nếu test dùng một queue hoặc broker dùng chung, cần routing key/queue riêng hoặc cơ chế dọn message sau mỗi scenario.

Không mock toàn bộ module đang được kiểm thử. Mock các dependency ngoài ranh giới cần thiết, nhưng giữ listener, event publication và logic nghiệp vụ thật nếu mục tiêu là kiểm tra scenario phản ứng với event.

## 13. Kiểm thử event không mong đợi

Một scenario không chỉ cần xác minh event mong đợi xuất hiện mà còn có thể cần xác minh event không nên phát.

Ví dụ, khi tồn kho không đủ, hệ thống không được phát InventoryReserved. Nếu test chỉ đợi InventoryRejected, một lỗi phát đồng thời cả hai event có thể không bị phát hiện.

Có thể kiểm tra các điều kiện âm:

- Không phát event thành công khi validation thất bại.
- Không tạo side effect lần hai khi Given event trùng.
- Không phát command tiếp theo khi saga đã bị hủy.
- Không phát event từ module không sở hữu hành vi đó.
- Không phát event trước khi transaction commit nếu contract yêu cầu after-commit.

Cách ghi nhận event phụ thuộc test API và cấu hình. Với event đồng bộ, có thể dùng công cụ ghi nhận application events của Spring Test; với async, nên dùng Scenario hoặc cơ chế chờ phù hợp để quan sát trong khoảng thời gian xác định. Không dùng assertion âm tức thời ngay sau publish nếu listener còn có thể chạy bất đồng bộ sau đó.

## 14. Kiểm thử Given event không hợp lệ

Payload không hợp lệ cần có scenario riêng. Các trường hợp có thể gồm event thiếu ID, quantity bằng 0, schema version không hỗ trợ hoặc event tham chiếu entity không tồn tại.

Test nên xác định rõ hệ thống xử lý thế nào:

- Reject hoặc dead-letter message.
- Ghi nhận quarantine có event ID và nguyên nhân.
- Phát event kết quả từ chối nếu contract quy định.
- Không thay đổi dữ liệu nghiệp vụ.
- Không retry vô hạn với lỗi dữ liệu không thể tự sửa.

Không tạo Given event không hợp lệ rồi chỉ assert rằng listener ném exception. Hãy xác minh cả publication/message state hoặc kết quả quarantine nếu đó là trách nhiệm của hệ thống đang kiểm thử.

Với lỗi kỹ thuật tạm thời như timeout, test cần phân biệt với lỗi payload. Lỗi tạm thời có thể được retry; payload sai thường cần cách ly hoặc xử lý thủ công.

## 15. Dữ liệu và thời gian trong Given event

Fixture event cần xác định các trường thời gian và định danh để kết quả có thể tái lập.

- Dùng Instant cố định thay vì Instant.now() khi thời gian không phải nội dung cần kiểm thử.
- Dùng event ID cố định khi kiểm tra duplicate, retry hoặc correlation.
- Dùng business ID riêng cho từng scenario.
- Đặt schema version rõ ràng nếu payload có version.
- Tạo dữ liệu số ở biên như quantity bằng 1, tồn kho bằng 0 hoặc decimal có scale cụ thể.

Nếu logic phụ thuộc thời gian hiện tại, tiêm Clock vào service và dùng clock cố định trong test. Không để test phụ thuộc timezone mặc định của máy phát triển hoặc CI.

Một Given event có dữ liệu ổn định giúp failure dễ tái hiện và làm assertion dễ đọc. Nếu dùng dữ liệu ngẫu nhiên, chỉ ngẫu nhiên những trường không ảnh hưởng điều kiện test và phải in chúng ra khi test thất bại.

## 16. Tổ chức bộ scenario theo hành vi

Thay vì tạo một test rất lớn bao phủ mọi nhánh, hãy chia thành các scenario nhỏ theo kết quả nghiệp vụ:

| Scenario | Given | Then |
|---|---|---|
| Giữ hàng thành công | OrderPlaced, đủ tồn | InventoryReserved và tồn giảm |
| Thiếu hàng | OrderPlaced, thiếu tồn | InventoryRejected, tồn không đổi |
| Event trùng | Cùng OrderPlaced hai lần | Chỉ một reservation |
| Đơn đã hủy | OrderPlaced cho đơn CANCELLED | Không giữ hàng |
| Payload không hợp lệ | OrderPlaced thiếu quantity | Quarantine hoặc reject |
| Saga tiếp tục | InventoryReserved khi saga chờ kho | Payment command được ghi nhận |
| Event đến muộn | InventoryReserved sau khi saga đã hủy | Không khởi động lại luồng thành công |

Tên test nên mô tả hành vi mong đợi, ví dụ reservesInventory_whenOrderPlacedEventArrives hoặc doesNotReserveTwice_whenOrderPlacedIsDeliveredAgain. Tránh tên chung chung như testEvent1.

## 17. Lỗi thường gặp khi viết Given event

**Dùng event kết quả làm event đầu vào.** Test không còn mô tả đúng hành vi đang kiểm tra. Hãy xác định rõ module nhận event nào và event nào là kết quả.

**Không chuẩn bị trạng thái nền.** Kết quả phụ thuộc dữ liệu cũ hoặc test khác. Hãy tạo fixture tối thiểu trong từng scenario.

**Gọi trực tiếp listener method.** Test bỏ qua event dispatch và transaction phase. Hãy publish qua ApplicationEventPublisher hoặc Scenario API khi mục tiêu là kiểm thử ranh giới event.

**Dùng sleep để đợi listener.** Test dễ flaky và chậm. Hãy chờ event hoặc state change bằng Scenario/Awaitility.

**Chỉ kiểm tra event type.** Một event cùng loại có thể thuộc order khác. Hãy match business ID hoặc correlation ID.

**Dùng thời gian và ID ngẫu nhiên không kiểm soát.** Test khó tái hiện. Hãy dùng fixture xác định hoặc Clock có thể kiểm soát.

**Không kiểm tra nhánh từ chối.** Listener có thể phát event sai hoặc cập nhật dữ liệu ngoài ý muốn. Hãy có scenario cho thiếu tài nguyên, dữ liệu lỗi và event stale.

**Coi publish thành công là xử lý xong.** Listener async có thể chưa chạy. Hãy chờ điều kiện kết quả thực sự.

## Kết luận

Given event là sự kiện đầu vào xác định bối cảnh cho một scenario kiểm thử. Nó cần đúng contract, định danh rõ ràng và trạng thái nền phù hợp. Test sau đó kích hoạt event qua ranh giới Spring, chờ listener hoặc process manager phản ứng và xác minh event kết quả cùng thay đổi nghiệp vụ.

Với Spring Modulith, Scenario API giúp viết test cho event và listener bất đồng bộ theo điều kiện thay vì dùng sleep. Kết hợp fixture ổn định, transaction boundary rõ ràng, assertion theo business ID, kiểm thử duplicate và nhánh lỗi giúp scenario dễ đọc, tái lập và bảo vệ đúng hành vi giao tiếp giữa các module.

