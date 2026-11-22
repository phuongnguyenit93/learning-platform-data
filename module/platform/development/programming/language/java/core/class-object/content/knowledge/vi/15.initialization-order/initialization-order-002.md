# Những thao tác kích hoạt khởi tạo lớp trong Java

## 1. Bài toán: khi nào khối `static` thực sự chạy?

Trong Java, một lớp có thể được **biết đến, nạp hoặc liên kết** trước khi JVM **khởi tạo** (*initialize*) lớp đó. Vì vậy, chỉ vì source code nhắc tới tên lớp **không có nghĩa** các static field initializers và static initialization blocks của lớp đã chạy.

Quan sát lớp:

```java
class Example {
    static int number = initialize();

    static int initialize() {
        System.out.println("Example initialized");
        return 42;
    }

    static void hello() {
        System.out.println("hello");
    }
}
```

Những thao tác khác nhau với `Example` có thể mang ý nghĩa khác nhau:

- `Example.class`: lấy một `Class` object, **không tự kích hoạt khởi tạo `Example`**.
- `new Example[3]`: tạo **mảng tham chiếu**, **không tự khởi tạo `Example`**.
- `Example.hello()`: gọi static method được khai báo ở `Example`, **kích hoạt khởi tạo `Example` trước khi vào `hello`** nếu lớp chưa được khởi tạo.
- `new Example()`: tạo instance, **kích hoạt khởi tạo lớp trước khi thực thi quá trình tạo instance**.
- `Example.number`: đọc non-constant static field được khai báo trong `Example`, **kích hoạt khởi tạo lớp** trước khi đọc.
- `Class.forName("Example")`: theo overload một đối số thông thường, **yêu cầu khởi tạo lớp** khi tìm thành công.

**Quy tắc nền tảng:** class initialization thường xảy ra ở **lần sử dụng chủ động đầu tiên** theo các điều kiện xác định của Java, không phải khi JVM gặp bất cứ chữ nào giống tên lớp.

Bài này dành cho **Java core, Java 17+**. Các ví dụ tập trung vào những lớp chạy trên classpath thông thường; khi có class loader riêng, module, interface hoặc reflection, cần xét thêm ngữ cảnh được ghi rõ.

## 2. Nạp, liên kết và khởi tạo không phải một giai đoạn

Theo mô hình Java Virtual Machine, quá trình chuẩn bị dùng một lớp thường được diễn giải thành:

1. **Loading (nạp):** JVM tìm biểu diễn của lớp và tạo thông tin runtime tương ứng.
2. **Linking (liên kết):** bao gồm **verification**, **preparation** và **resolution**. Resolution có thể diễn ra theo chiến lược thích hợp của JVM, không nhất thiết tất cả xong ngay một lúc.
3. **Initialization (khởi tạo):** chạy **class initialization method** (`<clinit>` ở mức JVM khi có nội dung cần khởi tạo), nhằm thực hiện static field initializers và static initializer blocks theo quy tắc.

Sơ đồ tư duy:

```text
Class được yêu cầu / được tham chiếu
            |
            v
         Loading
            |
            v
         Linking
   (verify / prepare /
       resolve ...)
            |
            v
 Có hoạt động yêu cầu
   class initialization?
      /             \
     / không         \ có
    v                 v
Chưa chạy         Initialization
static initializers    |
                       v
                   Tiếp tục thao tác
```

**Preparation** có thể cấp giá trị mặc định ở mức JVM cho static fields trước khi các initializer trong source chạy. Ví dụ static field `int count = 10` ban đầu có trạng thái chuẩn bị tương ứng với default value `0`; tới class initialization, initializer mới đặt nó thành `10`.

**Không nhầm:** “được nạp” không đồng nghĩa “đã chạy static block”. JVM có quyền nạp, verify hoặc resolve lớp theo thời điểm thích hợp miễn tôn trọng ngữ nghĩa quan sát được do specification yêu cầu.

### `<clinit>` khác constructor `<init>`

- `<clinit>` là tên đặc biệt ở mức JVM cho **class/interface initialization**, không phải method Java source mà bạn tự khai báo hoặc tự gọi.
- Constructor của object tương ứng với quy trình instance initialization và các method đặc biệt `<init>`.
- `new SomeClass()` có thể kéo theo **khởi tạo lớp** trước, rồi mới tới **khởi tạo instance/constructor**.
- `SomeClass.staticMethod()` có thể kéo theo **khởi tạo lớp**, nhưng **không tạo instance** và không gọi constructor của SomeClass.

## 3. Bảng tra nhanh: những thao tác quan trọng

| Thao tác | Có kích hoạt khởi tạo lớp đích khi chưa initialize? | Điều kiện / lưu ý |
| --- | --- | --- |
| `new Target()` | **Có** | Khởi tạo lớp tương ứng trước quá trình tạo instance |
| `Target.staticMethod()` | **Có** | Khi method static đó được khai báo ở Target; xem vấn đề method inherited |
| Đọc `Target.staticField` | **Có**, nếu field được khai báo ở Target và **không là constant variable** | Hằng compile-time là ngoại lệ quan trọng |
| Gán `Target.staticField = value` | **Có** | Việc dùng static field phải phù hợp quyền truy cập/không final |
| `Target.CONSTANT` | **Thường không**, nếu `CONSTANT` là **constant variable** | `static final` primitive/String với constant expression theo quy tắc JLS |
| `Target.class` | **Không** | Lấy class literal không tự chạy static initializers |
| `new Target[5]` | **Không** | Tạo mảng không tạo các phần tử `Target` |
| `Target[] refs = new Target[5]` | **Không** | Các slots của mảng tham chiếu mặc định null |
| `Class.forName("Target")` | **Có**, theo overload một đối số thông thường | Tìm và khởi tạo class khi thành công |
| `Class.forName(name, false, loader)` | **Không yêu cầu initialization** | `false` có ý nghĩa trì hoãn initialization |
| `ClassLoader.loadClass(name)` | **Không tự yêu cầu initialization** | Việc dùng class sau đó có thể kích hoạt |
| Import tên class/static member | **Không** | Import là khai báo nguồn dùng khi biên dịch |
| Khai báo biến `Target value;` | **Không** | Chưa có thao tác active use |
| Cast hoặc `instanceof Target` | **Không tự yêu cầu initialization của Target** | Có thể cần nạp/liên kết |
| Gọi constructor/đọc field từ reflection | **Có thể có** | Các reflective operations cụ thể có quy tắc riêng |
| `Class.getDeclaredMethods()` | **Không phải lệnh mặc định “initialize class”** | Tra metadata khác với gọi method |
| Chạy ứng dụng bằng entry class | **Có** | JVM khởi tạo entry class trước khi thực thi main theo quy tắc |

Bảng nói về **khởi tạo lớp đích**, không phủ nhận việc thao tác có thể kích hoạt **một lớp khác** do đánh giá tham số, tạo object phụ, static initializer phụ thuộc hoặc JVM thực hiện công việc hợp lệ khác.

## 4. Kích hoạt bằng `new`: tạo object cần class được khởi tạo

Tạo file **`NewTriggerDemo.java`**:

```java
class Widget {
    static {
        System.out.println("Widget: static init");
    }

    {
        System.out.println("Widget: instance block");
    }

    Widget() {
        System.out.println("Widget: constructor");
    }
}

public class NewTriggerDemo {
    public static void main(String[] args) {
        System.out.println("main begins");

        Widget first = new Widget();
        Widget second = new Widget();

        System.out.println(first != second);
    }
}
```

Chạy:

```bash
javac NewTriggerDemo.java
java NewTriggerDemo
```

Kết quả:

```text
main begins
Widget: static init
Widget: instance block
Widget: constructor
Widget: instance block
Widget: constructor
true
```

Giải thích theo thứ tự:

1. `main` in `main begins`.
2. Lần đầu thực thi `new Widget()`, JVM bảo đảm `Widget` được khởi tạo trước khi tiếp tục tạo instance. Static block in **một lần**.
3. Sau đó instance initialization block chạy, rồi thân constructor cho object thứ nhất.
4. Lần `new Widget()` thứ hai **không chạy lại static block** của cùng runtime class đã initialize thành công, nhưng vẫn chạy instance block và constructor cho **object thứ hai**.
5. Hai reference `first` và `second` trỏ hai object khác nhau, nên `first != second` là `true`.

**Quan trọng:** static initialization là công việc gắn với **runtime class**, không phải công việc được làm lại mỗi lần một object được tạo.

## 5. Gọi static method có thể kích hoạt khởi tạo lớp

Tạo file **`StaticMethodTriggerDemo.java`**:

```java
class Service {
    static {
        System.out.println("Service: static init");
    }

    static void work() {
        System.out.println("Service: work");
    }

    Service() {
        System.out.println("Service: constructor");
    }
}

public class StaticMethodTriggerDemo {
    public static void main(String[] args) {
        System.out.println("before first call");

        Service.work();
        Service.work();

        System.out.println("after calls");
    }
}
```

```bash
javac StaticMethodTriggerDemo.java
java StaticMethodTriggerDemo
```

```text
before first call
Service: static init
Service: work
Service: work
after calls
```

- Static block chạy trước thân `Service.work()` lần đầu.
- Method `work` **vẫn thực thi ở mỗi lần gọi**; chỉ class initialization không lặp lại sau khi thành công.
- Trong chương trình không có `new Service()`; vì vậy constructor **không chạy**.

**Đừng kết luận sai rằng** “static method chỉ chạy một lần” hoặc “static method tự tạo singleton”. Nó chỉ là một trong những hoạt động có thể **kích hoạt quá trình initialize class** khi cần.

### Static method được thừa hưởng: xét nơi khai báo thực sự

Nếu:

```java
class Base {
    static void ping() {
        System.out.println("Base ping");
    }
}

class Child extends Base {
}
```

`Child.ping()` có thể biên dịch, nhưng `ping` là method được **khai báo ở Base**. Theo quy tắc class initialization, lời gọi static member đó nhắm tới **class khai báo member**; không được suy từ văn bản `Child.ping()` rằng `Child` nhất thiết cũng được initialize.

Vì vậy nên viết `Base.ping()` để thể hiện rõ nguồn khai báo khi code không cố ý dựa vào inheritance của static member.

## 6. Đọc hoặc ghi static field không phải hằng compile-time

Tạo file **`StaticFieldTriggerDemo.java`**:

```java
class Settings {
    static int level = initialize();

    static int initialize() {
        System.out.println("Settings: initializing");
        return 3;
    }
}

public class StaticFieldTriggerDemo {
    public static void main(String[] args) {
        System.out.println("before read");
        System.out.println("level=" + Settings.level);

        Settings.level = 9;
        System.out.println("updated=" + Settings.level);
    }
}
```

```bash
javac StaticFieldTriggerDemo.java
java StaticFieldTriggerDemo
```

```text
before read
Settings: initializing
level=3
updated=9
```

- `Settings.level` là static field **không phải constant variable**, nên đọc nó kích hoạt `Settings` initialization.
- Trong initialization, `initialize()` được gọi để gán `level=3`.
- Lần đọc sau khi gán `Settings.level=9` chỉ thấy giá trị mới; initializer không chạy lại.

### Việc ghi static field cũng có thể kích hoạt

Nếu thao tác đầu tiên là:

```java
Settings.level = 9;
```

khi `Settings` chưa initialize, JVM phải bảo đảm class được initialize trước khi thực hiện thao tác ghi theo quy tắc. Vì vậy initializer có thể đặt level thành 3 trước, rồi **lệnh gán của caller** thay thành 9.

**Chú ý:** đây là static field được khai báo tại `Settings`. Nếu bạn truy cập một inherited static field qua tên subclass, quy tắc lớp **khai báo field** mới là chìa khóa, không chỉ tên viết trước dấu chấm.

## 7. Ngoại lệ trọng yếu: `static final` hằng compile-time có thể không initialize class

Một **constant variable** trong Java phải thỏa điều kiện về kiểu và initializer:

- Biến có kiểu **primitive** hoặc `String`.
- Được khai báo `final`.
- Được khởi tạo bằng một **constant expression** theo quy tắc Java Language Specification.

Với trường hợp static field:

```java
class Constants {
    static final int LIMIT = 100;
    static final String TITLE = "Java";

    static {
        System.out.println("Constants initialized");
    }
}
```

Các biểu thức `Constants.LIMIT` và `Constants.TITLE` khi được sử dụng như hằng theo ngữ nghĩa nguồn Java **không phải hoạt động yêu cầu khởi tạo `Constants`**. Compiler có thể nhúng giá trị hằng vào code client.

Tạo tệp **`ConstantVariableDemo.java`**:

```java
class Constants {
    static final int LIMIT = 100;
    static final String TITLE = "Java Core";

    static {
        System.out.println("Constants: initialized");
    }

    static void ping() {
        System.out.println("Constants: ping");
    }
}

public class ConstantVariableDemo {
    public static void main(String[] args) {
        System.out.println(Constants.LIMIT);
        System.out.println(Constants.TITLE);
        System.out.println("before ping");

        Constants.ping();
    }
}
```

```bash
javac ConstantVariableDemo.java
java ConstantVariableDemo
```

```text
100
Java Core
before ping
Constants: initialized
Constants: ping
```

Hai lần đọc hằng **không làm dòng `Constants: initialized` xuất hiện**. Chỉ khi gọi static method `ping`, class mới cần initialize và static block in ra.

**Đừng nhầm “có `static final`” với “là compile-time constant”.** Chỉ những declaration thỏa toàn bộ điều kiện `constant variable` mới có hành vi ngoại lệ này.

## 8. `static final` nhưng initializer runtime vẫn kích hoạt class

So sánh:

```java
static final int FIXED = 42;
static final int COMPUTED = Integer.parseInt("42");

static final String LITERAL = "hello";
static final String RUNTIME = new String("hello");
```

Đây là **mảnh khai báo field bên trong class**:

- `FIXED` là `int` final với constant expression → **constant variable**.
- `COMPUTED` dùng method call → **không phải constant variable** dù kết quả là 42.
- `LITERAL` là String final gán literal → **constant variable**.
- `RUNTIME` dùng `new String(...)` → **không phải constant variable** dù giá trị text giống hệt literal.
- Static final reference đến `List`, mảng, `Integer` hoặc object khác **không thể là constant variable** theo định nghĩa kiểu primitive/String, ngay cả khi thực thể được thiết kế immutable.

### Ví dụ chạy: hai static final field nhưng khác trigger

Tệp **`NonConstantStaticFinalDemo.java`**:

```java
class Data {
    static final int COMPILE_TIME = 7;
    static final int RUNTIME = makeRuntime();

    static int makeRuntime() {
        System.out.println("Data: initializing runtime value");
        return 11;
    }
}

public class NonConstantStaticFinalDemo {
    public static void main(String[] args) {
        System.out.println("constant=" + Data.COMPILE_TIME);
        System.out.println("before runtime read");
        System.out.println("runtime=" + Data.RUNTIME);
    }
}
```

```bash
javac NonConstantStaticFinalDemo.java
java NonConstantStaticFinalDemo
```

```text
constant=7
before runtime read
Data: initializing runtime value
runtime=11
```

Đọc `Data.COMPILE_TIME` chưa initialize `Data`. Đọc `Data.RUNTIME` yêu cầu khởi tạo class, khiến static field initializer gọi `makeRuntime()`.

### `String` nối hằng vẫn có thể là compile-time constant

```java
static final String MESSAGE = "Java" + " Core";
```

Vì biểu thức ghép trên là một **constant expression**, `MESSAGE` có thể là constant variable. Không thể suy rằng hễ có toán tử `+` thì kết quả phải được tính runtime; hãy xét quy tắc constant expression của Java.

Ngược lại:

```java
static final String MESSAGE = System.getProperty("app.title");
```

là initializer runtime, không phải constant variable.

## 9. Class literal `SomeType.class` không tự chạy static initializer

Tệp **`ClassLiteralDemo.java`**:

```java
class Passive {
    static {
        System.out.println("Passive: initialized");
    }

    static void activate() {
        System.out.println("Passive: activate");
    }
}

public class ClassLiteralDemo {
    public static void main(String[] args) {
        System.out.println("before literal");

        Class<Passive> type = Passive.class;
        System.out.println("class=" + type.getSimpleName());

        System.out.println("before active use");
        Passive.activate();
    }
}
```

```bash
javac ClassLiteralDemo.java
java ClassLiteralDemo
```

```text
before literal
class=Passive
before active use
Passive: initialized
Passive: activate
```

- `Passive.class` lấy `Class<Passive>`, nhưng **không tự initialize `Passive`**.
- `type.getSimpleName()` lấy thông tin tên type; trong trường hợp này không cần chạy static initializer của Passive.
- `Passive.activate()` là lời gọi static method khai báo ở Passive, nên kích hoạt initializer trước lời gọi method.

**Phân biệt:** `SomeType.class` không có nghĩa là **không tải/lưu metadata**. Nó chỉ **không phải yêu cầu initialize class**. JVM vẫn có thể thực hiện những bước class loading/linking cần thiết.

## 10. Tạo mảng kiểu lớp không tạo từng object

Một hành vi dễ nhầm:

```java
Target[] items = new Target[3];
```

Lệnh này tạo **array object có ba slot tham chiếu**, không tự gọi `new Target()` cho từng phần tử. Ban đầu các slots đều chứa `null`.

Đồng thời, chỉ tạo array có component type `Target` không tự yêu cầu `Target` class initialization.

Tệp **`ArrayDoesNotInitializeDemo.java`**:

```java
class Component {
    static {
        System.out.println("Component: class initialized");
    }

    Component() {
        System.out.println("Component: constructor");
    }
}

public class ArrayDoesNotInitializeDemo {
    public static void main(String[] args) {
        System.out.println("creating array");
        Component[] components = new Component[2];

        System.out.println("length=" + components.length);
        System.out.println("first null=" + (components[0] == null));

        components[0] = new Component();
        System.out.println("second null=" + (components[1] == null));
    }
}
```

```bash
javac ArrayDoesNotInitializeDemo.java
java ArrayDoesNotInitializeDemo
```

```text
creating array
length=2
first null=true
Component: class initialized
Component: constructor
second null=true
```

Giải thích:

1. `new Component[2]` chỉ tạo array, không initialize class Component theo trigger này.
2. `components[0] == null` là true vì chưa tạo object phần tử.
3. `components[0] = new Component()` tạo instance, nên kích hoạt Component initialization nếu chưa xảy ra, rồi constructor chạy.
4. `components[1]` tiếp tục null.

**Lưu ý nâng cao:** array có runtime class riêng do JVM quản lý, nhưng đó **không phải** static initialization của class dùng làm kiểu phần tử.

## 11. Class loading bằng reflection: `Class.forName`

Reflection có thể được dùng để tìm lớp hoặc gọi member runtime. Một số API **yêu cầu initialize class**, một số không.

### `Class.forName(String)`

Với class thuộc classpath và khả năng tìm thấy theo loader phù hợp, overload:

```java
Class<?> type = Class.forName("LoadedByName");
```

thông thường yêu cầu **nạp, liên kết và khởi tạo** lớp được đặt tên. Có thể khiến static initializer chạy dù chưa gọi method static hay tạo instance.

### `Class.forName(String, boolean, ClassLoader)`

Overload:

```java
Class<?> type = Class.forName(
        "LoadedByName", false, someLoader);
```

cho phép chỉ định `initialize=false`, tức là **không yêu cầu initialize class vào thời điểm đó**. Thời điểm sau có active use thì class vẫn có thể được initialize.

### Ví dụ runnable chứng minh khác biệt

Tệp **`ReflectionInitializationDemo.java`**:

```java
class ReflectionTarget {
    static {
        System.out.println("ReflectionTarget: initialized");
    }

    static void run() {
        System.out.println("ReflectionTarget: run");
    }
}

public class ReflectionInitializationDemo {
    public static void main(String[] args) throws Exception {
        System.out.println("before false");

        ClassLoader loader =
                ReflectionInitializationDemo.class.getClassLoader();

        Class<?> type =
                Class.forName("ReflectionTarget", false, loader);

        System.out.println("loaded=" + type.getSimpleName());
        System.out.println("before default forName");

        Class.forName("ReflectionTarget");

        System.out.println("after default forName");
        ReflectionTarget.run();
    }
}
```

```bash
javac ReflectionInitializationDemo.java
java ReflectionInitializationDemo
```

```text
before false
loaded=ReflectionTarget
before default forName
ReflectionTarget: initialized
after default forName
ReflectionTarget: run
```

Các file nằm trong **default package** và class loader có thể tìm `ReflectionTarget` trong classpath khi chạy như trên.

- `Class.forName(..., false, loader)` chưa yêu cầu initialize.
- `Class.forName("ReflectionTarget")` kích hoạt initialize tại thời điểm được gọi nếu chưa initialize trước đó.
- `ReflectionTarget.run()` không khiến static block chạy lần nữa.

**Không nhầm “đã có Class object” với “đã khởi tạo lớp”**. Class metadata và initialization state là hai khái niệm khác nhau.

## 12. `ClassLoader.loadClass` không đồng nghĩa initialize

`ClassLoader.loadClass(name)` về bản chất thực hiện yêu cầu **nạp lớp**; nó **không tự yêu cầu thực thi các static initializers** của lớp đích như `Class.forName(name)` một đối số thường làm.

Ví dụ minh họa:

```java
ClassLoader loader = MyType.class.getClassLoader();
Class<?> type = loader.loadClass("MyType");
```

Đây là **mảnh code** cần đặt trong môi trường có lớp `MyType` và xử lý checked exception. Việc lấy `MyType.class` để tìm loader cũng không tự initialize MyType.

Tuy nhiên:

- Class loader tùy chỉnh có thể thực hiện các hành động riêng theo implementation.
- JVM có thể nạp một class trước hoặc giải quyết dependencies vào thời điểm khác.
- Các **active uses sau đó** của class vẫn kích hoạt initialization theo quy tắc.

**Kết luận chính xác:** API nạp lớp và API yêu cầu khởi tạo lớp là hai chuyện khác nhau; đừng đồng nhất `loadClass` với một lần gọi constructor hay static initializer.

## 13. Reflection lấy metadata khác với gọi method hoặc đọc field

Giả sử có:

```java
class Probe {
    static {
        System.out.println("Probe: initialized");
    }

    public static void execute() {
        System.out.println("Probe: execute");
    }
}
```

Những thao tác chỉ lấy thông tin như `Probe.class`, `getName()` hoặc `getDeclaredMethods()` **không mặc định mang cùng ý nghĩa active execution** với `Probe.execute()`.

Trong khi đó, reflection **thực sự gọi static method** thông qua `Method.invoke` hoặc truy cập static field theo các API reflection có thể yêu cầu initialization theo quy tắc của API.

### Ví dụ Java 17+ dùng reflection gọi static method

Tệp **`ReflectiveInvocationDemo.java`**:

```java
import java.lang.reflect.Method;

class Probe {
    static {
        System.out.println("Probe: initialized");
    }

    public static void execute() {
        System.out.println("Probe: execute");
    }
}

public class ReflectiveInvocationDemo {
    public static void main(String[] args) throws Exception {
        Class<Probe> type = Probe.class;

        System.out.println("before method lookup");
        Method method = type.getDeclaredMethod("execute");

        System.out.println("before invoke");
        method.invoke(null);
    }
}
```

```bash
javac ReflectiveInvocationDemo.java
java ReflectiveInvocationDemo
```

```text
before method lookup
before invoke
Probe: initialized
Probe: execute
```

- `Probe.class` và `getDeclaredMethod` chỉ lấy thông tin kiểu/method.
- `method.invoke(null)` thực thi static method; đối số receiver `null` hợp lệ khi gọi static method qua reflection.
- Lúc thực thi, Probe được initialize trước method body, nên in static message trước `Probe: execute`.

Đừng suy rằng **mọi reflective API** đều giống nhau. Ví dụ `Constructor.newInstance`, `Field.get`/`set` cho static field và cơ chế method handles có những quy tắc riêng. Khi dùng reflection cho framework, cần đọc contract cụ thể của method liên quan.

## 14. Khi subclass initialize, superclass thường initialize trước

Một subclass không thể hoàn tất class initialization bình thường mà chưa xử lý những superclass initialization được yêu cầu trước nó.

Ví dụ:

Tệp **`SuperclassInitializationDemo.java`**:

```java
class Base {
    static {
        System.out.println("Base: static init");
    }

    Base() {
        System.out.println("Base: constructor");
    }
}

class Child extends Base {
    static {
        System.out.println("Child: static init");
    }

    Child() {
        System.out.println("Child: constructor");
    }
}

public class SuperclassInitializationDemo {
    public static void main(String[] args) {
        System.out.println("before new Child");
        new Child();
    }
}
```

```bash
javac SuperclassInitializationDemo.java
java SuperclassInitializationDemo
```

```text
before new Child
Base: static init
Child: static init
Base: constructor
Child: constructor
```

Giải thích:

1. `new Child()` yêu cầu class Child được initialize.
2. Trước khi initialize Child hoàn tất, JVM bảo đảm **Base** được initialize theo quan hệ superclass.
3. Static initializer của Base in trước static initializer của Child.
4. Sau phase class initialization, quá trình tạo object gọi phần constructor Base trước phần constructor Child.

Vì vậy **class initialization order** và **instance constructor order** đều có quan hệ với kế thừa, nhưng là **hai chuỗi công việc khác nhau**.

### Tránh kết luận ngược

Đọc static field của `Base` không tự bắt buộc khởi tạo `Child` chỉ vì Child extends Base. Một lớp con có thể chưa initialize dù lớp cha đã initialize.

## 15. Truy cập static field được khai báo ở superclass qua tên subclass

Đây là tình huống đánh lừa trực giác:

```java
class Parent {
    static int value = init();

    static int init() {
        System.out.println("Parent: initialized");
        return 7;
    }
}

class Child extends Parent {
    static {
        System.out.println("Child: initialized");
    }
}
```

Nếu viết `Child.value`, field `value` **được khai báo tại Parent**, không phải Child. Việc truy cập field có thể kích hoạt **Parent initialization**, mà **không nhất thiết initialize Child**.

### Chương trình chạy

Tệp **`DeclaringClassTriggerDemo.java`**:

```java
class Parent {
    static int value = init();

    static int init() {
        System.out.println("Parent: initialized");
        return 7;
    }
}

class Child extends Parent {
    static {
        System.out.println("Child: initialized");
    }

    static void ownMethod() {
        System.out.println("Child: ownMethod");
    }
}

public class DeclaringClassTriggerDemo {
    public static void main(String[] args) {
        System.out.println("value=" + Child.value);
        System.out.println("before ownMethod");

        Child.ownMethod();
    }
}
```

```bash
javac DeclaringClassTriggerDemo.java
java DeclaringClassTriggerDemo
```

```text
Parent: initialized
value=7
before ownMethod
Child: initialized
Child: ownMethod
```

Bài học: **class thực sự khai báo static field/method** là yếu tố quan trọng để xác định trigger. Nên dùng `Parent.value` khi muốn người đọc thấy rõ nguồn khai báo, thay vì dùng tên Child chỉ vì Java cho phép.

## 16. Interface initialization khác class inheritance ở điểm nào?

Một interface có thể khai báo static fields được khởi tạo bằng biểu thức runtime và static methods có body. Nhưng interface initialization có những khác biệt so với lớp.

**Điểm chính:**

- Dùng **static field không phải constant variable được khai báo trong interface** có thể kích hoạt chính interface đó.
- Gọi **static method được khai báo trong interface** kích hoạt interface initialization theo quy tắc.
- Khi initialize một interface, **không tự động phải initialize toàn bộ superinterfaces** chỉ vì quan hệ `extends`.
- Khi initialize một class, một số **superinterfaces khai báo default methods** cũng nằm trong quá trình initialization theo quy tắc Java. Đây là ngoại lệ tinh tế của câu “khởi tạo class không kéo theo khởi tạo interface”.

### Ví dụ interface static field runtime

Tệp **`InterfaceInitializationDemo.java`**:

```java
interface Flags {
    int RUNTIME = announce();

    static int announce() {
        System.out.println("Flags: initialized");
        return 5;
    }

    static void ping() {
        System.out.println("Flags: ping");
    }
}

public class InterfaceInitializationDemo {
    public static void main(String[] args) {
        System.out.println("before read");
        System.out.println(Flags.RUNTIME);

        Flags.ping();
    }
}
```

```bash
javac InterfaceInitializationDemo.java
java InterfaceInitializationDemo
```

```text
before read
Flags: initialized
5
Flags: ping
```

Mặc dù interface fields mặc định là `public static final`, field `RUNTIME` **không phải constant variable** vì initializer gọi method `announce()`. Vì thế đọc `Flags.RUNTIME` kích hoạt initialization.

### Interface compile-time constant vẫn là ngoại lệ

```java
interface Configuration {
    int MAX = 10;
}
```

`Configuration.MAX` là compile-time constant theo các quy tắc liên quan, nên chỉ dùng hằng này **không phải hoạt động yêu cầu interface initialization**.

## 17. Default method có thể khiến interface được khởi tạo cùng class

JLS có quy tắc riêng: khi initialize một class, JVM còn initialize những superinterfaces **khai báo default methods** theo trình tự yêu cầu. Đây là một trường hợp thường bị bỏ sót khi nói về trigger.

Tệp **`DefaultInterfaceInitDemo.java`**:

```java
interface Feature {
    int MARKER = announce();

    static int announce() {
        System.out.println("Feature: initialized");
        return 1;
    }

    default void perform() {
    }
}

class FeatureImpl implements Feature {
    static {
        System.out.println("FeatureImpl: initialized");
    }
}

public class DefaultInterfaceInitDemo {
    public static void main(String[] args) {
        new FeatureImpl();
    }
}
```

```bash
javac DefaultInterfaceInitDemo.java
java DefaultInterfaceInitDemo
```

```text
Feature: initialized
FeatureImpl: initialized
```

- `Feature` khai báo một `default void perform()`, nên được xem xét theo quy tắc superinterface có default method khi khởi tạo `FeatureImpl`.
- `Feature.MARKER` không phải compile-time constant vì gọi `announce()`; initialization của Feature thực thi initializer và in message.
- Sau đó `FeatureImpl` được initialize và in message của class.

**Lưu ý:** không nên khái quát rằng bất cứ interface nào được implements cũng luôn initialize trước class; cần xét default-method rule và những active uses riêng của interface.

## 18. Static nested class có vòng khởi tạo riêng với enclosing class

Khi có:

```java
class Outer {
    static class Nested {
        static void work() {
        }
    }
}
```

`Outer.Nested` là **một class riêng về mặt runtime**, và static initialization của nó không tự đồng nhất với initialization của `Outer`. Vì Nested là `static nested class`, nó không cần enclosing `Outer` instance.

Tệp **`NestedClassInitializationDemo.java`**:

```java
class Outer {
    static {
        System.out.println("Outer: initialized");
    }

    static class Nested {
        static {
            System.out.println("Nested: initialized");
        }

        static void run() {
            System.out.println("Nested: run");
        }
    }

    static void run() {
        System.out.println("Outer: run");
    }
}

public class NestedClassInitializationDemo {
    public static void main(String[] args) {
        Outer.Nested.run();
        System.out.println("between");
        Outer.run();
    }
}
```

```bash
javac NestedClassInitializationDemo.java
java NestedClassInitializationDemo
```

```text
Nested: initialized
Nested: run
between
Outer: initialized
Outer: run
```

Đầu tiên chỉ `Nested` được initialize do static method được khai báo ở Nested được gọi. Sau đó `Outer.run()` mới cần initialize Outer.

**Sai lầm thường gặp:** thấy tên nguồn `Outer.Nested` rồi tưởng initializer của `Outer` phải chạy trước mọi thao tác tới `Nested`. Java không có quy tắc đó chỉ vì quan hệ lexical nesting.

## 19. Thứ tự static field initializers và static blocks trong cùng class

Khi một class được initialize, các static field initializers và static initialization blocks được thực thi theo **thứ tự xuất hiện trong source**, trong một quy trình tuân theo quy tắc definite assignment/forward references.

Tệp **`StaticOrderDemo.java`**:

```java
class Config {
    static int first = announce("field first", 1);

    static {
        System.out.println("static block A");
    }

    static int second = announce("field second", 2);

    static {
        System.out.println("static block B");
    }

    static int announce(String label, int value) {
        System.out.println(label);
        return value;
    }
}

public class StaticOrderDemo {
    public static void main(String[] args) {
        System.out.println("before read");
        System.out.println("sum=" + (Config.first + Config.second));
    }
}
```

```bash
javac StaticOrderDemo.java
java StaticOrderDemo
```

```text
before read
field first
static block A
field second
static block B
sum=3
```

Diễn giải:

1. `Config.first` được yêu cầu lần đầu → Config phải initialize.
2. Static field initializer đầu gọi `announce("field first",1)`.
3. Static block A chạy.
4. Static field initializer `second` chạy.
5. Static block B chạy.
6. Sau class initialization hoàn tất, phép cộng `Config.first + Config.second` trả 3.

**Đừng nhầm thứ tự khai báo static members với thứ tự gọi methods.** Thân `announce` được định nghĩa ở cuối vẫn có thể được gọi từ initializer trước nó, phù hợp quy tắc phân giải methods.

## 20. Static initialization xảy ra trước instance initialization

Cùng một class có thể chứa:

- Static field initializers.
- Static blocks.
- Instance field initializers.
- Instance initialization blocks.
- Constructors.

**Thứ tự khái quát khi tạo object lần đầu:** initialize class (và các superclass liên quan) → cấp phát/khởi tạo instance theo chuỗi constructor và instance initializers.

Ví dụ đầy đủ:

Tệp **`ClassAndObjectOrderDemo.java`**:

```java
class Machine {
    static {
        System.out.println("Machine.static");
    }

    int code = printAndReturn("Machine.field", 1);

    {
        System.out.println("Machine.instanceBlock");
    }

    Machine() {
        System.out.println("Machine.constructor");
    }

    static int printAndReturn(String label, int value) {
        System.out.println(label);
        return value;
    }
}

public class ClassAndObjectOrderDemo {
    public static void main(String[] args) {
        System.out.println("before new");
        new Machine();
        System.out.println("second new");
        new Machine();
    }
}
```

```bash
javac ClassAndObjectOrderDemo.java
java ClassAndObjectOrderDemo
```

```text
before new
Machine.static
Machine.field
Machine.instanceBlock
Machine.constructor
second new
Machine.field
Machine.instanceBlock
Machine.constructor
```

Static block in một lần, trong khi field initializer instance, instance block và constructor chạy cho mỗi instance.

**Mẹo nhận diện:** `static` gắn với **class initialization**; không có `static` trong field/initialization block gắn với **instance initialization**.

## 21. Chạy lớp chứa `main` cũng cần initialize entry class

Khi dùng Java launcher để chạy một main class theo cơ chế truyền thống, JVM phải initialize class mang entry method trước khi thực thi phần thân `main`.

Tệp **`MainClassInitializationDemo.java`**:

```java
public class MainClassInitializationDemo {
    static {
        System.out.println("main class initialized");
    }

    public static void main(String[] args) {
        System.out.println("main method");
    }
}
```

```bash
javac MainClassInitializationDemo.java
java MainClassInitializationDemo
```

```text
main class initialized
main method
```

Điều này giải thích vì sao các static initializers **trong chính entry class** có thể chạy trước dòng đầu của `main` mà bạn không viết `new EntryClass()`.

**Không kết luận:** nếu một class không phải entry class có static block thì JVM sẽ chạy static block chỉ vì file `.class` tồn tại trong thư mục. Đối với các lớp khác, phải xét active uses và những quan hệ initialization bắt buộc.

## 22. Một lớp thông thường chỉ được initialize một lần thành công trong một runtime identity

“Chỉ một lần” ở đây phải hiểu đúng phạm vi: **mỗi class/interface được định danh runtime bởi tên và defining class loader theo mô hình JVM**. Nếu cùng tên lớp được định nghĩa bởi những class loaders khác nhau, đó có thể là **những runtime classes khác nhau**, với static state/initialization riêng.

Trong trường hợp ứng dụng đơn giản chỉ dùng một loader thông thường, bạn thường quan sát:

```text
Lần active use đầu tiên -> static initialization chạy
Các active uses tiếp theo -> dùng trạng thái class đã initialized
```

**Nhưng không phải:** JVM toàn máy tính chỉ được initialize lớp cùng tên đúng một lần trong mọi tiến trình, JVM sessions hoặc class loaders.

### Multiple threads cùng chạm tới class chưa initialize

JVM phối hợp class initialization theo cơ chế đồng bộ do specification quy định:

- Hai threads đồng thời kích hoạt cùng một class chưa khởi tạo không được tự ý chạy hai lượt static initializers thành công chồng nhau.
- Một thread khác có thể phải chờ quá trình initialization đang được thực hiện.
- Nếu initialization thất bại, các yêu cầu sau có thể nhận lỗi liên quan tới trạng thái erroneous class.

Đừng tự mô phỏng một static initializer “chạy duy nhất” bằng một boolean không đồng bộ rồi cho rằng giống hành vi JVM; hãy dựa trên quy tắc class initialization chuẩn.

## 23. Khi static initializer ném exception: class có thể rơi vào trạng thái lỗi

Một lỗi trong static initializer ảnh hưởng đến **cả quá trình class initialization**, không chỉ lời gọi method hiện tại.

Tệp **`FailedInitializationDemo.java`**:

```java
class Broken {
    static final int VALUE = fail();

    static int fail() {
        System.out.println("Broken: initializing");
        throw new IllegalStateException("boom");
    }

    static void work() {
        System.out.println("unreachable in this demo");
    }
}

public class FailedInitializationDemo {
    public static void main(String[] args) {
        try {
            Broken.work();
        } catch (ExceptionInInitializerError ex) {
            System.out.println("first: initialization failed");
        }

        try {
            Broken.work();
        } catch (NoClassDefFoundError ex) {
            System.out.println("second: class unusable");
        }
    }
}
```

```bash
javac FailedInitializationDemo.java
java FailedInitializationDemo
```

```text
Broken: initializing
first: initialization failed
second: class unusable
```

Giải thích:

1. Gọi `Broken.work()` là active use, yêu cầu initialize Broken trước khi vào method body.
2. Khi khởi tạo `VALUE`, `fail()` in thông báo rồi ném `IllegalStateException`.
3. Theo quy tắc xử lý lỗi initialization, một exception không phải `Error` thoát khỏi initializer được bọc thành `ExceptionInInitializerError` ở tình huống này.
4. `Broken` không hoàn tất initialization và bị đánh dấu trạng thái erroneous trong ngữ cảnh runtime tương ứng.
5. Một nỗ lực active use sau đó không “chạy thử initializer lại” như một retry bình thường; ví dụ bắt `NoClassDefFoundError`.

**Đừng dùng loại exception ở lượt sau để chứng minh class file bị xóa**. `NoClassDefFoundError` ở tình huống này có thể xuất hiện vì lớp không thể sử dụng sau initialization failure, khác lỗi “file .class không tìm thấy” thường gặp.

### Lưu ý về `Error`

Nếu static initializer ném một `Error`, cách truyền lỗi có quy tắc riêng: không phải mọi lỗi đều bị bọc như runtime exception ở ví dụ trên. Học quy tắc tổng quát thay vì khẳng định bất cứ `Throwable` nào cũng luôn thành `ExceptionInInitializerError`.

## 24. Tránh side effects khó kiểm soát trong static initializers

Static initializer có thể chạy **muộn hơn người mới học nghĩ**: chẳng hạn chỉ khi một class được active use qua lời gọi static method hoặc non-constant static field. Nếu initializer thực hiện nhiều việc phức tạp, việc class được dùng lần đầu có thể gây bất ngờ:

- Mở file hoặc kết nối mạng.
- Đọc biến môi trường/cấu hình.
- Đăng ký callback hoặc bắt đầu thread.
- Ghi dữ liệu xuống database.
- Ném exception do môi trường chưa chuẩn bị.
- Chờ lock và vô tình tương tác với những class khác đang initialize.

Một thiết kế thận trọng:

1. Giữ static initialization **đơn giản, có thời gian chạy dự đoán được**.
2. Không mặc định static initializer là điểm khởi động nghiệp vụ toàn ứng dụng.
3. Đưa I/O hoặc initialization có thể thất bại vào **factory/service/lifecycle methods** có contract rõ khi hợp lý.
4. Nếu dùng lazy holder để trì hoãn khởi tạo resource, phải hiểu hành vi khi initialization thất bại và cách retry.
5. Không dựa vào side effect của compile-time constant access để “kích hoạt class”.

**Quan trọng:** class initialization có cơ chế đồng bộ của JVM, nhưng không tự đảm bảo những side effects ngoài JVM là atomic, idempotent hoặc rollback được.

## 25. Lazy initialization nhờ static holder class

Một idiom thường dùng là **initialization-on-demand holder**: đặt một instance hoặc giá trị cần tạo muộn trong một static nested class. Nested class sẽ được initialize khi static member tương ứng được active use.

Ví dụ tệp **`LazyHolderDemo.java`**:

```java
public class LazyHolderDemo {
    private LazyHolderDemo() {
    }

    private static class Holder {
        static final String VALUE = makeValue();

        static String makeValue() {
            System.out.println("Holder: computing value");
            return "ready";
        }
    }

    static String value() {
        return Holder.VALUE;
    }

    public static void main(String[] args) {
        System.out.println("before first value");
        System.out.println(value());
        System.out.println(value());
    }
}
```

```bash
javac LazyHolderDemo.java
java LazyHolderDemo
```

```text
before first value
Holder: computing value
ready
ready
```

Vì `Holder.VALUE` được khởi tạo bằng **method call**, nó **không phải compile-time constant**. Lần đầu `value()` truy cập Holder.VALUE, Holder được initialize và `makeValue()` chạy. Lần thứ hai dùng giá trị đã có.

Nếu đổi thành:

```java
static final String VALUE = "ready";
```

thì `VALUE` có thể là **constant variable**, và **đọc nó không nhất thiết kích hoạt initialization của Holder**. Đó là khác biệt then chốt khi sử dụng holder pattern.

**Lưu ý:** ở singleton holder thực tế, holder thường giữ `static final Singleton INSTANCE = new Singleton();` — field tham chiếu object không phải compile-time constant; active use kích hoạt holder initialization. Việc singleton có đúng nghĩa trong mọi tình huống reflection/serialization/classloaders lại là một chủ đề riêng.

## 26. Constant inlining còn ảnh hưởng việc cập nhật thư viện

Khi một client đã được biên dịch dùng:

```java
public static final int LIMIT = 100;
```

compiler có thể nhúng giá trị hằng vào bytecode client. Nếu thư viện đổi thành `LIMIT=200` nhưng **không biên dịch lại client**, client cũ có thể vẫn dùng 100 theo cách nó được biên dịch.

Đây không phải “JVM initialize chậm” mà là **constant variable sử dụng giá trị tại compile time**. Vì thế:

- Đừng dùng public compile-time constants cho cấu hình dự kiến thay đổi runtime hoặc giữa các phiên bản thư viện mà không tính compatibility.
- Nếu cần giá trị linh hoạt, có thể dùng **static method** hoặc **non-constant static field** theo API phù hợp.
- Recompile client khi contract public constants thay đổi, và kiểm tra binary compatibility trong thư viện đã phát hành.
- Không dùng constant access chỉ để cố tình kích hoạt static initializer.

Ví dụ khai báo `static final int LIMIT = readConfig();` không còn là constant variable và có initialization runtime; nhưng việc đọc config trong class initialization cũng mang rủi ro thời điểm/lỗi cần quản lý.

## 27. Những thao tác có thể kích hoạt lớp khác ngoài lớp bạn đang chú ý

Quy tắc active use của lớp đích không đồng nghĩa “toàn bộ chương trình không initialize lớp nào khác”.

Ví dụ:

```java
System.out.println(Settings.level);
```

Biểu thức này đồng thời tham gia các hoạt động trên `System`, `PrintStream` và `Settings` tùy trạng thái runtime. Điều bạn kiểm soát/diễn giải ở đây là **thao tác đọc `Settings.level` có thể yêu cầu initialize Settings**.

Tương tự:

```java
new Child(computeArgument());
```

Nếu `computeArgument()` có side effects hoặc active uses lớp khác, output phụ thuộc cả quy tắc **đánh giá biểu thức tạo object**, **arguments**, **superclass initialization**, static/instance initializers và constructors. Không nên dự đoán một thứ tự chung bằng câu “static luôn chạy đầu tiên của cả chương trình”.

**Cách suy luận đúng:**

1. Xác định dòng nào **thực sự chạy**.
2. Xác định class/interface nào được **chủ động sử dụng**.
3. Xác định static member **được khai báo ở đâu**.
4. Xác định class/interface ấy đã initialize thành công trước đó chưa.
5. Xét superclass và superinterfaces theo quy tắc liên quan.
6. Sau khi initialization hoàn tất, tiếp tục đánh giá lời gọi/đọc field/constructor theo thứ tự Java.

## 28. So sánh ba dạng gọi dễ lẫn

### A. Static method của chính class

```java
Target.compute();
```

Nếu `compute` là static method được khai báo ở Target và lần này Target chưa initialize, đó là một trigger.

### B. Static method của superclass nhưng gọi qua tên subclass

```java
Subclass.inheritedStatic();
```

Nếu `inheritedStatic` thực sự khai báo ở Superclass, hãy xác định **declaring class**. Không suy rằng Subclass bắt buộc initialize chỉ vì qualifier hiển thị trong source.

### C. Static method của interface

```java
SomeInterface.helper();
```

Static interface methods được gọi qua **tên interface khai báo**, không được kế thừa như instance methods của interface. Việc gọi helper của interface khiến interface ấy được initialize nếu cần.

Sự khác nhau này giúp tránh lỗi phân tích code sử dụng kế thừa hoặc refactor static methods giữa các lớp.

## 29. Câu hỏi tự kiểm tra: có kích hoạt initialization không?

Giả sử `Target` chưa được initialize, và các biểu thức sau xuất hiện trong method đang chạy với các class được tìm thấy bình thường:

| Biểu thức | Trả lời ngắn | Vì sao |
| --- | --- | --- |
| `Class<Target> t = Target.class;` | **Không** | Class literal không tự initialize |
| `Target[] arr = new Target[4];` | **Không** | Chỉ tạo array, không tạo Target instances |
| `Target x;` | **Không** | Chỉ khai báo biến local |
| `new Target();` | **Có** | Tạo instance kích hoạt class initialization |
| `Target.run();` | **Có** nếu static run khai báo ở Target | Static invocation |
| `Target.value` | **Có** nếu là non-constant static field khai báo ở Target | Đọc field |
| `Target.value = 3;` | **Có** nếu static field có thể gán | Ghi field |
| `Target.LIMIT` | **Không** nếu LIMIT là constant variable | Constant-variable exception |
| `Class.forName("Target")` | **Có** khi resolution/lookup thành công theo overload đó | Reflection API yêu cầu initialize |
| `Class.forName("Target", false, loader)` | **Không từ lời gọi này** | `initialize=false` |
| `loader.loadClass("Target")` | **Không chỉ vì loadClass** | Loading khác initialization |
| `Target.class.getName()` | **Không tự initialize Target** | Metadata, không active execution |
| `target instanceof Target` | **Không tự initialize Target** | Type check khác class initialization |
| `import static pkg.Target.run;` | **Không** | Import được xử lý ở compile time |

Bảng giả định các declaration và context hợp lệ; nếu compiler từ chối biểu thức trước khi chạy (ví dụ gán một `final` field), sẽ **không có runtime trigger để quan sát**.

## 30. Các ngộ nhận phổ biến

| Ngộ nhận | Điều đúng |
| --- | --- |
| “Viết tên lớp ở source là đã initialize lớp” | Chỉ những hoạt động theo quy tắc mới yêu cầu initialization |
| “Loading bằng initialization” | Loading/linking và initialization là các phase khác nhau |
| “Class literal `X.class` chạy static block” | Không tự chạy |
| “Tạo `new X[3]` gọi ba constructor X” | Chỉ tạo array; slots là null |
| “Đọc mọi static field đều chạy static block” | Constant variable là ngoại lệ |
| “Cứ `static final` thì là compile-time constant” | Cần primitive/String và constant expression |
| “Gọi `Class.forName(name,false,loader)` khởi tạo như overload một đối số” | `false` không yêu cầu khởi tạo |
| “`loadClass` chạy initializer ngay” | Không tự yêu cầu initialization |
| “Reflection lấy metadata và gọi method là một” | Lookup và invocation có quy tắc khác |
| “Lúc đầu gọi static method, constructor cũng chạy” | Không cần tạo instance |
| “Static initializer chạy mỗi lần gọi static method” | Initialization thành công không lặp trong cùng runtime class |
| “`Child.parentField` nhất định initialize Child” | Xét class khai báo static field |
| “Initialize Parent sẽ tự initialize tất cả descendants” | Không |
| “Tất cả interfaces implement đều initialize trước class” | Có quy tắc đặc biệt liên quan default methods |
| “Static nested class phải initialize outer class trước” | Không chỉ vì quan hệ lexical nesting |
| “`static` luôn chạy trước dòng đầu `main` của bất kỳ class nào” | Chỉ xét class entry và những active uses thực tế |
| “Mọi lần lỗi initialization sẽ tự retry” | Class có thể trở nên erroneous trong runtime identity |
| “NoClassDefFoundError sau lỗi nghĩa thiếu file .class” | Có thể do initialization đã thất bại |
| “Static initialization có tính nguyên tử cho mọi side effect bên ngoài” | Không; transaction/external systems có quy tắc riêng |
| “`final` reference tới object nghĩa object được khởi tạo từ lúc compile time” | Không; final không quyết định initialization trigger |
| “Một class tên X trên mọi class loader luôn có một static state chung” | Runtime class identity gắn với defining loader |
| “Static block là nơi nên khởi động mọi tài nguyên production” | Side effects phức tạp trong initialization khó kiểm soát |

## 31. Bài thực hành tổng hợp: dự đoán chính xác output

Tạo **`InitializationTraceDemo.java`**:

```java
class Parent {
    static final int CONST = 10;

    static {
        System.out.println("Parent.init");
    }

    static int state = compute();

    static int compute() {
        System.out.println("Parent.compute");
        return 20;
    }

    static void ping() {
        System.out.println("Parent.ping");
    }
}

class Child extends Parent {
    static {
        System.out.println("Child.init");
    }

    Child() {
        System.out.println("Child.constructor");
    }
}

public class InitializationTraceDemo {
    public static void main(String[] args) {
        System.out.println("A");
        System.out.println(Child.CONST);

        System.out.println("B");
        System.out.println(Child.state);

        System.out.println("C");
        Child child = new Child();

        System.out.println("D");
        Parent.ping();

        System.out.println(child != null);
    }
}
```

```bash
javac InitializationTraceDemo.java
java InitializationTraceDemo
```

**Đáp án:**

```text
A
10
B
Parent.init
Parent.compute
20
C
Child.init
Child.constructor
D
Parent.ping
true
```

### Lời giải theo từng dòng

1. `System.out.println("A")` chạy bình thường trong main.
2. `Child.CONST` truy cập constant variable `CONST` khai báo ở Parent; in `10` **chưa cần initialize Parent hoặc Child**.
3. In `B`.
4. `Child.state` truy cập non-constant static field `state` **khai báo ở Parent**. Parent được initialize: static block in `Parent.init`, sau đó field initializer gọi `compute()` in `Parent.compute`.
5. Giá trị `state` là 20, nên in `20`. **Child vẫn chưa cần initialize** chỉ vì `Child.state`.
6. In `C`.
7. `new Child()` yêu cầu initialize Child; Parent đã initialize rồi nên không chạy lại. In `Child.init`, sau đó constructor Child in `Child.constructor`.
8. In `D`.
9. `Parent.ping()` gọi static method; Parent đã initialize nên chỉ in `Parent.ping`, không in lại block hay compute.
10. Biến `child` chứa một reference khác null, nên in `true`.

**Điểm học trọng tâm:** không thể đoán output chỉ bằng cách đếm `static`. Phải xét **declaring class**, **constant variable**, **đã initialize chưa**, **quan hệ superclass** và **thứ tự biểu thức thực thi**.

## 32. Bài tập sửa dự đoán sai

Đọc các thay đổi độc lập sau của chương trình trên và tự suy luận:

**Tình huống A:** đổi `static final int CONST = 10;` thành `static final int CONST = Integer.parseInt("10");`.

- `CONST` không còn là constant variable.
- Dòng `System.out.println(Child.CONST)` có thể trở thành lần đầu kích hoạt Parent initialization.
- Vì vậy `Parent.init` và `Parent.compute` sẽ xuất hiện **trước khi in giá trị 10**, không phải đợi đến khi đọc `state`.

**Tình huống B:** thêm một static block in `Child.extra` sau block có sẵn trong Child.

- Khi Child initialize, hai static blocks của Child chạy theo thứ tự source.
- Điều đó không làm Child initialize sớm ở `Child.CONST` hoặc `Child.state` trong chương trình gốc.

**Tình huống C:** thay `new Child()` bằng `Child[] array = new Child[1];`.

- Chỉ tạo array, không tạo Child instance.
- Nếu chưa có active use của Child khác, static block `Child.init` và constructor Child **không chạy** chỉ vì dòng này.

**Tình huống D:** gọi `Class.forName("Child")` trước `new Child()`.

- Nếu class được tìm thấy với loader/ngữ cảnh phù hợp, invocation có thể yêu cầu initialize Child trước.
- `new Child()` sau đó sẽ không in static initialization của Child lần nữa; constructor vẫn chạy.

Những tình huống này là **bài suy luận thay đổi chương trình mẫu**, không phải các chương trình Java độc lập ghép nguyên văn vào cùng file.

## 33. Checklist khi debug “static block chạy lúc nào?”

1. **Xác định class/interface nào có static initializer**; đừng chỉ dựa vào tên xuất hiện trong source.
2. **Tách loading/linking khỏi initialization**; lấy `Class` object không tự đồng nghĩa đã initialize.
3. **Liệt kê các active uses đầu tiên**: `new`, static method, đọc/ghi non-constant static field, reflective invocation.
4. **Nếu truy cập static member qua subclass**, tra **declaring class/interface** của member.
5. **Nếu field `static final`**, kiểm tra chính xác có phải **constant variable** không: primitive/String + constant expression.
6. **Nếu mảng**, phân biệt `new ElementType[n]` với `new ElementType()` cho từng slot.
7. **Nếu reflection**, xem overload/API có yêu cầu initialization không; `Class.forName(name,false,loader)` khác `Class.forName(name)`.
8. **Nếu superclass/subclass**, xét initialization dependency của superclass.
9. **Nếu interface**, xem default methods và quy tắc initialization đặc thù.
10. **Nếu nested class**, đừng tự khởi tạo outer chỉ vì tên `Outer.Nested`.
11. **Trong một class**, kiểm tra thứ tự static field initializers và static blocks theo source.
12. **Đối chiếu instance field initializers/constructors**; chúng chỉ chạy khi tạo instance theo quy trình liên quan.
13. **Xem class đã initialize trước đó chưa** trong cùng runtime identity.
14. **Nếu lỗi**, phân biệt exception ở lần initialize đầu và lỗi khi thử dùng erroneous class lần tiếp.
15. **Nếu nhiều threads**, xét ràng buộc initialization synchronization và đừng nhầm với transaction.
16. **Nếu library constants thay đổi**, cân nhắc compile-time inlining và client rebuild.
17. **Giữ static initializers đơn giản**, không phụ thuộc thứ tự khởi động ngẫu nhiên của các thành phần ứng dụng.
18. **Chạy `javac`/`java` với đúng tệp và môi trường** để quan sát thực tế nếu có code cụ thể.

---

**Ghi nhớ cuối bài:** Những thao tác thường **kích hoạt khởi tạo lớp** là **tạo instance bằng `new`**, **gọi static method thực sự được khai báo ở lớp đó**, **đọc/ghi static field không phải constant variable**, và **các reflective operations có yêu cầu initialization** như `Class.forName(String)`. Ngược lại, **`SomeClass.class`**, **chỉ khai báo biến**, **tạo mảng `new SomeClass[n]`**, **import**, **đọc constant variable compile-time** và **chỉ nạp class** không phải cùng một điều với chạy static initializer. Khi cần dự đoán thời điểm chính xác, luôn xét **đã khởi tạo chưa, nơi khai báo member, superclass/superinterface, thứ tự static initializers và API reflection cụ thể**.