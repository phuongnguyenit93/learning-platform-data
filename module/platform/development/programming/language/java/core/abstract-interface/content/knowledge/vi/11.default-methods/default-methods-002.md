# Cú pháp và thân phương thức default trong Java interface

Một phương thức `default` là phương thức instance có thân được khai báo **bên trong interface**. Từ Java 8, nó cho phép interface cung cấp hành vi chung; lớp triển khai có thể kế thừa hành vi đó mà không phải tự viết lại.

## 1. Cú pháp và quyền truy cập

```java
interface CounterView {
    int value();

    default boolean isEmpty() {
        return value() == 0;
    }

    default void printStatus() {
        System.out.println(isEmpty() ? "Rỗng" : "Có dữ liệu");
    }
}
```

`value()` là phương thức abstract, còn `isEmpty()` và `printStatus()` có phần thân. Một default method có thể dùng tham số, biến cục bộ, điều kiện, vòng lặp, `return`, `throw` và gọi những phương thức hợp lệ khác như một instance method thông thường.

Default method luôn là **public**, kể cả khi không ghi từ khóa `public`. Khi override trong class, phương thức thay thế cũng phải là `public`. Từ khóa `default` không có nghĩa package-private và không biến phương thức thành `static`.

## 2. Phân biệt các loại phương thức

| Khai báo | Có thân? | Ý nghĩa |
| --- | --- | --- |
| `void run();` | Không | Hợp đồng abstract; class cụ thể cần implementation phù hợp. |
| `default void run() { ... }` | Có | Hành vi instance mặc định; class có thể kế thừa hoặc override. |
| `static void help() { ... }` | Có | Thuộc interface, gọi bằng `InterfaceName.help()`; không override theo đa hình instance. |
| `private void helper() { ... }` | Có, từ Java 9 | Helper nội bộ để các phương thức của interface tái sử dụng logic. |

Default method bắt buộc có thân. Muốn khai báo abstract, hãy bỏ `default` và kết thúc bằng dấu chấm phẩy. Không thể dùng `default` trong một class thông thường.

## 3. Ví dụ chạy được

Lưu vào `Main.java`:

```java
public class Main {
    interface Greeting {
        default String greet(String name) {
            return "Xin chào, " + name;
        }
    }

    static final class BasicGreeter implements Greeting {
        // Kế thừa greet(String).
    }

    static final class FriendlyGreeter implements Greeting {
        @Override
        public String greet(String name) {
            return "Chào bạn, " + name;
        }
    }

    public static void main(String[] args) {
        System.out.println(new BasicGreeter().greet("An"));
        System.out.println(new FriendlyGreeter().greet("An"));
    }
}
```

Chạy bằng JDK 17 trở lên:

```bash
javac Main.java
java Main
```

Kết quả:

```text
Xin chào, An
Chào bạn, An
```

`BasicGreeter` dùng thân mặc định. `FriendlyGreeter` cung cấp một phương thức instance `public` với cùng chữ ký để thay đổi hành vi. Class không viết thêm từ khóa `default`.

## 4. Những lỗi cú pháp thường gặp

```java
interface Invalid {
    default void run();          // Sai: thiếu thân.
    abstract default void a() {} // Sai: abstract và default xung đột.
    static default void b() {}   // Sai: static và default xung đột.
    protected default void c() {} // Sai: default method là public.
}
```

Một phương thức có thân trong interface cũng không được khai báo `default` để thay thế các phương thức public tương ứng của `Object`, chẳng hạn `toString()`, `equals(Object)` hoặc `hashCode()`. Nếu cần cách triển khai riêng, hãy đặt override trong class.

Đừng nhầm `default method` với nhánh `default:` của `switch`, giá trị mặc định của annotation hoặc package-private access. Đây là modifier riêng cho phương thức instance có thân trong interface.

## 5. Cách quyết định

Dùng default method khi có một hành vi chung hợp lý mà các implementation có thể kế thừa. Nếu mọi implementation phải tự xác định chính sách quan trọng, dùng phương thức abstract. Nếu hành vi cần trạng thái riêng, constructor hoặc quản lý tài nguyên, hãy cân nhắc class hoặc composition. Quy tắc chọn giữa các phương thức kế thừa được trình bày ở các bài về override và kế thừa; cú pháp cơ bản ở đây không tự giải quyết mọi xung đột.

## Tự kiểm tra

1. Vì sao `default void run();` không hợp lệ?
2. Default method có phải là phương thức package-private không?
3. Class override default method có cần ghi `default` không?
4. Từ phiên bản Java nào interface có private helper methods?

**Ghi nhớ:** `default ReturnType method(...) { ... }` chỉ dùng cho phương thức instance có thân trong interface. Nó là public và có thể được class triển khai override bằng phương thức instance bình thường.