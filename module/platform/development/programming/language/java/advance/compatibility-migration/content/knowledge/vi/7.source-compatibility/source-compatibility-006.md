# Lambda và method reference khi hợp đồng hàm thay đổi

## 1. Vì sao thay đổi hợp đồng hàm ảnh hưởng đến mã nguồn Java?

Lambda expression và method reference giúp truyền hành vi như một giá trị. Chúng xuất hiện trong Stream API, callback, listener, executor, comparator, event handler và nhiều API thư viện. Một thay đổi nhỏ trong kiểu hàm mà API yêu cầu có thể làm hàng loạt lời gọi không còn biên dịch, dù phần thân lambda nhìn qua vẫn có vẻ đúng.

Ví dụ, một thư viện ban đầu nhận `Function<String, Integer>` rồi đổi tham số thành `ToIntFunction<String>`. Cả hai đều nhận một `String` và trả về một giá trị số, nhưng kiểu kết quả và hợp đồng kiểu khác nhau: `Function` trả về `Integer`, còn `ToIntFunction` trả về `int`. Một lambda có thể tiếp tục biên dịch nhờ target typing và boxing/unboxing, nhưng biến hoặc method reference đã được khai báo theo kiểu cũ có thể cần điều chỉnh.

Khi khảo sát source compatibility trong migration Java, cần hiểu ba thành phần:

- **Functional interface:** giao diện có một phương thức trừu tượng phù hợp để làm kiểu đích cho lambda hoặc method reference.
- **Lambda expression:** biểu thức cung cấp phần triển khai cho phương thức trừu tượng của functional interface.
- **Method reference:** cú pháp tham chiếu đến một method hoặc constructor có thể được thích nghi với chữ ký của functional interface đích.

Khi hợp đồng hàm thay đổi, compiler phải kiểm tra lại số lượng và kiểu tham số, kiểu trả về, generic type, checked exception, overload resolution và ngữ cảnh target type. Một biểu thức từng hợp lệ có thể không còn biên dịch, hoặc có thể được phân giải sang overload khác với ý định ban đầu.

Bài này tập trung vào cách nhận diện tác động đó, cách đọc lỗi compiler và cách chuyển đổi call site có kiểm soát khi nâng cấp API, thư viện hoặc framework.

## 2. Functional interface là hợp đồng của lambda

### 2.1. Phương thức trừu tượng duy nhất (SAM)

Một functional interface có một phương thức trừu tượng duy nhất (Single Abstract Method — SAM). Các phương thức `default` và `static` không làm tăng số SAM. Các phương thức trừu tượng có chữ ký tương đương được kế thừa từ nhiều interface cũng có thể được xem là một hợp đồng trừu tượng duy nhất theo quy tắc của Java.

Ví dụ:

```java
@FunctionalInterface
interface TextFormatter {
    String format(String input);
}

TextFormatter trimAndUpper = text -> text.trim().toUpperCase();
System.out.println(trimAndUpper.format("  java  "));
```

Lambda `text -> ...` được kiểm tra dựa trên SAM `format(String)`. Compiler biết `text` có kiểu `String` và kết quả phải tương thích với `String`.

Annotation `@FunctionalInterface` không bắt buộc để viết lambda, nhưng nên dùng cho interface được thiết kế làm hợp đồng hàm. Nếu một thay đổi vô tình thêm một abstract method thứ hai, compiler sẽ báo lỗi ngay tại khai báo interface.

### 2.2. Các functional interface phổ biến trong JDK

Package `java.util.function` cung cấp các kiểu hàm thường dùng:

| Interface | Hợp đồng khái quát | Ví dụ sử dụng |
| --- | --- | --- |
| `Predicate<T>` | `boolean test(T value)` | Điều kiện lọc |
| `Function<T, R>` | `R apply(T value)` | Chuyển đổi giá trị |
| `Consumer<T>` | `void accept(T value)` | Xử lý có side effect |
| `Supplier<T>` | `T get()` | Cung cấp giá trị |
| `UnaryOperator<T>` | `T apply(T value)` | Biến đổi cùng kiểu vào/ra |
| `BiFunction<T, U, R>` | `R apply(T left, U right)` | Kết hợp hai đầu vào |
| `BiConsumer<T, U>` | `void accept(T left, U right)` | Xử lý hai đầu vào |
| `ToIntFunction<T>` | `int applyAsInt(T value)` | Chuyển sang `int` primitive |
| `IntFunction<R>` | `R apply(int value)` | Nhận `int` primitive |
| `IntPredicate` | `boolean test(int value)` | Predicate cho `int` |

Các interface chuyên biệt cho primitive giúp tránh một số thao tác boxing/unboxing. Vì thế, đổi từ `Function<T, Integer>` sang `ToIntFunction<T>` có thể thay đổi cả kiểu SAM và cách API biểu diễn kết quả.

### 2.3. Thay đổi `default` và `static` method

Thêm một `default` method hoặc `static` method vào functional interface thường không làm mất tính chất SAM vì số abstract method không tăng.

```java
@FunctionalInterface
interface NameRule {
    boolean accepts(String name);

    default boolean acceptsNonBlank(String name) {
        return name != null && !name.isBlank() && accepts(name);
    }

    static NameRule allowAll() {
        return name -> true;
    }
}
```

Lambda hiện có vẫn triển khai `accepts(String)`. Tuy vậy, một default method mới vẫn có thể ảnh hưởng đến hành vi khi được gọi, tạo xung đột với default method kế thừa từ interface khác, hoặc thay đổi cách framework sử dụng interface. Vì vậy, “không đổi SAM” không đồng nghĩa với “không có thay đổi hành vi”.

Nếu thêm một abstract method mới không có implementation mặc định, interface không còn là functional interface và lambda hiện tại không thể triển khai nó. Đây là thay đổi source compatibility rõ ràng.

## 3. Lambda được kiểm tra theo target type

Lambda không có kiểu độc lập hoàn chỉnh như một object class được khai báo tường minh. Compiler dùng target type — thường là functional interface ở vị trí gán, tham số method hoặc kiểu trả về — để suy luận tham số và kiểm tra phần thân.

```java
Predicate<String> isLong = value -> value.length() > 10;
Function<String, Integer> length = value -> value.length();
Consumer<String> print = value -> System.out.println(value);
```

Trong ba ví dụ:

- `Predicate<String>` yêu cầu một tham số `String` và kết quả boolean.
- `Function<String, Integer>` yêu cầu một tham số `String` và kết quả tương thích `Integer`.
- `Consumer<String>` yêu cầu một tham số `String`; phần thân được dùng như thao tác không trả kết quả.

Target type có thể đến từ chữ ký API:

```java
void register(Predicate<String> rule) {
    // Lưu rule để sử dụng sau
}

register(value -> value.startsWith("J"));
```

Nếu thư viện đổi tham số `register` sang một functional interface khác, compiler sẽ phân tích lại lambda theo hợp đồng mới. Lambda có thể vẫn hợp lệ, nhưng tên kiểu tham số được suy luận, kiểu trả về, checked exception hoặc cách chọn overload có thể đổi.

### 3.1. Lambda có kiểu tham số tường minh

Có thể khai báo kiểu tham số tường minh để làm rõ ý định:

```java
Predicate<String> rule = (String value) -> value.startsWith("J");
```

Điều này hữu ích khi compiler không suy luận được hoặc khi có nhiều overload. Tuy nhiên, khai báo tường minh không làm cho một hợp đồng mới tương thích với kiểu tham số cũ. Nếu API chuyển từ `String` sang `Path`, lambda `(String value) -> ...` vẫn không phù hợp.

### 3.2. Block lambda và kiểu trả về

Với block lambda, các nhánh `return` phải đáp ứng kiểu trả về của SAM:

```java
Function<String, Integer> parseLength = value -> {
    if (value == null) {
        return 0;
    }
    return value.length();
};
```

Nếu functional interface đổi kiểu trả về từ `Integer` sang `String`, các lệnh `return` cần được điều chỉnh. Nếu đổi sang `void`, block lambda không thể giữ các giá trị trả về như trước. Ngược lại, một lambda không trả kết quả không thể tự động đáp ứng một SAM yêu cầu giá trị.

## 4. Method reference và các dạng thích nghi

Method reference dùng method có sẵn thay cho việc viết lambda chuyển tiếp trực tiếp. Compiler vẫn cần target type để xác định method nào được chọn và cách thích nghi tham số/kết quả.

### 4.1. Tham chiếu static method

```java
Function<String, Integer> parser = Integer::parseInt;
```

Tương đương về ý nghĩa với:

```java
Function<String, Integer> parser = value -> Integer.parseInt(value);
```

Target type cho biết cần một method nhận `String` và trả về `Integer`. Compiler có thể chọn overload `Integer.parseInt(String)` trả `int`, sau đó boxing thành `Integer` theo kiểu kết quả của `Function`.

### 4.2. Tham chiếu instance method trên một đối tượng cụ thể (bound reference)

```java
String prefix = "java-";
Function<String, String> addPrefix = prefix::concat;
```

Đối tượng nhận lời gọi đã được xác định trong biểu thức `prefix::concat`; lambda tương đương về ý nghĩa là:

```java
Function<String, String> addPrefix = value -> prefix.concat(value);
```

Đối tượng receiver được lấy khi biểu thức method reference được tạo. Nếu biến `prefix` sau đó được gán lại sang một chuỗi khác, method reference đã tạo vẫn giữ receiver ban đầu. Nếu receiver là `null`, lỗi có thể xuất hiện khi tạo method reference vì biểu thức receiver cần được đánh giá ngay.

### 4.3. Tham chiếu instance method trên một đối tượng bất kỳ của kiểu cho trước (unbound reference)

```java
Function<String, String> trim = String::trim;
```

Ở dạng này, tham số đầu tiên của functional interface trở thành receiver của method:

```java
Function<String, String> trim = value -> value.trim();
```

Một ví dụ có hai tham số:

```java
BiFunction<String, Integer, Character> charAt = String::charAt;
```

Tham số đầu là receiver `String`, tham số thứ hai được truyền vào `charAt(int)`, và kết quả primitive `char` được boxing thành `Character`.

### 4.4. Constructor reference

```java
Supplier<ArrayList<String>> newList = ArrayList::new;
Function<Integer, ArrayList<String>> listWithCapacity = ArrayList::new;
```

Target type giúp compiler chọn constructor không tham số hoặc constructor nhận `int`. Nếu API thay đổi target type, constructor overload được chọn có thể thay đổi hoặc không còn phù hợp.

### 4.5. Tóm tắt các dạng method reference

| Dạng | Cú pháp | Ý nghĩa |
| --- | --- | --- |
| Static method | `TypeName::staticMethod` | Gọi static method trên kiểu |
| Bound instance | `instance::method` | Gọi method trên receiver đã xác định |
| Unbound instance | `TypeName::instanceMethod` | Tham số đầu tiên làm receiver |
| Constructor | `TypeName::new` | Tạo object bằng constructor phù hợp |
| Array constructor | `TypeName[]::new` | Tạo mảng theo kích thước đầu vào |

Ví dụ array constructor:

```java
IntFunction<String[]> createArray = String[]::new;
String[] values = createArray.apply(3);
```

Method reference ngắn gọn, nhưng không cho phép viết thêm logic chuyển đổi tham số, xử lý ngoại lệ hoặc kiểm tra điều kiện. Khi hợp đồng thay đổi, một lambda tường minh thường dễ thích nghi hơn.

## 5. Những thay đổi trong SAM làm lambda và method reference bị ảnh hưởng

### 5.1. Thay đổi số lượng tham số

Giả sử API cũ nhận một callback một tham số:

```java
@FunctionalInterface
interface ItemHandler {
    void handle(String item);
}
```

Call site:

```java
ItemHandler handler = item -> System.out.println(item);
```

Nếu hợp đồng đổi thành hai tham số:

```java
@FunctionalInterface
interface ItemHandler {
    void handle(String item, int index);
}
```

Lambda một tham số không còn tương thích. Cần nhận thêm tham số hoặc tạo adapter:

```java
BiConsumer<String, Integer> handler =
        (item, index) -> System.out.println(index + ": " + item);
```

Method reference cũng cần method có số tham số phù hợp. `System.out::println` có nhiều overload, nhưng một target type hai tham số sẽ không tự động biến nó thành thao tác nhận hai giá trị. Có thể viết lambda để kết hợp tham số.

### 5.2. Thay đổi kiểu tham số

Giả sử API chuyển từ:

```java
Consumer<String> consumer = value -> process(value);
```

sang `Consumer<Path>`. Lambda suy luận kiểu `value` thành `Path`, nên phần thân cần dùng API của `Path`. Nếu lambda khai báo tường minh `(String value) -> ...`, nó sẽ không tương thích với `Consumer<Path>`.

Với method reference, kiểu tham số mới có thể làm method không còn phù hợp:

```java
Function<String, Integer> parse = Integer::parseInt;
```

Nếu target chuyển sang `Function<Path, Integer>`, `Integer.parseInt` không nhận `Path`. Cần chuyển đổi rõ ràng:

```java
Function<Path, Integer> parseFileNameLength =
        path -> Integer.parseInt(path.getFileName().toString());
```

Không nên sửa bằng cách ép kiểu tùy tiện. Hãy xác định API mới thực sự muốn nhận kiểu dữ liệu nào và việc chuyển đổi có hợp lệ với mọi đầu vào hay không.

### 5.3. Thay đổi kiểu trả về

Nếu SAM đổi từ `R` sang `void`, hoặc từ `void` sang `R`, phần thân lambda và method reference có thể không còn phù hợp.

Ví dụ cũ:

```java
Function<String, Integer> length = String::length;
```

Nếu API mới yêu cầu `Consumer<String>`, có thể dùng:

```java
Consumer<String> printLength = value -> System.out.println(value.length());
```

Ngược lại, một method trả `void` không thể làm nguồn cho `Function<T, R>` cần giá trị. Cần xác định giá trị trả về có thể lấy từ đâu; không thể tự tạo một kết quả có ý nghĩa bằng cách ép kiểu.

Một trường hợp đặc biệt: method reference tới method trả giá trị có thể được dùng với target `Consumer` khi lời gọi là một statement expression và giá trị trả về được bỏ qua:

```java
Consumer<String> addToList = list::add;
```

`List.add` trả `boolean`, nhưng trong ngữ cảnh `Consumer`, kết quả bị bỏ qua. Điều này không có nghĩa mọi method trả giá trị đều có thể thay cho mọi `void` method; method phải phù hợp về tham số và quy tắc tương thích của method reference.

### 5.4. Thay đổi checked exception

Checked exception là một phần quan trọng của hợp đồng nguồn. Ví dụ:

```java
@FunctionalInterface
interface TextReader {
    String read(Path path) throws IOException;
}

TextReader reader = Files::readString;
```

`Files.readString(Path)` ném `IOException`, nên target `TextReader` cho phép ngoại lệ này.

Nếu API đổi sang `Function<Path, String>`, method reference trên không còn hợp lệ vì `Function.apply` không khai báo `IOException`. Cần xử lý ngoại lệ bên trong lambda:

```java
Function<Path, String> reader = path -> {
    try {
        return Files.readString(path);
    } catch (IOException exception) {
        throw new UncheckedIOException(exception);
    }
};
```

Hoặc giữ một functional interface chuyên biệt nếu việc truyền checked exception là một phần có chủ đích của API:

```java
@FunctionalInterface
interface IOFunction<T, R> {
    R apply(T value) throws IOException;
}
```

Nếu SAM trước đây khai báo `throws IOException` rồi bị bỏ khai báo, lambda có thể không còn biên dịch khi gọi API ném `IOException`. Nếu SAM mở rộng từ `IOException` sang `Exception`, các caller gọi phương thức SAM cũng có thể phải xử lý loại exception rộng hơn. Thay đổi `throws` thường ảnh hưởng source compatibility dù không làm đổi method descriptor ở JVM.

### 5.5. Thay đổi generic type và variance

Generic type quyết định target type cụ thể của lambda. Ví dụ:

```java
Function<String, Integer> length = String::length;
Function<CharSequence, Integer> lengthOfSequence = CharSequence::length;
```

Hai biến có kiểu khác nhau dù cùng biểu diễn thao tác lấy độ dài. `Function<String, Integer>` không phải subtype của `Function<CharSequence, Integer>` vì generic type trong Java là invariant.

API thường dùng wildcard để nhận hàm linh hoạt hơn:

```java
static <T> void consumeAll(
        Iterable<T> values,
        Consumer<? super T> consumer) {
    for (T value : values) {
        consumer.accept(value);
    }
}
```

`? super T` cho phép consumer nhận `T` hoặc một kiểu cha của `T`. Với hàm chuyển đổi, mẫu thường dùng là:

```java
static <T, R> List<R> mapAll(
        Iterable<T> values,
        Function<? super T, ? extends R> mapper) {
    List<R> result = new ArrayList<>();
    for (T value : values) {
        result.add(mapper.apply(value));
    }
    return result;
}
```

Đầu vào dùng `? super T` vì hàm có thể nhận một kiểu rộng hơn `T`; kết quả dùng `? extends R` vì hàm có thể trả về một kiểu con của `R`. Nếu API thay wildcard bằng kiểu invariant chặt hơn, một số method reference hoặc biến hàm đang truyền vào có thể không còn được chấp nhận.

### 5.6. Thay đổi tên hoặc phương thức SAM

Đổi tên phương thức trừu tượng thường không làm lambda tại call site mất khả năng biên dịch nếu kiểu functional interface vẫn được giữ nguyên và lambda không gọi trực tiếp tên SAM. Tuy nhiên, code gọi trực tiếp `handler.oldName(...)`, method reference tới chính phương thức SAM, reflection hoặc framework dựa vào tên method có thể bị ảnh hưởng.

Ví dụ:

```java
@FunctionalInterface
interface RetryPolicy {
    boolean shouldRetry(int attempt);
}

RetryPolicy policy = attempt -> attempt < 3;
boolean retry = policy.shouldRetry(1);
```

Nếu đổi SAM thành `canRetry(int)`, lambda assignment vẫn có thể hợp lệ nhưng lời gọi `policy.shouldRetry(1)` không còn biên dịch. Vì vậy, khi đánh giá source compatibility, cần tìm cả nơi tạo lambda lẫn nơi gọi phương thức interface.

## 6. Overload resolution có thể thay đổi khi thêm hoặc sửa method

Method reference thường được phân giải theo target type. Nếu thư viện thêm overload hoặc thay đổi overload set, một biểu thức có thể trở nên mơ hồ hoặc chọn method khác.

Ví dụ có hai API nhận hai functional interface khác nhau:

```java
static void configure(Function<String, String> mapper) {
    // ...
}

static void configure(UnaryOperator<String> mapper) {
    // ...
}
```

Hai interface này có cùng hình dạng tham số/kết quả nhưng `UnaryOperator<String>` là subtype của `Function<String, String>`. Việc overload các API bằng những functional interface có quan hệ subtype như vậy dễ làm lời gọi lambda hoặc method reference khó đọc và có thể dẫn đến lựa chọn overload không như người viết mong đợi. Thiết kế API nên tránh các overload chỉ khác nhau ở functional interface gần như đồng nhất.

Khi compiler báo ambiguous method call, có thể làm rõ target type bằng biến trung gian hoặc cast:

```java
Function<String, String> mapper = String::trim;
configure(mapper);

configure((UnaryOperator<String>) String::trim);
```

Cast chỉ nên dùng khi thật sự muốn chọn overload tương ứng. Nếu API thay đổi làm overload resolution khác đi, hãy xác minh method nào được gọi và liệu semantics có còn đúng.

### 6.1. Overload của method được tham chiếu

Một method reference có thể trỏ tới method overload:

```java
Function<String, String> stringify = String::valueOf;
```

Trong ví dụ cụ thể, `String::valueOf` có nhiều overload static, nhưng target type chỉ nhận một `String`. Compiler chọn overload phù hợp. Nếu target type đổi hoặc thư viện thêm overload, kết quả phân giải có thể thay đổi.

Khi gặp lỗi khó đọc, viết lambda tường minh để cho compiler một lời gọi có ngữ cảnh rõ:

```java
Function<Object, String> stringify = value -> String.valueOf(value);
```

Lambda làm rõ kiểu đầu vào và lời gọi trong thân. Tuy nhiên, nếu `String.valueOf` có nhiều overload vẫn phù hợp với kiểu `value`, cần dùng kiểu tham số rõ hơn hoặc gọi overload cụ thể.

### 6.2. Generic method reference và type inference

Method reference tới generic method có thể phụ thuộc mạnh vào target type:

```java
Function<String, String> identity = Function.identity();
```

Khi target type bị mất hoặc API dùng wildcard phức tạp hơn, compiler có thể không suy luận được type argument. Biến trung gian với kiểu cụ thể hoặc lambda khai báo kiểu tham số tường minh thường giúp xác định ý định.

Không nên thêm cast rộng như `(Function) ...` để dập lỗi. Raw type làm mất kiểm tra generic và có thể đẩy lỗi sang runtime dưới dạng `ClassCastException`.

## 7. Thay đổi API từ `Function` sang interface chuyên biệt

Một thay đổi phổ biến trong thư viện là chuyển từ functional interface tổng quát sang interface chuyên biệt để diễn tả rõ hơn hợp đồng hoặc tránh boxing.

| Thay đổi | Tác động có thể gặp | Cách xử lý |
| --- | --- | --- |
| `Function<T, Boolean>` → `Predicate<T>` | Phương thức SAM đổi từ `apply` sang `test`; biến `Function` không truyền trực tiếp được | Đổi kiểu biến và method reference, hoặc adapter `value -> old.apply(value)` |
| `Function<T, Integer>` → `ToIntFunction<T>` | Kết quả primitive `int`; SAM đổi sang `applyAsInt` | Dùng lambda/method reference tương thích và kiểm tra boxing/null semantics |
| `Function<T, T>` → `UnaryOperator<T>` | Target type cụ thể hơn; biến `Function<T,T>` có thể không truyền vào tham số `UnaryOperator<T>` | Đổi khai báo nếu đúng hợp đồng hoặc tạo adapter |
| `Consumer<T>` → custom callback có thêm context | Số tham số hoặc exception contract đổi | Viết lambda nhận context mới và cập nhật call site |
| Custom SAM bỏ checked exception | Lambda gọi I/O không còn biên dịch trực tiếp | Bắt và chuyển đổi exception hoặc giữ interface I/O chuyên biệt |

Ví dụ chuyển từ `Function<String, Boolean>` sang `Predicate<String>`:

```java
Function<String, Boolean> oldRule = value -> value.startsWith("J");

Predicate<String> newRule = value -> oldRule.apply(value);
```

Trong code mới, nên khai báo trực tiếp `Predicate<String>` nếu API mong đợi predicate:

```java
Predicate<String> newRule = value -> value.startsWith("J");
```

Điểm cần chú ý là `Function<String, Boolean>` có thể trả về `null`, còn `Predicate<String>` trả primitive `boolean`. Nếu adapter gọi `oldRule.apply(value)` và nhận `null`, unboxing sang boolean có thể ném `NullPointerException`. Chuyển đổi kiểu không chỉ là thay tên interface; phải xác định rõ nullability và semantics.

## 8. Method reference có thể giữ được, nhưng ý nghĩa có thể đổi

Một method reference biên dịch thành công chưa đủ để chứng minh hành vi tương đương. Những thay đổi sau có thể làm ý nghĩa của nó khác đi:

- Overload được chọn khác do target type hoặc overload set thay đổi.
- Method được tham chiếu thay đổi semantics, giá trị mặc định hoặc cách xử lý lỗi.
- Receiver của bound method reference được tạo ở thời điểm khác với điều người đọc giả định.
- Generic type được suy luận rộng/hẹp hơn, làm thay đổi kiểu thực tế của giá trị truyền vào.
- Boxing/unboxing xuất hiện hoặc biến mất khi đổi giữa wrapper và primitive functional interface.
- API mới gọi callback nhiều lần, ở thread khác hoặc sau thời điểm khác so với trước đây.

Ví dụ, một API trước đây gọi callback đồng bộ ngay trong method, nhưng phiên bản mới lưu callback để gọi bất đồng bộ. Lambda/method reference vẫn có thể biên dịch, nhưng việc bắt giữ biến mutable, thread-safety và vòng đời object đã thay đổi. Đây là behavioral compatibility cần kiểm thử riêng.

Vì vậy, khi nâng API callback, hãy đọc tài liệu về thời điểm gọi, số lần gọi, thread, thứ tự, cancellation và exception propagation, ngoài việc sửa lỗi compile.

## 9. Chiến lược chuyển đổi call site

### 9.1. Ưu tiên lambda tường minh khi cần thích nghi

Method reference phù hợp khi chữ ký nguồn và target type khớp trực tiếp. Khi cần đổi tham số, chuyển đổi dữ liệu, xử lý exception hoặc thêm validation, lambda tường minh thể hiện rõ logic hơn.

Ví dụ API đổi từ `Function<String, Integer>` sang `ToIntFunction<Path>`:

```java
// Trước đây
Function<String, Integer> oldMapper = Integer::parseInt;

// Sau khi hợp đồng yêu cầu Path -> int
ToIntFunction<Path> newMapper = path ->
        Integer.parseInt(path.getFileName().toString());
```

Lambda cho thấy rõ `Path` được chuyển thành tên file rồi mới parse. Nếu tên file không phải số hợp lệ, cần quyết định cách xử lý lỗi thay vì để `NumberFormatException` xuất hiện bất ngờ.

### 9.2. Dùng adapter để giữ module cũ hoạt động trong giai đoạn chuyển tiếp

Khi nhiều module chưa thể chuyển cùng lúc, adapter có thể chuyển đổi giữa hợp đồng cũ và mới.

```java
static <T, U, R> Function<T, R> adapt(
        Function<? super T, ? extends U> before,
        Function<? super U, ? extends R> after) {
    return value -> after.apply(before.apply(value));
}
```

Ví dụ:

```java
Function<String, Integer> parse = Integer::parseInt;
Function<Integer, String> label = number -> "ID-" + number;

Function<String, String> toLabel = adapt(parse, label);
System.out.println(toLabel.apply("42"));
```

Adapter giúp module gọi API mới mà vẫn nhận đầu vào từ module cũ. Tuy nhiên, nó cần có owner và thời hạn nếu chỉ phục vụ migration. Khi tất cả consumer đã chuyển sang hợp đồng mới, loại bỏ adapter để tránh duy trì hai cách biểu diễn cùng một thao tác.

### 9.3. Giữ checked exception bằng functional interface phù hợp

Nếu callback thực hiện I/O, có thể định nghĩa một functional interface nêu rõ exception thay vì bọc unchecked ở mọi call site:

```java
@FunctionalInterface
interface IOFunction<T, R> {
    R apply(T value) throws IOException;
}

IOFunction<Path, String> readText = Files::readString;
```

Nếu API mới chỉ nhận `Function<Path, String>`, cần xử lý `IOException` bên trong lambda hoặc dùng một abstraction khác được API hỗ trợ. Quyết định này ảnh hưởng đến nơi exception được xử lý và cách caller quan sát lỗi.

### 9.4. Tránh ép kiểu raw hoặc cast không kiểm chứng

Các cách sau thường che giấu vấn đề:

```java
Function raw = (Function) someCallback;
```

Raw type bỏ qua kiểm tra generic. Nếu kiểu thực tế không khớp, lỗi có thể xuất hiện muộn ở runtime. Hãy dùng generic type cụ thể, adapter có kiểm tra hoặc chuyển đổi rõ ràng.

## 10. Quy trình đánh giá khi hợp đồng hàm thay đổi

Khi nâng phiên bản thư viện/framework có thay đổi functional interface, thực hiện theo trình tự:

### Bước 1: Xác định hợp đồng cũ và mới

Ghi lại:

- Tên functional interface và SAM.
- Số lượng, thứ tự và kiểu tham số.
- Kiểu trả về, primitive/wrapper và nullability.
- Generic parameter, bound và wildcard.
- Checked exception được khai báo.
- Các default/static method mới hoặc thay đổi semantics.
- Cách API gọi callback: đồng bộ/bất đồng bộ, số lần gọi, thread và thứ tự.

### Bước 2: Tìm tất cả call site

Tìm lambda, method reference, biến functional interface, method nhận/trả callback và nơi gọi trực tiếp SAM. Đừng chỉ tìm ký tự `->` hoặc `::`; callback có thể được gán qua biến, trả về từ factory, lưu trong field hoặc được tạo bởi helper method.

### Bước 3: Biên dịch để phân loại lỗi

Compiler error có thể chỉ ra:

- Incompatible parameter types.
- Incompatible return type.
- Unhandled checked exception.
- Cannot infer type arguments.
- Reference to method is ambiguous.
- Method reference cannot be applied to given types.
- Functional interface is not valid because it has multiple abstract methods.

Ghi lại lỗi theo nhóm thay vì sửa từng dòng theo cách đoán. Một thay đổi SAM có thể gây nhiều lỗi giống nhau trên nhiều module.

### Bước 4: Chọn cách sửa phù hợp

- Giữ method reference nếu chữ ký vẫn khớp và semantics không đổi.
- Dùng lambda tường minh nếu cần đổi kiểu hoặc chuyển đổi tham số/kết quả.
- Dùng adapter nếu cần hỗ trợ nhiều consumer trong thời gian chuyển tiếp.
- Thay functional interface nếu API mới thể hiện đúng hợp đồng hơn.
- Tách overload hoặc thêm kiểu trung gian nếu lời gọi trở nên mơ hồ.
- Xử lý checked exception tại ranh giới được thiết kế rõ ràng.

### Bước 5: Kiểm thử hành vi

Kiểm thử các trường hợp bình thường, null/empty, dữ liệu biên, lỗi chuyển đổi, checked exception, số lần callback được gọi và cách callback tương tác với thread/lifecycle. Với method reference overload, có thể viết test nhỏ hoặc gán vào biến target type tường minh để xác nhận overload được chọn.

### Bước 6: Loại bỏ lớp chuyển tiếp sau migration

Nếu adapter hoặc overload cũ chỉ được thêm để hỗ trợ chuyển đổi, theo dõi consumer còn dùng nó. Xóa sau khi đã có bằng chứng rằng không còn caller cần hợp đồng cũ và phiên bản API mới đã được áp dụng đồng nhất.

## 11. Ví dụ tổng hợp: API callback đổi từ `Function` sang `Predicate`

Giả sử phiên bản thư viện cũ cung cấp:

```java
public void filterNames(Function<String, Boolean> condition) {
    // ...
}
```

Consumer gọi:

```java
filterNames(name -> name.startsWith("A"));
filterNames(String::isEmpty);
```

Phiên bản mới đổi API:

```java
public void filterNames(Predicate<String> condition) {
    // ...
}
```

Lambda inline có thể tiếp tục biên dịch vì compiler suy luận lại target type. Nhưng biến đã khai báo kiểu cũ không truyền trực tiếp được:

```java
Function<String, Boolean> condition = name -> name.startsWith("A");
filterNames(condition); // Không tương thích với Predicate<String>
```

Chuyển biến sang kiểu mới:

```java
Predicate<String> condition = name -> name.startsWith("A");
filterNames(condition);
```

Nếu cần giữ `Function` tạm thời:

```java
Function<String, Boolean> oldCondition = name -> name.startsWith("A");
Predicate<String> adapted = name -> Boolean.TRUE.equals(oldCondition.apply(name));
filterNames(adapted);
```

Adapter dùng `Boolean.TRUE.equals` để xử lý trường hợp hàm cũ trả `null` như `false`, tránh lỗi unboxing. Đây là quyết định semantics cần được xác nhận với yêu cầu nghiệp vụ; nếu `null` phải được coi là lỗi, hãy ném exception rõ ràng thay vì âm thầm chuyển thành `false`.

Đối với `String::isEmpty`, method reference có thể tiếp tục phù hợp với `Predicate<String>` vì `isEmpty()` trả primitive boolean và nhận receiver `String`. Tuy nhiên, cần xác nhận method reference đang trỏ đến đúng overload/kiểu mong muốn nếu target API thay đổi thêm.

## 12. Thiết kế API callback để giảm rủi ro tương thích

Người thiết kế thư viện có thể giảm chi phí migration bằng một số nguyên tắc:

- Chọn functional interface có sẵn trong JDK khi hợp đồng phù hợp; tránh tạo nhiều interface có cùng hình dạng nhưng không có lý do rõ ràng.
- Đặt tên method và generic parameter thể hiện đúng ý nghĩa, đặc biệt phân biệt predicate, mapping và consumer.
- Dùng wildcard variance hợp lý, như `Predicate<? super T>` hoặc `Function<? super T, ? extends R>`, để giảm ràng buộc không cần thiết cho consumer.
- Tránh overload method chỉ khác nhau ở hai functional interface có cùng số tham số và kiểu trả về gần tương đương.
- Giữ checked exception contract ổn định hoặc cung cấp một abstraction rõ ràng cho thao tác có thể lỗi.
- Quy định rõ callback được gọi bao nhiêu lần, đồng bộ hay bất đồng bộ, trên thread nào và có thể được gọi sau khi method trả về hay không.
- Khi cần đổi SAM, cân nhắc cung cấp adapter/default method hoặc API mới có tên khác trong một giai đoạn chuyển tiếp.
- Dùng `@FunctionalInterface` để compiler bảo vệ ý định thiết kế SAM.
- Cung cấp release note và migration example cho thay đổi target type, generic, exception hoặc overload.

Không nên duy trì API cũ mãi chỉ để tránh mọi thay đổi. Điều quan trọng là thay đổi có lộ trình, có cảnh báo deprecation khi phù hợp và có ví dụ chuyển đổi đủ rõ để consumer sửa đúng.

## 13. Những lỗi thường gặp khi chuyển lambda và method reference

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Lambda không còn biên dịch | Số lượng/kiểu tham số hoặc kiểu trả về của SAM đổi | Đọc chữ ký SAM mới và sửa lambda theo target type mới. |
| Method reference không tìm thấy method phù hợp | Method nguồn không khớp tham số/kết quả của target type | Viết lambda để chuyển đổi rõ hoặc chọn overload cụ thể. |
| Checked exception không được xử lý | Functional interface mới không khai báo exception đó | Bắt/chuyển đổi exception hoặc dùng interface có throws phù hợp. |
| Cannot infer type arguments | Generic bound/wildcard hoặc target type thay đổi | Khai báo kiểu biến, type witness hoặc tham số lambda tường minh. |
| Ambiguous method call | Nhiều overload nhận functional interface tương tự | Tách biến target type hoặc cast có chủ đích; xem lại thiết kế overload. |
| `NullPointerException` sau khi đổi `Function<T, Boolean>` sang `Predicate<T>` | Kết quả `Boolean` null bị unbox thành `boolean` | Xác định semantics của null và chuyển đổi có chủ đích. |
| Callback vẫn compile nhưng chạy khác | Thay đổi thời điểm, số lần gọi, thread hoặc semantics | Đọc hợp đồng runtime và bổ sung integration/concurrency test. |
| Lambda bị báo nhiều abstract method | Interface không còn là SAM | Thêm default implementation hoặc triển khai interface bằng class cụ thể. |

## 14. Kết luận

Lambda và method reference luôn được kiểm tra dựa trên functional interface đích. Khi hợp đồng hàm thay đổi, cần xem xét chữ ký SAM, generic type, kiểu trả về, checked exception, overload resolution và cách callback được thực thi. Một method reference có thể tiếp tục biên dịch nhưng chọn overload hoặc có hành vi khác; một lambda inline có thể tự thích nghi nhờ target typing trong khi biến functional interface đã khai báo theo kiểu cũ không còn truyền được.

Trong migration, hãy xác định hợp đồng cũ và mới trước, tìm toàn bộ call site, phân loại lỗi compiler rồi chọn giữa method reference, lambda tường minh và adapter. Cuối cùng, kiểm thử cả hành vi callback — số lần gọi, thread, exception và null semantics — để bảo đảm thay đổi source code phản ánh đúng hợp đồng mới của thư viện.
