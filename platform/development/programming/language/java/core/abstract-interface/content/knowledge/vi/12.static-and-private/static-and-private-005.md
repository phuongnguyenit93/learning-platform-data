# Chia sẻ mã giữa các default method bằng private instance method trong Java

## 1. Vì sao cần private method trong interface?

Từ Java 8, interface có thể định nghĩa **default method** có thân, cung cấp hành vi mặc định cho các lớp triển khai. Khi nhiều default method cần cùng một bước xử lý, sao chép logic vào từng phương thức làm mã lặp và dễ lệch nhau khi bảo trì.

Từ **Java 9**, interface có thể khai báo phương thức `private` để giữ phần triển khai dùng chung bên trong interface. **Private instance method** có thân, không có từ khóa `static`, và hoạt động trong ngữ cảnh đối tượng hiện tại. Nó cho phép các phương thức trong interface dùng chung logic mà không công khai helper thành một phần API.

Mẫu sử dụng:

1. Giữ các default method làm điểm gọi công khai.
2. Chuyển logic lặp lại vào private instance method.
3. Gọi helper đó từ từng default method với tham số phù hợp.
4. Giữ helper private để caller và lớp triển khai không phụ thuộc vào chi tiết nội bộ.

## 2. Ví dụ Java 17+: hai default method dùng chung helper

Lưu mã sau vào **PrivateInterfaceMethodDemo.java**:

~~~java
interface ReportFormatter {
    String serviceName();

    default String success(String user) {
        return format("SUCCESS", user);
    }

    default String failure(String user) {
        return format("FAILURE", user);
    }

    private String format(String status, String user) {
        return "[" + serviceName() + "] " + status + ": "
                + clean(user);
    }

    private String clean(String user) {
        if (user == null || user.isBlank()) {
            return "guest";
        }
        return user.trim();
    }
}

final class BillingFormatter implements ReportFormatter {
    @Override
    public String serviceName() {
        return "Billing";
    }
}

public class PrivateInterfaceMethodDemo {
    public static void main(String[] args) {
        ReportFormatter formatter = new BillingFormatter();
        System.out.println(formatter.success(" Mia "));
        System.out.println(formatter.failure(" "));
        System.out.println(formatter.success(null));
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~bash
javac PrivateInterfaceMethodDemo.java
java PrivateInterfaceMethodDemo
~~~

Đầu ra chính xác:

~~~text
[Billing] SUCCESS: Mia
[Billing] FAILURE: guest
[Billing] SUCCESS: guest
~~~

`success()` và `failure()` là default method có thể gọi qua biến kiểu `ReportFormatter`. Cả hai dùng `format()`, còn `format()` gọi `clean()` để xử lý tên. Nhờ đó, cách ghép thông báo chỉ được định nghĩa một lần.

Helper `format()` gọi `serviceName()` trên đối tượng hiện tại. Lời gọi được điều phối đến `BillingFormatter.serviceName()`, nên kết quả chứa `[Billing]`. Đây là lý do ví dụ dùng private **instance** method: helper dựa vào hành vi của đối tượng thực tế. `clean()` biến `null`, chuỗi rỗng hoặc chuỗi chỉ có khoảng trắng thành `guest`; các tên khác được loại khoảng trắng đầu/cuối.

## 3. Khác biệt giữa default method và private instance method

| Đặc điểm | Default method | Private instance method |
| --- | --- | --- |
| Có thân phương thức | Có | Có |
| Gọi qua biến kiểu interface từ caller | Có | Không |
| Lớp triển khai kế thừa để gọi trực tiếp | Có, trừ khi bị ghi đè hoặc có xung đột | Không |
| Lớp triển khai override như một phương thức được kế thừa | Có | Không; helper private không được kế thừa |
| Mục đích | Hành vi mặc định trong API | Chia sẻ chi tiết triển khai nội bộ |

Caller có thể gọi `formatter.success("Mia")` nhưng không thể gọi `formatter.format("SUCCESS", "Mia")` vì `format()` là private. Lớp triển khai cũng không thể gọi helper qua `this` hay qua biến kiểu interface.

Nếu lớp triển khai tự khai báo phương thức cùng tên `format`, đó không phải override helper private của interface: hai phương thức không có quan hệ kế thừa. Lời gọi từ default method vẫn dùng helper trong interface. Private method phải có thân; không khai báo nó như phương thức trừu tượng và không kết hợp `private` với `default` trong cùng một khai báo.

## 4. Khi nào nên dùng private instance method?

Dùng nó khi nhiều default method cần cùng logic, phần logic là chi tiết triển khai và nó cần ngữ cảnh của đối tượng hiện tại. Private instance method có thể gọi phương thức instance khác trong interface, kể cả phương thức trừu tượng như `serviceName()`. Lời gọi đến phương thức trừu tượng sẽ được điều phối theo đối tượng thực tế.

Nếu hành vi phải được cung cấp bởi mọi lớp triển khai, hãy khai báo một phương thức hợp đồng công khai thay vì giấu hành vi đó trong helper private. Nếu logic chỉ được dùng một lần và việc tách helper làm luồng xử lý khó đọc hơn, không cần tạo thêm phương thức chỉ để tách một dòng mã.

## 5. Ranh giới sử dụng

**Private instance method** phù hợp khi helper cần ngữ cảnh đối tượng, như lời gọi `serviceName()` trong ví dụ. Nếu xử lý chỉ dựa trên tham số, một `private static` helper có thể đơn giản hơn; helper static không có `this` và chỉ gọi được hành vi instance khi có receiver cụ thể. Cả hai loại helper trong interface đều yêu cầu **Java 9 trở lên**.

Không nên tạo helper nếu việc tách hàm khiến luồng xử lý một lần dùng khó đọc hơn. Nếu nhiều interface **không liên quan** cùng cần một thuật toán, private helper của interface này không được interface khác gọi; hãy cân nhắc utility class hoặc thành phần dùng chung.

**Tự kiểm tra:** Vì sao `format()` cần là private *instance* method? Vì nó gọi `serviceName()` theo đối tượng `BillingFormatter` thực tế; một private static helper không có sẵn đối tượng đó.
