# Gọi default method bằng InterfaceName.super trong Java

Khi override một default method nhưng muốn tái sử dụng đúng phần thân của interface, Java có cú pháp `InterfaceName.super.method(arguments)`. Nó hữu ích để mở rộng một hành vi mặc định hoặc lựa chọn rõ ràng giữa các default method xung đột.

## 1. Phân biệt ba kiểu gọi

| Cú pháp | Ý nghĩa |
| --- | --- |
| `this.method()` hoặc `method()` | Gọi phương thức trên đối tượng hiện tại theo quy tắc dispatch thông thường. |
| `super.method()` | Tìm implementation qua nhánh superclass. |
| `InterfaceName.super.method()` | Chỉ định một default implementation từ superinterface phù hợp. |

`InterfaceName.super` không phải biến hoặc đối tượng có thể lưu vào tham chiếu. Đây là cú pháp đặc biệt của Java, chỉ dùng trong ngữ cảnh hợp lệ và với một default implementation có thể gọi được.

## 2. Mở rộng default method

```java
public class InterfaceSuperDemo {
    interface Greeting {
        default String sayHello(String name) {
            return "Xin chào, " + name;
        }
    }

    static final class FriendlyGreeting implements Greeting {
        @Override
        public String sayHello(String name) {
            String base = Greeting.super.sayHello(name);
            return base + "!";
        }
    }

    public static void main(String[] args) {
        Greeting greeting = new FriendlyGreeting();
        System.out.println(greeting.sayHello("Lan"));
    }
}
```

Kết quả:

```text
Xin chào, Lan!
```

`FriendlyGreeting` gọi phần thân default để tạo câu chào, rồi thêm dấu cảm thán. Nếu viết `return sayHello(name) + "!";` trong chính override này, phương thức sẽ gọi lại nó và đệ quy cho đến `StackOverflowError`. Qualified super call tránh việc đó.

## 3. Chọn giữa hai default method

```java
public class DefaultConflictDemo {
    interface Left {
        default String source() { return "Left"; }
    }

    interface Right {
        default String source() { return "Right"; }
    }

    static final class Combined implements Left, Right {
        @Override
        public String source() {
            return Left.super.source() + " + " + Right.super.source();
        }
    }

    public static void main(String[] args) {
        System.out.println(new Combined().source());
    }
}
```

Kết quả là `Left + Right`. Hai interface độc lập cung cấp cùng chữ ký nên class phải override để giải quyết xung đột. Override có thể chọn một phía, kết hợp cả hai hoặc viết logic mới; thứ tự interface trong `implements` không tạo ưu tiên.

## 4. Interface con cũng có thể gọi default của cha

```java
interface Parent {
    default String label() {
        return "parent";
    }
}

interface Child extends Parent {
    @Override
    default String label() {
        return Parent.super.label() + "/child";
    }
}
```

`Child` có thể gọi `Parent.super.label()` vì `Parent` là superinterface trực tiếp của `Child`. Khi một class triển khai `Child` mà không override, nó nhận default mới của `Child`.

## 5. Điều kiện cần nhớ

- Phương thức được gọi phải có default implementation phù hợp; không thể gọi một method chỉ abstract.
- Lời gọi phải ở ngữ cảnh instance hợp lệ, không dùng trong phương thức static.
- Interface qualifier phải phù hợp với quan hệ superinterface tại nơi chứa lời gọi. Không thể tùy ý gọi một interface bất kỳ mà đối tượng có thể ép kiểu sang.
- Static method của interface được gọi bằng tên interface, không bằng `InterfaceName.super`.
- Qualified super call không cho phép bỏ qua mọi quy tắc kế thừa hoặc tùy tiện gọi một implementation đã bị thay thế ở nhánh cụ thể hơn.

Các điều kiện tinh vi về superinterface trực tiếp, interface trung gian và nhánh cụ thể hơn được phân tích riêng ở bài về giới hạn gọi super qua interface trực tiếp.

**Ghi nhớ:** `InterfaceName.super.method()` chỉ định rõ một default implementation trong phạm vi mà Java cho phép. Dùng nó bên trong override khi cần mở rộng hành vi hoặc giải quyết xung đột; đừng nhầm nó với `super.method()` của class.