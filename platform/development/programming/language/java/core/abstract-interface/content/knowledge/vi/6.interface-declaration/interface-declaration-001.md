# Cú pháp, tên và mục đích của interface trong Java

## 1. Interface mô tả hợp đồng hành vi

Một `interface` là kiểu Java công bố những thao tác mà một đối tượng có thể cung cấp. Nó giúp mã gọi làm việc với **khả năng** của đối tượng mà không phải phụ thuộc vào một lớp cụ thể. Ví dụ, hệ thống thanh toán chỉ cần biết cách gọi `pay`; tiền mặt, thẻ hoặc chuyển khoản có thể triển khai hành vi đó theo cách riêng.

```java
interface PaymentMethod {
    String pay(int amount);
}

final class CashPayment implements PaymentMethod {
    @Override
    public String pay(int amount) {
        return "Cash: " + amount;
    }
}

public class Main {
    public static void main(String[] args) {
        PaymentMethod payment = new CashPayment();
        System.out.println(payment.pay(150));
    }
}
```

Lưu thành `Main.java`, biên dịch và chạy bằng JDK 17+:

```bash
javac Main.java
java Main
```

Kết quả:

```text
Cash: 150
```

Biến `payment` có kiểu khai báo `PaymentMethod`, còn đối tượng thực tế là `CashPayment`. Khi gọi `pay`, Java thực thi phần cài đặt của đối tượng đó. Hợp đồng kiểu được trình biên dịch kiểm tra; ý nghĩa nghiệp vụ như “thanh toán thành công” vẫn cần được cài đặt và kiểm thử.

## 2. Cú pháp và cách đặt tên

Cú pháp cơ bản:

```java
public interface PaymentMethod {
    String pay(int amount);
}
```

- `interface` là từ khóa khai báo kiểu.
- `PaymentMethod` là tên kiểu; quy ước Java dùng **PascalCase** cho tên class và interface.
- `String pay(int amount);` là phương thức được công bố. Dấu chấm phẩy cho biết đây là khai báo không có thân phương thức.
- `public` cho phép mã ở package khác tham chiếu kiểu khi các điều kiện truy cập liên quan được đáp ứng. Nếu bỏ modifier trên interface cấp cao nhất, kiểu trở thành package-private; bài về truy cập sẽ giải thích kỹ hơn.

Tên interface nên thể hiện vai trò hoặc khả năng, chẳng hạn `Runnable`, `Comparable<T>`, `Closeable`, `MessageSender` hoặc `PriceCalculator`. Tránh tên mơ hồ như `CommonInterface` nếu không cho biết hợp đồng gì được cung cấp. Tên phương thức thường là động từ hoặc cụm mô tả hành vi; hằng số thường viết `UPPER_SNAKE_CASE`.

## 3. Interface giúp ích khi nào?

Interface hữu ích khi:

1. Nhiều lớp cung cấp cùng một khả năng nhưng có cách thực hiện khác nhau.
2. Thành phần sử dụng nên phụ thuộc vào hợp đồng ổn định thay vì tự tạo một implementation cụ thể.
3. Cần thay implementation trong kiểm thử, ví dụ truyền một sender giả để xác minh thông điệp được gửi.
4. Một lớp cần đảm nhiệm nhiều vai trò độc lập, như vừa có thể in vừa có thể lưu.

Không cần tạo interface cho mọi class. Nếu chưa có ranh giới thay thế hoặc hợp đồng có ích, interface trung gian chỉ làm tăng số kiểu và tệp phải quản lý.

## 4. Phân biệt nhanh với class và abstract class

| Cơ chế | Trọng tâm | Constructor và trạng thái instance | Quan hệ kế thừa |
| --- | --- | --- | --- |
| Class cụ thể | Cung cấp implementation và tạo đối tượng | Có thể có | Một superclass trực tiếp |
| Abstract class | Chia sẻ implementation hoặc trạng thái cho các lớp con | Có thể có constructor và field instance | Một superclass trực tiếp |
| Interface | Công bố hợp đồng và kiểu đa hình | Không có constructor hoặc field instance | Một class có thể triển khai nhiều interface |

Interface hiện đại còn có thể chứa phương thức `default`, `static` và `private`, nên không phải mọi phương thức đều trừu tượng. Các bài tiếp theo phân tích kiểu tham chiếu, quyền truy cập, `extends`, `implements`, giới hạn trạng thái, kiểu thành viên và annotation interface.

## 5. Lỗi thường gặp

- Dùng `new PaymentMethod()`: interface không thể được khởi tạo trực tiếp; hãy tạo một implementation.
- Đổi chữ ký ở class, ví dụ `pay(String)` thay cho `pay(int)`: đây không phải implementation của phương thức đã khai báo.
- Giảm quyền truy cập khi triển khai phương thức public của interface: implementation phải giữ mức truy cập `public`.
- Tạo interface chỉ để phản chiếu một class mà không có nhu cầu về hợp đồng hay thay thế: cân nhắc xem abstraction đó có giúp thiết kế rõ hơn không.

**Tự kiểm tra:** Nếu `CardPayment` và `CashPayment` cùng triển khai `PaymentMethod`, thành phần nhận tham số kiểu `PaymentMethod` có cần biết tên hai class đó không? Không; nó chỉ cần gọi các thao tác được công bố bởi hợp đồng.