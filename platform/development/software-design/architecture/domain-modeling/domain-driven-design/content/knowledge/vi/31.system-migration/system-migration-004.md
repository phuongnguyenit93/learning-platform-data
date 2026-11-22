# Trích xuất Value Object và hành vi miền theo từng bước

Khi đưa Domain-Driven Design (DDD) vào một hệ thống đã tồn tại, không nhất thiết phải viết lại toàn bộ ứng dụng. Một hệ thống legacy có thể đang lưu dữ liệu bằng các kiểu nguyên thủy, chứa quy tắc nghiệp vụ trong service lớn, controller hoặc stored procedure. Những quy tắc đó vẫn đang phục vụ người dùng và có thể đã tích lũy nhiều trường hợp đặc biệt qua nhiều năm.

Thách thức là cải thiện mô hình mà không làm gián đoạn hành vi đang chạy. Một cách tiếp cận thực tế là chuyển đổi tăng dần: chọn một khái niệm nghiệp vụ nhỏ, bảo vệ hành vi hiện tại bằng test, trích xuất Value Object, sau đó chuyển từng quy tắc và caller sang mô hình miền mới. Mỗi bước cần có ranh giới rõ, có thể kiểm chứng và có khả năng triển khai độc lập.

Trong DDD, phạm vi chuyển đổi cần phù hợp với chiến lược tổng thể: xác định subdomain và bounded context sở hữu khái niệm, hiểu quan hệ với context khác qua context map, rồi mới chọn tactical model như Entity, Value Object, Aggregate, Repository và Domain Event. Trích xuất một class khỏi legacy code chỉ có ý nghĩa khi tên gọi và quy tắc của nó thuộc đúng mô hình nghiệp vụ.

Bài học này tập trung vào **trích xuất Value Object và hành vi miền theo từng bước**. Ví dụ xuyên suốt dùng quy trình đơn hàng: ban đầu hệ thống dùng String, BigDecimal và các hàm xử lý thủ tục; sau đó dần hình thành Money, Quantity, OrderLine và hành vi của Order. Mục tiêu là giữ cho hệ thống hoạt động trong suốt quá trình chuyển đổi, đồng thời làm rõ ngôn ngữ và invariant của nghiệp vụ.

## Sau bài học này

Bạn có thể:

- Nhận diện primitive obsession và quy tắc nghiệp vụ đang bị phân tán trong legacy code.
- Chọn một phạm vi nhỏ để chuyển đổi mà không cần viết lại cả module.
- Dùng characterization test để ghi nhận hành vi hiện tại trước khi refactor.
- Trích xuất Value Object bất biến với validation và equality theo giá trị.
- Chuyển đổi API/caller từng bước bằng adapter và compatibility seam.
- Đưa hành vi cùng invariant về Entity hoặc Aggregate phù hợp.
- Phân biệt hành vi của Entity, Value Object, Domain Service và Application Service.
- Di chuyển dữ liệu theo chiến lược expand-and-contract và tránh dual-write không an toàn.
- Triển khai theo từng đợt, quan sát kết quả và có phương án rollback.
- Biết khi nào nên dừng, giữ một phần legacy code hoặc hoãn việc trừu tượng hóa.

## 1. Vì sao nên chuyển đổi từng bước?

Legacy code không chỉ là code cũ. Nó còn chứa những hành vi mà người dùng đang dựa vào, các tích hợp chưa được tài liệu hóa và những quy tắc chỉ xuất hiện trong dữ liệu thực tế. Một cuộc viết lại lớn có thể mất nhiều tháng, trong khi hệ thống cũ vẫn phải tiếp tục nhận thay đổi và xử lý giao dịch.

Chuyển đổi tăng dần giúp:

- Giữ hệ thống chạy trong khi thay đổi cấu trúc bên trong.
- Phát hiện sai khác ở phạm vi nhỏ trước khi lan rộng.
- Đưa ngôn ngữ nghiệp vụ vào code theo từng khái niệm.
- Giảm rủi ro khi dữ liệu và API đã được nhiều caller sử dụng.
- Cho phép dừng hoặc điều chỉnh sau mỗi bước.
- Đưa ra giá trị sớm mà không phải chờ hoàn tất một đợt rewrite lớn.

### Mục tiêu là thay đổi mô hình mà giữ đúng hành vi

Ví dụ legacy:

~~~java
public BigDecimal calculateLineTotal(
    BigDecimal unitPrice,
    int quantity,
    String currency
) {
    if (unitPrice.signum() < 0) {
        throw new IllegalArgumentException("Invalid price");
    }
    if (quantity <= 0) {
        throw new IllegalArgumentException("Invalid quantity");
    }
    return unitPrice.multiply(BigDecimal.valueOf(quantity));
}
~~~

Đoạn code có thể chạy đúng với các trường hợp đã biết, nhưng ngữ nghĩa còn yếu:

- BigDecimal có thể là giá, số lượng, thuế hoặc một đại lượng khác.
- String currency có thể chứa mã tiền tệ sai.
- Quy tắc về precision, scale và làm tròn chưa được thể hiện.
- Mỗi caller có thể kiểm tra giá và số lượng theo cách khác nhau.
- Hàm chỉ tính toán; chưa có nơi rõ ràng sở hữu invariant của dòng đơn hàng.

Mục tiêu không phải thay mọi kiểu nguyên thủy bằng class. Mục tiêu là đưa những khái niệm có quy tắc và ý nghĩa riêng thành mô hình có tên, có hành vi và có thể bảo vệ tính hợp lệ.

## 2. Bắt đầu bằng việc hiểu phạm vi legacy

Trước khi thay đổi code, hãy chọn một luồng nghiệp vụ có thể theo dõi từ đầu đến cuối. Ví dụ: tạo dòng hàng, tính tổng tiền và lưu đơn.

Thu thập đủ thông tin trong phạm vi đó:

- Entry point: controller, message consumer, scheduler hoặc batch job.
- Các service, helper và repository được gọi.
- Bảng, cột, stored procedure và dữ liệu liên quan.
- Các caller khác đang dùng cùng hàm hoặc cùng field.
- Quy tắc nghiệp vụ đã biết và trường hợp ngoại lệ.
- Tác động bên ngoài như event, email, thanh toán hoặc cập nhật hệ thống khác.
- Các lỗi và response mà caller hiện tại đang phụ thuộc.

Không cần lập bản đồ toàn bộ hệ thống ngay. Cần biết đủ để tránh thay đổi một hàm dùng chung mà không hiểu các caller khác.

### Chọn một seam nhỏ

Seam là điểm trong cấu trúc hiện tại nơi có thể thay đổi cách triển khai mà vẫn giữ hợp đồng bên ngoài. Ví dụ:

- Một service method có đầu vào/đầu ra rõ.
- Một module nội bộ chỉ có một số caller.
- Một repository adapter.
- Một API boundary có DTO ổn định.
- Một luồng command có thể chuyển sang handler mới.

Ưu tiên phạm vi có:

- Ý nghĩa nghiệp vụ tương đối rõ.
- Số lượng caller có thể kiểm soát.
- Dữ liệu có thể xác minh.
- Test có thể viết hoặc bổ sung.
- Giá trị cải thiện đủ cụ thể.

Tránh bắt đầu bằng aggregate lớn nhất, module có nhiều tích hợp nhất hoặc phần code chưa ai hiểu nếu chưa có cách kiểm chứng hành vi.

## 3. Ghi nhận hành vi hiện tại bằng Characterization Test

Khi hệ thống chưa có đặc tả đầy đủ, characterization test giúp ghi lại điều code đang thực sự làm. Test có thể chưa khẳng định behavior đó là đúng về mặt nghiệp vụ; nó ghi nhận kết quả hiện tại để đội có cơ sở so sánh khi refactor.

Ví dụ:

~~~java
class LegacyOrderCalculatorTest {
    private final LegacyOrderCalculator calculator =
        new LegacyOrderCalculator();

    @Test
    void calculatesLineTotalForPositiveQuantity() {
        BigDecimal total = calculator.calculateLineTotal(
            new BigDecimal("12.50"), 3, "USD"
        );

        assertEquals(new BigDecimal("37.50"), total);
    }

    @Test
    void rejectsNegativePrice() {
        assertThrows(
            IllegalArgumentException.class,
            () -> calculator.calculateLineTotal(
                new BigDecimal("-1.00"), 1, "USD"
            )
        );
    }
}
~~~

Test thực tế nên bao gồm các trường hợp đã được quan sát:

- Giá bằng không, giá âm và giá có nhiều chữ số thập phân.
- Số lượng bằng không, âm và rất lớn.
- Currency không hợp lệ hoặc khác nhau.
- Làm tròn ở các ranh giới.
- Chiết khấu, thuế và phí vận chuyển.
- Null, chuỗi rỗng và dữ liệu lịch sử không chuẩn.
- Các ngoại lệ đang được caller xử lý.

### Characterization test khác với specification test

Characterization test trả lời: “Code hiện tại làm gì với đầu vào này?”. Specification test trả lời: “Nghiệp vụ muốn hệ thống làm gì?”. Nếu test hiện tại cho kết quả sai theo chuyên gia nghiệp vụ, không nên vô tình đóng băng bug thành quy tắc mới.

Hãy ghi nhận sai khác đã biết và quyết định riêng: giữ tương thích trong đợt refactor, hay sửa bug bằng một thay đổi nghiệp vụ được phê duyệt.

### Test các tác động, không chỉ giá trị trả về

Với use case ghi, hãy ghi nhận:

- Bản ghi nào được tạo hoặc cập nhật.
- Event nào được phát sinh.
- Thứ tự gọi dịch vụ ngoài.
- Transaction commit/rollback.
- Response và error code.
- Quy tắc idempotency hoặc retry.

Một hàm tính toán có thể cho cùng tổng tiền nhưng use case vẫn thay đổi nếu nó phát event hai lần hoặc bỏ qua audit record.

## 4. Nhận diện Primitive Obsession

Primitive obsession xảy ra khi các kiểu nguyên thủy như String, int, long, BigDecimal hoặc UUID được dùng để biểu diễn nhiều khái niệm nghiệp vụ khác nhau, trong khi ý nghĩa và quy tắc của chúng không được đóng gói.

Ví dụ:

~~~java
void transfer(
    String sourceAccount,
    String targetAccount,
    BigDecimal amount,
    String currency
);
~~~

Chữ ký trên không thể hiện:

- SourceAccount và TargetAccount có thể bị đảo vị trí.
- amount có được âm hay bằng không không.
- currency có nằm trong tập mã được hỗ trợ không.
- Hai tài khoản có cùng currency không.
- Có được chuyển tiền giữa hai tài khoản cùng chủ sở hữu không.

### Khi nào nên trích xuất Value Object?

Một kiểu nguyên thủy đáng được xem xét khi:

- Có tên nghiệp vụ rõ như Money, EmailAddress, AccountNumber hoặc Quantity.
- Có validation hoặc normalization cần dùng nhất quán.
- Có phép toán riêng hoặc quy tắc so sánh.
- Có nhiều field phải đi cùng nhau, như amount và currency.
- Nhầm lẫn kiểu dữ liệu có thể gây lỗi đáng kể.
- Khái niệm được dùng ở nhiều nơi và có cùng semantics.

### Không tạo Value Object cho mọi primitive

Một biến đếm nội bộ không có quy tắc riêng có thể giữ kiểu int. Một String chỉ dùng làm nhãn hiển thị không nhất thiết cần class riêng. Trích xuất Value Object khi nó làm ngôn ngữ, tính hợp lệ hoặc quy tắc trở nên rõ hơn.

## 5. Bước 1: Trích xuất Value Object đầu tiên

Chọn một khái niệm có phạm vi nhỏ và ít phụ thuộc. Money là ví dụ phổ biến vì số tiền luôn gắn với currency và có quy tắc toán học.

### Mô hình Money

~~~java
public record Money(BigDecimal amount, Currency currency) {
    public Money {
        Objects.requireNonNull(amount, "amount");
        Objects.requireNonNull(currency, "currency");
        amount = amount.stripTrailingZeros();
    }

    public static Money of(String amount, String currencyCode) {
        return new Money(
            new BigDecimal(amount),
            Currency.getInstance(currencyCode)
        );
    }

    public Money add(Money other) {
        requireSameCurrency(other);
        return new Money(amount.add(other.amount), currency);
    }

    public Money multiply(int quantity) {
        if (quantity < 0) {
            throw new IllegalArgumentException("quantity must not be negative");
        }
        return new Money(
            amount.multiply(BigDecimal.valueOf(quantity)),
            currency
        );
    }

    private void requireSameCurrency(Money other) {
        if (!currency.equals(other.currency)) {
            throw new CurrencyMismatchException(currency, other.currency);
        }
    }
}
~~~

Đây là ví dụ khung. Quy tắc precision, scale, rounding mode, giới hạn giá trị và việc có cho phép số âm hay không phải được xác nhận theo nghiệp vụ. Không nên coi stripTrailingZeros là quy tắc phù hợp cho mọi hệ thống tiền tệ.

Money đóng gói amount và currency thành một khái niệm. Caller không thể vô tình cộng USD với VND mà không đi qua kiểm tra.

### Value Object nên bất biến

Value Object thường bất biến:

- Không cung cấp setter thay đổi một phần trạng thái.
- Constructor/factory bảo đảm instance hợp lệ.
- Phép biến đổi trả về instance mới.
- Equality dựa trên giá trị thay vì identity.
- Có thể chia sẻ giữa các object mà không lo một caller sửa dữ liệu của caller khác.

Trong Java, record có thể phù hợp với Value Object nhỏ, nhưng record không tự bảo đảm mọi invariant. Constructor compact hoặc factory vẫn cần kiểm tra dữ liệu và defensive copy cho collection nếu có.

### Value Object có thể có hành vi

Value Object không chỉ là túi dữ liệu. Money có thể cộng, trừ, nhân; DateRange có thể kiểm tra giao nhau; EmailAddress có thể chuẩn hóa và xác thực định dạng theo chính sách; Quantity có thể cộng và so sánh theo đơn vị.

Hành vi nên thuộc khái niệm đó khi quy tắc không cần identity hoặc trạng thái của một Entity khác.

## 6. Bước 2: Giữ API cũ trong khi chuyển đổi caller

Sau khi có Money, không nhất thiết phải đổi tất cả caller trong một commit. Có thể tạo một compatibility adapter tại seam hiện tại:

~~~java
public class OrderPricing {
    private final NewOrderPricing pricing;

    public BigDecimal calculateLineTotal(
        BigDecimal unitPrice,
        int quantity,
        String currencyCode
    ) {
        Money price = Money.of(unitPrice.toPlainString(), currencyCode);
        return pricing.calculateLineTotal(price, OrderQuantity.of(quantity))
            .amount();
    }
}
~~~

Hợp đồng cũ vẫn nhận primitive; bên trong adapter chuyển sang Value Object mới. Sau đó caller có thể được chuyển dần sang API mới.

### Quy tắc khi dùng compatibility adapter

- Adapter chỉ chuyển đổi dữ liệu và gọi implementation mới.
- Không để cả adapter và implementation cùng chứa một bản logic nghiệp vụ.
- Không duy trì hai nguồn sự thật cho cùng một trạng thái.
- Ghi nhận caller nào còn dùng API cũ.
- Có thời hạn hoặc điều kiện loại bỏ adapter.
- Test tương đương giữa API cũ và API mới trong phạm vi behavior cần giữ.

### Tránh overload gây mơ hồ

Không nên tạo quá nhiều overload như:

~~~java
calculate(BigDecimal amount, String currency)
calculate(Money money)
calculate(String amount, String currency)
~~~

nếu caller khó biết nên dùng cách nào hoặc overload cũ tiếp tục được sử dụng vô thời hạn. Hãy đánh dấu API cũ deprecated khi phù hợp, ghi migration path và theo dõi usage.

## 7. Bước 3: Trích xuất Quantity và các khái niệm có đơn vị

Số lượng không phải lúc nào cũng là int. Một số sản phẩm được bán theo kg, lít, mét hoặc giờ. Quantity có thể cần đơn vị đo, precision và phép cộng/trừ hợp lệ.

~~~java
public record Quantity(BigDecimal value, UnitOfMeasure unit) {
    public Quantity {
        Objects.requireNonNull(value);
        Objects.requireNonNull(unit);
        if (value.signum() <= 0) {
            throw new InvalidQuantityException(value);
        }
    }

    public Quantity add(Quantity other) {
        if (!unit.equals(other.unit)) {
            throw new UnitMismatchException(unit, other.unit);
        }
        return new Quantity(value.add(other.value), unit);
    }
}
~~~

Ví dụ này giả định Quantity trong ngữ cảnh dòng đơn hàng phải lớn hơn không. Với tồn kho, một phép điều chỉnh có thể cho phép số lượng âm; khi đó nên phân biệt RequestedQuantity, StockDelta hoặc kiểu có semantics phù hợp thay vì nới lỏng mọi Quantity.

### Đơn vị là một phần của ngữ nghĩa

Không cộng 2 kg với 3 lít chỉ vì cả hai đều là BigDecimal. Nếu domain cho phép chuyển đổi, phép chuyển đổi cần có quy tắc và nguồn hệ số rõ ràng. Nếu không, hãy từ chối phép toán.

### Tránh Value Object quá tổng quát

Một class NumberValue dùng cho mọi đại lượng sẽ không thể hiện được sự khác nhau giữa số tiền, số lượng và tỷ lệ. Tên cụ thể giúp compiler và người đọc phát hiện nhầm lẫn sớm hơn.

## 8. Bước 4: Chuyển field primitive trong Entity sang Value Object

Giả sử legacy entity:

~~~java
public class OrderLine {
    private String productId;
    private BigDecimal unitPrice;
    private int quantity;
    private BigDecimal lineTotal;
}
~~~

Mô hình mới:

~~~java
public final class OrderLine {
    private final ProductId productId;
    private final Money unitPrice;
    private final OrderQuantity quantity;

    public OrderLine(
        ProductId productId,
        Money unitPrice,
        OrderQuantity quantity
    ) {
        this.productId = Objects.requireNonNull(productId);
        this.unitPrice = Objects.requireNonNull(unitPrice);
        this.quantity = Objects.requireNonNull(quantity);
    }

    public Money lineTotal() {
        return unitPrice.multiply(quantity.value());
    }
}
~~~

Ví dụ trên minh họa hướng chuyển đổi; trong một thiết kế thực tế, Quantity cần API rõ cho loại đơn vị và phép nhân Money × Quantity cần quy định đơn vị tương thích. Không nên đưa vào code một phép nhân tổng quát nếu Quantity có thể là kg, giờ hoặc đơn vị không tương thích với giá theo sản phẩm.

### Chuyển đổi từng field

Một lộ trình có thể là:

1. Tạo ProductId và Money.
2. Chuyển constructor/factory mới sang nhận các kiểu đó.
3. Chuyển các method nội bộ sang dùng Value Object.
4. Giữ mapper cũ ở boundary để chuyển primitive.
5. Chuyển caller theo nhóm.
6. Khi không còn caller cũ, loại bỏ API primitive.

### Không giữ hai field làm nguồn sự thật

Tránh lưu đồng thời:

~~~java
private BigDecimal totalAmount;
private Money total;
~~~

và cập nhật cả hai bằng tay. Chúng có thể lệch nhau. Nếu cần giữ representation cũ cho persistence hoặc API, hãy tính nó từ Value Object ở mapper/adapter thay vì lưu hai trạng thái độc lập.

## 9. Bước 5: Xác định invariant thuộc về đâu

Value Object bảo vệ tính hợp lệ của chính giá trị. Entity/Aggregate bảo vệ quy tắc phụ thuộc vào identity, vòng đời hoặc quan hệ giữa nhiều đối tượng.

Ví dụ:

| Quy tắc | Nơi phù hợp |
| --- | --- |
| Currency code phải được hỗ trợ | Money/Currency value type hoặc factory chính sách. |
| Quantity phải lớn hơn không trong dòng đơn hàng | Quantity theo semantics hoặc OrderLine. |
| Đơn đã hủy không thể xác nhận | Order aggregate. |
| Tổng số lượng reservation không vượt tồn kho | Inventory aggregate/context có thẩm quyền. |
| Actor có quyền xác nhận đơn | Application authorization policy/security boundary. |
| Gửi event sau khi transaction commit | Application/infrastructure qua outbox. |

### Đừng nhét mọi validation vào Value Object

Money không thể tự biết khách hàng có đủ hạn mức hay không. EmailAddress không thể tự quyết định một người có quyền truy cập tài khoản. Value Object bảo vệ quy tắc nội tại của giá trị; quy tắc liên quan đến nhiều object hoặc chính sách bên ngoài thuộc nơi khác.

### Invariant phải được bảo vệ trên mọi đường ghi

Nếu aggregate chỉ được tạo hợp lệ qua factory nhưng ORM hoặc mapper có thể nạp dữ liệu sai, cần có cơ chế reconstitution/validation phù hợp. Nếu có batch job hoặc service khác ghi database, cần database constraint hoặc ranh giới tích hợp để bảo vệ dữ liệu. Chỉ chuyển một class sang Value Object không tự sửa được mọi đường ghi.

## 10. Bước 6: Trích xuất hành vi miền khỏi procedural service

Legacy service thường chứa nhiều đoạn code đọc field, kiểm tra trạng thái rồi cập nhật trực tiếp:

~~~java
public void confirmOrder(String orderId) {
    OrderRow row = repository.find(orderId);
    if (!"ACCEPTED".equals(row.getStatus())) {
        throw new IllegalStateException("Cannot confirm");
    }
    if (row.getLineCount() == 0) {
        throw new IllegalStateException("Empty order");
    }
    row.setStatus("CONFIRMED");
    row.setConfirmedAt(Instant.now());
    repository.update(row);
}
~~~

Quy tắc xác nhận đang nằm trong service và thao tác trực tiếp trên persistence row. Có thể chuyển từng bước:

1. Xác định invariant xác nhận đơn với chuyên gia nghiệp vụ.
2. Tạo domain model Order có trạng thái rõ.
3. Chuyển kiểm tra trạng thái và dòng hàng vào method confirm.
4. Đưa thời điểm vào tham số để dễ kiểm thử.
5. Ghi Domain Event khi hành vi thành công.
6. Application handler điều phối load, authorization và save.

### Hành vi mới trong Aggregate

~~~java
public final class Order {
    private final OrderId id;
    private final List<OrderLine> lines;
    private OrderStatus status;
    private Instant confirmedAt;
    private final List<DomainEvent> domainEvents = new ArrayList<>();

    public void confirm(Instant now) {
        if (status != OrderStatus.ACCEPTED) {
            throw new OrderCannotBeConfirmedException(id, status);
        }
        if (lines.isEmpty()) {
            throw new EmptyOrderCannotBeConfirmedException(id);
        }

        status = OrderStatus.CONFIRMED;
        confirmedAt = Objects.requireNonNull(now);
        domainEvents.add(new OrderConfirmed(id, now));
    }

    public List<DomainEvent> pullDomainEvents() {
        List<DomainEvent> pending = List.copyOf(domainEvents);
        domainEvents.clear();
        return pending;
    }
}
~~~

Ví dụ lược giản constructor và collection policy. Aggregate giữ trạng thái và quyết định có thể chuyển từ ACCEPTED sang CONFIRMED không. Caller không được tự gán status để bỏ qua quy tắc.

### Application Service vẫn có vai trò

Sau khi chuyển hành vi vào domain:

~~~java
@Service
public class ConfirmOrderHandler {
    private final OrderRepository orders;
    private final OrderAccessPolicy accessPolicy;
    private final Clock clock;

    @Transactional
    public void handle(ConfirmOrder command) {
        Order order = orders.findById(command.orderId())
            .orElseThrow(OrderNotFoundException::new);

        accessPolicy.ensureCanConfirm(command.actorId(), order);
        order.confirm(clock.instant());
        orders.save(order);
    }
}
~~~

Application Service không biến mất. Nó tiếp tục điều phối use case, transaction, authorization và persistence. Domain model sở hữu quyết định nghiệp vụ bên trong aggregate.

## 11. Bước 7: Phân biệt Entity, Value Object và Domain Service

Khi refactor, có thể gặp quy tắc không rõ nên đặt ở đâu.

### Entity

Entity có identity và vòng đời. Hành vi phụ thuộc identity hoặc trạng thái của chính đối tượng thường thuộc entity/aggregate.

Ví dụ: Order.confirm(), Subscription.cancel(), Account.debit().

### Value Object

Value Object được xác định bởi giá trị, thường bất biến. Phép toán và validation nội tại thuộc value type.

Ví dụ: Money.add(), DateRange.overlaps(), Quantity.convertTo() nếu quy tắc chuyển đổi thuộc khái niệm đó.

### Domain Service

Domain Service phù hợp khi quy tắc nghiệp vụ không tự nhiên thuộc về một Entity hoặc Value Object, nhưng vẫn là logic miền. Ví dụ tính phí vận chuyển dựa trên nhiều yếu tố độc lập hoặc chính sách phân bổ phức tạp.

~~~java
public final class ShippingFeePolicy {
    public Money calculate(
        DeliveryAddress destination,
        Weight totalWeight,
        ShippingMethod method
    ) {
        // Quy tắc nghiệp vụ tính phí vận chuyển.
    }
}
~~~

Không nên chuyển mọi hàm từ service cũ thành Domain Service. Nếu logic là điều phối repository, transaction, HTTP hoặc message broker thì đó là application/infrastructure responsibility.

### Dùng câu hỏi để quyết định

- Quy tắc có thuộc bản chất của một giá trị không? → Value Object.
- Quy tắc phụ thuộc identity/vòng đời/trạng thái của một entity? → Entity/Aggregate.
- Quy tắc miền kết hợp nhiều đối tượng mà không thuộc tự nhiên về một đối tượng? → Domain Service.
- Quy tắc chỉ điều phối một use case? → Application Service.
- Quy tắc giao tiếp database hoặc hệ thống ngoài? → Infrastructure adapter.

## 12. Bước 8: Tạo Anti-Corruption Layer ở ranh giới legacy

Trong quá trình chuyển đổi, mô hình mới có thể cần giao tiếp với API hoặc database cũ. Không nên để kiểu dữ liệu và tên gọi legacy lan vào domain model mới.

Anti-Corruption Layer (ACL) chuyển đổi giữa hai mô hình:

~~~java
public final class LegacyOrderAdapter {
    private final LegacyOrderGateway legacyGateway;

    public OrderSnapshot load(OrderId id) {
        LegacyOrderRecord record = legacyGateway.find(id.value());

        return new OrderSnapshot(
            new OrderId(record.orderCode()),
            mapStatus(record.statusCode()),
            mapLines(record.lines()),
            Instant.parse(record.createdAt())
        );
    }

    private OrderStatus mapStatus(String code) {
        return switch (code) {
            case "A" -> OrderStatus.ACCEPTED;
            case "C" -> OrderStatus.CONFIRMED;
            case "X" -> OrderStatus.CANCELLED;
            default -> throw new UnknownLegacyOrderStatus(code);
        };
    }
}
~~~

Ví dụ minh họa mapping. Mã trạng thái không nhận diện được nên được phát hiện rõ, không tự đổi sang trạng thái mặc định có thể gây sai nghiệp vụ.

ACL giúp:

- Domain model mới dùng ngôn ngữ của bounded context mới.
- Thay đổi schema legacy được cô lập ở adapter.
- Có thể thay nguồn dữ liệu cũ sau này mà ít ảnh hưởng domain.
- Mapping và lỗi dữ liệu lịch sử có nơi xử lý rõ ràng.

### Không biến ACL thành nơi chứa domain logic mới

Adapter nên chuyển đổi representation và xử lý khác biệt hợp đồng. Quy tắc như đơn có thể xác nhận không nên nằm trong mapping status từ "A" sang ACCEPTED. Quy tắc đó thuộc aggregate.

## 13. Bước 9: Di chuyển dữ liệu theo Expand-and-Contract

Khi Value Object hoặc domain model mới thay đổi cách lưu dữ liệu, không nên đổi schema và code cùng lúc nếu có nhiều phiên bản ứng dụng đang chạy.

Expand-and-contract chia migration thành các bước tương thích.

### Expand

- Thêm cột/bảng hoặc cấu trúc mới mà code cũ vẫn hoạt động.
- Triển khai reader có thể đọc representation mới và cũ theo chính sách rõ.
- Chuẩn bị backfill dữ liệu cũ.
- Xác định nguồn có thẩm quyền trong giai đoạn chuyển tiếp.

### Migrate

- Backfill dữ liệu cũ sang representation mới.
- Chạy theo batch có checkpoint.
- Có thể so sánh dữ liệu cũ và mới.
- Theo dõi record lỗi hoặc không thể chuyển đổi.
- Chuyển từng caller sang API/model mới.

### Contract

- Xác nhận không còn caller dùng representation cũ.
- Ngừng ghi/đọc cột cũ.
- Xóa cột/bảng/adapter cũ trong một đợt triển khai riêng.
- Dọn code tương thích sau khi hết thời hạn rollback.

~~~mermaid
flowchart LR
    A[Expand schema]
    B[Deploy compatible code]
    C[Backfill and verify]
    D[Move callers]
    E[Stop legacy usage]
    F[Contract old schema]
    A --> B --> C --> D --> E --> F
~~~

### Tránh dual-write không kiểm soát

Nếu một request ghi cả cột cũ và cột mới bằng hai thao tác độc lập, một thao tác có thể thành công còn thao tác kia thất bại. Dữ liệu lệch nhau sẽ khó sửa.

Nếu bắt buộc ghi hai representation trong giai đoạn chuyển đổi, cần một transaction bảo vệ cả hai khi cùng database, hoặc một cơ chế đồng bộ có idempotency/reconciliation nếu khác resource. Tốt hơn là xác định một nguồn có thẩm quyền và coi representation còn lại là projection có thể tái tạo.

### Backfill phải an toàn khi chạy lại

Backfill nên:

- Có khóa/checkpoint xác định vị trí đã xử lý.
- Có batch size và giới hạn tải.
- Có thể chạy lại mà không nhân đôi dữ liệu.
- Ghi nhận record không chuyển đổi được.
- Có số liệu trước/sau để đối soát.
- Không ghi đè thay đổi mới hơn từ ứng dụng đang chạy.

## 14. Bước 10: Chuyển đổi caller theo từng đợt

Sau khi có Value Object và hành vi miền, hãy chuyển caller theo mức độ rủi ro.

Ví dụ:

1. Chuyển một command handler nội bộ.
2. Chuyển một API adapter.
3. Chuyển một batch job.
4. Chuyển message consumer.
5. Chuyển báo cáo hoặc query projection.
6. Loại bỏ compatibility adapter khi không còn usage.

### Branch by Abstraction

Branch by Abstraction tạo một interface ổn định trước, rồi chuyển implementation phía sau:

~~~java
public interface OrderConfirmation {
    void confirm(OrderId orderId, UserId actorId);
}
~~~

Implementation cũ có thể gọi service thủ tục; implementation mới tải aggregate và gọi hành vi miền. Caller chỉ phụ thuộc interface. Khi implementation mới đã được xác minh, chuyển binding sang implementation mới rồi loại bỏ code cũ.

### Feature flag

Feature flag có thể bật luồng mới cho một nhóm tenant hoặc tỷ lệ traffic nhỏ. Cần bảo đảm hai luồng không cùng thực hiện một command cho cùng request. Flag nên quyết định một implementation được chọn, không làm cả hai implementation chạy song song rồi cùng ghi.

### Không giữ hai implementation mãi mãi

Compatibility code có chi phí: test matrix lớn hơn, hai cách xử lý có thể lệch và đội phải hiểu cả hai. Mỗi adapter/flag nên có owner, tiêu chí kết thúc và kế hoạch xóa.

## 15. So sánh kết quả cũ và mới

Trong một số phạm vi, có thể chạy logic cũ và mới trên cùng input để so sánh kết quả nhưng chỉ cho một implementation tạo side effect.

Ví dụ:

- Legacy calculator tính total.
- Domain model mới tính total.
- Test hoặc shadow computation so sánh kết quả.
- Chỉ implementation được chọn ghi database hoặc phát event.

### Shadow mode không có nghĩa dual execution đầy đủ

Không chạy hai luồng cùng gửi thanh toán, giữ hàng hoặc gửi email. Nếu cần shadow, implementation phụ phải thuần hoặc bị chặn quyền ghi/tác động ngoài.

### Sai khác cần phân loại

- Sai khác do bug legacy đã biết.
- Sai khác do quy tắc mới được nghiệp vụ phê duyệt.
- Sai khác do rounding/precision.
- Sai khác do dữ liệu lịch sử không chuẩn.
- Sai khác do thứ tự hoặc concurrency.
- Sai khác do timezone, locale hoặc currency.

Không tự động sửa output mới để giống legacy nếu legacy đang sai. Cần phân biệt mục tiêu “giữ behavior” với mục tiêu “sửa nghiệp vụ”.

## 16. Ví dụ xuyên suốt: chuyển dòng đơn hàng sang Value Object và behavior

### Trạng thái ban đầu

~~~java
public class LegacyOrderService {
    public BigDecimal lineTotal(
        BigDecimal price,
        int quantity
    ) {
        if (price.signum() < 0 || quantity <= 0) {
            throw new IllegalArgumentException();
        }
        return price.multiply(BigDecimal.valueOf(quantity));
    }

    public void confirm(LegacyOrderRow row) {
        if (!"ACCEPTED".equals(row.getStatus())) {
            throw new IllegalStateException();
        }
        row.setStatus("CONFIRMED");
        repository.update(row);
    }
}
~~~

### Giai đoạn A: bảo vệ behavior

- Viết characterization test cho lineTotal và confirm.
- Ghi nhận rounding, status code và exception hiện tại.
- Kiểm tra caller của LegacyOrderService.
- Chọn một use case để chuyển trước.

### Giai đoạn B: trích xuất Value Object

~~~java
public record UnitPrice(Money value) {
    public UnitPrice {
        Objects.requireNonNull(value);
        if (value.amount().signum() < 0) {
            throw new InvalidUnitPriceException(value);
        }
    }
}

public record OrderQuantity(int value) {
    public OrderQuantity {
        if (value <= 0) {
            throw new InvalidOrderQuantityException(value);
        }
    }

    public static OrderQuantity of(int value) {
        return new OrderQuantity(value);
    }
}
~~~

Các kiểu cụ thể thể hiện semantics: UnitPrice không phải mọi Money; OrderQuantity khác một bộ đếm tùy ý. Nếu Quantity có đơn vị đo, hãy dùng mô hình phù hợp thay vì int.

### Giai đoạn C: chuyển phép tính

~~~java
public final class OrderLine {
    private final ProductId productId;
    private final UnitPrice unitPrice;
    private final OrderQuantity quantity;

    public Money subtotal() {
        return unitPrice.value().multiply(quantity.value());
    }
}
~~~

Phép tính subtotal giờ nằm cùng khái niệm dòng hàng. Nếu thuế, discount hoặc rounding có quy tắc riêng, hãy đưa chúng vào policy/value object phù hợp thay vì nhồi mọi thứ vào một công thức.

### Giai đoạn D: chuyển hành vi xác nhận

~~~java
public void confirm(Instant now) {
    if (status != OrderStatus.ACCEPTED) {
        throw new OrderCannotBeConfirmedException(id, status);
    }
    if (lines.isEmpty()) {
        throw new EmptyOrderCannotBeConfirmedException(id);
    }
    status = OrderStatus.CONFIRMED;
    confirmedAt = now;
    recordEvent(new OrderConfirmed(id, now));
}
~~~

Application handler tải Order, kiểm tra authorization, gọi confirm, lưu aggregate và ghi outbox. Persistence mapper chuyển status enum sang mã cũ nếu schema chưa thể thay đổi ngay.

### Giai đoạn E: chuyển caller và schema

- Caller mới dùng OrderQuantity, UnitPrice và Money.
- API cũ tiếp tục nhận primitive qua adapter.
- Backfill currency và dữ liệu giá theo chính sách đã xác nhận.
- Theo dõi usage của API cũ.
- Khi tất cả caller đã chuyển, bỏ adapter và schema cũ trong đợt contract.

## 17. Rollout, quan sát và rollback

Một đợt migration cần kế hoạch triển khai:

### Trước rollout

- Test domain và characterization đều pass.
- Có test integration cho persistence mapping.
- Có dữ liệu backfill và báo cáo đối soát.
- Xác định feature flag/traffic cohort.
- Có dashboard lỗi, latency và business metric.
- Có cách tắt implementation mới hoặc chuyển lại adapter cũ.

### Trong rollout

- Chuyển một nhóm caller/tenant nhỏ.
- Theo dõi exception, validation rejection và transaction conflict.
- So sánh output cũ/mới nếu có shadow computation.
- Theo dõi số record không map được.
- Theo dõi event, outbox và các tác động ngoài.
- Dừng mở rộng nếu sai khác vượt ngưỡng đã định.

### Sau rollout

- Xác nhận business metric và dữ liệu đúng.
- Chuyển hết caller theo kế hoạch.
- Giữ rollback window đủ dài.
- Loại bỏ flag/adapter cũ khi đã an toàn.
- Cập nhật tài liệu và ownership của mô hình mới.

### Rollback code không tự rollback dữ liệu

Nếu code mới đã ghi representation mới hoặc phát event mới, quay lại binary cũ có thể không đọc được dữ liệu đó. Vì vậy:

- Giữ schema tương thích trong thời gian chuyển tiếp.
- Không ghi format mới mà code cũ không hiểu trước khi rollout hoàn tất.
- Có forward-fix hoặc data repair plan.
- Xác định rõ điều kiện rollback ứng dụng và điều kiện rollback dữ liệu.
- Không xóa dữ liệu cũ trước khi hết rollback window.

## 18. Những sai lầm thường gặp

- **Rewrite toàn bộ module cùng lúc:** phạm vi lớn, khó biết thay đổi nào gây regression.
- **Tạo Value Object mà không có semantics:** chỉ bọc BigDecimal/String nhưng không thêm validation, equality hoặc hành vi có ích.
- **Trích xuất quá nhiều class nhỏ:** làm mô hình khó theo dõi mà không thể hiện quy tắc nghiệp vụ.
- **Không viết characterization test:** refactor có thể vô tình đổi rounding, error hoặc side effect.
- **Đóng băng bug legacy thành specification:** giữ nguyên kết quả sai mà không có quyết định nghiệp vụ.
- **Đưa mọi validation vào Value Object:** quy tắc liên quan nhiều entity hoặc authorization bị đặt sai chỗ.
- **Để domain gọi repository/HTTP:** domain model bị gắn với infrastructure.
- **Giữ logic ở cả service cũ và aggregate mới:** hai nguồn quyết định có thể lệch nhau.
- **Lưu đồng thời primitive và Value Object như hai nguồn sự thật:** dữ liệu có thể không đồng bộ.
- **Chuyển tất cả caller trong một đợt:** khó rollback và khó xác định phạm vi lỗi.
- **Dual-write không có transaction hoặc reconciliation:** representation cũ/mới có thể lệch.
- **Backfill không idempotent:** chạy lại tạo bản ghi trùng hoặc ghi đè dữ liệu mới.
- **Shadow mode vẫn cho phép side effect:** hai implementation có thể cùng thu tiền hoặc giữ hàng.
- **Feature flag không có ngày loại bỏ:** hệ thống duy trì hai đường code vô thời hạn.
- **Rollback binary nhưng không xét schema/event:** phiên bản cũ có thể không đọc được dữ liệu mới.
- **Không đo caller còn dùng API cũ:** adapter không bao giờ được xóa.

## 19. Quy trình trích xuất Value Object và behavior

Với một khái niệm legacy, có thể thực hiện theo thứ tự:

1. **Chọn phạm vi:** xác định use case, caller và dữ liệu liên quan.
2. **Hiểu ngôn ngữ:** hỏi chuyên gia nghiệp vụ tên, ý nghĩa, đơn vị và quy tắc.
3. **Ghi nhận behavior:** viết characterization test và specification test cho quy tắc đã xác nhận.
4. **Tìm primitive obsession:** xác định kiểu nguyên thủy nào đang đại diện cho khái niệm có semantics.
5. **Tạo Value Object:** constructor/factory bảo vệ invariant nội tại, equality theo giá trị và immutable.
6. **Giữ seam tương thích:** chuyển primitive ở adapter, không để hai implementation nghiệp vụ.
7. **Chuyển field và caller:** từng nhóm, có test và theo dõi usage.
8. **Tìm invariant cấp Entity/Aggregate:** chuyển quy tắc trạng thái và quan hệ vào hành vi miền.
9. **Giữ orchestration ở Application Service:** transaction, authorization và repository nằm đúng boundary.
10. **Cô lập legacy:** dùng mapper/ACL để chuyển representation và lỗi dữ liệu.
11. **Di chuyển dữ liệu:** expand, backfill, verify, move callers rồi contract.
12. **Rollout có kiểm soát:** feature flag/cohort, metrics, shadow thuần và rollback plan.
13. **Dọn compatibility:** xóa adapter, field và đường code cũ khi không còn caller.
14. **Đánh giá lại:** xác nhận mô hình mới làm ngôn ngữ và invariant rõ hơn.

## Checklist rà soát

- [ ] Đã chọn một seam nhỏ, hiểu caller và tác động trong phạm vi.
- [ ] Có characterization test cho behavior legacy quan trọng.
- [ ] Quy tắc nghiệp vụ mới đã được xác nhận với chuyên gia.
- [ ] Value Object biểu diễn một khái niệm có semantics rõ.
- [ ] Value Object bất biến, có validation và equality theo giá trị.
- [ ] Đơn vị đo, currency, precision và rounding được xác định.
- [ ] Không tạo class wrapper không có giá trị mô hình hóa.
- [ ] Invariant nội tại thuộc Value Object; invariant trạng thái thuộc Entity/Aggregate.
- [ ] Application Service tiếp tục điều phối use case và transaction.
- [ ] Compatibility adapter chỉ chuyển đổi, không nhân đôi business logic.
- [ ] Không có hai field/implementation cùng là nguồn sự thật.
- [ ] Legacy model được cô lập qua mapper hoặc Anti-Corruption Layer.
- [ ] Data backfill có checkpoint, idempotency và reconciliation.
- [ ] Không dual-write qua nhiều resource mà thiếu cơ chế bảo đảm.
- [ ] Caller được chuyển theo từng đợt và usage cũ được theo dõi.
- [ ] Shadow mode không tạo side effect hai lần.
- [ ] Rollout có metrics, feature flag và rollback plan.
- [ ] Schema/event mới vẫn tương thích với phiên bản đang chạy trong giai đoạn chuyển tiếp.
- [ ] Compatibility code có tiêu chí và thời điểm loại bỏ.

## Kết luận

Trích xuất Value Object và hành vi miền là một quá trình cải thiện mô hình theo từng bước. Hãy bắt đầu bằng việc hiểu một luồng nghiệp vụ nhỏ và ghi nhận behavior hiện tại bằng test. Sau đó tạo Value Object có semantics, validation và equality rõ ràng; chuyển caller qua adapter; đưa invariant và hành vi trạng thái về Entity/Aggregate; giữ transaction và orchestration ở Application Service. Khi dữ liệu hoặc API phải thay đổi, dùng expand-and-contract, backfill có thể chạy lại, rollout theo nhóm và quan sát kết quả. Cách làm này giúp mô hình DDD hình thành từ hệ thống đang hoạt động, giảm rủi ro rewrite và cho phép đội kiểm chứng từng thay đổi trước khi loại bỏ legacy path.
