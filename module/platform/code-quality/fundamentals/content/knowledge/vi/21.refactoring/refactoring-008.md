# Giảm trạng thái và làm rõ phụ thuộc

Một lớp Java xử lý checkout có vẻ đơn giản: nhận giỏ hàng, tính tổng tiền, tạo mã biên nhận và lưu kết quả. Nhưng khi chạy hai lần liên tiếp trên cùng đối tượng, số tiền lần thứ hai lại cộng thêm tiền của lần đầu. Test chạy riêng thường qua, chạy cả bộ đôi khi thất bại. Nhóm sửa bằng cách đặt lại một biến ở đầu phương thức; sau đó lỗi xuất hiện lần nữa khi hai request chạy đồng thời.

Vấn đề không chỉ nằm ở một dòng thiếu lệnh gán. **Kết quả một lần xử lý đang phụ thuộc vào trạng thái của những lần gọi trước và các nguồn dữ liệu ngầm.** Người đọc không thể xác định hành vi chỉ từ tham số và những phụ thuộc được công khai.

Trong chương **Tái cấu trúc** của module `CODE_QUALITY_FUNDAMENTALS`, chất lượng mã nguồn được nhìn qua khả năng **đáng tin cậy, dễ hiểu và dễ thay đổi**. Một hướng refactor quan trọng là **giảm trạng thái phải ghi nhớ, đưa dữ liệu về phạm vi sở hữu phù hợp và làm lộ các phụ thuộc quyết định hành vi**. Điều này không đồng nghĩa xóa mọi trạng thái: đơn hàng, tồn kho, phiên làm việc hay tiến trình nhiều bước vẫn cần trạng thái thực. Mục tiêu là giữ **trạng thái cần thiết** và loại bỏ **trạng thái dư thừa hoặc bị đặt sai chỗ**.

Sau bài học, bạn có thể:

- Phân biệt dữ liệu đầu vào, biến tạm, trạng thái suy ra, trạng thái nghiệp vụ và trạng thái chia sẻ.
- Phát hiện phụ thuộc ẩn vào đồng hồ, random, biến toàn cục, môi trường và hạ tầng.
- Chuyển trạng thái chỉ phục vụ một lời gọi thành biến cục bộ hoặc kết quả bất biến.
- Sử dụng `record`, defensive copy và ranh giới sở hữu để hạn chế thay đổi ngoài ý muốn.
- Làm rõ phụ thuộc bằng constructor và hợp đồng nhỏ khi có lợi, không tạo abstraction máy móc.
- Tách logic thuần túy khỏi I/O, nhưng giữ những bất biến, transaction và side effect cần thiết.
- Viết test kiểm tra khả năng gọi lại, tính độc lập, lỗi và tác động của nhiều request.
- Refactor từng bước mà không ngầm thay đổi hợp đồng nghiệp vụ.

## 1. “Trạng thái” trong mã là gì?

**Trạng thái (*state*)** là thông tin được giữ tại một thời điểm và có thể ảnh hưởng đến hành vi sau đó. Trong Java, nó có thể nằm ở biến cục bộ, field của đối tượng, `static` field, cache, database, hàng đợi hoặc một hệ thống ngoài.

Ví dụ:

```java
final class Counter {
    private int count;

    int increment() {
        return ++count;
    }
}
```

`increment()` không chỉ phụ thuộc vào việc được gọi. Kết quả phụ thuộc `count` trước đó. Đây là trạng thái có chủ đích nếu lớp thật sự biểu diễn một bộ đếm.

Ngược lại:

```java
final class PriceCalculator {
    private long subtotal;

    long calculate(long unitPrice, int quantity) {
        subtotal += unitPrice * quantity;
        return subtotal;
    }
}
```

Nếu yêu cầu là “tính tiền cho **một** dòng hàng”, field `subtotal` khiến kết quả phụ thuộc những lần gọi trước mà nghiệp vụ không yêu cầu. Đó là **trạng thái phát sinh do cách triển khai**, không phải bản chất của bài toán.

Câu hỏi khi đọc code: **Dữ liệu này cần sống bao lâu, và ai có quyền thay đổi nó?**

## 2. Phân loại trạng thái trước khi refactor

Không nên xóa mọi field chỉ vì “stateless tốt hơn”. Hãy phân loại:

| Loại dữ liệu | Ví dụ | Phạm vi sở hữu phù hợp |
| --- | --- | --- |
| **Đầu vào một lời gọi** | Giỏ hàng của request hiện tại | Tham số hoặc object đầu vào |
| **Kết quả trung gian** | `subtotalVnd` đang cộng | Biến cục bộ trong phép tính |
| **Giá trị suy ra** | `totalVnd = subtotal + fee` | Tính khi cần hoặc lưu có kiểm soát nếu có lý do |
| **Cấu hình ổn định** | Ngưỡng miễn phí giao hàng | Hằng/policy/config theo vòng đời phù hợp |
| **Trạng thái miền thật** | Trạng thái đơn, số tồn kho | Đối tượng sở hữu bất biến và kho lưu trữ |
| **Trạng thái phiên hoặc tiến trình** | Bước đang thực hiện của workflow | State machine hoặc session có lifecycle rõ |
| **Cache** | Báo giá được tái sử dụng | Thành phần cache với TTL, quota, invalidation |
| **Trạng thái toàn cục chia sẻ** | `static mutable Map` | Chỉ khi thật sự cần; quản lý concurrency và lifecycle |
| **Phụ thuộc bên ngoài** | Database, đồng hồ, HTTP client | Ranh giới giao tiếp hoặc dependency công khai |

Một dấu hiệu đáng nghi là field chỉ được ghi ở đầu một phương thức, đọc ở cuối phương thức đó, nhưng vẫn được giữ đến lần gọi sau. Nếu không cần vòng đời dài hơn một lần gọi, biến cục bộ thường đơn giản và an toàn hơn.

Tương tự, một object có cả `unitPrice`, `quantity` và `lineTotal` trong trạng thái mutable có thể chứa ba giá trị không nhất quán sau khi một thành phần bị cập nhật. Nếu `lineTotal` luôn suy ra được từ hai giá trị đầu, có thể tránh lưu nó như nguồn dữ liệu độc lập.

## 3. Tình huống Java: trạng thái của request bị giữ trong service

Giả sử hệ thống có yêu cầu:

- Mã khách và SKU không được rỗng.
- Số lượng dương và đơn giá nguyên VND không âm.
- Tạm tính là tổng đơn giá nhân số lượng, phát hiện tràn `long`.
- Từ 500.000 VND được miễn phí giao hàng; dưới ngưỡng phí 25.000 VND.
- Tạo một biên nhận có mã và thời gian, sau đó lưu vào kho dữ liệu.

Các kiểu nghiệp vụ dùng trong những ví dụ tiếp theo:

```java
import java.time.Instant;
import java.util.List;
import java.util.Objects;

record OrderLine(String sku, int quantity, long unitPriceVnd) {
    OrderLine {
        if (sku == null || sku.isBlank()) {
            throw new IllegalArgumentException("SKU is required");
        }
        if (quantity <= 0 || unitPriceVnd < 0) {
            throw new IllegalArgumentException("Invalid line values");
        }
    }
}

record CheckoutRequest(String customerId, List<OrderLine> lines) {
    CheckoutRequest {
        if (customerId == null || customerId.isBlank()) {
            throw new IllegalArgumentException("Customer ID is required");
        }
        Objects.requireNonNull(lines, "lines");
        if (lines.isEmpty()) {
            throw new IllegalArgumentException("Cart cannot be empty");
        }
        lines = List.copyOf(lines);
    }
}

record Receipt(
        String id,
        String customerId,
        long subtotalVnd,
        long shippingFeeVnd,
        long totalVnd,
        Instant createdAt
) {}

@FunctionalInterface
interface ReceiptStore {
    void save(Receipt receipt);
}
```

`List.copyOf` tạo một danh sách không thể chỉnh sửa qua API danh sách và từ chối phần tử `null`. Nó là **bản sao nông**; ở đây từng `OrderLine` là record chỉ chứa dữ liệu bất biến nên không có object mutable bên trong cần bảo vệ thêm.

### Phiên bản có trạng thái sai phạm vi

```java
import java.time.Instant;
import java.util.Objects;
import java.util.UUID;

final class StatefulCheckoutService {
    private final ReceiptStore store;

    private CheckoutRequest currentRequest;
    private long subtotalVnd;
    private Receipt lastReceipt;

    StatefulCheckoutService(ReceiptStore store) {
        this.store = Objects.requireNonNull(store);
    }

    Receipt checkout(CheckoutRequest request) {
        currentRequest = Objects.requireNonNull(request);

        for (OrderLine line : currentRequest.lines()) {
            long lineTotal = Math.multiplyExact(
                    line.unitPriceVnd(), line.quantity());
            subtotalVnd = Math.addExact(subtotalVnd, lineTotal);
        }

        long feeVnd = subtotalVnd >= 500_000L ? 0L : 25_000L;
        long totalVnd = Math.addExact(subtotalVnd, feeVnd);

        Receipt receipt = new Receipt(
                UUID.randomUUID().toString(),
                currentRequest.customerId(),
                subtotalVnd,
                feeVnd,
                totalVnd,
                Instant.now()
        );

        store.save(receipt);
        lastReceipt = receipt;
        return receipt;
    }
}
```

Dù mã khá ngắn, có ít nhất bốn điểm cần chú ý:

1. `subtotalVnd` là field và **không được đặt về 0** giữa các lần gọi. Checkout thứ hai có thể cộng cả giá trị của checkout thứ nhất.
2. `currentRequest` chỉ phục vụ lần xử lý đang chạy nhưng được giữ thành field. Khi hai luồng gọi cùng lúc, một luồng có thể đọc request mà luồng khác vừa gán.
3. `lastReceipt` giữ dữ liệu đã được trả về và lưu. Nếu không có chức năng thực sự sử dụng nó, field này chỉ tăng trách nhiệm quản lý và có thể tạo nguồn dữ liệu thứ hai.
4. `UUID.randomUUID()` và `Instant.now()` là hai **đầu vào ngầm**. Người gọi không thể chọn ID và thời gian cho một bài test xác định.

Thêm `subtotalVnd = 0L` vào đầu `checkout` có thể chữa lỗi tuần tự, nhưng **không bảo vệ nhiều request đồng thời** trên cùng instance vì field vẫn bị chia sẻ.

### Trường hợp trùng lỗi hoặc bị che khuất

Nếu test luôn tạo một instance mới cho mỗi lần checkout, lỗi tích lũy của `subtotalVnd` có thể không xuất hiện. Nếu ứng dụng dùng một service singleton, cùng code sẽ gặp rủi ro khi xử lý nhiều request. Vì vậy, độ an toàn không chỉ phụ thuộc thuật toán mà còn phụ thuộc **vòng đời đối tượng**.

Không cần suy rằng mọi service luôn là singleton. Điều cần xác minh là instance được tạo ở đâu, được chia sẻ như thế nào và các field mutable có bị nhiều luồng truy cập không.

## 4. Trạng thái ẩn tạo ra “phụ thuộc thời gian”

Một dấu hiệu thường gọi là *temporal coupling*: hành vi chỉ đúng nếu các phương thức được gọi theo **thứ tự ngầm**.

```java
final class PriceSession {
    private long subtotalVnd;
    private boolean initialized;

    void begin() {
        subtotalVnd = 0L;
        initialized = true;
    }

    void add(long amountVnd) {
        if (!initialized) {
            throw new IllegalStateException("Call begin first");
        }
        subtotalVnd = Math.addExact(subtotalVnd, amountVnd);
    }

    long finish() {
        if (!initialized) {
            throw new IllegalStateException("Call begin first");
        }
        return subtotalVnd;
    }
}
```

API này buộc người gọi nhớ `begin → add → finish`. Với một đối tượng tích lũy nhiều bước thật sự cần thiết, chu trình đó có thể có cơ sở. Nhưng nếu bài toán chỉ là cộng một danh sách đã có sẵn, nó tạo ra trạng thái và chuỗi lời gọi không cần thiết.

Một hợp đồng gọn hơn:

```java
long sumAmounts(List<Long> amounts) {
    long total = 0L;
    for (long amount : amounts) {
        total = Math.addExact(total, amount);
    }
    return total;
}
```

`sumAmounts` phụ thuộc vào tham số, không phụ thuộc `begin()` từng được gọi hay chưa. Nó cũng tránh việc người gọi quên reset bộ tích lũy.

**Không phải mọi workflow nên biến thành một hàm một bước.** Với quy trình thanh toán gồm nhiều giai đoạn bất đồng bộ, trạng thái có thể là yêu cầu nghiệp vụ. Khi đó nên làm rõ các trạng thái và chuyển trạng thái hợp lệ thay vì giấu chúng sau cờ `initialized` hoặc các lời gọi không có hợp đồng.

## 5. Bước refactor đầu tiên: đưa dữ liệu một lời gọi về biến cục bộ

Với `StatefulCheckoutService`, thay đổi ít rủi ro đầu tiên là **không giữ request và tổng tạm tính trên instance**:

```java
Receipt checkout(CheckoutRequest request) {
    Objects.requireNonNull(request, "request");

    long subtotalVnd = 0L;
    for (OrderLine line : request.lines()) {
        long lineTotal = Math.multiplyExact(
                line.unitPriceVnd(), line.quantity());
        subtotalVnd = Math.addExact(subtotalVnd, lineTotal);
    }

    long feeVnd = subtotalVnd >= 500_000L ? 0L : 25_000L;
    long totalVnd = Math.addExact(subtotalVnd, feeVnd);

    Receipt receipt = new Receipt(
            UUID.randomUUID().toString(),
            request.customerId(),
            subtotalVnd, feeVnd, totalVnd, Instant.now()
    );

    store.save(receipt);
    return receipt;
}
```

Đoạn mã là **phần phương thức minh họa sau bước refactor**, dùng lại các khai báo trước đó. Nó chưa giải quyết vấn đề đồng hồ/ID ngầm, nhưng đã loại bỏ dữ liệu của request khỏi field.

Lợi ích cụ thể:

- Checkout mới luôn bắt đầu cộng từ 0.
- Hai lời gọi không ghi đè `currentRequest` của nhau.
- Không còn `lastReceipt` dư thừa.
- Giá trị trung gian chỉ sống trong khoảng thời gian cần thiết.

**Đây không nhất thiết là refactor thuần bảo toàn hành vi**: bản cũ vốn có lỗi khi sử dụng lại instance. Bước sửa này chủ động thay hành vi lỗi thành hành vi theo yêu cầu. Phải ghi rõ trong pull request, thêm test hồi quy và không che giấu dưới nhãn “chỉ dọn code”.

### Vì sao không chuyển tất cả thành static?

Phương thức `static` không tự bảo đảm không có trạng thái. Một hàm static vẫn có thể đọc `static mutable Map`, `System.getenv` hoặc gọi database toàn cục. Điều quan trọng là **trạng thái nào được đọc/ghi**, không phải có từ khóa `static` hay không.

## 6. Loại bỏ trạng thái suy ra bị lưu trùng

Giả sử một đối tượng giỏ hàng cho phép sửa từng giá trị:

```java
class MutableLine {
    long unitPriceVnd;
    int quantity;
    long lineTotalVnd;
}
```

Người gọi có thể cập nhật `quantity` nhưng quên tính lại `lineTotalVnd`. Đối tượng lúc đó chứa hai nguồn thông tin mâu thuẫn.

Nếu kết quả dễ tính và không có yêu cầu tối ưu đặc biệt, có thể giữ **nguồn sự thật tối thiểu**:

```java
record LinePrice(long unitPriceVnd, int quantity) {
    LinePrice {
        if (unitPriceVnd < 0 || quantity <= 0) {
            throw new IllegalArgumentException("Invalid line");
        }
    }

    long totalVnd() {
        return Math.multiplyExact(unitPriceVnd, quantity);
    }
}
```

Với `LinePrice`, tổng luôn được tính từ giá và số lượng trong object. Không có setter nào có thể làm tổng tiền lệch với các thành phần.

### Khi lưu giá trị suy ra vẫn có lý do

Có trường hợp `totalVnd` cần được lưu như **ảnh chụp giao dịch** vì đơn giá, thuế hoặc tỷ giá có thể thay đổi sau khi khách thanh toán. Trong trường hợp ấy, tổng tiền là dữ liệu lịch sử có ý nghĩa nghiệp vụ, không đơn thuần là cache của thông tin hiện tại.

Tương tự, một số phép tính quá tốn tài nguyên có thể được memoize. Nhưng phải xác định:

- Nguồn dữ liệu nào là chuẩn?
- Khi nguồn thay đổi, giá trị suy ra bị vô hiệu hóa thế nào?
- Giá trị có cần bền vững qua các phiên bản chính sách không?
- Ai chịu trách nhiệm bảo vệ nhất quán và concurrency?

**Đừng xóa trạng thái quan trọng chỉ vì nó được tính từ giá trị khác ở một thời điểm.** Bối cảnh thời gian và lịch sử nghiệp vụ có thể làm nó trở thành nguồn dữ liệu cần lưu.

## 7. Làm rõ phụ thuộc: nhìn qua chữ ký, constructor và ranh giới

Một phụ thuộc là thứ mà thành phần cần để thực hiện hành vi: dữ liệu, chính sách, đồng hồ, random, kết nối, dịch vụ ngoài hoặc bộ lưu trữ.

Phụ thuộc **ẩn** là những thứ code lấy trực tiếp mà người dùng API khó thay thế hoặc kiểm soát:

```java
Receipt createReceipt(CheckoutRequest request) {
    String region = System.getenv("DEFAULT_REGION");
    Instant now = Instant.now();
    String id = UUID.randomUUID().toString();
    // Lựa chọn tính giá còn phụ thuộc cấu hình/hạ tầng ngầm...
}
```

Ở đây, `region`, `now` và `id` không xuất hiện trong chữ ký. Test muốn kiểm tra hết hạn hoặc kết quả theo vùng phải điều khiển môi trường bên ngoài hàm.

Có hai hướng làm rõ, tùy thời gian sống của phụ thuộc:

- **Tham số phương thức:** giá trị thực sự khác theo mỗi lần xử lý, như vùng giao hàng hoặc thời điểm do caller truyền.
- **Phụ thuộc ở constructor:** một dịch vụ có vòng đời rõ, như repository, policy cấu hình, đồng hồ hoặc nguồn tạo ID.

Không phải cứ có tham số là tốt hơn. Truyền mười lăm giá trị cấu hình qua mọi phương thức có thể gây rối. Mục tiêu là làm rõ **ai sở hữu và ai chọn** từng giá trị.

### Phụ thuộc được khai báo không cần framework DI

```java
import java.time.Clock;
import java.util.Objects;

final class ReportService {
    private final Clock clock;

    ReportService(Clock clock) {
        this.clock = Objects.requireNonNull(clock);
    }

    boolean isExpired(Instant deadline) {
        return !clock.instant().isBefore(deadline);
    }
}
```

Ở đây `Clock` được chọn từ bên ngoài. Trong sản xuất dùng `Clock.systemUTC()`; trong test có thể dùng `Clock.fixed(...)`. Không cần thêm container dependency injection để nhận được lợi ích.

Đừng biến mọi phép tính đơn giản thành interface. Một `PricingPolicy` có quy tắc chung được gọi trực tiếp và không có phụ thuộc bên ngoài có thể là lớp cụ thể dễ hiểu hơn một hệ thống factory/registry chỉ phục vụ mock.

## 8. Tách tính toán thuần túy khỏi I/O

Một hướng tổ chức hữu ích là **lõi quyết định thuần túy (*functional core*)** và **lớp điều phối tác dụng phụ (*imperative shell*)**:

```text
CheckoutRequest
      |
      v
Tính giá thuần túy --------------> CheckoutTotals
      |                                  |
      +----------------------------------+
                                         v
                            CheckoutService điều phối
                              |          |         |
                              v          v         v
                          ID source    Clock    ReceiptStore
                                         |
                                         v
                                   Receipt trả về
```

Ý tưởng:

1. Phép tính tiền nên dựa trên dữ liệu đầu vào và hằng/chính sách rõ.
2. Điều phối tạo ID, thời điểm và ghi dữ liệu nên làm việc qua các phụ thuộc có hợp đồng.
3. Giá trị trả về cần chứa dữ liệu mà người gọi thực sự cần.

Một lõi tính giá Java 17:

```java
record CheckoutTotals(
        long subtotalVnd,
        long shippingFeeVnd,
        long totalVnd
) {}

final class CheckoutPricing {
    private static final long FREE_SHIPPING_THRESHOLD_VND = 500_000L;
    private static final long STANDARD_SHIPPING_FEE_VND = 25_000L;

    CheckoutTotals calculate(CheckoutRequest request) {
        Objects.requireNonNull(request, "request");

        long subtotal = 0L;
        for (OrderLine line : request.lines()) {
            long lineTotal = Math.multiplyExact(
                    line.unitPriceVnd(), line.quantity());
            subtotal = Math.addExact(subtotal, lineTotal);
        }

        long shipping = subtotal >= FREE_SHIPPING_THRESHOLD_VND
                ? 0L
                : STANDARD_SHIPPING_FEE_VND;
        long total = Math.addExact(subtotal, shipping);

        return new CheckoutTotals(subtotal, shipping, total);
    }
}
```

`CheckoutPricing` không biết JDBC, HTTP, thời điểm hệ thống hay người gọi trước đó. Với cùng `CheckoutRequest`, nó cho cùng `CheckoutTotals` hoặc cùng điều kiện lỗi liên quan số học.

Lợi ích không nhất thiết là “ít dòng code”. Phép tính giá bây giờ có thể đọc, kiểm thử và thay đổi mà không khởi động hạ tầng lưu đơn.

### Tránh tách lớp chỉ để làm đẹp sơ đồ

Nếu chỉ có một phép cộng nhỏ, tách sang năm interface có thể làm khó theo dõi hơn. Tách lõi tính giá ở ví dụ có cơ sở vì nó gom **quy tắc tiền** và có thể thay đổi độc lập với **lưu biên nhận**. Đó là ranh giới theo trách nhiệm, không phải theo số dòng.

## 9. Làm rõ đồng hồ, nguồn ID và kho lưu trữ

Các phụ thuộc thay đổi theo môi trường sẽ được khai báo:

```java
@FunctionalInterface
interface ReceiptIdSource {
    String nextId();
}
```

Lớp điều phối:

```java
import java.time.Clock;
import java.util.Objects;

final class CheckoutService {
    private final CheckoutPricing pricing;
    private final ReceiptStore store;
    private final Clock clock;
    private final ReceiptIdSource ids;

    CheckoutService(
            CheckoutPricing pricing,
            ReceiptStore store,
            Clock clock,
            ReceiptIdSource ids
    ) {
        this.pricing = Objects.requireNonNull(pricing, "pricing");
        this.store = Objects.requireNonNull(store, "store");
        this.clock = Objects.requireNonNull(clock, "clock");
        this.ids = Objects.requireNonNull(ids, "ids");
    }

    Receipt checkout(CheckoutRequest request) {
        CheckoutTotals totals = pricing.calculate(request);

        String id = Objects.requireNonNull(ids.nextId(), "receipt ID");
        if (id.isBlank()) {
            throw new IllegalStateException("Receipt ID must not be blank");
        }

        Receipt receipt = new Receipt(
                id,
                request.customerId(),
                totals.subtotalVnd(),
                totals.shippingFeeVnd(),
                totals.totalVnd(),
                clock.instant()
        );

        store.save(receipt);
        return receipt;
    }
}
```

**Đọc từ chữ ký:** lớp này phụ thuộc vào `CheckoutPricing`, `ReceiptStore`, `Clock` và `ReceiptIdSource`. Người tạo service có trách nhiệm chọn triển khai. Ví dụ wiring ở ranh giới ứng dụng:

```java
CheckoutService checkoutService = new CheckoutService(
        new CheckoutPricing(),
        receiptStore, // Adapter lưu dữ liệu do ứng dụng cung cấp.
        Clock.systemUTC(),
        () -> UUID.randomUUID().toString()
);
```

Đoạn wiring dùng lại các loại đã khai báo và giả định `receiptStore` là adapter thật được khởi tạo trước; cần `import java.util.UUID;`. Nó minh họa **nơi chọn dependency**, không phải mã ứng dụng hoàn chỉnh.

Kết quả:

- Test có thể tạo clock cố định và nguồn ID cố định.
- `CheckoutService` không giữ dữ liệu checkout của request trước.
- Phần tính tiền có test riêng mà không cần repository.
- Lời gọi lưu vẫn là tác dụng phụ rõ, tại một vị trí dễ đọc.

### Phân biệt lỗi cấu hình với trạng thái nghiệp vụ

Một nguồn ID trả `null` hoặc chuỗi rỗng vi phạm hợp đồng nguồn ID và bị từ chối trước khi lưu. Một repository không lưu được thì phải báo lỗi theo hợp đồng; không nên chuyển lỗi thành biên nhận thành công hoặc phí 0.

Việc khai báo phụ thuộc rõ làm test dễ kiểm soát, nhưng **không tự sửa chính sách lỗi hoặc đảm bảo đã lưu đúng**. Những điều đó phải được thiết kế và kiểm thử ở tầng phù hợp.

## 10. Trước–sau: thay đổi chính xác điều gì?

| Góc nhìn | Trước | Sau |
| --- | --- | --- |
| Dữ liệu request | `currentRequest` là field mutable | `request` chỉ là tham số |
| Giá trị cộng dồn | `subtotalVnd` giữ qua các lần gọi | `subtotal` là biến cục bộ |
| Biên nhận gần nhất | `lastReceipt` giữ bản sao không có yêu cầu | Không lưu trong service; trả trực tiếp |
| Chính sách giá | Trộn cùng điều phối và lưu | `CheckoutPricing` xử lý riêng |
| Thời gian | `Instant.now()` ẩn trong hàm | `Clock` là dependency |
| ID | `UUID.randomUUID()` ẩn trong hàm | `ReceiptIdSource` là dependency |
| Lưu trữ | Phụ thuộc đã khai báo qua `ReceiptStore` | Giữ hợp đồng lưu trữ, dễ dùng fake |
| Test tính giá | Phải đi qua checkout và I/O fake | Gọi `pricing.calculate(request)` trực tiếp |
| Tính độc lập request | Phụ thuộc instance đã từng xử lý gì | Không lưu state biến động theo request |

Điểm cần phân biệt: **phụ thuộc** và **trạng thái** liên quan nhưng không giống nhau. `ReceiptStore` là dependency được giữ ở field, nhưng không phải “trạng thái checkout trước” cần loại bỏ. `Clock` cũng là dependency ổn định theo vòng đời service, mặc dù giá trị thời gian nó cung cấp thay đổi.

Do đó, giảm trạng thái không nhất thiết giảm số field xuống 0. Nó là việc **giữ đúng loại field và đúng vòng đời**.

## 11. Kiểm thử độc lập, lặp lại và không rò rỉ trạng thái

Các test dưới đây dùng JUnit 5 và các kiểu đã khai báo. Chúng giúp mô tả lợi ích có thể quan sát từ việc refactor.

### Test phần tính giá thuần túy

```java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;
import java.util.List;

class CheckoutPricingTest {
    private final CheckoutPricing pricing = new CheckoutPricing();

    @Test
    void computesExactBoundary() {
        CheckoutRequest below = new CheckoutRequest(
                "C-1", List.of(new OrderLine("A", 1, 499_999L)));
        CheckoutRequest exact = new CheckoutRequest(
                "C-1", List.of(new OrderLine("A", 1, 500_000L)));

        assertEquals(25_000L,
                pricing.calculate(below).shippingFeeVnd());
        assertEquals(0L,
                pricing.calculate(exact).shippingFeeVnd());
    }

    @Test
    void sameInputProducesSameResultOnRepeatedCalls() {
        CheckoutRequest request = new CheckoutRequest(
                "C-1", List.of(new OrderLine("A", 2, 100_000L)));

        CheckoutTotals first = pricing.calculate(request);
        CheckoutTotals second = pricing.calculate(request);

        assertEquals(first, second);
        assertEquals(225_000L, second.totalVnd());
    }

    @Test
    void overflowIsRejected() {
        CheckoutRequest request = new CheckoutRequest(
                "C-1", List.of(
                        new OrderLine("A", 2, Long.MAX_VALUE)));

        assertThrows(ArithmeticException.class,
                () -> pricing.calculate(request));
    }
}
```

Các test này kiểm tra ranh giới phí, hành vi lặp lại và tràn số. Chúng không cần database, UUID ngẫu nhiên hoặc đồng hồ thật.

### Test lớp điều phối với phụ thuộc được kiểm soát

```java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.List;

class CheckoutServiceTest {
    private static final Instant FIXED_TIME =
            Instant.parse("2026-11-16T08:00:00Z");

    @Test
    void twoRequestsDoNotShareSubtotal() {
        List<Receipt> stored = new ArrayList<>();
        CheckoutService service = new CheckoutService(
                new CheckoutPricing(),
                stored::add,
                Clock.fixed(FIXED_TIME, ZoneOffset.UTC),
                () -> "receipt-1"
        );

        Receipt first = service.checkout(new CheckoutRequest(
                "C-1", List.of(new OrderLine("A", 1, 100_000L))));
        Receipt second = service.checkout(new CheckoutRequest(
                "C-2", List.of(new OrderLine("B", 1, 200_000L))));

        assertEquals(100_000L, first.subtotalVnd());
        assertEquals(200_000L, second.subtotalVnd());
        assertEquals("C-2", second.customerId());
        assertEquals(FIXED_TIME, second.createdAt());
        assertEquals(List.of(first, second), stored);
    }

    @Test
    void invalidCalculationDoesNotPersist() {
        List<Receipt> stored = new ArrayList<>();
        CheckoutService service = new CheckoutService(
                new CheckoutPricing(),
                stored::add,
                Clock.fixed(FIXED_TIME, ZoneOffset.UTC),
                () -> "receipt-2"
        );

        CheckoutRequest request = new CheckoutRequest(
                "C-1",
                List.of(new OrderLine("A", 2, Long.MAX_VALUE)));

        assertThrows(ArithmeticException.class,
                () -> service.checkout(request));
        assertTrue(stored.isEmpty());
    }

    @Test
    void storageFailureIsNotReportedAsSuccess() {
        ReceiptStore failingStore = receipt -> {
            throw new IllegalStateException("Storage unavailable");
        };
        CheckoutService service = new CheckoutService(
                new CheckoutPricing(),
                failingStore,
                Clock.fixed(FIXED_TIME, ZoneOffset.UTC),
                () -> "receipt-3"
        );

        assertThrows(IllegalStateException.class,
                () -> service.checkout(new CheckoutRequest(
                        "C-1",
                        List.of(new OrderLine("A", 1, 100_000L)))));
    }
}
```

`stored::add` là một fake rất nhỏ ghi nhận biên nhận mà service yêu cầu lưu. Những test này kiểm tra luồng ứng dụng **trong một tiến trình**. Việc fake lưu hai biên nhận có cùng ID cố định không chứng minh database thật cho phép ID trùng; test chỉ tập trung vào tính độc lập của hai phép tính. Trong sản xuất, nguồn ID và ràng buộc duy nhất cần được kiểm tra riêng.

Test thứ ba xác nhận ngoại lệ lưu không bị biến thành kết quả thành công. Nó không chứng minh transaction thật rollback đúng hay không có side effect nào đã xảy ra trước lúc exception.

## 12. Không phải mọi trạng thái shared đều có thể loại bỏ bằng local variable

Giả sử hai request cùng đặt mặt hàng cuối cùng trong kho. Mỗi request có thể tính toán cục bộ đúng, nhưng cùng đọc `available = 1` rồi cùng ghi `available = 0`. Kết quả có thể là **đã bán hai sản phẩm trong khi chỉ còn một**.

```text
Request A             Request B
---------             ---------
Đọc tồn kho = 1       Đọc tồn kho = 1
Quyết định bán        Quyết định bán
Ghi tồn kho = 0       Ghi tồn kho = 0
Trả thành công        Trả thành công
```

Bất biến tồn kho không thể bảo đảm chỉ bằng cách biến một service thành stateless. Trạng thái ở **database dùng chung** cần được bảo vệ bằng một thao tác cập nhật nguyên tử hoặc cơ chế transaction/locking phù hợp.

Ví dụ SQL minh họa một cập nhật có điều kiện:

```sql
UPDATE inventory
SET available = available - :quantity
WHERE product_id = :product_id
  AND available >= :quantity;
```

Phải kiểm tra số hàng được cập nhật để biết yêu cầu trừ kho có thành công không. Ký hiệu `:quantity` và `:product_id` là placeholders minh họa của framework, không phải cú pháp bind thống nhất của mọi JDBC driver.

Đây là điểm mấu chốt: **stateless application service không đồng nghĩa stateless business**. Trạng thái nghiệp vụ vẫn tồn tại, nhưng được đặt ở nơi có thể bảo vệ tính nhất quán và kiểm soát cạnh tranh.

### Tách tính toán và thay đổi trạng thái đúng cách

Có thể dùng một hàm thuần túy để kiểm tra quy tắc “sau khi trừ không được âm”, nhưng quyết định và cập nhật dùng dữ liệu chia sẻ cần thực thi trong ranh giới concurrency đúng. Không nên tách thao tác đọc/kiểm tra/ghi thành những request mạng độc lập mà không có cơ chế giữ bất biến.

## 13. Cache: trạng thái có ích nhưng phải có chính sách

Cache là trường hợp không nên xóa chỉ vì nó mutable. Nó có thể giảm độ trễ và tải database. Tuy nhiên, cache thiếu giới hạn hoặc quy tắc hết hạn tạo thêm trạng thái khó hiểu.

Ví dụ đáng nghi:

```java
final class PriceCache {
    static final Map<String, Long> PRICES = new HashMap<>();
}
```

Trong ví dụ này, cần `import java.util.Map;` và `import java.util.HashMap;`. Dạng cache toàn cục mutable đặt ra nhiều câu hỏi:

- Giá lưu theo tiền tệ và phiên bản chính sách nào?
- Khi giá đổi, cache được xóa thế nào?
- Nhiều luồng đọc/ghi đồng thời có an toàn không?
- Có giới hạn số phần tử hoặc thời gian sống không?
- Test sau có bị ảnh hưởng bởi dữ liệu của test trước không?
- Nếu nhiều instance ứng dụng có cache riêng, điều gì giữ kết quả nhất quán?

Một cache tốt thường có **chủ sở hữu**, **khóa và đơn vị rõ**, **TTL/eviction**, **giới hạn bộ nhớ**, **đồng bộ hóa thích hợp** và **định nghĩa độ mới dữ liệu chấp nhận được**.

Chuyển từ `static Map` sang một trường `private final Map` trong service **chưa đủ** nếu map vẫn được chia sẻ không an toàn hoặc có vòng đời quá dài. Trọng tâm là ranh giới sở hữu, không chỉ cú pháp khai báo.

## 14. Trạng thái thực cần một vòng đời và bất biến rõ ràng

Có những đối tượng sinh ra để giữ trạng thái: giỏ hàng đang chỉnh sửa, session đăng nhập, một quá trình phê duyệt hoặc đơn hàng theo trạng thái xử lý.

Khi đó, thay vì loại bỏ state, hãy **mô hình hóa nó**:

```java
enum ApprovalStatus {
    PENDING,
    APPROVED,
    REJECTED
}

record Approval(ApprovalStatus status) {
    Approval {
        Objects.requireNonNull(status, "status");
    }

    Approval approve() {
        if (status != ApprovalStatus.PENDING) {
            throw new IllegalStateException("Approval is not pending");
        }
        return new Approval(ApprovalStatus.APPROVED);
    }
}
```

Đối tượng chỉ giữ **trạng thái nghiệp vụ thực**. Phương thức `approve` tạo giá trị mới và từ chối chuyển trạng thái không hợp lệ. Với mô hình lớn hơn, cần kiểm tra liên trạng thái, quyền và tính nhất quán khi nhiều actor cùng cập nhật.

Nếu ứng dụng lưu `Approval` vào database, việc hai phiên xử lý cùng tạo kết quả mới vẫn cần transaction hoặc optimistic locking. Bất biến trong một record không bảo đảm cập nhật từ nhiều tiến trình được tuần tự hóa.

### Immutable không có nghĩa “không có trạng thái”

Một record `Approval(APPROVED)` vẫn **mang trạng thái**, chỉ là giá trị đó không bị sửa tại chỗ. Immutability giúp giảm số thời điểm đối tượng có thể bị thay đổi bất ngờ, nhưng không biến một workflow có trạng thái thành workflow vô trạng thái.

## 15. Làm rõ nguồn dữ liệu và cấu hình

Phụ thuộc ẩn không chỉ là database hoặc đồng hồ. Ví dụ, một chính sách miễn phí giao hàng đọc cấu hình toàn cục trong lúc tính:

```java
long shippingFee(long subtotalVnd) {
    long threshold = Long.parseLong(
            System.getenv("FREE_SHIPPING_THRESHOLD_VND"));
    return subtotalVnd >= threshold ? 0L : 25_000L;
}
```

Hàm này có đầu vào ngầm từ môi trường. Nếu biến môi trường thiếu hoặc không parse được, hàm có thể ném lỗi khi đang phục vụ request. Việc kiểm tra quy tắc trên nhiều ngưỡng cũng cần sửa môi trường hoặc thao tác phức tạp.

Một policy nhận cấu hình đã xác thực:

```java
record ShippingPolicy(long freeThresholdVnd, long standardFeeVnd) {
    ShippingPolicy {
        if (freeThresholdVnd < 0 || standardFeeVnd < 0) {
            throw new IllegalArgumentException("Negative shipping policy");
        }
    }

    long feeFor(long subtotalVnd) {
        if (subtotalVnd < 0) {
            throw new IllegalArgumentException("Negative subtotal");
        }
        return subtotalVnd >= freeThresholdVnd ? 0L : standardFeeVnd;
    }
}
```

Bây giờ test có thể tạo `new ShippingPolicy(500_000L, 25_000L)` mà không phụ thuộc vào `System.getenv`. Cấu hình được đọc, parse và validate tại ranh giới khởi động hoặc cơ chế cấu hình phù hợp.

**Lưu ý:** nếu cấu hình được phép thay đổi động trong lúc hệ thống chạy, truyền một giá trị cố định vào constructor có thể làm mất tính năng đó. Khi cần cập nhật runtime, hãy dùng một nguồn cấu hình có hợp đồng rõ về tính nhất quán, phiên bản và phạm vi áp dụng. Refactor phải giữ yêu cầu thực, không ép mọi giá trị thành hằng bất biến.

## 16. Null, Optional và dữ liệu thiếu có thể là trạng thái ẩn

Một field nullable thường che giấu nhiều trạng thái:

```java
class ReportRunner {
    private Report currentReport; // null nghĩa là gì?
}
```

`currentReport == null` có thể nghĩa là chưa chạy, đã chạy nhưng không có dữ liệu, đã hủy hoặc gặp lỗi. Nếu logic nhiều nơi tự suy đoán, người đọc phải nhớ quy ước không được thể hiện ở kiểu.

Có thể dùng:

- **Biến cục bộ:** nếu report chỉ cần trong một lời gọi.
- **`Optional<Report>` ở kết quả tra cứu:** nếu kết quả có hoặc không có report là tình huống hợp lệ.
- **`enum` hoặc sealed result:** nếu cần phân biệt `NOT_STARTED`, `RUNNING`, `SUCCEEDED`, `FAILED`.
- **Trạng thái bền vững trong database:** nếu job cần tiếp tục sau khi process khởi động lại.

Giảm trạng thái không có nghĩa thay mọi `null` bằng `Optional`; bản thân `Optional` có thể bị truyền `null`, và một `Optional.empty()` vẫn không diễn đạt được nhiều nguyên nhân khác nhau. Chọn kiểu phù hợp với **số trạng thái có ý nghĩa thật**.

## 17. Lộ trình refactor an toàn cho một service có trạng thái

Có thể làm theo các bước sau mà không cần viết lại toàn bộ hệ thống:

### Bước 1 — Viết hợp đồng hiện tại và hành vi mong muốn

Liệt kê đầu vào, đầu ra, exception, side effect và thứ tự. Với checkout, ghi rõ phí ở ngưỡng 500.000 VND, phát hiện overflow, ghi biên nhận trước khi trả thành công.

Nếu mã cũ có lỗi cộng dồn, phải **ghi nhận đây là bugfix** chứ không khẳng định mọi hành vi đang được bảo toàn.

### Bước 2 — Lập bảng field và nguồn phụ thuộc

| Field/lời gọi | Ai đọc/ghi? | Có cần sống qua nhiều lần gọi? | Hành động |
| --- | --- | --- | --- |
| `currentRequest` | `checkout` | Không | Chuyển thành tham số |
| `subtotalVnd` | `checkout` | Không | Chuyển thành biến cục bộ |
| `lastReceipt` | `checkout` | Không, theo yêu cầu đang xét | Xóa; trả giá trị |
| `store` | `checkout` | Có, dependency | Giữ, khai báo qua constructor |
| `Instant.now()` | `checkout` | Nguồn thời gian | Tiêm `Clock` |
| `UUID.randomUUID()` | `checkout` | Nguồn ID | Tiêm `ReceiptIdSource` nếu cần kiểm soát |
| `inventory.available` | Nhiều request | Có, trạng thái miền dùng chung | Giữ trong kho có transaction |
| Cache giá | Nhiều request | Có thể | Làm rõ lifecycle, TTL và concurrency |

Không thực hiện “xóa tất cả field” vì như vậy có thể phá những dependency hợp lý hoặc trạng thái miền quan trọng.

### Bước 3 — Viết test đặc tả và test phát hiện rò rỉ

Chạy hai request trên **cùng instance** để phát hiện dữ liệu lần trước ảnh hưởng lần sau. Dùng test giá trị biên, overflow và lỗi lưu. Cẩn thận phân biệt test đang chốt hành vi đúng với test chỉ ghi lại hành vi lỗi cũ.

### Bước 4 — Thu nhỏ phạm vi của dữ liệu

Chuyển các field tạm thành biến cục bộ; đặt các phép tính không cần I/O vào hàm/lớp với đầu vào, đầu ra rõ. Đọc lại code để thấy request nào sở hữu dữ liệu nào.

### Bước 5 — Làm lộ các phụ thuộc biến động

Đưa đồng hồ, nguồn ID và adapter ngoài vào constructor hoặc ranh giới khởi tạo. Không cần tạo interface cho từng lớp thuần túy; chỉ thêm abstraction nếu nó có ý nghĩa về biến thể, tích hợp hoặc kiểm thử.

### Bước 6 — Giữ nguyên ranh giới trạng thái nghiệp vụ

Đừng tách một transaction thành nhiều bước độc lập chỉ để các class trở nên “stateless”. Kiểm tra quyền, tính nguyên tử và thứ tự tác dụng phụ trước khi di chuyển lời gọi.

### Bước 7 — Đọc lại như người bảo trì

Hỏi: một lần checkout có cần biết lần trước diễn ra thế nào không? Có thể hiểu chính sách giá từ một nơi rõ ràng không? Có thể giả lập lỗi lưu và thời gian trong test không? Các lớp mới có tạo thêm đường đi không cần thiết không?

### Bước 8 — Kiểm thử ở đúng tầng và theo dõi sau rollout

Unit test bảo vệ tính toán và điều phối. Integration test bảo vệ JDBC, transaction, constraint, concurrency và adapter. Nếu thay đổi ảnh hưởng sản phẩm, theo dõi lỗi, latency và kết quả nghiệp vụ sau triển khai.

## 18. Những cách refactor dễ gây tác dụng ngược

**Chỉ reset field ở đầu phương thức.** Có thể chữa lỗi tuần tự nhưng chưa an toàn khi nhiều luồng cùng dùng một instance.

**Đưa mọi biến cục bộ thành field để “đỡ truyền tham số”.** Làm tăng trạng thái chia sẻ, rò dữ liệu giữa request và temporal coupling.

**Đưa tất cả dữ liệu vào một `Context` mutable khổng lồ.** Người đọc không còn biết trường nào thực sự cần cho từng bước; thay đổi nhỏ ảnh hưởng diện rộng.

**Tạo interface cho mọi lớp.** Một phép tính không phụ thuộc hạ tầng có thể dễ test mà không cần interface, factory và registry.

**Cho rằng `final` tự làm object immutable.** Một field `final List` chỉ ngăn gán lại tham chiếu, không ngăn thay đổi danh sách nếu nó mutable.

**Cho rằng `record` luôn bất biến sâu.** Record có thể chứa list/map hoặc object mutable; cần defensive copy và kiểm tra cấu trúc dữ liệu bên trong.

**Biến state nghiệp vụ thành biến local rồi mất dữ liệu qua request.** Đơn hàng đang xử lý hoặc trạng thái phê duyệt cần được lưu với vòng đời và ràng buộc phù hợp.

**Tách đọc–kiểm tra–ghi thành các dịch vụ riêng mà quên transaction.** Làm mất tính nguyên tử và có thể tạo lỗi cạnh tranh.

**Cache mọi kết quả để tránh tính lại.** Cache làm tăng trạng thái cần đồng bộ, thu hồi và kiểm soát độ mới; chỉ dùng khi lợi ích được đo.

**Dùng một biến `static` để chia sẻ ID hoặc cấu hình thử.** Dễ gây test phụ thuộc thứ tự, và có thể ảnh hưởng kết quả dưới concurrency.

**Che lỗi phụ thuộc bằng giá trị mặc định hợp lệ.** Ví dụ lỗi database thành `Optional.empty()`, lỗi phí thành 0 VND: mã trông đơn giản hơn nhưng sai nghĩa.

**Đổi hành vi trong một PR ghi “refactor only”.** Nếu sửa điều kiện biên, error handling hoặc thứ tự side effect, phải ghi rõ thay đổi chức năng và kiểm chứng.

## 19. Bài tập tình huống

### Tình huống A — Bộ tính giá cộng dồn

Một `PriceCalculator` được dùng như singleton, có field `subtotal` và mỗi request gọi `calculate`. Test một lần qua, test hai lần thất bại.

Hãy xác định trạng thái sai phạm vi và viết phiên bản dùng biến cục bộ. Nêu vì sao `subtotal = 0` ở đầu hàm vẫn chưa bảo vệ được hai lời gọi đồng thời.

### Tình huống B — Cấu hình được đọc ở mọi lời gọi

`ShippingService` gọi `System.getenv("REGION")` và `Instant.now()` bên trong `calculate`. Test ở máy khác cho kết quả khác.

Hãy chọn dữ liệu nào nên là tham số, dữ liệu nào nên được truyền qua constructor, và cách dùng `Clock.fixed` để kiểm tra trường hợp trước/đúng/sau một thời hạn.

### Tình huống C — Tồn kho dùng chung

Hai worker cùng đặt sản phẩm cuối cùng. Nhóm muốn làm mọi service stateless bằng cách di chuyển số lượng tồn kho sang tham số.

Giải thích tại sao điều đó chưa bảo vệ bất biến toàn hệ thống. Đề xuất nơi giữ trạng thái, ranh giới transaction/cập nhật có điều kiện và integration test concurrency cần có.

### Tình huống D — Cache giá không hết hạn

Một cache `static Map<String, Long>` làm API nhanh hơn nhưng trả giá cũ sau khi thay đổi bảng giá. Unit test cũng rò dữ liệu giữa các lần chạy.

Hãy lập bảng chủ sở hữu, vòng đời, giới hạn dung lượng, độ mới và cơ chế vô hiệu hóa. Nếu không có bằng chứng hiệu năng, giữ cache có đáng không?

### Tình huống E — Tách mọi lớp thành interface

Một nhóm tạo `IOrderPricing`, `IOrderSubtotal`, `IOrderFee`, `IOrderAdder` và các factory tương ứng chỉ để một phép tính giá 20 dòng “dễ mock”.

Hãy xác định abstraction nào bảo vệ phụ thuộc thực và abstraction nào chỉ thêm gián tiếp. Đề xuất cấu trúc giúp người đọc tìm quy tắc giá trong ít bước hơn.

### Tình huống F — Biên nhận cần lưu lịch sử

Một refactor bỏ field `totalVnd` khỏi bản ghi hóa đơn vì “đây là dữ liệu suy ra từ đơn giá”. Sau đó chính sách thuế và giá thay đổi, làm hóa đơn cũ được tính lại khác trước.

Hãy phân biệt giá trị suy ra tạm thời với **ảnh chụp giao dịch** cần lưu bền vững. Nêu hợp đồng dữ liệu và test lịch sử cần có.

### Tình huống G — Workflow phê duyệt có nhiều trạng thái

Một lớp phê duyệt có các cờ `initialized`, `approved`, `rejected` và `sent`. Một số tổ hợp cờ không hợp lệ, nhưng mã hiện không kiểm tra.

Hãy đề xuất cách mô hình hóa trạng thái và chuyển trạng thái, làm rõ nơi cần lưu trạng thái qua các request và cách kiểm tra cạnh tranh khi nhiều người phê duyệt cùng lúc.

Với mỗi tình huống, trả lời theo trình tự: **trạng thái đang nằm ở đâu → có thật sự cần tồn tại không → ai sở hữu → phụ thuộc nào đang ẩn → thay đổi nhỏ nhất → test xác minh và rủi ro còn lại**.

## 20. Ghi nhớ

**Giảm trạng thái và làm rõ phụ thuộc** là giảm số thông tin ngầm mà người đọc phải ghi nhớ để hiểu một hành vi.

- Đưa dữ liệu dùng trong một lời gọi về **tham số và biến cục bộ** thay vì field có vòng đời dài không cần thiết.
- Tránh lưu các giá trị suy ra như nguồn sự thật thứ hai khi có thể tính lại an toàn.
- Dùng kiểu bất biến và defensive copy để hạn chế thay đổi ngoài ý muốn; hiểu giới hạn của bản sao nông.
- Khai báo dependency như repository, đồng hồ, nguồn ID hoặc chính sách cấu hình ở ranh giới thích hợp.
- Tách phần tính toán thuần túy khỏi I/O khi điều đó làm trách nhiệm và test rõ hơn.
- Không xóa **trạng thái nghiệp vụ thật** hoặc làm mất bất biến, transaction và chính sách concurrent update.
- Test một service qua nhiều lần gọi, dữ liệu biên, lỗi phụ thuộc và side effect; giữ integration test cho các ranh giới thật.
- Không đo hiệu quả refactor bằng số field hoặc interface giảm/tăng đơn thuần: hãy xem người bảo trì có hiểu, kiểm chứng và thay đổi dễ hơn không.

Thiết kế tốt không nhất thiết hoàn toàn vô trạng thái. Nó giữ **đúng trạng thái ở đúng chủ sở hữu**, để **đầu vào và phụ thuộc quan trọng hiện rõ** và để mỗi thay đổi có thể được kiểm tra mà không cần dựa vào lịch sử ngầm của hệ thống.
