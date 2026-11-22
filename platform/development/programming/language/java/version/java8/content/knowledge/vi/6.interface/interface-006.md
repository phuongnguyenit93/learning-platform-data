# Gọi triển khai mặc định bằng InterfaceName.super trong Java

## Mục tiêu

Từ Java 8, **interface có thể khai báo phương thức `default` có phần thân**, giúp bổ sung hành vi mặc định vào một hợp đồng mà không bắt mọi lớp triển khai tự viết lại phương thức ấy. Khi một lớp **override** phương thức `default`, hoặc khi hai interface đưa ra những triển khai mặc định xung đột, Java cung cấp cú pháp **`InterfaceName.super.method(...)`** để gọi một triển khai mặc định cụ thể từ một **superinterface hợp lệ**.

Đây vẫn là một phần của ngôn ngữ Java hiện hành. Nó có ích khi mở rộng hành vi có sẵn, giải quyết diamond conflict và duy trì một hợp đồng interface dễ hiểu.

Sau bài này, bạn sẽ:

- Viết và đọc đúng cú pháp `InterfaceName.super.method(arguments)`.
- Phân biệt `this.method()`, `super.method()` và `InterfaceName.super.method()`.
- Hiểu quy tắc kế thừa phương thức `default`, thứ tự ưu tiên giữa class và interface, và trường hợp hai interface xung đột.
- Gọi mặc định của interface trực tiếp trong lớp triển khai hoặc trong một **subinterface**.
- Biết giới hạn về **direct superinterface**, phạm vi instance và phương thức phải có triển khai `default` phù hợp.
- Kiểm tra được chương trình Java 17+ với kết quả đầu ra chính xác và tránh những ví dụ chỉ đúng trên giấy.

## 1. Vì sao Java có default method?

Trước tiên hãy xét interface chứa hợp đồng trừu tượng và một hành vi mặc định:

~~~java
interface Greeter {
    String name();

    default String greeting() {
        return "Xin chào, " + name();
    }
}
~~~

`name()` chưa có phần thân, nên lớp triển khai phải cung cấp hành vi. `greeting()` là phương thức **`default`** với phần thân. Một lớp có thể kế thừa nguyên triển khai:

~~~java
class BasicGreeter implements Greeter {
    @Override
    public String name() {
        return "Mai";
    }
}
~~~

Khi gọi:

~~~java
Greeter value = new BasicGreeter();
System.out.println(value.greeting());
~~~

kết quả:

~~~text
Xin chào, Mai
~~~

Phương thức `default` là **instance method**, được gọi trên đối tượng; nó không phải phương thức `static` và không phải đoạn mã chạy ngay khi khai báo interface. Trong ví dụ, `greeting()` gọi `name()` trên chính đối tượng đó.

Nếu lớp muốn thay đổi nội dung lời chào, nó có thể override `greeting()`. Nhưng khi chỉ muốn **bọc thêm** hành vi quanh triển khai mặc định, viết lại toàn bộ nội dung sẽ gây lặp mã và dễ lệch hợp đồng. Cú pháp `Greeter.super.greeting()` giải quyết nhu cầu này.

## 2. Cú pháp `InterfaceName.super.method(...)`

Dạng tổng quát:

~~~java
InterfaceName.super.methodName(argument1, argument2);
~~~

Ví dụ, lớp thực hiện `Greeter` và override `greeting()`:

~~~java
class FormalGreeter implements Greeter {
    @Override
    public String name() {
        return "Lan";
    }

    @Override
    public String greeting() {
        return Greeter.super.greeting() + "!";
    }
}
~~~

Nếu `Greeter` là **direct superinterface** của lớp như trên, lời gọi `Greeter.super.greeting()` chọn **triển khai `default greeting()` của `Greeter`**, sau đó thêm dấu chấm than.

~~~java
Greeter value = new FormalGreeter();
System.out.println(value.greeting());
~~~

Kết quả:

~~~text
Xin chào, Lan!
~~~

**Điểm cốt lõi:** bên trong triển khai `greeting()` của `FormalGreeter`, gọi `this.greeting()` sẽ gọi lại override hiện tại và gây đệ quy vô hạn. Dùng `Greeter.super.greeting()` là cách yêu cầu gọi trực tiếp **phiên bản mặc định** được kế thừa từ interface.

### So sánh ba cách gọi

| Cú pháp | Ý nghĩa | Lưu ý |
| --- | --- | --- |
| `this.greeting()` | Gọi phương thức trên đối tượng hiện tại bằng dynamic dispatch | Trong chính `greeting()` có thể gọi lại override và gây recursion |
| `super.greeting()` | Gọi triển khai đủ điều kiện từ **class superclass** theo quy tắc `super` của class | Không phải cách viết để chọn một interface mặc định theo tên |
| `Greeter.super.greeting()` | Gọi triển khai `default` phù hợp từ superinterface `Greeter` | Chỉ hợp lệ trong ngữ cảnh kế thừa/đủ điều kiện theo Java Language Specification |

`InterfaceName.super` không phải biến chứa một “đối tượng cha” riêng và cũng không thể được truyền như một giá trị tùy ý. Nó là thành phần đặc biệt của **super method invocation** tại vị trí code được phép.

## 3. Khi chỉ có một default method và lớp không override

Lớp triển khai **không bắt buộc** viết `InterfaceName.super` để dùng phương thức mặc định:

~~~java
interface Versioned {
    default String version() {
        return "v1";
    }
}

class Service implements Versioned {
}
~~~

Gọi `new Service().version()` là đủ. Java sẽ chọn phương thức kế thừa theo quy tắc method lookup.

Khi lớp muốn thay đổi lời trả về và **tái sử dụng triển khai mặc định**, mới cần:

~~~java
class CustomizedService implements Versioned {
    @Override
    public String version() {
        return Versioned.super.version() + "-custom";
    }
}
~~~

Cách này tránh sao chép giá trị `"v1"` vào lớp con. Nếu interface thay đổi logic mặc định trong một phiên bản API tương lai, lớp vẫn nhận thay đổi đó qua lời gọi `Versioned.super.version()`. Tuy nhiên, **đây cũng là sự phụ thuộc vào hành vi default**: hãy đánh giá tương thích nghiệp vụ khi nâng cấp thư viện.

## 4. Diamond conflict: hai interface cùng có default method

Một trường hợp rất thực tế là một lớp triển khai hai interface không có quan hệ subtype với nhau, nhưng **cùng cung cấp default method có chữ ký trùng nhau**:

~~~java
interface EmailChannel {
    default String channel() {
        return "EMAIL";
    }
}

interface SmsChannel {
    default String channel() {
        return "SMS";
    }
}
~~~

Nếu khai báo:

~~~java
// Không hợp lệ: có hai default method channel() xung đột.
// class NotificationChannel implements EmailChannel, SmsChannel {
// }
~~~

compiler từ chối lớp cụ thể vì không thể tùy ý chọn `EmailChannel.channel()` hay `SmsChannel.channel()`. **Java không “chọn interface bên trái” hoặc bên phải trong `implements`.**

### Override và chọn rõ triển khai mong muốn

~~~java
class NotificationChannel implements EmailChannel, SmsChannel {
    @Override
    public String channel() {
        return EmailChannel.super.channel()
                + "+" + SmsChannel.super.channel();
    }
}
~~~

Lúc này:

~~~java
System.out.println(new NotificationChannel().channel());
~~~

Kết quả:

~~~text
EMAIL+SMS
~~~

Compiler biết hai interface đều là **direct superinterfaces** của lớp, đồng thời mỗi interface cung cấp một default method phù hợp. Lớp đã override để định nghĩa quy tắc xử lý xung đột: ghép hai kênh theo đúng thứ tự mong muốn.

### Không bắt buộc gọi cả hai

Bạn hoàn toàn có thể quyết định một trong hai hành vi là chủ đạo:

~~~java
class EmailPreferredChannel implements EmailChannel, SmsChannel {
    @Override
    public String channel() {
        return EmailChannel.super.channel();
    }
}
~~~

Điểm bắt buộc là **lớp phải giải quyết xung đột về mặt ngôn ngữ**; cách chọn một nhánh, ghép cả hai hoặc viết một implementation mới là quyết định thiết kế theo nghiệp vụ.

**Không biến `InterfaceName.super` thành mẹo né contract.** Nếu hai interface biểu diễn ý nghĩa khác nhau dù có cùng tên phương thức, việc kết hợp kết quả một cách máy móc có thể sai. Đọc Javadoc và xác định mục đích thật của từng default method.

## 5. Quy tắc ưu tiên của Java: class thắng interface

Java có quy tắc quan trọng thường diễn đạt là **class wins**. Khi một phương thức instance phù hợp đã được triển khai ở class hierarchy và một interface đồng thời cung cấp default method cùng chữ ký, **phiên bản từ class** thường là phiên bản được lựa chọn.

Ví dụ:

~~~java
class BasePrinter {
    public String header() {
        return "CLASS";
    }
}

interface HeaderProvider {
    default String header() {
        return "INTERFACE";
    }
}

class DerivedPrinter extends BasePrinter implements HeaderProvider {
}
~~~

Gọi:

~~~java
System.out.println(new DerivedPrinter().header());
~~~

Kết quả:

~~~text
CLASS
~~~

**Không cần override** trong `DerivedPrinter` vì phương thức concrete từ class `BasePrinter` giải quyết hợp đồng `header()`. Vì vậy không nên nghĩ rằng interface có `default` sẽ ghi đè phương thức class đã tồn tại.

Cũng cần phân biệt **class thắng interface** với tình huống có **hai default methods thuộc hai interface ngang hàng**: ở trường hợp thứ hai, class thường phải override như ví dụ `NotificationChannel`.

### Khi có nhiều interface liên quan kế thừa

Nếu một subinterface override default của interface cha, **phiên bản cụ thể hơn theo quan hệ kế thừa** thường là phiên bản được kế thừa; Java không xem mọi default method trong toàn bộ cây kế thừa như những lựa chọn ngang hàng.

Ví dụ:

~~~java
interface ParentPolicy {
    default int score() {
        return 10;
    }
}

interface ChildPolicy extends ParentPolicy {
    @Override
    default int score() {
        return ParentPolicy.super.score() + 5;
    }
}
~~~

Lớp chỉ triển khai `ChildPolicy` thông thường sẽ nhận `score()` trả về `15`. Phương thức của `ChildPolicy` đã ghi rõ việc tái sử dụng default của `ParentPolicy`. Đây là một ví dụ của **gọi triển khai mặc định ngay trong một interface con**.

## 6. InterfaceName.super trong chính subinterface

Một interface được phép **extends** interface khác và cung cấp bản override `default` mới. Nó có thể gọi default inherited từ interface trực tiếp:

~~~java
interface PriceRule {
    default int apply(int value) {
        return value + 2;
    }
}

interface PremiumPriceRule extends PriceRule {
    @Override
    default int apply(int value) {
        return PriceRule.super.apply(value) * 3;
    }
}
~~~

Với đầu vào `4`:

~~~text
PriceRule.apply(4) = 6
PremiumPriceRule.apply(4) = 18
~~~

Cụ thể, `PremiumPriceRule` gọi `PriceRule.super.apply(4)` để lấy `6`, sau đó nhân ba thành `18`. Việc này có ích khi subinterface muốn **điều chỉnh một hành vi mặc định** mà vẫn tuân theo hợp đồng cơ sở.

Từ góc nhìn thiết kế, một subinterface cũng có thể **tái khai báo abstract method** thay cho default method để buộc class cuối cùng cung cấp triển khai mới. Trong trường hợp đó, việc gọi một triển khai default không hiện hữu hoặc không đủ điều kiện từ nhánh được chọn sẽ không tự nhiên trở thành hợp lệ chỉ vì trước đó một ancestor từng có default method.

## 7. Direct superinterface: giới hạn hay gây lỗi nhất

`InterfaceName.super.m()` **không** cho phép chọn một interface tổ tiên bất kỳ trong toàn bộ đồ thị kế thừa. Java áp dụng quy tắc chặt chẽ về **direct superinterface** của class hoặc interface chứa lời gọi và những trường hợp qualifier bị che bởi nhánh kế thừa cụ thể hơn.

### Trường hợp hợp lệ

~~~java
interface Root {
    default String value() {
        return "root";
    }
}

interface Middle extends Root {
    @Override
    default String value() {
        return Root.super.value() + "-middle";
    }
}

class Leaf implements Middle {
    @Override
    public String value() {
        return Middle.super.value() + "-leaf";
    }
}
~~~

`Root` là direct superinterface của `Middle` nên `Root.super.value()` được dùng ở **bên trong `Middle`**. `Middle` là direct superinterface của `Leaf` nên lớp dùng `Middle.super.value()`.

~~~java
System.out.println(new Leaf().value());
~~~

Kết quả:

~~~text
root-middle-leaf
~~~

### Trường hợp không hợp lệ: đi thẳng qua nhánh gián tiếp

~~~java
// Không hợp lệ: Root không phải direct superinterface của Leaf.
class WrongLeaf implements Middle {
    @Override
    public String value() {
        return Root.super.value();
    }
}
~~~

Ngay cả khi `Middle extends Root`, điều đó **không** cho phép `WrongLeaf` gọi `Root.super.value()` từ vị trí không đủ điều kiện. Hãy gọi `Middle.super.value()` khi đó là superinterface trực tiếp và có default hợp lệ, hoặc thay đổi thiết kế API nếu cần một thao tác được công bố độc lập.

### Không “lách” quy tắc bằng một superinterface dư thừa

Xét:

~~~java
interface Basic {
    default String get() {
        return "basic";
    }
}

interface Enhanced extends Basic {
    @Override
    default String get() {
        return "enhanced";
    }
}
~~~

Một class ghi cả `implements Basic, Enhanced` không được mặc nhiên dùng `Basic.super.get()` để bỏ qua override của `Enhanced`. Java đặt ràng buộc với **qualified superinterface invocation** khi một direct superclass hoặc một direct superinterface cụ thể hơn là subtype của qualifier. Đừng coi việc thêm tên `Basic` vào `implements` là một cách “vượt cấp” tới phương thức đã bị nhánh cụ thể hơn override.

Khi cần một phiên bản cũ để tái sử dụng, thiết kế đúng thường là gọi `Basic.super.get()` **ngay trong `Enhanced`** và công bố một hành vi phù hợp cho lớp triển khai.

## 8. Super call chỉ hoạt động trong ngữ cảnh được phép

### A. Đây là lời gọi instance, không phải static utility call

~~~java
interface Logger {
    default void write() {
        System.out.println("log");
    }
}

class LoggingService implements Logger {
    @Override
    public void write() {
        Logger.super.write(); // Hợp lệ: instance override.
    }
}
~~~

Không thể lấy `Logger.super.write()` đem đặt tùy tiện vào một **static method** không có instance context. `Logger.super` liên quan tới superinterface của đối tượng đang thực hiện code, không phải cách gọi phương thức static của interface.

### B. Không dùng cho static method của interface

Phương thức static của interface được gọi thông qua tên interface:

~~~java
interface Config {
    static String key() {
        return "app";
    }
}

String value = Config.key();
~~~

`Config.super.key()` **không** phải cú pháp thay thế cho `Config.key()`. Static interface methods **không được kế thừa như default instance methods**.

### C. Không dùng cho abstract method không có triển khai

~~~java
interface Task {
    void execute();
}
~~~

`Task` chỉ khai báo abstract `execute()`, không cung cấp thân mặc định. Vì vậy việc cố gọi `Task.super.execute()` **không tạo ra một body để chạy**; compiler không chấp nhận lời gọi được giả định như thế.

### D. Quy tắc truy cập vẫn áp dụng

`InterfaceName.super.method()` không vượt qua `private`, accessibility hay các ràng buộc ngôn ngữ khác. Từ Java 9, interface có thể chứa **private methods** để tái sử dụng bên trong default/static methods; các private methods không phải default methods và không trở thành mục tiêu gọi từ class triển khai bằng `InterfaceName.super`.

Nếu method có tham số và trả về giá trị, bạn vẫn phải cung cấp đối số có kiểu hợp lệ và xử lý checked exception đúng theo chữ ký. Không có ưu tiên đặc biệt về boxing, generics hay exception chỉ vì dùng `super`.

## 9. Lời gọi default vẫn chạy trên đối tượng hiện tại

`InterfaceName.super.m()` chọn **thân phương thức mặc định** để bắt đầu thực hiện; nó **không tạo một đối tượng interface độc lập**. Bên trong default body, `this` vẫn là đối tượng đang được gọi và những lời gọi instance khác có thể tiếp tục được **dispatch động**.

Quay lại:

~~~java
interface Greeter {
    String name();

    default String greeting() {
        return "Xin chào, " + name();
    }
}

class FormalGreeter implements Greeter {
    @Override
    public String name() {
        return "Lan";
    }

    @Override
    public String greeting() {
        return Greeter.super.greeting() + "!";
    }
}
~~~

Khi `Greeter.super.greeting()` được thực thi, nó gọi `name()` trên `FormalGreeter`, trả về `"Lan"`. Vì thế kết quả là `"Xin chào, Lan!"`. Không có một “phiên bản của `Greeter`” được tạo riêng để xử lý `name()`.

Điều này đặc biệt quan trọng nếu default body gọi những phương thức được override khác hoặc thay đổi trạng thái của đối tượng. **Chọn body default không đồng nghĩa bỏ qua toàn bộ polymorphism bên trong body đó.**

## 10. Ví dụ Java 17+ hoàn chỉnh, biên dịch và chạy độc lập

Tạo tệp **`InterfaceSuperDemo.java`**:

~~~java
public class InterfaceSuperDemo {

    interface Greeter {
        String name();

        default String greeting() {
            return "Xin chao, " + name();
        }
    }

    static class User implements Greeter {
        @Override
        public String name() {
            return "Mai";
        }

        @Override
        public String greeting() {
            return Greeter.super.greeting() + "!";
        }
    }

    interface Left {
        default String source() {
            return "Left";
        }
    }

    interface Right {
        default String source() {
            return "Right";
        }
    }

    static class Both implements Left, Right {
        @Override
        public String source() {
            return Left.super.source()
                    + " & " + Right.super.source();
        }
    }

    interface Parent {
        default int points() {
            return 10;
        }
    }

    interface Child extends Parent {
        @Override
        default int points() {
            return Parent.super.points() + 5;
        }
    }

    static class Player implements Child {
        @Override
        public int points() {
            return Child.super.points() * 2;
        }
    }

    static class Base {
        public String title() {
            return "class";
        }
    }

    interface Caption {
        default String title() {
            return "interface";
        }
    }

    static class Derived extends Base implements Caption {
        // Phương thức concrete của Base thắng default của Caption.
    }

    public static void main(String[] args) {
        System.out.println("user=" + new User().greeting());
        System.out.println("both=" + new Both().source());
        System.out.println("player=" + new Player().points());
        System.out.println("class-wins=" + new Derived().title());
    }
}
~~~

Dùng JDK 17 hoặc một JDK hiện đại có hỗ trợ tùy chọn `--release 17`:

~~~bash
javac --release 17 InterfaceSuperDemo.java
java InterfaceSuperDemo
~~~

**Stdout chính xác:**

~~~text
user=Xin chao, Mai!
both=Left & Right
player=30
class-wins=class
~~~

### Tại sao có đúng những kết quả ấy?

1. `User.greeting()` gọi `Greeter.super.greeting()`. Body của `Greeter` gọi `name()` được `User` triển khai, trả `"Mai"`, rồi `User` thêm `!`.
2. `Both.source()` buộc phải giải quyết hai default methods cùng chữ ký. Nó gọi `Left.super.source()` và `Right.super.source()` rồi ghép hai chuỗi thành `"Left & Right"`.
3. `Child.points()` nhận `10` từ `Parent.super.points()` và thêm `5` thành `15`. `Player.points()` gọi `Child.super.points()` rồi nhân hai thành `30`.
4. `Derived` không cần override `title()`. Phương thức concrete từ superclass `Base` có ưu tiên nên kết quả là `"class"` chứ không phải `"interface"`.

Toàn bộ cú pháp chính của ví dụ — **default interface methods, qualified super invocation, multiple interfaces** — đã được hỗ trợ từ Java 8 và **vẫn hợp lệ ngày nay**. Có thể biên dịch lại bằng `javac --release 8 InterfaceSuperDemo.java` trên các JDK hiện đại còn hỗ trợ mục tiêu phát hành đó. Việc chọn `--release 8` chỉ nên dùng khi cần kiểm tra khả năng tương thích, không phải khuyến nghị triển khai ứng dụng mới trên runtime đã cũ.

## 11. Ba ví dụ cố ý không biên dịch

Các đoạn sau phục vụ phân tích compiler, **không đặt chung vào chương trình `InterfaceSuperDemo.java` phía trên**.

### Lỗi 1: hai default methods mà không override

~~~java
interface A {
    default void show() {
        System.out.println("A");
    }
}

interface B {
    default void show() {
        System.out.println("B");
    }
}

// Không hợp lệ: inherited defaults xung đột.
// class Bad implements A, B {
// }
~~~

**Sửa:** lớp `Bad` phải cung cấp `public void show()` và nêu rõ xử lý mong muốn. Ví dụ có thể gọi `A.super.show()`, `B.super.show()` hoặc một hành vi mới.

### Lỗi 2: qualifier không phải direct superinterface

~~~java
interface Root {
    default void action() {
        System.out.println("root");
    }
}

interface Middle extends Root {
}

class BadLeaf implements Middle {
    public void run() {
        // Không hợp lệ: Root không phải direct superinterface.
        // Root.super.action();
    }
}
~~~

**Sửa:** khi `Middle` là direct superinterface và nó kế thừa default `action()`, cân nhắc `Middle.super.action()` nếu hợp đồng của `Middle` cho phép. Không mặc định rằng class có thể gọi mọi ancestor interface theo tên.

### Lỗi 3: gọi qua `super` như thể instance method là static

~~~java
interface Notification {
    default void emit() {
        System.out.println("sent");
    }
}

class BadStatic implements Notification {
    static void helper() {
        // Không hợp lệ trong static context:
        // Notification.super.emit();
    }
}
~~~

**Sửa:** gọi trên một instance thích hợp qua API công khai nếu mục đích là thực thi hành vi, hoặc đặt việc tái sử dụng default vào một instance method hợp lệ của lớp đang triển khai interface.

Trong IDE, hãy đọc chính xác lỗi `javac`, xác định **phương thức có default body thật hay không**, qualifier có nằm trong quan hệ direct-superinterface thích hợp không và lời gọi có nằm trong ngữ cảnh được phép không.

## 12. Những hiểu nhầm thường gặp

| Hiểu nhầm | Sự thật |
| --- | --- |
| “`InterfaceName.super` gọi một đối tượng superinterface riêng.” | Không. Đây là qualified invocation tới default implementation, dùng instance hiện tại. |
| “Mọi interface ancestor đều gọi được bằng `Ancestor.super.m()`.” | Sai. Cần direct superinterface và các điều kiện hợp lệ khác. |
| “Hai default methods trùng nhau thì Java chọn interface viết trước.” | Sai. Lớp cần giải quyết xung đột khi hai nhánh không liên quan có default cạnh tranh. |
| “Thêm `implements A, B` giúp tôi tùy ý bỏ qua override của B.” | Sai. Có ràng buộc khi một superinterface cụ thể hơn đã override phương thức. |
| “Một lớp đã có concrete method sẽ bị interface default ghi đè.” | Sai. Class method có ưu tiên trong method inheritance. |
| “`this.m()` trong override tương đương `I.super.m()`.” | Sai. `this.m()` có thể gọi lại chính override và gây recursion. |
| “`InterfaceName.super.m()` dùng được cho static/abstract/private methods.” | Sai. Mục tiêu phải là default implementation phù hợp, cùng quyền truy cập/ngữ cảnh. |
| “Có thể viết `super.super.m()` để truy cập tổ tiên xa hơn.” | Không. Đây không phải cú pháp Java hợp lệ. |
| “Chỉ cần bỏ default đi thì code ở subclass vẫn gọi được `I.super.m()`.” | Không. Khi default implementation không còn, lời gọi phụ thuộc vào nó có thể không biên dịch. |
| “`InterfaceName.super` là tính năng lỗi thời của Java 8.” | Sai. Nó vẫn là công cụ chuẩn để giải quyết hành vi interface default trong Java hiện đại. |

## 13. Khi nào nên dùng InterfaceName.super, khi nào nên thiết kế khác?

**Nên dùng khi:**

- Lớp muốn **thêm hành vi trước/sau** default method nhưng vẫn giữ logic mặc định.
- Một class triển khai hai giao diện có default method cùng chữ ký và cần chọn/ghép minh bạch.
- Một subinterface muốn **mở rộng** default của direct superinterface, ví dụ thêm hậu xử lý mà vẫn tái sử dụng hợp đồng gốc.

**Cân nhắc thiết kế khác khi:**

- Logic nghiệp vụ của hai interface thực sự khác nhau và ghép hai default methods không có ý nghĩa.
- Bạn phải gọi “vượt cấp” liên tục qua nhiều tầng interface, dấu hiệu API cần một helper hoặc một phương thức đặt tên rõ ràng hơn.
- Default method bị thay đổi ngữ nghĩa giữa các phiên bản thư viện: lớp gọi `InterfaceName.super` có thể thay đổi hành vi sau nâng cấp dù code client không đổi.
- Cần chia sẻ một thuật toán độc lập với cơ chế kế thừa. Có thể tách ra một utility/service hoặc phương thức được đặt tên riêng, rồi để cả default method và class dùng chung. Cách đó phù hợp hơn với composition và kiểm thử độc lập.

**Ví dụ thiết kế lại:** nếu `BasicPolicy.super.calculate()` thực chất là phép tính chung mà mọi lớp đều cần, một phương thức có tên rõ `PolicyMath.calculateBase(...)` có thể dễ tái sử dụng và kiểm thử hơn cố gắng thay đổi cây kế thừa chỉ để gọi `super`. Chọn giải pháp theo tính ổn định của API và ranh giới trách nhiệm, không phải vì `InterfaceName.super` luôn tốt hoặc luôn xấu.

## 14. Tương tác với generic, overload và checked exceptions

Lời gọi `I.super.method(args)` vẫn là một **method invocation** trong Java:

- Nếu default method có nhiều đối số, phải truyền đúng số lượng/kiểu (hoặc varargs nếu được khai báo).
- Nếu default method generic, compiler phải suy luận hoặc nhận type arguments hợp lệ.
- Nếu default method khai báo checked exception, code gọi phải bắt hoặc khai báo tiếp ngoại lệ.
- Trong quan hệ override, kiểu trả về và mức truy cập phải hợp lệ.
- Nếu một default method gọi phương thức khác trên `this`, dispatch cho phương thức đó vẫn dựa trên implementation thực tế.

Ví dụ ngắn:

~~~java
interface Formatter<T> {
    default T normalize(T value) {
        return value;
    }
}

class TextFormatter implements Formatter<String> {
    @Override
    public String normalize(String value) {
        return Formatter.super.normalize(value).strip();
    }
}
~~~

`Formatter<String>` cung cấp default `String normalize(String)` sau khi thay generic; lớp gọi `Formatter.super.normalize(value)` rồi áp dụng `String.strip()`. `strip()` có từ **Java 11**, vì vậy đoạn này đòi JDK/API mức Java 11+ mặc dù default methods và `InterfaceName.super` đã có từ Java 8.

Nếu cần tương thích `--release 8`, thay `strip()` bằng hành vi làm sạch tương thích đúng nhu cầu; đừng giả định `trim()` và `strip()` đồng nghĩa trên mọi ký tự Unicode.

### Tác động của thứ tự gọi

Khi lớp kết hợp default của hai interface, thứ tự lời gọi có thể quan trọng nếu chúng có **side effect**. Ví dụ default methods có thể ghi log hoặc cập nhật trạng thái qua các instance methods khác. Hai lời gọi `A.super.m(); B.super.m();` và `B.super.m(); A.super.m();` không nhất thiết tương đương.

Nếu dự án dùng đồng thời nhiều thread, `InterfaceName.super` cũng **không tự cung cấp đồng bộ**. Hành vi thread-safe hay không phụ thuộc mã default, trạng thái và cách sử dụng đối tượng; cần review/test theo hợp đồng của ứng dụng.

## 15. Kiểm thử hành vi khi override default

Bạn nên kiểm tra cả **hành vi lớp override** và **hợp đồng phương thức default** mà nó tái sử dụng:

1. Trường hợp bình thường: kết quả sau khi bọc default có đúng không?
2. Trường hợp có nhiều interface: class đã chọn đúng default và đúng thứ tự kết hợp chưa?
3. Trường hợp subinterface: phiên bản `Child.super` có đưa vào logic kế thừa mong muốn không?
4. Tác dụng phụ: default method có gọi instance method khác mà subclass đã override không?
5. Sau refactor thư viện: thay đổi default method có phá kết quả mà lớp đang dựa vào không?

Ví dụ các điều kiện độc lập với in/out tiêu chuẩn:

~~~java
if (!"Xin chao, Mai!".equals(new InterfaceSuperDemo.User().greeting())) {
    throw new AssertionError("Greeting contract violated");
}

if (!"Left & Right".equals(new InterfaceSuperDemo.Both().source())) {
    throw new AssertionError("Default conflict resolution violated");
}

if (new InterfaceSuperDemo.Player().points() != 30) {
    throw new AssertionError("Parent/Child default reuse violated");
}
~~~

Đoạn trên chỉ là **các assertion minh họa** có thể đặt trong code test khi `InterfaceSuperDemo` đã được biên dịch và có thể truy cập theo quy tắc package/visibility. Với JUnit Jupiter, có thể dùng `assertEquals(...)` tương ứng; khi kiểm thử trong ứng dụng thực tế nên dùng framework đang được dự án duy trì.

## 16. Bài tập thực hành

**Bài 1 — Bổ sung hành vi mặc định.** Cho interface `Printable` có `default String print() { return "base"; }`. Hãy viết lớp `Decorated` override `print()` để trả `"[base]"` mà không copy chuỗi `"base"`.

**Bài 2 — Hai default methods xung đột.** Viết `interface A` và `interface B`, mỗi interface có `default int level()` lần lượt trả 2 và 3. Viết lớp triển khai cả hai để trả tổng 5 bằng `A.super.level() + B.super.level()`. Vì sao lớp không override sẽ bị lỗi?

**Bài 3 — Tầng kế thừa.** Cho `Root` có default `count()` trả 1, `Middle extends Root` override default cộng 2, `Leaf implements Middle` override cộng 3. Viết các qualified calls hợp lệ; giá trị cuối cùng phải là 6.

**Bài 4 — Class wins.** Cho `Base` có concrete `name()` trả `"class"`; `Named` có default `name()` trả `"interface"`; `Derived extends Base implements Named`. Dự đoán kết quả `new Derived().name()` và giải thích bằng quy tắc ưu tiên.

**Bài 5 — Tránh đệ quy.** Trong lớp `C implements I`, nếu `C.m()` override `I.m()` và gọi `this.m()`, điều gì xảy ra? Viết lời gọi tới default của `I` nếu `I` là direct superinterface hợp lệ.

**Bài 6 — Sai ngữ cảnh.** Vì sao không thể gọi `I.super.m()` trong một static utility method? Phân biệt nó với `I.staticMethod()`.

**Bài 7 — Kế thừa gián tiếp.** Nếu `Middle extends Root` và `Leaf implements Middle`, `Leaf` có thể dùng `Root.super.m()` để truy cập default của `Root` không? Hãy giải thích direct-superinterface restriction và cách gọi đúng.

**Bài 8 — Hợp đồng với side effect.** Hai interface có default method cùng ghi log. Khi lớp gọi cả hai phiên bản, thứ tự gọi ảnh hưởng ra sao? Viết test xác nhận thứ tự sự kiện nếu nghiệp vụ yêu cầu.

## 17. Tổng kết

- `InterfaceName.super.method(...)` là **qualified super method invocation** để gọi một triển khai `default` phù hợp từ **superinterface** trong ngữ cảnh instance hợp lệ.
- Một lớp có thể override một default method và **bọc thêm** hành vi bằng cách gọi lại phiên bản mặc định, tránh sao chép logic.
- Khi hai interface ngang hàng cung cấp default methods có chữ ký xung đột, lớp phải **giải quyết xung đột**; có thể gọi từng nhánh qua `A.super.m()`, `B.super.m()`.
- Quy tắc **class wins** ưu tiên phương thức từ class hierarchy trước default method cạnh tranh của interface.
- Có thể gọi `Parent.super.m()` **bên trong subinterface** trực tiếp mở rộng `Parent`, rồi một class dùng `Child.super.m()` nếu `Child` là direct superinterface thích hợp.
- **Không gọi xuyên qua mọi interface tổ tiên**: direct-superinterface và tính cụ thể hơn của các nhánh là những ràng buộc có ý nghĩa.
- **Không dùng cú pháp này cho static/abstract/private methods** hoặc từ static context. `InterfaceName.super` cũng không tạo một object riêng.
- Hành vi bên trong default method vẫn thực thi trên **đối tượng hiện tại**; các lời gọi instance bên trong default vẫn được dispatch động khi thích hợp.
- Tính năng được giới thiệu từ Java 8 và **vẫn có giá trị trong Java hiện đại**, song phải đối chiếu baseline khi ví dụ kết hợp API mới hơn như `String.strip()`.

## 18. Tài liệu chính thức

- Java Language Specification, **`9.4 Interface Member Declarations** và **`9.4.3 Interface Method Body** (quy tắc default method): https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html
- Java Language Specification, **`15.12 Method Invocation Expressions**, đặc biệt **`15.12.3**, phương thức qua superinterface: https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.12.3
- Java Language Specification, **`8.4.8 Inheritance, Overriding, and Hiding** và các quy tắc liên quan class/interface: https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html
- Oracle Java Tutorial, **Default Methods** (giới thiệu khái niệm từ Java 8): https://docs.oracle.com/javase/tutorial/java/IandI/defaultmethods.html
- Java SE 17 API, **String.strip()**, API từ Java 11 thường được dùng khi override default xử lý chuỗi: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html#strip()

Khi triển khai hệ thống hiện tại, ưu tiên **JLS và Javadoc tương ứng với JDK mục tiêu** để kiểm tra những chi tiết góc cạnh. Tài liệu tutorial Java 8 dùng để thấy xuất xứ tính năng, không thay cho đặc tả Java còn được hỗ trợ.