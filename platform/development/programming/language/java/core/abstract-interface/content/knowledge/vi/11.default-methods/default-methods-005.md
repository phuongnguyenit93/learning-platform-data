# Kế thừa default method qua interface con trong Java

Khi interface con `extends` một interface cha, nó kế thừa các phương thức hợp lệ của cha, bao gồm cả default method. Nếu interface con không khai báo lại phương thức, lớp triển khai có thể sử dụng default đó qua nhiều tầng kế thừa.

## 1. Kế thừa nguyên trạng

```java
public class DefaultInheritanceDemo {
    interface Greeter {
        default String greet(String name) {
            return "Hello, " + name;
        }
    }

    interface NamedGreeter extends Greeter {
        String kind();
    }

    static final class ConsoleGreeter implements NamedGreeter {
        @Override
        public String kind() {
            return "console";
        }
        // greet(String) được kế thừa.
    }

    public static void main(String[] args) {
        NamedGreeter greeter = new ConsoleGreeter();
        System.out.println(greeter.greet("Java"));
        System.out.println(greeter.kind());
    }
}
```

Kết quả:

```text
Hello, Java
console
```

`NamedGreeter` không cần khai báo lại `greet`. `ConsoleGreeter` chỉ cài đặt phương thức abstract `kind` nhưng vẫn có thể gọi `greet` trên tham chiếu kiểu `NamedGreeter`.

## 2. Interface con cung cấp default mới

Interface con có thể override phương thức default bằng một default method khác. Bản của interface con được chọn vì nó nằm ở nhánh chuyên biệt hơn.

```java
interface BasicLabel {
    default String label() {
        return "base";
    }
}

interface DetailedLabel extends BasicLabel {
    @Override
    default String label() {
        return BasicLabel.super.label() + "-detailed";
    }
}

final class Service implements DetailedLabel {
}
```

`new Service().label()` trả về `base-detailed`. Trong ví dụ, interface con thay đổi hành vi mặc định cho toàn bộ nhánh của nó. Cú pháp `BasicLabel.super.label()` được dùng ở đúng nơi interface con trực tiếp kế thừa `BasicLabel`; điều kiện chi tiết của cú pháp này được bàn riêng ở bài về qualified super calls.

## 3. Nhiều interface cha

Nếu interface con kế thừa hai default method cùng chữ ký từ hai interface cha không có quan hệ đặc hiệu, Java không tự chọn một bên. Interface con cần override để quyết định hành vi hoặc khai báo lại phương thức thành abstract để yêu cầu các lớp triển khai cung cấp implementation.

```java
interface Left {
    default String side() { return "left"; }
}

interface Right {
    default String side() { return "right"; }
}

interface Combined extends Left, Right {
    @Override
    default String side() {
        return Left.super.side() + " + " + Right.super.side();
    }
}

final class CombinedImpl implements Combined {
}
```

`new CombinedImpl().side()` trả về `left + right`. Nếu không có override tại `Combined`, hai default method cạnh tranh sẽ gây lỗi biên dịch. Không có quy tắc ưu tiên interface được liệt kê trước.

Khi một interface con override default của interface cha, lớp triển khai nhận bản chuyên biệt hơn. Nếu hai interface không liên quan cùng khai báo default cạnh tranh, phải giải quyết rõ ràng. Nếu class/superclass có một phương thức instance concrete phù hợp, phương thức class có thể được ưu tiên.

## 4. Chọn cách thiết kế

- **Không khai báo lại:** giữ default của cha.
- **Override bằng default mới:** cung cấp một hành vi chung khác cho nhánh con.
- **Khai báo lại thành abstract:** bỏ việc thừa hưởng implementation cho chữ ký đó và yêu cầu implementation phù hợp. Trường hợp này có điều kiện và hệ quả riêng, được giải thích ở bài về tái trừu tượng hóa.

Các lựa chọn này áp dụng theo từng chữ ký; khai báo lại một phương thức không làm các default method khác của cha biến mất.

## Tự kiểm tra

1. Một class chỉ implements interface con có cần cài lại mọi default method từ cha không?
2. Vì sao default method của interface con thắng default từ interface cha mà nó override?
3. Java xử lý thế nào khi hai interface cha độc lập cùng cung cấp default method trùng chữ ký?
4. Thứ tự interface trong mệnh đề `implements` có quyết định bên nào thắng không?

**Ghi nhớ:** interface con có thể giữ nguyên default của cha, cung cấp default mới hoặc yêu cầu implementation rõ ràng. Khi có nhiều nguồn phương thức, phải xét quan hệ đặc hiệu, xung đột và phương thức concrete được kế thừa từ class.