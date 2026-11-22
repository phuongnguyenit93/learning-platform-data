# Chọn functional interface chuẩn hay tự định nghĩa interface theo nghiệp vụ

Khi truyền lambda hoặc method reference trong Java, câu hỏi thực tế không chỉ là “dùng cú pháp `->` như thế nào?” mà còn là **nên dùng functional interface có sẵn trong JDK hay tạo một interface riêng?** Cả hai lựa chọn đều hợp lệ trong Java hiện đại. Lựa chọn tốt phụ thuộc vào chữ ký phương thức, kiểu trả về, ý nghĩa nghiệp vụ, hợp đồng checked exception và mức độ rõ ràng của API đối với người sử dụng.

**Nguyên tắc nền tảng:** ưu tiên functional interface chuẩn khi nó biểu diễn **đúng hành vi cần truyền** và tên kiểu không làm mất ý nghĩa quan trọng. Tự định nghĩa functional interface khi bạn cần một **hợp đồng chuyên biệt** mà interface chuẩn không diễn đạt đủ rõ, chẳng hạn có tên nghiệp vụ, tham số kiểu primitive đặc biệt, quy tắc checked exception hoặc ràng buộc quan trọng thuộc API. Không cần tạo interface mới chỉ để đổi tên một `Function` trong mọi tình huống.

Bài học tập trung vào quyết định thiết kế, ví dụ sử dụng và các đánh đổi vẫn còn áp dụng với Java 8 trở lên.

## 1. Functional interface là kiểu đích của lambda

Functional interface là interface có **một phương thức trừu tượng** theo quy tắc xác định *single abstract method* (SAM) của Java. Nó có thể có thêm phương thức `default`, `static` và những phương thức có chữ ký tương ứng với `Object` mà không làm mất tính chất functional interface. Annotation `@FunctionalInterface` là cách nên dùng để compiler kiểm tra ý định, dù không bắt buộc để interface được coi là functional.

```java
@FunctionalInterface
interface NameFormatter {
    String format(String rawName);

    default String description() {
        return "Định dạng tên";
    }

    static boolean isValidInput(String rawName) {
        return rawName != null;
    }
}
```

`NameFormatter` vẫn là functional interface vì chỉ `format` là phương thức trừu tượng cần triển khai. Lambda tương thích:

```java
NameFormatter formatter = rawName -> rawName.trim();
String value = formatter.format("  Java  ");
```

Trong đoạn minh họa trên, `value` bằng `"Java"`. Interface được gán cho lambda chính là **kiểu đích** (*target type*), cho compiler biết tham số, kết quả và ngoại lệ được phép.

Đừng tự thêm một phương thức trừu tượng khác vào một interface đang dùng với lambda mà không đánh giá tác động: nếu có hai phương thức trừu tượng độc lập, nó không còn đáp ứng hợp đồng functional interface. Nếu đối tượng thực sự phải thực hiện nhiều trách nhiệm khác nhau, có thể cần một interface thông thường hoặc nhiều interface nhỏ.

## 2. Bắt đầu từ chữ ký và ý nghĩa hành vi

Trước khi chọn interface, trả lời lần lượt:

1. **Có bao nhiêu đầu vào?** Không, một, hai, hay một đối tượng chứa dữ liệu đầu vào phức tạp?
2. **Có cần kết quả không?** Kết quả dạng dữ liệu, cờ `boolean` hay không trả về (`void`)?
3. **Có quan hệ đặc biệt giữa kiểu vào/ra không?** Ví dụ biến đổi `T -> T` thường hợp với `UnaryOperator<T>` hơn `Function<T,T>`.
4. **Đầu vào/đầu ra là primitive?** Dùng các interface chuyên biệt nếu việc tránh boxing có ý nghĩa.
5. **Thân callback có thể ném checked exception không?** Chữ ký `throws` của SAM là ràng buộc thật, không chỉ thông tin tài liệu.
6. **Hành vi có một tên nghiệp vụ rõ ràng cần xuất hiện trong API không?** Ví dụ `ShippingFeePolicy.calculateFee` có thể rõ hơn `BiFunction<Integer,Boolean,Integer>.apply` tại ranh giới public API.

Không có quy tắc “interface chuẩn luôn tốt hơn” hoặc “interface riêng luôn tốt hơn”. Nếu cả hai giải được bài toán, ưu tiên cách giúp **người đọc hiểu hợp đồng** và **người gọi sử dụng an toàn**.

## 3. Những interface chuẩn quan trọng trong JDK

Phần lớn các kiểu dưới đây thuộc `java.util.function`, được giới thiệu từ Java 8 và vẫn sử dụng rộng rãi. `Runnable` thuộc `java.lang`, `Callable` thuộc `java.util.concurrent`, `Comparator` thuộc `java.util`.

| Hành vi | Functional interface | SAM chính | Khi nào chọn |
| --- | --- | --- | --- |
| Không đầu vào, tạo kết quả | `Supplier<T>` | `T get()` | Lazy value, factory, giá trị dự phòng |
| Một đầu vào, biến đổi thành kết quả | `Function<T,R>` | `R apply(T)` | Chuyển đổi, ánh xạ, xử lý dữ liệu |
| Một đầu vào và một đầu ra cùng kiểu | `UnaryOperator<T>` | `T apply(T)` | Chuẩn hóa, cập nhật giá trị cùng kiểu |
| Hai đầu vào, tạo kết quả | `BiFunction<T,U,R>` | `R apply(T,U)` | Kết hợp hai giá trị |
| Hai đầu vào cùng kiểu, kết quả cùng kiểu | `BinaryOperator<T>` | `T apply(T,T)` | Gộp, cộng, chọn max/min cùng kiểu |
| Một đầu vào, không trả kết quả | `Consumer<T>` | `void accept(T)` | Logging, gửi thông báo, hành động phụ |
| Hai đầu vào, không trả kết quả | `BiConsumer<T,U>` | `void accept(T,U)` | Xử lý cặp khóa/giá trị |
| Một đầu vào, trả điều kiện | `Predicate<T>` | `boolean test(T)` | Lọc, xác thực điều kiện, kiểm tra quy tắc |
| Hai đầu vào, trả điều kiện | `BiPredicate<T,U>` | `boolean test(T,U)` | Điều kiện phụ thuộc hai giá trị |
| Không đầu vào, không trả kết quả | `Runnable` | `void run()` | Tác vụ hoặc callback không tạo kết quả |
| Không đầu vào, có kết quả, cho phép checked exception | `Callable<V>` | `V call() throws Exception` | Tác vụ có kết quả khi API nhận Callable |
| So sánh hai đối tượng | `Comparator<T>` | `int compare(T,T)` | Sắp xếp, lựa chọn thứ tự |

Ví dụ cú pháp (đoạn minh họa cần import các interface tương ứng):

```java
Supplier<String> greeting = () -> "Xin chào";
Function<String, Integer> length = String::length;
UnaryOperator<String> trim = String::trim;
BiFunction<Integer, Integer, Integer> sum = (a, b) -> a + b;
BinaryOperator<Integer> larger = Integer::max;
Consumer<String> print = System.out::println;
Predicate<String> nonEmpty = s -> !s.isEmpty();
BiPredicate<String, Integer> atLeast = (s, n) -> s.length() >= n;
Runnable task = () -> System.out.println("Đã chạy");
Comparator<String> byLength = Comparator.comparingInt(String::length);
```

Các đoạn này minh họa lựa chọn theo chữ ký; chương trình hoàn chỉnh ở mục 8.

### 3.1. Chọn interface theo ý định, không chỉ vì các kiểu đều biên dịch

Với biến đổi chuỗi sang chuỗi, `Function<String,String>` có thể chạy đúng. Nhưng `UnaryOperator<String>` biểu đạt trực tiếp “nhận và trả về cùng kiểu”:

```java
UnaryOperator<String> normalize = s -> s.trim().toLowerCase();
```

Với một điều kiện, dùng `Predicate<String>` thay cho `Function<String,Boolean>` nếu đó là phép kiểm tra:

```java
Predicate<String> present = s -> !s.trim().isEmpty();
```

`Predicate.test` cho kết quả primitive `boolean` và có các phép kết hợp `and`, `or`, `negate`. `Function<String,Boolean>` có thể biểu đạt cùng phép tính nhưng không nói rõ đây là một predicate và có thể kéo theo boxing của Boolean.

Với một tác vụ không có kết quả, dùng `Consumer<T>` hoặc `Runnable` thay vì ép hành động vào `Function<T,Void>` rồi trả `null`. Cách dùng `Void` thường khiến chữ ký khó hiểu và kết quả không có ý nghĩa.

### 3.2. Phân biệt `Supplier`, `Runnable` và `Callable`

Cả ba đều có thể dùng lambda không có tham số nhưng có hợp đồng khác nhau:

```java
Supplier<Integer> counter = () -> 10; // Có kết quả; không khai báo checked exception.
Runnable log = () -> System.out.println("Start"); // void.
Callable<Integer> task = () -> 10; // Có kết quả; call() throws Exception.
```

Không thay `Callable` cho `Supplier` chỉ vì thân có I/O, nếu API hiện tại chỉ nhận `Supplier`. Kiểu đích được API quyết định. Khi thiết kế API mới, chọn `Callable` nếu ngữ cảnh là tác vụ và hợp đồng `throws Exception` thực sự phù hợp; nếu cần checked exception chuyên biệt, một interface riêng có thể chính xác hơn.

### 3.3. `Comparator` đã là functional interface

Không cần khai báo một interface `CompareItems` chỉ để truyền quy tắc sắp xếp:

```java
Comparator<String> order =
        Comparator.comparingInt(String::length)
                  .thenComparing(Comparator.naturalOrder());
```

`Comparator` cung cấp nhiều công cụ như `comparing`, `thenComparing`, `reversed`, `nullsFirst` và `nullsLast`. Dù nó có các phương thức khác, hợp đồng SAM dùng cho lambda là `compare`. Các phương thức kế thừa/khai báo tương đương phương thức của `Object` không làm nó mất tính chất functional.

## 4. Primitive-specialized interface: tránh boxing không cần thiết

`Function<Integer,Integer>` có thể dùng trong nhiều trường hợp. Nhưng khi lặp rất nhiều lần trên dữ liệu primitive, auto-boxing/unboxing có thể tạo chi phí không cần thiết. JDK có các interface chuyên biệt:

| Nhu cầu | Kiểu nên cân nhắc | SAM |
| --- | --- | --- |
| `int -> int` | `IntUnaryOperator` | `int applyAsInt(int)` |
| `int,int -> int` | `IntBinaryOperator` | `int applyAsInt(int,int)` |
| `int -> boolean` | `IntPredicate` | `boolean test(int)` |
| `int -> void` | `IntConsumer` | `void accept(int)` |
| `() -> int` | `IntSupplier` | `int getAsInt()` |
| `T -> int` | `ToIntFunction<T>` | `int applyAsInt(T)` |
| `int -> R` | `IntFunction<R>` | `R apply(int)` |
| `T,int -> void` | `ObjIntConsumer<T>` | `void accept(T,int)` |

JDK còn có các họ tương ứng cho `long` và `double`; chọn theo chữ ký thực, không suy đoán rằng mọi tổ hợp kiểu đều có một interface dựng sẵn.

```java
IntUnaryOperator doubleValue = n -> n * 2;
ToIntFunction<String> textLength = String::length;
IntPredicate positive = n -> n > 0;
```

Các interface primitive chuyên biệt dùng được từ Java 8. **Đừng tuyên bố mặc định chúng luôn nhanh hơn trong mọi ứng dụng**: với mã thông thường, trước hết chọn API rõ ràng, còn lợi ích hiệu năng nên đo khi cần.

## 5. Khi nào nên ưu tiên interface chuẩn?

### 5.1. Biến đổi dữ liệu, lọc và xử lý có ngữ nghĩa phổ quát

Stream API là ví dụ điển hình. `map` nhận `Function`, `filter` nhận `Predicate`, `forEach` nhận `Consumer`. Việc dùng các kiểu chuẩn cho phép kết nối trực tiếp với hệ sinh thái JDK:

```java
UnaryOperator<String> normalize =
        s -> s.trim().toLowerCase(Locale.ROOT);
Predicate<String> nonEmpty = s -> !s.isEmpty();

List<String> cleaned = source.stream()
        .map(normalize)
        .filter(nonEmpty)
        .collect(Collectors.toList());
```

Đoạn trên giả định `source` có kiểu `List<String>` và đã import `Locale`, `List`, `Collectors`. Đây là đoạn minh họa, không phải file độc lập.

Không cần một interface `MyMapper` hoặc `MyFilter` có cùng chữ ký, rồi viết adapter chỉ để truyền vào `map` và `filter`. Nếu kiểu riêng không bổ sung thông tin hợp đồng thực sự, nó chỉ làm mã rườm rà.

### 5.2. Muốn dùng phép kết hợp có sẵn

Nhiều interface chuẩn có phương thức `default`/`static` rất hữu ích:

```java
Function<String, String> trim = String::trim;
Function<String, Integer> length = String::length;

Function<String, Integer> normalizedLength =
        trim.andThen(length); // trim trước, length sau.

Predicate<String> hasText = s -> !s.trim().isEmpty();
Predicate<String> shortEnough = s -> s.length() <= 20;
Predicate<String> acceptable = hasText.and(shortEnough);
```

`Function.andThen` thực hiện hàm hiện tại rồi mới áp dụng hàm tiếp theo; `compose` thực hiện hàm được truyền vào trước. `Predicate.and`/`or` sử dụng logic ngắn mạch theo ngữ nghĩa Java. Đặt tên các bước rõ ràng giúp ít nhầm thứ tự.

`Consumer.andThen` cũng hỗ trợ ghép hai hành động theo thứ tự, nhưng với hành động có side effect cần hiểu ngoại lệ có thể khiến bước sau không được thực hiện.

### 5.3. Callback chỉ là một chính sách kỹ thuật nội bộ

Nếu phương thức chỉ cần callback để chọn cách tính hoặc điều kiện trong một luồng xử lý nội bộ, chữ ký chuẩn thường là đủ:

```java
static <T> List<T> retain(List<T> input, Predicate<T> criterion) {
    return input.stream()
            .filter(criterion)
            .collect(Collectors.toList());
}
```

`retain` là đoạn khai báo minh họa cần `java.util.List`, `java.util.function.Predicate` và `java.util.stream.Collectors`. Phương thức mô tả một thao tác lọc phổ quát; tên `Predicate` đã đủ rõ.

**Tiêu chí kiểm tra:** nếu người sử dụng nhìn `Function<T,R>`, `Predicate<T>`, `Consumer<T>` và hiểu chính xác vai trò của callback mà không cần quy tắc phụ, không có lý do mạnh để tạo interface mới.

## 6. Khi nào nên định nghĩa functional interface riêng?

### 6.1. Cần tên nghiệp vụ và hành vi có ý nghĩa cụ thể

Giả sử API tính phí vận chuyển nhận trọng lượng và lựa chọn giao nhanh:

```java
BiFunction<Integer, Boolean, Integer> calculator =
        (weightKg, express) ->
                10 + weightKg * 2 + (express ? 15 : 0);
```

Code chạy được, nhưng chữ ký `BiFunction<Integer,Boolean,Integer>` không cho biết **đơn vị phí**, ý nghĩa hai đối số hay chính sách áp dụng. Một interface riêng thể hiện rõ hợp đồng hơn:

```java
@FunctionalInterface
interface ShippingFeePolicy {
    // Kết quả tính bằng đơn vị phí nguyên của ứng dụng.
    int calculateFee(int weightKg, boolean express);

    default String policyName() {
        return "standard";
    }
}
```

Sử dụng:

```java
ShippingFeePolicy feePolicy =
        (weightKg, express) ->
                10 + weightKg * 2 + (express ? 15 : 0);

int fee = feePolicy.calculateFee(3, true); // 31
```

Tên `ShippingFeePolicy` và `calculateFee` giúp API diễn đạt rõ hơn. Chữ ký dùng `int` và `boolean` trực tiếp, tránh boxing của `Integer`/`Boolean`. Phương thức `default` không làm mất tính chất functional.

Đây là công thức mô phỏng để học thiết kế callback, không phải quy tắc tính phí áp dụng ngoài đời. Hệ thống tiền tệ thật thường cần một kiểu giá trị tiền/đơn vị rõ ràng, quy tắc làm tròn và kiểm tra tính hợp lệ của đầu vào.

### 6.2. Cần checked exception cụ thể trong hợp đồng

Các interface phổ biến `Function`, `Consumer`, `Supplier`, `Predicate` **không khai báo checked exception** ở SAM. Nếu callback được phép đưa `IOException` ra caller, hãy cân nhắc một hợp đồng tự định nghĩa khi bạn kiểm soát API:

```java
@FunctionalInterface
interface FileContentReader {
    String read(Path path) throws IOException;
}
```

Sau đó:

```java
FileContentReader reader =
        path -> new String(
                Files.readAllBytes(path),
                StandardCharsets.UTF_8);
```

Hai đoạn trên minh họa, cần import `Path`, `Files`, `IOException` và `StandardCharsets`. `Files.readAllBytes` là API còn được hỗ trợ. Nội dung bị lỗi đọc có thể ném `IOException` theo hợp đồng `read`, để caller có trách nhiệm bắt/khai báo phù hợp.

Ngược lại, khai báo sau **không biên dịch** nếu không bắt checked exception ngay trong lambda:

```java
// SAI: Function.apply không khai báo IOException.
// Function<Path, String> reader = path ->
//         new String(Files.readAllBytes(path),
//                 StandardCharsets.UTF_8);
```

Không thể khắc phục bằng cách thêm `throws IOException` cho phương thức **tạo ra** `Function`: quy tắc kiểm tra checked exception dựa vào **SAM đích**. Nếu bị ràng buộc bởi API bắt buộc nhận `Function`, phải xử lý lỗi trong thân hoặc chuyển thành unchecked exception có ngữ nghĩa phù hợp như `UncheckedIOException` và giữ nguyên `cause`.

### 6.3. Hợp đồng nghiệp vụ có quy tắc riêng, cần đặt tên để người gọi không nhầm

Các ví dụ hợp lý:

- `AccessPolicy` với phương thức `boolean mayAccess(User user, Resource resource)`, khi quyền truy cập là một khái niệm riêng của hệ thống.
- `RetryDecision` với `boolean shouldRetry(Failure failure, int attempt)`, khi cần một hợp đồng policy rõ ràng.
- `ValidationRule` với `ValidationResult validate(Command command)` nếu kết quả cần thông tin lỗi phong phú, không chỉ `boolean`.
- `FileContentReader` với `throws IOException`, khi người gọi phải thấy rõ lỗi I/O là một phần hợp đồng.

Những kiểu `User`, `Resource`, `Failure`, `Command`, `ValidationResult` ở đây là **tên kiểu giả định thuộc một ứng dụng**, không phải lớp có sẵn trong Java SDK. Chúng minh họa cách đặt tên API; chưa tạo ra chương trình Java độc lập.

Nếu API thực sự yêu cầu một **đối tượng có nhiều phương thức bắt buộc**, nên dùng interface thông thường thay vì ép mọi trách nhiệm thành một SAM duy nhất.

### 6.4. Cần giữ API ổn định và dễ giải thích

Với một callback công khai trong thư viện/framework nội bộ, interface riêng giúp gắn Javadoc, xác định ý nghĩa đối số, đơn vị kết quả, chính sách null, điều kiện trước/sau, quy tắc lỗi và tên phương thức dễ đọc.

Ví dụ tên `FeePolicy.calculateFee(Shipment)` có thể giàu ngữ nghĩa hơn `Function<Shipment, BigDecimal>.apply`. Nhưng **việc tạo interface riêng không tự động kiểm tra tất cả điều kiện nghiệp vụ**: bạn vẫn phải kiểm tra input, viết tài liệu, lựa chọn kiểu dữ liệu đúng và triển khai chính sách thống nhất.

## 7. Khi nào KHÔNG nên tạo interface riêng?

Tránh các trường hợp sau nếu không có yêu cầu bổ sung:

- Một `MyFunction<T,R>` chỉ khai báo `R apply(T input)` giống `Function<T,R>` và không mang hợp đồng khác.
- Một `MyPredicate<T>` chỉ để dùng với `Stream.filter`, buộc bạn viết adapter `rule::test` mà không tạo thêm ý nghĩa.
- Một interface riêng cho mỗi lambda sử dụng một lần trong method nội bộ.
- Một interface có quá nhiều type parameter hoặc phương thức `apply` mơ hồ trong khi tên nghiệp vụ có thể rõ hơn.
- Tự viết `TriFunction` chỉ vì có ba đối số, dù nhiều đối số thực tế mô tả một đối tượng đầu vào kết hợp có ý nghĩa.

**Không có `TriFunction` phổ quát trong `java.util.function`.** Nếu logic thật sự cần ba đối số độc lập, có thể tạo interface riêng; nếu các tham số cùng mô tả một yêu cầu nghiệp vụ, cân nhắc đóng gói thành kiểu dữ liệu `Request` rồi dùng `Function<Request,Result>` hoặc một interface mang tên nghiệp vụ. Không cố gom mọi API thành `Object[]` để tránh khai báo kiểu: điều này làm mất kiểm tra kiểu và gây lỗi thời gian chạy.

## 8. Chương trình Java hoàn chỉnh: kết hợp kiểu chuẩn và kiểu nghiệp vụ

Ví dụ dưới đây dùng **Java 8-compatible syntax/API**, biên dịch được trên JDK 17+ và tương thích với mức nguồn Java 8. Chương trình minh họa khi nào nên chọn `UnaryOperator`, `Predicate`, `Function`, `Supplier`, `BiPredicate`, `IntUnaryOperator`, `Consumer` và khi nào interface nghiệp vụ `ShippingFeePolicy` tạo thêm giá trị.

Tạo tệp **`FunctionalInterfaceChoiceDemo.java`**:

```java
import java.util.Arrays;
import java.util.List;
import java.util.Locale;
import java.util.function.BiPredicate;
import java.util.function.Consumer;
import java.util.function.Function;
import java.util.function.IntUnaryOperator;
import java.util.function.Predicate;
import java.util.function.Supplier;
import java.util.function.UnaryOperator;
import java.util.stream.Collectors;

public class FunctionalInterfaceChoiceDemo {

    @FunctionalInterface
    interface ShippingFeePolicy {
        int calculateFee(int weightKg, boolean express);

        default String policyName() {
            return "standard";
        }
    }

    public static void main(String[] args) {
        List<String> raw =
                Arrays.asList("  Java ", " ", " Lambda ");

        UnaryOperator<String> normalize =
                text -> text.trim().toLowerCase(Locale.ROOT);
        Predicate<String> nonEmpty = text -> !text.isEmpty();

        List<String> words = raw.stream()
                .map(normalize)
                .filter(nonEmpty)
                .collect(Collectors.toList());

        System.out.println("Danh sách: " + words);

        Function<String, Integer> length = String::length;
        Function<String, Integer> normalizedLength =
                normalize.andThen(length);
        System.out.println("Độ dài: "
                + normalizedLength.apply("  Java  "));

        Supplier<String> fallback = () -> "không có";
        String missing = words.stream()
                .filter(text -> text.startsWith("z"))
                .findFirst()
                .orElseGet(fallback);
        System.out.println("Dự phòng: " + missing);

        BiPredicate<String, Integer> minLength =
                (text, minimum) -> text.length() >= minimum;
        System.out.println("Tối thiểu 5: "
                + minLength.test("lambda", 5));

        ShippingFeePolicy policy =
                (weightKg, express) ->
                        10 + weightKg * 2 + (express ? 15 : 0);
        int fee = policy.calculateFee(3, true);
        System.out.println("Cước: " + fee);
        System.out.println("Chính sách: " + policy.policyName());

        IntUnaryOperator doubleFee = amount -> amount * 2;
        System.out.println("Cước gấp đôi: "
                + doubleFee.applyAsInt(fee));

        Consumer<String> audit =
                message -> System.out.println("Audit: " + message);
        audit.accept("đã tính cước");
    }
}
```

Biên dịch và chạy:

```bash
javac FunctionalInterfaceChoiceDemo.java
java FunctionalInterfaceChoiceDemo
```

**Stdout dự kiến chính xác:**

```text
Danh sách: [java, lambda]
Độ dài: 4
Dự phòng: không có
Tối thiểu 5: true
Cước: 31
Chính sách: standard
Cước gấp đôi: 62
Audit: đã tính cước
```

**Giải thích kết quả:**

1. `UnaryOperator<String>` biến đổi chuỗi thành chuỗi, còn `Predicate<String>` loại chuỗi rỗng sau khi `trim`; kết quả là `[java, lambda]`.
2. `normalize.andThen(length)` áp dụng chuẩn hóa trước khi tính độ dài; `"  Java  "` thành `"java"`, độ dài bằng 4.
3. Không có chuỗi bắt đầu bằng `"z"`, nên `Optional.orElseGet` gọi `Supplier` để lấy `"không có"`. Giá trị dự phòng chỉ được tạo khi `Optional` rỗng.
4. `BiPredicate` kiểm tra `"lambda".length() >= 5`, kết quả `true`.
5. `ShippingFeePolicy` diễn đạt cách tính cước theo trọng lượng và giao nhanh. Với 3 kg giao nhanh: `10 + 3 * 2 + 15 = 31`; phương thức `default policyName()` trả `standard`.
6. `IntUnaryOperator` nhân đôi giá trị `int` từ 31 thành 62.
7. `Consumer` thực hiện hành động in thông báo, không trả về dữ liệu. Với hệ thống thật, tác dụng phụ nên được kiểm soát để có thể kiểm thử và quan sát.

Chỉ có **một** interface tự định nghĩa, dành cho hợp đồng mang ngữ nghĩa nghiệp vụ. Các thao tác phổ quát khác được biểu diễn trực tiếp bằng JDK functional interfaces.

## 9. Một ví dụ thiết kế API: kiểu chuẩn hay hợp đồng nghiệp vụ?

Giả sử hệ thống cần kiểm tra đơn hàng có đủ điều kiện hưởng ưu đãi. Nếu chỉ lọc danh sách theo một điều kiện đơn giản, `Predicate<Order>` phù hợp:

```java
// Order là kiểu của ứng dụng; đoạn này chỉ minh họa.
Predicate<Order> eligible =
        order -> order.totalAmount() >= 100;
```

Giả định `totalAmount()` là phương thức do ứng dụng định nghĩa, trả về một số theo đơn vị đã quy định. Trong hệ thống xử lý tiền thật, nên sử dụng kiểu tiền có độ chính xác thích hợp.

Nếu điều kiện này trở thành **chính sách nghiệp vụ** dùng bởi nhiều module, cần lý do từ chối, ngữ cảnh người dùng, phiên bản chính sách hoặc hợp đồng kiểm thử riêng, một interface có tên như `PromotionEligibilityPolicy` có thể tốt hơn. Chẳng hạn:

```java
@FunctionalInterface
interface PromotionEligibilityPolicy {
    boolean isEligible(Order order, Customer customer);
}
```

`Order` và `Customer` trong ví dụ này là lớp của ứng dụng cần định nghĩa thêm. Khi API chỉ cần cặp đầu vào trả về boolean mà không có ngữ nghĩa bổ sung, `BiPredicate<Order,Customer>` vẫn là lựa chọn hợp lệ. **Tên nghiệp vụ chỉ thực sự có ích khi nó ghi nhận một hợp đồng cần bảo vệ**, không phải vì interface riêng tự động tốt hơn.

Có thể chọn giải pháp trung gian: giữ phép toán nội bộ dưới dạng `Predicate`/`Function` chuẩn và chỉ tạo interface riêng tại ranh giới API nơi tên/hợp đồng nghiệp vụ mang giá trị.

## 10. Những đánh đổi khi công khai API

### 10.1. Khả năng tương thích với API của thư viện

`java.util.function.Function`, `Predicate` và `Consumer` được nhận trực tiếp bởi nhiều API chuẩn; interface tự định nghĩa thường không thay thế tự động dù SAM có cùng chữ ký:

```java
@FunctionalInterface
interface TextTransform {
    String change(String input);
}

TextTransform transform = String::trim;

// Function<String, String> function = transform; // SAI: khác kiểu.
Function<String, String> adapted = transform::change; // Hợp lệ.
```

Hai interface có thể chấp nhận lambda tương đương nhưng **không tự động là kiểu con của nhau**. Adapter method reference `transform::change` chuyển hành vi theo đúng target type; đó là một bước thiết kế có chi phí nhỏ nhưng có thật.

Không nên tạo interface riêng chỉ để rồi adapter qua lại ở từng lời gọi Stream khi interface đó không mang thông tin bổ sung.

### 10.2. Generic và suy luận kiểu

Các interface chuẩn dùng generic để hỗ trợ nhiều kiểu:

```java
Function<String, Integer> countCharacters = String::length;
Predicate<Integer> positive = n -> n > 0;
```

Khai báo quá tổng quát như `Function<Object,Object>` làm mất thông tin kiểu hữu ích. Ở chiều ngược lại, interface nghiệp vụ quá cụ thể cho một hành vi kỹ thuật phổ biến có thể hạn chế tái sử dụng.

Lambda thường cần ngữ cảnh kiểu đích rõ ràng:

```java
Function<String, Integer> f = String::length;

// SAI: Không thể suy luận target functional interface chỉ từ lambda.
// var f2 = text -> text.length();
```

Dòng `var` minh họa lỗi: `var` cho biến cục bộ có từ Java 10, nhưng phép khởi tạo **bằng lambda trần không có kiểu đích** vẫn không hợp lệ. Java 11+ có cú pháp `(var x) -> ...` trong **danh sách tham số lambda**, đó là khái niệm khác với `var local = lambda`.

### 10.3. Overload với functional interface

Khi có hai overload nhận các functional interface khác nhau nhưng lambda tương thích cả hai, lời gọi có thể nhập nhằng. Tránh công khai API có nhiều overload khó phân biệt chỉ bằng callback.

Ví dụ minh họa (không phải chương trình độc lập):

```java
static void process(Predicate<String> p) { }
static void process(Function<String, Boolean> f) { }

// Lời gọi sau có thể không xác định được overload:
// process(s -> s.isEmpty());
```

Có thể đặt hai tên phương thức rõ ràng theo hành vi, hoặc khai báo biến lambda có kiểu cụ thể trước:

```java
Predicate<String> empty = String::isEmpty;
process(empty);
```

Cách dùng biến trung gian giúp compiler và người đọc thấy rõ API đích. Cũng không thể overload hai phương thức chỉ khác type argument generic mà có cùng erasure như `Function<String,String>` và `Function<Integer,Integer>`: hai chữ ký đó bị xung đột do type erasure.

### 10.4. Null, thread safety và side effect

Functional interface không tự bảo đảm callback là **pure**, **thread-safe**, **non-null** hay **idempotent**. Ngay cả `Function`/`Predicate` có thể capture và thay đổi trạng thái bên ngoài; `Consumer` thường biểu đạt side effect nhưng không có cơ chế tự đồng bộ.

Nếu dùng callback trong xử lý song song hoặc bất đồng bộ, hãy ghi rõ hợp đồng và kiểm tra trạng thái chung. Biến cục bộ được lambda capture phải `final` hoặc *effectively final*, nhưng điều đó không làm trạng thái của đối tượng được capture trở nên bất biến.

Việc dùng interface nghiệp vụ có thể giúp **mô tả** ràng buộc trong tên/Javadoc, nhưng không thay thế kiểm thử, kiểm tra runtime hoặc thiết kế dữ liệu bất biến khi cần.

## 11. Checklist lựa chọn trước khi thiết kế callback

| Câu hỏi | Nếu câu trả lời là… | Lựa chọn nên xem xét |
| --- | --- | --- |
| Chỉ tạo giá trị khi được yêu cầu? | Không có đầu vào, có kết quả | `Supplier<T>` |
| Đang lọc/kiểm tra một điều kiện? | `T -> boolean` | `Predicate<T>` |
| Đang biến đổi dữ liệu? | `T -> R` | `Function<T,R>` |
| Biến đổi cùng kiểu? | `T -> T` | `UnaryOperator<T>` |
| Ghi nhận sự kiện/thực hiện hành động? | `T -> void` | `Consumer<T>` |
| Thao tác số primitive trong đường nóng? | `int`/`long`/`double` | Họ primitive-specialized phù hợp |
| Đang sắp xếp? | Hai giá trị cùng kiểu cần quy tắc thứ tự | `Comparator<T>` |
| Thực thi tác vụ có kết quả và API nhận Callable? | `() -> V`, có thể phát sinh checked exception | `Callable<V>` |
| Cần tên policy nghiệp vụ rõ? | Public API có quy tắc cụ thể | Functional interface có tên nghiệp vụ |
| Cần checked exception chính xác? | SAM chuẩn không khai báo `throws` mong muốn | Interface riêng với `throws` phù hợp |
| Cần nhiều hành vi trừu tượng bắt buộc? | Không còn một SAM | Interface/lớp thông thường |
| Có nhiều tham số ràng buộc lẫn nhau? | Các đầu vào tạo thành yêu cầu nghiệp vụ | Cân nhắc input object được đặt tên |

### Những lỗi nên tránh

1. **Tạo interface riêng không có giá trị hợp đồng:** chỉ sao chép `Function.apply` hoặc `Predicate.test` khiến API khó tích hợp.
2. **Dùng kiểu chuẩn sai ý nghĩa:** biến hành động `void` thành `Function<T,Void>` hoặc biến điều kiện thành `Function<T,Boolean>` mà không có lý do.
3. **Cho rằng SAM cùng chữ ký sẽ tự tương thích:** hai interface độc lập không tự chuyển kiểu cho nhau.
4. **Dùng `Callable` để né `throws` của `Function`:** nếu API nhận `Function`, phải tuân thủ chính interface đó.
5. **Bọc checked exception rồi bỏ nguyên nhân:** khi cần adapter, giữ `cause` và tài liệu hóa kiểu unchecked có thể phát sinh.
6. **Cố dùng boxed generics ở nơi primitive mới là hợp đồng rõ:** cân nhắc primitive-specialized interface khi cần.
7. **Thêm nhiều abstract method vào `@FunctionalInterface`:** khiến compiler báo lỗi và lambda không còn target SAM hợp lệ.
8. **Định nghĩa contract quá mơ hồ:** tên `apply` trong API nghiệp vụ công khai có thể kém rõ ràng hơn `calculateFee` hoặc `isEligible`.
9. **Quá tối ưu hiệu năng dựa trên giả định:** nếu ảnh hưởng boxing chưa được đo, ưu tiên thiết kế đúng và dễ bảo trì.
10. **Thiết kế callback mà không nói rõ null, lỗi và side effect:** interface chuẩn lẫn interface riêng đều cần hợp đồng sử dụng rõ ràng.

## 12. Kết luận thực hành

Hãy chọn **interface chuẩn** khi hành vi có chữ ký phổ quát và được dùng như một phép biến đổi, điều kiện, nhà cung cấp giá trị hoặc hành động. Điều này tận dụng API `java.util.function`, Stream và khả năng kết hợp sẵn có.

Hãy tạo **functional interface riêng** khi quyết định đó làm rõ một ranh giới nghiệp vụ: tên phương thức có ý nghĩa, kiểu primitive cụ thể, quy tắc lỗi `throws`, điều kiện tham số hoặc một hợp đồng cần được duy trì ổn định cho caller. Chỉ nên thêm interface nếu nó thực sự bổ sung sự rõ ràng hoặc khả năng biểu đạt.

Dù chọn cách nào, lambda vẫn được kiểm tra theo **SAM của target type**: kiểu tham số, kiểu kết quả, checked exception và tính tương thích đều phải hợp lệ. Đây là kiến thức tiếp tục áp dụng trong Java hiện đại, không dựa vào thư viện đã lỗi thời.

### Tài liệu tra cứu chuẩn

- Java SE API: `java.util.function` — https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/function/package-summary.html
- Java SE API: `Comparator` — https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Comparator.html
- Java SE API: `Callable` — https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/Callable.html
- Java Language Specification: Lambda Expressions (`15.27`) — https://docs.oracle.com/javase/specs/jls/se25/html/jls-15.html#jls-15.27
