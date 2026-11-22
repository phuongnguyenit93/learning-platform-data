# Phân biệt final với tính bất biến của đối tượng trong Java

## 1. Hai câu hỏi khác nhau

**final** trên biến hoặc field giới hạn việc gán lại biến. **Immutability** mô tả việc trạng thái có thể quan sát của đối tượng có thay đổi sau khi tạo hay không. Một thuộc tính không tự suy ra thuộc tính kia.

~~~java
final int count = 3;
// count = 4;                 // Lỗi: không thể gán lại count

final StringBuilder text = new StringBuilder("Java");
text.append(" 17");           // Hợp lệ: sửa đối tượng được tham chiếu
// text = new StringBuilder(); // Lỗi: không thể đổi tham chiếu
~~~

Với primitive, final cố định giá trị sau khi khởi tạo. Với kiểu tham chiếu, final cố định tham chiếu; API của đối tượng đích vẫn có thể cho phép sửa trạng thái.

String và Integer là các kiểu bất biến. StringBuilder, mảng và ArrayList có trạng thái thay đổi được. Một final class chỉ ngăn kế thừa, và một record chỉ cố định việc gán lại component field theo cấu trúc của record; cả hai không tự làm các đối tượng con bất biến sâu.

## 2. Vì sao điều này quan trọng với field interface?

Field khai báo trong interface là public static final. Nếu field trỏ tới một đối tượng mutable, mã bên ngoài vẫn có thể thay đổi đối tượng đó qua tham chiếu công khai.

~~~java
interface SharedSettings {
    int TIMEOUT_SECONDS = 5;
    int[] PORTS = {8080, 8081};
}
~~~

Không thể gán SharedSettings.PORTS sang mảng mới, nhưng phép gán SharedSettings.PORTS[0] = 9090 hợp lệ. Tất cả nơi đọc field đều nhìn thấy thay đổi trên cùng mảng. Tránh công khai mảng hoặc collection mutable nếu bạn muốn dữ liệu cấu hình ổn định.

## 3. Bất biến cần kiểm soát các tham chiếu thoát ra ngoài

~~~java
import java.util.List;

final class UnsafeProfile {
    private final List<String> roles;

    UnsafeProfile(List<String> roles) {
        this.roles = roles;
    }

    List<String> roles() {
        return roles;
    }
}
~~~

Lớp này không bất biến: bên gọi có thể giữ danh sách đầu vào rồi sửa nó sau khi tạo profile; đồng thời getter trả thẳng danh sách nội bộ cho phép sửa từ bên ngoài. Hai vấn đề thường được gọi là aliasing ở đầu vào và representation exposure ở đầu ra.

Muốn trạng thái ổn định, hãy kiểm soát cả dữ liệu đi vào lẫn dữ liệu được trả ra.

## 4. Sao chép phòng vệ với List.copyOf

Lưu mã sau vào **ProfileDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.List;

final class Profile {
    private final String username;
    private final List<String> roles;

    Profile(String username, List<String> roles) {
        this.username = username;
        this.roles = List.copyOf(roles);
    }

    String username() {
        return username;
    }

    List<String> roles() {
        return roles;
    }
}

public class ProfileDemo {
    public static void main(String[] args) {
        List<String> input = new ArrayList<>(List.of("READER"));
        Profile profile = new Profile("mai", input);
        input.add("ADMIN");

        System.out.println(profile.username());
        System.out.println(profile.roles());
        System.out.println(input);
    }
}
~~~

Chạy với JDK 17+:

~~~bash
javac --release 17 ProfileDemo.java
java ProfileDemo
~~~

Kết quả:

~~~text
mai
[READER]
[READER, ADMIN]
~~~

List.copyOf tạo danh sách không sửa đổi được và tách cấu trúc danh sách khỏi nguồn mutable. Vì phần tử trong ví dụ là String bất biến, không cần sao chép riêng từng phần tử. List.copyOf từ chối null ở danh sách hoặc phần tử, và không tự sao chép sâu các phần tử mutable.

## 5. View không sửa đổi và snapshot khác nhau

**Collections.unmodifiableList(source)** chặn thao tác sửa qua view, nhưng view vẫn phản ánh thay đổi từ source. **List.copyOf(source)** tạo cấu trúc không sửa đổi được, không tiếp tục phản ánh việc thêm hoặc xóa trên nguồn mutable.

| Cách tạo | Có thể sửa qua kết quả? | Thấy thay đổi cấu trúc từ source? |
| --- | --- | --- |
| Collections.unmodifiableList(source) | Không | Có |
| List.copyOf(source) | Không | Không |

Cả hai cách đều không làm các phần tử mutable trở nên bất biến. Nếu một phần tử là StringBuilder và có tham chiếu khác tới nó, nội dung phần tử vẫn có thể thay đổi.

## 6. Record và bất biến sâu

Record không tự sao chép collection được truyền vào. Nếu record nhận một List mutable và giữ nguyên tham chiếu, bên gọi vẫn có thể làm nội dung quan sát được thay đổi. Có thể sao chép phòng vệ trong compact constructor:

~~~java
import java.util.List;

record Report(List<String> tags) {
    Report {
        tags = List.copyOf(tags);
    }
}
~~~

Với các phần tử bất biến như String, cách này bảo vệ cấu trúc và dữ liệu quan sát được trong ví dụ. Với phần tử mutable, phải định nghĩa rõ cách sao chép hoặc chuyển chúng thành kiểu dữ liệu bất biến.

## 7. final không làm dữ liệu chia sẻ thread-safe

Một public static final ArrayList vẫn có thể bị nhiều thread đọc và sửa đồng thời. final không biến các thao tác sửa trên đối tượng mutable thành thao tác an toàn luồng. Cần chọn cấu trúc dữ liệu và cơ chế đồng bộ phù hợp; tốt nhất là tránh chia sẻ mutable state khi không cần thiết.

### Checklist thiết kế

- Dùng final để ngăn gán lại biến hoặc tham chiếu.
- Dùng kiểu bất biến khi giá trị không nên đổi sau khi tạo.
- Sao chép phòng vệ dữ liệu đầu vào và không trả trực tiếp tham chiếu mutable nội bộ.
- Phân biệt view không sửa đổi với snapshot độc lập.
- Đừng suy luận bất biến sâu chỉ từ final class, record hoặc List.copyOf.
- Tránh công khai mutable state từ interface vì mọi nơi có quyền truy cập đều có thể tác động đến cùng dữ liệu.

Tính bất biến là kết quả của thiết kế đối tượng và các tham chiếu có thể tiếp cận nó; từ khóa final chỉ là một phần của cách thiết kế đó.