# Phân biệt che khuất thành viên với ghi đè trong Java

Khi một lớp con khai báo thành viên có **cùng tên** với lớp cha, Java không phải lúc nào cũng thực hiện **ghi đè (overriding)**. Tùy thành viên là **field**, **phương thức `static`** hay **phương thức instance**, Java dùng những quy tắc khác nhau:

- **Che khuất field (*field hiding*):** Field ở lớp con có cùng tên với field lớp cha. Truy cập `ref.field` chủ yếu được chọn theo **kiểu của biểu thức tham chiếu tại lúc biên dịch**, không theo lớp thực tế của đối tượng.
- **Che khuất phương thức tĩnh (*static method hiding*):** Lớp con khai báo một static method có chữ ký tương ứng với static method của lớp cha. Lời gọi được phân giải theo **kiểu được dùng tại compile time**, không có đa hình động như instance method.
- **Ghi đè phương thức (*method overriding*):** Lớp con cung cấp implementation mới cho một **instance method** được phép override từ lớp cha. Với một lời gọi có receiver object, Java chọn implementation tại **runtime** dựa vào kiểu thực tế của object.

Sự khác biệt này rất quan trọng khi đọc:

~~~java
Parent ref = new Child();
~~~

Biến `ref` có kiểu khai báo `Parent`, nhưng nó đang tham chiếu tới một đối tượng `Child`. Field, static method và instance method **không nhất thiết được chọn theo cùng một kiểu**.

## 1. Bảng đối chiếu nhanh

| Đặc điểm | Field hiding | Static method hiding | Instance method overriding |
|---|---|---|---|
| Điều kiện điển hình | Lớp con khai báo field trùng tên | Lớp con khai báo static method cùng chữ ký hợp lệ | Lớp con khai báo instance method override hợp lệ |
| Chọn thành viên theo | Kiểu biểu thức tham chiếu lúc biên dịch | Kiểu dùng để gọi/lựa chọn method lúc biên dịch | Kiểu thực tế của receiver object lúc chạy |
| Có đa hình động? | **Không** | **Không** | **Có** |
| Dùng `@Override`? | Không | Không, sẽ báo lỗi | Nên dùng |
| `super` có ích? | `super.field` đọc field lớp cha | `super.method()` với static có quy tắc riêng, nhưng nên gọi `Parent.method()` | `super.method()` gọi implementation superclass |
| Hai thành viên tồn tại riêng? | Có thể có hai field cùng tên ở phần dữ liệu các lớp | Có hai phương thức static được khai báo ở hai lớp | Có các implementation khác nhau của cùng hợp đồng method |
| Khuyến nghị | Tránh che khuất field để khỏi gây nhầm | Gọi static method bằng **tên lớp** | Dùng cho hành vi đa hình có hợp đồng rõ ràng |

**Cách nhớ:** *field và static method phụ thuộc vào kiểu tham chiếu/kiểu dùng tại compile time; instance method được override phụ thuộc vào object ở runtime.*

Đây là quy tắc cốt lõi, nhưng cách compiler phân giải lời gọi còn chịu ảnh hưởng của overload, khả năng truy cập và kiểu của từng đối số. Ta sẽ tách những cơ chế ấy trong các phần tiếp theo.

## 2. Ví dụ Java đầy đủ: một object, ba cách phân giải thành viên

Lưu toàn bộ vào **`Demo.java`**, biên dịch/chạy bằng Java 17 trở lên:

~~~java
public class Demo {
    public static void main(String[] args) {
        Parent parentView = new Child();
        Child childView = (Child) parentView;

        System.out.println("=== Field ===");
        System.out.println(parentView.label);
        System.out.println(childView.label);
        System.out.println(((Parent) childView).label);

        System.out.println("=== Static method ===");
        System.out.println(Parent.kind());
        System.out.println(Child.kind());

        // Hợp lệ về cú pháp, nhưng không nên gọi static qua instance:
        System.out.println(parentView.kind());
        System.out.println(childView.kind());

        System.out.println("=== Instance method ===");
        System.out.println(parentView.describe());
        System.out.println(childView.describe());

        System.out.println("=== Kết hợp với super ===");
        childView.inspect();
        System.out.println(parentView.report());
    }
}

class Parent {
    public String label = "Field của Parent";

    public static String kind() {
        return "Static của Parent";
    }

    public String describe() {
        return "Method của Parent";
    }

    public String report() {
        // describe() là instance method: dispatch theo object.
        return "Report: " + describe();
    }
}

class Child extends Parent {
    public String label = "Field của Child"; // Field hiding.

    public static String kind() {            // Static method hiding.
        return "Static của Child";
    }

    @Override
    public String describe() {               // Method overriding.
        return "Method của Child";
    }

    public void inspect() {
        System.out.println(this.label);
        System.out.println(super.label);
        System.out.println(this.describe());
        System.out.println(super.describe());
    }
}
~~~

Chạy:

~~~bash
javac Demo.java
java Demo
~~~

Kết quả:

~~~text
=== Field ===
Field của Parent
Field của Child
Field của Parent
=== Static method ===
Static của Parent
Static của Child
Static của Parent
Static của Child
=== Instance method ===
Method của Child
Method của Child
=== Kết hợp với super ===
Field của Child
Field của Parent
Method của Child
Method của Parent
Report: Method của Child
~~~

### Phân tích theo từng cơ chế

**Field hiding:**

~~~java
Parent parentView = new Child();

System.out.println(parentView.label);          // Field của Parent
System.out.println(((Child) parentView).label); // Field của Child
~~~

Cả hai biểu thức cùng trỏ tới **một object `Child`**, nhưng field được chọn theo **kiểu tham chiếu** của biểu thức:

- `parentView` được khai báo là `Parent` → đọc `Parent.label`.
- `(Child) parentView` có kiểu `Child` → đọc `Child.label`.

Phép cast trong trường hợp này **không tạo object khác và không di chuyển giá trị field**; nó làm thay đổi cách compiler nhìn nhận biểu thức.

**Static method hiding:**

~~~java
System.out.println(parentView.kind()); // Static của Parent
System.out.println(childView.kind());  // Static của Child
~~~

Hai lời gọi này được phép nhưng gây hiểu nhầm rằng static method sử dụng đa hình. **Nên viết `Parent.kind()` và `Child.kind()`** để thể hiện rõ static method gắn với lớp.

**Instance method overriding:**

~~~java
System.out.println(parentView.describe()); // Method của Child
~~~

Compiler xác nhận `Parent` có `describe()`, còn JVM chọn implementation `Child.describe()` của đối tượng thực tế.

Điểm thú vị là `Parent.report()` cũng gọi được `Child.describe()` khi chạy trên object `Child`: phương thức của lớp cha gọi một **instance method có thể override**, và dispatch vẫn diễn ra ở runtime.

## 3. Field hiding: cùng tên nhưng không phải cùng field

Khi subclass khai báo lại field cùng tên, có thể hình dung một object lớp con có các phần trạng thái tương ứng với cả superclass lẫn subclass:

~~~mermaid
flowchart TD
    R["parentView: Parent"] --> O["Object thực tế: Child"]
    S["childView: Child"] --> O
    O --> P["Phần Parent: label = Field của Parent"]
    O --> C["Phần Child: label = Field của Child"]
    R -.->|"parentView.label"| P
    S -.->|"childView.label"| C
~~~

Đây là sơ đồ **logic**, không cam kết vị trí bộ nhớ vật lý hoặc cách JVM tối ưu hóa field.

Một ví dụ chỉnh sửa cho thấy **hai field độc lập**:

~~~java
class CounterBase {
    public int count = 1;
}

class CounterChild extends CounterBase {
    public int count = 10;
}

CounterChild obj = new CounterChild();
obj.count = 20;
((CounterBase) obj).count = 2;

System.out.println(obj.count);               // 20
System.out.println(((CounterBase) obj).count); // 2
~~~

Phần sử dụng ở cuối cần đặt trong một phương thức Java thích hợp. Gán `obj.count = 20` **không thay đổi** `CounterBase.count`; gán qua cast về `CounterBase` cũng không sửa `CounterChild.count`.

Điều này dễ gây lỗi khi lớp cha có một invariant dựa vào field của nó, còn lớp con lại khai báo field trùng tên và vô tình làm code đọc dữ liệu không nhất quán.

### Đừng dùng field công khai để tạo đa hình

Thiết kế dễ gây nhầm:

~~~java
class Configuration {
    public String environment = "default";
}

class ProductionConfiguration extends Configuration {
    public String environment = "production";
}
~~~

Code sử dụng:

~~~java
Configuration config = new ProductionConfiguration();
System.out.println(config.environment); // default
~~~

Nếu muốn kết quả tùy thuộc object thực tế, hãy dùng **phương thức instance**:

~~~java
class Configuration {
    public String environment() {
        return "default";
    }
}

class ProductionConfiguration extends Configuration {
    @Override
    public String environment() {
        return "production";
    }
}

Configuration config = new ProductionConfiguration();
System.out.println(config.environment()); // production
~~~

Với dữ liệu quan trọng, thường nên giữ field `private` và cung cấp getter hoặc hành vi thể hiện ý định. Nếu getter được override thì client nhận đa hình đúng theo hợp đồng; đồng thời class vẫn có thể kiểm soát invariant.

## 4. Static method hiding: cùng chữ ký, không có dispatch động

Trong Java, static method thuộc về **lớp**, không thuộc trạng thái riêng của một instance. Một subclass có thể khai báo static method cùng chữ ký để **hide** static method của superclass, trong những điều kiện hợp lệ.

~~~java
class Formatter {
    public static String format() {
        return "BASE";
    }
}

class JsonFormatter extends Formatter {
    public static String format() {
        return "JSON";
    }
}
~~~

Sử dụng:

~~~java
Formatter base = new JsonFormatter();

System.out.println(Formatter.format());      // BASE
System.out.println(JsonFormatter.format());  // JSON
System.out.println(base.format());           // BASE
~~~

Dòng cuối **được phép** nhưng không nên sử dụng: `base.format()` trông như gọi phương thức của object, nhưng compiler xác định là static method của `Formatter` theo kiểu biểu thức.

**`@Override` không hợp lệ trên phương thức `JsonFormatter.format()`**, vì static method chỉ hide, không override.

### Không thể “đổi” một static method thành instance override

Ví dụ bị Java từ chối:

~~~java
class Parent {
    public static void process() {}
}

class Child extends Parent {
    // public void process() {} // Lỗi biên dịch:
    // instance method không thể override/hide static method tương ứng.
}
~~~

Chiều ngược lại cũng không hợp lệ:

~~~java
class Parent {
    public void process() {}
}

class Child extends Parent {
    // public static void process() {} // Lỗi biên dịch:
    // static method không thể hide instance method tương ứng.
}
~~~

Hai phương thức trùng chữ ký trong quan hệ kế thừa không thể hoán đổi giữa static và instance tùy ý.

### Static method của interface có khác biệt

Java interface cho phép static method:

~~~java
interface TextRules {
    static boolean hasText(String value) {
        return value != null && !value.isBlank();
    }
}

class TextService implements TextRules {}

System.out.println(TextRules.hasText("Java")); // true

// TextService.hasText("Java");  // Không hợp lệ.
// new TextService().hasText("Java"); // Không hợp lệ.
~~~

Static method khai báo trong interface **không được kế thừa sang class implements** như instance/default method. Vì thế, không nên áp dụng máy móc quy tắc class static hiding cho static method của interface.

## 5. Ghi đè phương thức tạo sự khác biệt với hiding

~~~java
class Notification {
    String send() { return "Gửi thông báo"; }
}
class EmailNotification extends Notification {
    @Override String send() { return "Gửi email"; }
}
Notification item = new EmailNotification();
System.out.println(item.send()); // Gửi email
~~~

`send()` là **instance method có thể override** nên Java dispatch theo object `EmailNotification`, khác hẳn truy cập `item.field` hoặc gọi một static method bị hide. `@Override` giúp compiler kiểm tra chữ ký; một override hợp lệ còn phải giữ kiểu trả về tương thích, không giảm khả năng truy cập, không mở rộng checked exception sai quy tắc và giữ hợp đồng hành vi.

Với cú pháp ghi đè, covariant return, `final`, `super` và tác động của hook trong constructor, bài *Ghi đè và lựa chọn phương thức khi chạy* là nơi hướng dẫn chính.

## 6. Phương thức private có phải là overridden không?

Không. Private instance method của superclass **không được kế thừa để override** bởi subclass.

~~~java
class SecureBase {
    private String secretLabel() {
        return "Base private";
    }

    public String audit() {
        return secretLabel();
    }
}

class SecureChild extends SecureBase {
    // Phương thức riêng, không phải override private method của Base.
    public String secretLabel() {
        return "Child public";
    }
}
~~~

Sử dụng:

~~~java
SecureBase ref = new SecureChild();
System.out.println(ref.audit()); // Base private

SecureChild child = new SecureChild();
System.out.println(child.secretLabel()); // Child public
~~~

`SecureBase.audit()` gọi phương thức `private secretLabel()` của chính `SecureBase`; phương thức cùng tên do `SecureChild` khai báo không thay thế nó.

Đây là một điểm rất khác so với `public`/`protected` instance method có thể override.

Lưu ý: class lồng nhau (*nestmates*) có thể có quyền truy cập private đặc biệt theo quy tắc Java, nhưng điều đó không biến private method của superclass thành phương thức được override.

### Lớp con không thể truy cập field private qua `super`

~~~java
class Parent {
    private int balance = 100;

    public int getBalance() {
        return balance;
    }
}

class Child extends Parent {
    public int readBalance() {
        // return super.balance; // Lỗi: private không được truy cập.
        return getBalance();     // Hợp lệ: gọi public method.
    }
}
~~~

Từ khóa `super` không cho phép vượt qua mức truy cập `private`; nó chỉ chỉ rõ ngữ cảnh superclass cho những thành viên được phép sử dụng.

## 7. Che khuất field và override có thể cùng xuất hiện, dẫn tới trạng thái bất nhất

Xét:

~~~java
class Profile {
    protected String displayName = "Base";

    public String summary() {
        return "Tên: " + displayName;
    }
}

class PremiumProfile extends Profile {
    protected String displayName = "Premium";

    @Override
    public String summary() {
        return "Tên cao cấp: " + displayName;
    }
}
~~~

~~~java
Profile profile = new PremiumProfile();
System.out.println(profile.displayName); // Base
System.out.println(profile.summary());   // Tên cao cấp: Premium
~~~

Dù cùng tham chiếu tới một object, việc đọc field và gọi method cho kết quả dựa vào **hai quy tắc khác nhau**.

Đó là lý do **không nên để code ngoài phụ thuộc vào protected/public field trùng tên** giữa các lớp trong cây kế thừa. Khi thật sự cần hành vi khác nhau, ưu tiên method override. Nếu cần trạng thái chung, lớp cha nên giữ một field private và cung cấp các thao tác có kiểm tra.

## 8. Overload là một câu hỏi khác: chọn chữ ký nào?

~~~java
class Printer {
    void print(Object value) { System.out.println("Object"); }
    void print(String value) { System.out.println("String"); }
}
Object text = "hello";
Printer printer = new Printer();
printer.print(text);      // Object
printer.print("hello");   // String
~~~

`print(Object)` và `print(String)` là **hai overload**; compiler chọn dựa trên kiểu tĩnh của đối số, không dựa trên object runtime của `text`. Sau khi chọn chữ ký, nếu lời gọi instance có override thì runtime mới chọn implementation tương ứng.

| Cơ chế | Chọn bằng |
|---|---|
| Field hiding | Kiểu tĩnh của biểu thức |
| Static hiding | Kiểu tĩnh/tên lớp |
| Overload | Kiểu tĩnh của receiver, đối số và quy tắc overload resolution |
| Instance override | Runtime class của receiver sau khi chữ ký đã xác định |

Các ví dụ kết hợp overload/override, `null`, boxing và varargs được dạy riêng ở bài *Phân biệt ghi đè với nạp chồng*.

## 9. Cách `super` ảnh hưởng đến các trường hợp

`super` được dùng trong instance context để chỉ rõ thao tác với lớp cha, giúp tránh mơ hồ khi cả hai lớp có thành viên cùng tên.

~~~java
class Vehicle {
    protected String label = "Vehicle";

    public String move() {
        return "Vehicle moves";
    }
}

class Car extends Vehicle {
    protected String label = "Car";

    @Override
    public String move() {
        return "Car moves; " + super.move();
    }

    public void inspect() {
        System.out.println(this.label);  // Car
        System.out.println(super.label); // Vehicle
        System.out.println(this.move()); // Car moves; Vehicle moves
    }
}
~~~

- `super.label` chọn field `label` được khai báo ở superclass.
- `super.move()` gọi implementation của superclass (không dùng dynamic dispatch để quay lại `Car.move()` tại đúng lời gọi `super` đó).
- `this.move()` là lời gọi instance method thông thường trên object hiện tại, nên dùng override của `Car`.

`super` không phải một object khác: vẫn đang làm việc trên phần superclass của **cùng đối tượng `Car`**.

Nếu phương thức lớp cha tự gọi một instance method có thể override, lời gọi bên trong nó vẫn có thể dispatch tới class con. Vì thế, có thể có đường đi như `super.doWork()` → phương thức cha → `this.hook()` → implementation hook của subclass.

### Cẩn trọng khi constructor gọi phương thức có thể override

Một lỗi thiết kế liên quan đa hình:

~~~java
class Base {
    Base() {
        initialize(); // Có thể gọi implementation trong subclass.
    }

    void initialize() {}
}

class Derived extends Base {
    private String configuration = "ready";

    @Override
    void initialize() {
        System.out.println(configuration);
    }
}
~~~

~~~java
new Derived();
~~~

Có thể in `null`, vì khi `Base` constructor gọi `initialize()`, quá trình khởi tạo field của `Derived` theo thứ tự thông thường **chưa hoàn tất**. Đây không phải lỗi field hiding; nó là hệ quả của **dynamic dispatch trong lúc xây dựng object**. Đừng gọi những phương thức có thể override từ constructor nếu implementation subclass có thể phụ thuộc vào trạng thái chưa sẵn sàng.

## 10. Cùng tên thành viên trong interface có thể gây mơ hồ

Ngoài cây class, Java cho phép triển khai nhiều interface:

~~~java
interface Left {
    int VERSION = 1;
}

interface Right {
    int VERSION = 2;
}

class Combined implements Left, Right {
    void printVersions() {
        // System.out.println(VERSION); // Mơ hồ, không biên dịch.
        System.out.println(Left.VERSION);
        System.out.println(Right.VERSION);
    }
}
~~~

Các field trong interface ngầm là `public static final`. Nếu hai interface khai báo cùng tên field, phải định danh nguồn thích hợp, chẳng hạn `Left.VERSION`.

Với hai interface có **default instance method** trùng chữ ký, class triển khai có thể phải override để giải quyết xung đột:

~~~java
interface LeftAction {
    default String action() {
        return "left";
    }
}

interface RightAction {
    default String action() {
        return "right";
    }
}

class CombinedAction implements LeftAction, RightAction {
    @Override
    public String action() {
        return LeftAction.super.action()
                + " + " + RightAction.super.action();
    }
}
~~~

Ở đây có hai default method được cung cấp qua interface, không phải static hiding. Quy tắc giải quyết xung đột default method thuộc cơ chế kế thừa interface và lựa chọn implementation instance method của Java; cần phân biệt với việc field được chọn theo tên/kiểu ở compile time.

## 11. Trường hợp `final` và mức truy cập

### `final` trên method chặn override/hiding phù hợp

~~~java
class Service {
    public final void start() {
        System.out.println("Started");
    }
}

class SpecialService extends Service {
    // public void start() {} // Lỗi: final method không thể override.
}
~~~

Một static method khai báo `final` cũng không thể bị một static method của subclass che khuất với chữ ký tương ứng trong ngữ cảnh kế thừa hợp lệ.

### `final` trên field không ngăn field hiding

~~~java
class Parent {
    public final int code = 100;
}

class Child extends Parent {
    public final int code = 200;
}
~~~

Cú pháp này hợp lệ: `final` ngăn **gán lại chính field**, chứ không cấm subclass khai báo một field **khác** cùng tên.

~~~java
Parent view = new Child();
System.out.println(view.code);          // 100
System.out.println(((Child) view).code); // 200
~~~

Trường hợp này càng dễ gây nhầm nếu field được dùng như một dấu hiệu nhận dạng loại object. Tránh thiết kế đa hình dựa vào các field cùng tên.

### Override không được giảm quyền truy cập

~~~java
class Parent {
    public String describe() {
        return "Parent";
    }
}

class Child extends Parent {
    @Override
    public String describe() {
        return "Child";
    }
}
~~~

Nếu đổi `Child.describe()` thành `protected`, Java sẽ báo lỗi vì phương thức override không được thu hẹp quyền truy cập mà caller đã có trên `Parent`.

Với phương thức `protected` của superclass, subclass có thể override bằng `public`, tức **mở rộng** quyền truy cập khi phù hợp.

## 12. Khi nào nên dùng và khi nào nên tránh?

| Nhu cầu | Nên làm | Tránh |
|---|---|---|
| Hành vi khác nhau theo object thực tế | Instance method + `@Override` | Dùng field cùng tên để “override” |
| Tiện ích không phụ thuộc instance | `static` method gọi bằng tên class | Gọi static qua object khiến người đọc tưởng có dispatch |
| Dữ liệu trạng thái riêng cho mỗi instance | `private` field và hành vi kiểm soát | Field công khai trùng tên ở nhiều cấp kế thừa |
| Mở rộng hành vi của lớp cha | Override và `super.method()` khi cần | Gọi `super` như cơ chế vượt quyền truy cập |
| Nhiều cách xử lý đầu vào khác kiểu | Overload với hợp đồng rõ ràng | Nhầm overload với runtime override |
| Cần hỗ trợ subtype mới mà client không đổi | Thiết kế abstraction qua instance method/interface | Chuỗi `if` theo class hoặc đọc field type/name để chọn thuật toán |

Lý do thực tế để **tránh field hiding** là khả năng bảo trì: chỉ cần đổi kiểu khai báo của một biến, hoặc thêm một cast, kết quả đọc field có thể thay đổi dù runtime object không thay đổi. Hành vi đa hình qua method được thiết kế để cung cấp một lựa chọn implementation theo object thực tế, phù hợp hơn với nhu cầu OOP.

## 13. Những sai lầm khi suy luận theo tên thành viên

- **“Trùng tên luôn là override.”** Field trùng tên là field hiding; static method cùng chữ ký là static hiding; method khác tham số thường là overload.
- **“`new Child()` nghĩa là mọi truy cập đều dùng Child.”** Với `Parent ref = new Child()`, chỉ instance method đủ điều kiện override có dynamic dispatch; field và static method có quy tắc khác.
- **“`@Override` dùng được cho static method hoặc chỉ đổi return type.”** Không. Static method không override, còn chỉ khác return type không tạo overload.
- **“Một method getter giống field.”** Getter là lời gọi instance method và có thể override; field lookup không dispatch.
- **“`super` gọi object cha riêng hay vượt qua `private`.”** Không. `super` chọn thành viên superclass hợp lệ trên cùng object.
- **“Đặt method cùng tên private của cha là ghi đè.”** Không. Private method của superclass không phải hook được kế thừa để override.

Khi debug, xác định trước **member thuộc loại nào** rồi mới hỏi compiler chọn gì và runtime dispatch tới đâu. Bài tập sau cho phép tự kiểm chứng các kết quả khác biệt.

## 14. Bài tập kiểm tra

### Bài 1 — Đoán kết quả field và method

~~~java
class A {
    int value = 1;
    String who() { return "A"; }
}

class B extends A {
    int value = 2;
    @Override String who() { return "B"; }
}

A obj = new B();
System.out.println(obj.value);
System.out.println(obj.who());
~~~

**Đáp án:** `1`, sau đó `B`. Field theo kiểu `A`; instance method override theo object `B`.

### Bài 2 — Đoán kết quả static method

~~~java
class A {
    static String id() { return "A"; }
}

class B extends A {
    static String id() { return "B"; }
}

A x = new B();
System.out.println(x.id());
~~~

**Đáp án:** `A`. Tuy cú pháp hợp lệ, lời gọi static qua `x` không nên dùng; thay bằng `A.id()` để diễn đạt chính xác.

### Bài 3 — Override hay overload?

~~~java
class A {
    void draw(Object value) {}
}

class B extends A {
    void draw(String value) {}
}
~~~

**Đáp án:** `B.draw(String)` **overload**, không override `A.draw(Object)`, vì tham số khác nhau. `@Override` trên `B.draw(String)` sẽ báo lỗi.

### Bài 4 — Có thể override private method không?

~~~java
class A {
    private void save() {}
}

class B extends A {
    public void save() {}
}
~~~

**Đáp án:** Không phải override. `B.save()` là phương thức riêng, không thay implementation private `A.save()`.

### Bài 5 — `super` sẽ chọn implementation nào?

~~~java
class A {
    String message() { return "A"; }
}

class B extends A {
    @Override String message() {
        return super.message() + "B";
    }
}
~~~

**Đáp án:** `new B().message()` trả `"AB"`. `super.message()` gọi implementation của `A`, sau đó `B` nối thêm `"B"`.

### Bài 6 — Tại sao `report()` của Parent có thể gọi `describe()` của Child?

**Đáp án:** Vì `Parent.report()` đang chạy trên một receiver là object `Child`. Lời gọi instance `describe()` trong `report()` vẫn sử dụng dynamic dispatch, nên implementation `Child.describe()` được chọn.

### Bài 7 — Chỉnh thiết kế

Một hệ thống dùng:

~~~java
class Payment {
    public String type = "generic";
}
class CardPayment extends Payment {
    public String type = "card";
}
~~~

Nhưng code `Payment p = new CardPayment();` lại in `p.type == "generic"`. Bạn sẽ sửa như thế nào?

**Gợi ý:** Chuyển `type` thành hành vi truy vấn:

~~~java
class Payment {
    public String type() { return "generic"; }
}
class CardPayment extends Payment {
    @Override public String type() { return "card"; }
}
~~~

Bây giờ `Payment p = new CardPayment(); p.type()` trả `"card"` nhờ overriding.

## 15. Quy trình đọc một lời gọi trong cây kế thừa

Khi thấy `ref.member`, hãy kiểm tra lần lượt:

1. **`member` là field hay method?** Nếu là field, không áp dụng dynamic overriding.
2. **Nếu là method, nó có phải static không?** Static method không sử dụng runtime dispatch.
3. **Nếu là instance method, compiler chọn chữ ký nào?** Có overload dựa vào kiểu đối số hay không?
4. **Chữ ký ấy có được override hợp lệ bởi kiểu object thực tế không?** Nếu có, runtime dùng implementation tương ứng.
5. **Có modifier chặn override không?** `private`, `final`, static hoặc quyền truy cập có thể làm quan hệ khác bạn tưởng.
6. **Có `super` hoặc cast rõ ràng không?** Chúng có thể ảnh hưởng cách chọn field, phương thức lớp cha hoặc kiểu biểu thức.
7. **Hành vi có đúng hợp đồng không?** Dù Java chọn đúng implementation về ngôn ngữ, phương thức override vẫn phải giữ điều kiện sử dụng của supertype.

~~~mermaid
flowchart TD
    A["Gặp ref.member"] --> B{"Member là field?"}
    B -->|Có| C["Chọn field theo kiểu biểu thức<br/>Field hiding, không dynamic dispatch"]
    B -->|Không| D{"Method là static?"}
    D -->|Có| E["Chọn static method theo compile-time type<br/>Static hiding"]
    D -->|Không| F["Compiler chọn chữ ký overload phù hợp"]
    F --> G["Runtime chọn override theo object thực tế"]
~~~

**Kết luận:** Trong Java, **che khuất thành viên** và **ghi đè** khác nhau cả về ý nghĩa OOP lẫn cách Java phân giải lời gọi. Field hiding và static method hiding được quyết định chủ yếu tại compile time; instance method overriding mới đem lại **đa hình động**. Muốn thay đổi hành vi theo loại object, hãy thiết kế một instance method với hợp đồng rõ ràng, ưu tiên `@Override`, giữ state được đóng gói và tránh sử dụng field trùng tên trong cây kế thừa.