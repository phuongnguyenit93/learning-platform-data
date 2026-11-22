# Kiểm thử hồi quy khi thay đổi thiết kế trong OOP

## 1. Vấn đề: đổi cấu trúc mã, giữ nguyên hành vi

Trong OOP, thiết kế có thể thay đổi từ một lớp lớn sang nhiều lớp nhỏ, tách interface, chuyển sang **Strategy**, thêm **Dependency Injection (DI)** hoặc đổi cách các đối tượng phối hợp. Những thay đổi này thường là **refactoring**: cải thiện cấu trúc nội bộ mà không chủ định đổi hành vi bên ngoài.

**Kiểm thử hồi quy (regression testing)** là chạy lại những kiểm thử đã có và bổ sung các ca cần thiết để phát hiện hành vi bị hỏng sau thay đổi. Câu hỏi cốt lõi:

> Sau khi đổi thiết kế, cùng một đầu vào và trạng thái hợp lệ có còn tạo ra kết quả, lỗi và tác dụng phụ đúng như hợp đồng đã công bố không?

Ví dụ, mã ban đầu dùng một phương thức tính tổng đơn hàng. Sau refactor, mã áp dụng mẫu thiết kế Strategy để tính phí vận chuyển. Client vẫn phải nhận đúng hóa đơn; đơn vừa chạm ngưỡng miễn phí phải được tính miễn phí; dữ liệu sai vẫn phải bị từ chối theo hợp đồng.

**Đạt mục tiêu bài học:**

- Xác định những **hành vi quan sát được** phải được giữ ổn định khi thay đổi thiết kế.
- Viết regression test dựa trên yêu cầu nghiệp vụ, với input/expected output rõ ràng.
- Chạy cùng bộ kiểm thử cho **thiết kế cũ và thiết kế mới** thông qua một interface.
- Phát hiện lỗi ở biên, ngoại lệ, trạng thái và tương tác giữa các đối tượng.
- Phân biệt **kiểm thử so sánh hai phiên bản** với **nguồn sự thật độc lập** là hợp đồng nghiệp vụ.
- Xây quy trình kiểm thử hồi quy trong review/CI trước và sau refactor.

## 2. Điều gì phải được giữ nguyên?

Giả sử một hệ thống báo giá đơn hàng có yêu cầu:

1. `subtotalCents` là số nguyên cent từ **0 đến 1.000.000**, tính cả hai đầu.
2. Khách hàng thành viên luôn được **miễn phí giao hàng**.
3. Khách thường có `subtotalCents >= 100_000` được miễn phí giao hàng; nhỏ hơn ngưỡng phải trả **15.000 cent**.
4. `totalCents = subtotalCents + shippingCents`.
5. Giá trị tiền hàng ngoài miền hợp lệ phải ném `IllegalArgumentException`.
6. Việc báo giá không thay đổi đơn hàng hoặc dữ liệu hệ thống.

Ở đây, cách tổ chức class là chi tiết triển khai. **Kết quả `Invoice`, lỗi và tác dụng phụ** mới là hành vi mà client trông đợi.

| Thành phần | Có thể thay đổi khi refactor | Hợp đồng phải giữ |
|---|---|---|
| Thiết kế class | Tách `Checkout` và `ShippingRule`, đổi tên class nội bộ | Client vẫn gọi dịch vụ báo giá được công bố |
| Thuật toán bên trong | Tách điều kiện, thay bằng Strategy | Quy tắc giá và phí vận chuyển không đổi |
| Phụ thuộc | Tiêm dependency qua constructor | Đầu vào hợp lệ vẫn xử lý thành công |
| Giá trị trả về | Cách dựng object | Các trường tiền trong `Invoice` đúng |
| Ngoại lệ | Nơi thực hiện validation | Input ngoài miền vẫn bị từ chối đúng hợp đồng |
| Trạng thái/tác dụng phụ | Cách lưu hoặc phối hợp component | Không phát sinh ghi dữ liệu bất ngờ |
| Hiệu năng | Tối ưu cache, thuật toán | Không phá SLA nếu SLA là phần yêu cầu |

**Lưu ý:** Không nhất thiết mọi chi tiết đều bất biến. Nếu yêu cầu nghiệp vụ cố ý thay đổi, test tương ứng cần được cập nhật có chủ đích và được review; đó không còn là refactor thuần túy.

## 3. Ba lớp bằng chứng cho regression test

Một bộ kiểm thử tốt không chỉ so sánh `before` và `after`:

- **Specification examples:** ca kiểm thử với kết quả kỳ vọng lấy từ yêu cầu nghiệp vụ. Các ví dụ này là oracle độc lập, giúp tránh sao chép lỗi cũ.
- **Differential testing:** chạy cùng input trên phiên bản cũ và mới, so sánh kết quả quan sát được. Cách này phát hiện chênh lệch ngoài các ví dụ cố định.
- **Invariant/contract tests:** kiểm tra các tính chất luôn đúng, chẳng hạn `total = subtotal + shipping`, tổng không âm, lỗi input nhất quán.

Không có cách nào riêng lẻ bảo đảm tuyệt đối. Chẳng hạn, nếu logic cũ tính sai ngay từ đầu thì việc hai phiên bản trả cùng một kết quả sai vẫn khiến phép so sánh `before/after` đi qua. Hãy ưu tiên **hợp đồng đã xác nhận** để quyết định đúng/sai.

## 4. Ví dụ Java chạy được: refactor Checkout sang Strategy

Dùng **JDK 17 trở lên**. Tạo tệp duy nhất `DesignRegressionDemo.java`, dán toàn bộ mã sau và chạy mà không cần thư viện ngoài:

~~~java
import java.util.Random;

public final class DesignRegressionDemo {
    private static final long MAX_SUBTOTAL = 1_000_000L;
    private static final long FREE_SHIPPING_AT = 100_000L;
    private static final long STANDARD_SHIPPING = 15_000L;

    // Hợp đồng chung mà các client sử dụng.
    interface PriceQuoteService {
        Invoice quote(long subtotalCents, boolean member);
    }

    // Value object bất biến, equals() so sánh theo giá trị.
    record Invoice(long shippingCents, long totalCents) {}

    private static void validateSubtotal(long subtotalCents) {
        if (subtotalCents < 0 || subtotalCents > MAX_SUBTOTAL) {
            throw new IllegalArgumentException("subtotalCents out of range");
        }
    }

    // BEFORE: nghiệp vụ và logic vận chuyển trong một class.
    static final class LegacyCheckout implements PriceQuoteService {
        @Override
        public Invoice quote(long subtotalCents, boolean member) {
            validateSubtotal(subtotalCents);
            long shipping = (member || subtotalCents >= FREE_SHIPPING_AT)
                    ? 0L : STANDARD_SHIPPING;
            return new Invoice(shipping, subtotalCents + shipping);
        }
    }

    // AFTER: tách chính sách giao hàng ra khỏi Checkout.
    interface ShippingRule {
        long shippingFor(long subtotalCents, boolean member);
    }

    static final class StandardShippingRule implements ShippingRule {
        @Override
        public long shippingFor(long subtotalCents, boolean member) {
            if (member || subtotalCents >= FREE_SHIPPING_AT) {
                return 0L;
            }
            return STANDARD_SHIPPING;
        }
    }

    static final class RefactoredCheckout implements PriceQuoteService {
        private final ShippingRule shippingRule;

        RefactoredCheckout(ShippingRule shippingRule) {
            this.shippingRule = java.util.Objects.requireNonNull(shippingRule);
        }

        @Override
        public Invoice quote(long subtotalCents, boolean member) {
            validateSubtotal(subtotalCents);
            long shipping = shippingRule.shippingFor(subtotalCents, member);
            return new Invoice(shipping, subtotalCents + shipping);
        }
    }

    // AFTER nhưng cố ý LỖI: > thay vì >= ở ngưỡng miễn phí.
    static final class BrokenShippingRule implements ShippingRule {
        @Override
        public long shippingFor(long subtotalCents, boolean member) {
            if (member || subtotalCents > FREE_SHIPPING_AT) {
                return 0L;
            }
            return STANDARD_SHIPPING;
        }
    }

    // Expected value đến từ đặc tả, không gọi production code để tự tính.
    record Example(long subtotal, boolean member, Invoice expected) {}

    private static final Example[] EXAMPLES = {
        new Example(0L,       false, new Invoice(15_000L,   15_000L)),
        new Example(0L,       true,  new Invoice(0L,             0L)),
        new Example(99_999L,  false, new Invoice(15_000L,  114_999L)),
        new Example(100_000L, false, new Invoice(0L,       100_000L)),
        new Example(100_001L, false, new Invoice(0L,       100_001L)),
        new Example(99_999L,  true,  new Invoice(0L,        99_999L)),
        new Example(1_000_000L, false, new Invoice(0L,   1_000_000L))
    };

    private static void require(boolean condition, String detail) {
        if (!condition) {
            throw new AssertionError(detail);
        }
    }

    // Chạy được cho mọi implementation của PriceQuoteService.
    static void verifyAgainstSpecification(
            String label, PriceQuoteService service) {
        for (Example example : EXAMPLES) {
            Invoice actual = service.quote(example.subtotal(), example.member());

            require(actual.equals(example.expected()),
                label + ": wrong quote at subtotal=" + example.subtotal()
                + ", member=" + example.member()
                + ", expected=" + example.expected()
                + ", actual=" + actual);

            require(actual.shippingCents() >= 0L,
                label + ": shipping cannot be negative");
            require(actual.totalCents()
                    == example.subtotal() + actual.shippingCents(),
                label + ": total must equal subtotal + shipping");
        }

        expectInvalid(label, service, -1L);
        expectInvalid(label, service, MAX_SUBTOTAL + 1L);
    }

    private static void expectInvalid(
            String label, PriceQuoteService service, long subtotal) {
        try {
            service.quote(subtotal, false);
            throw new AssertionError(label + ": accepted invalid subtotal " + subtotal);
        } catch (IllegalArgumentException expected) {
            // Đúng hợp đồng: từ chối input không hợp lệ.
        }
    }

    // So sánh hai thiết kế trên nhiều input có thể tái lập.
    static void verifySameBehavior(
            PriceQuoteService before, PriceQuoteService after) {
        Random random = new Random(209L);
        for (int i = 0; i < 1_000; i++) {
            long subtotal = random.nextInt(1_000_001);
            boolean member = random.nextBoolean();

            Invoice expectedFromOld = before.quote(subtotal, member);
            Invoice actualFromNew = after.quote(subtotal, member);
            require(expectedFromOld.equals(actualFromNew),
                "Behavior changed at subtotal=" + subtotal
                + ", member=" + member);
        }
    }

    public static void main(String[] args) {
        PriceQuoteService before = new LegacyCheckout();
        PriceQuoteService after =
            new RefactoredCheckout(new StandardShippingRule());

        verifyAgainstSpecification("LegacyCheckout", before);
        System.out.println("PASS specification: LegacyCheckout");

        verifyAgainstSpecification("RefactoredCheckout", after);
        System.out.println("PASS specification: RefactoredCheckout");

        verifySameBehavior(before, after);
        System.out.println("PASS differential: before vs after");

        // Minh họa khả năng phát hiện regression ở đúng điểm biên.
        PriceQuoteService broken =
            new RefactoredCheckout(new BrokenShippingRule());
        boolean regressionDetected = false;
        try {
            verifyAgainstSpecification("BrokenShippingRule", broken);
        } catch (AssertionError error) {
            regressionDetected = true;
            System.out.println("EXPECTED FAIL: " + error.getMessage());
        }
        require(regressionDetected, "The broken implementation was not detected");
        System.out.println("DONE: regression tests caught the design-change bug");
    }
}
~~~

Chạy bằng terminal:

~~~bash
javac DesignRegressionDemo.java
java DesignRegressionDemo
~~~

Đầu ra kỳ vọng (các dòng có thể dài hơn tùy `toString()` của record):

~~~text
PASS specification: LegacyCheckout
PASS specification: RefactoredCheckout
PASS differential: before vs after
EXPECTED FAIL: BrokenShippingRule: wrong quote at subtotal=100000, member=false, ...
DONE: regression tests caught the design-change bug
~~~

**Giải thích lỗi:** `BrokenShippingRule` dùng `subtotalCents > 100_000`. Khi tổng tiền **đúng bằng** 100.000 và không phải thành viên, nó tính phí 15.000 mặc dù hợp đồng yêu cầu miễn phí. Đây là lỗi **off-by-one ở ranh giới điều kiện**. Cả class cũ và mới đều implement `PriceQuoteService`, nhưng chỉ thiết kế mới đúng mới duy trì kết quả.

Trong ví dụ này, `main` bắt `AssertionError` của một implementation **cố tình sai** để minh họa. Ở bộ kiểm thử thực tế, regression phải làm job CI **FAIL**; không chuyển lỗi thành một kết quả PASS.

## 5. Vì sao phép kiểm thử này đáng tin hơn test chỉ kiểm tra nội bộ?

Nhìn vào quan hệ các lớp sau refactor:

~~~mermaid
classDiagram
    class PriceQuoteService {
      <<interface>>
      +quote(long, boolean) Invoice
    }
    class LegacyCheckout
    class RefactoredCheckout
    class ShippingRule {
      <<interface>>
      +shippingFor(long, boolean) long
    }
    class StandardShippingRule
    class BrokenShippingRule
    PriceQuoteService <|.. LegacyCheckout
    PriceQuoteService <|.. RefactoredCheckout
    RefactoredCheckout --> ShippingRule : sử dụng
    ShippingRule <|.. StandardShippingRule
    ShippingRule <|.. BrokenShippingRule
~~~

Bộ test gọi `quote()` thông qua **`PriceQuoteService`**, quan sát đối tượng `Invoice` trả về và các ngoại lệ công khai. Vì vậy, test tiếp tục có ý nghĩa khi code chuyển từ điều kiện `if` trong một class sang một Strategy được inject qua constructor.

**Không nên** khẳng định trong regression test rằng một lớp nhất định bắt buộc phải gọi `shippingRule.shippingFor()` đúng một lần, hoặc rằng implementation phải có một phương thức `private` cụ thể. Đó là chi tiết thiết kế có thể thay đổi mà không làm sai kết quả cuối. Chỉ xác nhận số lần gọi hoặc thứ tự tương tác khi nó **thực sự là một cam kết** (ví dụ không được charge thẻ hai lần).

## 6. Lập ma trận hồi quy trước khi refactor

| Nhóm kiểm thử | Ca mẫu | Sai sót thường bị phát hiện |
|---|---|---|
| Trường hợp thường | Thành viên/không thành viên, đơn nhỏ/đơn lớn | Nhánh logic bị đổi khi tách class |
| Giá trị biên | 0; 99.999; **100.000**; 100.001; 1.000.000 | `>`/`>=`, sai mức phí, tràn giá trị |
| Đầu vào không hợp lệ | -1; 1.000.001 | Validation bị bỏ sót hoặc đổi loại lỗi |
| Contract output | Tổng = subtotal + shipping | Kết quả không nhất quán giữa component |
| Trạng thái | Gọi nhiều lần, kiểm tra dữ liệu trước/sau | State bị thay đổi khi tách trách nhiệm |
| Side effect | Tạo báo giá không ghi DB, không charge tiền | Refactor gọi nhầm command có tác dụng phụ |
| Tích hợp | API → service → repository/payment gateway giả lập | Wiring/DI sai, transaction không đúng |
| Cạnh tranh | Nhiều request đồng thời trên đối tượng dùng chung | Cache hoặc shared mutable state gây race |
| Phi chức năng | Thời gian đáp ứng trong ngưỡng đã cam kết | Tăng truy vấn/IO ngoài dự kiến |

**Chọn ca theo rủi ro.** Nếu thay đổi chủ yếu ở tầng domain thuần Java, ưu tiên unit + contract + boundary tests. Nếu thay đổi wiring, transaction, dữ liệu hoặc serialization, thêm integration test. Nếu thay đổi giao diện API, thêm contract test theo payload hoặc kiểm tra tương thích ngược.

## 7. Áp dụng JUnit 5 vào dự án thực tế

Trong dự án Maven/Gradle đã khai báo phụ thuộc **JUnit Jupiter** và có class `DesignRegressionDemo` trong cùng package với test, có thể chuyển các kiểm tra sang `@Test`/`@TestFactory`. Ví dụ:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;

class CheckoutRegressionTest {
    @Test
    void minimumFreeShippingBoundaryMustRemainUnchanged() {
        DesignRegressionDemo.PriceQuoteService service =
            new DesignRegressionDemo.RefactoredCheckout(
                new DesignRegressionDemo.StandardShippingRule());

        assertEquals(
            new DesignRegressionDemo.Invoice(0, 100_000),
            service.quote(100_000, false)
        );
    }

    @Test
    void rejectsOutOfRangeSubtotals() {
        DesignRegressionDemo.PriceQuoteService service =
            new DesignRegressionDemo.RefactoredCheckout(
                new DesignRegressionDemo.StandardShippingRule());

        assertThrows(IllegalArgumentException.class,
            () -> service.quote(-1, false));
        assertThrows(IllegalArgumentException.class,
            () -> service.quote(1_000_001, false));
    }

    @Test
    void refactoringKeepsContractAndSampledBehavior() {
        DesignRegressionDemo.PriceQuoteService before =
            new DesignRegressionDemo.LegacyCheckout();
        DesignRegressionDemo.PriceQuoteService after =
            new DesignRegressionDemo.RefactoredCheckout(
                new DesignRegressionDemo.StandardShippingRule());

        DesignRegressionDemo.verifyAgainstSpecification("old", before);
        DesignRegressionDemo.verifyAgainstSpecification("new", after);
        DesignRegressionDemo.verifySameBehavior(before, after);
    }
}
~~~

Trong `src/test/java`, đặt test cùng package để truy cập các nested type không khai báo `public` trong ví dụ. Với ứng dụng production, thường tách mỗi type thành tệp và sử dụng modifier truy cập phù hợp với API công khai.

Khi chuyển sang JUnit, **đừng đưa implementation cố ý sai vào danh sách test phải PASS**. Nếu muốn khẳng định test bắt được lỗi mẫu thì dùng mutation testing hoặc một test minh họa riêng có điều khiển. Khi pipeline đang chạy, thất bại của implementation thật phải được giữ nguyên để chặn thay đổi lỗi.

## 8. Cách triển khai kiểm thử hồi quy theo từng bước

1. **Chốt hợp đồng hiện tại.** Viết yêu cầu, trường hợp mẫu, ranh giới, lỗi được phép, bất biến và side effect. Review với người hiểu nghiệp vụ khi hợp đồng chưa rõ.
2. **Tạo baseline trước khi đổi thiết kế.** Chạy bộ test trên mã hiện tại; ghi nhận những ca pass/fail và lỗi đã biết. Không coi kết quả của mã cũ là đúng tuyệt đối.
3. **Bổ sung test biên và test từng luồng quan trọng.** Mức độ ưu tiên phụ thuộc những đoạn code có nguy cơ thay đổi hành vi.
4. **Refactor từng phần nhỏ.** Tách abstraction, chuyển dependency, đổi cách khởi tạo object; giữ test chạy sau mỗi thay đổi.
5. **So sánh cả hợp đồng và hai phiên bản.** Dùng example-based tests độc lập trước, sau đó differential tests cho dải input rộng hơn.
6. **Chạy đúng tầng kiểm thử.** Unit test bắt lỗi logic; integration test xác nhận wiring, transaction và tác dụng phụ; end-to-end test kiểm tra luồng người dùng chính.
7. **Đưa vào CI và review.** Job chạy test tự động, báo tên ca/input gây lỗi; không bỏ qua test fail bằng cách sửa expected value tùy tiện.
8. **Xóa thiết kế cũ theo kế hoạch.** Sau khi refactor đã ổn định và được xác nhận, loại đường đi cũ; giữ **các test đặc tả** làm regression suite lâu dài. Differential test chỉ dựa vào implementation cũ có thể được bỏ khi không còn nhu cầu so sánh.

~~~mermaid
flowchart TD
    A["Chốt hợp đồng và baseline"] --> B["Viết test đặc tả + biên"]
    B --> C["Refactor từng bước nhỏ"]
    C --> D["Chạy unit/contract regression tests"]
    D --> E{"Các cam kết còn đúng?"}
    E -->|Không| F["Điều tra lỗi, sửa code hoặc làm rõ yêu cầu"]
    F --> D
    E -->|Có| G["Chạy integration + luồng quan trọng"]
    G --> H{"Đã xác minh thay đổi?"}
    H -->|Chưa| F
    H -->|Rồi| I["Merge và giữ regression suite trong CI"]
~~~

## 9. Những sai lầm cần tránh

**Chỉ chạy test của lớp mới.** Nếu refactor ảnh hưởng đến luồng ở nhiều nơi, một lớp mới pass unit test vẫn có thể làm hỏng transaction, serialization hoặc lỗi truyền lên API. Hãy chạy test ở các ranh giới mà client quan sát được.

**Chỉ test input “đẹp”.** Các lỗi dễ phát sinh ngay tại 0, ngưỡng, giá trị cực đại, object rỗng, `null` hoặc thứ tự thao tác bất thường. Chọn rõ miền input và kiểm tra ranh giới bên trong và ngoài.

**Lấy kết quả của implementation cũ làm đặc tả duy nhất.** Nếu mã cũ có bug, new code sao chép bug vẫn pass so sánh. Hãy bổ sung các ví dụ được chốt độc lập từ yêu cầu.

**Bắt test phụ thuộc cấu trúc class.** Refactor hợp lệ thường đổi số class, thứ tự lời gọi nội bộ hoặc mô hình injection. Nên kiểm tra giá trị, state, exception và hiệu ứng có ý nghĩa bên ngoài.

**Lạm dụng mock.** Mock mọi dependency theo đúng từng lời gọi khiến test dễ vỡ khi thay cách phối hợp lớp. Mock tại ranh giới IO không muốn thực thi thật, kết hợp integration test với cấu hình đại diện.

**Dùng dữ liệu ngẫu nhiên khó tái lập.** Với differential/property tests, sử dụng seed cố định, in input khi fail, thêm trường hợp sai vào bộ regression cố định; đừng phụ thuộc duy nhất vào dữ liệu random.

**Thấy xanh là coi như đã chứng minh không có regression.** Test chỉ đo những ca và thuộc tính đã mã hóa; coverage cao cũng không tự bảo đảm oracle đúng. Code review, test tích hợp và kiểm tra rủi ro còn cần thiết.

## 10. Bài tập thực hành

1. Thay `>=` thành `>` trong `StandardShippingRule`; dự đoán và chạy để xem test nào fail.
2. Chuyển validation từ `RefactoredCheckout` sang `ShippingRule` rồi cố ý quên một nhánh. Kiểm tra các input -1 và 1.000.001.
3. Tạo `PromotionShippingRule` mới: với giả định **yêu cầu nghiệp vụ không đổi**, viết cùng một bộ test và xác định implementation mới có tuân thủ hợp đồng hay không.
4. Bổ sung trường `discountCents` vào `Invoice` theo một **yêu cầu mới**; viết hợp đồng mới và cập nhật test có chủ đích, phân biệt thay đổi chức năng với refactor.
5. Áp dụng vào một repository hoặc service thật: chọn một public method, mô tả input/output/error/side effect, viết test đặc tả rồi refactor ít nhất hai class mà vẫn giữ test pass.

**Tiêu chí đạt:** Bạn thực hiện được một thay đổi thiết kế OOP, chứng minh kết quả từ client vẫn đúng qua test đặc tả, dữ liệu biên và ít nhất một phép so sánh trước/sau; nếu thay đổi gây regression, test phải chỉ ra input và cam kết nào bị phá vỡ.