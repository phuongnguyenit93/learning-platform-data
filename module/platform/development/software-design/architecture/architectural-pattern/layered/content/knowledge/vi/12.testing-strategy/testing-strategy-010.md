# Tránh kiểm thử chỉ xác nhận chuỗi gọi nội bộ mà bỏ sót hành vi nghiệp vụ

Trong module **SOFTWARE_DESIGN_ARCHITECTURE_ARCHITECTURAL_PATTERN_LAYERED** (Học tổ chức phần mềm theo kiến trúc phân tầng), bài học này tập trung vào cách kiểm thử một use case sao cho kết quả phản ánh đúng quy tắc nghiệp vụ. Ta dùng chức năng tạo đơn hàng để phân biệt kiểm thử hành vi với kiểm thử chuỗi lời gọi giữa các lớp, đồng thời tìm hiểu khi nào mock, fake và kiểm thử tích hợp thực sự hữu ích.

Một bài test có thể xác nhận controller đã gọi service, service đã gọi repository và repository đã được yêu cầu lưu dữ liệu. Nhưng nếu tổng tiền sai, đơn được lưu ở trạng thái không hợp lệ hoặc tồn kho bị trừ sai, bài test đó vẫn có thể xanh. Mục tiêu của kiểm thử là phát hiện hành vi sai mà người dùng, hệ thống bên ngoài hoặc dữ liệu nghiệp vụ có thể quan sát được.

## 1. Kiểm thử điều gì: hành vi hay cách triển khai?

Trong kiến trúc phân tầng, một yêu cầu thường đi qua controller, application service, domain model và repository. Các lớp này cộng tác để hoàn thành một mục tiêu. Tuy nhiên, người dùng không quan tâm ứng dụng đã gọi bao nhiêu phương thức nội bộ. Họ quan tâm đơn hàng được tạo đúng hay không, số tiền phải trả là bao nhiêu, tồn kho được giữ đúng số lượng hay yêu cầu bị từ chối khi không đủ hàng.

**Kiểm thử hành vi (behavior-focused test)** xác minh kết quả có ý nghĩa của một tình huống:

- Đầu vào hợp lệ tạo ra đơn hàng với các dòng hàng và tổng tiền chính xác.
- Số lượng không hợp lệ bị từ chối.
- Không đủ tồn kho thì đơn không được ghi nhận như một đơn đã đặt thành công.
- Đơn đã giao không thể bị hủy theo chính sách.
- Một yêu cầu thanh toán lặp không tạo ra lần thu tiền thứ hai.
- API trả đúng status code và dữ liệu theo hợp đồng đã công bố.

**Kiểm thử tương tác (interaction test)** xác minh một thành phần đã giao tiếp với collaborator theo cách có ý nghĩa, ví dụ cổng thanh toán nhận đúng số tiền và mã idempotency. Loại kiểm thử này hữu ích khi chính tương tác là một phần của hợp đồng. Nó trở nên mong manh khi chỉ xác nhận thứ tự gọi các phương thức nội bộ mà không kiểm tra kết quả nghiệp vụ.

| Câu hỏi | Kiểm thử hành vi | Kiểm thử chuỗi gọi nội bộ |
|---|---|---|
| Đơn có tổng tiền đúng không? | Xác minh trực tiếp | Có thể không kiểm tra |
| Đơn có trạng thái hợp lệ không? | Xác minh trực tiếp | Có thể chỉ kiểm tra repository đã được gọi |
| Tồn kho có thay đổi đúng không? | Kiểm tra trạng thái sau use case | Chỉ xác nhận `reserve()` được gọi |
| Có phụ thuộc cấu trúc lớp không? | Thường ít hơn | Thường nhiều hơn |
| Khi nào có ích? | Hầu hết quy tắc và use case | Tương tác bên ngoài có ý nghĩa như thanh toán, gửi thông điệp |

Không phải mọi lời gọi nội bộ đều phải trở thành một assertion. Một service có thể đổi từ ba lớp helper thành một lớp, đổi thứ tự các bước không ảnh hưởng kết quả, hoặc thay repository adapter; nếu hành vi công khai vẫn đúng thì các test nghiệp vụ nên tiếp tục xanh.

## 2. Vì sao test chỉ verify lời gọi có thể tạo cảm giác an toàn giả?

Giả sử test tạo đơn dùng Mockito và chỉ xác minh các collaborator đã được gọi:

```java
@Test
void placeOrderCallsExpectedCollaborators() {
    service.placeOrder(command);

    InOrder order = inOrder(productCatalog, inventory, orderRepository);
    order.verify(productCatalog).getSellableProduct(productId);
    order.verify(inventory).reserve(command.items());
    order.verify(orderRepository).save(any(Order.class));
}
```

Bài test này có thể xanh trong cả những trường hợp:

- Service tính tổng tiền bằng đơn giá cũ thay vì giá catalog hiện hành.
- Service lưu đơn với trạng thái `CANCELLED` thay vì `PENDING_PAYMENT`.
- Số lượng được truyền vào inventory bị nhân đôi.
- Service bỏ mất một dòng hàng nhưng vẫn gọi `save()`.
- Repository nhận đúng một object nhưng object đó chứa dữ liệu sai.

Nó chỉ chứng minh một chuỗi tương tác đã xảy ra theo kỳ vọng của test. Nó không chứng minh nội dung được truyền đi đúng về mặt nghiệp vụ hoặc trạng thái cuối cùng hợp lệ.

Một test còn dễ gắn chặt vào triển khai hơn nếu kiểm tra quá nhiều chi tiết:

- Phải gọi helper A trước helper B dù thứ tự đó không phải quy tắc nghiệp vụ.
- Phải gọi repository đúng một lần dù tối ưu hợp lệ có thể gom hoặc tách truy vấn.
- Phải gọi một phương thức private thông qua spy.
- Phải dùng đúng một class cụ thể dù interface và hành vi bên ngoài không đổi.

Khi refactor mà không thay đổi hành vi, các test kiểu này thường thất bại. Nhóm phát triển phải sửa test theo cấu trúc mới dù sản phẩm vẫn đúng. Chi phí bảo trì test tăng nhưng khả năng phát hiện lỗi nghiệp vụ không tăng tương ứng.

## 3. Xác định kết quả có ý nghĩa trước khi viết test

Trước khi mock bất kỳ collaborator nào, hãy diễn đạt tình huống bằng ngôn ngữ nghiệp vụ:

**Given**: một khách hàng hợp lệ, sản phẩm đang được bán với giá 12.000 đồng và còn đủ tồn kho.

**When**: khách hàng đặt hai sản phẩm.

**Then**:

- Một đơn mới được tạo cho đúng khách hàng.
- Đơn có một dòng hàng với số lượng hai.
- Đơn giá được lấy từ catalog là 12.000 đồng.
- Tổng tiền là 24.000 đồng.
- Trạng thái ban đầu là `PENDING_PAYMENT`.
- Tồn kho khả dụng giảm hai đơn vị hoặc số lượng được giữ chỗ tăng hai đơn vị theo mô hình tồn kho của ứng dụng.

Các kết quả này là những điều có ý nghĩa đối với nghiệp vụ. Chúng vẫn đúng nếu nhóm phát triển đổi tên service, gộp repository, thay JPA bằng JDBC hoặc tối ưu cách truy vấn.

Một test tốt thường có ba phần rõ ràng:

1. **Arrange:** tạo dữ liệu ban đầu và các collaborator cần thiết.
2. **Act:** gọi hành động công khai của đối tượng hoặc use case.
3. **Assert:** kiểm tra kết quả, trạng thái và tác động có ý nghĩa.

Tên test nên mô tả điều kiện và kết quả, chẳng hạn `placesOrderAtCurrentCatalogPrice`, thay vì tên triển khai như `callsCatalogThenInventoryThenRepository`.

## 4. Dùng fake để kiểm tra use case qua trạng thái quan sát được

Mock rất tiện để thay thế một collaborator, nhưng với repository hoặc thành phần có trạng thái đơn giản, một fake có thể làm test tự nhiên hơn. Fake là một triển khai thay thế có hành vi đủ thật cho phạm vi kiểm thử, ví dụ repository lưu object trong bộ nhớ.

Giả sử application có các abstraction:

```java
public interface ProductCatalog {
    ProductSnapshot getSellableProduct(UUID productId);
}

public interface Inventory {
    void reserve(UUID productId, int quantity);
    int available(UUID productId);
}

public interface OrderRepository {
    Order save(Order order);
    Optional<Order> findById(UUID orderId);
    List<Order> findAll();
}
```

Các fake có thể lưu trạng thái trong bộ nhớ:

```java
final class InMemoryOrderRepository implements OrderRepository {
    private final Map<UUID, Order> orders = new HashMap<>();

    @Override
    public Order save(Order order) {
        orders.put(order.id(), order);
        return order;
    }

    @Override
    public Optional<Order> findById(UUID id) {
        return Optional.ofNullable(orders.get(id));
    }

    @Override
    public List<Order> findAll() {
        return List.copyOf(orders.values());
    }
}
```

```java
final class InMemoryInventory implements Inventory {
    private final Map<UUID, Integer> available;

    InMemoryInventory(Map<UUID, Integer> initialStock) {
        this.available = new HashMap<>(initialStock);
    }

    @Override
    public void reserve(UUID productId, int quantity) {
        int current = available.getOrDefault(productId, 0);

        if (quantity <= 0 || current < quantity) {
            throw new InsufficientStockException(productId);
        }

        available.put(productId, current - quantity);
    }

    @Override
    public int available(UUID productId) {
        return available.getOrDefault(productId, 0);
    }
}
```

Một test use case có thể kiểm tra kết quả thay vì thứ tự gọi:

```java
@Test
void placesOrderAtCurrentCatalogPriceAndReservesRequestedQuantity() {
    UUID customerId = UUID.randomUUID();
    UUID productId = UUID.randomUUID();

    ProductCatalog catalog = new StubProductCatalog(Map.of(
        productId,
        new ProductSnapshot(
            productId,
            "Bình nước",
            new BigDecimal("12000")
        )
    ));

    var inventory = new InMemoryInventory(Map.of(productId, 5));
    var orders = new InMemoryOrderRepository();

    var useCase = new PlaceOrderService(catalog, inventory, orders);

    var result = useCase.handle(new PlaceOrderCommand(
        customerId,
        List.of(new PlaceOrderItem(productId, 2))
    ));

    var saved = orders.findById(result.orderId()).orElseThrow();

    assertThat(result.total())
        .isEqualByComparingTo("24000");
    assertThat(saved.customerId()).isEqualTo(customerId);
    assertThat(saved.status()).isEqualTo(OrderStatus.PENDING_PAYMENT);
    assertThat(saved.lines()).singleElement().satisfies(line -> {
        assertThat(line.productId()).isEqualTo(productId);
        assertThat(line.quantity()).isEqualTo(2);
        assertThat(line.unitPrice()).isEqualByComparingTo("12000");
    });
    assertThat(inventory.available(productId)).isEqualTo(3);
}
```

Ví dụ giả định `PlaceOrderService` dùng giá từ `ProductCatalog`, kiểm tra và giữ tồn kho qua `Inventory`, sau đó lưu `Order`. `StubProductCatalog` cung cấp snapshot cố định cho test; các kiểu miền và command là kiểu minh họa của ứng dụng. Điểm quan trọng là test quan sát đơn đã lưu và tồn kho sau hành động. Test không cần biết service gọi helper nào hoặc repository được gọi trước hay sau một mapper cụ thể.

### Kiểm tra trường hợp bị từ chối

Test lỗi cũng nên xác minh kết quả nghiệp vụ:

```java
@Test
void doesNotCreateOrderWhenStockIsInsufficient() {
    UUID productId = UUID.randomUUID();

    var catalog = new StubProductCatalog(Map.of(
        productId,
        new ProductSnapshot(
            productId, "Bình nước", new BigDecimal("12000"))
    ));
    var inventory = new InMemoryInventory(Map.of(productId, 1));
    var orders = new InMemoryOrderRepository();
    var useCase = new PlaceOrderService(catalog, inventory, orders);

    assertThatThrownBy(() -> useCase.handle(
        new PlaceOrderCommand(
            UUID.randomUUID(),
            List.of(new PlaceOrderItem(productId, 2))
        )
    )).isInstanceOf(InsufficientStockException.class);

    assertThat(orders.findAll()).isEmpty();
    assertThat(inventory.available(productId)).isEqualTo(1);
}
```

Test này xác minh điều quan trọng: khi không đủ hàng, không có đơn nào được lưu và tồn kho không bị giảm. Với fake trong bộ nhớ, nếu implementation use case cần bảo đảm hoàn tác nhiều thay đổi khi một bước sau thất bại, fake phải mô phỏng đúng hợp đồng đó hoặc test cần dùng integration test với transaction thật. Không nên cho rằng fake đơn giản tự chứng minh được rollback của database.

## 5. Kiểm thử quy tắc miền trực tiếp

Các quy tắc thuộc về domain nên được kiểm tra gần mô hình miền. Không cần khởi động Spring, database hay mock repository nếu hành vi có thể kiểm tra trực tiếp trên đối tượng.

Ví dụ, đơn đã giao không được hủy:

```java
@Test
void deliveredOrderCannotBeCancelled() {
    Order order = anOrder()
        .withStatus(OrderStatus.DELIVERED)
        .build();

    assertThatThrownBy(order::requestCancellation)
        .isInstanceOf(InvalidOrderStateException.class);

    assertThat(order.status()).isEqualTo(OrderStatus.DELIVERED);
}
```

Test này kiểm tra cả hai điều: hành động bị từ chối và trạng thái vẫn được giữ nguyên. Nếu chỉ xác minh `requestCancellation()` ném exception mà không kiểm tra trạng thái, một implementation có thể đổi trạng thái trước khi ném lỗi mà test vẫn xanh.

Với quy tắc tính tiền, hãy kiểm tra kết quả và các biên:

```java
@ParameterizedTest
@CsvSource({
    "1, 12000",
    "2, 24000",
    "5, 60000"
})
void calculatesLineSubtotal(int quantity, String expected) {
    var line = new OrderLine(
        productId,
        quantity,
        new BigDecimal("12000")
    );

    assertThat(line.subtotal())
        .isEqualByComparingTo(expected);
}
```

Bổ sung test cho số lượng bằng không, số lượng âm, đơn không có dòng hàng, đơn giá âm, làm tròn và đơn vị tiền tệ theo chính sách thực tế. Một test chỉ xác nhận phương thức `subtotal()` được gọi không chứng minh phép tính đúng.

## 6. Khi nào mock và verify tương tác là hợp lý?

Mock không xấu. Nó hữu ích khi một collaborator khó khởi tạo, không nên gọi thật trong unit test hoặc tạo ra tác động bên ngoài. Điều cần tránh là dùng mock để mô phỏng toàn bộ hệ thống rồi chỉ xác nhận các lời gọi nội bộ.

Có thể kiểm tra tương tác khi tương tác đó mang ý nghĩa nghiệp vụ hoặc là hợp đồng của một ranh giới bên ngoài:

- Cổng thanh toán phải nhận đúng số tiền, đơn vị tiền tệ và mã idempotency.
- Email xác nhận chỉ được yêu cầu sau khi đơn đã được tạo thành công.
- Adapter gửi message phải phát đúng loại event và đúng mã đơn.
- Dịch vụ bên ngoài không được gọi khi điều kiện nghiệp vụ chưa thỏa.
- Một thao tác có chi phí hoặc tác động không thể lặp phải tuân thủ chính sách retry đã định.

Ví dụ, thay vì chỉ kiểm tra `paymentGateway.capture()` đã được gọi, hãy kiểm tra nội dung yêu cầu:

```java
@Test
void capturesTheExactAmountForTheOrder() {
    var gateway = new RecordingPaymentGateway();
    var service = new CaptureOrderPaymentService(gateway, orderRepository);

    service.handle(new CapturePaymentCommand(
        orderId,
        new BigDecimal("24000"),
        "VND",
        "capture-order-" + orderId
    ));

    assertThat(gateway.requests()).singleElement().satisfies(request -> {
        assertThat(request.orderId()).isEqualTo(orderId);
        assertThat(request.amount()).isEqualByComparingTo("24000");
        assertThat(request.currency()).isEqualTo("VND");
        assertThat(request.idempotencyKey())
            .isEqualTo("capture-order-" + orderId);
    });
}
```

Ở đây, fake ghi nhận request để test kiểm tra hợp đồng với cổng thanh toán. Nếu dùng Mockito, có thể dùng `ArgumentCaptor` để kiểm tra cùng các trường. Điều quan trọng là kiểm tra ý nghĩa của request, không chỉ xác nhận phương thức đã chạy.

Một số tương tác cũng cần kiểm tra số lần gọi. Ví dụ, việc thu tiền là tác động có thể gây mất tiền nếu lặp ngoài ý muốn. Test idempotency nên chứng minh hai yêu cầu cùng mã idempotency không tạo hai lần capture thực tế. Đây là quy tắc tích hợp có ý nghĩa, khác với việc xác minh một helper nội bộ được gọi đúng một lần vì implementation hiện tại có một vòng lặp.

### Khi thứ tự tương tác thực sự quan trọng

Có những thứ tự là một phần của hợp đồng:

- Phải xác thực chữ ký webhook trước khi xử lý nội dung thanh toán.
- Phải kiểm tra quyền trước khi trả dữ liệu nhạy cảm.
- Chỉ gửi yêu cầu hoàn tiền sau khi xác nhận đơn đủ điều kiện hủy.
- Chỉ phát thông báo thành công sau khi thay đổi nghiệp vụ đã commit.

Khi đó, hãy kiểm tra thứ tự ở ranh giới có ý nghĩa và gắn với kết quả. Ví dụ, test không chỉ xác nhận `authorize()` chạy trước `capture()`; nó cần chứng minh capture không xảy ra khi authorization thất bại và đơn không được chuyển sang trạng thái đã thanh toán.

Không nên kiểm tra thứ tự mọi lời gọi giữa các lớp nếu thứ tự đó không phải quy tắc. Một refactor hợp lệ có thể đổi cách phối hợp nội bộ mà không làm thay đổi kết quả.

## 7. Phân biệt stub, fake, mock và spy

Các test double có mục đích khác nhau:

| Loại | Vai trò | Ví dụ |
|---|---|---|
| Dummy | Đối tượng được truyền vào nhưng không được dùng trong test | Một clock hoặc context rỗng khi đường chạy không truy cập |
| Stub | Trả về dữ liệu định trước | Catalog luôn trả một snapshot sản phẩm |
| Fake | Có implementation đơn giản nhưng hoạt động được | Repository trong bộ nhớ, inventory giả lập số lượng |
| Mock | Ghi nhận hoặc xác minh tương tác mong đợi | Payment gateway mock, message publisher mock |
| Spy | Bọc đối tượng thật và quan sát một số lời gọi | Theo dõi một adapter thật trong trường hợp cần thiết |

Không có quy tắc rằng fake luôn tốt hơn mock. Chọn loại phù hợp với mục tiêu:

- Dùng stub để kiểm soát dữ liệu đầu vào của test.
- Dùng fake khi cần quan sát trạng thái sau use case.
- Dùng mock khi cần xác minh hợp đồng tương tác bên ngoài.
- Dùng spy tiết chế vì spy thường làm test phụ thuộc cách đối tượng được triển khai.

Nếu một test phải mock quá nhiều lớp nội bộ, đó có thể là dấu hiệu use case phụ thuộc quá sâu vào chi tiết triển khai hoặc trách nhiệm chưa được phân chia hợp lý. Hãy xem lại ranh giới abstraction trước khi thêm nhiều mock và `verify()`.

## 8. Kiểm thử theo tầng nhưng không tách rời hành vi

Kiến trúc phân tầng cho phép chọn phạm vi kiểm thử phù hợp. Mỗi tầng có thể được kiểm thử riêng, nhưng test ở mỗi tầng vẫn cần xác minh hành vi có ý nghĩa.

| Phạm vi | Nên xác minh | Tránh chỉ xác minh |
|---|---|---|
| Domain unit test | Bất biến, phép tính, chuyển trạng thái, điều kiện bị từ chối | Một phương thức nội bộ đã được gọi |
| Application/use case test | Kết quả use case, trạng thái được lưu, lỗi và tác động có ý nghĩa | Repository được gọi với `any()` |
| Repository/adapter integration test | Truy vấn, mapping, transaction, constraint với database thật | Mock Spring Data repository |
| Controller/API test | HTTP status, JSON contract, validation, quyền truy cập | Controller gọi đúng một service cụ thể |
| End-to-end test | Một luồng quan trọng hoạt động khi ghép các thành phần | Mọi chi tiết nội bộ của toàn ứng dụng |

### Domain unit test

Kiểm tra nhanh, độc lập với framework. Nên có các trường hợp hợp lệ, không hợp lệ và biên. Đây là nơi phù hợp để xác minh quy tắc giá, trạng thái hoặc quyền hành động nếu quy tắc nằm trong domain.

### Application test

Dùng fake hoặc mock cho các port mà use case phụ thuộc. Kiểm tra kết quả của use case và trạng thái có thể quan sát. Không cần mock các lớp domain chỉ để xác minh phương thức miền được gọi; hãy để domain chạy thật để test phát hiện lỗi quy tắc.

### Repository integration test

Dùng database kiểm thử để xác minh JPQL, SQL, mapping, constraint và transaction. Nếu mock Spring Data repository, test chỉ chứng minh service gọi mock; nó không chứng minh truy vấn thực sự đúng hoặc database từ chối dữ liệu sai.

### Controller/API test

Kiểm tra hợp đồng HTTP: status code, body, validation, security và định dạng. Không nên phụ thuộc vào số lần gọi một service nội bộ trừ khi đó là hành vi có ý nghĩa đối với ranh giới API.

### End-to-end test

Giữ số lượng vừa phải, tập trung vào các luồng quan trọng như đặt đơn, thanh toán, hủy đơn. E2E kiểm tra sự phối hợp tổng thể nhưng thường chậm và khó khoanh vùng lỗi; không nên thay thế toàn bộ unit test bằng E2E.

## 9. Test transaction và side effect theo kết quả cuối

Một test application dùng fake không chứng minh transaction database thật sự rollback. Với yêu cầu như "nếu ghi dòng hàng thất bại thì đơn và dòng hàng đều không tồn tại", cần integration test chạy qua Spring transaction manager và database.

Ví dụ khái niệm:

```java
@Test
void rollsBackOrderWhenSavingALineFails() {
    assertThatThrownBy(() -> service.createOrderThatFailsAfterHeader(command))
        .isInstanceOf(DataAccessException.class);

    assertThat(orderRepository.findById(expectedOrderId)).isEmpty();
    assertThat(orderLineRepository.findByOrderId(expectedOrderId)).isEmpty();
}
```

Đây là ví dụ khái niệm, giả định fixture làm cho thao tác lưu dòng hàng ném `DataAccessException` và `expectedOrderId` là ID đã biết của đơn. Sau khi bắt exception, test truy vấn lại dữ liệu bằng một transaction/EntityManager phù hợp. Cần tránh để transaction do chính test mở bao trùm toàn bộ thao tác rồi khiến test chỉ quan sát trạng thái chưa commit. Có thể dùng transaction riêng cho bước xác minh hoặc cấu hình test không tự mở transaction.

Với outbox hoặc message, hãy xác minh bản ghi được ghi cùng transaction nghiệp vụ. Nếu transaction rollback, không được có event thành công trong outbox. Nếu publisher có thể phát lặp, consumer cần test idempotency. Một test chỉ verify `eventPublisher.publish()` được gọi chưa chứng minh event được lưu bền vững hoặc chỉ được phát sau commit.

## 10. Dữ liệu test và fixture nên làm rõ ý nghĩa nghiệp vụ

Test có thể trở nên khó đọc nếu dữ liệu được tạo bằng nhiều constructor, UUID và giá trị rời rạc. Builder hoặc fixture giúp mô tả bối cảnh:

```java
Order order = anOrder()
    .forCustomer(customerId)
    .withStatus(OrderStatus.PAID)
    .withLine(productId, 2, money("12000", "VND"))
    .build();
```

Builder nên cung cấp giá trị mặc định hợp lệ và cho phép thay đổi những trường liên quan đến tình huống. Không nên ẩn quá nhiều quy tắc trong fixture khiến người đọc không biết vì sao đơn được coi là hợp lệ.

Tránh dùng chung một object mutable giữa nhiều test. Mỗi test nên tự tạo trạng thái ban đầu hoặc dùng fixture bất biến. Với thời gian, dùng `Clock` có thể tiêm vào service để test hết hạn hoặc thời điểm thanh toán mà không phụ thuộc đồng hồ hệ thống. Với ID, có thể dùng UUID cố định nếu cần kết quả dễ đọc.

Một test thất bại cần cho biết dữ liệu nào và quy tắc nào sai. Tên biến như `paidOrderPastDeliveryWindow` có ý nghĩa hơn `order1` khi kiểm tra chính sách hoàn tiền.

## 11. Tránh assertion yếu và coverage gây hiểu lầm

Một số test có assertion nhưng vẫn không kiểm tra đủ hành vi:

- Chỉ kiểm tra kết quả khác null.
- Chỉ kiểm tra danh sách không rỗng mà không kiểm tra phần tử.
- Chỉ kiểm tra exception nhưng không kiểm tra trạng thái sau lỗi.
- Chỉ kiểm tra repository nhận một entity mà không kiểm tra trường trong entity.
- Chỉ kiểm tra status code 200 mà không kiểm tra nội dung response.
- Chỉ kiểm tra một nhánh thành công, bỏ qua điều kiện biên và nhánh bị từ chối.

Code coverage cao không đồng nghĩa test tốt. Một dòng có thể được chạy qua mà không có assertion nào phát hiện kết quả sai. Branch coverage cũng không bảo đảm các tổ hợp trạng thái và dữ liệu quan trọng đã được kiểm tra.

Một cách đánh giá hữu ích là tự hỏi: nếu cố ý làm sai phép tính tổng tiền, bỏ điều kiện kiểm tra tồn kho hoặc cho phép hủy đơn đã giao, test nào sẽ thất bại? Nếu không có test nào thất bại, bộ test chưa bảo vệ quy tắc đó.

Có thể dùng mutation testing, chẳng hạn PIT cho Java, để thay đổi nhỏ mã nguồn trong lúc chạy test và xem test có phát hiện được không. Mutation testing giúp tìm assertion yếu hoặc nhánh chưa được bảo vệ, nhưng cũng có chi phí chạy và cần phân biệt mutant tương đương với lỗi thực sự. Không nhất thiết bật cho mọi module ngay từ đầu.

## 12. Tránh test mong manh khi refactor

Test nên bảo vệ hành vi đã cam kết, không khóa implementation vào một hình dạng duy nhất.

Dấu hiệu test mong manh:

- Dùng `InOrder` để xác minh nhiều lời gọi nội bộ không mang ý nghĩa nghiệp vụ.
- Verify mọi getter, mapper hoặc helper.
- Spy vào service chỉ để xác minh private method được gọi.
- Assert một truy vấn repository cụ thể dù hợp đồng chỉ yêu cầu kết quả đúng.
- Mock cả domain model, khiến test không chạy quy tắc thật.
- Kiểm tra số lần gọi nội bộ thay vì kết quả có thể quan sát.

Khi refactor, hãy giữ những test mô tả hợp đồng và loại bỏ assertion chỉ phản ánh cấu trúc cũ. Nếu đổi từ JPA sang JDBC mà endpoint vẫn trả đúng dữ liệu và use case vẫn bảo vệ quy tắc, test nghiệp vụ nên không cần viết lại hàng loạt.

Tuy nhiên, một số chi tiết kỹ thuật là mục tiêu kiểm thử hợp lệ. Ví dụ, truy vấn danh sách phải không tạo N+1 hoặc một adapter phải gửi một request theo giao thức xác định. Khi kiểm tra hiệu năng hoặc giao thức, hãy ghi rõ lý do và phạm vi của assertion để người bảo trì hiểu đây là yêu cầu thực sự.

## 13. Một ma trận tình huống cho use case tạo đơn

Trước khi hoàn thiện test suite, lập ma trận từ các quy tắc quan trọng:

| Bối cảnh | Hành động | Kết quả nghiệp vụ cần xác minh |
|---|---|---|
| Sản phẩm đang bán, đủ hàng | Đặt đơn | Đơn được tạo, giá và tổng tiền đúng, tồn kho được giữ đúng |
| Số lượng bằng 0 | Đặt đơn | Bị từ chối, không có đơn |
| Sản phẩm không còn bán | Đặt đơn | Bị từ chối theo chính sách, không có đơn |
| Tồn kho thấp hơn số lượng yêu cầu | Đặt đơn | Bị từ chối, tồn kho không âm, không có đơn thành công |
| Catalog đổi giá | Đặt đơn | Dùng giá áp dụng tại thời điểm đặt theo chính sách |
| Lưu đơn thất bại | Đặt đơn | Các thay đổi trong transaction được rollback |
| Thanh toán xác nhận hai lần cùng reference | Xử lý webhook | Không ghi nhận thanh toán hai lần |
| Đơn đã giao | Yêu cầu hủy | Bị từ chối và trạng thái vẫn là đã giao |
| Người dùng không sở hữu đơn | Xem/hủy đơn | Không truy cập hoặc thay đổi đơn trái quyền |
| Event phát lại | Cập nhật read model | Projection không bị nhân đôi dữ liệu |

Không nhất thiết mỗi dòng phải là một E2E test. Quy tắc miền có thể được kiểm tra bằng unit test; điều phối use case bằng application test; SQL và transaction bằng integration test; hợp đồng HTTP bằng controller test. Chọn phạm vi rẻ nhất nhưng đủ chứng minh hành vi.

## 14. Quy trình rà soát một bài test

Khi viết hoặc review test, hãy lần lượt hỏi:

1. Test mô tả tình huống nghiệp vụ nào?
2. Kết quả mong đợi có thể quan sát từ bên ngoài thành phần đang kiểm thử không?
3. Assertion có kiểm tra giá trị, trạng thái, dữ liệu lưu hoặc tác động thực sự không?
4. Nếu thay đổi thứ tự gọi helper hoặc thay repository adapter, test có còn hợp lệ không?
5. Mock có đang thay thế một ranh giới bên ngoài hay chỉ mô phỏng toàn bộ lớp nội bộ?
6. Nếu dùng verify, tương tác được kiểm tra có mang ý nghĩa nghiệp vụ hoặc là hợp đồng tích hợp không?
7. Khi có lỗi, test có xác minh dữ liệu không bị thay đổi một phần ngoài ý muốn không?
8. Test có chạy quy tắc miền thật hay đã mock mất phần quan trọng nhất?
9. Có integration test cho những hành vi phụ thuộc database, transaction hoặc framework không?
10. Nếu cố ý làm sai quy tắc, test nào sẽ thất bại?

Một bộ test có giá trị giúp nhóm phát hiện lỗi làm thay đổi kết quả nghiệp vụ, đồng thời cho phép thay đổi cấu trúc bên trong một cách an toàn. Hãy ưu tiên kiểm tra điều hệ thống phải làm và điều hệ thống phải từ chối; dùng xác minh tương tác khi ranh giới bên ngoài thực sự yêu cầu nó. Như vậy, test vừa bảo vệ tính đúng đắn vừa hỗ trợ refactor các tầng của ứng dụng.

