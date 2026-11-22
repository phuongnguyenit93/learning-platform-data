# Thiết kế bộ quy tắc với Predicate, Function và method reference (Java 8+)

Khi ứng dụng có nhiều điều kiện nghiệp vụ, cách dễ bảo trì là biểu diễn mỗi điều kiện thành một hàm có kiểu rõ ràng, đặt tên cho từng rule, rồi kết hợp chúng theo chính sách. Java cung cấp ba công cụ nền tảng trong `java.util.function`:

- `Predicate<T>` nhận một giá trị và trả về `boolean`: phù hợp để hỏi đối tượng có thỏa điều kiện không.
- `Function<T,R>` nhận một giá trị kiểu `T` và trả về kết quả kiểu `R`: phù hợp để trích xuất, chuẩn hóa hoặc biến đổi dữ liệu.
- **Method reference** dùng method có sẵn làm implementation của functional interface, giúp diễn đạt ngắn gọn những phép kiểm tra/biến đổi đã có tên.

Nguyên tắc thiết kế là tách **điều kiện** khỏi **phép biến đổi**, giữ từng rule nhỏ và có tên, xác định rõ thứ tự/short-circuit, và không đặt side effect vào predicate. Các functional interface này có từ **Java 8** và vẫn là API chuẩn trong JDK hiện đại. Chương trình cuối bài chỉ dùng API và cú pháp Java 8, được biên dịch bằng JDK 17 với tùy chọn `--release 8`.

## 1. Functional interface là target type của lambda và method reference

Một functional interface có một abstract method duy nhất (single abstract method, SAM). Lambda hoặc method reference được gán vào interface đó theo **target type** mà compiler suy ra từ ngữ cảnh.

~~~java
Predicate<String> hasText = value -> !value.trim().isEmpty();
Function<String, Integer> length = String::length;

boolean valid = hasText.test("Java");
int count = length.apply("Java");
~~~

`Predicate<String>` có abstract method `test(String)` trả boolean; `Function<String,Integer>` có `apply(String)` trả Integer. Method reference `String::length` phù hợp với chữ ký Function yêu cầu: nhận String, trả int (được boxing thành Integer).

Có thể dùng lambda trong assignment, argument của method hoặc cast context khi có target functional interface phù hợp. Không thể viết lambda như biểu thức độc lập mà không có target type.

Functional interface vẫn có thể có default method, static method và method kế thừa từ Object. Điều kiện cốt lõi là nó có một function type/SAM để lambda hoặc method reference triển khai.

## 2. Chọn đúng Predicate hay Function

| Câu hỏi thiết kế | Kiểu phù hợp | Method chính | Ví dụ |
| --- | --- | --- | --- |
| Đối tượng có thỏa điều kiện không? | `Predicate<T>` | `test(T)` | `order -> order.total() > 100` |
| Từ đối tượng lấy ra/biến đổi giá trị? | `Function<T,R>` | `apply(T)` | `Order::total` |
| Nhận input và thực hiện thao tác không trả kết quả? | `Consumer<T>` | `accept(T)` | `System.out::println` |
| Cung cấp giá trị không cần input? | `Supplier<T>` | `get()` | `() -> UUID.randomUUID()` |
| Hai input tạo boolean? | `BiPredicate<T,U>` | `test(T,U)` | `(user, role) -> ...` |
| Hai input tạo kết quả? | `BiFunction<T,U,R>` | `apply(T,U)` | `(price, tax) -> ...` |
| Một input và output cùng kiểu? | `UnaryOperator<T>` | `apply(T)` | `String::trim` |
| Hai operand cùng kiểu tạo kết quả cùng kiểu? | `BinaryOperator<T>` | `apply(T,T)` | `BigDecimal::add` |

Không dùng `Function<T,Boolean>` thay `Predicate<T>` nếu mục tiêu chỉ là kiểm tra điều kiện. `Predicate` diễn đạt đúng ý nghĩa, trả primitive boolean và có sẵn các phép kết hợp `and`, `or`, `negate`.

Tương tự, không dùng `Predicate<T>` để biến đổi object. Nếu cần lấy tổng tiền, tên khách hàng hoặc mã vùng, dùng `Function<T,R>`; sau đó mới ghép kết quả với predicate.

## 3. Thiết kế rule nguyên tử bằng Predicate

Một rule nên biểu diễn một điều kiện nhỏ, có thể đọc như câu nghiệp vụ:

~~~java
Predicate<Order> accountActive = order -> !order.blocked();
Predicate<Order> minimumTotal = order -> order.total().signum() > 0;
Predicate<Order> regionSupported = order -> "VN".equals(order.region());
~~~

Tên biến mô tả ý nghĩa rule; phần thân tập trung vào đúng một điều kiện. Predicate nguyên tử có thể được kiểm thử độc lập, tái sử dụng và kết hợp thành policy lớn.

Một rule tốt thường có các đặc điểm:

- Có tên diễn đạt nghiệp vụ, không chỉ tên kỹ thuật như `p1` hay `check2`.
- Nhận input đã được xác định kiểu và trả boolean.
- Không thay đổi input hoặc trạng thái dùng chung.
- Có quy định rõ về null, giá trị biên và ngoại lệ.
- Không gọi I/O hoặc service bên ngoài trong lúc đánh giá nếu có thể tách việc đó ra trước.

`Predicate` không tự đảm bảo các đặc điểm này. Chúng là tiêu chuẩn thiết kế của ứng dụng.

## 4. Kết hợp rule bằng and, or và negate

Java 8 cung cấp các default method cho `Predicate<T>`:

~~~java
Predicate<Order> accountActive = order -> !order.blocked();
Predicate<Order> minimumTotal = order -> order.total().signum() > 0;
Predicate<Order> regionSupported = order -> "VN".equals(order.region());

Predicate<Order> eligible =
        accountActive.and(minimumTotal).and(regionSupported);

Predicate<Order> blocked = accountActive.negate();
Predicate<Order> domesticOrPartner =
        regionSupported.or(order -> "SG".equals(order.region()));
~~~

- `and(other)` chỉ true nếu cả hai predicate đều true.
- `or(other)` true nếu ít nhất một predicate true.
- `negate()` đảo kết quả true/false.

**`and` và `or` dùng short-circuit.** Với `a.and(b)`, nếu `a` false thì `b` không chạy. Với `a.or(b)`, nếu `a` true thì `b` không chạy. Thứ tự đánh giá là thứ tự kết hợp từ trái sang phải.

Điều này hữu ích khi điều kiện đầu rẻ và loại được nhiều input, hoặc khi cần bảo vệ điều kiện sau khỏi null:

~~~java
Predicate<String> nonNull = Objects::nonNull;
Predicate<String> hasPrefix = nonNull.and(value -> value.startsWith("ORD-"));

boolean safe = hasPrefix.test(null); // false, không gọi startsWith trên null.
~~~

Không đặt side effect vào predicate bên phải rồi dựa vào việc nó chắc chắn chạy. Short-circuit có nghĩa một số predicate có thể không được gọi.

`Predicate.negate()` có từ **Java 8**. Static method `Predicate.not(predicate)` được bổ sung từ **Java 11**. Với code cần chạy Java 8, dùng `predicate.negate()`.

## 5. Dùng Function để trích xuất và chuẩn hóa dữ liệu

`Function<T,R>` nhận một input và trả kết quả. Khi xây rule engine, Function thường làm hai việc:

1. **Trích xuất:** lấy field cần kiểm tra từ object, ví dụ `Order::total` hoặc `Order::region`.
2. **Chuẩn hóa/biến đổi:** đưa dữ liệu về dạng chuẩn trước khi so sánh, ví dụ trim mã, chuẩn hóa chữ hoa hoặc parse decimal.

~~~java
Function<Order, BigDecimal> totalOf = Order::total;
Function<Order, String> regionOf = Order::region;

BigDecimal total = totalOf.apply(order);
String region = regionOf.apply(order);
~~~

Method reference `Order::total` là cách gọn để viết `order -> order.total()`. Tên accessor thể hiện field được trích xuất và có thể tái sử dụng ở nhiều rule.

Một Function có thể trả null nếu contract cho phép. Hãy quyết định rõ kết quả null có nghĩa gì; đừng mặc định mọi Function đều trả object hợp lệ.

## 6. Tạo Predicate tái sử dụng từ Function và Predicate

Một mẫu hữu ích là **extract field rồi kiểm tra field**. Ta có thể viết helper tổng quát:

~~~java
static <T, U> Predicate<T> by(
        Function<? super T, ? extends U> extractor,
        Predicate<? super U> condition) {
    return value -> condition.test(extractor.apply(value));
}
~~~

Dùng helper:

~~~java
Predicate<BigDecimal> atLeastMinimum =
        total -> total.compareTo(new BigDecimal("100.00")) >= 0;

Predicate<Order> orderMeetsMinimum =
        by(Order::total, atLeastMinimum);
~~~

`by` tách hai trách nhiệm: `Function` xác định lấy dữ liệu ở đâu; `Predicate` xác định dữ liệu đó phải thỏa điều kiện gì. Cùng một predicate kiểm tra decimal có thể dùng cho Order, Invoice hoặc Cart nếu các kiểu đó đều trích xuất được BigDecimal.

Chữ ký dùng variance có chủ đích:

- `Function<? super T, ? extends U>` chấp nhận extractor nhận T hoặc supertype của T, rồi trả U hoặc subtype của U.
- `Predicate<? super U>` chấp nhận predicate kiểm tra U hoặc supertype của U.

Đây là mẫu wildcard phổ biến để API linh hoạt mà vẫn giữ type safety.

## 7. Biến nhiều predicate thành Rule có tên và thông điệp lỗi

Một `Predicate<T>` chỉ trả boolean. Nó không tự nói vì sao input bị từ chối. Nếu giao diện cần hiển thị nhiều lỗi, hãy bọc predicate cùng tên và message vào một kiểu miền:

~~~java
final class Rule<T> {
    private final String name;
    private final Predicate<? super T> condition;
    private final String failureMessage;

    Rule(String name, Predicate<? super T> condition, String failureMessage) {
        this.name = Objects.requireNonNull(name);
        this.condition = Objects.requireNonNull(condition);
        this.failureMessage = Objects.requireNonNull(failureMessage);
    }

    Predicate<? super T> condition() { return condition; }

    String failureDescription() {
        return name + " (" + failureMessage + ")";
    }
}
~~~

`Rule<T>` không thay thế `Predicate`. Nó là metadata của ứng dụng: đặt tên, mô tả lỗi và giữ predicate cần đánh giá. Khi có thêm yêu cầu như mã lỗi, severity, nhóm rule hoặc nguồn cấu hình, có thể mở rộng kiểu Rule mà không làm thay đổi cách viết predicate cơ bản.

Không nhét mọi thông tin vào một predicate khổng lồ nếu ứng dụng cần hiển thị lỗi riêng cho từng điều kiện.

## 8. Hai chiến lược đánh giá: fail-fast và thu thập mọi lỗi

Đây là quyết định quan trọng khi thiết kế bộ quy tắc.

### Fail-fast: chỉ cần biết có đạt hay không

~~~java
Predicate<Order> eligible =
        accountActive.and(minimumTotal).and(regionSupported);

boolean accepted = eligible.test(order);
~~~

Cách này short-circuit và phù hợp với quyết định boolean đơn giản. Nếu rule đầu đã false, các rule sau có thể không được đánh giá.

### Collect-all: cần báo tất cả lỗi

~~~java
List<String> failures = rules.stream()
        .filter(rule -> !rule.condition().test(order))
        .map(Rule::failureDescription)
        .collect(Collectors.toList());
~~~

Cách này chạy từng rule độc lập để thu thập tất cả vi phạm. Nếu cần hiện cả “tài khoản bị khóa”, “tổng tiền thấp” và “vùng không hỗ trợ”, đây thường là cách phù hợp hơn.

Không dùng một chuỗi `and` rồi mong nó trả đủ mọi lỗi: short-circuit được thiết kế để dừng sớm. Ngược lại, nếu chỉ cần true/false, không nhất thiết phải chạy tất cả rule.

## 9. Rule order, short-circuit và tính xác định

Thứ tự predicate có thể ảnh hưởng hiệu năng và hành vi quan sát:

- Đưa điều kiện rẻ, dễ loại input lên trước khi dùng fail-fast.
- Đặt null guard trước điều kiện dereference object.
- Đặt rule có chi phí cao sau điều kiện rẻ nếu semantics cho phép.
- Giữ thứ tự rule ổn định để thông báo lỗi và test có kết quả dễ dự đoán.

Nếu predicate thuần và không ném ngoại lệ ngoài contract, thay đổi thứ tự thường chỉ thay đổi chi phí đánh giá. Nếu predicate có side effect hoặc phụ thuộc trạng thái dùng chung, thay đổi thứ tự có thể đổi kết quả ứng dụng; đó là dấu hiệu rule đang gánh quá nhiều trách nhiệm.

Với collect-all, các rule độc lập được đánh giá lần lượt. Nếu một rule ném exception, stream/loop sẽ dừng trừ khi ứng dụng có chính sách xử lý lỗi riêng. Đừng tự động biến mọi exception thành “rule không đạt”; lỗi hệ thống và dữ liệu không hợp lệ là hai tình huống khác nhau.

## 10. Function composition: compose và andThen

`Function` hỗ trợ kết hợp các phép biến đổi:

~~~java
Function<String, String> trim = String::trim;
Function<String, String> uppercase =
        value -> value.toUpperCase(Locale.ROOT);

Function<String, String> normalize = trim.andThen(uppercase);

String code = normalize.apply("  acme  "); // ACME
~~~

| Biểu thức | Thứ tự thực hiện | Dạng toán học |
| --- | --- | --- |
| `f.andThen(g)` | f trước, rồi g | `g(f(x))` |
| `f.compose(g)` | g trước, rồi f | `f(g(x))` |
| `Function.identity()` | Trả lại input | `x` |

Ví dụ `parse.compose(trim)` tương đương trim chuỗi trước rồi parse:

~~~java
Function<String, BigDecimal> parse = BigDecimal::new;
Function<String, String> trim = String::trim;

Function<String, BigDecimal> parseTrimmed = parse.compose(trim);
BigDecimal amount = parseTrimmed.apply(" 125.50 ");
~~~

`andThen`/`compose` tạo Function mới; chúng không thực hiện phép biến đổi ngay tại thời điểm ghép. Hàm chỉ chạy khi gọi `apply`. Nếu một bước ném exception, exception được truyền về caller.

## 11. Method reference: bốn dạng thường gặp

Method reference là cú pháp tham chiếu tới method hoặc constructor có sẵn. Compiler đối chiếu target functional interface để xác định chữ ký phù hợp.

| Dạng | Cú pháp | Ví dụ |
| --- | --- | --- |
| Static method | `Type::staticMethod` | `Objects::nonNull` |
| Bound instance method | `object::instanceMethod` | `allowedRegions::contains` |
| Unbound instance method | `Type::instanceMethod` | `Order::total` |
| Constructor | `Type::new` | `BigDecimal::new` |

Ví dụ:

~~~java
Predicate<String> nonNull = Objects::nonNull;
Predicate<String> allowed = allowedRegions::contains;
Function<Order, BigDecimal> totalOf = Order::total;
Function<String, BigDecimal> parse = BigDecimal::new;
~~~

- Static method reference không cần object receiver.
- Bound reference giữ receiver đã chỉ định ở phía trái `::`.
- Unbound reference nhận object làm đối số đầu tiên rồi gọi method trên object đó.
- Constructor reference tạo object bằng constructor phù hợp với target type.

Method reference giúp code gọn khi method có sẵn đã diễn đạt đúng ý. Nếu lambda rõ nghĩa hơn, hãy dùng lambda; không cần biến mọi biểu thức thành method reference.

## 12. Target typing, overload và lỗi method reference mơ hồ

Method reference cần target type để compiler xác định tham số, kiểu trả về và overload phù hợp.

~~~java
Function<String, String> uppercase =
        value -> value.toUpperCase(Locale.ROOT);
~~~

Ở đây dùng lambda để nói rõ muốn chuẩn hóa theo locale độc lập với locale mặc định. Với `String::toUpperCase`, compiler có thể phân giải overload dựa trên target type, nhưng ý nghĩa locale vẫn cần được cân nhắc.

Một số method như `String::valueOf` có nhiều overload nhận primitive/object; trong lời gọi method có overload, type inference có thể khó đọc. Khi compiler báo ambiguous method reference, hãy khai báo target type tường minh hoặc viết lambda có tham số/kiểu rõ ràng.

Không cast tùy tiện để ép compiler im lặng nếu chưa hiểu chữ ký method được chọn.
## 13. Null handling và contract dữ liệu

`Predicate` không tự xử lý null. Chẳng hạn:

~~~java
Predicate<String> startsWithOrder =
        value -> value.startsWith("ORD-");
~~~

Gọi `startsWithOrder.test(null)` sẽ ném `NullPointerException`. Nếu null là input hợp lệ nhưng không đạt điều kiện, hãy bảo vệ rõ:

~~~java
Predicate<String> nonNull = Objects::nonNull;
Predicate<String> startsWithOrder =
        nonNull.and(value -> value.startsWith("ORD-"));
~~~

`Predicate.isEqual(target)` kiểm tra equality qua `Objects.equals`, do đó có semantics null-safe cho phép so sánh. Với field nghiệp vụ bắt buộc, thường nên validate null ở biên hệ thống hoặc constructor thay vì để null lan qua toàn bộ rule engine.

Với Function, hãy định nghĩa liệu extractor có thể trả null hay không. Nếu null có ý nghĩa “không có dữ liệu”, cân nhắc biểu diễn bằng `Optional` ở API phù hợp; đừng tạo Optional lồng nhau không cần thiết hoặc dùng null cho nhiều trạng thái không phân biệt.

## 14. Purity, side effect và exception trong rule

`Predicate` và `Function` chỉ định hình chữ ký, không cưỡng chế tính thuần (purity). Về thiết kế, predicate nên trả lời một câu hỏi dựa trên input và snapshot rõ ràng.

Tránh đặt các hành động sau vào predicate:

- Ghi database, gửi HTTP hoặc publish event.
- Tăng counter, cập nhật cache hoặc thay đổi object đầu vào.
- Đọc file/network trong lúc kiểm tra rule.
- Dựa vào trạng thái mutable có thể thay đổi giữa các lần đánh giá.
- Sinh random value hoặc timestamp mới làm kết quả mỗi lần gọi khác nhau.

Nếu cần tải dữ liệu, thực hiện việc đó ở service/use-case trước, tạo context hoặc snapshot rồi truyền vào rule. Điều này giúp rule dễ test, có thể đánh giá lặp lại và không phụ thuộc thứ tự ngẫu nhiên.

Exception từ predicate/function thường được truyền về caller. Hãy phân biệt:

- **Không đạt rule:** kết quả boolean false, có thể kèm message nghiệp vụ.
- **Dữ liệu không hợp lệ:** có thể là validation failure đã định nghĩa.
- **Lỗi kỹ thuật:** database timeout, service unavailable, bug hoặc trạng thái bất ngờ; không nên âm thầm đổi thành false.

Nếu ứng dụng muốn gom exception theo từng rule, hãy thiết kế kiểu kết quả rõ ràng (ví dụ `RuleOutcome`) và policy bắt lỗi cụ thể; không dùng catch-all rồi che nguyên nhân.

## 15. Generic variance và thiết kế API dễ tái sử dụng

Khi viết helper hoặc RuleSet, wildcard giúp chấp nhận function/predicate có kiểu tổng quát hơn:

~~~java
static <T, U> Predicate<T> by(
        Function<? super T, ? extends U> extractor,
        Predicate<? super U> condition) {
    return value -> condition.test(extractor.apply(value));
}
~~~

Vì extractor chỉ **nhận T** nên có thể nhận T hoặc supertype của T (`? super T`). Nó **trả U** nên có thể trả U hoặc subtype của U (`? extends U`). Predicate tiêu thụ U nên `? super U` là phù hợp.

Một Rule có thể lưu `Predicate<? super T>` để dùng predicate nhận một kiểu cha. Không cần đưa wildcard vào mọi biến local: dùng wildcard ở ranh giới API nơi nó tăng khả năng tái sử dụng; giữ kiểu cụ thể bên trong code khi điều đó giúp đọc dễ hơn.

## 16. Khi nào dùng primitive-specialized functional interfaces?

`Predicate<Integer>` nhận wrapper Integer; khi truyền primitive int, Java có thể boxing/unboxing. Với xử lý số lượng lớn, các interface chuyên primitive có thể tránh boxing:

| Kiểu | Vai trò |
| --- | --- |
| `IntPredicate` | `int -> boolean` |
| `LongPredicate` | `long -> boolean` |
| `DoublePredicate` | `double -> boolean` |
| `ToIntFunction<T>` | `T -> int` |
| `ToLongFunction<T>` | `T -> long` |
| `ToDoubleFunction<T>` | `T -> double` |
| `IntUnaryOperator` | `int -> int` |
| `LongUnaryOperator` | `long -> long` |
| `DoubleUnaryOperator` | `double -> double` |

Đây là các API hiện hành trong `java.util.function`. Chọn chúng khi primitive type là một phần tự nhiên của contract và profiling cho thấy boxing có ý nghĩa. Với logic nghiệp vụ đọc nhiều field, `Predicate<Order>`/`Function<Order,R>` thường rõ ràng hơn; không tối ưu boxing trước khi có bằng chứng.

## 17. Dùng rule với Stream, Optional và collection

Functional interfaces kết nối trực tiếp với nhiều API chuẩn:

~~~java
List<Order> accepted = orders.stream()
        .filter(eligible)
        .collect(Collectors.toList());

List<String> codes = accepted.stream()
        .map(Order::customerCode)
        .collect(Collectors.toList());

boolean anyBlocked = orders.stream()
        .anyMatch(Order::blocked);
~~~

- `filter(Predicate)` giữ phần tử thỏa điều kiện.
- `map(Function)` biến đổi mỗi phần tử.
- `anyMatch/allMatch/noneMatch` đánh giá predicate với short-circuit.
- `Collection.removeIf(Predicate)` loại phần tử thỏa predicate khỏi collection mutable.
- `Optional.filter(Predicate)` giữ Optional nếu giá trị thỏa điều kiện.

Stream pipeline thường lazy cho tới terminal operation; nhưng bản thân `Predicate.test` hoặc `Function.apply` là lời gọi đồng bộ khi được thực thi. Đừng mặc định việc tạo Function đồng nghĩa công việc đã chạy.

Không thay đổi collection nguồn từ bên trong predicate của stream đang duyệt nó. Hãy dùng terminal operation hoặc collection API phù hợp để tránh concurrent modification và hành vi khó đoán.

## 18. Thiết kế RuleSet: khi nào cần class riêng?

Nếu ứng dụng chỉ có hai hoặc ba điều kiện, các biến `Predicate<T>` đặt tên và ghép trực tiếp thường đủ. Khi rule có tên, thông điệp lỗi, nhóm, phiên bản hoặc thứ tự ưu tiên, hãy dùng abstraction nhỏ như `Rule<T>`.

Một RuleSet có thể có các trách nhiệm:

- Lưu danh sách rule theo thứ tự ổn định.
- Đánh giá tất cả rule để thu thập vi phạm.
- Cung cấp một predicate tổng hợp cho fail-fast.
- Trả kết quả bất biến gồm accepted/rejected và danh sách lỗi.
- Không tự quyết định persistence, gửi notification hay ghi log thay tầng nghiệp vụ.

Đừng xây framework rule tổng quát có DSL, reflection, expression parser, dynamic class loading và plugin registry nếu bài toán chỉ cần vài predicate. Bắt đầu bằng functional interface có sẵn; chỉ thêm abstraction khi metadata hoặc lifecycle thực sự cần.

## 19. Chương trình Java độc lập: rule engine nhỏ có thể chạy

Chương trình dưới đây tương thích **Java 8**. Nó dùng POJO và collection API có từ Java 8; biên dịch trên JDK 17 với tùy chọn `--release 8`. Demo thể hiện Function chuẩn hóa chuỗi và parse BigDecimal, method reference, Predicate nguyên tử, helper kết hợp Function với Predicate, Rule có tên, collect-all, fail-fast, null guard và short-circuit.

Lưu thành **`RuleDesignDemo.java`**:

~~~java
import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Objects;
import java.util.Set;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Function;
import java.util.function.Predicate;
import java.util.stream.Collectors;

public final class RuleDesignDemo {
    private static final BigDecimal MIN_TOTAL = new BigDecimal("100.00");

    static final class Order {
        private final String customerCode;
        private final BigDecimal total;
        private final String region;
        private final boolean blocked;

        Order(String customerCode, BigDecimal total, String region, boolean blocked) {
            this.customerCode = Objects.requireNonNull(customerCode, "customerCode");
            this.total = Objects.requireNonNull(total, "total");
            this.region = Objects.requireNonNull(region, "region");
            this.blocked = blocked;
        }

        String customerCode() { return customerCode; }
        BigDecimal total() { return total; }
        String region() { return region; }
        boolean blocked() { return blocked; }
    }

    static final class Rule<T> {
        private final String name;
        private final Predicate<? super T> condition;
        private final String failureMessage;

        Rule(String name, Predicate<? super T> condition, String failureMessage) {
            this.name = Objects.requireNonNull(name, "name");
            this.condition = Objects.requireNonNull(condition, "condition");
            this.failureMessage = Objects.requireNonNull(failureMessage, "failureMessage");
        }

        Predicate<? super T> condition() { return condition; }

        String failureDescription() {
            return name + " (" + failureMessage + ")";
        }
    }

    static final class Evaluation {
        private final List<String> failures;

        Evaluation(List<String> failures) {
            this.failures = Collections.unmodifiableList(new ArrayList<>(failures));
        }

        boolean accepted() {
            return failures.isEmpty();
        }

        String summary() {
            return accepted() ? "accepted" : "rejected: " + String.join("; ", failures);
        }
    }

    private static <T, U> Predicate<T> by(
            Function<? super T, ? extends U> extractor,
            Predicate<? super U> condition) {
        Objects.requireNonNull(extractor, "extractor");
        Objects.requireNonNull(condition, "condition");
        return value -> condition.test(extractor.apply(value));
    }

    private static <T> Evaluation evaluateAll(T input, List<Rule<T>> rules) {
        List<String> failures = rules.stream()
                .filter(rule -> !rule.condition().test(input))
                .map(Rule::failureDescription)
                .collect(Collectors.toList());
        return new Evaluation(failures);
    }

    private static void check(boolean condition, String message) {
        if (!condition) throw new AssertionError(message);
    }

    public static void main(String[] args) {
        Function<String, String> trim = String::trim;
        Function<String, String> uppercase =
                value -> value.toUpperCase(Locale.ROOT);
        Function<String, String> normalizeCode = trim.andThen(uppercase);
        Function<String, BigDecimal> parseTotal = BigDecimal::new;

        Set<String> allowedRegions = new HashSet<>(Arrays.asList("VN", "SG"));
        Predicate<Order> blocked = Order::blocked;
        Predicate<Order> notBlocked = blocked.negate();
        Predicate<BigDecimal> atLeastMinimum =
                total -> total.compareTo(MIN_TOTAL) >= 0;
        Predicate<Order> minimumTotal = by(Order::total, atLeastMinimum);
        Predicate<Order> regionAllowed = by(Order::region, allowedRegions::contains);

        List<Rule<Order>> rules = Arrays.asList(
                new Rule<>("account active", notBlocked, "Account is blocked"),
                new Rule<>("minimum total", minimumTotal, "Total is below minimum"),
                new Rule<>("region supported", regionAllowed, "Region is unsupported")
        );

        Function<Order, Evaluation> evaluate = order -> evaluateAll(order, rules);
        Function<Evaluation, String> render = Evaluation::summary;
        Function<Order, String> explain = evaluate.andThen(render);

        Order raw = new Order(" acme ", parseTotal.apply("120.00"), "VN", false);
        Order normalized = new Order(
                normalizeCode.apply(raw.customerCode()),
                raw.total(), raw.region(), raw.blocked());
        Order rejected = new Order("blocked", new BigDecimal("20.00"), "XX", true);

        Predicate<Order> eligible = notBlocked.and(minimumTotal).and(regionAllowed);
        Evaluation acceptedResult = evaluate.apply(normalized);
        String rejectedSummary = explain.apply(rejected);

        Predicate<String> nonNull = Objects::nonNull;
        Predicate<String> nonBlank = nonNull.and(value -> !value.trim().isEmpty());

        AtomicInteger laterRuleCalls = new AtomicInteger();
        Predicate<Order> instrumentedLaterRule = order -> {
            laterRuleCalls.incrementAndGet(); // Test instrumentation only.
            return true;
        };
        Predicate<Order> shortCircuit = notBlocked.and(instrumentedLaterRule);
        boolean blockedRejected = !shortCircuit.test(rejected);

        System.out.println("normalized code: " + normalized.customerCode());
        System.out.println("parsed amount: " + raw.total().toPlainString());
        System.out.println("accepted order: " + acceptedResult.summary());
        System.out.println("rejected order: " + rejectedSummary);
        System.out.println("combined predicate accepts normalized: " + eligible.test(normalized));
        System.out.println("combined predicate accepts rejected: " + eligible.test(rejected));
        System.out.println("null-safe name predicate: " + nonBlank.test(null));
        System.out.println("later rule skipped: " + (laterRuleCalls.get() == 0));

        check(normalized.customerCode().equals("ACME"), "normalization");
        check(acceptedResult.accepted(), "accepted rule set");
        check(rejectedSummary.equals(
                "rejected: account active (Account is blocked); "
                + "minimum total (Total is below minimum); "
                + "region supported (Region is unsupported)"), "all violations");
        check(eligible.test(normalized) && !eligible.test(rejected), "predicate composition");
        check(!nonBlank.test(null) && nonBlank.test("Java"), "null guard");
        check(blockedRejected && laterRuleCalls.get() == 0, "short circuit");
        System.out.println("all checks passed");
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 8 -encoding UTF-8 RuleDesignDemo.java
java RuleDesignDemo
~~~

**Stdout chính xác:**

~~~text
normalized code: ACME
parsed amount: 120.00
accepted order: accepted
rejected order: rejected: account active (Account is blocked); minimum total (Total is below minimum); region supported (Region is unsupported)
combined predicate accepts normalized: true
combined predicate accepts rejected: false
null-safe name predicate: false
later rule skipped: true
all checks passed
~~~

### Đọc kết quả

1. `String::trim` và Function `andThen` chuẩn hóa ` acme ` thành `ACME`.
2. `BigDecimal::new` parse chuỗi `120.00` thành decimal; không dùng double cho tiền.
3. `Order::blocked` là unbound method reference, sau `negate()` thành điều kiện tài khoản không bị khóa.
4. `by(Order::total, atLeastMinimum)` ghép extractor với predicate kiểm tra ngưỡng.
5. `allowedRegions::contains` là bound method reference dùng tập vùng được phép.
6. RuleSet thu thập cả ba lỗi của input bị từ chối; `Function.andThen` biến Evaluation thành chuỗi giải thích.
7. `Objects::nonNull` kết hợp short-circuit bảo vệ việc gọi trim trên null.
8. Predicate đầu false nên rule instrumented phía sau không chạy; `all checks passed` chỉ in sau các assertion.

`AtomicInteger` trong chương trình chỉ là **test instrumentation** để chứng minh short-circuit. Trong code nghiệp vụ, predicate nên không có side effect.

## 20. Kiểm thử bộ quy tắc

Một rule engine cần test cả rule riêng và cách kết hợp:

- **Atomic rule:** input đạt và không đạt điều kiện.
- **Boundary:** đúng bằng ngưỡng, thấp hơn một đơn vị nhỏ, cao hơn ngưỡng.
- **Null:** input null, field null, extractor trả null.
- **Composition:** and/or/negate cho đúng truth table.
- **Short-circuit:** rule sau không chạy khi rule trước đã quyết định kết quả.
- **Collect-all:** danh sách vi phạm chứa đúng rule fail và đúng thứ tự.
- **Determinism:** cùng input/snapshot cho kết quả như nhau.
- **Exception:** lỗi kỹ thuật được truyền hoặc xử lý theo policy rõ, không âm thầm biến thành false.

Với unit test, có thể truyền predicate lambda đơn giản. Nếu cần chứng minh thứ tự hoặc short-circuit, dùng spy/counter chỉ trong test. Không phụ thuộc identity của lambda hoặc method reference; JLS không bảo đảm mỗi lần đánh giá lambda tạo một object có identity riêng ổn định.

## 21. Những lỗi thường gặp

| Sai lầm | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Dùng `Function<T,Boolean>` cho điều kiện | Sai ý nghĩa, có boxing | Dùng `Predicate<T>` |
| Dùng Predicate để trích xuất field | Chỉ còn true/false, mất giá trị | Dùng `Function<T,R>` |
| Nhét mọi điều kiện vào một lambda dài | Khó test, khó giải thích lỗi | Tách predicate có tên |
| Dùng `and` rồi mong nhận tất cả lỗi | Short-circuit bỏ qua rule sau | Đánh giá từng Rule khi cần collect-all |
| Không hiểu thứ tự short-circuit | Rule sau có thể không được gọi | Đặt thứ tự rõ và giữ predicate thuần |
| Có side effect trong predicate | Kết quả phụ thuộc số lần/thứ tự gọi | Chuyển side effect ra service/use-case |
| Gọi field trên null | `NullPointerException` | Xác định null contract và guard |
| Dùng method reference overload mơ hồ | Compile error hoặc chọn overload ngoài ý muốn | Khai báo target type/lambda rõ |
| Dùng `Predicate.not` trong code Java 8 | Không có method ở Java 8 | Dùng `negate()` |
| Dùng `Stream.toList()` trong code Java 8 | API mới hơn | Dùng `collect(Collectors.toList())` |
| Dùng `Predicate<Integer>` cho xử lý số không cần boxing | Boxing/unboxing | Cân nhắc `IntPredicate` |
| Function trả null không có contract | NPE xuất hiện ở rule sau | Quy định null/Optional rõ |
| Bắt mọi exception rồi trả false | Che lỗi hệ thống thành lỗi nghiệp vụ | Phân loại exception |
| Sắp xếp rule không ổn định | Message/test đổi thứ tự | Dùng danh sách có thứ tự rõ |
| Tạo framework rule quá sớm | Tăng abstraction và khó debug | Bắt đầu bằng functional interface chuẩn |
| Dùng method reference chỉ để code ngắn | Che ý nghĩa hoặc overload | Chọn lambda khi dễ đọc hơn |

## 22. Checklist code review

- [ ] Mỗi điều kiện có Predicate riêng và tên phản ánh nghiệp vụ?
- [ ] Function chỉ đảm nhiệm trích xuất/biến đổi đúng một giá trị?
- [ ] Method reference có target type rõ và không bị overload mơ hồ?
- [ ] Rule được kết hợp bằng and/or/negate theo đúng truth table?
- [ ] Đã quyết định fail-fast hay collect-all?
- [ ] Thứ tự rule ổn định và có chủ đích?
- [ ] Null contract của input/field/extractor đã rõ?
- [ ] Predicate không ghi DB, gửi network, tăng metric hoặc mutate object?
- [ ] Exception kỹ thuật không bị âm thầm đổi thành rule false?
- [ ] Function composition có đúng hướng compose/andThen?
- [ ] Generic wildcard chỉ dùng ở ranh giới API có lợi?
- [ ] Có primitive-specialized interface khi cần tránh boxing?
- [ ] Không dùng API có version cao hơn target runtime mà không ghi rõ?
- [ ] Có test boundary, null, composition, short-circuit và collect-all?
- [ ] RuleSet không gánh thay trách nhiệm persistence/notification?

**Kết luận:** Thiết kế bộ quy tắc dễ bảo trì bằng cách dùng `Predicate` cho điều kiện, `Function` cho trích xuất/biến đổi và method reference cho method có chữ ký phù hợp. Đặt tên từng rule, kết hợp bằng `and/or/negate` khi cần quyết định nhanh, hoặc đánh giá từng rule riêng khi cần báo tất cả lỗi. Giữ predicate thuần, xác định null/exception/order rõ ràng và kiểm thử cả biên lẫn short-circuit. Các functional interface này có từ Java 8 và vẫn là nền tảng của Collections, Stream và nhiều API JDK hiện đại.

### Tài liệu chính thức đang được duy trì

- [`java.util.function` — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/function/package-summary.html): functional interfaces, lambda/method reference target types và các dạng Function/Predicate.
- [`Predicate<T>` — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/function/Predicate.html): `test`, `and`, `or`, `negate`, `isEqual` và `not`.
- [`Function<T,R>` — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/function/Function.html): `apply`, `compose`, `andThen` và `identity`.
- [`UnaryOperator<T>` — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/function/UnaryOperator.html): function có input/output cùng kiểu.
- [Java Language Specification, Chapter 15 — Expressions](https://docs.oracle.com/en/java/javase/26/docs/specs/jls/jls-15.html): target typing, lambda expressions, method references và overload resolution.
- [`Stream` — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/Stream.html): `filter`, `map`, matching operations và pipeline.