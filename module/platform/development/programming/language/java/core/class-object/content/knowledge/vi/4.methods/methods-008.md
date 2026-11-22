# Nhận diện `abstract`, `final`, `synchronized` và `native` trên phương thức trong Java

## 1. Bốn từ khóa này nói điều gì về một phương thức?

Một khai báo phương thức Java không chỉ gồm kiểu trả về, tên và tham số. Các **modifier** (từ bổ nghĩa) đứng trước kiểu trả về có thể quyết định liệu phương thức có bắt buộc phải được triển khai, có thể bị ghi đè, có lấy khóa đồng bộ khi chạy, hoặc có phần triển khai nằm ngoài Java.

Bốn modifier cần phân biệt:

| Modifier | Ý nghĩa chính | Có thân Java `{ ... }` trong khai báo tương ứng? | Thực thi/triển khai | Điều cần nhớ |
| --- | --- | --- | --- | --- |
| `abstract` | Chỉ khai báo hợp đồng của **instance method**, chưa cung cấp implementation | **Không**; kết thúc bằng `;` | Lớp con cụ thể phải triển khai (trừ khi đã thừa hưởng triển khai phù hợp) | Không được đồng thời `private`, `static`, `final`, `synchronized` hay `native` |
| `final` | Không cho lớp con **override** phương thức | Có, nếu là concrete method Java thông thường; có thể kết hợp `native` | Dùng implementation hiện có (và có thể overload) | `final` không khiến object bất biến và không cấm gọi method |
| `synchronized` | Khi gọi, JVM lấy **monitor lock** tương ứng trước khi thực thi method | Có đối với method Java thông thường; cũng có thể đi với `native` | Thực thi với khóa của **receiver** (instance) hoặc **Class object** (static) | Chỉ đồng bộ với mã dùng **cùng monitor**; không tự bảo đảm toàn bộ thiết kế thread-safe |
| `native` | Khai báo method có implementation ngoài mã Java, thường qua JNI | **Không**; kết thúc bằng `;` | JVM liên kết lời gọi tới native implementation | Cần triển khai, nạp thư viện và mapping phù hợp; có thể gặp `UnsatisfiedLinkError` |

Các modifier này thuộc về **phương thức**, không phải các thuật ngữ thay thế cho nhau. `abstract` quy định **chưa có triển khai**, `final` quy định **không được ghi đè**, `synchronized` quy định **cách kiểm soát đồng thời khi gọi**, còn `native` quy định **implementation nằm ở phía native**.

Ví dụ nhận diện nhanh:

```java
abstract class Processor {
    abstract String process(String input); // abstract; không có body

    final String label() {                  // final; có body
        return "processor";
    }

    synchronized void record() {           // synchronized; có body
        System.out.println("record");
    }

    native int nativeCode();                // native; không có body
}
```

Đây là **khai báo lớp minh họa**, không phải chương trình chạy độc lập. Lớp `Processor` là `abstract` nên không thể `new Processor()`; nếu gọi `nativeCode()` mà chưa cấu hình native implementation, lời gọi có thể thất bại khi liên kết.

## 2. Vị trí modifier trong cú pháp phương thức

Một phương thức có thân trong class thông thường có dạng:

```java
[annotations] [modifiers] ReturnType methodName(Parameters) [throws Exceptions] {
    // Statements
}
```

Một abstract hoặc native method có thể kết thúc bằng dấu chấm phẩy:

```java
[annotations] [modifiers] ReturnType methodName(Parameters) [throws Exceptions];
```

Hai khung trên là **ký pháp giải thích**, không phải mã Java có thể biên dịch nguyên văn; phần trong ngoặc vuông chỉ là tùy chọn.

Ví dụ cụ thể:

```java
abstract class Operation {
    protected abstract int apply(int left, int right);

    public final String typeName() {
        return "operation";
    }

    public synchronized void logCall() {
        System.out.println("Operation called");
    }
}
```

Khi đọc một chữ ký method:

1. Xác định **modifier** trước kiểu trả về: `abstract`, `final`, `synchronized`, `native` hay tổ hợp hợp lệ.
2. Xác định **kiểu trả về** (`int`, `String`, `void`,...), tên method và danh sách tham số.
3. Kiểm tra khai báo có **thân `{...}`** hay chỉ kết thúc bằng **`;`**.
4. Kiểm tra class hoặc interface chứa method, vì **modifier hợp lệ phụ thuộc ngữ cảnh**.
5. Khi có kế thừa, kiểm tra method sẽ bị **override**, **hide**, **overload**, hay không thể ghi đè.

`abstract` và `native` đều có khai báo không có thân Java, nhưng **không có cùng ý nghĩa**: abstract yêu cầu có một implementation Java phù hợp trong kiểu con cụ thể; native cần implementation ngoài Java và cơ chế liên kết tương ứng.

## 3. `abstract`: khai báo hợp đồng, để lớp con triển khai

Một **abstract method** chỉ khai báo chữ ký, có thể kèm `throws` và modifier truy cập phù hợp, rồi kết thúc bằng `;`.

```java
abstract class Shape {
    abstract double area();
}
```

Lớp `Shape` phải khai báo `abstract` vì nó chứa abstract method `area()`. Không thể tạo đối tượng trực tiếp bằng `new Shape()`; một lớp con **không abstract** phải cung cấp implementation cho các abstract method còn thiếu theo quy tắc override.

### Ví dụ hoàn chỉnh: lớp trừu tượng và lớp con cụ thể

Tạo tệp **`AbstractMethodDemo.java`**:

```java
abstract class Shape {
    private final String name;

    Shape(String name) {
        this.name = name;
    }

    abstract double area();

    String describe() {
        return name + " area=" + area();
    }
}

final class Rectangle extends Shape {
    private final double width;
    private final double height;

    Rectangle(double width, double height) {
        super("rectangle");
        if (width <= 0 || height <= 0) {
            throw new IllegalArgumentException("Dimensions must be positive");
        }
        this.width = width;
        this.height = height;
    }

    @Override
    double area() {
        return width * height;
    }
}

public class AbstractMethodDemo {
    public static void main(String[] args) {
        Shape shape = new Rectangle(3, 4);
        System.out.println(shape.describe());
        System.out.println(shape.area());
    }
}
```

Chạy bằng JDK 17+:

```bash
javac AbstractMethodDemo.java
java AbstractMethodDemo
```

Output:

```text
rectangle area=12.0
12.0
```

Diễn giải:

- `Shape.area()` chỉ mô tả **hợp đồng** trả về `double`, không tính diện tích.
- `Rectangle.area()` có `@Override` và thân trả về `width * height`; đây là **concrete method**.
- Biến `shape` có kiểu tĩnh `Shape` nhưng trỏ tới instance `Rectangle`. Khi gọi `shape.area()`, JVM dispatch đến implementation `Rectangle.area()`.
- `Shape.describe()` là concrete method của abstract class. Nó gọi `area()` trên receiver hiện tại; do receiver là `Rectangle` nên lời gọi bên trong cũng dùng implementation `Rectangle.area()`.
- `Rectangle` được đánh dấu `final` **ở cấp lớp** để ngăn tạo subclass của `Rectangle`; điều này khác modifier `final` trên method. Đoạn ví dụ dùng `final class` chỉ để giới hạn cây kế thừa minh họa.

### Abstract class vẫn có constructor và method có thân

Một abstract class có thể có field, constructor, static method, concrete instance method và abstract method. Constructor của abstract class được gọi trong quá trình tạo **instance lớp con**, dù bản thân abstract class không thể được khởi tạo trực tiếp.

Ngược lại, một lớp khai báo `abstract` **không bắt buộc** phải có abstract method:

```java
abstract class UtilityBase {
    final void ready() {
        System.out.println("ready");
    }
}
```

Đây là khai báo hợp lệ: tác giả muốn giới hạn khởi tạo trực tiếp hoặc tạo nền tảng để subclass sử dụng. Lưu ý `UtilityBase` không có `main`.

### Abstract method trong interface

Trong interface, các method instance thông thường không có thân được hiểu là `public abstract` dù người viết không ghi rõ:

```java
interface Formatter {
    String format(String text); // Ngầm public abstract.
}
```

Interface cũng có thể có **default method**, **static method** và **private method** với thân trong những ngữ cảnh ngôn ngữ phù hợp; chúng không phải abstract method chỉ vì được khai báo trong interface. Những modifier `final`, `synchronized`, `native` không phải lựa chọn hợp lệ để khai báo method của interface; muốn đồng bộ một hành vi default method, có thể đặt `synchronized (lock) { ... }` trong thân nếu thiết kế yêu cầu.

### Những kết hợp `abstract` không hợp lệ

`abstract` không thể đứng cùng:

- `private`: abstract method cần cơ chế triển khai/override hợp lệ, còn private method không bị override.
- `static`: static method gắn với class và không tham gia instance overriding.
- `final`: abstract cần implementation qua override; final cấm override.
- `synchronized`: abstract method không có thân để chạy dưới monitor tương ứng tại cấp khai báo.
- `native`: abstract chưa có implementation, còn native xác nhận implementation nằm ngoài Java.
- `strictfp`: các tổ hợp modifier của Java không cho phép khai báo abstract method đồng thời strictfp.

Các dòng sau **cố ý sai**, đã được comment để tránh nhầm là ví dụ biên dịch:

```java
abstract class InvalidAbstractSamples {
    // abstract final void execute();
    // abstract static void execute();
    // private abstract void execute();
    // abstract synchronized void execute();
    // abstract native void execute();
}
```

Với phương thức abstract, viết thân `{ ... }` ngay trong khai báo cũng là lỗi cú pháp. Nếu muốn cung cấp hành vi sẵn có, bỏ `abstract` và khai báo concrete method.

## 4. `final`: ngăn override method, nhưng không ngăn gọi hay overload

Một **final method** là method mà subclass không được **override**. Nó vẫn có thể được gọi và vẫn có thể chứa phép thay đổi trạng thái.

```java
class Device {
    final String category() {
        return "device";
    }

    void activate() {
        System.out.println("activated");
    }
}

class Phone extends Device {
    @Override
    void activate() {
        System.out.println("phone activated");
    }

    // String category() { return "phone"; }
    // Nếu bỏ comment, lỗi: không được override final method.
}
```

Đây là khai báo lớp hợp lệ khi dòng override `category()` vẫn được comment. `Phone` được phép override `activate()` vì method này không `final`; ngược lại, không thể thay triển khai `category()` trong subclass.

### Ví dụ hoàn chỉnh: final method và overload

Tạo tệp **`FinalMethodDemo.java`**:

```java
class BaseService {
    private int requests;

    final void record() {
        requests++;
    }

    final int getRequests() {
        return requests;
    }

    String status() {
        return "base";
    }
}

class ApiService extends BaseService {
    void record(String label) { // Overload, không override record().
        System.out.println("label=" + label);
        record();
    }

    @Override
    String status() {
        return "api";
    }
}

public class FinalMethodDemo {
    public static void main(String[] args) {
        ApiService service = new ApiService();
        service.record("create");
        service.record();
        System.out.println("requests=" + service.getRequests());
        System.out.println("status=" + service.status());
    }
}
```

Chạy:

```bash
javac FinalMethodDemo.java
java FinalMethodDemo
```

Output:

```text
label=create
requests=2
status=api
```

Giải thích:

1. `record()` của `BaseService` là final; `ApiService` không thể override method không tham số đó.
2. `record(String)` ở lớp con có danh sách tham số **khác** nên là một **overload**, hoàn toàn hợp lệ. Nó gọi `record()` kế thừa rồi chương trình gọi `service.record()` thêm lần nữa; `requests` thành `2`.
3. `status()` không final nên `ApiService` có thể override; lời gọi cuối in `api`.
4. `getRequests()` cũng final nhưng vẫn đọc field instance. Dùng `final` trên method **không làm `requests` bất biến**; việc tăng `requests` vẫn xảy ra.

### Phân biệt `final` theo vị trí

| Khai báo | Tác dụng |
| --- | --- |
| `final class Utility { ... }` | Không thể kế thừa lớp `Utility`. |
| `final void save() { ... }` | Subclass không thể override instance method `save()`. |
| `final int size = 3;` | Biến không được gán lại sau lần gán hợp lệ. |
| `private final List<String> items = ...;` | Không gán lại field tham chiếu; **không tự làm nội dung list bất biến**. |
| `static final int MAX = 10;` | Field tĩnh không được gán lại sau khi đã khởi tạo hợp lệ; thường dùng làm hằng số. |

`final` trên method cũng không có nghĩa method **không thể trả về kết quả mới** hoặc **không có side effect**. `final` chỉ đặt ràng buộc lên **ghi đè trong quan hệ kế thừa**.

### `private`, `static` và `final`

- `private method` không được **override** theo cơ chế kế thừa Java, nên thêm `final` vào private method thường không mang thêm ích lợi về thiết kế API.
- `static method` không được override theo dynamic dispatch; subclass có thể khai báo static method cùng chữ ký theo **method hiding** khi các quy tắc cho phép. Nếu static method của superclass là `final` thì cũng không thể hide nó bằng method cùng chữ ký hợp lệ ở subclass.
- Một method `final` vẫn có thể bị **overload** bằng chữ ký khác, miễn không vi phạm các quy tắc khai báo khác.
- Không thể kết hợp `abstract final`; đây là hai yêu cầu mâu thuẫn về việc phải triển khai bằng override và bị cấm override.

Nên dùng final method khi subclass cần giữ nguyên một thuật toán cốt lõi, một quy tắc kiểm tra hoặc bước không được thay đổi. Không nên mặc định thêm `final` cho mọi method nếu dự án chủ đích cho phép mở rộng bằng kế thừa.

## 5. `synchronized`: tự động khóa monitor khi gọi method

`synchronized` áp dụng **đồng bộ hóa nội tại** (*intrinsic synchronization*) của Java. Khi một thread vào synchronized method, JVM yêu cầu thread giữ **monitor** phù hợp trước khi chạy thân method; khi thoát method, JVM giải phóng monitor theo quy tắc, kể cả khi method kết thúc vì exception.

Có hai trường hợp phải phân biệt:

| Loại phương thức | Monitor được khóa | Ví dụ |
| --- | --- | --- |
| **Instance synchronized method** | Monitor của **receiver object** (`this`) | `synchronized void increment() { ... }` |
| **Static synchronized method** | Monitor của đối tượng `Class` biểu diễn **lớp khai báo method** | `static synchronized void reset() { ... }` |

Monitor thuộc về một object ở runtime; `synchronized` **không tạo một khóa độc lập cho mỗi tên method**.

### Instance synchronized: nhiều thread cùng dùng một object

Tạo tệp **`SynchronizedCounterDemo.java`** (Java 17+):

```java
final class SafeCounter {
    private int count;

    synchronized void increment() {
        count++;
    }

    synchronized int getCount() {
        return count;
    }
}

public class SynchronizedCounterDemo {
    public static void main(String[] args) throws InterruptedException {
        SafeCounter counter = new SafeCounter();

        Runnable job = () -> {
            for (int i = 0; i < 10_000; i++) {
                counter.increment();
            }
        };

        Thread first = new Thread(job);
        Thread second = new Thread(job);
        first.start();
        second.start();

        first.join();
        second.join();

        System.out.println("count=" + counter.getCount());
    }
}
```

Biên dịch và chạy:

```bash
javac SynchronizedCounterDemo.java
java SynchronizedCounterDemo
```

Kết quả:

```text
count=20000
```

Phân tích:

1. Hai thread chạy cùng `job` và gọi `counter.increment()` **trên cùng một object `SafeCounter`**.
2. `increment()` đồng bộ trên monitor của `counter` nên hai thread không thực thi phần method được bảo vệ **đồng thời trên cùng monitor**.
3. Phép `count++` thực chất gồm đọc giá trị cũ, tính toán và ghi lại. Nếu thiếu đồng bộ phù hợp, có thể xảy ra **lost update** khi nhiều thread tăng cùng biến; `synchronized` ở đây giúp tránh vấn đề đó.
4. `getCount()` cũng synchronized, nên đọc dưới cùng monitor với các lần ghi. Mặt khác, `join()` bảo đảm luồng chính chỉ in sau khi hai thread đã hoàn tất; ví dụ có kết quả xác định là `20000`.
5. Nếu tạo **hai đối tượng `SafeCounter` khác nhau**, mỗi đối tượng có monitor khác nhau và count riêng. Hai thread đang khóa hai receiver khác nhau **không bị chặn lẫn nhau chỉ vì gọi cùng tên phương thức**.

Ví dụ dùng `Thread` và `join` để minh họa tính đúng đắn, nhưng không hứa lịch chạy hoặc thứ tự CPU cụ thể. Kết quả cuối có thể dự đoán vì cùng đối tượng được khóa nhất quán và main chờ các thread hoàn tất.

### Cách viết tương đương với synchronized block

Với một instance synchronized method đơn giản:

```java
class Box {
    private int value;

    synchronized void addOne() {
        value++;
    }
}
```

Lựa chọn khác với cùng monitor là:

```java
class Box {
    private int value;

    void addOne() {
        synchronized (this) {
            value++;
        }
    }
}
```

Hai khai báo trên là **hai phiên bản riêng biệt của cùng một lớp để so sánh**, không đặt đồng thời vào một tệp nguồn vì trùng định nghĩa `Box`. Trong phiên bản thứ hai, block được viết rõ `synchronized (this)` và phạm vi khóa nằm trong block. Trong phiên bản thứ nhất, khóa bao phủ toàn bộ thân method.

Một synchronized block cũng có thể khóa **đối tượng bất kỳ**:

```java
private final Object lock = new Object();

// Đoạn trong một instance method:
synchronized (lock) {
    // Truy cập trạng thái cần bảo vệ.
}
```

Đoạn sau là **mảnh code minh họa**; field `lock` phải được đặt trong lớp còn khối `synchronized` phải nằm trong method/constructor/initializer thích hợp. Dùng một private lock object có thể tránh để mã bên ngoài chiếm monitor `this`, nhưng các thao tác truy cập dữ liệu chung phải thống nhất dùng cùng khóa.

### Static synchronized: khóa đối tượng `Class`

Tạo tệp **`StaticSynchronizedDemo.java`**:

```java
class Registry {
    private static int registered;

    static synchronized void register() {
        registered++;
    }

    static synchronized int total() {
        return registered;
    }
}

public class StaticSynchronizedDemo {
    public static void main(String[] args) {
        Registry.register();
        Registry.register();
        System.out.println(Registry.total());
    }
}
```

```bash
javac StaticSynchronizedDemo.java
java StaticSynchronizedDemo
```

```text
2
```

`Registry.register()` và `Registry.total()` là **static synchronized methods**, dùng monitor của `Registry.class` khi được gọi. Chúng không lấy monitor của một object `new Registry()` nào. Về **khóa được sử dụng**, một static synchronized method tương đương block `synchronized (Registry.class) { ... }` bao toàn bộ thân.

**Bẫy:** `synchronized` instance method và `static synchronized` method của cùng lớp **không tự chặn nhau**, vì khóa `this` và khóa `Class` là **hai monitor khác nhau**. Nếu cùng thay đổi một static field, dùng những khóa khác nhau có thể không bảo vệ được invariant.

### `synchronized` còn giúp bảo đảm visibility

Theo **Java Memory Model**, một lần unlock monitor *happens-before* lần lock **sau đó** trên chính monitor ấy. Vì thế `synchronized` không chỉ chống hai thread chen vào vùng bảo vệ cùng monitor, mà còn thiết lập các quan hệ **hiển thị thay đổi bộ nhớ** giữa các thao tác đồng bộ phù hợp.

Tuy nhiên, `synchronized` **không tự biến toàn bộ lớp thành thread-safe**:

- Nếu có method khác đọc/ghi cùng field mà **không tham gia cùng giao thức đồng bộ**, dữ liệu vẫn có thể bị race.
- Nếu dùng **hai monitor khác nhau** để bảo vệ một invariant, hai thread vẫn có thể xen kẽ không như dự tính.
- Việc một method synchronized gọi một method khác rồi giao object có thể sửa được ra ngoài đòi hỏi xem xét **toàn bộ chuỗi thao tác** và việc thoát tham chiếu.
- Nếu logic gồm nhiều lời gọi `get()`, kiểm tra, rồi `set()` riêng rẽ, từng method synchronized có thể vẫn chưa đủ để bảo đảm **tính nguyên tử của cả chuỗi**; có thể cần bao trọn giao dịch trong một vùng khóa.
- Cần lưu ý nguy cơ **deadlock** nếu các thread lấy nhiều lock theo thứ tự không nhất quán; giữ khóa trong lúc chờ I/O lâu cũng có thể giảm khả năng đáp ứng.

Các synchronized method trên **cùng monitor** có tính **reentrant**: một thread đang giữ monitor có thể gọi tiếp một synchronized method khác cần cùng monitor mà không tự deadlock vì khóa đó. Cơ chế reentrancy không giải quyết mọi deadlock giữa **các khóa khác nhau**.

### Override một synchronized method có bắt buộc synchronized không?

Không. Modifier `synchronized` **không thuộc chữ ký method** và không được tự động kế thừa như một ràng buộc “method override phải synchronized”. Ví dụ:

```java
class Parent {
    synchronized void process() {
        System.out.println("parent");
    }
}

class Child extends Parent {
    @Override
    void process() {
        System.out.println("child");
    }
}
```

Đây là khai báo lớp hợp lệ. `Child.process()` override `Parent.process()` mà không dùng synchronized; lời gọi dispatch đến `Child.process()` sẽ **không tự lấy monitor do modifier synchronized của bản superclass**. Vì thế API dựa vào đồng bộ qua override cần được thiết kế và rà soát cẩn thận.

### `synchronized` không dùng trên constructor

Java không cho khai báo `synchronized ConstructorName(...)`. Nếu cần đồng bộ một phần công việc trong constructor, có thể dùng một synchronized block theo quy tắc. Nhưng object thường chưa được công bố cho thread khác trước khi constructor hoàn thành, nên việc dùng monitor `this` trong constructor chỉ để “an toàn” có thể là dấu hiệu cần xem lại cách xuất bản object.

## 6. `native`: khai báo method, implementation nằm ngoài mã Java

`native` biểu thị một method mà **phần thân triển khai không được viết bằng thân Java ngay trong khai báo đó**. Kịch bản truyền thống là **Java Native Interface (JNI)** nối mã Java tới hàm viết bằng C/C++ hoặc mã native khác thông qua cơ chế thích hợp.

```java
class NativeMath {
    native int square(int value);
}
```

Chữ ký là hợp lệ nhưng lớp chưa chứa implementation Java của `square`. Native method phải khai báo **không có body**, kết thúc bằng `;`. Để gọi thành công, runtime phải có native function tương ứng được liên kết đúng qua môi trường JNI hoặc cơ chế liên quan.

### Ví dụ nhận diện có nạp thư viện

```java
class NativeCalculator {
    static {
        System.loadLibrary("native_calculator");
    }

    native int multiply(int left, int right);

    static native String platformName();
}
```

Đây là **mã khai báo minh họa**, không chạy độc lập khi chưa biên dịch và cung cấp thư viện `native_calculator` đúng nền tảng. `System.loadLibrary(...)` yêu cầu JVM tìm và nạp thư viện native theo cơ chế cấu hình đường dẫn/tên thư viện của hệ điều hành.

- `multiply` là **instance native method**; lời gọi `calculator.multiply(2, 3)` có receiver `calculator` nhưng implementation chạy phía native.
- `platformName` là **static native method**; lời gọi `NativeCalculator.platformName()` không dùng receiver object thông thường.
- Đối số, kiểu trả về và hành vi throw exception vẫn chịu những ràng buộc của cầu nối giữa Java và native code.
- Nếu thư viện không được tìm thấy, nạp sai kiến trúc hoặc không có native symbol/mapping phù hợp, JVM có thể ném **`UnsatisfiedLinkError`** khi nạp hoặc liên kết.
- Native code có khả năng tương tác với bộ nhớ hoặc tài nguyên ngoài mô hình Java thông thường; lỗi ở phía native có thể gây hỏng tiến trình, không chỉ là một Java exception thông thường.

### Chu trình tối thiểu khi dùng JNI

Một quy trình phổ biến với JNI trên JDK hiện đại:

1. Khai báo native method trong Java, dùng `javac -h` tạo JNI header cho các khai báo cần thiết.
2. Viết và biên dịch shared library native theo header và platform ABI của hệ điều hành.
3. Đặt thư viện vào vị trí mà JVM có thể nạp, hoặc cấu hình đường dẫn nạp phù hợp.
4. Nạp bằng `System.loadLibrary(...)` hoặc cơ chế tương đương, rồi gọi method để kiểm tra tên hàm, kiểu và hành vi.

Ví dụ ký pháp lệnh với một tệp `NativeMath.java` thực sự chứa khai báo native tương ứng:

```bash
javac -h . NativeMath.java
```

Tùy cấu trúc lớp/package, JDK tạo tệp header mang tên thích hợp; phần C/C++ phải triển khai đúng chữ ký sinh ra. Chỉ chạy lệnh `javac -h` **chưa thể gọi thành công method native** nếu chưa có thư viện native hoàn chỉnh.

### `native` khác gì với `abstract`?

| Điểm so sánh | `abstract` | `native` |
| --- | --- | --- |
| Có thân Java tại chỗ? | Không | Không |
| Implementation dự kiến | Concrete subclass/implementing class cung cấp triển khai phù hợp | Native implementation được liên kết lúc chạy |
| Có thể gọi trên instance của lớp chứa khai báo ngay không? | Không thể tạo instance nếu lớp còn abstract | Có thể tạo instance của concrete class có native method; việc gọi vẫn cần native link |
| Có thể `static`? | Không | Có |
| Có thể `final`? | Không | Có |
| Có thể `synchronized`? | Không | Có, theo quy tắc method phù hợp |
| Trường hợp thường dùng | API/hợp đồng đa hình | JNI, tích hợp native library/hệ thống |

Một khai báo `native` **không làm cho method abstract**, và khai báo `abstract` **không ám chỉ triển khai bằng C/C++**.

### Có thể kết hợp `native` với `synchronized` và `final` không?

Ở mức cú pháp modifier Java cho **method trong class**, một native method có thể là `static`, `final` hoặc `synchronized` khi không vi phạm điều kiện khác:

```java
class NativeBridge {
    final native int checksum(byte[] bytes);
    static native long nativeClock();
    synchronized native void updateNativeState();
}
```

Đoạn này **chỉ minh họa khai báo hợp lệ**, chưa có thư viện JNI nên không có output độc lập. `final` trên `checksum` ngăn override; `synchronized` trên `updateNativeState` yêu cầu lấy monitor receiver trong quá trình invocation theo quy tắc JVM, dù phần thân chạy phía native.

Một native method không có Java body nên không thể viết:

```java
// native int checksum(byte[] bytes) {
//     return 0;
// }
// Cố ý sai: native method không được có method body Java.
```

`native` cũng không thể cùng `abstract` hoặc `strictfp` theo quy tắc modifier. Method `native` không thể đặt trong một Java interface như một interface method modifier hợp lệ.

## 7. Bảng kết hợp modifier: hợp lệ hay lỗi?

Bảng sau áp dụng cho **method trong class thông thường**, không mặc định áp dụng cho method trong interface, constructor hoặc class declaration.

| Tổ hợp | Hợp lệ? | Giải thích |
| --- | --- | --- |
| `abstract void run();` | Có, trong abstract class | Chưa có body; class chứa abstract method phải abstract. |
| `final void run() { }` | Có | Concrete method không thể bị override. |
| `synchronized void run() { }` | Có | Instance method khóa monitor của receiver. |
| `static synchronized void run() { }` | Có | Static method khóa monitor của `Class` khai báo method. |
| `native void run();` | Có | Implementation bên ngoài Java. |
| `static native void run();` | Có | Static native method. |
| `final synchronized void run() { }` | Có | Không thể override; method dùng monitor của receiver. |
| `final native void run();` | Có | Native method không thể bị override. |
| `synchronized native void run();` | Có | Native method được gọi dưới monitor tương ứng. |
| `abstract final void run();` | **Không** | Cần override để triển khai nhưng final cấm override. |
| `abstract synchronized void run();` | **Không** | Abstract method không có body để đồng bộ tại khai báo. |
| `abstract native void run();` | **Không** | Hai mô hình cung cấp implementation xung đột. |
| `abstract static void run();` | **Không** | Static method không là instance method có thể override. |
| `private abstract void run();` | **Không** | Private không được override theo cách abstract yêu cầu. |
| `native void run() { }` | **Không** | Native method không có Java method body. |
| `synchronized Constructor() { }` | **Không** | Constructor không mang modifier synchronized. |

Việc một tổ hợp **hợp lệ về cú pháp modifier** chưa bảo đảm lời gọi thành công: chẳng hạn mọi khai báo `native` vẫn cần triển khai/link thư viện thích hợp.

Tham chiếu nhanh theo câu hỏi nhận diện:

- Thấy **`abstract`** → tìm **subclass/implementation** và kiểm tra lớp chứa có `abstract`.
- Thấy **`final`** → tìm **kế thừa/override** và chặn các override vi phạm; đừng suy ra trạng thái bất biến.
- Thấy **`synchronized`** → xác định **monitor nào được khóa** và những đường truy cập trạng thái chung khác có dùng cùng monitor không.
- Thấy **`native`** → tìm **JNI/native integration**, khả năng nạp thư viện và mapping implementation.

## 8. Kế thừa và bốn modifier trong cùng một thiết kế

Có thể kết hợp các modifier khác nhau trên **các method khác nhau** để tạo lớp nền rõ ràng.

Tạo tệp **`MethodPolicyDemo.java`**:

```java
abstract class WorkerTask {
    private int completed;

    abstract String perform();

    final String category() {
        return "worker-task";
    }

    synchronized void markCompleted() {
        completed++;
    }

    synchronized int completedCount() {
        return completed;
    }
}

class EmailTask extends WorkerTask {
    @Override
    String perform() {
        markCompleted();
        return "sent";
    }
}

public class MethodPolicyDemo {
    public static void main(String[] args) {
        WorkerTask task = new EmailTask();

        System.out.println("category=" + task.category());
        System.out.println("result=" + task.perform());
        System.out.println("result=" + task.perform());
        System.out.println("completed=" + task.completedCount());
    }
}
```

Biên dịch/chạy:

```bash
javac MethodPolicyDemo.java
java MethodPolicyDemo
```

Output:

```text
category=worker-task
result=sent
result=sent
completed=2
```

Đọc thiết kế:

1. `WorkerTask.perform()` là **abstract method**, buộc `EmailTask` cung cấp implementation vì `EmailTask` là concrete class.
2. `category()` là **final method**, lớp con không được thay đổi cách trả về danh mục. Dù variable `task` có kiểu `WorkerTask`, receiver thực là `EmailTask` thì method final vẫn được dùng theo quy tắc.
3. `markCompleted()` và `completedCount()` là **instance synchronized methods** cùng khóa trên receiver `task`; chúng bảo vệ truy cập vào field `completed` khi những lời gọi đó được thực hiện từ nhiều thread trên cùng object.
4. `perform()` của `EmailTask` gọi `markCompleted()`. Bản thân `perform()` **không synchronized**, nên những phần khác trong body ngoài lời gọi `markCompleted()` không được monitor bao trọn.
5. Bài này không cần `native` vì logic hoàn toàn nằm trong Java. Thêm `native` chỉ để “thấy đủ bốn từ khóa” sẽ tạo phụ thuộc native không có ích.

Ví dụ còn cho thấy **final và synchronized không thay thế nhau**: `category()` không cho override nhưng không cần lock, trong khi `markCompleted()` dùng lock để bảo vệ trạng thái mà vẫn có thể bị override nếu subclass cố ý làm vậy. Khi bảo vệ invariant trong một API cho phép kế thừa, cần xem xét có nên thêm `final` vào method đồng bộ để ngăn subclass bỏ cơ chế đồng bộ, hoặc thiết kế API tránh phụ thuộc vào override không được kiểm soát.

## 9. Ngữ cảnh interface, constructor và static method

Một số nhầm lẫn đến từ việc áp dụng modifier của **class method** sang cấu trúc khác.

### Interface

Trong Java 17, một interface có thể chứa:

```java
interface TaskListener {
    void onDone(); // Ngầm public abstract.

    default void onStart() {
        System.out.println("start");
    }

    static String kind() {
        return "listener";
    }

    private void helper() {
        System.out.println("helper");
    }
}
```

- `onDone()` là abstract method; nó không có body.
- `onStart()` là default method có body, có thể được implementation class kế thừa/override theo quy tắc.
- `kind()` là static interface method, không có receiver instance, được gọi qua `TaskListener.kind()`.
- `helper()` là private interface method có body và hỗ trợ tái sử dụng logic nội bộ trong interface.

Không khai báo interface method bằng `final`, `native` hoặc `synchronized`. Cũng không gộp `abstract` với `default` hay `static` trên cùng method; đây là các chế độ khác nhau.

### Constructor

Một constructor có tên lớp và **không có kiểu trả về**:

```java
class Report {
    Report() {
        System.out.println("created");
    }

    final void publish() {
        System.out.println("published");
    }
}
```

`Report()` **không phải method**, nên không khai báo bằng `abstract`, `final`, `synchronized` hay `native` như modifier của method. `publish()` mới là final instance method.

### Static method

`static synchronized void refresh() { ... }` là hợp lệ và khóa monitor của `Class`. `static final void refresh() { ... }` cũng hợp lệ trong class, nhưng việc dùng `final` với static method liên quan đến **method hiding**, vì static method không tham gia override/dynamic dispatch.

`static abstract` là bất hợp lệ. `static native` có thể hợp lệ và thường được dùng khi một native function không cần receiver Java instance.

## 10. Method modifier không bao hàm mọi khía cạnh an toàn và thiết kế

### 10.1. `final` không làm method không có side effect

```java
class ChangingState {
    private int value;

    final void increase() {
        value++;
    }

    int value() {
        return value;
    }
}
```

`increase()` hoàn toàn có thể thay đổi field dù là final method. Muốn object bất biến cần thiết kế field, luồng xuất bản và API sửa đổi thích hợp; điều đó độc lập với việc method có bị override hay không.

### 10.2. `synchronized` không bảo vệ theo tên field tự động

Hai method khác nhau cùng sửa một field nhưng khóa **khác nhau** chưa bảo đảm an toàn. Nếu `methodA()` dùng `synchronized (lockA)` còn `methodB()` dùng `synchronized (lockB)`, hai thread vẫn có thể đồng thời thay đổi field. Cần thiết kế lock discipline nhất quán.

### 10.3. `native` không đồng nghĩa chạy nhanh hơn

Gọi native method có thể thêm chi phí chuyển qua ranh giới JNI, xử lý dữ liệu và kiểm soát tài nguyên. Độ nhanh phụ thuộc workload và cách triển khai. `native` là quyết định tích hợp, không phải một công tắc tăng tốc.

### 10.4. `abstract` không buộc lớp con có duy nhất một cách triển khai

Nhiều subclass có thể triển khai cùng abstract method theo cách riêng. Kiểu khai báo là contract, còn hành vi cụ thể có thể khác nhau theo receiver runtime. Bản thân một abstract class có thể cung cấp một phần hành vi chung và quản lý trạng thái.

### 10.5. `final` không luôn ngăn mọi hình thức tùy biến

Không thể override một final instance method, nhưng subclass vẫn có thể khai báo **method overload** có tham số khác hoặc cung cấp các method mới. Lớp con cũng có thể thay đổi những trạng thái mà implementation final method có sử dụng qua các đường hợp lệ; vì vậy final method giúp ổn định thuật toán nhưng chưa hẳn bảo đảm toàn bộ kết quả nghiệp vụ bất biến.

### 10.6. Exception và khóa trong `synchronized`

Nếu synchronized method ném exception, monitor được giải phóng khi method thoát. Nhưng điều này không làm các thay đổi state đã thực hiện trước exception tự động rollback. Nếu invariant gồm nhiều field, cần thiết kế thứ tự cập nhật và xử lý thất bại hợp lý.

### 10.7. Native code và yêu cầu đóng gói

Một lớp chứa native declaration có thể **biên dịch** mà chưa có JNI library, nhưng **khả năng chạy thành công** khi gọi method yêu cầu thư viện cho đúng nền tảng, kiến trúc, đường dẫn và symbol. Không đưa native method vào API thông thường nếu không có nhu cầu tích hợp rõ ràng.

## 11. Cách nhận diện lỗi biên dịch qua ví dụ ngắn

Các tình huống dưới đây là **đoạn cố ý sai**; không chép thẳng vào chương trình chạy.

### Lỗi A: abstract method có body

```java
// abstract class Bad {
//     abstract void execute() {
//         System.out.println("run"); // Không được có body cho abstract.
//     }
// }
```

Sửa bằng `abstract void execute();` hoặc bỏ `abstract` để có concrete method.

### Lỗi B: subclass override final method

```java
// class Parent {
//     final void ping() { }
// }
// class Child extends Parent {
//     @Override
//     void ping() { } // Không thể override Parent.ping().
// }
```

Sửa bằng không override, đổi hợp đồng thiết kế nếu có quyền thay đổi superclass, hoặc dùng overload thật sự khác chữ ký.

### Lỗi C: abstract kết hợp synchronized

```java
// abstract class Bad {
//     abstract synchronized void run(); // Tổ hợp modifier không hợp lệ.
// }
```

Sửa thành `abstract void run();`. Implementation cụ thể ở subclass có thể tự dùng `synchronized` nếu cần:

```java
abstract class ParentTask {
    abstract void runTask();
}

class LoggedTask extends ParentTask {
    @Override
    synchronized void runTask() {
        System.out.println("run");
    }
}
```

### Lỗi D: native method có body Java

```java
// class Bad {
//     native int read() {
//         return 1; // Không được có Java body cho native method.
//     }
// }
```

Nếu muốn viết thân Java, bỏ `native`; nếu muốn JNI, giữ khai báo `native int read();` và cung cấp native implementation qua thư viện phù hợp.

### Lỗi E: tưởng override synchronized method tự đồng bộ

```java
class Base {
    synchronized void update() {
        System.out.println("base");
    }
}

class Derived extends Base {
    @Override
    void update() {
        System.out.println("derived");
    }
}
```

Đoạn này **hoàn toàn hợp lệ** về cú pháp, nhưng `Derived.update()` **không tự động synchronized**. Đây là lỗi về suy luận hành vi, không phải lỗi biên dịch. Nếu thiết kế yêu cầu mọi đường ghi state đều đồng bộ, phải xác định đường nào thực sự giữ lock.

## 12. Tự kiểm tra với đáp án

**Câu 1.** Phương thức `abstract int size();` có thể xuất hiện trong một concrete class không?

**Đáp án:** Không. Class chứa abstract method phải là `abstract`; implementation cụ thể cần được cung cấp ở subclass không abstract (trừ trường hợp được đáp ứng hợp lệ qua kế thừa).

**Câu 2.** `final void run() { }` có cấm mọi lời gọi `run()` từ subclass không?

**Đáp án:** Không. Subclass có thể kế thừa và gọi final method khi quyền truy cập cho phép, nhưng không được override nó. Overload bằng chữ ký khác vẫn có thể hợp lệ.

**Câu 3.** Hai thread gọi `counter.increment()` trên **cùng một** object và method là instance synchronized thì khóa nào được dùng?

**Đáp án:** Monitor của chính đối tượng `counter`; một thread phải chờ nếu monitor đó đang bị thread kia giữ.

**Câu 4.** Một `static synchronized void update()` khóa object instance hay khóa lớp?

**Đáp án:** Khóa monitor của **`Class` object** biểu diễn lớp khai báo method; không phải khóa `this`.

**Câu 5.** Tại sao `native int sum(int a, int b);` có thể biên dịch nhưng gọi lại phát sinh `UnsatisfiedLinkError`?

**Đáp án:** Java declaration hợp lệ không đồng nghĩa JVM đã nạp và liên kết được native implementation. Nếu thư viện/symbol tương ứng thiếu hoặc sai, native call có thể thất bại.

**Câu 6.** `abstract native void work();` có hợp lệ không?

**Đáp án:** Không. Hai modifier này không được kết hợp trên cùng một method.

**Câu 7.** Một method `final synchronized void save() { ... }` có hợp lệ không, và hai từ khóa kiểm soát điều gì?

**Đáp án:** Có, với class method phù hợp. `final` ngăn override trong subclass; `synchronized` lấy monitor của receiver khi gọi instance method.

**Câu 8.** Nếu override một synchronized instance method bằng method không synchronized, JVM có tự lấy khóa do superclass khai báo không?

**Đáp án:** Không. Lời gọi dispatch đến implementation overriding sẽ có hành vi đồng bộ theo modifier của chính method được gọi và các synchronized block bên trong nó.

**Câu 9.** Vì sao `native` không nên được xem là từ khóa “tối ưu hiệu năng” mặc định?

**Đáp án:** JNI là cầu nối kỹ thuật đến native implementation; khả năng nhanh/chậm tùy công việc và chi phí chuyển đổi dữ liệu, không có bảo đảm tăng tốc chỉ nhờ modifier.

**Câu 10.** Trong `MethodPolicyDemo`, khi gọi `task.perform()`, tại sao hành vi là của `EmailTask` dù biến có kiểu `WorkerTask`?

**Đáp án:** `perform` là abstract instance method và `EmailTask` cung cấp implementation. Runtime dispatch theo receiver thực tế là `EmailTask`.

## 13. Checklist khi đọc chữ ký phương thức trong dự án Java

Khi gặp một method có những modifier này, hãy rà soát theo trình tự:

1. **Cú pháp:** method kết thúc bằng `;` hay có `{ ... }`? `abstract` và `native` yêu cầu không có Java body; `final` và `synchronized` có những ràng buộc riêng.
2. **Ngữ cảnh:** method nằm trong abstract class, concrete class hay interface? Có modifier bất hợp lệ tại vị trí đó không?
3. **Kế thừa:** phương thức có thể override không? Có @Override ở subclass không? `final` có chặn thay triển khai không?
4. **Lời gọi:** phương thức là static hay instance? Static synchronized khóa `Class`; instance synchronized khóa receiver object.
5. **Trạng thái:** đồng bộ hóa có bao phủ tất cả đường truy cập tới field chung không? Có nhiều bước cần thực hiện nguyên tử như một giao dịch không?
6. **Implementation:** nếu `native`, thư viện được nạp ở đâu, mapping JNI ra sao, native ABI có phù hợp không?
7. **Kiểm chứng:** kiểm tra compile error với tổ hợp modifier sai; chạy ví dụ thread có `join` để quan sát giá trị cuối; không dùng các output phụ thuộc race để khẳng định hành vi “luôn xảy ra”.

---

**Ghi nhớ:** `abstract` là **hợp đồng chờ triển khai**, `final` là **ràng buộc ngăn override**, `synchronized` là **khóa monitor khi gọi** và `native` là **khai báo implementation nằm ngoài Java**. Với mỗi phương thức, việc nhận diện đúng modifier, kiểu static/instance, class/interface chứa nó, sự hiện diện của thân method và quan hệ kế thừa sẽ cho biết **lời gọi được triển khai ở đâu, khi nào được khóa, và ai được phép thay đổi hành vi**.