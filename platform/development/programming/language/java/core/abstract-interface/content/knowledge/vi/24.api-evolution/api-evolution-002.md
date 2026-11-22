# Mốc Java 9 cho private method trong interface

Java 9 bổ sung **private method trong interface** để tác giả interface có thể chia sẻ logic nội bộ giữa nhiều phương thức mà không làm lộ các hàm trợ giúp đó thành một phần API công khai. Tính năng này đặc biệt hữu ích khi interface có nhiều phương thức default hoặc static cần thực hiện cùng một bước chuẩn hóa, kiểm tra hay định dạng.

Điểm cần nhớ: **private method trong interface là chi tiết triển khai của chính interface**. Lớp triển khai không thể gọi nó trực tiếp, không kế thừa nó và không ghi đè nó theo cơ chế đa hình.

## 1. Vì sao Java cần private method trong interface?

Java 8 cho phép interface khai báo phương thức **default** có phần thân và phương thức **static** có phần thân. Nhờ vậy, một interface có thể bổ sung hành vi dùng chung mà không buộc mọi lớp triển khai phải viết lại phương thức đó.

Tuy nhiên, khi nhiều phương thức default phải dùng chung một đoạn xử lý, trước Java 9 tác giả thường phải chọn giữa việc lặp lại mã hoặc đưa helper thành một phương thức public trong interface. Phương thức public có thể trở thành một phần hợp đồng mà người dùng interface nhìn thấy và có thể gọi, dù nó chỉ được tạo ra để phục vụ nội bộ.

Java 9 cho phép khai báo phương thức private bên trong interface để giải quyết việc này:

- Phương thức private instance có thể được gọi từ các phương thức instance khác trong cùng interface, chẳng hạn các phương thức default.
- Phương thức private static có thể được gọi từ các phương thức static hoặc những đoạn mã khác bên trong cùng interface phù hợp với quy tắc static.
- Helper được giữ ở phạm vi nội bộ, nên mã gọi interface không thể dựa vào helper như một API công khai.

## 2. Mốc phiên bản và các dạng phương thức

| Tính năng | Phiên bản Java |
|---|---|
| Phương thức abstract trong interface | Có từ các phiên bản Java đầu tiên |
| Phương thức default có phần thân | Java 8 |
| Phương thức static trong interface | Java 8 |
| Phương thức private trong interface | Java 9 |
| Phương thức private static trong interface | Java 9 |

Một interface Java 9+ có thể khai báo các dạng phương thức sau:

- **Abstract method:** không có phần thân; lớp cụ thể triển khai hợp đồng này.
- **Default method:** có phần thân và được kế thừa bởi lớp triển khai nếu không có quy tắc ghi đè khác áp dụng.
- **Public static method:** thuộc interface, được gọi qua tên interface; không phải phương thức instance của đối tượng.
- **Private instance method:** helper có phần thân, dùng bên trong interface bởi các phương thức instance thích hợp.
- **Private static method:** helper static có phần thân, dùng bên trong interface bởi các phương thức nội bộ thích hợp.

Trong interface, phương thức không ghi rõ access modifier thường là public. Phương thức default và static thông thường của interface cũng là public ngầm định. Từ Java 9, từ khóa private cho phép giới hạn helper trong interface.

## 3. Ví dụ chạy được với Java 9 trở lên

Ví dụ dưới đây có hai phương thức default dùng chung các helper instance private để chuẩn hóa tên và bọc thông điệp. Phương thức static công khai dùng một helper private static để chuẩn hóa mã.

Lưu mã sau vào tệp **PrivateInterfaceMethodsDemo.java**:

~~~java
import java.util.Locale;

interface MessageFormatter {
    default String greeting(String name) {
        return decorate("Hello, " + normalizeName(name) + "!");
    }

    default String farewell(String name) {
        return decorate("Goodbye, " + normalizeName(name) + "!");
    }

    static String formatCode(String code) {
        return "CODE-" + normalizeCode(code);
    }

    private String normalizeName(String name) {
        if (name == null || name.trim().isEmpty()) {
            return "guest";
        }
        return name.trim();
    }

    private String decorate(String message) {
        return "[" + message + "]";
    }

    private static String normalizeCode(String code) {
        if (code == null) {
            throw new IllegalArgumentException("code must not be null");
        }
        return code.trim().toUpperCase(Locale.ROOT);
    }
}

public class PrivateInterfaceMethodsDemo implements MessageFormatter {
    public static void main(String[] args) {
        PrivateInterfaceMethodsDemo demo = new PrivateInterfaceMethodsDemo();

        System.out.println(demo.greeting("Linh"));
        System.out.println(demo.farewell("Linh"));
        System.out.println(demo.greeting("  "));
        System.out.println(MessageFormatter.formatCode(" ab-7 "));
    }
}
~~~

Biên dịch và chạy bằng JDK 9 trở lên:

~~~bash
javac PrivateInterfaceMethodsDemo.java
java PrivateInterfaceMethodsDemo
~~~

Stdout chính xác:

~~~text
[Hello, Linh!]
[Goodbye, Linh!]
[Hello, guest!]
CODE-AB-7
~~~

Cả hai phương thức default gọi normalizeName và decorate, nhưng các helper đó không xuất hiện như phương thức công khai của MessageFormatter. Phương thức static formatCode gọi normalizeCode để dùng chung logic chuẩn hóa. Lớp PrivateInterfaceMethodsDemo chỉ sử dụng các phương thức public mà interface cung cấp.

Ví dụ dùng trim và isEmpty để có thể chạy từ Java 9. Nếu dự án đặt mức biên dịch thấp hơn Java 9, trình biên dịch sẽ từ chối cú pháp private method trong interface. JDK 17 cũng có thể biên dịch và chạy ví dụ này.

## 4. Quy tắc truy cập cần nắm

**Phương thức private phải có phần thân.** Một phương thức private không thể đồng thời là phương thức abstract, vì abstract yêu cầu lớp triển khai cung cấp phần thân còn private giữ helper ở nội bộ interface.

**Phương thức private không phải default method.** Không khai báo một phương thức vừa private vừa default. Default method là hành vi instance được công bố cho lớp triển khai và người gọi; private instance method chỉ là helper nội bộ.

**Lớp triển khai không gọi được helper private.** Mã bên ngoài không thể gọi helper qua đối tượng hoặc qua tên interface. Chỉ các phương thức thích hợp bên trong interface mới có thể sử dụng chúng.

**Phương thức private không được kế thừa hay ghi đè.** Nếu một lớp triển khai khai báo một phương thức cùng tên với helper private của interface, phương thức đó là thành viên riêng của lớp triển khai; nó không ghi đè helper private của interface.

**Phân biệt instance và static.** Helper instance có thể làm việc với lời gọi instance trong interface. Helper static không có ngữ cảnh đối tượng và không thể truy cập trực tiếp thành viên instance nếu không có một đối tượng phù hợp. Giữ helper static cho logic chỉ phụ thuộc vào tham số và dữ liệu static.

**Private static cũng chỉ dùng nội bộ.** Dù helper static không cần đối tượng, nó vẫn không trở thành một API gọi được từ lớp triển khai. Từ khóa static không làm mất giới hạn truy cập của private.

## 5. Những lỗi thường gặp

- **Dùng Java 8 để biên dịch mã có private method trong interface.** Tính năng cần Java 9 trở lên; hãy kiểm tra JDK và tùy chọn source/release của dự án.
- **Gọi helper private từ lớp triển khai.** Helper này chỉ dùng trong interface. Nếu hành vi thực sự cần được gọi từ bên ngoài, hãy thiết kế một phương thức public phù hợp với hợp đồng thay vì cố truy cập helper.
- **Đưa mọi logic vào phương thức public chỉ để tái sử dụng.** Việc đó làm API lớn hơn và khiến người dùng phụ thuộc vào chi tiết vốn chỉ nhằm hỗ trợ triển khai. Dùng private method khi logic chỉ cần dùng bên trong interface.
- **Lặp lại cùng một logic trong nhiều default method.** Nếu các phương thức cần cùng một bước xử lý, hãy cân nhắc tách helper private để tránh sai khác khi sửa đổi.
- **Gọi thành viên instance từ helper static như thể có sẵn đối tượng.** Phương thức static không có this. Hãy truyền dữ liệu cần thiết qua tham số hoặc dùng helper instance khi logic phụ thuộc vào ngữ cảnh instance.
- **Nhầm private method với phương thức mặc định.** Default method tạo hành vi công khai mà lớp triển khai có thể thừa hưởng; private method là cơ chế tổ chức mã bên trong interface.

## 6. Khi nào nên sử dụng?

Dùng private method trong interface khi một hoặc nhiều phương thức default cần chia sẻ quy trình nhỏ như chuẩn hóa dữ liệu đầu vào, tạo thông điệp, kiểm tra điều kiện hoặc ghép các bước xử lý. Dùng private static khi helper không cần trạng thái instance và được gọi từ các phương thức static hoặc logic nội bộ phù hợp.

Nếu helper cần được gọi từ lớp triển khai, từ một service độc lập hoặc từ nhiều kiểu không liên quan, cân nhắc chuyển nó thành phương thức của một lớp trợ giúp hay thành một API public được thiết kế có chủ đích. Không nên dùng private method trong interface chỉ vì có thể; nó phù hợp nhất khi hành vi thực sự thuộc về phần triển khai của interface.

Tính năng Java 9 này giúp interface duy trì API gọn hơn trong khi vẫn cho phép tác giả tổ chức mã dùng chung rõ ràng. Khi đọc code, hãy phân biệt phương thức public/default mà người dùng có thể gọi với helper private chỉ phục vụ bên trong interface.
