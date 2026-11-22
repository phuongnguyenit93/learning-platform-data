# Kiểm thử hành vi thông qua hợp đồng của functional interface

## Mục tiêu

Khi một API Java nhận **functional interface**, người gọi thường truyền vào lambda hoặc method reference để cung cấp hành vi. Compiler bảo đảm lambda phù hợp **chữ ký phương thức trừu tượng duy nhất (SAM)**, nhưng không tự bảo đảm rằng hành vi ấy **đúng nghiệp vụ**. Vì vậy, kiểm thử cần dựa trên **hợp đồng hành vi đã công bố**: đầu vào hợp lệ, kết quả mong đợi, bất biến, trường hợp biên, ngoại lệ, tác dụng phụ và những cam kết mà nhiều triển khai phải cùng tuân thủ.

Sau bài học, bạn có thể:

- Phân biệt **hợp đồng kiểu** (SAM) với **hợp đồng hành vi** (quy tắc nghiệp vụ).
- Thiết kế các ca kiểm thử “hộp đen” cho một functional interface mà không phụ thuộc cú pháp lambda, anonymous class hay method reference.
- Viết **bộ kiểm thử hợp đồng dùng chung** cho nhiều triển khai, phát hiện một triển khai sai ngay cả khi mã biên dịch thành công.
- Kiểm tra kết quả chính xác, bất biến, ngoại lệ, trường hợp biên và tác dụng phụ mà hợp đồng cho phép hoặc cấm.
- Dùng Java 17+ để chạy chương trình kiểm thử độc lập; biết cách chuyển cùng nguyên tắc sang JUnit trong dự án thực tế.

## 1. Vì sao functional interface cần kiểm thử hợp đồng?

Một functional interface mô tả một **vai trò có một phương thức trừu tượng chức năng**. Ví dụ:

~~~java
@FunctionalInterface
interface DiscountPolicy {
    long discountCents(long subtotalCents);
}
~~~

Về mặt kiểu, lambda sau hoàn toàn có thể được gán cho `DiscountPolicy`:

~~~java
DiscountPolicy broken = amount -> -100L;
~~~

Compiler không báo lỗi vì lambda nhận một `long` và trả về một `long`, đúng SAM. Nhưng nếu ứng dụng quy định **tiền giảm giá không được âm và không được vượt tổng tiền**, hành vi này sai hoàn toàn.

Hai lớp hợp đồng cần tách rõ:

| Lớp hợp đồng | Điều gì được bảo đảm? | Cơ chế kiểm tra |
| --- | --- | --- |
| **Kiểu / cấu trúc SAM** | Số và kiểu tham số, kiểu kết quả, ràng buộc checked exception, functional interface hợp lệ | Compiler, type checking, `@FunctionalInterface` |
| **Hành vi / ngữ nghĩa** | Đầu vào được hỗ trợ, kết quả đúng, ngoại lệ cần ném, tính ổn định, thứ tự, tác dụng phụ | Kiểm thử, đặc tả nghiệp vụ, review và quan sát runtime |

**`@FunctionalInterface` không phải công cụ kiểm thử nghiệp vụ.** Nó giúp compiler xác nhận interface còn là functional interface; không thể tự biết “giảm giá phải nằm trong khoảng từ 0 đến tổng tiền”.

Với Java hiện hành, nguyên tắc vẫn giống Java 8: lambda là một cách cung cấp triển khai của SAM. Bạn nên kiểm tra **hành vi có thể quan sát qua phương thức của interface**, không kiểm tra chuỗi mã nguồn của lambda.

## 2. Viết hợp đồng đủ rõ trước khi viết test

Một chữ ký như `long discountCents(long subtotalCents)` chỉ nói về **kiểu**. Nếu không có tài liệu, không thể suy ra mặc nhiên:

- Có chấp nhận giá trị âm không?
- Kết quả là tiền giảm, phần trăm, hay số tiền cuối cùng phải trả?
- Có làm tròn hay không, theo quy tắc nào?
- Có được trả về giá trị lớn hơn tổng tiền không?
- Cùng đầu vào có phải cho cùng kết quả không?
- Có được ghi log, gửi mạng hoặc thay đổi trạng thái bên ngoài không?

Để kiểm thử, trước hết định nghĩa hợp đồng ví dụ cụ thể:

> `DiscountPolicy.discountCents(subtotalCents)` nhận tổng tiền **không âm** tính bằng cent. Với đầu vào âm, phải ném `IllegalArgumentException`. Với đầu vào hợp lệ, kết quả phải thỏa `0 <= discount <= subtotalCents`, cùng đầu vào cho cùng kết quả và không có tác dụng phụ quan sát được. Từng chính sách có thể công bố thêm quy tắc giảm giá riêng.

Đây là **hợp đồng do ứng dụng lựa chọn**, không phải hành vi Java mặc định của mọi functional interface. Nếu một API của bạn quy định điều khác, kiểm thử phải bám đúng API đó.

Có thể ghi hợp đồng ngay trong Javadoc:

~~~java
@FunctionalInterface
interface DiscountPolicy {
    /**
     * Computes the discount, in cents, for a non-negative subtotal.
     *
     * @param subtotalCents non-negative subtotal in cents
     * @return a value between zero and subtotalCents, inclusive
     * @throws IllegalArgumentException if subtotalCents is negative
     */
    long discountCents(long subtotalCents);
}
~~~

Ngoài Javadoc, tài liệu nghiệp vụ phải nêu rõ nếu cần cam kết **không có side effect** hoặc **kết quả ổn định**. Khi những cam kết này đã được xác định, bộ test mới có cơ sở hợp lý để kiểm tra.

## 3. Kiểm thử hợp đồng (contract testing) có nghĩa gì?

Ở đây, **contract testing** là kiểm thử tất cả các triển khai của cùng một abstraction theo **bộ quy tắc chung**. Nó không nhất thiết liên quan đến giao tiếp microservice hay công cụ consumer-driven contracts.

Mô hình:

~~~text
                    DiscountPolicy
                      |  hợp đồng
             -------------------------
             |           |           |
          lambda      lambda      method reference
         giảm 10%     trần 30     không giảm
             |           |           |
             +-----------+-----------+
                         |
                runCommonContract(...)
                         |
          input hợp lệ, âm, biên, bất biến
                         |
                  PASS hoặc FAIL
~~~

Thay vì sao chép các assertion giống nhau cho từng lambda, bạn viết một hàm kiểm tra **một instance của interface** rồi chạy nó với từng triển khai.

Kiểu kiểm thử này đặc biệt phù hợp với **Strategy**, **Policy**, **Predicate**, **Mapper**, **Validator**, **Comparator** và các callback khi chúng có ràng buộc hành vi chung. Không phải mọi interface đều có cùng tập bất biến: chọn các ca test từ **hợp đồng thật**, đừng tự áp đặt quy tắc không được tài liệu công bố.

## 4. Ví dụ hoàn chỉnh Java 17+: nhiều triển khai, một bộ test chung

Lưu toàn bộ chương trình sau thành **`DiscountContractDemo.java`**. Nó chỉ dùng Java SE, không cần thư viện test bên ngoài.

~~~java
public class DiscountContractDemo {

    @FunctionalInterface
    interface DiscountPolicy {
        /**
         * @param subtotalCents non-negative subtotal in cents
         * @return discount in [0, subtotalCents]
         * @throws IllegalArgumentException for a negative subtotal
         */
        long discountCents(long subtotalCents);
    }

    static void requireNonNegative(long value) {
        if (value < 0) {
            throw new IllegalArgumentException("subtotal must be >= 0");
        }
    }

    // Method reference có cùng chữ ký với SAM.
    static long noDiscount(long subtotalCents) {
        requireNonNegative(subtotalCents);
        return 0;
    }

    // Kiểm tra điều kiện cho mọi implementation.
    static void checkContract(String name, DiscountPolicy policy) {
        long[] inputs = {
            0L, 1L, 9L, 10L, 99L, 100L, Long.MAX_VALUE
        };

        for (long subtotal : inputs) {
            long first = policy.discountCents(subtotal);
            long second = policy.discountCents(subtotal);

            check(first >= 0 && first <= subtotal,
                  name + " violates result range for " + subtotal);
            check(first == second,
                  name + " is not deterministic for " + subtotal);
        }

        boolean rejected = false;
        try {
            policy.discountCents(-1L);
        } catch (IllegalArgumentException expected) {
            rejected = true;
        }
        check(rejected, name + " must reject negative input");

        System.out.println(name + ": contract PASS");
    }

    static void check(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    public static void main(String[] args) {
        DiscountPolicy none = DiscountContractDemo::noDiscount;

        DiscountPolicy tenPercent = subtotal -> {
            requireNonNegative(subtotal);
            return subtotal / 10L; // Làm tròn xuống tới cent.
        };

        DiscountPolicy fixed30 = subtotal -> {
            requireNonNegative(subtotal);
            return Math.min(30L, subtotal);
        };

        checkContract("none", none);
        checkContract("ten-percent", tenPercent);
        checkContract("fixed-30", fixed30);

        // Oracle nghiệp vụ riêng của từng policy.
        check(none.discountCents(100L) == 0L,
              "no-discount calculation is wrong");
        check(tenPercent.discountCents(199L) == 19L,
              "ten-percent rounding is wrong");
        check(fixed30.discountCents(15L) == 15L,
              "fixed discount exceeds small subtotal");
        check(fixed30.discountCents(100L) == 30L,
              "fixed discount cap is wrong");

        System.out.println("examples: PASS");
    }
}
~~~

Biên dịch và chạy trên JDK 17+:

~~~bash
javac --release 17 DiscountContractDemo.java
java DiscountContractDemo
~~~

Stdout dự kiến **chính xác**:

~~~text
none: contract PASS
ten-percent: contract PASS
fixed-30: contract PASS
examples: PASS
~~~

### Phân tích ví dụ

- `none` là **method reference**, `tenPercent` và `fixed30` là **lambda**. Cả ba được đối xử như những `DiscountPolicy` thông thường. Test không cần quan tâm chúng được tạo bằng cách nào.
- `checkContract` nhận trực tiếp **functional interface**. Nó dùng các đầu vào `0`, `1`, giá trị quanh ranh giới chính sách, và `Long.MAX_VALUE` để bắt các lỗi tính toán thường bị bỏ sót.
- Các assertion `first >= 0 && first <= subtotal` xác minh **bất biến chung** cho mọi chính sách.
- Hai lần gọi cùng đầu vào chỉ được dùng để kiểm tra **tính xác định vì hợp đồng ví dụ đã quy định như vậy**. Không tự áp dụng phép thử này cho mọi `Supplier`, `Consumer` hoặc chính sách được phép thay đổi trạng thái.
- Ca `-1` khẳng định **ngoại lệ được quy định**. Không cần so khớp nguyên văn message của ngoại lệ vì hợp đồng chỉ yêu cầu kiểu `IllegalArgumentException`.
- `Long.MAX_VALUE` cho thấy tại sao nên chọn phép tính an toàn: `subtotal / 10L` không bị tràn số như phép tính `subtotal * 10 / 100` trên giá trị lớn.
- `checkContract` chỉ kiểm tra những điều **mọi implementation phải đáp ứng**. Các kiểm tra `199 -> 19`, `15 -> 15`, `100 -> 30` xác minh **quy tắc riêng**. Cả hai nhóm test đều cần thiết.

Trong ứng dụng thực tế, các ràng buộc tiền tệ có thể phức tạp hơn, ví dụ thuế, làm tròn, nhiều loại tiền và số thập phân. Chọn kiểu dữ liệu và quy tắc số học theo yêu cầu miền nghiệp vụ; ở ví dụ này sử dụng **cent nguyên `long`** để giữ phép tính minh bạch và không dùng `double` cho tiền.

## 5. Một implementation sai vẫn qua compiler nhưng trượt test

Ví dụ mã sau là **đoạn minh họa** đặt trong phạm vi có định nghĩa `DiscountPolicy` và `checkContract` từ chương trình trên:

~~~java
DiscountPolicy broken = subtotal -> {
    requireNonNegative(subtotal);
    return subtotal + 1L;
};

// Lời gọi dưới đây sẽ ném AssertionError:
// checkContract("broken", broken);
~~~

Với `subtotal = 0`, kết quả `1` vi phạm điều kiện `discount <= subtotal`. Vì vậy test thất bại ngay cả khi lambda hoàn toàn hợp lệ về chữ ký.

Một lỗi khác:

~~~java
DiscountPolicy forgetsValidation = subtotal -> 0L;

// Biên dịch thành công, nhưng checkContract sẽ phát hiện
// đầu vào âm không bị từ chối bằng IllegalArgumentException.
~~~

Đây chính là **mức bảo vệ mà `@FunctionalInterface` không cung cấp**. Annotation bảo vệ **cấu trúc SAM**, còn test bảo vệ **ngữ nghĩa đã cam kết**.

Đừng viết test chỉ để xác nhận “lambda trả về một số” hoặc “gọi không ném lỗi” nếu hợp đồng đòi hỏi nhiều hơn. Hãy chủ động đưa một implementation sai có kiểm soát vào bài tập để chứng minh test thực sự phát hiện vi phạm.

## 6. Chọn ca kiểm thử theo bản chất hợp đồng

Với một functional interface, đặt câu hỏi theo các nhóm sau:

| Nhóm | Câu hỏi | Ví dụ cho `DiscountPolicy` |
| --- | --- | --- |
| Dữ liệu điển hình | Kết quả với đầu vào bình thường? | `199` cho chính sách 10% phải trả `19` cent giảm |
| Ranh giới | Đầu vào nhỏ nhất/lớn nhất? | `0` và `Long.MAX_VALUE` |
| Tiền điều kiện | Đầu vào nào bị cấm? | `-1` phải ném `IllegalArgumentException` |
| Hậu điều kiện | Kết quả bắt buộc nằm trong giới hạn nào? | `0 <= result <= subtotal` |
| Bất biến | Điều gì luôn phải đúng? | Không giảm nhiều hơn tổng tiền |
| Tính xác định | Cùng đầu vào có luôn cùng kết quả? | Có, **vì** hợp đồng policy này yêu cầu |
| Tác dụng phụ | Có thay đổi trạng thái ngoài không? | Hợp đồng nói không; cần kiểm tra qua quan sát phù hợp |
| Tính kết hợp | Nếu được dùng qua API bậc cao, có giữ nghĩa không? | Chính sách dùng trong tính tổng vẫn bảo đảm giới hạn giảm |

Bộ ca test không cần chứa mọi số `long` để có ích. Bắt đầu với các **lớp tương đương** và **giá trị biên**, sau đó bổ sung test theo lỗi thực tế, trường hợp nghiệp vụ quan trọng và rủi ro overflow.

Một property-based testing framework có thể tạo nhiều đầu vào và kiểm tra bất biến trên quy mô lớn; tuy nhiên việc sinh dữ liệu không tự thay thế **oracle nghiệp vụ**. Với thuật toán ngẫu nhiên, lưu seed để lỗi có thể tái hiện và bổ sung ví dụ cụ thể cho những ngưỡng đặc biệt.

## 7. Phân biệt hợp đồng chung với quy tắc của từng triển khai

Giả sử có ba chính sách giảm giá:

- `none`: luôn không giảm.
- `tenPercent`: giảm 10%, lấy phần nguyên của số cent.
- `fixed30`: giảm tối đa 30 cent và không vượt tổng tiền.

Tất cả cùng phải tuân thủ các **hậu điều kiện chung**. Tuy nhiên test “`discountCents(100) == 10`” **không được đặt trong bộ contract test chung**, vì nó chỉ đúng với `tenPercent`, không đúng với `none` hoặc `fixed30`.

Cách thiết kế tốt:

1. **Contract suite** kiểm tra ràng buộc mọi implementation đều phải tuân thủ.
2. **Implementation-specific suite** kiểm tra quy tắc riêng của từng implementation.
3. **Integration tests** kiểm tra khi chính sách được gắn vào luồng thực tế, có được gọi đúng chỗ, đúng số lần và kết quả có ảnh hưởng đúng nơi cần hay không.

Nếu hợp đồng chung **không** cam kết deterministic, không đưa kiểm tra deterministic vào suite dùng chung chỉ vì implementation đầu tiên vô tình làm được. Nếu hợp đồng **cho phép** đầu vào `null`, không áp đặt rằng mọi lambda phải ném `NullPointerException`. Chính đặc tả API quyết định oracle.

## 8. Kiểm thử các functional interface chuẩn: Function, Predicate, Consumer, Comparator

Java `java.util.function` cung cấp các functional interface được sử dụng từ Java 8 tới hiện nay: `Function<T,R>`, `Predicate<T>`, `Consumer<T>`, `Supplier<T>`, `UnaryOperator<T>`, `BiFunction<T,U,R>`, v.v.

**Chúng chỉ định chữ ký và một số quy tắc kết hợp**, không mặc nhiên biến mọi lambda thành hàm thuần (pure function). Phần lớn quy tắc nghiệp vụ phải do ứng dụng xác định.

### Function: kiểm tra ánh xạ đầu vào → đầu ra

~~~java
java.util.function.Function<String, Integer> length =
        text -> text.length();

if (length.apply("Java") != 4) {
    throw new AssertionError("length must be four");
}
~~~

Nếu hợp đồng ứng dụng **cho phép `null`**, cần viết và kiểm thử hành vi rõ ràng với `null`; ví dụ trên không có khả năng đó. Cũng nên kiểm tra Unicode nếu ý nghĩa “độ dài” của miền nghiệp vụ là **số ký tự người đọc nhìn thấy**, vì `String.length()` trả về số **UTF-16 code units**, không luôn bằng số Unicode code points hay số grapheme clusters.

### Predicate: kiểm tra đúng/sai tại các ranh giới

~~~java
java.util.function.Predicate<String> hasText =
        value -> value != null && !value.isBlank();

if (hasText.test(null)) {
    throw new AssertionError("null must be rejected");
}
if (hasText.test("   ")) {
    throw new AssertionError("blank must be rejected");
}
if (!hasText.test("Java")) {
    throw new AssertionError("Java must be accepted");
}
~~~

`String.isBlank()` có từ **Java 11**; ví dụ thích hợp với JDK 17+. Đây là **hợp đồng do người viết predicate định nghĩa**, không phải hành vi bắt buộc của mọi `Predicate<String>`.

### Consumer: quan sát tác dụng phụ thay vì chỉ gọi phương thức

Với `Consumer<T>`, SAM `accept(T)` trả về `void`. Để test hành vi, cần quan sát **tác dụng bên ngoài đã cam kết** qua fake/in-memory collaborator:

~~~java
java.util.List<String> events = new java.util.ArrayList<>();
java.util.function.Consumer<String> sink = events::add;

sink.accept("created");

if (!events.equals(java.util.Collections.singletonList("created"))) {
    throw new AssertionError("one event must be recorded");
}
~~~

Đây là **đoạn minh họa**, đặt trong một phương thức. Kết quả thực tế cần kiểm tra là danh sách `events`, không phải giá trị trả về của `accept`. Trong ứng dụng, fake sender, in-memory repository hoặc test double có thể thay nơi ghi log/mạng; tránh kiểm thử phụ thuộc dịch vụ thật nếu hợp đồng không cần.

### Comparator: kiểm tra các quy tắc nhất quán, không chỉ một phép so sánh

`Comparator<T>` có hợp đồng quan hệ thứ tự. Khi tự viết comparator, cần kiểm tra:

- `compare(x, x) == 0`.
- Dấu của `compare(x, y)` đối nghịch dấu của `compare(y, x)`.
- Tính bắc cầu (`transitivity`) cho những bộ ba có quan hệ.
- Khi `compare(x, y) == 0`, dấu so sánh của `x` và `y` với một `z` phải nhất quán theo hợp đồng Comparator.
- Cách xử lý `null` và việc comparator có nhất quán với `equals` hay không phải được công bố nếu liên quan.

Một lỗi thường gặp là `(a, b) -> a - b` trên `Integer`: phép trừ có thể **overflow**, làm sai thứ tự. Cách an toàn hơn:

~~~java
java.util.Comparator<Integer> ascending =
        (left, right) -> Integer.compare(left, right);
~~~

Các luật của `Comparator` là **hợp đồng chuẩn được Javadoc định nghĩa**, còn điều kiện “giá trị null phải được đặt trước” chẳng hạn là **lựa chọn của ứng dụng**. Khi cần hỗ trợ `null`, xem `Comparator.nullsFirst(...)` hoặc `nullsLast(...)` theo yêu cầu.

## 9. Kiểm thử tính tương đương giữa lambda, method reference và class

Một functional interface có thể được triển khai theo nhiều cú pháp:

~~~java
java.util.function.Function<String, String> lambda =
        s -> s.trim();

java.util.function.Function<String, String> methodReference =
        String::trim;

java.util.function.Function<String, String> anonymousClass =
        new java.util.function.Function<String, String>() {
            @Override
            public String apply(String s) {
                return s.trim();
            }
        };
~~~

Nếu hợp đồng quy định “bỏ khoảng trắng ở hai đầu theo `String.trim()`”, có thể chạy cùng bộ dữ liệu qua cả ba implementation. Test **hành vi** sẽ cho kết luận tương đương đối với các trường hợp được kiểm thử.

**Không** khẳng định tất cả lambda, method reference và anonymous class luôn hoàn toàn giống nhau trong mọi chi tiết: khác biệt có thể xuất hiện ở `this`, phạm vi biến, danh tính đối tượng, biểu diễn lớp triển khai và ngữ cảnh bắt ngoại lệ. Test đúng mức trừu tượng là kiểm tra **những bảo đảm công khai mà người gọi cần**.

Ở đây `trim()` vẫn tồn tại trong Java hiện đại, nhưng nếu nghiệp vụ xử lý **Unicode whitespace** thì cần xác định rõ yêu cầu và cân nhắc `strip()` (Java 11+) thay vì giữ `trim()` theo thói quen. Không biến một phương thức cũ thành “đúng cho mọi trường hợp” chỉ vì test ASCII vượt qua.

## 10. Dùng JUnit cho contract suite trong dự án thật

Ví dụ độc lập ở mục 4 dùng `AssertionError` để chạy mà không cần dependency. Trong dự án thực tế, thường tổ chức test bằng **JUnit Jupiter** và để build tool quản lý phiên bản phù hợp với dự án.

Ví dụ khung kiểm thử cho một `DiscountPolicy` đã có sẵn; **đoạn này phụ thuộc JUnit Jupiter trong classpath và khai báo `DiscountPolicy`, không phải tệp Java độc lập**:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

class DiscountPolicyContractTest {
    // factory được test phải trả về một policy thỏa hợp đồng.
    private final DiscountPolicy policy = subtotal -> {
        if (subtotal < 0) {
            throw new IllegalArgumentException();
        }
        return subtotal / 10;
    };

    @Test
    void discountStaysWithinSubtotal() {
        for (long subtotal : new long[]{0, 1, 99, 100}) {
            long discount = policy.discountCents(subtotal);
            assertTrue(discount >= 0 && discount <= subtotal);
        }
    }

    @Test
    void negativeSubtotalIsRejected() {
        assertThrows(IllegalArgumentException.class,
                () -> policy.discountCents(-1));
    }

    @Test
    void tenPercentRoundsDownToWholeCent() {
        assertEquals(19L, policy.discountCents(199L));
    }
}
~~~

Ý tưởng tương ứng khi có nhiều chính sách:

- Tách các assertion chung thành helper/test contract nhận một `DiscountPolicy`.
- Mỗi implementation cung cấp một **factory** (khởi tạo lambda, method reference hoặc class).
- Chạy cùng các trường hợp ranh giới và bất biến; thêm test riêng cho công thức tính của từng chính sách.
- Đối với JUnit parameterized tests, có thể truyền các trường hợp và implementation qua `@MethodSource` hoặc cấu trúc test factory phù hợp. Chỉ thêm abstraction khi thật sự giảm lặp và giúp đọc test dễ hơn.

Hãy tránh test tương đương với việc **sao chép code triển khai** vào phần expected. Ví dụ, nếu implementation tính `amount / 10`, một test cũng gọi lại đúng cùng công thức trên một vài dữ liệu có thể lặp lại cùng sai lầm. Nên có **ví dụ nghiệp vụ được chốt độc lập** như `199 cent → 19 cent`, cùng các bất biến dùng được cho nhiều trường hợp.

## 11. Những tình huống đặc biệt cần suy xét

### Ngoại lệ và checked exceptions

Một functional interface có SAM không khai báo checked exception, chẳng hạn `Function.apply`, không cho phép lambda ném trực tiếp checked exception chưa xử lý. Nếu nghiệp vụ cần truyền thao tác IO có `IOException`, phải thiết kế interface phù hợp với `throws` hoặc xử lý ngoại lệ rõ ràng. **Hợp đồng exception** cần test ở lớp abstraction mà bạn thực sự cung cấp, không giả định mọi callback đều được phép ném cùng một kiểu lỗi.

### Mutable state và tính xác định

Ví dụ:

~~~java
java.util.concurrent.atomic.AtomicInteger counter =
        new java.util.concurrent.atomic.AtomicInteger();

java.util.function.Supplier<Integer> next =
        counter::incrementAndGet;
~~~

`next.get()` sẽ thay đổi qua mỗi lần gọi. Điều này **không sai** đối với `Supplier<Integer>` nói chung. Chỉ có thể kiểm tra “same input, same output” nếu hợp đồng cụ thể cam kết tính xác định; với `next`, hợp đồng phù hợp hơn là giá trị tăng dần theo từng lần gọi trong bối cảnh sử dụng được kiểm soát.

### Thời gian, ngẫu nhiên và mạng

Nếu lambda dùng `Instant.now()`, `Random` hoặc dịch vụ bên ngoài, test nên kiểm soát nguồn thời gian/ngẫu nhiên bằng **Clock**, seed hoặc dependency injection khi cần kiểm tra kết quả lặp lại. Đừng mặc định mọi lambda phải pure. Với async callback, hợp đồng cần nêu khi nào hoàn tất, thứ tự callback, cách báo lỗi và ràng buộc thread; bộ test đồng bộ đơn giản không đủ để chứng minh những tính chất đó.

### Null và generic

`Function<T,R>` hay `Predicate<T>` không tự quyết định một nghiệp vụ có chấp nhận `null` hay không. Chính implementation hoặc API bao ngoài định nghĩa tiền điều kiện và kết quả mong đợi. Với generic, test cùng kiểu dữ liệu được công bố, các trường hợp ranh giới cần thiết và cả sự khác biệt giữa `null`, chuỗi rỗng, danh sách rỗng nếu miền nghiệp vụ yêu cầu.

### Tính độc lập của test

Kiểm thử hợp đồng tốt không dựa vào thứ tự chạy các test, thời gian thực, mạng hay trạng thái toàn cục ngoài ý muốn. Với policy stateful được cho phép, mỗi test nên có **fixture** mới hoặc quy tắc reset được xác định để không làm lẫn kết quả.

## 12. Những sai lầm phổ biến

1. **Chỉ kiểm tra “lambda biên dịch được”** rồi coi là đúng nghiệp vụ. Compiler bảo đảm SAM, không bảo đảm kết quả.
2. **Lấy tất cả tính chất của implementation đầu tiên làm hợp đồng chung**, ví dụ ép mọi `Supplier` phải deterministic. Chỉ kiểm tra điều được công bố cho tất cả.
3. **Chỉ thử happy path** và bỏ ranh giới `0`, số lớn, `null`, đầu vào âm, dữ liệu rỗng hoặc tình huống overflow.
4. **Viết expected bằng chính công thức implementation** khiến sai lầm ở cả code và test giống nhau; bổ sung oracle độc lập và bất biến.
5. **Kiểm tra chi tiết lambda không công khai**, như tên class do JVM sinh, thứ tự biến nội bộ hay số bytecode. Đó thường không thuộc hợp đồng người gọi.
6. **Không phân biệt test chung và test riêng** dẫn đến thất bại giả khi policy đúng nhưng có thuật toán khác.
7. **Cho rằng `@FunctionalInterface` thay thế runtime test**. Annotation kiểm tra cấu trúc tại compile time.
8. **So khớp thông điệp exception khi hợp đồng chỉ yêu cầu kiểu exception**, gây test dễ vỡ do thay đổi lời giải thích.
9. **Phớt lờ tác dụng phụ được công bố**, ví dụ `Consumer` cần ghi một sự kiện nhưng test chỉ gọi `accept` không quan sát gì.
10. **Không phân biệt mức Java của API ví dụ**, như `String.isBlank()` có từ Java 11; khi dự án yêu cầu `--release 8` phải chọn API tương thích và test lại.

## 13. Bài tập luyện tập

**Bài 1 — Nhận diện hợp đồng.** Với `Predicate<Integer> positive = n -> n > 0;`, hãy viết chính xác điều kiện cho các đầu vào `-1`, `0`, `1`. Nếu hợp đồng nói `null` phải trả `false`, sửa implementation và thêm test tương ứng.

**Bài 2 — Phát hiện lỗi.** Đưa `DiscountPolicy broken = subtotal -> subtotal + 1;` vào `checkContract`. Dự đoán ca test đầu tiên thất bại và giải thích vì sao compiler vẫn chấp nhận lambda.

**Bài 3 — Phân loại test.** Điều kiện `0 <= discount <= subtotal` thuộc **test chung** hay **test riêng**? Điều kiện `discount(199) == 19` cho policy 10% thuộc loại nào?

**Bài 4 — Refactor cú pháp.** Thay `DiscountContractDemo::noDiscount` bằng lambda gọi cùng phương thức. Bộ contract test có cần sửa các assertion không? Tại sao?

**Bài 5 — Statefulness.** Tạo `Supplier<Integer>` trả về giá trị tăng dần từ một `AtomicInteger`. Nếu bộ contract test mặc định “hai lời gọi phải bằng nhau”, lỗi nằm ở implementation hay ở **hợp đồng test**?

**Bài 6 — Overflow.** Với policy 10% viết `subtotal * 10 / 100`, thử trên `Long.MAX_VALUE`. So sánh với `subtotal / 10` và xác định cách ghi test bất biến để phát hiện lỗi.

**Bài 7 — Consumer.** Thiết kế `Consumer<String>` ghi vào `List<String>` trong bộ nhớ. Test chính xác một phần tử mới được thêm sau một lần gọi, và thảo luận điều gì phải thay đổi nếu hợp đồng cho phép ghi bất đồng bộ.

## Tóm tắt kiến thức trọng tâm

- **Functional interface xác định hình dạng đầu vào/đầu ra của hành vi**; `@FunctionalInterface` chỉ kiểm tra cấu trúc SAM khi biên dịch.
- **Hợp đồng hành vi phải được viết rõ và được kiểm chứng qua kết quả quan sát được**. Không thể suy ra mọi bất biến chỉ từ chữ ký SAM.
- **Contract suite dùng chung** giúp kiểm tra nhiều lambda, method reference hoặc class implementation theo cùng một tập nghĩa vụ.
- **Test riêng từng implementation** xác minh phép tính hoặc quy tắc đặc thù mà contract chung không quy định.
- **Cần đầu vào điển hình, dữ liệu biên, trường hợp không hợp lệ, ngoại lệ và tác dụng phụ**, theo mức độ rủi ro thật của API.
- **Không test chi tiết triển khai không nằm trong hợp đồng**; khi refactor cú pháp hoặc tổ chức mã, test hành vi vẫn có giá trị.
- **Luôn xác định baseline Java**. Lambda và `java.util.function` có từ Java 8 và vẫn dùng hiện nay; `String.isBlank()` từ Java 11, nên ví dụ chứa nó cần JDK phù hợp.

## Tài liệu chính thức

- Java SE 17, `java.lang.FunctionalInterface`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/FunctionalInterface.html
- Java SE 17, `java.util.function`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/function/package-summary.html
- Java SE 17, `Function`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/function/Function.html
- Java SE 17, `Predicate`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/function/Predicate.html
- Java SE 17, `Consumer`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/function/Consumer.html
- Java SE 17, `Comparator`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Comparator.html
- Java Language Specification, `9.8 Functional Interfaces`: https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.8
- Java Language Specification, `15.27 Lambda Expressions`: https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.27

Các nguyên tắc kiểm thử dựa trên **hợp đồng công khai** vẫn phù hợp với Java hiện đại; khi dùng API mới, đọc Javadoc đúng phiên bản JDK của dự án và diễn đạt những cam kết nghiệp vụ thành test có thể tái hiện.