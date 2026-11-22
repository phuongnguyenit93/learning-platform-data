# Khối static và khởi tạo dữ liệu cấp lớp trong Java

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích `static field`, `static initializer block` và việc **khởi tạo một lớp/interface** trong Java; phân biệt chúng với dữ liệu và khối khởi tạo của từng đối tượng.
- Dự đoán thứ tự đánh giá **static field initializers** và **static blocks** theo thứ tự xuất hiện trong mã nguồn, sau bước chuẩn bị giá trị mặc định.
- Xác định những tình huống thường làm JVM **khởi tạo lớp lần đầu**, và phân biệt *loading*, *linking*, *initialization*.
- Phân biệt `static final` là **constant variable** có giá trị hằng tại thời điểm biên dịch với `static final` được tính lúc khởi tạo lớp.
- Nhận biết giới hạn **illegal forward reference**, khác biệt giữa truy cập qua tên đơn giản và qualified name, và lỗi logic do đọc giá trị mặc định quá sớm.
- Hiểu quan hệ giữa việc khởi tạo superclass, subclass và interface; tránh suy luận rằng mọi lớp được nhắc đến đều đã khởi tạo.
- Giải thích vì sao khối `static` chạy một lần cho **mỗi lần khởi tạo lớp bởi một defining class loader**, không phải mỗi object hay mỗi lần gọi method.
- Nhận diện hậu quả của exception trong static initialization, rủi ro phụ thuộc vòng và tác động khi nhiều luồng cùng dùng class.
- Thiết kế dữ liệu cấp lớp an toàn: cấu hình không đổi, unmodifiable collections, static factories và kỹ thuật *initialization-on-demand holder*.
- Biên dịch/chạy các ví dụ Java 17+ và đối chiếu stdout chính xác.

## 1. Thành viên static là dữ liệu/hành vi thuộc lớp

Một **instance field** gắn với từng object được tạo bằng `new` (hoặc cơ chế tạo instance tương đương); mỗi instance thường có trạng thái field riêng.

Một **static field** gắn với khai báo class ở runtime, được chia sẻ bởi những đoạn mã nhìn tới **cùng class runtime**. Nó không được tạo mới mỗi lần `new` một object.

~~~java
class Counter {
    static int totalCreated;
    int id;

    Counter() {
        totalCreated++;
        id = totalCreated;
    }
}
~~~

Đây là **khai báo minh họa**, chưa có `main`. Sau hai lần tạo `new Counter()` tuần tự trong một luồng, `Counter.totalCreated` có giá trị 2, còn mỗi object có `id` khác nhau theo logic constructor.

Tuy nhiên, `totalCreated++` **không tự an toàn đa luồng** chỉ vì field là `static`. `static` nói về nơi thuộc về và vòng đời tương đối của thành viên, không cung cấp synchronization.

### 1.1. Cú pháp khối static

Một class có thể chứa một hoặc nhiều **static initializer blocks**:

~~~java
class Settings {
    static int timeoutSeconds;

    static {
        timeoutSeconds = 30;
        System.out.println("Settings initialized");
    }
}
~~~

Khối `static { ... }` chạy khi **class được khởi tạo**, theo quy tắc Java/JVM. Nó không có tên, không nhận parameters, không có return type và không được gọi như một method thông thường.

Không thể viết `Settings.staticBlock()` để “chạy lại” khối static. Nếu muốn chạy một thao tác nhiều lần, hãy đặt thao tác trong method riêng, và có thể gọi method đó từ static block khi cần.

### 1.2. `static` trong class body so với static local variable

Java không hỗ trợ khai báo local variable theo kiểu C/C++ `static int count;` ngay bên trong method để giữ một local variable sống qua nhiều lời gọi. Muốn trạng thái dùng chung, khai báo **static field** ở cấp class, hoặc sử dụng đối tượng/lớp phụ trách state theo thiết kế.

~~~java
class Example {
    private static int calls;

    static void run() {
        calls++;
        int local = calls;
        System.out.println(local);
    }
}
~~~

`calls` là static field. `local` là local variable được tạo trong mỗi lần gọi `run()`. Cả hai có cùng giá trị tại một thời điểm trong ví dụ, nhưng thuộc hai phạm vi và cơ chế lưu trữ khác nhau.

## 2. Hai cách thường dùng để khởi tạo static fields

**Cách 1 — ngay tại khai báo:**

~~~java
class MathConstants {
    static final int BASE = 10;
    static final int SQUARED_BASE = BASE * BASE;
}
~~~

Các biểu thức được gán trong field declarators. Hai giá trị ở đây là các hằng biểu thức kiểu nguyên thủy, sẽ được giải thích kỹ ở phần *constant variables*.

**Cách 2 — static initializer block:**

~~~java
class CacheConfig {
    static final java.util.Map<String, Integer> LIMITS;

    static {
        java.util.Map<String, Integer> data = new java.util.HashMap<>();
        data.put("FREE", 3);
        data.put("PRO", 20);
        LIMITS = java.util.Map.copyOf(data);
    }
}
~~~

Khối static hữu ích khi dữ liệu cần nhiều bước tính toán hoặc validation. `LIMITS` là `static final`: field phải được gán đúng theo quy tắc definite assignment của blank final field; sau khi gán, không thể gán lại field này ở các vị trí tùy ý.

**Lưu ý:** `final` của `Map` chỉ khóa **reference field**; việc map có sửa được hay không còn phụ thuộc object được giữ. Ở đây `Map.copyOf` cho một map không sửa được thông qua API thông thường. Nếu values là mutable objects, bản thân chúng vẫn có thể bị chia sẻ.

### 2.1. Khối static có thể khai báo biến cục bộ

~~~java
static {
    int parsed = 12;
    // parsed chỉ có scope trong block này.
}
~~~

Biến `parsed` là local của static block, không biến thành field cấp lớp. Muốn các methods dùng giá trị sau đó, bạn phải gán vào một static field hoặc lưu trong một object thích hợp.

### 2.2. Khối static không thể dùng `this` hoặc `super`

`this` và `super` mang ý nghĩa của một **instance** trong những ngữ cảnh phù hợp. Static initializer chạy ở mức khởi tạo class, không có “object hiện tại”:

~~~java
class InvalidExample {
    int count = 1;

    static {
        // System.out.println(this.count); // Không biên dịch.
        // System.out.println(count);      // Không có instance receiver.
    }
}
~~~

Bạn có thể truy cập **static members**, gọi static methods hoặc tạo một object một cách tường minh trong block, nhưng không thể ngầm giả định có instance của class để dùng `this`.

## 3. Trình tự class initialization cơ bản

Ở mức học Java Core, mô hình hữu ích:

1. Runtime cần class và thực hiện những bước **loading/linking** theo cơ chế JVM.
2. Trong giai đoạn **preparation**, các static fields được cấp giá trị mặc định thích hợp (`0`, `false`, `null`...), đồng thời một số trường hợp `static final` có `ConstantValue` được xử lý theo quy tắc JVM.
3. Khi class được **initialized**, JVM bảo đảm các superclass liên quan được khởi tạo theo quy tắc trước, cùng các trường hợp superinterfaces có default methods theo JLS.
4. Java thực thi các **static field initializer expressions** và **static initializer blocks** của class theo **thứ tự xuất hiện trong class body**. Chúng cùng tham gia vào quá trình khởi tạo, không phải “tất cả fields trước rồi mới đến blocks”.
5. Khi thành công, class ở trạng thái đã initialized. Việc dùng lại class theo cùng runtime/defining-loader context không tự chạy lại những initializers đó.

Trong mã nguồn, bạn thường quan sát được hai điểm: **thứ tự khai báo** và **khởi tạo đúng một lần** (trừ những tình huống class runtime riêng do loader khác, hoặc cả tiến trình chạy lại).

### 3.1. Static field trước/sau một static block

Lưu file **`StaticOrderDemo.java`**:

~~~java
public class StaticOrderDemo {
    static int first = log("first field", 10);

    static {
        System.out.println("block one: first=" + first);
    }

    static int second = log("second field", 20);

    static {
        System.out.println("block two: second=" + second);
    }

    private static int log(String name, int value) {
        System.out.println(name + "=" + value);
        return value;
    }

    public static void main(String[] args) {
        System.out.println("main: " + first + "," + second);
    }
}
~~~

Biên dịch/chạy với JDK 17 trở lên:

~~~bash
javac StaticOrderDemo.java
java StaticOrderDemo
~~~

**Output:**

~~~text
first field=10
block one: first=10
second field=20
block two: second=20
main: 10,20
~~~

Phân tích thứ tự:

- Trước khi thực thi `main`, class `StaticOrderDemo` phải được initialized.
- `first = log(...)` chạy trước và in `first field=10`.
- Khối static thứ nhất in giá trị `first` đã gán.
- `second = log(...)` chạy tiếp.
- Khối static thứ hai in `second`.
- Sau đó `main` mới in dòng cuối.

**Không đúng** nếu nói các static blocks luôn chạy trước mọi static field initializers; chúng cùng được sắp theo **textual order** trong class.

### 3.2. Phương thức có thể được khai báo ở phía dưới

Trong ví dụ, method `log` nằm sau các field/block gọi nó. Lời gọi method vẫn hợp lệ, vì các method declarations trong class có quy tắc tên/scope riêng. Điều đó **không** có nghĩa method chạy trước: nó chỉ được thực thi khi initializer gọi đến.

## 4. Chỉ khởi tạo khi cần theo quy tắc Java

Một class không nhất thiết được initialized ngay khi máy ảo bắt đầu, chỉ vì source code chứa tên class đó hoặc có file `.class` trong classpath.

Các tình huống thường kích hoạt initialization của class `Target` bao gồm:

- Tạo instance bằng `new Target()` khi Target chưa initialized.
- Gọi một **static method được khai báo bởi Target** theo quy tắc active use.
- Đọc hoặc gán một **static field do Target khai báo** nếu field đó không phải constant variable phù hợp.
- Một số thao tác reflection, như `Class.forName(String)` mặc định yêu cầu initialization.
- Khởi động class chứa method `main` trong một ứng dụng thông thường.

JLS định nghĩa chính xác các trigger; không nên lấy một mẹo đơn giản như “nhắc tới tên lớp là class khởi tạo” làm quy tắc tuyệt đối.

### 4.1. Ví dụ class chỉ initialized ở lần dùng đầu

Lưu **`InitializeOnceDemo.java`**:

~~~java
public class InitializeOnceDemo {
    static class Config {
        static int VALUE = initialize();

        static {
            System.out.println("Config static block");
        }

        private static int initialize() {
            System.out.println("Config field initialized");
            return 7;
        }
    }

    public static void main(String[] args) {
        System.out.println("main begins");
        System.out.println("first access=" + Config.VALUE);
        System.out.println("second access=" + Config.VALUE);
        new Config();
        System.out.println("main ends");
    }
}
~~~

Chạy:

~~~bash
javac InitializeOnceDemo.java
java InitializeOnceDemo
~~~

Output:

~~~text
main begins
Config field initialized
Config static block
first access=7
second access=7
main ends
~~~

- `InitializeOnceDemo` được initialized để chạy `main`; nhưng `Config` là một nested class riêng, chưa nhất thiết initialized từ đầu.
- Lần đầu đọc `Config.VALUE`, JVM initializes `Config`: chạy field initializer rồi static block.
- Lần đọc thứ hai không chạy lại quá trình khởi tạo.
- `new Config()` tạo object mới nhưng **không** chạy lại static field/block của `Config` đã initialized.

Đặt nested class trong file này giúp ví dụ chạy độc lập; bản chất vẫn là một class `Config` ở runtime.

## 5. Phân biệt static initialization với instance initialization

**Static initialization:** logic thuộc **class**, chạy khi class initialized.

**Instance initialization:** logic thuộc **mỗi object**, xảy ra trong quy trình constructor khi tạo instance mới. Có thể dùng instance field initializers và **instance initializer blocks** `{ ... }` không có `static`.

Lưu **`StaticVersusInstanceDemo.java`**:

~~~java
public class StaticVersusInstanceDemo {
    private static int nextId = boot();

    static {
        System.out.println("static block");
    }

    private final int id;

    {
        System.out.println("instance block");
    }

    StaticVersusInstanceDemo() {
        id = ++nextId;
        System.out.println("constructor id=" + id);
    }

    private static int boot() {
        System.out.println("static field initializer");
        return 100;
    }

    public static void main(String[] args) {
        System.out.println("main starts");
        new StaticVersusInstanceDemo();
        new StaticVersusInstanceDemo();
        System.out.println("nextId=" + nextId);
    }
}
~~~

Chạy:

~~~bash
javac StaticVersusInstanceDemo.java
java StaticVersusInstanceDemo
~~~

Output:

~~~text
static field initializer
static block
main starts
instance block
constructor id=101
instance block
constructor id=102
nextId=102
~~~

**Diễn giải:**

1. `nextId = boot()` và static block chạy một lần trước `main`.
2. Mỗi `new StaticVersusInstanceDemo()` chạy **instance block** và constructor logic cho object đó.
3. `id` thuộc mỗi instance, còn `nextId` là static field chia sẻ.
4. `nextId` được tăng trong constructor, **không** tăng chỉ vì có thêm lần đọc field static.

Ví dụ không có superclass tùy chỉnh nên thứ tự dễ quan sát. Khi class có superclass, quy trình tạo object còn liên quan constructor chain `super(...)` và các instance initializers ở từng cấp; điều đó khác với trình tự class initialization.

### 5.1. Không nhầm static block với constructor

| Đặc điểm | Static block | Constructor | Instance initializer block |
| --- | --- | --- | --- |
| Cú pháp | `static { ... }` | `ClassName(...) { ... }` | `{ ... }` trong class body |
| Gắn với | Class initialization | Mỗi lần tạo instance | Mỗi lần tạo instance |
| Tham số | Không | Có thể có | Không |
| `this` | Không dùng được | Dùng được trong instance context phù hợp | Dùng được trong instance context phù hợp |
| Dùng cho | Thiết lập trạng thái cấp lớp | Xây dựng object hợp lệ | Logic chung mỗi object khi thích hợp |
| Lặp lại khi `new` object thứ hai? | Không, nếu class đã initialized | Có | Có |

Một constructor không thể thay thế nhu cầu đặt dữ liệu cấp lớp đúng trước lần gọi static method đầu tiên. Ngược lại, một static block không có object riêng nên không thể khởi tạo instance fields của một object chưa tạo.

## 6. Superclass và subclass: thứ tự khởi tạo

Khi initialized một class con, JVM phải bảo đảm các superclass liên quan đã được initialized theo quy tắc Java. Điều này dẫn tới thứ tự dễ thấy:

- Static field/block của **Base**.
- Static field/block của **Child**.
- Sau đó, nếu tạo object, chuỗi khởi tạo instance superclass rồi subclass.

Lưu **`InheritanceStaticOrderDemo.java`**:

~~~java
public class InheritanceStaticOrderDemo {
    static class Base {
        static int code = log("Base static field", 1);

        static {
            System.out.println("Base static block");
        }

        Base() {
            System.out.println("Base constructor");
        }
    }

    static class Child extends Base {
        static int version = log("Child static field", 2);

        static {
            System.out.println("Child static block");
        }

        Child() {
            System.out.println("Child constructor");
        }
    }

    private static int log(String name, int value) {
        System.out.println(name + "=" + value);
        return value;
    }

    public static void main(String[] args) {
        System.out.println("main begins");
        new Child();
        System.out.println("create second");
        new Child();
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac InheritanceStaticOrderDemo.java
java InheritanceStaticOrderDemo
~~~

Output:

~~~text
main begins
Base static field=1
Base static block
Child static field=2
Child static block
Base constructor
Child constructor
create second
Base constructor
Child constructor
~~~

Ở lần tạo `Child` đầu tiên, class initialization diễn ra một lần; tiếp đó, constructor chain tạo object. Lần tạo thứ hai chỉ chạy các constructors, không chạy lại static initializers.

### 6.1. Field static được khai báo ở superclass

Khi truy cập một static field kế thừa nhưng **thực sự được khai báo** ở superclass, class con không nhất thiết bị initialized chỉ vì biểu thức ghi tên class con.

~~~java
class Base {
    static int VALUE = init();

    static int init() {
        System.out.println("Base initialized");
        return 10;
    }
}

class Child extends Base {
    static {
        System.out.println("Child initialized");
    }
}
~~~

Đây là khai báo minh họa; nếu trong method khác dùng `System.out.println(Child.VALUE);`, field `VALUE` thực sự do `Base` khai báo, nên chỉ việc đọc field đó không bắt buộc khởi tạo `Child`. Class initialization phụ thuộc **lớp khai báo thành viên** và quy tắc active use, không phải chỉ chuỗi ký tự đứng trước dấu chấm.

### 6.2. Interface initialization có quy tắc riêng

Khởi tạo class con và khởi tạo interface không hoàn toàn giống nhau:

- Khi khởi tạo class, các superclass phải initialized theo quy tắc, và một số superinterfaces có khai báo default methods cũng tham gia yêu cầu initialization.
- Khởi tạo một interface **không mặc nhiên yêu cầu khởi tạo mọi superinterface** như quy trình superclass chain của class.
- Fields trong interface ngầm là `public static final`, nhưng không phải tất cả đều là compile-time constants; initializer có thể được chạy khi interface initialized.

Đừng lấy ví dụ class extends class rồi suy ra interface extends interface sẽ cho ra cùng thứ tự in dòng trong mọi trường hợp.

## 7. `static final` không phải lúc nào cũng là constant variable

So sánh:

~~~java
static final int MAX_RETRIES = 3;
static final String PRODUCT = "Demo";
static final int GENERATED = compute();
static final java.util.List<String> LABELS =
        java.util.List.of("A", "B");
~~~

- `MAX_RETRIES` và `PRODUCT` là **constant variables** nếu được khai báo final đúng kiểu primitive hoặc String và initialized bởi **constant expressions**. Compiler có thể dùng giá trị hằng mà không cần class initialization của nơi khai báo.
- `GENERATED` là static final nhưng gọi method `compute()`; nó **không** phải compile-time constant.
- `LABELS` là static final reference tới List object; không phải compile-time constant variable vì kiểu không phải primitive/String và cần tạo/nhận object tại runtime.

Do đó không thể nói **“mọi lần đọc static final đều không khởi tạo class”** hoặc **“mọi static final đều immutable sâu”**.

### 7.1. Ví dụ constant variable không kích hoạt khối static

Lưu **`ConstantInitializationDemo.java`**:

~~~java
public class ConstantInitializationDemo {
    static class Constants {
        static final int LITERAL = 42;
        static final String GREETING = "Hello";
        static final int COMPUTED = compute();

        static {
            System.out.println("Constants initialized");
        }

        private static int compute() {
            System.out.println("compute called");
            return 7;
        }
    }

    public static void main(String[] args) {
        System.out.println("literal=" + Constants.LITERAL);
        System.out.println("greeting=" + Constants.GREETING);
        System.out.println("before computed");
        System.out.println("computed=" + Constants.COMPUTED);
    }
}
~~~

Chạy:

~~~bash
javac ConstantInitializationDemo.java
java ConstantInitializationDemo
~~~

Output:

~~~text
literal=42
greeting=Hello
before computed
compute called
Constants initialized
computed=7
~~~

Giải thích:

1. Hai lần đọc `Constants.LITERAL` và `Constants.GREETING` có thể dùng giá trị **constant expressions**, không khởi tạo `Constants`.
2. Lần đọc `Constants.COMPUTED` là active use của field không phải constant variable; `Constants` initialized.
3. Field initializer `compute()` in `compute called`.
4. Static block in `Constants initialized`.
5. Cuối cùng mới in `computed=7`.

### 7.2. Hệ quả khi thay đổi public compile-time constants

Với code đã biên dịch ở các module/project khác, giá trị của một public compile-time constant có thể đã được **nhúng vào bytecode client**. Nếu thư viện đổi `public static final int LIMIT = 10` thành 20 nhưng client **không được biên dịch lại**, client có thể vẫn dùng giá trị cũ.

Đây là một rủi ro tương thích nhị phân cần nhớ khi công bố API. Nếu giá trị cấu hình cần thay đổi theo phiên bản/chạy thực tế, cân nhắc **method truy cập** hoặc field không phải constant variable, thay vì hằng public được inline.

Đồng thời, `final` trên một object reference không ngăn code khác thay đổi mutable object mà reference đó trỏ tới.

## 8. Static forward reference: tên trong scope chưa đủ

Trong class body, fields có scope theo các quy tắc Java; nhưng khi **static field initializer** hoặc **static initializer block** truy cập **static field khai báo phía sau bằng tên đơn giản**, có các hạn chế **illegal forward reference**.

Ví dụ cố ý sai:

~~~java
class BadOrder {
    static int a = b; // Compile error: illegal forward reference.
    static int b = 10;
}
~~~

Đây là ví dụ lỗi minh họa; **không** đưa nguyên khối vào project muốn biên dịch thành công.

Một cách thường dùng là **đặt khai báo phụ thuộc lên trên**:

~~~java
class GoodOrder {
    static int b = 10;
    static int a = b;
}
~~~

Không nên “lách” hạn chế bằng qualified name rồi suy luận rằng giá trị đã sẵn sàng. Qualified access hoặc truy cập qua method có thể dẫn tới quan sát **giá trị mặc định khi initialization chưa đến lượt field đó**.

### 8.1. Ví dụ biên dịch nhưng cho kết quả bất ngờ

Lưu **`ForwardReferenceDemo.java`**:

~~~java
public class ForwardReferenceDemo {
    static class Values {
        static int first = Values.second;
        static int second = 10;

        static {
            System.out.println("first=" + first);
            System.out.println("second=" + second);
        }
    }

    public static void main(String[] args) {
        System.out.println("main first=" + Values.first);
        System.out.println("main second=" + Values.second);
    }
}
~~~

Chạy:

~~~bash
javac ForwardReferenceDemo.java
java ForwardReferenceDemo
~~~

Output:

~~~text
first=0
second=10
main first=0
main second=10
~~~

Tại lúc evaluating `first = Values.second`, class `Values` đang trong quá trình initialization, nhưng initializer của `second = 10` **chưa chạy**. Field `second` đang mang giá trị mặc định `0` theo preparation, nên `first` được gán 0. Sau đó `second` được gán 10, **không cập nhật lại** `first`.

Ví dụ này đặc biệt có ích để phân biệt:

- **Tên nhận diện được** (qualified reference biên dịch).
- **Field đã hoàn tất khởi tạo chưa** (chưa, nên có default value).
- **Sự phụ thuộc dữ liệu đúng** (trật tự khởi tạo sai ý định).

Trong code thật, hãy khai báo dependency trước dependent value, hoặc dùng một factory method có cấu trúc phụ thuộc rõ ràng; tránh các thủ thuật đánh lừa forward-reference check.

### 8.2. Vì sao static final không luôn cứu được?

Nếu field thứ hai là **compile-time constant variable**, ngữ nghĩa của nó khác static field cần runtime computation. Nhưng nếu bạn dựa vào `static final Value settings = load();` hoặc `static final int value = compute();`, đó vẫn là initialization có thời điểm chạy; `final` không đưa việc tính vào một “thời điểm thần kỳ” trước mọi code.

Luôn phân tích **loại initializer**, **thứ tự khai báo**, và **triggers** thay vì chỉ dựa vào modifier `final`.

## 9. Chu trình phụ thuộc khi khởi tạo static

Một thiết kế dễ lỗi là class A cần giá trị static từ B, trong khi B cũng cần giá trị static từ A. JVM có cơ chế xử lý recursive initialization theo từng luồng, nhưng logic có thể dùng **giá trị mặc định chưa hoàn tất**, tạo kết quả lạ.

Lưu **`StaticCycleDemo.java`**:

~~~java
public class StaticCycleDemo {
    static class Alpha {
        static int value = Beta.value + 1;
    }

    static class Beta {
        static int value = Alpha.value + 1;
    }

    public static void main(String[] args) {
        System.out.println("alpha=" + Alpha.value);
        System.out.println("beta=" + Beta.value);
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac StaticCycleDemo.java
java StaticCycleDemo
~~~

Output:

~~~text
alpha=2
beta=1
~~~

Truy vết:

1. Lần đọc `Alpha.value` bắt đầu initialization của Alpha.
2. Alpha cần `Beta.value`, dẫn tới initialization của Beta.
3. Beta đọc `Alpha.value` khi Alpha **đang initialized bởi cùng luồng**. Giá trị field Alpha lúc này vẫn là mặc định 0.
4. Beta tính `0 + 1 = 1` và hoàn tất.
5. Alpha tính `1 + 1 = 2` và hoàn tất.
6. Hai dòng in lần lượt là `alpha=2`, `beta=1`.

**Lưu ý:** Kết quả phụ thuộc đường kích hoạt. Nếu khởi tạo Beta trước Alpha trong một thiết kế tương tự, bạn có thể quan sát một kết quả khác. Các static dependencies vòng khiến code khó hiểu và dễ lỗi.

### 9.1. Cách tránh phụ thuộc vòng

- Đặt dữ liệu cần thiết trong một nơi có trách nhiệm rõ ràng, không để hai class cần nhau để hoàn thành `static` initialization.
- Dùng constructor/factory để đưa dependencies vào khi khởi tạo **đối tượng**, nếu dependency là state ứng dụng.
- Dùng **lazy initialization** có kiểm soát khi đối tượng tốn chi phí tạo hoặc cần trì hoãn, nhưng vẫn tránh vòng.
- Dùng tests khởi tạo trong một JVM sạch để kiểm tra kết quả: class đã initialized ở test trước có thể che lỗi thứ tự trong test sau.

Nếu nhiều luồng tạo vòng chờ nhau ở giai đoạn class initialization hoặc nắm các locks khác, có nguy cơ deadlock phức tạp. Đó là lý do nên giữ static initialization đơn giản.

## 10. Khởi tạo class có thể bị lỗi

Nếu exception xảy ra khi đánh giá một static field initializer hoặc static block, initialization của class có thể thất bại.

Thông thường:

- Nếu nguyên nhân là một non-`Error` throwable (như `IllegalStateException`), JVM báo lỗi khởi tạo lớp ở lần đầu bằng `ExceptionInInitializerError`, kèm nguyên nhân.
- Sau khi class được đánh dấu initialization thất bại, những lần active use tiếp theo của **class runtime đó** có thể ném `NoClassDefFoundError` cho biết class không thể initialized.
- Nếu lỗi gốc là `Error`, Java có các quy tắc lan truyền khác, không được khẳng định lúc nào cũng bọc mọi thứ trong `ExceptionInInitializerError`.
- Không có “chạy lại static block” bằng cách thử `new` lần nữa trên cùng class đã đánh dấu erroneous.

### 10.1. Ví dụ chạy được và bắt lỗi để minh họa

Lưu **`StaticInitializationFailureDemo.java`**:

~~~java
public class StaticInitializationFailureDemo {
    static class Broken {
        static int VALUE = load();

        private static int load() {
            System.out.println("load attempted");
            throw new IllegalStateException("invalid startup configuration");
        }
    }

    public static void main(String[] args) {
        for (int attempt = 1; attempt <= 2; attempt++) {
            try {
                System.out.println(Broken.VALUE);
            } catch (Error error) {
                System.out.println("attempt " + attempt + ": " +
                        error.getClass().getSimpleName());
            }
        }
    }
}
~~~

Chạy:

~~~bash
javac StaticInitializationFailureDemo.java
java StaticInitializationFailureDemo
~~~

Output:

~~~text
load attempted
attempt 1: ExceptionInInitializerError
attempt 2: NoClassDefFoundError
~~~

**Chỉ bắt `Error` ở ví dụ để quan sát cơ chế runtime**, không phải hướng dẫn code ứng dụng bắt/nuốt mọi `Error`. Với ứng dụng thật, hãy xác định chính sách startup fail-fast, logging nguyên nhân gốc, cấu hình hợp lệ trước khi load hoặc phục hồi bằng cơ chế rõ ràng.

### 10.2. Có thể viết `throw` checked exception trực tiếp từ static block không?

Static initializer **không được phép hoàn tất bất thường vì checked exception** mà không xử lý theo quy tắc Java; không thể đơn giản ghi `static { throw new IOException(); }` và mong compiler chấp nhận. Nếu thao tác tải file ném checked exception, cần bắt/xử lý, hoặc chuyển thành một exception phù hợp để phản ánh lỗi khởi tạo.

Không có khái niệm `throws IOException` gắn trực tiếp vào một static block như chữ ký method.

## 11. Khối static với dữ liệu cấp lớp phức tạp

Một ứng dụng có bảng ngưỡng cố định cần xây dựng và validate:

~~~java
static final Map<String, Integer> LIMITS;

static {
    Map<String, Integer> draft = new HashMap<>();
    draft.put("BASIC", 3);
    draft.put("PLUS", 10);
    // Validate dữ liệu trước khi công bố.
    LIMITS = Map.copyOf(draft);
}
~~~

Đây là **mảnh minh họa** cần import `Map`, `HashMap` và đặt trong class. Lưu ý danh sách/map cấp lớp không nên là một mutable singleton vô tình có thể bị caller thay đổi ngoài API.

### 11.1. Chương trình hoàn chỉnh: dựng immutable map trong static block

Lưu **`StaticConfigurationDemo.java`**:

~~~java
import java.util.HashMap;
import java.util.Map;

public class StaticConfigurationDemo {
    private static final Map<String, Integer> LIMITS;

    static {
        Map<String, Integer> draft = new HashMap<>();
        draft.put("BASIC", 3);
        draft.put("PLUS", 10);

        if (draft.values().stream().anyMatch(value -> value <= 0)) {
            throw new IllegalStateException("invalid limit");
        }

        LIMITS = Map.copyOf(draft);
        System.out.println("configuration initialized");
    }

    public static int maxItems(String tier) {
        Integer value = LIMITS.get(tier);
        if (value == null) {
            throw new IllegalArgumentException("unknown tier");
        }
        return value;
    }

    public static void main(String[] args) {
        System.out.println("BASIC=" + maxItems("BASIC"));
        System.out.println("PLUS=" + maxItems("PLUS"));

        try {
            LIMITS.put("BASIC", 999);
        } catch (UnsupportedOperationException expected) {
            System.out.println("configuration read-only");
        }

        System.out.println("BASIC after attempt=" + maxItems("BASIC"));
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac StaticConfigurationDemo.java
java StaticConfigurationDemo
~~~

Output:

~~~text
configuration initialized
BASIC=3
PLUS=10
configuration read-only
BASIC after attempt=3
~~~

- Static block chạy trước `main` vì class được initialized để bắt đầu chương trình.
- `draft` chỉ là mutable local Map dùng để xây dựng dữ liệu.
- `Map.copyOf` cho một map không sửa được, giữ state có trách nhiệm ở cấp lớp.
- Caller không thể thay nội dung `LIMITS` qua `put` trên map kết quả.
- Giá trị là `Integer` immutable, nên không có mutability gián tiếp qua values trong ví dụ.

### 11.2. Đừng lưu secrets trong public static fields

Nếu cấu hình chứa API keys, credentials hoặc bí mật khác, không đặt chúng ở public fields hay in ra log static initializer. `private` trong Java giúp giảm bề mặt API nhưng **không** thay cho mô hình quản lý bí mật, phân quyền, mã hóa và môi trường triển khai an toàn.

## 12. Khởi tạo lười với initialization-on-demand holder

Nếu đối tượng cấp lớp đắt chi phí tạo và không cần cho mọi đường chạy, khởi tạo sớm ở class chính có thể tốn tài nguyên không cần thiết.

Một idiom Java thường dùng là **initialization-on-demand holder**:

- Class public chứa static method `get()`.
- Một nested static class `Holder` chứa static final value cần khởi tạo.
- `Holder` chỉ initialized khi được active used thích hợp.
- JVM class initialization cung cấp cơ chế thread-safe initialization cho class theo chuẩn; đối tượng trả về có được thread-safe khi sử dụng về sau hay không vẫn là câu hỏi riêng.

Lưu **`LazyHolderDemo.java`**:

~~~java
public class LazyHolderDemo {
    static final class Registry {
        private Registry() {
        }

        private static String make() {
            System.out.println("resource created");
            return "READY";
        }

        private static class Holder {
            static final String RESOURCE = make();
        }

        static String get() {
            return Holder.RESOURCE;
        }
    }

    public static void main(String[] args) {
        System.out.println("before first get");
        System.out.println("first=" + Registry.get());
        System.out.println("second=" + Registry.get());
    }
}
~~~

Chạy:

~~~bash
javac LazyHolderDemo.java
java LazyHolderDemo
~~~

Output:

~~~text
before first get
resource created
first=READY
second=READY
~~~

**Giải thích:**

- `Registry.get()` là một static method nên việc gọi nó cần initialization của `Registry`.
- `Holder` là nested static class **riêng**, chưa nhất thiết initialized ngay lúc `Registry` initialized.
- `Holder.RESOURCE` được gán bằng lời gọi method `make()`, nên **không** là compile-time constant variable; lần đọc đầu kích hoạt `Holder` initialization.
- Những lần đọc tiếp theo nhận cùng giá trị đã lưu, không gọi lại `make()`.

**Quan trọng:** Giá trị `"READY"` được trả về từ một method, không khai báo trực tiếp bằng string literal ở `Holder.RESOURCE`. Điều này tránh biến `RESOURCE` thành constant variable được inline, vốn sẽ làm ví dụ lazy initialization sai ý đồ.

### 12.1. Idiom này có giới hạn gì?

- Nó phù hợp với một resource/value khởi tạo một lần, nhưng nếu tạo thất bại thì class holder có thể trở thành erroneous; không tự retry mỗi lần gọi.
- Nó không giải quyết nhu cầu đóng tài nguyên (`close()`) hoặc vòng đời có start/stop/reset phức tạp.
- Nó không khiến object mutable được chia sẻ tự thread-safe.
- Với dependency injection hoặc application lifecycle phức tạp, quản lý đối tượng trong container/service có thể rõ ràng hơn.

## 13. `Class.forName` và class literal: có thể khác về thời điểm initialization

Đọc `Target.class` cho `Class` object tương ứng **không tự đòi initialized Target** trong ví dụ thông thường. Nhưng overload đơn giản `Class.forName(String)` có tác dụng khởi tạo class được yêu cầu theo hợp đồng API.

Lưu **`ClassLiteralInitializationDemo.java`**:

~~~java
public class ClassLiteralInitializationDemo {
    static class Target {
        static {
            System.out.println("Target initialized");
        }
    }

    public static void main(String[] args) throws ClassNotFoundException {
        System.out.println("before literal");
        Class<?> type = Target.class;
        System.out.println("after literal=" + type.getSimpleName());

        Class.forName(type.getName());
        System.out.println("after forName");

        Class.forName(type.getName());
        System.out.println("after second forName");
    }
}
~~~

Chạy:

~~~bash
javac ClassLiteralInitializationDemo.java
java ClassLiteralInitializationDemo
~~~

Output:

~~~text
before literal
after literal=Target
Target initialized
after forName
after second forName
~~~

Dòng `Target initialized` xuất hiện khi gọi `Class.forName(type.getName())` lần đầu, **không phải** ngay sau `Target.class`. Gọi lại với cùng class runtime không chạy lại static block.

Nếu cần load mà chưa initialize, API có overload `Class.forName(String name, boolean initialize, ClassLoader loader)` với cờ `initialize`. Tuy nhiên, class loading/reflective APIs có các chi tiết ngoại lệ và class loader riêng; không nên dùng reflection chỉ để điều khiển order tùy tiện khi source-level design có thể rõ ràng hơn.

## 14. Khối static được đồng bộ khởi tạo, nhưng static state không tự thread-safe

JVM có quy trình phối hợp class initialization giữa các threads. Khi một thread đang initialized một class, threads khác cần active use class đó thường phải chờ hoặc theo đúng các trạng thái initialization được định nghĩa.

Điều này tạo một **điểm an toàn** để công bố state được xây dựng đúng trong quá trình class initialization. Nhưng sau khi initialization hoàn tất:

~~~java
class SharedCounter {
    static int count;

    static void increment() {
        count++; // Không atomic khi có nhiều threads.
    }
}
~~~

`count++` vẫn có thể race nếu nhiều threads đồng thời gọi. `static` không bảo đảm atomicity, visibility của mutable updates hoặc bảo toàn invariants sau đó.

Nếu cần mutable counter dùng chung, có thể sử dụng `AtomicInteger` hoặc synchronization phù hợp:

~~~java
class SharedCounter {
    private static final java.util.concurrent.atomic.AtomicInteger COUNT =
            new java.util.concurrent.atomic.AtomicInteger();

    static int increment() {
        return COUNT.incrementAndGet();
    }
}
~~~

Đây là class minh họa; `COUNT` được khởi tạo một lần khi class initialized. `AtomicInteger.incrementAndGet()` có atomic semantics phù hợp cho một phép tăng đơn giản. Nếu cần cập nhật nhiều fields nhất quán như một giao dịch, một atomic counter riêng chưa đủ.

### 14.1. Class initialization với hai threads

Nếu thread A đang chạy static initializer, thread B cố dùng class cùng lúc, JVM phải phối hợp để không coi class initialized hoàn chỉnh từ hai đường độc lập. Tuy nhiên, nếu static initializer tự chờ thread khác, thread kia lại chờ class initialization, ứng dụng có thể gặp deadlock.

**Không nên** thực hiện network blocking, chờ thread phức tạp, gọi dependency vòng hoặc tạo event loop trong static block nếu không có lý do chắc chắn và contract khởi động rõ.

## 15. Số lần static initialization phụ thuộc runtime class identity

Một câu thường nghe là “static block chạy đúng một lần trong toàn bộ chương trình”. Cách nói đó **cần điều kiện**.

Thực tế, class runtime được xác định bởi **tên nhị phân và defining class loader** theo Java/JVM. Hai class loaders khác nhau có thể định nghĩa hai class runtime riêng cho cùng tên mã nguồn/binary name, và mỗi class có initialization state riêng.

Ở một ứng dụng đơn giản dùng một application class loader và chạy một JVM, bạn thường quan sát một lần initialization cho một class. Nhưng trong application servers, plugins, test frameworks hoặc hot reload, **cùng tên class** không nhất thiết đại diện cùng class runtime identity.

Nếu chạy lại chương trình ở **tiến trình JVM mới**, static initialization lại diễn ra trong tiến trình mới. Không nên dùng static fields như kho lưu dữ liệu bền vững qua các lần chạy.

### 15.1. Static fields có thật sự là global variables?

Trong một ứng dụng nhỏ, static field được nhiều object dùng chung nên **giống global state**. Nhưng:

- Quyền truy cập còn phụ thuộc `private`/package/protected/public` và module.
- Class loader boundaries có thể tạo nhiều class runtimes.
- Mutable static state làm tests phụ thuộc lẫn nhau, gây hidden coupling.
- Mọi threads có thể cùng đụng vào state nếu được chia sẻ.

Vì vậy, hạn chế **mutable public static fields**. Ưu tiên immutable constants, stateless utilities hoặc dependencies được truyền rõ ràng khi có state phức tạp.

## 16. Trình tự khởi tạo khi fields và static blocks phụ thuộc nhau

Hãy lập một bảng thời gian:

| Bước | Khai báo gặp trong source | Hành vi |
| --- | --- | --- |
| 1 | `static int a = initA();` | Tính/gán `a` |
| 2 | `static { configure(); }` | Chạy `configure()` |
| 3 | `static int b = initB();` | Tính/gán `b` |
| 4 | `static { verify(); }` | Chạy `verify()` |

Nếu `initA()` đọc `b` trước bước 3, có thể nhận giá trị mặc định 0, tùy cách code và các forward-reference rules. Nếu `verify()` dựa trên cả `a`, `b`, đặt nó **sau** hai initializers là rõ ràng hơn.

### 16.1. Dồn initialization phức tạp vào method có tên

Thay vì một static block dài:

~~~java
static final Settings SETTINGS = loadAndValidateSettings();

private static Settings loadAndValidateSettings() {
    // Read/configure/validate một cách có cấu trúc.
    return new Settings();
}
~~~

Đây là **mảnh minh họa** cần class `Settings`/logic phù hợp. Dùng method có tên giúp tách trách nhiệm, viết tests cho logic thuần khiết, và khiến static initialization chỉ còn một bước gán rõ ràng.

Nhưng gọi method không biến code này thành lazy: vì `SETTINGS` là static field initializer gọi method, nó vẫn chạy khi class initialized. Muốn trì hoãn, có thể dùng holder hoặc lifecycle service như phần trên.

## 17. Khi nào không nên dùng static initialization?

Dùng static initializer thường phù hợp với:

- Bảng tra cứu nhỏ, immutable, không cần đọc dịch vụ ngoài.
- Constants/runtime values không đổi suốt vòng đời class.
- Những phép thiết lập nội bộ đơn giản có thể hoàn thành nhanh và dự đoán được.

Cân nhắc **tránh static block** cho:

- Kết nối database/network cần retry, shutdown, kiểm soát credentials, metrics hoặc cấu hình runtime.
- State thuộc từng user/session/request/tenant.
- Dữ liệu cần reload giữa lúc chương trình chạy.
- Logic phụ thuộc thứ tự class initialization khó đoán hoặc có vòng phụ thuộc.
- Công việc có side effects lớn; nếu fail thì cả class trở thành unusable trong defining-loader context.
- Mã test cần thay thế dependency hoặc tạo nhiều trạng thái độc lập.

Với những trường hợp đó, constructor, factory, dependency injection, application startup service hoặc lazy holder có kiểm soát thường dễ vận hành hơn.

## 18. Lỗi thường gặp và hướng khắc phục

| Hiểu nhầm/lỗi | Giải thích đúng |
| --- | --- |
| “`static` block chạy mỗi lần tạo object.” | Nó gắn với class initialization, không phải mỗi instance. |
| “Mọi static field đều gán trước mọi static block.” | Field initializers và blocks chạy xen kẽ theo thứ tự khai báo. |
| “Khai báo method phía dưới là không gọi được trong block phía trên.” | Method declarations có quy tắc scope riêng; method có thể được gọi từ initializer. |
| “`static final` luôn là compile-time constant.” | Chỉ khi đúng kiểu primitive/String và initializer là constant expression theo JLS. |
| “Đọc mọi static final đều initialized class.” | Đọc constant variable có thể không trigger initialization. |
| “`new` object thứ hai sẽ chạy lại static initializer.” | Class đã initialized thường không lặp lại logic static. |
| “`this` dùng được trong static block.” | Static context không có current instance. |
| “Tên field trong scope thì giá trị đã được khởi tạo.” | Có thể còn default value do chưa tới lượt initializer. |
| “Qualified name vượt forward reference thì luôn an toàn.” | Qualified access có thể thấy default value sớm; đó là bug logic. |
| “`Child.VALUE` luôn initialized Child.” | Nếu field được khai báo ở Base, việc đọc có thể chỉ initialized Base. |
| “Khởi tạo class con luôn giống quy tắc interface.” | Interface initialization có quy tắc riêng. |
| “`Class.forName` và `Target.class` luôn giống nhau.” | `Target.class` không tự initialize Target; `Class.forName(String)` có thể yêu cầu initialized class. |
| “Exception trong static block được retry ở lần truy cập sau.” | Class initialization thất bại có thể đánh dấu class erroneous, dùng sau bị `NoClassDefFoundError`. |
| “Static blocks chạy đúng một lần cho mọi class cùng tên trên tất cả class loaders.” | Mỗi runtime class do defining class loader xác định có initialization state riêng. |
| “`private static final List` luôn immutable.” | Final khóa reference; list object có thể mutable nếu không được bảo vệ. |
| “Map static có thể dùng HashMap mutable public cho tiện.” | Caller có thể phá shared configuration; dùng private + unmodifiable map/API phù hợp. |
| “Static initialization thread-safe nên static counter ++ cũng thread-safe.” | Bảo đảm khởi tạo không biến subsequent mutable operations thành atomic. |
| “Static block thích hợp để bắt đầu mọi I/O và thread.” | Nó khó quản lý lifecycle/retry; cân nhắc explicit startup services. |
| “Muốn chạy lại block thì gọi static method.” | Gọi method khác không tự chạy lại static block; chỉ code trong method được gọi chạy. |

## 19. Checklist đọc một đoạn mã có `static`

Khi gặp:

~~~java
class Example {
    static int a = calculateA();
    static { initialize(); }
    static final int b = 5;
}
~~~

hãy tự hỏi:

1. **Class đã được initialized chưa?** Nếu chưa, đoạn code nào kích hoạt nó?
2. **`b` có phải compile-time constant không?** Đọc `b` có thể không kích hoạt class.
3. **Superclass đã được initialized chưa?** Có superinterface default methods cần xét không?
4. **Các static field initializers và blocks xuất hiện theo thứ tự nào?**
5. **Có field nào bị đọc trước khi initializer của nó chạy không?** Có thể thấy default value hoặc illegal forward reference.
6. **Có dependency vòng giữa classes không?**
7. **Static block có thể ném exception không?** Nếu thất bại, ứng dụng xử lý startup ra sao?
8. **Dữ liệu sau initialized có bị bên ngoài sửa được không?** `static final` reference chưa chắc immutable referent.
9. **Nếu nhiều threads truy cập, có đồng bộ hóa subsequent mutations không?**
10. **State này thuộc class hay thực ra thuộc instance/request/user?**
11. **Dữ liệu có cần reload/lazy load không?** Có thể dùng holder hoặc service riêng?
12. **Test chạy ở một JVM hay có nhiều class loaders?** Không nên dựa vào “một lần duy nhất toàn hệ thống” nếu context khác nhau.

## 20. Bài tập tự kiểm tra có lời giải

**Câu 1.** Một class có `static { System.out.println("INIT"); }` và constructor in `NEW`. Nếu tạo hai objects liên tiếp trong cùng JVM/class loader, thông thường in gì?  
**Đáp án:** `INIT` một lần trước object đầu tiên, rồi `NEW` hai lần. Static initialization không lặp với mỗi `new`.

**Câu 2.** Có hai khai báo: `static int a = log("A");` rồi `static { log("B"); }`. Dòng nào in trước?  
**Đáp án:** `A` trước `B` vì field initializer và static block theo thứ tự xuất hiện.

**Câu 3.** Vì sao static block không được dùng `this.value`?  
**Đáp án:** Static context không có current instance để `this` trỏ tới.

**Câu 4.** Field `static final int MAX = 10;` khác `static final int MAX = calculate();` ở đâu?  
**Đáp án:** Trường hợp đầu có thể là constant variable; trường hợp sau phải tính runtime nên không phải compile-time constant.

**Câu 5.** Đọc `Constants.MAX` với MAX là constant variable có chắc in dòng trong static block của Constants không?  
**Đáp án:** Không. Đọc constant variable không bắt buộc initialization của class khai báo.

**Câu 6.** `static int first = Later.second; static int second = 10;` (đúng tên kiểu class) có thể dẫn tới first bằng bao nhiêu?  
**Đáp án:** Có thể nhận default 0 trước khi initializer second chạy, nếu code có qualified access hợp lệ và không có constant-value semantics khác.

**Câu 7.** Vì sao `static int a=b; static int b=10;` trong cùng class thường báo illegal forward reference?  
**Đáp án:** Java giới hạn một số cách đọc simple-name field khai báo sau trong static initializer contexts để giảm lỗi đọc quá sớm.

**Câu 8.** Nếu class Alpha initialized và trong initializer đọc Beta, trong khi Beta đọc lại Alpha, điều gì đáng lo?  
**Đáp án:** Vòng phụ thuộc có thể quan sát default values của field chưa hoàn tất, dẫn tới state bất ngờ hoặc deadlock ở thiết kế phức tạp.

**Câu 9.** Khi lần đầu static initializer ném `IllegalStateException`, caller thường thấy lỗi gì?  
**Đáp án:** `ExceptionInInitializerError` theo quy tắc wrapping phù hợp; những lần active use sau có thể `NoClassDefFoundError` trên cùng erroneous class.

**Câu 10.** Có thể đặt `throws IOException` sau `static { ... }` không?  
**Đáp án:** Không. Static block không có chữ ký method/throws clause. Checked exception phải được xử lý theo quy tắc Java.

**Câu 11.** Tạo `new Child()` khiến static initializers của Base và Child có thứ tự gì khi cả hai chưa initialized?  
**Đáp án:** Base trước Child theo quy tắc class initialization; sau đó thực hiện constructor chain cho object.

**Câu 12.** `Child.BASE_FIELD` có chắc initialized Child nếu BASE_FIELD khai báo trong Base?  
**Đáp án:** Không. Active use của field phụ thuộc class khai báo field.

**Câu 13.** `Class<?> c = Target.class;` có tự chạy static block của Target không?  
**Đáp án:** Không bắt buộc; class literal thông thường không kích hoạt class initialization.

**Câu 14.** Vì sao `Map.copyOf` hữu ích khi chuẩn bị static configuration?  
**Đáp án:** Nó cung cấp map không sửa được theo API, tránh cho code khác mutate cấu trúc map sau khi initialized, miễn không lộ mutable values cần bảo vệ riêng.

**Câu 15.** `static final ArrayList<T> cache` có bất biến sâu không?  
**Đáp án:** Không. Reference field không gán lại được, nhưng ArrayList object vẫn có thể bị sửa thông qua reference.

**Câu 16.** Initialization-on-demand holder khởi tạo resource vào thời điểm nào?  
**Đáp án:** Khi nested holder class được initialized qua active use thích hợp, thường là lần đầu gọi accessor làm đọc non-constant static field của holder.

**Câu 17.** Holder initialization thread-safe có nghĩa là `ArrayList` trả từ Holder tự thread-safe không?  
**Đáp án:** Không. Việc tạo/công bố lúc class initialized khác với concurrency semantics của các mutations về sau.

**Câu 18.** Hai JVM processes riêng có chia sẻ cùng static field instance không?  
**Đáp án:** Không. Static fields là state trong runtime class của từng JVM, không là persistence xuyên tiến trình.

**Câu 19.** Hai defining class loaders khác nhau load class có cùng tên có thể có static state khác nhau không?  
**Đáp án:** Có. Runtime class identity xét defining loader cùng binary name, nên initialization states có thể khác.

**Câu 20.** Nếu cấu hình cần reload mỗi giờ, static final immutable map chỉ initialized một lần có tự reload không?  
**Đáp án:** Không. Cần thiết kế lifecycle/config service riêng có cập nhật rõ ràng, không trông chờ static block tự chạy lại.

## Tài liệu tham khảo

- Java Language Specification, [`12.4 — Initialization of Classes and Interfaces](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.4): thời điểm và trình tự initialization.
- Java Language Specification, [`12.4.1 — When Initialization Occurs](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.4.1): các trigger để initialized class/interface.
- Java Language Specification, [`12.4.2 — Detailed Initialization Procedure](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.4.2): quy trình, trạng thái và phối hợp nhiều luồng.
- Java Language Specification, [`8.7 — Static Initializers](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.7): static blocks, giới hạn ngữ cảnh.
- Java Language Specification, [`8.3.2 — Field Initialization](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.3.2): initializers và forward-reference restrictions.
- Java Language Specification, [`4.12.4 — final Variables](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.12.4): final/constant variables.
- Java Platform API, [`Class.forName](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html#forName(java.lang.String)): reflective loading/initialization.

## Ghi nhớ

**Khối `static { ... }` và static field initializers dùng để thiết lập dữ liệu cấp lớp khi JVM initialized class.** Chúng được thực thi theo **thứ tự xuất hiện trong class body**, không chạy lại cho mỗi object. Static initialization khác hẳn instance initialization và constructor.

Hãy đặc biệt cẩn thận với **constant variables không kích hoạt khởi tạo**, **illegal forward references và default values trước khi field initializer chạy**, **vòng phụ thuộc giữa classes**, **lỗi initialization có thể khiến class không dùng lại được**, và **mutable static state không tự an toàn đa luồng**. Dùng khối static cho dữ liệu cấp lớp đơn giản, nhanh, kiểm soát được; ưu tiên immutable collections hoặc holder khi cần lazy initialization. Với I/O phức tạp, resource lifecycle hoặc state thuộc từng người dùng, một service/factory có trách nhiệm rõ thường phù hợp hơn.
