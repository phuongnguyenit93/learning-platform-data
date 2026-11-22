# Lựa chọn `var` khi giúp làm rõ metadata hoặc ý định trong lambda (Java 11+)

## Mục tiêu

Sau bài này, bạn có thể quyết định lúc nào nên viết tham số lambda bằng `var`, lúc nào nên bỏ `var`, và lúc nào phải khai báo kiểu tường minh. Trọng tâm là **dùng `var` có chủ đích để gắn annotation hoặc modifier như `final`**, chứ không thêm cú pháp chỉ vì Java cho phép.

Kiến thức áp dụng cho Java 11 và các phiên bản Java hiện đại hỗ trợ JEP 323. Không cần thư viện ngoài JDK để chạy ví dụ chính.

## 1. Hiểu đúng vai trò của `var` trong lambda

Java suy luận kiểu tham số lambda từ **kiểu đích (target type)**, thường là một functional interface như `Function<T, R>`, `BiFunction<T, U, R>` hoặc `Predicate<T>`. Từ Java 11, có thể viết:

```java
Function<String, String> a = text -> text.strip();
Function<String, String> b = (var text) -> text.strip();
Function<String, String> c = (String text) -> text.strip();
```

Ba biểu thức trên đều nhận `String` và trả về `String` trong ngữ cảnh đã cho. Viết `var` **không tự suy ra kiểu tốt hơn** so với cách `text -> ...`; cả hai cùng dựa vào target type. `var` cũng không biến Java thành ngôn ngữ kiểu động. Trình biên dịch vẫn kiểm tra kiểu tại thời điểm biên dịch.

Điểm khác biệt thực dụng: `(var text)` cho phép dùng cú pháp khai báo tham số, trong đó có **annotation** và **`final`**, mà vẫn không phải lặp lại `String`.

| Cách viết | Khi nào phù hợp |
| --- | --- |
| `text -> ...` | Mặc định cho lambda một tham số, không cần annotation/modifier. |
| `(left, right) -> ...` | Mặc định cho nhiều tham số khi kiểu đích rõ ràng. |
| `(var text) -> ...` | Cần khai báo tham số theo cú pháp `var`, thường để thêm metadata/modifier. |
| `(@NonNull var text) -> ...` | Muốn gắn annotation có ý nghĩa với công cụ/quy ước của dự án. |
| `(final var left, final var right) -> ...` | Muốn tuyên bố rõ không gán lại các biến tham số. |
| `(String text) -> ...` | Kiểu tường minh giúp người đọc hiểu hơn hoặc cần cho ngữ cảnh khai báo kiểu. |

## 2. Dùng `var` khi annotation làm rõ metadata

Annotation có thể ghi nhận hợp đồng, ý định hoặc thông tin để công cụ phân tích nguồn/tĩnh xử lý. Ví dụ, dự án có quy ước đánh dấu tham số được kỳ vọng khác `null`. Cú pháp `(@NonNull var value) -> ...` thể hiện quy ước ngay tại tham số mà không cần ghi `String` một lần nữa.

**Quan trọng:** annotation chỉ có tác dụng theo định nghĩa của nó và công cụ sử dụng nó. Một annotation tự tạo tên `@NonNull` **không tự động kiểm tra null**, không tự khiến trình biên dịch Java chuẩn từ chối `null`, và không đương nhiên xuất hiện trong reflection. Khả năng tồn tại trong bytecode/runtime phụ thuộc `@Retention` cùng cách công cụ xử lý annotation. Muốn kiểm tra ở runtime, phải dùng logic thực thi như `Objects.requireNonNull(...)`.

Ví dụ hoàn chỉnh sau minh họa cả metadata qua annotation và ý định không gán lại qua `final var`.

**Tệp: `VarLambdaIntentDemo.java`** (Java 11+)

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.util.Objects;
import java.util.function.BiFunction;
import java.util.function.Function;

public class VarLambdaIntentDemo {

    @Target(ElementType.PARAMETER)
    @Retention(RetentionPolicy.SOURCE)
    @interface NonNull {}

    public static void main(String[] args) {
        Function<String, String> canonicalName =
                (@NonNull var name) ->
                        Objects.requireNonNull(name, "name").strip();

        BiFunction<String, String, String> key =
                (final var namespace, final var identifier) ->
                        namespace + ":" + identifier;

        System.out.println(canonicalName.apply("  Alice  "));
        System.out.println(key.apply("user", "42"));
    }
}
```

Chạy:

```bash
javac VarLambdaIntentDemo.java
java VarLambdaIntentDemo
```

Kết quả chính xác:

```text
Alice
user:42
```

Phân tích:

- `Function<String, String>` cho trình biên dịch biết `name` là `String`; `var` không chọn kiểu độc lập.
- `@NonNull` trong ví dụ được phép gắn vào **khai báo tham số** nhờ `@Target(ElementType.PARAMETER)`. `@Retention(SOURCE)` nghĩa là annotation này chỉ được giữ trong nguồn, không phải một cơ chế kiểm tra runtime.
- `Objects.requireNonNull(name, "name")` mới là thao tác kiểm tra null khi chạy; `strip()` cắt khoảng trắng ở đầu/cuối và có sẵn từ Java 11.
- `final var namespace` và `final var identifier` cho biết hai **biến tham số** không được gán giá trị mới trong thân lambda. Chúng vẫn được suy luận là `String` từ `BiFunction<String, String, String>`.

Trong dự án thực tế, annotation có thể đến từ thư viện hoặc hệ thống kiểm tra tĩnh. Hãy dùng đúng annotation, `@Target`, `@Retention` và cấu hình công cụ mà dự án quy định; đừng mặc định các annotation cùng tên có cùng hành vi.

## 3. Dùng `final var` khi muốn làm rõ ý định

`final` trên tham số lambda ngăn **gán lại biến tham số** trong thân lambda. Điều này có thể hữu ích nếu nhóm muốn giữ tham số đầu vào ổn định khi đọc một logic dài hoặc quan trọng.

```java
BiFunction<Integer, Integer, Integer> sum =
        (final var first, final var second) -> first + second;
```

Vì kiểu đích là `BiFunction<Integer, Integer, Integer>`, hai tham số được suy luận là `Integer`. Modifier `final` truyền đạt ý định; nó **không bắt buộc** để đoạn cộng này hoạt động. Với lambda nhỏ, `(first, second) -> first + second` thường gọn và đủ rõ.

Lưu ý: `final` chỉ cấm gán lại tham chiếu/biến tham số; nó **không tự biến đối tượng được tham chiếu thành bất biến**. Với một `List` có thể sửa đổi, `final var items` vẫn có thể gọi `items.add(...)` nếu API và ngữ cảnh cho phép. Muốn bất biến dữ liệu, cần loại đối tượng hoặc thiết kế bất biến phù hợp.

## 4. Quy tắc cú pháp bắt buộc

1. **Nếu chọn `var`, tất cả tham số của cùng một lambda đều phải dùng `var`.** Có thể gắn annotation hoặc `final` lên một số tham số theo nhu cầu, nhưng không được pha trộn hình thức khai báo kiểu.
2. **Không trộn `var` với tham số bỏ kiểu hoặc ghi kiểu tường minh** trong cùng danh sách.
3. **Một tham số dùng `var` phải có dấu ngoặc tròn**: `(var value) -> ...`. Dạng rút gọn `value -> ...` chỉ dùng khi không khai báo kiểu/modifier.
4. **Lambda cần target type.** `var` ở tham số không tự cung cấp kiểu đích cho toàn bộ biểu thức lambda.

Ví dụ hợp lệ trong ngữ cảnh có target type:

```java
BiFunction<Integer, Integer, Integer> add1 = (x, y) -> x + y;
BiFunction<Integer, Integer, Integer> add2 = (var x, var y) -> x + y;
BiFunction<Integer, Integer, Integer> add3 = (Integer x, Integer y) -> x + y;
Function<String, Integer> length = (var s) -> s.length();
```

Các dòng sau **cố ý sai, không dùng như chương trình chạy**:

```java
// Sai: trộn var với tham số suy luận kiểu không ghi var.
BiFunction<Integer, Integer, Integer> bad1 = (var x, y) -> x + y;

// Sai: trộn var với kiểu tường minh.
BiFunction<Integer, Integer, Integer> bad2 = (var x, Integer y) -> x + y;

// Sai: var phải nằm trong danh sách tham số có ngoặc.
Function<String, String> bad3 = var s -> s.strip();

// Sai: không có target type cho lambda.
var bad4 = (var s) -> s.strip();
```

Cần phân biệt các lỗi trên với việc **cố ý dùng kiểu tường minh cho toàn bộ tham số**; ví dụ `(String left, String right) -> ...` là hợp lệ khi có target type phù hợp.

## 5. Chọn cách viết qua tình huống thực tế

### Tình huống A — Không cần metadata: ưu tiên ngắn gọn

```java
Function<String, String> normalize = value -> value.strip();
```

`(var value) -> value.strip()` cũng hợp lệ, nhưng không làm rõ thêm loại dữ liệu, hợp đồng hay ý định. Trong ví dụ này, `var` chỉ tăng ký tự. Hãy giữ cách viết ngắn nhất mà nhóm đọc dễ.

### Tình huống B — Có annotation mang ý nghĩa rõ ràng: cân nhắc `var`

Giả sử dự án đã thiết lập quy ước hoặc bộ kiểm tra nullness phù hợp:

```java
Function<String, String> normalize =
        (@NonNull var value) -> value.strip();
```

Đoạn này là **mẫu minh họa phụ thuộc khai báo `@NonNull` và quy ước dự án**; bạn có thể dùng định nghĩa annotation trong chương trình ở mục 2 để biên dịch. Ý nghĩa kiểm tra tĩnh của `@NonNull` chỉ xuất hiện khi công cụ nhận diện annotation đó. Khi cần cưỡng chế kiểm tra null lúc chạy, vẫn phải dùng logic thực thi thích hợp.

Nếu đã cần khai báo cả kiểu, `(@NonNull String value) -> ...` cũng là một lựa chọn hợp lệ; `var` không phải cách duy nhất để gắn annotation.

### Tình huống C — Cần thể hiện không gán lại: dùng `final` có chọn lọc

```java
BiFunction<String, String, String> combine =
        (final var prefix, final var id) -> prefix + "-" + id;
```

Dùng cách này khi quy tắc nhóm hoặc độ phức tạp của code khiến `final` có ích. Đừng thêm `final var` hàng loạt cho mọi lambda nhỏ nếu nó làm khó đọc.

### Tình huống D — Kiểu đích không rõ: làm rõ kiểu đích trước

```java
Function<String, Integer> countCharacters = s -> s.length();
```

Tên biến, kiểu `Function<String, Integer>` và phương thức `length()` đã giúp đọc được luồng dữ liệu. Nếu viết `(var s)`, kiểu `s` vẫn chỉ đến từ target type. Để làm rõ một hợp đồng không rõ, hãy cân nhắc đặt tên, khai báo functional interface, hoặc khai báo kiểu tham số tường minh thích hợp; riêng `var` không giải quyết sự mơ hồ.

## 6. Các lỗi nhận thức thường gặp

- **“Dùng `var` sẽ khiến lambda chạy nhanh/chậm hơn.”** Không có bảo đảm hiệu năng nào đến từ việc thay `(x)` bằng `(var x)`; đây là lựa chọn cú pháp ở nguồn, không phải cấu hình tối ưu hóa.
- **“Có `var` thì khỏi cần kiểu đích.”** Sai: lambda vẫn phụ thuộc ngữ cảnh kiểu của functional interface.
- **“`@NonNull var` tự chặn `null`.”** Sai nếu không có công cụ/logic tương ứng. Phân biệt mô tả hợp đồng, kiểm tra tĩnh và kiểm tra runtime.
- **“`final var` làm dữ liệu bất biến.”** Sai: nó ngăn gán lại biến tham số, không tự khóa trạng thái bên trong đối tượng.
- **“Có thể chỉ đổi một tham số sang `var`.”** Sai nếu lambda có nhiều tham số: phải dùng `var` cho tất cả tham số trong danh sách.
- **“Dùng `var` luôn sạch hơn kiểu tường minh.”** Không nhất thiết; lựa chọn phải giúp người đọc hiểu chức năng, hợp đồng và kiểu dữ liệu.

## 7. Checklist khi review code

Trước khi thêm `var` vào tham số lambda, tự hỏi:

1. Có annotation cụ thể cần gắn lên tham số, với `@Target` và công cụ xử lý rõ ràng không?
2. `final` có diễn đạt ý định quan trọng về việc không gán lại biến tham số không?
3. Kiểu đích đã đủ rõ để người đọc biết kiểu suy luận chưa?
4. Nếu nhiều tham số, tất cả đã sử dụng cùng hình thức `var` chưa?
5. Cách viết sau sửa có dễ đọc hơn cách bỏ `var` hoặc dùng kiểu tường minh không?

**Nguyên tắc áp dụng:** mặc định dùng lambda tham số suy luận kiểu ngắn gọn; chọn `var` khi annotation/modifier mang thêm ý nghĩa thật; chọn kiểu tường minh khi thông tin kiểu thực sự giúp đọc hiểu. Cả ba đều là cú pháp Java còn được hỗ trợ.

## Tự kiểm tra nhanh

Với `BiFunction<String, String, String> f = ...`, xem ba cách viết:

- `(left, right) -> left + right`: hợp lệ, phù hợp khi không cần metadata.
- `(@NonNull var left, var right) -> left + right`: hợp lệ nếu `@NonNull` được khai báo đúng mục tiêu annotation; các tham số đều dùng `var`.
- `(@NonNull var left, String right) -> left + right`: không hợp lệ vì trộn `var` với kiểu tường minh.

Khi phân tích một lambda thực tế, hãy chỉ rõ annotation/modifier cụ thể mang đến thông tin gì. Nếu không có câu trả lời thuyết phục, `var` thường không cần thiết.

## Tài liệu chuẩn để đối chiếu

- [OpenJDK JEP 323 — Local-Variable Syntax for Lambda Parameters](https://openjdk.org/jeps/323): tính năng được hoàn thiện trong Java 11, mục đích và quy tắc đồng nhất của `var`.
- [Oracle — Local Variable Type Inference (Java 17)](https://docs.oracle.com/en/java/javase/17/language/local-variable-type-inference.html): cú pháp, target type và các cách trộn tham số không hợp lệ.
- [Java Language Specification, Java SE 25 — §15.27 Lambda Expressions](https://docs.oracle.com/javase/specs/jls/se25/html/jls-15.html#jls-15.27): ngữ nghĩa lambda, tham số, modifier và kiểm tra kiểu theo đặc tả ngôn ngữ.