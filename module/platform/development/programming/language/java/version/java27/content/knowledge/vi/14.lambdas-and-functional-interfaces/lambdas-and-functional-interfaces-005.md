# Kết hợp hàm, comparator và kiểm soát tác dụng phụ

## 1. Từ lambda riêng lẻ đến pipeline có hợp đồng rõ ràng

Trong Java 27, lambda và functional interface giúp chuyển một hành vi thành giá trị: có thể truyền hàm vào phương thức khác, kết hợp nhiều hàm nhỏ thành quy trình lớn hơn hoặc khai báo chính sách sắp xếp dữ liệu mà không phải tạo một class cho mỗi biến thể.

Chủ đề này có ba phần liên hệ chặt chẽ:

1. **Kết hợp hàm (function composition)**: nối các bước biến đổi hoặc kiểm tra theo thứ tự có kiểm soát.
2. **Comparator**: khai báo quan hệ thứ tự, kết hợp nhiều tiêu chí và bảo đảm kết quả so sánh nhất quán.
3. **Kiểm soát tác dụng phụ (side effects)**: tách phép tính dữ liệu khỏi ghi log, cập nhật trạng thái, I/O và tương tác hệ thống ngoài để mã dễ kiểm thử và an toàn hơn.

Các API được dùng trong bài, như **Function.compose**, **Function.andThen**, **Predicate.and/or/negate**, **Comparator.comparing/thenComparing** và các primitive functional interfaces, đều là API chính thức, tiếp tục áp dụng trong Java 27; không cần dùng preview hoặc cơ chế lập trình lỗi thời.

~~~mermaid
flowchart LR
    I["Input"] --> V["Validation: Predicate"]
    V --> T["Transformation: Function"]
    T --> O["Ordering: Comparator"]
    O --> R["Result"]
    R --> S["Boundary: Consumer / repository / I-O"]
~~~

Ý tưởng thực hành: phép kiểm tra, biến đổi và sắp xếp nên có đầu vào/đầu ra rõ ràng; phần có tác dụng phụ được đưa về ranh giới xử lý, nơi chương trình kiểm soát thời điểm thực thi và cách xử lý lỗi.

## 2. Những functional interface thường gặp

Functional interface là interface có **một phương thức abstract** phù hợp làm mục tiêu cho lambda hoặc method reference. Nó có thể có thêm default, static và private methods mà không mất tính chất functional interface. Chú thích **@FunctionalInterface** không bắt buộc nhưng giúp trình biên dịch kiểm tra chủ ý của người viết.

| Interface | Phương thức abstract | Ý nghĩa |
|---|---|---|
| **Function<T, R>** | **R apply(T t)** | Chuyển một giá trị T thành R |
| **UnaryOperator<T>** | **T apply(T t)** | Biến đổi nhưng giữ nguyên kiểu |
| **BiFunction<T, U, R>** | **R apply(T t, U u)** | Kết hợp hai đầu vào |
| **BinaryOperator<T>** | **T apply(T a, T b)** | Kết hợp hai giá trị cùng kiểu |
| **Predicate<T>** | **boolean test(T t)** | Kiểm tra điều kiện |
| **Consumer<T>** | **void accept(T t)** | Nhận dữ liệu và thực hiện hành động |
| **Supplier<T>** | **T get()** | Cung cấp một giá trị khi được gọi |
| **Comparator<T>** | **int compare(T a, T b)** | Xác định thứ tự giữa hai giá trị |

Ví dụ nhanh:

~~~java
import java.util.function.*;

Function<String, Integer> length = String::length;
Predicate<String> nonBlank = text -> text != null && !text.isBlank();
Consumer<String> output = System.out::println;
Supplier<String> fallback = () -> "unknown";

System.out.println(length.apply("Java")); // 4
System.out.println(nonBlank.test("Java")); // true
output.accept(fallback.get());             // unknown
~~~

Chọn interface theo **hợp đồng của hành vi**, không theo việc lambda ngắn hay dài. Một **Function** có thể gây tác dụng phụ về mặt ngôn ngữ, nhưng nếu phần còn lại của hệ thống dựa vào tính thuần khiết, hãy quy định và thực thi quy ước đó. Ngược lại, **Consumer** thường diễn đạt một hành động gây tác dụng phụ, nhưng tên interface cũng không tự bảo đảm điều gì về an toàn đa luồng.

## 3. Kết hợp Function bằng andThen và compose

**Function<T,R>** cung cấp hai phương thức mặc định quan trọng:

- **f.andThen(g)**: áp dụng **f** trước, sau đó áp dụng **g** lên kết quả của f.
- **f.compose(g)**: áp dụng **g** trước, sau đó áp dụng **f** lên kết quả của g.

Nếu ký hiệu hàm theo toán học thì:

~~~text
f.andThen(g) = g(f(x))
f.compose(g) = f(g(x))
~~~

Ví dụ chuẩn hóa một chuỗi rồi lấy độ dài:

~~~java
import java.util.Locale;
import java.util.function.Function;

Function<String, String> trim = String::strip;
Function<String, String> lowercase =
    text -> text.toLowerCase(Locale.ROOT);
Function<String, Integer> length = String::length;

Function<String, String> normalize = trim.andThen(lowercase);
Function<String, Integer> normalizedLength = normalize.andThen(length);

System.out.println(normalize.apply("  JAVA  "));      // java
System.out.println(normalizedLength.apply("  JAVA  ")); // 4
~~~

Viết tương đương bằng **compose**:

~~~java
Function<String, Integer> sameLength =
    length.compose(normalize);

System.out.println(sameLength.apply("  JAVA  ")); // 4
~~~

**andThen** thường thuận tiện khi muốn đọc pipeline từ trái sang phải: *strip → lowercase → length*. **compose** hữu ích khi có một hàm đầu ra và muốn tiền xử lý dữ liệu trước khi gọi hàm đó.

Điều kiện quan trọng nhất để kết hợp là **kiểu trả về của bước trước phải tương thích với kiểu đầu vào của bước sau**. Trong ví dụ, normalize trả String nên có thể nối với length nhận String. Không thể nối trực tiếp một bước trả Integer vào một hàm chỉ nhận String.

## 4. Thứ tự biến đổi có thể thay đổi kết quả

Kết hợp hàm không có nghĩa các bước có thể đổi vị trí tùy ý. Ví dụ, **strip()** trước hay sau **replace(...)** có thể tạo kết quả khác nhau; chia hoặc làm tròn trước/sau phép cộng cũng có thể khác nhau.

~~~java
import java.util.function.UnaryOperator;

UnaryOperator<String> addSuffix = text -> text + "!";
UnaryOperator<String> strip = String::strip;

String first = strip.andThen(addSuffix).apply("  ok  ");
String second = addSuffix.andThen(strip).apply("  ok  ");

System.out.println("[" + first + "]");  // [ok!]
System.out.println("[" + second + "]"); // [ok  !]
~~~

Pipeline nên phản ánh đúng thứ tự nghiệp vụ. Đặt tên có ý nghĩa cho các bước như **validate**, **normalize**, **enrich**, **format** giúp người đọc hiểu thứ tự hơn là dùng nhiều lambda ẩn danh trong một biểu thức quá dài.

Hãy giữ các phép biến đổi dữ liệu càng thuần khiết càng tốt. Nếu **normalize** vừa sửa một đối tượng bên ngoài vừa tạo String, việc đổi thứ tự trong pipeline có thể gây lỗi khó tái hiện.

## 5. Function.identity, UnaryOperator và BiFunction

**Function.identity()** trả một hàm giữ nguyên giá trị đầu vào:

~~~java
import java.util.function.Function;

Function<String, String> identity = Function.identity();
System.out.println(identity.apply("Java 27")); // Java 27
~~~

Nó hữu ích khi một API cần Function nhưng ứng dụng muốn giữ nguyên giá trị hoặc để chọn một chiến lược biến đổi mặc định.

**UnaryOperator<T>** là chuyên biệt của Function<T,T>; **BinaryOperator<T>** là chuyên biệt của BiFunction<T,T,T>.

~~~java
import java.util.function.BinaryOperator;
import java.util.function.UnaryOperator;

UnaryOperator<Integer> doubleIt = n -> n * 2;
UnaryOperator<Integer> plusOne = n -> n + 1;

int result = doubleIt.andThen(plusOne).apply(5);
System.out.println(result); // 11

BinaryOperator<Integer> max = Integer::max;
System.out.println(max.apply(7, 9)); // 9
~~~

Khi gọi **andThen** trên UnaryOperator, kiểu phương thức kế thừa từ Function có thể là **Function**, không phải lúc nào cũng giữ được kiểu khai báo UnaryOperator của biến kết quả. Vì vậy, nếu muốn gán pipeline, hãy chọn kiểu đích phù hợp:

~~~java
Function<Integer, Integer> pipeline =
    doubleIt.andThen(plusOne);
~~~

**BiFunction<T,U,R>** xử lý hai đầu vào; phương thức **andThen** của nó áp dụng Function vào kết quả sau cùng:

~~~java
import java.math.BigDecimal;
import java.util.function.BiFunction;

BiFunction<BigDecimal, BigDecimal, BigDecimal> subtotal =
    BigDecimal::multiply;

BiFunction<BigDecimal, BigDecimal, String> display =
    subtotal.andThen(value -> value.toPlainString() + " VND");

System.out.println(
    display.apply(new BigDecimal("10.50"), new BigDecimal("3"))
); // 31.50 VND
~~~

Không phải functional interface nào cũng cung cấp **compose/andThen**. Chẳng hạn Supplier không có phương thức compose được định nghĩa sẵn; nếu cần, có thể ghép kết quả Supplier vào Function bằng lambda rõ ràng:

~~~java
Supplier<String> source = () -> "  value  ";
Function<String, String> normalizeText = String::strip;
Supplier<String> normalizedSource =
    () -> normalizeText.apply(source.get());
~~~

## 6. Kết hợp điều kiện với Predicate

**Predicate<T>** mô tả một điều kiện trả về boolean. Các default methods **and**, **or** và **negate** cho phép kết hợp các điều kiện; phương thức tĩnh **Predicate.not** hỗ trợ đảo điều kiện bằng biểu thức method reference thuận tiện.

~~~java
import java.util.function.Predicate;

Predicate<String> nonNull = value -> value != null;
Predicate<String> notBlank = value -> !value.isBlank();
Predicate<String> shortName = value -> value.length() <= 20;

Predicate<String> valid =
    nonNull.and(notBlank).and(shortName);

System.out.println(valid.test("Ada")); // true
System.out.println(valid.test(""));    // false
System.out.println(valid.test(null));  // false
~~~

**Predicate.and** và **Predicate.or** áp dụng **short-circuit evaluation** theo thứ tự:

- Với **p.and(q)**, nếu p trả false thì q không được gọi.
- Với **p.or(q)**, nếu p trả true thì q không được gọi.
- Với **p.negate()**, kết quả của p được đảo ngược.

Vì vậy, điều kiện kiểm tra null cần đứng trước điều kiện truy cập phương thức:

~~~java
Predicate<String> safe =
    ((Predicate<String>) (text -> text != null))
        .and(text -> !text.isBlank());
~~~

Có thể dùng **Predicate.not** khi lọc danh sách:

~~~java
import java.util.List;
import java.util.function.Predicate;

List<String> cleaned = List.of("A", "", "B", " ")
    .stream()
    .filter(Predicate.not(String::isBlank))
    .toList();

System.out.println(cleaned); // [A, B]
~~~

**Không đưa tác dụng phụ vào Predicate** chỉ để lợi dụng thứ tự gọi. Việc đếm số lần gọi, ghi audit hoặc trừ tiền ngay trong **test** sẽ khiến hành vi thay đổi khi pipeline bị tái cấu trúc, short-circuit hoặc thực thi song song.

## 7. Phân biệt Predicate với kiểm tra nghiệp vụ có lỗi

Một Predicate thường thích hợp để diễn đạt **đúng/sai**. Nhưng nếu caller cần biết *vì sao* dữ liệu không hợp lệ, nên cân nhắc một kiểu kết quả rõ ràng, thay vì ghép nhiều predicate rồi đánh mất lý do thất bại.

~~~java
record ValidationResult(boolean valid, String reason) {}

static ValidationResult validateEmail(String email) {
    if (email == null) {
        return new ValidationResult(false, "Email is required");
    }
    if (email.isBlank()) {
        return new ValidationResult(false, "Email must not be blank");
    }
    if (!email.contains("@")) {
        return new ValidationResult(false, "Email is not well formed");
    }
    return new ValidationResult(true, "");
}
~~~

Ví dụ chỉ minh họa việc trả lỗi có cấu trúc; **contains("@")** không phải trình xác thực địa chỉ email đầy đủ. Với dữ liệu nghiệp vụ, nên viết quy tắc xác thực tương ứng với hợp đồng thực tế thay vì xem một Predicate ngắn như toàn bộ chính sách.

Một cách thiết kế tốt là dùng **Predicate** cho phép lọc đơn giản, còn thao tác cần thông báo lỗi hoặc thay đổi trạng thái sử dụng phương thức nghiệp vụ có kết quả cụ thể.

## 8. Consumer.andThen: phối hợp hành động có tác dụng phụ

Khác với Function, **Consumer<T>** trả về void. Nó thường dùng cho log, gửi thông báo, cập nhật trạng thái, ghi dữ liệu hoặc phản ứng với sự kiện.

**Consumer.andThen** gọi hành động thứ nhất rồi đến hành động thứ hai khi hành động thứ nhất kết thúc bình thường:

~~~java
import java.util.function.Consumer;

Consumer<String> audit = message ->
    System.out.println("AUDIT: " + message);

Consumer<String> notify = message ->
    System.out.println("NOTIFY: " + message);

Consumer<String> both = audit.andThen(notify);
both.accept("order-42");
~~~

Kết quả:

~~~text
AUDIT: order-42
NOTIFY: order-42
~~~

**Điểm khác biệt so với Predicate.and:** Consumer không có khái niệm short-circuit dựa trên true/false. Nếu consumer đầu tiên ném ngoại lệ, consumer thứ hai không được gọi; nếu consumer đầu tiên thành công, consumer thứ hai được gọi.

Việc ghép hai Consumer không tạo transaction. Nếu bước **audit** đã ghi ra bên ngoài nhưng bước **notify** thất bại, không có cơ chế rollback tự động. Với nghiệp vụ cần bảo đảm atomicity, retry hoặc gửi thông điệp tin cậy, hãy thiết kế transaction/outbox/workflow rõ ràng thay vì chỉ dùng **andThen**.

## 9. Primitive functional interfaces tránh boxing không cần thiết

Với pipeline tính toán số lượng lớn, generic functional interfaces có thể dẫn đến boxing/unboxing. Java cung cấp các phiên bản dùng kiểu nguyên thủy như **IntPredicate**, **IntFunction**, **ToIntFunction**, **IntUnaryOperator**, **LongUnaryOperator**, **DoubleUnaryOperator** và **IntConsumer**.

~~~java
import java.util.function.IntPredicate;
import java.util.function.IntUnaryOperator;

IntUnaryOperator doubleIt = value -> value * 2;
IntUnaryOperator plusOne = value -> value + 1;

IntUnaryOperator transform = doubleIt.andThen(plusOne);

System.out.println(transform.applyAsInt(5)); // 11

IntPredicate positive = value -> value > 0;
IntPredicate even = value -> value % 2 == 0;

System.out.println(positive.and(even).test(8)); // true
~~~

Khi sắp xếp đối tượng theo khóa nguyên thủy, **Comparator.comparingInt**, **comparingLong** và **comparingDouble** giúp tránh tạo đối tượng bao không cần thiết cho mỗi khóa.

Primitive specialization là công cụ tối ưu có ý nghĩa khi có dữ liệu đủ lớn hoặc đường xử lý nhạy hiệu năng. Với logic nghiệp vụ thông thường, ưu tiên API diễn đạt rõ mục đích; tối ưu khi có lý do đo lường.

## 10. Comparator mô tả thứ tự

**Comparator<T>** cung cấp phương thức **compare(a,b)** để quyết định thứ tự:

- Kết quả **nhỏ hơn 0**: a đứng trước b.
- Kết quả **bằng 0**: a và b được coi là tương đương theo thứ tự của Comparator.
- Kết quả **lớn hơn 0**: a đứng sau b.

Không cần trả đúng -1, 0 hoặc 1; chỉ dấu của kết quả quan trọng. Nhưng cài đặt Comparator phải tuân thủ các quy tắc đối xứng dấu, bắc cầu và nhất quán của quan hệ so sánh.

Ví dụ sắp xếp số:

~~~java
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;

List<Integer> scores = new ArrayList<>(List.of(30, 10, 20));

scores.sort(Comparator.naturalOrder());
System.out.println(scores); // [10, 20, 30]

scores.sort(Comparator.reverseOrder());
System.out.println(scores); // [30, 20, 10]
~~~

Nên dùng **Comparator.comparing(...)** và các phương thức kết hợp thay vì viết chuỗi if-else dài bên trong lambda so sánh. Đối với các kiểu đã có thứ tự tự nhiên, **Comparator.naturalOrder()** hoặc **reverseOrder()** thể hiện rõ chủ ý.

**Không trừ hai số nguyên để làm Comparator:** viết **a - b** có thể tràn số và phá hợp đồng. Hãy dùng **Integer.compare(a,b)** hoặc **Comparator.comparingInt**.

## 11. Comparator.comparing và trích xuất khóa

**Comparator.comparing(keyExtractor)** xây dựng Comparator dựa trên một khóa được trích xuất từ đối tượng. Khóa phải có thứ tự tự nhiên, hoặc bạn phải truyền Comparator phù hợp với kiểu khóa.

~~~java
import java.time.LocalDate;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;

record Task(String id, int priority, LocalDate dueDate) {}

List<Task> tasks = new ArrayList<>(List.of(
    new Task("A", 2, LocalDate.parse("2026-12-01")),
    new Task("B", 5, LocalDate.parse("2026-11-29")),
    new Task("C", 3, LocalDate.parse("2026-11-30"))
));

tasks.sort(Comparator.comparing(Task::dueDate));

System.out.println(tasks.stream().map(Task::id).toList());
// [B, C, A]
~~~

Nếu khóa là int, nên dùng phương thức chuyên biệt:

~~~java
Comparator<Task> byPriority =
    Comparator.comparingInt(Task::priority);
~~~

Mặc định comparator này sắp từ priority nhỏ đến lớn. Nếu quy tắc nghiệp vụ nói priority cao hơn phải đứng trước, đảo chiều một cách tường minh:

~~~java
Comparator<Task> highFirst =
    Comparator.comparingInt(Task::priority).reversed();
~~~

Điểm đáng chú ý: **reversed()** không chỉ thay đổi cách hiển thị. Nó thay đổi quan hệ thứ tự của Comparator, nên phải đặt đúng vị trí khi kết hợp nhiều tiêu chí.

## 12. Kết hợp nhiều tiêu chí với thenComparing

Nhiều nghiệp vụ cần thứ tự đa cấp: ưu tiên cao trước, hạn xử lý sớm trước, mã định danh tăng dần để phá thế hòa (*tie-breaker*).

~~~java
Comparator<Task> order =
    Comparator.comparingInt(Task::priority).reversed()
        .thenComparing(Task::dueDate)
        .thenComparing(Task::id);

tasks.sort(order);
~~~

Diễn giải:

1. So sánh theo priority giảm dần.
2. Nếu priority bằng nhau, so sánh dueDate tăng dần.
3. Nếu vẫn bằng nhau, so sánh id tăng dần.

~~~java
List<Task> input = new ArrayList<>(List.of(
    new Task("T-03", 5, LocalDate.parse("2026-12-01")),
    new Task("T-01", 5, LocalDate.parse("2026-11-30")),
    new Task("T-02", 5, LocalDate.parse("2026-11-30")),
    new Task("T-04", 3, LocalDate.parse("2026-11-29"))
));

input.sort(order);

System.out.println(input.stream().map(Task::id).toList());
// [T-01, T-02, T-03, T-04]
~~~

**Lưu ý về vị trí reversed():** Viết **base.thenComparing(other).reversed()** sẽ đảo **toàn bộ** quan hệ thứ tự, cả tiêu chí phụ. Nếu chỉ muốn đảo priority, hãy đảo comparator priority **trước khi** thêm **thenComparing**, như ví dụ trên.

Một Comparator có tie-breaker ổn định đặc biệt quan trọng khi dữ liệu được xuất ra file, phân trang hoặc so sánh snapshot. Nếu các phần tử khác nhau vẫn có compare bằng 0, thứ tự tương đối có thể phụ thuộc vào encounter order của nguồn.

## 13. So sánh String có quy tắc locale phù hợp

So sánh theo thứ tự tự nhiên của **String** dựa trên giá trị từ điển theo các đơn vị mã UTF-16, **không phải** thứ tự từ vựng phù hợp với mọi ngôn ngữ.

~~~java
Comparator<String> lexical = Comparator.naturalOrder();
Comparator<String> insensitive = String.CASE_INSENSITIVE_ORDER;
~~~

Nếu giao diện cần sắp xếp tên tiếng Việt theo quy tắc ngôn ngữ cụ thể, dùng **java.text.Collator** được cấu hình theo locale thích hợp:

~~~java
import java.text.Collator;
import java.util.Comparator;
import java.util.Locale;

Collator viCollator = Collator.getInstance(Locale.forLanguageTag("vi-VN"));

Comparator<String> vietnameseNames = viCollator::compare;
~~~

**Collator** có thể có cấu hình strength/decomposition và không được tự động coi là thread-safe khi dùng chung instance có trạng thái mutable. Nếu nhiều thread cần sắp xếp đồng thời, hãy đảm bảo chiến lược tạo hoặc bảo vệ Collator phù hợp.

Cần phân biệt **key kỹ thuật** với **text hiển thị**. Với mã sản phẩm, ID hoặc dữ liệu cần tính determinism giữa các hệ thống, thường nên định nghĩa thứ tự ổn định độc lập locale. Với danh sách tên hiển thị, thứ tự theo locale có thể giúp trải nghiệm người dùng hợp lý hơn.

## 14. Xử lý null bằng nullsFirst và nullsLast

**Comparator.comparing** với khóa null và Comparator tự nhiên có thể ném NullPointerException. Nếu dữ liệu cho phép null, hãy xác định chính sách thay vì dựa vào may mắn:

~~~java
import java.util.Comparator;

record Person(String id, String displayName) {}

Comparator<Person> byName =
    Comparator.comparing(
        Person::displayName,
        Comparator.nullsLast(String.CASE_INSENSITIVE_ORDER)
    ).thenComparing(Person::id);
~~~

Ở đây, **displayName == null** sẽ được xếp sau các tên không null. Comparator phụ **Person::id** dùng khi hai giá trị tên được so sánh là tương đương.

Cần phân biệt hai mức null:

- **null là chính đối tượng Person**: cần bọc toàn bộ Comparator.
- **Person khác null nhưng displayName null**: cần Comparator cho khóa như ví dụ trên.

~~~java
Comparator<Person> nullablePeople =
    Comparator.nullsLast(byName);
~~~

**Comparator.nullsFirst(...)** đưa null lên đầu; **nullsLast(...)** đưa null xuống cuối. Không nhất thiết dùng nullsFirst/nullsLast cho tất cả trường: nếu null vi phạm bất biến dữ liệu, nên từ chối nó sớm thay vì âm thầm sắp xếp.

Khi dùng **reversed()**, cũng cần kiểm tra lại thứ tự mong muốn của null vì đảo toàn bộ Comparator sẽ đảo thứ tự của các giá trị null. Có thể xây dựng comparator riêng cho phần khóa nếu muốn priority giảm dần nhưng null vẫn cố định ở cuối.

## 15. Hợp đồng Comparator và dữ liệu dùng trong Set/Map

Một comparator hợp lệ cần có quan hệ thứ tự nhất quán:

- **Đối xứng dấu:** dấu của compare(a,b) đối nghịch với dấu của compare(b,a).
- **Bắc cầu:** nếu a đứng trước b và b đứng trước c thì a phải đứng trước c.
- **Tương đương theo so sánh:** nếu compare(a,b) == 0, quan hệ so sánh với phần tử thứ ba phải nhất quán.
- **Không phụ thuộc trạng thái bên ngoài đang thay đổi** theo cách làm kết quả cho cùng cặp phần tử thay đổi bất ngờ.

Quan hệ **compare(a,b) == 0** không bắt buộc phải đồng nhất với **a.equals(b)** theo mọi Comparator. Tuy nhiên, điều này ảnh hưởng rõ rệt khi Comparator được dùng làm thứ tự của **TreeSet** hoặc **TreeMap**: chúng xem các phần tử/khóa có compare bằng 0 là tương đương cho mục đích lưu trữ.

~~~java
import java.util.Comparator;
import java.util.Set;
import java.util.TreeSet;

record Product(String id, String name) {}

Set<Product> byNameOnly = new TreeSet<>(
    Comparator.comparing(Product::name)
);

byNameOnly.add(new Product("P-1", "Pen"));
byNameOnly.add(new Product("P-2", "Pen"));

System.out.println(byNameOnly.size()); // 1
~~~

Hai Product có id khác nhau nhưng cùng tên; Comparator dựa riêng vào name xem chúng trùng nhau. Nếu cần cả hai cùng tồn tại, hãy có tie-breaker theo id:

~~~java
Comparator<Product> byNameThenId =
    Comparator.comparing(Product::name)
        .thenComparing(Product::id);
~~~

Với **TreeMap**, tình huống tương tự xảy ra với khóa: hai khóa so sánh bằng 0 có thể dẫn đến ghi đè một ánh xạ dù equals trả false. Do đó, phải thiết kế Comparator dựa trên ngữ nghĩa duy nhất của dữ liệu, không chỉ mục đích “sắp xếp cho đẹp”.

## 16. Sắp xếp List có ổn định; Stream và snapshot

**List.sort(comparator)** là thao tác ổn định (*stable sort*) theo hợp đồng Java: những phần tử được Comparator xem là tương đương giữ thứ tự tương đối ban đầu.

~~~java
record Event(String id, int group) {}

List<Event> events = new java.util.ArrayList<>(List.of(
    new Event("a", 2),
    new Event("b", 1),
    new Event("c", 2)
));

events.sort(Comparator.comparingInt(Event::group));

System.out.println(events.stream().map(Event::id).toList());
// [b, a, c]
~~~

Nếu không muốn sửa List đầu vào, dùng stream:

~~~java
List<Event> sortedSnapshot = events.stream()
    .sorted(Comparator.comparingInt(Event::group))
    .toList();
~~~

**Stream.toList()** tạo danh sách unmodifiable; kết quả không phải là một danh sách mutable để có thể add/remove tùy ý. Với ordered stream, **Stream.sorted** cũng có tính ổn định; với unordered stream, không được đảm bảo ổn định.

Nếu cần danh sách có thể sửa sau khi sắp, tạo bản sao mutable:

~~~java
List<Event> editable = new java.util.ArrayList<>(events);
editable.sort(Comparator.comparingInt(Event::group));
~~~

**Không nên biến một Comparator thành phép ghi trạng thái** để “ghi log mỗi lần so sánh”. Thuật toán sắp xếp có thể gọi comparator nhiều lần, với thứ tự không cố định; nếu comparator có side effect, kết quả/chi phí và log sẽ khó dự đoán.

## 17. Hàm thuần khiết và tác dụng phụ

Một hàm được xem là **thuần khiết (pure)** trong nghĩa thực dụng khi:

1. Với cùng đầu vào, nó tạo cùng đầu ra (bỏ qua các yếu tố không liên quan đến dữ liệu).
2. Nó không làm thay đổi trạng thái có thể quan sát từ bên ngoài.

Ví dụ thuần khiết:

~~~java
record Price(java.math.BigDecimal amount) {}

Function<Price, Price> withTax = price ->
    new Price(price.amount().multiply(new java.math.BigDecimal("1.08")));
~~~

Hàm tạo giá trị mới và không sửa Price đầu vào. **BigDecimal** cũng là immutable. Ngược lại, ví dụ có tác dụng phụ:

~~~java
List<String> auditLog = new java.util.ArrayList<>();

Function<String, String> impure = value -> {
    auditLog.add("processed " + value);
    return value.strip();
};
~~~

Hàm **impure** làm thay đổi một List ở bên ngoài. Khi chạy nhiều lần, thử lại, tái cấu trúc stream hoặc chạy song song, số lần ghi và thứ tự ghi có thể thay đổi.

Các tác dụng phụ không chỉ là ghi file hoặc gọi API: chúng còn gồm sửa field, thay đổi List/Map, tăng bộ đếm, đọc thời gian hiện tại, sinh số ngẫu nhiên, truy cập trạng thái toàn cục hoặc đọc một nguồn dữ liệu mutable có thể thay đổi theo lúc gọi.

**Thiết kế gợi ý:** dùng Function và Predicate cho phép tính/điều kiện có hợp đồng xác định; gom I/O, log và cập nhật dữ liệu vào các phương thức có ranh giới rõ ràng. Không phải mọi ứng dụng Java đều cần “thuần khiết hoàn toàn”; mục tiêu là làm tác dụng phụ **tường minh và kiểm soát được**.

## 18. Captured variables và effectively final

Lambda trong Java có thể sử dụng biến cục bộ từ phạm vi bao ngoài nếu biến đó là **final** hoặc **effectively final** (được gán một lần theo quy tắc ngôn ngữ).

~~~java
int threshold = 10;
Predicate<Integer> above = number -> number > threshold;

// threshold = 20; // Không hợp lệ nếu lambda đang capture threshold
System.out.println(above.test(12)); // true
~~~

Quy tắc effectively final áp dụng cho **biến tham chiếu cục bộ**, không tự làm đối tượng mà biến trỏ tới trở thành bất biến:

~~~java
List<String> results = new java.util.ArrayList<>();

Consumer<String> append = results::add;
append.accept("A");
append.accept("B");

System.out.println(results); // [A, B]
~~~

Đoạn code trên hợp lệ, nhưng **results** vẫn là một List mutable. Nếu lambda bị chia sẻ giữa nhiều thread, việc cùng sửa ArrayList có thể gây data race; effectively final không cung cấp synchronization hoặc atomicity.

Một nguyên tắc thực hành: hạn chế capture mutable state trong hàm dùng cho parallel stream, listener chạy đồng thời hoặc callback không có vòng đời rõ ràng.

## 19. Side effects trong Stream và short-circuit operations

Stream API thường được dùng với Function, Predicate và Consumer. Các phép trung gian như **map**, **filter**, **sorted** tạo pipeline; thao tác terminal như **toList**, **collect**, **forEach**, **count**, **findFirst** kích hoạt việc xử lý theo quy tắc của stream.

~~~java
List<String> names = List.of("An", "Binh", "Anh", "Lan");

List<String> selected = names.stream()
    .map(String::strip)
    .filter(name -> name.startsWith("A"))
    .sorted()
    .toList();

System.out.println(selected); // [An, Anh]
~~~

Trong pipeline trên, map/filter là những phép biến đổi và kiểm tra không gây tác dụng phụ. Nếu thay filter bằng lambda vừa lọc vừa cập nhật biến ngoài, kết quả có thể khó hiểu khi pipeline bị đổi cách thực thi.

**Không giả định một lambda trong stream sẽ được gọi đúng một lần cho mỗi phần tử** trong mọi pipeline. Các phép tối ưu hóa có thể bỏ qua những giai đoạn không cần thiết để tạo kết quả terminal; các thao tác short-circuit như **anyMatch**, **findFirst**, **limit** có thể dừng sớm.

Ví dụ:

~~~java
boolean hasBlank = names.stream()
    .anyMatch(String::isBlank);
~~~

Không nên viết logic ghi audit bắt buộc trong **map** hoặc **filter** rồi mong mọi phần tử đều được ghi. Nếu muốn thực hiện một hành động cho kết quả cuối cùng, hãy đặt nó **sau** khi pipeline hoàn thành.

**Stream.peek** phù hợp cho quan sát/debug ở một số tình huống, nhưng không nên dùng để đặt tác dụng phụ bắt buộc: thao tác có thể không được thực thi cho mọi phần tử, tùy terminal operation và tối ưu hóa.

## 20. Tác dụng phụ trong parallel stream và an toàn đa luồng

Trong parallel stream, các lambda có thể thực thi trên nhiều thread và không theo thứ tự dự kiến. Mã capture collection mutable không đồng bộ có thể vừa sai vừa khó tái hiện.

Ví dụ **không an toàn**:

~~~java
List<Integer> values = java.util.stream.IntStream
    .range(0, 10_000).boxed().toList();

List<Integer> unsafe = new java.util.ArrayList<>();

// Không dùng: có data race và có thể mất phần tử.
values.parallelStream().forEach(unsafe::add);
~~~

Thay bằng phép thu thập kết quả:

~~~java
List<Integer> safe = values.parallelStream()
    .map(number -> number * 2)
    .toList();

System.out.println(safe.size()); // 10000
~~~

Nếu cần gom vào một Map, dùng **collect** hoặc **Collectors.groupingByConcurrent** khi hợp đồng thứ tự và loại collection đích cho phép. Nếu phải cập nhật metric đồng thời, chọn **LongAdder**, **AtomicLong** hoặc hệ thống metrics thích hợp nhưng vẫn nên tách phần đó khỏi phép toán dữ liệu chính nếu có thể.

Parallel stream không phải lựa chọn mặc định cho mọi pipeline. Nó có overhead, có thể ảnh hưởng throughput của hệ thống dùng chung thread pool và cần phép toán đủ độc lập, đủ lớn để có lợi ích. Hãy đo hiệu năng trong điều kiện thực tế.

## 21. Ngoại lệ và chiến lược khi kết hợp hàm

Các functional interface chuẩn như **Function.apply** và **Predicate.test** không khai báo checked exception. Vì vậy, một lambda gọi API ném IOException trực tiếp sẽ không biên dịch nếu không bắt hoặc chuyển đổi ngoại lệ.

Ví dụ xử lý được kiểm soát:

~~~java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.function.Function;

Function<Path, String> readText = path -> {
    try {
        return Files.readString(path);
    } catch (IOException exception) {
        throw new java.io.UncheckedIOException(
            "Could not read " + path, exception
        );
    }
};
~~~

Không nên gom mọi checked exception thành **RuntimeException** không có thông điệp hoặc ngữ cảnh. Hãy cân nhắc một kết quả có cấu trúc, một phương thức nghiệp vụ có **throws**, hoặc adapter chuyển ngoại lệ phù hợp với hợp đồng API.

Khi dùng **f.andThen(g)**:

- Nếu f ném ngoại lệ, g không được gọi.
- Nếu g ném ngoại lệ, tác dụng phụ đã xảy ra trong f (nếu có) **không được rollback**.
- Nếu dữ liệu cần cập nhật nhiều hệ thống, composition thuần túy không thay thế được transaction hoặc quy trình retry.

Để dễ xử lý lỗi, nên giữ hàm biến đổi thuần khiết, kiểm tra đầu vào sớm và thực hiện cập nhật bên ngoài sau khi đã có một kết quả hợp lệ.

## 22. Ví dụ hoàn chỉnh: lọc, chuẩn hóa, sắp xếp yêu cầu hỗ trợ

Ví dụ sau kết hợp **Function**, **Predicate**, **Comparator** và một **Consumer** ở cuối pipeline. Tất cả dữ liệu xử lý được mô hình hóa bằng record immutable về mặt thành phần; phần sắp xếp không thay đổi đầu vào.

Lưu thành tệp **FunctionalCompositionDemo.java** và chạy bằng JDK 27.

~~~java
import java.time.Instant;
import java.util.Comparator;
import java.util.List;
import java.util.Locale;
import java.util.function.Consumer;
import java.util.function.Function;
import java.util.function.Predicate;

public class FunctionalCompositionDemo {
    record Ticket(
        String id,
        String customer,
        int severity,
        Instant createdAt
    ) {}

    static Function<String, String> customerNormalizer() {
        Function<String, String> strip = String::strip;
        Function<String, String> lowercase =
            value -> value.toLowerCase(Locale.ROOT);
        return strip.andThen(lowercase);
    }

    static Comparator<Ticket> ticketOrder() {
        return Comparator.comparingInt(Ticket::severity)
            .reversed()
            .thenComparing(Ticket::createdAt)
            .thenComparing(Ticket::id);
    }

    static List<Ticket> selectAndOrder(List<Ticket> input) {
        Function<String, String> normalize = customerNormalizer();

        Predicate<Ticket> severe = ticket -> ticket.severity() >= 3;
        Predicate<Ticket> isAnCustomer = ticket ->
            normalize.apply(ticket.customer()).startsWith("an");

        return input.stream()
            .filter(severe.and(isAnCustomer))
            .sorted(ticketOrder())
            .toList();
    }

    public static void main(String[] args) {
        List<Ticket> tickets = List.of(
            new Ticket("T-03", "  AN  ", 5,
                Instant.parse("2026-11-27T12:00:00Z")),
            new Ticket("T-01", "an", 5,
                Instant.parse("2026-11-27T08:00:00Z")),
            new Ticket("T-02", "An", 3,
                Instant.parse("2026-11-27T07:00:00Z")),
            new Ticket("T-04", "binh", 5,
                Instant.parse("2026-11-27T06:00:00Z")),
            new Ticket("T-05", "ANNA", 2,
                Instant.parse("2026-11-27T05:00:00Z"))
        );

        List<Ticket> selected = selectAndOrder(tickets);

        Consumer<Ticket> output = ticket ->
            System.out.println(ticket.id() + " severity=" + ticket.severity());

        // Side effect được thực hiện tường minh sau khi tính toán xong.
        selected.forEach(output);

        System.out.println("Selected: " + selected.size());
        System.out.println("Original: " + tickets.size());
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 FunctionalCompositionDemo.java
java FunctionalCompositionDemo
~~~

Kết quả dự kiến:

~~~text
T-01 severity=5
T-03 severity=5
T-02 severity=3
Selected: 3
Original: 5
~~~

Diễn giải:

1. **customerNormalizer** kết hợp strip và lowercase qua andThen.
2. Predicate **severe** kiểm tra mức ưu tiên; **isAnCustomer** kiểm tra mã khách hàng đã chuẩn hóa.
3. **severe.and(isAnCustomer)** short-circuit: vé có severity dưới 3 không cần gọi bước chuẩn hóa.
4. **sorted(ticketOrder())** sắp severity giảm dần, createdAt tăng dần, id tăng dần.
5. **toList()** tạo kết quả unmodifiable, không sửa List đầu vào.
6. **forEach(output)** chỉ thực hiện tác dụng phụ sau khi đã có kết quả cuối cùng.

Đầu vào ví dụ có customer khác null và createdAt khác null theo quy ước tạo dữ liệu. Nếu dùng dữ liệu thực tế, hãy xác thực những bất biến này trong constructor của record hoặc ngay tại ranh giới nhận dữ liệu. Không nên âm thầm để Comparator hoặc Function ném NullPointerException ở giữa pipeline.

## 23. Kiểm thử các hàm thành phần và Comparator

Khi pipeline được tách thành hàm nhỏ, có thể kiểm thử từng thành phần và cả kết quả tổng thể mà không cần chạy I/O.

Kiểm tra Function:

~~~java
Function<String, String> normalize =
    FunctionalCompositionDemo.customerNormalizer();

if (!"java".equals(normalize.apply("  JAVA "))) {
    throw new AssertionError("Normalization failed");
}
~~~

Kiểm tra thứ tự Comparator:

~~~java
Comparator<FunctionalCompositionDemo.Ticket> comparator =
    FunctionalCompositionDemo.ticketOrder();

var a = new FunctionalCompositionDemo.Ticket(
    "A", "an", 5, java.time.Instant.parse("2026-11-27T08:00:00Z")
);
var b = new FunctionalCompositionDemo.Ticket(
    "B", "an", 3, java.time.Instant.parse("2026-11-27T07:00:00Z")
);

if (comparator.compare(a, b) >= 0) {
    throw new AssertionError("Severity descending order failed");
}
~~~

Ngoài unit test, nên kiểm tra những đặc tính mang tính quy luật của Comparator trên nhiều bộ dữ liệu:

- **compare(x,x) == 0** với cùng đối tượng hợp lệ.
- Dấu của compare(a,b) và compare(b,a) đối nghịch.
- Quan hệ bắc cầu được giữ khi có ba đối tượng.
- Null và tie-breaker được xử lý theo chính sách đã chọn.
- Kết quả sắp xếp không phụ thuộc các tác dụng phụ do Comparator gây ra.

Với hàm thuần khiết, cùng một đầu vào nên cho cùng một kết quả; có thể kiểm tra cả các trường hợp biên và chuỗi trống. Với Consumer có I/O, test bằng fake sink hoặc adapter được inject thay vì kết nối thẳng hệ thống thật trong mọi test.

## 24. Lỗi thường gặp

| Biểu hiện | Nguyên nhân | Cách xử lý |
|---|---|---|
| Kết quả compose khác andThen | Đảo thứ tự áp dụng hàm | Ghi nhớ f.andThen(g) = g(f(x)), f.compose(g) = f(g(x)) |
| Không biên dịch khi nối hai Function | Kiểu trả về/đầu vào không tương thích | Kiểm tra generic parameters T, R và bước chuyển tiếp |
| Predicate thứ hai không được gọi | and/or có short-circuit | Không đặt tác dụng phụ bắt buộc trong predicate |
| Consumer thứ hai không chạy | Consumer đầu ném ngoại lệ | Có error handling rõ ràng; đừng giả định transaction |
| Gán lambda từ local variable đã thay đổi | Captured local variable không effectively final | Tách giá trị final hoặc đổi thiết kế luồng dữ liệu |
| Comparator ném NPE | Khóa hoặc đối tượng có null | Định nghĩa nullsFirst/nullsLast hoặc xác thực đầu vào |
| Sort sai khi đảo chiều | reversed() áp dụng cho toàn bộ comparator chain | Chỉ đảo tiêu chí muốn đảo trước thenComparing |
| Comparator cho kết quả thất thường | Dùng biến mutable, so sánh không bắc cầu hoặc trừ số bị overflow | Dùng comparingInt/Integer.compare và dữ liệu ổn định |
| TreeSet làm mất bản ghi khác ID | Comparator xem hai phần tử bằng nhau khi chỉ một khóa trùng | Thêm tie-breaker phù hợp với ngữ nghĩa duy nhất |
| Parallel stream cho sai số lượng | Lambda sửa ArrayList/HashMap bên ngoài | Dùng collect/toList hoặc concurrent data structure phù hợp |
| forEach/peek không phản ánh mọi bước | Pipeline lazy, short-circuit hoặc tối ưu hóa | Chỉ thực hiện side effect ở ranh giới rõ ràng |
| Locale hiển thị sắp tên bất ngờ | String tự nhiên không phải collator ngôn ngữ | Dùng Collator với Locale thích hợp |
| Checked exception không dùng được trong Function | Phương thức abstract không khai báo checked exception | Bắt và chuyển đổi có ngữ cảnh hoặc đổi hợp đồng xử lý lỗi |

## 25. Bài tập thực hành

**Bài tập 1 — Function composition.** Tạo ba hàm: chuẩn hóa khoảng trắng, chuyển chữ thường với Locale.ROOT và lấy độ dài. Viết hai biểu thức tương đương bằng andThen và compose; kiểm tra với chuỗi có khoảng trắng đầu/cuối.

**Bài tập 2 — Predicate short circuit.** Xây một Predicate nhận String và kiểm tra không null, không blank, chiều dài tối đa 30. Chứng minh điều kiện không null đứng trước giúp tránh NPE. Không dùng side effect để làm logic chính.

**Bài tập 3 — Comparator nhiều cấp.** Có record Employee(id, department, salary, joinedAt). Sắp xếp theo department tăng dần, salary giảm dần trong cùng department, joinedAt tăng dần, id tăng dần. Viết test cho các phần tử trùng khóa chính.

**Bài tập 4 — Xử lý null.** Tạo List<Person> có một Person tên null và một phần tử Person null. Viết Comparator đúng cho cả hai tầng null. Sau đó kiểm tra reversed() ảnh hưởng thế nào đến thứ tự null.

**Bài tập 5 — Không có side effect.** Viết lại một pipeline vừa filter vừa cập nhật List ngoài thành pipeline dùng filter/map/toList. Phần ghi log chạy sau khi kết quả đã được tạo.

**Bài tập 6 — Hợp đồng Comparator.** Tạo TreeSet cho Product(id,name) và Comparator so sánh riêng theo name, quan sát phần tử “mất”. Bổ sung tie-breaker id rồi giải thích sự khác nhau giữa compare == 0 và equals.

**Bài tập 7 — Kiểm thử song song.** Viết xử lý 100.000 số bằng IntStream và IntUnaryOperator, đo phiên bản tuần tự và parallel trong cùng môi trường. Không giả định parallel nhanh hơn; không capture mutable ArrayList dùng chung.

## 26. Checklist thiết kế hàm và comparator trong Java 27

- [ ] Chọn đúng functional interface: Function, Predicate, Consumer, Supplier, Comparator hoặc primitive specialization.
- [ ] Hiểu rõ thứ tự **compose** và **andThen**, cùng điều kiện tương thích kiểu giữa các bước.
- [ ] Đặt tên cho những hàm biến đổi/điều kiện có ý nghĩa nghiệp vụ.
- [ ] Dùng Predicate.and/or/negate với ý thức về short-circuit.
- [ ] Không đặt tác dụng phụ bắt buộc vào Predicate, Comparator, Stream.map/filter/peek.
- [ ] Dùng **Comparator.comparing** hoặc **comparingInt/Long/Double** và **thenComparing** để tạo thứ tự nhiều cấp.
- [ ] Đặt **reversed()** ở đúng cấp tiêu chí cần đảo.
- [ ] Xác định chính sách null cho toàn bộ đối tượng và cho khóa trích xuất.
- [ ] Duy trì hợp đồng Comparator: đối xứng dấu, bắc cầu, tương đương nhất quán.
- [ ] Dùng tie-breaker khi cần thứ tự ổn định hoặc tính duy nhất của TreeSet/TreeMap.
- [ ] Không trừ hai int để viết Comparator.
- [ ] Tách biến đổi thuần khiết khỏi cập nhật dữ liệu, log và I/O.
- [ ] Không suy luận thread safety từ effectively final; kiểm soát mutable captured state.
- [ ] Với parallel stream, ưu tiên collect/toList thay vì sửa collection dùng chung.
- [ ] Có hợp đồng xử lý ngoại lệ, retry và tính nguyên tử khi hành động gây tác dụng phụ.
- [ ] Test các trường hợp null, tie, duplicate, locale, ngoại lệ và thứ tự xử lý.

**Kết luận:** Kết hợp hàm cho phép biểu đạt luồng biến đổi dữ liệu bằng nhiều bước nhỏ, tái sử dụng được. Comparator khai báo thứ tự theo tiêu chí rõ ràng, thay cho logic so sánh khó theo dõi. Khi các phép tính và điều kiện được giữ ổn định, còn tác dụng phụ được đưa về ranh giới có kiểm soát, code Java 27 trở nên dễ đọc, dễ kiểm thử và an toàn hơn trước thay đổi nghiệp vụ hoặc thực thi song song.

## Tài liệu tham khảo

- [Java SE 27 — Function](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/function/Function.html): compose, andThen, identity.
- [Java SE 27 — Predicate](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/function/Predicate.html): and, or, negate, not.
- [Java SE 27 — Consumer](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/function/Consumer.html): accept và andThen.
- [Java SE 27 — BiFunction](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/function/BiFunction.html): hai đầu vào và phép kết hợp sau.
- [Java SE 27 — Comparator](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/Comparator.html): comparing, thenComparing, reversed, nullsFirst/nullsLast và quy tắc comparator.
- [Java SE 27 — Stream](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/stream/Stream.html): pipeline, tính lazy, non-interference, stateless behavior và toList.
- [Java Language Specification 27 — Lambda Expressions](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-15.html#jls-15.27): cú pháp lambda, target typing và capture local variables.
