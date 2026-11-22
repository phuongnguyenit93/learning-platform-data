# Kiểu tham số, kiểu kết quả và mệnh đề throws của phương thức hàm

## Mục tiêu

Khi làm việc với **functional interface** trong Java, cần hiểu chữ ký của **phương thức hàm** (functional method): nhận những tham số nào, trả kết quả kiểu gì và có thể ném những checked exception nào. Ba phần này quyết định một lambda hoặc method reference có thể dùng ở vị trí nào, trình biên dịch suy luận kiểu ra sao và nơi gọi phải xử lý lỗi thế nào.

Sau bài học, bạn có thể:

- Đọc đúng **function descriptor** của một functional interface, bao gồm danh sách tham số, kiểu trả về và mệnh đề `throws`.
- Phân biệt kiểu được khai báo trong interface với kiểu cụ thể mà lambda/method reference nhận từ **target type**.
- Chọn giữa `Function`, `Consumer`, `Predicate`, `Supplier`, `BiFunction`, `ToIntFunction` và functional interface tự định nghĩa.
- Viết lambda có tham số và giá trị trả về phù hợp, nhận diện các lỗi biên dịch về kiểu hoặc đường đi `return`.
- Hiểu vì sao checked exception phải tương thích với `throws` của phương thức hàm; biết cách khai báo, bắt hoặc chuyển đổi ngoại lệ mà không làm sai ngữ nghĩa.
- Kiểm chứng ví dụ Java 17 chạy được và giải thích các trường hợp không biên dịch.

## 1. Phương thức hàm và function descriptor

Một **functional interface** là interface có đúng một phương thức trừu tượng về mặt hợp đồng SAM (*single abstract method*). Phương thức `default`, `static` và phương thức trừu tượng tương ứng với phương thức `public` của `Object` không làm tăng số phương thức trừu tượng phải triển khai. Annotation `@FunctionalInterface` giúp trình biên dịch kiểm tra điều kiện này, nhưng không bắt buộc phải có để interface được coi là functional.

Ví dụ:

```java
@FunctionalInterface
interface Converter {
    String convert(String input, int repeat) throws java.io.IOException;

    default boolean isReady() {
        return true;
    }
}
```

Phương thức hàm là `convert(String, int)`. **Function descriptor** mô tả hợp đồng callable tương ứng:

```text
(String input, int repeat) -> String
                              throws IOException
Tham số: String, int
Kết quả: String
Checked exception được phép: IOException
```

Các thành phần có vai trò riêng:

1. **Danh sách tham số** quy định số lượng, thứ tự và kiểu của giá trị mà hàm được gọi với. Tên `input` và `repeat` chỉ là tên trong khai báo, không phải một phần khiến kiểu hàm khác nhau.
2. **Kiểu kết quả** quy định giá trị lambda phải tạo ra. `void` nghĩa là không trả giá trị để bên gọi sử dụng.
3. **Mệnh đề `throws`** xác định các ngoại lệ được phép thoát ra mà Java yêu cầu kiểm tra ở thời điểm biên dịch. Các ngoại lệ không kiểm tra (`RuntimeException` và `Error` cùng các lớp con) vẫn có thể xảy ra dù không liệt kê trong `throws`.

Chữ ký phương thức theo nghĩa hẹp trong Java bao gồm tên và các kiểu tham số, không bao gồm kiểu trả về và `throws`. Trong bài này, ta xét **ba thành phần của function descriptor**, không nhầm “chữ ký phương thức” theo JLS với toàn bộ mô tả kiểu hàm.

## 2. Kiểu tham số quyết định lambda nhận gì

Xét ba interface:

```java
@FunctionalInterface
interface UnaryText {
    String apply(String text);
}

@FunctionalInterface
interface TextAndCount {
    String apply(String text, int count);
}

@FunctionalInterface
interface NoArgument {
    String get();
}
```

Cả ba đều là functional interface, nhưng không thể hoán đổi lambda vì số tham số khác nhau:

```java
UnaryText trim = text -> text.trim();
TextAndCount repeat = (text, count) -> text.repeat(count);
NoArgument greeting = () -> "Xin chào";
```

Kiểu tham số được định hướng bởi **target type** ở bên trái phép gán (hoặc kiểu tham số của phương thức nhận lambda). Ví dụ `text -> text.trim()` không tự có một kiểu `Function` độc lập; nó tương thích với một functional interface có phương thức nhận `String` và trả giá trị thích hợp. Nếu dùng `UnaryText`, `text` được suy luận là `String`.

Java cho phép hai cách khai báo tham số lambda:

```java
UnaryText a = text -> text.trim();               // suy luận String
UnaryText b = (String text) -> text.trim();      // khai báo tường minh
TextAndCount c = (text, count) -> text.repeat(count);
TextAndCount d = (var text, var count) -> text.repeat(count);
```

Với nhiều tham số, cần dùng dấu ngoặc tròn. Trong cùng một danh sách tham số lambda, **không trộn** tham số viết theo kiểu suy luận, kiểu tường minh và `var` tùy tiện; chẳng hạn `(var x, int n) -> ...` không hợp lệ. Việc dùng `var` cho tham số lambda được hỗ trợ từ Java 11, kể cả khi cần annotation trên tham số và nhất quán mọi tham số.

Kiểu tham số không tự động bị “ép theo ý muốn” của lambda. Ví dụ:

```java
// KHÔNG biên dịch: left là String, không thể dùng làm toán hạng của phép + số học.
UnaryText invalid = left -> left + 1; // Biểu thức này THỰC RA biên dịch,
// vì "+" với String là phép nối chuỗi; kết quả "abc1", không phải phép cộng số.
```

Nhận diện chính xác lỗi kiểu là rất quan trọng: `String + 1` hợp lệ vì nối chuỗi. Ví dụ không biên dịch thực sự là:

```java
// Không biên dịch: cannot convert String to int.
java.util.function.IntUnaryOperator wrong = (String x) -> x.length();
```

`IntUnaryOperator` có descriptor `(int) -> int`, vì vậy tham số lambda không thể khai báo là `String`. Thay vào đó:

```java
java.util.function.IntUnaryOperator twice = x -> x * 2;
```

Lưu ý: các đoạn trong mục này là **đoạn minh họa cần đặt trong ngữ cảnh khai báo hợp lệ**; những dòng đánh dấu không biên dịch chỉ dùng để nhận biết lỗi, không được đưa nguyên xi vào chương trình chạy.

### Generic và kiểu thực tế ở nơi sử dụng

Functional interface tổng quát:

```java
@FunctionalInterface
interface Mapper<T, R> {
    R map(T value);
}

Mapper<String, Integer> length = String::length;
Mapper<Integer, String> asText = String::valueOf;
```

Khi thay `T = String`, `R = Integer`, descriptor của `length` là `(String) -> Integer`. Với `asText`, descriptor là `(Integer) -> String`. Cùng định nghĩa `Mapper<T,R>`, nhưng mỗi **parameterized type** tạo ra ngữ cảnh kiểu cụ thể cho lambda/method reference.

`Function<T,R>` trong thư viện chuẩn đã phục vụ trường hợp này; dùng interface riêng khi tên miền nghiệp vụ hoặc `throws` cần rõ hơn. Kiểu generic là invariant theo mặc định: `Function<Object,String>` không tự động là subtype của `Function<String,String>` chỉ vì `String` là subtype của `Object`; khi thiết kế API có thể sử dụng wildcard theo phương sai phù hợp.

## 3. Kiểu kết quả: giá trị, void và quy tắc return

Trong descriptor `(T) -> R`, `R` là kiểu kết quả. Với lambda biểu thức, biểu thức phải tương thích với kiểu đó. Với lambda có body dạng block, các nhánh kết thúc bình thường và câu lệnh `return` phải đáp ứng quy tắc của kiểu kết quả.

```java
java.util.function.Function<String, Integer> length =
        text -> text.length();

java.util.function.Predicate<String> nonBlank =
        text -> !text.isBlank();

java.util.function.Consumer<String> print =
        text -> System.out.println(text);

java.util.function.Supplier<String> defaultName =
        () -> "Khách";
```

Các descriptor lần lượt là:

| Functional interface | Tham số | Kết quả |
| --- | --- | --- |
| `Function<String,Integer>` | `String` | `Integer` |
| `Predicate<String>` | `String` | `boolean` |
| `Consumer<String>` | `String` | `void` |
| `Supplier<String>` | không có | `String` |

Vì `Integer` là kiểu wrapper, `text.length()` trả `int` được **boxing** thành `Integer` khi phù hợp; với xử lý dữ liệu số lớn, có thể chọn `ToIntFunction<String>` có descriptor `(String) -> int` để giảm boxing. Ngược lại, kết quả một lambda trả về `String` có thể dùng ở descriptor trả `CharSequence` nhờ kiểu kết quả tương thích.

Ví dụ body block với kết quả rõ ràng:

```java
java.util.function.Function<String, Integer> safeLength = text -> {
    if (text == null) {
        return 0;
    }
    return text.length();
};
```

Nếu descriptor trả `Integer`/`int`, mọi nhánh mà chương trình có thể đi đến điểm kết thúc block cần trả một giá trị tương thích hoặc kết thúc đột ngột do ném ngoại lệ. Lỗi:

```java
// Không biên dịch: một nhánh có thể kết thúc mà thiếu return.
java.util.function.Function<String, Integer> invalid = text -> {
    if (text.isEmpty()) {
        return 0;
    }
};
```

Còn với `void`, lambda block có thể thực hiện lệnh rồi kết thúc không cần `return` giá trị:

```java
java.util.function.Consumer<String> printer = text -> {
    System.out.println(text);
    return; // hợp lệ, nhưng không bắt buộc
};
```

Trình biên dịch phân biệt **value-compatible** (trả giá trị) và **void-compatible** (phù hợp với hàm `void`) cho lambda block. Một lambda biểu thức là *statement expression*, ví dụ `System.out.println(text)` hoặc `list.add(value)`, có thể dùng ở ngữ cảnh `void`. Không nên vì thế mà cố ép mọi phép tính trả kết quả thành `Consumer`: nếu bên gọi cần dùng kết quả, chọn `Function` hoặc interface trả giá trị.

### Method reference và kiểu kết quả

`String::length` có thể thích ứng với `Function<String,Integer>` vì lời gọi `length()` trả `int` và Java có thể boxing thành `Integer`. `"abc"::length` lại là method reference đã gắn receiver, phù hợp với `Supplier<Integer>` không nhận tham số.

Cần chú ý khác biệt giữa reference đã gắn đối tượng và reference dạng `Type::instanceMethod`: với dạng thứ hai, tham số đầu tiên thường là receiver của lời gọi phương thức. Method reference chỉ tương thích khi số tham số, kiểu đối số, kiểu kết quả và `throws` thỏa hợp đồng target.

## 4. Mệnh đề throws của functional method

Java chia ngoại lệ thành:

- **Checked exceptions**: các lớp con của `Throwable` mà không là `RuntimeException`/`Error` (và không thuộc các nhánh unchecked tương ứng). Trình biên dịch yêu cầu bắt hoặc khai báo khi có thể được ném, ví dụ `IOException` hoặc `SQLException`.
- **Unchecked exceptions**: `RuntimeException`, `Error` và lớp con. Không bắt buộc khai báo trong `throws`, dù lập trình viên vẫn cần quyết định cách xử lý phù hợp.

Xét:

```java
@FunctionalInterface
interface TextReader {
    String read(String input) throws java.io.IOException;
}
```

Descriptor là `(String) -> String throws IOException`. Ta có thể gán cho nó lambda hoặc method reference có thể ném `IOException` hay một checked exception **con** của `IOException`:

```java
TextReader reader = input -> {
    if (input.isBlank()) {
        throw new java.io.IOException("empty");
    }
    return input.trim();
};
```

Lambda **không ném checked exception nào** cũng tương thích với descriptor cho phép `IOException`:

```java
TextReader uppercase = input -> input.toUpperCase(java.util.Locale.ROOT);
```

Nhưng nếu lambda hoặc phương thức được tham chiếu có thể ném một checked exception không được phép bởi function descriptor, phép gán **lỗi biên dịch**:

```java
// Không biên dịch nếu readFile khai báo throws IOException:
java.util.function.Function<String, String> invalid =
        path -> readFile(path);
```

Vì `Function<T,R>.apply(T)` không khai báo checked exception, `IOException` không thể tự ý thoát ra từ body. `Function` không có mệnh đề `throws IOException`, cho dù nơi gọi `apply` được đặt trong `try/catch`. Cần đổi hợp đồng hàm hoặc bắt/chuyển ngoại lệ **bên trong** lambda.

**Phân biệt ba nơi có `throws`:**

1. `throws` của **phương thức hàm** xác định ngoại lệ checked mà implementation được phép ném.
2. `throws` của **phương thức được method reference trỏ tới** quyết định method reference có tương thích với target hay không.
3. `throws` của **phương thức gọi functional interface** chỉ giúp caller xử lý ngoại lệ khi gọi, không làm cho target functional interface tự cho phép thêm checked exception.

Ví dụ, dù `main() throws Exception` thì `Function<String,String> fn = s -> readFile(s)` vẫn không biên dịch nếu `readFile` khai báo `throws IOException`. Việc caller có thể bắt lỗi không đổi hợp đồng của `Function.apply`.

### Nên làm gì khi cần checked exception?

Có ba cách phổ biến:

**(1) Tạo functional interface khai báo checked exception.** Phù hợp khi I/O là phần thật sự của hợp đồng và caller phải xử lý lỗi.

```java
@FunctionalInterface
interface CheckedFunction<T, R> {
    R apply(T input) throws java.io.IOException;
}
```

**(2) Bắt lỗi tại ranh giới lambda.** Phù hợp khi API buộc dùng `Function` và có phương án khôi phục hợp lệ; không được âm thầm bỏ lỗi.

```java
// Minh họa; readFile(String) là phương thức có thể throws IOException.
java.util.function.Function<String, String> withFallback = path -> {
    try {
        return readFile(path);
    } catch (java.io.IOException e) {
        return "unavailable"; // chỉ phù hợp nếu fallback là quy tắc nghiệp vụ
    }
};
```

**(3) Chuyển checked exception sang unchecked exception** nếu tầng API không hỗ trợ checked exception và hợp đồng của tầng đó chấp nhận thất bại dạng unchecked. Giữ nguyên cause để không mất chẩn đoán:

```java
java.util.function.Function<String, String> wrapping = path -> {
    try {
        return readFile(path);
    } catch (java.io.IOException e) {
        throw new java.io.UncheckedIOException(e);
    }
};
```

Không mặc định chuyển mọi `IOException` sang `RuntimeException` chỉ để sử dụng Stream. Việc thay loại ngoại lệ ảnh hưởng caller, chính sách retry, quan sát lỗi và giao dịch. Nếu có thể, tách I/O ra trước khi thực hiện pipeline biến đổi thuần.

## 5. Ví dụ Java 17 đầy đủ, biên dịch và chạy

Chương trình sau minh họa ba yếu tố của function descriptor, lambda hợp lệ khi không ném checked exception, method reference đến phương thức có `throws IOException` và generic functional interface có tham số ngoại lệ.

Tạo tệp **`FunctionalMethodSignatureDemo.java`**:

```java
import java.io.BufferedReader;
import java.io.IOException;
import java.io.StringReader;
import java.util.Locale;

public class FunctionalMethodSignatureDemo {
    @FunctionalInterface
    interface TextReader {
        String read(String input) throws IOException;
    }

    @FunctionalInterface
    interface Summary {
        String format(String label, int quantity);
    }

    @FunctionalInterface
    interface TextLength {
        int length(String input);
    }

    @FunctionalInterface
    interface CheckedMapper<T, R, E extends Exception> {
        R apply(T input) throws E;
    }

    static String firstLine(String value) throws IOException {
        if (value.isBlank()) {
            throw new IOException("blank input");
        }
        try (BufferedReader reader =
                     new BufferedReader(new StringReader(value))) {
            return reader.readLine();
        }
    }

    public static void main(String[] args) throws IOException {
        TextReader first = FunctionalMethodSignatureDemo::firstLine;
        TextReader upper = text -> text.toUpperCase(Locale.ROOT);
        Summary summary = (label, quantity) ->
                label + " x" + quantity;
        TextLength length = String::length;

        CheckedMapper<String, String, IOException> generic =
                FunctionalMethodSignatureDemo::firstLine;

        System.out.println("First: " + first.read("Java\nFunctional"));
        System.out.println("Upper: " + upper.read("Java"));
        System.out.println("Summary: " + summary.format("Book", 3));
        System.out.println("Length: " + length.length("Java"));
        System.out.println("Generic: " + generic.apply("One\nTwo"));

        try {
            first.read("  ");
        } catch (IOException e) {
            System.out.println("Error: " + e.getMessage());
        }
    }
}
```

Biên dịch và chạy:

```bash
javac FunctionalMethodSignatureDemo.java
java FunctionalMethodSignatureDemo
```

Kết quả đầu ra:

```text
First: Java
Upper: JAVA
Summary: Book x3
Length: 4
Generic: One
Error: blank input
```

**Cách đọc hợp đồng và đối chiếu đầu ra:**

| Biến | Descriptor sau khi xác định kiểu | Cách triển khai |
| --- | --- | --- |
| `first` | `(String) -> String throws IOException` | `FunctionalMethodSignatureDemo::firstLine` |
| `upper` | `(String) -> String throws IOException` | Lambda không ném checked exception |
| `summary` | `(String,int) -> String` | Lambda nhận đúng hai tham số |
| `length` | `(String) -> int` | Method reference `String::length` |
| `generic` | `(String) -> String throws IOException` | `CheckedMapper<String,String,IOException>` |

`firstLine` đọc dòng đầu từ `StringReader` bằng `BufferedReader`. Vì `readLine()` khai báo `throws IOException`, phương thức `firstLine` cũng khai báo `throws IOException`; nhánh dữ liệu trắng chủ động ném `IOException("blank input")`. Method reference `firstLine` phù hợp với hai functional interface cho phép `IOException`. Lệnh `main` khai báo `throws IOException` để cho phép các lần gọi thành công mà không cần bắt tại từng câu lệnh; lần gọi thất bại được bắt rõ để in `Error: blank input`.

`String::length` nhận `String` làm receiver rồi trả số `int`; phù hợp với `TextLength`. `summary` nhận hai đối số và trả một `String`. Chương trình cho thấy chính **target type** của từng biến kiểm soát descriptor mà lambda/method reference phải đáp ứng.

## 6. Khi kế thừa nhiều interface và chọn descriptor

Một functional interface không nhất thiết chỉ *khai báo* đúng một phương thức: nó có thể thừa kế nhiều khai báo trừu tượng nhưng chúng vẫn đại diện cho cùng một phương thức về mặt SAM nếu các chữ ký đáp ứng quy tắc override-equivalence và các điều kiện về kiểu trả về.

Ví dụ không có ngoại lệ:

```java
interface A {
    CharSequence name(String value);
}

interface B {
    String name(String value);
}

@FunctionalInterface
interface C extends A, B { }

C fn = value -> value.trim();
```

Vì `String` là subtype của `CharSequence`, phương thức có kiểu trả về `String` phù hợp với hợp đồng đã kế thừa; `C` có một phương thức hàm với descriptor nhận `String` và trả `String`. Không phải mọi cặp return type đều hợp lệ: nếu hai kiểu trả về không thể dung hòa theo quy tắc return-type-substitutability, interface kế thừa sẽ lỗi.

Với **mệnh đề `throws` kế thừa**, cần đặc biệt thận trọng. Không được mặc nhiên lấy *hợp* các ngoại lệ từ mọi khai báo rồi cho lambda ném tất cả. Function type của interface kế thừa phải tuân theo các hạn chế checked exception từ những phương thức được xem là tương ứng; các ngoại lệ checked được phép phải tương thích với hợp đồng của mọi phương thức cần thực thi. Nếu interface kế thừa các khai báo mâu thuẫn về checked exception, danh sách checked exception được phép của descriptor có thể **hẹp hơn** từng khai báo ban đầu, thậm chí không cho phép ngoại lệ checked nào.

Trong thiết kế API, thường nên khai báo một interface có descriptor rõ ràng và giữ `throws` ở mức hẹp nhất hợp lý. Không cố tạo một cây interface phức tạp chỉ để “ghép” các nhóm ngoại lệ.

### Descriptor generic và giới hạn của lambda

Khai báo có tham số kiểu **ở cấp interface** thường thuận lợi cho lambda:

```java
@FunctionalInterface
interface Identity<T> {
    T apply(T value);
}

Identity<String> normalize = String::trim;
```

Một interface có thể có phương thức hàm generic ở **cấp phương thức**, nhưng kiểu function descriptor mang type parameter riêng của method có những hạn chế khi làm target cho biểu thức lambda. Không nên mặc định mọi khai báo generic SAM đều có thể triển khai bằng lambda theo cú pháp quen thuộc. Khi cần lambda, đưa generic vào cấp interface như `Identity<T>` hoặc `Function<T,R>` thường đơn giản, dễ sử dụng hơn.

## 7. Chọn đúng functional interface chuẩn

Trong `java.util.function`:

| Interface | Function descriptor | Dùng khi |
| --- | --- | --- |
| `Runnable` (`java.lang`) | `() -> void` | Chạy một tác vụ, không có kết quả |
| `Supplier<T>` | `() -> T` | Cấp phát hoặc lấy một giá trị |
| `Consumer<T>` | `(T) -> void` | Thực hiện hành động với một giá trị |
| `BiConsumer<T,U>` | `(T,U) -> void` | Hành động với hai giá trị |
| `Predicate<T>` | `(T) -> boolean` | Kiểm tra điều kiện |
| `Function<T,R>` | `(T) -> R` | Biến đổi một giá trị |
| `BiFunction<T,U,R>` | `(T,U) -> R` | Biến đổi hai giá trị |
| `UnaryOperator<T>` | `(T) -> T` | Biến đổi mà kiểu đầu vào/đầu ra giống nhau |
| `BinaryOperator<T>` | `(T,T) -> T` | Kết hợp hai giá trị cùng kiểu |
| `ToIntFunction<T>` | `(T) -> int` | Tính số `int` không cần boxing |

`Runnable` là functional interface lịch sử trong `java.lang`, không thuộc `java.util.function`. Các interface thông dụng trên nhìn chung không khai báo checked exception cho phương thức hàm của chúng; nếu API cần cho phép checked exception thoát ra, hãy xem xét hợp đồng riêng.

Một vài ví dụ ngắn:

```java
java.util.function.Predicate<String> hasText = s -> !s.isBlank();
java.util.function.Function<String, Integer> size = String::length;
java.util.function.BiFunction<String, Integer, String> repeat =
        String::repeat;
java.util.function.ToIntFunction<String> primitiveLength =
        String::length;
```

Method reference `String::repeat` trong ví dụ `BiFunction` nhận receiver `String` làm tham số đầu và `int` làm tham số thứ hai; `String::length` phù hợp với kiểu trả `Integer` qua boxing hoặc `int` trực tiếp. Cùng cách viết Java nhưng target descriptor quyết định cách kiểm tra kiểu.

## 8. Các lỗi biên dịch và cách sửa

**Sai số tham số.** `Function<String,Integer>` nhận một `String`; `(a,b) -> ...` không phù hợp. Đổi sang `BiFunction` khi thực sự cần hai đầu vào, hoặc gom các tham số thành một value object có ý nghĩa.

**Sai kiểu kết quả.** `Predicate<String> predicate = s -> s.length();` lỗi vì `int` không chuyển thành `boolean` trong Java. Viết `s -> s.length() > 0`. Với descriptor `void`, đừng viết `return expression;` trong lambda block.

**Thiếu đường `return`.** Lambda block dành cho `Function` phải trả kết quả ở mọi đường đi kết thúc bình thường. Thêm `return` hoặc tách điều kiện thành hàm có tên để dễ rà soát.

**Sai checked exception.** `Function<Path,String>` không cho lambda ném `IOException` ra ngoài. Chọn checked functional interface, xử lý bên trong lambda hoặc thiết kế lại ranh giới I/O. `main throws Exception` không sửa được lỗi descriptor.

**Nhầm thứ tự tham số của method reference.** `String::repeat` có receiver `String` và tham số `int`, nên không hợp với `Function<Integer,String>`. Kiểm tra kiểu sau khi bind receiver; dùng lambda tường minh nếu method reference khó hiểu.

**Quá rộng `throws Exception`.** Khai báo `throws Exception` cho mọi functional interface bắt caller xử lý nhiều lỗi hơn cần thiết, che giấu hợp đồng thực tế. Ưu tiên ngoại lệ cụ thể hoặc nhóm ngoại lệ được thiết kế có chủ đích.

**Lẫn lộn generic và primitive.** `Function<String,Integer>` trả wrapper `Integer`, còn `ToIntFunction<String>` trả primitive `int`. Boxing thường tiện, nhưng trong vòng lặp hiệu năng cao có thể có chi phí không cần thiết.

**Dùng một interface cho quá nhiều ý nghĩa.** Hai phép toán có cùng `(String) -> String` không nhất thiết có cùng mục đích nghiệp vụ. Tên interface/phương thức nên phản ánh vai trò, nhất là khi API công khai hoặc có checked exception.

## 9. Bài tập áp dụng

1. Cho `@FunctionalInterface interface PriceRule { long apply(int quantity, long unitPrice); }`. Hãy viết lambda tính tổng không giảm giá và cho biết function descriptor.
2. Viết `Predicate<String>` nhận `String`, trả `true` nếu bắt đầu bằng `"J"`, đồng thời chỉ ra kiểu kết quả.
3. Với `Function<String,Integer>`, vì sao `s -> { if (s.isEmpty()) return 0; }` lỗi? Viết lại để mọi đường đi trả kết quả.
4. Giả sử `static String fetch(String key) throws IOException`. Vì sao `Function<String,String>` không thể nhận trực tiếp `App::fetch`? Hãy thiết kế `CheckedFunction<String,String>` tương ứng.
5. Giải thích sự khác nhau giữa `Function<String,Integer> len = String::length` và `Supplier<Integer> len = "abc"::length`.
6. Dự đoán stdout của ví dụ hoàn chỉnh trước khi chạy, rồi đổi `upper` thành lambda `text -> text.trim()`: việc đổi body có làm thay function descriptor `throws IOException` không?

**Gợi ý:**

- (1) `(quantity, unitPrice) -> quantity * unitPrice`; descriptor `(int,long) -> long`; nếu muốn phát hiện tràn, dùng `Math.multiplyExact(unitPrice, quantity)`.
- (2) `s -> s.startsWith("J")`; kiểu trả `boolean`.
- (3) Có nhánh không trả giá trị; thêm `return s.length();` sau `if`.
- (4) `Function.apply` không có `throws IOException`; thiết kế `String apply(String key) throws IOException`.
- (5) Bản thứ nhất là method reference chưa gắn receiver nên nhận một `String`; bản thứ hai đã gắn receiver nên không nhận tham số.
- (6) Output như đã liệt kê; thay body bằng lambda không ném checked exception vẫn tương thích với `TextReader`, descriptor vẫn khai báo `throws IOException`.

## 10. Tự kiểm tra trước khi gán lambda hoặc method reference

Đọc target type rồi lần lượt hỏi:

1. **Bao nhiêu tham số?** Thứ tự và kiểu từng tham số là gì? Có generic cần thay bằng kiểu cụ thể không?
2. **Trả về gì?** `void` hay giá trị? Có boxing, unboxing, widening hoặc kiểu trả về subtype cần xét không?
3. **Có thể ném checked exception nào?** Body hoặc phương thức được tham chiếu có ném ngoại lệ rộng hơn danh sách được phép không?
4. **Caller sẽ xử lý lỗi ở đâu?** Nếu dùng interface cho phép checked exception, nơi gọi cần `try/catch` hoặc khai báo `throws`; nếu phải chuyển thành unchecked, lý do và chính sách lỗi đã rõ chưa?
5. **Tên interface có diễn đạt ý nghĩa nghiệp vụ?** Chọn interface chuẩn cho phép biến đổi phổ thông, interface riêng khi yêu cầu hợp đồng rõ hơn.

**Kết luận:** Functional interface trong Java có hợp đồng xác định qua **kiểu tham số, kiểu kết quả và mệnh đề `throws`**. Lambda và method reference chỉ dùng được khi tương thích với function descriptor do target type cung cấp. Hiểu ba thành phần này giúp đọc lỗi biên dịch chính xác, tận dụng generic/primitive hợp lý và xử lý checked exception có chủ đích.
