# Tận dụng hệ kiểu của Java

Khi xây dựng ngôn ngữ miền chuyên biệt nhúng (embedded Domain-Specific Language, hay embedded DSL) trong Java, hệ kiểu của Java là một công cụ quan trọng để biến nhiều quy tắc của DSL thành những ràng buộc được kiểm tra ngay khi biên dịch. Thay vì để mọi cấu trúc chỉ là chuỗi ký tự rồi kiểm tra tất cả khi chạy, API DSL có thể dùng lớp, interface, enum, generic, record và lambda để biểu diễn khái niệm miền. Trình biên dịch Java khi đó hỗ trợ phát hiện sai kiểu, thiếu dữ liệu, gọi thao tác không hợp lệ hoặc truyền nhầm loại đối tượng.

Tận dụng hệ kiểu không có nghĩa là cố gắng mã hóa mọi quy tắc nghiệp vụ vào kiểu dữ liệu. Những điều kiện phụ thuộc vào dữ liệu thực tế, thời gian, quyền người dùng hoặc hệ thống bên ngoài vẫn cần được kiểm tra khi chạy. Mục tiêu là đưa những sai sót có thể phát hiện sớm vào giai đoạn biên dịch, đồng thời giữ cho DSL dễ đọc và tự nhiên đối với người sử dụng.

Các ví dụ trong bài dùng cú pháp Java hiện đại, chủ yếu Java 17 trở lên khi có `record` và `sealed interface`. Ví dụ `switch` với pattern matching ở phần sealed type cần Java 21 trở lên; trên Java 17 có thể dùng chuỗi kiểm tra `instanceof`. Những ý tưởng cơ bản như interface, enum, generic và lambda cũng áp dụng được cho các phiên bản Java cũ hơn, với cách khai báo lớp tương ứng.

## 1. Vì sao hệ kiểu quan trọng với DSL nhúng?

DSL nhúng thường được triển khai như một API thư viện. Người dùng viết chương trình DSL bằng chính cú pháp Java, còn các phương thức và kiểu do thư viện cung cấp tạo nên từ vựng của miền.

Ví dụ, một API đơn giản có thể cho phép viết:

```java
Order order = orderService.find(orderId);

if (order.status() == OrderStatus.PENDING_PAYMENT) {
    paymentService.requestPayment(order);
}
```

Nếu DSL chỉ nhận chuỗi như `"PENDING_PAYMENT"`, lỗi chính tả hoặc tên trạng thái không tồn tại có thể chỉ được phát hiện khi chạy. Dùng `OrderStatus` là một enum giúp trình biên dịch giới hạn giá trị được phép và IDE có thể gợi ý các hằng số hợp lệ.

Hệ kiểu mang lại một số lợi ích:

- **Phát hiện lỗi sớm:** không thể truyền một `Customer` vào phương thức cần `Order` nếu API được định kiểu đúng.
- **Khám phá API tốt hơn:** IDE có thể gợi ý phương thức, kiểu và giá trị hợp lệ.
- **Tài liệu ngay trong mã:** chữ ký phương thức thể hiện dữ liệu đầu vào và kết quả.
- **Tái sử dụng cấu trúc:** generic cho phép viết các thành phần dùng chung nhưng vẫn giữ kiểu cụ thể.
- **Hạn chế trạng thái không hợp lệ:** kiểu miền và API theo giai đoạn có thể ngăn một số thao tác sai ngay từ lúc biên dịch.
- **Tái cấu trúc an toàn hơn:** thay đổi tên hoặc kiểu thường được compiler và IDE chỉ ra ở những vị trí bị ảnh hưởng.

## 2. Dùng kiểu miền thay cho kiểu nguyên thủy

Một lỗi thiết kế phổ biến là biểu diễn mọi dữ liệu bằng `String`, `int`, `long` hoặc `double`. Cách này dễ bắt đầu nhưng làm mất ý nghĩa miền. Một chuỗi có thể là mã đơn hàng, mã khách hàng, email hoặc tên sản phẩm; trình biên dịch không phân biệt được nếu tất cả đều là `String`.

Có thể tạo kiểu riêng để thể hiện ý nghĩa của dữ liệu:

```java
import java.util.UUID;

record OrderId(UUID value) {
    public OrderId {
        if (value == null) {
            throw new IllegalArgumentException("OrderId must not be null");
        }
    }
}

record CustomerId(UUID value) {
    public CustomerId {
        if (value == null) {
            throw new IllegalArgumentException("CustomerId must not be null");
        }
    }
}
```

Hai kiểu đều bọc một `UUID`, nhưng chúng không thể bị truyền nhầm cho nhau:

```java
void cancelOrder(OrderId orderId) {
    // Xử lý hủy đơn hàng
}

OrderId orderId = new OrderId(UUID.randomUUID());
CustomerId customerId = new CustomerId(UUID.randomUUID());

cancelOrder(orderId);     // Hợp lệ
// cancelOrder(customerId); // Lỗi biên dịch
```

Các kiểu miền như `OrderId`, `CustomerId`, `EmailAddress`, `Quantity` hoặc `Money` giúp API DSL nói rõ ý nghĩa thay vì chỉ nói về cách lưu trữ. Chúng cũng là nơi phù hợp để đặt những kiểm tra cơ bản có thể thực hiện ngay khi tạo giá trị.

### 2.1. Đóng gói giá trị có đơn vị

Không nên dùng `double` cho tiền tệ hoặc dùng một số nguyên không rõ đơn vị cho thời lượng. Một kiểu `Money` có thể giữ số tiền và loại tiền, đồng thời kiểm tra khi cộng:

```java
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
        return new Money(amount.add(other.amount()), currency);
    }
}
```

Khi API DSL nhận `Money`, người dùng không thể vô tình truyền một chuỗi hoặc một thời điểm vào vị trí cần tiền tệ. Kiểm tra hai giá trị cùng loại tiền là kiểm tra lúc chạy vì loại tiền cụ thể chỉ được biết khi có dữ liệu. Kiểu dữ liệu làm rõ cấu trúc, còn quy tắc tương thích giá trị vẫn được thực thi ở runtime.

## 3. Dùng enum và sealed types để giới hạn lựa chọn

### 3.1. Enum cho tập giá trị hữu hạn

Khi một khái niệm chỉ có một tập lựa chọn được xác định, `enum` thường phù hợp:

```java
public enum OrderStatus {
    DRAFT,
    PENDING_PAYMENT,
    PAID,
    SHIPPED,
    DELIVERED,
    CANCELLED
}
```

API có thể nhận `OrderStatus` thay vì chuỗi:

```java
boolean canShip(OrderStatus status) {
    return status == OrderStatus.PAID;
}
```

Enum tránh lỗi chính tả và làm rõ danh sách lựa chọn. Tuy nhiên, enum chỉ đảm bảo giá trị thuộc tập đã khai báo. Nó không tự đảm bảo chuyển trạng thái hợp lệ; ví dụ, việc chuyển từ `DRAFT` sang `DELIVERED` vẫn cần quy tắc kiểm tra riêng.

### 3.2. Sealed interface cho các biến thể có kiểm soát

Khi một khái niệm có một số biến thể với dữ liệu khác nhau, sealed interface kết hợp với record có thể biểu diễn cấu trúc rõ ràng:

```java
sealed interface PaymentMethod
        permits CardPayment, BankTransfer {
}

record CardPayment(String token) implements PaymentMethod {
}

record BankTransfer(String bankCode, String accountNumber)
        implements PaymentMethod {
}
```

Một phương thức có thể nhận mọi phương thức thanh toán được hỗ trợ:

```java
void charge(PaymentMethod method, Money amount) {
    switch (method) {
        case CardPayment card -> chargeCard(card, amount);
        case BankTransfer bank -> chargeBank(bank, amount);
    }
}
```

Với tập kiểu con được giới hạn, compiler có thể hỗ trợ kiểm tra tính đầy đủ của switch khi dùng pattern matching phù hợp. Sealed type hữu ích khi DSL cần một tập biến thể được quản lý rõ, chẳng hạn nguồn dữ liệu, phương thức thanh toán hoặc loại điều kiện. Nếu plugin bên ngoài cần tự do bổ sung biến thể, một interface mở thông thường có thể phù hợp hơn.

## 4. Dùng generic để giữ kiểu qua API DSL

Generic cho phép một API dùng chung cho nhiều loại dữ liệu mà vẫn giữ kiểu cụ thể. Nếu một DSL truy vấn trả về `Object`, người dùng phải ép kiểu và có thể mắc lỗi khi chạy. Generic giúp kết quả giữ nguyên kiểu:

```java
public interface Repository<T, ID> {
    T findById(ID id);
    void save(T entity);
}

Repository<Order, OrderId> orders = orderRepository;
Order order = orders.findById(orderId);
```

Ở đây, `T` đại diện cho loại thực thể và `ID` là kiểu định danh tương ứng. Repository dành cho đơn hàng không nhận `CustomerId` nếu được khai báo với `OrderId`.

### 4.1. Generic trong biểu thức DSL

Một DSL lọc dữ liệu có thể định kiểu cho trường và điều kiện:

```java
import java.util.function.Predicate;

record Field<T, V>(String name) {
}

record ConditionExpression<T>(Predicate<T> test) {
    public boolean matches(T value) {
        return test.test(value);
    }
}
```

Một API đầy đủ hơn có thể định nghĩa phép so sánh theo kiểu giá trị:

```java
public interface ComparableField<T, V extends Comparable<V>> {
    V get(T source);

    default ConditionExpression<T> greaterThan(V expected) {
        return new ConditionExpression<>(source ->
            get(source).compareTo(expected) > 0
        );
    }
}
```

Với `ComparableField<Order, Integer>`, kiểu tham số của phép so sánh được giữ theo trường. Nếu muốn so sánh `Money`, DSL cần định nghĩa comparator có xét loại tiền và quy tắc miền thay vì giả định mọi giá trị tiền tệ đều có thể so sánh trực tiếp; ví dụ trên chỉ minh họa cơ chế generic.

### 4.2. Giới hạn kiểu bằng bounded type parameters

Có thể giới hạn generic để chỉ cho phép kiểu đáp ứng một hợp đồng:

```java
interface Identifiable<ID> {
    ID id();
}

interface Store<T extends Identifiable<ID>, ID> {
    T find(ID id);
}
```

`T extends Identifiable<ID>` yêu cầu thực thể phải cung cấp định danh có kiểu `ID`. Ràng buộc này giúp DSL hoặc framework làm việc với nhiều loại thực thể mà không phải ép kiểu sang một lớp chung không an toàn.

## 5. Dùng lambda và functional interface cho quy tắc miền

Java có các functional interface như `Predicate<T>`, `Function<T, R>`, `Consumer<T>` và `Supplier<T>`. Chúng rất hữu ích khi DSL cần cho phép người dùng truyền điều kiện hoặc hành động dưới dạng lambda.

Ví dụ một quy tắc kiểm tra đơn hàng:

```java
import java.util.function.Predicate;

Predicate<Order> highValueOrder = order ->
    order.total().amount().compareTo(new BigDecimal("2000000")) >= 0;
```

Để API đọc gần với miền hơn, có thể tạo functional interface riêng:

```java
@FunctionalInterface
interface RulePredicate<T> {
    boolean matches(T value);
}

record RuleDefinition<T>(String name, RulePredicate<T> rule) {
    public boolean evaluate(T value) {
        return rule.matches(value);
    }
}
```

Người dùng có thể khai báo:

```java
RuleDefinition<Order> freeShipping = new RuleDefinition<>(
    "free-shipping",
    order -> order.total().amount()
        .compareTo(new BigDecimal("2000000")) >= 0
);
```

Generic `RulePredicate<Order>` bảo đảm điều kiện nhận một `Order`. Nếu truyền lambda dùng thuộc tính chỉ có trên `Customer`, compiler sẽ phát hiện lỗi kiểu khi biểu thức không phù hợp.

### 5.1. Tách điều kiện khỏi hành động

Một DSL có thể biểu diễn điều kiện và hành động bằng hai kiểu chức năng khác nhau:

```java
@FunctionalInterface
interface Condition<T> {
    boolean test(T context);
}

@FunctionalInterface
interface Action<T> {
    void execute(T context);
}

record Rule<T>(
    String name,
    Condition<T> condition,
    Action<T> action
) {
    public void apply(T context) {
        if (condition.test(context)) {
            action.execute(context);
        }
    }
}
```

Ví dụ:

```java
Rule<Order> markPriority = new Rule<>(
    "priority-order",
    order -> order.total().amount()
        .compareTo(new BigDecimal("5000000")) >= 0,
    order -> order.markPriority()
);
```

Cách tách này làm rõ đầu vào của quy tắc và phần hiệu ứng khi điều kiện đúng. Với hệ thống nghiệp vụ quan trọng, có thể thay `void` bằng một kiểu kết quả như `Decision` hoặc `Result<T, E>` để thể hiện lỗi và kết quả từ chối tường minh.

## 6. Dùng kiểu để hướng dẫn thứ tự xây dựng DSL

Một builder thông thường có thể cho phép gọi `build()` trước khi đã cung cấp các trường bắt buộc, rồi chỉ phát hiện lỗi khi chạy. Có thể dùng interface theo từng giai đoạn (staged builder) để chỉ công bố thao tác hợp lệ ở mỗi bước.

Ví dụ DSL xây dựng pipeline yêu cầu người dùng cung cấp tên, nguồn, đích và số lần thử lại trước khi hoàn tất:

```java
public record Pipeline(
    String name,
    String source,
    String target,
    int retries
) {}

interface PipelineStart {
    PipelineNamed name(String value);
}

interface PipelineNamed {
    PipelineSource source(String value);
}

interface PipelineSource {
    PipelineTarget target(String value);
}

interface PipelineTarget {
    PipelineOptions retries(int value);
}

interface PipelineOptions {
    Pipeline build();
}

final class Pipelines {
    static PipelineStart pipeline() {
        return new Builder();
    }

    private static final class Builder implements
            PipelineStart, PipelineNamed, PipelineSource,
            PipelineTarget, PipelineOptions {
        private String name;
        private String source;
        private String target;
        private int retries;

        public PipelineNamed name(String value) {
            this.name = value;
            return this;
        }

        public PipelineSource source(String value) {
            this.source = value;
            return this;
        }

        public PipelineTarget target(String value) {
            this.target = value;
            return this;
        }

        public PipelineOptions retries(int value) {
            this.retries = value;
            return this;
        }

        public Pipeline build() {
            if (retries < 0) {
                throw new IllegalArgumentException("retries must be >= 0");
            }
            return new Pipeline(name, source, target, retries);
        }
    }
}
```

Người dùng viết:

```java
Pipeline pipeline = Pipelines.pipeline()
    .name("daily-import")
    .source("orders")
    .target("warehouse")
    .retries(3)
    .build();
```

Sau khi gọi `pipeline()`, kiểu trả về chỉ có phương thức `name`. Sau `name`, API trả về `PipelineNamed`, chỉ cung cấp `source`; các bước tiếp theo tương tự. Vì vậy, việc gọi `build()` quá sớm hoặc bỏ qua bước bắt buộc sẽ không biên dịch.

Staged builder hữu ích khi thứ tự thao tác là một phần quan trọng của DSL. Tuy nhiên, mỗi giai đoạn làm tăng số interface và độ phức tạp của API. Nếu trường có thể được khai báo theo nhiều thứ tự hoặc phần lớn đều tùy chọn, builder thông thường với kiểm tra khi xây dựng có thể dễ hiểu hơn.

## 7. Dùng kiểu kết quả để thể hiện khả năng thất bại

Một phương thức trả về `null` hoặc ném ngoại lệ cho mọi tình huống có thể khiến người dùng khó hiểu những kết quả nào được mong đợi. DSL có thể dùng kiểu kết quả để thể hiện thành công và thất bại.

Ví dụ đơn giản:

```java
sealed interface ValidationResult
        permits Valid, Invalid {
}

record Valid() implements ValidationResult {
}

record Invalid(String message) implements ValidationResult {
}
```

Một bộ kiểm tra có thể trả về `ValidationResult`:

```java
ValidationResult validate(Order order) {
    if (order.items().isEmpty()) {
        return new Invalid("Order must contain at least one item");
    }
    return new Valid();
}
```

Kiểu kết quả khiến người gọi phải xem xét các nhánh được định nghĩa. Với nhiều lỗi, có thể dùng `List<ValidationError>`; với thao tác cần trả về dữ liệu khi thành công, có thể thiết kế `Result<T, E>` tổng quát. Cách biểu diễn nên phù hợp với ngữ nghĩa của DSL, tránh tạo một framework kiểu quá phức tạp cho một API nhỏ.

## 8. Kiểu dữ liệu, suy luận kiểu và khả năng đọc

Java hỗ trợ suy luận kiểu cục bộ với `var` và suy luận tham số kiểu trong nhiều lời gọi generic. Điều này giúp API DSL ngắn hơn, nhưng không nên làm mất ý nghĩa kiểu ở những vị trí quan trọng.

Ví dụ:

```java
var orderId = new OrderId(UUID.randomUUID());
var order = orderRepository.findById(orderId);
```

Kiểu của biến vẫn là `OrderId` và `Order`, dù không viết tường minh. Tuy nhiên, trong API công khai hoặc ví dụ hướng dẫn, khai báo kiểu rõ đôi khi giúp người đọc hiểu mô hình miền nhanh hơn.

Tên kiểu và tên phương thức cũng là một phần của ngôn ngữ DSL. `Money`, `Quantity`, `OrderId` và `CustomerId` diễn đạt ý nghĩa tốt hơn `BigDecimal`, `int` và `String` khi người đọc đang làm việc với nghiệp vụ. Nên chọn tên theo ngôn ngữ của miền và tránh tạo quá nhiều wrapper không mang thêm ý nghĩa.

Java không hỗ trợ nạp chồng toán tử tùy ý. Vì vậy, DSL nhúng thường dùng phương thức có tên như `greaterThan`, `isEqualTo`, `and`, `or`, `plus` hoặc `within`. Tên phương thức rõ ràng thường dễ đọc và tránh các biểu thức gây hiểu nhầm.

## 9. Giới hạn của hệ kiểu Java

Hệ kiểu giúp kiểm tra nhiều điều kiện, nhưng không thể thay thế toàn bộ xác thực và quy tắc nghiệp vụ.

### 9.1. Quy tắc phụ thuộc dữ liệu runtime

Compiler không biết số lượng hàng còn lại trong kho hoặc tài khoản có đủ số dư tại thời điểm giao dịch. Những điều kiện này phải được kiểm tra khi chạy, gần với nguồn dữ liệu và thời điểm quyết định.

### 9.2. Null và dữ liệu không đáng tin cậy

Java không có hệ kiểu nullability đầy đủ trong ngôn ngữ cốt lõi. Một biến tham chiếu có thể là `null`, trừ khi API hoặc công cụ bổ sung quy ước. Có thể dùng `Objects.requireNonNull`, `Optional` cho một số giá trị có thể vắng mặt, annotation và công cụ phân tích tĩnh, nhưng vẫn cần xác thực dữ liệu đầu vào.

### 9.3. Type erasure

Generic của Java chủ yếu được kiểm tra lúc biên dịch và bị xóa phần lớn thông tin tham số kiểu khi chạy (type erasure). Không thể luôn truy vấn trực tiếp `T` ở runtime. Nếu framework cần biết kiểu cụ thể để giải mã dữ liệu hoặc đăng ký handler, có thể cần truyền `Class<T>`, `Type` hoặc một token kiểu được thiết kế riêng.

### 9.4. Ép kiểu không an toàn và raw types

Sử dụng raw type, unchecked cast hoặc `@SuppressWarnings` quá rộng có thể làm mất bảo đảm mà generic cung cấp. API DSL nên tránh yêu cầu người dùng ép kiểu thủ công và nên giữ kiểu cụ thể xuyên suốt chuỗi lời gọi.

### 9.5. Kiểu không đảm bảo mọi bất biến

Một `Money` có thể có cấu trúc đúng nhưng giá trị âm có thể không hợp lệ cho một loại giao dịch. Một `OrderStatus` hợp lệ không đảm bảo chuyển trạng thái hợp lệ. Những bất biến này cần constructor kiểm tra, phương thức miền hoặc bộ xác thực phù hợp.

### 9.6. Quá tải và suy luận kiểu phức tạp

Nhiều overload nhận lambda, generic lồng nhau hoặc kiểu target không rõ có thể làm lời gọi mơ hồ. Khi API DSL khó được compiler suy luận, người dùng phải thêm ép kiểu hoặc khai báo kiểu tường minh, làm giảm khả năng đọc. Nên ưu tiên chữ ký phương thức rõ, overload có khác biệt thực sự và ví dụ được biên dịch trong bộ kiểm thử.

## 10. Kết hợp hệ kiểu với kiểm tra runtime

Một thiết kế tốt chia kiểm tra thành hai nhóm:

| Kiểm tra có thể thực hiện lúc biên dịch | Kiểm tra thường cần lúc chạy |
|---|---|
| Truyền đúng loại đối tượng | Số dư tài khoản tại thời điểm thanh toán |
| Dùng đúng enum hoặc biến thể sealed | Trạng thái đơn hàng hiện tại trong cơ sở dữ liệu |
| Gọi các bước builder theo đúng thứ tự | Quyền thực tế của người dùng hiện tại |
| Kiểu đầu vào và đầu ra của lambda | Dữ liệu đến từ dịch vụ bên ngoài |
| Ràng buộc generic và quan hệ kiểu | Giới hạn số lượng còn lại trong kho |
| Một số cấu trúc và kết quả có thể kiểm tra tĩnh | Điều kiện phụ thuộc thời gian hoặc môi trường |

Ví dụ, một API có thể bảo đảm `ship` chỉ nhận `PaidOrder`, nhưng việc đơn hàng đó còn đủ hàng và địa chỉ giao hàng còn hợp lệ vẫn cần được kiểm tra tại thời điểm xử lý. Có thể kết hợp kiểu trạng thái với xác thực runtime để vừa làm rõ quy trình trong mã vừa bảo vệ dữ liệu thực tế.

## 11. Nguyên tắc thiết kế API DSL tận dụng hệ kiểu Java

Khi thiết kế DSL nhúng, nên cân nhắc những nguyên tắc sau:

- **Dùng kiểu miền có ý nghĩa:** tạo kiểu riêng cho định danh, tiền tệ, số lượng và khái niệm có quy tắc riêng.
- **Ưu tiên kiểu cụ thể hơn chuỗi:** dùng enum, sealed interface hoặc value object khi tập giá trị và ý nghĩa đã được xác định.
- **Giữ generic xuyên suốt:** tránh trả về `Object` hoặc yêu cầu ép kiểu nếu kiểu cụ thể có thể được biểu diễn.
- **Dùng lambda có hợp đồng rõ:** chọn `Predicate`, `Function` hoặc functional interface riêng có tên theo miền.
- **Giới hạn thứ tự khi thực sự cần:** staged builder có thể ngăn thiếu bước bắt buộc, nhưng chỉ nên dùng khi lợi ích lớn hơn độ phức tạp.
- **Thể hiện lỗi và kết quả tường minh:** cân nhắc kiểu kết quả thay cho `null` hoặc ngoại lệ cho các kết quả nghiệp vụ dự kiến.
- **Giữ API dễ đọc:** tên phương thức nên diễn đạt ý nghĩa miền; tránh generic lồng sâu và overload gây mơ hồ.
- **Kết hợp kiểm tra tĩnh với runtime:** không giả định compiler có thể biết dữ liệu và trạng thái bên ngoài.
- **Kiểm thử ví dụ DSL:** biên dịch các đoạn mã hướng dẫn để bảo đảm chữ ký API và cách suy luận kiểu hoạt động như tài liệu.

## 12. Quy trình áp dụng hệ kiểu khi thiết kế DSL

Có thể bắt đầu từ một DSL nhỏ và tăng dần mức độ bảo đảm kiểu:

1. **Liệt kê khái niệm miền:** xác định thực thể, định danh, giá trị, trạng thái và thao tác.
2. **Tạo kiểu miền:** dùng record hoặc class cho value object, enum cho tập lựa chọn hữu hạn và sealed type cho các biến thể có kiểm soát.
3. **Xác định hợp đồng API:** chọn kiểu tham số và kết quả cụ thể; tránh `Object` và chuỗi tùy ý ở các điểm cốt lõi.
4. **Bổ sung generic:** giữ mối quan hệ kiểu giữa dữ liệu, điều kiện, hành động và kết quả.
5. **Dùng functional interface:** cho phép người dùng truyền biểu thức hoặc hành vi bằng lambda có kiểu.
6. **Xem xét staged API:** chỉ mã hóa thứ tự thao tác vào kiểu khi đó là yêu cầu quan trọng và ổn định.
7. **Đặt kiểm tra runtime:** xác thực dữ liệu bên ngoài, bất biến phụ thuộc trạng thái và quyền thực thi.
8. **Biên dịch ví dụ thực tế:** dùng test hoặc ví dụ mẫu để xác nhận API vừa đúng kiểu vừa dễ đọc.

Hệ kiểu Java có thể biến một API thư viện thành một ngôn ngữ miền có hướng dẫn và có khả năng kiểm tra. Kiểu miền làm rõ dữ liệu, enum và sealed type giới hạn lựa chọn, generic giữ quan hệ kiểu, lambda biểu diễn điều kiện và hành động, còn staged builder có thể hướng người dùng qua các bước hợp lệ. Kết hợp những cơ chế này một cách vừa phải giúp DSL nhúng dễ khám phá, an toàn hơn khi tái cấu trúc và gần với ngôn ngữ nghiệp vụ mà nó muốn diễn đạt.
