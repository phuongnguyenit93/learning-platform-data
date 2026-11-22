# Gộp hoặc loại bỏ trừu tượng không cần thiết trong OOP

> **Chủ đề:** Tái cấu trúc (Refactoring) — làm thiết kế Java đơn giản hơn bằng cách gộp những lớp, interface hoặc phương thức trung gian không còn mang trách nhiệm rõ ràng, đồng thời giữ nguyên hành vi mà client đang sử dụng.

Một thiết kế OOP tốt không được đánh giá bằng **số lượng interface, class hay pattern**. Trừu tượng hóa chỉ hữu ích khi nó mô tả một khái niệm đáng đặt tên, che giấu sự biến đổi, bảo vệ ranh giới trách nhiệm hoặc tạo ra khả năng thay thế có nhu cầu thực tế.

Khi một lớp chỉ chuyển tiếp mọi lời gọi sang lớp khác, một interface chỉ lặp lại chính xác API của implementation mà không phục vụ hợp đồng riêng, hoặc một hierarchy tồn tại do dự đoán tính năng chưa xảy ra, hệ thống có thể trở nên khó hiểu hơn. Việc loại bỏ những tầng này thường được gọi là **Inline Class**, **Remove Middle Man**, **Collapse Hierarchy** hoặc **Inline Method**, tùy cấu trúc đang được đơn giản hóa.

**Điểm quan trọng:** Không phải interface có một implementation nào cũng thừa. Một interface đơn lẻ vẫn có thể định nghĩa **ranh giới IO**, hợp đồng thư viện, cơ chế plugin, hoặc một phép thay thế cần thiết trong kiến trúc. Hãy dựa vào lý do tồn tại và chi phí thay đổi thực tế trước khi quyết định xóa.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt **trừu tượng hữu ích** với **tầng chuyển tiếp không thêm giá trị**.
- Nhận ra các dấu hiệu như `Middle Man`, `Speculative Generality`, hierarchy thừa, wrapper chỉ forward, method được tách quá mức.
- Chọn đúng kỹ thuật: `Inline Class`, `Remove Middle Man`, `Collapse Hierarchy`, `Inline Method` hoặc đơn giản hóa một tham số/adapter.
- Refactor theo từng bước, xác nhận kết quả bằng **regression/contract tests**.
- Cân nhắc rủi ro khi API đã được công bố, DI container, framework, serialization hoặc khả năng mở rộng thật sự phụ thuộc abstraction.
- Biết khi nào **giữ nguyên interface**, dù code hiện tại mới có một implementation.

## 2. Một abstraction hữu ích đang giải quyết việc gì?

Ví dụ một hệ thống thanh toán có interface:

~~~java
interface PaymentGateway {
    PaymentResult charge(PaymentRequest request);
}
~~~

Ứng dụng có thể chỉ chạy với một cổng thanh toán lúc này, nhưng `PaymentGateway` vẫn đáng giữ nếu nó tách nghiệp vụ khỏi nhà cung cấp dịch vụ, định nghĩa hợp đồng lỗi, tạo ranh giới network IO hoặc cho phép chạy sandbox trong môi trường kiểm thử.

Ngược lại:

~~~java
interface GreetingPort {
    String greeting(String name);
}

final class GreetingPortImpl implements GreetingPort {
    private final GreetingEngine engine = new GreetingEngine();

    @Override
    public String greeting(String name) {
        return engine.greeting(name); // không có logic, chính sách hoặc hợp đồng riêng
    }
}

final class GreetingEngine {
    String greeting(String name) {
        return "Xin chào, " + name;
    }
}
~~~

Nếu `GreetingPort` và `GreetingPortImpl` chỉ được dùng nội bộ tại một nơi, không phải API ổn định, không có thay thế thực tế và không đóng vai trò ranh giới kiến trúc, có thể đơn giản thành:

~~~java
final class Greeter {
    String greeting(String name) {
        return "Xin chào, " + name;
    }
}
~~~

Đây là **ví dụ có điều kiện**. Nếu `GreetingPort` đang được một thư viện công khai, DI module, plugin hay client bên ngoài sử dụng, xóa nó có thể gây lỗi biên dịch hoặc phá tương thích. Trước tiên phải kiểm tra người dùng thực tế của API.

| Câu hỏi | Dấu hiệu nên giữ | Dấu hiệu có thể gộp |
|---|---|---|
| Có **nhiều hành vi hợp lệ** cần thay thế không? | Strategy/plugin/adapter có nhiều lựa chọn thật | Chỉ một đường đi, không có biến thể được yêu cầu |
| Có **ranh giới hạ tầng** không? | API, DB, network, message broker, thời gian, file system | Wrapper thuần logic chuyển tiếp trong cùng module |
| Abstraction có **hợp đồng độc lập** không? | Bảo đảm hành vi, lỗi, quyền hạn và invariants riêng | Chữ ký và ý nghĩa hoàn toàn trùng lớp được bọc |
| Có giúp **giảm phụ thuộc** không? | Domain không cần biết về framework/vendor | Người đọc phải đi qua nhiều file mà phụ thuộc không giảm |
| Đã có **client bên ngoài** chưa? | Được phát hành/serialize/reflect/DI theo tên type | Chỉ private/internal call site, có thể chỉnh đồng bộ |
| Có **lý do thay đổi độc lập** không? | Các lớp thường phát triển khác nhau | Cả hai luôn thay đổi cùng lúc và không tạo ranh giới có ý nghĩa |
| Có **lợi ích test thật** không? | Tách external side effect, kiểm thử hợp đồng độc lập | Mock một lớp chỉ forward và test lặp lại cùng logic |

**Không dùng các luật cứng** kiểu “một implementation thì phải xóa interface”, “class dưới 20 dòng thì gộp” hay “mọi delegate đều thừa”. Giá trị của abstraction nằm ở trách nhiệm và tính ổn định của hợp đồng.

## 3. Dấu hiệu phổ biến của sự trừu tượng hóa quá mức

### Middle Man — lớp trung gian gần như chỉ ủy quyền

~~~java
final class OrderFacade {
    private final OrderService service;

    OrderFacade(OrderService service) {
        this.service = service;
    }

    long total(Order order) {
        return service.total(order);
    }
}
~~~

Nếu facade không thêm ý nghĩa cho API, không kiểm tra quyền, không điều phối nhiều collaborator, không dịch ngoại lệ và không ổn định hóa ranh giới, client có thể gọi `OrderService` trực tiếp. Nhưng facade là cần thiết nếu nó đại diện một **use case** hoặc che giấu sự phức tạp thật.

### Speculative Generality — chuẩn bị trước cho tương lai chưa có

Ví dụ tạo `AbstractReportFactoryBuilderBase`, `ReportFactoryProvider` và ba tầng interface chỉ vì “sau này có thể thêm định dạng”. Nếu hiện tại chỉ một loại báo cáo và chưa có yêu cầu thay đổi, các tầng đó có thể làm onboarding và debugging khó hơn.

### Collapsed responsibility — nhiều lớp chia nhau một trách nhiệm nhỏ

Một chuỗi `TaxInputWrapper → TaxCalculatorFacade → TaxCalculatorImpl` có thể chỉ truyền cùng hai tham số và trả lại một số nguyên. Nếu không có lý do tách biệt, đưa logic về class thể hiện rõ trách nhiệm sẽ làm mã ngắn đường đi hơn.

### Hierarchy không tạo đa hình có ý nghĩa

~~~java
class BaseOrderPrinter {
    String format(Order order) {
        return order.toString();
    }
}
final class DefaultOrderPrinter extends BaseOrderPrinter { }
~~~

Nếu subclass không có hành vi riêng, không có contract cho extension và inheritance chỉ tồn tại để thêm tên class, có thể bỏ cấp kế thừa sau khi kiểm tra các client phụ thuộc.

### Tiny Method không làm rõ ý định

~~~java
long add(long a, long b) { return a + b; }
long sum(long a, long b) { return add(a, b); }
~~~

Một phương thức chỉ có tác dụng gọi một phương thức khác đôi khi đáng inline. Tuy nhiên, các tên như `taxableAmount`, `validateAccess` có thể đại diện **ngữ nghĩa miền** hoặc một điểm kiểm soát tập trung; chúng đáng giữ dù rất ngắn.

## 4. Ví dụ Java chạy được: bỏ hai tầng forwarding dư thừa

**Bối cảnh:** Dịch vụ checkout tính phí vận chuyển và giảm giá. Mã cũ có ba tầng:

1. `CheckoutFacade` chỉ ủy quyền `quote`.
2. `PricingAdapter` implement `PricingPort` nhưng chỉ gọi `PricingEngine`.
3. `PricingEngine` thực sự kiểm tra đầu vào và tính giá.

Không có network/database/plugin hay chính sách bổ sung ở hai tầng trung gian trong ví dụ. Hệ thống nội bộ chỉ có một client sử dụng API `Checkout`. Ta giữ abstraction này là **hợp đồng mà client thấy**, nhưng thay chuỗi forward nội bộ bằng `SimplifiedCheckout` trực tiếp thực hiện nghiệp vụ.

### Hợp đồng cần giữ nguyên

- `subtotalCents` là số cent từ `0` đến `1_000_000`, bao gồm hai biên.
- Khách VIP được giảm **10%** (`subtotal / 10`, làm tròn xuống) và miễn phí vận chuyển.
- Khách thường không được giảm giá. Đơn từ **100.000 cent trở lên** miễn phí vận chuyển; nhỏ hơn thì phí **15.000 cent**.
- `totalCents = subtotalCents - discountCents + shippingCents`.
- Đầu vào ngoài miền hợp lệ ném `IllegalArgumentException`.
- Hàm báo giá không có side effect và cho kết quả ổn định với cùng đầu vào.

Tạo tệp `AbstractionRemovalDemo.java` bằng JDK **17 trở lên**:

~~~java
import java.util.List;
import java.util.Random;

public class AbstractionRemovalDemo {
    private static final long MAX_SUBTOTAL = 1_000_000L;
    private static final long FREE_SHIPPING_AT = 100_000L;
    private static final long SHIPPING_FEE = 15_000L;

    // Hợp đồng công khai với client trong ví dụ.
    interface Checkout {
        Invoice quote(long subtotalCents, boolean vip);
    }

    // Record: so sánh giá trị bằng equals(), không cần setter.
    record Invoice(long discountCents, long shippingCents, long totalCents) {}

    private static void validate(long subtotalCents) {
        if (subtotalCents < 0 || subtotalCents > MAX_SUBTOTAL) {
            throw new IllegalArgumentException("Invalid subtotalCents");
        }
    }

    // BEFORE: một interface nội bộ không có biến thể thực tế.
    interface PricingPort {
        Invoice calculate(long subtotalCents, boolean vip);
    }

    // Lớp chứa logic nghiệp vụ ở thiết kế cũ.
    static final class PricingEngine {
        Invoice calculate(long subtotalCents, boolean vip) {
            validate(subtotalCents);
            long discount = vip ? subtotalCents / 10 : 0;
            long shipping = (vip || subtotalCents >= FREE_SHIPPING_AT)
                ? 0 : SHIPPING_FEE;
            return new Invoice(
                discount, shipping, subtotalCents - discount + shipping
            );
        }
    }

    // Chỉ chuyển tiếp, không chuyển đổi dữ liệu/hợp đồng/ngoại lệ.
    static final class PricingAdapter implements PricingPort {
        private final PricingEngine engine = new PricingEngine();

        @Override
        public Invoice calculate(long subtotalCents, boolean vip) {
            return engine.calculate(subtotalCents, vip);
        }
    }

    // Facade này cũng chỉ forward vào adapter.
    static final class LegacyCheckout implements Checkout {
        private final PricingPort port = new PricingAdapter();

        @Override
        public Invoice quote(long subtotalCents, boolean vip) {
            return port.calculate(subtotalCents, vip);
        }
    }

    // AFTER: gộp logic nội bộ vào class thực hiện use case.
    // Hợp đồng Checkout mà client sử dụng không đổi.
    static final class SimplifiedCheckout implements Checkout {
        @Override
        public Invoice quote(long subtotalCents, boolean vip) {
            validate(subtotalCents);
            long discount = vip ? subtotalCents / 10 : 0;
            long shipping = (vip || subtotalCents >= FREE_SHIPPING_AT)
                ? 0 : SHIPPING_FEE;
            return new Invoice(
                discount, shipping, subtotalCents - discount + shipping
            );
        }
    }

    record Case(long subtotal, boolean vip, Invoice expected) {}

    // Oracle độc lập: expected value được ghi rõ theo yêu cầu.
    private static final List<Case> CASES = List.of(
        new Case(0, false, new Invoice(0, 15_000, 15_000)),
        new Case(0, true, new Invoice(0, 0, 0)),
        new Case(99_999, false, new Invoice(0, 15_000, 114_999)),
        new Case(100_000, false, new Invoice(0, 0, 100_000)),
        new Case(100_001, false, new Invoice(0, 0, 100_001)),
        new Case(250_001, true, new Invoice(25_000, 0, 225_001)),
        new Case(1_000_000, true, new Invoice(100_000, 0, 900_000))
    );

    static void require(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    // Bộ regression test áp cho bất kỳ implementation của Checkout.
    static void verifyContract(String label, Checkout service) {
        for (Case c : CASES) {
            Invoice actual = service.quote(c.subtotal(), c.vip());
            require(c.expected().equals(actual),
                label + " differs at " + c + "; actual=" + actual);

            require(actual.discountCents() >= 0,
                label + ": negative discount");
            require(actual.totalCents() ==
                    c.subtotal() - actual.discountCents()
                        + actual.shippingCents(),
                label + ": invalid total");
        }

        expectInvalid(() -> service.quote(-1, false));
        expectInvalid(() -> service.quote(MAX_SUBTOTAL + 1, true));
    }

    private static void expectInvalid(Runnable operation) {
        try {
            operation.run();
        } catch (IllegalArgumentException expected) {
            return;
        }
        throw new AssertionError("Expected IllegalArgumentException");
    }

    // Differential test dùng nhiều input cố định seed.
    static void compareBeforeAfter(Checkout before, Checkout after) {
        Random random = new Random(219L);
        for (int i = 0; i < 1_000; i++) {
            long subtotal = random.nextInt(1_000_001);
            boolean vip = random.nextBoolean();
            Invoice oldResult = before.quote(subtotal, vip);
            Invoice newResult = after.quote(subtotal, vip);
            require(oldResult.equals(newResult),
                "Behavior changed for subtotal=" + subtotal + ", vip=" + vip);
        }
    }

    public static void main(String[] args) {
        Checkout oldDesign = new LegacyCheckout();
        Checkout newDesign = new SimplifiedCheckout();

        verifyContract("legacy", oldDesign);
        verifyContract("simplified", newDesign);
        compareBeforeAfter(oldDesign, newDesign);

        System.out.println("PASS: legacy contract");
        System.out.println("PASS: simplified contract");
        System.out.println("PASS: before/after comparison");
        System.out.println(newDesign.quote(250_001, true));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac AbstractionRemovalDemo.java
java AbstractionRemovalDemo
~~~

Kết quả kỳ vọng:

~~~text
PASS: legacy contract
PASS: simplified contract
PASS: before/after comparison
Invoice[discountCents=25000, shippingCents=0, totalCents=225001]
~~~

Các lớp cũ và mới cùng tồn tại **chỉ để minh họa và so sánh trong tệp demo**. Khi áp dụng refactor cho dự án thật, sau khi kiểm chứng và chuyển toàn bộ call site, ta nên xóa các tầng `PricingPort`, `PricingAdapter`, `PricingEngine` và `LegacyCheckout` không còn được dùng. Không duy trì song song hai đường đi sản xuất nếu không có lý do tương thích hoặc chuyển đổi cụ thể.

### Trước và sau refactor

~~~mermaid
flowchart LR
    subgraph Before["Trước: bốn lớp/interface trên đường gọi"]
      A["Client"] --> B["Checkout"]
      B --> C["LegacyCheckout"]
      C --> D["PricingPort"]
      D --> E["PricingAdapter"]
      E --> F["PricingEngine"]
    end
    subgraph After["Sau: một hợp đồng và một implementation"]
      G["Client"] --> H["Checkout"]
      H --> I["SimplifiedCheckout"]
    end
~~~

Điều được cải thiện là **đường đi của hành vi rõ hơn**: không còn phải mở nhiều lớp chỉ để tìm nơi thực sự tính tiền. Điều không thay đổi là lời gọi qua `Checkout`, kiểu `Invoice` trả về và quy tắc input/output.

## 5. Chọn kỹ thuật gộp/loại bỏ đúng vấn đề

| Kỹ thuật | Khi nào dùng | Ví dụ | Rủi ro cần kiểm tra |
|---|---|---|---|
| **Inline Method** | Method chỉ gọi một method khác, tên không truyền thêm ý nghĩa | `int calc() { return addTax(); }` không thêm contract | Tên method có thể là ngôn ngữ miền hữu ích |
| **Inline Class** | Class làm quá ít việc, không có trách nhiệm độc lập | `AddressFormatterHelper` dùng riêng trong `AddressFormatter` | Class được framework/client bên ngoài tham chiếu |
| **Remove Middle Man** | Class phần lớn là chuỗi delegate đơn thuần | `Facade → Adapter → Engine` thuần forward | Delegate có thể là boundary bảo mật, transaction hay IO |
| **Collapse Hierarchy** | Superclass/subclass không khác biệt đáng kể về hành vi/trách nhiệm | `DefaultPrinter extends BasePrinter` mà không bổ sung logic | Hành vi đa hình, binary/source compatibility, override |
| **Remove Unused Abstraction** | Interface/abstract class/factory không còn caller hợp lệ | Interface chỉ tồn tại cho tính năng đã bỏ | Plugin, reflection, DI configuration, client bên ngoài |
| **Simplify Parameter Object** | Object chỉ bọc một giá trị, không có invariant/ý nghĩa riêng | `NameWrapper` không có chính sách và không được tái sử dụng | Có thể là value object cần bảo vệ unit/validation |
| **Replace Hierarchy with Composition** | Kế thừa phức tạp, dùng chỉ để tái sử dụng vài hành vi | Nhiều subclass vì phối hợp hai chiều biến đổi | Không phải lúc nào cũng **giảm** abstraction; đánh giá riêng |

**Đừng gộp trách nhiệm độc lập chỉ để giảm số file.** Nếu `PricingEngine` được nhiều use case dùng hoặc chịu trách nhiệm riêng, giữ nó và chỉ bỏ adapter dư thừa. Chọn mức đơn giản hóa sao cho *cohesion* tăng, *coupling* không xấu đi và test vẫn dễ viết.

## 6. Inline Class và Collapse Hierarchy khác nhau thế nào?

### Inline Class: đưa trách nhiệm nhỏ về nơi nó thực sự thuộc về

Giả sử:

~~~java
final class NameJoiner {
    String fullName(String first, String last) {
        return first + " " + last;
    }
}

final class CustomerLabel {
    private final NameJoiner joiner = new NameJoiner();

    String label(String first, String last) {
        return joiner.fullName(first, last);
    }
}
~~~

Nếu `NameJoiner` chỉ có một caller này, không tái sử dụng, không phụ thuộc IO, không encapsulate luật định dạng chung, có thể inline:

~~~java
final class CustomerLabel {
    String label(String first, String last) {
        return first + " " + last;
    }
}
~~~

Nhưng nếu toàn hệ thống phải tuân theo quy tắc hiển thị tên có địa phương hóa, định dạng độc lập là một trách nhiệm quan trọng. Khi đó nên giữ một dịch vụ/kiểu dữ liệu thể hiện đúng contract của nó.

### Collapse Hierarchy: bỏ mức kế thừa không có khác biệt

Trước:

~~~java
class BaseFormatter {
    String format(int value) {
        return Integer.toString(value);
    }
}

final class DefaultFormatter extends BaseFormatter {
    // Không override, không thêm trạng thái hoặc invariant.
}
~~~

Nếu không có consumer nào cần phân biệt `BaseFormatter` và `DefaultFormatter`, có thể thay bằng một class:

~~~java
final class Formatter {
    String format(int value) {
        return Integer.toString(value);
    }
}
~~~

Trường hợp này không có nghĩa mọi subclass rỗng đều phải xóa: class con có thể được dùng làm **marker type**, được framework tìm qua annotation, đại diện cho một hợp đồng tương thích hoặc sắp nhận extension đã có yêu cầu cụ thể. Phải kiểm tra client, annotation và cấu hình trước khi thay hierarchy.

## 7. Nhận diện ranh giới thật sự trước khi xóa abstraction

Cùng là một tầng gọi chuyển tiếp, nhưng ý nghĩa có thể rất khác:

~~~java
interface Clock {
    java.time.Instant now();
}
~~~

Đây có thể là ranh giới hữu ích để kiểm thử hành vi phụ thuộc thời gian mà không phải chờ đồng hồ thật. Nếu `Clock` giúp domain không phụ thuộc system clock, bỏ nó có thể làm test khó hơn.

~~~java
interface CustomerRepository {
    Customer findById(long id);
}
~~~

Có thể là một ranh giới giữa **domain/application** và **database**, ngay cả khi chỉ một implementation dùng JDBC. Loại bỏ interface có thể kéo SQL/hạ tầng vào nơi không nên phụ thuộc.

Ngược lại:

~~~java
final class IdEchoAdapter {
    long pass(long id) {
        return id;
    }
}
~~~

Nếu đây chỉ là một lớp vô nghĩa, không validation, transformation, boundary hay semantics, không có lý do kiến trúc rõ để giữ.

**Bảng quyết định nhanh:**

| Loại ranh giới | Nên giữ khi… | Cân nhắc gộp khi… |
|---|---|---|
| Domain ↔ database/network | Ẩn side effect, cho phép thay hạ tầng và test ổn định | Lớp trung gian chỉ copy tên, contract đã được định nghĩa ở nơi khác |
| Use case ↔ domain | Điều phối transaction, authorization, nhiều collaborator | Use case chỉ forward không có semantic riêng |
| API ↔ DTO/domain | Validation, versioning, mapping, serialization | Wrapper không chuyển đổi gì và không phải API công khai |
| Strategy/Plugin | Có biến thể thực tế hoặc hợp đồng mở rộng | Chỉ là dự đoán tương lai, không có người sử dụng |
| Value object | Đảm bảo đơn vị, ràng buộc, ý nghĩa miền | Wrapper chỉ đổi tên primitive, không thêm semantic |
| Module facade | Che giấu nhiều subsystem, làm API ổn định | Facade chỉ chuyển tiếp 100% và không che chi tiết nào |

## 8. Quy trình refactor an toàn: bỏ thừa mà vẫn giữ hợp đồng

1. **Xác định đường đi hiện tại.** Vẽ hoặc đọc chuỗi gọi từ public API tới nơi có nghiệp vụ. Đánh dấu mọi class/interface chỉ chuyển tiếp; ghi nhận chúng phục vụ client nào.
2. **Tìm lý do tồn tại.** Kiểm tra dependency, test, DI configuration, annotation, visibility, framework integration và các điểm extension. Đánh dấu boundary cần giữ.
3. **Chốt hành vi công khai.** Viết test từ specification cho input hợp lệ, biên, exception, output và side effect; lấy thêm các trường hợp đặc biệt từ bug thực tế.
4. **Chọn phép biến đổi nhỏ.** Có thể bỏ một lớp delegate trước khi xét gộp engine; không cần xóa cả hierarchy trong một commit lớn.
5. **Chuyển call site một cách nhất quán.** Gọi trực tiếp abstraction còn lại; giữ tên API cần ổn định; tránh để đường đi cũ và mới vô tình xử lý khác nhau.
6. **Chạy compiler, unit, regression và integration tests.** Với DI/reflection, cần kiểm tra khởi động ứng dụng, cấu hình bean, serialization và runtime route.
7. **Đo tác động thực tế.** Xem số bước tìm logic, số class phải chỉnh khi thêm yêu cầu, khả năng test, sự rõ ràng trong review. Loại bỏ tầng thừa có thể đáng giá hơn việc đếm giảm bao nhiêu dòng.
8. **Dọn code chết.** Sau khi chắc chắn không còn consumer, bỏ import, class, interface, file cấu hình và test chi tiết triển khai lỗi thời; giữ các test hành vi.

~~~mermaid
flowchart TD
    A["Tìm các tầng chỉ forward hoặc hierarchy thừa"] --> B["Xác định client và vai trò contract"]
    B --> C{"Có ranh giới/biến thể/lợi ích thật?"}
    C -->|Có| D["Giữ abstraction, cải thiện naming/API nếu cần"]
    C -->|Không| E["Chốt test hành vi và điểm tương thích"]
    E --> F["Inline/gộp một tầng"]
    F --> G["Chạy compile + regression/integration tests"]
    G --> H{"Hợp đồng và client còn đúng?"}
    H -->|Không| I["Sửa hoặc hoàn tác bước refactor"]
    I --> G
    H -->|Có| J["Xóa đường đi dư, review thiết kế"]
~~~

### Thứ tự thao tác khi public API đã có người dùng

Nếu `PricingPort` được công khai trong một thư viện, thay lời gọi client ngay lập tức có thể là **breaking change**. Một hướng an toàn hơn:

- Giữ **adapter tương thích** trong thời gian chuyển đổi và đánh dấu `@Deprecated` nếu phù hợp.
- Công bố API mới, hướng dẫn migration, di chuyển call site đã biết.
- Kiểm tra source/binary compatibility và phiên bản phát hành; chỉ xóa API cũ trong lần phát hành cho phép breaking change.
- Xác minh cả cấu hình DI, plugin, reflection và dữ liệu serialize có dùng tên type cũ không.

Ở một ứng dụng nội bộ được build cùng lúc, việc di chuyển mọi call site có thể thực hiện trực tiếp hơn, nhưng vẫn phải chạy test và kiểm tra runtime.

## 9. Kiểm thử tính đúng đắn của refactor

Khi **mục tiêu là đổi thiết kế, không đổi chức năng**, các test nên kiểm tra *kết quả client quan sát* hơn là số lớp hoặc số method.

| Nhóm test | Ví dụ | Điều được bảo vệ |
|---|---|---|
| Specification test | `quote(100_000, false)` miễn phí vận chuyển | Kết quả nghiệp vụ đúng độc lập với mã cũ |
| Boundary test | 0; 99.999; 100.000; 100.001; 1.000.000 | Không mất nhánh/điều kiện khi inline |
| Negative test | -1; 1.000.001 | Validation và loại lỗi giữ đúng |
| Differential test | 1.000 input random với seed cố định | Phát hiện khác biệt giữa hai đường đi |
| Side-effect test | Không phát sinh thao tác IO/charge ngoài hợp đồng | Bỏ tầng trung gian không tạo tác dụng phụ |
| Integration test | Khởi động DI, gọi API qua transport | Xóa type không phá wiring/runtime |
| Client compilation | Biên dịch module phụ thuộc, nếu có | Không phá chữ ký công khai vô ý |
| Performance check | Đo luồng bị ảnh hưởng nếu có SLA | Không tạo tính toán/IO thừa khi gộp |

### Ví dụ JUnit 5

Nếu dự án đã khai báo `org.junit.jupiter:junit-jupiter` và test cùng package với class demo, thêm tệp `CheckoutRefactoringTest.java`:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;

class CheckoutRefactoringTest {
    @Test
    void simplifiedImplementationKeepsBusinessContract() {
        var checkout = new AbstractionRemovalDemo.SimplifiedCheckout();

        assertEquals(
            new AbstractionRemovalDemo.Invoice(0, 0, 100_000),
            checkout.quote(100_000, false)
        );
        assertEquals(
            new AbstractionRemovalDemo.Invoice(25_000, 0, 225_001),
            checkout.quote(250_001, true)
        );
    }

    @Test
    void invalidInputsStillFail() {
        var checkout = new AbstractionRemovalDemo.SimplifiedCheckout();

        assertThrows(IllegalArgumentException.class,
            () -> checkout.quote(-1, false));
        assertThrows(IllegalArgumentException.class,
            () -> checkout.quote(1_000_001, true));
    }

    @Test
    void oldAndNewMatchOnRepresentativeCases() {
        AbstractionRemovalDemo.Checkout oldService =
            new AbstractionRemovalDemo.LegacyCheckout();
        AbstractionRemovalDemo.Checkout newService =
            new AbstractionRemovalDemo.SimplifiedCheckout();

        AbstractionRemovalDemo.verifyContract("old", oldService);
        AbstractionRemovalDemo.verifyContract("new", newService);
        AbstractionRemovalDemo.compareBeforeAfter(oldService, newService);
    }
}
~~~

Trong demo các nested type có quyền truy cập package-private; đặt test cùng package. Ở code production nên tổ chức mỗi type và visibility đúng với kiến trúc của ứng dụng.

**Không chỉ dựa vào phép so sánh phiên bản cũ/mới.** Nếu phiên bản cũ sai từ trước, việc copy đúng lỗi cũ vẫn pass differential test. Các `Invoice` kỳ vọng trong demo được viết **trực tiếp theo yêu cầu**, đóng vai trò oracle độc lập.

## 10. Những sai lầm thường gặp

**Xóa interface chỉ vì có một implementation.** Số implementation không phản ánh đầy đủ giá trị. Một abstraction ở ranh giới DB, IO, clock hay payment gateway có thể là yếu tố bảo vệ domain quan trọng.

**Gộp class theo số dòng.** Hai class mỗi class 10 dòng vẫn nên tách nếu chúng có **lý do thay đổi độc lập**. Ngược lại, một chuỗi class 100 dòng chỉ chuyển tiếp có thể cần đơn giản hóa.

**Chuyển hết logic vào một “God Class”.** Mục đích không phải giảm class bằng mọi giá. Nếu sau gộp class chịu nhiều trách nhiệm không liên quan, khả năng bảo trì sẽ xấu đi.

**Refactor và đổi nghiệp vụ cùng lúc.** Nếu tổng tiền thay đổi do chính sách giá mới, đó là thay đổi chức năng phải được mô tả riêng. Refactor chỉ được coi là giữ hành vi khi contract được xác minh không đổi.

**Không kiểm tra reflection, DI hoặc API ngoài module.** Code có thể compile nhưng ứng dụng lỗi lúc runtime vì bean name, annotation, constructor injection hoặc cấu hình dựa vào class đã xóa.

**Chỉ test chi tiết cấu trúc.** Một test xác nhận `PricingAdapter.calculate()` đã được gọi một lần trở nên vô nghĩa khi `PricingAdapter` bị bỏ. Thay bằng test của `Checkout.quote()` và những side effect thật sự có ý nghĩa.

**Inline phương thức lặp logic ở nhiều nơi.** Bỏ một method chung rồi copy nội dung sang nhiều client có thể tạo `Duplicate Code` và tăng chi phí thay đổi. Chỉ inline khi logic thực sự thuộc về caller và không làm phân tán một quy tắc chung.

**Không cân nhắc ràng buộc kiểu/visibility.** Chuyển method từ class này sang class khác có thể làm lộ field private, mở rộng quyền truy cập hoặc thay đổi overload/generics. Hãy dùng compiler, test và review access modifiers.

## 11. Bài tập thực hành

**Bài 1 — Phân loại:** Với các kiểu `UserRepository` (giao tiếp DB), `UserRepositoryImpl` (SQL thật), `UserRepositoryProxy` (chỉ forward), `UserService` (nghiệp vụ), hãy xác định lớp nào có thể là middle man. Nêu **bằng chứng cần kiểm tra** trước khi bỏ.

**Bài 2 — Inline Class:** Một `NamePrinter` chỉ được một `GreetingService` dùng để nối họ tên và không có định dạng chung. Viết lại để bỏ lớp phụ. Tạo test cho input thường, input rỗng và `null` theo hợp đồng hiện hành.

**Bài 3 — Collapse Hierarchy:** `DefaultDiscountCalculator extends DiscountCalculator` nhưng không override gì và không có client nào dùng kiểu con như một marker. Thiết kế lại thành một class, dự đoán ảnh hưởng đến constructor và các `import`.

**Bài 4 — Refactor có giới hạn:** Trong demo `AbstractionRemovalDemo`, thử chỉ xóa `PricingAdapter` và giữ `PricingEngine` nếu engine được một use case khác tái sử dụng. Đánh giá xem lớp còn lại có trách nhiệm rõ hơn không.

**Bài 5 — Lỗi ở ranh giới:** Cố tình sửa `subtotalCents >= FREE_SHIPPING_AT` thành `subtotalCents > FREE_SHIPPING_AT` ở `SimplifiedCheckout`. Chạy regression tests, giải thích chính xác case nào phát hiện lỗi. Khôi phục điều kiện đúng.

**Bài 6 — Review thật:** Tìm một chuỗi lời gọi dài trong ứng dụng. Vẽ đường gọi, đánh dấu mỗi tầng cung cấp contract, validation, transaction, auth, IO, mapping hay chỉ forward. Đề xuất loại bỏ **ít nhất một tầng có bằng chứng thừa**, viết test hành vi trước và ghi lại thay đổi sau khi chạy test.

## 12. Tiêu chí hoàn thành

Bạn có thể trả lời được ba câu trước khi loại bỏ một abstraction:

1. **Nó đang bảo vệ điều gì?** Hợp đồng, ranh giới phụ thuộc, biến thể có thật hay chỉ là một lời gọi chuyển tiếp?
2. **Việc gộp giúp ích gì?** Giảm số bước tìm logic, giảm chỗ phải sửa, làm rõ trách nhiệm hay đơn giản hóa kiểm thử mà không tạo coupling mới?
3. **Làm sao biết refactor an toàn?** Có test đặc tả, test biên, test ngoại lệ và kiểm tra các client/API chịu ảnh hưởng; kết quả public behavior vẫn đúng.

Khi cả ba câu đều có bằng chứng, việc **gộp hoặc loại bỏ trừu tượng không cần thiết** làm thiết kế OOP bớt vòng vo mà không đánh đổi sự rõ ràng và khả năng mở rộng thực sự.