# Method reference và kiểu đích của biểu thức

Method reference là cách viết gọn để chuyển một phương thức hoặc constructor thành hành động có thể truyền như một giá trị, bằng toán tử `::`. Ví dụ, `Integer::parseInt` có thể thay cho lambda `text -> Integer.parseInt(text)`. Tuy nhiên, bản thân method reference **không tự mang một kiểu hàm độc lập**: trình biên dịch cần biết kiểu đích để xác định tham số, kiểu trả về và phương thức cụ thể nào phù hợp.

## 1. Kiểu đích cung cấp điều gì?

Kiểu đích (target type) thường là một functional interface: interface có đúng một phương thức trừu tượng cần triển khai (SAM, *single abstract method*). Những phương thức `default` và `static` không làm tăng số SAM.

Ví dụ:

~~~java
Function<String, Integer> parser = Integer::parseInt;
~~~

Ở đây, `Function<String, Integer>` là kiểu đích. Phương thức trừu tượng `apply(String)` nhận một `String` và trả về một `Integer`. Vì vậy trình biên dịch tìm một cách gọi tương thích với chữ ký đó; `Integer.parseInt(String)` nhận chuỗi và trả về `int`, có thể được boxing thành `Integer`.

Kiểu đích thường đến từ một trong các ngữ cảnh sau:

- **Khai báo hoặc phép gán:** `Function<String, Integer> parser = Integer::parseInt;`
- **Tham số phương thức:** nếu `map` nhận `Function<String, Integer>`, đối số `Integer::parseInt` được kiểm tra theo kiểu đó.
- **Giá trị trả về:** phương thức trả về `Function<String, Integer>` có thể dùng `return Integer::parseInt;`.
- **Ép kiểu tường minh:** `(Function<String, Integer>) Integer::parseInt` cung cấp kiểu đích khi cần chọn một cách diễn giải cụ thể.

Không có kiểu đích, biểu thức như `var parser = Integer::parseInt;` không hợp lệ: `var` cần suy ra kiểu từ giá trị khởi tạo, nhưng method reference không có kiểu độc lập để suy ra theo cách đó. Hãy khai báo kiểu functional interface hoặc cung cấp ngữ cảnh kiểu rõ ràng.

## 2. Các dạng method reference và cách đọc

| Dạng | Ví dụ | Kiểu đích có thể dùng | Ý nghĩa |
|---|---|---|---|
| Phương thức static | `Integer::parseInt` | `Function<String, Integer>` | Tham số hàm được truyền làm đối số cho phương thức static. |
| Phương thức instance trên một đối tượng đã có (bound) | `System.out::println` | `Consumer<String>` | Đối tượng nhận lời gọi đã được xác định là `System.out`. |
| Phương thức instance trên một đối tượng được lấy từ tham số đầu (unbound) | `String::trim` | `Function<String, String>` | Tham số đầu tiên trở thành đối tượng nhận lời gọi. |
| Constructor | `StringBuilder::new` | `Function<String, StringBuilder>` | Gọi constructor nhận một chuỗi. |
| Constructor mảng | `String[]::new` | `IntFunction<String[]>` | Nhận độ dài và tạo mảng chuỗi. |
| Phương thức hiện tại hoặc lớp cha | `this::validate`, `super::toString` | Functional interface tương thích | Gọi phương thức trên đối tượng hiện tại hoặc phần triển khai của lớp cha. |

Dạng `String::trim` cần đặc biệt chú ý: dù cú pháp có tên lớp, đây là tham chiếu đến **phương thức instance**. Với kiểu đích `Function<String, String>`, tham số `String` của `apply` trở thành receiver để gọi `trim()`. Tương tự, `String::concat` có thể phù hợp với `BiFunction<String, String, String>`: tham số đầu là receiver, tham số thứ hai là đối số truyền cho `concat`.

Kiểu đích cũng quyết định số tham số mà hàm nhận. Constructor không tham số thường dùng với `Supplier<T>`; constructor một tham số có thể dùng với `Function<T, R>`; constructor mảng thường dùng với `IntFunction<T[]>`. Nếu không có functional interface chuẩn phù hợp, có thể định nghĩa một functional interface riêng.

## 3. Ví dụ Java 17+ chạy được

Lưu mã sau thành `TargetTypeMethodReference.java`. Ví dụ minh họa nhiều dạng method reference và cho thấy kiểu đích ảnh hưởng đến việc chọn overload.

~~~java
import java.util.function.BiFunction;
import java.util.function.Function;
import java.util.function.IntFunction;

public class TargetTypeMethodReference {
    static String surround(String value) {
        return "[" + value + "]";
    }

    static String render(Object value) {
        return "Object";
    }

    static String render(String value) {
        return "String";
    }

    public static void main(String[] args) {
        Function<String, Integer> parse = Integer::parseInt;
        Function<String, String> trim = String::trim;
        Function<String, String> surrounder =
                TargetTypeMethodReference::surround;
        BiFunction<String, String, String> concat = String::concat;
        Function<String, StringBuilder> builder = StringBuilder::new;
        IntFunction<String[]> arrayFactory = String[]::new;

        Function<String, String> renderString =
                TargetTypeMethodReference::render;
        Function<Object, String> renderObject =
                TargetTypeMethodReference::render;

        System.out.println("parse=" + parse.apply("42"));
        System.out.println("trim='" + trim.apply("  Java  ") + "'");
        System.out.println("surround=" + surrounder.apply("Java"));
        System.out.println("concat=" + concat.apply("Java", " 17"));
        System.out.println("builder=" + builder.apply("code"));
        System.out.println("arrayLength=" + arrayFactory.apply(3).length);
        System.out.println("renderString=" + renderString.apply("x"));
        System.out.println("renderObject=" + renderObject.apply("x"));
    }
}
~~~

Chạy bằng JDK 17 trở lên:

~~~text
javac TargetTypeMethodReference.java
java TargetTypeMethodReference
~~~

Kết quả chuẩn:

~~~text
parse=42
trim='Java'
surround=[Java]
concat=Java 17
builder=code
arrayLength=3
renderString=String
renderObject=Object
~~~

Giải thích các kiểu đích chính:

- `parse` có kiểu `Function<String, Integer>`, nên `Integer::parseInt` được dùng như hàm nhận chuỗi và trả về số nguyên.
- `trim` có kiểu `Function<String, String>`. Với `String::trim`, tham số chuỗi trở thành receiver.
- `concat` có kiểu `BiFunction<String, String, String>`, nên cần hai tham số: chuỗi nhận lời gọi và chuỗi ghép thêm.
- `builder` yêu cầu hàm nhận `String` và trả về `StringBuilder`, phù hợp với constructor `StringBuilder(String)`.
- `arrayFactory` có kiểu `IntFunction<String[]>`, vì constructor mảng nhận độ dài kiểu `int`.
- `renderString` và `renderObject` cùng trỏ đến tên phương thức overloaded `render`, nhưng kiểu tham số đầu vào của functional interface khác nhau. Với `Function<String, String>`, overload `render(String)` phù hợp hơn; với `Function<Object, String>`, chữ ký cần nhận `Object` nên overload `render(Object)` được chọn. Việc chọn overload diễn ra lúc biên dịch, dựa trên kiểu tĩnh trong ngữ cảnh, không dựa trên kiểu thực tế của đối tượng khi chạy.

## 4. Kiểu đích và overload resolution

Khi tên phương thức có nhiều overload, trình biên dịch sử dụng chữ ký hàm của kiểu đích để tìm overload phù hợp. Các yếu tố quan trọng gồm:

1. **Số lượng tham số:** kiểu đích có một tham số không thể dùng một overload cần hai tham số, trừ khi có dạng tham chiếu khác phù hợp.
2. **Kiểu tham số:** các kiểu tham số của functional interface phải tương thích với tham số/receiver của phương thức được tham chiếu.
3. **Kiểu trả về:** kết quả của phương thức phải tương thích với kiểu trả về của SAM, kể cả các chuyển đổi hợp lệ như boxing, unboxing và widening primitive.
4. **Tính mơ hồ:** nếu nhiều overload vẫn tương thích mà không có lựa chọn cụ thể nhất, biểu thức không biên dịch; cần làm rõ kiểu đích.

Ví dụ về tình huống mơ hồ:

~~~java
import java.util.function.Function;
import java.util.function.ToIntFunction;

static void accept(Function<String, Integer> parser) {}
static void accept(ToIntFunction<String> parser) {}

// Có thể mơ hồ: Integer::parseInt tương thích với cả hai kiểu đích.
accept(Integer::parseInt);

// Làm rõ kiểu đích bằng ép kiểu:
accept((Function<String, Integer>) Integer::parseInt);
accept((ToIntFunction<String>) Integer::parseInt);
~~~

`Function<String, Integer>` trả về kiểu tham chiếu `Integer`; `ToIntFunction<String>` trả về kiểu nguyên thủy `int`. Cả hai đều có thể sử dụng `Integer.parseInt(String)`, vì vậy chỉ nhìn vào tên phương thức là chưa đủ để chọn overload của `accept`. Hai lời gọi có ép kiểu làm rõ functional interface mong muốn. Đoạn này là ví dụ riêng về overload resolution, không phải phần tiếp nối bên trong lớp chạy ở mục trước.

## 5. Kiểu đích trong generic và lời gọi phương thức

Kiểu đích có thể tham gia vào quá trình suy luận kiểu generic. Ví dụ:

~~~java
import java.util.function.Function;

static <T, R> R map(T value, Function<? super T, ? extends R> mapper) {
    return mapper.apply(value);
}

// T được suy ra là String; R được suy ra là Integer.
Integer result = map("123", Integer::parseInt);
~~~

Đối số `Integer::parseInt` được kiểm tra theo tham số `mapper`, còn kiểu nhận của `result` cung cấp thêm ngữ cảnh cho kiểu trả về `R`. Trình biên dịch suy luận các kiểu sao cho toàn bộ lời gọi tương thích. Trong các pipeline Stream, cơ chế tương tự xuất hiện ở những lời gọi như `names.stream().map(String::trim)`: phương thức `map` nhận một hàm, nên kiểu phần tử của stream giúp xác định kiểu đích.

Nếu có thể diễn đạt cùng một ý bằng lambda, hãy so sánh chữ ký để hiểu method reference:

~~~java
Function<String, Integer> a = Integer::parseInt;
Function<String, Integer> b = text -> Integer.parseInt(text);
~~~

Hai biểu thức trên tương đương về mục đích trong ví dụ này. Lambda thể hiện rõ tham số và phần thân; method reference ngắn gọn hơn khi phần thân chỉ gọi một phương thức với các tham số tương ứng.

## 6. Lỗi thường gặp và cách xử lý

- **Thiếu kiểu đích:** `var f = String::trim;` không biên dịch. Khai báo `Function<String, String> f = String::trim;`.
- **Nhầm static và instance:** `Integer::parseInt` gọi phương thức static; `String::trim` là dạng unbound của phương thức instance và cần một đối số chuỗi làm receiver.
- **Sai số tham số:** `String::concat` cần receiver và đối số nối thêm, vì vậy phù hợp với kiểu hàm hai tham số như `BiFunction<String, String, String>`.
- **Overload mơ hồ:** nhiều phương thức cùng tên có thể cùng phù hợp với kiểu đích. Cung cấp kiểu functional interface cụ thể hoặc ép kiểu method reference khi cần.
- **Kiểu trả về không tương thích:** kiểm tra kiểu trả về của phương thức so với kiểu trả về của SAM; chỉ các chuyển đổi được Java cho phép mới được áp dụng.
- **Receiver có thể null:** với dạng bound như `object::method`, biểu thức receiver được đánh giá khi tạo method reference. Nếu receiver là `null`, việc tạo tham chiếu gây `NullPointerException`; hãy kiểm tra đối tượng trước khi tạo.
- **Checked exception:** phương thức được tham chiếu không thể làm cho checked exception biến mất. Kiểu SAM phải cho phép exception đó, hoặc mã gọi phải xử lý theo quy tắc Java.

## 7. Cách tự kiểm tra khi đọc một method reference

Khi gặp biểu thức `TypeOrObject::method`, hãy xác định lần lượt:

1. Functional interface nào cung cấp kiểu đích?
2. SAM nhận bao nhiêu tham số, mỗi tham số có kiểu gì và trả về kiểu gì?
3. Đây là phương thức static, phương thức instance có receiver cố định, phương thức instance dùng tham số đầu làm receiver, hay constructor?
4. Có overload nào tương thích với chữ ký SAM? Nếu có nhiều overload, quy tắc chọn overload có xác định được duy nhất một phương thức không?
5. Kiểu trả về, boxing/unboxing và exception có tương thích không?

Nếu trả lời được những câu hỏi này, có thể dự đoán cách trình biên dịch diễn giải method reference trước khi chạy chương trình.