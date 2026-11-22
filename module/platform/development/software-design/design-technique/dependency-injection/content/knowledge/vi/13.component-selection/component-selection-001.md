# Một hợp đồng có nhiều triển khai và nơi quyết định lựa chọn

Một ứng dụng Java có thể định nghĩa **một hợp đồng (contract)** nhưng cung cấp **nhiều cách thực hiện (implementation)**. Chẳng hạn, cùng hợp đồng tính phí vận chuyển có thể có chính sách **tiêu chuẩn** và **giao nhanh**. Cả hai đều tính phí từ một yêu cầu giao hàng, nhưng áp dụng quy tắc khác nhau.

Trong **Dependency Injection (DI)**, vấn đề không chỉ là viết interface và truyền nó vào constructor. Ta còn phải trả lời: **thành phần nào được quyền chọn implementation cụ thể, chọn vào thời điểm nào và lựa chọn đó có thay đổi giữa các lần xử lý không?**

Đây là nội dung cốt lõi của chương **Lựa chọn thành phần**. Khi tách việc *chọn phụ thuộc* khỏi việc *sử dụng phụ thuộc*, ta thực hành **Inversion of Control (IoC)** và giữ lớp nghiệp vụ dễ kiểm thử bằng Java thuần. Sau đó, DI container có thể tự động hóa một phần việc lắp ghép nhưng vẫn phải tuân theo cùng các quyết định thiết kế.

## 1. Một contract, nhiều implementation là gì?

Giả sử ứng dụng cần tính phí giao hàng từ vùng nhận và khối lượng:

```java
interface DeliveryFeePolicy {
    long calculate(Shipment shipment);
}
```

Hai implementation có thể cùng đáp ứng contract này:

```text
                  DeliveryFeePolicy
                calculate(Shipment)
                    ▲         ▲
                    │         │
          implements│         │implements
                    │         │
       StandardDelivery   ExpressDelivery
           FeePolicy          FeePolicy
                    ▲         ▲
                    │         │
                Được chọn tại composition root
                    │
                    ▼
              ShippingService
              nhận DeliveryFeePolicy
              qua constructor
```

`ShippingService` cần **năng lực tính phí**, không cần biết mã thực thi của chính sách tiêu chuẩn hay giao nhanh. Khi service gọi `policy.calculate(request)`, Java dispatch đến implementation đã được truyền cho nó.

Có ba vai trò tách biệt:

| Vai trò | Trách nhiệm | Ví dụ |
|---|---|---|
| **Contract / abstraction** | Quy định hành vi mà consumer cần | `DeliveryFeePolicy.calculate(...)` |
| **Implementation** | Cung cấp thuật toán hoặc tích hợp cụ thể theo contract | `StandardDeliveryFeePolicy`, `ExpressDeliveryFeePolicy` |
| **Selection / composition** | Quyết định implementation nào được cấp cho consumer trong hoàn cảnh hiện tại | `main`, factory cấu hình, composition root |

Một contract có nhiều implementation **không tự động là DI**. Nếu `ShippingService` tự viết `new ExpressDeliveryFeePolicy()` trong constructor hoặc method, service vẫn tự lựa chọn implementation. DI xuất hiện khi collaborator được **cung cấp từ bên ngoài**, để service tập trung sử dụng hành vi.

## 2. Phân biệt lựa chọn tại startup và lựa chọn cho từng yêu cầu

Hai câu hỏi cần được trả lời trước khi viết mã:

1. **Ai nắm thông tin để lựa chọn?** Cấu hình triển khai, môi trường chạy, tenant, dữ liệu một yêu cầu hay chính sách nghiệp vụ?
2. **Lựa chọn ổn định trong bao lâu?** Suốt vòng đời của service, trong một request, một transaction, hay thay đổi theo mỗi lời gọi?

Nếu chính sách giao hàng được chọn **khi khởi động ứng dụng**, composition root có thể đọc `DELIVERY_MODE=STANDARD` rồi tạo một `StandardDeliveryFeePolicy` và inject vào `ShippingService`. Tất cả lời gọi tiếp theo của service dùng chính sách đó, cho tới khi một graph mới được lắp với cấu hình khác.

Nếu **khách hàng chọn tiêu chuẩn hoặc giao nhanh cho từng đơn**, việc lựa chọn phải dựa vào dữ liệu của **lần gọi hiện tại**. Khi ấy thường nên cung cấp một `DeliveryFeePolicySelector` hoặc factory chuyên biệt và truyền `deliveryMode` theo phương thức. Không nên gắn một mode cố định vào singleton nếu yêu cầu nghiệp vụ thay đổi theo từng lần xử lý.

| Điều kiện chọn | Khi nào chọn? | Cách tổ chức thường phù hợp |
|---|---|---|
| Cấu hình triển khai cố định cho một instance ứng dụng | Lúc composition | Composition root tạo một implementation rồi inject |
| Chạy test thay implementation hạ tầng bằng fake | Khi dựng đối tượng test | Test inject fake qua constructor |
| Mỗi request mang lựa chọn giao hàng | Khi xử lý request | Inject selector/factory; phương thức nhận mode của request |
| Plugin được tìm theo khóa ở runtime | Khi host tải hoặc chọn plugin | Registry/factory ở ranh giới plugin, giữ API chuyên biệt |
| Một use case cần **tất cả** bộ xử lý tương thích | Khi dựng graph hoặc chạy pipeline | Inject collection các handler với quy tắc thứ tự và trách nhiệm rõ ràng |

Tên interface hoặc kiểu Java không quyết định phạm vi lựa chọn. Hai triển khai có thể cùng thread-safe, nhưng vẫn cần chọn theo từng request vì **quy tắc nghiệp vụ**; ngược lại, một triển khai có state riêng có thể cần factory tạo mới thay vì dùng chung.

## 3. Thiết kế khiến consumer tự quyết định implementation

Cách viết sau đưa quyết định lựa chọn vào lớp nghiệp vụ:

```java
// Phác họa phản ví dụ, giả định các kiểu đã tồn tại.
final class ShippingService {
    ShippingQuote quote(Shipment shipment, String mode) {
        DeliveryFeePolicy policy;

        if ("EXPRESS".equals(mode)) {
            policy = new ExpressDeliveryFeePolicy();
        } else {
            policy = new StandardDeliveryFeePolicy();
        }

        return new ShippingQuote(
            shipment.zone(), shipment.weightKg(),
            policy.calculate(shipment)
        );
    }
}
```

Lớp này vừa xử lý use case, vừa biết hai implementation và tự tạo chúng. Cách viết còn âm thầm chọn tiêu chuẩn cho **mọi giá trị khác `EXPRESS`**, kể cả cấu hình sai chính tả. Những hậu quả thường thấy:

- Thêm một implementation buộc sửa `ShippingService` và các nhánh lựa chọn của nó.
- Kiểm thử không thể đơn giản truyền fake vào constructor để kiểm soát thuật toán tính phí.
- Nếu mỗi implementation cần cấu hình, client hoặc tài nguyên riêng, business service sẽ dần ôm cả nhiệm vụ khởi tạo hạ tầng.
- Lựa chọn fallback ngầm có thể làm sai nghiệp vụ; trong lĩnh vực nhạy cảm, chọn nhầm cổng thanh toán hoặc nguồn dữ liệu còn có thể ảnh hưởng quyền truy cập.
- Nếu logic phân nhánh xuất hiện ở nhiều service, các nơi có thể chọn implementation không nhất quán.

Không phải **mọi câu lệnh `if` trong nghiệp vụ** đều là lỗi DI. Một nhánh phân loại đơn hàng, tính thuế hay áp dụng quy tắc theo dữ liệu có thể là logic nghiệp vụ hợp lệ. Vấn đề cụ thể ở đây là lớp điều phối use case đồng thời **chọn và tạo các cộng tác viên có vòng đời/cấu hình riêng**. Ta nên tách trách nhiệm tạo và chọn thành phần tới nơi phù hợp.

## 4. Ví dụ Java 17: chọn một implementation ở composition root

Ví dụ này cho phép triển khai hai chính sách phí giao hàng, nhưng `ShippingService` chỉ biết `DeliveryFeePolicy`. Một hàm `compose(...)` đóng vai trò composition root: parse cấu hình, từ chối mode không hợp lệ, chọn implementation và cấp nó vào constructor.

Lưu **toàn bộ** mã vào file `ComponentSelectionDemo.java`:

```java
import java.util.Locale;
import java.util.Objects;

public final class ComponentSelectionDemo {

    enum DeliveryMode {
        STANDARD, EXPRESS;

        static DeliveryMode parse(String raw) {
            if (raw == null || raw.isBlank()) {
                throw new IllegalArgumentException(
                    "DELIVERY_MODE is required");
            }
            try {
                return DeliveryMode.valueOf(
                    raw.strip().toUpperCase(Locale.ROOT));
            } catch (IllegalArgumentException cause) {
                throw new IllegalArgumentException(
                    "Unsupported DELIVERY_MODE: " + raw, cause);
            }
        }
    }

    // Dữ liệu của từng lần báo giá.
    record Shipment(String zone, int weightKg) {
        Shipment {
            if (!"LOCAL".equals(zone) && !"REMOTE".equals(zone)) {
                throw new IllegalArgumentException("Unknown zone");
            }
            if (weightKg <= 0) {
                throw new IllegalArgumentException(
                    "weightKg must be positive");
            }
        }
    }

    record ShippingQuote(
        String zone, int weightKg, long amountVnd) {}

    // Contract mà use case thực sự cần.
    @FunctionalInterface
    interface DeliveryFeePolicy {
        long calculate(Shipment shipment);
    }

    static final class StandardDeliveryFeePolicy
            implements DeliveryFeePolicy {

        @Override
        public long calculate(Shipment shipment) {
            Objects.requireNonNull(shipment, "shipment");

            long base = "LOCAL".equals(shipment.zone())
                ? 10_000L : 20_000L;

            return Math.addExact(
                base, Math.multiplyExact(shipment.weightKg(), 2_000L));
        }
    }

    static final class ExpressDeliveryFeePolicy
            implements DeliveryFeePolicy {

        @Override
        public long calculate(Shipment shipment) {
            Objects.requireNonNull(shipment, "shipment");

            long base = "LOCAL".equals(shipment.zone())
                ? 25_000L : 40_000L;

            return Math.addExact(
                base, Math.multiplyExact(shipment.weightKg(), 5_000L));
        }
    }

    static final class ShippingService {
        private final DeliveryFeePolicy policy;

        // Constructor injection: implementation cụ thể do caller chọn.
        ShippingService(DeliveryFeePolicy policy) {
            this.policy = Objects.requireNonNull(policy, "policy");
        }

        ShippingQuote quote(Shipment shipment) {
            Objects.requireNonNull(shipment, "shipment");
            long amount = policy.calculate(shipment);

            return new ShippingQuote(
                shipment.zone(), shipment.weightKg(), amount);
        }
    }

    // Composition root tối giản, không cần DI container.
    static ShippingService compose(String rawMode) {
        DeliveryMode mode = DeliveryMode.parse(rawMode);

        DeliveryFeePolicy selected = switch (mode) {
            case STANDARD -> new StandardDeliveryFeePolicy();
            case EXPRESS -> new ExpressDeliveryFeePolicy();
        };

        return new ShippingService(selected);
    }

    public static void main(String[] args) {
        if (args.length > 1) {
            throw new IllegalArgumentException(
                "Usage: java ComponentSelectionDemo [STANDARD|EXPRESS]");
        }

        // Mặc định trong demo khi không truyền đối số.
        String mode = args.length == 0 ? "STANDARD" : args[0];

        ShippingService service = compose(mode);
        System.out.println(
            service.quote(new Shipment("LOCAL", 3)));
        System.out.println(
            service.quote(new Shipment("REMOTE", 2)));
    }
}
```

Chạy bằng JDK 17 trở lên:

```bash
javac ComponentSelectionDemo.java
java ComponentSelectionDemo STANDARD
```

Kết quả:

```text
ShippingQuote[zone=LOCAL, weightKg=3, amountVnd=16000]
ShippingQuote[zone=REMOTE, weightKg=2, amountVnd=24000]
```

Thay cấu hình lựa chọn:

```bash
java ComponentSelectionDemo EXPRESS
```

Kết quả:

```text
ShippingQuote[zone=LOCAL, weightKg=3, amountVnd=40000]
ShippingQuote[zone=REMOTE, weightKg=2, amountVnd=50000]
```

Trong ví dụ, `Shipment` và `ShippingQuote` là dữ liệu của từng lần gọi và kết quả. Giá trị VND dùng `long` vì phí được mô hình hóa bằng số nguyên; hệ thống tính tiền thực tế cần xác định đơn vị, chính sách làm tròn và những giới hạn khác. `Math.multiplyExact` và `Math.addExact` giúp lỗi tràn số xuất hiện rõ ràng.

### Đọc vị trí của quyết định

Lệnh `switch` xuất hiện trong `compose(...)`, nơi tạo graph:

```java
DeliveryMode mode = DeliveryMode.parse(rawMode);

DeliveryFeePolicy selected = switch (mode) {
    case STANDARD -> new StandardDeliveryFeePolicy();
    case EXPRESS -> new ExpressDeliveryFeePolicy();
};

return new ShippingService(selected);
```

`compose(...)` biết các lớp cụ thể. `ShippingService` chỉ lưu một `DeliveryFeePolicy` và gọi `calculate(...)`. Khi thêm `EconomyDeliveryFeePolicy`, ta cập nhật cách chọn và cấu hình ở composition root; với điều kiện hợp đồng `calculate` vẫn giữ nguyên, không phải sửa logic `quote(...)`.

Dòng `return new ShippingService(selected)` là **constructor injection**. Người đọc constructor thấy rõ service cần một policy; object graph được lắp có chủ đích bằng Java thuần.

### Lựa chọn của demo ổn định đến khi nào?

Mỗi lần gọi `compose("STANDARD")` tạo một `ShippingService` dùng policy tiêu chuẩn; mỗi lần gọi `compose("EXPRESS")` tạo một service khác dùng policy giao nhanh. Sau khi service được tạo, ví dụ **không đổi policy của instance đang tồn tại**.

Điều này phù hợp khi mode là **cấu hình của một ứng dụng hoặc một phiên hoạt động**, và tất cả công việc của service đó tuân theo chính sách đã chọn. Nếu mode thực sự do người dùng chọn mỗi lần, ta phải đổi thiết kế theo mục 7 thay vì thay field policy của service dùng chung.

### Vì sao nên báo lỗi khi gặp mode không biết?

`DeliveryMode.parse(...)` từ chối giá trị không hợp lệ. Ví dụ có một **mặc định được công bố rõ** khi chạy demo không truyền đối số, nhưng không âm thầm chuyển `"EXPRSES"` thành `STANDARD`.

Với cấu hình production, mặc định có được phép hay không là quyết định của hệ thống. Nếu một lựa chọn ảnh hưởng quyền truy cập, cách thanh toán hoặc môi trường dữ liệu, nên xác minh rõ khóa cấu hình và **fail fast** khi không thể chọn an toàn.

## 5. Kiểm thử: thay implementation mà không sửa use case

DI phát huy giá trị khi ta có thể kiểm thử logic điều phối độc lập với thuật toán thật. Với `ShippingService`, test có thể truyền một fake policy:

```java
DeliveryFeePolicy fake = shipment -> 7_000L;
ShippingService service = new ShippingService(fake);
ShippingQuote quote = service.quote(new Shipment("LOCAL", 3));
```

*Đây là phác họa sử dụng các kiểu lồng nhau trong `ComponentSelectionDemo`; chương trình kiểm thử đầy đủ ở dưới.*

Lưu `ComponentSelectionCheck.java` cạnh `ComponentSelectionDemo.java`:

```java
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

public final class ComponentSelectionCheck {
    public static void main(String[] args) {
        AtomicInteger calls = new AtomicInteger();
        AtomicReference<String> lastInput = new AtomicReference<>();

        ComponentSelectionDemo.DeliveryFeePolicy fake = shipment -> {
            calls.incrementAndGet();
            lastInput.set(
                shipment.zone() + ":" + shipment.weightKg());
            return 7_000L;
        };

        var service = new ComponentSelectionDemo.ShippingService(fake);
        var result = service.quote(
            new ComponentSelectionDemo.Shipment("LOCAL", 3));

        if (calls.get() != 1
                || !"LOCAL:3".equals(lastInput.get())
                || result.amountVnd() != 7_000L) {
            throw new AssertionError(
                "ShippingService did not use injected policy");
        }

        // Cùng một contract, cấu hình khác → behavior khác.
        var standard = ComponentSelectionDemo.compose("STANDARD");
        var express = ComponentSelectionDemo.compose("EXPRESS");
        var request = new ComponentSelectionDemo.Shipment("LOCAL", 3);

        if (standard.quote(request).amountVnd() != 16_000L) {
            throw new AssertionError("Wrong standard selection");
        }
        if (express.quote(request).amountVnd() != 40_000L) {
            throw new AssertionError("Wrong express selection");
        }

        boolean rejected = false;
        try {
            ComponentSelectionDemo.compose("EXPRSES");
        } catch (IllegalArgumentException expected) {
            rejected = true;
        }
        if (!rejected) {
            throw new AssertionError(
                "Unknown configuration must be rejected");
        }

        System.out.println("PASS");
    }
}
```

Chạy:

```bash
javac ComponentSelectionDemo.java ComponentSelectionCheck.java
java ComponentSelectionCheck
```

Kết quả dự kiến: `PASS`.

Chương trình tách rõ hai loại kiểm thử:

1. **Kiểm thử consumer:** `ShippingService` dùng đúng collaborator được truyền vào, chuyển đúng `Shipment` và trả đúng kết quả. Fake kiểm soát giá, nên không phụ thuộc công thức của implementation thật.
2. **Kiểm thử composition:** `STANDARD` và `EXPRESS` chọn đúng implementation, còn cấu hình không nhận diện được bị từ chối.

Kiểm thử từng thuật toán `StandardDeliveryFeePolicy` và `ExpressDeliveryFeePolicy` là trách nhiệm riêng. Với các implementation kết nối tới database, HTTP hoặc broker, vẫn cần integration test và kiểm tra hợp đồng của những tài nguyên đó.

## 6. Thêm implementation mới mà không tăng trách nhiệm service

Giả sử muốn hỗ trợ chế độ **tiết kiệm** khi có một chính sách giá mới. Một thiết kế mở rộng có thể thực hiện:

1. Thêm giá trị `ECONOMY` vào kiểu `DeliveryMode`.
2. Viết `EconomyDeliveryFeePolicy implements DeliveryFeePolicy`.
3. Bổ sung nhánh chọn `ECONOMY` trong composition root.
4. Kiểm thử công thức mới và mapping cấu hình tới implementation mới.

`ShippingService` không cần thêm `if` hoặc import class `EconomyDeliveryFeePolicy`. Nó vẫn gọi `policy.calculate(shipment)`.

Tuy nhiên, cần hiểu chính xác nguyên lý **Open/Closed Principle (OCP)**: một module có thể được thiết kế để mở rộng qua contract mà không sửa logic consumer, nhưng **mã quyết định lựa chọn ở ranh giới composition vẫn có thể cần cập nhật** khi có một cấu hình hoặc lựa chọn mới. Không phải bất kỳ dòng `switch` nào tồn tại ở composition root cũng là vi phạm OCP.

Khi số lượng implementation lớn và được bổ sung từ plugin, composition root có thể dùng **registration map, factory hoặc plugin discovery** để thay thế `switch` dài. Việc dùng cơ chế động mang lại chi phí riêng về validation, thứ tự ưu tiên, tương thích contract, khởi tạo và dọn dẹp tài nguyên.

## 7. Khi mỗi request được quyền chọn implementation

Ở ví dụ chính, `compose(...)` chọn một policy khi tạo service. Giờ giả sử khách hàng chọn `STANDARD` hoặc `EXPRESS` cho **mỗi đơn hàng**. Nếu một `ShippingService` dùng chung phải phục vụ nhiều khách, ta không nên đổi một field `policy` chung trước mỗi lần tính giá:

```java
// Phản ví dụ: service dùng chung có trạng thái lựa chọn toàn cục.
final class MutableShippingService {
    private DeliveryFeePolicy currentPolicy;

    void setPolicy(DeliveryFeePolicy policy) {
        currentPolicy = policy;
    }

    ShippingQuote quote(Shipment shipment) {
        long amount = currentPolicy.calculate(shipment);
        return new ShippingQuote(
            shipment.zone(), shipment.weightKg(), amount);
    }
}
```

Nếu hai request đồng thời gọi `setPolicy(...)` rồi `quote(...)`, request A có thể tính tiền bằng policy vừa bị request B thay thế. Ngay cả khi chương trình chạy tuần tự, API này vẫn phụ thuộc vào một lệnh gọi trước đó và làm khó việc kiểm thử.

Một cách rõ ràng hơn là đưa **quyền lựa chọn tại thời điểm xử lý** vào một collaborator có trách nhiệm hẹp:

```java
interface DeliveryFeePolicySelector {
    DeliveryFeePolicy select(DeliveryMode mode);
}

final class RequestBasedShippingService {
    private final DeliveryFeePolicySelector selector;

    RequestBasedShippingService(DeliveryFeePolicySelector selector) {
        this.selector = Objects.requireNonNull(selector);
    }

    ShippingQuote quote(Shipment shipment, DeliveryMode requestedMode) {
        Objects.requireNonNull(shipment);
        Objects.requireNonNull(requestedMode);

        DeliveryFeePolicy policy = selector.select(requestedMode);
        long amount = policy.calculate(shipment);

        return new ShippingQuote(
            shipment.zone(), shipment.weightKg(), amount);
    }
}
```

*Đoạn mã này minh họa một biến thể khi `DeliveryMode`, `Shipment`, `ShippingQuote` và `DeliveryFeePolicy` đã được định nghĩa như trong ví dụ chính. Nếu đặt các lớp ở file độc lập, cần thêm import và dùng tên kiểu phù hợp.*

Composition root có thể triển khai selector bằng một map bất biến:

```java
Map<DeliveryMode, DeliveryFeePolicy> policies = Map.of(
    DeliveryMode.STANDARD, new StandardDeliveryFeePolicy(),
    DeliveryMode.EXPRESS, new ExpressDeliveryFeePolicy()
);

DeliveryFeePolicySelector selector = requestedMode -> {
    DeliveryFeePolicy selected = policies.get(
        Objects.requireNonNull(requestedMode));
    if (selected == null) {
        throw new IllegalArgumentException(
            "No policy registered for " + requestedMode);
    }
    return selected;
};

RequestBasedShippingService service =
    new RequestBasedShippingService(selector);
```

Ở biến thể này, **constructor injection** cung cấp selector cho service; **tham số `requestedMode`** là dữ liệu của lời gọi; selector thực hiện việc chọn implementation. Đây là một dạng **strategy selection** có chủ đích. Không có thao tác thay field dùng chung nên các request có thể chọn độc lập, với điều kiện các policy được chia sẻ an toàn theo hợp đồng.

Một selector biết tất cả implementation phù hợp với một nhóm nghiệp vụ có phạm vi hẹp hơn nhiều so với `GlobalServices.get(Class<?>)` hoặc việc truyền nguyên `ApplicationContext` vào service. Khi service tự tìm mọi loại dependency từ một registry tổng quát, code có xu hướng **Service Locator** và khó nhìn thấy phụ thuộc thật.

### Chọn theo request có luôn cần tạo instance mới?

Không. Hai quyết định cần tách riêng:

- **Chọn implementation nào:** `STANDARD` hay `EXPRESS`.
- **Tạo/chia sẻ instance ra sao:** một policy bất biến dùng chung, một instance theo request, hay mỗi lần cần thì tạo mới.

Nếu cả hai policy là thuật toán bất biến và thread-safe, selector có thể trả về những instance đã được lắp sẵn. Nếu một policy cần trạng thái transaction hoặc tài nguyên ngắn hạn, selector/factory phải tuân theo scope và ownership phù hợp. **Đổi lựa chọn theo request không đồng nghĩa cấp lại toàn bộ dependency graph theo request.**

## 8. Khi nào dùng factory thay cho selector?

Một **selector** thường trả về thành phần phù hợp từ những lựa chọn hiện có. Một **factory** có thể tạo instance mới, cấu hình instance hoặc cấp tài nguyên theo scope. Cả hai có thể được biểu diễn bằng một interface chuyên biệt; tên gọi không quan trọng bằng hợp đồng.

| Nhu cầu | API minh họa | Ý nghĩa |
|---|---|---|
| Chọn policy có sẵn | `selector.select(mode)` | Tìm implementation tương ứng mode |
| Tạo một processor mới | `factory.create(requestConfig)` | Mỗi lần có thể là một instance khác |
| Mượn tài nguyên giao dịch | `unitOfWorkFactory.open()` | Caller phải kết thúc scope và trả/đóng tài nguyên |
| Lựa chọn tại startup | `compose(settings)` | Chọn và lắp graph rồi trả service đã cấu hình |

Nếu factory tạo một `AutoCloseable` mỗi lần gọi, cần xác định caller có chịu trách nhiệm `close()` hay container sẽ quản lý nó. Không nên inject một instance chỉ sống trong transaction vào service có vòng đời toàn ứng dụng rồi giữ lâu. Khi dùng nhà cung cấp theo mỗi lời gọi, cần hiểu **thời điểm phân giải** và **thời điểm giải phóng**.

## 9. Nhiều implementation trong cùng một graph: chọn một hay cần tất cả?

Không phải lúc nào “một interface có nhiều implementation” cũng có nghĩa **chọn đúng một implementation**. Ví dụ hệ thống cần thực hiện tất cả rule kiểm tra cho đơn hàng, hoặc gửi cùng một sự kiện tới nhiều đích.

Nếu use case cần **một handler duy nhất**, chính sách lựa chọn cần trả về một handler:

```text
PaymentMethod
    │
    ▼
GatewaySelector ──► một PaymentGateway cụ thể
    │
    ▼
ChargeService
```

Nếu use case cần **nhiều handler cùng tham gia**, có thể inject collection:

```java
interface OrderRule {
    void validate(OrderRequest request);
}

final class OrderValidator {
    private final List<OrderRule> rules;

    OrderValidator(List<OrderRule> rules) {
        this.rules = List.copyOf(Objects.requireNonNull(rules));
    }

    void validate(OrderRequest request) {
        for (OrderRule rule : rules) {
            rule.validate(request);
        }
    }
}
```

*Đây là ví dụ kiến trúc riêng, giả định kiểu `OrderRequest` và import `List`, `Objects` tồn tại.*

Với collection, phải xác định **thứ tự chạy**, quy tắc dừng khi lỗi, cách xử lý trùng registration và liệu mỗi handler được chạy đúng một lần hay không. Nếu thứ tự ảnh hưởng kết quả, đừng dựa vào thứ tự không được bảo đảm của map hoặc thứ tự đăng ký ngẫu nhiên.

Đôi khi một hành vi cần chạy **theo chuỗi decorator**, ví dụ `LoggingPaymentGateway` bọc `RetryingPaymentGateway` bọc `HttpPaymentGateway`. Đây là bài toán **lắp chuỗi cộng tác viên**, không phải tìm một trong nhiều gateway. Composition root chịu trách nhiệm xác định thứ tự bọc và ownership cho toàn chuỗi.

## 10. DI container sẽ làm gì khi có nhiều implementation?

Trong Java thuần, composition root viết rõ:

```java
DeliveryFeePolicy policy = new ExpressDeliveryFeePolicy();
ShippingService service = new ShippingService(policy);
```

Với DI container, ta đăng ký các implementation và cấu hình cách container **chọn dependency phù hợp**. Nhiều container dùng cơ chế như *qualifier/name*, *primary/default registration*, key, profile hoặc factory binding. Chi tiết cú pháp và độ ưu tiên khác nhau giữa framework và version; không nên suy ra rằng framework nào cũng tự chọn đúng implementation khi nhiều object cùng thỏa một interface.

Các câu hỏi cần trả lời:

1. Nếu có **hai registration cùng type**, framework báo lỗi mơ hồ, chọn mặc định, hay lấy registration cuối? Chính sách đó có được công bố rõ không?
2. Nếu dùng **qualifier hoặc name**, tên có được kiểm tra và tập trung quản lý không, hay nằm rải rác trong nghiệp vụ?
3. Nếu chọn theo **profile/config**, cấu hình thiếu hoặc sai được phát hiện lúc startup hay tới khi dependency được resolve?
4. Nếu dùng collection, **thứ tự và số lượng** các implementation có được kiểm soát không?
5. Nếu một implementation có scope ngắn hơn consumer, container có phát hiện hoặc hỗ trợ provider/proxy phù hợp không?
6. Nếu implementation có tài nguyên cần đóng, **ai sở hữu và đóng nó** khi đổi scope hoặc shutdown?

Tư duy kiến trúc giữ nguyên:

```text
Java thuần:
  settings → composition root → selected implementation
                           → consumer constructor

DI container:
  settings/bindings → container composition → selected implementation
                                          → consumer constructor
```

**Container tự động hóa việc lắp ghép**, còn **quy tắc lựa chọn đúng** phải do người thiết kế xác định. Gọi `container.getBean(...)` hoặc `resolve(...)` trực tiếp từ business service để tự tìm mọi dependency là kiểu tra cứu gần với Service Locator. Nếu chỉ dùng API tra cứu ở composition root để lấy một collaborator rồi truyền vào constructor, service vẫn có hợp đồng DI tường minh.

## 11. Trường hợp cấu hình thay đổi khi ứng dụng đang chạy

Một lựa chọn có thể được cập nhật bởi feature flag, tenant config hoặc chính sách phát hành. Lúc đó cần xác định **khi nào thay đổi có hiệu lực**:

- **Một lần lúc startup:** tạo một graph từ snapshot cấu hình. Thay đổi áp dụng sau khi tái khởi động hoặc dựng graph mới.
- **Tại đầu mỗi request:** selector đọc snapshot chính sách được cập nhật an toàn, rồi giữ lựa chọn ổn định cho yêu cầu đó.
- **Tại từng thao tác nhỏ:** factory/selector được gọi theo từng thao tác, nhưng phải bảo đảm nhất quán trong một transaction nếu yêu cầu nghiệp vụ cần.

Một request thanh toán không nên vô tình đổi gateway ở giữa quy trình chỉ vì feature flag cập nhật giữa hai bước. Có thể cần cố định **snapshot lựa chọn** cho cả đơn vị công việc, lưu lại implementation ID trong audit hoặc bảo đảm retry dùng chính sách tương thích.

Nếu chuyển implementation có tài nguyên (pool, HTTP client, worker), không nên đóng instance cũ ngay khi có cấu hình mới nếu vẫn còn request đang sử dụng nó. Cần một kế hoạch thay thế theo lifecycle: tạo instance mới, kiểm tra readiness, chuyển luồng công việc, chờ những lời gọi cũ hoàn tất, rồi đóng tài nguyên cũ theo đúng ownership.

Đây là vấn đề riêng của cập nhật runtime và concurrency, không được giải quyết chỉ bằng việc thêm một annotation DI.

## 12. Các lỗi thường gặp khi chọn thành phần

| Biểu hiện | Vì sao có vấn đề | Cách cải thiện |
|---|---|---|
| Business service tự `new` implementation theo cấu hình | Gắn logic use case với composition | Chọn tại root hoặc inject selector/factory có nhiệm vụ rõ |
| Có nhiều implementation nhưng không chỉ rõ cái nào cần | Có thể chọn sai hoặc lỗi mơ hồ khi resolve | Cấu hình key/qualifier/registration tường minh |
| Mọi giá trị sai đều fallback về mặc định | Dễ che lỗi cấu hình hoặc sai nghiệp vụ | Validate các giá trị cho phép; fallback chỉ khi có chính sách rõ |
| Đọc biến môi trường trong từng service | Logic chọn phân tán, khó kiểm thử | Parse typed config tại ranh giới composition |
| Một singleton có `setStrategy(...)` cho từng request | Có thể lẫn state giữa các yêu cầu đồng thời | Truyền mode theo method, inject selector bất biến |
| Inject container tổng quát vào toàn bộ lớp nghiệp vụ | Ẩn danh sách collaborator, khó mock | Inject contract thực sự cần |
| Một selector tạo resource mới mỗi lần nhưng không định nghĩa ownership | Rò tài nguyên hoặc đóng nhầm resource dùng chung | Contract cấp/đóng rõ ràng, quản lý scope |
| Chọn implementation theo thứ tự map không ổn định | Kết quả có thể thay đổi khó kiểm soát | Key và thứ tự ưu tiên rõ, có kiểm thử composition |
| Không kiểm thử cấu hình từng nhánh | Có implementation tồn tại nhưng không bao giờ được nối đúng | Test mapping giữa cấu hình và implementation |
| Cho rằng interface tự đảm bảo hai triển khai tương đương | Có thể khác tiền điều kiện, tác dụng phụ và semantics | Viết contract chung, contract test cho implementation |
| Reload cấu hình và đóng client cũ ngay | Request đang chạy còn dùng client cũ | Thay graph/snapshot có kiểm soát và drain trước khi đóng |

## 13. Quy trình tự ra quyết định

Khi một contract có nhiều implementation, hãy trả lời lần lượt:

1. **Ai thật sự nắm quyền lựa chọn?** Hạ tầng triển khai, composition root, caller của use case, tenant hay một policy selector?
2. **Lựa chọn cần ổn định trong phạm vi nào?** Toàn ứng dụng, một request, một transaction hay mỗi lần thực thi?
3. **Có cần đúng một implementation, nhiều implementation cùng chạy, hay một chuỗi decorator?**
4. **Cần tạo mới hay có thể chia sẻ instance?** Xét trạng thái, thread safety và chi phí tạo.
5. **Ai sở hữu tài nguyên?** Đặc biệt khi implementation mở network connection, session hoặc thread.
6. **Cấu hình sai phải gây lỗi ra sao?** Nên fail fast hay dùng fallback được định nghĩa, có cần audit lựa chọn không?
7. **Kiểm thử gì để chứng minh đúng?** Mapping cấu hình, hành vi consumer với fake, contract của từng implementation, scope và đường cleanup.

Một thiết kế thuận lợi sẽ làm cho **quyết định lựa chọn nằm ở đúng nơi có đủ thông tin**, còn các lớp khác chỉ nhận một contract phù hợp. Khi điều kiện chọn thực sự là dữ liệu của lời gọi, giữ nó tường minh trên API method và delegate việc chọn sang collaborator hẹp là cách dễ quan sát và kiểm thử.

## 14. Bài tập thực hành

**Bài tập 1 — Thêm chế độ ECONOMY.** Mở rộng `ComponentSelectionDemo` bằng `EconomyDeliveryFeePolicy` với phí cơ bản 8.000 VND ở `LOCAL`, 16.000 VND ở `REMOTE` và 1.500 VND/kg. Thêm `ECONOMY` vào `DeliveryMode` và mapping ở `compose(...)`. Chạy `java ComponentSelectionDemo ECONOMY`; dự đoán kết quả cho `LOCAL` 3 kg và `REMOTE` 2 kg. Đáp án dự kiến là 12.500 VND và 19.000 VND.

**Bài tập 2 — Kiểm thử không sửa use case.** Viết fake `DeliveryFeePolicy` trả về giá 999 VND và ghi nhận số lần gọi. Tạo `ShippingService(fake)`, gọi hai request và xác minh fake được gọi hai lần. Không sửa `ShippingService` hoặc `compose(...)`.

**Bài tập 3 — Chọn theo request.** Triển khai `DeliveryFeePolicySelector` từ một map các policy dùng chung. Cho một `RequestBasedShippingService` xử lý hai request với mode khác nhau. Giải thích vì sao không cần mutate field policy của singleton.

**Bài tập 4 — Thay đổi runtime có tài nguyên.** Thay policy tính phí bằng hai `RemoteRateClient` sở hữu HTTP client. Mô tả cách tạo, health-check, chuyển request mới sang implementation mới, drain request cũ và đóng client cũ; nêu rõ ai là owner.

**Bài tập 5 — Có nhiều implementation nhưng cần tất cả.** Thiết kế `OrderValidator` chạy `InventoryRule` và `AddressRule` theo thứ tự được chọn. Xác định rõ khi một rule ném lỗi thì có chạy rule sau hay không, và viết test cho thứ tự thực thi.

### Câu hỏi tự kiểm tra

1. Có hai implementation của một interface đã đồng nghĩa hệ thống dùng DI chưa?
2. Vì sao `ShippingService` không nên tự tạo `ExpressDeliveryFeePolicy` nếu ta muốn thay chính sách bằng cấu hình?
3. Khi mode được cố định lúc startup, có cần gọi selector ở mọi request không?
4. Khi mode do khách chọn trong từng đơn, đặt lựa chọn vào constructor của một singleton có vấn đề gì?
5. Qualifier hoặc primary của DI container thay thế được yêu cầu phân tích nghiệp vụ và scope không?
6. Nếu cần chạy tất cả validator, tại sao lựa chọn một implementation duy nhất là sai yêu cầu?
7. Nếu selector tạo một `AutoCloseable` mỗi lần gọi, ai phải đóng resource đó?

**Gợi ý:** (1) Chưa, DI đòi dependency được cung cấp từ ngoài; (2) quyết định triển khai nên ở ranh giới composition hoặc selector; (3) không, có thể inject policy đã chọn; (4) thiếu tính linh hoạt hoặc dễ đua tranh nếu mutate; (5) không; (6) use case yêu cầu collection/pipeline; (7) chủ sở hữu theo contract factory/scope, không suy ra chỉ từ interface.

## Ghi nhớ

- **Một contract có thể có nhiều implementation**, nhưng lớp sử dụng contract nên chỉ biết những hành vi cần thiết của nó.
- **Composition root là nơi phù hợp để chọn implementation theo cấu hình ổn định** và inject đối tượng đã chọn vào constructor.
- **Nếu lựa chọn thay đổi theo từng request**, truyền dữ liệu lựa chọn theo method và inject selector/factory có contract rõ; tránh sửa state dùng chung.
- **Chọn implementation và chọn lifetime là hai quyết định khác nhau.** Cần xét thread safety, scope, ownership và thời điểm cleanup.
- **DI container hỗ trợ đăng ký và phân giải**, nhưng chính sách lựa chọn, xử lý lỗi cấu hình và kiểm thử mapping vẫn do thiết kế ứng dụng quyết định.
- **Java thuần đủ để kiểm chứng quyết định chọn thành phần:** chạy các implementation, inject fake, kiểm thử mapping cấu hình và quan sát rằng consumer không cần thay đổi khi implementation đổi.
