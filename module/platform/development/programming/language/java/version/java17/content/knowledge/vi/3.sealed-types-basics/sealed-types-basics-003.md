# Khai báo `sealed class`, `sealed interface` và `permits` trong Java 17

**Chủ đề:** Java 17 → Sealed cơ bản

Từ **Java 17**, `sealed` là tính năng ngôn ngữ chính thức cho phép lớp hoặc interface **giới hạn trực tiếp những kiểu được phép kế thừa hoặc triển khai nó**. Khi khai báo một kiểu là `sealed`, ta có thể dùng `permits` để chỉ rõ danh sách những lớp/interface con trực tiếp được phép tham gia hệ phân cấp đó.

Đây là cơ chế hữu ích khi một mô hình chỉ có một số biến thể hợp lệ, chẳng hạn trạng thái xử lý, kết quả giao dịch hoặc các nhóm sự kiện trong ứng dụng. Các ví dụ trong bài dùng cú pháp **ổn định của Java 17**, không cần `--enable-preview` hoặc API thử nghiệm.

## 1. `sealed` giải quyết vấn đề gì?

Giả sử ứng dụng có kiểu `PaymentResult` biểu diễn kết quả thanh toán. Hai trường hợp được thiết kế sẵn là `Success` và `Failure`. Nếu khai báo một interface thông thường:

~~~java
interface PaymentResult {
}
~~~

thì bất kỳ lớp nào nhìn thấy interface này và thỏa điều kiện truy cập đều có thể `implements PaymentResult`. Một thư viện hoặc module khác có thể tạo thêm kiểu kết quả ngoài dự kiến. Điều này không phải lúc nào cũng sai, nhưng có thể gây khó khăn khi miền nghiệp vụ **chỉ cho phép một tập trường hợp xác định**.

Với sealed interface:

~~~java
sealed interface PaymentResult permits Success, Failure {
}

record Success(String transactionId) implements PaymentResult {
}

record Failure(String reason) implements PaymentResult {
}
~~~

Java 17 kiểm soát ngay lúc biên dịch rằng chỉ những kiểu được cho phép mới được trực tiếp `implements PaymentResult`. Hai `record` ở đây là các kiểu trực tiếp được phép, đồng thời chúng có tính chất `final` ngầm định, nên không thể được kế thừa tiếp.

**Phân biệt ba khái niệm:**

| Khai báo | Ý nghĩa với kế thừa |
| --- | --- |
| `class` / `interface` thông thường | Các kiểu con có thể được khai báo theo quy tắc truy cập và kế thừa thông thường. |
| `final class` | Không cho lớp nào kế thừa lớp đó. |
| `sealed class` / `sealed interface` | Chỉ cho một danh sách các kiểu con **trực tiếp** đã được xác định; mỗi kiểu con quyết định cách hệ phân cấp được tiếp tục. |

`sealed` **không đồng nghĩa với bất biến (immutable)**. Nó kiểm soát quan hệ kế thừa, không tự động ngăn các thuộc tính của đối tượng thay đổi.

## 2. Cú pháp khai báo với `permits`

### 2.1. Sealed class

Cú pháp tổng quát:

~~~java
sealed class Parent permits ChildA, ChildB {
    // Thuộc tính, constructor và phương thức
}
~~~

Lớp `Parent` nêu rõ các lớp được phép **trực tiếp** `extends Parent`. Các lớp được liệt kê phải thực sự khai báo `extends Parent` và tuân theo những ràng buộc của sealed hierarchy.

Lớp sealed cũng có thể là lớp trừu tượng:

~~~java
abstract sealed class Shape permits Circle, Rectangle {
    abstract double area();
}

final class Circle extends Shape {
    @Override
    double area() {
        return Math.PI;
    }
}

non-sealed class Rectangle extends Shape {
    @Override
    double area() {
        return 1.0;
    }
}
~~~

Ví dụ này minh họa **cách khai báo**: `Shape` là lớp cha trừu tượng, `Circle` và `Rectangle` là hai lớp con trực tiếp được cho phép. Phần sau sẽ xây dựng ví dụ đầy đủ, có dữ liệu và chạy được.

### 2.2. Sealed interface

Cú pháp tổng quát:

~~~java
sealed interface Parent permits ChildA, ChildB {
    // Các khai báo phương thức
}
~~~

Đối với sealed interface, tên trong `permits` có thể là **lớp trực tiếp `implements`** hoặc **interface trực tiếp `extends`** interface sealed.

~~~java
sealed interface Event permits LoginEvent, LogoutEvent, SystemEvent {
}

record LoginEvent(String username) implements Event {
}

record LogoutEvent(String username) implements Event {
}

non-sealed interface SystemEvent extends Event {
    String description();
}
~~~

`LoginEvent` và `LogoutEvent` là các record; `SystemEvent` là interface con trực tiếp. Vì `SystemEvent` là `non-sealed`, những kiểu khác có thể triển khai `SystemEvent` theo quy tắc Java thông thường. Chúng là hậu duệ **gián tiếp** của `Event`, nên không cần có tên riêng trong `Event.permits`.

### 2.3. `permits` có ý nghĩa chính xác là gì?

Trong khai báo:

~~~java
sealed interface Message permits TextMessage, ImageMessage {
}
~~~

- `sealed`: yêu cầu trình biên dịch giới hạn các kiểu con trực tiếp.
- `interface Message`: kiểu cha được khai báo.
- `permits TextMessage, ImageMessage`: **danh sách kiểu con trực tiếp được phép**. Đây không phải danh sách các đối tượng được tạo khi chạy chương trình và cũng không phải cơ chế cấp quyền truy cập.
- `TextMessage` và `ImageMessage` phải trực tiếp `implements Message` hoặc, nếu là interface, trực tiếp `extends Message`.

`permits` không liệt kê mọi hậu duệ ở tất cả các cấp. Một kiểu con `non-sealed` có thể tiếp tục được kế thừa hoặc triển khai, tùy loại của nó.

## 3. Mỗi kiểu con trực tiếp phải khai báo thế nào?

Một lớp được phép kế thừa trực tiếp sealed class, hoặc một lớp trực tiếp triển khai sealed interface, phải có một trong các trạng thái sau:

| Trạng thái | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `final` | Chấm dứt nhánh kế thừa tại lớp đó. | `final class Circle extends Shape` |
| `sealed` | Tiếp tục giới hạn danh sách kiểu con trực tiếp ở cấp kế tiếp. | `sealed class Polygon extends Shape permits Triangle` |
| `non-sealed` | Mở lại khả năng kế thừa ở nhánh đó. | `non-sealed class Rectangle extends Shape` |

Với **interface** trực tiếp kế thừa sealed interface, hai lựa chọn là `sealed` hoặc `non-sealed`; interface không thể khai báo `final`. Với **record** trực tiếp triển khai sealed interface, record đã là `final` ngầm định nên không cần khai báo thêm modifier `final`.

Ví dụ cấu trúc:

~~~text
Shape (abstract sealed)
├── Circle (final)
└── Rectangle (non-sealed)
    └── Square (final)
~~~

Sealed class `Shape` cho phép đúng hai lớp con **trực tiếp** là `Circle` và `Rectangle`. Lớp `Square` vẫn có thể kế thừa `Rectangle` vì nhánh này được đánh dấu `non-sealed`. `Square` không phải lớp con trực tiếp của `Shape`, nên không xuất hiện trong `permits` của `Shape`.

> **Điểm cần nhớ:** `sealed`, `non-sealed` và `final` không phải ba từ khóa có thể kết hợp tùy ý. Một lớp không thể vừa `final` vừa `sealed`. Một lớp/interface `non-sealed` phải có một kiểu cha trực tiếp là sealed để việc “mở lại” kế thừa có ý nghĩa.

## 4. Ví dụ hoàn chỉnh với `sealed class`

Tạo tệp **`SealedClassDemo.java`**:

~~~java
public class SealedClassDemo {
    static abstract sealed class Shape permits Circle, Rectangle {
        abstract double area();
    }

    static final class Circle extends Shape {
        private final double radius;

        Circle(double radius) {
            this.radius = radius;
        }

        @Override
        double area() {
            return Math.PI * radius * radius;
        }
    }

    static non-sealed class Rectangle extends Shape {
        private final double width;
        private final double height;

        Rectangle(double width, double height) {
            this.width = width;
            this.height = height;
        }

        @Override
        double area() {
            return width * height;
        }
    }

    static final class Square extends Rectangle {
        Square(double side) {
            super(side, side);
        }
    }

    public static void main(String[] args) {
        Shape circle = new Circle(2.0);
        Shape square = new Square(3.0);

        System.out.println("Dien tich hinh tron: " + circle.area());
        System.out.println("Dien tich hinh vuong: " + square.area());
    }
}
~~~

Biên dịch và chạy bằng JDK 17:

~~~shell
javac --release 17 SealedClassDemo.java
java SealedClassDemo
~~~

Trong ví dụ:

1. `Shape` là **`abstract sealed class`**, định nghĩa hợp đồng tính diện tích và không thể khởi tạo trực tiếp.
2. `permits Circle, Rectangle` giới hạn các lớp kế thừa trực tiếp `Shape`.
3. `Circle` được khai báo `final`, nên không thể có lớp con của `Circle`.
4. `Rectangle` được khai báo `non-sealed`, cho phép `Square` kế thừa.
5. `Square` kế thừa `Rectangle`; nó không cần được khai báo trong `Shape.permits`.

Ở đây, các kiểu được khai báo lồng nhau trong cùng lớp `SealedClassDemo`, vì vậy có thể đặt cả ví dụ trong một file và thấy rõ quan hệ giữa các kiểu.

## 5. Ví dụ hoàn chỉnh với `sealed interface` và `record`

Một mô hình kết quả xử lý thường phù hợp với sealed interface vì mỗi biến thể mang dữ liệu khác nhau nhưng cùng thuộc một tập kết quả xác định.

Tạo tệp **`SealedInterfaceDemo.java`**:

~~~java
public class SealedInterfaceDemo {
    sealed interface Result permits Success, Failure, Deferred {
    }

    record Success(String value) implements Result {
    }

    record Failure(String reason) implements Result {
    }

    non-sealed interface Deferred extends Result {
        String ticket();
    }

    static final class Pending implements Deferred {
        private final String ticket;

        Pending(String ticket) {
            this.ticket = ticket;
        }

        @Override
        public String ticket() {
            return ticket;
        }
    }

    static String describe(Result result) {
        if (result instanceof Success success) {
            return "Thành công: " + success.value();
        }
        if (result instanceof Failure failure) {
            return "Thất bại: " + failure.reason();
        }
        if (result instanceof Deferred deferred) {
            return "Đang chờ: " + deferred.ticket();
        }
        throw new IllegalStateException("Kiểu Result chưa được xử lý");
    }

    public static void main(String[] args) {
        Result a = new Success("Đã lưu");
        Result b = new Failure("Dữ liệu không hợp lệ");
        Result c = new Pending("REQ-001");

        System.out.println(describe(a));
        System.out.println(describe(b));
        System.out.println(describe(c));
    }
}
~~~

Chạy:

~~~shell
javac --release 17 SealedInterfaceDemo.java
java SealedInterfaceDemo
~~~

Kết quả:

~~~text
Thành công: Đã lưu
Thất bại: Dữ liệu không hợp lệ
Đang chờ: REQ-001
~~~

Ở ví dụ này:

- `Result` là sealed interface với ba kiểu được phép **trực tiếp**.
- `Success` và `Failure` là `record` trực tiếp triển khai `Result`; record không thể được kế thừa tiếp.
- `Deferred` là interface con trực tiếp, nhưng đánh dấu `non-sealed` để cho phép thêm các loại xử lý đang chờ.
- `Pending` triển khai `Deferred` thay vì trực tiếp triển khai `Result`, vì vậy không cần xuất hiện trong `Result.permits`.
- `instanceof Success success` là **pattern matching for instanceof**, tính năng đã chính thức trước Java 17. Nó phù hợp khi xử lý các loại kết quả trong bài này.

**Lưu ý về Java 17:** tránh dùng *pattern matching for switch* để xử lý các kiểu sealed trong ví dụ chuẩn Java 17, vì tính năng ấy vẫn ở trạng thái **preview trong Java 17**. `switch` expression thông thường đã ổn định, nhưng đó là tính năng khác. Các nhánh `if`/`instanceof` ở trên sử dụng cú pháp chính thức, không cần cờ preview.

## 6. Khi nào được bỏ `permits`?

Trong Java 17, nếu các lớp hoặc interface con trực tiếp được khai báo **trong cùng một đơn vị mã nguồn Java (compilation unit)** với kiểu sealed, trình biên dịch có thể suy ra danh sách được phép. Khi đó có thể bỏ `permits`.

Ví dụ đặt tất cả khai báo sau trong **cùng file `State.java`**:

~~~java
sealed interface State {
}

final class Ready implements State {
}

final class Stopped implements State {
}
~~~

Trình biên dịch suy ra `Ready` và `Stopped` là hai kiểu con được phép của `State`.

Khai báo trên về ý nghĩa tương đương với:

~~~java
sealed interface State permits Ready, Stopped {
}
~~~

Khi các kiểu được đặt ở **nhiều file riêng biệt**, hãy khai báo `permits` một cách tường minh để chỉ rõ quan hệ được cho phép. Với mã dùng để giảng dạy hoặc mô hình miền nghiệp vụ có nhiều thành phần, việc ghi `permits` rõ ràng cũng giúp người đọc nhanh chóng thấy cấu trúc thiết kế.

> Việc suy ra `permits` phụ thuộc vào **cùng compilation unit**, không đơn thuần chỉ là các file ở cùng một thư mục hoặc cùng package.

## 7. Quy tắc về package, module và kiểu con trực tiếp

`sealed` được kiểm tra **tại thời điểm biên dịch** và có ràng buộc về vị trí khai báo:

| Bối cảnh | Vị trí được phép của kiểu con trực tiếp trong `permits` |
| --- | --- |
| Kiểu sealed thuộc **named module** (module có `module-info.java`) | Kiểu con trực tiếp phải nằm **trong cùng named module**; có thể ở package khác trong module đó nếu các quy tắc truy cập cho phép. |
| Kiểu sealed thuộc **unnamed module** (thường gặp trong dự án Java chưa dùng JPMS) | Kiểu con trực tiếp phải nằm **trong cùng package**. |

Ví dụ dự án đơn giản không dùng module, có thể đặt ở package `example.shapes`:

**`Shape.java`:**

~~~java
package example.shapes;

public abstract sealed class Shape permits Circle, Rectangle {
    public abstract double area();
}
~~~

**`Circle.java`:**

~~~java
package example.shapes;

public final class Circle extends Shape {
    @Override
    public double area() {
        return Math.PI;
    }
}
~~~

**`Rectangle.java`:**

~~~java
package example.shapes;

public non-sealed class Rectangle extends Shape {
    @Override
    public double area() {
        return 1.0;
    }
}
~~~

Ba kiểu cùng package, `Circle` và `Rectangle` trực tiếp `extends Shape`, và mỗi lớp con có trạng thái `final` hoặc `non-sealed` hợp lệ.

`permits` **không bỏ qua quy tắc visibility**. Ví dụ, nếu constructor hoặc phương thức của lớp cha không truy cập được từ lớp con, chương trình vẫn có thể lỗi biên dịch dù tên lớp con có trong `permits`.

## 8. Các lỗi thường gặp khi khai báo

### 8.1. Thiếu modifier ở lớp con trực tiếp

Ví dụ **sai**, cố tình minh họa lỗi:

~~~java
sealed class Vehicle permits Car {
}

class Car extends Vehicle {
    // Sai: lớp con trực tiếp của sealed class
    // phải được khai báo final, sealed hoặc non-sealed.
}
~~~

Sửa thành `final class Car extends Vehicle` nếu muốn đóng nhánh, hoặc dùng `sealed` / `non-sealed` theo ý định thiết kế.

### 8.2. Khai báo kiểu con không có trong `permits`

Ví dụ **sai**:

~~~java
sealed interface Command permits Start {
}

final class Start implements Command {
}

final class Stop implements Command {
    // Sai: Stop trực tiếp implements Command
    // nhưng không có trong permits của Command.
}
~~~

Muốn `Stop` là kiểu con hợp lệ, bổ sung nó vào danh sách `permits` và bảo đảm nó đáp ứng các quy tắc package/module.

### 8.3. Liệt kê nhầm hậu duệ gián tiếp

Ví dụ **sai**:

~~~java
sealed class Animal permits Dog, Poodle {
}

non-sealed class Dog extends Animal {
}

final class Poodle extends Dog {
    // Sai ở Animal.permits: Poodle không trực tiếp extends Animal.
}
~~~

Khai báo đúng là `sealed class Animal permits Dog`, bởi `Poodle` chỉ kế thừa **gián tiếp** từ `Animal`.

### 8.4. Dùng `non-sealed` không có kiểu cha sealed

Ví dụ **sai**:

~~~java
class PlainBase {
}

non-sealed class Other extends PlainBase {
    // Sai: không có sealed supertype trực tiếp cần mở nhánh.
}
~~~

`non-sealed` có ý nghĩa trong hệ phân cấp đã bị giới hạn bởi sealed supertype. Với lớp thông thường, chỉ cần khai báo `class Other extends PlainBase`.

### 8.5. Nhầm sealed với final hoặc cơ chế bảo mật

Không thể khai báo `final sealed class`, vì `final` cấm kế thừa hoàn toàn trong khi `sealed` cho phép một số lớp con cụ thể. `permits` cũng không cấp quyền gọi phương thức, truy cập thuộc tính hay vượt qua `private`, `protected` hoặc quy tắc module.

## 9. Chọn sealed class hay sealed interface?

| Tiêu chí | `sealed class` | `sealed interface` |
| --- | --- | --- |
| Mối quan hệ | Các kiểu con **`extends`** một lớp cha. | Các lớp **`implements`** hoặc interface con **`extends`** interface cha. |
| Trạng thái và hành vi chung | Có thể chứa field, constructor, phương thức có thân và phương thức trừu tượng; thích hợp khi cần chia sẻ mã hoặc trạng thái. | Chủ yếu biểu diễn hợp đồng, có thể khai báo phương thức và `default` method; không có constructor hay instance field. |
| Khả năng kết hợp | Một lớp Java chỉ trực tiếp `extends` được một lớp cha. | Một lớp có thể triển khai nhiều interface, tuân theo các quy tắc về kế thừa và `permits`. |
| Kết hợp với `record` | `record` không thể `extends` sealed class tùy ý vì đã kế thừa `java.lang.Record`. | `record` có thể trực tiếp `implements` sealed interface, rất tiện biểu diễn biến thể dữ liệu. |
| Trường hợp nên cân nhắc | Hệ phân cấp có hành vi hoặc trạng thái chung cần được quản lý bởi lớp cha. | Tập kiểu đại diện các trường hợp nghiệp vụ, trong đó mỗi biến thể có hình dạng dữ liệu khác nhau. |

Nếu muốn một API cho phép bên ngoài tự tạo nhiều kiểu triển khai mở rộng, sealed có thể làm giảm khả năng mở rộng của API đó. Hãy chọn sealed khi sự **giới hạn các kiểu con là yêu cầu thiết kế có chủ đích**.

## 10. Ghi nhớ khi làm việc với Java 17

1. Dùng `sealed class` hoặc `sealed interface` để giới hạn **các kiểu con trực tiếp**.
2. Ghi `permits` để liệt kê các kiểu con trực tiếp được phép, hoặc chỉ bỏ danh sách khi trình biên dịch có thể suy ra từ cùng compilation unit.
3. Mỗi lớp con trực tiếp phải là `final`, `sealed` hoặc `non-sealed`; interface con trực tiếp chọn `sealed` hoặc `non-sealed`; record đã là `final` ngầm định.
4. Tuân thủ quy tắc cùng named module hoặc cùng package trong unnamed module.
5. Không nhầm `sealed` với `final`, tính bất biến của dữ liệu hay quyền truy cập.
6. Khi viết ví dụ theo Java 17, dùng cú pháp sealed đã chính thức và tránh các tính năng *preview* khác như pattern matching trong `switch` ở chính phiên bản 17.

### Tài liệu tham khảo chính thức

- [JEP 409 — Sealed Classes](https://openjdk.org/jeps/409): đề xuất tính năng sealed class/interface được hoàn tất trong JDK 17.
- [Java Language Specification, Java SE 17 — Classes](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html): quy tắc khai báo lớp, sealed class và permitted direct subclasses.
- [Java Language Specification, Java SE 17 — Interfaces](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html): quy tắc sealed interface và quan hệ mở rộng interface.
- [Java SE 17 Language Updates](https://docs.oracle.com/en/java/javase/17/language/): tổng quan các tính năng ngôn ngữ Java 17.
