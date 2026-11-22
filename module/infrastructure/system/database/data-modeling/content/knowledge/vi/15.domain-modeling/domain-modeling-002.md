# Thực thể, đối tượng giá trị và dịch vụ miền trong mô hình dữ liệu

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt **thực thể** (*entity*), **đối tượng giá trị** (*value object*) và **dịch vụ miền** (*domain service*) theo danh tính, quy tắc so sánh, vòng đời và trách nhiệm nghiệp vụ.
- Phân tích một yêu cầu để quyết định khái niệm nào cần khóa định danh, khái niệm nào nên là giá trị bất biến và quy tắc nào thuộc dịch vụ miền.
- Chuyển mô hình thành khóa, quan hệ, ràng buộc, chỉ mục và transaction mà vẫn bảo vệ được bất biến nghiệp vụ.
- Phân biệt dịch vụ miền, dịch vụ ứng dụng, dịch vụ hạ tầng và ranh giới nhất quán của aggregate.
- Đánh giá cách ánh xạ các khái niệm trên sang dữ liệu quan hệ, document, đồ thị và phân tích.

Trong module **DATABASE_DATA_MODELING**, thiết kế dữ liệu bắt đầu từ việc hiểu một yêu cầu nghiệp vụ: khách được sửa số lượng hàng trước khi xác nhận đơn, nhưng đơn giá đã chốt không được thay đổi theo giá danh mục ngày hôm sau. Chỉ liệt kê các bảng Customer, Order, Product chưa đủ; cần biết đối tượng nào có vòng đời, giá trị nào được giữ nguyên và ai chịu trách nhiệm áp dụng quy tắc.

## 1. Phân biệt ba vai trò trong mô hình miền

Xét ba nhận định:

1. Đơn hàng #A123 vẫn là cùng một đơn sau khi khách đổi địa chỉ giao hàng.
2. Hai khoản tiền 100.000 VND có cùng ý nghĩa nghiệp vụ nếu số tiền và loại tiền bằng nhau.
3. Mức giảm giá của một đơn được tính từ các dòng hàng, hạng thành viên và chính sách khuyến mãi hiện hành.

Nhận định (1) cần **thực thể** vì một danh tính tồn tại qua thay đổi. Nhận định (2) cần **đối tượng giá trị** vì nội dung xác định sự bằng nhau. Nhận định (3) có thể cần **dịch vụ miền** nếu hành vi tính giá là quy tắc kết hợp nhiều khái niệm, không thuộc trách nhiệm tự nhiên của một đối tượng.

| Khía cạnh | Entity | Value Object | Domain Service |
| --- | --- | --- | --- |
| Điều làm nên ý nghĩa | Danh tính và vòng đời | Tập giá trị thành phần | Hành vi/chính sách nghiệp vụ |
| So sánh | Cùng danh tính trong phạm vi xác định | Các thuộc tính giá trị tương đương | Không cần cơ chế nhận diện đối tượng như entity |
| Thay đổi | Trạng thái có thể đổi, danh tính ổn định | Ưu tiên bất biến và thay thế bằng giá trị mới | Thực hiện thao tác, thường không lưu trạng thái nghiệp vụ dài hạn |
| Ví dụ | Order, Customer, InventoryReservation | Money, DateRange, AddressSnapshot | MembershipDiscountService, CommissionPolicy |
| Lưu trữ | Bản ghi có khóa, có vòng đời | Cột nhúng, document lồng nhau hoặc cấu trúc chuyên biệt | Mã nghiệp vụ; không mặc định có bảng riêng |

Đây là các **vai trò thuộc mô hình miền**, không phải phép đối chiếu một một với class Java hay bảng SQL. Một hàng trong database chưa chắc là entity của miền; một value object có thể trải trên nhiều cột, đôi khi được lưu ở bảng riêng vì nhu cầu kỹ thuật.

## 2. Thực thể: cùng danh tính qua nhiều trạng thái

### 2.1. Danh tính không phải tên hay mọi thuộc tính

Khách hàng đổi tên, số điện thoại hoặc địa chỉ vẫn là cùng một Customer. Đơn hàng đổi trạng thái từ nháp sang xác nhận vẫn là cùng một Order. Nếu mô hình nhận diện bằng các thuộc tính có thể thay đổi, liên kết và lịch sử rất dễ bị sai.

Những lựa chọn về định danh cần được tách rõ:

- **Khóa nội bộ:** UUID hoặc BIGINT sinh tự động; thường dùng để ổn định liên kết dữ liệu.
- **Mã nghiệp vụ:** mã đơn cho khách nhìn thấy, mã hợp đồng, số hồ sơ. Mã này có thể có quy tắc riêng về định dạng và phạm vi duy nhất.
- **Danh tính phụ thuộc cha:** dòng đơn số 1 chỉ duy nhất trong đơn cụ thể; khóa ghép (order_id, line_no) có ý nghĩa. Hai dòng có cùng số thứ tự ở hai đơn khác nhau không phải cùng thực thể.

Email và số điện thoại thường không nên dùng làm định danh bất biến của Customer vì có thể thay đổi hoặc được tái sử dụng. Nếu email cần duy nhất trong một phạm vi, đó là **một ràng buộc nghiệp vụ riêng**, không nhất thiết là khóa chính.

### 2.2. Thực thể có vòng đời và hành vi

Giả sử Order tuân theo quy tắc sau:

~~~mermaid
stateDiagram-v2
    [*] --> DRAFT: Tạo đơn
    DRAFT --> DRAFT: Chỉnh dòng hàng
    DRAFT --> CONFIRMED: Xác nhận
    DRAFT --> CANCELLED: Hủy
    CONFIRMED --> [*]
    CANCELLED --> [*]
~~~

- Chỉ Order ở trạng thái DRAFT được sửa dòng hàng.
- Trước khi xác nhận, đơn phải có ít nhất một dòng và từng dòng có số lượng lớn hơn 0.
- Đơn giá đã chốt phải được lưu để bảo toàn lịch sử; cập nhật giá niêm yết không tự sửa đơn cũ.
- Nếu lưu tổng tiền, tổng này phải khớp với dữ liệu dòng hàng, loại tiền và quy tắc làm tròn.

Đây là **bất biến** và quy tắc chuyển trạng thái của miền. Bất biến phải được thực thi trên mọi đường ghi dữ liệu, không chỉ trong biểu mẫu giao diện. Khi có cập nhật đồng thời, giao dịch và kiểm soát xung đột ở tầng lưu trữ cũng cần tham gia bảo vệ.

### 2.3. Entity và aggregate không đồng nghĩa

**Aggregate** là nhóm các đối tượng được quản lý qua một **aggregate root** để bảo vệ những bất biến cần nhất quán trong một giao dịch cục bộ.

Ví dụ: Order có thể là aggregate root và OrderLine là entity con. Khi đổi số lượng dòng, yêu cầu nên đi qua hành vi của Order để kiểm tra trạng thái và tính lại tổng. Customer có vòng đời khác Order nên thường là aggregate khác. Order chỉ cần giữ customerId và bản chụp thông tin đã cam kết, không tự đổi hồ sơ của Customer.

**Bounded context** xác định nơi một mô hình/ngôn ngữ nghiệp vụ có hiệu lực; aggregate xác định ranh giới nhất quán của các thay đổi. Một bounded context có nhiều aggregate. Việc đặt hai bảng vào cùng schema chưa chứng minh chúng thuộc cùng aggregate.

## 3. Đối tượng giá trị: bằng nhau theo nội dung

Một **value object** không có danh tính nghiệp vụ độc lập. Hai giá trị Money cùng amount và currency phải tương đương theo quy tắc của kiểu Money, bất kể nơi tạo ra chúng. Ngược lại, 100.000 VND và 100.000 USD là hai giá trị khác nhau.

| Value object | Thành phần có ý nghĩa | Quy tắc cần bảo vệ |
| --- | --- | --- |
| Money | amount, currency | Cộng tiền cùng loại, định nghĩa độ chính xác và làm tròn |
| DateRange | start, end | start không sau end; nêu rõ khoảng đóng hay nửa mở |
| Quantity | amount, unit | Không cộng tùy tiện 2 kg và 3 cái |
| GeoCoordinate | latitude, longitude | Vĩ độ và kinh độ phải trong miền hợp lệ |
| AddressSnapshot | người nhận, địa chỉ, khu vực, quốc gia | Lưu thông tin tại thời điểm giao dịch; thay cả giá trị khi sửa |

Đối tượng giá trị nên **tự kiểm tra hợp lệ** khi tạo và ưu tiên **bất biến (immutable)**. Chẳng hạn, thay vì sửa các trường street/city của một AddressSnapshot được nhiều đơn cùng tham chiếu, hãy tạo AddressSnapshot mới và gán cho đơn còn được phép sửa.

Một value object không chỉ chứa dữ liệu. Money có thể cộng, trừ, so sánh; DateRange có thể kiểm tra giao nhau. Đặt hành vi vào đúng kiểu giúp tránh tập hợp các biến nguyên thủy tách rời và giảm nhu cầu viết những lớp service không cần thiết.

**Lưu ý về ngữ nghĩa:** hai địa chỉ có chuỗi giống nhau không chứng minh chúng cùng một địa điểm vật lý. Nếu cần quản lý một địa điểm có mã số, trạng thái xác minh và lịch sử thay đổi, khái niệm DeliveryLocation có thể trở thành entity. Còn địa chỉ đã ghi trên một đơn thường chỉ là value object snapshot.

## 4. Dịch vụ miền: nơi đặt quy tắc không có chủ thể tự nhiên

**Domain service** biểu diễn một thao tác hoặc chính sách có ý nghĩa nghiệp vụ nhưng không thuộc tự nhiên về một entity hay value object duy nhất. Ví dụ quy tắc giảm giá phụ thuộc cả nội dung đơn, cấp thành viên và chương trình khuyến mãi. Order không sở hữu toàn bộ chính sách thành viên; cũng không nên tự gọi cơ sở dữ liệu để nạp thông tin hội viên mỗi lần tính giá.

Một cách thiết kế là để MembershipDiscountService nhận đầu vào đã chuẩn bị và trả về Money giảm giá. Dịch vụ miền xử lý **chính sách tính**, còn việc nạp dữ liệu, quản lý transaction và lưu kết quả thuộc trách nhiệm khác.

| Loại dịch vụ | Trách nhiệm | Ví dụ |
| --- | --- | --- |
| **Domain service** | Tính toán hoặc quyết định quy tắc nghiệp vụ | Tính giảm giá từ đơn + hạng thành viên + phiên bản chính sách |
| **Application service** | Điều phối một use case, kiểm quyền, nạp/lưu aggregate, mở transaction | ConfirmOrderUseCase |
| **Infrastructure service** | Kết nối cơ sở dữ liệu, API, hệ thống gửi thông báo | PostgresOrderRepository, PaymentGatewayAdapter |

Một domain service có thể nhận interface để truy vấn thông tin miền, nhưng phải thiết kế rõ tác động tới transaction và độ trễ. Với phép tính giá, truyền bản dữ liệu cần thiết giúp thao tác dễ kiểm thử, độc lập hạ tầng và không vô tình phát sinh I/O.

**Không dồn mọi nghiệp vụ vào OrderService:** nếu Order chỉ có getter/setter và OrderService tự sửa trạng thái, số lượng, giá và tổng tiền, bất biến sẽ phân tán. Hành vi liên quan trực tiếp một aggregate nên nằm ở chính aggregate; domain service dành cho quy tắc không có chủ sở hữu tự nhiên.

## 5. Ví dụ Java: Order, OrderLine, Money và dịch vụ tính giảm giá

Ví dụ sau giả định đơn dùng một loại tiền, giá có hai chữ số thập phân và chương trình giảm giá theo hạng thành viên. Hệ thống thực tế phải xét số chữ số lẻ theo từng loại tiền, thuế và quy tắc làm tròn.

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.ArrayList;
import java.util.Currency;
import java.util.List;
import java.util.Objects;
import java.util.UUID;

// VALUE OBJECT: so sánh theo giá trị, không cần ID.
record Money(BigDecimal amount, Currency currency) {
    Money {
        Objects.requireNonNull(amount);
        Objects.requireNonNull(currency);
        amount = amount.setScale(2, RoundingMode.UNNECESSARY);
    }

    Money add(Money other) {
        if (!currency.equals(other.currency())) {
            throw new IllegalArgumentException("Different currencies");
        }
        return new Money(amount.add(other.amount), currency);
    }

    Money multiply(int quantity) {
        if (quantity <= 0) throw new IllegalArgumentException("quantity <= 0");
        return new Money(amount.multiply(BigDecimal.valueOf(quantity)), currency);
    }
}

// ENTITY CON: lineId giữ nguyên khi sửa số lượng.
final class OrderLine {
    private final UUID lineId;
    private final String productId;
    private final Money unitPriceSnapshot;
    private int quantity;

    OrderLine(UUID lineId, String productId, Money unitPrice, int quantity) {
        this.lineId = Objects.requireNonNull(lineId);
        this.productId = Objects.requireNonNull(productId);
        this.unitPriceSnapshot = Objects.requireNonNull(unitPrice);
        changeQuantity(quantity);
    }

    UUID lineId() { return lineId; }
    Money subtotal() { return unitPriceSnapshot.multiply(quantity); }

    void changeQuantity(int newQuantity) {
        if (newQuantity <= 0) throw new IllegalArgumentException("quantity <= 0");
        quantity = newQuantity;
    }
}

enum OrderStatus { DRAFT, CONFIRMED, CANCELLED }
enum CustomerTier { NORMAL, SILVER, GOLD }

// AGGREGATE ROOT: thao tác sửa dòng hàng phải qua Order.
final class Order {
    private final UUID id;
    private final Currency currency;
    private final List<OrderLine> lines = new ArrayList<>();
    private OrderStatus status = OrderStatus.DRAFT;

    Order(UUID id, Currency currency) {
        this.id = Objects.requireNonNull(id);
        this.currency = Objects.requireNonNull(currency);
    }

    void addLine(UUID lineId, String productId, Money price, int quantity) {
        requireDraft();
        if (!currency.equals(price.currency())) {
            throw new IllegalArgumentException("Currency mismatch");
        }
        if (lines.stream().anyMatch(line -> line.lineId().equals(lineId))) {
            throw new IllegalArgumentException("Duplicate line identity");
        }
        lines.add(new OrderLine(lineId, productId, price, quantity));
    }

    void changeQuantity(UUID lineId, int quantity) {
        requireDraft();
        OrderLine line = lines.stream()
            .filter(item -> item.lineId().equals(lineId))
            .findFirst()
            .orElseThrow(() -> new IllegalArgumentException("Line not found"));
        line.changeQuantity(quantity);
    }

    Money subtotal() {
        Money result = new Money(BigDecimal.ZERO, currency);
        for (OrderLine line : lines) result = result.add(line.subtotal());
        return result;
    }

    void confirm() {
        requireDraft();
        if (lines.isEmpty()) throw new IllegalStateException("Order is empty");
        status = OrderStatus.CONFIRMED;
    }

    private void requireDraft() {
        if (status != OrderStatus.DRAFT) {
            throw new IllegalStateException("Order cannot be changed");
        }
    }
}

// DOMAIN SERVICE: tính quy tắc liên quan cả đơn và chính sách hội viên.
final class MembershipDiscountService {
    Money discountFor(Order order, CustomerTier tier) {
        BigDecimal rate = switch (Objects.requireNonNull(tier)) {
            case NORMAL -> new BigDecimal("0.00");
            case SILVER -> new BigDecimal("0.05");
            case GOLD -> new BigDecimal("0.10");
        };
        Money subtotal = order.subtotal();
        BigDecimal reduction = subtotal.amount()
            .multiply(rate).setScale(2, RoundingMode.HALF_UP);
        return new Money(reduction, subtotal.currency());
    }
}
~~~

Các quyết định cần quan sát:

- Order và OrderLine có **danh tính riêng trong phạm vi phù hợp**; sửa số lượng không tạo dòng mới, sửa trạng thái không tạo đơn mới.
- Money có hai thành phần amount/currency, được chuẩn hóa về hai chữ số thập phân để tránh sai khác do scale của BigDecimal khi so sánh theo giá trị trong ví dụ này.
- Order chặn thêm dòng trùng ID, sửa sau xác nhận và xác nhận đơn rỗng. OrderLine không được đưa ra ngoài để các lớp khác tự ý thay đổi, vượt qua quy tắc aggregate root.
- MembershipDiscountService áp dụng chính sách từ những giá trị đã truyền vào. Ứng dụng cần quyết định thời điểm chốt hạng thành viên, phiên bản quy tắc và lưu giảm giá đã áp dụng nếu phải truy vết.

Đây là mã minh họa miền, chưa bao gồm transaction, persistence, chính sách thuế hay giảm giá phân bổ theo dòng. Phương thức confirm() cũng không tự chứng minh kho đã giữ hàng hoặc giao dịch thanh toán thành công; điều kiện xuyên ngữ cảnh cần quy trình phối hợp riêng.

## 6. Ánh xạ mô hình sang lược đồ quan hệ

Một ví dụ PostgreSQL:

~~~sql
CREATE SCHEMA sales;

CREATE TABLE sales.orders (
    order_id UUID PRIMARY KEY,
    customer_id UUID NOT NULL,
    status VARCHAR(12) NOT NULL
        CHECK (status IN ('DRAFT', 'CONFIRMED', 'CANCELLED')),
    currency VARCHAR(3) NOT NULL
        CHECK (currency ~ '^[A-Z]{3}$'),
    -- AddressSnapshot lưu dưới dạng các cột của Order.
    shipping_recipient TEXT NOT NULL,
    shipping_street TEXT NOT NULL,
    shipping_city TEXT NOT NULL,
    shipping_country_code VARCHAR(2) NOT NULL,
    version BIGINT NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE sales.order_line (
    order_id UUID NOT NULL
        REFERENCES sales.orders(order_id),
    line_id UUID NOT NULL,
    product_id VARCHAR(64) NOT NULL,
    product_name_snapshot TEXT NOT NULL,
    unit_price_amount NUMERIC(19, 2) NOT NULL
        CHECK (unit_price_amount >= 0),
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    PRIMARY KEY (order_id, line_id)
);
~~~

**Order** tương ứng với một hàng có khóa order_id; **OrderLine** có danh tính duy nhất trong Order bằng khóa ghép (order_id, line_id). Khóa này đồng thời hỗ trợ truy vấn dòng theo order_id vì đây là tiền tố của chỉ mục khóa chính.

**Money** của giá dòng được tách thành unit_price_amount và currency của Order: ví dụ đơn chỉ cho phép một loại tiền, nên khi tái tạo Money cho một dòng, lớp ánh xạ kết hợp amount của dòng với currency của đơn. Nếu cho phép các dòng khác loại tiền, cần thay đổi mô hình và quy tắc chuyển đổi rõ ràng.

**AddressSnapshot** không cần address_id riêng: các cột shipping_* cùng biểu diễn giá trị của địa chỉ lúc đặt. Việc lưu địa chỉ trong Customer và tham chiếu động có thể làm đơn lịch sử thay đổi khi hồ sơ hiện tại bị cập nhật.

**MembershipDiscountService** không cần bảng chỉ vì có từ "service". Tuy nhiên, nếu chính sách thay đổi theo thời gian, nghiệp vụ có thể cần bảng policy có mã, hiệu lực và phiên bản, cùng khoản giảm giá đã chốt trên đơn. Phải tách **dịch vụ xử lý quy tắc** khỏi **dữ liệu mô tả chính sách**.

Sử dụng product_id để đối chiếu Catalog và product_name_snapshot/giá để giữ lịch sử. Nếu Product thuộc bounded context khác, tránh giả định FK xuyên hệ thống luôn hợp lý; quyền sở hữu, giao diện tích hợp và cách xử lý tham chiếu không tồn tại phải được định nghĩa.

### Những bất biến SQL không tự đảm bảo

PRIMARY KEY, FOREIGN KEY, CHECK, NOT NULL bảo vệ ràng buộc từng hàng và quan hệ cục bộ. Tuy nhiên:

1. CHECK trên status chỉ giới hạn tập trạng thái, không cấm chuyển trực tiếp từ CANCELLED sang CONFIRMED.
2. "Đơn CONFIRMED phải có dòng" là điều kiện trên nhiều hàng, cần được bảo vệ trong transaction hoặc bằng cơ chế DB phù hợp.
3. "Không sửa giá sau xác nhận" liên quan bảng Order và dòng, cần chặn mọi đường ghi; tùy độ nghiêm ngặt có thể bổ sung quyền truy cập và trigger.
4. Khi hai yêu cầu cùng sửa đơn, phải có khóa hoặc kiểm tra phiên bản. Một giao dịch đọc rồi ghi mà không kiểm soát xung đột có thể mất cập nhật.

Ví dụ một bước đổi trạng thái có điều kiện:

~~~sql
UPDATE sales.orders
SET status = 'CONFIRMED', version = version + 1
WHERE order_id = :order_id
  AND status = 'DRAFT'
  AND version = :expected_version;
~~~

Ứng dụng phải kiểm tra số hàng được cập nhật; nếu bằng 0, trạng thái/phiên bản đã thay đổi và phải xử lý xung đột. Khi sửa dòng hàng, thao tác này cũng cần tham gia cùng transaction và chiến lược kiểm soát phiên bản của Order; chỉ tăng version lúc xác nhận chưa đủ để bảo vệ các thao tác sửa dòng cạnh tranh.

## 7. Những trường hợp dễ chọn nhầm entity và value object

### OrderLine là gì?

Nếu nghiệp vụ cần sửa, xóa, hoàn trả, đối chiếu và theo dõi từng dòng theo ID, OrderLine có danh tính trong Order nên là entity con. Nếu giỏ hàng luôn được thay toàn bộ như một danh sách giá trị và không có vòng đời từng phần tử, tập các value object cũng có thể hợp lý. Việc có bảng riêng không tự quyết định vai trò miền.

### Địa chỉ là gì?

Địa chỉ giao hàng đã chốt thường là AddressSnapshot value object. Một mục trong "sổ địa chỉ" mà khách tạo, đặt tên, chỉnh sửa, xóa và quản lý riêng có thể là SavedAddress entity. Hai khái niệm có các trường văn bản giống nhau nhưng vòng đời khác nhau.

### Mã định danh có phải entity?

OrderId có thể là value object bọc UUID nhằm không truyền nhầm sang CustomerId. Điều đó không biến Order thành value object: **mã định danh** là một giá trị còn **đơn hàng** là đối tượng có lịch sử, trạng thái và danh tính.

### Số tiền và tỷ giá

Money thường là value object. Tỷ giá tại một thời điểm là một giá trị có đơn vị và nguồn; nếu cần theo dõi từng lần ban hành, nhà cung cấp, hiệu lực và chỉnh sửa, bản ghi ExchangeRateQuote có thể trở thành entity hoặc sự kiện lịch sử riêng. Việc lựa chọn dựa vào nhu cầu theo dõi danh tính của chính bản ghi đó.

Một phép thử hữu ích: "Nếu hai đối tượng có mọi thuộc tính hiện tại giống nhau, nghiệp vụ vẫn cần phân biệt chúng không?" Nếu có, thường cần entity. "Nếu thay một đối tượng bằng bản sao có giá trị tương đương, nghiệp vụ có nhận ra sự khác biệt không?" Nếu không, thường là value object.

## 8. Xác định đúng trách nhiệm của dịch vụ miền

Xét chính sách: khách GOLD giảm 10% tiền hàng, tối đa 200.000 VND, chỉ áp dụng với sản phẩm đủ điều kiện; voucher riêng có thứ tự áp dụng đã thỏa thuận.

- **Order** sở hữu dòng hàng, giá đã chốt, trạng thái và khoản giảm cuối cùng của đơn.
- **Membership** cung cấp hạng thành viên có hiệu lực tại thời điểm áp dụng.
- **Promotion policy** diễn đạt tỷ lệ, mức trần, đối tượng áp dụng, thứ tự chiết khấu và phiên bản hiệu lực.
- **Pricing domain service** tính giá trị giảm, phân bổ theo dòng nếu cần, trả kết quả có ý nghĩa nghiệp vụ.
- **Application service** nạp dữ liệu, kiểm tra quyền/điều kiện, chọn phiên bản chính sách, gọi miền, ghi kết quả trong transaction và phát thông điệp tích hợp nếu có.

Nếu tính toán thực ra chỉ thuộc riêng Money, đặt hành vi trong Money; nếu thay đổi chỉ dựa trên trạng thái Order, đặt trong Order. Chỉ tạo domain service khi hành vi miền không có chủ sở hữu tự nhiên, tránh biến mọi hành vi thành phương thức service.

Trong mô hình dữ liệu, cần quyết định **lưu kết quả nào**: discount_amount, policy_id, policy_version, từng khoản phân bổ giảm trên dòng để hoàn tiền chính xác. Không tính lại đơn lịch sử theo chính sách hôm nay nếu hợp đồng với khách yêu cầu bảo toàn giá trị đã chốt.

## 9. Cùng một mô hình, nhiều kiểu lưu trữ

| Kiểu lưu trữ | Ánh xạ thường gặp | Điểm cần kiểm chứng |
| --- | --- | --- |
| Quan hệ | Order và OrderLine thành các bảng; Money/Address thành các cột | FK, UNIQUE, CHECK, transaction, kiểm soát cập nhật đồng thời |
| Document | Document Order chứa lines và shippingAddress | Đọc/ghi theo aggregate thuận tiện; chú ý giới hạn document và thực thể có vòng đời riêng |
| Đồ thị | Order, Customer, Product là nút và liên kết là cạnh | Cạnh hỗ trợ duyệt quan hệ, nhưng không tự quyết định quyền sở hữu và bất biến |
| Phân tích/cột | FactOrderLine và dimension lịch sử | Phục vụ báo cáo/tổng hợp, thường là bản sao đọc chứ không thay thế nguồn ghi giao dịch |

Ví dụ biểu diễn Order dưới dạng document:

~~~json
{
  "orderId": "b188c0f3-83de-49be-8f84-fcdbbfbdc168",
  "status": "CONFIRMED",
  "currency": "VND",
  "shippingAddress": {
    "recipient": "Nguyen An",
    "street": "12 Nguyen Trai",
    "city": "Ho Chi Minh City",
    "countryCode": "VN"
  },
  "lines": [
    {
      "lineId": "9c640fdf-dfba-43d9-92f4-2b5e5f8646ed",
      "productId": "LAPTOP-001",
      "unitPriceAmount": "23000000.00",
      "quantity": 1
    }
  ]
}
~~~

Order vẫn là entity, Money vẫn là value object và OrderLine vẫn có thể là entity con. Chuyển từ bảng sang document **không đổi bản chất miền**. Tiền ở ví dụ JSON dùng chuỗi thập phân để tránh các lớp xử lý số thực nhị phân làm mất độ chính xác; ứng dụng cần chuyển sang decimal thích hợp.

Trong kho đồ thị hoặc phân tích, các thuật ngữ node, edge, fact, dimension mô tả cấu trúc lưu/truy vấn; chúng không tự tương đương với entity/value object trong thiết kế miền.

## 10. Những lỗi mô hình hóa thường gặp

| Dấu hiệu | Hệ quả | Hướng sửa |
| --- | --- | --- |
| Tạo ID riêng cho mọi Money và AddressSnapshot | Join thừa, danh tính giả, khó kiểm soát giá trị hợp lệ | Dùng value object và lưu theo aggregate |
| So sánh Customer theo tên hoặc số điện thoại | Đổi thông tin làm mất nhận diện | Chọn danh tính ổn định, ràng buộc duy nhất tách biệt |
| Dùng double để lưu tiền | Sai số biểu diễn nhị phân và làm tròn | BigDecimal/NUMERIC cùng currency và chính sách làm tròn |
| Sửa AddressSnapshot dùng chung nhiều đơn | Lịch sử giao hàng thay đổi ngoài ý muốn | Value object bất biến, thay bằng snapshot mới |
| Mọi quy tắc nằm trong các lớp tên Service | Entity chỉ còn CRUD, bất biến bị phân tán | Trả hành vi đúng về entity/value object |
| Domain service tự gọi HTTP và ghi DB tùy tiện | Khó kiểm thử, transaction và thất bại khó kiểm soát | Tách orchestration ứng dụng và adapter hạ tầng |
| Chỉ dùng CHECK cho trạng thái đơn | Cho phép chuyển trạng thái sai quy trình | Bảo vệ state machine trong hành vi miền và thao tác ghi |
| Dùng FK để đồng nhất mọi ngữ cảnh | Phụ thuộc schema/vòng đời ngoài trách nhiệm | Quyết định chủ sở hữu và hợp đồng tích hợp trước |

## 11. Bài tập thực hành

**Tình huống:** Một hệ thống đặt lịch khám quản lý bệnh nhân, lịch hẹn, khoảng thời gian khám, địa chỉ phòng khám và phí hủy. Bệnh nhân có thể đổi số điện thoại. Phòng khám có thể chuyển địa điểm trong tương lai; lịch đã đặt cần lưu địa điểm và mức phí đã cam kết.

**Yêu cầu:**

1. Phân loại Patient, Appointment, TimeSlot, ClinicAddressSnapshot và CancellationFeePolicy thành entity, value object hoặc chính sách/dịch vụ miền. Giải thích.
2. Viết ba bất biến nghiệp vụ và đề xuất khóa chính/khóa ngoại cho dữ liệu lịch hẹn.
3. Cho biết thông tin nào cần lưu snapshot và cách phòng tránh hai người đặt trùng giờ cho một bác sĩ.
4. Nêu điểm khác nhau giữa kiểm tra trạng thái mỗi hàng với kiểm tra chồng lấp khoảng thời gian nhiều hàng.

**Hướng giải tham khảo:**

- Patient và Appointment là entity vì có danh tính/vòng đời. TimeSlot(start, end) là value object với điều kiện start < end. ClinicAddressSnapshot là value object ghi lại địa điểm lúc đặt. Chính sách phí có thể là value object mô tả tỷ lệ/điều kiện; phép tính dựa trên nhiều đầu vào (thời gian hủy, loại lịch, phiên bản chính sách) có thể thuộc domain service.
- Bất biến ví dụ: start trước end; không có hai lịch đang chiếm chỗ của cùng bác sĩ với thời gian giao nhau; lịch đã hoàn thành hoặc hủy không được tùy ý đổi giờ. Bảng appointment có các trường appointment_id, patient_id, doctor_id, start_at, end_at, status, address_snapshot..., fee_amount, currency, policy_version, version.
- Chống đặt trùng giờ là ràng buộc **giữa nhiều hàng**. Trong PostgreSQL có thể dùng exclusion constraint theo doctor_id và khoảng thời gian đối với lịch còn hiệu lực, hoặc thiết kế transaction/lock phù hợp. Chỉ đọc thấy trống rồi INSERT có thể gặp race condition; CHECK từng hàng không đủ.
- Snapshot địa điểm, giá và phiên bản chính sách giúp lịch đã xác nhận không thay đổi theo dữ liệu hiện tại.

## 12. Checklist rà soát mô hình

- Đối tượng nào có danh tính và lịch sử riêng? Khóa định danh có ổn định và phạm vi duy nhất có rõ không?
- Những giá trị nào cần được đóng gói và kiểm tra hợp lệ như Money, Quantity, DateRange hay AddressSnapshot?
- Hành vi nào thuộc entity/value object; hành vi nào thực sự cần domain service?
- Aggregate root nào kiểm soát thao tác cập nhật và bất biến trong một transaction?
- Ràng buộc nào DB có thể bảo vệ trực tiếp; ràng buộc nào cần state machine, khóa/phiên bản và phối hợp ứng dụng?
- Giá, địa chỉ, chính sách nào phải lưu snapshot và phiên bản để truy vết lịch sử?
- Cấu trúc quan hệ, document, đồ thị hoặc phân tích được chọn đã phục vụ đúng cách đọc/ghi và khả năng tiến hóa chưa?

**Kết luận:** Entity trả lời "đây có còn là cùng một đối tượng qua thời gian không?", value object trả lời "giá trị này được xác định bởi thành phần nào?", còn domain service mô tả "quy tắc nghiệp vụ nào không thuộc tự nhiên về một đối tượng?". Phân biệt đúng ba vai trò giúp chọn khóa, cấu trúc lưu trữ, ranh giới giao dịch và nơi đặt quy tắc nhất quán rõ ràng ngay từ yêu cầu nghiệp vụ.
