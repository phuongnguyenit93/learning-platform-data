# Kiểm thử quy tắc, hành vi và bất biến nghiệp vụ độc lập với hạ tầng

Bài học này thuộc module `SOFTWARE_DESIGN_ARCHITECTURE_ARCHITECTURAL_PATTERN_LAYERED`, nhằm giúp người học tổ chức phần mềm theo kiến trúc phân tầng. Trong chương **Chiến lược kiểm thử**, ta tập trung kiểm thử mô hình nghiệp vụ mà không cần khởi động Spring, kết nối cơ sở dữ liệu hoặc gọi dịch vụ bên ngoài. Mục tiêu là xác minh các hành vi và bất biến mà miền phải bảo vệ, để lỗi quy tắc được phát hiện nhanh và không phụ thuộc vào cách ứng dụng triển khai hạ tầng.

## 1. Điều gì cần được kiểm thử ở mô hình nghiệp vụ?

Mô hình nghiệp vụ biểu diễn khái niệm, trạng thái, hành vi và chính sách của lĩnh vực mà phần mềm phục vụ. Một đối tượng miền không chỉ chứa dữ liệu; nó cần bảo đảm các thao tác làm thay đổi dữ liệu tuân thủ quy tắc.

Ví dụ với đơn hàng, các quy tắc có thể gồm:

- Đơn hàng phải có ít nhất một dòng hàng.
- Số lượng của mỗi dòng hàng phải lớn hơn 0.
- Các khoản tiền trong cùng một phép tính phải dùng cùng loại tiền tệ.
- Đơn đã giao không thể bị hủy.
- Chỉ đơn đã được thanh toán mới có thể chuyển sang trạng thái đang giao.
- Tổng tiền phải bằng tổng giá trị các dòng hàng theo chính sách làm tròn đã chọn.

Đây là những điều kiện thuộc nghiệp vụ, cần đúng bất kể yêu cầu đến từ REST API, tác vụ nền, message consumer hay giao diện quản trị. Vì vậy, kiểm thử chúng trực tiếp trên entity, aggregate, value object hoặc domain service giúp xác nhận quy tắc tại nơi sở hữu nó.

Một **bất biến (invariant)** là điều kiện phải luôn đúng đối với đối tượng hoặc phạm vi miền được xác định. Bất biến được kiểm tra khi khởi tạo và sau mỗi hành vi công khai có thể thay đổi trạng thái. Ví dụ, `Order` không được rơi vào trạng thái có danh sách dòng hàng rỗng sau khi đã được tạo.

## 2. Vì sao kiểm thử miền nên độc lập với hạ tầng?

Kiểm thử quy tắc miền thường chỉ cần tạo đối tượng, gọi hành vi và kiểm tra kết quả. Nếu một unit test phải khởi động Spring, dựng database, chạy migration và tạo HTTP request chỉ để kiểm tra việc đơn đã giao không thể hủy, ranh giới giữa nghiệp vụ và hạ tầng có thể đang bị trộn lẫn.

Kiểm thử miền độc lập mang lại một số lợi ích:

- **Phản hồi nhanh:** không phải khởi động container ứng dụng hoặc dịch vụ phụ trợ.
- **Kết quả ổn định:** ít phụ thuộc vào mạng, trạng thái database, đồng hồ hệ thống hoặc cấu hình môi trường.
- **Lỗi dễ định vị:** khi test `Order.cancel()` thất bại, nguyên nhân thường nằm trong hành vi hoặc quy tắc của mô hình đó.
- **Thiết kế rõ hơn:** mô hình miền không cần gọi repository, đọc HTTP request hoặc lấy dữ liệu từ Spring context để bảo vệ bất biến.
- **Kiểm thử nhiều trường hợp:** có thể thử ranh giới và tổ hợp đầu vào mà không tốn chi phí thiết lập môi trường.

Độc lập với hạ tầng không có nghĩa mọi lớp miền phải hoàn toàn không có dependency. Một domain service có thể cần một clock hoặc một chính sách được tiêm vào. Điều cần tránh là để quy tắc phụ thuộc trực tiếp vào cơ sở dữ liệu, web framework, message broker hoặc dịch vụ bên ngoài khi những phụ thuộc đó không phải bản chất của quy tắc.

## 3. Kiểm thử hành vi công khai thay vì chi tiết triển khai

Một unit test tốt mô tả hành vi mà người dùng mô hình hoặc thành phần gọi có thể quan sát. Test nên gọi phương thức công khai như `cancel()`, `reserve()` hoặc `calculateTotal()` rồi xác minh kết quả, trạng thái hoặc lỗi theo hợp đồng.

Không nên kiểm thử trực tiếp phương thức `private`, số lần một getter nội bộ được gọi hay thứ tự các câu lệnh trong một phương thức nếu thứ tự đó không phải hành vi có ý nghĩa với caller. Các kiểm thử như vậy thường bị hỏng khi tái cấu trúc dù quy tắc nghiệp vụ không thay đổi.

Ví dụ, thay vì kiểm tra `Order` có gọi một phương thức nội bộ tên `validateStatus()` hay không, hãy kiểm tra rằng đơn đã giao bị từ chối khi gọi `cancel()` và trạng thái vẫn là `SHIPPED`.

## 4. Ví dụ mô hình miền và bất biến

Giả sử một đơn hàng có các dòng hàng và trạng thái. Ta định nghĩa hành vi cùng bất biến ngay trong mô hình:

```java
package com.example.orders.domain;

import java.util.List;

public final class Order {
    private final OrderId id;
    private final List<OrderLine> lines;
    private OrderStatus status;

    private Order(OrderId id, List<OrderLine> lines) {
        if (id == null) {
            throw new IllegalArgumentException("Order ID is required");
        }
        if (lines == null || lines.isEmpty()) {
            throw new EmptyOrderException();
        }

        this.id = id;
        this.lines = List.copyOf(lines);
        this.status = OrderStatus.PLACED;
    }

    public static Order place(OrderId id, List<OrderLine> lines) {
        return new Order(id, lines);
    }

    public void cancel() {
        if (status != OrderStatus.PLACED) {
            throw new OrderCannotBeCancelledException(id, status);
        }
        status = OrderStatus.CANCELLED;
    }

    public void markAsPaid() {
        if (status != OrderStatus.PLACED) {
            throw new InvalidOrderTransitionException(status, OrderStatus.PAID);
        }
        status = OrderStatus.PAID;
    }

    public void ship() {
        if (status != OrderStatus.PAID) {
            throw new InvalidOrderTransitionException(status, OrderStatus.SHIPPED);
        }
        status = OrderStatus.SHIPPED;
    }

    public OrderId id() { return id; }
    public List<OrderLine> lines() { return lines; }
    public OrderStatus status() { return status; }
}
```

`OrderId`, `OrderLine`, `OrderStatus` và các exception là những kiểu miền được giả định đã định nghĩa. Constructor riêng buộc caller tạo đơn qua factory `place`, nhờ đó điều kiện đơn phải có dòng hàng được kiểm tra ngay khi khởi tạo. `List.copyOf` giữ danh sách không bị caller sửa sau khi tạo đơn. Các phương thức công khai kiểm soát chuyển trạng thái.

Ta có thể viết unit test bằng JUnit 5:

```java
package com.example.orders.domain;

import static org.junit.jupiter.api.Assertions.*;

import java.util.List;
import org.junit.jupiter.api.Test;

class OrderTest {
    @Test
    void placingOrderCreatesPlacedOrderWithItsLines() {
        OrderLine line = anOrderLine("BOOK-1", 2);

        Order order = Order.place(new OrderId("ORD-1"), List.of(line));

        assertEquals(OrderStatus.PLACED, order.status());
        assertEquals(1, order.lines().size());
        assertEquals("ORD-1", order.id().value());
    }

    @Test
    void cannotPlaceOrderWithoutLines() {
        assertThrows(EmptyOrderException.class,
            () -> Order.place(new OrderId("ORD-2"), List.of()));
    }

    @Test
    void placedOrderCanBeCancelled() {
        Order order = anOrder();

        order.cancel();

        assertEquals(OrderStatus.CANCELLED, order.status());
    }

    @Test
    void shippedOrderCannotBeCancelledAndKeepsItsState() {
        Order order = anOrder();
        order.markAsPaid();
        order.ship();

        assertThrows(OrderCannotBeCancelledException.class, order::cancel);

        assertEquals(OrderStatus.SHIPPED, order.status());
    }

    private static Order anOrder() {
        return Order.place(new OrderId("ORD-1"),
            List.of(anOrderLine("BOOK-1", 2)));
    }

    private static OrderLine anOrderLine(String productId, int quantity) {
        return new OrderLine(new ProductId(productId), quantity);
    }
}
```

Test không cần `@SpringBootTest`, repository mock hoặc database. Mỗi test tạo trạng thái ban đầu rõ ràng, gọi một hành vi và xác minh kết quả. Test `shippedOrderCannotBeCancelledAndKeepsItsState` kiểm tra cả việc từ chối lẫn việc không làm thay đổi trạng thái khi hành động thất bại.

## 5. Kiểm thử bất biến ở nhiều điểm biên

Không chỉ kiểm thử trường hợp hợp lệ. Bất biến thường bị phá vỡ ở giá trị biên hoặc khi một thao tác bị gọi sai thứ tự. Với từng hành vi, hãy xác định:

- Điều kiện hợp lệ tối thiểu và tối đa.
- Giá trị ngay dưới, đúng tại và ngay trên ngưỡng.
- Trạng thái trước khi gọi hành vi.
- Trạng thái mong muốn sau thành công.
- Trạng thái phải được giữ nguyên khi hành động bị từ chối.
- Những trường hợp null, rỗng hoặc dữ liệu không tương thích nếu hợp đồng cho phép caller truyền vào.

Ví dụ với số lượng đặt hàng phải lớn hơn 0 và không vượt quá tồn kho:

| Đầu vào | Kết quả mong đợi |
|---|---|
| `quantity = -1` | Từ chối vì số lượng âm |
| `quantity = 0` | Từ chối vì số lượng phải dương |
| `quantity = 1`, tồn kho `1` | Thành công, tồn kho còn `0` |
| `quantity = 2`, tồn kho `1` | Từ chối vì không đủ hàng; tồn kho không đổi |

Một test có thể xác minh hai điều kiện cùng lúc: lỗi đúng loại và trạng thái không bị cập nhật một phần.

```java
@Test
void reserveMoreThanAvailableDoesNotChangeStock() {
    Stock stock = new Stock(new ProductId("BOOK-1"), 4);

    assertThrows(InsufficientStockException.class,
        () -> stock.reserve(5));

    assertEquals(4, stock.available());
    assertEquals(0, stock.reserved());
}
```

Test này cần xác nhận hành vi từ chối không để lại trạng thái nửa chừng. Nếu phương thức có nhiều bước cập nhật, mô hình nên kiểm tra tất cả điều kiện trước khi thay đổi hoặc thiết kế sao cho thao tác có tính nguyên tử ở cấp đối tượng.

## 6. Kiểm thử Value Object và phép tính

Value object thường có quy tắc ngay khi khởi tạo và trong các phép toán. Ví dụ `Money` có số tiền và loại tiền tệ; phép cộng chỉ hợp lệ khi hai giá trị cùng currency.

```java
public record Money(long minorUnits, Currency currency) {
    public Money {
        if (currency == null) {
            throw new IllegalArgumentException("Currency is required");
        }
    }

    public Money add(Money other) {
        if (!currency.equals(other.currency())) {
            throw new CurrencyMismatchException(currency, other.currency());
        }
        return new Money(minorUnits + other.minorUnits, currency);
    }
}
```

Các kiểm thử nên bao gồm phép cộng cùng loại tiền, từ chối khác loại tiền, giá trị âm nếu nghiệp vụ có cho phép hay không, và các trường hợp biên của độ chính xác. Với tiền, không nên dùng `double` cho phép tính chính xác; hãy chọn kiểu số nguyên theo đơn vị nhỏ nhất hoặc `BigDecimal` cùng chính sách scale/rounding được xác định rõ.

```java
@Test
void addingMoneyWithDifferentCurrenciesIsRejected() {
    Money vnd = new Money(100_000, Currency.getInstance("VND"));
    Money usd = new Money(500, Currency.getInstance("USD"));

    assertThrows(CurrencyMismatchException.class, () -> vnd.add(usd));
}
```

Với value object bất biến, test còn có thể xác minh phép toán tạo ra giá trị mới và không làm thay đổi toán hạng ban đầu. Cần kiểm tra `equals` và `hashCode` theo ngữ nghĩa giá trị nếu chúng được dùng làm key trong collection.

## 7. Kiểm thử Domain Service và chính sách nghiệp vụ

Một quy tắc có thể liên quan đến nhiều đối tượng mà không thuộc tự nhiên về một entity cụ thể. Khi đó có thể đặt nó trong domain service hoặc policy. Ví dụ chính sách giảm giá phụ thuộc vào hạng thành viên và tổng giá trị giỏ hàng.

```java
public final class DiscountPolicy {
    public Percentage discountFor(
            MembershipLevel level,
            Money cartTotal) {
        if (cartTotal.isNegative()) {
            throw new InvalidCartTotalException();
        }

        return switch (level) {
            case BASIC -> Percentage.ZERO;
            case SILVER -> cartTotal.amountAtLeast(100_00)
                ? Percentage.of(5) : Percentage.ZERO;
            case GOLD -> cartTotal.amountAtLeast(100_00)
                ? Percentage.of(10) : Percentage.of(5);
        };
    }
}
```

Đây là ví dụ minh họa; `Money`, `Percentage` và phương thức so sánh cần dùng cùng đơn vị tiền tệ. Unit test của policy chỉ cần đưa các giá trị miền vào và kiểm tra mức giảm. Không cần tải thành viên từ database trong test này. Việc lấy dữ liệu và phối hợp repository thuộc use case ở tầng ứng dụng.

Nếu domain service thật sự phụ thuộc một nguồn dữ liệu hoặc dịch vụ ngoài, hãy xem xét tách phần quyết định thuần khỏi phần truy xuất. Có thể truyền các giá trị đã tải vào policy, hoặc định nghĩa một cổng phù hợp khi phụ thuộc là một phần không thể tránh của hợp đồng. Mục tiêu là kiểm thử quy tắc mà không cần dựng hệ thống bên ngoài.

## 8. Kiểm thử thời gian, ngẫu nhiên và các nguồn không xác định

Quy tắc có thể phụ thuộc thời gian, chẳng hạn đơn hàng chỉ được hủy trong vòng 24 giờ. Nếu mô hình gọi trực tiếp `Instant.now()` hoặc `LocalDate.now()`, test có thể phụ thuộc thời điểm chạy và trở nên khó lặp lại.

Hãy đưa `Clock` hoặc thời điểm hiện tại vào hành vi:

```java
public boolean canCancel(Instant requestedAt) {
    return status == OrderStatus.PLACED
        && !requestedAt.isAfter(cancellationDeadline);
}
```

Hoặc truyền `Clock` qua một domain service nếu việc đọc thời gian là trách nhiệm của service đó. Trong test, dùng `Clock.fixed(...)` hoặc truyền `Instant` cụ thể để kiểm tra đúng tại hạn, trước hạn và sau hạn.

Tương tự, nếu quy tắc cần sinh ID ngẫu nhiên, hãy tiêm một `IdGenerator` hoặc tạo ID ở application layer rồi truyền vào factory. Test có thể dùng generator cố định để kết quả lặp lại được. Không nên phụ thuộc vào `Thread.sleep`, đồng hồ máy hoặc thứ tự ngẫu nhiên của collection để kiểm tra quy tắc.

## 9. Kiểm thử theo bảng trường hợp và kiểm thử dựa trên thuộc tính

Với quy tắc có nhiều giá trị đầu vào, kiểm thử tham số hóa giúp tránh lặp code và làm rõ các trường hợp biên.

```java
@ParameterizedTest
@CsvSource({
    "1, true",
    "0, false",
    "-1, false"
})
void quantityMustBePositive(int quantity, boolean valid) {
    if (valid) {
        assertDoesNotThrow(() -> new OrderLine(
            new ProductId("BOOK-1"), quantity));
    } else {
        assertThrows(InvalidQuantityException.class,
            () -> new OrderLine(new ProductId("BOOK-1"), quantity));
    }
}
```

Với miền đầu vào lớn, **property-based testing** có thể tạo nhiều giá trị tự động để kiểm tra một thuộc tính tổng quát. Ví dụ, với mọi số lượng dương không vượt tồn kho, `reserve(quantity)` phải làm giảm `available` đúng bằng quantity và tăng `reserved` tương ứng; tổng `available + reserved` phải được giữ nguyên nếu mô hình không có thao tác xuất kho.

Property-based testing hữu ích khi có nhiều tổ hợp trạng thái hoặc phép toán. Tuy nhiên, nó bổ sung cho các ví dụ cụ thể chứ không thay thế chúng. Những trường hợp nghiệp vụ quan trọng như đúng hạn, hết hạn, trạng thái đã giao hoặc mức giảm giá theo chính sách vẫn nên có test tên rõ ràng để người đọc hiểu ý nghĩa.

## 10. Tạo dữ liệu kiểm thử dễ đọc

Test nên làm nổi bật điều kiện quan trọng. Nếu mọi test phải khai báo hàng chục trường không liên quan, người đọc khó nhận ra điều gì làm hành vi thay đổi.

Một số cách tổ chức dữ liệu:

- Dùng factory nhỏ như `anOrder()` hoặc `aPaidOrder()` để tạo trạng thái thường dùng.
- Dùng builder khi đối tượng có nhiều trường tùy chọn, nhưng để mặc định hợp lệ và nêu rõ những trường thay đổi trong từng test.
- Dùng value object thay cho chuỗi hoặc số nguyên không có ngữ nghĩa nếu chúng giúp tránh nhầm lẫn.
- Tránh fixture dùng chung có thể bị một test sửa và làm ảnh hưởng test khác.
- Không tạo một framework test lớn hơn mô hình đang kiểm thử; helper nên đơn giản và gần với test.

Tên test có thể diễn đạt theo mẫu `given...when...then...` hoặc `should...when...`. Ví dụ `shippedOrderCannotBeCancelled` nói rõ trạng thái ban đầu và hành vi bị từ chối. Tên như `testCancel2` không cho người đọc biết quy tắc nào đang được bảo vệ.

## 11. Những gì không nên kiểm tra trong unit test miền

Unit test miền không phải nơi xác minh JPA mapping, SQL, transaction của Spring, serialization HTTP hoặc kết nối broker. Những điều đó thuộc kiểm thử tích hợp hoặc kiểm thử hợp đồng ở ranh giới tương ứng.

| Câu hỏi cần xác minh | Loại kiểm thử phù hợp |
|---|---|
| Đơn đã giao có bị từ chối khi hủy không? | Unit test mô hình miền |
| Tổng tiền được tính theo quy tắc làm tròn nào? | Unit test value object/domain model |
| Use case tải đơn, kiểm tra quyền và gọi hành vi theo đúng trình tự không? | Unit test tầng ứng dụng với fake port |
| JPA adapter ánh xạ trạng thái và lưu đơn đúng không? | Integration test repository/adapter |
| Endpoint chuyển lỗi miền thành HTTP response đúng không? | Controller/API test |
| Transaction rollback khi ghi thất bại không? | Integration test với transaction thật |

Không nên mock chính đối tượng miền để kiểm tra hành vi của nó. Nếu `Order` được mock, test chỉ xác minh cách caller tương tác với mock chứ không kiểm tra bất biến thực của `Order`. Hãy tạo đối tượng thật và gọi hành vi thật; chỉ thay thế phụ thuộc ở ranh giới khi cần.

## 12. Tổ chức test theo hành vi và bảo trì lâu dài

Một test suite tốt tập trung vào quy tắc có ý nghĩa, không chạy theo số lượng assertion hoặc số dòng code. Khi một quy tắc thay đổi, test cần chỉ ra chính xác hành vi cũ nào không còn đúng và hành vi mới nào phải được bảo vệ.

Các nguyên tắc hữu ích:

1. Mỗi test nên kiểm tra một hành vi hoặc một nhóm kết quả liên quan chặt chẽ.
2. Tạo trạng thái ban đầu rõ ràng; tránh phụ thuộc thứ tự chạy test.
3. Kiểm tra cả kết quả thành công, trường hợp bị từ chối và trạng thái sau khi từ chối.
4. Ưu tiên hành vi công khai và kết quả quan sát được thay vì private method.
5. Dùng dữ liệu biên và trường hợp nghiệp vụ có ý nghĩa, không chỉ dữ liệu “đẹp”.
6. Giữ test độc lập với framework và môi trường khi đang kiểm tra quy tắc thuần.
7. Khi test khó viết nếu không khởi động hạ tầng, xem lại xem mô hình có đang phụ thuộc không cần thiết vào hạ tầng hay không.

Không phải mọi getter hoặc dòng gán đều cần test riêng. Hãy ưu tiên những quy tắc nếu bị sai sẽ làm hệ thống đưa ra quyết định nghiệp vụ sai, phá vỡ trạng thái hoặc gây thiệt hại cho người dùng.

## 13. Checklist cho một bộ unit test miền

Trước khi hoàn tất test cho một aggregate, entity, value object hoặc policy, hãy hỏi:

1. Các bất biến phải đúng khi tạo đối tượng là gì?
2. Những hành vi công khai nào có thể thay đổi trạng thái?
3. Với mỗi hành vi, trạng thái nào được phép và trạng thái nào phải bị từ chối?
4. Khi hành động bị từ chối, đối tượng có giữ nguyên trạng thái không?
5. Các giá trị biên, null, rỗng, tiền tệ, thời gian và giới hạn đã được kiểm tra chưa?
6. Có nguồn không xác định như clock hoặc ID generator cần được tiêm để test ổn định không?
7. Test có tạo đối tượng miền thật và chạy không cần Spring/database không?
8. Test có tập trung vào hành vi quan sát được thay vì chi tiết triển khai không?

## 14. Ghi nhớ

Kiểm thử quy tắc, hành vi và bất biến trực tiếp trên mô hình miền giúp xác nhận trạng thái hợp lệ mà không phụ thuộc Spring, database hay dịch vụ bên ngoài. Hãy kiểm tra hành vi công khai của entity, aggregate, value object và domain service; bao gồm trường hợp hợp lệ, ranh giới, trường hợp bị từ chối và trạng thái sau lỗi. Dùng dữ liệu xác định, clock hoặc generator có thể kiểm soát, test tham số hóa và property-based testing khi phù hợp. Unit test miền không thay thế integration test cho repository, transaction hay API; mỗi loại kiểm thử cần xác minh đúng ranh giới của nó. Bộ test tốt bảo vệ các quyết định nghiệp vụ quan trọng và giúp mô hình có thể thay đổi mà vẫn giữ được những bất biến đã cam kết.
