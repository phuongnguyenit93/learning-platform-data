# Giới hạn với sealed interface và phương thức hàm có kiểu tổng quát

Bài này tập trung vào hai cơ chế thường bị nhầm khi thiết kế API Java: `sealed interface` để giới hạn hệ phân cấp kiểu, và phương thức trừu tượng có tham số kiểu tổng quát trong một interface dạng hàm. Ví dụ dùng Java 17 trở lên; phần pattern matching cho `switch` cần Java 21 trở lên.

## 1. Phân biệt hai mục tiêu

- **Sealed interface** xác định những kiểu nào được phép triển khai trực tiếp interface. Nó giúp mô hình hóa một tập biến thể có giới hạn, chẳng hạn kết quả thành công hoặc thất bại.
- **Functional interface** cung cấp một hợp đồng hàm để có thể truyền lambda hoặc method reference. Hợp đồng này cần có một phương thức trừu tượng tương thích với cách biểu diễn hàm của Java.
- **Generic interface** có thể nhận tham số kiểu ở cấp interface, ví dụ `Converter<S, T>`. Sau khi chọn một kiểu cụ thể như `Converter<String, Integer>`, phương thức hàm có kiểu đầu vào và đầu ra rõ ràng.
- **Generic method** khai báo tham số kiểu ngay trên phương thức, ví dụ `<T> T identity(T value)`. Đây là trường hợp có giới hạn khi dùng lambda, vì lambda không thể khai báo tham số kiểu của phương thức đích.

Các cơ chế này giải quyết vấn đề khác nhau. Một interface có thể là generic và dùng lambda rất tự nhiên; một interface sealed có thể generic; nhưng không nên dùng sealed interface làm kiểu đích cho lambda, và một phương thức trừu tượng tự khai báo tham số kiểu không thể được triển khai bằng lambda thông thường.

## 2. Quy tắc của sealed interface

Một sealed interface dùng từ khóa `sealed` và thường liệt kê các kiểu được phép triển khai trực tiếp bằng `permits`.

~~~java
sealed interface Outcome<T> permits Success, Failure {
}

record Success<T>(T value) implements Outcome<T> {
}

record Failure<T>(String message) implements Outcome<T> {
}
~~~

Trong ví dụ, `Outcome<T>` chỉ cho phép `Success` và `Failure` triển khai trực tiếp. Các record tự động là `final`, nên chúng đáp ứng quy tắc dành cho kiểu con trực tiếp của sealed type. Danh sách `permits` dùng tên kiểu, không viết tham số kiểu như `Success<T>`.

Các quy tắc quan trọng:

1. Mỗi kiểu con trực tiếp được liệt kê trong `permits` phải thật sự kế thừa hoặc triển khai sealed type đó.
2. Nếu sealed type nằm trong named module, các kiểu con trực tiếp phải thuộc cùng module. Nếu không nằm trong named module, chúng phải thuộc cùng package.
3. Mỗi kiểu con trực tiếp phải khai báo `final`, `sealed` hoặc `non-sealed`. Record vốn đã final nên không cần ghi thêm `final`.
4. `final` đóng nhánh kế thừa tại kiểu đó. `sealed` tiếp tục giới hạn các kiểu con ở tầng sau. `non-sealed` mở lại nhánh đó để có thể phát sinh các kiểu con khác.
5. Có thể bỏ `permits` nếu compiler suy ra được danh sách kiểu con từ các khai báo trong cùng compilation unit. Khi các kiểu nằm ở file khác, hãy khai báo `permits` tường minh.
6. Sealed type giới hạn quan hệ kế thừa trực tiếp; nó không tự kiểm tra tính hợp lệ của dữ liệu hay bảo đảm mọi nhánh đều xử lý đúng nghiệp vụ.

Một sealed interface có thể có tham số kiểu. Việc sealed hay không sealed kiểm soát hệ phân cấp lớp/kiểu; generic kiểm soát quan hệ kiểu giữa giá trị và API. Hai cơ chế này bổ sung cho nhau.

## 3. Generic functional interface có thể dùng lambda

Cách thường phù hợp nhất là đặt tham số kiểu ở cấp interface, trong khi phương thức trừu tượng không tự khai báo tham số kiểu riêng.

~~~java
@FunctionalInterface
interface Converter<S, T> {
    T convert(S source);
}

class ConverterDemo {
    public static void main(String[] args) {
        Converter<String, Integer> length = String::length;
        System.out.println(length.convert("Java"));
    }
}
~~~

Lệnh biên dịch và chạy:

~~~text
javac ConverterDemo.java
java ConverterDemo
~~~

Kết quả:

~~~text
4
~~~

Với `Converter<String, Integer>`, compiler xác định phương thức cần tương thích với đầu vào `String` và đầu ra `Integer`. `String::length` trả về `int`, được boxing thành `Integer`, nên method reference này tương thích.

Lambda cũng dùng được:

~~~java
Converter<String, Integer> length = text -> text.length();
~~~

Nếu compiler không suy ra được kiểu tham số do overload hoặc ngữ cảnh phức tạp, có thể khai báo kiểu tường minh, ví dụ `(String text) -> text.length()`.

## 4. Giới hạn của phương thức trừu tượng tự khai báo kiểu tổng quát

Xét một interface có phương thức trừu tượng khai báo `<T>` ngay trên phương thức:

~~~java
interface UniversalIdentity {
    <T> T identity(T value);
}

final class Identity implements UniversalIdentity {
    @Override
    public <T> T identity(T value) {
        return value;
    }
}
~~~

Lớp `Identity` hợp lệ vì phương thức của nó khai báo lại tham số kiểu `<T>` và hoạt động với mọi kiểu T. Tuy nhiên, không thể thay việc triển khai này bằng lambda thông thường:

~~~java
UniversalIdentity identity = value -> value; // Không biên dịch
~~~

Compiler từ chối lambda vì phương thức đích có descriptor tổng quát: bản thân phương thức khai báo tham số kiểu. Cú pháp lambda không cung cấp chỗ để khai báo tham số kiểu của phương thức đích. Một lambda không thể giả định rằng kiểu của `value` chỉ là một kiểu cố định; hợp đồng yêu cầu phương thức hoạt động với mọi T.

Đây là khác biệt quan trọng:

- `Converter<String, Integer>` đã chốt các kiểu cho một lần dùng cụ thể, nên lambda có thể khớp với `String -> Integer`.
- `<T> T identity(T value)` yêu cầu một phương thức có tham số kiểu riêng và phải giữ đúng quan hệ kiểu cho mọi T. Hãy triển khai bằng lớp cụ thể hoặc lớp ẩn danh thay vì lambda.
- Việc interface có đúng một phương thức trừu tượng không tự động có nghĩa mọi biểu thức lambda đều có thể triển khai phương thức đó; descriptor của phương thức cũng phải tương thích với lambda.

Nếu mục tiêu chỉ là tạo một hàm chuyển đổi có kiểu đầu vào và đầu ra được chọn khi khai báo biến, hãy ưu tiên tham số kiểu ở cấp interface. Chỉ dùng generic method khi mỗi lần gọi cần tự chọn một kiểu T độc lập.

## 5. Vì sao nên tách sealed model khỏi callback lambda

Sealed interface thích hợp để biểu diễn các biến thể nghiệp vụ đã biết. Lambda lại cần một kiểu đích có thể được triển khai bằng lớp do compiler/runtime tạo ra; lớp triển khai đó không thể được liệt kê trước trong danh sách `permits`. Vì vậy, không thiết kế sealed interface làm đích cho lambda hoặc method reference.

Mẫu thiết kế phù hợp là để callback là một functional interface thông thường, còn kết quả do callback trả về có thể là sealed interface:

~~~java
sealed interface Outcome<T> permits Success, Failure {
}

record Success<T>(T value) implements Outcome<T> {
}

record Failure<T>(String message) implements Outcome<T> {
}

@FunctionalInterface
interface Parser<T> {
    Outcome<T> parse(String input);
}
~~~

Ở đây `Parser<T>` có thể nhận lambda vì chính `Parser` không bị sealed. Kết quả của hàm vẫn được giới hạn trong hai dạng `Success<T>` và `Failure<T>`. Thiết kế này tách hai trách nhiệm rõ ràng: callback có thể thay thế linh hoạt, còn các biến thể kết quả được kiểm soát.

## 6. Ví dụ Java hoàn chỉnh

Lưu đoạn sau thành `OutcomeDemo.java`. Tất cả các kiểu đều nằm trong cùng compilation unit để danh sách `permits` rõ ràng.

~~~java
sealed interface Outcome<T> permits Success, Failure {
}

record Success<T>(T value) implements Outcome<T> {
}

record Failure<T>(String message) implements Outcome<T> {
}

@FunctionalInterface
interface Parser<T> {
    Outcome<T> parse(String input);
}

interface UniversalIdentity {
    <T> T identity(T value);
}

final class Identity implements UniversalIdentity {
    @Override
    public <T> T identity(T value) {
        return value;
    }
}

public class OutcomeDemo {
    public static void main(String[] args) {
        Parser<Integer> parser = text -> {
            try {
                return new Success<>(Integer.parseInt(text));
            } catch (NumberFormatException ex) {
                return new Failure<>("Not an integer: " + text);
            }
        };

        System.out.println(parser.parse("42"));
        System.out.println(parser.parse("x"));

        UniversalIdentity identity = new Identity();
        String word = identity.identity("Java");
        Integer number = identity.identity(17);
        System.out.println(word + " " + number);
    }
}
~~~

Biên dịch và chạy bằng Java 17 trở lên:

~~~text
javac OutcomeDemo.java
java OutcomeDemo
~~~

Kết quả stdout chính xác:

~~~text
Success[value=42]
Failure[message=Not an integer: x]
Java 17
~~~

Ví dụ minh họa đồng thời ba điều: `Outcome<T>` giới hạn các dạng kết quả; `Parser<Integer>` là generic functional interface mà lambda có thể triển khai; `UniversalIdentity` giữ generic method và cần một lớp triển khai có khai báo `<T>` tường minh.

## 7. Generic, type erasure và pattern matching

Tham số kiểu generic chủ yếu được kiểm tra ở thời điểm biên dịch. Sau type erasure, không thể dựa vào runtime để phân biệt mọi kiểu tham số generic. Ví dụ, kiểm tra `instanceof Success<String>` thường không hợp lệ vì `Success<String>` không phải kiểu có thể kiểm tra đầy đủ tại runtime. Có thể kiểm tra dạng tổng quát bằng `instanceof Success<?> success`, rồi xử lý giá trị theo kiểu mà API cho phép.

Tính invariant của generic cũng cần được nhớ: `Outcome<Integer>` không phải là `Outcome<Number>`, dù `Integer` là subtype của `Number`. Khi API cần nhận nhiều kiểu con, hãy cân nhắc wildcard như `Outcome<? extends Number>` theo đúng hướng dữ liệu được đọc hoặc ghi.

Từ Java 21, pattern matching cho `switch` có thể tận dụng sealed hierarchy để compiler kiểm tra tính bao phủ của các nhánh. Khả năng kiểm tra exhaustiveness phụ thuộc vào kiểu selector, các kiểu con được phép và các pattern; khi hierarchy có generic hoặc nhánh `non-sealed`, cần kiểm tra kỹ kiểu pattern thay vì giả định compiler luôn suy ra được mọi trường hợp. Sealed hierarchy cũng không thay thế xử lý lỗi runtime hoặc xác thực dữ liệu đầu vào.

## 8. Lỗi thường gặp và cách chọn thiết kế

| Tình huống | Nguyên nhân | Hướng xử lý |
|---|---|---|
| Thêm một kiểu triển khai mới nhưng quên cập nhật `permits` | Kiểu mới chưa thuộc tập subtype được cho phép | Cập nhật danh sách và kiểm tra modifier của subtype |
| Subtype trực tiếp không có `final`, `sealed` hoặc `non-sealed` | Vi phạm quy tắc sealed hierarchy | Chọn rõ nhánh đóng hay nhánh được mở rộng |
| Gán lambda cho sealed interface | Sealed type không phù hợp làm target type của lambda | Tạo functional interface không sealed cho callback |
| Viết lambda cho phương thức trừu tượng `<T> T apply(T value)` | Phương thức đích tự khai báo type parameter | Dùng lớp triển khai hoặc thiết kế lại tham số kiểu ở cấp interface |
| Dùng `instanceof` với `Success<String>` | Kiểu tham số generic không reifiable ở runtime | Kiểm tra `Success<?>` và xử lý theo hợp đồng kiểu an toàn |
| Coi `Outcome<Integer>` là subtype của `Outcome<Number>` | Generic Java invariant | Dùng wildcard phù hợp khi API cần chấp nhận họ kiểu |
| Dùng `non-sealed` nhưng vẫn giả định toàn bộ cây con đóng | `non-sealed` cho phép mở rộng nhánh | Xem nhánh đó như một điểm mở rộng và thiết kế xử lý tương ứng |

Quy tắc chọn nhanh:

- Chọn **sealed interface** khi miền dữ liệu có tập biến thể trực tiếp được kiểm soát.
- Chọn **generic functional interface** khi muốn truyền lambda và kiểu đầu vào/đầu ra được xác định bởi tham số kiểu của interface.
- Chọn **generic method** khi mỗi lần gọi phải làm việc với kiểu T do chính lời gọi suy ra; nếu phương thức đó là phương thức trừu tượng, đừng mặc định rằng có thể triển khai nó bằng lambda.
- Kết hợp hai cơ chế bằng cách để callback không sealed trả về một sealed result khi cần vừa linh hoạt trong cách thực thi, vừa giới hạn các dạng kết quả.
