# Lạm dụng mẫu thiết kế và trừu tượng hóa quá sớm

**Chủ đề:** OOP → Lỗi thiết kế  
**Mục tiêu:** nhận ra khi nào một Design Pattern hoặc abstraction đang giải quyết vấn đề thật và khi nào nó chỉ làm tăng độ phức tạp; biết bắt đầu từ thiết kế đơn giản, phát hiện áp lực thay đổi, refactor an toàn bằng Java và kiểm thử, thay vì thiết kế cho những giả định chưa được xác nhận.

## 1. “Thiết kế tốt” có nhất thiết phải nhiều lớp và interface?

Hãy tưởng tượng yêu cầu đầu tiên của một cửa hàng:

> Đơn hàng dưới 500.000 VND có phí vận chuyển 30.000 VND; từ 500.000 VND trở lên thì miễn phí.

Một cách triển khai:

~~~java
static long shippingFeeVnd(long goodsTotalVnd) {
    if (goodsTotalVnd < 0) {
        throw new IllegalArgumentException("Tiền hàng không được âm");
    }
    return goodsTotalVnd >= 500_000L ? 0L : 30_000L;
}
~~~

Đối với quy tắc này, một phương thức ngắn, có tên rõ, được kiểm thử có thể là **thiết kế tốt nhất ở hiện tại**. Nó không thiếu tính hướng đối tượng chỉ vì chưa có Strategy, Abstract Factory, một interface hoặc dependency injection.

Thế nhưng người lập trình có thể nghĩ:

> “Sau này chắc sẽ có nhiều chính sách giao hàng. Hãy tạo trước `ShippingPolicy`, `AbstractShippingPolicy`, `PolicyFactory`, `PolicyRegistry`, `PolicyResolver`, `ShippingPolicyConfiguration` và một plugin framework.”

Khi chỉ có một công thức duy nhất, người đọc phải đi qua nhiều file để hiểu một câu lệnh `if`. Mỗi kiểu mới là một cam kết cần bảo trì, đặt tên, viết test và giải thích.

Đó là **lạm dụng mẫu thiết kế (pattern overuse)** và có thể là **trừu tượng hóa quá sớm (premature abstraction)**: trả giá cho tính linh hoạt mà dự án chưa chứng minh rằng mình cần.

Điểm quan trọng: **không phải pattern nào cũng xấu**, và **không phải cứ ít lớp hơn là tốt**. Một abstraction ở ranh giới thanh toán, quyền truy cập hoặc nhà cung cấp ngoài có thể rất đáng giá từ đầu nếu đã có yêu cầu rõ. Điều cần đánh giá là **lợi ích so với chi phí trong bối cảnh cụ thể**, chứ không phải số lượng pattern.

## 2. Hai mùi thiết kế gần nhau nhưng không giống hệt

### Lạm dụng mẫu thiết kế

Đây là việc đưa một pattern vào **không đúng bài toán**, **không đúng quy mô** hoặc **không đúng thời điểm**, khiến hành vi bị chia nhỏ qua nhiều thành phần mà không nhận được lợi ích tương xứng.

Ví dụ:

- Dùng **Singleton** cho mọi service mặc dù ứng dụng cần kiểm thử tách biệt và nhiều cấu hình.
- Dùng **Abstract Factory** cho một loại object chỉ cần constructor.
- Dùng **Observer/Event Bus** cho lời gọi nghiệp vụ đồng bộ, làm luồng điều khiển trở nên khó truy vết dù không có nhu cầu phát cho nhiều bên.
- Dùng **Decorator** nhiều tầng cho một phép kiểm tra cố định, khiến thứ tự xử lý và lỗi trở nên khó hiểu.
- Dùng **Strategy + Registry** cho hai nhánh điều kiện rất ngắn và gần như không thay đổi.

Pattern là tên gọi của một cách phối hợp đối tượng. Không phải chứng nhận chất lượng kiến trúc.

### Trừu tượng hóa quá sớm

Đây là việc khái quát một hoặc vài trường hợp hiện tại thành API tổng quát khi **chưa hiểu chính xác điều gì thay đổi và điều gì không thay đổi**.

Ví dụ hai chức năng hiện cùng gửi email nhưng về sau có mục đích khác nhau:

- `sendPasswordResetEmail(...)`: có hạn sử dụng, tính bảo mật, chống lạm dụng.
- `sendMarketingEmail(...)`: có unsubscribe, consent, chiến dịch, tần suất.

Nếu gom cả hai vào một abstraction `UniversalEmailWorkflow<T, Context, Policy>` chỉ vì cả hai đều gọi SMTP, rất dễ khiến hai trách nhiệm bị ràng buộc bởi nhau. **Giống mã không nhất thiết đồng nghĩa cùng tri thức nghiệp vụ.**

### So sánh

| Tiêu chí | Lạm dụng pattern | Trừu tượng hóa quá sớm |
| --- | --- | --- |
| Sai lầm cốt lõi | Chọn một cơ chế thiết kế lớn hơn nhu cầu | Đoán trước điểm biến thiên mà chưa đủ bằng chứng |
| Ví dụ | Factory để `return new User(...)` | Generic `BaseRepository<T, K, V>` cho một entity |
| Chi phí | Nhiều kiểu, tầng chuyển tiếp, cấu hình và tracing | Hợp đồng mơ hồ, phải thêm cờ/nhánh khi nhu cầu thật xuất hiện |
| Hệ quả | Code nhìn “có kiến trúc” nhưng khó đọc | Các trường hợp mới phải bẻ cong abstraction cũ |
| Cách khắc phục | Bỏ tầng trung gian không đem lại giá trị | Học từ các use case thật rồi trích abstraction đúng trách nhiệm |

Hai vấn đề thường cùng xuất hiện. Ví dụ cố dự đoán một tương lai có 20 cách tính phí, rồi triển khai Factory + Strategy + plugin architecture khi hiện tại chỉ có một cách tính.

## 3. Chi phí thực sự của một abstraction

Một interface rất ngắn có vẻ không tốn gì:

~~~java
interface FeePolicy {
    long calculateFee(Shipment shipment);
}
~~~

Nhưng **chi phí thiết kế** không nằm riêng trong ba dòng này:

| Loại chi phí | Điều cần tính |
| --- | --- |
| **Đọc hiểu** | Phải mở bao nhiêu kiểu và lớp cấu hình để hiểu một thao tác? |
| **Thay đổi** | Khi một yêu cầu thay đổi, có phải sửa cả interface, implementation, factory, registry và test fixture? |
| **Tính tương thích** | Interface đã công khai cho module khác chưa? Có khó thay đổi không? |
| **Định hướng domain** | Abstraction mang tên nghiệp vụ thật hay chỉ tên chung chung như `Manager`, `Handler`, `Provider`? |
| **Kiểm thử** | Có giảm phụ thuộc ngoài và tăng khả năng test, hay chỉ sinh ra hàng chục mock vô nghĩa? |
| **Vận hành** | Cấu hình DI, chọn implementation, phát hiện lỗi, log/tracing có phức tạp thêm không? |
| **Nâng cấp** | Khi giả định tương lai sai, API mới có phải phá bỏ hoặc đổi lớn không? |

**Abstraction có giá trị khi nó che giấu một quyết định có khả năng thay đổi và cung cấp một hợp đồng ổn định, dễ hiểu.** Nếu chỉ chuyển tiếp một lời gọi mà không tách được trách nhiệm hoặc giảm được ảnh hưởng của thay đổi, đó có thể là một tầng trung gian không cần thiết.

Điều ngược lại cũng đúng: một object không phải đắt vì có nhiều dòng code, và một abstraction không phải vô ích chỉ vì hiện có **một implementation**. Ví dụ tách port giao tiếp ngân hàng khỏi domain có thể bảo vệ một ranh giới quan trọng dù hiện chỉ dùng một ngân hàng.

## 4. KISS, YAGNI, DRY và SOLID: hiểu đúng để tránh cực đoan

| Nguyên tắc | Ý nghĩa thực tế | Hiểu sai thường gặp |
| --- | --- | --- |
| **KISS** | Chọn giải pháp đơn giản nhất đáp ứng đúng yêu cầu và đủ dễ thay đổi | “Càng ít file càng tốt” |
| **YAGNI** (*You Aren't Gonna Need It*) | Không triển khai khả năng chưa có nhu cầu đủ rõ | “Không được thiết kế trước bất kỳ ranh giới nào” |
| **DRY** (*Don't Repeat Yourself*) | Tránh lặp **tri thức/quy tắc** mà khi thay đổi phải cập nhật nhất quán | “Hai khối code nhìn giống nhau phải gộp” |
| **SRP** | Một module có nhóm trách nhiệm/lý do thay đổi nhất quán | “Mỗi lớp chỉ được có một phương thức” |
| **OCP** | Giảm tác động sửa mã ổn định khi thêm biến thể ở điểm mở rộng thích hợp | “Không được phép chỉnh sửa class đã viết” |
| **DIP** | Logic quan trọng không bị khóa chặt bởi chi tiết biến động | “Mọi class phải có interface tương ứng” |

Không có mâu thuẫn tất yếu giữa các nguyên tắc này. Chúng trả lời những câu hỏi khác nhau.

Ví dụ **DIP** có thể gợi ý một interface cho cổng thanh toán bên ngoài vì đó là ranh giới biến động quan trọng. Nhưng **YAGNI** ngăn ta xây thêm một hệ thống auto-discovery 20 loại cổng thanh toán nếu không có nhu cầu.

**DRY cần xét ngữ nghĩa.** Hai hàm cùng gồm 8 dòng không nên tự động gộp thành một hàm có 6 tham số boolean; nếu mỗi hàm phục vụ quy tắc thuộc nhóm nghiệp vụ độc lập, việc tách riêng có thể giúp mỗi bên tiến hóa đúng.

### Đừng biến “Rule of Three” thành luật

Một lời nhắc thực dụng là quan sát vài trường hợp trùng nhau trước khi trích abstraction. Nhưng con số 2, 3 hay 4 **không tự chứng minh** điều gì.

Nếu hai client đã được xác nhận cần cùng một hợp đồng ổn định, abstraction có thể đáng tạo ngay. Nếu ba đoạn code trông giống nhau nhưng có chủ sở hữu và lý do thay đổi khác nhau, trích chúng thành một interface chung có thể là sai.

**Tiêu chí quan trọng hơn số lần lặp: những chỗ này có thật sự phải thay đổi cùng nhau không?**

## 5. Ví dụ tiến hóa: từ một điều kiện tới điểm mở rộng có căn cứ

### Giai đoạn 1 — yêu cầu chỉ có một chính sách

Giả sử cửa hàng chỉ có giao hàng **STANDARD**, miễn phí từ 500.000 VND, còn lại tính 30.000 VND.

Một phiên bản đơn giản, có validation và kiểm soát overflow:

~~~java
static long checkoutTotalVnd(long goodsTotalVnd) {
    if (goodsTotalVnd < 0) {
        throw new IllegalArgumentException("Tổng tiền hàng âm");
    }
    long fee = goodsTotalVnd >= 500_000L ? 0L : 30_000L;
    return Math.addExact(goodsTotalVnd, fee);
}
~~~

**Không có gì sai** khi bắt đầu từ phương thức này. API dễ đọc, kết quả hiển nhiên, test nhanh. Tạo trước `PolicyFactory` sẽ không làm phép tính chính xác hơn.

### Giai đoạn 2 — xuất hiện biến thể thật

Sau một thời gian, yêu cầu được xác nhận:

- **STANDARD:** quy tắc cũ.
- **EXPRESS:** phí cố định 50.000 VND, cộng 5.000 VND cho mỗi kilogram, phần lẻ kilogram làm tròn lên.
- Hai chính sách do các nhóm nghiệp vụ khác nhau quản lý và có thể thay đổi độc lập.

Đến đây có ít nhất hai hướng hợp lý:

**Hướng A — vẫn dùng `switch`:** nếu hai công thức ngắn, cùng nơi sở hữu, ít thay đổi, một `switch` có test vẫn dễ đọc.

**Hướng B — tách `FeePolicy`:** nếu mỗi thuật toán dần lớn, được test/deploy độc lập hoặc sẽ có nhà cung cấp phí riêng, Strategy trở nên hữu ích. Ta đã nhìn thấy **điểm biến thiên thật**, thay vì chỉ đoán.

~~~mermaid
flowchart TD
    A["Một chính sách đơn giản"] --> B{"Có biến thể thật hoặc ranh giới độc lập?"}
    B -->|"Chưa"| C["Hàm/điều kiện rõ nghĩa + test"]
    B -->|"Có"| D{"Các nhánh còn ngắn và cùng thay đổi?"}
    D -->|"Có"| E["Cân nhắc switch + test"]
    D -->|"Không"| F["Policy interface + implementation riêng"]
    C --> G["Quan sát tác động thay đổi"]
    E --> G
    F --> G
    G --> H["Refactor khi có bằng chứng mới"]
~~~

Đây là **quy trình ra quyết định**, không phải công thức máy móc. Cấu trúc tối ưu phụ thuộc rủi ro và vòng đời của code.

## 6. Java 17 chạy độc lập: so sánh thiết kế đơn giản và phiên bản có Strategy

Lưu thành **AbstractionTimingDemo.java**. Trong cùng file có:

1. `SimpleCheckout` cho giai đoạn ban đầu;
2. `FeePolicy`, `StandardFee`, `ExpressFee` và `PolicyCheckout` cho giai đoạn có biến thể;
3. `Shipment` là dữ liệu đầu vào được validate.

Mục tiêu của ví dụ **không phải chứng minh Strategy luôn tốt hơn**. Mục tiêu là nhìn rõ lúc nào một abstraction bắt đầu có nhiệm vụ thực tế.

~~~java
import java.util.Map;
import java.util.Objects;

public class AbstractionTimingDemo {

    public record Shipment(long goodsValueVnd, long weightGrams) {
        public Shipment {
            if (goodsValueVnd < 0 || weightGrams < 0) {
                throw new IllegalArgumentException(
                        "Giá trị hàng và khối lượng không được âm");
            }
        }
    }

    // Giai đoạn 1: không có nhu cầu hoán đổi thuật toán.
    public static final class SimpleCheckout {
        public long totalVnd(Shipment shipment) {
            Objects.requireNonNull(shipment, "shipment");
            long fee = shipment.goodsValueVnd() >= 500_000L
                    ? 0L : 30_000L;
            return Math.addExact(shipment.goodsValueVnd(), fee);
        }
    }

    public enum Mode {
        STANDARD, EXPRESS
    }

    // Giai đoạn 2: một hợp đồng tính phí cho các chính sách
    // thay đổi độc lập. Interface này chỉ cần đúng một năng lực.
    @FunctionalInterface
    public interface FeePolicy {
        long feeVnd(Shipment shipment);
    }

    public static final class StandardFee implements FeePolicy {
        @Override
        public long feeVnd(Shipment shipment) {
            Objects.requireNonNull(shipment, "shipment");
            return shipment.goodsValueVnd() >= 500_000L
                    ? 0L : 30_000L;
        }
    }

    public static final class ExpressFee implements FeePolicy {
        @Override
        public long feeVnd(Shipment shipment) {
            Objects.requireNonNull(shipment, "shipment");

            // Không dùng weightGrams + 999 để tránh overflow.
            long kilograms = shipment.weightGrams() / 1_000L;
            if (shipment.weightGrams() % 1_000L != 0) {
                kilograms = Math.addExact(kilograms, 1L);
            }

            long surcharge = Math.multiplyExact(kilograms, 5_000L);
            return Math.addExact(50_000L, surcharge);
        }
    }

    public static final class PolicyCheckout {
        private final Map<Mode, FeePolicy> policies;

        public PolicyCheckout(Map<Mode, FeePolicy> policies) {
            this.policies = Map.copyOf(
                    Objects.requireNonNull(policies, "policies"));
        }

        public long totalVnd(Mode mode, Shipment shipment) {
            Objects.requireNonNull(mode, "mode");
            Objects.requireNonNull(shipment, "shipment");

            FeePolicy policy = policies.get(mode);
            if (policy == null) {
                throw new IllegalArgumentException(
                        "Chưa cấu hình chế độ: " + mode);
            }

            long fee = policy.feeVnd(shipment);
            if (fee < 0) {
                throw new IllegalStateException(
                        "Chính sách trả về phí âm");
            }

            return Math.addExact(shipment.goodsValueVnd(), fee);
        }
    }

    public static void main(String[] args) {
        Shipment shipment = new Shipment(600_000L, 1_500L);

        SimpleCheckout initial = new SimpleCheckout();
        System.out.println(
                "Initial: " + initial.totalVnd(shipment));

        PolicyCheckout evolved = new PolicyCheckout(Map.of(
                Mode.STANDARD, new StandardFee(),
                Mode.EXPRESS, new ExpressFee()
        ));
        System.out.println(
                "Standard: " + evolved.totalVnd(Mode.STANDARD, shipment));
        System.out.println(
                "Express: " + evolved.totalVnd(Mode.EXPRESS, shipment));
    }
}
~~~

Chạy:

~~~bash
javac AbstractionTimingDemo.java
java AbstractionTimingDemo
~~~

Kết quả:

~~~text
Initial: 600000
Standard: 600000
Express: 660000
~~~

**Kiểm tra công thức:** đơn giá trị 600.000 VND miễn phí STANDARD. Với EXPRESS, trọng lượng 1.500 g được làm tròn lên **2 kg**, nên phí = 50.000 + 2 × 5.000 = **60.000 VND**, tổng = 660.000 VND.

### Điều gì thay đổi giữa hai giai đoạn?

| Trước có biến thể | Sau có biến thể được xác nhận |
| --- | --- |
| Một công thức, một nơi sửa | Hai thuật toán có thể thay đổi độc lập |
| Không cần chọn implementation | `Mode`/composition root chọn chính sách |
| Hàm đơn giản là đủ | `FeePolicy` trở thành hợp đồng có ý nghĩa |
| Một số test trực tiếp | Test riêng cho từng policy và test điều phối |
| Ít tầng chuyển hướng | Có thêm tầng trừu tượng để giảm coupling giữa thuật toán |

**Không phải mọi lần có thêm mode đều cần Strategy.** Nếu tổng logic vẫn chỉ vài câu lệnh và cùng một nhóm sở hữu, dùng `switch` có thể là lựa chọn kinh tế hơn. Trong ví dụ, Strategy được giới thiệu vì giả định **quy tắc thay đổi độc lập**, không chỉ vì `enum` có hai giá trị.

Tính mở rộng vẫn có giới hạn: thêm chế độ giao hàng mới có thể phải cập nhật `Mode` và cấu hình `Map`. OCP không phải lời hứa “sẽ không bao giờ sửa file nào” — nó khuyến khích đặt thay đổi ở đúng điểm mở rộng.

## 7. Kiểm thử: bằng chứng giúp refactor mà không làm đổi hành vi cũ

Khi tách một hàm thành các policy, không nên dựa vào cảm giác rằng code mới “trông chuẩn hơn”. Hãy giữ **hành vi ban đầu** bằng test rồi kiểm tra nhánh mới:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.Map;
import org.junit.jupiter.api.Test;

class AbstractionTimingDemoTest {

    @Test
    void logicStandardCuVanDungSauKhiTachPolicy() {
        var oldCheckout = new AbstractionTimingDemo.SimpleCheckout();
        var newCheckout = new AbstractionTimingDemo.PolicyCheckout(
                Map.of(AbstractionTimingDemo.Mode.STANDARD,
                        new AbstractionTimingDemo.StandardFee()));

        long[] totals = {0L, 100_000L, 499_999L, 500_000L, 750_000L};

        for (long goodsValueVnd : totals) {
            var request = new AbstractionTimingDemo.Shipment(
                    goodsValueVnd, 1_000L);

            assertEquals(
                    oldCheckout.totalVnd(request),
                    newCheckout.totalVnd(
                            AbstractionTimingDemo.Mode.STANDARD,
                            request)
            );
        }
    }

    @Test
    void expressLamTronTheoKilogram() {
        var policy = new AbstractionTimingDemo.ExpressFee();

        assertEquals(50_000L,
                policy.feeVnd(new AbstractionTimingDemo.Shipment(
                        100_000L, 0L)));
        assertEquals(55_000L,
                policy.feeVnd(new AbstractionTimingDemo.Shipment(
                        100_000L, 1L)));
        assertEquals(60_000L,
                policy.feeVnd(new AbstractionTimingDemo.Shipment(
                        100_000L, 1_500L)));
    }

    @Test
    void thieuChinhSachPhaiBaoLoiRoRang() {
        var checkout = new AbstractionTimingDemo.PolicyCheckout(
                Map.of());

        assertThrows(IllegalArgumentException.class, () ->
                checkout.totalVnd(
                        AbstractionTimingDemo.Mode.EXPRESS,
                        new AbstractionTimingDemo.Shipment(
                                100_000L, 1_000L)));
    }

    @Test
    void dauVaoAmBiTuChoi() {
        assertThrows(IllegalArgumentException.class, () ->
                new AbstractionTimingDemo.Shipment(-1L, 0L));
    }
}
~~~

File test là **AbstractionTimingDemoTest.java**, cần JUnit Jupiter 5 trong classpath. File demo chính chỉ dùng JDK 17.

Các test chứng minh điều gì?

- Công thức STANDARD **không đổi** khi chuyển từ hàm đơn giản sang implementation của interface.
- EXPRESS làm tròn trọng lượng theo quy tắc đã viết.
- Registry thiếu implementation báo lỗi rõ.
- Dữ liệu đầu vào sai bị từ chối trước khi tính toán.

**Không thể dùng số test thành công để kết luận mọi kiến trúc tốt.** Test chủ yếu giúp thay đổi an toàn; độ phức tạp và khả năng hiểu cần được review riêng. Không nên mock mọi helper chỉ để “có thể kiểm thử”: một hàm thuần túy đã có thể test trực tiếp rất tốt.

## 8. Dấu hiệu nhận biết abstraction đã đi quá xa

### 8.1. Một interface cho mỗi class mà không có ranh giới rõ

Ví dụ:

~~~text
UserController
  → IUserService
  → UserServiceImpl
  → IUserManager
  → UserManagerImpl
  → IUserRepository
  → UserRepositoryImpl
~~~

Chuỗi này **không tự động xấu**: một service có business rule và một repository tách hạ tầng có thể rất hợp lý. Nhưng nếu mọi lớp chỉ chuyển tiếp lời gọi và không có trách nhiệm, chính sách hay điểm thay thế độc lập, số tầng này có thể chỉ gây thêm công việc.

**Hãy hỏi:** bỏ một interface/tầng trung gian có làm mất khả năng thực tế (ranh giới module, hợp đồng công khai, thay adapter, test độc lập, phân quyền) không? Nếu không, cân nhắc đơn giản hóa.

Trong Java, interface không phải điều kiện bắt buộc để unit test. Có thể test class cụ thể trực tiếp; hoặc dùng fake ở những ranh giới có phụ thuộc ngoài thực sự.

### 8.2. Generic framework cho đúng một bài toán

~~~java
// Ý tưởng đáng ngờ nếu chỉ dùng với đúng một màn hình CRUD:
// AbstractWorkflowCoordinator<T, ID, META, POLICY, CONTEXT>
~~~

Một bộ generic như vậy đặt nhiều gánh nặng lên người dùng API: type parameters, factory, converter, hook, cấu hình và lifecycle. Nếu không có nhiều workflow thực sự chung về hợp đồng, ta có thể đang đóng gói **sự chưa hiểu bài toán** vào generic parameters.

Một abstraction mạnh không nhất thiết là abstraction rộng. Một interface `PaymentGateway` có hai phương thức được thiết kế kỹ có thể hữu ích hơn một framework “universal” với hai mươi điểm mở rộng.

### 8.3. Hệ thống cấu hình thay cho một nhánh điều kiện

Nếu để thay một ngưỡng miễn phí giao hàng phải sửa YAML, registry key, factory mapping và một bean profile, có thể abstraction đã **chuyển độ phức tạp từ Java sang cấu hình** chứ không giảm nó.

Cấu hình động hữu ích khi **thực sự cần đổi chính sách mà không phát hành code**, phân quyền cấu hình theo tenant, hoặc chọn implementation tùy môi trường. Nếu không có các yêu cầu ấy, hằng số/domain setting rõ ràng có thể phù hợp hơn.

### 8.4. Abstraction rò rỉ chi tiết

Một `StoragePort` được thiết kế để tách business khỏi database nhưng lộ `JdbcConnection`, tên cột SQL và transaction driver trong API thì chưa che được hạ tầng. Một `NotificationSender` nhận trực tiếp object riêng của nhà cung cấp cũng làm business code bị khóa vào SDK.

**Đúng hướng** thường là biểu diễn năng lực cần thiết theo domain ở phía client, rồi adapter chuyển sang API kỹ thuật bên ngoài.

## 9. Phân biệt “lặp code” và “lặp tri thức”

Xem hai quy tắc đang giống nhau hôm nay:

~~~java
long loyaltyDiscount(long amountVnd) {
    return amountVnd * 5 / 100;
}

long seasonalDiscount(long amountVnd) {
    return amountVnd * 5 / 100;
}
~~~

Chúng cùng công thức 5% nhưng có thể **khác lý do thay đổi**:

- Giảm giá thành viên thay đổi theo chính sách duy trì khách hàng.
- Giảm theo mùa thay đổi theo chiến dịch marketing.

Nếu gộp vào `universalDiscount(amount, isLoyalty, isSeasonal, ...)`, các chính sách khác nhau sẽ bị ràng buộc trong cùng một hàm. Đây là **sự giống nhau ngẫu nhiên về cú pháp**, chưa chắc là một tri thức cần được chia sẻ.

Ngược lại, nếu cả hai đều phải dùng một **quy tắc làm tròn tiền chuẩn của công ty**, việc trích riêng một helper nhỏ về rounding có thể là đúng: tri thức **quy tắc làm tròn** thật sự chung và cần nhất quán.

**Một số câu hỏi kiểm tra:**

1. Khi yêu cầu A thay đổi, yêu cầu B có cần thay đổi cùng lúc không?
2. Hai chỗ có cùng chủ sở hữu/ngôn ngữ nghiệp vụ không?
3. Có bất biến hoặc hợp đồng chung thực sự cần giữ không?
4. Abstraction mới có tên phản ánh khái niệm domain không?
5. Có bao nhiêu biến cờ/nhánh cần thêm để nó xử lý được cả A và B?

Nếu một abstraction liên tục được mở rộng bởi các cờ như `isSpecial`, `skipValidation`, `useLegacyMode`, rất có thể các trường hợp không còn chia sẻ một hợp đồng lành mạnh.

## 10. Những câu hỏi nên trả lời trước khi chọn Design Pattern

| Pattern hoặc cơ chế | Bằng chứng nên có | Cảnh báo lạm dụng |
| --- | --- | --- |
| **Strategy** | Các thuật toán cùng vai trò cần thay thế/biến thiên độc lập | Chỉ có một phép tính ngắn |
| **Factory Method/Abstract Factory** | Quá trình chọn/tạo object có logic thật; nhiều họ object tương ứng | Factory chỉ gọi một constructor |
| **Builder** | Nhiều tham số tùy chọn, tổ hợp cần kiểm tra, quá trình dựng có bước | Object có 2–3 field rõ ràng |
| **Decorator** | Cần ghép các hành vi quanh nhiều object cùng interface | Một wrapper chỉ forward `return next.call()` |
| **Observer/Event** | Có nhiều bên phản ứng độc lập, cần tách publish/subscribe | Lời gọi đồng bộ một chiều đã đủ |
| **State** | Nhiều hành vi thay đổi theo vòng đời và bảng chuyển trạng thái phức tạp | Hai trạng thái với một câu lệnh `if` |
| **Repository/Port** | Business cần cách ly lưu trữ, hạ tầng hoặc public contract | Interface sao chép 1:1 toàn bộ API của class mà không tách được gì |
| **Dependency Injection** | Cần cấu hình vòng đời và cung cấp phụ thuộc rõ ràng | Bean container cho phép tính thuần không có phụ thuộc |
| **Inheritance** | Thực sự có quan hệ subtype giữ hợp đồng LSP | Chỉ muốn tái sử dụng 5 dòng code |

Bảng này không phải luật chọn pattern. Nó giúp tránh chọn từ **tên pattern** trước khi hiểu **áp lực thay đổi**.

## 11. Một quy trình refactor dựa trên bằng chứng

### Bước 1 — mô tả hành vi hiện tại

Đầu tiên viết rõ input, output, tiền điều kiện, hậu điều kiện và ca biên. Ví dụ với phí giao hàng: đúng ngưỡng 500.000, thấp hơn 1 VND, miễn phí, weight = 0, làm tròn phần lẻ kilogram.

### Bước 2 — ghi nhận thay đổi thật

Một dấu hiệu tốt là nhiều lần chỉnh sửa cùng một điểm biến thiên: thêm cách tính phí, thay nhà cung cấp thanh toán, thêm mô hình phân quyền, hoặc hai đội cần phát triển cùng một khả năng khác nhau.

Không cần đợi sản phẩm gặp sự cố mới refactor. Nhưng cũng không cần dựng plugin engine cho một tính năng không nằm trong roadmap đã xác thực.

### Bước 3 — xác định điều ổn định và điều biến thiên

Ví dụ:

- Ổn định: `checkout` cần một **số tiền phí hợp lệ**.
- Biến thiên: **cách tính phí** theo chính sách.
- Tách `FeePolicy` đúng ranh giới, thay vì trích cả một “ShippingFramework” quản lý giá, địa chỉ, kho, voucher và vận chuyển cùng lúc.

### Bước 4 — refactor từng bước, có kiểm thử hồi quy

Giữ test cho hành vi cũ, trích một hợp đồng nhỏ, chuyển implementation cũ sang hợp đồng ấy, thêm biến thể mới và chạy test. Không đổi đồng thời toàn bộ tên API, persistence, giao thức và business rule nếu không cần.

### Bước 5 — đánh giá “mức độ ma sát” sau thay đổi

Đừng chỉ hỏi “đã áp dụng SOLID chưa?”. Hãy hỏi:

- Muốn thêm biến thể, **cần sửa bao nhiêu nơi và bao nhiêu hợp đồng công khai?**
- Người mới có cần mở nhiều file để lần ra một công thức không?
- Test logic có cần dựng một graph mock quá lớn không?
- Lỗi runtime do cấu hình hoặc thứ tự decorator có tăng không?
- Có abstraction nào không còn khách hàng hoặc không còn ý nghĩa?

Nếu refactor chỉ chuyển mọi dòng `if` thành các lớp trống mà không cải thiện tình huống thay đổi cụ thể, hãy cân nhắc đơn giản hóa lại.

~~~mermaid
flowchart LR
    A["Yêu cầu có thật"] --> B["Giải pháp rõ nhất đáp ứng yêu cầu"]
    B --> C["Test bất biến và ca biên"]
    C --> D["Quan sát thay đổi"]
    D --> E{"Có điểm biến thiên / coupling gây chi phí?"}
    E -->|"Chưa"| F["Giữ thiết kế nhỏ"]
    E -->|"Có"| G["Trích abstraction tối thiểu"]
    G --> H["Đo lại độ dễ đổi, test và đọc"]
    F --> D
    H --> D
~~~

## 12. Những trường hợp nên trừu tượng hóa sớm có chủ đích

**YAGNI không có nghĩa “không thiết kế”**. Có những ranh giới đáng đầu tư từ sớm vì nhu cầu hoặc rủi ro đã được xác nhận:

- **API công khai:** nhiều client sẽ phụ thuộc vào hợp đồng, nên khó thay đổi phá tương thích.
- **Tích hợp nhà cung cấp:** SDK bên thứ ba dễ đổi, có timeout, lỗi mạng, chính sách retry hoặc giới hạn quyền; port theo nhu cầu business giúp cô lập.
- **Bảo mật và phân quyền:** có ranh giới truy cập rõ để tránh các đường đi bỏ qua kiểm tra bắt buộc.
- **Tiền, giao dịch và dữ liệu quan trọng:** thiết kế kiểu giá trị, invariant, transaction boundary rõ ngay từ đầu thường rẻ hơn xử lý sai lệch về sau.
- **Tính khả kiểm thử của nghiệp vụ cốt lõi:** tách đồng hồ (`Clock`), nguồn ngẫu nhiên hoặc API mạng ra khỏi logic khi tính xác định của test thực sự bị ảnh hưởng.
- **Nhiều nhóm hoặc module độc lập:** cần hợp đồng ổn định đã xác định, không chỉ là giả định sẽ có “vô số module”.

Điểm chung: **có bằng chứng về chi phí thay đổi hoặc rủi ro**. Không nên suy diễn từ ví dụ nhỏ rằng tất cả abstraction trong kiến trúc ứng dụng đều là thừa.

## 13. Overengineering trong Java và Spring

Một số trường hợp cụ thể:

**Tạo interface cho mỗi `@Service` chỉ để Spring inject được** là không cần thiết: Spring có thể inject class cụ thể qua constructor. Interface nên thể hiện một hợp đồng cần bảo vệ, nhiều implementation hoặc ranh giới module/hạ tầng, không đơn thuần là vật trang trí.

**Đưa mọi helper thành bean** làm tăng phụ thuộc vào container, trong khi một phương thức thuần hoặc một value object có thể được tạo và test trực tiếp. Không phải toàn bộ code Java cần được “quản lý bởi Spring”.

**Dùng `@Lazy` để né circular dependency** có thể làm ứng dụng khởi động nhưng chưa giải quyết vòng trách nhiệm giữa service. Nên xem lại hướng phụ thuộc và nơi điều phối thay vì coi việc hoãn khởi tạo là sửa kiến trúc.

**Dùng AOP cho một chỗ gọi duy nhất** có thể khó theo dõi hơn lời gọi rõ. AOP có ích ở cross-cutting concern áp dụng có hệ thống, nhưng phải hiểu join point, thứ tự advice, proxy và giới hạn self-invocation.

**Tạo event bus cho mọi lời gọi trong cùng một transaction** có thể làm việc xác định khi nào hoàn thành, khi nào lỗi và lúc nào dữ liệu đã commit trở nên khó hơn. Event hợp lý khi cần nhiều subscriber hoặc xử lý bất đồng bộ; nó không tự cung cấp exactly-once hay transaction.

Với các ví dụ trên, tiêu chí là **mục tiêu vận hành và ranh giới nghiệp vụ**, không phải “framework làm được nên dùng”.

## 14. Bài tập tự đánh giá thiết kế

Giả sử một ứng dụng quản lý lịch học cần chức năng:

- Mỗi lớp có `startTime`, `endTime`, `teacherId`.
- Không chấp nhận `endTime` trước hoặc bằng `startTime`.
- Ban đầu chỉ có một quy tắc tính số buổi: mỗi lịch được tạo đại diện một buổi.
- Sau khi nhận yêu cầu thật, có thêm buổi lặp hằng tuần và buổi đặc biệt.
- Các trường hợp mới có quy tắc kiểm tra khác nhau.

**Thực hành:**

1. Viết một `record ClassSession` hoặc class bất biến đơn giản với validation, không cần Factory cho bản đầu tiên.
2. Viết test cho thời gian bắt đầu/kết thúc, trường hợp bằng nhau và dữ liệu null.
3. Thiết kế phiên bản thứ hai khi xuất hiện lịch lặp: trước tiên thử một API nhỏ có tên rõ; nếu quy tắc mỗi loại trở nên độc lập, cân nhắc Strategy hoặc các domain type riêng.
4. Vẽ sơ đồ phụ thuộc trước và sau, chỉ ra nơi đặt các quy tắc thay đổi.
5. So sánh phương án `switch` với interface: phương án nào khiến thêm kiểu lịch mới dễ test, ít sửa nơi khác và đọc dễ hơn?
6. Xem có abstraction nào chỉ forward lời gọi và không bảo vệ hợp đồng nào không; thử bỏ nó.
7. Giải thích vì sao **hai kiểu lịch có vài đoạn code giống nhau** chưa đủ chứng minh chúng phải chung một lớp cơ sở.

**Tiêu chí đạt:** thiết kế đáp ứng đúng yêu cầu hiện tại; không có bước truy cập hoặc factory thừa vô lý; các ràng buộc được kiểm thử; mỗi abstraction mới có lý do tạo cụ thể; và khi có yêu cầu mới, refactor giữ nguyên hành vi cũ.

## 15. Kết luận: abstraction tốt phải “trả được tiền thuê”

Một mẫu thiết kế chỉ có giá trị khi nó giúp hệ thống **đúng hơn, dễ đọc hơn, dễ kiểm thử hơn hoặc thay đổi an toàn hơn** trong một bối cảnh xác định. Thiết kế quá sớm thường biến dự đoán chưa chắc đúng thành hợp đồng phải bảo trì.

**Cách tư duy hữu ích:** bắt đầu với giải pháp đơn giản, đặt tên theo domain, bảo vệ invariant và test; sau đó quan sát các thay đổi thực tế để trích **abstraction nhỏ nhất giải quyết đúng loại thay đổi**. Đừng tối ưu số lớp ít nhất, cũng đừng tối ưu số pattern nhiều nhất. Hãy tối ưu khả năng một người hiểu và sửa hệ thống mà không làm hỏng điều đã chạy đúng.