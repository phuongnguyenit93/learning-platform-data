# Phân biệt lớp cụ thể với lớp trừu tượng trong Java OOP

Một hệ thống có thể hỗ trợ nhiều cách gửi thông báo: email, SMS, thông báo trong ứng dụng. Chúng đều phải kiểm tra dữ liệu đầu vào, nhưng cách gửi thực tế khác nhau. Trong Java, **lớp trừu tượng (abstract class)** giúp mô tả phần chung và những hành vi mà lớp con phải hoàn thiện; **lớp cụ thể (concrete class)** có đủ triển khai để có thể tạo đối tượng và thực hiện công việc.

Điều cốt lõi không phải “lớp nào tốt hơn”, mà là **vai trò của từng lớp trong thiết kế**:

- Lớp trừu tượng mô tả một kiểu đối tượng còn *chưa hoàn chỉnh để dùng trực tiếp*; nó có thể cung cấp mã nguồn và trạng thái chung.
- Lớp cụ thể cung cấp triển khai hoàn chỉnh đối với mọi phương thức trừu tượng còn lại và có thể được khởi tạo bằng `new` nếu constructor có thể truy cập.
- Mã sử dụng có thể lập trình theo kiểu lớp cha trừu tượng, còn đối tượng thực tế là instance của lớp con cụ thể.

## 1. Nhận diện nhanh qua cú pháp

~~~java
// Lớp trừu tượng: không tạo instance trực tiếp bằng new Vehicle().
abstract class Vehicle {
    abstract void move(); // Chưa có phần thân
}

// Lớp cụ thể: đã triển khai hành vi còn thiếu.
class Bicycle extends Vehicle {
    @Override
    void move() {
        System.out.println("Đạp xe");
    }
}
~~~

~~~java
Vehicle vehicle = new Bicycle(); // Hợp lệ
vehicle.move();                   // In: Đạp xe

// Vehicle v = new Vehicle();     // Lỗi biên dịch
Bicycle bicycle = new Bicycle();  // Hợp lệ
~~~

`vehicle` có **kiểu khai báo** là `Vehicle`, nhưng đối tượng được tạo bằng `new Bicycle()` là một **Bicycle cụ thể**. Khi gọi phương thức instance được override, Java chọn cách triển khai thích hợp với kiểu thực tế của đối tượng (đa hình động).

Không cần có từ khóa `concrete` trong Java. Một lớp **không khai báo `abstract`**, đáp ứng đầy đủ hợp đồng các phương thức trừu tượng mà nó kế thừa và đủ điều kiện tạo instance, được gọi là lớp cụ thể.

| Tiêu chí | Lớp trừu tượng | Lớp cụ thể |
| --- | --- | --- |
| Khai báo | Có `abstract class` | `class` không có `abstract` |
| `new` trực tiếp tên lớp | Không | Có, nếu constructor/phạm vi truy cập cho phép |
| Có phương thức chưa triển khai (`abstract method`) | Có thể có hoặc không | Không thể còn phương thức abstract chưa triển khai |
| Có field/constructor/phương thức đã triển khai | Có | Có |
| Được kế thừa | Có, nếu không bị chặn bởi điều kiện khác | Có thể, trừ khi là `final` |
| Đóng vai trò kiểu tham chiếu | Có | Có |
| Dùng làm nền tảng cho đa hình | Thường xuyên | Có thể là lớp cha hoặc lớp con |

**Hai điểm hay bị hiểu sai:** lớp trừu tượng **không bắt buộc** phải chứa một phương thức `abstract`; và lớp cụ thể **không bắt buộc** có phương thức do chính nó khai báo nếu đã kế thừa đủ triển khai cần thiết.

## 2. Ví dụ hoàn chỉnh: chuẩn hóa hành vi gửi thông báo

Bài toán: mỗi kênh đều cần kiểm tra `recipientId` và `content` trước khi gửi. Email và SMS lại có cách xử lý riêng. Ta đặt quy trình chung ở lớp trừu tượng và yêu cầu từng lớp cụ thể cài đặt bước gửi.

Lưu vào **`NotificationDemo.java`**. Mã tương thích Java 11+, chỉ dùng thư viện chuẩn:

~~~java
import java.util.List;
import java.util.Objects;

public class NotificationDemo {

    // Abstract class: biểu diễn một kênh thông báo chưa xác định cách gửi.
    static abstract class NotificationChannel {
        private final String channelName;

        protected NotificationChannel(String channelName) {
            this.channelName = Objects.requireNonNull(
                    channelName, "channelName");
        }

        public final String getChannelName() {
            return channelName;
        }

        // Quy trình chung; final để lớp con không bỏ qua bước kiểm tra.
        public final void send(String recipientId, String content) {
            String id = Objects.requireNonNull(
                    recipientId, "recipientId").trim();
            String message = Objects.requireNonNull(
                    content, "content").trim();

            if (id.isEmpty() || message.isEmpty()) {
                throw new IllegalArgumentException(
                        "Người nhận và nội dung không được rỗng");
            }

            deliver(id, message); // Chọn triển khai của lớp con thực tế.
        }

        // Hợp đồng bắt buộc: lớp cụ thể phải triển khai.
        protected abstract void deliver(
                String recipientId, String content);
    }

    static final class EmailChannel extends NotificationChannel {
        EmailChannel() {
            super("EMAIL");
        }

        @Override
        protected void deliver(String recipientId, String content) {
            System.out.println("[EMAIL] tới " + recipientId
                    + ": " + content);
        }
    }

    static final class SmsChannel extends NotificationChannel {
        SmsChannel() {
            super("SMS");
        }

        @Override
        protected void deliver(String recipientId, String content) {
            System.out.println("[SMS] tới " + recipientId
                    + ": " + content);
        }
    }

    public static void main(String[] args) {
        List<NotificationChannel> channels = List.of(
                new EmailChannel(),
                new SmsChannel()
        );

        for (NotificationChannel channel : channels) {
            System.out.println("Đang dùng: "
                    + channel.getChannelName());
            channel.send("KH-001", "Đơn hàng đã xác nhận");
        }

        // new NotificationChannel("UNKNOWN"); // KHÔNG biên dịch
    }
}
~~~

~~~bash
javac NotificationDemo.java
java NotificationDemo
~~~

Kết quả:

~~~text
Đang dùng: EMAIL
[EMAIL] tới KH-001: Đơn hàng đã xác nhận
Đang dùng: SMS
[SMS] tới KH-001: Đơn hàng đã xác nhận
~~~

Ví dụ mô phỏng bằng console để quan sát OOP; `KH-001` là mã người nhận giả lập, chưa phải email/số điện thoại thực tế. Khi triển khai thật, lớp kênh sẽ ánh xạ mã người nhận sang thông tin liên hệ, gọi nhà cung cấp tương ứng và xử lý lỗi.

Trong đoạn mã, `NotificationChannel` cùng hai lớp con được đặt thành **lớp lồng `static`** để cả ví dụ nằm trong một file. Khi thiết kế dự án, chúng có thể tách thành các file riêng và vẫn giữ nguyên quan hệ kế thừa.

### Từng thành phần đang đóng vai trò gì?

**`NotificationChannel` là lớp trừu tượng:**

- Có field `private final String channelName` và constructor `protected` để lớp con khởi tạo phần chung.
- Định nghĩa đầy đủ `getChannelName()` và `send(...)`.
- `send(...)` chứa bước kiểm tra dữ liệu và gọi `deliver(...)`.
- Khai báo `protected abstract void deliver(...)`: biết *mỗi kênh phải gửi*, nhưng chưa biết *gửi bằng cách nào*.

**`EmailChannel` và `SmsChannel` là các lớp cụ thể:**

- Kế thừa dữ liệu và quy trình chung từ `NotificationChannel`.
- Gọi `super("EMAIL")` hoặc `super("SMS")` để khởi tạo phần lớp cha.
- Dùng `@Override` để triển khai `deliver(...)` theo cách của từng kênh.
- Có thể được tạo thành instance bằng `new EmailChannel()` và `new SmsChannel()`.

**`List<NotificationChannel>` thể hiện đa hình:**

- Danh sách giữ các tham chiếu khai báo theo **kiểu lớp cha trừu tượng**.
- Mỗi phần tử lại trỏ đến một đối tượng thuộc lớp con cụ thể.
- `channel.send(...)` gọi quy trình chung; bên trong, `deliver(...)` được dispatch tới `EmailChannel` hoặc `SmsChannel` tương ứng.

## 3. Theo dõi lời gọi bằng sequence diagram

~~~mermaid
sequenceDiagram
    actor App as Main
    participant Channel as NotificationChannel (API chung)
    participant Email as EmailChannel instance

    App->>Channel: send("KH-001", "Đơn hàng đã xác nhận")
    Note over Channel,Email: send() là phương thức chung final<br/>được thừa kế bởi EmailChannel
    Channel->>Channel: kiểm tra id và nội dung
    Channel->>Email: deliver(id, message) (dynamic dispatch)
    Email-->>Channel: hoàn tất
    Channel-->>App: hoàn tất
~~~

`Channel` trong sơ đồ là **vai trò lớp cha/API của lời gọi**; tại runtime, `send()` thực thi trên một đối tượng `EmailChannel` cụ thể. Không tồn tại một instance độc lập của `NotificationChannel` được tạo bởi `new NotificationChannel()`.

Đây là mẫu thiết kế **Template Method** ở dạng đơn giản: lớp cha sở hữu bộ khung quy trình (`send`), còn lớp con bổ sung một bước thay đổi (`deliver`). Không phải chương trình có lớp trừu tượng nào cũng bắt buộc áp dụng Template Method; đây chỉ là một cách sử dụng phù hợp.

## 4. “Abstract” ở cấp lớp và ở cấp phương thức

Cần tách hai khái niệm.

### Lớp abstract

~~~java
abstract class AuditService {
    void record(String message) {
        System.out.println("Audit: " + message);
    }
}
~~~

Lớp này **không có một phương thức abstract nào** nhưng vẫn là abstract vì đã được khai báo như vậy. Ta có thể muốn ngăn tạo một `AuditService` quá chung chung, chỉ cho phép khởi tạo các phiên bản có vai trò rõ ràng:

~~~java
class FileAuditService extends AuditService {
    // Kế thừa record(); không bắt buộc thêm phương thức mới.
}
~~~

`FileAuditService` là concrete dù không override gì:

~~~java
AuditService audit = new FileAuditService();
audit.record("Đăng nhập");
~~~

### Phương thức abstract

~~~java
abstract class Report {
    abstract String render(); // Không có phần thân phương thức.
}
~~~

Một lớp có phương thức instance `abstract` thì **bản thân lớp cũng phải khai báo `abstract`**. Lớp con có hai lựa chọn:

1. Triển khai tất cả phương thức abstract còn thiếu để trở thành lớp cụ thể.
2. Tiếp tục khai báo `abstract` nếu vẫn chưa triển khai đầy đủ.

~~~java
abstract class BaseReport {
    abstract String render();
}

abstract class BrandedReport extends BaseReport {
    // Vẫn chưa triển khai render(), nên phải là abstract.
}

class SalesReport extends BrandedReport {
    @Override
    String render() {
        return "Doanh thu tháng này";
    }
}
~~~

Cấp kế thừa có thể dài nhiều tầng; **chỉ những phương thức còn thiếu triển khai** mới là nghĩa vụ đối với lớp con concrete. Nếu một lớp cha khác đã cung cấp implementation hợp lệ, lớp con không phải viết lại bằng mọi giá.

## 5. Constructor và trạng thái chung trong lớp trừu tượng

Một hiểu nhầm phổ biến: “abstract class không tạo được đối tượng nên không có constructor”. Thực tế, **abstract class vẫn có constructor**; constructor của nó được gọi như một phần của việc tạo instance lớp con.

~~~java
abstract class Employee {
    private final String id;

    protected Employee(String id) {
        if (id == null || id.isBlank()) {
            throw new IllegalArgumentException("ID không hợp lệ");
        }
        this.id = id;
        System.out.println("Khởi tạo phần Employee");
    }

    public final String getId() {
        return id;
    }

    public abstract BigDecimal calculateSalary();
}

class SalariedEmployee extends Employee {
    private final BigDecimal monthlySalary;

    public SalariedEmployee(String id, BigDecimal salary) {
        super(id); // Phải khởi tạo phần Employee trước.
        this.monthlySalary = salary;
    }

    @Override
    public BigDecimal calculateSalary() {
        return monthlySalary;
    }
}
~~~

*Ví dụ này cần `import java.math.BigDecimal;` khi đặt trong file Java thực tế.*

Khi gọi `new SalariedEmployee("E001", ...)`, Java tạo **một đối tượng SalariedEmployee** có phần trạng thái được khai báo ở cả các lớp trong chuỗi kế thừa; constructor lớp cha chạy trước phần thân constructor lớp con. Nó **không tạo ra hai instance độc lập** gồm một `Employee` và một `SalariedEmployee`.

Field `private` của lớp cha không được lớp con truy cập trực tiếp, nhưng lớp con có thể sử dụng các phương thức `public`/`protected` phù hợp mà lớp cha công khai.

### Vì sao không nên gọi phương thức có thể override trong constructor?

Đối tượng lớp con có thể **chưa được khởi tạo đầy đủ** khi constructor lớp cha đang chạy. Nếu constructor cha gọi một phương thức overridable, Java vẫn có thể dispatch tới override ở lớp con trước khi các field của lớp con có giá trị mong muốn.

~~~java
abstract class Base {
    Base() {
        // Nguy hiểm nếu gọi overridableMethod() ở đây.
    }

    abstract void overridableMethod();
}
~~~

Trong thiết kế thực tế, hãy ưu tiên constructor xác lập invariant của phần chung, tránh để `this` thoát ra bên ngoài hoặc gọi hành vi lớp con khi đối tượng chưa hoàn thiện.

## 6. Các quy tắc Java thường gặp và lỗi biên dịch

| Quy tắc | Ví dụ không hợp lệ hoặc hợp lệ | Giải thích |
| --- | --- | --- |
| Không khởi tạo trực tiếp abstract class | `new NotificationChannel(...)` | Không có một lớp cụ thể để tạo instance |
| Abstract method phải có lớp chứa abstract | `class A { abstract void run(); }` | `A` phải thành `abstract class A` |
| Concrete class phải cài đặt abstract method còn lại | `class B extends A { }` khi `A.run()` abstract | Thiếu implementation |
| Abstract method không có body | `abstract void run() { }` | Khai báo abstract dùng dấu `;` |
| Không kết hợp `abstract` và `final` trên class | `abstract final class A` | Vừa yêu cầu lớp con, vừa ngăn kế thừa |
| Không kết hợp `abstract` với `private`, `static` hoặc `final` trên method | `private abstract void run();` | Abstract method phải có khả năng được override |
| Abstract class được có method `final` | `public final void send(...)` | Hợp lệ: cố định quy trình chung |
| Constructor không thể là abstract | `abstract A();` | Constructor dùng khởi tạo, không được override |
| Không giảm quyền truy cập khi override | Override `public` bằng `protected` | Bị lỗi vì làm hẹp hợp đồng |
| Concrete class có thể là `final` | `final class EmailChannel extends NotificationChannel` | Đã hoàn chỉnh và không cho kế thừa tiếp |

**Mẹo:** luôn đặt `@Override` trên phương thức định triển khai. Trình biên dịch sẽ phát hiện lỗi gõ sai tên hoặc chữ ký làm phương thức không thực sự override.

Ví dụ:

~~~java
abstract class Animal {
    abstract void makeSound();
}

// LỖI nếu bỏ comment và biên dịch:
// class Cat extends Animal {
//     void makesSound() { } // Sai tên; makeSound() vẫn chưa triển khai.
// }
~~~

Phiên bản đúng:

~~~java
class Cat extends Animal {
    @Override
    void makeSound() {
        System.out.println("Meo");
    }
}
~~~

Cẩn thận: không phải mọi `static` method trong một abstract class đều sai. Abstract class **có thể chứa phương thức static đã triển khai**. Điều không hợp lệ là khai báo một phương thức vừa `static` vừa `abstract`, vì static không tham gia override như phương thức instance.

## 7. Abstract class và interface khác nhau thế nào?

Để hiểu lý do cần abstract class, đôi khi cần đối chiếu với `interface`. Cả hai có thể mô tả một **hợp đồng** mà các lớp cụ thể phải đáp ứng, nhưng cơ chế kế thừa khác nhau.

| Tiêu chí | Abstract class | Interface |
| --- | --- | --- |
| Mục đích thường gặp | Chia sẻ trạng thái/cách triển khai giữa các lớp có quan hệ chặt | Mô tả năng lực mà nhiều lớp có thể cung cấp |
| Field của instance | Có thể giữ field mutable/immutable | Không có instance field; field khai báo trong interface là `public static final` |
| Constructor | Có | Không |
| Method đã triển khai | Có, mọi mức truy cập hợp lệ | Có `default`, `static`, `private` (tùy phiên bản Java) |
| Quan hệ một lớp Java | `extends` tối đa một class trực tiếp | `implements` nhiều interface |
| Tạo đối tượng trực tiếp | Không | Không |
| Khi cần chia sẻ mã chung | Phù hợp nếu có quan hệ kế thừa tự nhiên | Có thể dùng `default method`, hoặc composition với helper/service |

Ví dụ một năng lực độc lập:

~~~java
interface Trackable {
    String trackingCode();
}

abstract class Shipment {
    protected final String id;

    protected Shipment(String id) {
        this.id = id;
    }

    abstract int estimateDays();
}

class ExpressShipment extends Shipment implements Trackable {
    ExpressShipment(String id) {
        super(id);
    }

    @Override
    int estimateDays() {
        return 1;
    }

    @Override
    public String trackingCode() {
        return "EXP-" + id;
    }
}
~~~

`ExpressShipment` vừa kế thừa trạng thái chung của `Shipment`, vừa cam kết cung cấp năng lực `Trackable`. Nếu hai kiểu không thật sự có quan hệ “is-a” hợp lý, việc dùng composition (`has-a`) hoặc interface có thể linh hoạt hơn việc ép chúng kế thừa chung một abstract class.

## 8. Khi nào chọn lớp trừu tượng, khi nào chọn lớp cụ thể?

Cách lựa chọn thường đi từ **nhu cầu thật**:

- **Lớp cụ thể**: khi kiểu đã mô tả đủ hành vi và hợp lệ để tạo instance ngay. Ví dụ `EmailChannel` biết cách thực hiện `deliver`.
- **Lớp trừu tượng**: khi có các lớp con cùng bản chất, muốn chia sẻ trạng thái hoặc quy trình nhưng vẫn còn bước phải chuyên biệt hóa. Ví dụ `NotificationChannel` chứa quy trình `send` nhưng chưa biết `deliver`.
- **Interface**: khi muốn nhiều kiểu không nhất thiết cùng cây kế thừa cùng hỗ trợ một khả năng. Ví dụ `Trackable`.
- **Composition**: khi các chức năng cần thay đổi độc lập hoặc việc kế thừa dễ làm lớp cha/lớp con bị ràng buộc quá mức. Ví dụ `NotificationService` nhận một `NotificationChannel` qua constructor thay vì tự kế thừa lớp kênh.

Đặt một lớp thành `abstract` chỉ để “trông có vẻ OOP hơn” có thể khiến thiết kế phức tạp vô ích. Ngược lại, nếu nhiều lớp đang sao chép cùng một quy trình và chỉ thay một bước, một lớp trừu tượng rõ trách nhiệm có thể giảm lặp và tập trung quy tắc.

Một trường hợp đáng cân nhắc: nếu ứng dụng hiện chỉ có **một** loại thông báo và chưa có nhu cầu thay đổi, một lớp cụ thể đơn giản đôi khi đủ. Khi xuất hiện nhiều cách gửi với phần chung ổn định, mới cân nhắc trích xuất abstraction dựa trên sự giống nhau thực tế.

### Đa hình không đồng nghĩa “phải dùng abstract class”

Ví dụ:

~~~java
class Printer {
    void print() {
        System.out.println("Mặc định");
    }
}

class ColorPrinter extends Printer {
    @Override
    void print() {
        System.out.println("Có màu");
    }
}

Printer p = new ColorPrinter();
p.print(); // Có màu
~~~

`Printer` là lớp **cụ thể**, vẫn là kiểu cha để sử dụng đa hình. `abstract` chỉ thể hiện rằng bản thân lớp cha không được tạo instance trực tiếp hoặc có hợp đồng chưa hoàn chỉnh; không phải điều kiện bắt buộc để có kế thừa/override.

## 9. Bài tập xác định lỗi và giải thích kết quả

**Câu 1.** Đoạn sau có biên dịch không?

~~~java
abstract class A {
    void hello() { System.out.println("Hello"); }
}
class B extends A { }
~~~

**Đáp án:** Có. `B` kế thừa phương thức có triển khai `hello()` nên không có nghĩa vụ override; `B` là lớp cụ thể. `new B().hello()` in `Hello`.

**Câu 2.** Đoạn sau có biên dịch không?

~~~java
abstract class Shape {
    abstract double area();
}
class Square extends Shape { }
~~~

**Đáp án:** Không. `Square` chưa triển khai `area()` mà cũng không khai báo `abstract`. Cần override:

~~~java
class Square extends Shape {
    private final double side;

    Square(double side) {
        if (side <= 0) throw new IllegalArgumentException("side");
        this.side = side;
    }

    @Override
    double area() {
        return side * side;
    }
}
~~~

**Câu 3.** Trong `NotificationDemo`, `send()` là `final`. Tại sao `EmailChannel` vẫn thay đổi được cách gửi?

**Đáp án:** `send()` cố định các bước xử lý chung, nhưng gọi phương thức `deliver()` là abstract và được override ở lớp con. Gọi `deliver()` trên instance cụ thể sẽ dùng phần triển khai của lớp con tương ứng.

**Câu 4.** Biến `NotificationChannel channel = new SmsChannel();` có phải đang tạo một instance của lớp trừu tượng?

**Đáp án:** Không. Đối tượng thực tế là `SmsChannel`, còn biến tham chiếu `channel` được khai báo theo kiểu cha trừu tượng để dùng chung hợp đồng.

**Câu 5.** Một abstract class có field `private`, constructor, static method, final method và không có abstract method được không?

**Đáp án:** Được. `abstract` ở cấp lớp chỉ ngăn khởi tạo trực tiếp và cho phép nó là nền tảng của các lớp con; không bắt buộc phải có một phương thức abstract.

**Câu 6.** Thêm `PushChannel` cần thay đổi `NotificationChannel.send()` không?

**Gợi ý đáp án:** Thường không nếu quy trình chung vẫn đúng. Tạo lớp `PushChannel extends NotificationChannel`, gọi constructor cha và override `deliver()`. Đây là lợi ích của việc tách **phần chung ổn định** và **điểm mở rộng cụ thể**.

## Ghi nhớ để đọc thiết kế OOP

Hãy nhìn vào ba thứ: **`new` đang tạo đối tượng thuộc lớp nào**, **kiểu khai báo của biến tham chiếu là gì**, và **phương thức được gọi đã có implementation chung hay còn chờ override**.

Lớp trừu tượng cho phép tái sử dụng phần chung và áp đặt những điểm phải hoàn thiện; lớp cụ thể hiện thực hóa hợp đồng đó thành đối tượng chạy được. Thiết kế hiệu quả là tìm đúng nơi đặt hành vi chung, giữ phần thay đổi ở lớp triển khai và tránh tạo một cây kế thừa khi không có lý do rõ ràng.