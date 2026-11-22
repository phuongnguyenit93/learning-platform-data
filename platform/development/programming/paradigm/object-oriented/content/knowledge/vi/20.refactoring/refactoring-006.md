# Thay điều kiện theo loại bằng đa hình (Replace Conditional with Polymorphism) — Java OOP

## 1. Bài toán: vì sao nhiều nhánh theo loại gây khó bảo trì?

Giả sử ứng dụng bán hàng hỗ trợ ba hình thức nhận hàng: STANDARD (giao thường), EXPRESS (giao nhanh), PICKUP (khách tự nhận). Mỗi loại có quy tắc tính phí và thời gian giao khác nhau.

Cách viết ban đầu thường kiểm tra loại bằng switch hoặc chuỗi if/else:

~~~java
switch (request.type) {
    case STANDARD: /* tính phí giao thường */ break;
    case EXPRESS:  /* tính phí giao nhanh */ break;
    case PICKUP:   /* tự nhận hàng */ break;
}
~~~

Một khối như vậy không tự động là lỗi. Vấn đề xuất hiện khi **cùng một điều kiện theo loại** lặp lại ở nhiều nghiệp vụ (tính phí, xác định thời gian giao, xử lý yêu cầu, xuất thông báo), khiến bổ sung loại mới phải sửa nhiều chỗ. Những nhánh có liên quan dễ bị bỏ sót, và một lớp dần gánh nhiều hành vi của các loại đối tượng khác nhau.

**Thay điều kiện theo loại bằng đa hình** là kỹ thuật refactoring: đưa hành vi thay đổi theo loại vào các implementation của một hợp đồng chung. Đoạn gọi chỉ yêu cầu đối tượng thực hiện hành vi; Java chọn phương thức tương ứng qua **dynamic dispatch**.

> Mục tiêu là thay đổi cách tổ chức code **mà vẫn giữ nguyên hợp đồng quan sát được**: đầu vào hợp lệ, kết quả, exception và side effect đã được cam kết. Không phải cứ thấy switch là phải tạo hệ phân cấp lớp.

## 2. Phân biệt cấu trúc trước và sau

| Góc nhìn | Điều kiện theo loại | Đa hình |
|---|---|---|
| Chọn hành vi | Caller dùng if/else, switch, instanceof | Caller gọi phương thức chung trên interface/lớp cha |
| Vị trí quy tắc | Nhiều nhánh trong một lớp lớn | Mỗi implementation nắm quy tắc riêng |
| Bổ sung loại | Sửa từng switch có liên quan | Thêm implementation và đăng ký ở ranh giới tạo/chọn đối tượng |
| Kiểm thử | Một lớp ôm nhiều nhánh | Test hợp đồng chung và từng biến thể |
| Khả năng mở rộng | Dễ bỏ sót nhánh | Phụ thuộc cách tổ chức đăng ký và cấu trúc loại |
| Chi phí | Ít lớp, đơn giản cho vài nhánh | Nhiều đối tượng và lớp hơn, cần thiết kế interface hợp lý |

Kỹ thuật này thường liên quan **Open/Closed Principle**: mở rộng hành vi bằng implementation mới, hạn chế sửa code nghiệp vụ đã ổn định. Nó không loại bỏ mọi bước chọn loại: dữ liệu đầu vào vẫn có thể chứa mã loại, và tại một ranh giới vẫn cần ánh xạ mã đó sang đối tượng phù hợp.

~~~mermaid
flowchart LR
    C["Client"] --> B["DeliveryService"]
    B --> P["DeliveryPolicy interface"]
    S["StandardPolicy"] -.-> P
    E["ExpressPolicy"] -.-> P
    K["PickupPolicy"] -.-> P
~~~

Trong mô hình này, DeliveryService không biết công thức phí của từng loại. Nó chỉ dùng interface DeliveryPolicy.

## 3. Ví dụ Java 11 chạy được: chuyển từ switch sang đa hình

### Hợp đồng nghiệp vụ

Đơn hàng có giá trị tiền hàng (VND) không âm và trọng lượng nguyên dương (kg). Ta giả định trọng lượng tính theo kg nguyên để tập trung vào refactor, không phải bài toán đo lường thực tế.

| Loại | Quy tắc phí vận chuyển | Số ngày giao dự kiến |
|---|---|---:|
| STANDARD | Nếu giá trị đơn từ 500.000 VND: 0; nếu thấp hơn: 20.000 + 5.000 × kg | 5 |
| EXPRESS | 45.000 + 10.000 × kg | 1 |
| PICKUP | 0 VND | 0 (khách tự đến lấy) |

Kết quả của dịch vụ là DeliveryQuote gồm feeVnd và etaDays. Bản cũ và bản sau refactor phải cho **cùng kết quả** đối với toàn bộ đầu vào hợp lệ, đồng thời không thay đổi quy tắc xác thực đã cam kết.

Lưu toàn bộ chương trình dưới đây trong file **DeliveryRefactoringDemo.java**. Mã sử dụng Java 11 trở lên, không cần Maven, Spring hoặc thư viện kiểm thử.

~~~java
import java.util.Map;
import java.util.Objects;

public class DeliveryRefactoringDemo {
    enum DeliveryType {
        STANDARD, EXPRESS, PICKUP
    }

    static final class DeliveryRequest {
        final DeliveryType type;
        final long orderValueVnd;
        final int weightKg;

        DeliveryRequest(DeliveryType type,
                        long orderValueVnd,
                        int weightKg) {
            if (type == null || orderValueVnd < 0 || weightKg <= 0) {
                throw new IllegalArgumentException("Invalid delivery request");
            }
            this.type = type;
            this.orderValueVnd = orderValueVnd;
            this.weightKg = weightKg;
        }
    }

    static final class DeliveryQuote {
        final long feeVnd;
        final int etaDays;

        DeliveryQuote(long feeVnd, int etaDays) {
            this.feeVnd = feeVnd;
            this.etaDays = etaDays;
        }
    }

    // TRƯỚC: mọi quy tắc tính phí và thời gian ở một switch.
    static final class LegacyDeliveryService {
        DeliveryQuote quote(DeliveryRequest request) {
            Objects.requireNonNull(request, "request");

            switch (request.type) {
                case STANDARD:
                    long standardFee =
                            request.orderValueVnd >= 500_000L
                            ? 0L
                            : Math.addExact(20_000L,
                                  Math.multiplyExact(
                                      5_000L, (long) request.weightKg));
                    return new DeliveryQuote(standardFee, 5);

                case EXPRESS:
                    long expressFee = Math.addExact(45_000L,
                            Math.multiplyExact(
                                10_000L, (long) request.weightKg));
                    return new DeliveryQuote(expressFee, 1);

                case PICKUP:
                    return new DeliveryQuote(0L, 0);

                default:
                    throw new IllegalStateException("Unsupported type");
            }
        }
    }

    // SAU: một hợp đồng chung cho mọi loại giao hàng.
    interface DeliveryPolicy {
        DeliveryQuote quote(DeliveryRequest request);
    }

    static final class StandardPolicy implements DeliveryPolicy {
        @Override
        public DeliveryQuote quote(DeliveryRequest request) {
            long fee = request.orderValueVnd >= 500_000L
                    ? 0L
                    : Math.addExact(20_000L,
                          Math.multiplyExact(
                              5_000L, (long) request.weightKg));
            return new DeliveryQuote(fee, 5);
        }
    }

    static final class ExpressPolicy implements DeliveryPolicy {
        @Override
        public DeliveryQuote quote(DeliveryRequest request) {
            long fee = Math.addExact(45_000L,
                    Math.multiplyExact(
                        10_000L, (long) request.weightKg));
            return new DeliveryQuote(fee, 1);
        }
    }

    static final class PickupPolicy implements DeliveryPolicy {
        @Override
        public DeliveryQuote quote(DeliveryRequest request) {
            return new DeliveryQuote(0L, 0);
        }
    }

    // SAU: service điều phối, không chứa công thức theo loại.
    static final class DeliveryService {
        private final Map<DeliveryType, DeliveryPolicy> policies;

        DeliveryService(Map<DeliveryType, DeliveryPolicy> policies) {
            Objects.requireNonNull(policies, "policies");
            this.policies = Map.copyOf(policies);
            for (DeliveryType type : DeliveryType.values()) {
                if (!this.policies.containsKey(type)) {
                    throw new IllegalArgumentException(
                            "Missing policy for " + type);
                }
            }
        }

        DeliveryQuote quote(DeliveryRequest request) {
            Objects.requireNonNull(request, "request");
            // Đây là tra cứu chính sách, không phải các nhánh tính phí.
            DeliveryPolicy policy = policies.get(request.type);
            return policy.quote(request); // Dynamic dispatch
        }
    }

    private static void check(boolean ok, String message) {
        if (!ok) {
            throw new AssertionError(message);
        }
    }

    private static void assertScenario(
            LegacyDeliveryService before,
            DeliveryService after,
            DeliveryRequest request,
            long expectedFee,
            int expectedDays) {

        DeliveryQuote oldQuote = before.quote(request);
        DeliveryQuote newQuote = after.quote(request);

        // Kiểm tra yêu cầu nghiệp vụ bằng kỳ vọng độc lập.
        check(oldQuote.feeVnd == expectedFee,
                "Old fee differs from requirement");
        check(oldQuote.etaDays == expectedDays,
                "Old ETA differs from requirement");
        check(newQuote.feeVnd == expectedFee,
                "New fee differs from requirement");
        check(newQuote.etaDays == expectedDays,
                "New ETA differs from requirement");

        // Đồng thời xác nhận hành vi cũ/sau refactor tương đương.
        check(oldQuote.feeVnd == newQuote.feeVnd,
                "Fee changed after refactoring");
        check(oldQuote.etaDays == newQuote.etaDays,
                "ETA changed after refactoring");
    }

    private static void expectInvalid(Runnable action) {
        try {
            action.run();
        } catch (IllegalArgumentException expected) {
            return;
        }
        throw new AssertionError("Expected IllegalArgumentException");
    }

    public static void main(String[] args) {
        LegacyDeliveryService before = new LegacyDeliveryService();

        DeliveryService after = new DeliveryService(Map.of(
                DeliveryType.STANDARD, new StandardPolicy(),
                DeliveryType.EXPRESS, new ExpressPolicy(),
                DeliveryType.PICKUP, new PickupPolicy()
        ));

        // Dưới ngưỡng: 20.000 + 5.000 × 2 = 30.000.
        assertScenario(before, after,
                new DeliveryRequest(DeliveryType.STANDARD,
                                    499_999L, 2),
                30_000L, 5);

        // Đúng ngưỡng miễn phí.
        assertScenario(before, after,
                new DeliveryRequest(DeliveryType.STANDARD,
                                    500_000L, 2),
                0L, 5);

        // Giao nhanh: 45.000 + 10.000 × 3 = 75.000.
        assertScenario(before, after,
                new DeliveryRequest(DeliveryType.EXPRESS,
                                    100_000L, 3),
                75_000L, 1);

        // Tự đến lấy: không tính phí và không có ngày giao.
        assertScenario(before, after,
                new DeliveryRequest(DeliveryType.PICKUP,
                                    0L, 1),
                0L, 0);

        // Các quy tắc dữ liệu không hợp lệ vẫn được giữ.
        expectInvalid(() ->
                new DeliveryRequest(DeliveryType.STANDARD, -1L, 1));
        expectInvalid(() ->
                new DeliveryRequest(DeliveryType.EXPRESS, 100L, 0));
        expectInvalid(() ->
                new DeliveryRequest(null, 100L, 1));

        System.out.println("4 scenarios + 3 invalid inputs: PASS");
    }
}
~~~

Biên dịch và chạy trong thư mục chứa file:

~~~bash
javac DeliveryRefactoringDemo.java
java DeliveryRefactoringDemo
~~~

Khi các phép kiểm tra đều đạt:

~~~text
4 scenarios + 3 invalid inputs: PASS
~~~

Chương trình cố tình viết kiểm chứng **hai chiều**: so sánh giá trị trước/sau refactor, đồng thời so sánh với kỳ vọng nghiệp vụ độc lập. Chỉ so hai phiên bản với nhau là chưa đủ, vì cả hai hoàn toàn có thể cùng thực hiện sai một công thức.

### Điều gì đã thay đổi và điều gì giữ nguyên?

| Nội dung | Trước refactor | Sau refactor |
|---|---|---|
| Công thức giao thường | Nhánh STANDARD trong LegacyDeliveryService | StandardPolicy.quote |
| Công thức giao nhanh | Nhánh EXPRESS | ExpressPolicy.quote |
| Tự đến lấy | Nhánh PICKUP | PickupPolicy.quote |
| Chọn loại phù hợp | switch theo enum | Map ánh xạ enum → DeliveryPolicy |
| Chạy hành vi theo loại | Thực thi nhánh đã chọn | Gọi policy.quote; JVM chọn implementation |
| Điều kiện miễn phí tại 500.000 | Giữ nguyên | Giữ nguyên |
| Kết quả và quy tắc kiểm tra dữ liệu | Hợp đồng gốc | Giữ nguyên |

### Vì sao đây là đa hình?

Biến policy có kiểu **DeliveryPolicy**, nhưng đối tượng thực tế có thể là StandardPolicy, ExpressPolicy hoặc PickupPolicy. Khi gọi policy.quote(request), JVM thực thi phương thức override trên class thực tế. Đoạn DeliveryService không cần biết công thức nào được chạy.

Đây là **đa hình lúc chạy (runtime polymorphism)** qua interface và method overriding, không chỉ là việc đổi switch thành ba phương thức private. Nếu ba công thức vẫn nằm trong một class với điều kiện rẽ nhánh theo enum, hành vi theo loại chưa được phân phối cho từng đối tượng.

## 4. Các bước refactor có thể áp dụng trong dự án

1. **Khoanh vùng điều kiện theo loại.** Tìm các nhánh đang kiểm tra cùng một type/discriminator như enum, mã chuỗi hoặc instanceof. Xác định nhánh nào thật sự thuộc cùng một hành vi.
2. **Viết characterization tests.** Ghi nhận kết quả hiện tại của các input quan trọng: loại phổ biến, loại ít dùng, ngưỡng giá, trường hợp lỗi và side effect có ý nghĩa.
3. **Rút ra hợp đồng chung.** Ví dụ DeliveryPolicy.quote(request). Chọn method theo trách nhiệm nghiệp vụ, không tạo interface chỉ để che giấu một switch.
4. **Tách implementation từng loại.** Di chuyển lần lượt công thức và logic đặc thù từ nhánh sang StandardPolicy, ExpressPolicy và PickupPolicy. Mỗi lần di chuyển đều biên dịch/test lại.
5. **Giới hạn nơi lựa chọn implementation.** Dùng factory, dependency injection container hoặc registry Map ở ranh giới tạo/chọn đối tượng. Code nghiệp vụ chỉ nhận hoặc tra về DeliveryPolicy.
6. **Xóa điều kiện cũ khi không còn cần.** Tránh duy trì song song switch cũ và hệ policy mới quá lâu vì rất dễ lệch hành vi.
7. **Chạy test hồi quy và integration test.** Xác nhận đầu ra, exception, hợp đồng collaborator, transaction và tài nguyên bên ngoài nếu ứng dụng thực có sử dụng.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant S as DeliveryService
    participant R as Registry
    participant P as DeliveryPolicy cụ thể
    C->>S: quote(request)
    S->>R: get(request.type)
    R-->>S: policy
    S->>P: quote(request)
    P-->>S: DeliveryQuote
    S-->>C: DeliveryQuote
~~~

## 5. Chọn interface, lớp trừu tượng, subclass hay Strategy?

**Interface + implementation** như ví dụ phù hợp khi các biến thể chia sẻ hợp đồng nhưng công thức khác nhau, không có nhiều trạng thái/chức năng chung cần kế thừa.

**Abstract class + subclass** phù hợp nếu có bất biến và một số bước xử lý mặc định thật sự dùng chung, ví dụ mọi phương thức đều cần một cách kiểm tra dữ liệu thống nhất. Tránh dồn quá nhiều logic điều kiện ngược trở lại lớp cha.

**Strategy pattern (ưu tiên composition)** phù hợp nếu hành vi được chọn theo cấu hình hoặc thay đổi lúc chạy, không đồng nhất với kiểu của thực thể miền. Trong ví dụ, STANDARD/EXPRESS/PICKUP là chính sách giao hàng được gán theo yêu cầu, không nhất thiết cần tạo các lớp con của Order.

**Enum có method riêng cho từng hằng** cũng là một hình thức đa hình trong Java:

~~~java
enum SimpleDelivery {
    STANDARD {
        @Override long fee(int kg) {
            return 20_000L + 5_000L * kg;
        }
    },
    EXPRESS {
        @Override long fee(int kg) {
            return 45_000L + 10_000L * kg;
        }
    };

    abstract long fee(int kg);
}
~~~

Đây là ví dụ ngắn **minh họa cú pháp**, không thay thế hợp đồng tính phí đầy đủ ở mục 3 (chưa có miễn phí theo giá trị đơn, kiểm tra input hoặc xử lý tràn số). Enum-specific method thích hợp với tập biến thể cố định, logic ngắn. Nếu các chính sách phức tạp, cần dependency ngoài hoặc muốn đăng ký implementation mới theo module, các lớp Strategy độc lập thường linh hoạt và dễ kiểm thử hơn.

## 6. Những sai lầm thường gặp

| Sai lầm | Vì sao không đạt mục tiêu? | Hướng xử lý |
|---|---|---|
| Tạo interface nhưng service vẫn switch theo type để gọi các class cụ thể | Caller vẫn nắm chi tiết và phải sửa nhiều nhánh | Đưa lựa chọn sang factory/registry, gọi một hợp đồng |
| Dùng instanceof rồi ép kiểu cho mọi biến thể | Phụ thuộc subtype còn nguyên | Gọi phương thức đa hình; type-check chỉ giữ nếu thật sự cần ở boundary |
| Mọi policy lại tự kiểm tra request.type rồi quyết định xử lý | Điều kiện bị sao chép sang nhiều class | Registry chọn đúng policy; policy chỉ xử lý quy tắc của nó |
| Thêm superclass khổng lồ để chia sẻ nhiều chi tiết không liên quan | Coupling cao, thay lớp cha ảnh hưởng mọi loại | Tách abstraction gọn, ưu tiên composition |
| Di chuyển code đồng thời sửa công thức nghiệp vụ | Khó chứng minh refactor bảo toàn hành vi | Giữ refactor và thay đổi chính sách ở những bước có test riêng |
| Thêm subtype mà quên đăng ký trong registry | Lỗi runtime khi gặp loại mới | Kiểm tra tính đầy đủ đăng ký, fail fast khi khởi tạo |
| Coi mọi switch là code smell | Tạo nhiều lớp cho một điều kiện đơn giản, ổn định | Giữ switch khi dễ hiểu và ít thay đổi |
| Test chỉ xác minh phương thức policy được gọi một lần | Không chứng minh phí giao hàng đúng | Assert feeVnd, etaDays và các ca biên độc lập |

### Bổ sung loại mới có hoàn toàn không cần sửa code cũ?

Không tuyệt đối. Trong kiến trúc dùng enum và Map ở ví dụ, khi thêm SAME_DAY, ta vẫn phải khai báo hằng enum, tạo SameDayPolicy và đăng ký vào Map. Điều quan trọng là **DeliveryService.quote không cần thêm công thức hoặc nhánh mới**. Nếu yêu cầu cho phép plugin đăng ký động, có thể đưa quá trình khám phá implementation vào DI container/factory; đổi lại sẽ có chi phí cấu hình, kiểm tra trùng và xử lý thiếu policy.

### Có nên đưa các field đặc thù vào interface chung?

Không nên bắt mọi loại chứa dữ liệu không dùng tới chỉ để đồng nhất hình dạng. Nếu mỗi loại có đầu vào hoàn toàn khác, cân nhắc request chuyên biệt, abstraction theo hành vi, hoặc ranh giới xác thực rõ ràng. Interface nên thể hiện khả năng chung thật sự, không phải một tập method buộc nhiều lớp override rồi ném UnsupportedOperationException.

### Vấn đề với đối tượng có trạng thái

Các policy trong ví dụ là stateless nên có thể dùng chung an toàn. Nếu một implementation ghi vào field mutable khi phục vụ nhiều request, phải xét vòng đời object, thread safety và đồng bộ. Refactor không được vô tình biến trạng thái riêng của mỗi request thành shared singleton state.

## 7. Kiểm thử để chứng minh không đổi hành vi

Việc thay switch bằng đa hình không được làm mất trường hợp biên. Nên kiểm thử ở hai mức:

- **Contract tests cho DeliveryService:** mỗi loại trả đúng phí và ETA, STANDARD đúng ngưỡng 499.999/500.000, input không hợp lệ bị từ chối, loại mới được đăng ký đầy đủ.
- **Unit tests từng policy:** tập trung vào công thức đặc thù và tràn số. Ví dụ ExpressPolicy.quote với trọng lượng lớn phải dùng phép toán long chính xác hoặc ném ArithmeticException khi tràn.
- **Integration tests khi có hệ thống ngoài:** kiểm tra việc factory/DI tạo đúng policy, thực thi thanh toán/gửi yêu cầu giao hàng với adapter thật trong môi trường kiểm thử.

Ví dụ kiểm thử JUnit 5 riêng cho biên giao thường (giả định file chương trình ở trên nằm cùng package):

~~~java
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;

class StandardPolicyTest {
    @Test
    void freeShippingAppliesAtThreshold() {
        DeliveryRefactoringDemo.DeliveryPolicy policy =
                new DeliveryRefactoringDemo.StandardPolicy();

        var below = policy.quote(
                new DeliveryRefactoringDemo.DeliveryRequest(
                    DeliveryRefactoringDemo.DeliveryType.STANDARD,
                    499_999L, 2));

        var atThreshold = policy.quote(
                new DeliveryRefactoringDemo.DeliveryRequest(
                    DeliveryRefactoringDemo.DeliveryType.STANDARD,
                    500_000L, 2));

        assertEquals(30_000L, below.feeVnd);
        assertEquals(5, below.etaDays);
        assertEquals(0L, atThreshold.feeVnd);
        assertEquals(5, atThreshold.etaDays);
    }
}
~~~

Dùng JUnit Jupiter trong test scope để chạy ví dụ trên. Lưu ý policy.quote nhận DeliveryRequest có type để minh họa contract với hệ thống hiện có, nhưng bản thân StandardPolicy không dựa vào trường type; DeliveryService là nơi quyết định đúng policy từ type. Trong thiết kế trưởng thành, có thể truyền riêng dữ liệu cần thiết cho policy để tránh gây hiểu nhầm rằng policy luôn phải kiểm tra enum.

## 8. Khi nào KHÔNG nên áp dụng?

Một switch ngắn, đứng ở **một nơi**, phân loại mã trạng thái để log hoặc ánh xạ đơn giản thường dễ hiểu hơn cả một cây class. Nếu tập loại là cố định và các hành vi hiếm khi thay đổi, chi phí interface, factory và nhiều file có thể lớn hơn lợi ích.

Cũng không nên thay một phép kiểm tra điều kiện theo **giá trị hoặc trạng thái** bằng subtype chỉ vì có if. Ví dụ ngưỡng miễn phí vận chuyển (orderValueVnd >= 500.000) là quy tắc **bên trong StandardPolicy**, không phải một loại giao hàng mới. Đa hình lựa chọn *họ hành vi* theo loại; các điều kiện nghiệp vụ bên trong mỗi biến thể có thể và nên tiếp tục tồn tại.

Trước khi refactor, đặt ba câu hỏi:

1. Điều kiện có lặp lại ở nhiều hành vi và thường phải sửa đồng thời không?
2. Các biến thể có một hợp đồng chung đủ rõ để caller sử dụng mà không biết class cụ thể không?
3. Bài test hiện có có thể bảo vệ đầu ra, lỗi và side effect khi chuyển code sang implementation khác không?

Nếu cả ba câu trả lời đều có, Replace Conditional with Polymorphism thường đem lại lợi ích rõ rệt.

## 9. Bài tập

**Bài 1 — Thêm SAME_DAY:** Giả sử phí giao trong ngày là 80.000 + 12.000 × kg, ETA = 0 ngày (trong ngày). Thêm DeliveryType.SAME_DAY, SameDayPolicy và đăng ký policy. Viết test độc lập xác minh chính xác công thức, không thêm nhánh vào DeliveryService.quote.

**Bài 2 — Phát hiện regression:** Cố tình đổi ngưỡng miễn phí STANDARD thành lớn hơn 500.000 (thay vì lớn hơn hoặc bằng). Chạy chương trình; case bằng đúng 500.000 phải fail.

**Bài 3 — Nhận diện trùng điều kiện:** Nếu một class khác cũng dùng switch theo DeliveryType để format mô tả dịch vụ, cân nhắc đưa tên hiển thị vào DeliveryPolicy. Giải thích trường hợp việc đưa trách nhiệm định dạng vào policy lại làm giảm cohesion, và đề xuất một collaborator riêng nếu cần.

**Bài 4 — Kiểm tra đăng ký:** Bỏ một policy trong Map; hãy kiểm tra constructor của DeliveryService từ chối cấu hình thiếu bằng IllegalArgumentException trước khi tiếp nhận request.

**Bài 5 — Lựa chọn kỹ thuật:** Với bốn mã trạng thái chỉ đổi màu nhãn trên UI, so sánh một switch ngắn với bốn class. Chọn phương án có độ phức tạp thấp hơn và giải thích vì sao đa hình không phải lúc nào cũng tốt.

## 10. Ghi nhớ

**Replace Conditional with Polymorphism** giúp đưa hành vi biến đổi theo loại vào đúng đối tượng chịu trách nhiệm. Caller gọi hợp đồng chung, Java tự dispatch đến implementation tương ứng. Đây là một kỹ thuật **tái cấu trúc**, nên cần bảo toàn hành vi trong quá trình thực hiện; không nhầm việc thay đổi kiến trúc với việc thay đổi chính sách nghiệp vụ. Chọn đa hình khi nó thực sự giảm nhánh lặp, tăng cohesion, giảm coupling và giúp bổ sung biến thể một cách kiểm soát được.