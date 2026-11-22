# Ý nghĩa `this` và `super` trong lambda Java

## 1. Câu hỏi cốt lõi: bên trong lambda, `this` là ai?

Trong Java, lambda biểu diễn hành vi theo một **functional interface** (interface có một phương thức trừu tượng chức năng). Lambda có thể được khai báo bên trong phương thức của một đối tượng và truy cập thành viên của đối tượng đó. Khi ấy, cần phân biệt hai ý tưởng:

- **`this` trong lambda** giữ ý nghĩa của `this` tại **vị trí viết lambda**: nó là đối tượng bao quanh về mặt từ vựng (*lexically enclosing instance*).
- **`super` trong lambda** cũng được hiểu theo **ngữ cảnh lớp bao quanh**: nó cho phép tham chiếu thành viên lớp cha mà lớp hiện tại được quyền gọi, giống như khi viết trực tiếp ở vị trí bao quanh đó.

Lambda **không tạo ra một đối tượng `this` mới cho thân lambda** theo cách một anonymous inner class làm. Tuy runtime cần một đối tượng hoặc cơ chế thực thi phù hợp để biểu diễn functional interface, từ khóa `this` được viết trong thân lambda vẫn tham chiếu đến đối tượng của lớp đang chứa biểu thức lambda.

Đây là khác biệt quan trọng giữa:

~~~java
Runnable lambda = () -> System.out.println(this);
~~~

và:

~~~java
Runnable anonymous = new Runnable() {
    @Override
    public void run() {
        System.out.println(this);
    }
};
~~~

Hai đoạn trên là **minh họa đặt trong một phương thức thể hiện (instance method)**. Ở đoạn đầu, `this` là instance của lớp đang chứa phương thức. Ở đoạn sau, `this` là **instance của lớp ẩn danh** vừa được tạo bằng `new Runnable() {...}`.

Điều này ảnh hưởng đến việc gọi phương thức bị override, truy cập trường, sử dụng `super`, viết callback dài hạn và chuyển code từ anonymous class sang lambda.

## 2. Ôn ngắn: `this` và `super` khi chưa dùng lambda

Giả sử có hai lớp:

~~~java
class Parent {
    String describe() {
        return "parent";
    }
}

class Child extends Parent {
    @Override
    String describe() {
        return "child";
    }

    void print() {
        System.out.println(this.describe());
        System.out.println(super.describe());
    }
}
~~~

Đây là **đoạn minh họa**. Trong `Child.print()`:

- `this.describe()` gọi phương thức theo đối tượng hiện tại. Với instance `Child`, kết quả là **"child"**.
- `super.describe()` chọn implementation của lớp cha **Parent**, kết quả là **"parent"**.
- `this` không đồng nghĩa với “kiểu cha”; `super` cũng không tạo một đối tượng cha mới. Cả hai đang làm việc trong ngữ cảnh của cùng instance nhưng cách **chọn thành viên** khác nhau.

Khi đưa hai biểu thức trên vào **lambda được viết trong phương thức instance của Child**, ý nghĩa này vẫn được giữ lại.

## 3. Ví dụ hoàn chỉnh Java 17: lambda và anonymous class nhìn `this` khác nhau

Tạo tệp **LambdaThisSuperDemo.java**:

~~~java
class ParentPrinter {
    String describe() {
        return "parent";
    }
}

public class LambdaThisSuperDemo extends ParentPrinter {
    private final String name = "child";

    @Override
    String describe() {
        return "child";
    }

    void demonstrate() {
        Runnable lambda = () -> {
            System.out.println("lambda this: " + this.describe());
            System.out.println("lambda super: " + super.describe());
            System.out.println("lambda name: " + this.name);
            System.out.println("lambda this==outer: "
                    + (this == LambdaThisSuperDemo.this));
        };

        Runnable anonymous = new Runnable() {
            @Override
            public void run() {
                System.out.println("anonymous this==outer: "
                        + (((Object) this)
                                == LambdaThisSuperDemo.this));
                System.out.println("anonymous outer: "
                        + LambdaThisSuperDemo.this.describe());
            }
        };

        lambda.run();
        anonymous.run();
    }

    public static void main(String[] args) {
        new LambdaThisSuperDemo().demonstrate();
    }
}
~~~

Biên dịch và chạy bằng **JDK 17 trở lên**:

~~~bash
javac -encoding UTF-8 LambdaThisSuperDemo.java
java LambdaThisSuperDemo
~~~

Stdout:

~~~text
lambda this: child
lambda super: parent
lambda name: child
lambda this==outer: true
anonymous this==outer: false
anonymous outer: child
~~~

Giải thích theo thứ tự:

1. Lambda được viết trong `LambdaThisSuperDemo.demonstrate()`, một **instance method**. Do đó, `this.describe()` gọi implementation của instance `LambdaThisSuperDemo` và in **child**.
2. `super.describe()` trong cùng lambda dùng ngữ cảnh kế thừa của lớp `LambdaThisSuperDemo`, nên gọi implementation trong `ParentPrinter` và in **parent**.
3. `this.name` đọc trường của instance lớp bao quanh, in **child**.
4. `LambdaThisSuperDemo.this` là cú pháp `OuterClass.this` để chỉ rõ instance bao quanh khi được phép. Trong lambda này, `this` và `LambdaThisSuperDemo.this` cùng tham chiếu một đối tượng, nên `==` trả **true**.
5. Trong anonymous class, `this` là instance của chính anonymous class. Phép so sánh được ép một phía sang `Object` để hai tham chiếu có thể so sánh bằng `==`; kết quả là **false**.
6. Từ anonymous class vẫn có thể truy cập instance bao quanh bằng `LambdaThisSuperDemo.this`, vì vậy lời gọi cuối in **child**.

**Hệ quả thực tế:** Chuyển `new Runnable() { ... }` sang `() -> { ... }` có thể làm thay đổi hành vi nếu mã cũ sử dụng `this` hoặc `super`. Hai cách viết không tương đương về ngữ nghĩa receiver, dù cùng tạo callback có phương thức `run()`.

Ví dụ chủ động dùng `Runnable` vì nó có một phương thức `void run()`. Đối với `Supplier<String>` hay `Function<T,R>`, quy tắc `this` và `super` trong lambda vẫn tương tự.

## 4. `super` trong lambda chọn lớp cha của ngữ cảnh nào?

Khi lớp `Child` kế thừa `Parent`, lambda được viết trong instance method của `Child` có thể dùng `super.method()` nếu lời gọi hợp lệ tại vị trí đó. `super` ở đây **không phải** “cha của một đối tượng lambda” hay “cha của functional interface”.

Với đoạn sau (minh họa trong `Child` ở mục 2):

~~~java
Runnable task = () -> {
    System.out.println(super.describe());
};
~~~

Kết quả khi chạy `task.run()` trên một `Child` là **parent**.

Nếu viết lại bằng anonymous class:

~~~java
Runnable task = new Runnable() {
    @Override
    public void run() {
        // super.describe() KHÔNG hợp lệ tại đây:
        // super thuộc ngữ cảnh anonymous class, không phải Child.
        System.out.println(Child.this.describe());
    }
};
~~~

Đây là **đoạn minh họa** trong instance method của `Child`; chú thích chỉ ra code cố ý không được dùng. Anonymous class `new Runnable() {...}` có lớp cha thực tế là `Object` và triển khai `Runnable`. Vì `Object` không định nghĩa `describe()`, `super.describe()` bên trong anonymous class sẽ không biên dịch. `Child.this.describe()` gọi implementation qua instance bao quanh, thường theo virtual dispatch. Để gọi implementation của cha từ một nơi khác, nên đặt logic vào một phương thức phù hợp của `Child` rồi gọi phương thức đó theo hợp đồng rõ ràng.

**Một giới hạn cần nhớ:** `super` vẫn chịu các quy tắc về truy cập, kế thừa, kiểu thành viên và vị trí cú pháp của Java. Việc ở trong lambda không mở thêm quyền truy cập thành viên private của lớp cha hay biến lời gọi không hợp lệ thành hợp lệ.

### 4.1. `super` không đồng nghĩa với dynamic dispatch

Khi override một instance method, `this.method()` thường dùng dynamic dispatch và có thể chọn implementation bị override ở runtime. `super.method()` chỉ định implementation của lớp cha được chọn theo luật Java. Do đó, hai biểu thức có thể trả kết quả khác nhau trên **cùng một instance**.

Không được hiểu `super` như một biến chứa “đối tượng Parent” riêng; nó là cú pháp truy cập thành viên trong quan hệ kế thừa. Cũng không nên sử dụng `super` để bỏ qua thiết kế API: nếu lớp cha cung cấp hành vi cần mở rộng, hãy xem xét liệu override và lời gọi super có đúng hợp đồng hay không.

## 5. Method reference: `this::method` và `super::method`

Java cho phép viết method reference thay cho lambda khi chữ ký phù hợp. Trong ngữ cảnh instance, hai cách sau có thể khác nhau:

- **`this::method`**: tham chiếu phương thức trên receiver hiện tại; với phương thức override, việc gọi thực hiện theo quy tắc dispatch thông thường.
- **`super::method`**: tạo method reference gọi implementation của lớp cha, theo ngữ nghĩa `super.method()` ở vị trí viết.

Tạo tệp **BoundMethodReferenceDemo.java**:

~~~java
import java.util.function.Supplier;

class BaseMessage {
    String message() {
        return "from base";
    }
}

public class BoundMethodReferenceDemo extends BaseMessage {
    @Override
    String message() {
        return "from child";
    }

    void demonstrate() {
        Supplier<String> current = this::message;
        Supplier<String> parent = super::message;

        Supplier<String> currentLambda = () -> this.message();
        Supplier<String> parentLambda = () -> super.message();

        System.out.println(current.get());
        System.out.println(parent.get());
        System.out.println(currentLambda.get());
        System.out.println(parentLambda.get());
    }

    public static void main(String[] args) {
        new BoundMethodReferenceDemo().demonstrate();
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 BoundMethodReferenceDemo.java
java BoundMethodReferenceDemo
~~~

Stdout:

~~~text
from child
from base
from child
from base
~~~

**Giải thích:** `Supplier<String>` có SAM `String get()`; vì vậy method reference tới một phương thức không tham số trả String là phù hợp. Hai cặp biểu thức cho ra cùng kết quả, nhưng điều quan trọng là **receiver/ngữ cảnh gọi** khác nhau. Đây là ví dụ thực tế để kiểm tra việc đổi từ lambda sang method reference có giữ đúng hành vi hay không.

Method reference `this::message` hoặc `super::message` được tạo trong instance context nên có thể gắn với instance đang tồn tại. Nếu callback được giữ lại trong một cấu trúc sống lâu, việc giữ tham chiếu đến callback đó có thể khiến instance được giữ lại lâu hơn mong đợi. Việc quản lý vòng đời vẫn là trách nhiệm của thiết kế ứng dụng.

## 6. Không có `this` hoặc `super` trong static context

Một lambda được viết trong **static method** không có `this` của lớp đang chứa phương thức, vì bản thân static method không gắn với một instance cụ thể.

~~~java
import java.util.function.Supplier;

public class StaticContextDemo {
    private static final String PREFIX = "static:";

    static Supplier<String> makeLabel() {
        return () -> PREFIX + "ready";
    }

    public static void main(String[] args) {
        System.out.println(makeLabel().get());
    }
}
~~~

Tệp **StaticContextDemo.java** trên chạy được:

~~~bash
javac StaticContextDemo.java
java StaticContextDemo
~~~

Stdout:

~~~text
static:ready
~~~

Nếu trong `makeLabel()` bạn viết `() -> this.toString()` hoặc `() -> super.toString()`, mã sẽ **không biên dịch** vì không có instance context. Tương tự, không thể viết `this::someInstanceMethod` trong static method nếu không có receiver hiện hữu.

Cách làm phù hợp nếu cần dùng một instance cụ thể:

~~~java
// Đoạn minh họa có import Supplier.
static Supplier<String> makeFor(Object receiver) {
    return receiver::toString;
}
~~~

Hàm nhận instance làm tham số rồi trả bound method reference; nó không cần `this` ở static context. Nếu interface chỉ yêu cầu một phép biến đổi không phụ thuộc instance, phương thức static hoặc lambda không bắt receiver là đủ.

**Ngoại lệ về cấp độ bao quanh:** một lambda nằm trong instance method nhưng bên trong một đoạn code khác được chạy từ ngữ cảnh static vẫn phải được xét theo **vị trí viết lambda thực tế**. Không suy ra ngữ nghĩa `this` từ nơi callback được gọi. Lambda được khai báo trong instance method giữ liên hệ với instance đó khi được chạy ở luồng khác hay vị trí khác.

## 7. Nested lambda vẫn tuân theo lexical `this`

Nếu lambda trả về một lambda khác, việc lồng nhiều cấp biểu thức **không tự tạo thêm receiver `this`**:

~~~java
import java.util.function.Supplier;

public class NestedLambdaDemo {
    private final String label = "outer";

    Supplier<Supplier<String>> factory() {
        return () -> () -> this.label;
    }

    public static void main(String[] args) {
        NestedLambdaDemo owner = new NestedLambdaDemo();
        System.out.println(owner.factory().get().get());
    }
}
~~~

Chạy:

~~~bash
javac NestedLambdaDemo.java
java NestedLambdaDemo
~~~

Stdout:

~~~text
outer
~~~

Cả hai lambda trong `factory()` đều được viết trong ngữ cảnh instance của `NestedLambdaDemo`. Từ `this.label` ở lambda sâu nhất vẫn là trường của **owner**.

### 7.1. Local variables khác với `this`

Lambda có thể dùng một **biến local** từ phạm vi bao quanh nếu biến đó là **final hoặc effectively final** (được gán một lần theo quy tắc của Java). Ví dụ:

~~~java
String prefix = "item:";
Supplier<String> labeler = () -> prefix + this.label;
~~~

Đây là **đoạn minh họa** đặt trong instance method có import Supplier và một trường `label` tương ứng.

Ở đây có hai nguồn dữ liệu khác nhau:

1. **`prefix`** là local variable được lambda bắt (*captured local variable*), phải là final/effectively final.
2. **`this.label`** là trường của receiver hiện tại. Đối tượng `this` có thể được giữ tham chiếu lại để lambda dùng về sau; nếu trường mutable thì giá trị có thể thay đổi giữa các lần gọi.

`this` không phải một biến local phải tuân thủ luật effectively final giống `prefix`; nó là biểu thức receiver trong ngữ cảnh instance của lớp bao quanh.

### 7.2. Trùng tên tham số của lambda và biến local bao ngoài

Trong Java, lambda không tạo một namespace độc lập cho tên biến local theo cách anonymous class tạo phạm vi lớp riêng. Vì thế không được khai báo lại tham số lambda trùng với biến local cùng phạm vi bao quanh.

~~~java
int quantity = 5;
// KHÔNG BIÊN DỊCH:
// Function<Integer, Integer> f = quantity -> quantity + 1;
~~~

Đây là ví dụ **cố ý sai** để nêu vấn đề shadowing biến local, giả định khai báo cùng phương thức và import Function. Hãy dùng tên khác như `value -> value + 1`.

Ngược lại, tham số lambda có thể trùng tên một **trường instance** mà không vi phạm quy tắc local variable shadowing; khi đó dùng `this.fieldName` để phân biệt trường với tham số. Ngữ nghĩa `this` vẫn là receiver bao quanh.

## 8. Anonymous class và lambda: bảng so sánh quan trọng

| Góc nhìn | Lambda viết trong instance method | Anonymous class `new Runnable() {...}` |
| --- | --- | --- |
| `this` trong body | Instance của lớp bao quanh về mặt từ vựng | Instance của anonymous class |
| `super` trong body | Lớp cha/ngữ cảnh kế thừa của lớp bao quanh | Lớp cha của anonymous class |
| `Outer.this` | Có thể dùng khi có enclosing instance hợp lệ | Có thể dùng để chỉ rõ instance bao quanh hợp lệ |
| Scope của tên biến local | Trong phạm vi dùng tên của khối bao quanh; tránh khai báo trùng | Anonymous class có phạm vi lớp riêng |
| Capture local variable | Chỉ capture biến final/effectively final | Cũng chỉ capture biến local final/effectively final |
| Callback giữ reference tới outer | Có thể khi lambda sử dụng receiver `this`/trường instance | Có thể khi anonymous class tham chiếu instance bao quanh |
| Khả năng viết nhiều method | Target functional interface có một SAM | Anonymous class có thể triển khai kiểu với nhiều phương thức abstract |
| Truy cập `this::method` | Gắn với outer receiver | Trong body, gắn với anonymous receiver nếu dùng `this::method` |

**Một lưu ý về phương thức trong anonymous class:** Nếu anonymous class khai báo phương thức riêng, `this.method()` trong nó có thể gọi phương thức của chính anonymous class. Khi chuyển sang lambda, `this.method()` lại tìm thành viên của lớp bao quanh; code có thể không biên dịch hoặc thay đổi hành vi.

Vì vậy, refactor anonymous class → lambda cần kiểm tra **receiver**, thành viên được chọn, tên biến và mục đích callback. Không đánh giá phép refactor chỉ bằng số dòng ít đi.

## 9. `this` trong lambda không có nghĩa là thread-safe

Lambda có thể giữ receiver và truy cập trường của instance, nhưng **không tự làm đồng bộ hóa** các truy cập đó. Nếu một callback được chuyển sang thread khác hoặc executor, các trường mutable có thể tạo data race nếu không có cơ chế đồng bộ phù hợp.

Ví dụ minh họa:

~~~java
class Counter {
    private int value;

    Runnable incrementAction() {
        return () -> value++;
    }
}
~~~

Đây là đoạn định nghĩa lớp minh họa. `value++` thực hiện đọc, cộng và ghi; không phải phép tăng nguyên tử. Nếu nhiều thread chạy callback trên cùng một `Counter`, kết quả có thể thiếu lần tăng và vi phạm kỳ vọng. Thay đổi sang lambda hoặc sử dụng `this.value++` không làm phép toán an toàn hơn.

Khi callback có thể chạy ở nhiều thread, cần xem xét `AtomicInteger`, đồng bộ hóa, thiết kế bất biến hoặc cơ chế phối hợp phù hợp. Luật **effectively final** đối với biến local được capture cũng không làm những object được tham chiếu trở nên immutable.

## 10. Capture `this`, vòng đời callback và rủi ro giữ instance quá lâu

Một callback được tạo từ instance method có thể sống lâu hơn lần gọi tạo ra nó:

~~~java
import java.util.function.Supplier;

class SessionView {
    private final String id;

    SessionView(String id) {
        this.id = id;
    }

    Supplier<String> snapshotLabel() {
        String snapshot = id;
        return () -> snapshot;
    }

    Supplier<String> liveLabel() {
        return () -> this.id;
    }
}
~~~

Đây là **đoạn minh họa lớp**, không phải chương trình độc lập. Hai phương thức cùng có thể trả chuỗi tương ứng nhưng ý nghĩa capture khác nhau:

- `snapshotLabel()` giữ **local variable** `snapshot`. Lambda không cần truy cập `this` trong thân để đọc giá trị đó.
- `liveLabel()` tham chiếu trường qua `this`, vì vậy callback có thể giữ receiver để đọc trường khi chạy.

**Không được suy luận rằng mọi lambda tạo trong instance method bắt buộc giữ `this`**. Một lambda chỉ dùng hằng số hoặc biến local đã copy có thể không cần giữ receiver. Ngược lại, lambda truy cập instance field hoặc instance method cần receiver tương ứng.

Nếu một listener được đăng ký với đối tượng sống lâu (event bus, scheduler, static registry) và giữ callback tham chiếu `this`, instance chứa listener có thể bị giữ lại lâu hơn ý định. Giải pháp là quản lý đăng ký/hủy đăng ký theo vòng đời, tránh capture receiver không cần thiết, hoặc dùng một mô hình ownership phù hợp. Tương tự, cần thận trọng khi xuất bản `this` qua callback trong constructor trước khi đối tượng được khởi tạo đầy đủ.

## 11. `super` với default method của interface: một biến thể cần biết

Ngoài lớp cha, Java còn có cú pháp **`InterfaceName.super.method()`** để gọi một default method cụ thể của interface khi điều kiện của ngôn ngữ cho phép. Khi biểu thức lambda nằm trong một instance context hợp lệ, cú pháp đó vẫn dựa trên **lớp bao quanh**.

Ví dụ trong lớp triển khai trực tiếp interface:

~~~java
interface Greeter {
    default String message() {
        return "default";
    }
}

class FriendlyGreeter implements Greeter {
    String greeting() {
        Supplier<String> fromDefault =
                () -> Greeter.super.message();
        return fromDefault.get();
    }
}
~~~

Đây là **đoạn minh họa**, cần import `java.util.function.Supplier`. Trong `FriendlyGreeter`, `Greeter.super.message()` chọn default method của interface `Greeter` theo quy tắc của Java. Nó không tham chiếu đến một “interface instance” khác.

Không được sử dụng `InterfaceName.super` tùy tiện: các quy định về **superinterface**, kế thừa default method và vị trí gọi vẫn áp dụng. Nếu có xung đột default method từ nhiều interface, lớp triển khai phải giải quyết xung đột theo quy tắc Java trước khi một lời gọi trong lambda có ý nghĩa hợp lệ.

Trong bài học cơ bản về kế thừa lớp, hãy tập trung trước vào sự khác biệt `this.method()` và `super.method()`; cú pháp cho default method là một trường hợp mở rộng hữu ích khi học interface nâng cao.

## 12. Lỗi phổ biến và cách chẩn đoán

| Tình huống | Vấn đề | Cách xử lý |
| --- | --- | --- |
| Nghĩ `this` trong lambda là đối tượng functional interface | Gọi nhầm trường/method hoặc giải thích sai receiver | Nhìn vị trí khai báo lambda và lớp bao quanh |
| Chuyển anonymous class sang lambda mà giữ `this.method()` | Receiver thay đổi; hành vi hoặc khả năng biên dịch thay đổi | Dùng `Outer.this` khi thực sự cần outer, hoặc xem lại hợp đồng |
| Viết `super.method()` bên trong `new Runnable(){...}` để gọi cha của outer | `super` thuộc anonymous class, thường không có method mong muốn | Đặt lời gọi vào phương thức của outer hoặc chỉnh thiết kế |
| Viết `this` / `super` trong lambda của static method | Không có instance context | Truyền receiver làm tham số hoặc dùng static member |
| Cho rằng `this::method` và `super::method` tương đương | Có thể gọi implementation khác nhau khi override | Xác định rõ mục tiêu dispatch |
| Nghĩ `this` giống local variable captured phải effectively final | Nhầm quy tắc capture và receiver | Phân biệt local variable với instance field |
| Dùng tên tham số lambda trùng biến local bên ngoài | Lỗi redeclaration/shadowing | Đổi tên tham số hoặc biến local |
| Callback lambda cập nhật trường mutable từ nhiều luồng | Data race hoặc lost update | Dùng đồng bộ hóa/atomic/immutable design |
| Listener sống lâu giữ `this` ngoài ý muốn | Instance có thể bị giữ lại quá lâu | Quản lý vòng đời listener và giảm capture cần thiết |
| Gọi `super` để vượt mọi giới hạn truy cập | Java vẫn áp dụng access control | Kiểm tra protected/public và quy tắc kế thừa |

Một cách tự rà soát tại nơi viết lambda:

1. **Lambda đang nằm trong instance method, constructor hay static context?**
2. **Lớp nào bao quanh biểu thức tại vị trí viết?** Đó là nơi xác định `this` và `super`.
3. **Có override thành viên đang gọi không?** `this.method()` và `super.method()` có thể khác kết quả.
4. **Có anonymous class lồng quanh lambda không?** Nếu lambda được viết bên trong phương thức của anonymous class, ngữ cảnh `this` gần nhất thuộc anonymous class đó.
5. **Callback có chạy muộn hoặc trên thread khác không?** Nếu có, kiểm tra vòng đời receiver và tính an toàn trạng thái.
6. **Đang refactor từ anonymous class?** Kiểm tra kỹ mọi chỗ có `this`, `super`, tên trường/method và biến local.

## 13. Bài tập thực hành

### Bài 1: Dự đoán stdout

Dựa trên `LambdaThisSuperDemo`, giải thích lần lượt các dòng **lambda this: child**, **lambda super: parent**, **anonymous this==outer: false** và **anonymous outer: child**. Tại sao cùng viết bên trong phương thức `demonstrate()` mà hai body có `this` khác nhau?

### Bài 2: So sánh hai method reference

Đổi implementation `message()` của `BoundMethodReferenceDemo` để trả **"new child"**. Dự đoán dòng nào đổi và dòng nào vẫn là **"from base"**. Sau đó đổi `current = this::message` thành `() -> this.message()` và kiểm tra kết quả có đổi không.

### Bài 3: Tìm lỗi biên dịch

Giải thích vì sao đoạn này không hợp lệ:

~~~java
// Đoạn cố ý không biên dịch.
static Runnable invalid() {
    return () -> System.out.println(this);
}
~~~

Cần sửa thế nào nếu callback phải hiển thị thông tin của một đối tượng được truyền cho static method?

### Bài 4: Phân biệt snapshot và live reference

Với một lớp có trường `String label` mutable, so sánh callback `() -> label` (truy cập field) với `() -> snapshot` (local variable được copy từ field trước đó). Thay đổi field sau khi tạo callback rồi kiểm tra dự đoán. Cân nhắc tình huống callback được lưu trong registry sống lâu.

### Bài 5: Xem xét thread safety

Cho một callback `() -> counter++` tham chiếu trường `counter` của instance, hãy giải thích vì sao chạy callback từ hai thread không an toàn. Tạo phiên bản dùng `AtomicInteger.incrementAndGet()` và so sánh ngữ nghĩa.

## 14. Ghi nhớ

- Lambda sử dụng **lexical `this` và `super`**: hai từ khóa giữ ý nghĩa từ nơi viết lambda, không trỏ đến “đối tượng lambda”.
- Anonymous class có **`this` riêng**; `super` bên trong nó cũng thuộc ngữ cảnh kế thừa của anonymous class.
- `this::method` và `super::method` có thể tham chiếu đến **implementation khác nhau**, dù cùng là method reference hợp lệ với một SAM.
- Lambda trong **static context** không có `this` hay `super` của một instance; cần truyền receiver khi hành vi phụ thuộc đối tượng.
- Biến local được lambda capture cần **final/effectively final**; quy tắc đó khác với việc truy cập instance field qua `this`.
- Khi lambda giữ receiver, phải xét **vòng đời callback, listener, side effect và thread safety**.

Khi gặp lỗi hoặc bất ngờ về receiver trong callback, đừng bắt đầu từ nơi lambda **được chạy**. Hãy xác định lớp và ngữ cảnh tại nơi biểu thức lambda **được viết**; đó là chìa khóa để hiểu chính xác `this` và `super` trong Java.