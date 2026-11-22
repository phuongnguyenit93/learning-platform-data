# Gọi phương thức abstract từ phương thức default trong Java

Một default method có thể định nghĩa quy trình chung nhưng giao một bước cụ thể cho phương thức abstract mà mỗi lớp triển khai cung cấp. Mẫu này giúp tái sử dụng thuật toán mà không gắn interface với một lớp cụ thể.

## 1. Hợp đồng và điểm tùy biến

```java
interface Greeter {
    String displayName();

    default String greet() {
        return "Xin chào, " + displayName();
    }
}
```

`displayName()` khai báo hợp đồng; `greet()` cung cấp cách chào dùng chung. Default method được phép gọi phương thức abstract vì phương thức đó thuộc kiểu interface. Khi chạy, lời gọi instance được phân phối đến implementation của đối tượng thực tế.

## 2. Theo dõi luồng thực thi

```java
public class Main {
    interface Greeter {
        String displayName();

        default String greet() {
            return "Xin chào, " + displayName();
        }
    }

    static final class Employee implements Greeter {
        private final String name;

        Employee(String name) {
            this.name = name;
        }

        @Override
        public String displayName() {
            return name;
        }
    }

    static final class Guest implements Greeter {
        @Override
        public String displayName() {
            return "bạn";
        }
    }

    public static void main(String[] args) {
        Greeter employee = new Employee("An");
        Greeter guest = new Guest();

        System.out.println(employee.greet());
        System.out.println(guest.greet());
    }
}
```

Kết quả:

```text
Xin chào, An
Xin chào, bạn
```

Khi gọi `employee.greet()`, Java dùng thân default của `Greeter` vì `Employee` không override `greet`. Bên trong thân đó, `displayName()` chạy trên đối tượng hiện tại nên kết quả đến từ `Employee.displayName()`. Đối tượng `Guest` đi qua cùng quy trình chung nhưng trả tên khác.

Trình biên dịch kiểm tra rằng `Greeter` khai báo `displayName()`. JVM thực thi implementation phù hợp với đối tượng thật khi chạy. `this` bên trong default method tham chiếu đến đối tượng triển khai đang nhận lời gọi, không phải một instance riêng của interface.

## 3. Hai quyết định độc lập

Nếu một lớp override `greet()`, lời gọi ngoài sẽ dùng thân override đó. Khi thân được chọn lại gọi `displayName()`, lời gọi thứ hai vẫn được phân phối theo implementation thực tế của đối tượng. Vì vậy cần phân biệt:

1. Phương thức nào cung cấp quy trình tổng thể: default hay override của class.
2. Implementation nào cung cấp từng bước abstract mà quy trình gọi đến.

Mẫu này hữu ích khi nhiều lớp cần cùng một quy trình nhưng khác dữ liệu hoặc một bước xử lý, chẳng hạn định dạng thông điệp, tạo nhãn hay xác định một giá trị theo loại đối tượng.

## 4. Giữ hợp đồng đủ rõ

Default method nên dựa vào những thao tác mà interface công bố. Nếu phương thức abstract có thể trả về `null`, ném ngoại lệ hoặc thay đổi trạng thái, hợp đồng cần giải thích cách default method xử lý những trường hợp đó. Một chữ ký hợp lệ không tự bảo đảm mọi implementation đều có cùng ngữ nghĩa.

Nếu thuật toán cần nhiều thao tác thay đổi trạng thái mà phải chạy như một giao dịch duy nhất, không nên giả định rằng gom chúng trong một default method sẽ khiến chúng atomic. Hãy để lớp sở hữu trạng thái cung cấp một thao tác trừu tượng phù hợp.

## Tự kiểm tra

1. Vì sao `greet()` có thể gọi `displayName()` dù interface không có phần thân cho phương thức đó?
2. Khi `employee.greet()` chạy, vì sao tên là `An`?
3. Nếu `Employee` override `greet()`, phương thức `displayName()` có tự mất tính đa hình không?
4. Vì sao default method nên dựa vào hợp đồng interface thay vì ép kiểu sang một lớp cụ thể?

**Ghi nhớ:** default method định nghĩa quy trình dùng chung; phương thức abstract là điểm mở để đối tượng thật cung cấp dữ liệu hoặc hành vi riêng. Dynamic dispatch quyết định implementation của phương thức instance được gọi ở từng bước.