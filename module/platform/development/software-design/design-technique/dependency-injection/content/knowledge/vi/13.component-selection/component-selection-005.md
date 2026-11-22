# Truyền danh sách, tập hợp hoặc bảng tra các chiến lược

## 1. Khi một dependency không chỉ có một implementation

Trong **Dependency Injection (DI)**, một đối tượng nhận các thành phần cộng tác từ bên ngoài thay vì tự tạo chúng. Với **constructor injection**, ta thường gặp trường hợp dịch vụ nhận một interface và composition root cung cấp một implementation:

```java
final class CheckoutService {
    private final PaymentProcessor processor;

    CheckoutService(PaymentProcessor processor) {
        this.processor = java.util.Objects.requireNonNull(
                processor, "processor");
    }
}
```

Nhưng nhiều ứng dụng cần **nhiều implementation của cùng một hợp đồng**:

- Tính giá qua một chuỗi quy tắc giảm giá và phụ phí.
- Chạy nhiều bước kiểm tra dữ liệu độc lập.
- Chọn cách thanh toán theo mã `card`, `bank` hoặc lựa chọn của người dùng.
- Áp dụng nhiều bộ chuyển đổi, formatter, handler hoặc bộ lọc.

Nếu lớp nghiệp vụ viết hàng loạt `new CardProcessor()`, `new BankProcessor()` hoặc `if/else` để tạo adapter cụ thể, quyết định lắp ghép sẽ nằm rải rác trong logic sử dụng. Một giải pháp là **inject cả một cấu trúc chứa các chiến lược**: `List<Strategy>`, `Set<Strategy>` hoặc `Map<Key, Strategy>`.

Ý tưởng chính:

1. **Composition root** chọn, tạo và đưa các implementation vào cấu trúc dữ liệu thích hợp.
2. **Lớp nghiệp vụ** nhận danh sách/tập hợp/bảng tra qua constructor.
3. Tại thời điểm chạy, lớp nghiệp vụ thực hiện **quy tắc điều phối hoặc lựa chọn** dựa trên dữ liệu nghiệp vụ, không tự tạo implementation.

Đây vẫn là Dependency Injection và **Inversion of Control (IoC)** bằng Java thuần. DI container có thể tự tập hợp các bean/implementation về sau, nhưng cần hiểu rõ ý nghĩa **thứ tự, tính duy nhất, khóa, phạm vi và lỗi cấu hình** trước khi dùng khả năng tự động đó.

## 2. Chọn List, Set hay Map dựa trên ngữ nghĩa

Ba cấu trúc có mục đích khác nhau; không nên chọn chỉ vì API dễ gọi.

| Cấu trúc inject | Ngữ nghĩa chính | Tình huống phù hợp | Điều phải quy định |
| --- | --- | --- | --- |
| `List<Strategy>` | Một **chuỗi có thứ tự**, có thể chứa cùng instance nhiều lần. | Pipeline điều chỉnh giá, middleware, chain xử lý theo mức ưu tiên. | Thứ tự thực thi; hành vi khi gặp lỗi; có cho phép trùng hay không. |
| `Set<Strategy>` | Tập các phần tử **không trùng theo `equals/hashCode`**, không cam kết thứ tự theo contract `Set`. | Các validation độc lập, các hook không cần ưu tiên. | Khái niệm “trùng” là gì; có được phụ thuộc thứ tự hay không; cách tổng hợp lỗi. |
| `Map<Key, Strategy>` | Tra một chiến lược theo **khóa duy nhất**. | Chọn processor theo phương thức thanh toán, formatter theo định dạng, exporter theo loại job. | Nguồn gốc/chuẩn hóa khóa; trùng khóa; khóa không tồn tại; thay đổi registry lúc chạy. |

Có hai phân biệt dễ nhầm:

- **Set không có nghĩa “mỗi loại chiến lược chỉ xuất hiện một lần”.** Hai object khác nhau cùng class thường vẫn có thể nằm trong Set nếu chúng không bằng nhau theo `equals`. Nếu cần duy nhất theo *vai trò nghiệp vụ*, hãy định nghĩa khóa vai trò và kiểm tra trùng tại composition root.
- **Map không có nghĩa “không còn logic lựa chọn”.** Map làm việc tra cứu trở nên rõ ràng, nhưng ứng dụng vẫn phải quy định lấy khóa nào từ request, cách kiểm tra quyền sử dụng, xử lý lựa chọn không hợp lệ và cách gọi chiến lược được chọn.

**Quy tắc nhanh:** nếu *thứ tự có ý nghĩa*, ưu tiên `List`; nếu *cần chạy mọi thành phần và không phụ thuộc thứ tự*, xem xét `Set`; nếu *cần chọn một thành phần theo khóa*, ưu tiên `Map`.

## 3. Ví dụ tổng hợp: pipeline giá, tập kiểm tra và bảng tra thanh toán

Giả sử ứng dụng checkout có ba nhóm cộng tác viên:

1. **`PriceRule`** điều chỉnh tổng tiền theo thứ tự (giảm 10% rồi cộng phí dịch vụ).
2. **`CheckoutValidator`** kiểm tra yêu cầu hợp lệ; mọi validator được phép chạy, nhưng không có thứ tự phụ thuộc.
3. **`PaymentProcessor`** thực hiện thanh toán theo phương thức do request chỉ định.

Đồ thị đối tượng:

```text
                         Composition Root
                     (chọn và tạo các adapter)
                               |
          +--------------------+---------------------+
          |                    |                     |
          v                    v                     v
   List<PriceRule>    Set<CheckoutValidator>   Map<String, PaymentProcessor>
   [discount, fee]     {id, amount check}      {"card": ..., "bank": ...}
          \                    |                     /
           \                   |                    /
            +------------------+-------------------+
                               |
                               v
                        CheckoutService
                               |
                               v
                         checkout(request)
                        - validate request
                        - calculate total
                        - select processor
                        - perform payment
```

**Phần phụ thuộc cố định lúc lắp ghép:** các implementation nào được hỗ trợ, danh sách quy tắc tính giá và khóa nào ánh xạ tới processor nào.

**Phần quyết định theo dữ liệu khi chạy:** request cần kiểm tra gì, tổng sau quy tắc là bao nhiêu, và request chọn khóa `card` hay `bank`. Lớp nghiệp vụ không cần biết lớp adapter cụ thể.

### 3.1. Java thuần: một chương trình có thể biên dịch

Lưu mã dưới đây vào `StrategyCollectionDemo.java`. Ví dụ chỉ in thanh toán ra console và **không kết nối cổng thanh toán thật**.

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

final class CheckoutCommand {
    final String orderId;
    final long subtotalVnd;
    final String paymentMethod;

    CheckoutCommand(String orderId, long subtotalVnd,
                    String paymentMethod) {
        this.orderId = orderId;
        this.subtotalVnd = subtotalVnd;
        this.paymentMethod = paymentMethod;
    }
}

// Danh sách: thứ tự PriceRule là một phần của hành vi.
interface PriceRule {
    long apply(long currentTotalVnd);
}

final class TenPercentDiscount implements PriceRule {
    @Override
    public long apply(long currentTotalVnd) {
        return currentTotalVnd - currentTotalVnd / 10;
    }
}

final class FlatServiceFee implements PriceRule {
    private final long feeVnd;

    FlatServiceFee(long feeVnd) {
        if (feeVnd < 0) {
            throw new IllegalArgumentException("Phí không được âm");
        }
        this.feeVnd = feeVnd;
    }

    @Override
    public long apply(long currentTotalVnd) {
        return Math.addExact(currentTotalVnd, feeVnd);
    }
}

// Tập hợp: các validator phải độc lập với thứ tự gọi.
interface CheckoutValidator {
    void validate(CheckoutCommand command);
}

final class OrderIdValidator implements CheckoutValidator {
    @Override
    public void validate(CheckoutCommand command) {
        if (command.orderId == null
                || command.orderId.trim().isEmpty()) {
            throw new IllegalArgumentException("Thiếu mã đơn hàng");
        }
    }
}

final class PositiveSubtotalValidator implements CheckoutValidator {
    @Override
    public void validate(CheckoutCommand command) {
        if (command.subtotalVnd <= 0) {
            throw new IllegalArgumentException(
                    "Tạm tính phải là số dương");
        }
    }
}

// Bảng tra: một khóa phương thức thanh toán -> một processor.
interface PaymentProcessor {
    void pay(String orderId, long totalVnd);
}

final class ConsoleCardProcessor implements PaymentProcessor {
    @Override
    public void pay(String orderId, long totalVnd) {
        System.out.println("CARD | order=" + orderId
                + " | amount=" + totalVnd);
    }
}

final class ConsoleBankProcessor implements PaymentProcessor {
    @Override
    public void pay(String orderId, long totalVnd) {
        System.out.println("BANK | order=" + orderId
                + " | amount=" + totalVnd);
    }
}

final class CheckoutService {
    private final List<PriceRule> rules;
    private final Set<CheckoutValidator> validators;
    private final Map<String, PaymentProcessor> processors;

    CheckoutService(List<PriceRule> rules,
                    Set<CheckoutValidator> validators,
                    Map<String, PaymentProcessor> processors) {
        Objects.requireNonNull(rules, "rules");
        Objects.requireNonNull(validators, "validators");
        Objects.requireNonNull(processors, "processors");

        // Copy phòng vệ: caller không sửa thành viên collection
        // qua tham chiếu ban đầu sau khi CheckoutService đã tạo.
        List<PriceRule> ruleCopy = new ArrayList<>(rules);
        for (PriceRule rule : ruleCopy) {
            Objects.requireNonNull(rule, "rule");
        }
        this.rules = Collections.unmodifiableList(ruleCopy);

        Set<CheckoutValidator> validatorCopy =
                new LinkedHashSet<>(validators);
        for (CheckoutValidator validator : validatorCopy) {
            Objects.requireNonNull(validator, "validator");
        }
        this.validators = Collections.unmodifiableSet(validatorCopy);

        if (processors.isEmpty()) {
            throw new IllegalArgumentException(
                    "Phải cấu hình ít nhất một PaymentProcessor");
        }
        Map<String, PaymentProcessor> processorCopy =
                new LinkedHashMap<>();
        for (Map.Entry<String, PaymentProcessor> entry
                : processors.entrySet()) {
            String key = entry.getKey();
            // Khóa trong registry phải ở dạng canonical.
            if (key == null || !key.equals(normalizeMethod(key))) {
                throw new IllegalArgumentException(
                        "Khóa phương thức thanh toán không chuẩn: " + key);
            }
            processorCopy.put(key, Objects.requireNonNull(
                    entry.getValue(), "processor"));
        }
        this.processors = Collections.unmodifiableMap(processorCopy);
    }

    static String normalizeMethod(String raw) {
        if (raw == null) {
            throw new IllegalArgumentException(
                    "Thiếu phương thức thanh toán");
        }
        String result = raw.trim().toLowerCase(Locale.ROOT);
        if (result.isEmpty()) {
            throw new IllegalArgumentException(
                    "Phương thức thanh toán rỗng");
        }
        return result;
    }

    long checkout(CheckoutCommand command) {
        Objects.requireNonNull(command, "command");

        // Với Set, không được phụ thuộc vào thứ tự validator.
        for (CheckoutValidator validator : validators) {
            validator.validate(command);
        }

        String method = normalizeMethod(command.paymentMethod);
        PaymentProcessor processor = processors.get(method);
        if (processor == null) {
            throw new IllegalArgumentException(
                    "Không hỗ trợ phương thức thanh toán: " + method);
        }

        long total = command.subtotalVnd;
        for (PriceRule rule : rules) {
            total = rule.apply(total);
            if (total < 0) {
                throw new IllegalStateException(
                        "Quy tắc giá tạo ra số tiền âm");
            }
        }

        processor.pay(command.orderId, total);
        return total;
    }
}

public class StrategyCollectionDemo {
    // Đăng ký trùng khóa phải thất bại, không âm thầm ghi đè.
    static void register(Map<String, PaymentProcessor> registry,
                         String method, PaymentProcessor processor) {
        Objects.requireNonNull(registry, "registry");
        Objects.requireNonNull(processor, "processor");

        String key = CheckoutService.normalizeMethod(method);
        if (registry.putIfAbsent(key, processor) != null) {
            throw new IllegalArgumentException(
                    "Trùng phương thức thanh toán: " + key);
        }
    }

    public static void main(String[] args) {
        // Composition root: lựa chọn và LẮP GHÉP các chiến lược.
        List<PriceRule> priceRules = Arrays.asList(
                new TenPercentDiscount(),
                new FlatServiceFee(10_000));

        Set<CheckoutValidator> checks = new LinkedHashSet<>();
        checks.add(new OrderIdValidator());
        checks.add(new PositiveSubtotalValidator());

        Map<String, PaymentProcessor> methods = new LinkedHashMap<>();
        register(methods, "CARD", new ConsoleCardProcessor());
        register(methods, "bank", new ConsoleBankProcessor());

        CheckoutService service =
                new CheckoutService(priceRules, checks, methods);

        long total = service.checkout(
                new CheckoutCommand("ORDER-42", 200_000, "card"));
        System.out.println("Total: " + total);
    }
}
```

Chạy bằng JDK:

```bash
javac StrategyCollectionDemo.java
java StrategyCollectionDemo
```

Đầu ra:

```text
CARD | order=ORDER-42 | amount=190000
Total: 190000
```

Số tiền được tính theo đúng thứ tự `List`:

```text
Tạm tính 200.000 VND
    |
    v  TenPercentDiscount: giảm 10%
180.000 VND
    |
    v  FlatServiceFee: cộng 10.000
190.000 VND
    |
    v  tra map theo "card"
ConsoleCardProcessor.pay(...)
```

Nếu đổi thứ tự thành **cộng 10.000 trước, giảm 10% sau**, kết quả là `189.000 VND`. Vì vậy, thay thứ tự các `PriceRule` là **thay hành vi nghiệp vụ**, không phải chỉ thay cách trình bày collection.

### 3.2. Điều gì thuộc về root, điều gì thuộc về service?

**Composition root** có quyền:

- Tạo `TenPercentDiscount`, `FlatServiceFee`, các validator và processor.
- Quyết định thứ tự quy tắc giá.
- Gắn khóa `"card"` với processor thẻ và `"bank"` với processor chuyển khoản.
- Kiểm tra cấu hình trùng khóa trước khi ứng dụng phục vụ yêu cầu.

**`CheckoutService`** có trách nhiệm:

- Xác minh các validator được truyền vào và chạy kiểm tra theo contract.
- Áp dụng các rule theo thứ tự cấu hình.
- Đọc phương thức thanh toán trong request và tìm processor tương ứng.
- Báo lỗi rõ khi không có processor, thay vì tự tạo hoặc âm thầm chọn nhầm processor.

Lưu ý, việc dùng **Map do inject trực tiếp** không đồng nghĩa với Service Locator. Map có kiểu và vai trò nghiệp vụ rõ (`Map<String, PaymentProcessor>`); các dependency được khai báo trong constructor. **Service Locator** là khi lớp nghiệp vụ tra cứu dịch vụ tùy ý qua một container/registry toàn cục như `Container.get(SomeType.class)`, khiến dependency bị che giấu.

## 4. List: chuỗi chiến lược có thứ tự và chính sách thực thi

**Dùng `List<Strategy>` khi thứ tự là một phần của hợp đồng.** Những ví dụ khác gồm:

- Filter kiểm tra quyền trước khi ghi audit.
- Chuỗi formatter chuyển dữ liệu qua các bước.
- Middleware xử lý request/response theo thứ tự vào và thứ tự ngược lúc thoát.
- Quy tắc làm sạch, chuẩn hóa, rồi xác thực dữ liệu.

Nếu một nhóm chiến lược chỉ có thể chạy khi chiến lược trước thành công, cần làm rõ chính sách lỗi:

| Chính sách | Cách ứng xử | Phù hợp khi |
| --- | --- | --- |
| **Fail-fast** | Dừng pipeline tại rule ném exception. | Một bước sai làm các bước tiếp theo không còn ý nghĩa. |
| **Tiếp tục và thu thập lỗi** | Ghi nhận lỗi rồi thử các bước độc lập còn lại. | Các bước độc lập, không dựa vào dữ liệu biến đổi từ bước lỗi. |
| **Rollback/compensation** | Hoàn tác các tác động đã thực hiện nếu bước sau thất bại. | Chuỗi có I/O/tác dụng phụ và đã thiết kế cơ chế nhất quán. |

Không thể chỉ dùng `List` là tự có transaction hoặc rollback. Nếu chiến lược làm thay đổi hệ thống bên ngoài, cần phân tích tính idempotent, thứ tự side effect và cách phục hồi khi lỗi.

### 4.1. Thứ tự phải được xác định ở đâu?

Một lựa chọn dễ hiểu là **root tạo danh sách theo đúng thứ tự**:

```java
List<PriceRule> rules = Arrays.asList(
        new TenPercentDiscount(),
        new FlatServiceFee(10_000));
```

Nếu muốn cấu hình bằng `priority`, cần định nghĩa:

- Priority thấp chạy trước hay sau?
- Nếu hai rule có cùng priority, làm gì: từ chối cấu hình hay có tie-breaker?
- Có cho phép một implementation xuất hiện hai lần với cấu hình khác nhau?
- Thứ tự có ổn định giữa các môi trường và các lần khởi động không?

Không nên dựa vào **thứ tự `HashSet` hoặc `HashMap`** để điều phối pipeline. Nếu dùng DI container, việc container inject `List` theo thứ tự đăng ký hoặc annotation có thể phụ thuộc framework; hãy xác minh contract của framework thay vì suy đoán.

### 4.2. Nhân bản phần tử không tự bị loại

`List` cho phép cùng một instance hoặc hai instance có cùng vai trò xuất hiện nhiều lần. Nếu cộng phí hai lần là sai, root phải có kiểm tra cấu hình; `List` không tự phát hiện tình huống này.

Ngược lại, đôi khi lặp cùng loại rule với tham số khác nhau là có chủ đích. Vì vậy không nên áp đặt “mọi class chỉ được xuất hiện một lần” nếu nghiệp vụ không yêu cầu.

## 5. Set: tập các chiến lược không yêu cầu thứ tự

**Dùng `Set<Strategy>` khi các chiến lược độc lập và không cần thứ tự ưu tiên.** Ví dụ trong `CheckoutService` là các validator. Nó hợp lý khi mỗi validator chỉ đọc dữ liệu cần kiểm tra và không dựa vào một validator khác đã sửa request.

Với `Set`, cần hiểu chính xác **tính duy nhất**:

```java
Set<CheckoutValidator> validators = new LinkedHashSet<>();
validators.add(new OrderIdValidator());
validators.add(new OrderIdValidator());
```

Nếu `OrderIdValidator` **không override `equals/hashCode`**, hai instance khác nhau không bằng nhau theo mặc định, nên cả hai có thể cùng tồn tại trong Set. Khi cần duy nhất theo “loại validation” hoặc một `validatorId`, dùng khóa nghiệp vụ và kiểm tra lúc lắp ghép.

`LinkedHashSet` duy trì thứ tự duyệt theo thứ tự thêm phần tử, nhưng interface `Set` **không cam kết** điều đó. Nếu thứ tự chính là quy tắc nghiệp vụ, nên khai báo `List` và truyền một danh sách có thứ tự tường minh. Tránh viết test yêu cầu validator A luôn chạy trước validator B khi hợp đồng chỉ là `Set`.

### 5.1. Chọn fail-fast hay tổng hợp lỗi?

Ví dụ chạy ở mục 3 chọn **fail-fast**: validator đầu tiên ném exception khiến việc kiểm tra dừng lại. Với Set, validator nào được gọi trước có thể thay đổi theo implementation hoặc cấu hình, nên **không nên gắn ý nghĩa nghiệp vụ với thông báo lỗi đầu tiên**.

Nếu giao diện cần hiển thị **tất cả lỗi nhập liệu**, có thể thiết kế hợp đồng validator trả về danh sách vi phạm thay vì ném exception:

```java
// Ví dụ về hợp đồng thay thế khi muốn tổng hợp lỗi.
interface CollectingValidator {
    List<String> validate(CheckoutCommand command);
}
```

Bên điều phối gom các vi phạm, rồi sắp xếp theo mã/trường trước khi hiển thị nếu cần kết quả ổn định. Không nên giả định lỗi được liệt kê theo thứ tự Set.

### 5.2. Trùng do cấu hình khác trùng theo `equals`

Một rule dùng tên `fraud-check` có thể có hai instance khác nhau nhưng cùng vai trò. Nếu nghiệp vụ chỉ cho phép một rule tên đó, hãy dùng một **registry có khóa**, hoặc chuyển input từ danh sách plugin có định danh thành Map và từ chối trùng khóa ở composition root. Đây là ràng buộc ở tầng nghiệp vụ, không phải thuộc tính mặc định của `Set`.

## 6. Map: tra cứu chiến lược theo khóa

**Dùng `Map<Key, Strategy>` khi có một khóa đáng tin cậy để chọn đúng một implementation.** Một ví dụ thường gặp là map phương thức thanh toán:

```java
Map<String, PaymentProcessor> processors = new LinkedHashMap<>();
StrategyCollectionDemo.register(processors,
        "card", new ConsoleCardProcessor());
StrategyCollectionDemo.register(processors,
        "bank", new ConsoleBankProcessor());
```

Trong `checkout`, phương thức `processors.get(method)` thể hiện rõ bước dispatch. Lớp nghiệp vụ không cần `if (method.equals("card")) new CardProcessor()`.

### 6.1. Định danh và chuẩn hóa khóa

Đối với khóa `String`, cần quy tắc rõ:

- Có phân biệt chữ hoa/chữ thường không? Trong ví dụ, `"CARD"` và `"card"` cùng được chuẩn hóa thành `"card"`.
- Có bỏ khoảng trắng ở đầu/cuối không?
- Chuỗi rỗng và `null` có được chấp nhận không?
- Khóa có cần đối chiếu danh sách giá trị được cho phép hay không?
- Một implementation có được đăng ký dưới nhiều khóa (alias) không?

`normalizeMethod` trong ví dụ dùng `Locale.ROOT` để tránh phụ thuộc locale hệ thống khi chuyển chữ thường. Với một tập phương thức thanh toán cố định, **enum** như `PaymentMethod.CARD` và `PaymentMethod.BANK` thường giảm lỗi chính tả hơn `String`:

```java
enum PaymentMethod {
    CARD, BANK
}

// Minh họa cấu trúc thay thế:
// Map<PaymentMethod, PaymentProcessor> processors;
```

Nếu khóa lấy từ JSON, URL hoặc form, lớp ở ranh giới đầu vào cần parse/validate thành giá trị tin cậy trước khi điều phối. **Đừng dùng khóa do người dùng nhập để truy xuất tùy ý service hạ tầng** ngoài phạm vi hợp đồng thanh toán được hỗ trợ.

### 6.2. Trùng khóa phải được xử lý sớm

`Map.put(key, value)` có thể âm thầm ghi đè implementation cũ. Nếu root đăng ký hai processor với khóa `"card"`, ứng dụng có thể chọn nhầm adapter mà không báo lỗi.

Hàm `register` trong ví dụ dùng `putIfAbsent` rồi ném `IllegalArgumentException` khi khóa đã có. Điều đó tạo **fail-fast khi cấu hình**. Nó giả định registry được đăng ký tuần tự ở bootstrap, và mọi giá trị được đăng ký đều khác `null`; nếu nhiều thread đồng thời đăng ký bằng `HashMap` hoặc `LinkedHashMap`, cần một cơ chế đồng bộ hóa riêng.

Một `Map` **đã được tạo sẵn** không thể chứa hai entry cùng một khóa. Do đó, để phát hiện trùng khóa của **các ứng viên ban đầu**, phải kiểm tra **trong lúc xây map**; đợi đến lúc inject một Map đã hoàn thành thì thông tin về entry bị ghi đè có thể đã mất.

### 6.3. Không tìm được khóa: không chọn mặc định ngầm

Khi không có `PaymentProcessor` tương ứng, ví dụ báo `IllegalArgumentException`. Không nên tự động chuyển tất cả phương thức thanh toán không nhận diện sang `"card"` hoặc `"bank"` nếu nghiệp vụ không định nghĩa fallback như vậy.

Với use case thật, thông báo trả về người dùng có thể là mã lỗi có cấu trúc như `UNSUPPORTED_PAYMENT_METHOD`; nội dung hiển thị và mã HTTP thuộc về presentation layer. Đừng để chọn sai processor biến thành một giao dịch bất ngờ.

## 7. Kiểm thử với fake: thứ tự, tập hợp và tra cứu khóa

Ta kiểm thử độc lập logic của service, không cần cổng thanh toán thật hoặc DI container. Lưu mã sau vào `StrategyCollectionTest.java`, cùng thư mục với `StrategyCollectionDemo.java`:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;

final class RecordingPaymentProcessor implements PaymentProcessor {
    int calls;
    String lastOrderId;
    long lastAmount;

    @Override
    public void pay(String orderId, long amountVnd) {
        calls++;
        lastOrderId = orderId;
        lastAmount = amountVnd;
    }
}

public class StrategyCollectionTest {
    static void check(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    public static void main(String[] args) {
        List<String> ruleCalls = new ArrayList<>();
        List<PriceRule> rules = new ArrayList<>();
        rules.add(current -> {
            ruleCalls.add("discount");
            return current - current / 10;
        });
        rules.add(current -> {
            ruleCalls.add("fee");
            return Math.addExact(current, 10_000);
        });

        int[] checked = {0, 0};
        Set<CheckoutValidator> validators = new HashSet<>();
        validators.add(command -> {
            checked[0]++;
            if (command.orderId == null
                    || command.orderId.trim().isEmpty()) {
                throw new IllegalArgumentException("Thiếu mã đơn");
            }
        });
        validators.add(command -> {
            checked[1]++;
            if (command.subtotalVnd <= 0) {
                throw new IllegalArgumentException("Giá không hợp lệ");
            }
        });

        RecordingPaymentProcessor card = new RecordingPaymentProcessor();
        RecordingPaymentProcessor bank = new RecordingPaymentProcessor();
        Map<String, PaymentProcessor> processors = new LinkedHashMap<>();
        StrategyCollectionDemo.register(processors, "card", card);
        StrategyCollectionDemo.register(processors, "bank", bank);

        CheckoutService service =
                new CheckoutService(rules, validators, processors);

        // Test copy phòng vệ của collection: caller sửa source
        // sau khi inject nhưng object graph vẫn giữ cấu hình ban đầu.
        rules.clear();
        validators.clear();
        processors.clear();

        long total = service.checkout(
                new CheckoutCommand("TEST-1", 200_000, "CARD"));
        check(total == 190_000, "Sai tổng tiền");
        check(ruleCalls.equals(Arrays.asList("discount", "fee")),
                "Không tuân theo thứ tự List");
        check(checked[0] == 1 && checked[1] == 1,
                "Không chạy đủ các validator trong Set");
        check(card.calls == 1 && bank.calls == 0,
                "Map chọn sai payment processor");
        check("TEST-1".equals(card.lastOrderId)
                && card.lastAmount == 190_000,
                "Fake không nhận đúng dữ liệu thanh toán");

        // Chọn khóa khác phải đi vào một processor khác.
        service.checkout(new CheckoutCommand("TEST-2", 100_000, "bank"));
        check(card.calls == 1 && bank.calls == 1,
                "Không điều phối độc lập theo khóa");

        // Khóa không có phải lỗi; không được dùng fallback ngầm.
        boolean unknownRejected = false;
        try {
            service.checkout(
                    new CheckoutCommand("TEST-3", 100_000, "unknown"));
        } catch (IllegalArgumentException expected) {
            unknownRejected = true;
        }
        check(unknownRejected, "Không từ chối khóa không được hỗ trợ");
        check(card.calls == 1 && bank.calls == 1,
                "Đã gọi processor dù khóa không hợp lệ");

        // Chặn trùng khóa ngay tại composition root.
        Map<String, PaymentProcessor> registry = new LinkedHashMap<>();
        StrategyCollectionDemo.register(registry, "card", card);
        boolean duplicateRejected = false;
        try {
            StrategyCollectionDemo.register(registry, " CARD ", bank);
        } catch (IllegalArgumentException expected) {
            duplicateRejected = true;
        }
        check(duplicateRejected, "Không phát hiện trùng khóa canonical");

        System.out.println("PASS");
    }
}
```

Biên dịch và chạy:

```bash
javac StrategyCollectionDemo.java StrategyCollectionTest.java
java StrategyCollectionTest
```

Kết quả dự kiến: `PASS`.

Bài test xác minh bốn điểm tách biệt:

1. Các rule trong `List` chạy theo thứ tự `discount` rồi `fee`.
2. Cả hai validator trong `Set` được gọi đúng một lần ở tình huống hợp lệ, **không assert validator nào chạy trước**.
3. Map chọn processor đúng khóa; khóa không tồn tại không gọi nhầm processor.
4. Lỗi đăng ký trùng khóa được phát hiện ở root, và collection được copy nên caller không thể thay cấu hình qua tham chiếu đầu vào.

**Giới hạn:** test chỉ kiểm tra cách phối hợp giữa các dependency fake và dữ liệu in-memory. Nó không kiểm tra kết nối tới payment gateway thật, retry/idempotency, rollback, concurrency hay kiểm soát quyền sử dụng từng phương thức thanh toán.

## 8. Copy phòng vệ không có nghĩa mọi thành phần bất biến

Trong constructor `CheckoutService`, ta tạo bản sao của `List`, `Set` và `Map`, rồi bọc bằng `Collections.unmodifiable...`.

Điều này giúp tránh kiểu lỗi:

```java
List<PriceRule> rules = new ArrayList<>();
rules.add(new TenPercentDiscount());
CheckoutService service = new CheckoutService(
        rules, validators, processors);

// Nếu CheckoutService giữ thẳng tham chiếu List của caller,
// lệnh này có thể thay đổi pipeline đang phục vụ request:
rules.clear();
```

Ở đoạn minh họa trên, `validators` và `processors` là các collection giả định đã cấu hình. Khi constructor copy phòng vệ, `rules.clear()` **không** làm thay đổi danh sách mà service đã giữ.

Nhưng đây chỉ là **bất biến ở cấu trúc collection**:

- Object `PriceRule`, `CheckoutValidator` hoặc `PaymentProcessor` bên trong vẫn có thể mang trạng thái mutable.
- Wrapper không tự làm một processor an toàn khi nhiều thread cùng gọi.
- Bản sao của map không chứng minh các processor đáp ứng cùng contract; cần test adapter, xử lý lỗi và cấu hình.
- Bản sao cũng không giải quyết ownership: ai tạo, ai đóng một processor có client hoặc thread pool?

Nếu các strategy cần thay đổi lúc ứng dụng đang chạy, đừng sửa trực tiếp collection đã inject. Hãy thiết kế một **registry/configuration snapshot** có quy tắc thay đổi rõ ràng (ví dụ thay cả snapshot bằng cơ chế thread-safe), và xác định cách dừng sử dụng/đóng các implementation bị thay thế.

## 9. Nhiều implementation có scope và vòng đời khác nhau

Một danh sách, tập hợp hoặc map **chỉ chứa tham chiếu**; nó không tự quản lý vòng đời các strategy.

Ví dụ:

- `TenPercentDiscount` không giữ trạng thái request nên có thể chia sẻ nếu implementation không có mutable state khác.
- `ConsoleCardProcessor` của demo chỉ in ra console, nhưng processor thật có thể dùng HTTP client hoặc pool. Cần kiểm tra thread safety và xác định ai đóng client.
- Validator phụ thuộc `CurrentUser` hoặc `RequestContext` cụ thể có thể cần tạo trong **request scope**; không nên đưa instance của request đầu vào Map dùng chung suốt ứng dụng.
- Factory có thể tạo processor mới theo task, nhưng khi đó nơi gọi factory cần hiểu và chịu trách nhiệm đóng resource thuộc task theo contract.

### 9.1. Tránh capture dependency sống ngắn trong registry sống dài

```java
// Ý tưởng cần tránh:
// Application singleton giữ PaymentProcessor có tham chiếu
// tới requestContext của một request đã kết thúc.
Map<String, PaymentProcessor> appMap =
        createMapUsingOneRequestContext(requestContext);
```

Mã này là pseudocode, không phải chương trình độc lập. Điểm sai là **vòng đời**: map dùng chung giữ dependency chỉ hợp lệ trong một request. Nếu processor cần dữ liệu của request hiện tại, hãy truyền dữ liệu vào tham số `pay(...)` hoặc tạo graph/processor trong đúng scope.

### 9.2. Registry có sở hữu tài nguyên không?

Composition root tạo processor rồi inject vào `CheckoutService`. Service thường **mượn** những processor này để sử dụng, không tự động đóng chúng. Nếu một processor sở hữu HTTP client hoặc connection pool, root hay một lifecycle manager phù hợp cần đóng tài nguyên sau khi ngừng nhận việc và xử lý xong các tác vụ còn lại.

Có thể cùng một processor được đăng ký dưới nhiều khóa. Nếu root chịu trách nhiệm đóng, phải tránh đóng trùng cùng một instance theo cả hai khóa. Việc duyệt `map.values()` rồi gọi `close()` với từng entry không tự bảo đảm an toàn cho alias/trùng instance.

### 9.3. Không lấy strategy từ container toàn cục trong lúc request

Nếu các strategy đã được đăng ký vào DI container, thành phần cấu hình/bootstrap có thể lấy tất cả và tạo collection cần thiết. Nghiệp vụ nên thấy `List<PriceRule>`, `Set<CheckoutValidator>` hoặc `Map<PaymentMethod, PaymentProcessor>`, không cần biết cấu trúc toàn bộ container.

Các framework có thể khác nhau về auto-collection, thứ tự `List`, khóa `Map` và cách áp scope. Khi chuyển từ Java thuần sang container, hãy kiểm tra rõ:

1. Những implementation nào được đưa vào collection?
2. Khóa Map được lấy từ đâu: tên bean, qualifier, annotation hay cấu hình?
3. Collection được tạo khi nào; nếu có nhiều implementation, thứ tự ra sao?
4. Scope của từng implementation có tương thích với nơi collection được giữ không?
5. Resource của mỗi implementation được đóng lúc nào và bởi ai?

Container có thể giảm mã wiring, nhưng **không tự xác định đúng quy tắc lựa chọn theo nghiệp vụ**.

## 10. Những trường hợp không nên inject collection strategy

Không phải cứ có hai implementation là phải tạo `List`, `Set` hoặc `Map`.

- Nếu chức năng chỉ cần **một** `PaymentProcessor` cố định cho toàn bộ ứng dụng, inject thẳng một interface thường đơn giản hơn.
- Nếu chiến lược được chọn bằng **quy tắc phức tạp** (theo khu vực, thời điểm, hạn mức, quyền, trạng thái dịch vụ), có thể tốt hơn khi inject một `PaymentProcessorSelector`/resolver có hợp đồng rõ, thay vì rải điều kiện lựa chọn vào service.
- Nếu phải tạo implementation có tham số **riêng cho mỗi tác vụ**, inject factory thay vì tạo toàn bộ instance tại startup.
- Nếu số lượng rule nhỏ và không bao giờ thay đổi độc lập, đôi khi một implementation đơn giản rõ ràng hơn việc tạo nhiều class/interface.
- Nếu collection trở thành một danh sách mọi service của ứng dụng, đó là dấu hiệu **Service Locator trá hình**. Hãy thu hẹp về một vai trò nghiệp vụ như `PriceRule`, không inject `Map<String, Object>` để caller lấy tùy ý mọi loại service.

**Tiêu chí:** collection phải đại diện cho một tập collaborator có **cùng vai trò hợp đồng**, đồng thời cách lặp/chọn của nó có ý nghĩa nghiệp vụ minh bạch.

## 11. Quy trình thiết kế collection injection

Khi chuyển một chuỗi `if/else` hoặc mã tự tạo adapter sang DI:

1. **Xác định vai trò chung:** từng implementation phải thực sự đáp ứng một contract ổn định (`PriceRule`, `CheckoutValidator`, `PaymentProcessor`).
2. **Xác định quy tắc lựa chọn:** chạy mọi strategy có thứ tự, chạy mọi strategy không thứ tự hay chỉ chọn một theo khóa?
3. **Chọn cấu trúc dữ liệu:** `List`, `Set` hoặc `Map` theo ngữ nghĩa đã xác định; tránh dựa vào thứ tự ngầm của collection khác.
4. **Lắp ghép ở composition root:** tạo implementation, gắn thứ tự/khóa, kiểm tra trùng và phụ thuộc bắt buộc; không tạo adapter trong service.
5. **Xác thực và đóng băng cấu hình:** fail-fast với `null`, khóa sai, trùng vai trò hoặc thiếu implementation bắt buộc; cân nhắc defensive copy.
6. **Kiểm tra scope/lifecycle:** bảo đảm strategy được chia sẻ đúng phạm vi, có ownership tài nguyên và an toàn khi dùng đồng thời nếu cần.
7. **Viết test ở nhiều mức:** unit test thứ tự/dispatch/bộ lọc với fake; integration test adapter và cấu hình root; kiểm thử concurrency/lifecycle khi ứng dụng hỗ trợ nhiều request cùng lúc.
8. **Chỉ cân nhắc DI container sau:** dùng auto-collection/qualifier khi thực sự giảm mã wiring mà vẫn giữ được hợp đồng và cách lựa chọn rõ ràng.

## 12. Bài tập thực hành

**Bối cảnh:** một hệ thống xử lý file có các bước:

- Chạy nhiều `FileValidator` độc lập.
- Áp dụng `FileTransformer` theo thứ tự: chuẩn hóa tên, đổi encoding rồi nén.
- Chọn `FileExporter` theo định dạng đích `"s3"`, `"local"`, `"ftp"`.

Hãy hoàn thành:

1. Đề xuất ba hợp đồng và quyết định dùng `List`, `Set` hay `Map` cho từng nhóm. Giải thích vì sao.
2. Viết constructor `FileProcessingService(...)` nhận đúng các collection cần thiết, kiểm tra `null`, giá trị không hợp lệ và copy cấu trúc collection khi cần.
3. Ở composition root, tạo danh sách transformer đúng thứ tự và một registry exporter. Thêm kiểm tra trùng khóa, kể cả trường hợp `"S3"` và `" s3 "`.
4. Dùng fake để kiểm tra thứ tự ba transformer, tất cả validator được gọi mà không phụ thuộc thứ tự, và chỉ exporter theo khóa được gọi.
5. Đề xuất cách tổng hợp **tất cả** lỗi validation cho người dùng mà không phụ thuộc thứ tự duyệt Set.
6. Giả sử exporter FTP có connection riêng và phải đóng: ai sở hữu nó và khi nào được phép gọi `close()`?
7. Giả sử hai request đồng thời cùng export file: những thành phần nào phải thread-safe, và có nên giữ file content/request context trong singleton exporter không?
8. Nếu quy tắc chọn exporter phụ thuộc loại file, quyền truy cập và kích thước, hãy cân nhắc khi nào cần một `ExporterSelector` thay vì map lookup trực tiếp.

**Gợi ý đối chiếu:** validator độc lập có thể được tổ chức như `Set`, nhưng cần định nghĩa uniqueness và cách gom lỗi; transformer tạo pipeline theo thứ tự nên phù hợp với `List`; exporter tra bằng khóa nên phù hợp với `Map`. Composition root chịu trách nhiệm tạo/đăng ký component và phát hiện lỗi cấu hình. Test fake chứng minh phối hợp đúng, còn export thật cần integration test, idempotency và quy tắc tài nguyên cụ thể.

**Điểm cần nhớ:** Inject `List<Strategy>`, `Set<Strategy>` hoặc `Map<Key, Strategy>` là cách mở rộng constructor injection để làm việc với **nhiều implementation cùng vai trò**. Chọn collection theo **ngữ nghĩa lựa chọn**: thứ tự, tập hợp độc lập hay bảng tra theo khóa. Đặt lựa chọn implementation và cấu hình tại composition root; giữ điều phối nghiệp vụ tường minh, kiểm chứng bằng Java thuần, đồng thời quản lý scope, vòng đời và lỗi cấu hình trước khi dựa vào DI container.
