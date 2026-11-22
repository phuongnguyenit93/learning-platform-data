# Tái sử dụng logic trong phạm vi interface bằng private methods

Từ Java 9, interface có thể khai báo phương thức `private` và `private static`. Các phương thức này cho phép nhiều phương thức trong cùng interface dùng chung một phần xử lý mà không làm lộ hàm trợ giúp ra API công khai.

Cơ chế này vẫn được hỗ trợ trong các phiên bản Java hiện đại. Special Note của module yêu cầu chỉ dùng kiến thức còn áp dụng hiện nay; private interface methods đáp ứng yêu cầu đó. Chúng đặc biệt hữu ích khi một interface có nhiều `default` method hoặc `static` method cần cùng chuẩn hóa dữ liệu, kiểm tra điều kiện hoặc tạo thông báo.

## 1. Vì sao cần phương thức private trong interface?

Interface có thể chứa các phương thức có phần thân, chẳng hạn:

- **Abstract method:** khai báo hành vi mà lớp triển khai phải cung cấp.
- **Default method:** phương thức instance có phần thân, được lớp triển khai kế thừa nếu không ghi đè.
- **Static method:** phương thức thuộc về chính interface, được gọi qua tên interface.

Khi nhiều phương thức có phần thân cần dùng chung một đoạn logic, nếu lặp lại đoạn mã đó ở từng phương thức thì việc sửa đổi và kiểm thử sẽ khó hơn. Nếu biến đoạn logic thành một phương thức public, nó lại trở thành một phần của API mà lớp triển khai và người gọi có thể nhìn thấy.

Private method giải quyết đúng phạm vi này: giữ logic dùng chung bên trong interface, để các phương thức public của interface gọi lại khi cần.

Ví dụ, hai default method có thể cùng dùng một hàm chuẩn hóa tên. Một static method khác có thể dùng các private static helper để chuẩn hóa và kiểm tra mã tiền tệ.

## 2. Hai dạng private method

Java 9 bổ sung hai dạng:

### Private instance method

```java
private String normalize(String value) {
    return value.trim();
}
```

Phương thức này thuộc ngữ cảnh instance của interface. Nó có thể được gọi từ các default method hoặc private instance method khác trong cùng interface. Nó không thể được gọi trực tiếp từ một static method vì static method không có instance để gọi hàm đó.

### Private static method

```java
private static String normalizeCode(String value) {
    return value.trim().toUpperCase(Locale.ROOT);
}
```

Phương thức này thuộc về interface, không cần đối tượng. Nó có thể được gọi từ static method, default method hoặc private method khác trong cùng interface.

| Dạng | Cách khai báo | Ngữ cảnh gọi thường dùng |
|---|---|---|
| Private instance | `private ReturnType helper(...)` | Default method và private instance method |
| Private static | `private static ReturnType helper(...)` | Static method, default method và private method |

Cả hai dạng đều phải có phần thân. Private method trong interface không phải phương thức abstract.

## 3. Ví dụ hoàn chỉnh: nhiều phương thức dùng chung logic

Tạo tệp `InterfaceLogicReuseDemo.java`:

```java
import java.util.Locale;

interface OrderText {
    default String displayName(String input) {
        return normalizeRequired(input, "name");
    }

    default String displayCode(String input) {
        return normalizeRequired(input, "code")
                .toUpperCase(Locale.ROOT);
    }

    static boolean supportsCurrency(String input) {
        return isSupportedCurrency(normalizeCurrency(input));
    }

    // Dùng chung bởi các default method.
    private String normalizeRequired(String value, String field) {
        if (value == null || value.trim().isEmpty()) {
            throw new IllegalArgumentException(
                    field + " must not be blank");
        }

        return value.trim().replaceAll("\\s+", " ");
    }

    // Dùng chung trong nhóm xử lý static.
    private static String normalizeCurrency(String value) {
        return value == null
                ? ""
                : value.trim().toUpperCase(Locale.ROOT);
    }

    private static boolean isSupportedCurrency(String value) {
        return value.equals("VND")
                || value.equals("USD")
                || value.equals("EUR");
    }
}

class PurchaseOrder implements OrderText {
}

public class InterfaceLogicReuseDemo {
    public static void main(String[] args) {
        PurchaseOrder order = new PurchaseOrder();

        System.out.println(
                order.displayName("  Nguyen   An  "));
        System.out.println(
                order.displayCode(" po-2026 "));
        System.out.println(
                OrderText.supportsCurrency(" vnd "));
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac InterfaceLogicReuseDemo.java
java InterfaceLogicReuseDemo
```

Kết quả:

```text
Nguyen An
PO-2026
true
```

Trong ví dụ:

1. `displayName()` và `displayCode()` là hai default method công khai, cùng gọi private instance method `normalizeRequired()`.
2. `supportsCurrency()` là static method công khai, gọi hai private static helper để chuẩn hóa và kiểm tra mã tiền tệ.
3. `PurchaseOrder` chỉ cần triển khai interface. Nó được kế thừa hai default method, nhưng không nhìn thấy và không thể gọi trực tiếp các private helper.
4. Người dùng API gọi `order.displayName(...)` hoặc `OrderText.supportsCurrency(...)`; chi tiết chuẩn hóa được giữ bên trong interface.

Ví dụ sử dụng `String.trim().isEmpty()` và `String.trim()`, là các API có từ Java 11. Cú pháp private interface method được giới thiệu từ Java 9 và vẫn hoạt động trong JDK hiện đại.

## 4. Quy tắc truy cập và giới hạn

Private method trong interface có một số quy tắc quan trọng:

- Chỉ mã bên trong chính interface khai báo nó mới có thể gọi private method đó.
- Lớp triển khai không kế thừa private method và không thể ghi đè nó.
- Private method không phải thành viên public của API; người gọi qua đối tượng hoặc tên interface không thể truy cập nó.
- Private instance method phải được gọi trong ngữ cảnh instance, ví dụ từ default method.
- Private static method không truy cập trực tiếp trạng thái instance; nó phù hợp với logic không phụ thuộc đối tượng.
- Private method phải có phần thân. Không khai báo private abstract method.
- Không kết hợp `private` với `default`; default method là phương thức instance công khai.
- Interface không dùng `protected` hoặc phạm vi package-private cho phương thức trợ giúp. Khi cần đóng gói logic nội bộ trong interface, dùng `private`.

Các phương thức `default` vẫn là phương thức instance công khai. Lớp triển khai có thể ghi đè chúng theo nhu cầu. Static method thuộc interface được gọi bằng tên interface, ví dụ `OrderText.supportsCurrency(...)`; static method của interface không trở thành static method kế thừa của lớp triển khai.

## 5. Khi nào nên dùng private method?

Dùng private method khi đoạn logic:

- Được nhiều default method trong cùng interface dùng chung.
- Được nhiều static method trong cùng interface dùng chung.
- Là bước kiểm tra hoặc chuẩn hóa nội bộ, không nên trở thành hợp đồng công khai.
- Giúp các phương thức public ngắn hơn và thể hiện rõ ý định.

Ví dụ, một interface xử lý thông báo có thể có nhiều default method như gửi thông báo thành công, gửi cảnh báo hoặc gửi thông báo thất bại. Các phương thức đó có thể dùng chung một private helper để chuẩn hóa nội dung. Một interface quản lý mã định danh có thể dùng private static helper để chuẩn hóa mã trước khi nhiều static method kiểm tra định dạng.

Không nên đưa mọi logic vào private method chỉ để chia nhỏ mã. Nếu logic chỉ được dùng một lần và việc tách riêng làm luồng xử lý khó hiểu hơn, giữ nó ở phương thức chính có thể rõ ràng hơn.

## 6. Khi nào nên đặt logic bên ngoài interface?

Private method chỉ tái sử dụng logic **trong cùng một interface**. Nếu nhiều interface hoặc nhiều lớp độc lập cần dùng chung cùng một quy tắc nghiệp vụ, hãy cân nhắc:

- Một class tiện ích có trách nhiệm rõ ràng.
- Một service được inject vào các thành phần cần dùng.
- Composition để ghép hành vi thay vì phụ thuộc vào một interface lớn.

Không nên dùng private interface method làm nơi chứa một hệ thống xử lý phức tạp hoặc logic cần được nhiều thành phần ngoài interface truy cập. Giới hạn phạm vi đúng giúp API ổn định và dễ hiểu.

## 7. Quan hệ với default method và xung đột kế thừa

Private method không giải quyết xung đột giữa các default method. Nếu một lớp triển khai hai interface có default method trùng chữ ký, lớp đó vẫn phải giải quyết xung đột bằng cách ghi đè phương thức tương ứng.

```java
interface Printable {
    default void print() {
        System.out.println("Printable");
    }
}

interface Loggable {
    default void print() {
        System.out.println("Loggable");
    }
}

class Report implements Printable, Loggable {
    @Override
    public void print() {
        Printable.super.print();
        Loggable.super.print();
    }
}
```

Private helper chỉ hỗ trợ tổ chức mã bên trong từng interface. Nó không làm thay đổi quy tắc phân giải default method của Java.

## 8. Lỗi thường gặp

- **Gọi private method từ lớp triển khai:** không hợp lệ vì phương thức không được kế thừa và chỉ có phạm vi trong interface khai báo.
- **Gọi private instance method từ static method:** không hợp lệ vì static method không có instance. Nếu logic không cần trạng thái instance, chuyển helper thành private static.
- **Đánh dấu helper là default:** default method là API instance công khai; dùng `private` cho helper nội bộ.
- **Khai báo private method không có phần thân:** private method trong interface phải có phần triển khai.
- **Đưa logic dùng chung giữa nhiều interface vào một private helper:** private helper không thể được interface khác gọi. Chuyển logic dùng chung ra class hoặc service phù hợp.
- **Nhầm private helper với phương thức triển khai bắt buộc:** lớp triển khai chỉ phải cung cấp các abstract method; private helper là chi tiết nội bộ của interface.

## 9. Checklist thiết kế

Trước khi thêm một private method vào interface, hãy kiểm tra:

1. Logic có thật sự được dùng chung bởi ít nhất hai phương thức trong cùng interface không?
2. Logic có phải chi tiết nội bộ, không cần xuất hiện trong public API không?
3. Nên dùng private instance hay private static dựa trên việc logic có cần ngữ cảnh instance không?
4. Tên helper có diễn tả đúng một trách nhiệm nhỏ và rõ ràng không?
5. Có nên chuyển logic sang class/service vì nó cần được chia sẻ ngoài interface không?
6. Các default method công khai có còn dễ hiểu và có hợp đồng ổn định không?

Private interface method là công cụ tổ chức mã được bổ sung từ Java 9 và vẫn phù hợp với thiết kế interface hiện nay. Dùng private instance method cho logic cần ngữ cảnh instance, private static method cho logic độc lập với instance, và giữ các helper ở đúng interface giúp tái sử dụng nội bộ mà không mở rộng API công khai.
