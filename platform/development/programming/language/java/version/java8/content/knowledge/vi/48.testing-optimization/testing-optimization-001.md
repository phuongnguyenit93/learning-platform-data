# Kiểm thử lambda qua functional interface trong Java

Lambda expression cung cấp phần triển khai cho một **functional interface**. Khi kiểm thử lambda, ta cần xác định hợp đồng mà interface công bố: đầu vào nào được chấp nhận, kết quả nào phải trả về, side effect nào được phép xảy ra và exception nào được truyền ra. Sau đó kiểm tra hành vi bằng các input có chủ đích.

Một lambda không phải là API riêng biệt có thể kiểm tra bằng cách nhìn tên class ẩn do compiler sinh. **Kiểu đích của lambda là functional interface**; vì vậy test nên làm việc với interface và hành vi của nó. Cách này áp dụng cho interface tự định nghĩa và các kiểu chuẩn trong `java.util.function` như `Predicate`, `Function`, `Consumer`, `Supplier` và `UnaryOperator`.

Bài này dùng cú pháp lambda từ Java 8, một chương trình độc lập chạy được trên Java 8+, và ví dụ kiểm thử hiện đại bằng JUnit Jupiter 6.1.3 dành cho runtime Java 17+. Phần cốt lõi không phụ thuộc framework kiểm thử. Các ví dụ tập trung vào giá trị trả về, điều kiện biên, side effect, exception, composition, closure và việc truyền lambda vào service.

## 1. Functional interface là hợp đồng kiểm thử

Một functional interface là interface có đúng **một abstract method** làm functional method. Interface vẫn có thể có default method, static method hoặc các method tương ứng với public method của `Object` mà không mất tính functional. Annotation `@FunctionalInterface` thể hiện ý định thiết kế và giúp compiler báo lỗi nếu interface vô tình có thêm abstract method.

~~~java
@FunctionalInterface
interface DiscountPolicy {
    BigDecimal discountFor(Order order);
}
~~~

Lambda:

~~~java
DiscountPolicy tenPercent =
        order -> order.getSubtotal().multiply(new BigDecimal("0.10"));
~~~

Biến `tenPercent` có kiểu `DiscountPolicy`. Functional method là `discountFor`; khi gọi `tenPercent.discountFor(order)`, lambda nhận order và trả về mức giảm giá.

### 1.1. Lambda được kiểm tra thông qua kiểu đích

Compiler cần biết kiểu functional interface để suy luận kiểu tham số và kết quả:

~~~java
Predicate<String> nonEmpty = text -> !text.isEmpty();
Function<String, Integer> length = text -> text.length();
Consumer<String> printer = text -> System.out.println(text);
Supplier<String> greeting = () -> "Hello";
~~~

Bốn lambda có bốn functional interface khác nhau. Test nên khai báo biến với kiểu đích rõ ràng rồi gọi functional method, hoặc truyền lambda vào method nhận đúng interface đó.

Không thể khai báo lambda độc lập mà không có target type trong mọi ngữ cảnh. Khi gặp compile error hoặc overload ambiguity, hãy kiểm tra kiểu tham số của method nhận lambda trước khi sửa phần thân lambda.

### 1.2. Các functional interface thường gặp

| Interface | Functional method | Hình dạng | Dùng để kiểm thử |
|---|---|---|---|
| `Predicate<T>` | `test(T)` | T → boolean | Điều kiện, validation, filter |
| `Function<T,R>` | `apply(T)` | T → R | Chuyển đổi, tính toán |
| `Consumer<T>` | `accept(T)` | T → void | Side effect, ghi nhận event |
| `Supplier<T>` | `get()` | () → T | Giá trị được tạo khi gọi |
| `UnaryOperator<T>` | `apply(T)` | T → T | Biến đổi cùng kiểu |
| `BiFunction<T,U,R>` | `apply(T,U)` | (T,U) → R | Tính toán từ hai đầu vào |
| `BiPredicate<T,U>` | `test(T,U)` | (T,U) → boolean | Điều kiện có hai đầu vào |
| `BinaryOperator<T>` | `apply(T,T)` | (T,T) → T | Kết hợp hai giá trị cùng kiểu |

Các biến thể primitive như `IntPredicate`, `IntUnaryOperator`, `ToIntFunction<T>` và `LongSupplier` giúp tránh boxing/unboxing trong những đường xử lý phù hợp. Chọn interface theo đúng shape nghiệp vụ; không dùng `Function<T,Boolean>` khi `Predicate<T>` diễn đạt hợp đồng rõ hơn.

### 1.3. Vì sao nên dùng @FunctionalInterface?

~~~java
@FunctionalInterface
interface TaxCalculator {
    BigDecimal calculate(BigDecimal amount);

    default BigDecimal calculateWithMinimum(
            BigDecimal amount, BigDecimal minimum) {
        BigDecimal result = calculate(amount);
        return result.max(minimum);
    }
}
~~~

Interface vẫn hợp lệ vì chỉ có một abstract method; default method không tạo thêm functional method. Annotation giúp compiler kiểm tra ý định. Nó **không phải annotation của test framework**, và không tự chạy test hay xác minh logic lambda.

## 2. Test hợp đồng trước, không test chi tiết triển khai của lambda

Có ba phạm vi kiểm thử thường gặp:

1. **Kiểm thử trực tiếp lambda:** tạo lambda với functional interface, truyền input và kiểm kết quả/side effect.
2. **Kiểm thử component sử dụng lambda:** truyền lambda vào constructor hoặc method, rồi kiểm hành vi của component.
3. **Kiểm thử tích hợp:** kết nối component với implementation thật, ví dụ repository, filesystem, HTTP client hoặc callback từ framework.

Mỗi phạm vi trả lời một câu hỏi khác nhau. Test trực tiếp lambda xác minh logic của rule; test component xác minh component gọi rule đúng lúc và xử lý kết quả đúng; integration test xác minh adapter thật hoạt động với dependency bên ngoài.

### 2.1. Kiểm thử trực tiếp một Predicate

~~~java
Predicate<Integer> isPositive = value -> value > 0;

assertTrue(isPositive.test(5));
assertFalse(isPositive.test(0));
assertFalse(isPositive.test(-3));
~~~

Test bao phủ ba vùng: dương, bằng 0 và âm. Nếu nghiệp vụ yêu cầu lớn hơn hoặc bằng 0, test tại ranh giới sẽ phát hiện lỗi dùng `>` thay cho `>=`.

### 2.2. Kiểm thử Function

~~~java
Function<String, Integer> countCharacters =
        text -> text.length();

assertEquals(Integer.valueOf(5), countCharacters.apply("hello"));
assertEquals(Integer.valueOf(0), countCharacters.apply(""));
~~~

Đối với hàm chuyển đổi, kiểm cả dữ liệu bình thường, rỗng, biên và null nếu contract có quy định null. Không tự giả định lambda phải nhận null; xác định trước interface được phép nhận gì.

### 2.3. Kiểm thử Consumer bằng cách quan sát side effect

~~~java
List<String> sent = new ArrayList<String>();
Consumer<String> sender = message -> sent.add(message);

sender.accept("order-created");

assertEquals(Collections.singletonList("order-created"), sent);
~~~

`Consumer` trả về void, nên kết quả quan sát là side effect. Test cần kiểm nội dung được ghi, số lần được gọi và thứ tự nếu thứ tự là một phần của contract. Không chỉ assert rằng test không ném exception.

### 2.4. Kiểm thử Supplier và thời điểm thực thi

~~~java
AtomicInteger calls = new AtomicInteger();
Supplier<String> value = () -> {
    calls.incrementAndGet();
    return "ready";
};

assertEquals(0, calls.get());
assertEquals("ready", value.get());
assertEquals(1, calls.get());
~~~

Supplier chỉ tạo kết quả khi `get()` được gọi. Test kiểm được tính lazy và số lần gọi. Không giả định mỗi lần `get()` phải trả một object mới; contract của `Supplier` không yêu cầu kết quả mới hoặc khác nhau ở mỗi lần gọi.

## 3. Thiết kế component để có thể truyền lambda vào

Một component dễ kiểm thử có thể nhận functional interface qua constructor hoặc method. Ví dụ checkout cần ba quy tắc độc lập:

- `Predicate<Order>` quyết định order có đủ điều kiện không.
- `DiscountPolicy` tính mức giảm giá.
- `Consumer<Order>` ghi nhận order sau khi xử lý hợp lệ.

~~~java
@FunctionalInterface
interface DiscountPolicy {
    BigDecimal discountFor(Order order);
}

final class Checkout {
    private final Predicate<Order> eligible;
    private final DiscountPolicy discountPolicy;
    private final Consumer<Order> audit;

    Checkout(Predicate<Order> eligible,
             DiscountPolicy discountPolicy,
             Consumer<Order> audit) {
        this.eligible = eligible;
        this.discountPolicy = discountPolicy;
        this.audit = audit;
    }

    BigDecimal total(Order order) {
        if (!eligible.test(order)) {
            throw new IllegalArgumentException("order is not eligible");
        }
        BigDecimal discount = discountPolicy.discountFor(order);
        if (discount.signum() < 0
                || discount.compareTo(order.getSubtotal()) > 0) {
            throw new IllegalStateException("invalid discount");
        }
        BigDecimal total = order.getSubtotal().subtract(discount);
        audit.accept(order);
        return total;
    }
}
~~~

Đây là **mảnh code minh họa**; class `Order` và imports được cung cấp trong chương trình hoàn chỉnh ở phần 10. Constructor injection cho phép mỗi test cung cấp rule nhỏ và xác định. Không cần khởi tạo database, network client hoặc framework nếu test chỉ muốn xác minh logic checkout.

### 3.1. Test component bằng lambda giả lập

~~~java
List<String> audit = new ArrayList<String>();

Checkout checkout = new Checkout(
        order -> order.isActive(),
        order -> new BigDecimal("5.00"),
        order -> audit.add(order.getId()));
~~~

Đây là test double đơn giản: các lambda mô tả chính xác hành vi test cần. Với interface chỉ có một method, lambda thường dễ đọc hơn một class mock dài.

### 3.2. Không nhầm test lambda với test component

Giả sử predicate sai do điều kiện eligibility. Test predicate riêng xác minh rule. Nếu predicate đúng nhưng checkout vẫn gọi audit khi order không hợp lệ, đó là lỗi của component; test checkout phải bắt được lỗi ấy.

| Test | Đầu vào được kiểm soát | Điều cần xác minh |
|---|---|---|
| Rule trực tiếp | Order | Predicate/discount trả đúng |
| Checkout | Order + injected rules | Gọi đúng rule và đúng thứ tự |
| Audit adapter | Event/order | Lưu/gửi event đúng |
| Integration | DB/network thật | Adapter và hệ thống ngoài tương tác đúng |

## 4. Các nhóm trường hợp nên kiểm thử

### 4.1. Giá trị bình thường và điều kiện biên

Với một lambda tính phí, test ít nhất giá trị thường, 0, giá trị lớn nhất được hỗ trợ, số âm và điểm ngay trước/sau ngưỡng. Dùng dữ liệu cụ thể giúp test diễn đạt quy tắc nghiệp vụ.

~~~java
Predicate<BigDecimal> freeShipping =
        amount -> amount.compareTo(new BigDecimal("500000")) >= 0;

assertFalse(freeShipping.test(new BigDecimal("499999")));
assertTrue(freeShipping.test(new BigDecimal("500000")));
assertTrue(freeShipping.test(new BigDecimal("500001")));
~~~

Với số tiền, dùng `BigDecimal` và quy định scale/rounding phù hợp. Không dùng `double` cho so sánh tiền nếu contract yêu cầu độ chính xác thập phân.

### 4.2. Side effect và số lần gọi

Khi lambda là Consumer hoặc callback, kiểm tra:

- Có được gọi hay không.
- Được gọi đúng số lần.
- Nhận đúng argument.
- Thứ tự có đúng nếu là yêu cầu.
- Không được gọi khi validation thất bại.

~~~java
List<String> events = new ArrayList<String>();
Consumer<String> record = events::add;

record.accept("created");
record.accept("paid");

assertEquals(Arrays.asList("created", "paid"), events);
~~~

Method reference `events::add` có cùng target type `Consumer<String>` như lambda tương đương. Có thể test cả lambda lẫn method reference bằng cùng contract.

### 4.3. Exception và điều kiện lỗi

Một lambda có thể ném unchecked exception; caller thường nhận exception đó trực tiếp nếu không có lớp bắt/chuyển đổi. Test phải xác định exception type và message quan trọng, đồng thời kiểm side effect không xảy ra sau lỗi.

~~~java
Predicate<String> validCode = code -> {
    if (code == null) {
        throw new IllegalArgumentException("code is required");
    }
    return !code.isEmpty();
};

IllegalArgumentException error = assertThrows(
        IllegalArgumentException.class,
        () -> validCode.test(null));
assertEquals("code is required", error.getMessage());
~~~

Đây là cú pháp JUnit Jupiter. Lambda truyền cho `assertThrows` chính là một functional interface của JUnit để thực thi đoạn code có thể ném exception.

### 4.4. Null và contract đầu vào

Functional interface trong `java.util.function` không tự áp đặt null policy. Ví dụ `Predicate<String>` có thể trả false, ném NullPointerException hoặc xử lý null tùy lambda. Test phải theo contract ứng dụng, không mặc định mọi functional method đều chấp nhận null.

Nếu null không hợp lệ, xác minh lỗi được báo tại đúng boundary. Nếu null là một giá trị nghiệp vụ hợp lệ, test hành vi rõ ràng của nó. Tránh test ngầm định dựa trên implementation detail của compiler.

### 4.5. Composition

Nhiều functional interface có default method để kết hợp hành vi:

~~~java
Predicate<Order> active = Order::isActive;
Predicate<Order> highValue =
        order -> order.getSubtotal().compareTo(limit) >= 0;

Predicate<Order> eligible = active.and(highValue);

assertTrue(eligible.test(activeHighValueOrder));
assertFalse(eligible.test(inactiveHighValueOrder));
~~~

Có thể kiểm từng predicate riêng, sau đó kiểm composition. `Predicate.and` và `or` có short-circuit; `Function.andThen`/`compose` nối phép biến đổi; `Consumer.andThen` thực hiện hai side effect theo thứ tự. Test thứ tự khi nó là một phần của contract.

### 4.6. Closure và biến được capture

Lambda có thể capture biến local final hoặc effectively final:

~~~java
BigDecimal minimum = new BigDecimal("100.00");
Predicate<Order> eligible =
        order -> order.getSubtotal().compareTo(minimum) >= 0;
~~~

Test nên kiểm hành vi với giá trị captured cụ thể. Nếu lambda capture mutable state như List hoặc AtomicInteger, test phải khởi tạo state riêng cho từng test để tránh kết quả phụ thuộc thứ tự chạy. Không chia sẻ mutable capture giữa test song song nếu không có cơ chế đồng bộ thích hợp.

## 5. Kiểm thử lambda trong Stream và callback

### 5.1. Stream là lazy: phải có terminal operation

~~~java
List<String> names = Arrays.asList("An", "Binh", "Chi");
Predicate<String> startsWithB = name -> name.startsWith("B");

List<String> result = names.stream()
        .filter(startsWithB)
        .collect(Collectors.toList());

assertEquals(Collections.singletonList("Binh"), result);
~~~

Gọi `filter` chỉ xây dựng pipeline; lambda thường được thực thi khi terminal operation như `collect`, `count` hoặc `forEach` chạy. Nếu test chỉ tạo stream rồi kết thúc, predicate có thể chưa được gọi. Assert kết quả cuối hoặc side effect quan sát được theo contract.

### 5.2. Không phụ thuộc thứ tự của parallel stream

Với parallel stream, không giả định thứ tự thực thi lambda hoặc thứ tự side effect nếu API không bảo đảm. Không ghi vào ArrayList thường từ nhiều thread; dùng collector phù hợp hoặc cấu trúc thread-safe khi cần. Đối với business logic, ưu tiên lambda thuần và stateless để test dễ tái lập.

### 5.3. Callback bất đồng bộ

Nếu functional interface được gọi trong executor hoặc callback, tránh dùng `Thread.sleep` để chờ test. Dùng `CompletableFuture`, `CountDownLatch` hoặc API đồng bộ hóa phù hợp, kèm timeout hữu hạn. Test cần xác minh callback hoàn tất, kết quả/exception được truyền đúng và không có race condition.

## 6. Checked exception và functional interface tự định nghĩa

Các interface chuẩn như `Function`, `Predicate` và `Consumer` không khai báo checked exception trong functional method. Nếu lambda cần gọi API ném checked exception, có thể xử lý tại chỗ hoặc định nghĩa interface riêng.

~~~java
@FunctionalInterface
interface IOFunction<T, R> {
    R apply(T value) throws IOException;
}

IOFunction<Path, String> readText =
        path -> Files.readString(path);
~~~

Đây là **mảnh minh họa JDK 11+** vì `Files.readString` có từ Java 11; nếu target Java 8, dùng API file phù hợp phiên bản đó. Test cần kiểm cả đường thành công và IOException khi file không tồn tại/không thể đọc. Đừng bọc mọi checked exception thành RuntimeException nếu contract yêu cầu caller xử lý lỗi I/O.

Nếu adapter chuyển checked exception sang unchecked, test riêng việc chuyển đổi: loại exception mới, cause gốc và thông tin ngữ cảnh cần thiết.

## 7. Kiểm thử hiện đại với JUnit Jupiter

JUnit 6.1.3 là bản hiện hành trong tài liệu được dùng cho bài. JUnit 6 yêu cầu Java 17 trở lên ở runtime; nó vẫn có thể chạy test cho code đã compile bằng JDK cũ hơn. Vì vậy phần core ở dưới vẫn compile với Java 8, còn ví dụ JUnit 6 dành cho project test chạy trên Java 17+.

Dependency Maven tối thiểu:

~~~xml
<dependency>
    <groupId>org.junit.jupiter</groupId>
    <artifactId>junit-jupiter</artifactId>
    <version>6.1.3</version>
    <scope>test</scope>
</dependency>
~~~

### 7.1. @Test kiểm hành vi component

~~~java
@Test
void appliesDiscountAndAuditsOrder() {
    List<String> audit = new ArrayList<String>();
    Checkout checkout = new Checkout(
            order -> order.isActive(),
            order -> new BigDecimal("12.00"),
            order -> audit.add(order.getId()));

    Order order = new Order("ORD-1", new BigDecimal("120.00"), true);

    assertEquals(0,
            new BigDecimal("108.00").compareTo(checkout.total(order)));
    assertEquals(Collections.singletonList("ORD-1"), audit);
}
~~~

Test kiểm kết quả và side effect. So sánh `BigDecimal` bằng `compareTo` khi scale không phải một phần của contract; nếu scale là yêu cầu, dùng kiểm tra phù hợp để xác minh chính xác representation.

### 7.2. @ParameterizedTest kiểm nhiều giá trị

~~~java
@ParameterizedTest
@CsvSource({
    "99.99, false",
    "100.00, true",
    "100.01, true"
})
void eligibilityUsesInclusiveThreshold(
        String subtotal, boolean expected) {
    Predicate<Order> eligible = order ->
            order.isActive()
            && order.getSubtotal().compareTo(
                    new BigDecimal("100.00")) >= 0;

    Order order = new Order(
            "ORD-TEST", new BigDecimal(subtotal), true);

    assertEquals(expected, eligible.test(order));
}
~~~

Parameterized test giúp chạy cùng một hợp đồng với nhiều bộ input. Dùng case tại ranh giới, ngay dưới và ngay trên ngưỡng; bổ sung case âm/null nếu contract có quy định.

### 7.3. assertThrows kiểm tra exception và side effect

~~~java
@Test
void invalidDiscountFailsBeforeAudit() {
    List<String> audit = new ArrayList<String>();
    Checkout checkout = new Checkout(
            order -> true,
            order -> new BigDecimal("-1.00"),
            order -> audit.add(order.getId()));

    Order order = new Order("ORD-2", new BigDecimal("120.00"), true);

    IllegalStateException error = assertThrows(
            IllegalStateException.class,
            () -> checkout.total(order));

    assertEquals("discount is outside the valid range",
            error.getMessage());
    assertTrue(audit.isEmpty());
}
~~~

`assertThrows` nhận một lambda thực thi hành động và trả lại exception để kiểm thêm message/cause. Dùng `assertThrowsExactly` chỉ khi contract yêu cầu đúng class exception, không chấp nhận subclass.

### 7.4. assertAll gom các assertion liên quan

~~~java
assertAll(
        () -> assertEquals(expectedTotal, actualTotal),
        () -> assertEquals(1, audit.size()),
        () -> assertEquals("ORD-1", audit.get(0))
);
~~~

`assertAll` giúp kiểm nhiều điều kiện trên cùng kết quả và báo các assertion failure trong một lần chạy. Đừng dùng nó để gom các thao tác có side effect phụ thuộc nhau; chuẩn bị dữ liệu trước rồi assertion trên trạng thái đã thu được.

## 8. Dùng mock hay lambda fake?

Với một functional interface đơn giản, một lambda fake thường đủ:

~~~java
Predicate<Order> alwaysEligible = order -> true;
Consumer<Order> noAudit = order -> { };
~~~

Đây là các test double có hành vi xác định. Không cần tạo mock chỉ để trả true hoặc để ghi một argument vào list.

Mocking framework hữu ích khi dependency có nhiều method, cần mô phỏng lỗi phức tạp hoặc cần xác minh tương tác với một boundary. Nhưng nếu test chỉ xác minh lambda có trả đúng kết quả, hãy gọi functional method trực tiếp.

Không mock class dữ liệu/value object chỉ để kiểm một phép tính. Không mock chính lambda bằng cách so sánh tên class ẩn hoặc địa chỉ object. Một lambda có thể được runtime tạo/reuse theo cách implementation-specific; identity của lambda không phải hợp đồng Java.

### 8.1. Khi cần xác minh argument callback

Có thể dùng list capture hoặc Mockito ArgumentCaptor tùy mức độ phức tạp. Với callback đơn giản, list thường rõ ràng hơn:

~~~java
List<Order> received = new ArrayList<Order>();
Consumer<Order> callback = received::add;

service.process(order, callback);

assertEquals(1, received.size());
assertSame(order, received.get(0));
~~~

Nếu object có thể được copy/transform, kiểm các field theo contract thay vì yêu cầu cùng reference.

## 9. Những lỗi kiểm thử lambda thường gặp

**1. Test class ẩn của lambda.** Class name/identity là chi tiết runtime, không phải contract.

**2. Không khai báo target type.** Compiler cần biết functional interface để type inference.

**3. Chỉ test một input bình thường.** Thiếu biên, null và đường lỗi.

**4. Chỉ kiểm return value của Consumer.** Consumer trả void; cần kiểm side effect.

**5. Quên gọi Supplier.get().** Tạo Supplier không có nghĩa lambda đã chạy.

**6. Gọi Stream.filter nhưng không có terminal operation.** Pipeline lazy có thể chưa thực thi.

**7. Test mutable capture dùng chung.** Kết quả có thể phụ thuộc thứ tự hoặc song song.

**8. Dùng Thread.sleep để chờ callback.** Dễ flaky; dùng synchronization primitive và timeout.

**9. Mock functional interface chỉ để trả hằng số.** Một lambda fake thường đơn giản hơn.

**10. Kiểm tra mọi method call không cần thiết.** Tập trung contract và side effect có ý nghĩa.

**11. Không kiểm exception cause/message khi contract yêu cầu.** Test chỉ biết có lỗi nhưng không biết lỗi có đúng không.

**12. Bỏ qua short-circuit của Predicate.and/or.** Nếu side effect nằm trong predicate, test cần xác minh predicate thứ hai có được gọi không.

**13. Dùng BigDecimal.equals khi scale không phải yêu cầu.** So số học bằng compareTo; nếu scale là contract thì kiểm riêng.

**14. Giả định lambda luôn stateless.** Lambda có thể capture state; kiểm vòng đời và concurrency của state.

**15. Test implementation detail thay hành vi.** Đừng yêu cầu lambda có một class cụ thể hay method synthetic cụ thể.

**16. Dùng functional interface sai shape.** Predicate cho boolean; Function cho giá trị; Consumer cho side effect; Supplier cho giá trị không tham số.

**17. Quên exception trong custom checked functional interface.** Xác định rõ checked exception được truyền hay chuyển đổi.

**18. Test JUnit6 trên JDK8.** JUnit 6 yêu cầu Java17 runtime; giữ core code Java8-compatible và chọn runtime test phù hợp.

**19. Test async không có timeout.** Test có thể treo vô hạn khi callback không chạy.

**20. Ghi side effect vào collection không thread-safe trong parallel execution.** Dùng collector/concurrent collection hoặc tránh shared mutation.

## 10. Chương trình Java hoàn chỉnh và stdout

Tạo file **`LambdaFunctionalInterfaceDemo.java`**. Chương trình chỉ dùng JDK chuẩn và có thể compile với Java 8. Nó kiểm:

- Functional interface tự định nghĩa `DiscountPolicy`.
- Predicate xác định điều kiện eligibility và ngưỡng bằng đúng 100.
- Consumer ghi audit event.
- Checkout gọi đúng rule và không audit khi order bị từ chối.
- Discount không hợp lệ gây exception.
- Supplier chỉ thực thi khi gọi `get()`.

~~~java
import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Consumer;
import java.util.function.Predicate;
import java.util.function.Supplier;

public class LambdaFunctionalInterfaceDemo {
    @FunctionalInterface
    interface DiscountPolicy {
        BigDecimal discountFor(Order order);
    }

    static final class Order {
        final String id;
        final BigDecimal subtotal;
        final boolean active;

        Order(String id, BigDecimal subtotal, boolean active) {
            this.id = Objects.requireNonNull(id, "id");
            this.subtotal = Objects.requireNonNull(subtotal, "subtotal");
            if (subtotal.signum() < 0) {
                throw new IllegalArgumentException("subtotal must not be negative");
            }
            this.active = active;
        }
    }

    static final class Checkout {
        private final Predicate<Order> eligible;
        private final DiscountPolicy discountPolicy;
        private final Consumer<Order> audit;

        Checkout(Predicate<Order> eligible,
                 DiscountPolicy discountPolicy,
                 Consumer<Order> audit) {
            this.eligible = Objects.requireNonNull(eligible, "eligible");
            this.discountPolicy = Objects.requireNonNull(discountPolicy, "discountPolicy");
            this.audit = Objects.requireNonNull(audit, "audit");
        }

        BigDecimal total(Order order) {
            Objects.requireNonNull(order, "order");
            if (!eligible.test(order)) {
                throw new IllegalArgumentException("order is not eligible");
            }

            BigDecimal discount = discountPolicy.discountFor(order);
            if (discount == null || discount.signum() < 0
                    || discount.compareTo(order.subtotal) > 0) {
                throw new IllegalStateException("discount is outside the valid range");
            }

            BigDecimal total = order.subtotal.subtract(discount);
            audit.accept(order);
            return total;
        }
    }

    static void check(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    static void expectThrows(
            Class<? extends RuntimeException> expected,
            Runnable action,
            String message) {
        try {
            action.run();
        } catch (RuntimeException actual) {
            if (expected.isInstance(actual)) {
                return;
            }
            throw new AssertionError(message + ": wrong exception "
                    + actual.getClass().getName(), actual);
        }
        throw new AssertionError(message + ": no exception was thrown");
    }

    public static void main(String[] args) {
        List<String> auditEntries = new ArrayList<String>();

        Predicate<Order> eligible = order ->
                order.active
                && order.subtotal.compareTo(new BigDecimal("100.00")) >= 0;

        DiscountPolicy tenPercent = order ->
                order.subtotal.multiply(new BigDecimal("0.10"));

        Consumer<Order> audit = order -> auditEntries.add(order.id);

        Checkout checkout = new Checkout(eligible, tenPercent, audit);
        Order order = new Order("ORD-1", new BigDecimal("120.00"), true);

        BigDecimal total = checkout.total(order);
        check(total.compareTo(new BigDecimal("108.0000")) == 0,
                "10 percent discount should produce 108.0000");
        check(auditEntries.size() == 1 && "ORD-1".equals(auditEntries.get(0)),
                "audit consumer should receive the processed order");
        System.out.println("Eligible order total: " + total.toPlainString());
        System.out.println("Audit recorded: " + auditEntries.get(0));

        Order boundary = new Order("ORD-2", new BigDecimal("100.00"), true);
        check(eligible.test(boundary), "threshold must be inclusive");
        System.out.println("Boundary eligible: " + eligible.test(boundary));

        Order inactive = new Order("ORD-3", new BigDecimal("150.00"), false);
        expectThrows(IllegalArgumentException.class,
                () -> checkout.total(inactive),
                "inactive order must be rejected");
        check(auditEntries.size() == 1,
                "rejected order must not be audited");
        System.out.println("Rejected order: IllegalArgumentException");

        Checkout invalidCheckout = new Checkout(
                eligible,
                ignored -> new BigDecimal("-1.00"),
                audit);
        expectThrows(IllegalStateException.class,
                () -> invalidCheckout.total(order),
                "negative discount must be rejected");
        check(auditEntries.size() == 1,
                "invalid discount must not be audited");
        System.out.println("Invalid discount: IllegalStateException");

        AtomicInteger supplierCalls = new AtomicInteger();
        Supplier<String> lazyValue = () -> {
            supplierCalls.incrementAndGet();
            return "ready";
        };
        int before = supplierCalls.get();
        String supplied = lazyValue.get();
        check(before == 0 && supplierCalls.get() == 1,
                "supplier should run only when get is called");
        System.out.println("Supplier calls: " + before + " -> "
                + supplierCalls.get() + " (" + supplied + ")");
        System.out.println("All checks passed");
    }
}
~~~

Biên dịch trên JDK8 hoặc JDK hiện hành:

~~~bash
javac -encoding UTF-8 LambdaFunctionalInterfaceDemo.java
java LambdaFunctionalInterfaceDemo
~~~

Nếu dùng JDK 9+, có thể kiểm tính tương thích Java 8 bằng:

~~~bash
javac -Xlint:-options --release 8 -encoding UTF-8 LambdaFunctionalInterfaceDemo.java
java LambdaFunctionalInterfaceDemo
~~~

Stdout đã được chạy kiểm chứng:

~~~text
Eligible order total: 108.0000
Audit recorded: ORD-1
Boundary eligible: true
Rejected order: IllegalArgumentException
Invalid discount: IllegalStateException
Supplier calls: 0 -> 1 (ready)
All checks passed
~~~

Chương trình dùng `BigDecimal.compareTo` để kiểm giá trị tiền mà không phụ thuộc scale. Dòng `Boundary eligible: true` xác nhận ngưỡng 100 là inclusive. Hai dòng exception xác nhận order không hợp lệ và discount âm bị từ chối. Audit list giữ đúng một order hợp lệ; Supplier được gọi đúng một lần khi `get()` chạy.

## 11. Ma trận kiểm thử nên có

| Nhóm | Input | Điều cần assert |
|---|---|---|
| Giá trị thường | Dữ liệu hợp lệ | Kết quả đúng |
| Ranh giới | Ngay dưới/ngay tại/ngay trên ngưỡng | Điều kiện chính xác |
| Giá trị rỗng | Empty collection/string | Contract rõ |
| Null | Null được phép/cấm | Kết quả hoặc exception đúng |
| Side effect | Consumer/callback | Argument và số lần gọi |
| Thứ tự | Nhiều callback | Thứ tự theo contract |
| Exception | Rule ném lỗi | Type, message/cause, không side effect sai |
| Composition | and/or/compose/andThen | Kết quả chuỗi hành vi |
| Closure | Captured variable | Giá trị và vòng đời đúng |
| Supplier | Chưa gọi/đã gọi | Lazy evaluation và số lần |
| Stream | Có terminal operation | Lambda thực sự được thực thi |
| Async | Callback/executor | Kết quả, timeout, context |
| Parallel | Nhiều thread | Không race hoặc mutation sai |
| Precision | BigDecimal | Scale/rounding theo contract |
| Integration | Adapter thật | Boundary bên ngoài hoạt động |

## 12. Bài tập tự luyện

1. Functional interface có bao nhiêu abstract method?
2. Default method có làm interface mất tính functional không?
3. `@FunctionalInterface` giúp compiler kiểm tra điều gì?
4. Vì sao lambda cần target type?
5. Functional method của Predicate, Function, Consumer và Supplier là gì?
6. Vì sao Consumer cần kiểm side effect thay vì return value?
7. Supplier chạy lúc nào?
8. Khi nào nên định nghĩa functional interface riêng?
9. Test một predicate có ngưỡng 100 cần những input nào?
10. Vì sao nên kiểm cả điều kiện ngay dưới và ngay tại ngưỡng?
11. Làm sao xác minh callback được gọi đúng một lần?
12. Làm sao kiểm lambda ném đúng exception?
13. `assertThrows` nhận tham số functional interface nào về mặt ý nghĩa?
14. Vì sao không so sánh class name của hai lambda?
15. Vì sao Stream cần terminal operation để test filter?
16. Vì sao parallel stream không nên ghi vào ArrayList thường?
17. Khi nào dùng fake lambda thay vì Mockito?
18. Cách kiểm một Supplier lazy là gì?
19. Nếu lambda capture AtomicInteger, test cần chú ý gì?
20. JUnit 6 yêu cầu Java runtime tối thiểu nào?
21. Vì sao phần core demo vẫn có thể compile với Java 8?
22. Khi functional interface cần checked exception, nên thiết kế thế nào?
23. Khi test component nhận lambda, cần kiểm điều gì ngoài output?
24. Vì sao không nên test lambda bằng reflection hoặc synthetic class name?

**Gợi ý đáp án:** (1) Một functional abstract method. (2) Không. (3) Bảo vệ ý định một abstract method. (4) Để suy luận kiểu tham số và kết quả. (5) test, apply, accept, get. (6) Vì nó trả void và tác động lên trạng thái/boundary. (7) Khi get được gọi. (8) Khi tên nghiệp vụ, checked exception hoặc contract riêng cần thể hiện rõ. (9) 99.99, 100 và 100.01. (10) Phát hiện dùng sai > hoặc >=. (11) Đếm/capture callback. (12) assertThrows và kiểm type/message/cause. (13) Executable, một functional interface mô tả đoạn code có thể ném Throwable. (14) Class identity là chi tiết implementation. (15) Vì pipeline lazy. (16) Vì ArrayList không thread-safe cho concurrent writes. (17) Khi dependency chỉ cần một hành vi nhỏ và xác định. (18) Đếm lời gọi trước/sau get. (19) Reset state riêng, tránh chia sẻ giữa test. (20) Java 17. (21) Core chỉ dùng Java 8 API/syntax. (22) Tạo custom functional interface khai báo throws. (23) Rule được gọi đúng lúc, side effect, exception và thứ tự. (24) Không thuộc contract công khai của lambda.

## Tổng kết

Kiểm thử lambda qua functional interface nghĩa là kiểm tra **hợp đồng hành vi của functional method**. Dùng `Predicate` cho điều kiện, `Function` cho chuyển đổi, `Consumer` cho side effect, `Supplier` cho giá trị được cung cấp khi gọi và custom functional interface khi nghiệp vụ cần tên/exception riêng. Test input bình thường, biên, null, exception, số lần gọi, thứ tự và side effect. Khi lambda được inject vào service, test cả rule lẫn cách service sử dụng rule. Dùng JUnit Jupiter parameterized tests cho nhiều bộ dữ liệu, giữ test deterministic và tránh phụ thuộc class ẩn/identity của lambda. Core Java demo vẫn tương thích Java 8; JUnit 6 hiện hành cần Java 17+.

### Tài liệu chính thức hiện hành

- [Oracle Java SE 26 — java.util.function package](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/function/package-summary.html)
- [Java Language Specification SE 26 — Functional Interfaces](https://docs.oracle.com/javase/specs/jls/se26/html/jls-9.html#jls-9.8)
- [Oracle Java SE 26 — Predicate](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/function/Predicate.html)
- [Oracle Java SE 26 — Function](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/function/Function.html)
- [Oracle Java SE 26 — Consumer](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/function/Consumer.html)
- [Oracle Java SE 26 — Supplier](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/function/Supplier.html)
- [JUnit 6.1.3 — User Guide](https://docs.junit.org/6.1.3/_exports/junit-user-guide-6.1.3.html)
- [JUnit 6.1.3 — Release Notes](https://docs.junit.org/6.1.3/release-notes)
- [JUnit 6.1.3 — Parameterized Tests](https://docs.junit.org/6.1.3/writing-tests/parameterized-classes-and-tests.html)
