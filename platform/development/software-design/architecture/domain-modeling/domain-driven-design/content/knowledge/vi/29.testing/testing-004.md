# Kiểm thử Aggregate bảo vệ bất biến qua mọi đường thay đổi

Trong Domain-Driven Design (DDD), aggregate là ranh giới nhất quán của một nhóm đối tượng nghiệp vụ. Aggregate root là điểm truy cập từ bên ngoài và chịu trách nhiệm bảo vệ các invariant của nhóm. Một invariant là quy tắc phải luôn đúng tại những thời điểm mà mô hình cam kết trạng thái hợp lệ, chẳng hạn đơn hàng không thể được xác nhận khi không có dòng hàng, số lượng của mỗi dòng phải dương hoặc tổng tiền phải khớp với các dòng và chính sách giá đã áp dụng.

Việc viết một unit test cho một phương thức chưa đủ chứng minh aggregate bảo vệ invariant. Cùng một trạng thái có thể bị thay đổi qua nhiều hành vi: thêm dòng, bỏ dòng, thay số lượng, áp dụng khuyến mại, xác nhận, khôi phục từ persistence hoặc xử lý một command khác. Nếu một đường thay đổi bỏ qua kiểm tra, aggregate vẫn có thể rơi vào trạng thái không hợp lệ.

Vì vậy, kiểm thử aggregate cần bắt đầu từ invariant và mọi đường thay đổi có thể tác động đến invariant đó. Nhóm cần kiểm tra hành vi hợp lệ, hành vi bị từ chối, trạng thái sau thao tác, domain event, các đường vào application, persistence và concurrency khi có liên quan. Bài học này trình bày cách lập ma trận invariant, viết unit test theo hành vi, kiểm tra mọi command, kết hợp property-based testing và integration testing, đồng thời tránh các test chỉ kiểm tra implementation hoặc getter/setter.

## 1. Aggregate bảo vệ điều gì?

Aggregate là ranh giới mà các invariant cần được bảo vệ cùng nhau. Aggregate root cung cấp các hành vi để thay đổi trạng thái và kiểm soát việc truy cập đến entity/value object nội bộ.

Ví dụ, một Order có thể chứa nhiều OrderLine và có các quy tắc:

- Đơn phải có ít nhất một dòng hàng trước khi được xác nhận.
- Số lượng của mỗi dòng phải lớn hơn 0.
- Không thể thêm hoặc bỏ dòng hàng sau khi đơn đã xác nhận.
- Tổng tiền được tính từ các dòng hàng và chính sách giá đã áp dụng.
- Mã khuyến mại không được áp dụng nhiều lần nếu chính sách không cho phép.
- Đơn đã hủy không thể được xác nhận hoặc giao.

Những quy tắc này không chỉ là điều kiện hiển thị trên giao diện. Chúng là cam kết của domain model. Dù hành động được gọi từ REST controller, message consumer, batch job hay test, aggregate vẫn phải bảo vệ invariant.

### 1.1. Invariant khác với một assertion tùy ý

Một assertion trong test là cách kiểm tra kết quả. Invariant là quy tắc nghiệp vụ mà mô hình phải duy trì. Test có thể dùng assertion để xác nhận invariant, nhưng cần xác định invariant trước khi viết test.

Ví dụ:

| Quy tắc | Loại | Nơi thường bảo vệ |
| --- | --- | --- |
| Quantity phải dương | Ràng buộc của giá trị | Quantity value object |
| Order không được xác nhận khi rỗng | Invariant của aggregate | Order root |
| Chỉ đơn nháp mới được thay đổi dòng hàng | Quy tắc vòng đời | Order root |
| Một SKU không xuất hiện hai lần trong đơn | Invariant cấu trúc nếu nghiệp vụ yêu cầu | Order root |
| Tồn kho không âm | Invariant của kho | Inventory aggregate/context |
| Người dùng có quyền xác nhận đơn | Authorization | Application/security boundary và chính sách liên quan |

Không nên đưa mọi kiểm tra vào Order. Aggregate chỉ bảo vệ invariant thuộc ranh giới của nó; các context khác chịu trách nhiệm quy tắc dữ liệu của mình.

## 2. Bắt đầu bằng ma trận invariant và đường thay đổi

Trước khi viết test, liệt kê invariant và những hành vi có thể làm thay đổi dữ liệu liên quan. Đây là bước quan trọng để không bỏ sót một đường mutation.

Ví dụ với Order:

| Invariant | Hành vi có thể ảnh hưởng | Trạng thái cần kiểm tra |
| --- | --- | --- |
| Đơn xác nhận phải có dòng hàng | create, addLine, removeLine, confirm | Không thể confirm khi rỗng |
| Quantity luôn dương | addLine, changeQuantity, import/re-hydrate | Không thể tạo hoặc lưu dòng có quantity không hợp lệ |
| Dòng hàng chỉ sửa khi đơn nháp | addLine, removeLine, changeQuantity, applyPromotion | Các hành vi sửa bị từ chối sau confirm |
| Tổng tiền khớp nội dung đơn | addLine, removeLine, changeQuantity, applyPromotion | Total được tính lại hoặc cập nhật nhất quán |
| Khuyến mại không áp dụng trùng | applyPromotion, reapply/retry command | Không giảm giá hai lần ngoài chính sách |
| Đơn đã hủy không thể tiếp tục fulfillment | cancel, confirm, markReadyForShipment | Không có transition trái vòng đời |

Ma trận giúp nhóm nhìn thấy rằng một invariant có thể bị tác động bởi nhiều hành vi. Ví dụ, quy tắc tổng tiền không chỉ liên quan addLine; removeLine, changeQuantity và applyPromotion cũng có thể làm thay đổi nó.

### 2.1. Liệt kê cả đường tạo và đường khôi phục

Trạng thái aggregate không chỉ được tạo qua factory hoặc constructor. Nó có thể được tải từ database, dựng từ event stream, chuyển đổi từ dữ liệu cũ hoặc nhận kết quả import. Các đường này phải bảo đảm dữ liệu được khôi phục phù hợp với invariant.

Không nhất thiết mọi lần load đều chạy lại toàn bộ business workflow. Nhưng persistence adapter không được âm thầm tạo ra object có cấu trúc bất hợp lệ mà domain model không thể phát hiện hoặc xử lý.

### 2.2. Liệt kê đường vào, không nhân bản quy tắc

Một hành vi nghiệp vụ có thể được gọi từ nhiều entry point:

- REST endpoint.
- Message consumer.
- Scheduled job.
- Batch import.
- CLI hoặc tác vụ quản trị.

Các entry point nên đi qua cùng application use case hoặc cùng hành vi domain. Test cần chứng minh các đường vào không tạo ra biến thể logic bỏ qua invariant. Không nên copy cùng quy tắc vào từng controller rồi kiểm thử riêng từng bản sao.

## 3. Thiết kế aggregate để có thể kiểm thử hành vi

Một aggregate dễ kiểm thử thường có những đặc điểm:

- Trạng thái nội bộ được đóng gói.
- Thay đổi thông qua method có tên nghiệp vụ.
- Không công khai setter tùy tiện.
- Collection nội bộ không bị sửa trực tiếp từ bên ngoài.
- Value object bất biến hoặc có semantics rõ.
- Quy tắc và lỗi nghiệp vụ được thể hiện cụ thể.
- Domain event được ghi nhận có chủ đích khi fact nghiệp vụ xảy ra.

Ví dụ cấu trúc rút gọn:

~~~java
public final class Order {
    private final OrderId id;
    private final List<OrderLine> lines = new ArrayList<>();
    private OrderStatus status;

    public Order(OrderId id) {
        this.id = Objects.requireNonNull(id);
        this.status = OrderStatus.DRAFT;
    }

    public void addLine(ProductId productId, Quantity quantity) {
        ensureDraft();
        lines.add(new OrderLine(productId, quantity));
    }

    public void removeLine(ProductId productId) {
        ensureDraft();
        if (lines.size() == 1) {
            throw new OrderMustContainAtLeastOneLineException();
        }
        boolean removed = lines.removeIf(line ->
                line.productId().equals(productId));
        if (!removed) {
            throw new OrderLineNotFoundException(productId);
        }
    }

    public void confirm() {
        ensureDraft();
        if (lines.isEmpty()) {
            throw new EmptyOrderCannotBeConfirmedException();
        }
        status = OrderStatus.CONFIRMED;
    }

    public List<OrderLine> lines() {
        return List.copyOf(lines);
    }

    public OrderStatus status() {
        return status;
    }

    private void ensureDraft() {
        if (status != OrderStatus.DRAFT) {
            throw new OrderIsNotEditableException(status);
        }
    }
}
~~~

Ví dụ chỉ tập trung vào invariant và đóng gói. Mô hình thực tế có thể dùng OrderLineId, Money, pricing policy và domain event. Việc trả về List.copyOf giúp caller không thể thay đổi collection nội bộ qua reference được trả ra.

### 3.1. Không kiểm thử bằng cách gọi setter nội bộ

Nếu test dùng reflection hoặc setter để đặt aggregate vào trạng thái cần thiết, nó có thể bỏ qua hành vi thật. Hãy tạo trạng thái qua factory, constructor có ý nghĩa hoặc các hành vi hợp lệ. Với test persistence, có thể dùng repository fixture hoặc builder chuyên dụng để dựng dữ liệu hợp lệ.

### 3.2. Không để test trở thành một đường mutation đặc biệt

Một phương thức package-private chỉ tồn tại để test sửa trạng thái có thể làm yếu encapsulation. Ưu tiên test qua public behavior của aggregate. Nếu cần dựng trạng thái phức tạp, dùng test data builder tạo một aggregate hợp lệ qua API miền.

## 4. Unit test cho invariant cơ bản

Unit test aggregate nên kiểm tra hành vi mà không cần Spring context, database hoặc message broker. Đây là nơi nhanh nhất để xác nhận quy tắc của mô hình.

Ví dụ với JUnit 5:

~~~java
class OrderTest {

    @Test
    void cannotConfirmAnEmptyOrder() {
        Order order = new Order(new OrderId("ORD-1"));

        assertThrows(
                EmptyOrderCannotBeConfirmedException.class,
                order::confirm
        );

        assertEquals(OrderStatus.DRAFT, order.status());
    }

    @Test
    void cannotAddLineWithNonPositiveQuantity() {
        Order order = new Order(new OrderId("ORD-1"));

        assertThrows(
                IllegalArgumentException.class,
                () -> new Quantity(0)
        );

        assertTrue(order.lines().isEmpty());
    }
}
~~~

Điểm quan trọng là test không chỉ xác nhận exception. Nó còn xác nhận trạng thái sau khi hành vi bị từ chối vẫn hợp lệ.

### 4.1. Kiểm tra trạng thái không bị thay đổi khi command thất bại

Một lỗi phổ biến là aggregate thay đổi một phần rồi mới phát hiện điều kiện không hợp lệ. Ví dụ, removeLine xóa dòng trước rồi mới kiểm tra đơn phải có ít nhất một dòng. Khi exception được ném ra, object trong bộ nhớ đã bị thay đổi dù transaction có thể chưa lưu.

Test nên xác nhận hành vi thất bại không để lại mutation ngoài ý muốn:

~~~java
@Test
void removingTheOnlyLineIsRejectedWithoutChangingTheOrder() {
    Order order = OrderTestData.draftOrderWithOneLine();
    List<OrderLine> before = order.lines();

    assertThrows(
            OrderMustContainAtLeastOneLineException.class,
            () -> order.removeLine(new ProductId("SKU-1"))
    );

    assertEquals(before, order.lines());
    assertEquals(OrderStatus.DRAFT, order.status());
}
~~~

Đây là kiểm tra tính nguyên tử ở cấp hành vi của aggregate: nếu hành động bị từ chối, trạng thái không bị thay đổi một phần.

## 5. Kiểm thử mọi hành vi có thể làm thay đổi invariant

Không nên dừng ở test addLine và confirm. Hãy quay lại ma trận invariant để kiểm tra mọi method có khả năng tác động.

Ví dụ với invariant “chỉ đơn nháp mới được chỉnh sửa dòng hàng”:

~~~java
@Test
void confirmedOrderCannotBeModifiedThroughAnyLineOperation() {
    Order order = OrderTestData.confirmedOrderWithTwoLines();
    List<OrderLine> before = order.lines();

    assertThrows(OrderIsNotEditableException.class,
            () -> order.addLine(
                    new ProductId("SKU-3"),
                    new Quantity(1)));

    assertThrows(OrderIsNotEditableException.class,
            () -> order.removeLine(new ProductId("SKU-1")));

    assertThrows(OrderIsNotEditableException.class,
            () -> order.changeQuantity(
                    new ProductId("SKU-2"),
                    new Quantity(5)));

    assertEquals(before, order.lines());
    assertEquals(OrderStatus.CONFIRMED, order.status());
}
~~~

Đoạn mã giả định aggregate có method changeQuantity và test fixture tạo đơn đã xác nhận hợp lệ. Mỗi public behavior thay đổi dữ liệu phải được đưa vào danh sách kiểm tra; nếu sau này thêm replaceLines hoặc applyBulkUpdate, ma trận invariant phải được cập nhật.

### 5.1. Kiểm tra các method cùng bảo vệ một invariant

Có thể dùng parameterized test khi nhiều hành vi cần xác nhận cùng một điều kiện. Tuy nhiên, tránh viết test quá trừu tượng khiến tên tình huống và lỗi khó hiểu. Một test riêng cho hành vi quan trọng thường dễ đọc hơn.

### 5.2. Kiểm tra collection không thể bị thay đổi từ bên ngoài

~~~java
@Test
void returnedLinesCannotMutateAggregateState() {
    Order order = OrderTestData.draftOrderWithOneLine();
    List<OrderLine> exposed = order.lines();

    assertThrows(
            UnsupportedOperationException.class,
            () -> exposed.clear()
    );

    assertEquals(1, order.lines().size());
}
~~~

Nếu collection chứa object mutable, copy danh sách chưa đủ. Các phần tử cũng cần được đóng gói hoặc bất biến để caller không thể sửa gián tiếp state của aggregate.

## 6. Kiểm thử state transition

Aggregate thường có vòng đời. Test cần xác nhận các transition hợp lệ và từ chối transition không hợp lệ.

Ví dụ:

| Trạng thái hiện tại | Hành vi | Kết quả mong đợi |
| --- | --- | --- |
| DRAFT | submit | SUBMITTED |
| DRAFT | confirm | Bị từ chối nếu chưa đủ điều kiện |
| SUBMITTED | confirm | CONFIRMED nếu policy cho phép |
| CONFIRMED | addLine | Bị từ chối |
| CONFIRMED | cancel | Chỉ được phép theo chính sách hủy |
| CANCELLED | confirm | Bị từ chối |
| SHIPPED | cancel | Có thể cần quy trình trả hàng thay vì hủy |

Không chỉ test happy path. Mỗi trạng thái cần được xem xét với các hành vi có thể gọi từ bên ngoài. Với state machine phức tạp, có thể lập bảng transition hoặc sơ đồ trạng thái làm nguồn thiết kế test.

### 6.1. Test transition hợp lệ

~~~java
@Test
void submittedOrderCanBeConfirmedWhenAllConditionsHold() {
    Order order = OrderTestData.submittedOrderWithValidLines();

    order.confirm();

    assertEquals(OrderStatus.CONFIRMED, order.status());
}
~~~

### 6.2. Test transition không hợp lệ

~~~java
@Test
void cancelledOrderCannotBeConfirmed() {
    Order order = OrderTestData.cancelledOrder();

    assertThrows(
            OrderCannotBeConfirmedException.class,
            order::confirm
    );

    assertEquals(OrderStatus.CANCELLED, order.status());
}
~~~

### 6.3. Test transition không làm mất dữ liệu

Nếu một transition thất bại, xác nhận các dữ liệu liên quan và domain events không bị thay đổi sai. Một exception không tự động chứng minh aggregate không bị mutation trước đó.

## 7. Kiểm thử Value Object và Entity nội bộ

Invariant của aggregate thường dựa trên value object và entity con. Chúng cần test riêng cho quy tắc thuộc trách nhiệm của chúng, đồng thời test tích hợp qua aggregate để bảo đảm các thành phần phối hợp đúng.

Ví dụ Quantity:

~~~java
class QuantityTest {
    @Test
    void acceptsPositiveValue() {
        assertEquals(3, new Quantity(3).value());
    }

    @Test
    void rejectsZero() {
        assertThrows(
                IllegalArgumentException.class,
                () -> new Quantity(0)
        );
    }

    @Test
    void rejectsNegativeValue() {
        assertThrows(
                IllegalArgumentException.class,
                () -> new Quantity(-1)
        );
    }
}
~~~

Nếu Quantity đã bảo đảm dương, OrderLine có thể dựa vào điều kiện đó. Nhưng Order vẫn cần test rằng mọi đường thêm/thay số lượng đều sử dụng Quantity hợp lệ.

### 7.1. Entity con không nên bị test như aggregate độc lập nếu nó không có lifecycle riêng

Nếu OrderLine chỉ có ý nghĩa trong Order, test hành vi chính qua Order root. Có thể test riêng phép tính hoặc value object của dòng hàng, nhưng không nên tạo repository và API độc lập cho entity con chỉ để test dễ hơn.

### 7.2. Equality và identity

Với entity, test cần phân biệt identity với equality theo giá trị. Hai OrderLine có cùng product và quantity chưa chắc là cùng một entity. Nếu domain dùng line ID, test cần xác nhận thay đổi một dòng không vô tình thay thế hoặc xóa dòng khác có cùng giá trị.

## 8. Kiểm thử Domain Event do aggregate ghi nhận

Một hành vi nghiệp vụ có thể làm thay đổi trạng thái và ghi nhận domain event. Test nên xác nhận event chỉ được tạo khi fact thực sự xảy ra và mang dữ liệu đúng.

Ví dụ:

~~~java
@Test
void confirmingOrderRecordsOrderConfirmedEvent() {
    Order order = OrderTestData.submittedOrderWithValidLines();

    order.confirm();

    List<DomainEvent> events = order.domainEvents();
    assertEquals(1, events.size());
    assertInstanceOf(OrderConfirmed.class, events.get(0));
}
~~~

### 8.1. Hành vi bị từ chối không phát event thành công

~~~java
@Test
void rejectedConfirmationDoesNotRecordOrderConfirmed() {
    Order order = new Order(new OrderId("ORD-1"));

    assertThrows(
            EmptyOrderCannotBeConfirmedException.class,
            order::confirm
    );

    assertTrue(order.domainEvents().isEmpty());
}
~~~

### 8.2. Kiểm tra nội dung event

Ngoài event type, kiểm tra các dữ liệu có ý nghĩa như aggregate ID, thời điểm nghiệp vụ, tổng tiền đã xác nhận hoặc policy version nếu đó là một phần của fact. Không kiểm tra những chi tiết kỹ thuật không thuộc contract của domain event.

### 8.3. Phân biệt ghi nhận event và publish event

Unit test aggregate kiểm tra event được ghi nhận. Việc lưu event vào outbox và gửi đến broker thuộc tầng application/infrastructure, cần integration test riêng. Không cần mock message broker bên trong unit test của aggregate.

## 9. Kiểm thử qua mọi đường vào của ứng dụng

Invariant phải được giữ bất kể hành vi được khởi phát từ đâu. Tuy nhiên, không nên sao chép test domain cho từng controller hoặc consumer. Thay vào đó, tất cả entry point nên gọi cùng application use case.

Ví dụ:

~~~text
REST Controller -----------+
                           |
Message Consumer ----------+----> ConfirmOrderHandler
                           |              |
Scheduled Job -------------+              v
                                      Order.confirm()
                                           |
                                           v
                                      Invariant
~~~

Test có thể xác nhận:

- REST adapter chuyển request thành đúng command.
- Message consumer chuyển event/request thành cùng use case hoặc một use case tương đương.
- Batch job không cập nhật trực tiếp entity/table bỏ qua aggregate.
- Application handler luôn tải aggregate và gọi behavior.

### 9.1. Test adapter không thay thế unit test aggregate

Controller test thường xác nhận status code, request mapping và response. Nó không nên là nơi duy nhất kiểm tra invariant. Nếu chỉ có integration test HTTP, lỗi domain có thể khó định vị và test chậm hơn cần thiết.

### 9.2. Kiểm tra đường ghi phụ

Các tác vụ import, migration, admin endpoint hoặc scheduled job thường là đường ghi dễ bị bỏ quên. Nếu chúng có thể tạo hoặc sửa aggregate, phải dùng cùng quy tắc domain hoặc có quy trình migration được kiểm soát và kiểm chứng riêng.

## 10. Kiểm thử Application Handler và transaction

Unit test aggregate chứng minh behavior trong bộ nhớ. Application handler cần test rằng use case tải đúng aggregate, gọi đúng hành vi, lưu thay đổi và xử lý transaction/error theo mong đợi.

Ví dụ có thể dùng fake repository:

~~~java
class ConfirmOrderHandlerTest {
    @Test
    void loadsOrderConfirmsAndSavesIt() {
        InMemoryOrderRepository repository =
                new InMemoryOrderRepository(
                        OrderTestData.submittedOrderWithValidLines());
        ConfirmOrderHandler handler =
                new ConfirmOrderHandler(repository);

        handler.handle(new ConfirmOrderCommand(
                new OrderId("ORD-1")));

        Order saved = repository.findById(new OrderId("ORD-1"))
                .orElseThrow();
        assertEquals(OrderStatus.CONFIRMED, saved.status());
    }
}
~~~

Fake repository phù hợp để kiểm tra orchestration ở mức unit. Nó không chứng minh JPA mapping, transaction hoặc SQL hoạt động đúng.

### 10.1. Kiểm thử lỗi và không lưu khi hành vi bị từ chối

Test nên xác nhận handler không lưu thay đổi nếu aggregate ném lỗi, hoặc transaction rollback khi persistence đã được thực hiện trước khi lỗi xảy ra. Thứ tự thao tác và transaction boundary cần được xem xét trong integration test.

### 10.2. Transaction test cần kiểm tra trạng thái database

Với JPA, có thể cần flush và clear persistence context trước khi đọc lại để tránh test chỉ nhìn thấy object đang được quản lý trong bộ nhớ. Dùng rollback test transaction một cách có chủ đích; nếu mọi test đều tự rollback, cần có test xác nhận commit thực tế khi điều đó quan trọng.

## 11. Kiểm thử Repository và khôi phục Aggregate

Repository là cổng lưu và tải aggregate. Integration test repository nên xác nhận:

- Aggregate được lưu với entity/value object nội bộ.
- Tải lại vẫn giữ identity và state đúng.
- Quan hệ sở hữu và collection được khôi phục chính xác.
- Domain behavior sau khi tải lại vẫn bảo vệ invariant.
- Optimistic version được lưu và kiểm tra nếu có.
- Mapping enum, tiền tệ, ngày giờ và value object không làm thay đổi semantics.

Ví dụ luồng kiểm thử:

1. Tạo Order hợp lệ với hai dòng.
2. Lưu qua repository.
3. Flush và clear persistence context.
4. Tải lại bằng Order ID.
5. Gọi hành vi changeQuantity hoặc confirm.
6. Xác nhận invariant vẫn được bảo vệ.

### 11.1. Kiểm thử dữ liệu cũ hoặc không hợp lệ

Database có thể chứa dữ liệu được tạo từ phiên bản ứng dụng cũ hoặc từ một đường ghi ngoài ORM. Nếu domain model không thể khôi phục trạng thái đó, cần một chiến lược rõ: từ chối load, chuyển dữ liệu qua migration, tạo trạng thái legacy có kiểm soát hoặc sửa dữ liệu.

Không nên âm thầm bỏ qua child hoặc thay giá trị lỗi bằng default nếu điều đó làm thay đổi ý nghĩa nghiệp vụ.

### 11.2. Rehydration không được tạo event nghiệp vụ mới

Khi repository tải aggregate từ database, việc dựng lại object không nên phát lại các event như OrderPlaced hoặc OrderConfirmed như thể chúng vừa xảy ra. Nếu event collection được dùng để lưu domain events, cần bảo đảm rehydration không tạo event mới ngoài ý muốn.

## 12. Kiểm thử concurrency và optimistic locking

Một số invariant không thể được bảo vệ chỉ bằng kiểm tra tuần tự trong một instance. Ví dụ, hai request đồng thời cùng đọc số lượng tồn là 1 rồi cả hai cùng đặt một đơn vị. Mỗi request riêng lẻ đều thấy điều kiện hợp lệ, nhưng kết quả tổng thể có thể vi phạm invariant.

Với aggregate có version, optimistic locking có thể phát hiện hai transaction cùng sửa một phiên bản:

~~~java
@Entity
public class InventoryItemEntity {
    @Id
    private UUID id;

    @Version
    private long version;

    private int availableQuantity;
}
~~~

Ví dụ này minh họa cơ chế version của JPA. Khi hai transaction cập nhật cùng version, một transaction có thể thất bại với optimistic locking exception. Application cần xử lý conflict phù hợp, có thể tải lại và đánh giá lại command.

### 12.1. Test race condition ở mức database

Một integration test concurrency có thể:

1. Tạo tồn kho bằng 1.
2. Khởi chạy hai transaction đồng thời, mỗi transaction cố giữ 1 đơn vị.
3. Đồng bộ hai luồng để cả hai đọc trạng thái ban đầu trước khi ghi.
4. Commit cả hai.
5. Xác nhận chỉ một reservation thành công và invariant tồn kho không âm.

Không nên chỉ test bằng hai object Order trong bộ nhớ vì chúng không chia sẻ transaction hoặc storage.

### 12.2. Không phải mọi invariant đều giải quyết bằng @Version

Optimistic locking bảo vệ xung đột cập nhật trên version của entity/aggregate được ánh xạ. Một invariant liên quan nhiều hàng hoặc nhiều aggregate có thể cần unique constraint, transaction isolation phù hợp, atomic update, reservation model hoặc cơ chế điều phối khác. Chọn cơ chế dựa trên invariant cụ thể.

### 12.3. Kiểm tra retry sau conflict

Nếu application tự retry khi optimistic lock conflict, test cần xác nhận command được đánh giá lại trên state mới. Không được phát event hoặc thực hiện tác dụng phụ bên ngoài hai lần khi transaction đầu đã thất bại.

## 13. Property-based testing cho invariant

**Property-based testing** sinh nhiều dữ liệu đầu vào và kiểm tra một thuộc tính phải luôn đúng.

Ví dụ, nếu quantity luôn dương:

~~~text
Với mọi số nguyên q:
  nếu q > 0 thì Quantity(q) hợp lệ
  nếu q <= 0 thì Quantity(q) bị từ chối
~~~

Một thuộc tính khác cho Order:

~~~text
Với mọi chuỗi hành vi hợp lệ:
  nếu Order.status != DRAFT
  thì không hành vi chỉnh sửa dòng hàng nào được làm thay đổi lines
~~~

### 13.1. Ví dụ kiểm tra số lượng

Với thư viện property testing như jqwik, có thể viết:

~~~java
@Property
void quantityAcceptsOnlyPositiveNumbers(
        @ForAll int value
) {
    if (value > 0) {
        assertEquals(value, new Quantity(value).value());
    } else {
        assertThrows(
                IllegalArgumentException.class,
                () -> new Quantity(value)
        );
    }
}
~~~

Đây là ví dụ minh họa API của jqwik; cần thêm dependency và import phù hợp với phiên bản thư viện. Với giá trị lớn hoặc miền dữ liệu giới hạn, có thể dùng generator tùy chỉnh để tránh tạo dữ liệu không có ý nghĩa.

### 13.2. Property trên chuỗi hành vi

Có thể sinh một chuỗi command như addLine, changeQuantity, removeLine, submit, confirm và cancel. Sau mỗi command, kiểm tra các invariant tổng quát:

- Mọi quantity trong lines đều dương.
- Trạng thái không nằm ngoài tập trạng thái hợp lệ.
- Nếu status không phải DRAFT thì không thể chỉnh sửa lines.
- Nếu command bị từ chối, state không thay đổi ngoài các side effect được định nghĩa.

Test dạng stateful/property-based phức tạp hơn và cần model tham chiếu để biết command nào hợp lệ. Bắt đầu với các property đơn giản, sau đó mở rộng khi có giá trị.

### 13.3. Shrinking giúp tìm ví dụ lỗi nhỏ

Một số thư viện property-based testing có khả năng thu nhỏ dữ liệu đầu vào khi phát hiện lỗi. Một chuỗi 50 hành vi có thể được rút thành 3 hành vi tối thiểu tái hiện invariant bị phá vỡ. Điều này giúp tìm nguyên nhân tốt hơn so với một test ngẫu nhiên lớn khó tái tạo.

## 14. Kiểm thử invariant với mutation testing

Mutation testing thay đổi nhỏ trong code để kiểm tra test có phát hiện lỗi hay không. Ví dụ, công cụ có thể loại bỏ điều kiện kiểm tra status, đổi toán tử lớn hơn thành lớn hơn hoặc bằng, hoặc bỏ một lời gọi cập nhật tổng tiền.

Nếu test vẫn pass sau khi một điều kiện quan trọng bị loại bỏ, có thể bộ test chưa bảo vệ invariant đó.

Mutation testing hữu ích để đánh giá sức mạnh của test, nhưng:

- Không thay thế việc xác định invariant với chuyên gia.
- Mutation score cao không chứng minh mô hình đúng nghiệp vụ.
- Một số mutation không thể ảnh hưởng đến hành vi hoặc là tương đương về semantics.
- Không cần chạy trên mọi module nếu chi phí quá lớn; ưu tiên domain core có rủi ro cao.

## 15. Kiểm thử lỗi nghiệp vụ và lỗi kỹ thuật

Test nên phân biệt lỗi do quy tắc nghiệp vụ với lỗi hạ tầng:

| Loại lỗi | Ví dụ | Kỳ vọng |
| --- | --- | --- |
| Invariant violation | Đơn rỗng không thể xác nhận | Từ chối command, không đổi state |
| Invalid transition | Đơn đã hủy không thể xác nhận | Từ chối theo lỗi miền |
| Authorization | Actor không có quyền duyệt | Từ chối ở application/security boundary |
| Not found | Order ID không tồn tại | Use case trả kết quả không tìm thấy |
| Concurrency conflict | Version đã thay đổi | Transaction thất bại hoặc command được đánh giá lại |
| Infrastructure failure | Database unavailable | Rollback, retry hoặc báo lỗi kỹ thuật theo chính sách |

Không nên bắt mọi exception rồi chuyển thành một lỗi chung Invalid request. Điều đó làm mất khả năng phân biệt và có thể khiến hệ thống retry lỗi nghiệp vụ vô hạn.

### 15.1. Test mã lỗi và semantics, không phụ thuộc thông điệp tùy ý

Với API, nên kiểm tra error code hoặc error type ổn định. Nội dung thông điệp có thể được dịch hoặc điều chỉnh; test không nên phụ thuộc chính xác một câu văn nếu đó không phải contract.

## 16. Test data builder và fixture

Aggregate phức tạp có thể cần nhiều dữ liệu để đạt trạng thái cụ thể. Test data builder giúp tạo dữ liệu hợp lệ và làm test dễ đọc.

~~~java
public final class OrderTestData {
    public static Order draftOrderWithOneLine() {
        Order order = new Order(new OrderId("ORD-1"));
        order.addLine(new ProductId("SKU-1"), new Quantity(1));
        return order;
    }

    public static Order submittedOrderWithValidLines() {
        Order order = draftOrderWithOneLine();
        order.submit();
        return order;
    }

    public static Order confirmedOrderWithTwoLines() {
        Order order = draftOrderWithOneLine();
        order.addLine(new ProductId("SKU-2"), new Quantity(2));
        order.submit();
        order.confirm();
        return order;
    }
}
~~~

Builder nên dùng hành vi công khai để tạo state hợp lệ. Tránh builder dùng reflection hoặc ghi trực tiếp field private, vì nó có thể tạo trạng thái mà production code không thể tạo.

### 16.1. Fixture cần rõ dữ liệu quan trọng

Một fixture tên confirmedOrderWithTwoLines dễ hiểu hơn setup dài với nhiều setter. Nhưng không nên che giấu dữ liệu quyết định kết quả test. Nếu test phụ thuộc tổng tiền, hãy làm rõ giá và số lượng trong fixture hoặc tạo builder có tham số.

### 16.2. Tránh fixture dùng chung có state mutable

Mỗi test nên có aggregate mới hoặc fixture độc lập. Dùng một static object mutable cho nhiều test có thể khiến thứ tự chạy test ảnh hưởng kết quả.

## 17. Kiểm thử bằng ví dụ nghiệp vụ và bảng quyết định

Để bảo đảm test phản ánh đúng hiểu biết của chuyên gia, hãy chuyển các ví dụ đã thống nhất thành test case.

Ví dụ chính sách áp dụng khuyến mại:

| Khách hàng | Đơn đạt ngưỡng | Khu vực hợp lệ | Mã còn hiệu lực | Kết quả |
| --- | --- | --- | --- | --- |
| Thành viên | Có | Có | Có | Áp dụng |
| Thành viên | Không | Có | Có | Từ chối vì chưa đạt ngưỡng |
| Khách thường | Có | Có | Có | Từ chối nếu chỉ dành cho thành viên |
| Thành viên | Có | Không | Có | Từ chối do vùng không hỗ trợ |
| Thành viên | Có | Có | Không | Từ chối do mã hết hiệu lực |

Test nên kiểm tra cả outcome và reason code nếu domain cần giải thích quyết định. Nếu có nhiều điều kiện tương tác, bảng quyết định giúp phát hiện các tổ hợp chưa được hỏi chuyên gia.

### 17.1. Boundary value

Với ngưỡng 1.000.000 VND, cần test:

- 999.999: dưới ngưỡng.
- 1.000.000: đúng ngưỡng.
- 1.000.001: trên ngưỡng.

Các giá trị biên thường phát hiện lỗi dùng nhầm > với >=, rounding hoặc scale tiền tệ.

### 17.2. Kiểm tra tiền và đơn vị

Không chỉ test con số; cần kiểm tra currency, scale và rounding. 100 USD không thể được cộng trực tiếp với 100 VND. Nếu aggregate dùng Money value object, test cần xác nhận phép toán từ chối tiền tệ không tương thích.

## 18. Kiểm thử transaction, event và outbox

Nếu aggregate ghi domain event và application layer lưu outbox, cần kiểm thử các cam kết liên quan:

- Khi command thành công, state và outbox message được commit cùng nhau.
- Khi transaction rollback, không có outbox message được publish như thể hành động đã thành công.
- Khi publisher gửi message nhưng chưa đánh dấu sent, retry không tạo tác dụng phụ nghiệp vụ trùng ở consumer.
- Consumer lưu inbox/deduplication cùng transaction cập nhật read model hoặc aggregate của nó.

Đây là integration concern, không phải trách nhiệm của unit test aggregate. Test cần dùng database/broker test phù hợp hoặc adapter fake ở cấp kiểm thử tương ứng.

### 18.1. Không kiểm tra broker trong mọi unit test

Unit test của Order chỉ cần xác nhận OrderConfirmed được ghi nhận. Integration test của outbox/publisher mới xác nhận message được lưu và gửi đúng. Chia test theo ranh giới giúp lỗi được định vị nhanh hơn.

## 19. Test không nên kiểm tra implementation detail

Một test tốt mô tả hành vi quan sát được và invariant. Nó không nên bị hỏng chỉ vì nhóm đổi cấu trúc nội bộ mà không đổi semantics.

Tránh:

- Kiểm tra số lần gọi private helper.
- Dùng reflection để đọc mọi field nội bộ.
- Assert thứ tự gọi method không thuộc contract.
- Mock mọi collaborator của aggregate dù aggregate không có dependency.
- Kiểm tra tên class persistence hoặc câu SQL trong unit test domain.
- Viết test chỉ xác nhận getter trả lại giá trị vừa set.

Ưu tiên:

- Gọi hành vi công khai.
- Kiểm tra trạng thái quan sát được qua API domain có ý nghĩa.
- Kiểm tra kết quả hoặc exception nghiệp vụ.
- Kiểm tra event được ghi nhận.
- Dùng integration test khi cần xác nhận persistence, transaction hoặc concurrency.

### 19.1. Test phải thất bại khi invariant bị phá

Hãy tự hỏi: nếu bỏ điều kiện bảo vệ invariant khỏi production code, test nào sẽ thất bại? Nếu không có test nào, ma trận kiểm thử còn thiếu.

## 20. Phân tầng test cho Aggregate

Một chiến lược thực tế có thể chia thành:

| Tầng test | Phạm vi | Công cụ thường dùng | Mục tiêu |
| --- | --- | --- | --- |
| Unit test value object | Giá trị và phép toán | JUnit | Bảo vệ quy tắc giá trị |
| Unit test aggregate | Hành vi, invariant, transition, event | JUnit | Bảo vệ mô hình miền |
| Unit test application | Điều phối command/query và repository port | JUnit, fake | Kiểm tra use case |
| Repository integration | Mapping, load/save, rehydration | Testcontainers hoặc DB test | Kiểm tra persistence thực |
| Transaction/concurrency | Commit, rollback, locking | Database mục tiêu | Kiểm tra invariant dưới cạnh tranh |
| API/message contract | Request, response, command/event mapping | MockMvc, contract test | Kiểm tra đường vào và hợp đồng |
| Property/mutation testing | Nhiều đầu vào và sức mạnh test | jqwik, PIT hoặc công cụ tương đương | Tìm khoảng trống trong test |

Không cần chạy tất cả tầng cho mọi thay đổi nhỏ. Chọn test dựa trên ranh giới bị tác động và rủi ro của invariant.

## 21. Quy trình thiết kế bộ test cho một Aggregate

Nhóm có thể đi theo các bước sau:

### Bước 1: Liệt kê invariant bằng ngôn ngữ nghiệp vụ

Viết mỗi invariant thành một câu có thể kiểm tra. Tránh bắt đầu từ method hoặc class hiện có.

### Bước 2: Xác định owner của invariant

Xác định invariant thuộc value object, entity, aggregate root, domain service hay bounded context khác. Không gom mọi quy tắc vào một aggregate.

### Bước 3: Liệt kê mọi đường tạo và thay đổi state

Bao gồm constructor/factory, public behavior, command handler, API, message, batch, import, repository rehydration và thao tác đồng thời nếu có.

### Bước 4: Lập ma trận invariant × behavior

Với mỗi invariant, đánh dấu những behavior có thể ảnh hưởng. Những ô chưa có test là điểm cần xem xét.

### Bước 5: Viết unit test cho hành vi hợp lệ và bị từ chối

Kiểm tra trạng thái trước/sau, exception có ý nghĩa và không có mutation một phần.

### Bước 6: Kiểm tra state transition và domain event

Đảm bảo transition hợp lệ được chấp nhận, transition sai bị từ chối và event chỉ được ghi nhận khi fact thực sự xảy ra.

### Bước 7: Kiểm tra application entry point

Đảm bảo REST, message và batch đi qua cùng use case/domain behavior; không có đường ghi bỏ qua aggregate.

### Bước 8: Bổ sung persistence và concurrency test

Kiểm tra repository load/save, transaction, optimistic locking, unique constraint hoặc cơ chế bảo vệ invariant liên aggregate khi cần.

### Bước 9: Thêm property-based hoặc mutation test khi có giá trị

Ưu tiên quy tắc có nhiều tổ hợp đầu vào, phép tính hoặc rủi ro cao. Không thêm công cụ chỉ để tăng số lượng test.

### Bước 10: Duy trì ma trận khi mô hình thay đổi

Khi thêm method hoặc trạng thái mới, xem lại invariant nào bị tác động và cập nhật test tương ứng. Test là một phần của mô hình hóa, không chỉ là bước cuối sau code.

## 22. Những sai lầm thường gặp

| Sai lầm | Hệ quả | Cách cải thiện |
| --- | --- | --- |
| Chỉ test một method chính | Các đường thay đổi khác có thể phá invariant | Lập ma trận invariant × behavior |
| Chỉ test happy path | Không phát hiện transition và dữ liệu biên sai | Test cả hành vi bị từ chối và trạng thái sau lỗi |
| Test bằng setter hoặc reflection | Bỏ qua đường hành vi thật | Tạo state qua factory/builder và public behavior |
| Aggregate trả collection mutable | Caller sửa state mà không qua root | Trả immutable copy và bảo vệ phần tử |
| Chỉ test exception | Aggregate có thể đã bị thay đổi một phần trước khi ném lỗi | Assert state và event sau khi thất bại |
| Đặt invariant ở controller | Message/batch hoặc use case khác có thể bỏ qua | Bảo vệ trong domain model |
| Dùng mock repository để kết luận mapping đúng | Không phát hiện lỗi ORM hoặc transaction | Bổ sung repository integration test |
| Chỉ test một thread | Bỏ sót race condition và lost update | Test concurrency trên database mục tiêu |
| Không kiểm tra domain event | Event có thể phát sai hoặc phát khi command bị từ chối | Assert event type và payload ở unit test |
| Kiểm tra broker trong unit test aggregate | Test chậm và gắn domain với hạ tầng | Tách unit test và outbox integration test |
| Test phụ thuộc private method hoặc call count | Refactor không đổi behavior làm test vỡ | Assert kết quả và contract công khai |
| Fixture dùng chung mutable | Test phụ thuộc thứ tự chạy | Tạo fixture độc lập cho từng test |
| Không test dữ liệu rehydrate | Aggregate tải từ database có thể vi phạm invariant | Test save/load rồi thực hiện behavior |
| Bỏ qua đường ghi import/admin | Một lối ghi khác có thể tạo dữ liệu không hợp lệ | Kiểm kê mọi entry point và kiểm soát migration |

## 23. Nguyên tắc thực hành

Khi kiểm thử Aggregate bảo vệ invariant qua mọi đường thay đổi, nhóm nên nhớ:

- **Bắt đầu từ invariant.** Viết quy tắc bằng ngôn ngữ nghiệp vụ trước khi chọn assertion.
- **Xác định đúng owner.** Aggregate chỉ bảo vệ invariant thuộc ranh giới của nó.
- **Lập ma trận invariant và behavior.** Một quy tắc có thể bị ảnh hưởng bởi nhiều hành vi.
- **Kiểm thử qua public behavior.** Không dùng setter/reflection để bỏ qua mô hình.
- **Kiểm tra cả state sau thất bại.** Exception không bảo đảm không có mutation một phần.
- **Kiểm tra mọi transition.** Bao gồm transition hợp lệ, không hợp lệ và trạng thái terminal.
- **Kiểm tra domain event.** Fact chỉ được ghi nhận khi hành vi thành công.
- **Bao phủ mọi entry point.** REST, message, batch và admin phải đi qua use case/domain behavior có kiểm soát.
- **Tách unit và integration test.** Unit test bảo vệ domain; integration test bảo vệ ORM, transaction và database.
- **Kiểm tra concurrency khi invariant có cạnh tranh.** Dùng version, constraint hoặc cơ chế phù hợp và test trên storage thật.
- **Dùng property-based testing có mục tiêu.** Tìm tổ hợp đầu vào và chuỗi hành vi khó liệt kê thủ công.
- **Tránh implementation detail.** Test semantics công khai, không khóa test vào cấu trúc private.
- **Cập nhật test cùng mô hình.** Mỗi behavior mới cần được đánh giá theo invariant có thể bị ảnh hưởng.

Kiểm thử aggregate không chỉ chứng minh một method trả đúng kết quả. Nó chứng minh các quy tắc nghiệp vụ vẫn được bảo vệ qua mọi hành vi và mọi đường đi có thể làm thay đổi trạng thái. Ma trận invariant × behavior giúp nhóm không bỏ sót đường mutation; unit test kiểm tra logic và transition; application test xác nhận use case; integration/concurrency test kiểm tra persistence và cạnh tranh thực tế. Khi test tập trung vào hành vi công khai và semantics nghiệp vụ, nhóm có thể refactor cấu trúc nội bộ mà vẫn giữ được những cam kết quan trọng của domain model.

## 24. Câu hỏi tự kiểm tra

1. Invariant là gì và vì sao cần xác định nó trước khi viết unit test?
2. Vì sao một invariant có thể cần được kiểm tra qua nhiều behavior khác nhau?
3. Ma trận invariant × behavior giúp phát hiện khoảng trống kiểm thử như thế nào?
4. Phân biệt invariant của aggregate với validation đầu vào, authorization và quy tắc của bounded context khác.
5. Vì sao test nên đi qua public behavior thay vì setter hoặc reflection?
6. Khi một hành vi ném exception, vì sao cần kiểm tra state không bị thay đổi một phần?
7. Những transition nào cần được kiểm thử trong vòng đời của Order?
8. Làm thế nào để kiểm tra domain event chỉ được ghi nhận khi fact nghiệp vụ xảy ra?
9. Vì sao unit test aggregate không đủ để chứng minh JPA mapping và repository rehydration đúng?
10. Khi nào cần kiểm thử concurrency và optimistic locking trên database thật?
11. Property-based testing và mutation testing giúp tìm khoảng trống nào trong bộ test?
12. Làm thế nào để bảo đảm REST, message consumer và batch job đều không bỏ qua invariant?
13. Vì sao test không nên phụ thuộc private method hoặc số lần gọi helper?
14. Hãy chọn một aggregate trong hệ thống của bạn, lập ma trận invariant × behavior và đề xuất unit, integration, concurrency test tương ứng.
