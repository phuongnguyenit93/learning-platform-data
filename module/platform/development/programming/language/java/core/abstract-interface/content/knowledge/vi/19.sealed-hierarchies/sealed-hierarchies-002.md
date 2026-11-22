# Sealed abstract class và sealed interface trong Java

## 1. Mục tiêu và ý tưởng

Từ Java 17, `sealed class` và `sealed interface` là tính năng chính thức giúp giới hạn những kiểu được phép kế thừa hoặc triển khai trực tiếp một kiểu. Chúng hữu ích khi mô hình miền có một tập hợp biến thể đã biết, chẳng hạn các loại hình học, trạng thái xử lý hoặc phương tiện vận tải.

`abstract` và `sealed` giải quyết hai vấn đề khác nhau:

- `abstract` ngăn tạo đối tượng trực tiếp từ một lớp và cho phép khai báo phương thức chưa có phần triển khai.
- `sealed` giới hạn tập hợp các lớp hoặc interface được phép kế thừa trực tiếp kiểu đó.
- Kết hợp `abstract sealed class` tạo một lớp cơ sở không thể khởi tạo, đồng thời kiểm soát rõ nhánh kế thừa của nó.

`sealed` không làm đối tượng bất biến, không tự biến mọi phương thức thành `final`, và cũng không thay thế việc kiểm tra dữ liệu đầu vào.

## 2. Sealed abstract class và sealed interface khác nhau thế nào?

| Khía cạnh | `sealed abstract class` | `sealed interface` |
| --- | --- | --- |
| Mục đích thường gặp | Chia sẻ trạng thái, constructor và hành vi chung cho một họ lớp | Định nghĩa hợp đồng cho một tập hợp kiểu được kiểm soát |
| Trạng thái đối tượng | Có thể có field instance | Không có field instance; field khai báo trong interface là hằng `public static final` |
| Constructor | Có thể khai báo constructor để khởi tạo trạng thái chung | Không có constructor |
| Phương thức | Có thể có phương thức abstract, concrete, final hoặc protected | Có thể có phương thức abstract, `default`, `static` và private theo quy tắc của interface |
| Kế thừa | Một lớp chỉ có thể extends một lớp | Một lớp có thể implements nhiều interface |
| Loại được phép kế thừa trực tiếp | Lớp con | Lớp hoặc interface con |

Chọn abstract class khi các biến thể có dữ liệu hoặc quy trình chung cần được dùng lại. Chọn interface khi trọng tâm là một khả năng hay hợp đồng mà các kiểu có thể thực hiện theo nhiều cách. Có thể dùng cả hai trong cùng một thiết kế.

## 3. Quy tắc của sealed hierarchy

### Khai báo và `permits`

```java
sealed abstract class Vehicle permits Car, Truck {
    abstract double maxLoad();
}

sealed interface Shape permits Circle, Rectangle {
    double area();
}
```

`permits` liệt kê các kiểu con trực tiếp được cho phép. Hãy liệt kê đúng các kiểu `extends` hoặc `implements` trực tiếp kiểu sealed; không liệt kê những lớp ở sâu hơn trong cây kế thừa.

Có thể bỏ `permits` khi toàn bộ kiểu con trực tiếp được khai báo trong cùng compilation unit với kiểu sealed; trình biên dịch sẽ suy ra danh sách đó. Nếu các kiểu được khai báo ở những tệp nguồn khác nhau, hãy khai báo `permits` rõ ràng.

### Chính sách của kiểu con trực tiếp

Class được phép kế thừa hoặc triển khai trực tiếp một sealed type phải là `final`, `sealed` hoặc `non-sealed`; record đã là `final` ngầm định. `final` đóng nhánh, `sealed` tiếp tục giới hạn theo tầng, còn `non-sealed` mở nhánh cho các hậu duệ không cần xuất hiện trong `permits` của tổ tiên. Riêng **interface con** không thể là `final`, nên chỉ chọn `sealed` hoặc `non-sealed`.

Một nhánh `Truck` là `non-sealed` có thể có `DeliveryTruck` kế thừa, nhưng `DeliveryTruck` vẫn là hậu duệ **gián tiếp** của `Vehicle`.

### Quy tắc về package và module

- Khi không dùng named module, kiểu sealed và các kiểu con trực tiếp được phép phải nằm trong cùng package.
- Khi dùng named module, chúng phải nằm trong cùng module; các package có thể khác nhau.
- Mỗi kiểu được liệt kê trong `permits` phải thật sự là kiểu con trực tiếp của kiểu sealed tương ứng.
- Một `record` là kiểu `final` ngầm định, nên có thể trực tiếp triển khai sealed interface khi đáp ứng các quy tắc còn lại. Record luôn kế thừa `java.lang.Record`, vì vậy **không thể** trực tiếp `extends` một sealed class.

### Sealed không đồng nghĩa với abstract

Một lớp sealed có thể concrete. `abstract` chỉ cần thiết khi muốn cấm khởi tạo trực tiếp lớp cơ sở hoặc còn phương thức abstract chưa được triển khai. Một sealed interface vốn không thể được khởi tạo trực tiếp, nên không cần từ khóa `abstract`.

## 4. Ví dụ Java 17 hoàn chỉnh

Ví dụ dưới đây minh họa hai hierarchy độc lập: `Shape` là sealed interface; `Vehicle` là sealed abstract class. `Circle` và `Car` đóng nhánh bằng `final`, còn `Rectangle` và `Truck` mở rộng nhánh bằng `non-sealed`.

Lưu nội dung sau thành `Main.java`:

```java
import java.util.Locale;
import java.util.Objects;

public class Main {
    public static void main(String[] args) {
        Shape circle = new Circle(2.0);
        Shape rectangle = new Rectangle(3.0, 4.0);
        System.out.printf(Locale.ROOT, "Circle area: %.2f%n", circle.area());
        System.out.printf(Locale.ROOT, "Rectangle area: %.2f%n", rectangle.area());

        Vehicle car = new Car("51A-123.45");
        Vehicle truck = new DeliveryTruck("51C-678.90", 8.5);
        System.out.println(car.description());
        System.out.printf(Locale.ROOT, "Truck max load: %.1f t%n", truck.maxLoad());

        if (truck instanceof Truck t) {
            System.out.println("Truck registration: " + t.registration());
        }
    }
}

sealed interface Shape permits Circle, Rectangle {
    double area();
}

final class Circle implements Shape {
    private final double radius;

    Circle(double radius) {
        if (radius <= 0) {
            throw new IllegalArgumentException("radius must be positive");
        }
        this.radius = radius;
    }

    @Override
    public double area() {
        return Math.PI * radius * radius;
    }
}

non-sealed class Rectangle implements Shape {
    private final double width;
    private final double height;

    Rectangle(double width, double height) {
        if (width <= 0 || height <= 0) {
            throw new IllegalArgumentException("dimensions must be positive");
        }
        this.width = width;
        this.height = height;
    }

    @Override
    public double area() {
        return width * height;
    }
}

sealed abstract class Vehicle permits Car, Truck {
    private final String registration;

    protected Vehicle(String registration) {
        this.registration = Objects.requireNonNull(registration, "registration");
    }

    public final String registration() {
        return registration;
    }

    public String description() {
        return getClass().getSimpleName() + " [" + registration + "]";
    }

    public abstract double maxLoad();
}

final class Car extends Vehicle {
    Car(String registration) {
        super(registration);
    }

    @Override
    public double maxLoad() {
        return 0.0;
    }
}

non-sealed class Truck extends Vehicle {
    private final double maxLoad;

    Truck(String registration, double maxLoad) {
        super(registration);
        if (maxLoad < 0) {
            throw new IllegalArgumentException("maxLoad must not be negative");
        }
        this.maxLoad = maxLoad;
    }

    @Override
    public double maxLoad() {
        return maxLoad;
    }
}

final class DeliveryTruck extends Truck {
    DeliveryTruck(String registration, double maxLoad) {
        super(registration, maxLoad);
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```text
javac --release 17 Main.java
java Main
```

Kết quả stdout:

```text
Circle area: 12.57
Rectangle area: 12.00
Car [51A-123.45]
Truck max load: 8.5 t
Truck registration: 51C-678.90
```

## 5. Đọc ví dụ theo từng phần

- `Shape` định nghĩa hợp đồng `area()`. `Circle` và `Rectangle` là hai kiểu triển khai trực tiếp được cho phép.
- `Circle` là `final`, nên không thể có lớp con. `Rectangle` là `non-sealed`, nên có thể được mở rộng thêm mà không phải sửa danh sách `permits` của `Shape`.
- `Vehicle` vừa `sealed` vừa `abstract`. Constructor dùng chung kiểm tra `registration`, còn `description()` là hành vi chung và `maxLoad()` là yêu cầu mà từng loại xe phải triển khai.
- `Car` là kiểu con trực tiếp `final`; `Truck` là kiểu con trực tiếp `non-sealed`. `DeliveryTruck` mở rộng `Truck`, minh họa một kiểu con gián tiếp được phép bởi nhánh đã mở.
- Biến `truck` có kiểu khai báo `Vehicle`, nhưng đối tượng thực tế là `DeliveryTruck`. Biểu thức `truck instanceof Truck t` kiểm tra kiểu và tạo biến mẫu `t` khi điều kiện đúng; cú pháp này dùng được từ Java 16, nên phù hợp Java 17.
- `Locale.ROOT` giữ dấu thập phân của định dạng số ổn định, giúp stdout ở ví dụ không phụ thuộc locale của máy.

## 6. Lỗi thường gặp

1. **Quên khai báo trạng thái của kiểu con trực tiếp.** Một kiểu con trực tiếp của sealed class hoặc interface phải khai báo `final`, `sealed` hoặc `non-sealed` (record là `final` ngầm định). Thiếu lựa chọn này sẽ gây lỗi biên dịch.
2. **Đưa kiểu con gián tiếp vào `permits`.** Chỉ các kiểu `extends` hoặc `implements` trực tiếp mới được liệt kê.
3. **Đặt kiểu con ở sai package hoặc module.** Kiểm tra quy tắc package khi dùng unnamed module và quy tắc module khi dùng named module.
4. **Dùng `non-sealed` trên kiểu không có cha sealed trực tiếp.** Từ khóa này chỉ hợp lệ khi kiểu đó trực tiếp mở rộng hoặc triển khai một kiểu sealed.
5. **Nhầm `abstract` với `sealed`.** Một lớp abstract có thể được kế thừa tự do nếu không có ràng buộc khác; sealed mới là từ khóa giới hạn các kiểu con trực tiếp.
6. **Cho rằng `sealed` khóa toàn bộ cây kế thừa.** Các nhánh `non-sealed` vẫn cho phép mở rộng tiếp. Nếu cần đóng hoàn toàn một nhánh, dùng `final`; nếu muốn tiếp tục kiểm soát từng tầng, dùng `sealed` ở tầng tiếp theo.
7. **Dùng ví dụ cú pháp mới hơn phiên bản mục tiêu.** Sealed types được hoàn thiện trong Java 17. Nếu dùng pattern matching cho `switch`, cần kiểm tra phiên bản Java tương ứng; ví dụ trên không phụ thuộc tính năng `switch` mới hơn.

## 7. Khi nào nên dùng?

Dùng sealed hierarchy khi tập hợp biến thể hợp lệ có thể được xác định rõ ở cấp thiết kế và việc thêm một biến thể mới nên buộc người bảo trì xem lại các điểm xử lý liên quan. Đây là lựa chọn phù hợp cho mô hình miền, cây cú pháp, trạng thái giao dịch hoặc các kiểu kết quả có tập trường hợp hữu hạn.

Tránh dùng sealed chỉ để tạo thêm từ khóa cho một hierarchy vốn cần được mở rộng tự do bởi thư viện hoặc ứng dụng bên ngoài. Trong trường hợp đó, interface hoặc abstract class thông thường có thể phù hợp hơn.

Trước khi hoàn tất thiết kế, hãy kiểm tra:

- Danh sách kiểu con trực tiếp có phản ánh đúng các biến thể hợp lệ không?
- Mỗi kiểu con trực tiếp đã chọn `final`, `sealed` hoặc `non-sealed` chưa?
- Nên chia sẻ trạng thái và triển khai bằng abstract class, hay chỉ cần hợp đồng bằng interface?
- Có thực sự muốn mở nhánh kế thừa bằng `non-sealed` không?
- Phiên bản JDK dùng để biên dịch có hỗ trợ các tính năng xuất hiện trong mã nguồn không?
