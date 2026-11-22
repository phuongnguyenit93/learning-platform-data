# Suy luận kiểu cho lambda và method reference: ngữ cảnh phép gán, tham số và ép kiểu

Trong Java, lambda (`x -> ...`) và method reference (`String::trim`, `Integer::parseInt`, `String[]::new`) **không tự mang một kiểu functional interface duy nhất khi đứng độc lập**. Chúng được kiểm tra dựa trên *kiểu đích* (*target type*) do ngữ cảnh sử dụng cung cấp. Cơ chế này gọi là **target typing**, là một phần của hệ thống suy luận kiểu của Java từ Java 8 và vẫn áp dụng trên các JDK hiện đại.

Ba ngữ cảnh quan trọng nhất:

1. **Phép gán (assignment context):** kiểu biến hoặc trường khai báo bên trái cung cấp hợp đồng cho lambda ở bên phải.
2. **Tham số lời gọi (invocation context):** kiểu tham số của phương thức hoặc constructor nhận lambda cung cấp hợp đồng; đôi khi còn phải giải quyết overload và suy luận generic.
3. **Ép kiểu (casting context):** một cast tường minh cung cấp functional interface đích khi ngữ cảnh không đủ rõ hoặc khi cần phân biệt overload.

Cùng một đoạn `s -> s.length()` có thể có ý nghĩa khác nhau tùy đích là `Function<String,Integer>` hay một interface khác. Vì vậy, khi compiler báo “incompatible types”, “cannot infer type” hoặc “reference ... is ambiguous”, hãy xem **ngữ cảnh gắn kiểu**, không chỉ nhìn thân lambda.

Bài học dùng các API Java hiện vẫn được hỗ trợ; ví dụ độc lập sử dụng JDK **17 trở lên**.

## 1. Tư duy nền tảng: target type và SAM

Một *functional interface* có đúng **một hợp đồng phương thức trừu tượng chức năng** (*single abstract method*, SAM) theo các quy tắc JLS. Ví dụ:

```java
@FunctionalInterface
interface TextRule {
    boolean test(String text);
}
```

Đây là **định nghĩa minh họa**, chưa có phương thức `main`. Chữ ký SAM là `boolean test(String text)`. Khi gán:

```java
TextRule nonBlank = text -> !text.isBlank();
```

Compiler biết rằng `text` được suy ra là `String` và kết quả của lambda phải tương thích với `boolean`. `String.isBlank()` có từ Java 11 và dùng được trên JDK 17+.

Với interface chuẩn:

```java
Function<String, Integer> length = text -> text.length();
Predicate<String> nonEmpty = text -> !text.isEmpty();
Consumer<String> print = text -> System.out.println(text);
```

Đây là các **đoạn minh họa**, cần `import java.util.function.*;` và đặt trong scope thích hợp.

| Kiểu đích | SAM | Kiểu tham số `text` được suy ra | Kết quả hợp lệ |
| --- | --- | --- | --- |
| `Function<String,Integer>` | `Integer apply(String)` | `String` | `Integer` hoặc `int` nhờ boxing |
| `Predicate<String>` | `boolean test(String)` | `String` | `boolean` |
| `Consumer<String>` | `void accept(String)` | `String` | Một câu lệnh/hành động tương thích `void` |
| `UnaryOperator<String>` | `String apply(String)` | `String` | `String` |
| `IntUnaryOperator` | `int applyAsInt(int)` | `int`, nếu tên tham số là `n` | `int` |

**Không phải chỉ đếm số tham số.** Kiểu của tham số, kiểu trả về, checked exception và khả năng tương thích body đều phải thỏa mãn chữ ký của functional interface. Target typing không có nghĩa Java tự đoán một interface bất kỳ từ nội dung lambda.

### “Poly expression” là gì?

Lambda và method reference thuộc nhóm *poly expressions*: kiểu của chúng phụ thuộc vào target type. Ví dụ `String::length` có thể dùng để triển khai `Function<String,Integer>`, nhưng không thể khẳng định nó “vốn có kiểu `Function<String,Integer>`” khi viết đơn lẻ.

```java
Function<String, Integer> length = String::length;
ToIntFunction<String> primitiveLength = String::length;
```

Hai khai báo minh họa cần import `Function` và `ToIntFunction`. Cùng method reference, nhưng target khác nhau. `length.apply("Java")` trả kiểu wrapper `Integer`, trong khi `primitiveLength.applyAsInt("Java")` trả primitive `int`.

## 2. Ngữ cảnh phép gán: kiểu khai báo dẫn đường

Trong phép gán, compiler lấy kiểu đích từ biến, trường, phần tử mảng hoặc thành phần nhận giá trị. Với lambda, kiểu này phải là một functional interface phù hợp.

```java
Function<String, String> trim = s -> s.trim();
Predicate<Integer> positive = n -> n > 0;
Runnable task = () -> System.out.println("done");
```

Đây là các đoạn minh họa, cần import `Function` và `Predicate`. Compiler đối chiếu lần lượt:

- `Function<String,String>` → một tham số `String`, trả `String`.
- `Predicate<Integer>` → một tham số `Integer`, trả `boolean`.
- `Runnable` → không tham số, trả `void`; `println` là câu lệnh phù hợp.

Gán lại một biến đã có kiểu cũng là ngữ cảnh đích:

```java
Function<String, String> normalizer;
normalizer = String::trim;
normalizer = s -> s.strip();
```

Đây là ví dụ minh họa, `String.strip()` có từ Java 11. Việc gán mới chỉ thay object hành vi mà biến tham chiếu giữ; method reference không thực thi cho đến khi gọi `apply`. Trong các API hiện đại, nên dùng `strip()` khi muốn bỏ các khoảng trắng Unicode theo semantics của `String.strip`, và hiểu nó không hoàn toàn đồng nghĩa `trim()`.

### Lambda suy luận kiểu tham số từ bên trái

```java
Function<String, Integer> count = s -> s.length();
```

Ở đây `s` có kiểu `String` vì SAM nhận `String`. Không cần viết `(String s) -> s.length()`. Với lambda một tham số, tên có thể viết không ngoặc; với hai tham số trở lên, dùng ngoặc.

```java
BiFunction<String, String, Integer> sumLengths =
        (left, right) -> left.length() + right.length();
```

Đoạn minh họa cần `BiFunction`. Hai tham số đều được suy ra là `String`, kết quả `int` được boxing thành `Integer` để tương thích SAM.

Nếu muốn khai báo kiểu tham số tường minh:

```java
Function<String, Integer> count = (String s) -> s.length();
```

Kiểu khai báo `String` phải phù hợp chính xác với kiểu tham số SAM theo quy tắc áp dụng cho *explicitly typed lambda*; không thể tự thay bằng `Object` chỉ vì `String` kế thừa `Object`:

```java
// SAI: kiểu tham số tường minh không khớp tham số SAM.
// Function<String, Integer> bad = (Object s) -> s.toString().length();
```

**Đừng nhầm với generic variance:** `Function<? super String, Integer>` có quy tắc linh hoạt khác ở cấp *type argument*, không đồng nghĩa mọi lambda khai báo `Object` đều gán được cho `Function<String,Integer>` tường minh.

### Kiểu trả về cũng được kiểm tra

```java
Function<String, Integer> length = s -> s.length();
Function<String, String> upper = s -> s.toUpperCase();
```

Cả hai hợp lệ. Nhưng:

```java
// SAI: String không tương thích với Integer.
// Function<String, Integer> invalid = s -> s.toUpperCase();
```

Compiler không “tự sửa” kiểu trả về bằng cách chuyển chuỗi thành số. Cần một phép biến đổi có kết quả đúng kiểu, ví dụ `Integer.parseInt` nếu dữ liệu thực sự là số.

### Không thể gán lambda trực tiếp cho Object

```java
// SAI: Object không phải functional interface.
// Object action = () -> System.out.println("hi");

// ĐÚNG: chỉ rõ target functional interface trước.
Object action = (Runnable) () -> System.out.println("hi");
```

Đây là các đoạn minh họa. Cast `(Runnable)` giúp lambda được *target typed* trước khi tham chiếu kết quả vào biến `Object`. Đối tượng đó vẫn triển khai `Runnable`; không phải “Object tự động có phương thức `run()`”.

## 3. Tại sao var không tự suy luận kiểu từ lambda?

`var` (suy luận kiểu biến cục bộ, từ Java 10) cần biểu thức khởi tạo có kiểu có thể xác định. Lambda và method reference thuần túy **cần target type**, nên:

```java
// SAI: thiếu target type cho poly expression.
// var callback = s -> s.length();
// var mapper = String::length;
```

Đây là ví dụ lỗi đã comment. Không có luật cho phép compiler tự chọn `Function` hay `ToIntFunction` làm loại callback.

Có thể viết:

```java
Function<String, Integer> callback = String::length;

// HỢP LỆ nhưng thường kém rõ hơn khai báo bên trên.
var mapper = (Function<String, Integer>) String::length;
```

Đoạn minh họa cần import `Function`. Trong dòng thứ hai, **cast cung cấp target type** trước khi `var` suy ra kiểu biến. Thường nên khai báo rõ functional interface, để người đọc thấy contract ngay lập tức.

**Phân biệt:** việc Java cho dùng `var` ở khai báo **tham số lambda** (từ Java 11) không làm `var f = x -> ...` hợp lệ. Ví dụ sau đúng vì **target type vẫn được khai báo ở bên trái**:

```java
Function<String, Integer> length = (var s) -> s.length();
```

Khi sử dụng `var` cho tham số lambda, phải sử dụng nhất quán cho toàn bộ tham số trong danh sách; đừng trộn `var` với kiểu tham số tường minh hoặc tham số suy luận kiểu không có `var` trong cùng danh sách.

## 4. Ngữ cảnh tham số: kiểu mà phương thức yêu cầu

Khi gọi một phương thức có tham số là functional interface, đối số lambda/method reference có thể nhận target type từ **chữ ký tham số** mà không cần khai báo biến trung gian.

```java
static void inspect(String value, Predicate<String> rule) {
    System.out.println(rule.test(value));
}

// Trong phương thức gọi:
inspect("Java", text -> text.length() >= 4);
```

Đây là **đoạn minh họa**, cần `Predicate` và đặt static method trong class. `inspect` yêu cầu tham số thứ hai có kiểu `Predicate<String>`, nên `text` trong lambda được hiểu là `String`, body phải trả `boolean`. Đầu ra của lời gọi minh họa là `true`.

Một ví dụ nhận mapper:

```java
static <R> R convert(String input, Function<String, R> mapper) {
    return mapper.apply(input);
}

int count = convert("Lambda", String::length); // 6
String trimmed = convert("  Java  ", String::trim); // "Java"
```

Đây là các đoạn minh họa cần `Function`. Generic method dùng suy luận kiểu cho `R`, kết hợp thông tin từ tham số mapper và ngữ cảnh nhận kết quả. Đây là **hai tầng suy luận**: suy luận type argument của phương thức và target typing của method reference.

### Method reference được kiểm tra theo SAM tại call site

Ví dụ:

```java
static void printLength(ToIntFunction<String> fn) {
    System.out.println(fn.applyAsInt("Java"));
}

// Gọi:
printLength(String::length);
```

Đoạn minh họa cần `ToIntFunction`. Chữ ký SAM là `int applyAsInt(String)`, vì thế `String::length` được hiểu như hành vi nhận một `String` rồi gọi `length()` trên nó. Nếu target là một interface có số tham số không phù hợp, method reference sẽ không hợp lệ.

### Stream.map và filter cũng là invocation context

```java
List<String> names = List.of("An", "Binh", "Chi");

List<Integer> lengths = names.stream()
        .map(String::length)
        .toList();

List<String> longNames = names.stream()
        .filter(s -> s.length() >= 4)
        .toList();
```

Đoạn minh họa cần `java.util.List`. `Stream.map` cần một `Function<? super T, ? extends R>`, còn `Stream.filter` cần `Predicate<? super T>`. Với nguồn `Stream<String>`, compiler xác định loại đầu vào và kiểm tra thân biểu thức. `Stream.toList()` dùng được từ Java 16, trả danh sách không thể sửa cấu trúc bằng các thao tác thay đổi; nếu cần mutable list, tạo `ArrayList` tường minh. Ở đây kết quả `lengths` là `[2,4,3]` và `longNames` là `["Binh"]`.

**Một điểm quan trọng:** danh sách kết quả không bị “tự chuyển” thành kiểu khác chỉ vì bạn dùng lambda. `map` tạo phần tử kết quả theo `R` được suy luận, còn `filter` giữ kiểu phần tử ban đầu và chỉ quyết định có giữ phần tử hay không.

## 5. Ngữ cảnh ép kiểu: cast đặt target trực tiếp

Cú pháp cast có thể cung cấp target type cho lambda khi khai báo ngoài chưa đủ rõ:

```java
Object callback = (Runnable) () -> System.out.println("run");

Runnable typed = (Runnable) callback;
typed.run();
```

Đây là đoạn minh họa. `(Runnable)` đứng trước lambda giúp trình biên dịch biết SAM là `void run()`. Cast ở dòng thứ hai là **cast tham chiếu object bình thường**: nếu `callback` không thực sự triển khai `Runnable`, có thể ném `ClassCastException`.

Một ví dụ với method reference:

```java
Object lengthMapper = (Function<String, Integer>) String::length;

@SuppressWarnings("unchecked")
Function<String, Integer> typed =
        (Function<String, Integer>) lengthMapper;
```

Đây là minh họa. Cách viết hợp lệ, nhưng **không nên lưu Function trong Object rồi cast lại** trong API thường ngày. `@SuppressWarnings("unchecked")` chỉ tắt cảnh báo unchecked cast, không khiến phép ép kiểu sai trở nên an toàn. Tốt hơn nên giữ khai báo gốc:

```java
Function<String, Integer> typed = String::length;
```

### Cast không biến lambda thành một kiểu bất kỳ

Cú pháp sau sai:

```java
// SAI: String không phải functional interface.
// String text = (String) (() -> "hello");
```

Một lambda có thể được target typed thành **functional interface** phù hợp, không phải một class bất kỳ. Dùng `Supplier<String>` nếu cần một tác vụ không tham số trả về chuỗi; dùng chuỗi trực tiếp nếu không cần hành vi trì hoãn.

## 6. Khi phương thức overload nhận nhiều functional interface

Một tình huống khó: compiler thấy nhiều overload đều có tham số là functional interface, trong khi lambda chưa có kiểu độc lập. **Overload resolution** diễn ra ở compile time; không phải Java thực thi lambda để đoán mục đích.

Giả sử class có hai overload:

```java
static String choose(Supplier<String> supplier) {
    return "Supplier:" + supplier.get();
}

static String choose(Callable<String> callable) throws Exception {
    return "Callable:" + callable.call();
}
```

Đây là **đoạn định nghĩa minh họa**; cần import `java.util.function.Supplier` và `java.util.concurrent.Callable`. Cả hai SAM không tham số và trả `String`.

Do đó:

```java
// SAI: không có overload ưu tiên giữa hai interface không liên quan.
// String result = choose(() -> "ok");

// ĐÚNG: cast chỉ rõ overload cần gọi.
String first = choose((Supplier<String>) () -> "ok");
String second = choose((Callable<String>) () -> "ok");
```

Đây là minh họa cần hai method `choose` ở trên; phương thức chứa lời gọi `Callable` cần xử lý hoặc khai báo `throws Exception`. `first` là `"Supplier:ok"`, `second` là `"Callable:ok"`.

**Cách rõ nghĩa hơn khi có thể:** tạo biến trung gian có kiểu:

```java
Supplier<String> getValue = () -> "ok";
String first = choose(getValue);
```

Cách này đưa target type vào **ngữ cảnh phép gán**, rồi lời gọi phương thức chỉ phải chọn overload dựa trên kiểu đã xác định. Với API công khai, cân nhắc **đổi tên hai overload** nếu cùng một lambda thường làm phát sinh nhập nhằng, thay vì bắt người dùng cast ở mọi nơi.

### Không phải cứ overload là ambiguous

Nếu một overload có tham số `Predicate<String>` và một overload có tham số `Consumer<String>`, một lambda trả boolean có thể phù hợp với một hoặc cả hai tùy dạng body và quy tắc *void-compatible/value-compatible*. Trình biên dịch áp dụng những quy tắc chính xác của JLS, chứ không chỉ nhìn tên interface. Tránh khẳng định quá đơn giản rằng “nếu có hai overload functional interface thì luôn lỗi”.

Ví dụ body là một lời gọi phương thức:

```java
Function<String, String> normalize = s -> s.trim();
Consumer<String> ignoreResult = s -> s.trim();
```

Đây là minh họa cần `Function` và `Consumer`. `s.trim()` là method invocation expression, được phép dùng như một câu lệnh nên nó **void-compatible**, đồng thời trả `String` nên nó **value-compatible**. Gán vào `Consumer` hợp lệ nhưng **bỏ kết quả trả về**, thường không diễn đạt đúng mục đích chuẩn hóa dữ liệu.

Nếu cần thay đổi chuỗi, dùng `Function<String,String>`; nếu cần xử lý một hành động không trả kết quả, dùng `Consumer<String>` với body như `System.out.println(s)`.

## 7. Explicitly typed và implicitly typed lambda khác nhau thế nào?

Hai cách sau đều hợp lệ trong ngữ cảnh gán `Function<String,Integer>`:

```java
Function<String, Integer> implicit = s -> s.length();
Function<String, Integer> explicit = (String s) -> s.length();
```

Với lambda **implicit**, kiểu tham số lấy từ target. Với lambda **explicit**, bạn chỉ định kiểu tham số trong lambda và Java đối chiếu nó với SAM. Việc viết tường minh có thể hữu ích ở call site phức tạp, khi overload resolution cần thêm thông tin; nhưng nếu kiểu đích đã rõ, phiên bản implicit thường ngắn gọn và dễ bảo trì.

**Không trộn kiểu tham số trong một danh sách lambda:**

```java
// ĐÚNG: cả hai tham số được suy ra từ BiFunction.
BiFunction<String, String, String> join1 =
        (left, right) -> left + right;

// ĐÚNG: cả hai tham số có kiểu tường minh.
BiFunction<String, String, String> join2 =
        (String left, String right) -> left + right;

// SAI: trộn explicit và implicit parameter declaration.
// BiFunction<String, String, String> invalid =
//         (String left, right) -> left + right;
```

Đây là các đoạn minh họa; cần `BiFunction`. Một tập tham số lambda phải tuân theo cùng hình thức khai báo hợp lệ. Java không tự lấy kiểu `String` của tham số đầu rồi “đoán” rằng mọi tham số không khai báo cũng là `String`.

### Target quyết định kiểu trả về và checked exceptions

Một lambda chỉ hợp lệ khi body cung cấp kết quả tương thích kiểu trả về của SAM:

```java
Predicate<String> valid = s -> s.length() > 2;

// SAI: Function<String,Integer> cần Integer, không phải boolean.
// Function<String,Integer> invalid = s -> s.length() > 2;
```

Ví dụ minh họa. Với **checked exception**, SAM cũng quyết định lambda có được ném ra ngoài hay không:

```java
// SAI: Files.readString(Path) có thể ném IOException,
// nhưng Function.apply không khai báo checked IOException.
// Function<Path, String> read = Files::readString;
```

Đây là ví dụ lỗi đã comment; `Files.readString` có từ Java 11. Nếu cần đọc file, bạn có thể tạo phương thức riêng có contract lỗi phù hợp hoặc xử lý `IOException` có chủ đích tại tầng I/O. Không nên nuốt ngoại lệ chỉ để biến biểu thức thành lambda ngắn.

Ví dụ minh họa về xử lý rõ ràng:

```java
static String readRequired(Path path) throws IOException {
    return Files.readString(path);
}
```

Đây là **phương thức minh họa**, cần import `java.nio.file.Files`, `Path` và `java.io.IOException`, và một class chứa phương thức. Việc truyền hành vi ném checked exception đòi một functional interface có method khai báo `throws` tương ứng, hoặc code bắt exception tại ranh giới phù hợp.

## 8. Method reference: cùng ký pháp, nhiều target type hợp lệ

Method reference mô tả tham chiếu tới một method hoặc constructor; compiler chọn declaration tương ứng dựa trên target SAM và các quy tắc giải quyết phương thức.

### Static method reference

```java
Function<String, Integer> parse = Integer::parseInt;
ToIntFunction<String> parsePrimitive = Integer::parseInt;
```

Đây là minh họa cần `Function` và `ToIntFunction`. `Integer.parseInt` trả primitive `int`. Khi target là `Function<String,Integer>`, kết quả được boxing thành `Integer`; khi target là `ToIntFunction<String>`, kết quả giữ `int`. Ngữ cảnh không tự loại bỏ yêu cầu kiểm tra lỗi: dữ liệu không phải số có thể gây `NumberFormatException`.

### Unbound instance method reference

```java
Function<String, String> trim = String::trim;
ToIntFunction<String> length = String::length;
```

Các method reference dạng `TypeName::instanceMethod` tương ứng với việc nhận receiver là **đối số đầu tiên** của SAM: `text -> text.trim()` hoặc `text -> text.length()`. Trong ví dụ thứ hai, `String::length` không phải static method; receiver được đưa vào qua tham số `String` của `ToIntFunction`.

### Bound instance method reference

```java
String message = "  Java  ";
Supplier<String> trimFixed = message::trim;
String value = trimFixed.get(); // "Java"
```

Đây là minh họa cần `Supplier`. Receiver `message` được gắn khi tạo method reference, còn việc gọi method diễn ra khi gọi `get()`. Không thể gán `message::trim` cho `Function<String,String>` chỉ vì method có tên `trim`; target phải khớp số tham số: tham chiếu bound này không cần tham số SAM.

Nếu receiver của bound reference là `null` trong trường hợp instance method tương ứng, phép đánh giá reference có thể ném `NullPointerException` ngay khi tạo; với unbound reference, null receiver được đưa tới lúc gọi có thể gây lỗi khi thực thi. Đừng nhầm hai thời điểm.

### Constructor reference

```java
Supplier<StringBuilder> emptyBuilder = StringBuilder::new;
Function<String, StringBuilder> fromText = StringBuilder::new;
IntFunction<String[]> arrayFactory = String[]::new;
```

Đây là minh họa cần `Supplier`, `Function`, `IntFunction`. Target SAM quyết định constructor hoặc hành vi tạo mảng phù hợp. `StringBuilder::new` có thể trỏ tới constructor không tham số hoặc constructor nhận `String`; `String[]::new` nhận độ dài `int` và trả mảng `String[]`.

**Chỉ có target type mới quyết định đầy đủ ý nghĩa một method/constructor reference.** Không nên cho rằng một cú pháp `::` tương ứng đúng một chữ ký cố định, đặc biệt khi method hoặc constructor có overload.

## 9. Cast tường minh có thể chọn overload nhưng cũng có giới hạn

Trong ví dụ `choose(Supplier<String>)` và `choose(Callable<String>)`, cast giúp làm rõ vì hai overload đều có thể nhận `() -> "ok"`. Nhưng cast không phải công cụ để “ép” một SAM có chữ ký không tương thích.

```java
// SAI: Runnable.run trả void, literal "hello" không phải
// statement expression phù hợp với Runnable.
// Runnable invalid = (Runnable) () -> "hello";

// ĐÚNG:
Supplier<String> valid = (Supplier<String>) () -> "hello";
```

Ví dụ minh họa. Java không bỏ qua kiểm tra kiểu chỉ vì có cast. Cast cũng **không làm mất checked exception**, không tạo ra overload mới và không đổi ngữ nghĩa đối tượng lambda thành một kiểu class không liên quan.

### Intersection cast: trường hợp nâng cao

Một intersection type có thể mô tả functional interface cùng một hoặc nhiều marker interface tương thích:

```java
Runnable identifiable = (Runnable & java.io.Serializable)
        () -> System.out.println("run");
```

Đây là minh họa hợp lệ: `Runnable` cung cấp SAM, còn `Serializable` là marker interface. Tuy nhiên, **không nên mặc định serialize lambda** để lưu trữ lâu dài hoặc trao đổi giữa các phiên bản ứng dụng; dạng serialize của lambda có tính nhạy cảm với chi tiết triển khai và thay đổi code. Intersection cast có ích trong một số API chuyên biệt, không phải kỹ thuật mặc định cho target typing.

Một intersection chứa hai interface có hai SAM khác nhau và không thể hợp thành một functional interface **không tự trở thành target hợp lệ** cho lambda chỉ vì dùng toán tử `&`.

## 10. Những ngữ cảnh liên quan khác: return, array initializer và conditional expression

Đề bài tập trung phép gán, tham số và ép kiểu; nhưng target typing cũng xuất hiện khi bạn trả về lambda từ một method, đặt lambda vào khởi tạo mảng functional interface hoặc dùng conditional expression có target rõ ràng.

### Return context

```java
static Predicate<String> nonBlankRule() {
    return text -> text != null && !text.isBlank();
}
```

Đây là phương thức minh họa cần `Predicate`, đặt trong một class. Kiểu return đã khai báo `Predicate<String>` cung cấp target cho lambda.

### Khởi tạo mảng functional interface

```java
@SuppressWarnings("unchecked")
Function<String, String>[] stages = new Function[] {
        (Function<String, String>) String::trim,
        (Function<String, String>) String::toUpperCase
};
```

Đây là **đoạn minh họa kỹ thuật** nhưng không phải cách khuyến nghị lưu trữ generic functional interface: Java không hỗ trợ tạo trực tiếp mảng generic reifiable tương ứng; mảng thô sinh unchecked warning và có nguy cơ heap pollution. Thực tế nên dùng `List<Function<String,String>>` với target type rõ:

```java
List<Function<String, String>> steps = List.of(
        String::trim,
        String::toUpperCase
);
```

Đoạn minh họa cần `List` và `Function`. Các phần tử method reference được kiểm tra trong ngữ cảnh generic argument do `List.of` cung cấp và suy luận kiểu.

### Conditional expression có target type

```java
boolean removeOuterSpace = true;
Function<String, String> normalizer =
        removeOuterSpace ? String::trim : String::toUpperCase;
```

Đây là minh họa. Khi phép toán điều kiện nằm trong ngữ cảnh target typing thích hợp, cả hai nhánh có thể được kiểm tra theo `Function<String,String>`. Nếu bỏ kiểu target và chỉ viết một biểu thức `?:` chứa method reference mà không có thông tin kiểu thích hợp, compiler không thể tùy ý đoán một functional interface.

## 11. Ví dụ Java 17+ hoàn chỉnh: ba ngữ cảnh trong một chương trình

Ví dụ sau chỉ dùng API JDK, có đủ:

- Phép gán `Function`/`Predicate`, suy luận tham số lambda.
- Truyền lambda và method reference làm đối số của các method thường và generic.
- Dùng ép kiểu để chọn đúng một overload giữa `Supplier` và `Callable`.
- Chuyển `Stream<String>` bằng method reference, không cần cast.
- Trường hợp `Object` lưu một lambda đã có target type.
- Sử dụng `var` an toàn **khi có cast**.
- Kiểm tra cả `Function<String,Integer>` và `ToIntFunction<String>` với cùng method reference.

Lưu nguyên đoạn vào **TargetTypingContextsDemo.java**:

```java
import java.util.List;
import java.util.function.Function;
import java.util.function.Predicate;
import java.util.function.Supplier;
import java.util.function.ToIntFunction;
import java.util.concurrent.Callable;

public class TargetTypingContextsDemo {

    static void inspect(String input, Predicate<String> condition) {
        System.out.println("Accepted: " + condition.test(input));
    }

    static <T, R> List<R> transform(
            List<T> input, Function<? super T, ? extends R> mapper) {
        return input.stream().map(mapper).toList();
    }

    static String choose(Supplier<String> action) {
        return "Supplier:" + action.get();
    }

    static String choose(Callable<String> action) throws Exception {
        return "Callable:" + action.call();
    }

    public static void main(String[] args) throws Exception {
        // 1. Assignment context.
        Function<String, Integer> length = s -> s.length();
        Predicate<String> nonEmpty = s -> !s.isEmpty();

        System.out.println("Length: " + length.apply("Java"));
        System.out.println("NonEmpty: " + nonEmpty.test(""));

        // 2. Invocation context.
        inspect("Lambda", s -> s.length() >= 5);
        List<Integer> lengths =
                transform(List.of("An", "Binh", "Chi"), String::length);
        System.out.println("Mapped: " + lengths);

        // 3. Casting context selects one of two overloads.
        System.out.println(choose(
                (Supplier<String>) () -> "ready"));
        System.out.println(choose(
                (Callable<String>) () -> "ready"));

        // 4. Method references adapt to their target SAM.
        Function<String, Integer> boxedLength = String::length;
        ToIntFunction<String> primitiveLength = String::length;
        System.out.println("Boxed: " + boxedLength.apply("Java"));
        System.out.println("Primitive: " +
                primitiveLength.applyAsInt("Java"));

        // 5. Cast supplies the type before assigning to Object.
        Object task = (Runnable) () ->
                System.out.println("Runnable: executed");
        ((Runnable) task).run();

        // 6. var can infer from a typed cast expression.
        var trim = (Function<String, String>) String::trim;
        System.out.println("Trimmed: " + trim.apply("  hi  "));

        // 7. A typed lambda variable avoids overload ambiguity.
        Supplier<String> fixed = () -> "typed";
        System.out.println(choose(fixed));
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac TargetTypingContextsDemo.java
java TargetTypingContextsDemo
```

**Stdout chính xác:**

```text
Length: 4
NonEmpty: false
Accepted: true
Mapped: [2, 4, 3]
Supplier:ready
Callable:ready
Boxed: 4
Primitive: 4
Runnable: executed
Trimmed: hi
Supplier:typed
```

**Từng dòng được giải thích:**

1. Trong `Function<String,Integer> length = s -> s.length()`, target quy định `s` là `String`, trả `Integer` nhờ boxing từ `int`; `"Java"` dài `4`.
2. `Predicate<String> nonEmpty` kiểm tra chuỗi rỗng nên `test("")` trả `false`.
3. `inspect` nhận `Predicate<String>`: `s.length() >= 5` là `true` đối với `"Lambda"` (sáu ký tự).
4. `transform` là generic method. `String::length` được target typed theo mapper của `Stream<String>`, cho danh sách `[2,4,3]`. `Stream.toList()` chỉ thay đổi cách thu thập kết quả, không thay đổi quy tắc target typing.
5. Cả `Supplier<String>` và `Callable<String>` đều nhận lambda không tham số trả chuỗi; cast tường minh chỉ định overload. `Callable.call()` có checked exception trong chữ ký; method `main` khai báo `throws Exception` cho ví dụ.
6. `boxedLength` và `primitiveLength` cùng trỏ method `String.length()`, nhưng kiểu trả về của các SAM lần lượt là `Integer` và `int`.
7. `(Runnable) () -> ...` đặt target trước khi lưu vào `Object`. Cast trở lại `Runnable` giúp gọi `run()`.
8. `var trim` suy luận kiểu từ biểu thức cast có kiểu `Function<String,String>`, không từ method reference đứng một mình.
9. `fixed` có kiểu tĩnh `Supplier<String>`, do đó lời gọi `choose(fixed)` không còn nhập nhằng.

## 12. Checklist khi compiler không suy luận được kiểu

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý có chủ đích |
| --- | --- | --- |
| `var f = x -> ...` bị lỗi | Lambda không có target type | Khai báo `Function<...> f` hoặc interface SAM phù hợp |
| `Object f = () -> ...` bị lỗi | `Object` không phải functional interface | Gán trực tiếp cho SAM, hoặc cast lambda về SAM trước |
| `method(() -> ...)` báo ambiguous | Nhiều overload nhận các SAM ngang hàng | Tạo biến có kiểu hoặc cast vào SAM cần chọn |
| Lambda body trả sai loại | Kết quả không khớp SAM | Xem lại `Function`/`Predicate`/`Consumer` và phép chuyển đổi |
| `String::length` không hợp lệ | Target yêu cầu số tham số/kiểu không phù hợp | Kiểm tra SAM; chọn `Function<String,Integer>` hay `ToIntFunction<String>` |
| Parameter lambda tường minh không khớp | Kiểu khai báo khác tham số SAM | Khai báo đúng hoặc dùng implicit lambda |
| Checked exception từ method reference | SAM không khai báo `throws` tương ứng | Xử lý tại tầng I/O hoặc định nghĩa contract ném lỗi |
| Kết quả `Consumer` bị “mất” | Statement expression void-compatible nên bỏ giá trị trả về | Dùng `Function` khi thực sự cần phép biến đổi |
| `var` với method reference báo lỗi | Không có ngữ cảnh target | Khai báo SAM rõ ràng |
| Nhiều generic constraints khiến suy luận khó | Target chưa đủ thông tin hoặc có overload | Đặt biến mapper có kiểu, bổ sung type witness khi phù hợp, giảm overload |

### Quy trình xác định kiểu bằng tay

1. **Tìm vị trí biểu thức:** RHS phép gán, đối số lời gọi, trong cast, return hay ngữ cảnh khác?
2. **Tìm target type:** nhìn khai báo biến hoặc chữ ký method được chọn, không đoán từ tên lambda.
3. **Đọc SAM:** có bao nhiêu tham số, kiểu mỗi tham số, kiểu return và checked exceptions?
4. **Thay lambda bằng chữ ký cụ thể:** `s -> s.length()` trở thành “nhận `String`, trả `Integer`/`int`” hay một hợp đồng khác?
5. **Kiểm tra body:** kiểu trả về, đường đi của `return`, void compatibility, boxing/unboxing, `null`.
6. **Nếu là lời gọi overloaded:** xác định những overload khả dụng và most-specific method; nếu nhập nhằng, dùng biến có kiểu hoặc cast.
7. **Nếu là generic method:** xem ràng buộc type arguments từ đối số, mapper và ngữ cảnh nhận kết quả; đừng giả định compiler suy ra mọi ý định nghiệp vụ.
8. **Biên dịch thử ví dụ nhỏ:** thêm unit test cho lựa chọn overload/cast quan trọng thay vì dựa vào trực giác.

## 13. Bài tập thực hành có đáp án định hướng

**Bài 1 — phép gán.** Viết `Function<String,Integer>` nhận chuỗi và trả số ký tự, không ghi kiểu tham số trong lambda. **Đáp án:** `Function<String,Integer> length = s -> s.length();`. Tên `s` được suy ra là `String`.

**Bài 2 — tham số.** Cho `static boolean check(String s, Predicate<String> p)` trả `p.test(s)`. Gọi hàm để kiểm tra chuỗi bắt đầu bằng chữ `J`. **Gợi ý:** `check("Java", text -> text.startsWith("J"))`.

**Bài 3 — ép kiểu.** Tạo `Object action` chứa một lambda không tham số in dòng `"go"`. Sau đó gọi nó. **Đáp án:** `Object action = (Runnable) () -> System.out.println("go"); ((Runnable) action).run();`.

**Bài 4 — overload.** Có `choose(Supplier<String>)` và `choose(Callable<String>)`. Vì sao `choose(() -> "ok")` không được chọn tự động? **Đáp án:** cả hai functional interface không có quan hệ subtype ưu tiên, cùng khớp lambda không tham số trả `String`; cần biến có kiểu hoặc cast.

**Bài 5 — var.** Tại sao `var f = String::length;` lỗi dù có thể thấy ý nghĩa `length`? **Đáp án:** method reference là poly expression cần target type. Viết `ToIntFunction<String> f = String::length;`.

**Bài 6 — void và value.** Giải thích vì sao `Consumer<String> c = s -> s.trim();` có thể hợp lệ nhưng không làm người gọi nhận chuỗi đã chuẩn hóa. **Đáp án:** lời gọi `trim()` là statement expression void-compatible; giá trị `String` trả về bị bỏ đi. Dùng `Function<String,String>` và gọi `apply` nếu cần kết quả.

**Bài 7 — method reference gắn receiver.** So sánh `String::trim` khi target là `Function<String,String>` với `value::trim` khi target là `Supplier<String>`. **Đáp án:** trường hợp đầu truyền receiver qua tham số; trường hợp sau receiver được gắn sẵn, SAM không cần tham số.

**Bài 8 — generic mapper.** Cho `List<String> names = List.of("A", "Java")`, viết `names.stream().map(String::length).toList()` và cho biết kiểu/dữ liệu đầu ra. **Đáp án:** `List<Integer>` chứa `[1,4]` nếu biến nhận được khai báo tương ứng.

## 14. Kết luận

**Target typing** giải thích tại sao lambda và method reference thường viết rất ngắn mà vẫn type-safe:

- Trong **phép gán**, target nằm ở kiểu biến hoặc trường.
- Trong **lời gọi**, target đến từ tham số được chọn; generic inference và overload resolution có thể ảnh hưởng.
- Trong **cast**, lập trình viên chỉ rõ functional interface đích và có thể giải quyết overload nhập nhằng.
- Lambda và method reference **không tự có một kiểu SAM cố định khi thiếu target**, nên `var f = ...` hoặc `Object f = ...` thường không hợp lệ nếu dùng trực tiếp.
- Kiểu tham số, kiểu trả về, checked exception và quy tắc void/value compatibility đều được kiểm tra. Cast **không** bỏ qua các quy tắc đó.

Mục tiêu khi viết mã không phải “làm compiler chịu nhận” bằng cast liên tiếp, mà là **đưa hợp đồng functional interface vào đúng nơi**: kiểu biến rõ ràng, chữ ký API dễ hiểu, overload tránh nhập nhằng và test chứng minh hành vi.

### Tài liệu chính thức

- [Java Language Specification (JLS) `15.27.3 — Type of a Lambda Expression](https://docs.oracle.com/javase/specs/jls/se25/html/jls-15.html#jls-15.27.3)
- [JLS `15.13.2 — Type of a Method Reference](https://docs.oracle.com/javase/specs/jls/se25/html/jls-15.html#jls-15.13.2)
- [JLS `15.12.2 — Compile-Time Method Resolution](https://docs.oracle.com/javase/specs/jls/se25/html/jls-15.html#jls-15.12.2)
- [JLS `5.2 — Assignment Contexts](https://docs.oracle.com/javase/specs/jls/se25/html/jls-5.html#jls-5.2)
- [JLS `5.3 — Strict Invocation Contexts](https://docs.oracle.com/javase/specs/jls/se25/html/jls-5.html#jls-5.3)
- [JLS `5.5 — Casting Contexts](https://docs.oracle.com/javase/specs/jls/se25/html/jls-5.html#jls-5.5)
- [Java SE 25 — java.util.function](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/function/package-summary.html)
