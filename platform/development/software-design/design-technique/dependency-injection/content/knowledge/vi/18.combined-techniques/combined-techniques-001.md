# DI với Strategy để thay thuật toán hoặc chính sách

## 1. Hai kỹ thuật giải quyết hai câu hỏi khác nhau

Trong thiết kế phần mềm, **Strategy Pattern** đóng gói những thuật toán hoặc chính sách có thể thay thế phía sau một hợp đồng chung. **Dependency Injection (DI)** cung cấp một đối tượng phụ thuộc từ bên ngoài, thay vì để lớp sử dụng tự tạo và tự chọn nó.

Hai kỹ thuật bổ sung cho nhau:

- **Strategy trả lời:** “Đâu là các cách thực hiện cùng một trách nhiệm, và làm sao thay một cách bằng cách khác mà không sửa lớp sử dụng?”
- **DI trả lời:** “Ai chọn, tạo và cung cấp cách thực hiện đó cho lớp sử dụng?”
- **Composition root trả lời:** “Tại điểm lắp ghép ứng dụng, chính sách nào đang được áp dụng, với cấu hình và vòng đời nào?”

Ví dụ một dịch vụ đặt hàng tính phí vận chuyển. Hợp đồng `ShippingPolicy` có thể có hai hiện thực:

- `FlatFeePolicy`: thu một mức phí cố định cho mọi đơn hợp lệ.
- `FreeFromThresholdPolicy`: miễn phí nếu giá trị đơn đạt ngưỡng, nếu không thu phí cơ bản.

`CheckoutService` chỉ cần **một chính sách có thể tính phí**. Nó không cần biết lớp cụ thể, không đọc biến môi trường để chọn chính sách, và không chứa nhiều nhánh `if` xử lý từng loại phí.

~~~mermaid
flowchart TB
    Root["Composition root / App.main"]
    Flat["FlatFeePolicy"]
    Threshold["FreeFromThresholdPolicy"]
    Checkout["CheckoutService"]
    Contract["ShippingPolicy"]
    Repo["OrderRepository"]
    Root -->|"chọn một policy và tiêm"| Checkout
    Root -->|"tạo nếu được chọn"| Flat
    Root -->|"tạo nếu được chọn"| Threshold
    Root -->|"tạo và tiêm"| Repo
    Checkout -->|"dùng hợp đồng"| Contract
    Checkout -->|"ghi kết quả"| Repo
    Flat -.->|"implements"| Contract
    Threshold -.->|"implements"| Contract
~~~

Trong module **DEPENDENCY_INJECTION**, kỹ thuật kết hợp này cho phép học **constructor injection**, cách tạo **object graph** tại composition root và kiểm thử bằng **Java thuần** trước khi dùng DI container. **Strategy không đòi hỏi framework**, và DI cũng không đòi hỏi mọi lớp phải có một interface. Interface có giá trị ở đây vì thật sự có **nhiều hành vi thay thế được**.

## 2. Khi nào Strategy đáng giá hơn một nhánh điều kiện?

Hãy xem một phiên bản buộc service biết mọi biến thể:

~~~java
// Phác họa cách thiết kế dễ phình to khi chính sách thay đổi.
long fee(long subtotalVnd, String mode) {
    if ("flat".equals(mode)) {
        return 15_000;
    }
    if ("threshold".equals(mode)) {
        return subtotalVnd >= 200_000 ? 0 : 25_000;
    }
    throw new IllegalArgumentException("Chế độ không được hỗ trợ");
}
~~~

Với đúng hai nhánh đơn giản, đặt điều kiện tại một nơi có chủ đích **không nhất thiết sai**. Tuy nhiên, nếu mỗi loại vận chuyển có quy tắc riêng, đội ngũ riêng sở hữu hoặc cần thêm kiểm thử/biến thể độc lập, service sẽ phải thay đổi mỗi khi thêm chính sách mới.

Strategy giúp chuyển các quy tắc sang những thành phần có trách nhiệm riêng:

~~~java
interface ShippingPolicy {
    long feeFor(long subtotalVnd);
}
~~~

Lợi ích thường xuất hiện khi:

1. Các phương án **cùng thực hiện một hành vi** nhưng có logic khác nhau.
2. Thuật toán/chính sách **thay đổi độc lập** với luồng nghiệp vụ sử dụng nó.
3. Cần kiểm thử từng phương án một cách độc lập, đặc biệt ở các giá trị biên.
4. Cần chọn chính sách theo môi trường triển khai, nhóm khách hàng, hợp đồng hoặc cấu hình được xác thực.
5. Các điều kiện bắt đầu tạo ra nhiều nhánh lồng nhau trong một service.

Ngược lại, **đừng tạo Strategy chỉ để thay một `if` ít thay đổi bằng nhiều file và class**. Nếu khác biệt chỉ là hai tham số cấu hình cho cùng thuật toán, một class có constructor rõ ràng có thể đủ.

## 3. Các vai trò trong thiết kế DI + Strategy

| Thành phần | Trách nhiệm | Ví dụ |
| --- | --- | --- |
| **Strategy contract** | Định nghĩa hành vi mà bên sử dụng cần | `ShippingPolicy.feeFor(long)` |
| **Concrete strategies** | Thực hiện các thuật toán/chính sách cụ thể | `FlatFeePolicy`, `FreeFromThresholdPolicy` |
| **Context / consumer** | Thực hiện use case, gọi Strategy qua hợp đồng | `CheckoutService` |
| **Composition root** | Chọn, tạo, cấu hình và tiêm Strategy | `App.main()` |
| **Adapter/port khác** | Xử lý tác dụng phụ riêng biệt với việc tính phí | `OrderRepository` |

**Về hướng phụ thuộc:** `CheckoutService` phụ thuộc vào `ShippingPolicy`, không phụ thuộc vào `FlatFeePolicy` hay `FreeFromThresholdPolicy`. Composition root biết các hiện thực để lắp ghép; đó là nơi hợp lý cho chi tiết lựa chọn.

**Về quyền điều khiển:** `CheckoutService` quyết định *khi nào* cần tính phí trong luồng checkout; Strategy quyết định *tính như thế nào*. Việc chọn implementation được đưa ra ngoài service.

**Về bất biến:** service vẫn phải kiểm tra phụ thuộc bắt buộc không `null`, dữ liệu đầu vào hợp lệ và kết quả tính phí đáp ứng hợp đồng. DI không thay thế việc kiểm tra những điều kiện ấy.

## 4. Ví dụ đầy đủ bằng Java thuần: thay chính sách qua composition root

Ví dụ sau dùng **Java 11 trở lên**, không cần Spring, JUnit hoặc DI container. Toàn bộ lớp nằm trong một file **`ShippingStrategyDemo.java`** để dễ biên dịch.

Chương trình minh họa:

- Hai Strategy có thể thay thế nhau.
- `CheckoutService` nhận Strategy qua constructor.
- `OrderRepository` là một port ghi kết quả, tách khỏi thuật toán tính phí.
- Lựa chọn chính sách theo tham số dòng lệnh nằm ở **composition root**, không nằm trong `CheckoutService`.
- Các giá trị tiền được biểu diễn bằng `long` theo đơn vị VND trong ví dụ; khi cộng dùng `Math.addExact` để không âm thầm tràn số.

~~~java
import java.util.Objects;

public final class ShippingStrategyDemo {

    // 1. Hợp đồng dùng bởi CheckoutService.
    public interface ShippingPolicy {
        long feeFor(long subtotalVnd);
    }

    // 2. Strategy A: phí cố định.
    public static final class FlatFeePolicy implements ShippingPolicy {
        private final long feeVnd;

        public FlatFeePolicy(long feeVnd) {
            if (feeVnd < 0) {
                throw new IllegalArgumentException("feeVnd không được âm");
            }
            this.feeVnd = feeVnd;
        }

        @Override
        public long feeFor(long subtotalVnd) {
            if (subtotalVnd <= 0) {
                throw new IllegalArgumentException("subtotalVnd phải dương");
            }
            return feeVnd;
        }
    }

    // 3. Strategy B: miễn phí nếu đạt ngưỡng.
    public static final class FreeFromThresholdPolicy
            implements ShippingPolicy {
        private final long feeVnd;
        private final long freeFromVnd;

        public FreeFromThresholdPolicy(long feeVnd, long freeFromVnd) {
            if (feeVnd < 0 || freeFromVnd <= 0) {
                throw new IllegalArgumentException(
                        "Cấu hình phí/ngưỡng không hợp lệ");
            }
            this.feeVnd = feeVnd;
            this.freeFromVnd = freeFromVnd;
        }

        @Override
        public long feeFor(long subtotalVnd) {
            if (subtotalVnd <= 0) {
                throw new IllegalArgumentException("subtotalVnd phải dương");
            }
            return subtotalVnd >= freeFromVnd ? 0 : feeVnd;
        }
    }

    // Kết quả nghiệp vụ không phụ thuộc framework.
    public static final class OrderSummary {
        private final String orderId;
        private final long subtotalVnd;
        private final long shippingFeeVnd;
        private final long totalVnd;

        public OrderSummary(
                String orderId, long subtotalVnd,
                long shippingFeeVnd, long totalVnd) {
            this.orderId = Objects.requireNonNull(orderId, "orderId");
            this.subtotalVnd = subtotalVnd;
            this.shippingFeeVnd = shippingFeeVnd;
            this.totalVnd = totalVnd;
        }

        public String orderId() {
            return orderId;
        }

        public long subtotalVnd() {
            return subtotalVnd;
        }

        public long shippingFeeVnd() {
            return shippingFeeVnd;
        }

        public long totalVnd() {
            return totalVnd;
        }
    }

    public interface OrderRepository {
        void save(OrderSummary order);
    }

    // Adapter minh họa, không kết nối database.
    public static final class ConsoleOrderRepository
            implements OrderRepository {
        @Override
        public void save(OrderSummary order) {
            System.out.println(
                    "SAVE " + order.orderId()
                    + ": shipping=" + order.shippingFeeVnd()
                    + ", total=" + order.totalVnd());
        }
    }

    // 4. Context: chỉ phụ thuộc vào hợp đồng, không biết tên Strategy.
    public static final class CheckoutService {
        private final ShippingPolicy shippingPolicy;
        private final OrderRepository orders;

        public CheckoutService(
                ShippingPolicy shippingPolicy, OrderRepository orders) {
            this.shippingPolicy =
                    Objects.requireNonNull(shippingPolicy, "shippingPolicy");
            this.orders = Objects.requireNonNull(orders, "orders");
        }

        public OrderSummary checkout(String orderId, long subtotalVnd) {
            if (orderId == null || !orderId.matches("[A-Z0-9-]+")) {
                throw new IllegalArgumentException("orderId không hợp lệ");
            }
            if (subtotalVnd <= 0) {
                throw new IllegalArgumentException("subtotalVnd phải dương");
            }

            // Service biết khi nào tính phí; Strategy biết cách tính.
            long shippingFeeVnd = shippingPolicy.feeFor(subtotalVnd);

            // Bảo vệ hợp đồng nếu có Strategy lỗi.
            if (shippingFeeVnd < 0) {
                throw new IllegalStateException(
                        "ShippingPolicy không được trả phí âm");
            }

            long totalVnd = Math.addExact(subtotalVnd, shippingFeeVnd);
            OrderSummary summary = new OrderSummary(
                    orderId, subtotalVnd, shippingFeeVnd, totalVnd);
            orders.save(summary);
            return summary;
        }
    }

    // 5. Lựa chọn implementation tại composition root.
    public static ShippingPolicy choosePolicy(String name) {
        if ("flat".equals(name)) {
            return new FlatFeePolicy(15_000);
        }
        if ("threshold".equals(name)) {
            return new FreeFromThresholdPolicy(25_000, 200_000);
        }
        throw new IllegalArgumentException(
                "Policy không hỗ trợ: " + name);
    }

    public static void main(String[] args) {
        String policyName = args.length == 0 ? "threshold" : args[0];

        ShippingPolicy policy = choosePolicy(policyName);
        OrderRepository repository = new ConsoleOrderRepository();
        CheckoutService checkout = new CheckoutService(policy, repository);

        checkout.checkout("ORDER-001", 150_000);
    }
}
~~~

Biên dịch:

~~~bash
javac ShippingStrategyDemo.java
~~~

Chạy theo chính sách mặc định:

~~~bash
java ShippingStrategyDemo threshold
~~~

Kết quả:

~~~text
SAVE ORDER-001: shipping=25000, total=175000
~~~

Đổi chính sách mà **không sửa `CheckoutService`**:

~~~bash
java ShippingStrategyDemo flat
~~~

Kết quả:

~~~text
SAVE ORDER-001: shipping=15000, total=165000
~~~

### Đọc đúng điều đã thay đổi

Khi chọn `threshold`, composition root tạo `FreeFromThresholdPolicy` và tiêm vào `CheckoutService`. Khi chọn `flat`, composition root tạo `FlatFeePolicy` thay thế. `CheckoutService` gọi cùng một phương thức `feeFor(subtotalVnd)`, nên **không chứa nhánh `if` phân biệt hai loại chính sách**.

Sự thay đổi này không cần DI container. Khi mở rộng sang container, phần lựa chọn và khởi tạo có thể được khai báo bằng bean/factory/qualifier; phần nghiệp vụ vẫn giữ nguyên constructor và hành vi.

### Chính sách không phải phép màu với tính đúng đắn nghiệp vụ

Nếu `shippingPolicy.feeFor(...)` trả giá trị âm, service từ chối. Nếu kết quả cộng tràn `long`, `Math.addExact` ném `ArithmeticException` trước khi gọi repository. Nhưng các kiểm tra này chỉ bảo vệ một số bất biến. Trong hệ thống thực, còn phải thống nhất đơn vị tiền, giới hạn số tiền và quy tắc làm tròn theo miền nghiệp vụ; có thể dùng `BigDecimal` hoặc kiểu tiền riêng khi cần.

## 5. Kiểm thử Strategy và Context mà không dùng framework

Bài kiểm thử cần tách hai mức:

1. **Kiểm tra từng Strategy:** giá trị phí với đầu vào thông thường, điều kiện biên, cấu hình không hợp lệ.
2. **Kiểm tra Context:** service gọi Strategy, tính tổng, lưu kết quả; không lưu nếu đầu vào sai, Strategy trả lỗi hoặc xảy ra tràn số.

Không cần mock mọi lớp. Có thể dùng **Strategy thật** vì chúng thuần túy, rẻ và tất định; chỉ cần fake repository để quan sát tác dụng phụ.

Lưu thành **`ShippingStrategyDemoTest.java`** cạnh file chính:

~~~java
public final class ShippingStrategyDemoTest {

    static final class RecordingRepository
            implements ShippingStrategyDemo.OrderRepository {
        int saves;
        ShippingStrategyDemo.OrderSummary last;

        @Override
        public void save(ShippingStrategyDemo.OrderSummary order) {
            saves++;
            last = order;
        }
    }

    static void check(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    static void expect(
            Class<? extends RuntimeException> expected, Runnable action) {
        try {
            action.run();
        } catch (RuntimeException failure) {
            if (expected.isInstance(failure)) {
                return;
            }
            throw new AssertionError(
                    "Sai ngoại lệ: " + failure.getClass(), failure);
        }
        throw new AssertionError("Thiếu ngoại lệ " + expected.getName());
    }

    public static void main(String[] args) {
        ShippingStrategyDemo.ShippingPolicy flat =
                new ShippingStrategyDemo.FlatFeePolicy(15_000);
        ShippingStrategyDemo.ShippingPolicy threshold =
                new ShippingStrategyDemo.FreeFromThresholdPolicy(
                        25_000, 200_000);

        // Strategy hoạt động độc lập với service.
        check(flat.feeFor(150_000) == 15_000, "Sai phí cố định");
        check(threshold.feeFor(150_000) == 25_000,
                "Đơn dưới ngưỡng phải chịu phí");
        check(threshold.feeFor(200_000) == 0,
                "Đơn đúng ngưỡng phải miễn phí");
        check(threshold.feeFor(250_000) == 0,
                "Đơn trên ngưỡng phải miễn phí");

        expect(IllegalArgumentException.class,
                () -> new ShippingStrategyDemo.FlatFeePolicy(-1));
        expect(IllegalArgumentException.class,
                () -> new ShippingStrategyDemo.FreeFromThresholdPolicy(
                        25_000, 0));
        expect(IllegalArgumentException.class,
                () -> flat.feeFor(0));

        // Cùng Context, chỉ thay Strategy được tiêm.
        RecordingRepository flatRepo = new RecordingRepository();
        ShippingStrategyDemo.CheckoutService flatCheckout =
                new ShippingStrategyDemo.CheckoutService(flat, flatRepo);

        ShippingStrategyDemo.OrderSummary flatOrder =
                flatCheckout.checkout("ORDER-001", 150_000);
        check(flatOrder.shippingFeeVnd() == 15_000,
                "Sai phí từ Strategy flat");
        check(flatOrder.totalVnd() == 165_000, "Sai tổng flat");
        check(flatRepo.saves == 1 && flatRepo.last == flatOrder,
                "Phải lưu kết quả flat đúng một lần");

        RecordingRepository thresholdRepo = new RecordingRepository();
        ShippingStrategyDemo.CheckoutService thresholdCheckout =
                new ShippingStrategyDemo.CheckoutService(
                        threshold, thresholdRepo);

        ShippingStrategyDemo.OrderSummary freeOrder =
                thresholdCheckout.checkout("ORDER-002", 200_000);
        check(freeOrder.shippingFeeVnd() == 0, "Sai phí miễn theo ngưỡng");
        check(freeOrder.totalVnd() == 200_000, "Sai tổng theo ngưỡng");
        check(thresholdRepo.saves == 1, "Phải lưu một đơn ngưỡng");

        // Fail fast trước khi lưu dữ liệu.
        expect(IllegalArgumentException.class,
                () -> flatCheckout.checkout("bad id", 150_000));
        expect(IllegalArgumentException.class,
                () -> flatCheckout.checkout("ORDER-003", -1));
        check(flatRepo.saves == 1, "Đầu vào sai không được ghi thêm");

        // Một Strategy vi phạm hợp đồng phải bị phát hiện.
        ShippingStrategyDemo.CheckoutService broken =
                new ShippingStrategyDemo.CheckoutService(
                        subtotal -> -1, flatRepo);
        expect(IllegalStateException.class,
                () -> broken.checkout("ORDER-004", 1_000));
        check(flatRepo.saves == 1, "Phí âm không được ghi");

        // Tổng tiền tràn số phải bị từ chối trước tác dụng phụ.
        expect(ArithmeticException.class,
                () -> flatCheckout.checkout("ORDER-005", Long.MAX_VALUE));
        check(flatRepo.saves == 1, "Tràn số không được ghi");

        expect(NullPointerException.class,
                () -> new ShippingStrategyDemo.CheckoutService(
                        null, flatRepo));

        System.out.println("Tất cả kiểm thử đều đạt.");
    }
}
~~~

Chạy:

~~~bash
javac ShippingStrategyDemo.java ShippingStrategyDemoTest.java
java ShippingStrategyDemoTest
~~~

Các test không cần Spring context, connection thật hoặc mock framework. Khả năng kiểm thử đến từ **hợp đồng có thể tiêm** và việc tách tính toán thuần túy khỏi tác dụng phụ lưu dữ liệu.

## 6. Chọn Strategy lúc startup hay theo từng request?

**Constructor injection một Strategy cố định** là lựa chọn tốt khi chính sách được quyết định lúc khởi động hoặc cho một instance service cụ thể.

Ví dụ: ứng dụng chọn chính sách `threshold` theo cấu hình đã được xác thực rồi xây một `CheckoutService` duy nhất. Mọi lời gọi của service sử dụng cùng chính sách cho đến khi tạo một service mới.

Nhưng có trường hợp **chính sách khác nhau theo từng lời gọi**: kênh bán hàng, chương trình ưu đãi, nhóm hợp đồng hoặc chính sách đã được xác thực của tenant. Khi đó, không nên thay field `shippingPolicy` của một singleton trước mỗi request. Cách đó biến lựa chọn của request thành **shared mutable state**, dễ khiến request A dùng nhầm chính sách của request B.

Một cách là xây sẵn nhiều service theo cấu hình rồi định tuyến tại ranh giới đầu vào:

~~~java
// Ví dụ Java 11; đặt trong CheckoutRouter.java cùng thư mục demo.
import java.util.Map;
import java.util.Objects;

enum ShippingMode {
    STANDARD,
    PROMOTION
}

final class CheckoutRouter {
    private final Map<ShippingMode, ShippingStrategyDemo.CheckoutService>
            services;

    CheckoutRouter(ShippingStrategyDemo.OrderRepository repository) {
        Objects.requireNonNull(repository, "repository");
        this.services = Map.of(
                ShippingMode.STANDARD,
                new ShippingStrategyDemo.CheckoutService(
                        new ShippingStrategyDemo.FlatFeePolicy(15_000),
                        repository),
                ShippingMode.PROMOTION,
                new ShippingStrategyDemo.CheckoutService(
                        new ShippingStrategyDemo.FreeFromThresholdPolicy(
                                25_000, 200_000),
                        repository));
    }

    ShippingStrategyDemo.OrderSummary checkout(
            ShippingMode mode, String orderId, long subtotalVnd) {
        Objects.requireNonNull(mode, "mode");
        ShippingStrategyDemo.CheckoutService service = services.get(mode);
        if (service == null) {
            throw new IllegalArgumentException("Mode không hỗ trợ");
        }
        return service.checkout(orderId, subtotalVnd);
    }
}
~~~

Ở đây, `Map<ShippingMode, CheckoutService>` có nhiệm vụ **định tuyến theo một khóa nghiệp vụ có kiểu**. Nó khác với việc để code nghiệp vụ gọi container tổng quát `getBean(String)` cho bất kỳ phụ thuộc nào.

Một phương án khác là **method injection**: truyền `ShippingPolicy` đã được chọn vào từng lời gọi của service. Lựa chọn này phù hợp khi chính sách thực sự là dữ liệu theo thao tác và phía gọi đã được phép quyết định; đổi lại, API use case phải biểu diễn rõ quyền và trách nhiệm chọn.

**Điểm bảo mật và tính đúng đắn:** Không mặc định tin một chuỗi do người dùng gửi lên để bật chính sách ưu đãi hoặc tính phí thấp hơn. Nếu mode phụ thuộc quyền hạn, hợp đồng hay nhóm khách hàng, hãy chọn nó từ dữ liệu đã xác thực và chính sách miền nghiệp vụ. Strategy là cách thực thi một chính sách, không thay thế bước xác định **ai được phép dùng chính sách nào**.

## 7. Strategy, Factory và Provider nên kết hợp ra sao?

**Strategy** mô tả cách thực hiện thuật toán. **Factory** tạo đối tượng khi được yêu cầu. **Provider** cung cấp một phụ thuộc tại thời điểm sử dụng (có thể tạo mới hoặc trả đối tượng theo scope). **DI** kết nối những vai trò này.

| Nhu cầu | Cách kết hợp | Ví dụ |
| --- | --- | --- |
| Một chính sách bất biến dùng chung | Tạo Strategy ở composition root, constructor-inject vào service | `FreeFromThresholdPolicy` |
| Chọn một trong nhiều chính sách đã tạo sẵn | Tiêm registry/router có kiểu hoặc tạo nhiều service | `CheckoutRouter` theo `ShippingMode` |
| Thông số chính sách chỉ biết lúc thao tác bắt đầu | Tiêm factory chuyên biệt tạo Strategy/config cho thao tác | `policyFactory.forContract(contractId)` |
| Strategy giữ trạng thái mutable riêng của một tác vụ | Factory tạo Strategy mới mỗi tác vụ, quản lý scope | Phiên tính toán với buffer riêng |
| Strategy sử dụng session ngắn hạn nhưng service sống lâu | Tiêm factory/provider đúng scope, không giữ session thật dài hạn | Strategy truy cập tài nguyên theo request |

Không nên dùng `Supplier<ShippingPolicy>` với kỳ vọng mặc định rằng mỗi `get()` tạo mới; giao diện `Supplier<T>` không quy định cache, scope hay quyền sở hữu. Khi vòng đời quan trọng, hãy **ghi rõ hợp đồng**: `createForTask(...)` có tạo instance mới không, sản phẩm có cần đóng không, ai quản lý nó.

### Policy có trạng thái: phải phân biệt cấu hình với trạng thái request

Hai Strategy trong ví dụ giữ các field `final` kiểu số nguyên, không sửa sau constructor. Chúng là ứng viên để chia sẻ nhiều lần gọi (khi các phụ thuộc khác cũng phù hợp).

Ngược lại, một Strategy lưu `currentUserId`, giỏ hàng đang tính hoặc transaction trong field sẽ không thể mặc nhiên chia sẻ giữa các request. Trong trường hợp ấy, thiết kế tốt hơn thường là:

- Truyền dữ liệu request vào phương thức `feeFor(...)` dưới dạng tham số/value object.
- Hoặc tạo instance Strategy theo request/tác vụ nếu nó thật sự cần state riêng.
- Không sửa một field chung của singleton cho mỗi request rồi hy vọng `volatile` giúp liên kết đúng dữ liệu với từng request.

**Scope** là quyết định độc lập với thuật toán Strategy, nhưng có ảnh hưởng trực tiếp đến tính đúng đắn khi dùng DI.

## 8. Điều kiện hợp đồng để nhiều Strategy thực sự thay thế được nhau

Để một Strategy thay thế được Strategy khác, cùng chữ ký phương thức **chưa đủ**. Những điều kiện sau cần có ý nghĩa nhất quán:

| Khía cạnh | Hợp đồng ví dụ cho `ShippingPolicy` |
| --- | --- |
| Đầu vào | `subtotalVnd` biểu diễn số tiền hàng bằng VND, phải dương |
| Đầu ra | Phí vận chuyển tính bằng VND, không âm |
| Hành vi | Chỉ tính phí, không lưu đơn hoặc gửi thông báo |
| Tác dụng phụ | Không có trong ví dụ |
| Ngoại lệ | Đầu vào sai được từ chối bằng `IllegalArgumentException` |
| Phạm vi | Có thể tái sử dụng nếu implementation không giữ mutable state theo request |
| Điều kiện miền | Không tự tạo ưu đãi trái quy tắc đã xác thực |

Nếu một Strategy mới trả phần trăm ở dạng `0.1` trong khi service hiểu đó là **10 VND**, việc thay thế sẽ sai dù interface giống nhau. Nếu một Strategy tự ghi database trong `feeFor`, service có thể vô tình gây tác dụng phụ nhiều lần khi thử tính phí. Hãy diễn đạt những điều này trong tài liệu API và test hợp đồng.

Một bộ **contract tests** có thể được áp dụng cho tất cả implementation, ví dụ đầu vào không dương phải bị từ chối, kết quả không âm và không có tác dụng phụ. Test riêng của từng Strategy sau đó kiểm tra các giá trị phí/biên đặc thù.

Nguyên tắc **Open/Closed** thường được nhắc đến khi dùng Strategy: có thể thêm một thuật toán mà không sửa consumer. Tuy nhiên, thêm policy mới vẫn cần **đăng ký/lựa chọn** nó ở composition root, registry hoặc cấu hình. “Không sửa consumer” không có nghĩa “không sửa bất kỳ code/config nào”.

## 9. Nên đặt quyết định chọn chính sách ở đâu?

Ba vị trí thường gặp:

**(1) Composition root:** lựa chọn theo môi trường, profile hoặc cấu hình triển khai. Đây là nơi tốt nếu cả ứng dụng dùng một chính sách cố định. Không để use case đọc biến môi trường trực tiếp.

**(2) Application service/coordinator:** lựa chọn theo luật nghiệp vụ có thể thay đổi mỗi request. Phần chọn phải kiểm tra dữ liệu và quyền phù hợp, rồi gọi Strategy hoặc service được định tuyến.

**(3) Factory/registry chuyên biệt:** nếu việc chọn phức tạp, có thể đóng gói thành một hợp đồng như `ShippingPolicySelector` nhận `ContractType` hoặc `ShippingMode`. Registry nên giới hạn vào đúng miền cần chọn, không biến thành service locator dùng để lấy tùy ý mọi bean.

~~~mermaid
flowchart TD
    Start["Nhận yêu cầu chọn chính sách"] --> Decision{"Chính sách cố định cho instance?"}
    Decision -->|"Có"| Root["Composition root chọn Strategy"]
    Decision -->|"Không"| Runtime{"Phụ thuộc dữ liệu từng tác vụ?"}
    Runtime -->|"Có"| Select["Coordinator/registry chọn theo dữ liệu hợp lệ"]
    Runtime -->|"Không rõ"| Simplify["Xem lại: có thật cần nhiều Strategy?"]
    Root --> Inject["Constructor injection vào Context"]
    Select --> Route["Chọn service/Strategy đúng scope"]
    Inject --> Execute["Gọi hành vi qua hợp đồng"]
    Route --> Execute
~~~

Điều cần tránh không phải mọi `if`, mà là **đặt sự thay đổi thuật toán vào sai nơi**. Một nhánh `if` ngắn tại composition root để chọn Strategy không phá vỡ lợi ích của mẫu thiết kế; trái lại, đó là nơi lựa chọn trở nên tường minh.

## 10. DI container tự động hóa được phần nào?

Giả sử sau này dùng Spring. Bạn có thể tạo các Strategy bằng `@Bean`, rồi dùng `@Qualifier` để chỉ rõ implementation cần tiêm vào `CheckoutService`.

Ví dụ **chỉ minh họa cấu hình Spring**, yêu cầu thư viện và môi trường Spring tương ứng; phần ví dụ Java thuần ở trên không cần những phụ thuộc này:

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class ShippingWiring {

    @Bean("flatShipping")
    ShippingStrategyDemo.ShippingPolicy flatShipping() {
        return new ShippingStrategyDemo.FlatFeePolicy(15_000);
    }

    @Bean("thresholdShipping")
    ShippingStrategyDemo.ShippingPolicy thresholdShipping() {
        return new ShippingStrategyDemo.FreeFromThresholdPolicy(
                25_000, 200_000);
    }

    @Bean
    ShippingStrategyDemo.OrderRepository orderRepository() {
        return new ShippingStrategyDemo.ConsoleOrderRepository();
    }

    @Bean
    ShippingStrategyDemo.CheckoutService checkoutService(
            @Qualifier("thresholdShipping")
            ShippingStrategyDemo.ShippingPolicy shipping,
            ShippingStrategyDemo.OrderRepository repository) {
        return new ShippingStrategyDemo.CheckoutService(
                shipping, repository);
    }
}
~~~

Hai bean có cùng type `ShippingPolicy`, nên điểm tiêm dùng qualifier `"thresholdShipping"` để xác định một đối tượng cụ thể. Nếu đổi chính sách mặc định, cấu hình có thể thay đổi mà không sửa `CheckoutService`.

Một container giúp **đăng ký và resolve** đúng Strategy, có thể quản lý scope/lifecycle theo cơ chế của framework. Nó **không** tự quyết định rằng một khách hàng đủ điều kiện miễn phí vận chuyển; đó vẫn là quy tắc nghiệp vụ. Nó cũng không mặc nhiên phát hiện một Strategy có mutable state không an toàn luồng.

Không nên inject `ApplicationContext` vào `CheckoutService` chỉ để gọi `getBean("thresholdShipping")` trong mỗi lần checkout. Điều đó làm dependency bị ẩn và kéo chi tiết container vào lõi. Nếu cần chọn động, hãy dùng registry/factory có kiểu và hợp đồng rõ ràng hoặc một coordinator chuyên biệt.

## 11. Những lỗi thiết kế dễ gặp

| Dấu hiệu | Vì sao rủi ro? | Cách tiếp cận tốt hơn |
| --- | --- | --- |
| `CheckoutService` tự `new FlatFeePolicy(...)` | Consumer quyết định cách tạo và khó thay lựa chọn | Tạo tại composition root, tiêm qua constructor |
| Logic từng chính sách vẫn nằm trong `switch` của service | Mẫu Strategy chỉ mang tính hình thức | Chuyển thuật toán riêng vào concrete strategies |
| Tạo interface và 10 class cho một công thức ít thay đổi | Tăng độ phức tạp và chi phí điều hướng | Dùng một class có cấu hình nếu chưa có biến thể thực |
| Strategy tự đọc biến môi trường mỗi lần tính | Kết quả khó dự đoán và khó test | Cấu hình tại startup rồi tiêm value object/Strategy |
| Singleton Strategy giữ `currentTenant` trong field | Lẫn dữ liệu giữa request, captive state | Truyền dữ liệu theo lời gọi hoặc tạo Strategy theo scope |
| Service đổi Strategy trong một field mutable trước mỗi request | Race condition khi nhiều request đồng thời | Định tuyến theo tham số hoặc tạo context đúng scope |
| Chọn chính sách ưu đãi theo tham số client chưa xác thực | Có thể cho phép tính phí sai quyền | Chọn dựa trên dữ liệu và quy tắc đã được xác thực |
| Factory/provider không nêu việc tạo mới hay dùng chung | Khó kiểm soát state và tài nguyên | Ghi rõ scope, ownership và hành vi `get()/create()` |
| Strategy trả giá trị âm hoặc sai đơn vị | Phá bất biến của consumer | Contract tests và kiểm tra invariant tại ranh giới |
| Tất cả test đều khởi động DI container | Chậm và khó cô lập logic | Test Strategy/Context bằng Java thuần, test wiring riêng |
| Thêm Strategy nhưng không có cách chọn nó | Mã tồn tại nhưng không được sử dụng | Cập nhật composition root, registry hoặc binding |
| Đánh đồng chọn Strategy với xử lý lỗi I/O | Lựa chọn đúng không đảm bảo adapter ngoài hoạt động | Xử lý lỗi runtime, retry/timeout và vòng đời riêng |

Lưu ý rằng `OrderRepository.save(...)` trong ví dụ là tác dụng phụ riêng. Strategy chỉ tính toán; nếu repository lưu thất bại, việc chọn đúng chính sách không giải quyết được tính nhất quán nghiệp vụ hay transaction.

## 12. Quy trình refactor từ điều kiện sang DI + Strategy

Nếu một service đang chứa nhiều nhánh tính phí, có thể refactor theo thứ tự sau:

1. **Ghi lại hành vi hiện tại bằng test**: giá trị bình thường, đúng ngưỡng, dưới/trên ngưỡng, cấu hình sai và điều kiện lỗi.
2. **Tìm phần thật sự biến đổi**: thuật toán tính phí, không phải toàn bộ luồng checkout.
3. **Định nghĩa hợp đồng nhỏ** theo nhu cầu consumer: `ShippingPolicy.feeFor(subtotalVnd)`.
4. **Di chuyển từng nhánh** sang class Strategy, giữ cách hiểu đơn vị tiền và ngoại lệ nhất quán.
5. **Đổi service sang constructor injection** và kiểm tra `null` tại constructor.
6. **Chuyển lựa chọn implementation ra composition root**, hoặc một coordinator/registry nếu lựa chọn biến đổi theo lời gọi.
7. **Chạy test cho từng Strategy và consumer** với fake repository, kiểm tra không phát sinh tác dụng phụ khi dữ liệu sai.
8. **Xem lại scope và ownership**: Strategy có thể chia sẻ không, có giữ tài nguyên nào cần đóng không?
9. **Bổ sung test wiring** nếu chuyển phần lắp ghép sang DI container sau này.

Phần lớn giá trị có được từ việc **làm rõ ranh giới thay đổi**, chứ không phải từ số lượng interface hoặc annotation.

### Checklist nhanh trước khi chấp nhận thiết kế

- Có ít nhất một lý do có căn cứ để xem thuật toán/chính sách là một điểm biến động không?
- Consumer chỉ gọi hành vi qua hợp đồng hay vẫn biết các lớp Strategy cụ thể?
- Strategy có bảo vệ quy tắc đầu vào, đầu ra và đơn vị dữ liệu nhất quán không?
- Composition root hoặc coordinator có xác định rõ ai được chọn chính sách nào không?
- Mọi phụ thuộc bắt buộc được tiêm rõ và kiểm tra tại constructor chưa?
- Nếu Strategy có trạng thái, nó có được dùng đúng scope và an toàn khi chạy đồng thời không?
- Có test Strategy độc lập và test của Context với ít nhất hai implementation không?
- Có thể dùng code nghiệp vụ bằng Java thuần, không khởi động container không?

## 13. Bài tập thực hành

**Bài 1 — Thêm chính sách thực sự khác biệt.** Viết `WeightBasedShippingPolicy` tính phí theo trọng lượng hoặc vùng giao nhận. Bạn cần quyết định có nên đổi hợp đồng từ `feeFor(long subtotalVnd)` sang nhận một `ShippingQuoteRequest` có trọng lượng/vùng không. Giải thích vì sao Strategy không thể giữ nguyên hợp đồng nếu nó thiếu dữ liệu thiết yếu, và cách thay đổi hợp đồng mà không làm rò rỉ DTO HTTP vào core.

**Bài 2 — So sánh hai cách chọn chính sách.** Dùng `ShippingStrategyDemo` ở chế độ `flat` rồi `threshold`. Sau đó viết một lớp định tuyến theo `ShippingMode` giống ví dụ mục 6. Nêu điểm khác nhau về thời điểm lựa chọn, số lượng `CheckoutService` và kiểm thử.

**Bài 3 — Viết contract test.** Tạo danh sách các Strategy và kiểm tra đầu vào `0`, đầu vào âm, kết quả không âm. Vì sao test giá trị phí cụ thể phải tách khỏi test hợp đồng chung?

**Bài 4 — Phát hiện scope sai.** Cho một Strategy có field `currentCustomerId` được cập nhật trước mỗi lời gọi trong singleton. Mô phỏng hai request có thể chạy đan xen. Hãy sửa bằng một tham số hoặc tạo Strategy mới theo request, rồi giải thích vai trò của factory/provider.

**Bài 5 — Kiểm thử lựa chọn động có quyền hạn.** Một nhóm người dùng không được dùng chính sách `PROMOTION`. Xác định vị trí kiểm tra quyền trước khi định tuyến đến service, và viết test rằng request không đủ quyền không được áp dụng chính sách ưu đãi.

**Bài 6 — Đưa lên DI container.** Khai báo hai `ShippingPolicy` theo bean và dùng qualifier để tiêm policy mặc định. Viết một unit test thuần Java cho `CheckoutService` và một test wiring riêng để phát hiện cấu hình thiếu hoặc nhiều ứng viên không phân biệt được.

Câu hỏi tự đánh giá cuối cùng: **Strategy nào có thể thay thế nhau theo cùng hợp đồng? Ai quyết định chọn Strategy, ở thời điểm nào? Object graph bảo đảm scope/vòng đời ra sao?** Khi trả lời được ba câu hỏi đó, bạn đã kết hợp **Strategy Pattern** và **Dependency Injection** một cách có chủ đích: thuật toán dễ thay, lớp nghiệp vụ ít phụ thuộc chi tiết và test được bằng Java thuần trước khi mở rộng sang DI container.
