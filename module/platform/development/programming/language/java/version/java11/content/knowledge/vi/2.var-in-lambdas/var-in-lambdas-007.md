# Java 11 — `var` trong lambda: yêu cầu dấu ngoặc và các cách khai báo không hợp lệ

## 1. `var` trong tham số lambda có ý nghĩa gì?

Từ Java 11 (JEP 323), có thể viết `var` trước **từng tham số** của một lambda để trình biên dịch suy luận kiểu của tham số từ *kiểu đích* (target type), thường là một functional interface. Ví dụ:

```java
BiFunction<Integer, Integer, Integer> sum = (var a, var b) -> a + b;
```

Ở đây `a` và `b` đều được suy luận là `Integer` vì kiểu đích là `BiFunction<Integer, Integer, Integer>`. Viết `(a, b) -> a + b` cũng hợp lệ và có cùng ý nghĩa về kiểu. `var` **không** khiến tham số trở thành kiểu động và không tự xác định kiểu khi thiếu ngữ cảnh functional interface.

Bài này tập trung vào hai câu hỏi thực tế: **khi nào phải có cặp ngoặc tròn `(...)` trước `->`, và những cách ghi tham số nào bị Java từ chối khi dùng `var`?** Các quy tắc này vẫn áp dụng trong Java hiện đại.

## 2. Quy tắc dấu ngoặc tròn

| Danh sách tham số trước `->` | Hợp lệ? | Lý do |
| --- | --- | --- |
| `() -> "ready"` | Có | Lambda không tham số: cặp ngoặc rỗng bắt buộc. |
| `name -> name.strip()` | Có | Một tham số **chỉ ghi tên**, được bỏ ngoặc. |
| `(name) -> name.strip()` | Có | Một tên tham số suy luận kiểu; có ngoặc vẫn đúng. |
| `(var name) -> name.strip()` | Có | Có `var` thì **bắt buộc** đặt danh sách tham số trong `(...)`. |
| `var name -> name.strip()` | **Không** | Không được bỏ ngoặc khi có bộ khai báo `var name`. |
| `(String name) -> name.strip()` | Có | Tham số ghi kiểu tường minh cũng cần ngoặc. |
| `(a, b) -> a + b` | Có | Từ hai tham số trở lên luôn cần ngoặc. |
| `(var a, var b) -> a + b` | Có | Tất cả tham số đều khai báo `var`. |
| `(int a, int b) -> a + b` | Có | Tất cả tham số khai báo kiểu tường minh. |

**Mẹo nhớ:** Chỉ lambda có **đúng một tham số dạng tên trần** (`x -> ...`) mới được bỏ ngoặc. Đã viết `var`, kiểu tường minh, `final` hoặc annotation thì phải dùng `(...)`. Dấu ngoặc ở đây là một phần cú pháp khai báo tham số; không phải phép nhóm biểu thức tùy ý, nên `((var x)) -> ...` cũng sai.

## 3. Không được trộn các kiểu khai báo tham số

Với lambda nhiều tham số, chọn **một** trong ba cách cho toàn bộ danh sách:

1. **Suy luận kiểu, chỉ ghi tên:** `(a, b) -> a + b`.
2. **Suy luận kiểu, ghi `var` cho tất cả:** `(var a, var b) -> a + b`.
3. **Ghi kiểu tường minh cho tất cả:** `(Integer a, Integer b) -> a + b`.

Không được kết hợp những cách trên trong cùng một danh sách:

```java
// Các ví dụ sau cố ý SAI; không đặt trong chương trình cần biên dịch.
(var a, b) -> a + b           // var + tên trần
(a, var b) -> a + b           // tên trần + var
(var a, Integer b) -> a + b   // var + kiểu tường minh
(Integer a, var b) -> a + b   // kiểu tường minh + var
(a, Integer b) -> a + b       // tên trần + kiểu tường minh
```

Quy tắc đồng nhất áp dụng cho **cách biểu diễn kiểu của tham số**, không đòi mọi tham số phải có cùng kiểu dữ liệu. Chẳng hạn, `(String key, Integer count) -> ...` là danh sách kiểu tường minh hợp lệ nếu phù hợp với functional interface. Với `var`, mọi tham số phải có `var`, còn `final` hay annotation có thể xuất hiện ở tham số cần dùng.

## 4. `final` và annotation: lý do hữu ích để dùng `var`

Tham số dạng tên trần như `name -> ...` không chấp nhận modifier. Khi cần gắn annotation áp dụng cho tham số, hoặc ghi rõ `final`, có thể viết `(@InputChecked final var name) -> ...`. Annotation phải được khai báo và có target phù hợp; `@InputChecked` dưới đây là annotation tự định nghĩa cho ví dụ, không phải annotation có sẵn trong JDK.

- `(final var name) -> ...`: hợp lệ; trong thân lambda không thể gán lại `name`.
- `(@InputChecked var name) -> ...`: hợp lệ khi `@InputChecked` có `@Target(ElementType.PARAMETER)`.
- `(@InputChecked final var name) -> ...`: hợp lệ, kết hợp annotation và `final`.
- `(final name) -> ...` hoặc `(@InputChecked name) -> ...`: không hợp lệ; thiếu `var` hoặc kiểu tường minh sau modifier.

Không cần thêm `var` vào mọi lambda: khi không dùng annotation/modifier, dạng `x -> ...` hoặc `(x, y) -> ...` thường ngắn và dễ đọc hơn.

## 5. Ví dụ Java 11+ chạy được

Lưu đoạn sau vào **`LambdaVarRulesDemo.java`**:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Target;
import java.util.function.BiFunction;
import java.util.function.Function;
import java.util.function.Supplier;

@Target(ElementType.PARAMETER)
@interface InputChecked {}

public class LambdaVarRulesDemo {
    public static void main(String[] args) {
        Supplier<String> noArgs = () -> "ready";
        Function<String, String> concise = word -> word.toUpperCase();
        Function<String, String> singleVar = (var word) -> word.strip();
        BiFunction<Integer, Integer, Integer> sum =
                (var left, var right) -> left + right;
        Function<String, String> annotated =
                (@InputChecked final var value) -> value.strip();
        BiFunction<String, String, String> typed =
                (String a, String b) -> a + "-" + b;

        System.out.println(noArgs.get());
        System.out.println(concise.apply("java"));
        System.out.println(singleVar.apply("  OK  "));
        System.out.println(sum.apply(7, 5));
        System.out.println(annotated.apply("  safe  "));
        System.out.println(typed.apply("left", "right"));
    }
}
```

Biên dịch và chạy bằng JDK 11 trở lên (tùy chọn `--release 11` giúp kiểm tra mã tương thích Java 11):

```bash
javac --release 11 LambdaVarRulesDemo.java
java LambdaVarRulesDemo
```

Đầu ra chính xác:

```text
ready
JAVA
OK
12
safe
left-right
```

Giải thích: `noArgs` dùng `()`; `concise` có một tên trần nên bỏ ngoặc được; `singleVar` bắt buộc có ngoặc; `sum` dùng `var` nhất quán; `annotated` cho thấy `var` hỗ trợ modifier/annotation; `typed` cho thấy khai báo tường minh cũng hợp lệ. Phương thức `String.strip()` có trong Java 11+.

## 6. Các cách khai báo không hợp lệ và cách sửa

Các dòng bên dưới là **ví dụ lỗi độc lập**, cố ý không biên dịch. Chúng giả sử đã import `java.util.function.Function` và `BiFunction`:

| Khai báo sai | Vì sao sai? | Cách sửa |
| --- | --- | --- |
| `Function<String,String> f = var x -> x.strip();` | `var` thiếu cặp ngoặc tham số. | `(var x) -> x.strip()` hoặc `x -> x.strip()` |
| `BiFunction<Integer,Integer,Integer> f = (var a, b) -> a + b;` | Trộn `var` và tên trần. | `(var a, var b) -> a + b` |
| `BiFunction<Integer,Integer,Integer> f = (a, var b) -> a + b;` | Trộn tên trần và `var`. | `(a, b) -> a + b` |
| `BiFunction<Integer,Integer,Integer> f = (var a, int b) -> a + b;` | Trộn suy luận và kiểu tường minh. | `(int a, int b) -> a + b` hoặc cả hai `var` |
| `BiFunction<Integer,Integer,Integer> f = (int a, var b) -> a + b;` | Trộn kiểu tường minh và `var`. | `(int a, int b) -> a + b` hoặc cả hai `var` |
| `Function<String,String> f = (var x,) -> x.strip();` | Dấu phẩy thừa ở cuối danh sách. | `(var x) -> x.strip()` |
| `Function<String,String> f = ((var x)) -> x.strip();` | Thừa một lớp ngoặc quanh khai báo tham số. | `(var x) -> x.strip()` |
| `Function<String[],Integer> f = (var values[]) -> values.length;` | Không được gắn `[]` sau tên của tham số khai báo bằng `var`. | `(var values) -> values.length` |
| `Function<String[],Integer> f = (var... values) -> values.length;` | `var` không dùng làm kiểu của khai báo varargs. | `(String[] values) -> values.length` hoặc `(String... values) -> values.length` |
| `Function<String,String> f = (final x) -> x.strip();` | Modifier `final` yêu cầu `var` hoặc một kiểu tường minh. | `(final var x) -> x.strip()` |
| `BiFunction<Integer,Integer,Integer> f = (var x, var x) -> x;` | Hai tham số có cùng tên. | Đổi tên, ví dụ `(var x, var y) -> x` |
| `var f = (var x) -> x.strip();` | Lambda cần kiểu đích để suy luận tham số; một biến `var` đơn lẻ không cung cấp kiểu đích. | `Function<String,String> f = (var x) -> x.strip();` |

**Phân biệt lỗi cú pháp và lỗi kiểu:** `(var values)` vẫn hoàn toàn hợp lệ khi kiểu suy luận là mảng, ví dụ `Function<String[], Integer> size = (var values) -> values.length;`. Lỗi nằm ở việc tự viết `values[]` hoặc `var...` trong khai báo, không phải ở chuyện `var` có thể suy luận một kiểu mảng.

Kể cả cú pháp đúng, lambda vẫn phải phù hợp chữ ký của functional interface: số tham số, kiểu tham số, kiểu trả về và checked exception. Ví dụ `Function<String, Integer> length = (var s) -> s.length();` hợp lệ vì `s` được suy luận là `String` và thân trả `int` (được boxing thành `Integer`).

## 7. Quy trình kiểm tra nhanh khi trình biên dịch báo lỗi

1. **Đếm tham số:** không tham số dùng `()`; một tên trần có thể bỏ ngoặc; mọi trường hợp `var` và từ hai tham số trở lên đều dùng `(...)`.
2. **Soát cả danh sách:** nếu đã chọn `var` thì từng tham số phải có `var`; đừng trộn với tên trần hoặc kiểu tường minh.
3. **Soát modifier:** `final` và annotation chỉ có trong cách khai báo đầy đủ (`var` hoặc kiểu cụ thể); annotation cần target đúng.
4. **Soát cấu trúc:** không có dấu phẩy cuối, ngoặc lồng thừa, tên trùng, `var name[]` hoặc `var...`.
5. **Soát kiểu đích:** khai báo biến bằng `Function`, `BiFunction` hay interface chức năng tương ứng; hoặc truyền lambda vào vị trí mà kiểu đích đã xác định.
6. **Biên dịch đúng phiên bản:** tính năng `var` ở tham số lambda bắt đầu từ Java 11; các lệnh ở mục 5 dùng `--release 11` để kiểm tra tính tương thích.

**Lưu ý về Java mới hơn:** từ Java 22, `_` có thể được dùng làm *tham số vô danh* của lambda khi không cần gọi tên tham số. Đó là một tính năng riêng, không thay đổi quy tắc `var`/dấu ngoặc/trộn kiểu ở trên. Những ví dụ chạy được trong bài được giữ tương thích Java 11.

## 8. Ghi nhớ

- `x -> ...` là trường hợp một tham số tên trần có thể bỏ `(...)`.
- `(var x) -> ...` mới là cách viết đúng khi dùng `var`; `var x -> ...` sai.
- Lambda nhiều tham số: **tất cả tên trần**, **tất cả `var`**, hoặc **tất cả kiểu tường minh**.
- `var` hỗ trợ annotation và `final` trên tham số; kiểu vẫn được suy luận từ functional interface.
- Một khai báo lambda phải có kiểu đích hợp lệ; `var f = (var x) -> ...` không tự cung cấp kiểu đích.

### Tài liệu đối chiếu

- [OpenJDK JEP 323 — Local-Variable Syntax for Lambda Parameters](https://openjdk.org/jeps/323)
- [Java Language Specification, `15.27.1 — Lambda Parameters](https://docs.oracle.com/javase/specs/jls/se25/html/jls-15.html#jls-15.27.1)
- [Oracle Java Language Updates — Local Variable Type Inference](https://docs.oracle.com/en/java/javase/20/language/local-variable-type-inference.html)
