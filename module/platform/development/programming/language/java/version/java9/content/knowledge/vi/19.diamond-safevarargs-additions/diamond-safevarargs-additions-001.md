# Diamond operator với lớp ẩn danh (Anonymous Classes)

Từ Java 9, có thể dùng **diamond operator** (**<>**) khi tạo một lớp ẩn danh từ lớp generic hoặc khi triển khai một generic interface. Trình biên dịch suy luận type argument từ tham số constructor và ngữ cảnh sử dụng, giúp mã nguồn ngắn gọn mà vẫn giữ kiểm tra kiểu an toàn.

Điểm cần nhớ là: diamond operator với anonymous class là một khả năng của ngôn ngữ Java từ **Java 9**. Diamond operator trong các biểu thức tạo đối tượng generic thông thường đã có từ Java 7; Java 9 mở rộng cú pháp đó cho trường hợp có phần thân lớp ẩn danh.

## 1. Hai khái niệm nền tảng

### Diamond operator

Diamond operator là cặp dấu ngoặc nhọn rỗng <> đặt sau tên một kiểu generic trong biểu thức new. Nó yêu cầu trình biên dịch suy luận các tham số kiểu thay vì phải viết lại chúng:

~~~java
List<String> names = new ArrayList<>();
~~~

Ở đây, ArrayList<> được suy luận thành ArrayList<String> dựa trên kiểu đích List<String>. Dấu <> không phải wildcard (?) và cũng không biến đối tượng thành raw type. Kiểm tra generic vẫn được thực hiện tại thời điểm biên dịch.

### Lớp ẩn danh

Lớp ẩn danh là lớp được khai báo ngay tại vị trí tạo đối tượng, không có tên riêng. Lớp này thường được dùng để kế thừa một lớp hoặc triển khai một interface và định nghĩa hành vi ngay tại chỗ:

~~~java
Runnable task = new Runnable() {
    @Override
    public void run() {
        System.out.println("Running");
    }
};
~~~

Khi lớp cha hoặc interface là generic, phần kiểu cụ thể thường phải được chỉ rõ trong biểu thức new. Từ Java 9, có thể dùng diamond operator tại vị trí này.

## 2. Cú pháp diamond với lớp ẩn danh từ Java 9

Cú pháp tổng quát khi kế thừa một generic class:

~~~java
GenericBase<String> value = new GenericBase<>("initial") {
    @Override
    public String transform(String input) {
        return input;
    }
};
~~~

Với generic interface:

~~~java
Processor<String> processor = new Processor<>() {
    @Override
    public String process(String input) {
        return input.trim();
    }
};
~~~

Trong cả hai trường hợp, <> yêu cầu compiler suy luận tham số kiểu. Phần thân { ... } là định nghĩa của lớp ẩn danh được tạo tại chỗ.

Trước Java 9, cú pháp diamond không được phép đi cùng anonymous class body. Khi cần biên dịch với source level thấp hơn Java 9, phải viết rõ type argument, ví dụ new Processor<String>() { ... }. Cú pháp diamond với anonymous class cần source level Java 9 trở lên.

## 3. Trình biên dịch suy luận type argument như thế nào?

Việc suy luận kiểu thường dựa trên hai nguồn thông tin chính:

1. **Tham số truyền cho constructor:** kiểu của các đối số giúp xác định tham số generic. Ví dụ, nếu constructor nhận T và truyền vào một String, compiler có thể suy luận T là String.
2. **Kiểu đích (target type):** kiểu của biến nhận kết quả, kiểu trả về của phương thức hoặc ngữ cảnh gán có thể cung cấp ràng buộc cho tham số generic. Điều này đặc biệt hữu ích khi constructor không có đối số để suy luận.

Ví dụ với constructor nhận một giá trị:

~~~java
Transformer<String> transformer = new Transformer<>("hello") {
    @Override
    public String transform(String input) {
        return input.toUpperCase();
    }
};
~~~

"hello" là một String, còn kiểu đích là Transformer<String>. Compiler suy luận tham số generic là String; do đó phương thức cần triển khai nhận và trả về String.

Ví dụ với interface không có constructor argument:

~~~java
Processor<String> processor = new Processor<>() {
    @Override
    public String process(String input) {
        return "[" + input + "]";
    }
};
~~~

Ở đây, kiểu đích Processor<String> cung cấp thông tin để suy luận T là String. Vì vậy, phương thức process có chữ ký tương ứng với String.

## 4. Ví dụ hoàn chỉnh có thể biên dịch và chạy

Lưu mã sau trong tệp **DiamondAnonymousDemo.java**. Chương trình minh họa cả hai trường hợp: suy luận kiểu từ constructor và suy luận từ kiểu đích của một generic interface.

~~~java
import java.util.Locale;

abstract class Transformer<T> {
    private final T initial;

    Transformer(T initial) {
        this.initial = initial;
    }

    public T initial() {
        return initial;
    }

    public abstract T transform(T input);
}

interface Processor<T> {
    T process(T input);
}

public class DiamondAnonymousDemo {
    public static void main(String[] args) {
        Transformer<String> transformer = new Transformer<>("hello") {
            @Override
            public String transform(String input) {
                return input.toUpperCase(Locale.ROOT);
            }
        };

        Processor<String> processor = new Processor<>() {
            @Override
            public String process(String input) {
                return "[" + input + "]";
            }
        };

        System.out.println(transformer.initial());
        System.out.println(transformer.transform("java 9"));
        System.out.println(processor.process("diamond"));
    }
}
~~~

Biên dịch với Java 9 trở lên:

~~~bash
javac --release 9 DiamondAnonymousDemo.java
java DiamondAnonymousDemo
~~~

Kết quả stdout:

~~~text
hello
JAVA 9
[diamond]
~~~

Giải thích:

- new Transformer<>("hello") dùng diamond với một generic abstract class. Compiler suy luận T là String từ đối số constructor và kiểu đích Transformer<String>.
- Lớp ẩn danh triển khai phương thức transform(String input) theo hợp đồng của Transformer<String>.
- new Processor<>() dùng diamond với generic interface. Kiểu đích Processor<String> giúp compiler suy luận T là String, dù interface không có constructor argument.
- @Override giúp compiler kiểm tra phương thức trong lớp ẩn danh có thực sự ghi đè hoặc triển khai đúng phương thức của kiểu cha hay không.
- Locale.ROOT làm cho phép chuyển chữ hoa không phụ thuộc locale mặc định của máy.

## 5. Điều kiện về kiểu có thể biểu diễn (denotable type)

Java 9 cho phép diamond với anonymous class khi các type argument được suy luận là **denotable**. Có thể hiểu denotable type là kiểu có thể được biểu diễn bằng cú pháp kiểu trong mã nguồn Java, chẳng hạn String, Integer hoặc List<String>.

Trong một số biểu thức generic phức tạp, quá trình suy luận có thể tạo ra kiểu nội bộ mà mã nguồn không thể viết trực tiếp, ví dụ một capture type phát sinh từ wildcard capture. Nếu type argument suy luận không denotable, compiler không cho phép dùng diamond với anonymous class và sẽ báo lỗi biên dịch.

Khi gặp trường hợp này:

- Kiểm tra kiểu đích và kiểu của các đối số constructor để hiểu compiler đang suy luận kiểu gì.
- Nếu có kiểu cụ thể, biểu diễn được trong mã nguồn và phù hợp với API, có thể khai báo type argument tường minh thay cho <>.
- Nếu kiểu đến từ wildcard hoặc capture phức tạp, cân nhắc thiết kế lại kiểu trung gian hoặc chữ ký generic để dùng một kiểu có tên, biểu diễn được.

Không nên giả định rằng mọi biểu thức generic đều có thể dùng <> với anonymous class. Điều kiện denotable là giới hạn quan trọng của tính năng này.

## 6. So sánh cách viết và các trường hợp cần lưu ý

| Cách viết | Ý nghĩa |
|---|---|
| new ArrayList<String>() | Ghi rõ type argument là String |
| new ArrayList<>() | Compiler suy luận type argument từ ngữ cảnh |
| new ArrayList() | Dùng raw type; làm mất kiểm tra generic và có thể phát sinh unchecked warning |
| new Processor<String>() { ... } | Anonymous class với type argument ghi rõ |
| new Processor<>() { ... } | Anonymous class với type argument được suy luận; hỗ trợ từ Java 9 |

Một số điểm cần lưu ý khi áp dụng:

- Diamond chỉ dùng với kiểu generic. Nếu lớp hoặc interface không khai báo tham số kiểu, không có type argument để suy luận.
- Phần thân anonymous class phải triển khai các phương thức abstract cần thiết và tuân thủ chữ ký sau khi type argument được suy luận.
- Kiểu đích cần đủ thông tin khi constructor không cung cấp được thông tin suy luận.
- Type argument suy luận phải denotable khi diamond được dùng với anonymous class.
- Diamond chỉ thay đổi cách viết ở thời điểm biên dịch; nó không loại bỏ cơ chế type erasure của Java generics.
- Nếu dự án đặt source level là Java 8 hoặc thấp hơn, <> với anonymous class sẽ không biên dịch. Có thể dùng type argument tường minh như new Processor<String>() { ... } để giữ khả năng tương thích với source level đó.

## 7. Lỗi thường gặp

| Lỗi | Nguyên nhân | Cách xử lý |
|---|---|---|
| Dùng <> với anonymous class trong source level dưới Java 9 | Cú pháp chưa được hỗ trợ ở source level đó | Nâng source level lên Java 9+ hoặc ghi rõ type argument |
| Nghĩ <> tương đương ? | Nhầm diamond với wildcard | <> yêu cầu compiler suy luận kiểu; ? biểu diễn wildcard trong khai báo kiểu |
| Dùng raw type thay cho diamond | Bỏ qua kiểm tra generic | Dùng new GenericType<>() hoặc type argument tường minh |
| Kiểu suy luận không denotable | Compiler không thể biểu diễn type argument trong kiểu của anonymous class | Xem lại kiểu đích, wildcard và chữ ký generic; dùng kiểu tường minh phù hợp khi có thể |
| Triển khai phương thức với kiểu tham số sai | Chữ ký không khớp với generic type sau khi suy luận | Kiểm tra type argument và dùng @Override |

## 8. Ghi nhớ

- Diamond operator <> giúp compiler tự suy luận type argument của generic type.
- Java 9 mở rộng diamond operator để dùng được với anonymous class.
- Compiler có thể dựa vào đối số constructor và target type để suy luận kiểu.
- Với anonymous class, các type argument được suy luận phải là denotable type.
- <> không phải wildcard và không phải raw type; kiểm tra generic vẫn diễn ra ở compile time.
- Nếu cần hỗ trợ source level Java 8 trở xuống, hãy ghi rõ type argument thay vì dùng diamond với anonymous class.
