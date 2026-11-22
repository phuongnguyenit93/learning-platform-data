# Lớp thực thi một hoặc nhiều interface bằng implements

## 1. Cú pháp trong khai báo class

Một class dùng `implements` để cam kết thực hiện một hoặc nhiều interface. Nếu class còn kế thừa một superclass, `extends` phải đứng trước `implements`:

```java
interface Printable {
    void print();
}

interface Storable {
    void save();
}

class DocumentBase {
    protected String prefix() {
        return "DOC";
    }
}

final class Report extends DocumentBase implements Printable, Storable {
    @Override
    public void print() {
        System.out.println(prefix() + " printed");
    }

    @Override
    public void save() {
        System.out.println(prefix() + " saved");
    }
}

public class Main {
    public static void main(String[] args) {
        Printable item = new Report();
        item.print();
    }
}
```

Kết quả:

```text
DOC printed
```

Cú pháp đúng là `class Report extends DocumentBase implements Printable, Storable`. Một class chỉ có một superclass trực tiếp, nhưng có thể triển khai nhiều interface. Giữa các interface với nhau, dùng `extends`.

## 2. Trách nhiệm của class concrete

Một class không khai báo `abstract` phải cung cấp implementation hợp lệ cho các abstract method mà nó nhận từ interface và superclass. Không nhất thiết mỗi method phải được viết lại ngay trong class có `implements`: một implementation phù hợp có thể được thừa hưởng từ superclass hoặc từ default method.

Ví dụ, với `interface Validator { boolean valid(String value); }`, phương thức `boolean valid(Object value)` không triển khai `valid(String)` vì khác kiểu tham số. Phương thức `protected boolean valid(String value)` cũng không hợp lệ để thực hiện một phương thức public của interface. Dùng `@Override` giúp compiler phát hiện các lỗi chữ ký phổ biến.

Các quy tắc khác của Java vẫn áp dụng: kiểu trả về phải tương thích, không được giảm quyền truy cập, và implementation không thể thêm checked exception trái với hợp đồng gốc. Nếu class chưa thể hoàn thành hợp đồng, có thể khai báo nó là `abstract` và để lớp con concrete hoàn tất.

## 3. Interface là kiểu cho đa hình

```java
interface Sender {
    void send(String message);
}

final class ConsoleSender implements Sender {
    @Override
    public void send(String message) {
        System.out.println("console: " + message);
    }
}

final class AlertService {
    private final Sender sender;

    AlertService(Sender sender) {
        this.sender = sender;
    }

    void alert(String message) {
        sender.send(message);
    }
}

public class Main {
    public static void main(String[] args) {
        AlertService service = new AlertService(new ConsoleSender());
        service.alert("Order received");
    }
}
```

Kết quả:

```text
console: Order received
```

`AlertService` phụ thuộc vào hợp đồng `Sender`. Có thể truyền vào một implementation khác mà không phải thay đổi logic gọi `alert`. Đây cũng là nền tảng của dependency injection và việc đưa một implementation giả vào test.

Compiler kiểm tra lời gọi theo kiểu khai báo `Sender`; lúc chạy, JVM dispatch `send` đến implementation của đối tượng thực tế. Nếu thường xuyên ép kiểu sang một class cụ thể để gọi các method riêng, hãy xem hợp đồng hiện tại có thiếu hành vi cần thiết hoặc có thể được chia thành interface nhỏ hơn hay không.

## 4. Kế thừa implementation và default method

Nếu `Vehicle implements Movable`, thì `ElectricVehicle extends Vehicle` cũng là `Movable` dù không lặp lại từ khóa `implements Movable`. Lớp con có thể dùng implementation thừa hưởng hoặc override nó.

Các method `default` có thể được dùng mà không cần override. Nếu nhiều interface mang các default method xung đột cùng chữ ký, class phải giải quyết xung đột theo quy tắc kế thừa Java; bài về `extends` trình bày cách dùng `InterfaceName.super.method()` và cách tái khai báo abstract method.

## 5. Lỗi thường gặp

| Sai lầm | Cách đúng |
| --- | --- |
| `class A implements I1 implements I2` | `class A implements I1, I2` |
| `class A implements I extends Base` | `class A extends Base implements I` |
| Concrete class thiếu abstract method | Cài đặt method còn thiếu, thừa hưởng implementation hợp lệ hoặc khai báo class abstract. |
| Implementation giảm mức truy cập | Giữ `public` khi thực hiện phương thức public của interface. |
| Nghĩ biến kiểu interface gọi được mọi method của implementation | Gọi qua các thành viên của kiểu tham chiếu, hoặc thiết kế hợp đồng phù hợp. |
| Tạo interface cho mọi class theo thói quen | Chỉ tạo khi hợp đồng mang lại lợi ích thực tế. |

**Tự kiểm tra:** Nếu `Report` triển khai cả `Printable` và `Storable`, một biến `Printable p = new Report()` có gọi trực tiếp `p.save()` không? Không; `save()` không thuộc kiểu tham chiếu `Printable` dù đối tượng thực tế cũng là `Storable`.