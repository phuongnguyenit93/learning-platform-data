# Interface mở rộng một hoặc nhiều interface bằng extends

## 1. Cú pháp và quan hệ subtype

Interface dùng `extends` để kế thừa một hoặc nhiều interface. Danh sách superinterface được ngăn cách bằng dấu phẩy:

```java
interface Identified {
    String id();
}

interface Named {
    String name();
}

interface CatalogEntry extends Identified, Named {
    String category();
}
```

`CatalogEntry` kế thừa hợp đồng của `Identified` và `Named`, đồng thời thêm `category()`. Một giá trị kiểu `CatalogEntry` cũng có thể được dùng qua kiểu `Identified` hoặc `Named`. Đây là quan hệ subtype; không tạo bản sao đối tượng.

Interface không thể `extends` class, và Java cấm vòng kế thừa. Cú pháp `interface Child implements Parent` là sai; `implements` dùng ở khai báo class.

## 2. Thành viên nào được kế thừa?

| Thành viên của superinterface | Quy tắc chính |
| --- | --- |
| Abstract instance method | Trở thành phần của hợp đồng con; class concrete phải đáp ứng nếu chưa có implementation hợp lệ. |
| `default` instance method | Có thể được kế thừa cùng implementation, trừ khi bị override hoặc có xung đột. |
| Field hằng `public static final` | Có thể được tham chiếu qua interface con, nhưng tên trùng có thể mơ hồ. |
| `static` method | Không được kế thừa như method của interface con; gọi qua tên interface khai báo nó. |
| `private` method | Là helper nội bộ của interface khai báo, không được kế thừa. |

Quan hệ kế thừa có tính bắc cầu. Nếu `Leaf extends Middle` và `Middle extends Root`, một class triển khai `Leaf` cũng phải thỏa các hợp đồng abstract còn thiếu của `Middle` và `Root`.

## 3. Các khai báo abstract tương thích

Hai superinterface có thể khai báo abstract method cùng chữ ký:

```java
interface Reader {
    String read();
}

interface TextSource {
    String read();
}

interface ReadableText extends Reader, TextSource {}

final class FileText implements ReadableText {
    @Override
    public String read() {
        return "hello";
    }
}
```

Một implementation `public String read()` đáp ứng cả hai hợp đồng. Kiểu trả về cũng phải tương thích theo quy tắc Java. Ví dụ, một method trả `Integer` có thể đáp ứng các khai báo trả `Integer` và `Number` tương thích trong cùng hierarchy. Trái lại, `String get()` và `Integer get()` không thể được phân biệt chỉ bằng return type; tổ hợp không tương thích sẽ gây lỗi biên dịch.

Với generic interface, đối số kiểu được áp dụng xuyên suốt chuỗi kế thừa. Việc kế thừa cùng generic interface qua các đối số kiểu không tương thích có thể bị từ chối do xung đột kiểu hoặc type erasure.

## 4. Xung đột default method

Hai interface không liên quan có thể cùng khai báo một `default` method. Interface con phải giải quyết xung đột thay vì để Java tự chọn tùy ý.

```java
interface Left {
    default String label() {
        return "left";
    }
}

interface Right {
    default String label() {
        return "right";
    }
}

interface Combined extends Left, Right {
    @Override
    default String label() {
        return Left.super.label() + "/" + Right.super.label();
    }
}

public class Main {
    public static void main(String[] args) {
        System.out.println(new Choice().label());
    }
}

final class Choice implements Combined {}
```

Kết quả:

```text
left/right
```

`Left.super.label()` và `Right.super.label()` gọi rõ implementation từ superinterface trực tiếp phù hợp. Cách khác là tái khai báo `String label();` trong `Combined` để buộc class concrete cung cấp implementation. Nếu interface con là nhánh chuyên biệt hơn và override một default method của cha, implementation chuyên biệt có thể được ưu tiên theo quy tắc Java; phương thức instance hợp lệ từ class cũng có thể thắng default method.

## 5. Những nhầm lẫn cần tránh

- `extends A, B` dùng dấu phẩy, không dùng dấu `&` trong danh sách superinterface.
- `static` method của cha không trở thành `Child.staticMethod()`.
- `private` helper không phải một phần hợp đồng được lớp triển khai cung cấp.
- Một class concrete triển khai interface con vẫn phải đáp ứng các abstract method được kế thừa.
- `sealed interface` (Java 17+) có thể giới hạn các subtype trực tiếp được phép; nó không thay đổi nguyên tắc cơ bản của `extends`.

**Tự kiểm tra:** Nếu `Combined extends Left, Right` mà hai cha có default method cùng chữ ký, khai báo interface con rỗng có luôn hợp lệ không? Không; cần override hoặc tái khai báo abstract method khi xung đột không được giải quyết bởi quy tắc kế thừa.