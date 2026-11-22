# Quan hệ giữa `var` và kiểu đích của lambda (Java 11 trở lên)

## 1. Ý chính: kiểu đích quyết định kiểu của tham số `var`

Từ Java 11, có thể viết `var` trước từng tham số của biểu thức lambda, ví dụ `(var s) -> s.length()`. Ở đây `var` là **cú pháp khai báo tham số được suy luận kiểu** (implicitly typed lambda parameter), không phải tên một kiểu dữ liệu, không tạo biến kiểu động và không tự xác định kiểu của cả lambda.

**Kiểu đích (target type)** là kiểu hàm mà ngữ cảnh yêu cầu lambda phải tương thích, thường là một *functional interface* (giao diện có một phương thức trừu tượng chức năng, còn gọi là SAM). Quan hệ diễn ra như sau:

1. Trình biên dịch xác định functional interface mà vị trí sử dụng lambda đang yêu cầu (qua phép gán, đối số phương thức, câu lệnh `return` hoặc phép ép kiểu).
2. Từ chữ ký của phương thức chức năng, trình biên dịch xác định số lượng và kiểu tham số lambda; chúng được áp dụng cho các tham số khai báo bằng `var`.
3. Trình biên dịch kiểm tra biểu thức/thân lambda, kiểu kết quả trả về và checked exception có tương thích với chữ ký chức năng hay không.
4. Nếu không xác định được kiểu đích thích hợp, hoặc chữ ký/thân lambda không phù hợp, chương trình lỗi lúc biên dịch.

Có thể ghi nhớ đường đi: **ngữ cảnh → functional interface → chữ ký SAM → kiểu của `var` → kiểm tra thân lambda**. Đây là *target typing*: lambda là một *poly expression*, phụ thuộc vào kiểu đích, thay vì có một kiểu độc lập chỉ dựa trên phần `-> ...`.

Ví dụ:

```java
import java.util.function.Function;

Function<String, Integer> first = (var s) -> s.length();
Function<CharSequence, Integer> second = (var s) -> s.length();
```

Ở `first`, tham số `s` có kiểu tĩnh `String`; ở `second`, `s` có kiểu tĩnh `CharSequence`. Cùng phần thân `s.length()` nhưng kiểu tham số khác vì kiểu đích khác. Cả hai dùng phương thức `apply` và nhận kết quả `Integer` (giá trị `int` của `length()` được boxing).

**`var` không có nghĩa là `Object`** và không làm mất kiểm tra kiểu tại thời điểm biên dịch. Ví dụ sau **không biên dịch**:

```java
Function<CharSequence, Boolean> invalid = (var s) -> s.isBlank();
```

Lý do: `CharSequence` không khai báo `isBlank()`, dù ở thời điểm chạy ta có thể truyền vào một đối tượng `String`. Muốn gọi `String.isBlank()`, dùng kiểu đích có tham số `String`, hoặc xử lý/kiểm tra kiểu một cách tường minh.

## 2. So sánh ba cách viết tham số lambda

Với cùng kiểu đích `Function<String, Integer>`, ba biểu thức sau tương thích và cùng tính độ dài chuỗi:

```java
Function<String, Integer> a = s -> s.length();
Function<String, Integer> b = (var s) -> s.length();
Function<String, Integer> c = (String s) -> s.length();
```

| Cách viết | Kiểu tham số | Ý nghĩa |
| --- | --- | --- |
| `s -> ...` hoặc `(s) -> ...` | Suy luận từ kiểu đích | Ngắn gọn khi không cần modifier/annotation |
| `(var s) -> ...` | **Vẫn suy luận từ kiểu đích** | Cho phép cú pháp khai báo đầy đủ, ví dụ `final` hoặc annotation |
| `(String s) -> ...` | Khai báo tường minh `String` | Chữ ký phải tương thích với kiểu đích |

Cả hai dạng `s` và `var s` thuộc nhóm **lambda có tham số được suy luận kiểu**. Viết `var` không khiến tham số thành “khai báo kiểu tường minh”. Nếu functional interface thay đổi, kiểu của `var s` thay đổi theo.

Với nhiều tham số:

```java
import java.util.function.BiFunction;

BiFunction<Integer, Integer, Integer> add =
        (var left, var right) -> left + right;
```

`left` và `right` đều là `Integer` theo chữ ký `BiFunction<Integer, Integer, Integer>`; phép cộng tự unboxing để tính toán rồi boxing kết quả thành `Integer`.

### Quy tắc cú pháp bắt buộc

- Nếu chọn `var` thì **mọi tham số có tên trong danh sách phải dùng `var`**; không trộn `var` với tham số không ghi kiểu hoặc tham số có kiểu tường minh.
- Với `var`, danh sách tham số phải có dấu ngoặc đơn, kể cả khi chỉ có một tham số.
- Có thể viết modifier `final` và annotation hợp lệ trên tham số `var`; phạm vi ảnh hưởng của chúng vẫn theo quy tắc tham số Java thông thường.
- Số tham số, kiểu được suy luận, kiểu trả về và checked exception vẫn phải tương thích với phương thức chức năng của kiểu đích.

Ví dụ lỗi cú pháp (chỉ để nhận diện, **không đặt các dòng này trong chương trình cần biên dịch**):

```java
// (var x, y) -> x + y;         // Sai: trộn var với tham số không ghi kiểu
// (x, var y) -> x + y;         // Sai: cùng nguyên nhân
// (var x, int y) -> x + y;     // Sai: trộn var với kiểu tường minh
// var s -> s.length();        // Sai: thiếu dấu ngoặc quanh tham số var
```

Các dạng đúng tương ứng gồm `(x, y) -> x + y`, `(var x, var y) -> x + y` và `(int x, int y) -> x + y` (tất cả vẫn phải đặt trong ngữ cảnh có kiểu đích phù hợp).

## 3. Kiểu đích đến từ đâu?

### 3.1. Phép gán vào biến có kiểu functional interface

```java
import java.util.function.Predicate;

Predicate<String> nonBlank = (var s) -> !s.isBlank();
boolean result = nonBlank.test("Java"); // true
```

Vì `Predicate<String>` có phương thức chức năng `boolean test(String value)`, `s` là `String`; phần thân phải tạo kết quả tương thích với `boolean`.

### 3.2. Đối số của một phương thức, kể cả Stream API

```java
import java.util.List;

long count = List.of("Java", " ", "lambda")
        .stream()
        .filter((var s) -> !s.isBlank())
        .count(); // 2
```

`Stream<String>.filter` yêu cầu `Predicate<? super String>`. Trong ngữ cảnh này, tham số `s` được suy luận như `String`. Việc dùng `var` không làm thay đổi cách lọc, kiểu phần tử của stream hay kết quả `count()`.

### 3.3. Kiểu trả về của phương thức

```java
import java.util.function.UnaryOperator;

static UnaryOperator<String> cleaner() {
    return (var value) -> value.strip();
}
```

Kiểu trả về `UnaryOperator<String>` cung cấp target type cho lambda ở câu lệnh `return`. `value` là `String` và phần thân trả về `String`.

### 3.4. Đối số của phương thức generic

```java
import java.util.function.Function;

static <T, R> R transform(T input, Function<T, R> mapper) {
    return mapper.apply(input);
}

// Trong một phương thức:
String text = transform(" Java ", (var s) -> s.strip());
```

Lời gọi cung cấp ràng buộc cho suy luận kiểu generic: `T` ứng với `String` từ `input`, nên tham số `s` của `Function<T, R>` được xem là `String`; kết quả `strip()` hỗ trợ xác định `R` là `String`. Quá trình suy luận generic và target typing phối hợp với nhau, nhưng `var` ở lambda không tự tạo kiểu đích.

### 3.5. Ép kiểu tường minh

```java
import java.util.function.UnaryOperator;

var cleaner = (UnaryOperator<String>) (var s) -> s.strip();
```

Ở đây phép ép kiểu `(UnaryOperator<String>)` cung cấp kiểu đích cho lambda; sau đó `var cleaner` của **biến cục bộ** suy luận từ biểu thức đã được ép kiểu. Đây là hai vị trí `var` khác vai trò, không phải một trường hợp lambda tự mang kiểu.

## 4. Phân biệt `var` trong tham số lambda với `var` của biến cục bộ

```java
var number = 42; // Đúng: kiểu của biến number suy ra từ initializer 42 (int)

Function<String, Integer> length = (var s) -> s.length();
// Đúng: kiểu s suy ra từ target type Function<String, Integer>

// var action = (var s) -> s.length(); // Sai: lambda thiếu target type
// Object action = (var s) -> s.length(); // Sai: Object không là functional interface
```

Ở `var number = 42`, biểu thức khởi tạo có kiểu đủ xác định để suy luận kiểu biến. Ngược lại, lambda cần ngữ cảnh functional interface để biết chữ ký chức năng; riêng `(var s) -> s.length()` không xác định được `s` là `String`, `CharSequence` hay một kiểu khác. Muốn khai báo biến chứa lambda, khai báo trực tiếp kiểu functional interface hoặc cung cấp phép ép kiểu tương ứng.

## 5. Kiểu đích còn ràng buộc kết quả và checked exception

Không chỉ kiểu tham số, kiểu đích còn quyết định điều kiện chấp nhận thân lambda:

```java
import java.util.Comparator;
import java.util.function.Function;
import java.util.function.Predicate;

Function<String, Integer> length = (var s) -> s.length(); // Hợp lệ
Comparator<String> compare = (var a, var b) -> a.compareTo(b); // Hợp lệ

// Predicate<String> wrong = (var s) -> s.length();
// Sai: Predicate.test phải trả về boolean, không phải int
```

Khi functional method khai báo một loại checked exception, thân lambda có thể ném checked exception tương thích; nếu không, phải bắt/xử lý hoặc dùng một functional interface có chữ ký phù hợp. `var` **không** nới lỏng các điều kiện ấy.

Ví dụ phân biệt:

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

@FunctionalInterface
interface FileLoader {
    String load(Path path) throws IOException;
}

// Đặt trong phương thức:
FileLoader loader = (var path) -> Files.readString(path); // Hợp lệ
```

`path` là `Path` vì chữ ký `FileLoader.load(Path)`. Thân lambda được phép truyền `IOException` ra ngoài vì SAM khai báo `throws IOException`. Ngược lại, đặt cùng thân lambda vào `Function<Path, String>` sẽ báo lỗi biên dịch do `Function.apply` không khai báo checked exception này.

## 6. Khi nào `var` hữu ích? Annotation và `final`

`var` có lợi khi muốn gắn annotation hoặc modifier lên tham số mà vẫn để kiểu được suy luận từ functional interface:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.util.function.BiFunction;

@Target(ElementType.PARAMETER)
@Retention(RetentionPolicy.SOURCE)
@interface ReviewedParameter {}

BiFunction<String, String, String> join =
        (@ReviewedParameter var left, final var right) -> left + right;
```

Đoạn trên là **mã minh họa đặt các khai báo đúng ngữ cảnh**: annotation được khai báo ở cấp loại; biến `join` được khai báo trong lớp/phương thức. `left` và `right` vẫn có kiểu `String` từ `BiFunction`. Annotation được phép áp dụng vì nó dành cho `PARAMETER`; annotation kiểu SOURCE này không tự kiểm tra dữ liệu lúc chạy. `final var right` cấm gán lại biến tham số `right` trong thân lambda, không làm đối tượng được tham chiếu trở nên bất biến.

Nếu không cần annotation hay modifier, dạng `s -> ...` thường dễ đọc hơn; dùng `var` khi việc khai báo thống nhất hoặc gắn metadata vào tham số thực sự có ích.

## 7. `var` không tự giải quyết nhập nhằng overload

Giả sử một lớp khai báo hai functional interface khác nhau nhưng có chữ ký phương thức tương tự:

```java
interface First {
    String run(String text);
}

interface Second {
    String run(String text);
}

static void choose(First f) { /* ... */ }
static void choose(Second f) { /* ... */ }

// choose((var s) -> s.strip()); // Lỗi: lời gọi choose nhập nhằng
choose((First) (var s) -> s.strip()); // Hợp lệ: ép kiểu chọn First
```

Đây là **đoạn minh họa để đặt bên trong một lớp**. Hai overload đều phù hợp với lambda `(var s) -> s.strip()`; viết `var` không đủ để chọn một trong hai. Ép kiểu tường minh làm rõ target type. Lưu ý rằng việc đổi sang `(String s) -> ...` cũng không mặc nhiên giải quyết nhập nhằng nếu cả hai overload vẫn tương thích; nguyên nhân là các chữ ký overload, không phải cách viết `var`.

## 8. Chương trình Java 11+ hoàn chỉnh

Lưu nội dung sau thành `LambdaTargetTypingDemo.java`. Ví dụ minh họa hai kiểu đích khác nhau, annotation, `final`, phương thức generic và việc suy luận kiểu qua `Predicate`:

```java
import java.lang.annotation.*;
import java.util.List;
import java.util.function.*;

public class LambdaTargetTypingDemo {
    @Target(ElementType.PARAMETER)
    @Retention(RetentionPolicy.SOURCE)
    @interface CheckedByTool {}

    static <T, R> R apply(T input, Function<T, R> mapper) {
        return mapper.apply(input);
    }

    static Predicate<String> nonBlank() {
        return (var s) -> !s.isBlank();
    }

    public static void main(String[] args) {
        Function<String, Integer> lengthOfString =
                (var s) -> s.length();

        Function<CharSequence, Integer> lengthOfChars =
                (var s) -> s.length();

        BiFunction<String, String, String> join =
                (@CheckedByTool var left, final var right) ->
                        left.strip() + "-" + right.strip();

        System.out.println(lengthOfString.apply("Java"));
        System.out.println(lengthOfChars.apply(new StringBuilder("target")));
        System.out.println(join.apply(" A ", " B "));

        String normalized = apply(" java ",
                (var s) -> s.strip().toUpperCase());
        System.out.println(normalized);

        System.out.println(List.of(" ", "Java")
                .stream()
                .filter(nonBlank())
                .count());
    }
}
```

Biên dịch và chạy trên JDK 11 trở lên:

```bash
javac --release 11 LambdaTargetTypingDemo.java
java LambdaTargetTypingDemo
```

Kết quả chuẩn:

```text
4
6
A-B
JAVA
1
```

Giải thích: `lengthOfString` nhận `String` dài 4 ký tự; `lengthOfChars` nhận `CharSequence` nên có thể xử lý `StringBuilder("target")` dài 6; `join` bỏ khoảng trắng ở hai đầu rồi nối bằng dấu gạch ngang; `apply` nhận chuỗi, suy luận `s` là `String` và trả `"JAVA"`; `nonBlank` loại phần tử chỉ chứa khoảng trắng nên stream còn 1 phần tử.

## 9. Bảng chẩn đoán lỗi thường gặp

| Hiện tượng | Nguyên nhân | Hướng sửa |
| --- | --- | --- |
| `var f = (var s) -> ...` không biên dịch | Không có target type cho lambda | Dùng `Function<...>`, `Predicate<...>` hoặc cast sang functional interface thích hợp |
| Gọi phương thức của `String` trên tham số `var` bị lỗi | SAM của kiểu đích khai báo tham số kiểu rộng hơn, ví dụ `CharSequence` | Kiểm tra chữ ký SAM, chọn target type đúng hoặc xử lý kiểu tường minh |
| `(var x, y)` / `(var x, int y)` bị lỗi | Trộn cách khai báo tham số | Dùng nhất quán `(var x, var y)`, `(x, y)` hoặc kiểu tường minh cho tất cả |
| Lambda trả về sai kiểu | Kết quả không tương thích kiểu trả về của SAM | Đối chiếu kiểu kết quả/`void` trong chữ ký functional interface |
| Lambda gọi API ném checked exception bị lỗi | SAM không cho phép checked exception ấy | Bắt exception hoặc dùng interface có `throws` phù hợp |
| Overload nhập nhằng | Có nhiều functional interface thích hợp | Chọn overload rõ ràng bằng kiểu biến, cast hoặc thiết kế API cụ thể hơn |

### Tự kiểm tra

1. Với `Predicate<List<String>> p = (var items) -> !items.isEmpty();`, `items` có kiểu gì? **`List<String>`**, vì `Predicate<T>.test` nhận tham số `T`.
2. Thay `(var left, var right)` bằng `(var left, right)` có hợp lệ không? **Không**, vì trộn hai cách khai báo.
3. Viết `Function<String, Integer> f = (var s) -> s.length();` có khác về kiểu tham số so với `s -> s.length()` không? **Không**, cả hai đều suy luận `s` là `String` từ target type.
4. `var` ở tham số có làm compiler suy luận kiểu chỉ từ lệnh trong thân lambda không? **Không**; functional interface cung cấp ràng buộc kiểu trước khi kiểm tra thân.

## Tài liệu chuẩn còn áp dụng

- [Java Language Specification, Java SE 26 — Lambda Expressions (`15.27)](https://docs.oracle.com/javase/specs/jls/se26/html/jls-15.html#jls-15.27): cú pháp, target typing và quy tắc tương thích.
- [JEP 323 — Local-Variable Syntax for Lambda Parameters](https://openjdk.org/jeps/323): lý do bổ sung `var` vào tham số lambda từ Java 11.
- [Oracle — Local Variable Type Inference](https://docs.oracle.com/en/java/javase/17/language/local-variable-type-inference.html): phân biệt suy luận kiểu biến cục bộ và cú pháp `var` trong lambda.

**Kết luận kỹ thuật:** Trong `(var x) -> body`, `var` chỉ yêu cầu suy luận kiểu của tham số. Ngữ cảnh functional interface vẫn quyết định target type và ràng buộc kiểu; mọi quy tắc kiểm tra kiểu tĩnh, generic, overload và checked exception vẫn áp dụng.