# Truy cập hằng qua tên interface và xử lý tên hằng trùng nhau

## 1. Ghi rõ kiểu sở hữu hằng

Field của interface là public static final, vì vậy có thể đọc trực tiếp qua tên interface mà không cần tạo đối tượng hoặc implements interface đó.

~~~java
interface Pagination {
    int DEFAULT_SIZE = 20;
    int MAX_SIZE = 100;
}

public class ConstantAccessDemo {
    public static void main(String[] args) {
        System.out.println(Pagination.DEFAULT_SIZE);
        System.out.println(Pagination.MAX_SIZE);
    }
}
~~~

Kết quả:

~~~text
20
100
~~~

Viết Pagination.DEFAULT_SIZE cho người đọc biết rõ nguồn khai báo. Trong class implements interface, tên đơn có thể hoạt động nếu không có xung đột, nhưng nó khiến người đọc phải dò toàn bộ các interface và field cùng tên. Ưu tiên qualifier để mã dễ bảo trì.

## 2. Hai interface có hằng cùng tên

~~~java
interface HttpSettings {
    int TIMEOUT_SECONDS = 5;
}

interface DatabaseSettings {
    int TIMEOUT_SECONDS = 30;
}

final class ConnectionMonitor implements HttpSettings, DatabaseSettings {
    void showTimeouts() {
        System.out.println(HttpSettings.TIMEOUT_SECONDS);
        System.out.println(DatabaseSettings.TIMEOUT_SECONDS);
    }
}

public class NameCollisionDemo {
    public static void main(String[] args) {
        new ConnectionMonitor().showTimeouts();
    }
}
~~~

Kết quả:

~~~text
5
30
~~~

Trong ConnectionMonitor, tên đơn TIMEOUT_SECONDS không chỉ ra muốn lấy trường nào và có thể gây lỗi ambiguous reference. Java không tự chọn interface đứng trước trong danh sách implements, kể cả khi hai field trùng tên có cùng giá trị. Ghi rõ HttpSettings.TIMEOUT_SECONDS hoặc DatabaseSettings.TIMEOUT_SECONDS sẽ giải quyết xung đột.

## 3. Field hiding không phải overriding

Field không tham gia đa hình ghi đè như phương thức instance. Nếu class khai báo field cùng tên, field của class che khuất tên kế thừa trong phạm vi phù hợp:

~~~java
interface DefaultLimits {
    int LIMIT = 10;
}

final class LimitedService implements DefaultLimits {
    static final int LIMIT = 25;

    void printLimits() {
        System.out.println(LIMIT);
        System.out.println(LimitedService.LIMIT);
        System.out.println(DefaultLimits.LIMIT);
    }
}
~~~

Hai giá trị vẫn tồn tại: LimitedService.LIMIT là 25, còn DefaultLimits.LIMIT là 10. Việc chọn field được giải quyết theo tên và kiểu khai báo, không theo đối tượng thực như lời gọi phương thức instance.

Interface con cũng có thể khai báo field trùng tên với field được kế thừa; field con che khuất tên, nhưng field cha vẫn có thể truy cập qua tên interface cha.

## 4. Xung đột với static import

Static import giúp dùng tên thành viên static mà không ghi tên kiểu. Nhưng nó không loại bỏ xung đột tên.

~~~java
import static java.lang.Integer.*;
import static java.lang.Long.*;

public class StaticImportCollisionDemo {
    public static void main(String[] args) {
        // MAX_VALUE một mình sẽ nhập nhằng giữa Integer và Long.
        System.out.println(Integer.MAX_VALUE);
        System.out.println(Long.MAX_VALUE);
    }
}
~~~

Kết quả:

~~~text
2147483647
9223372036854775807
~~~

Với tên phổ biến như MAX_VALUE, LIMIT, STATUS hoặc TIMEOUT, dùng OwnerType.CONSTANT giúp tránh phải suy luận từ danh sách import. Xung đột có thể đến từ interface mà class implements, interface cha, field của chính class hoặc static import.

## 5. Quy tắc thực tế

- Đọc hằng qua tên interface định nghĩa nó.
- Khi nhiều interface có cùng tên field, ghi qualifier rõ ràng.
- Nếu class khai báo field cùng tên, phân biệt field của class với field của interface; đó là hiding.
- Đừng implements interface chỉ để lấy tên hằng ngắn. Quan hệ implements nên thể hiện hợp đồng kiểu/hành vi.
- Trường mutable được công khai từ interface vẫn có thể bị thay đổi qua tham chiếu; xem bài về final và immutability.
- Giá trị compile-time constant có thể được nhúng vào client đã biên dịch; thay đổi giá trị hằng có thể cần biên dịch lại client.

### Tự kiểm tra

1. Có cần tạo đối tượng để đọc Pagination.DEFAULT_SIZE không? **Không**.
2. Hai interface không liên quan cùng khai báo TIMEOUT_SECONDS; tên đơn có tự chọn interface đầu tiên không? **Không**.
3. Field của class trùng tên field interface có override đa hình không? **Không**, đó là hiding.
4. Static import có làm hai hằng MAX_VALUE trở thành một field không? **Không**, qualifier kiểu giúp chọn nguồn.

Điểm chính là xác định rõ field thuộc kiểu nào. Tên đủ nghĩa tránh nhập nhằng và giữ ý định thiết kế ổn định khi class hoặc interface mở rộng.