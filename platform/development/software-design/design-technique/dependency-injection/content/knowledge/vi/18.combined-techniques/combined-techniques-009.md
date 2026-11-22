# Lựa chọn kỹ thuật theo vấn đề thay vì kết hợp nhiều mẫu một cách máy móc

Trong một ứng dụng Java, **Dependency Injection (DI)** có thể được sử dụng cùng *Strategy*, *Factory*, *Provider*, *Decorator*, *Adapter*, *Composition Root*, quản lý scope và DI container. Những kỹ thuật này bổ trợ nhau, nhưng **kết hợp càng nhiều mẫu không có nghĩa thiết kế càng tốt**. Mỗi lớp, interface và điểm cấu hình bổ sung đều có chi phí đọc hiểu, kiểm thử và quản lý vòng đời.

Ví dụ, khi yêu cầu chỉ là “tính phí vận chuyển bằng một công thức tiêu chuẩn”, ta có thể đơn giản truyền một `FeePolicy` qua constructor. Nếu lập tức thêm `PolicyRegistry`, `PolicySelector`, `PolicyFactory`, `PolicyDecoratorChain` và container, mã lắp ghép dễ phức tạp hơn cả nghiệp vụ mà chưa giải quyết vấn đề thực tế nào.

Nguyên tắc xuyên suốt bài học thuộc chương **Kỹ thuật kết hợp**:

> **Chọn kỹ thuật theo biến động có thật: điều gì có thể thay đổi, thay đổi lúc nào, ai quyết định, ai sở hữu tài nguyên và ràng buộc nào cần được giữ đúng.**

Ta sẽ phát triển một ví dụ Java 17 theo các yêu cầu tăng dần, bắt đầu từ constructor injection và composition root bằng Java thuần, rồi chỉ đưa Strategy/selector, decorator hoặc factory vào khi có nhu cầu rõ ràng.

## 1. Các kỹ thuật giải quyết những vấn đề khác nhau

| Kỹ thuật | Câu hỏi chính | Không tự giải quyết |
|---|---|---|
| **Constructor injection** | Đối tượng nhận collaborator bắt buộc từ đâu? | Chọn implementation, scope, giải phóng tài nguyên |
| **Composition root** | Nơi nào chọn, tạo và lắp graph? | Mọi thay đổi theo request hoặc tất cả lỗi runtime |
| **Strategy** | Có những thuật toán thay thế nhau qua cùng hợp đồng không? | Nơi chọn và tạo strategy |
| **Selector** | Với một tiêu chí, lấy implementation nào? | Tạo resource mới hoặc quản lý transaction |
| **Factory/provider** | Khi nào cần cấp instance mới? | Tự bảo đảm owner sẽ đóng resource |
| **Adapter** | Làm thế nào đổi API ngoài thành contract ứng dụng cần? | Tự bảo đảm semantics của API bên ngoài tương đương |
| **Decorator** | Cần bọc hành vi mà không sửa implementation gốc? | Tự quyết định thứ tự bọc, retry và cách xử lý lỗi |
| **Scope/lifecycle** | Instance được chia sẻ tới đâu và đóng khi nào? | Làm mọi state mutable trở nên thread-safe |
| **DI container** | Làm sao tự động hóa việc lắp object graph lớn? | Xác định đúng ranh giới nghiệp vụ hoặc ownership |

Một interface có hai implementation không bắt buộc phải có selector. Nếu cấu hình chọn một implementation **khi startup**, composition root có thể tạo đối tượng đó và inject trực tiếp. Ngược lại, một hệ thống chỉ có **một loại transaction session** vẫn có thể cần factory vì session phải được mở và đóng theo từng đơn vị công việc.

Vì vậy, hãy tách ba câu hỏi:

1. **Chọn loại implementation nào?** Ví dụ `STANDARD` hay `EXPRESS`.
2. **Chọn instance nào?** Dùng chung một object hay tạo instance mới?
3. **Sử dụng và kết thúc vào thời điểm nào?** Mỗi request, mỗi transaction hoặc toàn ứng dụng?

Nhầm ba câu hỏi này thường dẫn tới registry tổng quát, đối tượng dùng chung giữ dữ liệu request hoặc factory tạo lại những policy hoàn toàn bất biến.

## 2. Từ yêu cầu tới quyết định kỹ thuật

Một bảng phân loại giúp xác định lý do thêm abstraction:

| Yêu cầu được xác nhận | Nhu cầu thực | Cách đơn giản đáng thử trước |
|---|---|---|
| Cả ứng dụng dùng một công thức tính phí | Một collaborator ổn định | Constructor injection; chọn tại root |
| Chọn STANDARD hoặc EXPRESS bằng biến cấu hình lúc khởi động | Thay implementation ở startup | Parse config rồi `new` implementation phù hợp tại root |
| Khách chọn mode theo từng đơn hàng | Strategy theo request | Inject selector; method nhận mode |
| Đối tác cung cấp SDK với API không khớp | Chuyển đổi API | Adapter |
| Mọi lời gọi tới đối tác cần metrics | Hành vi cắt ngang | Decorator hoặc instrumentation tại biên phù hợp |
| Mỗi transaction cần connection/session riêng | Tạo và đóng theo scope | Inject factory, dùng `try-with-resources` |
| Nhiều module có graph và lifecycle phức tạp | Tự động hóa composition | Cân nhắc DI container |
| Chưa có thay đổi hoặc rủi ro mới | Không có vấn đề bổ sung | Không thêm mẫu chỉ vì dự phòng |

Không phải cứ có câu lệnh `if` là cần Strategy. Một nhánh kiểm tra dữ liệu hoặc quy tắc nghiệp vụ có thể thuộc đúng trách nhiệm của service. Chỉ cần tách phần **chọn/tạo cộng tác viên có cấu hình, implementation hoặc vòng đời riêng** khi sự trộn lẫn đang làm service khó thay đổi hoặc kiểm thử.

## 3. Phản ví dụ: chồng nhiều mẫu khi chưa có nhu cầu

Giả sử yêu cầu duy nhất là “tính phí tiêu chuẩn”. Một thiết kế quá sớm có thể tạo graph:

```text
ShippingService
      │
      ▼
PolicyFacade
      │
      ▼
PolicyFactory
      │
      ▼
PolicyRegistry
      │
      ▼
PolicyProvider
      │
      ▼
PolicyDecoratorChain
      │
      ▼
StandardFeePolicy
```

Các tên trên không sai tự thân. Vấn đề là không thể giải thích **từng tầng đang bảo vệ ranh giới nào hoặc giải quyết biến động nào**. Hệ quả:

- Muốn đọc logic báo giá phải lần qua nhiều lớp chỉ chuyển tiếp.
- Test phải cấu hình nhiều phụ thuộc không liên quan tới hành vi đang kiểm tra.
- Khi một factory có resource riêng, phải xác định thêm owner và đường cleanup.
- Mỗi registration có thể đưa tới lỗi thiếu binding, nhầm scope hoặc chọn implementation sai.
- Review code có nguy cơ kiểm tra “đủ mẫu thiết kế” thay vì tính đúng đắn của nghiệp vụ.

Ngược lại, không nên xóa mọi lớp trung gian chỉ để giảm số class. Một adapter ngắn có thể giữ nghiệp vụ độc lập với SDK biến động; một decorator nhỏ có thể giảm logic metrics bị sao chép. **Chi phí phức tạp phải được so với lợi ích thật**.

## 4. Khởi đầu: constructor injection là đủ

Yêu cầu đầu tiên: “Mọi đơn dùng cùng chính sách phí tiêu chuẩn.”

```java
interface FeePolicy {
    long calculate(Shipment shipment);
}

final class FixedQuoteService {
    private final FeePolicy policy;

    FixedQuoteService(FeePolicy policy) {
        this.policy = Objects.requireNonNull(policy);
    }

    long quote(Shipment shipment) {
        return policy.calculate(shipment);
    }
}
```

*Đoạn trên minh họa cấu trúc; `Shipment` và import `Objects` được định nghĩa trong ví dụ hoàn chỉnh ở mục 6.*

Composition root chỉ cần:

```java
FeePolicy standard = new StandardFeePolicy();
FixedQuoteService service = new FixedQuoteService(standard);
```

Điều này đã đạt được các mục tiêu quan trọng:

- Service không tự lựa chọn/tạo cộng tác viên.
- Constructor nói rõ dependency bắt buộc.
- Có thể inject fake `FeePolicy` trong unit test.
- Thời điểm tạo và lựa chọn implementation nằm ở composition root.
- Không cần container, selector, factory hoặc reflection.

Đây là DI thủ công hợp lệ. **DI không bắt buộc có interface**: nếu một concrete collaborator có ranh giới rõ, nhận nó qua constructor vẫn là DI. Interface được dùng ở đây vì ta chuẩn bị minh họa một nhu cầu thay đổi thuật toán thực sự.

## 5. Yêu cầu mới: mode thay đổi theo từng request

Sau đó hệ thống cần: “Khách có thể chọn `STANDARD` hoặc `EXPRESS` cho **mỗi đơn**.”

Sự biến động đã thay đổi:

```text
Trước:
  Composition root ── chọn STANDARD ──► FixedQuoteService
                                        │
                                        └── quote(shipment)

Sau:
  Composition root ──► FeePolicySelector
                           │
                           ▼
                     MultiModeQuoteService
                           │
                     quote(shipment, mode)
                           │
                           ▼
                  Chọn đúng FeePolicy
```

Có hai cách dễ gây lỗi:

**Cách 1: một singleton có method `setPolicy(...)` trước mỗi lần quote.** Khi hai request đồng thời thay policy, request A có thể bị tính giá theo lựa chọn của request B.

**Cách 2: service tự `new StandardFeePolicy()` hoặc `new ExpressFeePolicy()`.** Business service vừa xử lý use case vừa chọn và khởi tạo implementation, dễ phụ thuộc vào cấu hình hạ tầng khi policy trở nên phức tạp.

Ta có thể inject `FeePolicySelector` vào constructor và truyền `ServiceLevel` theo lời gọi. Nhờ vậy **mode là dữ liệu per-call**, không phải trạng thái mutable của singleton. Các policy bất biến có thể tiếp tục dùng chung; không cần tạo policy mới mỗi request.

## 6. Ví dụ Java 17: tăng kỹ thuật theo đúng yêu cầu

Chương trình sau thể hiện ba giai đoạn:

1. Chỉ có một `FeePolicy`: `FixedQuoteService`.
2. Cần chọn mode theo request: `MultiModeQuoteService` + `FeePolicySelector`.
3. Cần đếm số lần gọi EXPRESS: thêm `CountingFeePolicy` như một decorator, **không sửa use case**.

Lưu toàn bộ trong `TechniqueChoiceDemo.java`:

```java
import java.util.EnumSet;
import java.util.Map;
import java.util.Objects;
import java.util.concurrent.atomic.AtomicInteger;

public final class TechniqueChoiceDemo {

    enum ServiceLevel {
        STANDARD, EXPRESS
    }

    record Shipment(String orderId, int weightKg) {
        Shipment {
            if (orderId == null || orderId.isBlank()) {
                throw new IllegalArgumentException(
                    "orderId must not be blank");
            }
            if (weightKg <= 0) {
                throw new IllegalArgumentException(
                    "weightKg must be positive");
            }
        }
    }

    @FunctionalInterface
    interface FeePolicy {
        long calculate(Shipment shipment);
    }

    static final class StandardFeePolicy implements FeePolicy {
        @Override
        public long calculate(Shipment shipment) {
            Objects.requireNonNull(shipment, "shipment");
            return Math.addExact(
                12_000L,
                Math.multiplyExact(shipment.weightKg(), 2_000L));
        }
    }

    static final class ExpressFeePolicy implements FeePolicy {
        @Override
        public long calculate(Shipment shipment) {
            Objects.requireNonNull(shipment, "shipment");
            return Math.addExact(
                27_000L,
                Math.multiplyExact(shipment.weightKg(), 5_000L));
        }
    }

    // Chỉ dùng một implementation được chọn khi lắp graph.
    static final class FixedQuoteService {
        private final FeePolicy policy;

        FixedQuoteService(FeePolicy policy) {
            this.policy = Objects.requireNonNull(policy, "policy");
        }

        long quote(Shipment shipment) {
            return policy.calculate(
                Objects.requireNonNull(shipment, "shipment"));
        }
    }

    @FunctionalInterface
    interface FeePolicySelector {
        FeePolicy select(ServiceLevel level);
    }

    // Chỉ cần selector khi mode thay đổi theo request.
    static final class MapBasedSelector
            implements FeePolicySelector {

        private final Map<ServiceLevel, FeePolicy> policies;

        MapBasedSelector(Map<ServiceLevel, FeePolicy> policies) {
            this.policies = Map.copyOf(
                Objects.requireNonNull(policies, "policies"));

            if (!this.policies.keySet().containsAll(
                    EnumSet.allOf(ServiceLevel.class))) {
                throw new IllegalArgumentException(
                    "Missing a required delivery policy");
            }
        }

        @Override
        public FeePolicy select(ServiceLevel level) {
            Objects.requireNonNull(level, "level");
            FeePolicy selected = policies.get(level);
            if (selected == null) {
                throw new IllegalArgumentException(
                    "No policy for " + level);
            }
            return selected;
        }
    }

    static final class MultiModeQuoteService {
        private final FeePolicySelector selector;

        MultiModeQuoteService(FeePolicySelector selector) {
            this.selector = Objects.requireNonNull(
                selector, "selector");
        }

        long quote(Shipment shipment, ServiceLevel level) {
            Objects.requireNonNull(shipment, "shipment");
            Objects.requireNonNull(level, "level");

            FeePolicy selected = Objects.requireNonNull(
                selector.select(level),
                "selector must return a policy");

            return selected.calculate(shipment);
        }
    }

    // Decorator chỉ thêm khi cần quan sát số lần gọi.
    static final class CountingFeePolicy implements FeePolicy {
        private final FeePolicy delegate;
        private final AtomicInteger calls = new AtomicInteger();

        CountingFeePolicy(FeePolicy delegate) {
            this.delegate = Objects.requireNonNull(
                delegate, "delegate");
        }

        @Override
        public long calculate(Shipment shipment) {
            calls.incrementAndGet();
            return delegate.calculate(shipment);
        }

        int calls() {
            return calls.get();
        }
    }

    public static void main(String[] args) {
        Shipment shipment = new Shipment("ORD-100", 3);

        // Giai đoạn 1: không cần selector hay container.
        FeePolicy standard = new StandardFeePolicy();
        FixedQuoteService fixed =
            new FixedQuoteService(standard);

        System.out.println(
            "fixed=" + fixed.quote(shipment));

        // Giai đoạn 2: chọn theo từng request.
        CountingFeePolicy countedExpress =
            new CountingFeePolicy(new ExpressFeePolicy());

        FeePolicySelector selector = new MapBasedSelector(
            Map.of(
                ServiceLevel.STANDARD, standard,
                ServiceLevel.EXPRESS, countedExpress
            )
        );
        MultiModeQuoteService multiple =
            new MultiModeQuoteService(selector);

        System.out.println(
            "standard=" + multiple.quote(
                shipment, ServiceLevel.STANDARD));
        System.out.println(
            "express=" + multiple.quote(
                shipment, ServiceLevel.EXPRESS));

        // Giai đoạn 3: decorator ghi nhận đúng nhánh EXPRESS.
        System.out.println(
            "express-calls=" + countedExpress.calls());
    }
}
```

Chạy bằng JDK 17 trở lên:

```bash
javac TechniqueChoiceDemo.java
java TechniqueChoiceDemo
```

Kết quả dự kiến:

```text
fixed=18000
standard=18000
express=42000
express-calls=1
```

### Vì sao ví dụ này thể hiện đúng tinh thần “chỉ thêm khi cần”?

Ở giai đoạn đầu, chỉ cần `FixedQuoteService` và một policy. Thêm selector khi không có lựa chọn runtime sẽ làm graph dài hơn mà không cải thiện hành vi.

Đến giai đoạn hai, người dùng thật sự được chọn `ServiceLevel` trên từng request. Selector mang một nhiệm vụ mới: ánh xạ mode sang policy, từ chối mapping thiếu và giữ service không phụ thuộc lớp cụ thể. `MapBasedSelector` dùng `Map.copyOf(...)` để cố định cấu hình. Hai policy có trạng thái bất biến, không giữ dữ liệu request, nên dùng chung trong ví dụ này là hợp lý.

Đến giai đoạn ba, yêu cầu quan sát chỉ áp dụng cho EXPRESS. Composition root bọc `ExpressFeePolicy` bằng `CountingFeePolicy`, không sửa `MultiModeQuoteService`. Khi không còn cần metrics, ta có thể bỏ decorator mà không sửa giao diện báo giá.

`CountingFeePolicy` tăng counter **trước khi** gọi delegate, vì vậy nó đo **lượt gọi**, kể cả khi delegate ném exception. Nếu muốn đếm **lượt thành công**, phải tăng counter sau khi lời gọi trả về. Đây là minh chứng rằng một decorator đúng về cấu trúc chưa chắc đã đúng về ngữ nghĩa.

Trong ví dụ, phí dùng `long` với đơn vị VND nguyên, `Math.multiplyExact` và `Math.addExact` để phát hiện tràn số. Hệ thống tiền tệ thật có thể có yêu cầu riêng về thuế, làm tròn và giới hạn miền giá trị.

## 7. Kiểm thử bằng fake: chứng minh giá trị của từng kỹ thuật

Lưu `TechniqueChoiceCheck.java` cạnh chương trình trên:

```java
import java.util.Map;
import java.util.concurrent.atomic.AtomicInteger;

public final class TechniqueChoiceCheck {
    public static void main(String[] args) {
        var shipment =
            new TechniqueChoiceDemo.Shipment("TEST-1", 2);

        // 1. Service đơn giản vẫn dễ kiểm thử với fake.
        AtomicInteger directCalls = new AtomicInteger();

        TechniqueChoiceDemo.FeePolicy fake = request -> {
            directCalls.incrementAndGet();
            if (!"TEST-1".equals(request.orderId())
                    || request.weightKg() != 2) {
                throw new AssertionError("Wrong shipment");
            }
            return 777L;
        };

        var fixed =
            new TechniqueChoiceDemo.FixedQuoteService(fake);

        if (fixed.quote(shipment) != 777L
                || directCalls.get() != 1) {
            throw new AssertionError(
                "Fixed service ignored injected policy");
        }

        // 2. Chọn hai implementation theo từng lời gọi.
        AtomicInteger standardCalls = new AtomicInteger();
        AtomicInteger expressCalls = new AtomicInteger();

        TechniqueChoiceDemo.FeePolicy standard = request -> {
            standardCalls.incrementAndGet();
            return 100L;
        };
        TechniqueChoiceDemo.FeePolicy express = request -> {
            expressCalls.incrementAndGet();
            return 200L;
        };

        var selector = new TechniqueChoiceDemo.MapBasedSelector(
            Map.of(
                TechniqueChoiceDemo.ServiceLevel.STANDARD, standard,
                TechniqueChoiceDemo.ServiceLevel.EXPRESS, express
            )
        );
        var multiple =
            new TechniqueChoiceDemo.MultiModeQuoteService(selector);

        if (multiple.quote(
                shipment,
                TechniqueChoiceDemo.ServiceLevel.EXPRESS) != 200L
                || multiple.quote(
                    shipment,
                    TechniqueChoiceDemo.ServiceLevel.STANDARD) != 100L
                || expressCalls.get() != 1
                || standardCalls.get() != 1) {
            throw new AssertionError(
                "Per-request selection was incorrect");
        }

        // 3. Decorator ủy quyền và thêm hành vi đo.
        var counted =
            new TechniqueChoiceDemo.CountingFeePolicy(fake);

        if (counted.calculate(shipment) != 777L
                || counted.calculate(shipment) != 777L
                || counted.calls() != 2
                || directCalls.get() != 3) {
            throw new AssertionError(
                "Decorator did not delegate and count");
        }

        // 4. Cấu hình thiếu nhánh cần bị từ chối sớm.
        boolean rejected = false;
        try {
            new TechniqueChoiceDemo.MapBasedSelector(
                Map.of(
                    TechniqueChoiceDemo.ServiceLevel.STANDARD,
                    standard)
            );
        } catch (IllegalArgumentException expected) {
            rejected = true;
        }

        if (!rejected) {
            throw new AssertionError(
                "Missing EXPRESS mapping was accepted");
        }

        System.out.println("PASS");
    }
}
```

Chạy:

```bash
javac TechniqueChoiceDemo.java TechniqueChoiceCheck.java
java TechniqueChoiceCheck
```

Kết quả dự kiến: `PASS`.

Bài kiểm tra cho thấy:

- Constructor injection đã đủ để kiểm thử service ban đầu.
- Selector thực sự thay đổi thuật toán theo dữ liệu của lời gọi.
- Decorator bổ sung hành vi mà không thay đổi giá trị gốc.
- Mapping thiếu được phát hiện khi lắp graph, trước khi request chạy.

Trong ứng dụng dùng hạ tầng thực, test này không thay thế integration test cho HTTP/database; nó chỉ chứng minh các quyết định về composition và điều phối.

## 8. Factory/provider chỉ nên xuất hiện khi cần kiểm soát thời điểm tạo

Trong ví dụ báo giá, policy không sở hữu tài nguyên ngoài nên không cần tạo mới mỗi lần gọi. Nhưng nếu yêu cầu mới là: “Mỗi lần giữ chỗ trong kho phải mở một session riêng, và đóng session sau khi xử lý”, thì **lifetime mới là vấn đề**.

```text
Composition root
     │
     ▼
ReservationSessionFactory
     │ inject
     ▼
StockReservationService
     │
     └── reserve(orderId, sku)
           ├── factory.open()
           ├── session.reserve(...)
           └── session.close()
```

Ví dụ thiết kế:

```java
interface ReservationSession extends AutoCloseable {
    void reserve(String orderId, String sku);

    @Override
    void close();
}

@FunctionalInterface
interface ReservationSessionFactory {
    ReservationSession open();
}

final class StockReservationService {
    private final ReservationSessionFactory factory;

    StockReservationService(ReservationSessionFactory factory) {
        this.factory = Objects.requireNonNull(
            factory, "factory");
    }

    void reserve(String orderId, String sku) {
        try (ReservationSession session = factory.open()) {
            session.reserve(orderId, sku);
        }
    }
}
```

*Đây là một đoạn kiến trúc riêng, giả định `import java.util.Objects;` và các implementation đã được cung cấp. Với transaction thật, cần quy định commit/rollback và cách xử lý ngoại lệ; không suy ra transaction thành công chỉ từ `close()`.*

`ReservationSessionFactory` giải quyết **việc mở tài nguyên mỗi thao tác**, không giải quyết chọn thuật toán phí giao hàng. Session là tài nguyên ngắn hạn, còn connection pool nền có thể được composition root sở hữu và dùng chung.

Ngược lại, nếu use case cần tạo `new QuoteResult(...)` hoặc `new ShippingRequest(...)` là dữ liệu per-call, việc tạo dữ liệu đó không trái với DI. **Không cần một factory cho mọi lệnh `new`**.

## 9. Adapter chỉ cần khi API hoặc ngữ nghĩa giữa hai phía khác nhau

Giả sử hợp đồng nội bộ của ứng dụng là:

```java
interface FeePolicy {
    long calculate(Shipment shipment);
}
```

Nhưng một SDK bên ngoài có API:

```java
long priceFor(String destinationCode, int weightGrams);
```

Nếu business service phải biết các kiểu lỗi, mã vùng và đơn vị gram của SDK, mức độ phụ thuộc vào đối tác đã tăng. Một **Adapter** có thể chuyển đổi API:

```java
final class PartnerFeeAdapter implements FeePolicy {
    private final PartnerShippingSdk partner;

    PartnerFeeAdapter(PartnerShippingSdk partner) {
        this.partner = Objects.requireNonNull(partner);
    }

    @Override
    public long calculate(Shipment shipment) {
        String destination = lookupDestination(shipment.orderId());
        int grams = Math.multiplyExact(
            shipment.weightKg(), 1_000);
        return partner.priceFor(destination, grams);
    }
}
```

*Đây là pseudocode về ranh giới tích hợp: `PartnerShippingSdk` và `lookupDestination(...)` chưa được định nghĩa. Hệ thống thực tế phải cung cấp mã vùng đích đúng, không suy ra từ order ID nếu miền nghiệp vụ không cho phép.*

Adapter đáng có nếu nó **ngăn chi tiết SDK lan vào use case**. Nhưng việc chỉ có một interface chưa tự chứng minh cần thêm Adapter. Một implementation `FeePolicy` bình thường có thể đã là ranh giới đủ tốt.

Khi adapter truy cập network, cần xác định timeout, retry được phép, lỗi dữ liệu, client dùng chung và quyền đóng tài nguyên. Những quyết định đó không phải hệ quả tự động của tên “Adapter”.

## 10. Decorator: chỉ bọc hành vi có hợp đồng rõ

Decorator phù hợp khi cần thêm hành vi như metrics hoặc tracing, mà không sửa logic bên trong mỗi implementation.

```text
QuoteService
     │
     ▼
CountingFeePolicy
     │
     ▼
ExpressFeePolicy
```

Tuy nhiên, không phải mọi hành vi đều nên bọc:

| Yêu cầu | Vị trí nên xem xét |
|---|---|
| Quy tắc giảm giá là một phần nghiệp vụ | Một `FeePolicy` cụ thể hoặc use case |
| Cần đo lượt gọi tới policy | Decorator hoặc instrumentation |
| Chuyển SDK bên ngoài sang API nội bộ | Adapter |
| Chọn STANDARD/EXPRESS theo request | Selector |
| Mở resource ngắn hạn mỗi lần | Factory và scope |
| Phân quyền truy cập đơn | Boundary nghiệp vụ hoặc cơ chế security đã định nghĩa |
| Timeout HTTP | Client/transport adapter |
| Transaction nhất quán | Transaction boundary |

**Thứ tự bọc có thể thay đổi ý nghĩa.** Ví dụ:

```text
Measured(Retrying(RemoteGateway))
```

Có thể đo một lần gọi logic bao gồm nhiều lần thử. Trong khi đó:

```text
Retrying(Measured(RemoteGateway))
```

có thể đo từng lần gọi tới remote. Hai graph dùng cùng decorator nhưng số metrics khác nhau. Retry với thao tác có side effect còn cần chính sách idempotency, giới hạn số lần và timeout tổng; không được tự bọc chỉ để “có khả năng chịu lỗi”.

Nếu logging/metrics có thể lỗi, cần quyết định liệu lỗi đo đạc có làm thất bại nghiệp vụ hay không. Với telemetry tùy chọn, chính sách thường khác với một bước audit bắt buộc về mặt pháp lý hoặc nghiệp vụ.

## 11. Scope và lifecycle phải được lựa chọn theo đối tượng

Khi có factory, adapter hoặc client ngoài, cần cân nhắc **scope**:

```text
ApplicationRoot
   ├── FeePolicy bất biến          (dùng chung)
   ├── ClientPool thread-safe      (dùng chung theo hợp đồng)
   │
   └── RequestScope
         ├── RequestContext        (theo request)
         └── UnitOfWork            (theo transaction)
                └── mượn client từ pool
```

Một policy bất biến không cần được tạo lại theo request. Một transaction session ngắn hạn không nên bị inject trực tiếp vào singleton rồi giữ lâu. Một client dùng chung không nên bị đóng bởi một request chỉ vì request ấy nhận tham chiếu đến client.

Những câu hỏi phải trả lời:

- Ai **tạo** resource và ai **đóng** nó?
- Consumer còn dùng resource sau khi scope kết thúc không?
- Resource có thread-safe để chia sẻ không?
- Khi shutdown, có cần ngừng nhận request và drain công việc trước khi đóng pool không?
- Nếu startup thất bại giữa chừng, ai dọn tài nguyên đã mở?

Với object graph đơn giản, composition root có thể tự quản lý bằng Java `AutoCloseable` và `try-with-resources`. DI container có thể hỗ trợ scope, nhưng **không tự chữa sai thiết kế khi singleton giữ dependency request-scoped**.

## 12. Khi nhiều kỹ thuật kết hợp là lựa chọn đúng

Giả sử hệ thống trưởng thành có tất cả yêu cầu thật sau:

- Khách chọn STANDARD hoặc EXPRESS theo request.
- Một mode dùng SDK đối tác với API khác.
- Mỗi giao dịch ghi đơn cần session riêng.
- Lời gọi tới đối tác cần metrics.
- Client SDK được dùng chung và đóng đúng lúc shutdown.

Graph tương ứng có thể là:

```text
Composition Root
   │
   ├── StandardFeePolicy
   ├── PartnerShippingClient             (dùng chung)
   │        │
   │        ▼
   │   PartnerFeeAdapter
   │        │
   │        ▼
   │   MeasuredFeePolicy
   │
   ├── FeePolicySelector
   │       ├── STANDARD → StandardFeePolicy
   │       └── EXPRESS  → MeasuredFeePolicy
   │
   ├── UnitOfWorkFactory
   │       └── tạo UnitOfWork theo transaction
   │
   └── CheckoutService
           ├── FeePolicySelector
           └── UnitOfWorkFactory
```

Khi ấy mỗi kỹ thuật có lý do:

1. **DI** đưa selector và factory vào `CheckoutService` qua constructor.
2. **Strategy/selector** chọn thuật toán theo mode được caller yêu cầu.
3. **Adapter** bảo vệ nghiệp vụ khỏi API của đối tác.
4. **Decorator** đo riêng hành vi tích hợp.
5. **Factory** cấp session theo transaction.
6. **Composition root/lifecycle** sở hữu client dài hạn và đóng nó sau khi các consumer ngừng sử dụng.

Graph này phức tạp hơn `FixedQuoteService`, nhưng **độ phức tạp đến từ các yêu cầu độc lập đã được xác nhận**. Không có lý do dùng cả graph cho một ứng dụng chỉ tính phí bằng một công thức.

Khi review, hãy hỏi: “Lớp X được thêm do yêu cầu Y thay đổi ở thời điểm Z; nó ngăn thay đổi lan tới các phần nào?” Nếu không trả lời rõ, abstraction mới có thể chưa cần thiết.

## 13. Quy trình ra quyết định trước khi thêm một mẫu

### Bước 1 — Viết yêu cầu có thể kiểm chứng

Ví dụ: “Cùng một service phải báo giá STANDARD và EXPRESS theo từng request, không làm mode của request này ảnh hưởng request khác.”

Đó là yêu cầu. “Phải dùng Strategy + Factory + Container” chỉ là đề xuất giải pháp.

### Bước 2 — Xác định điểm biến động

- **Implementation** thay đổi hay chỉ **dữ liệu đầu vào** thay đổi?
- Lựa chọn xảy ra khi **startup**, **request**, hay **transaction**?
- Cần **chọn từ instance có sẵn** hay **tạo resource mới**?
- Thay đổi là thuật toán, giao diện SDK hay vấn đề ownership?
- Có yêu cầu thread safety, retry, audit hoặc shutdown nào cụ thể?

Nếu chỉ là dữ liệu theo lời gọi, có thể cần thêm tham số method chứ không cần Strategy hay Factory.

### Bước 3 — Tạo mốc thiết kế đơn giản

```java
FeePolicy policy = new StandardFeePolicy();
FixedQuoteService service = new FixedQuoteService(policy);
```

Kiểm thử được đường này trước. Không cần đợi tới khi có DI container để sử dụng constructor injection.

### Bước 4 — Chỉ mở rộng phần chưa đáp ứng yêu cầu

Khi có lựa chọn theo request, thêm selector. Khi có session ngắn hạn, thêm factory. Khi dùng SDK khác contract, thêm adapter. Khi đo đạc thật sự cần tách khỏi nghiệp vụ, thêm decorator.

Không thêm đồng thời mọi tầng “phòng khi tương lai cần”, trừ khi hợp đồng sản phẩm hoặc nền tảng hiện tại đã đòi hỏi chúng.

### Bước 5 — Kiểm tra những ràng buộc ngoài sơ đồ class

Một sơ đồ design pattern không tự chứng minh:

- Request state có bị giữ trong singleton không?
- Shared client có an toàn khi dùng từ nhiều thread không?
- Ai đóng session và pool?
- Khi constructor hoặc startup lỗi, resource đã mở có được cleanup không?
- Retry sau timeout có thể lặp side effect không?
- Khi thêm mode mới, cấu hình thiếu có được phát hiện sớm không?

Những ràng buộc này thường quan trọng hơn việc đặt đúng tên mẫu.

### Bước 6 — Đo chi phí thay đổi

Nếu muốn thêm mode mới, cần sửa bao nhiêu lớp? Khi test lỗi hạ tầng, có thể inject fake không? Khi debug, phải lần qua mấy tầng chuyển tiếp? Khi thêm một abstraction, chi phí registration và test tăng bao nhiêu?

**Một abstraction có giá trị khi nó giảm thay đổi lan truyền, giảm lặp lại hoặc bảo vệ bất biến**, không chỉ vì nó giống sơ đồ trong sách.

## 14. Khi nào cân nhắc DI container?

Một DI container có thể giúp khi:

- Object graph lớn và nhiều module có registration riêng.
- Có nhiều implementation cần qualifier, cấu hình và validation.
- Scope/lifecycle phức tạp hoặc framework đã tích hợp container.
- Việc viết wiring lặp lại trở thành nguồn lỗi.
- Cần tự động hóa việc xây graph nhưng vẫn muốn giữ constructor injection.

Container không bắt buộc vì số lượng class vượt một ngưỡng cố định. Hãy kiểm tra:

| Câu hỏi | Lý do |
|---|---|
| Service vẫn khai báo collaborator qua constructor không? | Tránh chuyển thành Service Locator |
| Có nhiều implementation thì binding nào được chọn? | Tránh mơ hồ hoặc default sai |
| Scope của các dependency có tương thích không? | Tránh giữ tài nguyên request quá lâu |
| Ai sở hữu bean có `close()`? | Tránh leak và double-close |
| Khi startup lỗi, graph đã tạo được cleanup thế nào? | Đảm bảo vòng đời đáng tin cậy |
| Unit test use case còn chạy với fake Java thuần không? | Giữ phần nghiệp vụ độc lập framework |

Container giúp tự động hóa **composition**, không tự quyết định có nên dùng Strategy, Adapter hoặc Decorator hay không. Một ứng dụng dùng container vẫn có thể hoàn toàn không cần các mẫu đó.

## 15. Dấu hiệu kết hợp kỹ thuật một cách máy móc

| Dấu hiệu | Cần hỏi lại | Khi nào có thể chấp nhận |
|---|---|---|
| Một policy nhưng có nhiều tầng selector/factory | Có biến động thực tế không? | Framework/plugin contract bắt buộc |
| Một façade chỉ chuyển tiếp mọi method | Nó bảo vệ boundary gì? | Boundary công khai ổn định, phục vụ API khác nhau |
| Business service inject `GlobalRegistry` | Có thể inject collaborator trực tiếp không? | Plugin host thực sự cần discovery động, nhưng nên giới hạn ở host |
| Mọi dependency đều được bọc retry/cache | Có SLO và quy tắc lỗi riêng không? | Chính sách được đo, kiểm soát và có test |
| DTO từng request được đưa vào container | Có thể truyền qua method không? | Request context có trách nhiệm rõ do framework quản lý |
| Mọi object đều đi qua factory | Có quy tắc tạo/ownership đáng kể không? | Tạo resource phức tạp với invariant quan trọng |
| Container được dùng chỉ để bỏ bốn lệnh `new` | Wiring thủ công đang gây vấn đề gì? | Dự án đã dùng một framework bắt buộc container |
| Không dùng interface nào để “ít code” | Business có đang tạo thẳng chi tiết hạ tầng không? | Concrete dependency thật sự ổn định và phù hợp |

**Đơn giản không có nghĩa tối thiểu số class bằng mọi giá.** Một class vừa xử lý nghiệp vụ vừa mở network, chọn implementation và đóng pool có thể ít file nhưng rất khó thay đổi. Mục tiêu là **ít phức tạp hơn mà vẫn tách đúng trách nhiệm**, không phải loại bỏ mọi abstraction.

## 16. Bài tập thực hành

**Bài tập 1 — Bắt đầu đơn giản.** Một chương trình CLI chỉ tính phí STANDARD. Viết `FixedQuoteService` nhận `FeePolicy` qua constructor, tạo `StandardFeePolicy` tại `main` và kiểm thử bằng fake trả 999 VND. Giải thích vì sao selector hoặc DI container chưa cần thiết.

**Bài tập 2 — Chọn theo request.** Sửa use case để xử lý luân phiên EXPRESS, STANDARD, EXPRESS. Không được có `setPolicy(...)` trên singleton. Dùng `FeePolicySelector`, assert ba kết quả và chứng minh lựa chọn không phụ thuộc thứ tự gọi.

**Bài tập 3 — Chỉ bọc nhánh cần đo.** Dùng `CountingFeePolicy` cho EXPRESS, không bọc STANDARD. Kiểm tra giá gốc không đổi và counter chỉ tăng ở nhánh EXPRESS. Nếu yêu cầu chuyển sang đo *số lần tính thành công*, cần đổi dòng tăng counter ở đâu?

**Bài tập 4 — Factory hay dữ liệu của lời gọi?** So sánh `Shipment` (DTO chứa mã đơn và cân nặng) với `PaymentSession` (giữ connection cần đóng sau mỗi transaction). Đối tượng nào cần factory? Đối tượng nào nên tạo/truyền trực tiếp? Giải thích theo ownership thay vì theo tên lớp.

**Bài tập 5 — Chỉ ra overengineering.** Một graph `Service → Registry → Factory → Provider → Policy` được dùng chỉ cho một policy cố định. Đề xuất phiên bản dùng constructor injection và composition root; liệt kê hành vi nào phải được kiểm thử trước và sau refactor để đảm bảo không đổi nghiệp vụ.

**Bài tập 6 — Khi nhiều mẫu thật sự cần.** Hệ thống có STANDARD/EXPRESS, SDK ngoài, timeout, metrics và transaction ngắn hạn. Vẽ graph chỉ gồm những thành phần giải quyết các vấn đề đó. Xác định ai chọn implementation, ai tạo transaction, ai sở hữu HTTP client và thứ tự đóng.

**Bài tập 7 — Đánh giá hai phương án đối cực.** Phương án A dùng 15 lớp factory/registry cho phép tính 20 dòng; phương án B đặt toàn bộ tính phí, network và resource cleanup vào một service tự `new` tất cả. Đề xuất phương án thứ ba đủ tách ranh giới nhưng không tạo tầng chuyển tiếp vô nghĩa.

### Câu hỏi tự kiểm tra

1. Có một implementation cố định thì selector có là điều kiện bắt buộc của DI không?
2. Strategy và Factory khác nhau về vấn đề chúng giải quyết ở đâu?
3. Khi một singleton phục vụ nhiều request, vì sao không nên đổi field `currentPolicy` ở mỗi request?
4. Tạo DTO bằng `new` có vi phạm DI không?
5. Một decorator đếm số lần gọi có tự tương đương decorator đếm số lần thành công không?
6. Một session có tuổi thọ transaction có nên được inject trực tiếp vào singleton không?
7. Tại sao có interface chưa đủ để kết luận cần Adapter?
8. Có thể dùng DI container mà không có Decorator hoặc Selector không?
9. Khi nào một graph dùng năm kỹ thuật có thể hợp lý?
10. Dựa vào tiêu chí nào để quyết định giữ hay bỏ abstraction?

**Gợi ý:** (1) Không; (2) Strategy đại diện thuật toán thay thế được, Factory quản lý cấp instance; (3) các request có thể ghi đè lựa chọn; (4) không, DTO là dữ liệu per-call; (5) không, vị trí đo khác nhau; (6) thường không, cần scope/factory phù hợp; (7) Adapter chỉ có ý nghĩa khi có sự khác biệt API/semantics cần chuyển đổi; (8) có; (9) khi từng kỹ thuật giải quyết yêu cầu độc lập; (10) trách nhiệm, chi phí thay đổi, testability, lifetime và ownership.

## Ghi nhớ

- **Đi từ vấn đề, không đi từ danh sách mẫu.** Xác định điều gì thay đổi, thời điểm lựa chọn và quyền sở hữu tài nguyên.
- **Constructor injection và composition root** thường là điểm khởi đầu đủ rõ để lắp object graph bằng Java thuần.
- **Strategy/selector** phù hợp cho nhiều thuật toán có tiêu chí lựa chọn; **factory/provider** phù hợp khi cần kiểm soát thời điểm tạo và vòng đời instance.
- **Adapter** bảo vệ hợp đồng ứng dụng khỏi API ngoài; **Decorator** thêm hành vi bọc với ngữ nghĩa rõ. Chỉ thêm khi yêu cầu có thật.
- **Scope và lifecycle** phải dựa vào trạng thái, thread-safety và ownership, không dựa vào số lượng pattern được sử dụng.
- **DI container tự động hóa việc lắp ghép**, không phải thước đo chất lượng kiến trúc. Unit test bằng fake nên vẫn đơn giản.
- **Thiết kế tốt đủ phức tạp để đúng, nhưng không phức tạp hơn mức cần thiết.**
