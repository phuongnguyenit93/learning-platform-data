# Cú pháp tham số, dấu mũi tên và phần thân của Lambda trong Java

Lambda expression là cách viết ngắn gọn một hành vi để triển khai **phương thức trừu tượng duy nhất** của một *functional interface* (giao diện hàm). Cú pháp lambda xuất hiện từ Java 8 và vẫn là kiến thức thiết yếu của Java hiện đại, đặc biệt khi làm việc với Collections, Stream API, callback và các API nhận hành vi làm đối số.

Bài này giải thích ba thành phần của lambda: **danh sách tham số**, **dấu mũi tên `->`** và **phần thân**. Nắm được ba phần giúp đọc, viết, sửa lỗi biên dịch và lựa chọn cách biểu diễn phù hợp với từng kiểu dữ liệu.

## 1. Cấu trúc cơ bản

```java
(thamSo1, thamSo2, ...) -> bieuThuc

(thamSo1, thamSo2, ...) -> {
    // Các câu lệnh Java
}
```

- **Bên trái `->`**: danh sách tham số đầu vào, phù hợp với số lượng và kiểu tham số của phương thức trừu tượng đích.
- **`->`**: dấu phân tách danh sách tham số với hành vi thực thi.
- **Bên phải `->`**: **một biểu thức** (*expression body*) hoặc **một khối câu lệnh** trong `{ }` (*block body*).
- Lambda cần một **kiểu đích** (*target type*) là functional interface; lambda không tự định nghĩa một phương thức có tên.

Ví dụ, `Function<String,Integer>` có phương thức trừu tượng `Integer apply(String value)`:

```java
Function<String, Integer> length = text -> text.length();
```

`text` là tham số; `->` nối với biểu thức `text.length()`; `String.length()` trả về `int` và Java boxing thành `Integer` cho kiểu kết quả. Lambda được thực thi khi chương trình gọi `length.apply("Java")`, khi đó kết quả là `4`. Biểu thức lambda tự nó không có tên; tên `length` là tên của biến tham chiếu tới hành vi.

## 2. Cú pháp danh sách tham số

### 2.1. Không có tham số: luôn dùng `()`

```java
Runnable task = () -> System.out.println("Đã chạy");
Supplier<Integer> answer = () -> 42;
```

`Runnable.run()` không nhận tham số và trả về `void`; `Supplier.get()` không nhận tham số nhưng trả về giá trị. Không thể bỏ `()` khi danh sách tham số rỗng.

### 2.2. Một tham số: có thể bỏ cặp ngoặc nếu không viết kiểu

```java
Function<String, String> upperA = s -> s.toUpperCase();
Function<String, String> upperB = (s) -> s.toUpperCase();
```

Hai dạng trên tương đương. Khi compiler suy luận được kiểu của một tham số duy nhất, `s -> ...` là dạng gọn và phổ biến. Nếu khai báo kiểu hoặc modifier tường minh, **phải dùng ngoặc tròn**:

```java
Function<String, String> trim = (String s) -> s.trim();
Function<String, String> trimFinal = (final String s) -> s.trim();
```

`String s -> s.trim()` sai cú pháp. Không có kiểu trả về đứng trước danh sách tham số như khai báo một phương thức thông thường.

### 2.3. Từ hai tham số trở lên: bắt buộc có `(...)`

```java
BiFunction<Integer, Integer, Integer> add = (a, b) -> a + b;
Comparator<String> byLength =
        (left, right) -> Integer.compare(left.length(), right.length());
```

Có thể viết kiểu cụ thể cho **tất cả** tham số:

```java
BiFunction<String, Integer, String> label =
        (String name, Integer age) -> name + ": " + age;
```

Dạng `a, b -> a + b` sai; phải viết `(a, b) -> a + b`. Tên `left` và `right` chỉ là tên tham số cục bộ, còn số lượng và kiểu do phương thức trừu tượng của giao diện quyết định.

### 2.4. Suy luận kiểu và khai báo kiểu tường minh

Compiler suy luận kiểu từ functional interface đích:

```java
Predicate<String> hasText = s -> !s.trim().isEmpty();
// s được suy luận là String; biểu thức trả về boolean.

IntUnaryOperator square = (int n) -> n * n;
// n có kiểu tường minh int; applyAsInt trả về int.
```

Trong cùng danh sách tham số, không trộn tham số có kiểu tường minh với tham số được suy luận: `(String first, second) -> ...` không hợp lệ. Chọn `(first, second)` hoặc `(String first, String second)`.

**Cập nhật còn áp dụng:** Java 11+ cho phép `var` trong khai báo tham số lambda:

```java
BiFunction<Integer, Integer, Integer> multiply = (var x, var y) -> x * y;
```

Toàn bộ tham số phải dùng `var` nếu chọn dạng này; không trộn `var` với kiểu tường minh hoặc tham số suy luận. `var` ở đây không có nghĩa rằng kiểu tham số biến đổi ở thời gian chạy; kiểu vẫn được suy luận tĩnh từ ngữ cảnh. Dạng `(var x, var y)` **không hỗ trợ bởi Java 8**. Nếu dự án phải biên dịch với `--release 8`, dùng `(x, y)` hoặc `(Integer x, Integer y)`.

### 2.5. Số lượng và kiểu tham số do functional interface quyết định

| Functional interface | Phương thức trừu tượng | Ví dụ lambda | Ý nghĩa |
| --- | --- | --- | --- |
| `Runnable` | `void run()` | `() -> doWork()` | Không tham số, không giá trị trả về |
| `Supplier<T>` | `T get()` | `() -> "hello"` | Không tham số, có kết quả |
| `Consumer<T>` | `void accept(T value)` | `s -> System.out.println(s)` | Một tham số, trả về `void` |
| `Function<T,R>` | `R apply(T value)` | `s -> s.length()` | Một tham số, có kết quả |
| `Predicate<T>` | `boolean test(T value)` | `n -> n > 0` | Một tham số, trả về boolean |
| `BiFunction<T,U,R>` | `R apply(T a, U b)` | `(a, b) -> a + b` | Hai tham số, có kết quả |
| `IntUnaryOperator` | `int applyAsInt(int x)` | `n -> n * n` | Phép biến đổi `int`, tránh boxing |

Các interface này đều thuộc thư viện Java còn được sử dụng. Ký hiệu `T`, `U`, `R` là type parameter của giao diện, không phải tên tham số trong lambda. Việc chọn interface quyết định compiler cho phép dạng tham số và phần thân nào.

## 3. Vai trò của dấu mũi tên `->`

Dấu `->` đánh dấu ranh giới giữa **khai báo các tham số** ở bên trái và **hành vi thực thi** ở bên phải. Đây không phải phép gán, không phải toán tử so sánh và không phải cú pháp `=>` của ngôn ngữ khác.

```java
Function<Integer, Integer> twice = x -> x * 2;
BinaryOperator<Integer> add = (a, b) -> a + b;
```

Khi gọi `twice.apply(5)`, tham số `x` mang giá trị `5`, phần thân tính `10`. Khi gọi `add.apply(3, 4)`, `a` và `b` nhận giá trị tương ứng. Mỗi tham số chỉ có hiệu lực trong thân lambda; không thể dùng tên tham số đó ngoài phạm vi khai báo.

Lưu ý vị trí dấu `;`:

```java
Function<Integer, Integer> f = x -> x + 1;
Consumer<String> printer = s -> { System.out.println(s); };
```

Ở dòng đầu, `;` kết thúc **câu lệnh khai báo biến**; phần thân biểu thức là `x + 1`. Ở dòng hai, `System.out.println(s);` là câu lệnh **bên trong block**, còn dấu `;` sau `}` kết thúc câu lệnh khai báo biến. Khi lambda được truyền trực tiếp làm đối số phương thức, không tự thêm `;` giữa biểu thức lambda và dấu đóng `)`:

```java
List<Integer> result = numbers.stream()
        .map(n -> n * 2)
        .collect(Collectors.toList());
```

Đoạn mã trên chỉ minh họa cú pháp khi đã có biến `numbers` kiểu `List<Integer>` và import `java.util.stream.Collectors`; nó không phải một chương trình độc lập.

## 4. Phần thân dạng biểu thức (*expression body*)

Dùng expression body khi hành vi chỉ cần một biểu thức:

```java
Function<String, Integer> length = s -> s.length();
Predicate<Integer> positive = n -> n > 0;
BiFunction<Integer, Integer, Integer> max = (a, b) -> Math.max(a, b);
Consumer<String> log = s -> System.out.println(s);
```

Nếu functional interface trả về giá trị, giá trị của biểu thức được **trả về tự động**, không viết `return`:

```java
Function<Integer, Integer> valid = x -> x + 1;

// SAI: return không dùng trực tiếp trong expression body.
// Function<Integer, Integer> invalid = x -> return x + 1;
```

Muốn dùng `return`, chuyển sang block body `x -> { return x + 1; }`. Dấu `;` bên trong một expression body đơn không thuộc biểu thức; dấu `;` ở cuối phép gán nằm bên ngoài lambda.

**Điểm dễ nhầm về `void`:** biểu thức làm body của lambda `void` phải thuộc loại *statement expression* hợp lệ, như lời gọi phương thức, phép gán hoặc tăng/giảm biến. Nếu lời gọi phương thức trả về giá trị, giá trị đó vẫn có thể bị bỏ qua trong ngữ cảnh `void`:

```java
Runnable sayHi = () -> System.out.println("Xin chào");
Runnable discard = () -> System.currentTimeMillis();
Supplier<Long> keep = () -> System.currentTimeMillis();

// SAI: 42 không phải statement expression được phép cho Runnable.
// Runnable invalid = () -> 42;
```

`Runnable` không thể nhận lambda có body đơn là phép tính thuần như `() -> 1 + 2`. Với `Supplier<Integer>`, `() -> 1 + 2` lại hợp lệ vì giao diện mong đợi kết quả.

## 5. Phần thân dạng khối (*block body*)

Khi cần nhiều thao tác, biến tạm, rẽ nhánh hoặc xử lý ngoại lệ, dùng `{ ... }`:

```java
Function<String, Integer> normalizedLength = text -> {
    String normalized = text.trim();
    int n = normalized.length();
    return n;
};

Consumer<String> printer = text -> {
    String normalized = text.trim();
    System.out.println(normalized);
};
```

Đây là các câu lệnh Java bình thường trong khối. Lambda `Function` cần `return n;`; lambda `Consumer` trả về `void` nên không có giá trị trả về.

### 5.1. Quy tắc `return`

- **Expression body với kết quả:** Java dùng giá trị biểu thức làm kết quả; không viết `return`.
- **Block body với kết quả:** dùng `return giaTri;` và bảo đảm **mọi đường đi có thể kết thúc bình thường** đều trả về giá trị.
- **Block body trả về `void`:** không được `return` giá trị; có thể dùng `return;` để thoát sớm.
- `return` nằm trong lambda chỉ kết thúc lần gọi lambda đó, **không** thoát khỏi phương thức đang bao quanh.

```java
Function<Integer, Integer> sign = n -> {
    if (n < 0) {
        return -1;
    }
    if (n == 0) {
        return 0;
    }
    return 1;
};

Consumer<String> printNonBlank = text -> {
    if (text.trim().isEmpty()) {
        return;
    }
    System.out.println(text.trim());
};
```

Ví dụ sai khi dùng cho `Function<Integer,Integer>`: `n -> { if (n > 0) return n; }`. Với `n <= 0`, có đường đi hết block mà không trả về giá trị. Sửa bằng cách thêm `return` cho các trường hợp còn lại hoặc đổi thành expression body có đủ kết quả.

### 5.2. Chọn body biểu thức hay block

Hai cách sau tương đương:

```java
Function<Integer, Integer> a = n -> n + 1;

Function<Integer, Integer> b = n -> {
    return n + 1;
};
```

Dùng expression body cho logic ngắn, dễ đọc. Dùng block khi cần nhiều câu lệnh hoặc điều kiện. Không cần thêm `{ return ...; }` cho biểu thức đơn nếu điều đó không làm rõ ý nghĩa.

## 6. Ví dụ Java hoàn chỉnh, có thể biên dịch và chạy

Lưu file tên **`LambdaSyntaxDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.function.BiFunction;
import java.util.function.Consumer;
import java.util.function.Function;
import java.util.function.IntUnaryOperator;
import java.util.function.Predicate;
import java.util.function.Supplier;

public class LambdaSyntaxDemo {
    public static void main(String[] args) {
        // Không tham số; expression body trả về String.
        Supplier<String> greeting = () -> "Xin chào";

        // Một tham số suy luận; int được boxing thành Integer.
        Function<String, Integer> length = text -> text.length();

        // Hai tham số được suy luận.
        BiFunction<Integer, Integer, Integer> add = (a, b) -> a + b;

        // Một tham số khai báo kiểu tường minh.
        Predicate<String> hasText = (String text) -> !text.trim().isEmpty();

        // Block body với nhiều nhánh và giá trị trả về.
        IntUnaryOperator sign = n -> {
            if (n < 0) {
                return -1;
            }
            if (n == 0) {
                return 0;
            }
            return 1;
        };

        // Block trả về void, có biến cục bộ.
        Consumer<String> printClean = message -> {
            String cleaned = message.trim();
            System.out.println(cleaned);
        };

        System.out.println(greeting.get());
        System.out.println(length.apply("Java"));
        System.out.println(add.apply(3, 4));
        System.out.println(hasText.test("   "));
        System.out.println(sign.applyAsInt(-9));
        System.out.println(sign.applyAsInt(0));
        System.out.println(sign.applyAsInt(9));
        printClean.accept("  Lambda đang chạy  ");

        List<String> words =
                new ArrayList<>(Arrays.asList("a", "pear", "kiwi"));
        words.sort((left, right) ->
                Integer.compare(left.length(), right.length()));
        System.out.println(words);
    }
}
```

Chạy bằng JDK 17+; toàn bộ mã ví dụ cũng tương thích Java 8:

```bash
javac LambdaSyntaxDemo.java
java LambdaSyntaxDemo
```

Stdout chính xác:

```text
Xin chào
4
7
false
-1
0
1
Lambda đang chạy
[a, pear, kiwi]
```

Giải thích: `length.apply("Java")` là `4`; `add.apply(3,4)` là `7`; chuỗi toàn khoảng trắng sau `trim()` thành rỗng nên `hasText.test("   ")` là `false`. Lambda `sign` trả về `-1`, `0`, `1` theo đầu vào. `printClean` bỏ khoảng trắng ở hai đầu. `List.sort` dùng comparator độ dài; `"pear"` và `"kiwi"` cùng dài 4 và giữ nguyên thứ tự tương đối ban đầu vì quá trình sắp xếp List này ổn định.

## 7. Ngữ cảnh kiểu, phạm vi biến và ngoại lệ

### 7.1. Lambda phải có functional interface làm kiểu đích

Lambda không thể suy ra một kiểu đối tượng tùy ý chỉ từ `->`. Kiểu đích được cung cấp qua phép gán, tham số phương thức, kiểu trả về của phương thức hoặc phép ép kiểu hợp lệ:

```java
Function<Integer, Integer> inc = n -> n + 1;
Runnable task = () -> System.out.println("Run");
```

`var inc = n -> n + 1;` không hợp lệ vì thiếu functional interface để compiler biết kiểu của `n` và kết quả. `Object obj = () -> 1;` cũng không hợp lệ vì `Object` không phải functional interface. Khi một lời gọi phương thức có nhiều overload nhận các functional interface tương thích, Java có thể báo mơ hồ; khai báo lambda trong biến có kiểu interface rõ ràng trước khi truyền là cách giải quyết đơn giản.

### 7.2. Phạm vi của tên tham số và capture biến cục bộ

```java
int limit = 10;
Predicate<Integer> greater = value -> value > limit;
```

`value` là tham số lambda; `limit` là local variable được capture từ phạm vi bên ngoài. Tham số lambda không được khai báo trùng tên một biến cục bộ/tham số vẫn đang nằm trong phạm vi bao quanh; không thể đổi tên `value` thành `limit` trong ví dụ này.

Local variable được capture phải là `final` hoặc **effectively final**: không bị gán lại sau lần gán xác định. Ví dụ gán tiếp `limit = 20;` sau khi tạo lambda sẽ làm đoạn mã không biên dịch. Điều đó không cấm thay đổi trạng thái của một đối tượng được biến capture tham chiếu tới; tuy nhiên tác dụng phụ cần được cân nhắc nếu lambda được thực thi đồng thời.

Trong lambda, `this` (ở ngữ cảnh có instance) tham chiếu đối tượng lớp bao quanh; nó không trỏ tới một instance riêng của lambda như cách hiểu nhầm từ anonymous class. `return` trong lambda chỉ thoát khỏi thân lambda.

### 7.3. Ngoại lệ đã kiểm tra (*checked exception*)

Body lambda phải tuân theo khai báo `throws` của phương thức trừu tượng đích. Chẳng hạn, `Function.apply` không khai báo `IOException`, nên không thể ném trực tiếp một `IOException` chưa xử lý từ body. Hãy xử lý ngoại lệ một cách có nghĩa hoặc dùng một functional interface có hợp đồng `throws` phù hợp khi ứng dụng thực sự yêu cầu. Không nên nuốt lỗi và trả về kết quả giả làm như xử lý đã thành công.

## 8. Lỗi thường gặp và cách sửa

Các ví dụ “Sai” dưới đây để học cách nhận diện lỗi, không phải mã cần chạy:

| Sai | Đúng | Nguyên nhân |
| --- | --- | --- |
| `x, y -> x + y` | `(x, y) -> x + y` | Hai tham số phải có `(...)`. |
| `String s -> s.length()` | `(String s) -> s.length()` | Tham số có kiểu cần ngoặc. |
| `(String a, b) -> a + b` | `(String a, String b) -> a + b` hoặc `(a, b) -> a + b` | Không trộn khai báo kiểu với suy luận. |
| `() => 1` | `() -> 1` | Java dùng `->`, không dùng `=>`. |
| `x -> return x + 1` | `x -> x + 1` hoặc `x -> { return x + 1; }` | `return` chỉ xuất hiện như câu lệnh trong block. |
| `x -> { x + 1; }` | `x -> { return x + 1; }` | `x + 1;` không phải một statement expression hợp lệ. |
| `() -> 42` gán cho `Runnable` | `() -> System.out.println(42)` | `Runnable.run()` trả về `void`; literal `42` không phải statement expression. |
| `var f = x -> x + 1` | `Function<Integer,Integer> f = x -> x + 1` | Lambda cần kiểu đích. |
| `(var x, String y) -> ...` | `(x, y) -> ...` hoặc khai báo cùng kiểu | Không trộn `var` và kiểu tường minh. |

Phân biệt vị trí dấu chấm phẩy trong các trường hợp hợp lệ:

```java
Function<Integer, Integer> a = n -> n * 2;
Function<Integer, Integer> b = n -> { return n * 2; };
Consumer<Integer> c = n -> { System.out.println(n); };
```

Ở `a`, `;` duy nhất kết thúc câu lệnh gán. Ở `b`, dấu `;` sau `return n * 2` nằm bên trong block, dấu `;` sau `}` kết thúc câu lệnh khai báo. Với expression body, đừng thêm dấu `;` trước khi phần cú pháp chứa lambda (ví dụ lời gọi `map(...)`) kết thúc.

## 9. Nguyên tắc áp dụng trong mã hiện đại

- **Không tham số**: luôn `() -> ...`.
- **Một tham số suy luận kiểu**: ưu tiên `value -> ...`, dùng `(value) -> ...` khi cần định dạng.
- **Nhiều tham số**: dùng `(first, second) -> ...`; chọn tên phản ánh vai trò.
- **Khai báo kiểu tường minh**: phải dùng ngoặc và khai báo nhất quán cho mọi tham số.
- **Biểu thức ngắn, rõ kết quả**: chọn expression body và để Java tự trả về giá trị.
- **Nhiều bước hoặc điều kiện**: chọn block body, chú ý `return` và tất cả nhánh.
- **Giao diện đích**: ưu tiên interface chuẩn `java.util.function` phù hợp với chữ ký; dùng primitive-specialized interface khi muốn tránh boxing không cần thiết.
- **Tương thích Java 8**: không dùng cú pháp tham số `var` của Java 11+ trong mã cần biên dịch cho Java 8. Những cú pháp lambda còn lại ở bài này vẫn hợp lệ trong Java mới.

### Câu hỏi tự kiểm tra

1. Vì sao `name -> name.trim()` hợp lệ nhưng `String name -> name.trim()` không hợp lệ?
2. Khi nào `() -> service.call()` hợp lệ cho `Runnable` dù `call()` có thể trả về một giá trị?
3. Vì sao block `n -> { if (n > 0) return n; }` chưa đủ cho `Function<Integer,Integer>`?
4. Viết hai lambda tương đương dùng `Function<Integer,Integer>`: một expression body và một block body.
5. Kiểu đích giúp compiler suy luận số lượng tham số, kiểu tham số và kiểu kết quả ra sao?

**Ghi nhớ:** danh sách tham số phải tương thích với functional interface đích; dấu phân tách chính xác là `->`; phần thân là **một biểu thức** hoặc **một block**. Expression body có thể trả về giá trị tự động, còn block body yêu cầu `return` tường minh khi hợp đồng cần kết quả. Đây là kiến thức đang áp dụng trong Java hiện đại.