# Phân biệt nạp lớp, liên kết lớp và khởi tạo lớp trong Java

Khi JVM sử dụng một kiểu Java, ba khái niệm thường bị gộp thành một là **nạp lớp (loading)**, **liên kết lớp (linking)** và **khởi tạo lớp (initialization)**. Thực ra chúng có vai trò khác nhau:

- **Loading** giúp JVM tìm/định nghĩa biểu diễn runtime của một class hoặc interface từ dữ liệu nhị phân phù hợp.
- **Linking** kiểm tra và chuẩn bị kiểu để các tham chiếu, trường và phương thức có thể được sử dụng an toàn; nó gồm **verification**, **preparation**, **resolution**.
- **Initialization** thực thi các **static field initializers** và **static initializer blocks** của class, hoặc các field initializers của interface, theo quy tắc khởi tạo.

Đây là các bước thuộc **vòng đời kiểu trong JVM**, khác với **khởi tạo từng object** khi gọi constructor. Nhìn thấy dòng `static { ... }` in ra console cho biết class đã đến giai đoạn khởi tạo, **không phải thời điểm chính xác mà class file lần đầu được đọc vào JVM**.

Bài thuộc Java Core — *class-object*, nhóm **Thứ tự khởi tạo**. Các ví dụ độc lập chạy với **Java 17 trở lên** và được thiết kế để minh họa rõ thứ tự, trường hợp trì hoãn initialization, class loader, hằng số compile-time, lớp cha/interface, thất bại khởi tạo và cách chẩn đoán.

## 1. Một bản đồ của ba giai đoạn

Một mô hình khái niệm thông dụng:

~~~text
Thông tin định danh kiểu (binary name + defining class loader)
                         |
                         v
        1. LOADING — tạo biểu diễn class/interface
                         |
                         v
        2. LINKING
           ├─ Verification: kiểm tra tính hợp lệ của biểu diễn
           ├─ Preparation : cấp phát/chuẩn bị static fields, giá trị mặc định
           └─ Resolution  : phân giải các symbolic references khi cần
                         |
                         v
        3. INITIALIZATION
           ├─ bảo đảm superclass cần thiết được initialized
           ├─ xử lý những superinterface thích hợp theo JLS
           └─ thực thi static initializers và field initializers
                         |
                         v
        Class sẵn sàng cho những sử dụng đòi initialization
~~~

Đây là **sơ đồ khái niệm**, không phải bản ghi một chuỗi thao tác tuyệt đối tại runtime. JVM có quyền chọn **phân giải symbolic references sớm hoặc muộn** trong phạm vi quy định; vì vậy đừng hiểu rằng mọi resolution của mọi dependency bắt buộc hoàn tất thành một khối duy nhất trước initialization.

Những ràng buộc quan trọng:

1. Kiểu phải được **nạp hoàn chỉnh** trước khi liên kết.
2. Verification và preparation cần đáp ứng trước initialization.
3. Resolution có thể được trì hoãn theo quy tắc JVM.
4. Một lớp không nhất thiết được initialized ngay khi vừa loaded hoặc đã linked.
5. Mỗi class hoặc interface được initialized theo trạng thái riêng, có phối hợp an toàn khi nhiều thread cùng yêu cầu khởi tạo.

Nguồn chuẩn để đối chiếu là [JLS 17, Chapter 12](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html) và [JVMS 17, Chapter 5](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html).

## 2. Loading: JVM tìm và định nghĩa một kiểu

**Loading** là quá trình JVM có được biểu diễn runtime của một class/interface dựa trên định danh của kiểu và **class loader định nghĩa** (*defining class loader*). Với kiểu thông thường trong ứng dụng, loader tìm các class bytes rồi JVM sử dụng biểu diễn nhị phân phù hợp để tạo thông tin kiểu.

Trong ứng dụng Java, những nguồn có thể dẫn đến loading gồm:

- Các class file được tìm trên classpath hoặc module path.
- Class thuộc JDK, thư viện và ứng dụng do những class loader thích hợp quản lý.
- Class được định nghĩa từ bytecode do một loader tùy biến cung cấp.
- Những kiểu được phát sinh động bởi cơ chế runtime; đối với array class, JVM có quy tắc tạo riêng.

**Loading không có nghĩa Java source được biên dịch tại thời điểm đó.** Trong quy trình `javac` thông thường, source `.java` đã được biên dịch thành `.class` trước khi ứng dụng chạy. JVM tiêu thụ dạng nhị phân; không cần tồn tại tệp `.java` trong môi trường runtime.

### Có phải loader đọc mọi class ngay khi `java Main` chạy?

Không. JVM và các class loader có thể nạp nhiều kiểu khi startup hoặc theo nhu cầu; không có yêu cầu phải nạp toàn bộ class của dự án trước khi chạy dòng đầu tiên của `main`.

Đừng dựa trên log “class được loaded” để kết luận một static block đã chạy. Một class có thể được biết tới ở runtime từ trước, nhưng static initializer vẫn chưa được thực thi.

## 3. Danh tính class phụ thuộc cả tên và loader

Một nguyên tắc rất quan trọng trong JVM: hai class có **cùng binary name** nhưng được **định nghĩa bởi hai class loader khác nhau** có thể là **hai kiểu runtime khác nhau**.

~~~text
Loader A định nghĩa org.example.Task  ---> Class object A
Loader B định nghĩa org.example.Task  ---> Class object B

Cùng chuỗi tên "org.example.Task"
không đủ khẳng định cùng một runtime type.
~~~

Sự phân biệt này giải thích một số lỗi classpath/plugin/server nâng cao: object trông như thuộc một class “cùng tên” nhưng việc ép kiểu có thể thất bại do khác class loader. Mỗi class/interface runtime có trạng thái initialization tương ứng của chính nó, thay vì một static state chung cho mọi bản định nghĩa cùng tên.

Mô hình delegation của class loader thường giúp hạn chế định nghĩa trùng kiểu, nhưng custom loaders có thể dùng những chiến lược khác trong phạm vi JVM cho phép. Chỉ cần ghi nhớ ở mức Java Core: **tên class không phải toàn bộ định danh runtime**.

Phân biệt:

- `ClassLoader.loadClass(...)` liên quan đến yêu cầu nạp kiểu; bản thân thao tác này **không phải mệnh lệnh chạy static initializer**.
- `Class.forName(name)` một tham số mặc định **yêu cầu initialization** của class tương ứng.
- `Class.forName(name, false, loader)` yêu cầu có đối tượng `Class` nhưng **không yêu cầu khởi tạo** class đó.

## 4. Linking: ba việc khác nhau, không phải chạy constructor

Linking gồm ba hoạt động theo [JLS §12.3](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.3):

| Thành phần | Vai trò chính | Không nên hiểu nhầm là |
| --- | --- | --- |
| **Verification** | Kiểm tra ràng buộc cấu trúc/an toàn của biểu diễn nhị phân | Chạy test nghiệp vụ của lớp |
| **Preparation** | Tạo và chuẩn bị các static fields cùng giá trị ban đầu theo quy tắc JVM | Chạy các biểu thức initializer tùy ý trong source |
| **Resolution** | Phân giải symbolic reference từ constant pool tới thực thể runtime thích hợp | Bắt buộc giải quyết mọi dependency ngay lập tức |

Một lỗi verification thường liên quan tới bytecode không hợp lệ hoặc vi phạm ràng buộc JVM; nó không đồng nghĩa constructor ném `IllegalArgumentException` khi validate input.

Một lỗi resolution có thể xuất hiện nếu trường/phương thức hoặc kiểu mà class nhắc tới không tồn tại hoặc không tương thích tại runtime; ví dụ thuộc họ `NoSuchMethodError` hoặc `NoSuchFieldError` trong tình huống thay đổi binary không tương thích. Đây là **linkage errors**, khác với exception do static initializer tự ném.

**Thứ tự không thể giản lược** thành “verification → preparation → giải hết mọi thứ → initialization”. JVM có quyền phân giải sớm hoặc theo nhu cầu, nhưng phải tuân yêu cầu mà JVM Specification đặt ra.

## 5. Preparation: static field đã có chỗ lưu, nhưng initializer chưa chạy

Xét class:

~~~java
class Metrics {
    static int count = calculateInitialCount();

    private static int calculateInitialCount() {
        System.out.println("calculate");
        return 7;
    }
}
~~~

Đây là một **class minh họa**, không chứa `main`. Tại **preparation**, trường `count` được chuẩn bị với giá trị mặc định kiểu `int` (`0`) theo mô hình JVM thông thường. Nhưng biểu thức `calculateInitialCount()` **chưa được gọi chỉ vì preparation**. Lời gọi `calculateInitialCount()` là công việc của **initialization**.

Các giá trị mặc định quen thuộc cho static field không thuộc nhóm constant-value đặc biệt:

| Kiểu | Giá trị mặc định khi chuẩn bị |
| --- | --- |
| `int`, `short`, `byte` | `0` |
| `long` | `0L` |
| `float`, `double` | `0.0` |
| `boolean` | `false` |
| `char` | `'\u0000'` |
| Reference | `null` |

**Ngoại lệ kỹ thuật cần biết:** với một trường `static final` có thuộc tính class-file `ConstantValue`, JVM xử lý giá trị hằng theo cơ chế riêng ở preparation/initialization tương ứng; không nên kết luận mọi `static final` luôn chỉ nhận `0` hoặc `null` tới tận lúc chạy static block. Ví dụ `static final int SIZE = 16;` là constant variable và có cơ chế compile-time constants khác với `static int x = compute();`.

Trong code bình thường, việc cố quan sát một class field từ bên ngoài trước khi class initialized **thường chính hành động đọc ấy lại kích hoạt initialization**. Vì thế đừng dự đoán chương trình phổ thông sẽ in `0` khi đọc `Metrics.count` lần đầu.

## 6. Chương trình: nhìn thấy initialization, không nhầm với preparation

Tạo tệp độc lập **`PreparationVsInitializationDemo.java`**:

~~~java
class MetricsStage {
    static int count = compute();

    static {
        System.out.println("MetricsStage.static block, count=" + count);
    }

    private static int compute() {
        System.out.println("MetricsStage.compute()");
        return 7;
    }
}

public class PreparationVsInitializationDemo {
    public static void main(String[] args) {
        System.out.println("before first active use");
        System.out.println("count=" + MetricsStage.count);
        System.out.println("again=" + MetricsStage.count);
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 PreparationVsInitializationDemo.java
java PreparationVsInitializationDemo
~~~

**Stdout chính xác:**

~~~text
before first active use
MetricsStage.compute()
MetricsStage.static block, count=7
count=7
again=7
~~~

Giải thích từng bước:

1. JVM có thể nạp/liên kết `MetricsStage` trước hoặc khi đến dòng đọc `MetricsStage.count`; stdout này **không chứng minh thời điểm nạp/liên kết**.
2. Dòng `count` là truy cập `static` field **không phải constant variable**, nên cần initialization của `MetricsStage`.
3. Trong quá trình initialization, biểu thức `compute()` chạy trước, in thông báo rồi trả 7.
4. Static block xuất hiện **sau khai báo `count`**, nên nó đọc được giá trị đã gán là 7.
5. Lời gọi đọc tiếp theo không chạy lại toàn bộ static initializer; chỉ in `again=7`.

Phân biệt **mặc định tại preparation** và **giá trị đã có sau initialization** giúp tránh lỗi suy luận: “vì preparation khởi tạo số về 0 nên lần đọc static đầu tiên sẽ thấy 0”. Đối với ví dụ này, kết luận đó là sai.

## 7. Resolution: vì sao liên kết có thể chưa giải quyết mọi tên?

Trong class file, nhiều tham chiếu đến kiểu, trường và phương thức ban đầu xuất hiện dưới dạng **symbolic references** trong *run-time constant pool*. Resolution là bước xác định một symbolic reference thực sự chỉ tới class, field, method hoặc thực thể runtime nào.

Ví dụ source:

~~~java
String text = Integer.toString(42);
~~~

Là một **câu lệnh minh họa**. Bytecode chứa thông tin để tham chiếu method thích hợp; JVM có thể cần giải quyết tham chiếu này khi thực hiện hoặc trước đó, theo chiến lược implementation và quy tắc [JVMS §5.4.3](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.4.3).

Những điểm nên nhớ:

- **Loading một class không đồng nghĩa nạp mọi kiểu mà class nhắc tới.** Verification/resolution có thể dẫn tới loading thêm các kiểu khác, tùy nhu cầu.
- **Resolution không luôn diễn ra toàn bộ trước initialization.** JVM được phép lựa chọn nhiều thời điểm trong giới hạn quy định.
- Lỗi như không tìm được method đúng binary signature có thể xuất hiện **khi sử dụng liên kết đó**, chứ không nhất thiết ngay tại startup.
- Resolution và initialization là hai công việc khác: phân giải một tên thành method không đồng nghĩa chạy static initializer của mọi class liên quan.

Nếu đổi phiên bản một thư viện sau khi compile mà chữ ký method đã thay đổi, code có thể compile thành công từ trước nhưng thất bại tại runtime với một dạng `LinkageError`. Khi xử lý tình huống này, cần kiểm tra classpath/module path và binary compatibility, **không nhầm với lỗi trong constructor**.

## 8. Khi nào class hoặc interface cần được initialized?

Theo [JLS 17 §12.4.1](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.4.1), các tình huống quan trọng gồm:

- Tạo **instance** của class bằng một biểu thức tạo object phù hợp.
- Gọi **static method thực sự được khai báo** bởi class.
- Gán một **static field** được khai báo bởi class/interface.
- Đọc một **static field không phải constant variable**.
- Một số thao tác reflection được đặc tả yêu cầu initialization.
- JVM cần initialization của entry class khi bắt đầu thực thi ứng dụng; class cha và những superinterface có default methods có thể liên quan đến trình tự này.

Các trường hợp **thường không tự kích hoạt initialization của kiểu thành phần**:

- Chỉ viết một khai báo biến `SomeType ref;` hoặc sử dụng tên kiểu trong chú giải source.
- Lấy class literal `SomeType.class`.
- Tạo một **mảng tham chiếu** kiểu `new SomeType[10]` mà chưa tạo instance `SomeType`.
- Đọc một **compile-time constant variable** kiểu primitive/`String` theo điều kiện JLS, vì constant có thể được inline.
- Yêu cầu lấy đối tượng `Class` qua `Class.forName(name, false, loader)`.

Không đánh đồng **referenced by source** với **actively used at runtime**. Một kiểu xuất hiện nhiều lần trong source chưa bảo đảm static initializer của nó đã chạy.

## 9. Chương trình: `Class.forName` có và không có initialization

Tạo tệp **`LoadWithoutInitializeDemo.java`**:

~~~java
class DeferredService {
    static {
        System.out.println("DeferredService initialized");
    }

    static int version = 42;
}

public class LoadWithoutInitializeDemo {
    public static void main(String[] args) throws Exception {
        ClassLoader loader =
                LoadWithoutInitializeDemo.class.getClassLoader();

        System.out.println("before");
        Class<?> metadata =
                Class.forName("DeferredService", false, loader);
        System.out.println("class=" + metadata.getSimpleName());
        System.out.println("after false");

        Class.forName("DeferredService");
        System.out.println("after true");
        System.out.println("version=" + DeferredService.version);
    }
}
~~~

Lệnh:

~~~bash
javac -encoding UTF-8 LoadWithoutInitializeDemo.java
java LoadWithoutInitializeDemo
~~~

**Stdout:**

~~~text
before
class=DeferredService
after false
DeferredService initialized
after true
version=42
~~~

### Các dòng này chứng minh điều gì?

- `Class.forName("DeferredService", false, loader)` trả `Class<?> ` cho `DeferredService` **mà không yêu cầu chạy static initializer**.
- `metadata.getSimpleName()` đọc thông tin về tên kiểu; trong ví dụ không làm chạy static block.
- `Class.forName("DeferredService")` yêu cầu class initialized. Vì vậy static block in `DeferredService initialized` **trước** `after true`.
- Lần đọc `DeferredService.version` sau đó không khởi tạo class lần thứ hai.

Nếu gọi `Class.forName("DeferredService")` ngay từ đầu, static block có thể được chạy ngay tại lời gọi đó. Ngược lại, `ClassLoader.loadClass("DeferredService")` là thao tác yêu cầu loading và **không tự buộc initialization** của kiểu chỉ vì tên method chứa chữ “load”.

**Giới hạn kết luận:** `false` nghĩa là **không khởi tạo**, chứ không cam kết JVM tuyệt đối không thực hiện bất kỳ linking/verification nào. Đừng dùng cùng một log dòng `static` để suy ra mọi giai đoạn nội bộ.

## 10. Chương trình: class literal và array không tự chạy static block

Tạo tệp **`ClassLiteralAndArrayDemo.java`**:

~~~java
class Widget {
    static {
        System.out.println("Widget initialized");
    }

    Widget() {
        System.out.println("Widget constructed");
    }
}

public class ClassLiteralAndArrayDemo {
    public static void main(String[] args) {
        System.out.println("start");

        Widget[] widgets = new Widget[2];
        System.out.println("array length=" + widgets.length);

        Class<Widget> type = Widget.class;
        System.out.println("class=" + type.getSimpleName());

        System.out.println("before new");
        Widget actual = new Widget();
        System.out.println("done");
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 ClassLiteralAndArrayDemo.java
java ClassLiteralAndArrayDemo
~~~

**Stdout:**

~~~text
start
array length=2
class=Widget
before new
Widget initialized
Widget constructed
done
~~~

Giải thích:

- `new Widget[2]` tạo **array object**, chứa hai phần tử tham chiếu ban đầu là `null`; nó **không gọi constructor `Widget()` hai lần**.
- `Widget.class` cho phép lấy `Class` token và không tự kích hoạt initialization của `Widget`.
- Đến `new Widget()`, JVM cần `Widget` initialized trước khi thực thi constructor; static block in một lần, rồi constructor mới in.
- Biến `actual` giữ tham chiếu đến instance được tạo; việc có hoặc không đọc lại nó không ảnh hưởng lý do static block chạy.

Trong một tệp lớn, việc nhìn thấy `Widget.class` có thể khiến compiler/JVM **đã biết về kiểu** trước khi tạo instance. Nhưng điều cần nhớ là **không đồng nghĩa static initialization xảy ra lúc lấy class literal**.

## 11. Hằng số compile-time không nhất thiết khởi tạo class chứa nó

Một trường `static final` không tự động là *constant variable*. Theo JLS, constant variable là trường hoặc biến `final` kiểu nguyên thủy hoặc `String`, được khởi tạo bằng một **constant expression** đáp ứng điều kiện.

So sánh:

~~~java
static final int LITERAL = 17;
static final String LABEL = "OK";
static final int COMPUTED = Integer.parseInt("18");
~~~

`LITERAL` và `LABEL` là các constant variables; `COMPUTED` **không** phải vì gọi method `Integer.parseInt` không phải constant expression.

Tạo tệp **`ConstantInitializationDemo.java`**:

~~~java
class Tokens {
    static final int LITERAL = 17;
    static final String LABEL = "OK";
    static final int COMPUTED = Integer.parseInt("18");

    static {
        System.out.println("Tokens static block");
    }
}

public class ConstantInitializationDemo {
    public static void main(String[] args) {
        System.out.println("before");
        System.out.println("literal=" + Tokens.LITERAL);
        System.out.println("label=" + Tokens.LABEL);
        System.out.println("computed=" + Tokens.COMPUTED);
        System.out.println("after=" + Tokens.COMPUTED);
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 ConstantInitializationDemo.java
java ConstantInitializationDemo
~~~

**Stdout:**

~~~text
before
literal=17
label=OK
Tokens static block
computed=18
after=18
~~~

Hai dòng đọc `Tokens.LITERAL` và `Tokens.LABEL` không khiến `Tokens` phải initialized. Tới dòng đọc `Tokens.COMPUTED`, JVM thực hiện initialization của `Tokens`, chạy phép `Integer.parseInt("18")` và static block. Lần đọc sau chỉ lấy kết quả đã có.

### Vì sao điều này quan trọng trong thực tế?

- Việc tham chiếu tới compile-time constant có thể được **compiler thay bằng giá trị trực tiếp** trong bytecode của client.
- Nếu thay đổi một public constant kiểu này trong thư viện mà không biên dịch lại các client, mã client cũ có thể tiếp tục dùng giá trị được inline.
- Một `static final int` gán trong **static block** không phải constant variable chỉ vì nó mang modifier `final`.
- Một `static final List<String>` dù tham chiếu không đổi cũng **không** là constant variable theo nghĩa primitive/`String` constant expression.

Vì vậy câu nói “hễ đọc một static field thì class sẽ initialized” **thiếu điều kiện**: phải xét xem field **có phải constant variable** hay không.

## 12. Thứ tự static initialization trong một class

Trong một class, static field initializers và static initializer blocks được thực thi theo **thứ tự xuất hiện trong source**, sau các bước và điều kiện initialization thích hợp.

Tạo tệp **`StaticTextualOrderDemo.java`**:

~~~java
class Ordered {
    static int first = announce("first field", 1);

    static {
        System.out.println("first block");
    }

    static int second = announce("second field", 2);

    static {
        System.out.println("second block");
    }

    private static int announce(String label, int value) {
        System.out.println(label);
        return value;
    }

    Ordered() {
        System.out.println("constructor");
    }
}

public class StaticTextualOrderDemo {
    public static void main(String[] args) {
        System.out.println("before");
        new Ordered();
        new Ordered();
        System.out.println("fields=" + Ordered.first
                + "," + Ordered.second);
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 StaticTextualOrderDemo.java
java StaticTextualOrderDemo
~~~

**Stdout:**

~~~text
before
first field
first block
second field
second block
constructor
constructor
fields=1,2
~~~

Giải thích:

1. Static field `first` được gán trong giai đoạn initialization, in `first field`.
2. Static block đầu tiên chạy, in `first block`.
3. `second` được tính tiếp, in `second field`.
4. Static block thứ hai chạy, in `second block`.
5. Constructor instance chạy cho object thứ nhất rồi object thứ hai, nên in `constructor` hai lần.
6. Static initializers **không lặp lại mỗi khi gọi `new Ordered()`**.

Lưu ý code source có thể tham chiếu một static field nằm phía sau trong những ngữ cảnh được Java cho phép, nhưng còn chịu quy tắc **illegal forward reference**; không nên thiết kế logic phụ thuộc các field chưa gán xong để cố đọc giá trị mặc định một cách khó hiểu.

## 13. Thứ tự giữa superclass và subclass

Khi JVM cần khởi tạo một class con, nó bảo đảm **superclass chưa được khởi tạo** sẽ được khởi tạo trước. Quy tắc này liên quan **class initialization** của `static` fields/blocks, không đồng nghĩa mọi constructor đã chạy.

~~~java
class Base {
    static { System.out.println("Base static"); }
    Base() { System.out.println("Base constructor"); }
}
class Derived extends Base {
    static { System.out.println("Derived static"); }
    Derived() { System.out.println("Derived constructor"); }
}
~~~

Nếu đây là các khai báo độc lập và caller lần đầu gọi `new Derived()`, bốn dòng lần lượt là `Base static`, `Derived static`, `Base constructor` và `Derived constructor`. Với lần `new Derived()` tiếp theo trong cùng runtime identity đã khởi tạo thành công, **chỉ hai constructor bodies** chạy lại. Đây là **snippet** để phân biệt hai quy tắc; chương trình trace hoàn chỉnh về thứ tự cha–con thuộc bài “Khởi tạo lớp cha trước lớp con”.

Cần phân biệt thêm: truy cập một static field được **khai báo ở Base** bằng cách viết `Derived.FIELD` không nhất thiết buộc Derived initialized; hãy xét nơi khai báo member thực sự. Một subclass instance không phải hai objects Base/Derived riêng biệt: constructor Base khởi tạo phần kế thừa của **cùng một object Derived**.

## 14. Truy cập inherited static field có thể không khởi tạo subclass

Một khác biệt dễ bỏ sót: nếu field static **thực sự được khai báo ở superclass**, truy cập field ấy bằng tên subclass không tự buộc subclass initialized.

Ví dụ:

~~~java
class BaseConfig {
    static int PORT = 8080;

    static {
        System.out.println("BaseConfig initialized");
    }
}

class AppConfig extends BaseConfig {
    static {
        System.out.println("AppConfig initialized");
    }
}
~~~

Nếu một `main` riêng viết:

~~~java
System.out.println(AppConfig.PORT);
~~~

thì field `PORT` thực tế thuộc `BaseConfig`. Theo JLS, kích hoạt initialization liên quan tới **lớp khai báo field** là `BaseConfig`; chỉ dùng cú pháp `AppConfig.PORT` không bắt `AppConfig` static block chạy.

Người đọc code có thể bị đánh lừa bởi tên đứng bên trái dấu chấm. Để diễn đạt nguồn đúng, thường nên viết `BaseConfig.PORT` khi có thể. Không nên nhầm đây là “lazy initialization của superclass”; superclass có thể đã initialized, còn subclass đơn giản **chưa có lý do cần initialized**.

Với phương thức static, Java cũng xét method **được khai báo bởi kiểu nào**, không chỉ dựa vào kiểu được viết trước dấu chấm. Hãy đọc quy tắc khởi tạo theo member thực sự được khai báo và cơ chế phân giải tên.

## 15. Interface initialization không luôn kéo theo superinterface

Interface có các field ngầm định `public static final`, nhưng **không phải mọi field đều là compile-time constants**. Một field được tính qua lời gọi method có thể kích hoạt initialization của interface khi được đọc.

Tạo tệp **`InterfaceInitializationDemo.java`**:

~~~java
final class InitTrace {
    private InitTrace() {
    }

    static int record(String name) {
        System.out.println(name + " initialized");
        return 1;
    }
}

interface RootRule {
    int ROOT = InitTrace.record("RootRule");
}

interface ChildRule extends RootRule {
    int CHILD = InitTrace.record("ChildRule");
}

public class InterfaceInitializationDemo {
    public static void main(String[] args) {
        System.out.println("before");
        System.out.println("child=" + ChildRule.CHILD);
        System.out.println("root=" + RootRule.ROOT);
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 InterfaceInitializationDemo.java
java InterfaceInitializationDemo
~~~

**Stdout:**

~~~text
before
ChildRule initialized
child=1
RootRule initialized
root=1
~~~

Tại sao `ChildRule` chạy trước `RootRule`?

- `CHILD` là một static final field nhưng **không phải constant variable**, vì initializer gọi `InitTrace.record(...)`. Đọc nó yêu cầu initialization của `ChildRule`.
- **Initialization của interface không tự bắt buộc initialization của các superinterfaces**.
- Khi đọc `RootRule.ROOT` sau đó, `RootRule` mới phải initialized theo nhu cầu của chính nó.

**Ngoại lệ khi class triển khai interface:** khi khởi tạo một **class**, Java còn phải khởi tạo những superinterfaces liên quan có **default methods** theo quy tắc cụ thể trong JLS 17. Không được diễn giải ví dụ trên thành “interface không bao giờ được initialized trước class thực thi nó”. Đây là một điểm tinh tế của thứ tự khởi tạo.

Để tránh nhầm, ưu tiên phân tích một ví dụ cụ thể: field nào được khai báo ở đâu, có phải constant variable không, class hay interface nào có default methods và hành động nào đang yêu cầu initialization.

## 16. Những thao tác không tự chạy constructor instance

Trong vòng đời JVM có hai khái niệm khác nhau:

| Hoạt động | Có thể thực thi static initialization? | Có tạo object instance của class đó không? |
| --- | --- | --- |
| Loading class | Không nhất thiết | Không |
| Linking class | Không phải chạy constructor | Không |
| Initialization class | Chạy static code theo điều kiện | Không nhất thiết |
| `SomeClass.class` | Thường không làm initialized class | Không |
| `new SomeClass[3]` | Không làm initialized component class chỉ vì tạo mảng | Chỉ tạo array object |
| `Class.forName(name)` | Có, yêu cầu initialized | Không tạo instance class đích |
| `new SomeClass()` | Có nếu class chưa initialized | Có, nếu phép tạo thành công |
| Đọc static nonconstant field | Có nếu field yêu cầu initialization | Không |

Constructor instance chỉ chạy khi có quá trình **tạo instance** thích hợp. Một class có thể đã initialized từ việc gọi static method hoặc đọc nonconstant static field, trong khi **chưa có object nào** của class được tạo.

Ngược lại, tạo instance đòi class initialized trước, nhưng sau khi class initialized thành công, constructor tiếp tục có thể chạy nhiều lần để tạo nhiều object. Do đó **static code một lần theo class lifecycle**, còn **constructor theo từng instance** là hai tầng tách biệt.

## 17. Khi class initialization thất bại: hệ quả không giống constructor lỗi

Static initialization có thể ném exception. Một lỗi không được xử lý trong giai đoạn này có thể khiến **class runtime bị đánh dấu trạng thái khởi tạo lỗi**. Trong cùng class loader, yêu cầu initialization về sau có thể thất bại thay vì được “thử lại như lần đầu”.

Tạo tệp **`InitializationFailureDemo.java`**:

~~~java
class BrokenService {
    static int port = readConfiguration();

    private static int readConfiguration() {
        System.out.println("BrokenService initializing");
        throw new IllegalStateException("bad config");
    }
}

public class InitializationFailureDemo {
    static void use() {
        System.out.println(BrokenService.port);
    }

    public static void main(String[] args) {
        try {
            use();
        } catch (ExceptionInInitializerError ex) {
            System.out.println("first="
                    + ex.getClass().getSimpleName());
        }

        try {
            use();
        } catch (NoClassDefFoundError ex) {
            System.out.println("second="
                    + ex.getClass().getSimpleName());
        }
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 InitializationFailureDemo.java
java InitializationFailureDemo
~~~

**Stdout:**

~~~text
BrokenService initializing
first=ExceptionInInitializerError
second=NoClassDefFoundError
~~~

Giải thích:

1. Lần đầu đọc `BrokenService.port` yêu cầu class initialized.
2. `readConfiguration()` in thông báo rồi ném `IllegalStateException`.
3. JVM xử lý sự thất bại này theo cơ chế class initialization; trong tình huống ném exception không phải `Error` này, caller quan sát `ExceptionInInitializerError`.
4. Class đã ở trạng thái khởi tạo lỗi. Lần yêu cầu dùng tiếp không khởi động lại initializer; trong ví dụ, caller bắt `NoClassDefFoundError`.

**Phân biệt với lỗi tạo instance:** nếu một constructor bình thường ném `IllegalArgumentException` khi validate dữ liệu đầu vào, điều đó không nhất thiết đánh dấu class ở trạng thái initialization thất bại. Caller có thể sửa input và tạo instance khác. Static initialization là phần **vòng đời của class**, nên lỗi tại đây thường nghiêm trọng hơn và cần thiết kế cấu hình phù hợp.

## 18. `ClassNotFoundException`, `NoClassDefFoundError` và `ExceptionInInitializerError`

Ba tên này thường bị nhầm:

| Loại lỗi | Ví dụ ý nghĩa | Nơi thường thấy |
| --- | --- | --- |
| `ClassNotFoundException` | API tìm class theo tên không tìm thấy định nghĩa được yêu cầu | `Class.forName("...")`, `ClassLoader.loadClass` |
| `NoClassDefFoundError` | JVM không thể dùng một class definition cần thiết lúc runtime; cũng có thể xảy ra khi class ở trạng thái khởi tạo lỗi | Thực thi mã có tham chiếu class thiếu/khởi tạo lỗi |
| `ExceptionInInitializerError` | Exception phát sinh trong initialization của class được JVM bọc thành lỗi tương ứng | Static initializer hoặc static field initializer ném lỗi |

Một `NoClassDefFoundError` không chứng minh chắc chắn file `.class` chưa tồn tại: nó **cũng có thể là hệ quả của lần initialization trước thất bại**, như ví dụ vừa chạy.

Một `ClassNotFoundException` thường là checked exception phát sinh từ API theo tên. Ngược lại, `NoClassDefFoundError` và `ExceptionInInitializerError` thuộc hệ `Error`. Trong ứng dụng, đừng dùng `catch (Error)` chung để bỏ qua các lỗi này rồi tiếp tục như không có chuyện gì; hãy điều tra classpath, binary compatibility, lỗi static initializer và quá trình startup.

## 19. Class initialization khi nhiều thread cùng kích hoạt

JVM phải phối hợp khi nhiều thread đồng thời yêu cầu initialization của cùng một class runtime. [JLS §12.4.2](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.4.2) mô tả trạng thái và cơ chế đồng bộ hóa để một lần initialization hợp lệ không bị chạy song song như hai chương trình độc lập.

Ví dụ, nếu hai luồng đồng thời gọi một static method của `Settings` lần đầu:

~~~java
Settings.getInstance();
~~~

đây là lời gọi **minh họa**, không có định nghĩa `Settings` độc lập ở đây. JVM bảo đảm quy trình class initialization được quản lý theo quy tắc riêng, chứ không để hai thread tự chạy hai bản static initializer của cùng class đồng thời.

Nhưng **class initialization được phối hợp an toàn không đồng nghĩa mọi static field mutable đều thread-safe sau đó**. Ví dụ:

~~~java
class SharedCounter {
    static int value;

    static void increment() {
        value++;
    }
}
~~~

Sau initialization, nếu nhiều thread cùng gọi `increment()`, phép `value++` vẫn là chuỗi đọc–tính–ghi không nguyên tử. Cần `synchronized`, atomic hoặc cơ chế tương ứng nếu yêu cầu tính nhất quán giữa luồng.

Một mẫu hay gặp là *initialization-on-demand holder idiom*: class lồng tĩnh chứa một `static final` instance được khởi tạo theo class initialization khi class holder được chủ động dùng lần đầu. Sự đơn giản của mẫu đến từ bảo đảm class initialization của JVM, không phải vì mọi static method tự nhiên synchronized.

## 20. Mẫu holder: dùng initialization theo nhu cầu

Tạo tệp **`HolderInitializationDemo.java`**:

~~~java
final class ConfigService {
    private ConfigService() {
        System.out.println("ConfigService constructed");
    }

    static ConfigService instance() {
        System.out.println("request");
        return Holder.INSTANCE;
    }

    private static class Holder {
        static final ConfigService INSTANCE = new ConfigService();

        static {
            System.out.println("Holder initialized");
        }
    }
}

public class HolderInitializationDemo {
    public static void main(String[] args) {
        System.out.println("begin");
        ConfigService first = ConfigService.instance();
        ConfigService second = ConfigService.instance();
        System.out.println("same=" + (first == second));
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 HolderInitializationDemo.java
java HolderInitializationDemo
~~~

**Stdout:**

~~~text
begin
request
ConfigService constructed
Holder initialized
request
same=true
~~~

Mạch thực thi:

1. `ConfigService.instance()` là static method của `ConfigService`, nên class ngoài được initialized nếu cần. Nhưng class `Holder` **chưa bắt buộc initialized chỉ vì nằm lồng bên trong**.
2. Khi method truy cập `Holder.INSTANCE` lần đầu, JVM cần initialization của class `Holder`.
3. Static field initializer tạo một `ConfigService` (constructor in `ConfigService constructed`), sau đó static block của Holder in `Holder initialized`.
4. Lần gọi `instance()` thứ hai chỉ đọc `Holder.INSTANCE` đã có, không tạo thêm object. Hai tham chiếu so bằng `==` vì trỏ cùng instance.

Ví dụ này giới thiệu **lợi ích của initialization có kiểm soát theo nhu cầu**. Trong ứng dụng thực tế, nếu một singleton có trạng thái mutable thì các phương thức làm việc với trạng thái đó vẫn phải tuân quy tắc thread safety riêng.

## 21. Công cụ quan sát: `javap` và log class loading

Để học sâu, có thể biên dịch một ví dụ rồi xem bytecode/class file:

~~~bash
javac -encoding UTF-8 StaticTextualOrderDemo.java
javap -c -p Ordered
javap -v -p Ordered
~~~

`javap` cho phép quan sát các method và instruction. Với class có static field initializers/static initializer blocks, compiler có thể sinh phương thức đặc biệt tên **`<clinit>`** trong class file để thực hiện phần khởi tạo class. Không phải mọi class đều phải có `<clinit>`; một class chỉ có constant variables có thể không cần phần mã initialization tương ứng.

Khi đang dùng Java 17, JVM HotSpot/OpenJDK phổ biến có thể bật log class loading bằng tùy chọn như:

~~~bash
java -Xlog:class+load=info SuperclassInitializationDemo
~~~

Log thực tế gồm thông tin class loading của JVM/JDK và ứng dụng; **nội dung, thứ tự và số dòng phụ thuộc runtime**, nên bài không đưa stdout giả định cho lệnh này. Không nên ép mọi runtime Java đều có cùng định dạng log hoặc cấu hình diagnostic giống nhau.

Một phương pháp quan sát đáng tin hơn cho bài học:

1. Chạy chương trình **không bật log** để xác nhận stdout nghiệp vụ đã liệt kê.
2. Dùng `javap` để nhìn phương thức/bytecode liên quan static code.
3. Bật class loading log khi cần tìm class được nạp từ nguồn nào.
4. So sánh: class có thể xuất hiện trong **loading log** sớm hơn lúc static initializer in thông báo.

**Tránh nhầm log class loading với log initialization.** Một dòng “class loaded” không có nghĩa `<clinit>` đã hoàn tất; muốn biết điều đó phải xem hành vi và công cụ thích hợp.

## 22. Phân biệt một số thời điểm hay gặp

| Thao tác | Có yêu cầu loading/linking? | Có yêu cầu initialization của kiểu đích? |
| --- | --- | --- |
| JVM chạy `Main.main` | Phải chuẩn bị các kiểu cần thiết | `Main` cần initialized trước `main` |
| `Class.forName("T")` | Có cơ chế tìm/định nghĩa kiểu | Có theo API một tham số |
| `Class.forName("T", false, loader)` | Có thể nạp/liên kết để nhận `Class` | **Không** yêu cầu initialized |
| `loader.loadClass("T")` | Yêu cầu loading | Không tự yêu cầu initialized |
| `T.class` | JVM xử lý class literal | Không tự yêu cầu initialized |
| `new T[3]` | Tạo array class/object thích hợp | Không tự initialized component `T` |
| `new T()` | JVM phải sẵn sàng dùng `T` | Có, nếu chưa initialized |
| `T.staticMethod()` | Phân giải lời gọi | Có cho class thực sự khai báo method |
| `T.staticNonconstantField` | Phân giải field | Có cho kiểu khai báo field |
| `T.COMPILE_TIME_CONSTANT` | Có thể inline từ lúc compile | Không chỉ vì đọc constant variable |
| Truy cập field static inherited qua subclass | Phân giải tới field khai báo | Chỉ yêu cầu init kiểu **khai báo** field |
| Tạo instance thứ hai của class đã initialized | Có thể tái sử dụng trạng thái class | Không chạy lại static code |

Cột loading/linking là **mô tả nhu cầu kiểu**, không phải cam kết thời điểm thực thi từng substep trong JVM. Với resolution, không thể ghi “bắt buộc hoàn tất mọi tham chiếu liên quan” chỉ dựa trên một biểu thức Java.

## 23. Lỗi suy luận phổ biến

| Nhận định sai | Vì sao sai | Cách hiểu đúng |
| --- | --- | --- |
| “Class file đã load thì static block chạy rồi.” | Loading và initialization là hai giai đoạn | Chờ trigger initialization |
| “Linking chính là chạy static initializer.” | Linking chủ yếu verify/prepare/resolve | Static code chạy ở initialization |
| “Preparation gọi `static int x = compute();`.” | Preparation không chạy biểu thức source initializer tùy ý | `compute()` chạy khi class initialized |
| “Resolution luôn xong toàn bộ trước initialization.” | JVM có quyền trì hoãn resolution | Không gộp ba substep thành thứ tự cứng |
| “Hễ dùng tên kiểu là nó initialized.” | Nhiều thao tác chỉ là class literal, khai báo kiểu, mảng | Xem active-use triggers |
| “`new T[5]` gọi constructor `T` năm lần.” | Chỉ tạo array object có 5 phần tử reference | Cần `new T()` cho từng instance |
| “Đọc `static final` luôn kích hoạt init.” | Compile-time constant variables có ngoại lệ | Kiểm tra constant expression |
| “`Class.forName(name,false,...)` vẫn chạy static block.” | Tham số false yêu cầu không khởi tạo | Dùng true hoặc một active use khi cần |
| “`Class.forName(name)` tạo một object của class đó.” | API trả `Class` metadata và yêu cầu initialization | Không gọi constructor instance |
| “Subclass static block luôn chạy khi truy cập field inherited.” | Khởi tạo phụ thuộc kiểu thực sự khai báo field | Truy cập `Base.field` cho rõ |
| “Khi khởi tạo interface luôn init các superinterfaces.” | JLS không đặt quy tắc đó theo mặc định | Xét interface nào được active use |
| “Superclass constructor chạy trước static block của subclass?” | Lẫn class init với object construction | Class init theo inheritance trước instance constructor |
| “Class init lỗi, lần sau JVM tự chạy lại static block.” | Class có thể bị đánh dấu initialization erroneous | Sửa nguyên nhân và môi trường loader/runtime |
| “Static initialization an toàn nên mọi `static int++` cũng an toàn.” | Bảo đảm khởi tạo không làm phép tăng trở nên atomic | Dùng đồng bộ/atomic khi chia sẻ mutable state |
| “Cùng tên class ở hai loader luôn cùng static field.” | Runtime identity bao gồm defining loader | Có thể là hai class riêng và static state riêng |

Nếu thấy thứ tự output bất ngờ, hãy ghi lại **class khai báo field/method**, **dòng nào gây active use**, **thứ tự textual initializers** và **quan hệ superclass/interface**. Đó thường là đủ để giải thích mà không phải đoán JVM “load ngẫu nhiên”.

## 24. Hướng dẫn giải bài tập theo thứ tự khởi tạo

Khi bài cho một sơ đồ lớp và hỏi chương trình in gì, hãy làm tuần tự:

1. **Liệt kê những class/interface có static blocks hoặc nonconstant field initializers.**
2. **Xác định hành động active use đầu tiên** của từng kiểu: `new`, static method, nonconstant static field, reflection yêu cầu init.
3. **Bỏ qua các giả định sai**: class literal, mảng chỉ chứa reference và compile-time constants không tự yêu cầu component/class init.
4. **Kiểm tra superclass** trước khi thực thi static initializers của subclass; với interface và default methods dùng quy tắc JLS thích hợp.
5. Với một class đang initialized, **thực thi field initializers và static blocks theo thứ tự source**.
6. Đánh dấu class đó **đã initialized**; lần sử dụng tiếp không chạy lại static code.
7. Nếu có `new`, tiếp tục phân tích constructor chain, instance field initializers, superclass/subclass constructors cho **từng object**.
8. Nếu static initialization ném lỗi, xét trạng thái class erroneous và các lần dùng sau; đừng cố tiếp tục tính stdout như thể class vẫn initialized thành công.

Với yêu cầu chỉ hỏi **giai đoạn nạp/liên kết**, đừng dùng bản ghi static output để khẳng định thời điểm resolution chính xác: việc đó thuộc implementation và các quy tắc JVM rộng hơn.

## 25. Câu hỏi tự luyện

**Bài 1 — Phân biệt ba giai đoạn.** Hãy mô tả một câu cho loading, một câu cho linking, một câu cho initialization. Static block thuộc giai đoạn nào?

**Bài 2 — Preparation.** `static int count = compute();`. Có phải preparation gọi `compute()` để gán field không? Khi nào `compute()` có thể được thực thi?

**Bài 3 — Resolution.** Tại sao một `NoSuchMethodError` đôi khi chỉ phát sinh khi chạy đến lời gọi cụ thể, không phải ngay khi class đầu tiên được loaded?

**Bài 4 — Class literal.** Với class `X` có static block in tên lớp, `Class<?> t = X.class;` có nhất thiết in tên đó không?

**Bài 5 — Array.** `X[] values = new X[3];` có tạo ba object `X` và chạy constructor `X()` ba lần không?

**Bài 6 — Constants.** Cho `static final int A = 10;` và `static final int B = Integer.parseInt("10");`. Đọc `A` hoặc `B` khác nhau ra sao về khả năng kích hoạt initialization?

**Bài 7 — Superclass.** Trước lời gọi `new Child()` đầu tiên, cả `Parent` và `Child` chưa initialized. Những static initializers nào chạy trước? Constructor thuộc giai đoạn nào?

**Bài 8 — Inherited field.** Nếu `Parent` khai báo `static int PORT` và `Child extends Parent`, câu `System.out.println(Child.PORT)` có buộc static block của `Child` chạy không?

**Bài 9 — Interface.** Interface `ChildRule extends RootRule` và hai field được tính bằng method. Đọc `ChildRule.CHILD` có bắt `RootRule.ROOT` initialized ngay không?

**Bài 10 — Reflection.** `Class.forName("X",false,loader)` khác gì `Class.forName("X")` đối với initialization?

**Bài 11 — Failure.** Nếu lần initialization đầu của `Bad` ném một `IllegalStateException`, caller có thể thấy lỗi nào? Trong cùng loader, lần yêu cầu khởi tạo sau có phải luôn thử lại không?

**Bài 12 — Class loader.** Hai lớp cùng binary name do hai defining class loaders khác nhau tạo có chắc cùng static fields không?

**Bài 13 — Concurrency.** Tại sao sự phối hợp an toàn của class initialization không làm `static int count; count++;` an toàn khi nhiều thread cùng gọi?

**Bài 14 — Holder idiom.** Vì sao class ngoài có thể initialized mà static nested holder class vẫn chưa initialized? Sự kiện gì khiến holder tạo instance lần đầu?

### Đáp án tham khảo

1. Loading định nghĩa kiểu runtime; linking gồm verify/prepare/resolve; initialization chạy static field initializers và static blocks.
2. Không. Preparation chuẩn bị field với giá trị ban đầu phù hợp; `compute()` chạy khi initialized.
3. Resolution có thể bị trì hoãn; JVM không nhất thiết phân giải mọi symbolic reference khi loading.
4. Không. Class literal tự nó không bắt class `X` initialized.
5. Không. Nó tạo một array object chứa ba tham chiếu mặc định null, chưa có instance `X`.
6. `A` là constant variable có thể được inline và không trigger init; `B` không phải constant variable, đọc nó yêu cầu initialized class khai báo.
7. Static initializer của `Parent` trước `Child`; constructor instance chạy khi tạo object, sau khi class initialization cần thiết đã được hoàn tất.
8. Không chỉ vì biểu thức viết `Child.PORT`; field do `Parent` khai báo, nên yêu cầu init thuộc về `Parent`.
9. Không tự động. Initialization của interface không mặc định khởi tạo các superinterfaces.
10. Dạng ba tham số với `false` không yêu cầu initialization; dạng một tham số có yêu cầu.
11. Có thể thấy `ExceptionInInitializerError` ở lần đầu và `NoClassDefFoundError` ở lần sau; một class runtime ở trạng thái initialization lỗi không tự được thử lại như mới.
12. Không. Defining loader góp phần vào danh tính runtime của lớp; static states có thể độc lập.
13. Phối hợp initialization là cơ chế riêng; phép `count++` vẫn không atomic.
14. Bản thân việc khai báo/nằm lồng không buộc holder initialized; lần đọc active `Holder.INSTANCE` sẽ làm initialized holder và tạo object.

## 26. Nguồn tham khảo chính thức

- [JLS Java 17, §12.1 — Java Virtual Machine Startup](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.1): chuỗi khái niệm startup, load/link/initialize main class.
- [JLS Java 17, §12.2 — Loading of Classes and Interfaces](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.2): loading và class loaders.
- [JLS Java 17, §12.3 — Linking of Classes and Interfaces](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.3): verification, preparation, resolution.
- [JLS Java 17, §12.4.1 — When Initialization Occurs](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.4.1): điều kiện active use, compile-time constants và inheritance.
- [JLS Java 17, §12.4.2 — Detailed Initialization Procedure](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.4.2): thứ tự, synchronization và lỗi initialization.
- [JVMS Java 17, §5.3 — Creation and Loading](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.3): tạo và loading class/interface, identity theo loader.
- [JVMS Java 17, §5.4 — Linking](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.4): verification, preparation và resolution ở tầng JVM.
- [JVMS Java 17, §5.5 — Initialization](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.5): cơ chế initialization trong JVM.
- [Java SE 17 API — Class.forName](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html#forName(java.lang.String,boolean,java.lang.ClassLoader)): phân biệt nhận Class object với yêu cầu initialized.
- [Java SE 17 API — ClassLoader.loadClass](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html#loadClass(java.lang.String)): yêu cầu nạp class.
- [Java SE 17 — javap](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javap.html): công cụ xem class file/bytecode.

**Kết luận:** Loading giúp JVM **có định nghĩa runtime của kiểu**; linking **kiểm tra, chuẩn bị và phân giải các liên kết cần thiết**; initialization mới là giai đoạn **chạy static initializers**. Ba bước không phải ba từ đồng nghĩa. Chỉ những hành động được Java quy định mới buộc class/interface initialized; class literal, mảng chỉ chứa tham chiếu và compile-time constants là các trường hợp rất dễ nhầm. Sau khi class initialized thành công, các static initializer không chạy lại mỗi lần tạo object, còn constructor vẫn chạy cho mỗi instance.
