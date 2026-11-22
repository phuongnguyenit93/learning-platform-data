# Khai báo biến, tham số và kiểu trả về bằng kiểu trừu tượng trong Java

Một nguyên tắc quan trọng của **đa hình (polymorphism)** là: mã sử dụng đối tượng có thể làm việc qua một **kiểu trừu tượng** thay vì phải biết chính xác class triển khai. Trong Java, kiểu trừu tượng ở bài này chủ yếu là **interface** hoặc **abstract class**. Ta có thể khai báo biến, tham số phương thức, field và kiểu trả về bằng những kiểu đó, dù bản thân chúng không thể được khởi tạo trực tiếp theo cách thông thường.

Ví dụ ngắn:

```java
interface Notifier {
    void send(String message);
}

class EmailNotifier implements Notifier {
    @Override
    public void send(String message) {
        System.out.println("Email: " + message);
    }
}
```

Với hai khai báo trên, ta có thể viết:

```java
Notifier notifier = new EmailNotifier();
notifier.send("Hello");
```

Hai đoạn trên là ví dụ cú pháp; đoạn thứ hai phải đặt bên trong một phương thức hoặc khối khởi tạo, chưa phải chương trình độc lập. Ý nghĩa là:

- **`Notifier`** là *kiểu khai báo* (declared/static type) của biến `notifier`.
- **`EmailNotifier`** là *class thực tế* của đối tượng được tạo bởi `new`.
- Class `EmailNotifier` thực hiện hợp đồng `Notifier` nên tham chiếu kiểu `Notifier` có thể trỏ tới đối tượng đó.
- Trình biên dịch kiểm tra lời gọi `notifier.send(...)` theo những phương thức mà `Notifier` công bố. Khi chạy, implementation thích hợp của `EmailNotifier` được thực thi.

Mục tiêu không phải “ẩn mọi class”, mà là cho phần mã *sử dụng* phụ thuộc vào hợp đồng ổn định, trong khi phần tạo đối tượng được quyền chọn một implementation phù hợp.

## 1. Phân biệt kiểu khai báo với kiểu thực tế

Xét đoạn mã minh họa:

```java
Notifier channel = new EmailNotifier();
```

| Thành phần | Ý nghĩa |
| --- | --- |
| `Notifier` | Kiểu khai báo của biến; quyết định API có thể gọi trực tiếp lúc biên dịch. |
| `channel` | Biến tham chiếu; có thể được gán `null` hoặc tham chiếu đối tượng tương thích. |
| `new EmailNotifier()` | Tạo một đối tượng thuộc class cụ thể `EmailNotifier`. |
| Kiểu runtime của đối tượng | `EmailNotifier`, kể cả khi biến lưu nó có kiểu `Notifier`. |
| `channel.send("Hi")` | Hợp lệ vì `send` được công bố trong `Notifier`; implementation được chọn theo đối tượng runtime. |

Phép gán từ subtype sang supertype (`EmailNotifier` → `Notifier`) là **upcasting**. Java thường thực hiện tự động, không cần ép kiểu tường minh. Quan hệ này cũng áp dụng với abstract superclass:

```java
abstract class Animal {
    abstract String sound();
}

final class Dog extends Animal {
    @Override
    String sound() {
        return "woof";
    }
}

// Hợp lệ khi đặt trong một phương thức:
Animal pet = new Dog();
```

Một interface có thể có nhiều class thực hiện; abstract class cũng có thể có nhiều concrete subclass. Đa hình phát huy tác dụng khi cùng một lời gọi trên kiểu cha được đáp ứng bởi các đối tượng con khác nhau.

**Không nhầm:** kiểu khai báo không làm thay đổi bản chất đối tượng. Gán một `EmailNotifier` cho biến `Notifier` không biến đối tượng thành “đối tượng interface”, và cũng không tạo bản sao hoặc làm mất phương thức của đối tượng. Chỉ có **những thao tác được cho phép qua biến** phụ thuộc vào kiểu khai báo.

## 2. Dùng kiểu trừu tượng để khai báo biến và field

Thay vì viết:

```java
EmailNotifier notifier = new EmailNotifier();
```

ta có thể viết:

```java
Notifier notifier = new EmailNotifier();
```

Cách thứ hai hữu ích khi phần mã phía sau chỉ cần `send`: implementation có thể chuyển sang `SmsNotifier`, `PushNotifier` hoặc một class khác thực hiện `Notifier`. Compiler vẫn bảo đảm rằng đối tượng được gán phù hợp với hợp đồng.

Một field cũng có thể khai báo theo interface:

```java
final class NotificationService {
    private final Notifier notifier;

    NotificationService(Notifier notifier) {
        this.notifier = java.util.Objects.requireNonNull(notifier);
    }

    void notifyUser(String message) {
        notifier.send(message);
    }
}
```

Đây là đoạn class minh họa; để chạy cần các khai báo `Notifier` và một implementation như trong chương trình hoàn chỉnh ở mục 5.

- `private final Notifier notifier` cho biết service **phụ thuộc vào khả năng gửi thông báo**, không gắn với `EmailNotifier` cụ thể.
- Constructor nhận một tham chiếu `Notifier` từ bên ngoài (**constructor injection**).
- `final` ở field nghĩa là tham chiếu không được gán lại sau khi khởi tạo hợp lệ; **không** có nghĩa đối tượng được tham chiếu là bất biến.
- Kiểm tra `null` tại ranh giới giúp tránh lỗi khi service gọi `notifier.send(...)` sau này.

Dùng kiểu trừu tượng cho field giúp mã dễ thay đổi implementation, nhưng không bảo đảm thiết kế tốt nếu interface có quá nhiều phương thức không liên quan hoặc caller vẫn thường xuyên ép kiểu về class cụ thể.

## 3. Dùng kiểu trừu tượng làm tham số phương thức

Chữ ký:

```java
static void deliver(Notifier notifier, String message) {
    notifier.send(message);
}
```

cho phép truyền **bất kỳ đối tượng nào có kiểu tương thích với `Notifier`**, không bắt người gọi cung cấp chính xác `EmailNotifier`.

Ví dụ cách gọi (trong cùng phạm vi đã khai báo `Notifier`, `EmailNotifier` và `SmsNotifier`):

```java
deliver(new EmailNotifier(), "Đơn hàng đã tạo");
deliver(new SmsNotifier(), "Đơn hàng đã tạo");
```

Hai đoạn này là minh họa chữ ký và lời gọi, không phải tệp chạy độc lập. Lợi ích:

1. **Tách người gọi khỏi implementation:** phương thức `deliver` chỉ thực hiện một thao tác trên hợp đồng `Notifier`.
2. **Thêm class mới ít ảnh hưởng:** class mới `implements Notifier` có thể được truyền vào mà không sửa tham số phương thức.
3. **Dễ kiểm thử hành vi:** có thể truyền fake/stub implementation để ghi nhận lời gọi, miễn đáp ứng hợp đồng.
4. **Tránh lặp code:** không cần tạo phiên bản `deliver(EmailNotifier)` và `deliver(SmsNotifier)` chỉ để gọi cùng một phương thức.

**Giới hạn của hợp đồng:** bên trong `deliver`, compiler chỉ bảo đảm các thành viên của `Notifier` và các superinterface liên quan. Phương thức chỉ tồn tại trên `EmailNotifier` không tự nhiên gọi được qua tham số `Notifier`.

Nếu hàm thực sự cần tính năng riêng của email, hãy xem có cần một interface giàu ý nghĩa hơn (chẳng hạn `EmailSender`) hoặc dùng loại tham số cụ thể; không nên khai báo interface rộng rồi luôn ép kiểu về implementation bên trong.

## 4. Dùng kiểu trừu tượng làm kiểu trả về

Một phương thức có thể cam kết trả về **`Notifier`** dù bên trong chọn một class cụ thể:

```java
static Notifier chooseNotifier(boolean useEmail) {
    if (useEmail) {
        return new EmailNotifier();
    }
    return new SmsNotifier();
}
```

Khi gọi `Notifier result = chooseNotifier(true);`, người gọi chỉ cần biết đối tượng nhận được hỗ trợ `send`. Phần chọn kênh vẫn được đóng gói ở nơi tạo đối tượng.

Những điểm cần nhớ:

- `return new EmailNotifier();` hợp lệ nếu `EmailNotifier implements Notifier`.
- `return new SmsNotifier();` cũng hợp lệ nếu `SmsNotifier implements Notifier`.
- Nếu phương thức khai báo trả về `Notifier` nhưng trả về đối tượng không tương thích, chương trình không biên dịch.
- `return null;` có thể hợp lệ về cú pháp đối với kiểu tham chiếu nhưng dễ gây `NullPointerException` cho caller; cần ghi rõ hợp đồng nếu chọn cách này.
- Không có đối tượng interface tự sinh ra từ câu lệnh `return`; **đối tượng vẫn cần được tạo** thông qua class cụ thể, factory hoặc nguồn dữ liệu khác.

Kiểu trả về interface cũng xuất hiện phổ biến trong các API của Java Collections, như một phương thức trả `List<String>` thay vì bắt caller phụ thuộc vào `ArrayList<String>`. `List` là interface; `ArrayList` là implementation. Khi trả về collection, cần quyết định thêm về mutability và ownership; **kiểu `List` tự nó không cam kết danh sách được phép sửa**.

### Kiểu trả về hiệp biến (covariant return)

Khi override phương thức trong Java, implementation có thể trả về subtype phù hợp của kiểu trả về ở hợp đồng cha.

```java
interface Factory {
    Notifier create();
}

final class EmailFactory implements Factory {
    @Override
    public EmailNotifier create() {
        return new EmailNotifier();
    }
}
```

Đoạn này minh họa cú pháp; giả định đã có `Notifier` và `EmailNotifier` như trên. `EmailNotifier` là subtype của `Notifier`, nên kiểu trả về ở phương thức override hợp lệ. Khi gọi qua biến `Factory factory`, biểu thức `factory.create()` vẫn có **kiểu tĩnh `Notifier`**, dù implementation trả một `EmailNotifier`.

Không được tùy tiện thay đổi kiểu tham số khi override: ví dụ `send(Object)` không override `send(String)`. Cần phân biệt **overriding** (cùng hợp đồng, đa hình runtime) với **overloading** (nhiều chữ ký khác nhau, chọn theo kiểu ở compile time).

## 5. Chương trình Java 17+ hoàn chỉnh: biến, tham số và kiểu trả về

Lưu toàn bộ mã sau vào tệp **`Main.java`**:

```java
import java.util.Objects;

interface Notifier {
    String channel();
    void send(String recipient, String message);
}

final class EmailNotifier implements Notifier {
    @Override
    public String channel() {
        return "Email";
    }

    @Override
    public void send(String recipient, String message) {
        System.out.println("Email to " + recipient + ": " + message);
    }
}

final class SmsNotifier implements Notifier {
    @Override
    public String channel() {
        return "SMS";
    }

    @Override
    public void send(String recipient, String message) {
        System.out.println("SMS to " + recipient + ": " + message);
    }
}

final class NotificationService {
    private final Notifier notifier;

    NotificationService(Notifier notifier) {
        this.notifier = Objects.requireNonNull(notifier);
    }

    void notifyUser(String recipient) {
        notifier.send(recipient, "Ready");
    }
}

public class Main {
    static void deliver(Notifier notifier, String recipient) {
        notifier.send(recipient, "Updated");
    }

    static Notifier chooseNotifier(String channel) {
        return switch (channel) {
            case "email" -> new EmailNotifier();
            case "sms" -> new SmsNotifier();
            default -> throw new IllegalArgumentException("Unknown channel");
        };
    }

    public static void main(String[] args) {
        Notifier primary = new EmailNotifier();
        Notifier secondary = new SmsNotifier();

        System.out.println(primary.channel());
        deliver(primary, "Lan");

        NotificationService service = new NotificationService(secondary);
        service.notifyUser("Minh");

        Notifier chosen = chooseNotifier("sms");
        System.out.println(chosen.channel());
        deliver(chosen, "An");
    }
}
```

Chạy với JDK 17 trở lên trong thư mục chứa `Main.java`:

```bash
javac Main.java
java Main
```

**Kết quả chuẩn:**

```text
Email
Email to Lan: Updated
SMS to Minh: Ready
SMS
SMS to An: Updated
```

Đọc chương trình theo ba vị trí khai báo kiểu trừu tượng:

| Vị trí | Mã | Vai trò |
| --- | --- | --- |
| Biến | `Notifier primary = new EmailNotifier();` | Giữ đối tượng class cụ thể thông qua interface. |
| Field | `private final Notifier notifier;` | Service không cần biết kênh cụ thể. |
| Tham số | `deliver(Notifier notifier, ...)` | Một phương thức nhận nhiều implementation. |
| Tham số constructor | `NotificationService(Notifier notifier)` | Cung cấp dependency khi tạo service. |
| Kiểu trả về | `static Notifier chooseNotifier(...)` | Cho phép chọn implementation ở runtime. |

Lệnh `javac Main.java` biên dịch các class/interface top-level trong cùng tệp; `java Main` chạy điểm vào `Main.main`. Trong `chooseNotifier`, `switch` là **switch expression** được Java 17 hỗ trợ. Cả hai nhánh `new EmailNotifier()` và `new SmsNotifier()` đều phù hợp với kiểu trả về `Notifier`.

Nếu bổ sung class `PushNotifier implements Notifier`, chữ ký `deliver` và `NotificationService` không phải thay đổi. Phần lựa chọn bên trong factory có thể cần bổ sung case mới theo yêu cầu nghiệp vụ; đó là trách nhiệm của nơi quyết định tạo đối tượng.

## 6. Ranh giới giữa kiểu trừu tượng và cơ chế đa hình

Khi `Notifier notifier = new EmailNotifier();`, compiler cho phép `notifier.send(...)` vì `send` thuộc hợp đồng `Notifier`; lúc chạy, implementation của `EmailNotifier` thực thi. Đây là lý do biến, field, tham số và kiểu trả về có thể dùng abstraction ổn định thay vì phụ thuộc vào một class triển khai.

Các quyết định khác có quy tắc riêng: overload được chọn theo kiểu tĩnh; field và phương thức `static` không dispatch theo đối tượng runtime; gọi instance method qua `null` ném `NullPointerException`. Xem các bài **Liên kết động khi gọi phương thức instance**, **Chọn overload lúc biên dịch và chọn override lúc chạy**, **Đối tượng null và lời gọi qua tham chiếu interface**, và **Vì sao truy cập field và phương thức static không đa hình** để học từng cơ chế.

## 7. Abstract class cũng dùng được cho biến, tham số và kiểu trả về

Một abstract class cung cấp một kiểu cha có thể bao gồm **trạng thái, constructor, phương thức concrete và abstract**. Ta vẫn dùng nó làm kiểu khai báo, nhưng phải tạo đối tượng từ **concrete subclass**.

Tệp độc lập **`ShapeDemo.java`**:

```java
import java.util.Locale;

abstract class Shape {
    abstract double area();

    String label() {
        return "Shape";
    }
}

final class Square extends Shape {
    private final double side;

    Square(double side) {
        this.side = side;
    }

    @Override
    double area() {
        return side * side;
    }

    @Override
    String label() {
        return "Square";
    }
}

final class Circle extends Shape {
    private final double radius;

    Circle(double radius) {
        this.radius = radius;
    }

    @Override
    double area() {
        return Math.PI * radius * radius;
    }

    @Override
    String label() {
        return "Circle";
    }
}

public class ShapeDemo {
    static Shape choose(boolean square) {
        return square ? new Square(2.0) : new Circle(1.0);
    }

    static void printShape(Shape shape) {
        System.out.printf(Locale.ROOT, "%s: %.2f%n",
                shape.label(), shape.area());
    }

    public static void main(String[] args) {
        Shape first = choose(true);
        Shape second = choose(false);
        printShape(first);
        printShape(second);
    }
}
```

```bash
javac ShapeDemo.java
java ShapeDemo
```

```text
Square: 4.00
Circle: 3.14
```

Ở đây `Shape` xuất hiện làm **kiểu biến**, **tham số** (`printShape`) và **kiểu trả về** (`choose`). Hai class con cung cấp implementation cho `area()` và override `label()`. Phương thức `printShape` làm việc bằng API của `Shape`, nên không phải viết hai phiên bản riêng cho hình vuông và hình tròn.

Phân biệt lựa chọn abstract class và interface:

| Nhu cầu | Interface | Abstract class |
| --- | --- | --- |
| Khai báo biến/tham số/trả về đa hình | Có | Có |
| Dùng `new` trực tiếp trên chính kiểu trừu tượng | Không | Không |
| Một class cùng lúc mang nhiều kiểu này | Có thể `implements` nhiều interface | Chỉ `extends` một class trực tiếp |
| Chia sẻ instance state và constructor | Không có instance field hoặc constructor | Có thể có |
| Chia sẻ hành vi mặc định | `default` method khi hợp lệ | Concrete instance methods |
| Thường phù hợp | Hợp đồng khả năng, API linh hoạt | Cùng một họ kiểu cần chung cơ chế/trạng thái kế thừa |

Không có quy tắc “cứ là abstract class thì kém interface”. Chọn loại thích hợp dựa trên hợp đồng và đặc điểm kế thừa thực sự của bài toán.

## 8. Upcasting, downcasting và `instanceof`

Gán `EmailNotifier` vào `Notifier` là upcast, thường ngầm định; tham chiếu vẫn trỏ đến cùng đối tượng. Khi cần hành vi chỉ có ở class cụ thể, downcast phải tương thích với kiểu runtime và có thể ném `ClassCastException` nếu sai. `instanceof` (pattern matching từ Java 16) cho phép kiểm tra trước khi dùng subtype; với `null`, phép thử trả `false`. Cast không tạo hoặc chuyển đổi đối tượng.

Các bài **Upcast và downcast giữa lớp, lớp trừu tượng và interface**, **instanceof, pattern matching và kiểm tra trước khi ép kiểu**, và **ClassCastException và giới hạn ép kiểu không hợp lệ** trình bày chi tiết các trường hợp này.

## 9. Kiểu trừu tượng trong collection và generics

Java thường khuyến khích sử dụng interface làm kiểu khai báo collection:

```java
import java.util.ArrayList;
import java.util.List;

List<String> names = new ArrayList<>();
names.add("Lan");
names.add("Minh");
```

`List` là interface, `ArrayList` là class triển khai. Caller làm việc qua các phương thức được khai báo bởi `List`; có thể thay implementation trong điều kiện hợp đồng và yêu cầu ứng dụng cho phép.

Cũng có thể khai báo một collection chứa các đối tượng có nhiều implementation:

```java
List<Notifier> channels = new ArrayList<>();
channels.add(new EmailNotifier());
channels.add(new SmsNotifier());

for (Notifier channel : channels) {
    System.out.println(channel.channel());
}
```

Các ví dụ trên là những đoạn lệnh minh họa, phải đặt trong phạm vi phù hợp và có các class `Notifier`, `EmailNotifier`, `SmsNotifier` đã khai báo; chưa phải chương trình chạy độc lập.

**Lưu ý quan trọng về generic invariance:** dù `EmailNotifier` là subtype của `Notifier`, **`List<EmailNotifier>` không phải subtype của `List<Notifier>`**. Nếu một phương thức chỉ đọc và gọi API của notifier, có thể cân nhắc tham số:

```java
static void showChannels(List<? extends Notifier> channels) {
    for (Notifier item : channels) {
        System.out.println(item.channel());
    }
}
```

`List<? extends Notifier>` chấp nhận danh sách của `Notifier` hoặc các subtype tương thích. Tuy nhiên, không thể thêm tùy ý một `new SmsNotifier()` vào danh sách đó vì kiểu phần tử cụ thể không được bảo đảm. Đây là cách generic bảo toàn type safety; **đa hình của phần tử không tự động biến các loại `List<T>` thành quan hệ subtype tương ứng**.

## 10. Lợi ích thiết kế và điều kiện để đa hình thực sự hữu ích

Khi chỉ phụ thuộc vào interface, ta có thể:

- **Thay implementation tại nơi khởi tạo:** cùng một service nhận kênh email hoặc SMS.
- **Truyền nhiều đối tượng khác nhau vào một API:** hàm `deliver(Notifier, ...)` không cần biết subtype.
- **Trả về một hợp đồng thống nhất:** factory trả `Notifier` dù nhánh lựa chọn tạo class nào.
- **Kiểm thử dễ hơn:** cung cấp một fake implementation ghi nhận tham số thay vì gửi thông báo thật.
- **Giới hạn điều mà caller biết:** các API đặc thù của class cụ thể không bị đưa thành dependency ngầm.

Nhưng **kiểu trừu tượng vẫn là một hợp đồng thực sự**. Hai class chỉ cùng chữ ký phương thức không tự trở thành subtype của một interface nếu không có quan hệ kiểu thích hợp (trừ các cơ chế khác theo quy tắc ngôn ngữ). Bản thân interface cũng không bảo đảm các implementation có cùng ý nghĩa nghiệp vụ. Ví dụ, nếu `send` hứa “gửi một lần”, một implementation gửi lặp nhiều lần có thể phá kỳ vọng dù vẫn biên dịch. Thiết kế đa hình cần sự tương thích cả về **kiểu** lẫn **hành vi** (nguyên tắc thay thế).

Không phải lúc nào cũng khai báo mọi biến bằng supertype cao nhất như `Object`. Nếu dùng `Object`, compiler không biết đến `send`; muốn gọi lại phải kiểm tra và ép kiểu. Hãy chọn **kiểu trừu tượng nhỏ nhất nhưng đầy đủ những thao tác caller thực sự cần**, đồng thời giữ hợp đồng rõ ràng.

## 11. Những lỗi thường gặp

| Lỗi hoặc ngộ nhận | Vì sao sai / cách sửa |
| --- | --- |
| `Notifier n = new Notifier();` | Không thể khởi tạo trực tiếp interface; dùng `new EmailNotifier()` hoặc implementation khác. |
| `Shape s = new Shape();` | Abstract class không thể khởi tạo trực tiếp; dùng concrete subclass. |
| `Notifier n = new EmailNotifier(); n.onlyEmailFeature();` | `onlyEmailFeature` không có trong kiểu khai báo `Notifier`; chỉ gọi API hợp đồng hoặc dùng kiểu hẹp hơn khi thực sự cần. |
| `EmailNotifier n = chooseNotifier("email");` | Hàm khai báo kiểu trả về `Notifier`, không thể tự động gán vào biến subclass; dùng `Notifier n` hoặc kiểm tra kiểu trước khi cast. |
| Cho rằng biến kiểu interface luôn chứa cùng một implementation | Biến có thể lần lượt trỏ đến nhiều subtype; kiểu runtime của từng đối tượng vẫn cố định. |
| Cho rằng `implements` mặc nhiên cung cấp mọi method | Concrete class phải đáp ứng abstract methods còn thiếu; default method chỉ cung cấp implementation khi hợp lệ. |
| Viết nhiều overload nhận từng implementation chỉ để gọi cùng hợp đồng | Có thể gom thành một phương thức nhận interface phù hợp. |
| Ép kiểu xuống class triển khai mà không kiểm tra | Có thể ném `ClassCastException`; dùng `instanceof` khi cần hoặc thiết kế lại API. |
| Gán `List<EmailNotifier>` cho `List<Notifier>` | Generics invariant; cân nhắc `List<? extends Notifier>` nếu chỉ cần đọc. |
| Cho rằng kiểu `List` bảo đảm đối tượng được phép thêm/xóa | Hợp đồng và implementation có thể không hỗ trợ sửa; cần ghi rõ yêu cầu mutability. |

## 12. Tự kiểm tra kiến thức

**1. `Notifier n = new EmailNotifier();` có tạo đối tượng thuộc kiểu `Notifier` hay `EmailNotifier`?**  
Tạo một đối tượng `EmailNotifier`. `Notifier` là kiểu khai báo của tham chiếu và hợp đồng mà caller nhìn thấy.

**2. Nếu `deliver(Notifier notifier)` chỉ gọi `notifier.send(...)`, truyền `SmsNotifier` có hợp lệ không?**  
Có, miễn `SmsNotifier implements Notifier` và đáp ứng các phương thức bắt buộc. Đó là đa hình qua tham số.

**3. Phương thức khai báo `Notifier create()` có thể trả đối tượng `new EmailNotifier()` không?**  
Có, vì `EmailNotifier` là subtype của `Notifier`. Caller nhận kiểu tĩnh `Notifier` khi gọi qua chữ ký đó.

**4. Vì sao `new Shape()` không hợp lệ nhưng `Shape x = new Square(2.0);` hợp lệ?**  
`Shape` là abstract class nên không khởi tạo trực tiếp; `Square` là concrete subclass và có thể được gán cho tham chiếu `Shape`.

**5. Có thể gọi phương thức chỉ nằm trong `EmailNotifier` qua biến khai báo kiểu `Notifier` không?**  
Không gọi trực tiếp. Compiler chỉ cho truy cập những thành viên thuộc API của `Notifier`. Có thể kiểm tra và downcast, nhưng nên cân nhắc lại thiết kế nếu thao tác đó xuất hiện thường xuyên.

**6. `List<EmailNotifier>` có gán trực tiếp cho `List<Notifier>` được không?**  
Không. Generics của Java invariant. Nếu chỉ cần đọc các đối tượng dưới góc nhìn `Notifier`, một tham số `List<? extends Notifier>` có thể phù hợp.

**7. Khi thay `EmailNotifier` bằng `SmsNotifier` trong service, có cần sửa chữ ký constructor `NotificationService(Notifier notifier)` không?**  
Không. Cả hai class đều thực hiện cùng hợp đồng `Notifier`. Phần khởi tạo chọn implementation, còn service gọi API chung.

Hãy nhớ ba mẫu cốt lõi: **biến `Notifier n`**, **tham số `void send(Notifier n)`**, **kiểu trả về `Notifier create()`**. Mỗi mẫu cho phép làm việc bằng một hợp đồng trừu tượng, trong khi đối tượng runtime được cung cấp bởi class cụ thể tương thích; đây là nền tảng sử dụng đa hình một cách có kiểm soát trong Java.