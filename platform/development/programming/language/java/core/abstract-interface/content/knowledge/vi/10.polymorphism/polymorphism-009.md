# Vì sao truy cập field và phương thức static không đa hình trong Java

## 1. Mục tiêu và vấn đề cần hiểu

Trong Java, một biến có kiểu khai báo là lớp cha hoàn toàn có thể tham chiếu đối tượng của lớp con:

~~~java
Parent ref = new Child();
~~~

Nhưng kết quả của ba biểu thức sau không nhất thiết cùng thuộc `Child`:

~~~java
ref.name;             // Truy cập field.
ref.describe();       // Gọi instance method có thể override.
ref.version();        // Gọi static method qua biến (hợp lệ nhưng không nên viết).
~~~

Điểm mấu chốt:

- **Field được lựa chọn theo kiểu biểu thức ở thời điểm biên dịch (compile-time type).** Field trong lớp con có thể *che khuất* (hide) field trùng tên của lớp cha, nhưng không thể override field.
- **Phương thức `static` cũng không được override.** Nếu lớp con khai báo phương thức `static` tương ứng, đó là *method hiding*. Phương thức `static` được xác định theo kiểu hoặc tên lớp ở thời điểm biên dịch.
- **Phương thức instance có thể được override** và được chọn theo lớp thực tế của đối tượng tại thời điểm chạy (runtime dispatch), khi lời gọi thỏa các quy tắc của Java.
- **Phương thức `default` của interface** cũng là phương thức instance và có thể tham gia cơ chế override, trong khi **phương thức `static` của interface** thuộc về chính interface.

Mục tiêu không chỉ là thuộc kết quả in ra, mà là hiểu mỗi biểu thức cần **kiểu khai báo**, **lớp thực tế** hay **cả hai** để Java lựa chọn đúng thành viên.

## 2. Đa hình thời điểm chạy áp dụng cho phương thức instance được ghi đè

Đa hình (runtime polymorphism) trong ngữ cảnh kế thừa thường được quan sát khi một lời gọi phương thức instance được chọn dựa trên lớp thực tế của đối tượng.

Ví dụ:

~~~java
abstract class Shape {
    abstract String draw();
}

class Circle extends Shape {
    @Override
    String draw() {
        return "Circle";
    }
}
~~~

Khi viết `Shape shape = new Circle();` rồi gọi `shape.draw()`, trình biên dịch kiểm tra rằng kiểu `Shape` có phương thức `draw()` phù hợp. Khi chương trình chạy, đối tượng thực tế là `Circle`, nên triển khai `Circle.draw()` được chọn.

Như vậy, đối với một lời gọi instance method có override hợp lệ:

1. **Compile time:** Java kiểm tra phương thức có thể gọi theo kiểu tĩnh của biểu thức tham chiếu và chọn chữ ký thích hợp.
2. **Runtime:** Java tìm triển khai instance phù hợp với đối tượng thực tế cho chữ ký đã chọn.
3. **Kết quả:** Thay đổi lớp đối tượng thực tế (trong một hệ phân cấp override) có thể thay đổi hành vi mà không cần đổi kiểu biến ở phía người gọi.

Cơ chế này khác căn bản với truy cập field và lời gọi static method. JVM có thể tối ưu hóa các lời gọi động khi đã chứng minh đích gọi, nhưng **ngữ nghĩa Java** vẫn là đa hình ở mức ngôn ngữ.

## 3. Ví dụ hoàn chỉnh: ba cách truy cập trên cùng một đối tượng

Lưu toàn bộ mã sau vào tệp **`DispatchDemo.java`**:

~~~java
class Parent {
    public String name = "parent-field";

    public static String version() {
        return "parent-static";
    }

    public String describe() {
        return "parent-instance";
    }
}

class Child extends Parent {
    public String name = "child-field";

    public static String version() {
        return "child-static";
    }

    @Override
    public String describe() {
        return "child-instance";
    }
}

public class DispatchDemo {
    public static void main(String[] args) {
        Parent asParent = new Child();
        Child asChild = (Child) asParent;

        System.out.println(asParent.name);
        System.out.println(asChild.name);

        System.out.println(Parent.version());
        System.out.println(Child.version());

        // Để minh họa sự khác nhau: Java cho phép gọi static qua tham chiếu.
        System.out.println(asParent.version());
        System.out.println(asChild.version());

        System.out.println(asParent.describe());
        System.out.println(asChild.describe());

        System.out.println(((Parent) asChild).name);
        System.out.println(((Child) asParent).name);
    }
}
~~~

Biên dịch và chạy bằng JDK 17 hoặc mới hơn:

~~~bash
javac --release 17 DispatchDemo.java
java DispatchDemo
~~~

Kết quả chính xác:

~~~text
parent-field
child-field
parent-static
child-static
parent-static
child-static
child-instance
child-instance
parent-field
child-field
~~~

**Giải thích lần lượt:**

- `asParent.name` → `parent-field`: biến `asParent` có kiểu khai báo `Parent`, nên truy cập `Parent.name`.
- `asChild.name` → `child-field`: biểu thức tham chiếu có kiểu `Child`, nên truy cập `Child.name`.
- `Parent.version()` và `Child.version()` chọn đúng phương thức `static` ở lớp được chỉ tên.
- `asParent.version()` → `parent-static` dù đối tượng thực tế là `Child`. Java cho phép cú pháp này nhưng liên kết lời gọi tới `Parent.version()` theo kiểu tĩnh của biến.
- `asChild.version()` → `child-static` vì kiểu tĩnh của biểu thức là `Child`. Nên viết `Parent.version()` hoặc `Child.version()` trực tiếp cho rõ ý.
- Cả `asParent.describe()` và `asChild.describe()` → `child-instance`: `describe()` là instance method được `Child` override, và cả hai biến cùng trỏ tới một đối tượng `Child`.
- Hai ép kiểu cuối **không tạo đối tượng mới**; chúng chỉ làm thay đổi kiểu tĩnh của biểu thức được dùng cho việc tra cứu field, vì vậy cho kết quả khác nhau.

Ví dụ chứng minh: **đổi kiểu tĩnh của biến hoặc biểu thức có thể đổi field/static được chọn, nhưng không tự đổi lớp thực tế của đối tượng và hành vi instance method override.**

## 4. Field hiding: cùng tên không có nghĩa là cùng một field

Khi `Child` khai báo `name` trùng tên với `Parent.name`, trường mới **che khuất tên** của trường kế thừa trong các ngữ cảnh tra cứu thích hợp. Hai khai báo vẫn là **hai field khác nhau**, không có quan hệ override.

Với field instance, một đối tượng `Child` có thể chứa phần trạng thái do `Parent` định nghĩa *và* phần trạng thái do `Child` định nghĩa. Bởi vậy giá trị hai field có thể khác nhau.

Ví dụ chạy độc lập trong tệp **`HiddenFieldDemo.java`**:

~~~java
class BaseRecord {
    protected String code = "BASE";
}

class DetailedRecord extends BaseRecord {
    protected String code = "CHILD";

    void changeBoth() {
        super.code = "BASE-UPDATED";
        this.code = "CHILD-UPDATED";
    }

    void printFields() {
        System.out.println(super.code);
        System.out.println(this.code);
    }
}

public class HiddenFieldDemo {
    public static void main(String[] args) {
        DetailedRecord record = new DetailedRecord();
        record.changeBoth();
        record.printFields();

        BaseRecord baseView = record;
        System.out.println(baseView.code);
        System.out.println(record.code);
    }
}
~~~

~~~bash
javac --release 17 HiddenFieldDemo.java
java HiddenFieldDemo
~~~

~~~text
BASE-UPDATED
CHILD-UPDATED
BASE-UPDATED
CHILD-UPDATED
~~~

`super.code` truy cập field của `BaseRecord`, còn `this.code` truy cập field của `DetailedRecord`. Biến `baseView` vẫn trỏ đúng đối tượng `record`, nhưng `baseView.code` đọc field của `BaseRecord` vì kiểu tĩnh của `baseView` là `BaseRecord`.

**Phân biệt hai từ thường gặp:**

- *Field hiding*: lớp con khai báo field trùng tên với field được kế thừa. Dù field là instance hay static, truy cập field vẫn không dùng runtime override.
- *Variable shadowing*: biến cục bộ/tham số có thể che tên field trong một phạm vi; chẳng hạn trong constructor có tham số `code` thì cần `this.code = code`. Shadowing theo phạm vi cũng không phải runtime polymorphism.

Để tránh khó hiểu và lỗi bảo trì, không nên thiết kế hai field có cùng tên ở các tầng kế thừa chỉ để biểu diễn “biến thể” của cùng một thuộc tính.

## 5. Vì sao phương thức `static` cũng không dispatch theo object?

Một phương thức `static` thuộc về **lớp/interface nơi nó được khai báo**, chứ không gắn với một instance cụ thể. Vì vậy Java có thể xác định phương thức mục tiêu theo lớp được gọi hoặc kiểu tĩnh của biểu thức, không cần nhìn vào lớp runtime của đối tượng.

~~~java
class Server {
    static String kind() {
        return "server";
    }
}

class WebServer extends Server {
    static String kind() {
        return "web-server";
    }
}
~~~

Hai khai báo `kind()` tạo quan hệ **method hiding**, không tạo quan hệ overriding. Trong một chương trình khác:

~~~java
Server service = new WebServer();
System.out.println(Server.kind());    // server
System.out.println(WebServer.kind()); // web-server
System.out.println(service.kind());   // server; cú pháp nên tránh
~~~

Dòng `service.kind()` không lựa chọn `WebServer.kind()` theo đối tượng `WebServer`. Dạng đúng, dễ đọc và không tạo ấn tượng sai về đa hình là **`Server.kind()`** khi muốn hành vi ở `Server`, hoặc **`WebServer.kind()`** khi muốn hành vi ở `WebServer`.

Ở mức bytecode, lời gọi static thường dùng lệnh `invokestatic`, còn nhiều lời gọi instance có thể đi qua `invokevirtual` hoặc `invokeinterface`. Đó là cách triển khai tương thích với khác biệt ngữ nghĩa: static call không có cơ chế chọn phương thức override theo receiver giống instance call. Không nên đồng nhất mọi hình thức gọi phương thức instance với đa hình: constructor, phương thức `private` và `final` có những quy tắc riêng; điều cốt lõi là liệu một phương thức **được override hợp lệ** hay không.

### Phương thức `static` không được override bằng phương thức instance

Các đoạn sau là **mã cố ý sai, không biên dịch**:

~~~java
class A {
    static void go() {}
}

class B extends A {
    // void go() {}       // Lỗi: instance method không thể override static method.
    // @Override
    // static void go() {} // Lỗi: @Override không áp dụng cho static method.
}
~~~

Tương tự, nếu `A.go()` là instance method thì lớp con không thể khai báo `static void go()` cùng chữ ký để “thay thế” nó. Đối với static hiding hợp lệ, Java vẫn áp dụng các ràng buộc về chữ ký, phạm vi truy cập và kiểu trả về tương thích; static method của lớp cha khai báo `final` thì không thể bị hide bằng cùng chữ ký trong lớp con.

Dùng `@Override` là một phép kiểm tra rất hữu ích: annotation này hợp lệ cho phương thức override, nhưng trình biên dịch sẽ từ chối nếu bạn cố gắn nó vào static method hiding.

## 6. Bảng quyết định: Java dựa vào thông tin nào?

| Biểu thức / khai báo | Cơ chế | Yếu tố quyết định thành viên được chọn |
| --- | --- | --- |
| `parentRef.field` | Field lookup / field hiding | Kiểu tĩnh của `parentRef` và quy tắc tìm tên, kiểm tra truy cập |
| `Child.field` với static field | Static field lookup | Lớp được chỉ tên |
| `parentRef.staticMethod()` | Static method hiding | Kiểu tĩnh của biểu thức; cú pháp qua tham chiếu không nên dùng |
| `Child.staticMethod()` | Gọi static theo tên lớp | Lớp được chỉ tên |
| `parentRef.instanceMethod()` có override | Runtime dispatch sau khi xác định chữ ký | Lớp thực tế của receiver và triển khai override tương ứng |
| `InterfaceName.staticMethod()` | Gọi static interface method | Chính interface khai báo phương thức |
| `parentRef.defaultMethod()` của interface | Instance method / có thể override | Triển khai runtime phù hợp và quy tắc ưu tiên/hợp nhất method |
| `Parent.CONSTANT` của interface hoặc lớp | Truy cập static field | Tên kiểu; không polymorphic |

Một quy tắc thực hành: **Khi cần hành vi thay đổi theo kiểu đối tượng, hãy biểu diễn hành vi bằng instance method của một hợp đồng lớp cha hoặc interface.** Đừng mong field hoặc static method tự đổi mục tiêu dựa trên lớp đối tượng con.

## 7. Khi nhìn qua interface: field, static, default và abstract method khác nhau thế nào?

Với interface, khác biệt còn rõ hơn:

- Mọi **field khai báo trong interface** ngầm định là `public static final`. Không có field instance ở interface.
- **Static method của interface** thuộc về interface; không được kế thừa như một instance method của lớp `implements` hoặc subinterface. Cần gọi bằng **tên interface khai báo nó**.
- **Abstract method của interface** là hợp đồng instance cần được triển khai bởi lớp cụ thể, trừ khi đã có triển khai hợp lệ từ hệ phân cấp.
- **Default method của interface** cũng là instance method. Lớp triển khai có thể override nó; lời gọi qua tham chiếu kiểu interface tham gia runtime dispatch.

Ví dụ đầy đủ trong tệp **`InterfaceDispatchDemo.java`**:

~~~java
interface Processor {
    String CATEGORY = "processor-field";

    static String family() {
        return "interface-static";
    }

    String process();

    default String description() {
        return "default:" + process();
    }
}

final class TextProcessor implements Processor {
    @Override
    public String process() {
        return "text";
    }

    @Override
    public String description() {
        return "custom:" + process();
    }

    // Khai báo static độc lập của lớp; không override static method của interface.
    public static String family() {
        return "class-static";
    }
}

public class InterfaceDispatchDemo {
    public static void main(String[] args) {
        Processor processor = new TextProcessor();

        System.out.println(Processor.CATEGORY);
        System.out.println(Processor.family());
        System.out.println(TextProcessor.family());
        System.out.println(processor.process());
        System.out.println(processor.description());
    }
}
~~~

~~~bash
javac --release 17 InterfaceDispatchDemo.java
java InterfaceDispatchDemo
~~~

~~~text
processor-field
interface-static
class-static
text
custom:text
~~~

**Phân tích:**

1. `Processor.CATEGORY` là field `public static final`, không gắn với đối tượng `TextProcessor`.
2. `Processor.family()` luôn gọi phương thức static của `Processor`.
3. `TextProcessor.family()` gọi phương thức static do chính `TextProcessor` khai báo. Vì static method của interface **không được kế thừa** vào lớp triển khai, hai phương thức này không tạo quan hệ override.
4. `processor.process()` là lời gọi instance method qua kiểu interface, được chuyển đến `TextProcessor.process()`.
5. `processor.description()` cũng là lời gọi instance method; dù `Processor` có sẵn triển khai `default`, lớp `TextProcessor` override nó, vì vậy kết quả là `custom:text`.

Nếu lớp không override `description()`, lời gọi sẽ sử dụng triển khai `default` trong interface (trừ khi có triển khai instance ở lớp cha có ưu tiên hoặc có xung đột cần giải quyết theo quy tắc Java).

**Cú pháp sai cần tránh:**

~~~java
// Processor processor = new TextProcessor();
// processor.family(); // Lỗi biên dịch: static method của Processor không được gọi qua instance.
// TextProcessor không có family() nếu không tự khai báo phương thức này.
// interface ChildProcessor extends Processor {}
// ChildProcessor.family(); // Lỗi: static method trong Processor không được subinterface kế thừa.
~~~

Khác với static method của **lớp**, static method của **interface** được thiết kế để gọi qua tên interface; không lấy cú pháp `processor.family()` làm phép kiểm tra đa hình.

## 8. Phương thức getter có thể đa hình, field mà nó đọc thì không

Đôi khi ta muốn các lớp con thể hiện “giá trị khác nhau” dưới cùng một hợp đồng. Đặt các field trùng tên và truy cập chúng trực tiếp qua biến lớp cha sẽ không đạt mục tiêu. Có thể khai báo **instance method** và override nó.

Tệp **`PolymorphicValueDemo.java`**:

~~~java
abstract class Shipping {
    public abstract int baseFee();

    public final int totalFee(int surcharge) {
        return baseFee() + surcharge;
    }
}

final class StandardShipping extends Shipping {
    @Override
    public int baseFee() {
        return 20;
    }
}

final class ExpressShipping extends Shipping {
    @Override
    public int baseFee() {
        return 50;
    }
}

public class PolymorphicValueDemo {
    public static void main(String[] args) {
        Shipping standard = new StandardShipping();
        Shipping express = new ExpressShipping();

        System.out.println(standard.baseFee());
        System.out.println(express.baseFee());
        System.out.println(standard.totalFee(5));
        System.out.println(express.totalFee(5));
    }
}
~~~

~~~bash
javac --release 17 PolymorphicValueDemo.java
java PolymorphicValueDemo
~~~

~~~text
20
50
25
55
~~~

`Shipping.baseFee()` là phương thức instance trừu tượng, vì vậy mỗi lớp con cung cấp hành vi riêng. `totalFee()` được khai báo `final`: không thể override, nhưng **lời gọi `baseFee()` bên trong nó vẫn là đa hình**, và kết quả tùy theo đối tượng nhận lời gọi `totalFee()`.

Đây là điểm tinh tế: một phương thức không bị override có thể **gọi một phương thức khác được override**, nhờ vậy kết quả tổng thể vẫn phụ thuộc vào lớp đối tượng thực tế. Không cần dùng field hiding để giải quyết yêu cầu này.

## 9. Đừng nhầm overload được chọn lúc biên dịch với override được chọn lúc chạy

Overload được chọn theo kiểu tĩnh của receiver và đối số; sau đó, nếu chữ ký đã chọn là instance method có thể override, runtime mới chọn implementation theo receiver thực tế. Bài **Chọn overload lúc biên dịch và chọn override lúc chạy** trình bày ví dụ kết hợp hai bước cùng các trường hợp boxing, varargs, `null` mơ hồ và generic erasure.

## 10. Các tình huống dễ nhầm

### 10.1. Ép kiểu tham chiếu không đổi đối tượng

~~~java
Parent one = new Child();
Child two = (Child) one;
~~~

Ở ví dụ `DispatchDemo`, hai biến trỏ cùng một instance `Child`. `one.name` và `two.name` khác nhau vì tra cứu field theo kiểu tĩnh; `one.describe()` và `two.describe()` cùng chạy `Child.describe()`. Ép kiểu **không làm mất trạng thái của đối tượng** và cũng không dựng đối tượng lớp cha mới.

### 10.2. `static` và `final` có phải cùng một ý?

Không:

- `static` định nghĩa thành viên thuộc về lớp hoặc interface, thay vì từng instance.
- `final` có nghĩa khác nhau theo vị trí: field không được gán lại sau khởi tạo, method không được override/hide khi quy tắc Java cấm, class không được kế thừa.
- Một field **`static final`** được truy cập theo lớp như các static field khác; bản thân `final` không tạo cơ chế đa hình cho field.
- Một **instance method `final`** không thể bị override bởi lớp con, nhưng không phải vì nó “trở thành static”. Nó vẫn là method trên đối tượng và có thể sử dụng trạng thái instance hoặc gọi các instance method khác.

### 10.3. Field `private` có “override” được không?

Không. Field không được override ở bất cứ mức truy cập nào. Một field `private` trong lớp cha không được thừa kế theo cách có thể truy cập trực tiếp từ lớp con. Lớp con có thể khai báo một field trùng tên riêng của nó; hai field vẫn là hai vị trí lưu trữ khác nhau. Thiết kế tốt thường để field `private` và cung cấp API instance phù hợp nếu cần hành vi đa hình.

### 10.4. Static method có thể đọc state của object không?

Có, nếu truyền vào object như tham số hoặc nhận được tham chiếu object hợp lệ theo cách khác. Nhưng method vẫn được chọn **tĩnh** theo kiểu tại điểm gọi. Ví dụ `Math.max(a, b)` là static method làm việc trên đối số; việc nó tính từ dữ liệu truyền vào không biến nó thành method đa hình của một đối tượng receiver.

### 10.5. Interface constant có đa hình không?

Không. `interface Config { int TIMEOUT = 10; }` khai báo trường `public static final`. Dùng `Config.TIMEOUT` là truy cập field theo tên interface. Với các hằng `int`/`String` được khởi tạo bằng biểu thức hằng, giá trị còn có thể được compiler nhúng vào mã của bên sử dụng. Vì vậy cập nhật hằng compile-time public đôi khi yêu cầu biên dịch lại các client đã biên dịch trước đó. Đây là một hệ quả thực tế khác của field constant, không liên quan runtime polymorphism.

### 10.6. Truy cập static method qua biến `null`

Với static method được khai báo trong class, `ref.staticMethod()` có thể chạy dù `ref` đang là `null`, vì lời gọi không cần receiver instance; tuy nhiên, biểu thức receiver vẫn được đánh giá. Nên gọi bằng `ClassName.staticMethod()` để làm rõ ý định. Static method của interface phải được gọi qua tên interface khai báo nó và không được kế thừa bởi class triển khai/subinterface.

Lời gọi instance method qua `null` gây `NullPointerException`; bài **Đối tượng null và lời gọi qua tham chiếu interface** giải thích các trường hợp này.

## 11. Tự kiểm tra bằng mã

Đọc đoạn dưới đây:

~~~java
class A {
    String label = "A";

    static String source() {
        return "A-static";
    }

    String message() {
        return "A-method";
    }
}

class B extends A {
    String label = "B";

    static String source() {
        return "B-static";
    }

    @Override
    String message() {
        return "B-method";
    }
}
~~~

Giả sử có:

~~~java
A ref = new B();
~~~

Hãy tự trả lời trước khi xem đáp án:

1. Giá trị của `ref.label` là gì?
2. Giá trị của `ref.source()` là gì? Có nên dùng cú pháp gọi static qua biến này không?
3. Giá trị của `ref.message()` là gì?
4. Nếu thay `ref.label` bằng `((B) ref).label`, kết quả có đổi không? Đối tượng có được tạo mới không?
5. Có thể thêm `@Override` phía trên `static String source()` trong `B` không?
6. Nếu `A.message()` được khai báo `final`, `B` có thể override nó không?

**Đáp án:**

1. `"A"` vì truy cập field theo kiểu tĩnh `A`.
2. `"A-static"` vì static method được chọn theo kiểu tĩnh `A`; nên viết `A.source()`.
3. `"B-method"` vì method instance được `B` override và đối tượng thực tế là `B`.
4. Có: kết quả là `"B"` vì biểu thức sau cast có kiểu tĩnh `B`. Không có đối tượng mới nào được tạo bởi phép cast.
5. Không. Static method trong lớp con *hide* static method lớp cha, không override; `@Override` sẽ tạo lỗi biên dịch.
6. Không. Instance method `final` không được override; sẽ có lỗi biên dịch nếu lớp con cố khai báo bản override.

## 12. Hướng dẫn lựa chọn thiết kế

Khi viết thư viện hoặc ứng dụng Java có nhiều lớp triển khai cùng hợp đồng:

- Cần **hành vi riêng cho từng loại object**: dùng abstract instance method, interface instance method hoặc default method thích hợp.
- Cần **dữ liệu riêng cho mỗi object**: lưu ở field instance (thường là `private`), truy cập qua method có API rõ ràng; đừng dùng field trùng tên để mô phỏng override.
- Cần **hàm tiện ích không phụ thuộc receiver**: dùng static method và gọi rõ tên lớp/interface.
- Cần **hằng số dùng chung**: dùng `static final` với kiểu và vị trí khai báo phù hợp, ý thức rằng field không đa hình và tham chiếu `final` chưa chắc chỉ tới object bất biến.
- Khi đọc biểu thức lạ, hãy hỏi: (1) loại thành viên là field/static/instance? (2) kiểu tĩnh của biểu thức là gì? (3) có override hợp lệ không? (4) lớp thực tế của đối tượng là gì? Chỉ sau khi phân loại đúng mới dự đoán output.

## 13. Kết luận kiến thức

**Truy cập field và static method không đa hình vì Java giải quyết chúng dựa trên kiểu hoặc tên lớp tại thời điểm biên dịch.** Field hiding và static method hiding chỉ tạo khai báo trùng tên ở các lớp khác nhau; không có bước tìm lại thành viên theo lớp đối tượng thực tế.

**Runtime polymorphism thuộc về phương thức instance có thể được override**, bao gồm cả phương thức `default` của interface khi được ghi đè hợp lệ. Một biến kiểu lớp cha có thể tham chiếu lớp con và gọi đúng hành vi instance của lớp con; tuy nhiên cùng biến đó vẫn truy cập field và static method theo kiểu khai báo của nó. Khi cần hành vi biến thiên theo lớp, hãy biểu diễn hợp đồng bằng instance method thay vì phụ thuộc vào field hiding hoặc static method hiding.
