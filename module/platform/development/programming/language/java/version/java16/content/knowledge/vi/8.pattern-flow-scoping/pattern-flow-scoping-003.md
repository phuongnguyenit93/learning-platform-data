# Kết hợp instanceof với && để kiểm tra tiếp dữ liệu đã ép kiểu

Java 16 hoàn thiện pattern matching cho `instanceof`. Cú pháp này cho phép kiểm tra kiểu và tạo một biến có kiểu tương ứng ngay trong cùng biểu thức. Khi kết hợp với toán tử `&&`, chương trình có thể kiểm tra tiếp dữ liệu qua biến pattern mà không cần viết thêm phép ép kiểu tường minh.

Trong module Java 16, pattern matching cho `instanceof` là cải tiến ngôn ngữ vẫn hữu ích trong Java hiện đại, bên cạnh `record` và các API Stream. Bài này tập trung vào cách dùng `&&` để kiểm tra tuần tự một giá trị đã khớp kiểu, bao gồm xử lý `null`, thứ tự điều kiện và các ví dụ thực tế. Các cú pháp được trình bày đã được chuẩn hóa, không cần preview feature.

## 1. Cú pháp kết hợp `instanceof` và `&&`

Mẫu cơ bản:

```java
if (value instanceof String text && text.length() >= 5) {
    System.out.println(text.toUpperCase());
}
```

Biểu thức có hai phần:

- `value instanceof String text` kiểm tra giá trị có phải là `String` hay không. Khi khớp, biến pattern `text` được tạo với kiểu tĩnh `String`.
- `text.length() >= 5` là điều kiện tiếp theo. Nó chỉ được đánh giá sau khi phép kiểm tra kiểu ở vế trái đúng.

Vì vậy, bên trong vế phải và thân `if`, compiler biết `text` là một `String`. Không cần viết `(String) value` để gọi `length()` hoặc `toUpperCase()`.

Pattern matching không thay đổi đối tượng ban đầu và không tạo một bản sao chuỗi. Biến pattern là một biến cục bộ tham chiếu đến giá trị đã được kiểm tra, với kiểu mà compiler có thể xác nhận.

## 2. Vì sao `&&` cho phép kiểm tra tiếp an toàn?

`&&` là toán tử AND có đánh giá ngắn mạch (*short-circuit*). Java đánh giá biểu thức từ trái sang phải:

1. Đánh giá vế trái.
2. Nếu vế trái sai, kết quả toàn biểu thức đã là `false`; Java bỏ qua vế phải.
3. Nếu vế trái đúng, Java đánh giá vế phải.
4. Chỉ khi mọi vế đều đúng thì thân `if` mới được thực hiện.

Với pattern `value instanceof String text`, trình tự này tạo ra bảo đảm cần thiết: vế phải chỉ chạy sau khi pattern khớp và `text` đã được gán.

```java
static void printText(Object value) {
    if (value instanceof String text && text.contains("Java")) {
        System.out.println("Có từ Java: " + text);
    }
}
```

Nếu `value` là một số hoặc một đối tượng không phải `String`, vế phải không được gọi. Nếu `value` là `String`, Java mới gọi `contains` trên biến `text`.

## 3. Nối nhiều điều kiện bằng `&&`

Có thể nối nhiều điều kiện để xác nhận kiểu trước, sau đó kiểm tra từng đặc điểm của dữ liệu:

```java
static void validateCommand(Object value) {
    if (value instanceof String command
            && !command.isBlank()
            && command.startsWith("deploy:")
            && command.length() <= 80) {
        System.out.println("Lệnh hợp lệ: " + command.strip());
    } else {
        System.out.println("Lệnh không hợp lệ");
    }
}
```

Các điều kiện được kiểm tra theo thứ tự:

1. Giá trị phải là `String` để tạo biến `command`.
2. Chuỗi không được rỗng hoặc chỉ chứa khoảng trắng.
3. Chuỗi phải bắt đầu bằng tiền tố `deploy:`.
4. Độ dài chuỗi không vượt quá 80 ký tự.

Mỗi vế tiếp theo chỉ được đánh giá khi tất cả vế trước đều đúng. Do đó, `command` có thể được dùng xuyên suốt các điều kiện sau phép kiểm tra kiểu và trong thân `if`.

Thứ tự điều kiện cũng thể hiện thứ tự kiểm tra hợp lý: đặt phép kiểm tra kiểu trước, rồi mới gọi phương thức riêng của kiểu đó. Nếu đặt `command.startsWith(...)` trước phép kiểm tra `instanceof`, biến `command` chưa được khai báo và chương trình không biên dịch.

## 4. Xử lý `null` mà không cần kiểm tra riêng

Biểu thức `instanceof` trả về `false` khi toán hạng là `null`. Kết hợp với short-circuit của `&&`, điều này giúp tránh gọi phương thức trên một giá trị null:

```java
static boolean isNonBlankText(Object value) {
    return value instanceof String text && !text.isBlank();
}
```

Nếu `value` là `null`, phép kiểm tra đầu tiên trả về `false`, nên `text.isBlank()` không được đánh giá. Nếu `value` không phải `String`, kết quả cũng tương tự. Chỉ một chuỗi khác `null` mới đi đến điều kiện tiếp theo.

Vì vậy, trong mẫu này, kiểm tra `value != null` trước phép `instanceof` là dư thừa:

```java
// Không cần thêm value != null.
if (value instanceof String text && !text.isEmpty()) {
    System.out.println(text);
}
```

Điều này không có nghĩa mọi phép gọi phương thức đều tự an toàn với `null`. Sự an toàn đến từ việc đặt phép kiểm tra kiểu ở vế trái và sử dụng `&&` để Java bỏ qua vế phải khi pattern không khớp.

## 5. Phân biệt `&&` với `&`

Khi làm việc với điều kiện boolean, cần dùng `&&` cho mẫu kiểm tra theo thứ tự. `&&` bỏ qua vế phải nếu vế trái sai. Toán tử `&` trên boolean luôn đánh giá cả hai vế, vì vậy không tạo ra bảo đảm short-circuit cần thiết cho cách viết này.

```java
if (value instanceof String text && text.length() > 0) {
    System.out.println(text);
}
```

Trong ví dụ trên, `text.length()` chỉ được đánh giá khi `instanceof` đúng. Không thay `&&` bằng `&` với ý định giữ nguyên hành vi. Ngoài khác biệt về đánh giá, quy tắc flow scoping của pattern variable cũng được thiết kế cho các vị trí mà kết quả biểu thức chứng minh pattern đã khớp.

## 6. Dùng pattern với kiểu giao diện và collection

Pattern không chỉ áp dụng cho lớp cụ thể như `String`. Có thể kiểm tra một kiểu giao diện rồi sử dụng các phương thức mà kiểu đó khai báo:

```java
static void printSequence(Object value) {
    if (value instanceof CharSequence sequence
            && sequence.length() > 0) {
        System.out.println(sequence.charAt(0));
    }
}
```

Ở đây, biến `sequence` có kiểu tĩnh `CharSequence`, vì vậy chỉ có thể gọi các phương thức được khai báo trong `CharSequence`, chẳng hạn `length()` và `charAt()`.

Với collection generic, dùng kiểu có thể kiểm tra tại runtime như `List<?>`:

```java
import java.util.List;

static void printFirstItem(Object value) {
    if (value instanceof List<?> items && !items.isEmpty()) {
        Object first = items.get(0);
        System.out.println(first);
    }
}
```

`List<?>` cho phép xác nhận đối tượng là một `List` mà không giả định kiểu phần tử cụ thể. Sau khi danh sách được xác nhận và không rỗng, chương trình mới đọc phần tử đầu tiên.

Không thể dùng `instanceof List<String> items` để kiểm tra trực tiếp tham số kiểu `String` tại runtime, vì generic type argument bị xóa bởi type erasure và `List<String>` không phải kiểu reifiable. Khi cần xác nhận kiểu của từng phần tử, phải kiểm tra phần tử riêng, ví dụ:

```java
static void printFirstString(Object value) {
    if (value instanceof List<?> items
            && !items.isEmpty()
            && items.get(0) instanceof String first) {
        System.out.println(first.toUpperCase());
    }
}
```

Mỗi pattern có biến riêng. Vế kiểm tra `items.get(0) instanceof String first` chỉ được đánh giá sau khi `items` đã được xác nhận là danh sách và không rỗng; thân `if` chỉ chạy khi phần tử đầu tiên cũng là `String`.

## 7. Những giới hạn cần nhớ

- Biến pattern chỉ dùng được từ vị trí mà luồng điều khiển chứng minh phép kiểm tra kiểu đã đúng. Trong biểu thức `A && B`, biến được khai báo trong `A` có thể dùng ở `B` vì `B` chỉ chạy khi `A` đúng.
- Biến pattern không tự động có trong nhánh `else` của điều kiện kết hợp. Nhánh đó có thể được chạy vì phép kiểm tra kiểu sai hoặc vì một điều kiện kiểm tra tiếp theo sai.
- Không gọi phương thức riêng của kiểu đích trước khi xác nhận kiểu. Đặt `instanceof` ở đầu chuỗi điều kiện.
- Các vế phải có thể bị bỏ qua do short-circuit. Không đặt thao tác có tác dụng phụ bắt buộc phải chạy trong một vế mà điều kiện trước đó có thể làm nó bị bỏ qua.
- `&&` nhận các biểu thức boolean. Một biểu thức kiểm tra dữ liệu không trả về boolean không thể đặt trực tiếp làm vế của toán tử này.

Ví dụ sau minh họa vì sao biến pattern không được bảo đảm trong `else`:

```java
if (value instanceof String text && !text.isBlank()) {
    System.out.println(text);
} else {
    // Không thể dùng text ở đây.
    // Điều kiện có thể sai ngay từ instanceof hoặc do chuỗi rỗng.
}
```

## 8. Ví dụ hoàn chỉnh

```java
import java.util.List;

public class InstanceofAndAndDemo {

    static void printCommand(Object value) {
        if (value instanceof String command
                && !command.isBlank()
                && command.startsWith("deploy:")
                && command.length() <= 80) {
            System.out.println("Command: " + command.strip());
        } else {
            System.out.println("Invalid command");
        }
    }

    static void printFirstString(Object value) {
        if (value instanceof List<?> items
                && !items.isEmpty()
                && items.get(0) instanceof String first) {
            System.out.println(first.toUpperCase());
        }
    }

    public static void main(String[] args) {
        printCommand("deploy:service-a");
        printCommand("   ");
        printCommand(42);
        printCommand(null);

        printFirstString(List.of("java", 16));
        printFirstString(List.of(16, "java"));
        printFirstString(List.of());
    }
}
```

Có thể biên dịch bằng JDK 16 trở lên. Khi dùng JDK mới và muốn kiểm tra mã theo mức ngôn ngữ Java 16:

```bash
javac --release 16 InstanceofAndAndDemo.java
java InstanceofAndAndDemo
```

## 9. Cách áp dụng trong mã thực tế

- Viết phép `instanceof` trước các điều kiện cần gọi phương thức của kiểu đã kiểm tra.
- Dùng `&&` để xâu chuỗi kiểm tra kiểu, kiểm tra null ngầm định, kiểm tra rỗng, giới hạn độ dài hoặc các quy tắc nghiệp vụ.
- Sắp xếp điều kiện từ bước xác nhận an toàn đến bước kiểm tra sâu hơn; điều kiện có chi phí thấp và cần thiết nên đặt trước điều kiện tốn kém.
- Chỉ dựa vào biến pattern trong vế phải và nhánh mà compiler xác định pattern đã khớp.
- Với collection generic, dùng wildcard như `List<?>` để kiểm tra kiểu container, rồi kiểm tra riêng kiểu phần tử khi cần.

Kết hợp `instanceof` với `&&` giúp biểu diễn rõ một chuỗi xác nhận: trước tiên xác định kiểu runtime, sau đó kiểm tra dữ liệu bằng các thao tác đúng với kiểu đó. Nhờ short-circuit và flow scoping, mã vừa tránh ép kiểu thủ công vừa giữ được kiểm tra kiểu tĩnh trong Java 16 và các phiên bản Java hiện đại.
