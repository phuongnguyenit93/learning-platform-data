# Vì sao phương thức `abstract` không thể kết hợp với `private`, `static` hoặc `final` trong Java?

## 1. Bản chất của một phương thức `abstract`

Trong Java, một phương thức trừu tượng (`abstract method`) **khai báo một hợp đồng nhưng không có phần thân**, và yêu cầu lớp con cụ thể cung cấp phần triển khai (trực tiếp hoặc thông qua một triển khai đã được kế thừa hợp lệ). Cơ chế quan trọng ở đây là **ghi đè phương thức instance (`override`)** và **đa hình lúc chạy (`dynamic dispatch`)**.

Ví dụ:

```java
abstract class Animal {
    public abstract String sound();
}

final class Dog extends Animal {
    @Override
    public String sound() {
        return "Woof";
    }
}
```

Đây là khai báo các lớp hợp lệ, nhưng không phải một chương trình độc lập có `main`. `Animal` xác định rằng mọi lớp con cụ thể phải có cách trả về âm thanh. `Dog` hiện thực hợp đồng đó bằng cách override `sound()`.

Từ bản chất này, ta rút ra ba yêu cầu đối với một phương thức `abstract` của class:

1. Phương thức phải **có khả năng được lớp con ghi đè** theo quy tắc truy cập của Java.
2. Nó phải là **phương thức instance**, vì override và dynamic dispatch làm việc với phương thức instance.
3. Nó không được **cấm lớp con ghi đè**.

Ba từ khóa `private`, `static`, `final` lần lượt xung đột với những yêu cầu trên. Java phát hiện sự kết hợp không hợp lệ ngay **lúc biên dịch**, trước khi chạy chương trình.

> **Phạm vi cần phân biệt:** Quy tắc “không kết hợp” ở đây áp dụng cho **khai báo một phương thức `abstract`**. Một **`abstract class`** vẫn có thể chứa trường `private`, phương thức `private`, phương thức `static` và phương thức `final` bình thường, miễn những phương thức đó có cách khai báo hợp lệ. Không nên nhầm quy tắc modifier của method với modifier của class.

## 2. Vì sao `abstract private` là mâu thuẫn?

Một phương thức `private` chỉ được truy cập trong phạm vi lớp khai báo nó; phương thức `private` **không được kế thừa và không thể bị lớp con override**. Ngược lại, `abstract` cần một triển khai do lớp con cung cấp theo quan hệ kế thừa/override. Nếu đặt cả hai trên cùng một phương thức, lớp con không có phương thức trừu tượng khả kiến để thực hiện hợp đồng đó.

**Ví dụ cố ý sai, không biên dịch được:**

```java
abstract class Parent {
    private abstract void process(); // LỖI: private và abstract
}
```

Cách đúng là chọn phạm vi truy cập cho phép lớp con triển khai, thường là `protected` hoặc `public`:

```java
abstract class Parent {
    protected abstract void process();
}

final class Child extends Parent {
    @Override
    protected void process() {
        System.out.println("Processing");
    }
}
```

Nếu hợp đồng cần được mã bên ngoài gọi trực tiếp, dùng `public abstract`. Nếu chỉ dành cho lớp cha và lớp con cộng tác, `protected abstract` thường phù hợp.

### Phương thức trùng tên trong lớp con chưa chắc là override

Xét ví dụ hợp lệ sau:

```java
class Base {
    private void ping() {
        System.out.println("Base");
    }

    void runBasePing() {
        ping();
    }
}

class Derived extends Base {
    public void ping() {
        System.out.println("Derived");
    }
}
```

`Derived.ping()` **không override** `Base.ping()`; đó là phương thức riêng của `Derived` có cùng tên và danh sách tham số. Lời gọi `ping()` bên trong `Base.runBasePing()` vẫn trỏ tới phương thức `private` của `Base`. Đặt `@Override` trên `Derived.ping()` trong trường hợp này sẽ báo lỗi biên dịch vì thực tế không có phương thức được override. Chính vì vậy một `private abstract` không thể tạo ra hợp đồng kế thừa như mong muốn.

**Khi nào vẫn dùng `private` trong abstract class?** Dùng cho các bước xử lý nội bộ đã có thân phương thức hoặc cho dữ liệu chỉ lớp nền được quyền thao tác. Bước bắt buộc lớp con tùy biến cần được khai báo `protected abstract` hoặc `public abstract` thay vì `private abstract`.

## 3. Vì sao `abstract static` là mâu thuẫn?

Một phương thức `static` **thuộc về lớp**, được phân giải theo kiểu hoặc tên lớp tại lúc biên dịch; nó không tham gia dynamic dispatch dựa trên đối tượng như phương thức instance.

Một phương thức `abstract` lại cần lớp con cung cấp implementation thông qua **override phương thức instance**. Java cho phép lớp con **che khuất (`hide`)** một phương thức static bằng một phương thức static cùng chữ ký theo các điều kiện hợp lệ, nhưng **hiding không phải overriding**. Vì vậy không tồn tại “static abstract method” của class theo kiểu lớp con phải override.

**Ví dụ cố ý sai, không biên dịch được:**

```java
abstract class Parent {
    public static abstract void load(); // LỖI: static và abstract
}
```

Để định nghĩa một hành vi mà mọi đối tượng con phải cung cấp, bỏ `static`:

```java
abstract class Parent {
    public abstract void load();
}

final class Child extends Parent {
    @Override
    public void load() {
        System.out.println("Loaded");
    }
}
```

Để định nghĩa một **tiện ích dùng chung không cần đối tượng**, bỏ `abstract` và giữ một phương thức `static` có thân:

```java
abstract class Parent {
    public static String formatCode(int code) {
        return "CODE-" + code;
    }
}
```

Gọi `Parent.formatCode(7)` sẽ cho chuỗi `"CODE-7"`. Lớp nền dù là `abstract` vẫn được phép chứa và cung cấp phương thức static.

### Phân biệt overriding và static hiding bằng chương trình chạy được

Lưu ví dụ dưới vào `StaticHidingDemo.java`:

```java
class Base {
    static String label() {
        return "Base";
    }

    String describe() {
        return "Base instance";
    }
}

class Derived extends Base {
    static String label() {
        return "Derived";
    }

    @Override
    String describe() {
        return "Derived instance";
    }
}

public class StaticHidingDemo {
    public static void main(String[] args) {
        Base value = new Derived();
        System.out.println(Base.label());
        System.out.println(Derived.label());
        System.out.println(value.describe());
        System.out.println(value.label()); // Hợp lệ nhưng không nên gọi static qua biến
    }
}
```

Chạy:

```bash
javac StaticHidingDemo.java
java StaticHidingDemo
```

Kết quả chuẩn:

```text
Base
Derived
Derived instance
Base
```

Giải thích: `value.describe()` gọi implementation của **đối tượng thực tế `Derived`** nhờ overriding. Trong khi đó `value.label()` được chọn theo **kiểu khai báo `Base` của biến**, nên trả `"Base"`; cách viết này dễ gây nhầm nên hãy gọi rõ `Base.label()` hoặc `Derived.label()`. Đó là lý do dùng `static` không thể thay hợp đồng `abstract` vốn cần đa hình.

## 4. Vì sao `abstract final` là mâu thuẫn?

`final` đặt trên một phương thức instance nghĩa là **lớp con không được override phương thức ấy**. Trong khi đó, một phương thức `abstract` chưa có thân và đòi hỏi lớp con cung cấp implementation. Hai yêu cầu đối nghịch trực tiếp: một bên **bắt buộc được triển khai bằng override**, bên kia **cấm override**.

**Ví dụ cố ý sai, không biên dịch được:**

```java
abstract class Parent {
    public abstract final void save(); // LỖI: abstract và final
}
```

Nếu muốn lớp con **bắt buộc triển khai khác nhau**, dùng `abstract`, không dùng `final`:

```java
abstract class Parent {
    public abstract void save();
}
```

Nếu muốn có **một triển khai cố định, cấm lớp con thay đổi**, dùng `final` với **thân phương thức**:

```java
abstract class Parent {
    public final void save() {
        System.out.println("Saved by parent");
    }
}
```

Việc lớp `Parent` là `abstract` không làm cho `save()` trở thành abstract. Trong abstract class, phương thức `final` là một phương thức **đã triển khai**. Lớp con có thể kế thừa và gọi nó, nhưng không thể override nó.

### Mẫu thiết kế phối hợp đúng: final điều phối, abstract tùy biến

Một kỹ thuật hữu ích là **Template Method**: lớp cha dùng phương thức `final` để cố định thứ tự xử lý, rồi gọi một hoặc nhiều bước `abstract` cho lớp con thực hiện. Nhờ đó, **quy trình chung ổn định** mà **hành vi cụ thể vẫn mở rộng được**.

Ví dụ:

```java
abstract class Task {
    public final void run() {
        System.out.println("Start");
        perform();
        System.out.println("Finish");
    }

    protected abstract void perform();
}

final class EmailTask extends Task {
    @Override
    protected void perform() {
        System.out.println("Send email");
    }
}
```

`Task.run()` không thể bị lớp con thay thế, nhưng bước `perform()` được triển khai khác nhau. Đây là cách phối hợp `abstract` và `final` **trên hai phương thức khác nhau**, hoàn toàn hợp lệ. Đoạn này chỉ khai báo lớp; ví dụ chương trình độc lập xuất hiện ở phần tiếp theo.

## 5. Ví dụ Java 17+ hoàn chỉnh: dùng `private`, `static`, `final` đúng chỗ trong một abstract class

Lưu **toàn bộ** mã sau vào tệp `Demo.java` (không đặt khai báo `package`):

```java
abstract class Payment {
    private final int amount;

    protected Payment(int amount) {
        if (amount <= 0) {
            throw new IllegalArgumentException("Amount must be positive");
        }
        this.amount = amount;
    }

    public final void execute() {
        logStart();
        process(amount);
        System.out.println("Done");
    }

    private void logStart() {
        System.out.println("Start payment");
    }

    protected abstract void process(int amount);

    public static String unit() {
        return "VND";
    }
}

final class CardPayment extends Payment {
    CardPayment(int amount) {
        super(amount);
    }

    @Override
    protected void process(int amount) {
        System.out.println("Charge card: " + amount + " " + Payment.unit());
    }
}

public class Demo {
    public static void main(String[] args) {
        Payment payment = new CardPayment(500);
        payment.execute();
    }
}
```

Chạy bằng **JDK 17+** tại thư mục chứa tệp:

```bash
javac Demo.java
java Demo
```

**Stdout chính xác:**

```text
Start payment
Charge card: 500 VND
Done
```

Quan sát từng thành phần:

- `Payment` là **abstract class**: không tạo `new Payment(...)` trực tiếp, nhưng constructor vẫn được gọi khi tạo `CardPayment`.
- `private final int amount` là **trường dữ liệu instance** được giữ kín và không thể gán lại sau khi khởi tạo thành công; `final` trên trường khác với `final` trên phương thức.
- `private void logStart()` có **phần thân**, phục vụ nội bộ lớp nền; không có nhu cầu cho lớp con override.
- `static String unit()` (ở đây là `public static`) là **phương thức dùng chung**, gọi qua tên lớp `Payment.unit()`, không cần đối tượng.
- `final void execute()` (ở đây là `public final`) cố định trình tự **ghi log → xử lý → thông báo hoàn tất**.
- `protected abstract void process(int amount)` không có thân, nên `CardPayment` phải cung cấp cách xử lý cụ thể.
- Biến `Payment payment` giữ đối tượng `CardPayment`. Khi `execute()` gọi `process(amount)`, Java chọn implementation ở `CardPayment` theo **đối tượng thực tế**.

**Ý nghĩa thiết kế:** ba từ khóa `private`, `static`, `final` đều có ích trong một abstract class. Vấn đề chỉ xuất hiện khi đem một trong ba kết hợp **ngay trên phương thức `abstract` cần override**.

## 6. Quy tắc compiler và những trường hợp dễ nhầm

| Khai báo | Hợp lệ? | Lý do |
| --- | --- | --- |
| `protected abstract void work();` trong abstract class | Có | Lớp con có thể override |
| `public abstract void work();` trong abstract class | Có | Hợp đồng public, có thể override |
| `private abstract void work();` | Không | Private không được override |
| `static abstract void work();` | Không | Static tham gia hiding, không tham gia overriding |
| `final abstract void work();` | Không | Final cấm override |
| `private void helper() { ... }` trong abstract class | Có | Hàm nội bộ đã có thân |
| `static void helper() { ... }` trong abstract class | Có | Hàm cấp lớp đã có thân |
| `final void run() { ... }` trong abstract class | Có | Hàm cụ thể không cho override |
| `private final int id;` trong abstract class | Có | Field riêng; phải được gán đúng quy tắc final |
| `abstract final class C { }` | Không | Abstract class cần có khả năng được kế thừa để tạo lớp con cụ thể; final class cấm kế thừa |

Lưu ý thêm về **cấp class**: `abstract static class Nested { ... }` là **hợp lệ khi `Nested` là một lớp thành viên `static` bên trong lớp khác**. Từ `static` ở đây mô tả **nested class** không gắn với instance của lớp bao ngoài, không phải một `static abstract method`. Không được từ quy tắc cấm ở cấp phương thức suy ra mọi cách viết có `abstract` và `static` đều sai.

### Interface có làm ba quy tắc này thay đổi không?

**Không.** Những điểm sau cần được tách bạch:

1. Trong interface, một phương thức không có thân theo kiểu thông thường mặc nhiên là **`public abstract`**; có thể viết tường minh `public abstract void send();`.
2. Interface hiện đại cho phép **phương thức `default` có thân**, **phương thức `static` có thân**, và từ Java 9 có **phương thức `private` có thân** để dùng nội bộ interface. Không có nghĩa là `private abstract` hoặc `static abstract` được cho phép.
3. Ví dụ hợp lệ về các loại phương thức khác nhau trong cùng một interface:

```java
interface MessageService {
    void send(String message); // public abstract theo ngầm định

    default void sendWelcome() {
        send(prefix() + "Welcome");
    }

    static String version() {
        return "1.0";
    }

    private String prefix() {
        return "[Message] ";
    }
}
```

Đây là khai báo interface hợp lệ trên Java 17+, không phải ứng dụng có `main`. `prefix()` là helper nội bộ đã có thân; `version()` được gọi bằng `MessageService.version()`; `send(String)` là hợp đồng phải được implementation đáp ứng. Interface không cho phép đặt `final` lên một phương thức interface; việc bổ sung `default` cũng không khiến `abstract final` trở nên hợp lệ.

### Nếu lớp con vẫn là abstract thì sao?

Một abstract subclass **có thể chưa triển khai** phương thức abstract mà nó kế thừa:

```java
abstract class Job {
    protected abstract void perform();
}

abstract class TimedJob extends Job {
    // Vẫn abstract, nên chưa bắt buộc triển khai perform().
}

final class ReportJob extends TimedJob {
    @Override
    protected void perform() {
        System.out.println("Create report");
    }
}
```

Nghĩa vụ triển khai được hoàn tất trước khi tạo **lớp cụ thể** `ReportJob`. Điều này không làm thay đổi quy tắc: phương thức `perform()` vẫn phải có khả năng override, vì cuối cùng một lớp cụ thể cần cung cấp implementation. Một lớp con cụ thể không thực hiện đủ hợp đồng sẽ bị compiler từ chối.

## 7. Nhận diện và sửa lỗi trong thực tế

Khi thấy compiler báo tổ hợp modifier không hợp lệ, hãy xác định **ý định thiết kế của phương thức** trước:

**Trường hợp A — Lớp con bắt buộc cung cấp hành vi.** Khai báo phương thức **instance `protected abstract` hoặc `public abstract`**; bỏ `private`, `static`, `final`. Lớp chứa phương thức phải là abstract class (hoặc dùng khai báo phương thức trừu tượng hợp lệ trong interface).

**Trường hợp B — Chỉ là helper nội bộ.** Giữ `private`, cung cấp **thân phương thức** và bỏ `abstract`. Nếu lớp con phải tùy biến một bước, tách riêng một hook `protected abstract` có chủ ý; tránh lộ toàn bộ helper.

**Trường hợp C — Hàm tiện ích cấp lớp.** Giữ `static`, cung cấp **thân phương thức** và bỏ `abstract`. Nếu yêu cầu hành vi thay đổi tùy implementation lúc chạy, thiết kế lại thành **instance method** hoặc một đối tượng chiến lược/interface; static hiding không đáp ứng đa hình.

**Trường hợp D — Khung xử lý bắt buộc giữ nguyên.** Giữ phương thức điều phối `final` **có thân**; để phần cần mở rộng trong các phương thức `abstract` khác. Có thể áp dụng Template Method như ví dụ `Payment.execute()`/ `Payment.process()`.

**Trường hợp E — Vừa muốn `abstract` vừa muốn `final` trên class.** Thiết kế lại: một class không thể vừa yêu cầu có lớp con để hoàn chỉnh hợp đồng trừu tượng vừa cấm mọi lớp kế thừa nó. Nếu muốn đóng hệ phân cấp nhưng cho phép một số lớp con, cân nhắc **sealed class** (Java 17+) theo ràng buộc cho phép kế thừa có kiểm soát; đây là cơ chế riêng, không cho phép viết `abstract final class`.

## 8. Câu hỏi kiểm tra

1. Vì sao một phương thức `private` trong lớp cha không thể bị lớp con override, dù lớp con khai báo phương thức cùng tên?
2. Phương thức `static` khác phương thức instance ở thời điểm Java lựa chọn implementation như thế nào?
3. Vì sao `final` và `abstract` không thể cùng xuất hiện trên một phương thức?
4. Trong ví dụ `Payment`, tại sao `execute()` được `final` mà `process()` vẫn `abstract`?
5. `abstract class` có được chứa `private`, `static`, `final` không? Hãy đưa ra một ví dụ hợp lệ cho mỗi loại.
6. Một phương thức `private` có thân trong interface Java 17 có trái với quy tắc cấm `private abstract` không?

**Đáp án ngắn:** (1) `private` không được kế thừa/override; khai báo trùng tên ở lớp con là phương thức riêng. (2) Static được phân giải theo lớp/kiểu tại biên dịch; instance override dùng kiểu thực tế lúc chạy. (3) `abstract` đòi override, `final` cấm override. (4) Lớp cha bảo vệ khung quy trình và cho lớp con triển khai đúng bước tùy biến. (5) Có: `private void helper() { }`, `static void util() { }`, `final void run() { }` bên trong abstract class. (6) Không, vì phương thức `private` của interface **có thân** và phục vụ logic nội bộ, không phải hợp đồng abstract.

Ghi nhớ mối quan hệ cốt lõi: **`abstract` cần một phương thức instance có thể được lớp con override; `private` ngăn override, `static` không được override, còn `final` cấm override.**