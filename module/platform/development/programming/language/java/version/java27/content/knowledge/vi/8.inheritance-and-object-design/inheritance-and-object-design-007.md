# Nguyên tắc thay thế kiểu con và phân tách trách nhiệm trong Java 27

Trong thiết kế hướng đối tượng, **kế thừa không chỉ là dùng lại mã nguồn**. Một kiểu con (subtype) còn phải giữ những cam kết mà mã nguồn sử dụng kiểu cha đang dựa vào. Đồng thời, các trách nhiệm khác nhau nên được đặt ở những thành phần phù hợp để khi yêu cầu thay đổi, hệ thống không phải sửa nhiều nơi không liên quan.

Bài học thuộc chương **Kế thừa và thiết kế hướng đối tượng** của module **Java 27 và các kiến thức liên quan**. Trọng tâm là **Liskov Substitution Principle (LSP)** và **Separation of Concerns (SoC)**, liên hệ trực tiếp với Single Responsibility Principle (SRP), Interface Segregation Principle (ISP), interface, composition, record, sealed type và kiểm thử hợp đồng. Các ví dụ dùng những khả năng Java đang được hỗ trợ chính thức; không cần API hay cú pháp legacy.

## 1. Kiểu con và tính đa hình trong Java

Java hỗ trợ quan hệ kiểu con qua nhiều cơ chế:

- Một class `extends` một class khác.
- Một class `implements` một hoặc nhiều interface.
- Một interface `extends` interface khác.
- Một class hoặc record triển khai các interface phù hợp với trách nhiệm của nó.

Ví dụ:

```java
interface Shape {
    double area();
}

final class Circle implements Shape {
    private final double radius;

    Circle(double radius) {
        if (!Double.isFinite(radius) || radius < 0 || radius > 1_000_000) {
            throw new IllegalArgumentException("Invalid radius");
        }
        this.radius = radius;
    }

    @Override
    public double area() {
        return Math.PI * radius * radius;
    }
}
```

Biến khai báo kiểu `Shape` có thể trỏ đến instance `Circle`:

```java
Shape shape = new Circle(2.0);
System.out.println(shape.area()); // xấp xỉ 12.566370614359172
```

Khi thực thi `shape.area()`, Java dùng dynamic method dispatch để gọi phần triển khai phù hợp với đối tượng thực tế. Tuy nhiên, **biên dịch thành công không chứng minh hành vi của mọi class triển khai đều phù hợp với mong đợi của bên gọi**. Đó là vấn đề LSP giải quyết.

## 2. Nguyên tắc thay thế kiểu con (LSP) là gì?

LSP được hiểu theo nghĩa thực hành như sau:

> Nếu một chương trình hoạt động đúng khi sử dụng đối tượng kiểu nền tảng `T`, thì việc thay bằng đối tượng thuộc một kiểu con `S` phải không làm sai các điều kiện đúng đắn mà chương trình đã dựa vào, trong phạm vi hợp đồng của `T`.

Từ "thay thế" là điểm quan trọng. LSP không nói rằng mọi kiểu con phải có kết quả giống hệt nhau. Chúng có thể khác thuật toán, tốc độ, cách lưu dữ liệu hoặc giá trị trả về cụ thể. Điều bắt buộc là **đều giữ hợp đồng có thể quan sát từ góc nhìn của bên sử dụng kiểu cha**.

Ví dụ: một interface tính phí giao hàng cam kết rằng với mọi quãng đường từ 0 đến 1.000 km, method sẽ trả về khoản phí không âm. Hai chính sách tính phí có thể trả về số tiền khác nhau nhưng vẫn thay thế cho nhau nếu cả hai đều thỏa các điều kiện đó.

### 2.1. Hợp đồng hành vi (behavioral contract)

Một hợp đồng hữu ích thường mô tả:

| Thành phần | Câu hỏi cần trả lời | Ví dụ |
|---|---|---|
| Tiền điều kiện (*precondition*) | Đầu vào hợp lệ là gì? | Khoảng cách từ 0 đến 1.000 km |
| Hậu điều kiện (*postcondition*) | Kết quả phải đảm bảo điều gì? | Phí không âm |
| Bất biến (*invariant*) | Điều gì phải luôn đúng về trạng thái đối tượng? | Số dư tài khoản không âm |
| Ngoại lệ | Khi nào có thể ném exception và loại nào? | Đầu vào ngoài phạm vi bị từ chối |
| Tác dụng phụ | Có sửa trạng thái hoặc gọi hệ thống khác không? | Một phép tính phí không ghi dữ liệu |
| Quy tắc thời gian | Các thao tác có cần theo một thứ tự không? | Không thanh toán đơn đã hủy |

Java kiểm tra nhiều quy tắc **kiểu và chữ ký**, nhưng không tự động chứng minh các hậu điều kiện hay bất biến nghiệp vụ. Hợp đồng hành vi cần được ghi rõ trong API và kiểm chứng bằng thiết kế, kiểm thử cùng review mã.

### 2.2. Các quy tắc thay thế thực tế

Khi tạo subtype hoặc implementation, hãy tự hỏi:

1. **Không siết tiền điều kiện:** nếu kiểu cha chấp nhận một đầu vào, kiểu con không được âm thầm từ chối chính đầu vào hợp lệ ấy.
2. **Không làm yếu hậu điều kiện:** nếu kiểu cha hứa giá trị không âm, kiểu con không được trả về giá trị âm.
3. **Giữ bất biến:** các thao tác của kiểu con không được làm hỏng những tính chất mà bên gọi được phép trông đợi.
4. **Giữ các cam kết về exception và tác dụng phụ:** không thêm bất ngờ trái hợp đồng, chẳng hạn tự nhiên ghi dữ liệu hoặc ném exception cho đầu vào mà API hứa xử lý được.
5. **Tôn trọng hành vi theo chuỗi thao tác:** một implementation phải giữ hợp đồng cả khi nhiều lời gọi diễn ra liên tiếp, không chỉ ở từng lời gọi riêng lẻ.

Có thể **nới lỏng** tiền điều kiện hoặc **tăng cường** hậu điều kiện mà không phá LSP, miễn là vẫn giữ những cam kết gốc. Ví dụ, một subtype hỗ trợ thêm đầu vào là lợi ích bổ sung; nhưng một subtype chỉ hỗ trợ nửa số đầu vào cũ là vấn đề.

## 3. Ví dụ vi phạm LSP: siết điều kiện đầu vào

Giả sử một ứng dụng cần áp dụng nhiều chính sách giao hàng khác nhau. Hợp đồng công khai xác định khoảng cách hợp lệ là từ 0 đến 1.000 km.

```java
record DistanceKm(int value) {
    DistanceKm {
        if (value < 0 || value > 1_000) {
            throw new IllegalArgumentException("Distance out of range");
        }
    }
}

interface ShippingFeePolicy {
    // Contract: distance != null; trả về phí không âm
    // cho mọi DistanceKm hợp lệ từ 0 đến 1.000 km.
    long feeFor(DistanceKm distance);
}
```

Implementation dưới đây **vi phạm LSP**:

```java
final class LocalOnlyFee implements ShippingFeePolicy {
    @Override
    public long feeFor(DistanceKm distance) {
        if (distance.value() > 10) {
            throw new UnsupportedOperationException(
                    "Chỉ hỗ trợ trong bán kính 10 km"
            );
        }
        return 10_000L;
    }
}
```

Tình huống lỗi:

```java
ShippingFeePolicy policy = new LocalOnlyFee();
long fee = policy.feeFor(new DistanceKm(25));
```

`DistanceKm(25)` là đầu vào **hợp lệ theo hợp đồng của `ShippingFeePolicy`**. Nhưng `LocalOnlyFee` lại ném `UnsupportedOperationException`. Bên gọi đang làm việc với kiểu `ShippingFeePolicy` không thể thay implementation một cách an toàn.

**Vấn đề nằm ở hợp đồng, không nằm ở câu lệnh `throw` tự thân.** Một exception với đầu vào không hợp lệ đã được công bố trong hợp đồng là bình thường; exception bất ngờ với đầu vào mà kiểu cha hứa hỗ trợ mới là dấu hiệu vi phạm.

### 3.1. Sửa bằng cách nào?

Có nhiều hướng, tùy nghiệp vụ:

- Nếu mọi chính sách thực sự đều chỉ nhận quãng đường tối đa 10 km, hãy thay đổi hợp đồng chung và kiểu đầu vào để mô tả đúng giới hạn ấy.
- Nếu chính sách tính phí được kỳ vọng hỗ trợ đến 1.000 km, implementation phải cung cấp kết quả hợp lệ cho toàn bộ khoảng đó.
- Nếu có các nhà cung cấp chỉ hoạt động ở một vùng hạn chế, **không** buộc chúng thực hiện interface hứa nhận tất cả khoảng cách. Có thể tách trách nhiệm kiểm tra khả dụng ra khỏi thao tác báo giá.

Ví dụ một API thể hiện rõ khả năng không đáp ứng:

```java
import java.util.OptionalLong;

interface LimitedShippingQuote {
    // Có thể không có báo giá ngay cả khi distance hợp lệ.
    OptionalLong quoteIfSupported(DistanceKm distance);
}

final class LocalQuote implements LimitedShippingQuote {
    @Override
    public OptionalLong quoteIfSupported(DistanceKm distance) {
        return distance.value() <= 10
                ? OptionalLong.of(10_000L)
                : OptionalLong.empty();
    }
}
```

Ở đây, `OptionalLong.empty()` là **một phần được công bố của hợp đồng mới**, nên không có cam kết sai rằng mọi khoảng cách hợp lệ đều nhận được báo giá.

Lưu ý: chỉ thêm `boolean supports(...)` vào một interface cũ nhưng vẫn để bên gọi tùy ý gọi `feeFor(...)` không tự động chữa được lỗi thiết kế. API phải mô tả rõ cách sử dụng hợp lệ và xử lý trường hợp không được hỗ trợ.

## 4. Ví dụ khác: Rectangle và Square có setter

Trong hình học, hình vuông là một loại hình chữ nhật. Nhưng giả sử API hình chữ nhật cho phép thay đổi chiều rộng và chiều cao **độc lập**:

```java
class MutableRectangle {
    private int width;
    private int height;

    MutableRectangle(int width, int height) {
        this.width = width;
        this.height = height;
    }

    public void setWidth(int width) {
        this.width = width;
    }

    public void setHeight(int height) {
        this.height = height;
    }

    public int width() {
        return width;
    }

    public int height() {
        return height;
    }
}
```

Một client hợp lệ có thể kỳ vọng:

```java
void resize(MutableRectangle rectangle) {
    rectangle.setWidth(10);
    rectangle.setHeight(5);

    if (rectangle.width() != 10 || rectangle.height() != 5) {
        throw new IllegalStateException("Contract violated");
    }
}
```

Nếu `MutableSquare extends MutableRectangle` và override hai setter để **luôn giữ hai cạnh bằng nhau**, câu lệnh `setHeight(5)` có thể đồng thời thay đổi chiều rộng thành 5. Hành vi này phá cam kết các chiều có thể thay đổi độc lập. Bởi vậy, kiểu con có thể hợp lý về mặt *phân loại toán học* nhưng lại **không thay thế được về mặt hành vi API**.

Một thiết kế phù hợp hơn thường là hai kiểu độc lập cùng hiện thực giao diện chỉ đọc về hình dạng:

```java
interface Shape2D {
    double area();
}

record Rectangle(double width, double height) implements Shape2D {
    Rectangle {
        if (!Double.isFinite(width) || width < 0 || width > 1_000_000
                || !Double.isFinite(height) || height < 0 || height > 1_000_000) {
            throw new IllegalArgumentException("Invalid dimensions");
        }
    }

    @Override
    public double area() {
        return width * height;
    }
}

record Square(double side) implements Shape2D {
    Square {
        if (!Double.isFinite(side) || side < 0 || side > 1_000_000) {
            throw new IllegalArgumentException("Invalid side");
        }
    }

    @Override
    public double area() {
        return side * side;
    }
}
```

Bên gọi chỉ dựa vào `area()` và không giả định rằng mọi hình đều có setter chiều rộng và chiều cao. Cả `Rectangle` lẫn `Square` đều phù hợp với hợp đồng `Shape2D` nếu hợp đồng yêu cầu diện tích không âm cho kích thước hợp lệ.

**Kết luận:** quan hệ "là một" (*is-a*) trong tên gọi hoặc sơ đồ lớp **chưa đủ** để quyết định quan hệ kế thừa. Phải xét cả những hành vi mà mã sử dụng được quyền dựa vào.

## 5. Kế thừa Java có kiểm tra gì, và không kiểm tra gì?

Java cung cấp nhiều ràng buộc biên dịch để hỗ trợ tính nhất quán khi override:

| Quy tắc | Kiểm tra của Java |
|---|---|
| Đúng phương thức được override | `@Override` giúp compiler phát hiện lỗi chữ ký hoặc không tồn tại phương thức có thể override |
| Kiểu trả về | Cho phép return-type substitutability, gồm kiểu trả về hiệp biến phù hợp |
| Mức truy cập | Không được thu hẹp khả năng truy cập của phương thức override |
| Checked exception | Method override không được khai báo checked exception rộng hơn theo quy tắc override |
| `final` | Không được override phương thức instance `final` |
| `private` | Method private của class cha không bị override như method kế thừa bình thường |
| `static` | Phương thức static có thể bị hide theo quy tắc, không có dynamic override giống method instance |

Ví dụ kiểu trả về hiệp biến:

```java
class ReportSource {
    public Number count() {
        return 1;
    }
}

class CachedReportSource extends ReportSource {
    @Override
    public Integer count() {
        return 1;
    }
}
```

Với các kiểu tham chiếu phù hợp, subtype có thể trả về một kiểu cụ thể hơn. Nhưng **hợp lệ về kiểu trả về không đảm bảo đúng giá trị**: nếu hợp đồng yêu cầu số đếm không âm, implementation trả `-1` vẫn sai về hành vi.

### 5.1. Checked exception và hợp đồng thực tế

Giả sử method cha khai báo:

```java
class DataSource {
    public String read() throws java.io.IOException {
        return "ok";
    }
}
```

Một phương thức override không được tùy ý khai báo `throws java.sql.SQLException` thay cho `IOException` nếu không thỏa quy tắc checked exception của Java. Compiler có thể ngăn việc mở rộng checked exception theo cách không tương thích.

Tuy nhiên, compiler **không ngăn mọi unchecked exception**. Nếu implementation mới bất ngờ ném `UnsupportedOperationException` đối với đầu vào hợp lệ thì có thể phá LSP dù hoàn toàn biên dịch được. Vì vậy, việc xét exception là một phần của hợp đồng, không chỉ là so danh sách `throws`.

### 5.2. Không gọi method có thể override từ constructor nếu chưa kiểm soát rủi ro

Một vấn đề thiết kế kế thừa thường gặp:

```java
class Base {
    Base() {
        initialize(); // gọi phương thức có thể override
    }

    void initialize() {
        // ...
    }
}

class Derived extends Base {
    private String config = "ready";

    @Override
    void initialize() {
        // Ở thời điểm Base() gọi method này, config chưa
        // được khởi tạo bởi field initializer của Derived.
        System.out.println(config); // có thể in null
    }
}
```

Dynamic dispatch có thể gọi method của subclass **trước khi** phần khởi tạo instance của subclass hoàn tất. Đây là nguồn lỗi về bất biến đối tượng. Cách thông thường là tránh gọi method có thể override trong constructor; chuyển việc khởi tạo phức tạp sang factory hoặc một bước có kiểm soát sau khi đối tượng được tạo.

## 6. Phân tách trách nhiệm (Separation of Concerns) là gì?

**Separation of Concerns (SoC)** là tư duy chia hệ thống thành những phần giải quyết các mối quan tâm khác nhau, để thay đổi ở một mối quan tâm ít gây tác động ngoài dự kiến đến mối quan tâm khác.

Ví dụ trong xử lý đơn hàng:

- **Định giá**: tính số tiền cần trả, phí giao hàng, thuế, chiết khấu.
- **Quy tắc nghiệp vụ**: xác định đơn có được xác nhận hoặc thanh toán không.
- **Lưu trữ**: ghi và đọc đơn hàng từ nguồn dữ liệu.
- **Gửi thông báo**: gửi email, SMS hoặc sự kiện tích hợp.
- **Giao tiếp ngoài**: REST controller, CLI hoặc consumer xử lý message.

Các trách nhiệm này có lý do thay đổi khác nhau. Nếu một class tính giá, ghi database, gọi HTTP, gửi email và định dạng JSON, việc thay đổi ở bất kỳ tầng nào cũng có thể buộc sửa cùng class và làm khó kiểm thử.

### 6.1. Phân biệt SoC, SRP và ISP

Ba khái niệm có liên quan nhưng không đồng nghĩa:

| Nguyên tắc | Câu hỏi chính | Cách áp dụng |
|---|---|---|
| **SoC** | Những mối quan tâm nào cần tách khỏi nhau? | Chia domain logic, persistence, transport, presentation thành các phần có ranh giới |
| **SRP — Single Responsibility Principle** | Thành phần này có một lý do thay đổi nhất quán không? | Gom hành vi có chung trách nhiệm vào thành phần có tính kết dính cao |
| **ISP — Interface Segregation Principle** | Client có phải phụ thuộc vào method nó không dùng không? | Chia interface lớn thành giao diện nhỏ phù hợp nhu cầu client |
| **LSP — Liskov Substitution Principle** | Implementation khác có thể được thay an toàn theo hợp đồng không? | Thiết kế interface và các implementation giữ cùng cam kết hành vi |

**SRP không có nghĩa mỗi class chỉ được chứa một method**, và SoC không có nghĩa phải tạo interface hoặc class mới cho mọi câu lệnh. Mục tiêu là ranh giới có lý do nghiệp vụ hoặc kỹ thuật rõ ràng.

### 6.2. Ví dụ một class gánh quá nhiều trách nhiệm

Ví dụ dưới đây minh họa cấu trúc cần tránh:

```java
class OrderProcessor {
    void process(String orderId) {
        // 1. Đọc dữ liệu từ database
        // 2. Tính giá và phí giao hàng
        // 3. Xác thực trạng thái đơn
        // 4. Ghi thay đổi vào database
        // 5. Gửi email xác nhận
        // 6. Tạo nội dung HTTP response
    }
}
```

Mã có thể chạy, nhưng thay công thức tính phí, thay nhà cung cấp email hay thay giao thức HTTP đều kéo cùng class vào vòng sửa đổi. Kiểm thử một phép tính đơn giản có thể phải cấu hình database và email.

Không nhất thiết phải chia thành **sáu class chỉ vì có sáu bước**. Cần phân biệt phần nào là **phối hợp luồng xử lý** (orchestration), phần nào là **logic nghiệp vụ thuần túy**, và phần nào là **tích hợp hệ thống**.

## 7. Thiết kế với interface và composition

Một hướng thường hiệu quả là dùng **composition**: đối tượng cần xử lý nhận các thành phần cộng tác qua constructor, thay vì kế thừa một lớp lớn chỉ để tái sử dụng vài dòng logic.

Ví dụ:

```java
interface PricingPolicy {
    long shippingFee(long distanceKm);
}

interface OrderRepository {
    void save(String orderId, long totalVnd);
}

interface ReceiptSender {
    void sendReceipt(String orderId, long totalVnd);
}
```

Các interface này biểu đạt ba trách nhiệm riêng. Một service điều phối có thể được cung cấp những implementation thích hợp:

```java
final class CheckoutService {
    private final PricingPolicy pricing;
    private final OrderRepository repository;
    private final ReceiptSender receipts;

    CheckoutService(
            PricingPolicy pricing,
            OrderRepository repository,
            ReceiptSender receipts
    ) {
        this.pricing = java.util.Objects.requireNonNull(pricing);
        this.repository = java.util.Objects.requireNonNull(repository);
        this.receipts = java.util.Objects.requireNonNull(receipts);
    }

    void checkout(String orderId, long goodsTotal, long distanceKm) {
        if (goodsTotal < 0 || distanceKm < 0) {
            throw new IllegalArgumentException("Negative input");
        }

        long delivery = pricing.shippingFee(distanceKm);
        long total = Math.addExact(goodsTotal, delivery);

        repository.save(orderId, total);
        receipts.sendReceipt(orderId, total);
    }
}
```

`CheckoutService` vẫn có một trách nhiệm hợp lý: **điều phối ca sử dụng thanh toán**. Nó không cần biết cách truy vấn database, tạo nội dung email hoặc tính công thức phí cụ thể. Các ranh giới hợp đồng của `PricingPolicy`, `OrderRepository` và `ReceiptSender` cần được xác định rõ trước khi thay implementation.

Lưu ý: thứ tự `save` rồi `sendReceipt` trong ví dụ chỉ minh họa việc phối hợp. Trong hệ thống thực tế, gửi email có thể thất bại sau khi lưu thành công; cần chiến lược transaction/outbox/retry phù hợp thay vì giả định hai thao tác độc lập tự động có tính nguyên tử.

### 7.1. Vì sao composition hỗ trợ LSP?

Khi một class nhận dependency theo interface, thay implementation trở nên dễ dàng. Nhưng composition **không tự động đảm bảo LSP**: implementation mới vẫn phải giữ contract của interface.

```java
CheckoutService checkout = new CheckoutService(
        new StandardPricing(),
        new DatabaseOrderRepository(),
        new EmailReceiptSender()
);
```

Các tên class ở đây chỉ minh họa vai trò, không phải implementation được định nghĩa ở ví dụ trên. Một hệ thống có thể thay `EmailReceiptSender` bằng `QueueReceiptSender`, nhưng phải làm rõ hợp đồng của `sendReceipt`: lời gọi đảm bảo thư **đã gửi thành công**, hay chỉ đảm bảo **đã xếp hàng để gửi**? Hai ý nghĩa này khác nhau và có thể ảnh hưởng tính thay thế.

**Thiết kế hợp đồng trước, sau đó chọn cơ chế implement.** Đừng dùng interface như một lớp vỏ cho hai hành vi thực chất khác nhau.

## 8. Ví dụ hoàn chỉnh: LSP kết hợp SRP trong Java 27

Đoạn mã dưới đây là một chương trình **tự chứa**, có thể lưu vào `LspAndResponsibilityDemo.java`. Ví dụ tách dữ liệu đơn hàng, chính sách tính phí và phép tính tổng tiền. Hai chính sách đều tuân theo cùng hợp đồng tính phí.

```java
import java.util.List;
import java.util.Objects;

record DistanceKm(int value) {
    DistanceKm {
        if (value < 0 || value > 1_000) {
            throw new IllegalArgumentException(
                    "Distance must be between 0 and 1000"
            );
        }
    }
}

record Order(long goodsTotalVnd, DistanceKm distance) {
    Order {
        if (goodsTotalVnd < 0) {
            throw new IllegalArgumentException(
                    "Goods total cannot be negative"
            );
        }
        Objects.requireNonNull(distance, "distance");
    }
}

interface ShippingFeePolicy {
    // Hợp đồng:
    // - distance là DistanceKm khác null, có giá trị 0..1000.
    // - Mọi đầu vào hợp lệ nhận phí >= 0.
    // - Phép tính không thay đổi trạng thái bên ngoài.
    long feeFor(DistanceKm distance);
}

final class StandardFee implements ShippingFeePolicy {
    @Override
    public long feeFor(DistanceKm distance) {
        Objects.requireNonNull(distance, "distance");
        return 15_000L + 3_000L * distance.value();
    }
}

final class ExpressFee implements ShippingFeePolicy {
    @Override
    public long feeFor(DistanceKm distance) {
        Objects.requireNonNull(distance, "distance");
        return 30_000L + 5_000L * distance.value();
    }
}

final class OrderTotalCalculator {
    private final ShippingFeePolicy shippingFee;

    OrderTotalCalculator(ShippingFeePolicy shippingFee) {
        this.shippingFee = Objects.requireNonNull(shippingFee);
    }

    long totalFor(Order order) {
        Objects.requireNonNull(order, "order");

        long fee = shippingFee.feeFor(order.distance());
        return Math.addExact(order.goodsTotalVnd(), fee);
    }
}

public class LspAndResponsibilityDemo {
    public static void main(String[] args) {
        Order order = new Order(250_000L, new DistanceKm(25));

        List<ShippingFeePolicy> policies =
                List.of(new StandardFee(), new ExpressFee());

        for (ShippingFeePolicy policy : policies) {
            OrderTotalCalculator calculator =
                    new OrderTotalCalculator(policy);

            long total = calculator.totalFor(order);
            System.out.println(
                    policy.getClass().getSimpleName() + ": " + total
            );
        }
    }
}
```

Biên dịch và chạy bằng JDK 27:

```bash
javac LspAndResponsibilityDemo.java
java LspAndResponsibilityDemo
```

Kết quả:

```text
StandardFee: 340000
ExpressFee: 405000
```

Giải thích số tiền:

- `StandardFee`: 15.000 + 3.000 × 25 = 90.000 VND; tổng 250.000 + 90.000 = **340.000 VND**.
- `ExpressFee`: 30.000 + 5.000 × 25 = 155.000 VND; tổng 250.000 + 155.000 = **405.000 VND**.

### 8.1. LSP trong ví dụ

`OrderTotalCalculator` chỉ biết `ShippingFeePolicy`. Nó sử dụng cùng lời gọi `feeFor` cho cả hai implementation và nhận kết quả đúng hợp đồng: mỗi khoảng cách hợp lệ cho phí không âm. Client không cần kiểm tra `instanceof StandardFee` hay `instanceof ExpressFee` để chọn cách xử lý riêng.

Nếu bổ sung `LocalOnlyFee` ở mục 3 vào danh sách, lời gọi quãng đường 25 km sẽ thất bại dù input hoàn toàn hợp lệ. Đó chính là chỗ vi phạm LSP xuất hiện trong mã sử dụng.

### 8.2. SoC và SRP trong ví dụ

- `DistanceKm` kiểm soát giới hạn của dữ liệu khoảng cách.
- `Order` chứa dữ liệu đầu vào và bất biến của đơn hàng.
- `ShippingFeePolicy` mô tả hợp đồng phí giao hàng.
- `StandardFee` và `ExpressFee` chỉ chịu trách nhiệm về quy tắc tính phí của mình.
- `OrderTotalCalculator` kết hợp tổng giá hàng và phí vận chuyển.
- `LspAndResponsibilityDemo` chỉ đóng vai trò entry point minh họa.

Mỗi phần có lý do thay đổi tương đối rõ. Thay công thức phí express không yêu cầu sửa `Order` hay `OrderTotalCalculator`. Thay cách lưu đơn cũng không liên quan đến code tính phí.

### 8.3. Giới hạn cần biết

Chương trình chỉ minh họa tính phí trong phạm vi 0..1.000 km. `Math.addExact` được dùng để **phát hiện tràn số khi cộng tổng tiền**; nếu tổng vượt giới hạn `long`, method ném `ArithmeticException` thay vì âm thầm tràn. Ứng dụng thực tế cần xác định hợp đồng rõ ràng cho trường hợp này và cân nhắc `BigDecimal`, kiểu tiền tệ hoặc thư viện số học phù hợp nếu miền dữ liệu đòi hỏi.

## 9. Kiểm thử hợp đồng cho nhiều implementation

Kiểm thử từng class riêng chưa đủ khi chúng cùng thực hiện một interface. Nên tạo **bộ kiểm thử hợp đồng** chạy cho mọi implementation nhằm kiểm tra các cam kết chung.

Ví dụ hàm kiểm tra thuần Java, không phụ thuộc thư viện kiểm thử:

```java
static void verifyShippingContract(ShippingFeePolicy policy) {
    for (int km : new int[] { 0, 1, 10, 11, 25, 100, 1_000 }) {
        long fee = policy.feeFor(new DistanceKm(km));

        if (fee < 0) {
            throw new AssertionError(
                    "Negative fee at distance " + km
            );
        }
    }
}
```

Hàm này giả sử được đặt trong một class có thể truy cập `ShippingFeePolicy` và `DistanceKm`. Gọi nó cho `new StandardFee()` và `new ExpressFee()` sẽ kiểm tra các điểm biên quan trọng. Với `LocalOnlyFee`, giá trị 11 km gây lỗi và giúp phát hiện sự không tương thích.

Tuy nhiên, **vài điểm kiểm thử không chứng minh hợp đồng đúng cho toàn bộ miền đầu vào**. Với yêu cầu quan trọng, hãy bổ sung:

- Kiểm thử các giá trị biên và lớp tương đương.
- Kiểm thử property-based trên dữ liệu được sinh trong toàn miền hợp lệ.
- Kiểm thử ngoại lệ với đầu vào không hợp lệ theo hợp đồng.
- Kiểm thử chuỗi thao tác và trạng thái đối tượng.
- Kiểm thử tác dụng phụ, tính idempotent và đồng thời nếu API hứa hẹn những đặc tính này.
- Chạy cùng bộ contract test mỗi khi thêm implementation mới.

Trong dự án có framework test, có thể chuyển `verifyShippingContract` thành một bộ test dùng chung cho tất cả implementation. Không cần làm một interface test riêng cho mọi class nếu chúng không chia sẻ hợp đồng thực sự.

## 10. Interface Segregation: tách đúng phần client cần

Một interface quá lớn có thể khiến implementation phải cung cấp những method không có ý nghĩa với chính nó:

```java
interface OfficeDevice {
    void print(String document);
    void scan(String destination);
    void fax(String phoneNumber);
}
```

Một máy in chỉ hỗ trợ in vẫn phải implement `scan` và `fax`. Nếu hai method đó chỉ ném `UnsupportedOperationException`, nhiều client có thể bị bất ngờ. Đây là dấu hiệu một abstraction đang gom các năng lực khác nhau.

Có thể phân tách:

```java
interface Printer {
    void print(String document);
}

interface Scanner {
    void scan(String destination);
}

interface FaxSender {
    void fax(String phoneNumber);
}

final class BasicPrinter implements Printer {
    @Override
    public void print(String document) {
        System.out.println(document);
    }
}

final class AllInOneDevice implements Printer, Scanner, FaxSender {
    @Override
    public void print(String document) {
        System.out.println(document);
    }

    @Override
    public void scan(String destination) {
        System.out.println("Scanning to " + destination);
    }

    @Override
    public void fax(String phoneNumber) {
        System.out.println("Faxing to " + phoneNumber);
    }
}
```

Client chỉ cần in thì phụ thuộc vào `Printer`. Thiết bị đa chức năng implement những khả năng nó thực sự hỗ trợ.

**Lưu ý về `UnsupportedOperationException`:** việc một method ném ngoại lệ này không tự động là vi phạm LSP. Một số API Java, ví dụ các thao tác cập nhật tùy chọn trong Collections Framework, **công bố rõ** rằng implementation có thể không hỗ trợ và ném `UnsupportedOperationException`. Đánh giá LSP phải dựa trên hợp đồng thật sự của interface, không chỉ dựa trên tên exception.

## 11. Kế thừa hay composition?

Kế thừa thích hợp khi có quan hệ kiểu con **và** hợp đồng hành vi ổn định, cần đa hình hoặc chia sẻ cơ chế được thiết kế cho việc mở rộng. Composition thích hợp khi một class chỉ cần **sử dụng** năng lực từ thành phần khác.

| Câu hỏi | Kế thừa | Composition |
|---|---|---|
| Có quan hệ kiểu con rõ ràng không? | Cần có | Không bắt buộc |
| Thay hành vi khi chạy | Qua đa hình phương thức instance | Qua thay đối tượng cộng tác |
| Phụ thuộc vào chi tiết implementation | Có thể lớn nếu kế thừa class cụ thể | Thường nhỏ hơn khi chỉ dùng interface |
| Tái sử dụng mã | Có thể qua protected method và class cha | Qua delegate hoặc service tái sử dụng |
| Rủi ro | Fragile base class, hành vi override không tương thích | Thêm đối tượng và bước ủy quyền |
| Khi nên ưu tiên | Subtype thật sự phải tuân theo cùng hợp đồng | Kết hợp nhiều năng lực độc lập |

Không cần từ bỏ kế thừa tuyệt đối: interface, abstract class và các class được thiết kế cho mở rộng vẫn rất hữu ích. Nhưng nếu mục đích duy nhất là "dùng lại vài method", một đối tượng cộng tác được inject qua constructor thường bộc lộ dependency rõ và tránh buộc client chấp nhận một quan hệ kiểu con không đúng.

### 11.1. Thận trọng với protected và base class

Nếu subclass phụ thuộc vào nhiều `protected` field hoặc trình tự gọi method nội bộ của superclass, thay đổi nhỏ của superclass có thể làm hỏng subclass. Đó là dạng phụ thuộc implementation thường gọi là *fragile base class*.

Khi cho phép kế thừa, superclass nên xác định rõ điểm mở rộng (*extension point*), hợp đồng override và những điều không được thay đổi. Nếu không dự kiến subclass tùy biến, cân nhắc `final class` hoặc các thành phần nội bộ `private` để tránh tạo nhầm API kế thừa.

## 12. Các công cụ Java hiện đại giúp thiết kế ranh giới rõ hơn

### 12.1. Record cho dữ liệu có cấu trúc

`record` phù hợp khi cần một loại dữ liệu mang các thành phần xác định. Compiler sinh accessor, `equals`, `hashCode` và `toString` phù hợp với các thành phần record.

```java
record PriceQuote(long goodsTotal, long shippingFee) {
    PriceQuote {
        if (goodsTotal < 0 || shippingFee < 0) {
            throw new IllegalArgumentException("Negative amount");
        }
    }

    long finalTotal() {
        return Math.addExact(goodsTotal, shippingFee);
    }
}
```

Record giúp gom các giá trị có cùng ý nghĩa và đặt validation gần dữ liệu. Record không đảm bảo **deep immutability** nếu chứa tham chiếu đến collection mutable hoặc đối tượng có thể thay đổi; cần defensive copy hoặc cấu trúc bất biến khi hợp đồng yêu cầu.

### 12.2. Sealed type cho tập biến thể có giới hạn

Nếu miền dữ liệu có một tập trường hợp đóng nhưng **các trường hợp mang dữ liệu khác nhau**, sealed interface và record có thể rõ ràng hơn một class cha có nhiều field `null`.

```java
sealed interface PaymentOutcome permits PaymentApproved, PaymentDeclined {}

record PaymentApproved(String transactionId)
        implements PaymentOutcome {}

record PaymentDeclined(String reason)
        implements PaymentOutcome {}

class PaymentMessages {
    static String describe(PaymentOutcome outcome) {
        return switch (outcome) {
            case PaymentApproved(var id) -> "Đã thanh toán: " + id;
            case PaymentDeclined(var reason) -> "Bị từ chối: " + reason;
        };
    }
}
```

Trong Java 27, `sealed` type, record pattern và `switch` pattern là những tính năng chính thức. Biểu thức `switch` có thể kiểm tra tính đầy đủ của các nhánh theo tập subtype được phép.

**Phân biệt hai bài toán:**

- **Behavioral subtype:** các implementation thực hiện cùng một khả năng và phải thay thế được theo contract; ví dụ `ShippingFeePolicy`.
- **Các biến thể dữ liệu:** mỗi biến thể thể hiện một kết quả khác nhau; mã sử dụng có thể cần phân nhánh theo kiểu; ví dụ `PaymentApproved` và `PaymentDeclined`.

Không cần ép mọi biến thể vào một interface chứa các thao tác thiếu ý nghĩa chỉ để "có tính đa hình". Khi một bài toán thiên về phân loại dữ liệu, sealed type và pattern matching thường biểu đạt ý định tốt hơn.

### 12.3. Interface chỉ nên mô tả hành vi thực sự chung

Một interface không nên được tạo chỉ vì dự án luôn "có interface cho mọi class". Abstraction có giá trị khi nó biểu đạt một hợp đồng ổn định, tạo ranh giới hữu ích hoặc có nhiều bên sử dụng/implementation dự kiến.

Đôi khi một `final class` nhỏ với method rõ nghĩa là đủ. Việc thêm hàng loạt interface và adapter không mang lại thay thế thực tế có thể khiến code khó đọc hơn mà không tăng tính linh hoạt.

## 13. Ranh giới module, package và phụ thuộc

Ở quy mô ứng dụng, phân tách trách nhiệm không chỉ nằm trong các class. Một cách tổ chức thường gặp:

```text
com.example.order.domain
    Order
    PriceQuote
    ShippingFeePolicy

com.example.order.application
    CheckoutService

com.example.order.persistence
    DatabaseOrderRepository

com.example.order.notification
    EmailReceiptSender

com.example.order.web
    CheckoutController
```

Đây là ví dụ về **vai trò**, không phải quy tắc cố định cho mọi hệ thống. Điều quan trọng là chiều phụ thuộc:

- Domain nên diễn đạt nghiệp vụ mà không cần phụ thuộc vào HTTP controller hoặc driver database cụ thể.
- Application service phối hợp nghiệp vụ, transaction và các dependency cần thiết.
- Persistence và notification chứa code tích hợp với công nghệ bên ngoài.
- API/transport chuyển request/response sang và từ dữ liệu ứng dụng.

Trong dự án Java có `module-info.java`, JPMS cho phép công bố package thông qua `exports` và khai báo module dependency qua `requires`. Phạm vi public của một class/method không đồng nghĩa package của nó tự động được module khác truy cập. Việc chia module chỉ nên làm khi mang lại ranh giới có ích; không cần tạo nhiều module chỉ để mô phỏng một sơ đồ kiến trúc.

### 13.1. Tránh phụ thuộc vòng

Ví dụ không nên để domain logic gọi trực tiếp REST controller, còn REST controller lại gọi domain logic. Vòng phụ thuộc kiểu này làm các thành phần khó dùng độc lập và khó kiểm thử.

Một hướng đơn giản là để adapter phụ thuộc vào hợp đồng do tầng thích hợp cung cấp. Trong ứng dụng phức tạp, có thể áp dụng dependency inversion: code điều phối phụ thuộc vào các interface cho thao tác bên ngoài, còn adapter triển khai interface đó.

## 14. Quy trình review một quan hệ kế thừa

Khi gặp một kế thừa mới hoặc triển khai interface mới, có thể xem xét theo các bước:

1. **Viết hợp đồng bằng ngôn ngữ cụ thể:** đầu vào hợp lệ, đầu ra, exception, invariant, side effect và các chuỗi thao tác.
2. **Tìm một client tiêu biểu:** client nhận kiểu cha và không biết subtype thực tế.
3. **Thử thay thế:** lần lượt truyền tất cả implementation mà client được phép sử dụng; xem giả định nào bị phá.
4. **Kiểm tra điều kiện bị siết:** subtype có đòi hỏi thêm đầu vào, trạng thái hoặc thứ tự thao tác không?
5. **Kiểm tra kết quả bị nới lỏng:** subtype có trả `null`, kết quả âm, kết quả sai đơn vị hoặc thiếu side effect đã cam kết không?
6. **Kiểm tra phân tách trách nhiệm:** method/class nào đang gánh nhiều lý do thay đổi? Interface nào bắt client phụ thuộc vào khả năng không cần?
7. **Chọn thiết kế phù hợp:** sửa hợp đồng, phân tách interface, dùng composition hoặc mô hình hóa biến thể dữ liệu bằng record/sealed type.
8. **Viết contract tests:** chạy bộ test chung với mọi implementation cùng hợp đồng.
9. **Xem xét thay đổi theo thời gian:** quy tắc hành vi và định dạng dữ liệu có còn tương thích với client cũ không?

Một hợp đồng đủ rõ thường giúp cả thiết kế, review, test và tài liệu API nhất quán hơn.

## 15. Những lỗi thiết kế phổ biến

| Sai lầm | Vấn đề | Hướng giải quyết |
|---|---|---|
| Kế thừa chỉ để dùng lại mã | Gắn quan hệ is-a không đúng | Composition/delegation |
| Thêm `UnsupportedOperationException` tùy ý | Subtype từ chối đầu vào hợp lệ | Phân tách capability hoặc sửa hợp đồng |
| Tin rằng `@Override` bảo đảm LSP | Compiler chỉ kiểm tra quy tắc ngôn ngữ | Ghi contract và kiểm thử hành vi |
| Subtype yêu cầu điều kiện chặt hơn | Làm client của kiểu cha thất bại | Giữ hoặc nới tiền điều kiện |
| Subtype trả kết quả yếu hơn cam kết | Phá hậu điều kiện | Bảo đảm đầu ra đúng miền và ý nghĩa |
| Đổi side effect của method | Client không còn nhận điều đã hứa | Ghi rõ và tuân thủ semantics |
| Override method gọi từ constructor | Trạng thái subclass chưa khởi tạo xong | Tránh gọi method có thể override trong constructor |
| God class ôm nhiều việc | Khó thay đổi/kiểm thử độc lập | Tách domain, persistence, notification, transport |
| Interface quá lớn | Client phụ thuộc vào method không dùng | Áp dụng ISP theo nhóm capability |
| Tạo interface cho tất cả class | Tăng trừu tượng không cần thiết | Chỉ tạo khi có contract/ràng buộc hữu ích |
| Cho rằng record là deep immutable | Field tham chiếu mutable vẫn thay đổi được | Defensive copy và thiết kế immutable |
| Dùng exception tùy ý như luồng điều khiển nghiệp vụ | Contract không nhất quán | Dùng result type hoặc `Optional` khi vắng kết quả là trường hợp bình thường |
| Nhầm "cùng tên method" là cùng hành vi | Semantic contract có thể khác nhau | So sánh tiền/hậu điều kiện và side effect |

## 16. Bài tập thực hành

### Bài 1. Phát hiện vi phạm LSP

Một interface `DocumentReader` cam kết `String read(String path)` đọc mọi tài liệu có đường dẫn hợp lệ, ném `IOException` nếu lỗi I/O. Một implementation chỉ hỗ trợ file `.txt` và ném `UnsupportedOperationException` cho `.pdf`.

Hãy xác định phần nào của hợp đồng bị phá và đề xuất hai cách thiết kế lại: một cách giữ interface chung và một cách biểu diễn khả năng hỗ trợ có giới hạn.

### Bài 2. Thực hành hợp đồng phí giao hàng

Mở rộng ví dụ ở mục 8 bằng `EconomyFee`. Đảm bảo implementation nhận toàn bộ miền quãng đường hợp lệ, trả về phí không âm và không có side effect. Viết hàm kiểm thử chung áp dụng cho cả ba implementation.

### Bài 3. Phân tách trách nhiệm

Giả sử class `InvoiceManager` hiện làm bốn việc: tính tổng, ghi database, tạo PDF và gửi email. Hãy xác định các lý do thay đổi khác nhau, rồi đề xuất ranh giới class hoặc interface phù hợp. Không cần tạo interface cho trách nhiệm mà hiện tại chưa có nhu cầu trừu tượng hóa.

### Bài 4. Thiết kế interface theo capability

Thiết kế ứng dụng quản lý thiết bị, gồm máy in, máy quét và thiết bị đa năng. Định nghĩa những interface tối thiểu để client in tài liệu không cần phụ thuộc vào khả năng quét hoặc fax. Giải thích vì sao `BasicPrinter` không nên phải ném `UnsupportedOperationException` cho các phương thức hoàn toàn không có ý nghĩa với thiết bị của nó.

### Bài 5. Chọn sealed type hay subtype hành vi

Thiết kế kết quả thanh toán gồm `Approved(transactionId)`, `Declined(reason)`, `Pending(expiresAt)`. Hãy dùng sealed interface và record để mô tả ba biến thể, sau đó viết `switch` expression hiển thị thông điệp cho từng trường hợp. Giải thích vì sao mô hình này khác interface `ShippingFeePolicy`.

### Bài 6. Review tác dụng phụ

Hai implementation cùng thực hiện `ReceiptSender`. Implementation A gửi email đồng bộ và chỉ trả về khi nhà cung cấp email xác nhận; implementation B chỉ ghi yêu cầu vào hàng đợi và trả về ngay. Hãy đề xuất một hợp đồng chung thích hợp **nếu có thể**, hoặc tách API thành hai khả năng khác nhau. Xác định những thông tin client cần biết để không tạo nhầm thông báo "đã gửi".

## 17. Tóm tắt

**LSP** yêu cầu một subtype hoặc implementation giữ được hợp đồng hành vi mà client của kiểu cha đang dựa vào. Không chỉ kiểu trả về và chữ ký phương thức, hợp đồng còn bao gồm miền đầu vào, kết quả được bảo đảm, invariant, exception, tác dụng phụ và các tương tác theo thời gian. Java hỗ trợ bằng kiểm tra kiểu, `@Override` và quy tắc override, nhưng không tự động chứng minh LSP.

**SoC** hướng đến tách các mối quan tâm khác nhau, **SRP** giúp giữ thành phần có một lý do thay đổi nhất quán, và **ISP** tránh ép client phụ thuộc vào capability không sử dụng. `interface`, composition, constructor injection, record và sealed type đều là công cụ hữu ích khi được dùng đúng bài toán; không nên lạm dụng trừu tượng hóa.

Khi thiết kế lớp và đối tượng trong Java 27, hãy **định nghĩa hành vi trước khi quyết định kế thừa**, giữ API rõ nghĩa, phân tách trách nhiệm theo lý do thay đổi thực tế và áp dụng contract test để việc thay implementation không phá chương trình.

## Tài liệu tham khảo

- [Java Language Specification, Java SE 27 — §8.4.8 Inheritance, Overriding, and Hiding](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-8.html#jls-8.4.8)
- [Java Language Specification, Java SE 27 — §8.4.8.3 Requirements in Overriding and Hiding](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-8.html#jls-8.4.8.3)
- [Java Language Specification, Java SE 27 — §9 Interfaces](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-9.html)
- [Java Language Specification, Java SE 27 — §8.10 Record Classes](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-8.html#jls-8.10)
- [Java Language Specification, Java SE 27 — §15 Expressions (method invocation và switch expression)](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-15.html)
