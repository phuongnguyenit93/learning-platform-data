# Khai báo tham số lambda bằng `var` (Java 11+)

## 1. `var` trong tham số lambda là gì?

Lambda là cách viết ngắn gọn phần triển khai của một **functional interface** (giao diện có một phương thức trừu tượng). Kiểu của tham số lambda thường được trình biên dịch suy ra từ functional interface mà lambda đang được gán hoặc truyền vào.

Từ **Java 11**, ta có thể viết `var` ngay trước **từng tham số lambda** để thể hiện rõ rằng kiểu của tham số vẫn do trình biên dịch suy ra:

```java
// Các dòng dưới đây là biểu thức khai báo; cần đặt trong phương thức hoặc lớp phù hợp.
java.util.function.Function<String, Integer> a = s -> s.length();
java.util.function.Function<String, Integer> b = (s) -> s.length();
java.util.function.Function<String, Integer> c = (var s) -> s.length();
java.util.function.Function<String, Integer> d = (String s) -> s.length();
```

Trong cả bốn cách, `s` có kiểu `String` và kết quả trả về là `Integer`. Dạng `(var s)` **không tạo kiểu dữ liệu động**, không biến `s` thành `Object` và không thay đổi hành vi của lambda. Trình biên dịch vẫn kiểm tra kiểu tại thời điểm biên dịch.

## 2. Cú pháp và quy tắc bắt buộc

Dạng tổng quát khi có tham số:

```java
(var thamSo) -> bieuThuc
(var thamSo1, var thamSo2) -> bieuThuc
(var thamSo) -> {
    // Các câu lệnh xử lý.
}
```

- Với **một tham số**, phải có dấu ngoặc `( )` nếu dùng `var`: `(var name) -> name.length()`. Chỉ dạng suy luận không ghi `var` mới được phép bỏ ngoặc: `name -> name.length()`.
- Với **nhiều tham số**, nếu chọn cú pháp `var` thì **tất cả tham số đều phải dùng `var`**: `(var left, var right) -> left + right`.
- Không được trộn `var` với kiểu khai báo tường minh, hoặc trộn `var` với tham số chỉ ghi tên. Các dạng `(var x, String y)`, `(String x, var y)` và `(var x, y)` đều lỗi biên dịch.
- Có thể dùng annotation hoặc `final` với từng tham số khai báo bằng `var`, ví dụ `(@InputLabel var name)` hoặc `(final var value)`. `final` cấm gán lại tham số trong thân lambda; bản thân `var` không hàm ý `final`.
- Với lambda không có tham số, dùng `() -> ...`; không có vị trí nào để thêm `var`.

Ví dụ cùng một phép cộng:

```java
java.util.function.BinaryOperator<Integer> sum1 = (a, b) -> a + b;
java.util.function.BinaryOperator<Integer> sum2 = (var a, var b) -> a + b;
java.util.function.BinaryOperator<Integer> sum3 = (Integer a, Integer b) -> a + b;
```

Cả ba đều hợp lệ. Không cần thêm `var` chỉ vì lambda có nhiều tham số; dạng `(a, b)` thường ngắn và dễ đọc hơn khi không cần modifier hoặc annotation.

## 3. Kiểu của `var` được xác định từ đâu?

`var` tại tham số lambda dùng **target typing**: compiler lấy kiểu tham số từ phương thức trừu tượng của functional interface đích, bao gồm tham số kiểu generic đã được xác định.

Ví dụ với `Predicate<String>`, phương thức `test` nhận một `String` và trả về `boolean`; do đó `text` ở lambda bên dưới là `String`:

```java
java.util.function.Predicate<String> hasText = (var text) -> !text.isBlank();
```

Với `BiFunction<Integer, Integer, Integer>`, cả hai tham số được suy ra là `Integer`:

```java
java.util.function.BiFunction<Integer, Integer, Integer> add =
        (var first, var second) -> first + second;
```

Trong ngữ cảnh gọi phương thức như `stream().map(...)` hoặc `stream().filter(...)`, kiểu đích do API của stream cung cấp. Vì vậy, `var` không cho phép bỏ qua việc xác định functional interface. Ví dụ sau **không hợp lệ** vì khai báo biến cục bộ bằng `var` không thể tự suy ra kiểu của một lambda đứng độc lập:

```java
// LỖI BIÊN DỊCH: lambda thiếu kiểu đích của functional interface.
// var action = (var text) -> text.length();

// ĐÚNG: có functional interface làm kiểu đích.
java.util.function.Function<String, Integer> action =
        (var text) -> text.length();
```

Đây là hai cách sử dụng khác nhau của cùng từ `var`: `var` ở **biến cục bộ** cần suy ra kiểu từ biểu thức khởi tạo; `var` ở **tham số lambda** cần suy ra kiểu từ functional interface đích.

## 4. Khi nào `var` thực sự hữu ích?

Lợi ích rõ nhất là có thể **gắn annotation vào tham số có kiểu suy luận** mà không phải viết lại kiểu tường minh, nhất là khi danh sách tham số có generic dài. Annotation phải được khai báo với target phù hợp; một annotation tự thân **không tự kiểm tra null, không tự xác thực dữ liệu** nếu không có công cụ hoặc logic xử lý nó.

Ví dụ hoàn chỉnh dưới đây vừa dùng `var` với một tham số, vừa dùng annotation với hai tham số. Annotation `@InputLabel` chỉ đóng vai trò metadata minh họa, không tạo thêm quy tắc kiểm tra dữ liệu.

Tạo tệp **`VarLambdaDemo.java`**:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Target;
import java.util.List;
import java.util.function.BiFunction;
import java.util.function.Predicate;

public class VarLambdaDemo {
    @Target(ElementType.PARAMETER)
    @interface InputLabel {}

    public static void main(String[] args) {
        Predicate<String> nonBlank = (var text) -> !text.isBlank();

        BiFunction<String, String, String> describe =
                (@InputLabel var name, @InputLabel var course) ->
                        name + " studies " + course;

        List.of("An", "  ", "Binh").stream()
                .filter(nonBlank)
                .map(name -> describe.apply(name, "Java 11"))
                .forEach(System.out::println);
    }
}
```

Biên dịch và chạy bằng **JDK 11 trở lên** (nếu muốn kiểm tra khả năng tương thích Java 11 bằng JDK mới hơn, giữ tùy chọn `--release 11`):

```bash
javac --release 11 -encoding UTF-8 VarLambdaDemo.java
java VarLambdaDemo
```

Kết quả chuẩn:

```text
An studies Java 11
Binh studies Java 11
```

Giải thích:

1. `Predicate<String>` khiến `text` có kiểu `String`; `String.isBlank()` xác định chuỗi rỗng hoặc chỉ gồm khoảng trắng.
2. `BiFunction<String, String, String>` khiến `name` và `course` cùng có kiểu `String` dù khai báo bằng `var`. Cả hai tham số dùng `var` nhất quán và có `@InputLabel`.
3. `filter` loại chuỗi `"  "`; `map` tạo hai chuỗi kết quả; `forEach` in theo thứ tự của stream tuần tự từ `List.of(...)`.
4. Kết quả và hoạt động giống nhau nếu thay `(var text)` bằng `text` và thay các tham số `@InputLabel var` bằng kiểu `String` tương ứng (kèm annotation nếu vẫn cần chúng).

## 5. Lỗi thường gặp và cách khắc phục

| Cách viết hoặc giả định | Vì sao sai | Cách đúng |
| --- | --- | --- |
| `var text -> text.length()` | Có `var` thì bắt buộc đặt tham số trong ngoặc | `(var text) -> text.length()` |
| `(var a, b) -> a + b` | Trộn hai cách khai báo tham số | `(var a, var b) -> a + b` hoặc `(a, b) -> a + b` |
| `(var a, Integer b) -> a + b` | Trộn tham số suy luận và khai báo kiểu tường minh | `(var a, var b)` hoặc `(Integer a, Integer b)` |
| `var f = (var x) -> x + 1;` | Thiếu functional interface làm kiểu đích cho lambda | `UnaryOperator<Integer> f = (var x) -> x + 1;` |
| Dùng `var` cho tham số của phương thức thông thường | Tính năng này áp dụng cho tham số **lambda**, không áp dụng cho tham số phương thức | Khai báo `void process(String text)` |
| Cho rằng `var` né được lỗi sai kiểu dữ liệu | Kiểu suy luận vẫn là kiểu tĩnh và vẫn bị compiler kiểm tra | Dùng đúng functional interface, kiểu generic và phép toán |

Các đoạn minh họa lỗi trong bảng **không phải chương trình độc lập** để chạy; mục đích là nhận diện quy tắc cú pháp.

## 6. Hướng dẫn sử dụng trong mã hiện nay

- **Ưu tiên `name -> ...` hoặc `(a, b) -> ...`** nếu lambda ngắn và không cần annotation/`final`. Việc thêm `var` không giúp tăng hiệu năng hoặc thay đổi cách stream hoạt động.
- **Dùng `(var name)` hoặc `(var a, var b)`** khi cần annotation/modifier trên tham số mà vẫn muốn compiler suy luận kiểu, hoặc khi cần nhất quán trong một đoạn mã theo quy ước dự án.
- **Dùng kiểu tường minh** như `(String name) -> ...` khi kiểu cần được trình bày rõ để người đọc hiểu phép toán hoặc để hỗ trợ lựa chọn overload phù hợp.
- Dự án phải biên dịch với **language level Java 11+**. Nếu target là Java 8 hoặc 10, cú pháp `var` ở tham số lambda không được hỗ trợ.

## 7. Ghi nhớ

`var` trong tham số lambda là **cú pháp khai báo có suy luận kiểu** được hỗ trợ từ Java 11 và tiếp tục hợp lệ trong các phiên bản Java hiện đại. Nó cần ngoặc, phải dùng nhất quán cho toàn bộ tham số của cùng lambda và vẫn phụ thuộc vào functional interface đích. Giá trị thực tế chính là kết hợp **kiểu suy luận** với **annotation hoặc `final`**, chứ không phải một cơ chế kiểu dữ liệu mới.

**Tài liệu kỹ thuật:** [JEP 323 — Local-Variable Syntax for Lambda Parameters](https://openjdk.org/jeps/323); [Java Language Specification `15.27.1 — Lambda Parameters](https://docs.oracle.com/javase/specs/jls/se25/html/jls-15.html#jls-15.27.1).