# Lambda trả về `void` và biểu thức có thể dùng như câu lệnh trong Java

## 1. Vấn đề cần hiểu

Trong Java, lambda không tự mang một kiểu độc lập như “hàm trả void” hay “hàm trả số”. **Kiểu đích (target type)** là một *functional interface* sẽ quyết định kiểu tham số và kiểu kết quả mà lambda phải đáp ứng. Khi phương thức trừu tượng duy nhất của interface trả về `void`, thân lambda có thể là:

- **Expression body**: một *statement expression* (biểu thức được phép đứng riêng thành câu lệnh Java), ví dụ gọi phương thức `System.out.println(...)`, `list.add(...)`, phép gán hoặc tăng biến.
- **Block body**: khối lệnh `{ ... }` phù hợp với ngữ nghĩa `void`; các `return` có thể xuất hiện phải có dạng `return;`, không mang giá trị.

Điểm dễ nhầm: **một phương thức được gọi trong lambda có thể trả giá trị, nhưng giá trị đó được phép bỏ qua khi target type trả `void`**. Vì thế `value -> list.add(value)` hợp lệ với `Consumer<String>` dù `List.add` trả về `boolean`.

Ngược lại, `value -> value + "!"` **không** hợp lệ với `Consumer<String>`: phép nối chuỗi thuần túy không phải *statement expression*. Muốn trả chuỗi đó, dùng `Function<String, String>`; muốn thực hiện hành động, gọi một phương thức hoặc viết block.

### Vì sao kiến thức này quan trọng?

Nó giải thích cách viết ngắn gọn khi truyền lambda vào `Runnable`, `Consumer<T>`, `forEach`, callback, event handler; giúp đọc đúng thông báo lỗi compiler khi lambda có câu lệnh `return`; và phòng tránh nhầm lẫn giữa “hàm thực hiện hành động” với “hàm tính kết quả”. Đây là quy tắc cú pháp của ngôn ngữ Java, không riêng về Stream API.

## 2. Hai nhóm functional interface phổ biến

| Interface | Phương thức trừu tượng | Kiểu kết quả | Ví dụ lambda |
| --- | --- | --- | --- |
| `Runnable` | `void run()` | `void` | `() -> System.out.println("Run")` |
| `Consumer<T>` | `void accept(T value)` | `void` | `s -> System.out.println(s)` |
| `BiConsumer<T,U>` | `void accept(T left, U right)` | `void` | `(a, b) -> System.out.println(a + b)` |
| `Function<T,R>` | `R apply(T value)` | `R` | `s -> s.length()` với `R = Integer` |
| `Supplier<T>` | `T get()` | `T` | `() -> "READY"` |
| `Predicate<T>` | `boolean test(T value)` | `boolean` | `s -> s.isBlank()` |

`Runnable` thuộc `java.lang`, các interface còn lại trong bảng thuộc `java.util.function`. `Runnable` không nhận đầu vào; `Consumer<T>` nhận một đầu vào và trả `void`; `BiConsumer<T,U>` nhận hai đầu vào và trả `void`.

Ví dụ:

```java
Runnable task = () -> System.out.println("Run");
Consumer<String> printer = text -> System.out.println(text);
Function<String, Integer> length = text -> text.length();

task.run();                // Run
printer.accept("Java");    // Java
System.out.println(length.apply("Java")); // 4
```

Đây là các câu lệnh để đặt trong phương thức hoặc `jshell`; cần import `java.util.function.Consumer` và `java.util.function.Function`. Khi được gọi, `task.run()` và `printer.accept(...)` không trả một kết quả để gán biến; `length.apply(...)` có trả `Integer`.

## 3. Expression lambda: vì sao một số biểu thức dùng được với `void`?

Cấu trúc expression lambda:

```java
(parameters) -> expression
```

Java định nghĩa **void-compatible expression lambda** là lambda có thân expression thuộc loại **statement expression**. Đó là biểu thức mà ngữ pháp Java cho phép viết thành một *expression statement* bằng cách thêm dấu `;`.

Các loại statement expression theo ngữ pháp Java:

| Loại | Ví dụ đứng riêng thành câu lệnh | Ghi chú |
| --- | --- | --- |
| Gán | `state[0] = 5;` | Giá trị biểu thức gán có thể bị bỏ |
| Tiền tố tăng/giảm | `state[0]++;` viết dạng `++state[0];` | Thực hiện thay đổi trước/sau khi trả giá trị |
| Hậu tố tăng/giảm | `state[0]++;` hoặc `state[0]--;` | Giá trị trả ra không buộc phải sử dụng |
| Gọi phương thức | `list.add("A");`, `text.trim();`, `System.out.println(text);` | Kết quả, nếu có, được phép bỏ |
| Khởi tạo đối tượng bằng `new` | `new StringBuilder("A");` | Có thể tạo đối tượng mà không dùng tham chiếu kết quả |

Bảng có cả tiền tố và hậu tố `++`/`--`. Đối với lambda, phải đồng thời tuân thủ các quy tắc khác của Java, nhất là không được gán lại biến cục bộ đang được capture nếu biến đó không còn *effectively final*. Có thể dùng một trường hoặc một phần tử mảng cho ví dụ tăng/giảm, nhưng khi làm vậy cần xem xét trạng thái thay đổi và an toàn luồng.

**Không phải statement expression**: literal `42`, tham chiếu biến đơn thuần `value`, toán tử cộng `a + b`, so sánh `a > b`, phép toán logic, biểu thức điều kiện `condition ? left : right`. Các biểu thức này có thể trả một giá trị và phù hợp với functional interface cần giá trị, nhưng không phù hợp làm *expression body* cho interface trả `void`.

### Lời gọi trả giá trị vẫn phù hợp `void`

```java
List<String> names = new ArrayList<>();

Consumer<String> addName = name -> names.add(name);
Consumer<String> trimButIgnore = name -> name.trim();

addName.accept("Lan");
trimButIgnore.accept("  Lan  ");
System.out.println(names); // [Lan]
```

Hai lambda đều biên dịch: `names.add(name)` là method invocation trả `boolean` và `name.trim()` là method invocation trả `String`. Vì target type là `Consumer<String>`, **giá trị trả về bị bỏ qua**.

Tuy vậy, `trimButIgnore` hầu như vô ích: `String` là bất biến, `trim()` trả một chuỗi khác nhưng không có ai sử dụng. Nếu muốn chuyển chuỗi thành dữ liệu mới, nên dùng:

```java
Function<String, String> trim = String::trim;
String cleaned = trim.apply("  Lan  "); // "Lan"
```

Đây là sự khác nhau giữa **hợp lệ về cú pháp** và **có ý nghĩa về nghiệp vụ**.

### Những biểu thức không hợp lệ cho `void`

Các đoạn sau cố ý minh họa **lỗi biên dịch**, không đặt vào chương trình chạy:

```java
// SAI: chỉ là phép cộng, không phải statement expression.
Consumer<Integer> bad1 = x -> x + 1;

// SAI: chỉ là tham chiếu biến, không phải statement expression.
Consumer<String> bad2 = x -> x;

// SAI: literal không phải statement expression.
Runnable bad3 = () -> 42;
```

Sửa theo mục đích:

```java
Function<Integer, Integer> plusOne = x -> x + 1;
Consumer<Integer> printNext = x -> System.out.println(x + 1);
Runnable print42 = () -> System.out.println(42);
```

Ở dòng `printNext`, phép cộng xuất hiện **bên trong đối số của lời gọi phương thức**, còn toàn bộ thân lambda là `System.out.println(...)`, tức một method invocation hợp lệ làm statement expression.

## 4. Block lambda: `return;` và `return expression;` khác nhau thế nào?

Với block lambda, ta dùng cú pháp:

```java
(parameters) -> {
    statement1;
    statement2;
}
```

Khi target method trả `void`, block phải **void-compatible**: mọi câu lệnh `return` nằm trong block (nếu có) đều phải là `return;`. Block có thể kết thúc bình thường mà không cần `return`.

```java
Consumer<String> greet = name -> {
    if (name.isBlank()) {
        return; // Hợp lệ: dừng sớm, không trả giá trị.
    }
    System.out.println("Hello, " + name);
};

greet.accept("Lan"); // Hello, Lan
greet.accept("");    // Không in gì
```

Trái lại, khi target type yêu cầu kết quả như `Function<String,Integer>`, block thường phải `return` đúng kiểu cho mọi đường đi có thể hoàn thành bình thường:

```java
Function<String, Integer> count = text -> {
    String cleaned = text.trim();
    return cleaned.length();
};
System.out.println(count.apply(" Java ")); // 4
```

Các ví dụ sai:

```java
// SAI: Consumer có kết quả void, không cho return có giá trị.
Consumer<String> bad = text -> {
    return text.length();
};

// SAI: Function yêu cầu Integer nhưng block kết thúc mà không trả.
Function<String, Integer> alsoBad = text -> {
    text.length();
};
```

Nếu lambda trả về giá trị nhưng không phải block, expression body có thể viết ngắn gọn `text -> text.length()`. Nếu block có điều kiện, đảm bảo các nhánh cần thiết trả về kết quả, ném exception hoặc không hoàn thành bình thường; không được để một đường đi có thể kết thúc mà thiếu `return`.

### Lưu ý về void-compatible và value-compatible

Java phân biệt hai khái niệm khi kiểm tra **block lambda**:

- **Void-compatible block**: tất cả `return` (nếu có) là `return;`.
- **Value-compatible block**: block không thể hoàn thành bình thường, và mọi `return` (nếu có) đều trả về một expression.

Ví dụ `x -> { return x.length(); }` phù hợp với `Function<String,Integer>`. Ví dụ `x -> { System.out.println(x); }` phù hợp với `Consumer<String>` và không phù hợp với `Function<String,Integer>` vì không trả giá trị. Với block **chỉ ném exception** như `() -> { throw new IllegalStateException(); }`, cả hai phép kiểm tra tương thích có thể được thỏa; điều này có ý nghĩa khi trình biên dịch chọn overload.

Đối với **expression lambda**, một expression có giá trị như lời gọi `String::trim` có thể vừa dùng làm kết quả của `Function`, vừa được xem là statement expression để dùng với `Consumer`. Vì thế không thể suy ra target type chỉ từ tên phương thức được gọi trong thân lambda; phải nhìn vào ngữ cảnh gán hoặc tham số phương thức nhận lambda.

## 5. Ví dụ Java 17 hoàn chỉnh: Consumer, Runnable và Function

Bài toán: xử lý một số mã đơn. Có thao tác *lưu mã vào danh sách*, *ghi log*, *kiểm tra đầu vào*, *chuyển dữ liệu* và *tạo báo cáo*. Ví dụ chủ ý cho thấy sự khác biệt giữa một lambda thực hiện side effect và một lambda trả kết quả.

Tạo tệp **`VoidLambdaDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.function.Consumer;
import java.util.function.Function;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class VoidLambdaDemo {
    @FunctionalInterface
    interface Action {
        void run();
    }

    static void execute(Action action) {
        action.run();
    }

    public static void main(String[] args) {
        List<String> history = new ArrayList<>();

        // List.add trả boolean nhưng Consumer.accept trả void.
        Consumer<String> save = value -> history.add(value);
        Consumer<String> log =
                value -> System.out.println("Saved: " + value);

        // Hai Consumer được thực hiện theo đúng thứ tự.
        save.andThen(log).accept("A01");

        // Runnable: gọi một phương thức in (trả void).
        Runnable count =
                () -> System.out.println("Count: " + history.size());
        count.run();

        // Block lambda trả void và có return; hợp lệ.
        Action insertThenLog = () -> {
            history.add("A02");
            System.out.println("Inserted: " + history.size());
            return;
        };
        execute(insertThenLog);

        // return; chỉ dừng hành động của Consumer, không trả dữ liệu.
        Consumer<String> verify = value -> {
            if (value.isBlank()) {
                System.out.println("Skipped blank");
                return;
            }
            System.out.println("Checked: " + value);
        };

        verify.accept("");
        verify.accept("BOOK");

        // Function có kết quả rõ ràng, không phụ thuộc history.
        Function<String, String> normalize =
                value -> value.trim().toUpperCase(Locale.ROOT);
        System.out.println("Mapped: " + normalize.apply("  book  "));

        // Method invocation history.set trả String nhưng bỏ kết quả.
        Runnable changeFirst = () -> history.set(0, "A01*");
        changeFirst.run();
        System.out.println("History: " + history);

        // map chuyển dữ liệu; collect gom kết quả; không thay đổi nguồn.
        String joined = Stream.of("pen", "book")
                .map(value -> value.toUpperCase(Locale.ROOT))
                .collect(Collectors.joining(","));
        System.out.println("Joined: " + joined);
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 VoidLambdaDemo.java
java VoidLambdaDemo
```

**Stdout xác định của chương trình:**

```text
Saved: A01
Count: 1
Inserted: 2
Skipped blank
Checked: BOOK
Mapped: BOOK
History: [A01*, A02]
Joined: PEN,BOOK
```

Giải thích kết quả:

1. `save.andThen(log).accept("A01")` gọi `save` trước để thêm `"A01"` vào `history`, sau đó mới gọi `log` để in. `List.add` trả `true`/`false` theo contract của collection nhưng `Consumer` không giữ giá trị ấy.
2. `count.run()` in kích thước 1. Nội dung của `history` được quan sát lúc chạy `run()`, không phải lúc tạo lambda.
3. `insertThenLog` thêm `"A02"`, in kích thước 2, rồi `return;` kết thúc block. Không có giá trị trả về.
4. `verify.accept("")` in “Skipped blank” và trở ra ngay; `verify.accept("BOOK")` in dòng kiểm tra bình thường.
5. `normalize.apply("  book  ")` trả `"BOOK"` vì `trim` bỏ khoảng trắng hai đầu và `toUpperCase(Locale.ROOT)` chuyển chữ hoa. Chữ hoa theo `Locale.ROOT` tránh phụ thuộc cấu hình locale mặc định của máy.
6. `history.set(0, "A01*")` trả về phần tử cũ là `"A01"`, nhưng `Runnable` bỏ qua giá trị đó; kết quả cuối danh sách là `[A01*, A02]`.
7. `Stream.map(...)` trả các giá trị `"PEN"` và `"BOOK"`, `Collectors.joining(",")` ghép thành `"PEN,BOOK"`.

Tất cả thao tác trên `history` chạy tuần tự trong một thread ở ví dụ này. `ArrayList` không tự an toàn cho cập nhật đồng thời; không suy ra `history` dùng được trực tiếp từ nhiều callback chạy song song.

## 6. `Consumer.andThen` và chuỗi hành động trả `void`

`Consumer<T>` cung cấp phương thức mặc định `andThen(Consumer<? super T> after)`, cho phép tạo một `Consumer` mới thực hiện hai hành động theo thứ tự.

```java
Consumer<String> first =
        text -> System.out.println("first: " + text);
Consumer<String> second =
        text -> System.out.println("second: " + text);

Consumer<String> chain = first.andThen(second);
chain.accept("A");
// first: A
// second: A
```

Đừng nhầm với `Function.andThen(...)`:

- `Consumer.andThen` ghép **hai hành động**, mỗi hành động nhận cùng giá trị đầu vào, trả `void`.
- `Function.andThen` ghép **hai phép biến đổi**, kết quả hàm đầu được truyền làm đầu vào hàm sau.

Nếu `first.accept(...)` ném exception, `second` không chạy. `andThen` không tự rollback side effect đã xảy ra; nếu lưu dữ liệu rồi gọi API thất bại, cần thiết kế cơ chế xử lý lỗi/giao dịch phù hợp.

## 7. Tham chiếu phương thức cũng có thể bỏ giá trị trả về

Quy tắc cho phép bỏ qua kết quả không chỉ có ở lambda expression. Khi target type trả `void`, một **method reference** đến phương thức trả giá trị cũng có thể phù hợp:

```java
List<String> names = new ArrayList<>();
Consumer<String> addName = names::add;
addName.accept("An");

Consumer<String> discardTrimmedValue = String::trim;
discardTrimmedValue.accept("  An  ");

System.out.println(names); // [An]
```

`names::add` trỏ đến `List.add` trả boolean. `String::trim` trỏ đến phương thức trả String. Cả hai đều có thể dùng như `Consumer<String>`; kết quả gọi bị bỏ. `discardTrimmedValue` không thay đổi chuỗi đầu vào và không tạo giá trị quan sát được, nên đây là ví dụ hợp lệ về cú pháp nhưng hiếm khi hữu ích.

Ngược lại, nếu mục tiêu là tạo tên đã trim, dùng `UnaryOperator<String> clean = String::trim;` hoặc `Function<String,String> clean = String::trim;`, rồi nhận kết quả từ `apply`.

## 8. Phân biệt “không trả giá trị” với “không có tác dụng phụ”

Hai khái niệm độc lập:

- `void` nghĩa là không có **giá trị trả về từ lời gọi**. Một hàm trả `void` thường được dùng cho hành động, nhưng bản thân chữ `void` không bảo đảm hành động ấy hữu ích hoặc có side effect.
- **Side effect** là tác động ngoài giá trị kết quả, như thay đổi danh sách, ghi file, gửi request, cập nhật biến hoặc in ra console. Hàm trả giá trị vẫn có thể có side effect.

Ví dụ `List.add` trả `boolean` nhưng đồng thời sửa danh sách; `String.trim` trả `String` mới nhưng không sửa chuỗi gốc. Dùng `Consumer<String> c = s -> s.trim();` không khiến `String.trim` trở thành thao tác sửa chuỗi.

Trong phong cách functional programming, phần **tính toán và biến đổi** thường nên trả kết quả qua `Function`/`map`, còn các **hành động cần thiết** nên xuất hiện ở ranh giới rõ ràng như `Consumer` hoặc tầng điều phối. Không nên tận dụng việc Java cho phép bỏ giá trị để vô tình vứt bỏ một kết quả nghiệp vụ quan trọng.

### Không tự cập nhật accumulator chung trong parallel stream

Đoạn sau không đáng tin nếu chạy song song:

```java
// Phản ví dụ: nạp vào một block demo riêng; không chạy chung với main.
List<String> output = new ArrayList<>();
List.of("A", "B", "C").parallelStream()
        .forEach(value -> output.add(value));
```

`output.add(value)` hợp lệ làm expression lambda trả void, nhưng nhiều worker có thể cập nhật cùng một `ArrayList` gây data race, thiếu phần tử, sai thứ tự hoặc hư cấu trúc. Cú pháp hợp lệ không chứng minh an toàn đồng thời.

Nếu mục tiêu là biến đổi thành danh sách mới:

```java
List<String> output = List.of("A", "B", "C")
        .parallelStream()
        .map(value -> value.toLowerCase(Locale.ROOT))
        .toList();
```

Ở đây `map` trả kết quả, `toList()` thu thập theo contract của Stream; danh sách nguồn có encounter order, kết quả giữ thứ tự encounter order trong trường hợp này. `Stream.toList()` cho danh sách không thể sửa qua `add`/`remove`. Không cần tự sửa một collection chia sẻ trong lambda.

Nếu mục tiêu là chỉ in/log, `forEach` có thể hợp lý, nhưng `parallelStream().forEach(...)` không bảo đảm thứ tự thực thi. Dùng `forEachOrdered` khi phải giữ encounter order, và cân nhắc chi phí/side effect trước khi song song hóa.

## 9. Quy tắc capture biến cục bộ và vấn đề trạng thái dùng chung

Một lambda được phép đọc biến cục bộ ở phạm vi ngoài chỉ khi biến đó là `final` hoặc **effectively final** (không được gán lại sau khi khởi tạo):

```java
String prefix = "Order: ";
Consumer<String> log = id -> System.out.println(prefix + id);
log.accept("A01"); // Order: A01
```

Compiler từ chối ví dụ sau:

```java
// SAI: biến local counter bị thay đổi và không effectively final.
int counter = 0;
Runnable increment = () -> counter++;
```

Có thể dùng holder, field hoặc `AtomicInteger` khi thực sự cần cập nhật một trạng thái, nhưng không nên dùng chúng chỉ để qua mặt quy tắc lambda:

```java
int[] counter = {0};
Runnable increment = () -> counter[0]++;
increment.run();
System.out.println(counter[0]); // 1
```

Đoạn này biên dịch nhưng `counter[0]` vẫn là mutable state, có nguy cơ data race nếu nhiều luồng cập nhật. Trong Stream, để đếm phần tử nên dùng `count()`; để cộng số dùng `sum()`/`reduce()`; để thu thập dùng `collect()`/`toList()`. Các phép tổng hợp này biểu đạt rõ mục tiêu và tránh tự quản lý biến tích lũy chia sẻ.

## 10. Trường hợp overload và khả năng tương thích kép

Một **expression lambda có giá trị** thuộc loại statement expression, như lời gọi phương thức `s.trim()`, có thể tương thích cả với target method trả `void` lẫn target method nhận kết quả `String`:

```java
Consumer<String> asAction = s -> s.trim();
Function<String, String> asMapping = s -> s.trim();
```

Cả hai đều hợp lệ, nhưng `asAction` bỏ kết quả trim; `asMapping` giữ nó. Khi hai overload cùng nhận functional interface khác nhau, việc chọn overload còn phụ thuộc *arity*, *target type*, quy tắc *most specific* và nội dung thân lambda. Một lambda dạng lời gọi phương thức trả giá trị có thể gây **lỗi ambiguous method call** khi có nhiều overload phù hợp; không nên chỉ nhìn `->` rồi suy ra overload nào được chọn.

Khi API overload gây khó đọc hoặc lỗi, dùng **biến có kiểu rõ ràng** hoặc **ép kiểu mục tiêu**:

```java
// Tạo biến có kiểu đích rõ ràng:
Consumer<String> action = value -> System.out.println(value);
Function<String, String> convert = String::trim;

// Nếu một API thật sự overload Consumer và Function,
// truyền action hoặc convert giúp chọn đúng overload.
```

Không có hàm overload tự tạo nào được yêu cầu để chạy chương trình `VoidLambdaDemo.java`; phần này là nguyên tắc đọc và xử lý lỗi biên dịch.

## 11. Những lỗi thường gặp

| Mã hoặc suy luận | Vấn đề | Cách đúng |
| --- | --- | --- |
| `Consumer<Integer> c = n -> n + 1;` | `n + 1` không phải statement expression | Dùng `Function<Integer,Integer>` hoặc gọi phương thức xử lý |
| `Runnable r = () -> 10;` | Literal không phải statement expression | `Runnable r = () -> System.out.println(10);` |
| `Consumer<String> c = s -> { return s; };` | Block trả giá trị, target method trả void | Dùng `return;` hoặc `Function` |
| `Function<String,Integer> f = s -> { s.length(); };` | Block hoàn thành bình thường mà không trả kết quả | `return s.length();` |
| `Consumer<String> c = s -> s.trim();` để “chuẩn hóa” | Kết quả của `trim()` bị bỏ | Dùng `Function<String,String>`/`UnaryOperator<String>` |
| `Runnable r = () -> localCounter++;` | Thay đổi biến local được capture, vi phạm effectively final | Chuyển thiết kế sang reduction, hoặc trạng thái có owner rõ ràng |
| `parallelStream().forEach(list::add)` | Có thể đua ghi vào danh sách mutable chung | Dùng `map(...).toList()` hoặc collector phù hợp |
| Cho rằng `void` là “hàm thuần” | `void` chỉ nói về giá trị trả về, không cấm side effect | Đánh giá nội dung và trạng thái mà hàm đọc/ghi |
| Cho rằng `andThen` tự hoàn tác khi lỗi | Side effect của hành động trước không được rollback | Thiết kế xử lý lỗi/giao dịch theo bài toán |

Cần phân biệt **biên dịch được**, **có kết quả mong muốn** và **an toàn với đồng thời**. Đây là ba câu hỏi khác nhau.

## 12. Bài tập tự kiểm tra

1. Với mỗi thân lambda sau, xác định có phải statement expression dùng được với `Runnable`/`Consumer` hay không: `System.out.println("OK")`, `list.add("A")`, `x + 1`, `new StringBuilder("A")`, `state[0]++`, `x > 10`. Giải thích theo loại biểu thức.
2. Viết `Consumer<String>` nhận một chuỗi, in `"empty"` rồi `return;` nếu chuỗi rỗng, ngược lại in chữ hoa. Tạo block lambda có đủ dấu ngoặc và dấu chấm phẩy.
3. Thay `Consumer<String> c = s -> s.trim();` bằng `Function<String,String>`. Dùng `apply("  book  ")` để lấy đúng `"book"`.
4. Dùng `Consumer<String> log = System.out::println` và `Consumer<String> save = list::add`. Tạo `save.andThen(log)` và gọi với `"A01"`; giải thích thứ tự cập nhật và in.
5. Chuyển `Consumer<String> bad = s -> { return s.length(); };` thành hai phiên bản hợp lệ: một phiên bản chỉ in độ dài, một phiên bản trả về độ dài theo `Function<String,Integer>`.
6. Sửa `Function<String,Integer> length = s -> { s.length(); };` để compile, rồi giải thích vì sao bản gốc thiếu giá trị trả về.
7. Với `List.of("A","B","C")`, tạo danh sách mới chứa `"a","b","c"` mà không thêm phần tử vào một `ArrayList` bên ngoài lambda. Kiểm tra bằng `map(...).toList()`.
8. Trong ví dụ `VoidLambdaDemo`, dự đoán thay đổi stdout nếu bỏ `save.andThen(log)` và chỉ gọi `log.accept("A01")`. Vì sao `Count` trở thành 0 và `history.set(0, ...)` sẽ thất bại sau đó? Nêu cách tránh phụ thuộc ẩn này.

**Ghi nhớ:** target type của functional interface quyết định lambda có phải trả giá trị không; expression lambda trả `void` cần một **statement expression**; block lambda trả `void` có thể dùng `return;` nhưng không dùng `return value;`; kết quả của method invocation có thể bị bỏ khi thích ứng với `void`. Trong xử lý dữ liệu, dùng `Function` để tạo kết quả mới và `Consumer` cho hành động có chủ đích, đồng thời kiểm soát tác dụng phụ và shared mutable state.
