# Biến default method thành yêu cầu abstract ở interface con

Một interface con có thể khai báo lại default method của interface cha bằng một phương thức không có thân. Khai báo đó là `public abstract` theo mặc định và yêu cầu các kiểu triển khai interface con có một implementation phù hợp.

## 1. Cú pháp và ý nghĩa

```java
interface Greeting {
    default String greet(String name) {
        return "Hello, " + name;
    }
}

interface FormalGreeting extends Greeting {
    @Override
    String greet(String name); // public abstract
}
```

Đây là **tái trừu tượng hóa** (*re-abstracting a default method*). Nó không xóa thân `Greeting.greet` khỏi interface cha; nó thay đổi hợp đồng của nhánh `FormalGreeting`. Những class chỉ implements `Greeting` vẫn có thể dùng default cũ.

Để tái trừu tượng hóa, interface con phải có quan hệ kế thừa với interface khai báo default, khai báo lại phương thức với chữ ký override hợp lệ và không viết thân hoặc từ khóa `default`. Viết `public abstract` tường minh cũng hợp lệ, nhưng không bắt buộc.

## 2. Ví dụ hoàn chỉnh

```java
public class ReabstractDemo {
    interface Greeting {
        default String greet(String name) {
            return "Hello, " + name;
        }

        default String farewell(String name) {
            return "Goodbye, " + name;
        }
    }

    interface FormalGreeting extends Greeting {
        @Override
        String greet(String name);
    }

    static final class BasicGreeting implements Greeting {
    }

    static final class CorporateGreeting implements FormalGreeting {
        @Override
        public String greet(String name) {
            return "Dear " + name;
        }
    }

    public static void main(String[] args) {
        Greeting basic = new BasicGreeting();
        FormalGreeting formal = new CorporateGreeting();

        System.out.println(basic.greet("An"));
        System.out.println(formal.greet("An"));
        System.out.println(((Greeting) formal).greet("An"));
        System.out.println(formal.farewell("An"));
    }
}
```

Kết quả:

```text
Hello, An
Dear An
Dear An
Goodbye, An
```

Ép kiểu tham chiếu `formal` về `Greeting` không chọn lại thân default của cha. Đối tượng thực tế vẫn là `CorporateGreeting`, nên dynamic dispatch gọi implementation `greet` của class. Phương thức `farewell` không bị khai báo lại, vì thế nó vẫn là default được kế thừa.

## 3. Lớp triển khai cần làm gì?

Một class cụ thể cần có phương thức instance `public` phù hợp. Nó có thể khai báo phương thức trực tiếp hoặc kế thừa một implementation công khai hợp lệ từ superclass. Vì vậy, tái trừu tượng hóa không có nghĩa mọi class luôn phải viết lại phương thức nếu class đã có implementation thỏa hợp đồng.

```java
abstract class GreetingBase {
    public String greet(String name) {
        return "Base: " + name;
    }
}

final class InheritedGreeting extends GreetingBase
        implements FormalGreeting {
    // Phương thức public greet(String) từ superclass đáp ứng hợp đồng.
}
```

Đoạn trên giả định `FormalGreeting` được khai báo như ví dụ trước. `InheritedGreeting` không cần tự override `greet` vì phương thức concrete kế thừa từ superclass có chữ ký phù hợp.

Không thể giảm quyền truy cập xuống package-private, `protected` hoặc `private`. Các quy tắc kiểu trả về và checked exception của override cũng tiếp tục áp dụng.

## 4. Khi nào nên dùng?

Tái trừu tượng hóa hữu ích khi interface cha có mặc định đủ tốt cho đa số trường hợp, nhưng một nhánh chuyên biệt cần yêu cầu hành vi cụ thể. Ví dụ, một `SecureStorage` có thể tái khai báo `validate()` thành abstract nếu default đơn giản của `Storage` không đáp ứng được hợp đồng bảo mật của nhánh đó.

Chỉ nên làm vậy khi không có một default duy nhất đáng tin cậy cho toàn bộ nhánh. Nếu interface con có thể cung cấp một default mới đúng cho mọi implementation, lựa chọn đó có thể đơn giản hơn. Re-abstract kiểm tra sự tồn tại của implementation ở cấp ngôn ngữ; nó không chứng minh logic nghiệp vụ của implementation là đúng.

## 5. Những lỗi dễ gặp

- Viết `default String greet(String name);` mà không có thân: không hợp lệ vì default method bắt buộc có thân.
- Cho rằng phải viết từ khóa `abstract`: không cần; khai báo `String greet(String name);` trong interface đã ngầm định public abstract.
- Cho rằng interface cha mất default method: sai; thay đổi chỉ áp dụng cho nhánh con.
- Cho rằng mọi class phải khai báo trực tiếp phương thức: không tuyệt đối nếu superclass đã cung cấp implementation công khai phù hợp.
- Tái khai báo static method hoặc method không có quan hệ override: không phải tái trừu tượng hóa default method.

## Tự kiểm tra

1. Trong `interface Child extends Parent { void act(); }`, khai báo `act()` là abstract hay default?
2. Nếu class cụ thể không có implementation phù hợp, biên dịch có thành công không?
3. Tại sao ép kiểu đối tượng triển khai về interface cha không gọi lại default cũ?
4. Một default method khác của interface cha có bị ảnh hưởng không?

**Ghi nhớ:** interface con có thể làm một default method thành yêu cầu abstract bằng cách khai báo lại phương thức không có thân. Lớp triển khai cần có implementation công khai phù hợp, trực tiếp hoặc được kế thừa từ superclass.