# Vì sao interface không được định nghĩa default method thay thế phương thức Object?

Java cho interface cung cấp default method để bổ sung hành vi dùng chung. Tuy nhiên, một interface không được khai báo default method có chữ ký override-equivalent với **bất kỳ phương thức non-private nào của java.lang.Object**. Các trường hợp quen thuộc là toString(), equals(Object) và hashCode(); phạm vi quy tắc không chỉ giới hạn ở ba method public này.

## 1. Ví dụ không biên dịch

~~~java
interface BadDisplay {
    default String toString() {
        return "custom display";
    }
}
~~~

~~~java
interface BadIdentity {
    default boolean equals(Object other) {
        return true;
    }

    default int hashCode() {
        return 1;
    }
}
~~~

Cả hai khai báo đều không hợp lệ. Đổi thân hàm hoặc thêm @Override không sửa được lỗi. Quy tắc còn áp dụng cho chữ ký override-equivalent với các method non-private khác của Object, kể cả protected clone(). Một số method public như getClass(), wait() và notify() còn final nên class cụ thể cũng không được override chúng.

## 2. Vì sao có giới hạn này?

Mọi class Java đều kế thừa trực tiếp hoặc gián tiếp từ Object. Nếu interface có thể cung cấp default implementation thay thế những method nền tảng này, ý nghĩa của phương thức sẽ không rõ ràng: hành vi của class đến từ Object hoặc superclass vẫn có ưu tiên trong cơ chế phân giải method. Cấm khai báo giúp API không hứa một default implementation mà lớp không thể sử dụng như cách override thông thường.

Đặc biệt, equals và hashCode ảnh hưởng đến equality và collection dựa trên hashing. Chính sách của chúng cần khớp với dữ liệu và identity của lớp cụ thể. toString cũng thường phụ thuộc trạng thái hoặc mục đích chẩn đoán của từng lớp. Một default chung trong interface không thể an toàn áp đặt ngữ nghĩa đó cho mọi implementation.

## 3. Abstract declaration khác default implementation

Interface vẫn có thể khai báo một chữ ký abstract tương thích. Nó thể hiện hợp đồng nhưng không cung cấp thân hàm:

~~~java
interface NamedObject {
    String name();
    String toString();

    default String description() {
        return name() + " | " + toString();
    }
}

final class Product implements NamedObject {
    private final String name;

    Product(String name) {
        this.name = name;
    }

    @Override
    public String name() {
        return name;
    }

    @Override
    public String toString() {
        return "Product[" + name + "]";
    }
}
~~~

NamedObject.description() hợp lệ vì description là method mới, dù thân hàm gọi toString(). Product cung cấp implementation cụ thể cho toString(). Một lớp cũng có thể thừa hưởng Object.toString() nếu implementation đó đáp ứng chữ ký interface và ngữ nghĩa mặc định là đủ.

## 4. “Class wins” không cho phép default toString()

Quy tắc phương thức lớp được ưu tiên hơn default method áp dụng cho các xung đột hợp lệ. Nó không làm cho default toString() trở nên hợp lệ; khai báo đó bị từ chối trước khi phân giải implementation.

~~~java
interface Greeter {
    default String greet() {
        return "Interface";
    }
}

class BaseGreeter {
    public String greet() {
        return "Base class";
    }
}

final class ActualGreeter extends BaseGreeter implements Greeter {
}

public class Main {
    public static void main(String[] args) {
        Greeter greeter = new ActualGreeter();
        System.out.println(greeter.greet());
    }
}
~~~

Kết quả:

~~~text
Base class
~~~

Ví dụ dùng greet(), một method thông thường không bị giới hạn bởi quy tắc Object. Implementation của BaseGreeter được chọn. Không suy ra từ ví dụ này rằng Java cho phép khai báo default method trùng chữ ký toString(), equals(Object) hoặc hashCode().

## 5. Cách thiết kế đúng

- Nếu muốn chia sẻ hành vi mặc định, đặt tên method riêng như description(), displayLabel() hoặc describe().
- Nếu interface cần nêu rõ một chữ ký Object, có thể khai báo abstract tương thích nhưng không thêm default body.
- Nếu cần chính sách equals/hashCode/toString theo dữ liệu, triển khai hoặc override ở class cụ thể.
- Nếu cần API sao chép công khai, đừng cố dùng default clone(); khai báo một phương thức public có hợp đồng rõ ràng.

Tự kiểm tra:
- Có thể khai báo abstract String toString() trong interface không? Có, nếu chữ ký tương thích.
- Có thể khai báo default int hashCode() không? Không.
- Quy tắc chỉ áp dụng cho ba method public thường gặp không? Không; quy tắc bao quát method non-private của Object.
