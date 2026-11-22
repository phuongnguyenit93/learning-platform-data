# Default, static và private method trong functional interface

Trong Java, một **functional interface** (giao diện hàm) có đúng một phương thức trừu tượng theo quy tắc của ngôn ngữ. Phương thức trừu tượng này là hợp đồng mà lớp triển khai phải cung cấp; nó cũng là phương thức được dùng khi gán lambda hoặc method reference cho kiểu giao diện.

Interface vẫn có thể khai báo thêm nhiều phương thức `default`, `static` và `private`. Các phương thức này có phần thân nên không tạo thêm yêu cầu phương thức trừu tượng. Vì vậy, một interface có nhiều phương thức được khai báo vẫn có thể là functional interface.

## 1. Phương thức trừu tượng là phần hợp đồng bắt buộc

Phương thức khai báo trong interface mà không có phần thân thường là phương thức trừu tượng. Phương thức đó phải được lớp triển khai thực hiện, trừ khi lớp triển khai tiếp tục là `abstract`.

```java
String process(String text);
```

Với phương thức trên, một lớp cụ thể triển khai interface phải cung cấp cách xử lý `process`. Nếu interface có thêm một phương thức trừu tượng độc lập khác, nó thường không còn đáp ứng điều kiện functional interface.

`@FunctionalInterface` giúp trình biên dịch kiểm tra điều kiện này. Annotation không bắt buộc để viết lambda, nhưng rất hữu ích vì trình biên dịch sẽ báo lỗi nếu các thay đổi sau này làm interface không còn là functional interface.

## 2. `default` method cung cấp hành vi mặc định

Phương thức `default` là phương thức instance có phần thân trong interface. Lớp triển khai được thừa hưởng hành vi mặc định và có thể ghi đè nó khi cần.

```java
default String processOrEmpty(String text) {
    return process(text == null ? "" : text);
}
```

Ở ví dụ này, `processOrEmpty` gọi phương thức trừu tượng `process` và xử lý trường hợp đầu vào `null`. Lớp triển khai chỉ cần định nghĩa `process`; không bắt buộc ghi đè `processOrEmpty`. Vì vậy, phương thức `default` không làm tăng số phương thức trừu tượng.

`default` method phù hợp khi muốn bổ sung hành vi dùng chung cho các lớp triển khai mà vẫn giữ khả năng tương thích với những lớp cũ. Nếu hai interface cung cấp các `default` method xung đột cùng chữ ký, lớp triển khai có thể phải tự ghi đè để giải quyết xung đột.

## 3. `static` method thuộc về interface

Phương thức `static` có phần thân và được gọi bằng tên interface. Nó không phải hành vi instance mà lớp triển khai phải cung cấp, cũng không được thừa hưởng như một phương thức instance thông thường.

```java
TextProcessor.trimmed();
```

Có thể đặt các hàm tạo, tiện ích hoặc factory method trong interface. Chẳng hạn, một static method có thể trả về một lambda mang kiểu interface. Bản thân static method không phải phương thức trừu tượng và không làm mất tính chất functional của interface.

## 4. `private` method là hàm trợ giúp nội bộ

Interface hỗ trợ `private` method từ Java 9. Phương thức private phải có phần thân và dùng để chia sẻ đoạn xử lý giữa các phương thức khác trong cùng interface.

- `private` instance method có thể được gọi từ phương thức instance có quyền truy cập trong interface, chẳng hạn một `default` method.
- `private static` method có thể được gọi từ các phương thức static khác trong interface.
- Lớp triển khai và interface con không thừa hưởng hay gọi trực tiếp các phương thức private này.

Vì là phương thức có phần thân và chỉ phục vụ triển khai nội bộ, `private` method không tạo thêm hợp đồng trừu tượng cho lớp triển khai.

## 5. Ví dụ Java hoàn chỉnh

Ví dụ sau có một phương thức trừu tượng `process` cùng các phương thức `default`, `static`, `private` và `private static`. Interface vẫn được đánh dấu `@FunctionalInterface` và có thể nhận lambda.

```java
import java.util.Locale;

public class FunctionalInterfaceMethodsDemo {

    @FunctionalInterface
    interface TextProcessor {
        String process(String text);

        default String processOrEmpty(String text) {
            return process(text == null ? "" : text);
        }

        default String processWrapped(String text) {
            return "[" + trimForDisplay(process(text)) + "]";
        }

        static TextProcessor trimmed() {
            return text -> normalize(text);
        }

        static TextProcessor normalized() {
            return text -> normalize(text).toLowerCase(Locale.ROOT);
        }

        private String trimForDisplay(String text) {
            return text == null ? "" : text.trim();
        }

        private static String normalize(String text) {
            return text == null ? "" : text.trim();
        }
    }

    public static void main(String[] args) {
        TextProcessor upper = text -> text.toUpperCase(Locale.ROOT);
        System.out.println(upper.process("java"));
        System.out.println(upper.processOrEmpty(null));
        System.out.println(TextProcessor.trimmed().process("  Java  "));
        System.out.println(TextProcessor.normalized().process("  JaVa  "));
        System.out.println(upper.processWrapped(" java "));
    }
}
```

Lưu đoạn mã vào tệp `FunctionalInterfaceMethodsDemo.java`, sau đó chạy bằng JDK 17 trở lên:

```bash
javac FunctionalInterfaceMethodsDemo.java
java FunctionalInterfaceMethodsDemo
```

Kết quả stdout:

```text
JAVA

Java
java
[JAVA]
```

Dòng thứ hai là dòng trống: `processOrEmpty(null)` chuyển `null` thành chuỗi rỗng rồi truyền chuỗi đó cho lambda `upper`.

Trong ví dụ:

- `process` là phương thức trừu tượng duy nhất mà lambda phải thực hiện.
- `processOrEmpty` và `processWrapped` là các phương thức instance `default` được thừa hưởng. `processWrapped` dùng `trimForDisplay`, một private instance helper.
- `trimmed` và `normalized` là static factory method, gọi bằng `TextProcessor`. Cả hai dùng private static helper `normalize`.
- `trimForDisplay` và `normalize` có phần thân và chỉ hỗ trợ triển khai bên trong interface.

## 6. So sánh nhanh

| Loại phương thức | Có phần thân | Lớp triển khai phải tự cung cấp | Được tính là phương thức trừu tượng |
| --- | --- | --- | --- |
| Phương thức trừu tượng | Không | Có, nếu lớp là concrete | Có |
| `default` | Có | Không; có thể ghi đè | Không |
| `static` | Có | Không | Không |
| `private` instance | Có | Không | Không |
| `private static` | Có | Không | Không |

Bảng trên nói về các loại phương thức trong interface. Quy tắc xác định functional interface còn xét cả phương thức được kế thừa và các chữ ký tương đương nhau; không nên chỉ đếm số dòng khai báo trong một interface.

## 7. Những điểm dễ nhầm

1. **Functional interface không có nghĩa là chỉ được khai báo một phương thức tổng cộng.** Nó có thể có nhiều phương thức `default`, `static` và `private`, miễn vẫn đáp ứng quy tắc về phương thức trừu tượng.
2. **Thêm một phương thức trừu tượng độc lập có thể làm hỏng hợp đồng lambda.** Khi interface có `@FunctionalInterface`, trình biên dịch sẽ báo lỗi nếu thay đổi đó khiến interface không còn phù hợp.
3. **Gọi static method qua tên interface.** Ví dụ là `TextProcessor.trimmed()`. Phương thức này không trở thành phương thức instance của đối tượng `TextProcessor`.
4. **Private interface method yêu cầu Java 9 trở lên.** Nếu cần tương thích với Java 8, không thể dùng private method trong interface.
5. **`default` method là hành vi được cung cấp sẵn.** Lớp triển khai có thể dùng trực tiếp hoặc ghi đè, nên nó không tạo thêm yêu cầu triển khai trừu tượng.

Các phương thức public của `Object` như `equals(Object)` cũng được xử lý theo quy tắc riêng khi xác định functional interface; đừng kết luận rằng mọi chữ ký trừu tượng nhìn thấy đều tạo thêm một yêu cầu lambda độc lập.

## Kết luận

Điều quyết định functional interface là hợp đồng phương thức trừu tượng, không phải tổng số phương thức được khai báo. `default` cung cấp hành vi instance có sẵn, `static` cung cấp hành vi thuộc về interface, còn `private` và `private static` là các hàm trợ giúp nội bộ. Những phương thức này có phần thân nên không tạo thêm yêu cầu phương thức trừu tượng cho lớp triển khai.