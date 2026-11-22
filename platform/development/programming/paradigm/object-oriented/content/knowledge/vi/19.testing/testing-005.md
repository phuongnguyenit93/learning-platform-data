# Kiểm thử tính thay thế của kiểu con (Liskov Substitution Principle — LSP)

> **Bối cảnh:** OOP → Kiểm thử. Bài học này tập trung vào cách **chứng minh bằng kiểm thử rằng mọi kiểu con có thể thay thế kiểu cha/interface tại nơi sử dụng** mà không làm sai hành vi đã được cam kết.

## 1. Kết quả cần đạt

Sau bài này, bạn có thể:

- Diễn giải LSP bằng **hợp đồng hành vi** (behavioral contract), thay vì chỉ dựa vào quan hệ `extends`/`implements`.
- Tách các điều kiện cần kiểm tra thành **tiền điều kiện**, **hậu điều kiện**, **bất biến**, **ngoại lệ** và **tác dụng phụ**.
- Thiết kế **một bộ kiểm thử hợp đồng dùng chung** cho mọi implementation của cùng một abstraction.
- Tạo ca kiểm thử ở **biên miền dữ liệu**, kết hợp trường hợp đại diện và dữ liệu sinh có seed cố định.
- Phát hiện implementation vi phạm LSP; phân biệt **test pass** với việc đã chứng minh đúng cho mọi dữ liệu.

## 2. Thay thế kiểu con nghĩa là gì?

Giả sử mã khách hàng sử dụng kiểu trừu tượng `T`. Nếu `S` là kiểu con của `T`, thay một đối tượng `T` bằng đối tượng `S` **không được làm hỏng các kỳ vọng được ghi trong hợp đồng của `T`**.

~~~java
DiscountPolicy policy = new TenPercentDiscount(); // dùng qua interface
Checkout checkout = new Checkout(policy);
long payable = checkout.amountToPay(50_000);
~~~

`Checkout` chỉ phụ thuộc vào `DiscountPolicy`, nên mọi lớp triển khai interface phải giữ các cam kết chung của interface.

**Quan hệ kiểu trong Java chưa đủ để bảo đảm LSP.** Trình biên dịch xác nhận chữ ký phương thức và các ràng buộc kiểu; nó không thể tự xác nhận implementation trả kết quả đúng, tuân thủ bất biến, không phát sinh ngoại lệ trái hợp đồng hay không gây tác dụng phụ ngoài dự kiến.

| Thành phần hợp đồng | Kiểu con được phép | Dấu hiệu vi phạm cần kiểm thử |
|---|---|---|
| Tiền điều kiện (`precondition`) | Giữ nguyên hoặc **nới lỏng** | Yêu cầu thêm điều kiện cho đầu vào vốn hợp lệ ở kiểu cha |
| Hậu điều kiện (`postcondition`) | Giữ nguyên hoặc **mạnh hơn** | Trả kết quả ngoài miền cho phép, bỏ cam kết về giá trị |
| Bất biến (`invariant`) | Luôn giữ các bất biến chung | Để đối tượng rơi vào trạng thái mà abstraction cấm |
| Ngoại lệ | Chỉ phát sinh theo hợp đồng đã công bố | Ném lỗi mới trên dữ liệu hợp lệ, thay đổi ý nghĩa thất bại |
| Tác dụng phụ | Không phá các bảo đảm quan sát được | Tự thay đổi trạng thái, ghi dữ liệu hoặc gây hiệu ứng bị cấm |
| Quan sát của client | Giữ hành vi mà client có quyền trông đợi | Client phải `instanceof` rồi xử lý riêng một kiểu con |

Ví dụ: nếu kiểu cha chấp nhận mọi số tiền từ 0 đến 1.000.000 đồng xu (cent), kiểu con không được tự ý từ chối các đơn dưới 50.000 cent. Đó là **siết chặt tiền điều kiện**, dù chương trình vẫn biên dịch.

## 3. Chọn một hợp đồng có thể kiểm thử

Ta xây dựng chức năng tính giảm giá dùng đơn vị **cent** và `long` để minh họa mà không phải xử lý sai số dấu phẩy động.

Hợp đồng của `DiscountPolicy.discountCents(subtotalCents)`:

1. **Miền đầu vào hợp lệ:** `0 <= subtotalCents <= 1_000_000`.
2. **Hậu điều kiện:** `0 <= discountCents <= subtotalCents`.
3. Với đầu vào `0`, kết quả phải bằng `0`.
4. Cùng một đối tượng, cùng một đầu vào hợp lệ thì kết quả phải nhất quán; ví dụ này quy định policy **không có trạng thái thay đổi**.
5. Không ném `RuntimeException` cho bất kỳ đầu vào hợp lệ nào.
6. `Checkout` phải tính `payable = subtotal - discount` và giữ `payable` trong đoạn `[0, subtotal]`.

**Phạm vi hợp đồng phải rõ ràng.** Chúng ta không yêu cầu hành vi nào cho đầu vào âm hoặc vượt 1.000.000; kiểu con có thể từ chối hoặc hỗ trợ thêm các giá trị đó. Cũng không được tự thêm quy tắc “giảm giá luôn tăng khi subtotal tăng”, vì các chính sách giảm giá hợp lệ chưa hứa điều đó.

## 4. Ví dụ Java chạy được: một bộ kiểm thử, nhiều kiểu con

Yêu cầu: **JDK 17 trở lên**, không dùng thư viện ngoài. Tạo tệp `LspContractDemo.java` với toàn bộ mã sau:

~~~java
import java.util.List;
import java.util.Objects;
import java.util.Random;
import java.util.function.Supplier;

public class LspContractDemo {
    private static final long MAX_SUBTOTAL = 1_000_000L;

    /**
     * Hợp đồng:
     * - Với 0 <= subtotalCents <= MAX_SUBTOTAL:
     *   trả giá trị trong [0, subtotalCents], không ném RuntimeException.
     * - discountCents(0) == 0.
     * - Không phụ thuộc vào lịch sử gọi (stateless/deterministic).
     * - Không có tác dụng phụ quan sát được bởi client.
     */
    interface DiscountPolicy {
        long discountCents(long subtotalCents);
    }

    // Hợp lệ: không giảm giá.
    static final class NoDiscount implements DiscountPolicy {
        @Override
        public long discountCents(long subtotalCents) {
            return 0;
        }
    }

    // Hợp lệ: giảm 10%, làm tròn xuống tới cent.
    static final class TenPercentDiscount implements DiscountPolicy {
        @Override
        public long discountCents(long subtotalCents) {
            return subtotalCents / 10;
        }
    }

    // Hợp lệ: chỉ giảm 20% khi đủ ngưỡng.
    // Không giảm dưới ngưỡng vẫn hợp lệ vì hợp đồng cho phép trả 0.
    static final class TieredDiscount implements DiscountPolicy {
        @Override
        public long discountCents(long subtotalCents) {
            return subtotalCents >= 50_000 ? subtotalCents / 5 : 0;
        }
    }

    // CỐ Ý SAI: từ chối những subtotal hợp lệ dưới 50_000.
    static final class MinimumOnlyDiscount implements DiscountPolicy {
        @Override
        public long discountCents(long subtotalCents) {
            if (subtotalCents < 50_000) {
                throw new IllegalArgumentException("Minimum purchase is 50000");
            }
            return subtotalCents / 10;
        }
    }

    static final class Checkout {
        private final DiscountPolicy policy;

        Checkout(DiscountPolicy policy) {
            this.policy = Objects.requireNonNull(policy);
        }

        long amountToPay(long subtotalCents) {
            return subtotalCents - policy.discountCents(subtotalCents);
        }
    }

    // Factory tạo fixture độc lập, tránh dùng chung một object có state.
    record PolicyCase(String name, Supplier<DiscountPolicy> factory) {}

    // Đây chính là contract suite áp cho TẤT CẢ kiểu con.
    static void verifyContract(PolicyCase testCase) {
        DiscountPolicy policy = testCase.factory().get();

        // Biên dưới, biên trên, hai phía ngưỡng nghiệp vụ và lân cận.
        long[] boundaryValues = {
            0, 1, 9, 10, 49_999, 50_000, 50_001, 999_999, 1_000_000
        };

        for (long subtotal : boundaryValues) {
            checkOne(testCase.name(), policy, subtotal);
        }

        // Bổ sung các giá trị trong miền hợp lệ, có thể tái lập nhờ seed.
        Random random = new Random(205L);
        for (int i = 0; i < 500; i++) {
            long subtotal = random.nextInt(1_000_001);
            checkOne(testCase.name(), policy, subtotal);
        }
    }

    static void checkOne(String name, DiscountPolicy policy, long subtotal) {
        try {
            long first = policy.discountCents(subtotal);
            long second = policy.discountCents(subtotal);
            long payable = new Checkout(policy).amountToPay(subtotal);

            require(first >= 0 && first <= subtotal,
                name + ": discount outside [0, subtotal] for " + subtotal);
            require(first == second,
                name + ": same input produced different results at " + subtotal);
            require(subtotal != 0 || first == 0,
                name + ": discount(0) must be zero");
            require(payable == subtotal - first,
                name + ": Checkout cannot rely on stable policy at " + subtotal);
            require(payable >= 0 && payable <= subtotal,
                name + ": invalid amount to pay at " + subtotal);
        } catch (RuntimeException ex) {
            throw new AssertionError(
                name + ": threw exception for valid subtotal " + subtotal, ex
            );
        }
    }

    static void require(boolean ok, String message) {
        if (!ok) {
            throw new AssertionError(message);
        }
    }

    public static void main(String[] args) {
        List<PolicyCase> validPolicies = List.of(
            new PolicyCase("NoDiscount", NoDiscount::new),
            new PolicyCase("TenPercentDiscount", TenPercentDiscount::new),
            new PolicyCase("TieredDiscount", TieredDiscount::new)
        );

        // Thay thế các kiểu con qua CÙNG interface và CÙNG contract suite.
        for (PolicyCase testCase : validPolicies) {
            verifyContract(testCase);
            System.out.println("PASS: " + testCase.name());
        }

        // Demonstration: bộ kiểm thử phải bắt được implementation sai.
        PolicyCase broken = new PolicyCase(
            "MinimumOnlyDiscount", MinimumOnlyDiscount::new
        );
        boolean detected = false;
        try {
            verifyContract(broken);
        } catch (AssertionError error) {
            detected = true;
            System.out.println("EXPECTED FAIL: " + error.getMessage());
        }
        require(detected, "Broken implementation unexpectedly passed");
        System.out.println("DONE: contract tests detected the LSP violation");
    }
}
~~~

Mở terminal tại thư mục chứa tệp:

~~~powershell
javac LspContractDemo.java
java LspContractDemo
~~~

Kết quả kỳ vọng (rút gọn):

~~~text
PASS: NoDiscount
PASS: TenPercentDiscount
PASS: TieredDiscount
EXPECTED FAIL: MinimumOnlyDiscount: threw exception for valid subtotal 0
DONE: contract tests detected the LSP violation
~~~

**Vì sao đây là kiểm thử tính thay thế?** Bộ kiểm thử gọi mọi implementation **thông qua `DiscountPolicy`**, áp cùng tập kỳ vọng của interface và dùng chúng trong một client thật (`Checkout`). `MinimumOnlyDiscount` tuy khai báo `implements DiscountPolicy` nhưng ném ngoại lệ với `0`, một đầu vào hợp lệ theo hợp đồng. Vì vậy nó không thể thay thế kiểu cha một cách an toàn.

Việc bắt `AssertionError` ở cuối `main` chỉ để trình diễn một trường hợp **cố ý sai**. Trong CI và bộ kiểm thử của dự án, hãy để test thực tế báo **FAIL** khi implementation bất kỳ vi phạm; đừng nuốt lỗi và báo thành công.

## 5. Từ ví dụ sang bộ kiểm thử của dự án

Một thiết kế kiểm thử có thể tái sử dụng:

~~~mermaid
flowchart TD
    A["Hợp đồng của interface / lớp cha"] --> B["Bộ test chung"]
    C["Factory: implementation A"] --> B
    D["Factory: implementation B"] --> B
    E["Factory: implementation mới"] --> B
    B --> F["Kiểm tra tiền/hậu điều kiện, bất biến, ngoại lệ"]
    F --> G{"Mọi assertion đều đạt?"}
    G -->|Có| H["Đạt các ca đã kiểm tra"]
    G -->|Không| I["Phát hiện vi phạm hợp đồng"]
~~~

Trong dự án dùng **JUnit 5**, có thể đưa `verifyContract` thành hàm trợ giúp và chạy cùng bộ assertion qua các `@TestFactory`/`@ParameterizedTest`. Ví dụ sau đặt trong cùng package với `LspContractDemo` (đã cài JUnit Jupiter):

~~~java
import static org.junit.jupiter.api.DynamicTest.dynamicTest;
import java.util.stream.Stream;
import org.junit.jupiter.api.DynamicTest;
import org.junit.jupiter.api.TestFactory;

class DiscountPolicyContractTest {
    @TestFactory
    Stream<DynamicTest> everyImplementationRespectsContract() {
        return Stream.of(
            new LspContractDemo.PolicyCase(
                "NoDiscount", LspContractDemo.NoDiscount::new),
            new LspContractDemo.PolicyCase(
                "TenPercentDiscount", LspContractDemo.TenPercentDiscount::new),
            new LspContractDemo.PolicyCase(
                "TieredDiscount", LspContractDemo.TieredDiscount::new)
        ).map(item ->
            dynamicTest(item.name(), () -> LspContractDemo.verifyContract(item))
        );
    }
}
~~~

Khi thêm implementation mới, thêm **factory** tương ứng vào danh sách kiểm thử. Nếu interface được sử dụng bởi các hệ thống khác, bổ sung kiểm thử tích hợp tại ranh giới API/storage/network để xác nhận behavior quan sát được thực sự phù hợp; mock thuần túy có thể bỏ sót sai khác quan trọng.

## 6. Thiết kế bộ ca kiểm thử LSP đầy đủ hơn

| Nhóm ca | Ví dụ nên kiểm tra | Lỗi LSP có thể lộ ra |
|---|---|---|
| Giá trị biên | `0`, `1`, giá trị tối đa, ngay trước/sau ngưỡng | Kiểu con từ chối input hợp lệ, lỗi off-by-one |
| Hậu điều kiện | `discount >= 0` và `discount <= subtotal` | Trả số âm hoặc giảm nhiều hơn tiền hàng |
| Ngoại lệ | Mọi giá trị thuộc miền hợp lệ | Ném `IllegalArgumentException` trái hợp đồng |
| Chuỗi thao tác | Gọi cùng input 2 lần; gọi A–B–A | State ẩn làm kết quả phụ thuộc thứ tự |
| Bất biến trạng thái | Trước/sau từng thao tác; sau exception | Tổng tiền hoặc trạng thái trở nên không hợp lệ |
| Quan sát từ client | Dùng implementation qua interface trong `Checkout` | Client phải phân nhánh theo subtype |
| Tính độc lập | Tạo object mới cho từng test khi có state | Test rò rỉ trạng thái giữa các implementation |
| Tính mở rộng | Đăng ký mọi implementation có thể dùng khi runtime | Một kiểu con mới bỏ sót contract suite |

Cụ thể với abstraction **có thể thay đổi trạng thái**, cần kiểm tra thêm chuỗi lệnh và trạng thái sau lỗi. Ví dụ, nếu `Account.withdraw(x)` hứa rằng khi rút thất bại thì số dư không đổi, một subtype trừ tiền trước rồi mới ném lỗi là vi phạm bất biến/hậu điều kiện, dù chữ ký phương thức không khác.

Các ca kiểm thử không được yêu cầu hành vi **ngoài hợp đồng**. Ví dụ, không thể khẳng định mọi `DiscountPolicy` phải giảm 10%, hay kết quả của hai subtype phải bằng nhau. Cần kiểm tra từng kiểu con thỏa **cùng các bảo đảm** chứ không tạo ra **cùng kết quả cụ thể**.

## 7. Những lỗi phổ biến khi kiểm thử tính thay thế

**1. Chỉ kiểm tra `instanceof` hoặc ép kiểu.** Điều này chứng minh quan hệ kiểu, không chứng minh hành vi. Hãy kiểm tra qua biến `DiscountPolicy` và cùng assertion.

**2. Viết test riêng, khác chuẩn cho từng implementation.** Các test riêng có thể hữu ích cho quy tắc đặc thù, nhưng không thể thay thế **contract suite chung**. Nếu mọi loại có bộ điều kiện chấp nhận khác nhau, có thể bạn đã đánh mất abstraction chung.

**3. Nhầm input không hợp lệ của subtype với input không hợp lệ của kiểu cha.** Một kiểu con không thể bổ sung điều kiện tối thiểu 50.000 nếu hợp đồng chung chấp nhận cả 0.

**4. Test giá trị trả về nhưng quên ngoại lệ và trạng thái.** Một subclass có thể trả đúng trên đường đi thành công nhưng thay đổi dữ liệu sau lỗi hoặc phát sinh ngoại lệ ở nơi client không dự kiến.

**5. Kiểm thử ngẫu nhiên không cố định seed.** Lỗi khó tái lập. Dùng seed cố định cho CI, lưu lại input khi fail và kết hợp test biên có chủ đích. `500` input mẫu **không phải chứng minh toán học** cho tất cả đầu vào.

**6. Thay hợp đồng bằng chi tiết implementation.** Nếu test yêu cầu nội bộ phải dùng cấu trúc dữ liệu, thuật toán hoặc chính xác một mức giảm giá, bạn đang làm mất tính thay thế dù client không có quyền yêu cầu những điều đó.

**7. Làm yếu interface để hợp thức hóa subtype lỗi.** Đôi khi giải pháp đúng là **tách abstraction**: chẳng hạn một API bắt buộc có khả năng ghi không nên nhận subtype chỉ đọc rồi để nó ném `UnsupportedOperationException` với mọi lệnh ghi hợp lệ. Có thể dùng hai interface `ReadableRepository` và `WritableRepository` thay cho một hợp đồng mâu thuẫn.

## 8. Cách áp dụng trong code review và CI

1. **Viết hợp đồng bằng câu có thể kiểm chứng.** Mô tả chính xác miền input, output, ngoại lệ, bất biến, state và tác dụng phụ mà client trông đợi.
2. **Đưa các assertion chung vào một test suite.** Dùng interface hoặc lớp cha trong chữ ký helper, cung cấp factory cho từng implementation.
3. **Bao phủ giá trị biên và chuỗi thao tác.** Với lớp stateful, sử dụng từng đối tượng mới và kiểm tra cả khi thao tác thất bại.
4. **Chạy test khi thêm/sửa subtype.** Nếu test chung fail, điều tra subtype và hợp đồng, không tự động sửa assertion theo hành vi mới.
5. **Bổ sung kiểm thử tích hợp ở client tiêu biểu.** Đặc biệt khi vấn đề liên quan transaction, IO, cache, concurrency hoặc external API.
6. **Kiểm tra giới hạn của lời khẳng định.** Một bộ test pass chỉ cho biết những ca và thuộc tính đã đo được đều đạt; review thiết kế và phương pháp kiểm chứng khác vẫn cần thiết.

### Bài tập thực hành

- Thêm `NegativeDiscount` trả `-1`: xác định assertion hậu điều kiện nào fail.
- Thêm `MoreThanTotalDiscount` trả `subtotalCents + 1`: chỉ ra hậu điều kiện và hệ quả trong `Checkout`.
- Thêm policy dùng bộ đếm số lần gọi rồi thay đổi kết quả: xác định phép thử tính nhất quán nào bắt được lỗi.
- Sửa `MinimumOnlyDiscount` để chấp nhận mọi đầu vào hợp lệ mà vẫn không giảm cho các đơn nhỏ; chạy lại bộ contract test để thấy subtype đã phù hợp.
- Chọn một interface thực tế (repository, thanh toán, bộ đọc dữ liệu), viết các cam kết quan sát được và chạy cùng bộ test với ít nhất hai implementation khác nhau.

**Tiêu chí hoàn thành:** Bạn có thể thêm một subtype mới, đăng ký nó với bộ kiểm thử hợp đồng hiện có và biết chính xác điều kiện hành vi nào sẽ khiến nó bị từ chối, kể cả khi chữ ký Java vẫn hoàn toàn hợp lệ.