# Đối tượng thay thế, stub và mock dùng đúng mục đích

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích **test double** (đối tượng thay thế trong kiểm thử) giúp kiểm soát phụ thuộc và quan sát hành vi của đơn vị mã như thế nào.
2. Phân biệt **dummy**, **stub**, **fake**, **spy** và **mock** theo **vai trò trong bài test**, thay vì chỉ dựa vào công cụ tạo đối tượng.
3. Chọn kiểm tra **trạng thái/kết quả** hoặc **tương tác** theo hợp đồng cần bảo vệ.
4. Viết unit test Java với JUnit Jupiter và Mockito mà không ràng buộc test quá chặt vào chi tiết triển khai.
5. Nhận biết giới hạn của test double và lựa chọn integration test hoặc contract test khi cần xác nhận hành vi của hệ thống thật.

Trong module **CODE_QUALITY_FUNDAMENTALS**, chất lượng mã nguồn được xem xét qua những thuộc tính quyết định mã có **đáng tin cậy, dễ hiểu và dễ thay đổi** hay không. **Khả năng kiểm thử (testability)** góp phần vào các thuộc tính đó: khi thay đổi quy tắc nghiệp vụ, nhóm cần nhanh chóng biết hành vi nào vẫn đúng, hành vi nào bị phá vỡ và lỗi nằm ở đâu.

Một lớp gọi database, HTTP API, đồng hồ hệ thống và dịch vụ gửi thông báo thường khó kiểm thử nếu tất cả các phụ thuộc ấy được tạo trực tiếp bên trong phương thức. **Test double** cho phép thay một số cộng tác viên bằng đối tượng được kiểm soát trong test. Tuy nhiên, dùng càng nhiều mock không đồng nghĩa kiểm thử càng tốt. Chọn sai đối tượng thay thế có thể khiến test xanh dù hệ thống thật vẫn lỗi, hoặc khiến test vỡ vì refactor không thay đổi hành vi.

## 1. Test double là gì và giải quyết vấn đề nào?

**Test double** là tên gọi chung cho một đối tượng được dùng thay cho cộng tác viên thật trong một tình huống kiểm thử. Tên gọi này tương tự “diễn viên đóng thế”: nó chỉ đảm nhận phần vai trò test cần để chạy và quan sát hành vi.

Ví dụ, một lớp **CheckoutService** tính thành tiền, lưu đơn hàng và gửi thông báo. Trong unit test về cách tính tổng, ta không cần thật sự ghi vào database hay gửi email. Ta có thể:

- Cấp một bảng giá biết trước để kết quả tính toán **có tính xác định**.
- Dùng kho lưu trữ trong bộ nhớ để quan sát đơn hàng được tạo.
- Dùng một mock để kiểm tra có lệnh gửi thông báo đúng đối tượng.

Đây là các mục đích khác nhau. Mỗi loại test double có điểm mạnh riêng, dù cùng có thể được tạo bằng một framework mocking.

### Những lợi ích thực tế

| Mục tiêu kiểm thử | Cách đối tượng thay thế hỗ trợ | Giới hạn cần nhớ |
| --- | --- | --- |
| **Tính xác định** | Trả cùng dữ liệu cho cùng tình huống, không phụ thuộc mạng hay thời gian thật | Không phản ánh hết biến động của dịch vụ thật |
| **Phản hồi nhanh** | Không chờ database, API hoặc hệ thống thư bên ngoài | Test nhanh chưa chứng minh kết nối thật hoạt động |
| **Cô lập nguyên nhân** | Khi unit test lỗi, phạm vi thường nằm ở logic được kiểm tra và hợp đồng của double | Double viết sai có thể che giấu lỗi thật |
| **Mô phỏng tình huống khó** | Cho phụ thuộc trả lỗi, timeout giả lập hoặc dữ liệu biên | Thời gian, đồng thời và giao thức thật cần kiểm chứng riêng |
| **Quan sát tác dụng phụ** | Ghi nhận lệnh gửi sự kiện, lưu dữ liệu hoặc gọi cổng ngoài | Quá nhiều kiểm tra tương tác làm test phụ thuộc vào cách viết bên trong |

**Quan trọng:** Test double không phải cơ chế thay thế mọi integration test. Nó hữu ích khi câu hỏi của test có thể trả lời bằng hợp đồng đã biết của cộng tác viên và không cần xác minh hoạt động thực của hệ thống ngoài.

## 2. Phân biệt dummy, stub, fake, spy và mock

Các thuật ngữ này thường được mô tả theo hệ phân loại test double của xUnit Patterns. Trong thực tế, nhiều người gọi mọi đối tượng do Mockito tạo ra là “mock”, dù nó chỉ cung cấp dữ liệu stub. Khi trao đổi thiết kế kiểm thử, nên gọi theo **vai trò mà đối tượng thực hiện trong test**.

| Loại | Mục đích | Cách hoạt động | Ví dụ phù hợp |
| --- | --- | --- | --- |
| **Dummy** | Điền vào tham số mà tình huống kiểm thử không sử dụng | Không cung cấp hành vi có ý nghĩa; nếu bị gọi ngoài dự kiến có thể báo lỗi | Một cộng tác viên không nằm trên nhánh logic đang kiểm tra |
| **Stub** | Cung cấp dữ liệu hoặc phản hồi đã định trước | Trả giá trị, lỗi hoặc trạng thái đã cấu hình để kích hoạt kịch bản | Bảng giá trả giá 120.000 đồng cho SKU cụ thể |
| **Fake** | Cung cấp một triển khai đơn giản nhưng có hành vi hoạt động được | Có logic gần với cộng tác viên, thường dùng bộ nhớ thay database hoặc mạng | Repository lưu và truy vấn đơn hàng trong Map |
| **Spy** | Ghi lại tương tác để test quan sát sau khi chạy | Theo dõi lời gọi, tham số hoặc thứ tự theo nhu cầu | Bộ gửi sự kiện ghi danh sách những sự kiện đã nhận |
| **Mock** | Kiểm tra kỳ vọng về một tương tác quan trọng | Test đặt expectation hoặc xác minh tương tác sau thực thi | Kiểm tra lệnh gửi xác nhận được phát đúng một lần |

### 2.1. Dummy: chỉ cần hiện diện

Dummy thường là đối tượng được truyền vào vì chữ ký constructor hoặc phương thức yêu cầu, nhưng nhánh đang kiểm tra **không dùng đến**. Nếu người đọc không biết dummy có thể bị gọi, test trở nên dễ hiểu nhầm.

Ví dụ, khi kiểm tra logic từ chối dữ liệu ngay từ đầu, dịch vụ gửi thông báo sẽ không được sử dụng. Có thể truyền một đối tượng thất bại ngay nếu ai đó vô tình gọi nó:

~~~java
ReceiptSender unusedSender = order -> {
    throw new AssertionError("Must not send a receipt here");
};
~~~

Đối tượng này vừa đóng vai trò dummy, vừa giúp chỉ ra một tương tác ngoài dự kiến. Tuy nhiên, nếu phải truyền hàng chục dummy mới kiểm tra được một điều kiện đơn giản, đó có thể là dấu hiệu đối tượng sản phẩm đang có quá nhiều phụ thuộc hoặc test đang chọn sai phạm vi.

### 2.2. Stub: điều khiển đầu vào gián tiếp

Một stub trả lại phản hồi đã chọn:

~~~java
PriceCatalog priceCatalog = sku ->
        java.util.Optional.of(new java.math.BigDecimal("120000"));
~~~

Khi logic được kiểm tra gọi **priceCatalog.findUnitPrice(...)**, giá đã xác định giúp tạo kết quả mong đợi. Stub phù hợp để đưa hệ thống vào một trạng thái cụ thể, ví dụ sản phẩm tồn tại, sản phẩm không tồn tại hoặc API trả lỗi.

Stub thường **không phải đối tượng cần xác minh có được gọi bao nhiêu lần**. Nếu hợp đồng chỉ yêu cầu tính ra số tiền đúng, test có thể kiểm tra số tiền, không cần kiểm tra mọi phương thức mà service đã gọi.

### 2.3. Fake: một triển khai đơn giản có trạng thái

Fake thường có hành vi gần với cộng tác viên thật nhưng giản lược hạ tầng. Ví dụ, **InMemoryOrderStore** lưu các đơn hàng trong **Map** và hỗ trợ tìm lại theo ID.

Fake có thể giúp test quan sát trạng thái sau thao tác mà không cần database. Tuy nhiên, một Map trong bộ nhớ không tự kiểm chứng **ràng buộc khóa của database, transaction, isolation, migration, mapping SQL, concurrency hoặc timeout**. Với các đặc tính đó, cần test adapter hoặc integration test dùng hệ thống thật hay môi trường đại diện.

### 2.4. Spy: ghi nhận điều đã xảy ra

Một spy là đối tượng ghi lại những lời gọi để test quan sát sau khi thực thi. Có thể tự viết một **RecordingReceiptSender** chứa danh sách đơn đã được yêu cầu gửi thông báo.

Trong Mockito, **spy(...)** còn có nghĩa là tạo một đối tượng gián điệp bao quanh **triển khai thực**, cho phép gọi phương thức thật trừ khi đã được cấu hình khác. Cần phân biệt **vai trò test spy** với **cơ chế partial mocking** của Mockito. Spy trên đối tượng thật có trạng thái hoặc I/O có thể gây tác dụng phụ không mong muốn; không nên dùng chỉ để né việc thiết kế ranh giới cộng tác viên rõ ràng.

### 2.5. Mock: kiểm tra một tương tác thuộc hợp đồng

Mock có giá trị khi **việc phát ra một lệnh** là đầu ra quan trọng và người kiểm thử không quan sát được nó qua kết quả trả về. Ví dụ, sau khi lưu đơn, dịch vụ cần gửi một lệnh xác nhận đúng đơn vừa tạo.

Trong Mockito:

~~~java
ReceiptSender receipts = org.mockito.Mockito.mock(ReceiptSender.class);

// Thực thi nghiệp vụ ở lớp đang kiểm tra...

org.mockito.Mockito.verify(receipts).send(expectedOrder);
~~~

Dòng **verify(...)** có ý nghĩa khi hợp đồng của dịch vụ yêu cầu gửi xác nhận. Nó ít giá trị hơn nếu chỉ xác minh service đã gọi một helper nội bộ để tính tổng, vì thứ tự hoặc cách gọi helper có thể thay đổi mà kết quả vẫn đúng.

**Kết luận về thuật ngữ:** Một đối tượng tạo bởi **Mockito.mock(...)** có thể chỉ đóng vai trò stub khi ta dùng **when(...).thenReturn(...)**. Tên framework không quyết định mục đích của test double.

## 3. Chọn kiểm tra trạng thái hay kiểm tra tương tác?

Một test có thể kiểm tra nhiều loại đầu ra quan sát được:

- **Kết quả trả về:** giá tiền, trạng thái, lỗi hoặc thông tin đơn hàng.
- **Trạng thái sau thực thi:** bản ghi được lưu, danh sách thay đổi, dữ liệu được tính.
- **Tương tác với cộng tác viên:** lệnh gửi email, phát sự kiện, gọi cổng thanh toán hoặc yêu cầu ghi dữ liệu.
- **Đặc tính phi chức năng đã cam kết:** giới hạn thời gian, tài nguyên, thứ tự, số lần thử lại, khả năng hủy.

### Kiểm tra trạng thái/kết quả

Phù hợp khi kết quả là phần quan trọng nhất của hợp đồng. Ví dụ, nếu tính tổng đơn hàng từ hai dòng giá, hãy so sánh với số tiền mong đợi; không cần kiểm tra **multiply(...)** được gọi mấy lần.

~~~java
assertEquals(new java.math.BigDecimal("240000"), actual.total());
~~~

Test theo kết quả thường bền vững trước refactor: có thể thay Stream bằng vòng lặp, đổi phương thức private hoặc di chuyển logic mà test vẫn đúng nếu hành vi không đổi.

### Kiểm tra tương tác

Phù hợp khi hành động **gửi lệnh tới ranh giới khác** chính là điều nghiệp vụ cần bảo vệ. Ví dụ, thao tác đặt hàng đã thành công thì phải gửi yêu cầu xác nhận tương ứng.

~~~java
verify(receipts).send(actualOrder);
~~~

Ở đây tương tác là quan sát được ở ranh giới của service. Nhưng nếu dùng mock để verify mọi lời gọi **priceCatalog.findUnitPrice**, **idGenerator.nextId**, **repository.save** cùng thứ tự chính xác, test có thể trở nên cứng nhắc nếu những thứ đó chỉ là chi tiết triển khai.

### Tiêu chí chọn

| Câu hỏi cần trả lời | Cách kiểm tra ưu tiên |
| --- | --- |
| Hàm tính đúng số tiền không? | Kết quả trả về, test điều kiện biên |
| Đơn đã được lưu dưới ID đúng chưa? | Trạng thái của fake store hoặc integration test với database |
| Yêu cầu gửi xác nhận có được phát không? | Mock/spy ở **ReceiptSender** |
| Khi kiểm tra đầu vào thất bại, có tránh gửi giao dịch không? | Kiểm tra **không có tương tác** với cổng gây tác dụng phụ |
| SQL có tôn trọng unique constraint không? | Integration test với database phù hợp |
| Client HTTP có tạo request đúng schema và header không? | Test adapter/contract với server giả lập hoặc môi trường đại diện |
| Đổi cách tổ chức phương thức private có phá kết quả không? | Test theo hành vi công khai thay vì verify chi tiết bên trong |

Không có quy tắc “state testing luôn tốt hơn interaction testing” hoặc ngược lại. **Chọn theo hợp đồng và rủi ro cần xác nhận**.

## 4. Thiết kế ranh giới kiểm thử trong Java

Một nguyên nhân khiến phải mock quá nhiều là lớp nghiệp vụ tự tạo các phụ thuộc bên ngoài:

~~~java
// Minh họa cấu trúc gây khó kiểm thử.
final class CheckoutService {
    Order place(String sku, int quantity) {
        // new JdbcOrderRepository(...)
        // new HttpPriceCatalog(...)
        // new SmtpReceiptSender(...)
        // Đọc đồng hồ hoặc tạo ID ngẫu nhiên trực tiếp
        // Sau đó tính tiền, lưu và gửi thông báo
        throw new UnsupportedOperationException("Example only");
    }
}
~~~

Khi logic tính tiền trộn với kết nối dữ liệu, HTTP, SMTP và việc tạo ID, test cần khởi động nhiều hạ tầng hoặc can thiệp sâu vào cấu trúc bên trong.

Một ranh giới dễ kiểm thử hơn là **tách hợp đồng cộng tác viên** và **truyền phụ thuộc qua constructor**. Tuy nhiên, chỉ tạo những giao diện có ý nghĩa thực tế; không cần bọc mọi phép cộng vào một interface.

### 4.1. Mã nghiệp vụ minh họa

Trong ví dụ sau:

- **PriceCatalog** cung cấp đơn giá của SKU.
- **OrderStore** lưu đơn và cho phép truy vấn lại.
- **ReceiptSender** nhận lệnh gửi xác nhận.
- **OrderIdSource** tạo mã đơn.
- **CheckoutService** điều phối một đơn giản đặt hàng.

~~~java
import java.math.BigDecimal;
import java.util.Objects;
import java.util.Optional;

record Order(
        String id,
        String sku,
        int quantity,
        BigDecimal total) {

    Order {
        Objects.requireNonNull(id, "id");
        Objects.requireNonNull(sku, "sku");
        Objects.requireNonNull(total, "total");
        if (id.isBlank() || sku.isBlank()
                || quantity <= 0 || total.signum() < 0) {
            throw new IllegalArgumentException("invalid order");
        }
    }
}

@FunctionalInterface
interface PriceCatalog {
    // Optional.empty() khi SKU không tồn tại;
    // giá hợp lệ không âm, không null.
    Optional<BigDecimal> findUnitPrice(String sku);
}

interface OrderStore {
    void save(Order order);
    Optional<Order> findById(String id);
}

@FunctionalInterface
interface ReceiptSender {
    void send(Order order);
}

@FunctionalInterface
interface OrderIdSource {
    String nextId();
}

final class CheckoutService {
    private final PriceCatalog prices;
    private final OrderStore orders;
    private final ReceiptSender receipts;
    private final OrderIdSource ids;

    CheckoutService(
            PriceCatalog prices,
            OrderStore orders,
            ReceiptSender receipts,
            OrderIdSource ids) {
        this.prices = Objects.requireNonNull(prices, "prices");
        this.orders = Objects.requireNonNull(orders, "orders");
        this.receipts = Objects.requireNonNull(receipts, "receipts");
        this.ids = Objects.requireNonNull(ids, "ids");
    }

    Order place(String sku, int quantity) {
        if (sku == null || sku.isBlank() || quantity <= 0) {
            throw new IllegalArgumentException("invalid order request");
        }

        BigDecimal price = prices.findUnitPrice(sku)
                .orElseThrow(() ->
                        new IllegalArgumentException("unknown SKU: " + sku));
        if (price.signum() < 0) {
            throw new IllegalStateException("catalog returned negative price");
        }

        Order order = new Order(
                ids.nextId(),
                sku,
                quantity,
                price.multiply(BigDecimal.valueOf(quantity)));

        orders.save(order);
        receipts.send(order);
        return order;
    }
}
~~~

Các kiểu trên được để **package-private** nhằm trình bày cùng một ví dụ. Mã minh họa có thể dùng với Java 17; test bên dưới sử dụng **JUnit Jupiter (JUnit 5)** và **Mockito**. Việc thêm các phụ thuộc kiểm thử cần thực hiện theo cấu hình build đang dùng của dự án.

**Giới hạn quan trọng:** Quy trình **lưu đơn rồi gửi xác nhận** ở đây chỉ minh họa hợp đồng và test double. Trong hệ thống thật, nếu gửi thất bại sau khi lưu thành công, sẽ xảy ra trạng thái lưu đơn nhưng chưa gửi thông báo. Một workflow cần độ tin cậy cao có thể dùng **transactional outbox**, trạng thái gửi riêng, worker retry có kiểm soát hoặc cơ chế phù hợp khác. Mock không chứng minh được tính nguyên tử giữa database và hệ thống thông báo.

### 4.2. Phân vai ba test double

Trong unit test cho **CheckoutService**, có thể chọn:

- **Stub PriceCatalog:** trả giá đã biết, đưa service vào tình huống định trước.
- **Fake OrderStore:** thực hiện lưu/tìm trong bộ nhớ, cho phép kiểm tra trạng thái sau khi đặt hàng.
- **Mock ReceiptSender:** xác minh lệnh gửi xác nhận đúng đơn được tạo.
- **Stub OrderIdSource:** trả ID cố định để test không phụ thuộc nguồn sinh ID ngẫu nhiên.

~~~mermaid
flowchart TB
    T[CheckoutServiceTest] --> S[CheckoutService]
    S --> P[PriceCatalog - stub]
    S --> R[OrderStore - fake trong bộ nhớ]
    S --> N[ReceiptSender - mock]
    S --> I[OrderIdSource - stub]
    T --> A[Assert kết quả và trạng thái]
    T --> V[Verify lệnh gửi xác nhận]
~~~

### 4.3. Unit test kết hợp stub, fake và mock

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;

import java.math.BigDecimal;
import java.util.HashMap;
import java.util.Map;
import java.util.Optional;
import org.junit.jupiter.api.Test;

class CheckoutServiceTest {

    // Fake: lưu và truy vấn đơn trong bộ nhớ, không có SQL/transaction.
    private static final class InMemoryOrderStore implements OrderStore {
        private final Map<String, Order> byId = new HashMap<>();

        @Override
        public void save(Order order) {
            if (byId.putIfAbsent(order.id(), order) != null) {
                throw new IllegalStateException("duplicate order ID");
            }
        }

        @Override
        public Optional<Order> findById(String id) {
            return Optional.ofNullable(byId.get(id));
        }
    }

    @Test
    void placesOrderAndRequestsOneReceipt() {
        PriceCatalog catalog = sku ->
                Optional.of(new BigDecimal("120000")); // Stub
        OrderIdSource ids = () -> "O-001";              // Stub
        InMemoryOrderStore store = new InMemoryOrderStore();
        ReceiptSender receipts = mock(ReceiptSender.class); // Mock

        CheckoutService checkout = new CheckoutService(
                catalog, store, receipts, ids);

        Order actual = checkout.place("SKU-01", 2);

        assertEquals("O-001", actual.id());
        assertEquals(new BigDecimal("240000"), actual.total());
        assertEquals(Optional.of(actual), store.findById("O-001"));
        verify(receipts).send(actual);
    }

    @Test
    void unknownProductDoesNotPersistOrSendReceipt() {
        PriceCatalog missingProduct = sku -> Optional.empty();
        OrderIdSource ids = () -> "O-002";
        InMemoryOrderStore store = new InMemoryOrderStore();
        ReceiptSender receipts = mock(ReceiptSender.class);

        CheckoutService checkout = new CheckoutService(
                missingProduct, store, receipts, ids);

        assertThrows(IllegalArgumentException.class,
                () -> checkout.place("UNKNOWN", 1));

        assertTrue(store.findById("O-002").isEmpty());
        verifyNoInteractions(receipts);
    }
}
~~~

Trong test đầu tiên, **assertEquals** bảo vệ kết quả và trạng thái; **verify** bảo vệ một tương tác thuộc hợp đồng. Test thứ hai xác nhận đường lỗi: sản phẩm không tồn tại thì **không lưu đơn và không gửi xác nhận**.

**Lưu ý về lời gọi “đúng một lần”:** Với Mockito, **verify(mock).method(...)** mặc định xác minh đúng **một** lần gọi khớp. Nếu nghiệp vụ cho phép nhiều thông báo hoặc một hệ thống retry ở tầng khác, cần xác định lại expectation theo hợp đồng. Đừng tự động thêm **verifyNoMoreInteractions(...)** cho mọi cộng tác viên, vì nó có thể khiến test vỡ khi bổ sung một tương tác hợp lệ không liên quan đến hành vi đang kiểm tra.

### 4.4. Một stub cũng có thể được tạo bằng Mockito

Ví dụ thay lambda PriceCatalog bằng:

~~~java
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

PriceCatalog catalog = mock(PriceCatalog.class);

when(catalog.findUnitPrice("SKU-01"))
        .thenReturn(java.util.Optional.of(
                new java.math.BigDecimal("120000")));
~~~

Dù được tạo bằng **mock(...)**, trong test này đối tượng **đóng vai trò stub** vì nó cung cấp đầu vào gián tiếp cho CheckoutService. Không nên xác minh **findUnitPrice("SKU-01")** được gọi bao nhiêu lần nếu mục tiêu duy nhất là tính đúng tổng tiền và số lần tra cứu không nằm trong hợp đồng.

Cần nhớ Mockito có giá trị mặc định cho các lời gọi chưa stub; test không nên phụ thuộc vào giá trị mặc định để suy ra hợp đồng nghiệp vụ. Nên cấu hình rõ những tình huống cần thử, nhất là khi **null**, **Optional.empty()** hoặc số 0 có ý nghĩa khác nhau.

## 5. Spy dùng khi nào và những điều dễ nhầm

Nếu muốn quan sát các sự kiện được ghi nhận mà không dùng Mockito, có thể viết một recording spy đơn giản:

~~~java
import java.util.ArrayList;
import java.util.List;

final class RecordingReceiptSender implements ReceiptSender {
    private final List<Order> sentOrders = new ArrayList<>();

    @Override
    public void send(Order order) {
        sentOrders.add(order);
    }

    List<Order> sentOrders() {
        return List.copyOf(sentOrders);
    }
}
~~~

Trong test:

~~~java
RecordingReceiptSender receipts = new RecordingReceiptSender();

// Sau khi CheckoutService.place(...) được gọi:
assertEquals(List.of(expectedOrder), receipts.sentOrders());
~~~

Đây là **spy theo vai trò**: nó ghi lại lệnh đã nhận để test kiểm tra. Cách này hữu ích khi các tương tác cần được xem như một tập sự kiện có thứ tự hoặc khi muốn tránh phụ thuộc vào framework mocking cho một ranh giới nhỏ.

### Phân biệt với Mockito.spy

Mockito còn có API **spy(realObject)** cho phép giám sát hoặc stub một **đối tượng triển khai thật**. Khi stub spy bằng cú pháp **when(spy.method()).thenReturn(...)**, phương thức thật có thể chạy ngay trong lúc cấu hình. Nếu cần chặn lời gọi thật, cú pháp **doReturn(value).when(spy).method()** thường phù hợp hơn.

Tuy nhiên, **partial mocking** có thể làm test khó suy luận: một số phương thức chạy logic thật, một số bị thay, trạng thái thay đổi của đối tượng có thể gây tác dụng phụ. Đặc biệt không spy một đối tượng đang truy cập database, network hoặc gửi thông báo chỉ vì tiện. Khi xuất hiện nhu cầu như vậy, nên xem lại liệu có thể tách phụ thuộc ở ranh giới rõ ràng không.

## 6. Những dấu hiệu test đang dùng mock sai mục đích

### 6.1. Kiểm tra chi tiết triển khai thay cho hành vi

Ví dụ dễ bị ràng buộc quá mức:

~~~java
// Ví dụ minh họa một test dễ vỡ.
verify(priceCatalog).findUnitPrice("SKU-01");
verify(orderIdSource).nextId();
verify(orderStore).save(expectedOrder);
verify(receiptSender).send(expectedOrder);
verifyNoMoreInteractions(
        priceCatalog, orderIdSource, orderStore, receiptSender);
~~~

Nếu mục tiêu chỉ là “tạo đơn đúng giá, đã lưu và phát lệnh gửi xác nhận”, test trên kiểm tra cả **mọi bước nội bộ**. Khi triển khai bổ sung cache hoặc đổi cách sinh ID mà hợp đồng vẫn đúng, test có thể vỡ không cần thiết.

Một cách tập trung hơn là kiểm tra **giá trị Order**, **trạng thái fake store** và **lệnh gửi xác nhận**. Chỉ kiểm tra thứ tự khi **thứ tự là một phần của hợp đồng**, chẳng hạn phải xác thực quyền trước khi thực hiện một tác dụng phụ nhạy cảm.

### 6.2. Mock cả đối tượng giá trị và logic thuần

Các kiểu như **Order**, **Money** hoặc một hàm tính toán thuần thường có thể được tạo thật với dữ liệu nhỏ. Mock chúng có thể làm giả chính logic cần kiểm tra.

~~~java
// Thay vì mock một giá trị tiền, tạo giá trị thật.
BigDecimal unitPrice = new BigDecimal("120000");
~~~

Nếu test cần kiểm tra công thức nhân, hãy thực hiện công thức với giá trị thật. Fake hay mock chỉ thực sự giúp ích khi có **ranh giới phụ thuộc** cần kiểm soát.

### 6.3. Dùng fake đơn giản làm bằng chứng cho database thật

Một Map giả lập có thể ghi và đọc đúng dữ liệu, nhưng database thật còn có:
- Khóa duy nhất, khóa ngoại, kiểu cột và ràng buộc độ dài.
- Transaction, isolation, deadlock hoặc optimistic locking.
- Mapping ORM/SQL, migration schema và quy ước null.
- Đồng thời nhiều giao dịch, latency và lỗi kết nối.

Nếu test về một trong những đặc tính này, fake không đủ. Cần integration test với database phù hợp hoặc test adapter được cấu hình đại diện.

### 6.4. Stub mọi lời gọi ngay cả khi không cần

Một test gồm hàng chục câu **when(...).thenReturn(...)** có thể đang phải biết quá nhiều về chi tiết của nhiều cộng tác viên. Những stub không được dùng khiến người đọc tưởng chúng quan trọng, còn cấu hình quá rộng che giấu đường chạy thật.

Để test dễ hiểu, nên chỉ stub những dữ liệu ảnh hưởng trực tiếp đến tình huống, dùng fixture có tên rõ ràng và để công cụ phát hiện cấu hình dư thừa khi có thể.

### 6.5. Dùng mock để né thiết kế hợp đồng

Nếu không rõ “thế nào là một lần gửi thành công”, “trường hợp không tìm thấy trả null hay Optional”, hoặc “retry có thể gây ghi trùng không”, mock vẫn có thể được lập trình trả bất kỳ giá trị nào. Unit test xanh lúc ấy chứng minh một kịch bản tự đặt ra, chưa chắc chứng minh yêu cầu thật.

Cần làm rõ **hợp đồng của port** trước khi stub hoặc verify. Dữ liệu đầu vào hợp lệ, đầu ra, lỗi, tác dụng phụ và khả năng chạy đồng thời đều có thể là phần của hợp đồng.

## 7. Khi cần kiểm tra thứ tự, số lần gọi hoặc không có tương tác

Không phải mọi interaction test đều dễ vỡ. Một số tương tác là phần quan trọng của tính đúng đắn hoặc an toàn.

| Hợp đồng | Nên xác minh gì? | Lý do |
| --- | --- | --- |
| Không gửi thông báo khi request sai | **verifyNoInteractions(...)** đối với cổng gửi | Ngăn tác dụng phụ ngoài ý muốn |
| Một lệnh thanh toán không được gửi hai lần | Số lần gọi hoặc idempotency ở ranh giới đúng | Tránh tác dụng phụ trùng lặp |
| Không lưu dữ liệu trước khi kiểm tra quyền | Tác dụng phụ không xảy ra khi chưa được phép | Bảo vệ ranh giới bảo mật |
| Sự kiện phải chứa mã đơn và số tiền đúng | Nội dung lệnh/sự kiện được phát | Đầu ra của service bao gồm một thông điệp |
| Phải đóng tài nguyên sau sử dụng | Đối tượng được giải phóng theo hợp đồng | Tránh rò rỉ tài nguyên |
| Chỉ hỏi bảng giá một lần vì giới hạn quota | Số lời gọi nếu quota là yêu cầu đã công bố | Tránh vượt giới hạn API |

Trong Mockito, có thể dùng **ArgumentCaptor** để kiểm tra một đối tượng được truyền vào mà không cần biết trước toàn bộ đối tượng:

~~~java
import org.mockito.ArgumentCaptor;

ArgumentCaptor<Order> captured =
        ArgumentCaptor.forClass(Order.class);

// Sau khi thực thi service:
verify(receipts).send(captured.capture());
assertEquals("SKU-01", captured.getValue().sku());
assertEquals(new BigDecimal("240000"), captured.getValue().total());
~~~

Chỉ dùng captor khi cần kiểm tra thuộc tính của lệnh đã phát. Nếu đã có **actualOrder** và hợp đồng yêu cầu gửi đúng giá trị ấy, **verify(receipts).send(actualOrder)** có thể đơn giản và dễ đọc hơn.

Nếu thứ tự thực sự là yêu cầu, Mockito cung cấp **InOrder**; nhưng đừng biến thứ tự giữa các cộng tác viên độc lập thành giả định cứng. Một refactor có thể thay trình tự các thao tác **không quan sát được** mà không vi phạm nghiệp vụ.

## 8. Làm cho thời gian, ngẫu nhiên và lỗi trở nên kiểm thử được

Không phải test double nào cũng là repository hoặc HTTP client. Một nguồn gây test không ổn định là phụ thuộc vào **thời gian hiện tại**, **ID ngẫu nhiên** hoặc **lịch chạy bất đồng bộ**.

### 8.1. Truyền Clock thay vì gọi thời gian hệ thống khắp nơi

Ví dụ một mã giảm giá hết hạn vào thời điểm xác định:

~~~java
import java.time.Clock;
import java.time.Instant;
import java.util.Objects;

final class VoucherExpiry {
    private final Clock clock;

    VoucherExpiry(Clock clock) {
        this.clock = Objects.requireNonNull(clock, "clock");
    }

    boolean isExpired(Instant expiresAt) {
        Objects.requireNonNull(expiresAt, "expiresAt");
        return !Instant.now(clock).isBefore(expiresAt);
    }
}
~~~

Test có thể tạo đồng hồ cố định:

~~~java
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import org.junit.jupiter.api.Test;

class VoucherExpiryTest {
    @Test
    void expiresAtTheExactDeadline() {
        Instant deadline = Instant.parse("2026-12-01T00:00:00Z");

        Clock before = Clock.fixed(
                deadline.minusMillis(1), ZoneOffset.UTC);
        Clock atDeadline = Clock.fixed(deadline, ZoneOffset.UTC);

        assertFalse(new VoucherExpiry(before).isExpired(deadline));
        assertTrue(new VoucherExpiry(atDeadline).isExpired(deadline));
    }
}
~~~

**Clock.fixed(...)** hoạt động như một nguồn thời gian được kiểm soát, giúp test không phải dùng **Thread.sleep(...)** để chờ đến giờ thật. Việc trừ một mili giây kiểm tra điều kiện biên: chính xác ở deadline thì voucher đã hết hạn theo hợp đồng minh họa.

### 8.2. ID và số ngẫu nhiên

Nếu mã tạo ID ngẫu nhiên hoặc dùng số ngẫu nhiên để lựa chọn nhánh, có thể truyền một nguồn sinh giá trị qua interface hoặc sử dụng nguồn có seed được kiểm soát trong những test phù hợp. **Không nên thay thế cơ chế sinh token bảo mật trong sản phẩm bằng bộ sinh dự đoán được** chỉ vì muốn test dễ hơn. Khi cần test bảo mật, phải kiểm tra tính chất của cơ chế thật bằng phương pháp phù hợp.

### 8.3. Scheduler và công việc bất đồng bộ

Đối với retry, timeout hoặc xử lý theo lịch, tốt hơn hết là tách **quy tắc quyết định** khỏi **cơ chế chờ**. Test quy tắc có thể dùng clock/scheduler giả để tiến thời gian có kiểm soát, tránh những test ngủ thật dài và không ổn định.

Tuy nhiên, scheduler giả không xác nhận được mọi race condition hay vấn đề tài nguyên trong runtime. Cần thêm test tích hợp/đồng thời cho những rủi ro thực tế.

## 9. Mock không thay thế integration test và contract test

Một ứng dụng đáng tin cậy cần nhiều mức kiểm tra, vì mỗi mức trả lời một câu hỏi khác nhau.

| Mức kiểm tra | Câu hỏi | Phụ thuộc thường dùng |
| --- | --- | --- |
| **Unit test với stub/fake/mock** | Logic của đơn vị có đúng với hợp đồng giả định của cộng tác viên không? | Test double tại ranh giới |
| **Contract test** | Hai bên có thống nhất schema, kiểu giá trị, mã lỗi và ngữ nghĩa giao tiếp không? | Provider/consumer contract hoặc bộ test hợp đồng |
| **Integration test** | Adapter thực có kết nối đúng database, HTTP, broker hoặc thư viện không? | Dịch vụ thật, container, server giả lập theo giao thức |
| **End-to-end test** | Luồng người dùng quan trọng đi qua hệ thống và tạo kết quả phù hợp không? | Nhiều thành phần chạy chung |
| **Resilience/load test** | Hệ thống phản ứng thế nào khi lỗi mạng, chậm, quá tải hoặc chạy đồng thời? | Môi trường và tải đại diện, fault injection khi thích hợp |

### Lấy ví dụ với OrderStore

Một fake cho phép ta biết CheckoutService **đã yêu cầu lưu** đơn và có thể đọc lại trạng thái trong bộ nhớ. Nhưng để biết **JdbcOrderStore** viết SQL đúng, kiểu dữ liệu tiền chính xác, khóa chính được bảo vệ và transaction được xử lý phù hợp, cần kiểm thử adapter với database phù hợp.

Nếu fake luôn nhận đơn trùng ID, còn database có unique constraint thì test có thể bỏ qua khác biệt quan trọng. Nên xác định **hợp đồng OrderStore** và đưa các tính chất chung quan trọng vào test cho cả fake lẫn adapter thật; sau đó kiểm thử những đặc tính riêng của database ở mức tích hợp.

### Lấy ví dụ với PriceCatalog

Stub trả **Optional.of(120000)** không xác minh được server bảng giá thật có JSON đúng, đơn vị tiền đúng, header xác thực đúng hay xử lý HTTP 404 đúng. Cần test cho adapter HTTP và hợp đồng API.

Điều cần tránh là khẳng định “đã mock thành công nên tích hợp chắc chắn hoạt động”. Test double là **một công cụ phân chia trách nhiệm kiểm tra**, không phải bằng chứng thay thế mọi tầng.

## 10. Thiết kế test double sao cho gần hợp đồng mà vẫn đơn giản

### 10.1. Không mô phỏng quá nhiều

Một fake database tự viết hỗ trợ transaction, SQL, isolation, lock và hàng chục trường hợp lỗi có thể trở thành một hệ thống phức tạp riêng, vẫn không giống database thật. Nếu cần kiểm chứng những đặc tính này, chạy test trên thành phần thật thường đáng tin cậy hơn.

Với unit test, chỉ giữ những hành vi liên quan tới hợp đồng đang cần; các đặc tính khó mô phỏng nên được kiểm thử ở mức khác.

### 10.2. Không đơn giản hóa đến mức che lỗi

Một fake lưu đơn nhưng không bao giờ từ chối ID trùng có thể làm team quên xử lý lỗi trùng khóa. Một stub bảng giá trả giá cho mọi SKU có thể khiến đường lỗi “sản phẩm không tồn tại” không bao giờ được thử.

Cần chọn những **đặc tính thực sự quan trọng của hợp đồng** để thể hiện trong double, đồng thời ghi rõ phần nào không được mô phỏng.

### 10.3. Không chia sẻ trạng thái mutable giữa các test

Một fake repository được khai báo **static** và dùng chung giữa các test có thể khiến kết quả phụ thuộc thứ tự chạy. Nếu một test lưu đơn “O-001”, test khác có thể thất bại vì khóa trùng hoặc đọc thấy dữ liệu của test trước.

Mỗi test nên có fixture độc lập hoặc một cơ chế reset có thể tin cậy. Mục tiêu là test chạy độc lập, có thể chạy riêng lẻ và lặp lại cho cùng kết quả.

### 10.4. Không chỉ test trường hợp thành công

Khi phụ thuộc có thể thất bại, cần thử cả:
- Không tìm thấy dữ liệu.
- Dữ liệu trả về không hợp lệ hoặc thiếu trường.
- Phụ thuộc trả lỗi tạm thời và lỗi không thể retry.
- Tác dụng phụ thất bại sau khi một bước trước đã thành công.
- Timeout hoặc request bị hủy, khi thuộc hợp đồng.
- Trùng lặp do request được gửi lại.

Với những kịch bản có I/O hoặc đồng thời, unit test bằng double chỉ xác nhận **quyết định xử lý**; cần thêm integration/resilience test để xác nhận cơ chế thật.

## 11. Một quy trình chọn đối tượng thay thế

Khi viết bài test cho một lớp Java, hãy đi theo các câu hỏi:

**Bước 1 — Xác định hợp đồng cần chứng minh.** Test này bảo vệ kết quả tính toán, việc thay đổi trạng thái, một lệnh gửi đi hay cách phản ứng khi phụ thuộc lỗi?

**Bước 2 — Tìm ranh giới phụ thuộc.** Thành phần nào là phép tính thuần, thành phần nào dùng network, database, thời gian, ngẫu nhiên hoặc I/O? Chỉ thay thế khi có lý do.

**Bước 3 — Chọn loại double nhỏ nhất đủ phục vụ test.**

| Nếu cần... | Thường chọn... |
| --- | --- |
| Một giá trị cố định hoặc một lỗi đã định | **Stub** |
| Cơ chế lưu/tìm đơn giản để kiểm tra trạng thái | **Fake** |
| Kiểm tra lệnh gửi quan trọng đã xảy ra | **Mock** hoặc **recording spy** |
| Tham số bắt buộc nhưng không chạy vào nhánh đó | **Dummy** có thể thất bại khi bị gọi |
| Kiểm soát thời gian | **Clock.fixed** hoặc nguồn thời gian theo hợp đồng |
| Kiểm tra giao thức và tích hợp thực | **Adapter/integration/contract test**, thay vì chỉ dùng double |

**Bước 4 — Viết assertion theo hành vi.** Ưu tiên kết quả, trạng thái và những tương tác thật sự có ý nghĩa nghiệp vụ. Tránh xác minh từng helper hoặc thứ tự không được hợp đồng yêu cầu.

**Bước 5 — Xác nhận phần double chưa kiểm tra.** Nếu test dùng fake database, cần biết ai sẽ kiểm tra SQL, transaction và migration. Nếu test dùng stub HTTP, cần biết ai sẽ kiểm tra serialization, mã lỗi và timeout.

**Bước 6 — Thử refactor trong suy nghĩ.** Nếu thay thuật toán mà giữ nguyên đầu vào/đầu ra và tác dụng phụ được cam kết, test có còn xanh không? Nếu không, có thể test đã phụ thuộc quá chặt vào cấu trúc nội bộ.

## 12. Tình huống thực hành: đặt hàng gặp lỗi gửi thông báo

Giả sử CheckoutService đã lưu đơn **O-001**, nhưng dịch vụ gửi email bị timeout. Khách không nhận được phản hồi và gửi lại yêu cầu. Nhóm có hai unit test:

- **Test A:** Stub ReceiptSender để nó không làm gì, rồi assert đơn đã được lưu.
- **Test B:** Mock ReceiptSender và verify nó đã được gọi một lần.

Cả hai có thể xanh nhưng chưa trả lời được những câu hỏi quan trọng:
1. Đơn thứ nhất đã được lưu hay chưa khi gửi thông báo lỗi?
2. Gửi lại có tạo đơn thứ hai không?
3. Email có thể đã được gửi dù client thấy timeout không?
4. Có cơ chế retry an toàn và theo dõi trạng thái gửi không?

### Phân tích

**Test A** chứng minh một phần logic lưu đơn với dependency thay thế; **Test B** chứng minh service đã phát lệnh gửi. Không test nào chứng minh **hệ thống thực** hoàn thành một giao dịch duy nhất và gửi một xác nhận chính xác trong tình huống lỗi giữa chừng.

Cần xác định yêu cầu nghiệp vụ: đặt hàng thành công khi nào, phản hồi nào được trả khi thông báo lỗi, request lặp được nhận diện bằng gì. Một thiết kế có thể dùng **idempotency key** cho lệnh tạo đơn và **transactional outbox** cho lệnh gửi thông báo; worker gửi có thể retry theo chính sách, còn việc nhận hoặc phát lại sự kiện vẫn phải xem xét idempotency phía nhận.

Trong test, có thể dùng stub làm **ReceiptSender ném lỗi** để kiểm tra CheckoutService xử lý thế nào, nhưng hệ thống cần thêm integration test và kiểm thử lỗi trên ranh giới dữ liệu/sự kiện. Việc cần sửa có thể là **thiết kế luồng nghiệp vụ**, không phải tăng số lượng verify.

### Một ví dụ nhận xét review

> “Test hiện kiểm tra rằng ReceiptSender được gọi, nhưng tình huống gửi thất bại sau khi lưu đơn chưa có hợp đồng rõ. Người gọi có thể gửi lại và tạo đơn trùng. Nên xác định trạng thái đơn sau lỗi gửi và cách chống trùng, rồi bổ sung test theo hợp đồng cùng kiểm thử tích hợp cho ranh giới lưu dữ liệu/phát thông báo.”

Nhận xét này gắn test với rủi ro thực tế thay vì chỉ yêu cầu “mock thêm”.

## 13. Những sai lầm thường gặp

1. **Gọi mọi đối tượng thay thế là mock.** Dẫn đến chọn verify cho cả những đối tượng chỉ nên trả dữ liệu stub.
2. **Mock chính đơn vị đang kiểm tra.** Test có thể chỉ xác nhận kịch bản đã cấu hình, bỏ qua logic thật cần kiểm chứng.
3. **Mock đối tượng giá trị đơn giản.** Mất cơ hội kiểm tra tính đúng đắn của phép tính và bất biến.
4. **Verify mọi lời gọi nội bộ.** Refactor nhỏ không đổi hành vi cũng làm test vỡ.
5. **Dùng fake để kết luận SQL/HTTP thật chính xác.** Bỏ sót lỗi giao thức, mapping, transaction và cấu hình.
6. **Spy đối tượng thật có I/O.** Một phương thức chưa stub có thể gọi mạng hoặc ghi dữ liệu ngoài ý muốn.
7. **Bỏ qua lời gọi gây tác dụng phụ trong đường lỗi.** Dễ gửi thông báo hoặc thanh toán khi validation thất bại.
8. **Dùng dữ liệu stub không hợp đồng.** Ví dụ stub trả giá âm dù API thật cam kết không âm, rồi test đi theo một trạng thái không hợp lệ mà không chỉ rõ mục đích.
9. **Chia sẻ fake mutable qua nhiều test.** Test phụ thuộc thứ tự chạy và kết quả không ổn định.
10. **Nhầm test xanh với đầy đủ bằng chứng.** Unit test tốt vẫn cần được bổ sung bằng integration/contract test ở những ranh giới quan trọng.

## 14. Bài tập tự luyện

### Bài tập 1 — Phân loại test double

Với từng tình huống, hãy chọn một loại double và giải thích:

1. Cần bảng giá trả cố định 50.000 đồng để test phép nhân với số lượng.
2. Cần kiểm tra một lệnh xác nhận đã được gửi với đúng mã đơn.
3. Cần lưu đơn và đọc lại bằng ID mà không chạy database.
4. Một tham số dịch vụ thông báo bắt buộc trong constructor nhưng nhánh kiểm tra dữ liệu sai không sử dụng nó.
5. Cần ghi lại danh sách sự kiện đã phát theo thứ tự để assert sau khi chạy.

*Gợi ý:* (1) stub; (2) mock hoặc spy; (3) fake; (4) dummy; (5) recording spy. Cùng một framework có thể tạo nhiều loại nhưng vai trò của chúng khác nhau.

### Bài tập 2 — Chọn assertion bền vững

Một hàm **calculateTotal()** dùng hai helper **sumLines()** và **applyDiscount()**. Test hiện chỉ verify cả hai helper đã được gọi đúng một lần. Sau refactor, hai helper được hợp nhất, nhưng số tiền cuối cùng không đổi.

Hãy trả lời:
- Test cũ đang bảo vệ hợp đồng hay chi tiết triển khai?
- Các trường hợp biên nào nên được assert bằng kết quả?
- Khi nào việc verify một lời gọi là cần thiết?

*Gợi ý:* Kiểm tra kết quả tính tiền, đơn hàng rỗng, mức giảm bằng ngưỡng, giảm giá không hợp lệ nếu hợp đồng quy định. Verify có giá trị khi tác dụng phụ hoặc số lần gọi là cam kết thật.

### Bài tập 3 — Fake không tương đương database

Một fake repository cho phép lưu hai đơn cùng **orderId**. Khi chạy môi trường thật, database từ chối vì khóa chính trùng.

Hãy đề xuất:
- Bất biến nào phải có trong hợp đồng repository?
- Fake cần mô phỏng điều gì trong unit test?
- Integration test nào vẫn phải chạy với database thật?

*Gợi ý:* Làm rõ hành vi khi khóa trùng; fake có thể từ chối trùng để test logic ứng dụng. Database integration test kiểm chứng ràng buộc SQL, transaction và mapping thực.

### Bài tập 4 — Dùng mock ở ranh giới nghiệp vụ

Một phương thức kiểm tra quyền trước khi phát lệnh chuyển tiền. Khi người gọi không đủ quyền, yêu cầu phải bị từ chối và **không được gửi lệnh**.

Hãy viết pseudocode hoặc JUnit/Mockito test có hai assertion:
1. Phương thức trả lỗi từ chối phù hợp.
2. Mock cổng chuyển tiền nhận **không có tương tác**.

*Gợi ý:* Khi lệnh chuyển tiền có tác dụng phụ, assertion về **không gọi** là một phần của hợp đồng bảo mật. Không cần verify mọi helper kiểm tra quyền bên trong.

### Bài tập 5 — Thời gian và độ ổn định của test

Một test voucher ngủ **2 giây** rồi xác nhận voucher đã hết hạn. Test thỉnh thoảng thất bại trong CI.

Hãy giải thích vì sao nên truyền **Clock**, dùng **Clock.fixed** ở hai thời điểm trước và đúng deadline, và việc này chưa kiểm chứng điều gì về scheduler hoặc hệ thống phân tán thật.

## 15. Tự kiểm tra kiến thức

**Câu 1.** Sử dụng **Mockito.mock(...)** có nghĩa đối tượng luôn đóng vai trò mock theo thuật ngữ test double không?

*Trả lời:* Không. Khi chỉ cấu hình dữ liệu trả về, đối tượng có thể đóng vai trò stub. Khi xác minh kỳ vọng về tương tác, nó đóng vai trò mock.

**Câu 2.** Có nên verify repository.save(...) trong mọi unit test tạo đơn?

*Trả lời:* Không bắt buộc. Nếu có thể quan sát đơn được lưu trong fake store, kiểm tra trạng thái thường diễn đạt mục tiêu rõ hơn. Verify có thể cần khi giao tiếp với repository là tác dụng phụ quan trọng và không có cách quan sát phù hợp khác.

**Câu 3.** Một fake Map hoạt động hoàn hảo có chứng minh transaction trong PostgreSQL hoạt động đúng không?

*Trả lời:* Không. Map không phản ánh đầy đủ transaction, khóa, isolation, SQL mapping hay lỗi kết nối. Cần kiểm thử adapter/database.

**Câu 4.** Vì sao **verifyNoInteractions(...)** đôi khi rất quan trọng?

*Trả lời:* Nó kiểm tra rằng một ranh giới có tác dụng phụ **không được gọi** trong tình huống bị từ chối, ví dụ dữ liệu sai hoặc thiếu quyền.

**Câu 5.** Có phải càng nhiều mock thì lớp càng dễ kiểm thử?

*Trả lời:* Không. Một lớp cần quá nhiều mock để chạy test có thể đang gánh quá nhiều trách nhiệm hoặc phụ thuộc quá rộng. Cần xem lại ranh giới và chọn test thích hợp.

**Câu 6.** Nếu một test fail sau khi chỉ đổi cách tổ chức phương thức private mà hành vi công khai không đổi, cần xem lại điều gì?

*Trả lời:* Test có thể đã ràng buộc vào chi tiết triển khai như lời gọi helper hay thứ tự nội bộ. Cần kiểm tra assertion có xuất phát từ hợp đồng thật hay không.

## Ghi nhớ

**Test double** giúp kiểm soát phụ thuộc khi kiểm thử nhưng phải được chọn theo mục tiêu: **stub** cấp dữ liệu hoặc lỗi định trước, **fake** cung cấp hành vi đơn giản có thể quan sát trạng thái, **spy** ghi nhận tương tác, **mock** xác nhận kỳ vọng quan trọng và **dummy** chỉ hiện diện ở nhánh không sử dụng. Test nên bảo vệ **kết quả, trạng thái và tác dụng phụ có ý nghĩa trong hợp đồng**, tránh kiểm tra mọi chi tiết triển khai. Unit test với double cung cấp phản hồi nhanh và rõ; **contract test, integration test và kiểm thử tình huống lỗi** tiếp tục kiểm tra các ranh giới mà double không mô phỏng được. Sử dụng đúng đối tượng thay thế giúp mã đáng tin cậy, dễ đọc test và dễ thay đổi hơn.
