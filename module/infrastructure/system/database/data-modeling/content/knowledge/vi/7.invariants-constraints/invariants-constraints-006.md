# Phân chia ràng buộc giữa kiểu Java, mô hình miền, ứng dụng và cơ sở dữ liệu

Một quy tắc nghiệp vụ có thể được kiểm tra ở nhiều nơi trong hệ thống, nhưng mỗi lớp có trách nhiệm và khả năng bảo vệ khác nhau. Kiểu Java giúp biểu diễn dữ liệu đúng hình dạng; mô hình miền bảo vệ ý nghĩa và trạng thái hợp lệ của nghiệp vụ; lớp ứng dụng điều phối một ca sử dụng qua nhiều đối tượng và dịch vụ; cơ sở dữ liệu bảo vệ tính toàn vẹn trước mọi đường ghi, kể cả các tiến trình chạy đồng thời.

Nếu dồn mọi kiểm tra vào giao diện hoặc service, một luồng ghi khác có thể bỏ qua quy tắc. Nếu đưa mọi điều kiện vào database, mô hình miền lại khó diễn đạt và khó kiểm thử hành vi nghiệp vụ. Nếu lặp lại cùng một điều kiện ở nhiều lớp mà không xác định nguồn có thẩm quyền, các lớp có thể dần hiểu quy tắc theo cách khác nhau.

Trong **data modeling**, thiết kế bất biến cần đi cùng thiết kế ranh giới phần mềm. Câu hỏi không chỉ là “điều kiện nào phải đúng?” mà còn là “lớp nào hiểu điều kiện đó, lớp nào có thể thực thi nó đáng tin cậy, và lớp nào là hàng rào cuối cùng?”. Bài học này dùng hệ thống bán hàng để phân chia trách nhiệm giữa Java types, domain model, application layer và database.

## 1. Bốn lớp, bốn loại trách nhiệm

Một hệ thống Java thường có các lớp xử lý sau:

1. **Kiểu Java và cấu trúc đầu vào** mô tả hình dạng dữ liệu, miền giá trị cơ bản và cách chuyển đổi dữ liệu từ bên ngoài.
2. **Mô hình miền (domain model)** biểu diễn khái niệm nghiệp vụ, hành vi và các trạng thái hợp lệ của một thực thể hoặc aggregate.
3. **Lớp ứng dụng (application layer)** thực hiện ca sử dụng, điều phối nhiều aggregate, transaction, quyền truy cập và các cổng tích hợp.
4. **Cơ sở dữ liệu (database)** bảo vệ tính toàn vẹn lưu trữ bằng khóa, constraint, transaction và cơ chế đồng thời.

~~~mermaid
flowchart TD
    A[HTTP, message, import] --> B[Java types và input validation]
    B --> C[Application use case]
    C --> D[Domain model]
    D --> C
    C --> E[Transaction và repository]
    E --> F[Database constraints]
    F --> E
    E --> C
    C --> G[Response hoặc event]
~~~

Sơ đồ mô tả một luồng phổ biến, không phải thứ tự bắt buộc cho mọi kiến trúc. Một message consumer hoặc batch import có thể đi vào cùng application use case mà không qua HTTP. Database cũng có thể được truy cập bởi migration, công cụ quản trị hoặc dịch vụ khác, nên constraint trong database có vai trò bảo vệ chung.

### 1.1. Nguyên tắc phân chia

- Đặt quy tắc ở lớp có đủ ngữ nghĩa để diễn đạt nó.
- Đặt hàng rào ở nơi có thể bảo vệ tất cả đường ghi.
- Kiểm tra sớm để trả lỗi dễ hiểu, nhưng không nhầm kiểm tra sớm với bảo đảm cuối cùng.
- Không để lớp ngoài tự sửa trạng thái miền bằng cách gán trực tiếp các trường.
- Dùng transaction và constraint cho những bất biến có thể bị phá vỡ bởi thao tác đồng thời.
- Chỉ lặp lại kiểm tra khi mỗi lần kiểm tra có mục đích riêng, chẳng hạn xác thực đầu vào, bảo vệ domain và bảo vệ dữ liệu.

Một điều kiện có thể xuất hiện ở nhiều lớp mà không phải là sự trùng lặp vô ích. Ví dụ, API kiểm tra số lượng là số dương để trả lỗi sớm; domain object cũng không cho tạo dòng hàng có số lượng không hợp lệ; database CHECK bảo vệ dữ liệu nếu có đường ghi khác. Ba hàng rào phục vụ ba ranh giới khác nhau. Điều cần tránh là mỗi nơi tự định nghĩa một quy tắc khác nhau.

## 2. Kiểu Java: biểu diễn hình dạng và miền giá trị cơ bản

Kiểu Java giúp loại bỏ một số trạng thái sai ngay trong mã. Dùng LocalDate cho ngày lịch, Instant hoặc OffsetDateTime cho thời điểm, BigDecimal cho số thập phân chính xác và enum cho một tập giá trị hữu hạn sẽ rõ nghĩa hơn dùng String hoặc double cho mọi thứ.

### 2.1. Dùng kiểu phù hợp với ý nghĩa dữ liệu

| Ý nghĩa | Kiểu Java thường phù hợp | Cần lưu ý |
|---|---|---|
| Số lượng nguyên | int, long | Kiểm tra giới hạn và dấu |
| Số tiền, đơn giá | BigDecimal | Không dùng float hoặc double |
| Ngày lịch | LocalDate | Không gắn múi giờ nếu chỉ là ngày |
| Thời điểm tuyệt đối | Instant | Hiển thị theo múi giờ ở lớp trình bày |
| Thời điểm có offset | OffsetDateTime | Phân biệt offset với vùng thời gian |
| Trạng thái hữu hạn | enum | Enum Java không thay thế constraint DB |
| Mã định danh | UUID hoặc kiểu wrapper riêng | Không dùng String tùy ý ở mọi nơi |

Kiểu dữ liệu giúp compiler phát hiện một số lỗi, nhưng không tự bảo vệ mọi quy tắc. Một biến int vẫn có thể bằng không hoặc âm. Một BigDecimal vẫn có thể mang giá trị âm, scale quá lớn hoặc vượt miền cho phép. Một enum vẫn có thể không tương thích với giá trị cũ trong database sau khi ứng dụng được nâng cấp.

### 2.2. Tạo kiểu chuyên biệt thay cho primitive obsession

Nếu mọi ID đều là long, rất dễ truyền nhầm productId vào tham số customerId. Wrapper type giúp compiler phân biệt:

~~~java
public record CustomerId(long value) {
    public CustomerId {
        if (value <= 0) {
            throw new IllegalArgumentException("customerId must be positive");
        }
    }
}

public record ProductId(long value) {
    public ProductId {
        if (value <= 0) {
            throw new IllegalArgumentException("productId must be positive");
        }
    }
}

public void loadCustomer(CustomerId customerId) {
    // Không thể truyền ProductId vào tham số này.
}
~~~

Wrapper type cũng hữu ích cho mã hợp đồng, mã tiền tệ, số serial hoặc mã tenant. Tuy nhiên, không cần tạo một lớp riêng cho mọi cột nếu nó không mang ý nghĩa hoặc quy tắc riêng. Mục tiêu là làm rõ các khái niệm dễ bị nhầm lẫn.

### 2.3. Value object cho tiền

Tiền không chỉ là BigDecimal. Nó có số tiền và loại tiền tệ. Một phép cộng giữa USD và VND phải bị từ chối hoặc được quy đổi theo một quy tắc có tỷ giá rõ ràng.

~~~java
import java.math.BigDecimal;
import java.util.Currency;
import java.util.Objects;

public record Money(BigDecimal amount, Currency currency) {
    public Money {
        Objects.requireNonNull(amount, "amount");
        Objects.requireNonNull(currency, "currency");
    }

    public Money add(Money other) {
        if (!currency.equals(other.currency())) {
            throw new IllegalArgumentException("Currency mismatch");
        }
        return new Money(amount.add(other.amount), currency);
    }

    public boolean isNegative() {
        return amount.signum() < 0;
    }
}
~~~

Ví dụ này cho phép Money biểu diễn số âm vì một số miền cần khoản hoàn tiền hoặc bút toán điều chỉnh. Quy tắc “số tiền thanh toán phải dương” thuộc về kiểu hoặc hành vi PaymentAmount/Payment, không nên áp đặt một cách máy móc lên mọi khoản tiền.

Trong hệ thống có tiền tệ lịch sử hoặc quy tắc riêng, danh mục currency có thể cần được quản lý trong domain thay vì chỉ dựa vào Currency của JDK. Cũng cần quy định precision, scale và rounding theo nghiệp vụ; Currency.getDefaultFractionDigits không tự giải quyết mọi quy tắc kế toán.

### 2.4. Value object cho đại lượng đo

Một Quantity có giá trị số và đơn vị. Chỉ hai giá trị cùng dimension mới có thể cộng sau khi quy đổi:

~~~java
import java.math.BigDecimal;
import java.util.Objects;

public record Quantity(BigDecimal value, Unit unit) {
    public Quantity {
        Objects.requireNonNull(value, "value");
        Objects.requireNonNull(unit, "unit");
    }

    public Quantity add(Quantity other, UnitConverter converter) {
        if (!unit.dimension().equals(other.unit().dimension())) {
            throw new IllegalArgumentException("Dimension mismatch");
        }
        BigDecimal converted = converter.convert(
            other.value(), other.unit(), unit
        );
        return new Quantity(value.add(converted), unit);
    }
}
~~~

Đoạn mã giả định UnitConverter kiểm tra dimension và dùng quy tắc chuyển đổi đã được quản lý. Với nhiệt độ, chuyển đổi có thể có độ lệch; với thể tích sang khối lượng, cần mật độ và ngữ cảnh. Không nên triển khai mọi phép đổi bằng cách nhân một factor chung.

### 2.5. Giới hạn của kiểu Java

Kiểu Java chỉ bảo vệ các đường đi qua mã Java đã biên dịch. Nó không tự bảo vệ:

- Dữ liệu nhận từ HTTP hoặc message trước khi được parse.
- Dữ liệu ghi trực tiếp từ SQL client hoặc công cụ quản trị.
- Một dịch vụ khác dùng schema cũ.
- Nhiều transaction cùng sửa một giá trị.
- Dữ liệu đã tồn tại trong database từ trước.

Vì vậy, Java types là lớp đầu tiên để làm dữ liệu rõ nghĩa và giảm lỗi lập trình, không phải hàng rào duy nhất cho toàn hệ thống.

## 3. Mô hình miền: bảo vệ ý nghĩa và hành vi nghiệp vụ

Domain model hiểu khái niệm nghiệp vụ. Nó có thể biết đơn hàng đã xác nhận thì không được thêm dòng tùy ý, số lượng đặt hàng phải dương, hoặc một khoản thanh toán không thể ghi nhận cho đơn đã hủy.

### 3.1. Entity và value object có trách nhiệm khác nhau

**Entity** có identity và vòng đời. Ví dụ Order có orderId và trạng thái thay đổi theo thời gian.

**Value object** được xác định bởi giá trị của nó và thường bất biến. Ví dụ Money, Quantity, Address hoặc DateRange.

Value object giúp gom dữ liệu cùng quy tắc vào một khái niệm. Entity kiểm soát việc thay đổi trạng thái qua hành vi có tên nghiệp vụ thay vì cho bên ngoài sửa trường tùy ý.

### 3.2. Bảo vệ bất biến trong aggregate

Aggregate là ranh giới nhất quán của một nhóm đối tượng được thay đổi như một đơn vị nghiệp vụ. Aggregate root kiểm soát các thao tác làm thay đổi trạng thái bên trong.

Ví dụ Order có thể là aggregate root và OrderLine là thành phần bên trong. Các dòng hàng chỉ được thêm qua hành vi của Order:

~~~java
import java.util.ArrayList;
import java.util.List;

public final class Order {
    private final OrderId id;
    private final CustomerId customerId;
    private final List<OrderLine> lines = new ArrayList<>();
    private OrderStatus status = OrderStatus.DRAFT;

    public Order(OrderId id, CustomerId customerId) {
        this.id = id;
        this.customerId = customerId;
    }

    public void addLine(ProductId productId, Quantity quantity, Money unitPrice) {
        if (status != OrderStatus.DRAFT) {
            throw new IllegalStateException("Only draft orders can be changed");
        }
        if (quantity.value().signum() <= 0) {
            throw new IllegalArgumentException("Quantity must be positive");
        }
        if (unitPrice.isNegative()) {
            throw new IllegalArgumentException("Unit price cannot be negative");
        }
        lines.add(new OrderLine(productId, quantity, unitPrice));
    }

    public void confirm() {
        if (status != OrderStatus.DRAFT) {
            throw new IllegalStateException("Order is not a draft");
        }
        if (lines.isEmpty()) {
            throw new IllegalStateException("An order needs at least one line");
        }
        status = OrderStatus.CONFIRMED;
    }

    public List<OrderLine> lines() {
        return List.copyOf(lines);
    }
}
~~~

Đây là ví dụ minh họa. Trong một mô hình đầy đủ, OrderLine có thể tự bảo vệ các quy tắc nội tại, Order có thể tính tổng tiền theo chính sách thuế/chiết khấu, và các phương thức cần lưu domain event hoặc metadata thay đổi.

Điểm quan trọng là bên ngoài không được lấy danh sách mutable rồi tự thêm dòng sau khi đơn hàng đã xác nhận. Domain model phải giữ quyền kiểm soát các chuyển đổi trạng thái.

### 3.3. Không đưa mọi quy tắc vào entity

Domain model không nên tự truy vấn tùy ý database hoặc gọi API từ bên trong entity. Một quy tắc có thể cần dữ liệu ngoài aggregate:

- Khách hàng có còn trong hạn mức tín dụng không?
- Kho còn đủ hàng ở tất cả vị trí không?
- Mã khuyến mại có đang hiệu lực và còn lượt dùng không?
- Một thiết bị đã có lịch bảo trì trong khoảng thời gian yêu cầu chưa?

Nếu entity tự gọi repository hoặc HTTP client, logic miền bị gắn với hạ tầng và khó kiểm thử. Có thể dùng domain service hoặc application service để lấy thông tin cần thiết, rồi truyền kết quả hoặc chính sách vào domain behavior.

### 3.4. Aggregate không đồng nghĩa với một bảng

Một aggregate có thể được lưu ở nhiều bảng; một bảng cũng có thể chứa dữ liệu của nhiều khái niệm tùy mô hình. Ranh giới aggregate được chọn theo quy tắc nhất quán và hành vi thay đổi, không phải theo số lượng bảng.

Ví dụ, Order và OrderLine có thể là một aggregate vì dòng hàng chỉ được thay đổi thông qua đơn hàng. Payment có thể là aggregate riêng vì có vòng đời, callback và đối soát riêng. Một đơn hàng có nhiều payment; việc ghi nhận payment và cập nhật trạng thái đơn cần được điều phối qua use case và transaction phù hợp.

### 3.5. State transition phải có hành vi rõ

Một enum có thể giới hạn tập trạng thái, nhưng domain model cần bảo vệ chuyển đổi hợp lệ:

~~~java
public void markPaid() {
    if (status != OrderStatus.CONFIRMED) {
        throw new IllegalStateException(
            "Only confirmed orders can be paid"
        );
    }
    status = OrderStatus.PAID;
}
~~~

Nếu nghiệp vụ cho phép thanh toán một phần, trạng thái có thể không đơn giản là CONFIRMED sang PAID. Khi đó cần mô hình số tiền đã thu, số còn phải thu và các trạng thái phù hợp. Không nên dùng một enum đơn giản để che giấu quy trình phức tạp.

## 4. Lớp ứng dụng: điều phối ca sử dụng và ranh giới giao dịch

Application layer nhận một yêu cầu cụ thể và phối hợp domain model với repository, transaction manager, authorization và các dịch vụ bên ngoài. Nó không nên trở thành nơi chứa toàn bộ quy tắc nghiệp vụ dưới dạng các câu if rời rạc.

### 4.1. Xác thực đầu vào tại biên hệ thống

DTO nhận từ HTTP hoặc message cần được kiểm tra hình dạng và cú pháp trước khi gọi use case:

~~~java
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Positive;

public record AddOrderLineRequest(
    @NotNull Long productId,
    @NotNull @Positive Integer quantity
) {}
~~~

Bean Validation giúp trả lỗi đầu vào sớm và nhất quán khi framework thực sự kích hoạt việc kiểm tra, chẳng hạn qua @Valid/@Validated hoặc Validator được gọi tường minh. Chỉ đặt annotation không tự xác thực mọi lần tạo DTO. Annotation trên DTO cũng không bảo vệ các đường gọi không đi qua controller và không thay thế domain validation. Một application use case có thể được gọi từ REST controller, message consumer, batch job hoặc test.

### 4.2. Application service điều phối hành vi

Một use case thêm dòng hàng có thể:

1. Xác minh người gọi được phép sửa đơn hàng.
2. Tải Order theo ID.
3. Lấy thông tin sản phẩm và giá áp dụng.
4. Tạo các value object có kiểu.
5. Gọi hành vi addLine của Order.
6. Lưu aggregate trong transaction.
7. Trả kết quả hoặc phát sự kiện sau commit.

Ví dụ:

~~~java
public final class AddOrderLineUseCase {
    private final OrderRepository orders;
    private final ProductCatalog products;
    private final Authorization authorization;
    private final TransactionRunner transactions;

    public AddOrderLineUseCase(
        OrderRepository orders,
        ProductCatalog products,
        Authorization authorization,
        TransactionRunner transactions
    ) {
        this.orders = orders;
        this.products = products;
        this.authorization = authorization;
        this.transactions = transactions;
    }

    public void execute(
        UserId actor,
        OrderId orderId,
        ProductId productId,
        Quantity quantity
    ) {
        transactions.required(() -> {
            authorization.requireCanEditOrder(actor, orderId);
            Order order = orders.getRequired(orderId);
            Product product = products.getRequired(productId);

            order.addLine(product.id(), quantity, product.currentPrice());
            orders.save(order);
        });
    }
}
~~~

Các interface và TransactionRunner trong ví dụ là abstraction do ứng dụng định nghĩa. Cách triển khai transaction có thể dùng Spring, Jakarta Transactions hoặc cơ chế của framework khác. Điều quan trọng là ranh giới commit/rollback bao trùm các thay đổi phải nguyên tử.

### 4.3. Quy tắc giữa nhiều aggregate

Giả sử một use case cần xác nhận đơn hàng và giữ chỗ hàng tồn kho. Order và Inventory có thể là hai aggregate riêng. Application service điều phối:

- Tải đơn hàng.
- Tính nhu cầu theo từng sản phẩm.
- Giữ chỗ tồn kho.
- Chuyển đơn hàng sang confirmed.
- Lưu thay đổi trong transaction hoặc quy trình nhất quán phù hợp.

Nếu tất cả dữ liệu nằm trong cùng một database và cần commit nguyên tử, transaction có thể bao trùm các cập nhật. Nếu tồn kho nằm ở dịch vụ khác, không thể giả định một transaction ACID xuyên qua HTTP. Khi đó cần quy trình nhiều bước như reservation, xác nhận, timeout và compensation.

### 4.4. Authorization không phải invariant dữ liệu

Quyền “người dùng này được sửa đơn hàng này” là chính sách truy cập, thường được kiểm tra ở application layer hoặc policy service. Foreign key không thể diễn đạt đầy đủ quyền theo người dùng, vai trò, tenant và ngữ cảnh.

Tuy nhiên, database vẫn cần bảo vệ ranh giới dữ liệu như tenant_id hoặc owner_id nếu mô hình yêu cầu. Với hệ thống đa tenant, có thể dùng composite foreign key, row-level security hoặc cơ chế tương đương tùy hệ quản trị. Không nên dựa vào việc client không gửi được ID của tenant khác như một hàng rào duy nhất.

### 4.5. Idempotency thuộc use case và persistence cùng nhau

Một yêu cầu có thể được gửi lặp do timeout hoặc webhook. Application layer xác định ý nghĩa của idempotency key và kết quả cần trả lại; database dùng UNIQUE để bảo đảm không có hai yêu cầu cùng key được tạo đồng thời.

Đây là ví dụ một quy tắc có hai trách nhiệm: application biết hai request có cùng ý nghĩa hay không; database bảo vệ tính duy nhất khi ghi đồng thời.

## 5. Cơ sở dữ liệu: hàng rào toàn vẹn cuối cùng

Database là nơi phù hợp để bảo vệ những điều kiện phải đúng bất kể dữ liệu được ghi từ REST API, batch job, message consumer, SQL script hay dịch vụ khác.

### 5.1. Dùng constraint cho quy tắc khai báo

Các constraint phổ biến:

- PRIMARY KEY: định danh hàng.
- UNIQUE: bảo vệ tính duy nhất.
- FOREIGN KEY: bảo vệ quan hệ tham chiếu.
- NOT NULL: yêu cầu có giá trị.
- CHECK: kiểm tra điều kiện trên một hàng.

Ví dụ:

~~~sql
CREATE TABLE orders (
    order_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id BIGINT NOT NULL REFERENCES customers(customer_id),
    order_number VARCHAR(40) NOT NULL UNIQUE,
    status VARCHAR(20) NOT NULL
        CHECK (status IN ('draft', 'confirmed', 'paid', 'cancelled')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE order_lines (
    order_line_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    order_id BIGINT NOT NULL REFERENCES orders(order_id),
    product_id BIGINT NOT NULL REFERENCES products(product_id),
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price NUMERIC(18, 2) NOT NULL CHECK (unit_price >= 0)
);
~~~

Constraint bảo vệ dữ liệu kể cả khi một đoạn mã Java quên kiểm tra. Nhưng constraint trên chỉ bảo vệ điều kiện được khai báo. Nó không tự bảo đảm đơn hàng confirmed phải có dòng hàng hoặc tổng tiền khớp các dòng.

### 5.2. Không dùng database constraint để thay thế domain behavior

CHECK status IN (...) chỉ kiểm tra trạng thái có nằm trong tập cho phép. Nó không thể diễn đạt đầy đủ rằng đơn hàng chỉ được chuyển từ confirmed sang paid khi đã có khoản thanh toán hợp lệ, hoặc không được chuyển từ cancelled sang fulfilled.

Domain model hiểu chuyển đổi đó. Application layer điều phối thanh toán và thay đổi trạng thái trong transaction. Database có thể lưu lịch sử trạng thái, khóa ngoại và constraint hỗ trợ. Mỗi lớp có vai trò riêng.

### 5.3. Bảo vệ tính duy nhất khi đồng thời

Một kiểm tra SELECT trước INSERT không đủ để bảo vệ tính duy nhất:

~~~sql
-- Hai transaction có thể cùng thấy mã chưa tồn tại.
SELECT 1
FROM orders
WHERE order_number = :order_number;

INSERT INTO orders (customer_id, order_number, status)
VALUES (:customer_id, :order_number, 'draft');
~~~

Nếu hai transaction cùng chạy, cả hai có thể vượt qua SELECT. UNIQUE constraint mới là hàng rào cuối cùng. Ứng dụng cần bắt lỗi unique violation và chuyển thành kết quả nghiệp vụ phù hợp, chẳng hạn mã đơn đã được sử dụng.

### 5.4. Transaction và cập nhật nguyên tử

Khi một nghiệp vụ gồm nhiều thay đổi phải cùng thành công hoặc cùng thất bại, dùng transaction. Ví dụ, tạo payment và cập nhật amount_paid phải cùng commit. Nếu chỉ một trong hai thành công, số dư sẽ sai.

Với tồn kho, cập nhật có điều kiện có thể bảo vệ giới hạn trong một câu lệnh:

~~~sql
UPDATE inventory_balances
SET reserved = reserved + :requested_quantity
WHERE product_id = :product_id
  AND warehouse_id = :warehouse_id
  AND on_hand - reserved >= :requested_quantity;
~~~

Ứng dụng kiểm tra số hàng được cập nhật. Nếu bằng không, không đủ hàng hoặc không tìm thấy balance. Thao tác tạo reservation detail phải nằm trong cùng transaction.

### 5.5. Khóa và isolation level

Khi bất biến phụ thuộc nhiều hàng, cần chọn cách bảo vệ trước các transaction cạnh tranh:

- SELECT FOR UPDATE để khóa hàng đại diện cho tài nguyên hoặc aggregate.
- Conditional UPDATE để kiểm tra và thay đổi nguyên tử.
- Optimistic locking với version để phát hiện xung đột.
- SERIALIZABLE khi cần kết quả tương đương thứ tự tuần tự và có thể xử lý retry.
- Constraint chuyên biệt như exclusion constraint khi hệ quản trị hỗ trợ.

Mức cô lập và hành vi khóa khác nhau giữa các hệ quản trị. Cần kiểm thử với workload thật và xử lý deadlock hoặc serialization failure. Việc đặt logic trong Java không thể tự ngăn hai transaction cùng đọc một giá trị cũ rồi ghi đè nhau.

### 5.6. Database không hiểu toàn bộ ngữ nghĩa nghiệp vụ

Database có thể bảo vệ quantity > 0, nhưng không nhất thiết biết một sản phẩm có được phép bán theo kilogram hay chỉ theo chiếc. Nó có thể lưu status hợp lệ, nhưng không biết người dùng nào được phép chuyển trạng thái. Nó có thể bảo vệ foreign key, nhưng không tự biết chính sách giá khuyến mại của từng khách hàng.

Những quy tắc có ngữ nghĩa phong phú nên được biểu diễn trong domain/application, đồng thời database bảo vệ các điều kiện cấu trúc và tính toàn vẹn mà nó có thể thực thi đáng tin cậy.

## 6. Ma trận phân chia trách nhiệm

| Loại quy tắc | Java types / DTO | Domain model | Application layer | Database |
|---|---|---|---|---|
| Dữ liệu đầu vào đúng hình dạng | Parse, Bean Validation, kiểu cụ thể | Nhận value object hợp lệ | Điều phối lỗi đầu vào | Kiểu cột và NOT NULL |
| ID không bị truyền nhầm | Wrapper type | Dùng đúng loại ID | Mapping và authorization | PK/FK |
| Số lượng dương | @Positive ở DTO khi phù hợp | Quantity/OrderLine từ chối giá trị không hợp lệ | Trả lỗi use case | CHECK |
| Đơn hàng phải có dòng khi xác nhận | Không đủ để bảo vệ | confirm() kiểm tra lines | Gọi confirm trong transaction | Có thể dùng trigger/procedure hoặc quy trình kiểm soát nếu cần bảo vệ mọi đường ghi |
| Chỉ chuyển trạng thái hợp lệ | Enum biểu diễn tập trạng thái | Phương thức chuyển trạng thái | Chọn đúng use case và transaction | CHECK giá trị, lưu lịch sử; constraint không thay thế state machine |
| Tổng thanh toán không vượt số phải thu | Money/PaymentAmount có kiểu | Kiểm tra trong ngữ cảnh đơn hàng | Điều phối ghi payment | Lock/atomic update/transaction |
| Tồn kho không bị giữ chỗ vượt mức | Quantity và Unit có kiểu | Quy tắc giữ chỗ trong domain | Điều phối order và inventory | Conditional UPDATE, lock, CHECK |
| Người dùng có quyền thao tác | Không phải trách nhiệm chính | Có thể cung cấp chính sách miền | Authorization/policy | RLS hoặc tenant boundary khi phù hợp |
| Idempotency key duy nhất | Kiểu key và request hash | Có thể mô hình hóa thao tác logic | Xác định request tương đương và kết quả | UNIQUE |

Ma trận là hướng dẫn phân vai, không phải luật cứng. Ranh giới phụ thuộc kiến trúc, hệ quản trị, cách triển khai và yêu cầu nhất quán. Khi một quy tắc xuất hiện ở nhiều lớp, hãy ghi rõ mỗi lần kiểm tra bảo vệ ranh giới nào.

## 7. Ví dụ xuyên suốt: xác nhận đơn hàng

Giả sử khách hàng tạo đơn hàng gồm nhiều dòng. Khi xác nhận, hệ thống phải bảo đảm:

- Đơn hàng đang ở trạng thái draft.
- Có ít nhất một dòng.
- Số lượng mỗi dòng dương.
- Sản phẩm còn được phép bán.
- Giá và tiền tệ được chốt.
- Tồn kho đủ để giữ chỗ.
- Tổng tiền được tính theo cùng quy tắc.
- Mã đơn hàng duy nhất.

### 7.1. Tại biên Java

DTO kiểm tra productId có mặt và quantity dương. Parser chuyển chuỗi ngày hoặc mã tiền tệ thành kiểu phù hợp. Dữ liệu sai định dạng bị từ chối trước khi chạy use case.

### 7.2. Trong domain model

Order.confirm() kiểm tra trạng thái hiện tại, danh sách dòng hàng và các quy tắc nội tại. OrderLine giữ Quantity và Money thay vì các số rời rạc. Domain model không cho thay đổi dòng sau khi đơn đã chốt nếu chính sách không cho phép.

### 7.3. Trong application layer

ConfirmOrderUseCase xác thực quyền người gọi, tải Order, lấy chính sách giá và phối hợp InventoryService để giữ chỗ. Nó xác định transaction boundary, xử lý idempotency và quyết định cách phản hồi khi tồn kho không đủ.

### 7.4. Trong database

PRIMARY KEY/UNIQUE bảo vệ định danh, FOREIGN KEY bảo vệ tham chiếu, CHECK bảo vệ số lượng và giá trên từng hàng. Transaction cập nhật tồn kho và lưu reservation. Conditional UPDATE hoặc khóa ngăn hai yêu cầu đồng thời giữ cùng lượng hàng.

### 7.5. Nếu một lớp bỏ qua quy tắc thì sao?

Nếu controller bỏ @Positive, domain vẫn từ chối Quantity không hợp lệ. Nếu một batch job không gọi domain model và ghi SQL trực tiếp, CHECK vẫn ngăn quantity âm. Nếu hai application request cùng giữ chỗ, database serialization bảo vệ số tồn. Nếu database không có constraint hoặc transaction đúng, kiểm tra ở Java có thể bị race condition.

Đây là lý do cần phân lớp trách nhiệm và hàng rào cuối cùng. Một lớp không thể thay thế hoàn toàn các lớp còn lại.

## 8. Tránh hai thái cực: kiểm tra trùng lặp và thiếu hàng rào

### 8.1. Khi nào nên kiểm tra ở nhiều lớp?

Kiểm tra lặp có chủ đích khi:

- DTO cần lỗi dễ hiểu trước khi vào domain.
- Domain cần bảo vệ trạng thái bất kể ai gọi phương thức.
- Database cần bảo vệ dữ liệu trước mọi đường ghi.
- Application cần xác minh điều kiện phụ thuộc nhiều aggregate hoặc dịch vụ.

Ví dụ quantity > 0 có thể được kiểm tra ở DTO, Quantity value object và CHECK. Ba lớp không nhất thiết là ba nguồn định nghĩa độc lập; domain rule phải có ý nghĩa chuẩn, còn DTO và DB là hàng rào tại ranh giới của chúng.

### 8.2. Khi nào kiểm tra lặp gây hại?

Kiểm tra lặp gây hại khi:

- Mỗi lớp dùng một ngưỡng khác nhau.
- Một nơi cho phép scale 3 nhưng nơi khác chỉ cho scale 2.
- Domain và database hiểu khác nhau về trạng thái hợp lệ.
- Quy tắc được sao chép nhiều nơi nhưng không có test hoặc tài liệu.
- Thay đổi nghiệp vụ chỉ cập nhật một lớp.

Hãy định nghĩa quy tắc chuẩn trong domain language và kiểm thử các adapter chuyển đổi. Nếu schema có giới hạn cụ thể, cần đồng bộ với miền giá trị của domain.

### 8.3. Khi nào không nên đưa quy tắc vào database?

Không phải mọi chính sách đều nên thành CHECK hoặc trigger:

- Quy tắc phụ thuộc quyền người dùng hoặc vai trò.
- Quy tắc cần gọi nhà cung cấp bên ngoài.
- Quy tắc thay đổi thường xuyên theo chiến dịch và cấu hình.
- Quy tắc có ngữ nghĩa phức tạp, cần giải thích theo ngôn ngữ nghiệp vụ.

Database vẫn có thể lưu cấu hình, khóa tham chiếu hoặc hàng rào cấu trúc. Nhưng việc quyết định một yêu cầu có đủ điều kiện nghiệp vụ thường thuộc application/domain.

### 8.4. Khi nào không nên chỉ dùng domain model?

Nếu nhiều ứng dụng, job hoặc công cụ quản trị cùng ghi một database, chỉ domain model trong một service không đủ bảo vệ dữ liệu. Nếu một bất biến cần đúng ngay cả khi có hai transaction cạnh tranh, phải dùng constraint, transaction, khóa hoặc cơ chế đồng thời phù hợp.

## 9. Mapping giữa domain và database

Domain model không nhất thiết phải giống cấu trúc bảng. Một domain object có thể chứa value object Money, Quantity, DateRange; database lưu chúng thành nhiều cột hoặc bảng liên quan.

Ví dụ Money có thể ánh xạ thành amount và currency_code. Quantity có thể ánh xạ thành measured_value và unit_code. Domain model giữ một đối tượng có ý nghĩa, trong khi schema vật lý chọn cách lưu phù hợp.

### 9.1. Không để kiểu persistence rò vào domain

Domain không nên phụ thuộc trực tiếp vào:

- Entity annotation của ORM nếu kiến trúc muốn tách domain khỏi persistence.
- Lazy-loading proxy.
- SQL exception hoặc transaction API cụ thể.
- Kiểu JSON hoặc row mapping riêng của database.

Có thể dùng mapper hoặc repository adapter để chuyển đổi. Trong một ứng dụng nhỏ, dùng JPA entity trực tiếp làm domain model có thể là lựa chọn thực dụng, nhưng cần hiểu rằng lifecycle, lazy loading và trạng thái ORM sẽ ảnh hưởng đến hành vi miền.

### 9.2. Kiểm tra khi đọc dữ liệu cũ

Dữ liệu trong database có thể được tạo bởi phiên bản ứng dụng cũ hoặc trước khi constraint mới được thêm. Khi hydrate domain object, cần xử lý dữ liệu không còn hợp lệ:

- Từ chối tải và báo lỗi dữ liệu.
- Cách ly bản ghi để xử lý.
- Dùng migration/backfill trước khi bật quy tắc mới.
- Tạo adapter tương thích trong giai đoạn chuyển đổi.

Không nên âm thầm tạo domain object ở trạng thái sai rồi để lỗi xuất hiện ở một hành vi khác khó truy nguyên.

### 9.3. Xử lý lỗi constraint

Database constraint violation có thể xuất hiện dù application đã kiểm tra trước đó, đặc biệt khi có concurrent writes. Application layer cần ánh xạ lỗi kỹ thuật thành lỗi use case có ý nghĩa:

- Unique violation: mã đã được sử dụng.
- Foreign key violation: tham chiếu không còn tồn tại hoặc không hợp lệ.
- Check violation: giá trị vi phạm miền dữ liệu.
- Deadlock/serialization failure: thao tác cần retry hoặc báo xung đột.

Không nên bắt mọi SQLException rồi trả về “lỗi hệ thống” chung nếu có thể xác định loại lỗi và cách xử lý an toàn. Đồng thời, không nên hiển thị chi tiết SQL hoặc tên bảng nội bộ cho người dùng cuối.

## 10. Kiểm thử theo ranh giới trách nhiệm

Mỗi lớp cần loại kiểm thử phù hợp:

| Lớp | Kiểm thử chính | Ví dụ |
|---|---|---|
| Java types/DTO | Unit test và validation test | ID không hợp lệ, quantity âm, request thiếu trường |
| Domain model | Unit test hành vi và bất biến | Không xác nhận đơn rỗng, không sửa đơn đã chốt |
| Application | Use-case test với repository/service giả hoặc integration test | Quyền truy cập, thứ tự điều phối, transaction và idempotency |
| Database | Integration test với hệ quản trị thật hoặc tương thích | CHECK, UNIQUE, FK, transaction và rollback |
| Đồng thời | Concurrency test | Hai yêu cầu cùng giữ một đơn vị tồn kho |
| Migration | Test trên bản sao dữ liệu gần thực tế | Backfill, thêm constraint và tương thích phiên bản |

### 10.1. Unit test domain

~~~java
@Test
void cannotConfirmAnEmptyOrder() {
    Order order = new Order(
        new OrderId(1L),
        new CustomerId(10L)
    );

    assertThrows(
        IllegalStateException.class,
        order::confirm
    );
}
~~~

Test này kiểm tra hành vi domain độc lập với database. Nó không chứng minh database có CHECK hoặc UNIQUE; đó là phạm vi test khác.

### 10.2. Integration test constraint

Hãy thử insert dữ liệu vi phạm trực tiếp vào database:

- quantity = 0.
- order_number trùng.
- customer_id không tồn tại.
- discount_amount lớn hơn thành tiền dòng.

Nếu các lệnh ghi vẫn thành công, constraint chưa được tạo hoặc chưa bảo vệ đúng quy tắc. Test này quan trọng vì các đường ghi có thể bỏ qua domain model.

### 10.3. Concurrency test

Tạo tồn kho một đơn vị, sau đó chạy hai transaction độc lập cùng yêu cầu giữ chỗ một đơn vị. Kết quả hợp lệ là chỉ một yêu cầu thành công, reserved không vượt on_hand và không có reservation detail mồ côi.

Test phải chạy đồng thời thật, không chỉ gọi hai lần tuần tự. Nên dùng đúng hệ quản trị và isolation level dự kiến triển khai vì hành vi cạnh tranh khác nhau giữa các sản phẩm.

### 10.4. Contract test cho mapping

Khi domain Money được lưu thành amount và currency_code, test mapping cần xác nhận:

- Giá trị thập phân không bị chuyển thành số thực.
- Mã tiền tệ được giữ nguyên.
- Scale và rounding theo quy tắc.
- Đọc lại tạo được Money hợp lệ.
- Dữ liệu cũ không bị diễn giải theo đơn vị hoặc currency khác.

## 11. Tiến hóa quy tắc giữa các lớp

Quy tắc nghiệp vụ có thể thay đổi. Ví dụ, ban đầu hệ thống chỉ cho một lần thanh toán toàn bộ, sau đó hỗ trợ thanh toán nhiều đợt. Sự thay đổi ảnh hưởng đến:

- DTO và API contract.
- Value object hoặc domain behavior.
- Use case và transaction flow.
- Schema payment, unique constraint và aggregate amount_paid.
- Migration dữ liệu cũ.
- Báo cáo và đối soát.

Hãy thay đổi theo từng bước:

1. Xác nhận định nghĩa mới và các trạng thái hợp lệ.
2. Cập nhật domain model và test hành vi.
3. Thiết kế schema tương thích và migration.
4. Cập nhật application use case, transaction và xử lý lỗi.
5. Triển khai tương thích với phiên bản cũ nếu cần.
6. Backfill và đối soát dữ liệu.
7. Chỉ bỏ cấu trúc cũ khi không còn luồng sử dụng.

Không nên chỉ sửa CHECK trong database rồi để domain vẫn từ chối trạng thái mới. Cũng không nên mở rộng enum Java trước khi database và các consumer đã sẵn sàng đọc giá trị mới.

### 11.1. Expand–migrate–contract

Khi thay đổi schema đang được nhiều phiên bản ứng dụng sử dụng:

- **Expand:** thêm cột/bảng/ràng buộc theo cách tương thích.
- **Migrate:** chuyển dữ liệu và cập nhật ứng dụng theo giai đoạn.
- **Switch:** chuyển luồng đọc/ghi sang cấu trúc mới.
- **Contract:** loại bỏ cấu trúc cũ sau khi mọi consumer đã chuyển.

Chiến lược này giảm rủi ro khi domain, application và database không thể được triển khai cùng một thời điểm.

## 12. Những lỗi phân chia trách nhiệm thường gặp

**Chỉ kiểm tra ở controller.** Batch job hoặc message consumer có thể bỏ qua controller. Hãy bảo vệ domain behavior và database constraint theo phạm vi phù hợp.

**Đưa toàn bộ nghiệp vụ vào service.** Các điều kiện bị phân tán thành nhiều câu if, dễ bị bỏ sót khi có luồng gọi mới. Chuyển hành vi gắn với entity vào domain model.

**Entity cho phép sửa mọi trường.** Bất kỳ caller nào cũng có thể tạo trạng thái không hợp lệ. Đóng gói trạng thái và cung cấp phương thức nghiệp vụ có kiểm tra.

**Dùng database constraint thay cho mọi quy tắc miền.** Database không hiểu đầy đủ chính sách, quyền và hành vi của domain. Dùng constraint cho tính toàn vẹn dữ liệu mà nó có thể bảo vệ.

**Tin rằng domain validation ngăn được race condition.** Hai instance domain có thể cùng đọc trạng thái cũ. Cần transaction, khóa, optimistic concurrency hoặc constraint tại database.

**Lặp validation mà không có định nghĩa chuẩn.** DTO cho phép 0, domain chỉ cho số dương và database lại cho số âm sẽ tạo lỗi khó đoán. Đồng bộ miền giá trị và test giữa các lớp.

**Nuốt lỗi constraint.** Bắt lỗi rồi tiếp tục có thể để use case trả thành công trong khi dữ liệu không được ghi. Transaction cần rollback và lỗi cần được ánh xạ rõ.

**Để ORM quyết định thay domain.** Callback persistence hoặc lifecycle hook không nên là nơi duy nhất chứa quy tắc nghiệp vụ quan trọng nếu domain có thể được gọi ngoài ORM.

**Không kiểm thử đường ghi trực tiếp.** Một hệ thống chỉ test qua REST API có thể bỏ sót import, migration, job và SQL script.

## 13. Quy trình phân chia một bất biến

Khi nhận một quy tắc mới, hãy thực hiện:

1. **Viết định nghĩa nghiệp vụ:** điều kiện nào phải đúng, trong trạng thái nào và ngoại lệ là gì?
2. **Xác định phạm vi dữ liệu:** một value, một entity, một aggregate, nhiều aggregate hay nhiều bảng?
3. **Chọn biểu diễn Java:** kiểu nguyên thủy, enum, wrapper ID hay value object?
4. **Chọn nơi giữ ngữ nghĩa:** hành vi của entity, value object, domain service hay policy?
5. **Xác định use case:** ai gọi, cần quyền gì, cần phối hợp repository/service nào?
6. **Xác định hàng rào database:** PK, UNIQUE, FK, CHECK, transaction, lock hay constraint chuyên biệt?
7. **Phân tích đồng thời:** có hai yêu cầu nào có thể cùng vượt qua kiểm tra không?
8. **Xác định lỗi và phục hồi:** trả lỗi nghiệp vụ, retry, rollback hay compensation?
9. **Kiểm thử từng ranh giới:** unit, use case, integration, concurrency và migration.
10. **Ghi tài liệu:** quy tắc chuẩn, lớp thực thi, nguồn sự thật và chủ sở hữu.

## 14. Checklist đánh giá thiết kế

- [ ] Kiểu Java thể hiện đúng ý nghĩa dữ liệu và giảm nhầm lẫn giữa các loại ID.
- [ ] DTO kiểm tra cú pháp và hình dạng đầu vào ở biên hệ thống.
- [ ] Value object bảo vệ miền giá trị và quy tắc nội tại của giá trị.
- [ ] Entity/aggregate chỉ cho thay đổi qua hành vi nghiệp vụ hợp lệ.
- [ ] Domain model không phụ thuộc trực tiếp vào HTTP, SQL hoặc dịch vụ ngoài.
- [ ] Application layer điều phối quyền, use case, transaction và tích hợp.
- [ ] Database có PK, UNIQUE, FK, NOT NULL và CHECK cho các quy tắc phù hợp.
- [ ] Bất biến liên hàng có cơ chế khóa, transaction hoặc isolation level phù hợp.
- [ ] Mọi đường ghi như API, job, import và webhook đều tuân thủ hàng rào cần thiết.
- [ ] Lỗi constraint được ánh xạ thành lỗi use case phù hợp.
- [ ] Có unit test domain, integration test database và concurrency test.
- [ ] Mapping giữa domain và schema giữ đúng giá trị, đơn vị, precision và lịch sử.
- [ ] Migration đồng bộ được thay đổi giữa Java, domain, application và database.
- [ ] Có tài liệu ghi nơi thực thi và chủ sở hữu của từng bất biến quan trọng.

## Kết luận

Kiểu Java, mô hình miền, lớp ứng dụng và cơ sở dữ liệu cùng bảo vệ chất lượng dữ liệu nhưng làm những việc khác nhau. Java types làm dữ liệu rõ nghĩa và ngăn nhầm lẫn cơ bản. Domain model bảo vệ hành vi và trạng thái hợp lệ của entity hoặc aggregate. Application layer điều phối ca sử dụng, quyền truy cập, nhiều aggregate và transaction. Database bảo vệ tính toàn vẹn trước mọi đường ghi và xử lý các tình huống cạnh tranh bằng constraint cùng cơ chế đồng thời.

Hãy xác định phạm vi của bất biến trước khi chọn lớp thực thi. Kiểm tra sớm để phản hồi tốt, giữ quy tắc nghiệp vụ ở domain, điều phối tại application và đặt hàng rào dữ liệu ở database khi có thể. Khi các lớp chia sẻ cùng một định nghĩa, được kiểm thử theo đúng ranh giới và tiến hóa cùng nhau, hệ thống vừa dễ hiểu vừa giữ được dữ liệu đáng tin cậy.
