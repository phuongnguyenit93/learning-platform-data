# Class loading, linking, initialization và class loader

## 1. Một class Java bắt đầu hoạt động như thế nào?

Khi chạy một ứng dụng Java 27, JVM không nhất thiết nạp và khởi tạo tất cả các class được nhắc đến trong mã nguồn ngay lập tức. Quá trình đưa một kiểu vào trạng thái có thể sử dụng gồm các công đoạn có hợp đồng khác nhau:

1. **Loading — nạp class:** tìm biểu diễn nhị phân và tạo đối tượng đại diện cho class hoặc interface trong JVM.
2. **Linking — liên kết:** xác minh biểu diễn nhị phân, chuẩn bị dữ liệu cấp class và phân giải các tham chiếu ký hiệu khi cần.
3. **Initialization — khởi tạo class:** chạy các bộ khởi tạo của biến static và các khối **static { ... }**, theo thứ tự và quy tắc ngôn ngữ.
4. **Execution — sử dụng:** tạo đối tượng, gọi phương thức và thực thi logic nghiệp vụ sau những bước cần thiết.

**Class loader** là thành phần xác định cách tìm hoặc tạo định nghĩa class; nó cũng góp phần quyết định **danh tính runtime của class**. Điều này ảnh hưởng trực tiếp đến plugin, application server, dependency isolation, reflection, JPMS, lỗi liên kết và khả năng thu hồi metadata của class.

~~~mermaid
flowchart TD
    S["Nhu cầu sử dụng một class"] --> L["Loading: tìm bytes, tạo Class"]
    L --> K["Linking"]
    K --> V["Verification: kiểm tra class file / bytecode"]
    V --> P["Preparation: chuẩn bị static fields với giá trị mặc định"]
    P --> R["Resolution: liên kết symbolic references khi cần"]
    R --> I["Initialization: <clinit> nếu có và được kích hoạt"]
    I --> E["Object creation / method invocation"]
    N["ClassLoader và module environment"] --> L
    R -.->|"Có thể phân giải muộn, ngay cả sau init"| E
~~~

Sơ đồ nhằm diễn giải, **không phải lịch thực thi cứng**: JVM được phép phân giải một số tham chiếu theo kiểu *lazy* và vẫn phải tuân thủ quy tắc thời điểm báo lỗi. Điều bắt buộc là class được nạp trước khi liên kết; **verification và preparation phải hoàn tất trước initialization**.

Nội dung thuộc chương **JVM, bộ nhớ và thu gom rác**, phạm vi **Java 27 và các kiến thức liên quan**. Các API và công cụ minh họa đều còn áp dụng trong Java 27; không dựa vào extension mechanism, finalization hay cơ chế nạp class đã lỗi thời.

## 2. Class, object và class loader là những thứ khác nhau

Ba khái niệm dễ bị trộn lẫn:

| Khái niệm | Diễn giải | Ví dụ |
|---|---|---|
| **Class file** | Biểu diễn nhị phân, thường có đuôi **.class**, được tạo bởi compiler hoặc công cụ sinh bytecode | **Order.class** trên đĩa |
| **Class<?>** | Đối tượng **java.lang.Class** đại diện cho một kiểu tại runtime | **Order.class** trong mã Java |
| **ClassLoader** | Đối tượng/tác nhân định nghĩa hoặc ủy quyền nạp class | Application class loader |
| **Instance** | Đối tượng được tạo từ một class cụ thể | **new Order(...)** |
| **Class metadata** | Thông tin runtime cần cho việc thực thi class, method, constant pool... | Nhiều cấu trúc do JVM quản lý |

Một class có thể được **nạp** trước khi một instance đầu tiên được tạo. Ngược lại, khi tạo instance, class phải được chuẩn bị và khởi tạo theo quy tắc cần thiết.

~~~java
record Order(String id) {}

Class<Order> type = Order.class; // Lấy Class object
Order instance = new Order("O-1"); // Tạo instance

System.out.println(type == instance.getClass()); // true
~~~

Đối với **record**, **enum**, interface, annotation interface và array, JVM cũng có các Class objects tương ứng. Không nên hiểu ClassLoader chỉ dành cho các class thông thường.

## 3. Loading: tìm biểu diễn nhị phân và tạo kiểu runtime

**Loading** bắt đầu từ một tên kiểu và một class loader. Nó có thể bao gồm đọc bytes từ classpath/module path/JAR, từ nguồn do ứng dụng quản lý hoặc do cơ chế runtime cung cấp.

Tùy cách triển khai, một class loader có thể:

- Tìm class từ nơi được cấu hình.
- Ủy quyền việc tìm kiếm cho parent loader.
- Kiểm tra class đã được nạp chưa.
- Chuyển class file bytes hợp lệ thành định nghĩa thông qua API phù hợp.
- Trả **Class<?>** đại diện cho định nghĩa đã tồn tại.

**Một class được nạp không có nghĩa mọi static initializer của nó đã chạy.** Đó là lý do một framework có thể tìm metadata trước khi thực sự khởi tạo class.

Không tự suy đoán cách một loader đọc dữ liệu: với named modules, lớp có thể xuất phát từ module image hoặc module layer; với plugin, lớp có thể từ JAR. Không phải mọi class đều được ánh xạ thành một file trên filesystem thông thường.

## 4. Binary name và tên class ở runtime

Với class top-level, tên nhị phân thường có dạng **package.Type**. Với nested class, biểu diễn nhị phân thường chứa ký tự **$**:

~~~java
public class NameDemo {
    static class Nested {}

    public static void main(String[] args) {
        System.out.println(Nested.class.getName());
        // NameDemo$Nested

        System.out.println(Nested.class.getCanonicalName());
        // NameDemo.Nested
    }
}
~~~

**Class.forName(String)** và **ClassLoader.loadClass(String)** dùng tên theo hợp đồng API của chúng; đừng tự thay dấu **$** bằng dấu **.** khi muốn nạp nested class qua tên nhị phân.

Class file có **binary name** phải nhất quán với tên loader đang định nghĩa; việc tùy tiện thay bytes hoặc giả dạng tên một class có thể dẫn đến **NoClassDefFoundError**, **ClassFormatError**, **LinkageError** hoặc lỗi xác minh khác.

Đối với array, tên theo **Class.getName()** có cú pháp đặc biệt như **[Ljava.lang.String;** hoặc **[I**. Nếu chỉ cần class literal, dùng **String[].class** hoặc **int[].class** thay vì tự tạo các tên chuỗi.

## 5. Linking: verification, preparation, resolution

Quy trình **linking** không đồng nghĩa chỉ kiểm tra bytecode. Nó bao gồm ba hoạt động có mục đích riêng:

| Giai đoạn | Vai trò | Lưu ý |
|---|---|---|
| **Verification** | Kiểm tra định dạng/quan hệ kiểu và các ràng buộc cấu trúc của class file và bytecode | Không nên chạy bytes không tin cậy chỉ vì verification đã thành công |
| **Preparation** | Chuẩn bị các trường **static** với **giá trị mặc định** và các điều kiện ràng buộc khi liên kết | Chưa chạy những biểu thức gán static thông thường |
| **Resolution** | Chuyển tham chiếu ký hiệu đến class, field, method và các thành phần khác thành liên kết runtime | Không bắt buộc hoàn thành tất cả cùng lúc |

Đặc tả JVM cho phép lựa chọn cách giải quyết tham chiếu linh hoạt. Vì vậy, một lỗi tham chiếu method có thể chỉ xuất hiện khi đường mã thực sự sử dụng method đó, không nhất thiết ở lần đầu nạp class.

**Không xem sơ đồ “Load → Verify → Prepare → Resolve toàn bộ → Initialize” như một thứ tự tuyệt đối cho mọi tham chiếu.** JVM phải giữ các bất biến của đặc tả, nhưng resolution có thể tiếp tục sau initialization trong những trường hợp cho phép.

## 6. Verification: bytecode phải hợp lệ

Verification giúp JVM bảo đảm rằng biểu diễn class không vi phạm các quy tắc định dạng và kiểu cần thiết để thực thi.

Những trường hợp lỗi liên quan:

- Class file bị hỏng hoặc sai cấu trúc → có thể gặp **ClassFormatError**.
- Bytecode vi phạm quy tắc xác minh → có thể gặp **VerifyError**.
- Class file được biên dịch cho phiên bản class-file mới hơn runtime có thể đọc → **UnsupportedClassVersionError**.
- Phân cấp class/interface không nhất quán hoặc thay đổi không tương thích → các biến thể của **LinkageError**.

Ví dụ điển hình: build bằng JDK 27 rồi chạy trên runtime cũ không hỗ trợ class-file version tương ứng. Điều này khác với **ClassNotFoundException**, vốn thường cho biết class không được tìm thấy theo cơ chế nạp được yêu cầu.

**Verification không phải sandbox bảo mật để thực thi bytecode tùy ý từ bên không tin cậy.** Nếu một plugin có quyền của process, mã plugin vẫn có thể đọc/ghi file hoặc gọi mạng theo quyền hệ điều hành và cơ chế ứng dụng.

## 7. Preparation: static fields nhận giá trị mặc định

Trong preparation, JVM chuẩn bị các trường cấp class với giá trị mặc định theo kiểu. Ví dụ:

~~~java
final class Settings {
    static int retryCount = 3;
    static boolean enabled = true;
    static String endpoint = "https://example.com";

    static {
        System.out.println("Settings initialized");
    }
}
~~~

Về mặt ngữ nghĩa:

- Các biến **int**, **boolean**, reference... được chuẩn bị với default values (0, false, null...), trừ quy tắc riêng cho **constant variables**.
- Những biểu thức như **retryCount = 3** hay khối **static** thuộc **initialization**, không phải bước preparation.
- Không có nghĩa ứng dụng có thể quan sát trực tiếp mọi trạng thái preparation bằng cách đọc field bình thường: thao tác đọc static field không phải compile-time constant thường **kích hoạt initialization trước**.

**Constant variable** như **static final int LIMIT = 100;** được xử lý đặc biệt theo Java Language Specification và có thể được compiler dùng như giá trị hằng ở nơi tham chiếu.

## 8. Resolution: từ symbolic reference đến thành phần runtime

Class file thường chứa **symbolic references** trong constant pool, ví dụ tên class, field hoặc method. Resolution biến chúng thành thông tin runtime tương ứng theo quy tắc truy cập và tải class.

~~~java
final class Payment {
    static int calculate(int amount) {
        return amount * 2;
    }
}

int result = Payment.calculate(21); // 42
~~~

Để gọi **Payment.calculate**, JVM cần giải quyết những tham chiếu phù hợp tới class và method khi cần. Resolution cũng kiểm tra các ràng buộc như quyền truy cập, khả năng tìm thấy field/method, kiểu và chữ ký tương ứng.

Một ứng dụng có thể nạp được class nhưng lỗi khi gọi một method vốn đã bị xóa khỏi bản thư viện đang chạy:

~~~text
App compiled with library-v2: Payment.calculate(int)
Runtime uses library-v1:        no matching method
                                ↓
                         NoSuchMethodError
~~~

Đây là dạng **binary compatibility mismatch**. Sửa bằng cách đồng bộ **dependency thực sự được nạp ở runtime**, không phải chỉ thêm một câu lệnh try/catch cho mọi lỗi.

## 9. Initialization: static initializers chạy khi nào?

Khởi tạo class bao gồm gán các static fields từ initializer expressions và chạy các khối **static { ... }** theo thứ tự văn bản phù hợp.

~~~java
final class Configuration {
    static String endpoint = loadEndpoint();

    static {
        System.out.println("Configuration static block");
    }

    static String loadEndpoint() {
        System.out.println("Loading endpoint");
        return "https://example.com";
    }

    static String endpoint() {
        return endpoint;
    }
}
~~~

Khi **Configuration** được khởi tạo lần đầu:

~~~text
Loading endpoint
Configuration static block
~~~

Các lần dùng tiếp theo **trong cùng class identity**, nếu khởi tạo đã thành công, không chạy lại những initializer đó.

Tên JVM cho phương thức thực hiện khởi tạo class/interface là **<clinit>**. Nó không phải constructor **<init>** của instance; bạn không thể gọi trực tiếp **<clinit>** như một phương thức Java thông thường.

**Cảnh báo thiết kế:** Không dùng static initializer để thực hiện I/O dài, thao tác dễ thất bại hoặc tạo tài nguyên mà không có cơ chế lifecycle. Lỗi ở đây có thể khiến class không còn sử dụng được trong loader hiện tại.

## 10. Những hành động thường kích hoạt initialization

Theo Java Language Specification, initialization xảy ra trước những lần sử dụng chủ động của kiểu, đặc biệt:

1. **new T(...)** tạo instance của class T.
2. Gọi một **static method** được khai báo bởi T.
3. Gán vào một **static field** được khai báo bởi T.
4. Đọc một **static field** được khai báo bởi T mà **không phải constant variable**.
5. Một số thao tác reflection hoặc các cơ chế runtime được đặc tả cần khởi tạo class.
6. Việc chạy class được chọn làm entry point cũng phải thỏa quy tắc khởi tạo.

~~~java
final class DatabaseSettings {
    static int poolSize = initializeSize();

    private static int initializeSize() {
        System.out.println("DatabaseSettings initialized");
        return 8;
    }

    static int getPoolSize() {
        return poolSize;
    }
}

// Lần đầu đọc field không phải constant variable:
System.out.println(DatabaseSettings.poolSize);
// DatabaseSettings initialized
// 8
~~~

**Chỉ class thực sự khai báo static field cần được khởi tạo vì thao tác đọc field đó**. Nếu **SubClass.INHERITED_FIELD** tham chiếu field được khai báo ở SuperClass thì thao tác không tự động khởi tạo SubClass chỉ vì viết tên SubClass.

Việc **load** class, **lookup** metadata hoặc đánh giá **SomeType.class** không nhất thiết kích hoạt initialization; xem các phần tiếp theo.

## 11. Class literal không tự chạy static initializer

Lấy đối tượng Class bằng **T.class** thường không kích hoạt initialization của T:

~~~java
public class LiteralDemo {
    static final class Target {
        static {
            System.out.println("Target initialized");
        }

        static void ping() {
            System.out.println("Target.ping");
        }
    }

    public static void main(String[] args) {
        Class<?> type = Target.class;

        System.out.println(type.getSimpleName());
        // Target

        Target.ping();
        // Target initialized
        // Target.ping
    }
}
~~~

**Target.class** chỉ tạo hoặc lấy đại diện kiểu cần thiết; **Target.ping()** là lần sử dụng chủ động kích hoạt initialization.

Không suy ra rằng mọi lời gọi reflection đều không khởi tạo: ví dụ **Constructor.newInstance** hoặc một số thao tác đọc/call static members qua reflection cần initialization theo quy tắc API.

## 12. static final: hằng số biên dịch và giá trị runtime

**static final** không tự động đồng nghĩa **compile-time constant**. Với primitive hoặc String được khởi tạo bằng *constant expression*, compiler có thể inline giá trị ở nơi sử dụng.

~~~java
public class ConstantDemo {
    static final class Flags {
        static final int VERSION = 27; // constant variable
        static final String LABEL = "Java" + "27"; // constant variable

        static final Integer BOXED_VERSION = 27; // không là constant variable
        static final String RUNTIME =
            System.getProperty("java.version"); // runtime expression

        static {
            System.out.println("Flags initialized");
        }
    }

    public static void main(String[] args) {
        System.out.println(Flags.VERSION); // 27
        System.out.println(Flags.LABEL);   // Java27

        System.out.println(Flags.BOXED_VERSION);
        // Flags initialized
        // 27

        System.out.println(Flags.RUNTIME);
        // Phiên bản runtime, không in "Flags initialized" lần nữa
    }
}
~~~

**Integer BOXED_VERSION** là object reference, không phải constant variable theo nghĩa JLS. Đọc nó kích hoạt khởi tạo Flags dù field là **static final**.

**Hệ quả khi thay thư viện:** Nếu một public constant đã được inline vào mã của client, đổi hằng số trong JAR mà không biên dịch lại client có thể khiến client vẫn dùng giá trị cũ. Với API có thể thay đổi, tránh lạm dụng compile-time constants như một cơ chế cấu hình động.

## 13. Class.forName và ClassLoader.loadClass khác nhau

Các API thường gặp:

| API | Ý nghĩa chính | Khởi tạo ngay? |
|---|---|---|
| **T.class** | Lấy Class object | Không tự kích hoạt initialization |
| **Class.forName(name)** | Tìm/nạp/liên kết và khởi tạo class theo caller loader phù hợp | **Có** với class được tìm thấy theo hợp đồng overload này |
| **Class.forName(name, false, loader)** | Tìm/nạp/liên kết class theo loader chỉ định | **Không yêu cầu initialization** |
| **Class.forName(name, true, loader)** | Tìm/nạp/liên kết và khởi tạo | **Có** |
| **loader.loadClass(name)** | Nạp class theo loader, tương đương resolve=false ở overload mặc định | **Không yêu cầu initialization** |

Demo độc lập:

~~~java
public class ForNameDemo {
    static class Lazy {
        static {
            System.out.println("Lazy initialized");
        }
    }

    public static void main(String[] args) throws Exception {
        String name = Lazy.class.getName();
        ClassLoader loader = Lazy.class.getClassLoader();

        Class<?> unloadedInit = Class.forName(name, false, loader);
        System.out.println("Loaded only: " + unloadedInit.getSimpleName());

        Class<?> withInit = Class.forName(name, true, loader);
        System.out.println("Same class: " + (unloadedInit == withInit));
    }
}
~~~

Kết quả:

~~~text
Loaded only: Lazy
Lazy initialized
Same class: true
~~~

**Không lấy tham số initialize=false làm bảo đảm không có bất kỳ hoạt động phụ nào:** việc tải và liên kết có thể cần đọc resources, khởi tạo class loader hoặc gây lỗi liên quan dependencies. Tham số chỉ phân biệt rõ việc có yêu cầu **khởi tạo chính class đích** hay không.

Ngoài ra, mỗi overload có hợp đồng chi tiết riêng, đặc biệt khi dùng module, array classes hoặc tên kiểu nguyên thủy; hãy xem Javadoc **Class.forName** trước khi xây cơ chế plugin bằng chuỗi tự do.

## 14. Demo hoàn chỉnh: nạp trước, khởi tạo sau

Chương trình **ClassLifecycleDemo.java** dưới đây xác nhận thứ tự class loading/initialization bằng console, không yêu cầu thư viện ngoài.

~~~java
public class ClassLifecycleDemo {
    static class Parent {
        static {
            System.out.println("Parent initialized");
        }
    }

    static class Child extends Parent {
        static final int COMPILE_TIME_CONSTANT = 42;

        static final String RUNTIME_VALUE = initializeRuntimeValue();

        static {
            System.out.println("Child static block");
        }

        static String initializeRuntimeValue() {
            System.out.println("Child runtime field initialized");
            return "ready";
        }

        Child() {
            System.out.println("Child constructor");
        }

        static void ping() {
            System.out.println("Child.ping");
        }
    }

    public static void main(String[] args) throws Exception {
        System.out.println("1. Obtain Class literal");
        Class<?> type = Child.class;
        System.out.println(type.getName());

        System.out.println("2. forName without initialization");
        Class.forName(type.getName(), false, type.getClassLoader());

        System.out.println("3. Read compile-time constant");
        System.out.println(Child.COMPILE_TIME_CONSTANT);

        System.out.println("4. Read non-constant static field");
        System.out.println(Child.RUNTIME_VALUE);

        System.out.println("5. Create instance");
        new Child();

        System.out.println("6. Invoke static method");
        Child.ping();
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 ClassLifecycleDemo.java
java ClassLifecycleDemo
~~~

Kết quả:

~~~text
1. Obtain Class literal
ClassLifecycleDemo$Child
2. forName without initialization
3. Read compile-time constant
42
4. Read non-constant static field
Parent initialized
Child runtime field initialized
Child static block
ready
5. Create instance
Child constructor
6. Invoke static method
Child.ping
~~~

Những điểm rút ra:

- **Child.class** và **Class.forName(name,false,loader)** không tự chạy static initializer của Child.
- Đọc **COMPILE_TIME_CONSTANT** không khiến Child khởi tạo.
- Đọc **RUNTIME_VALUE** kích hoạt initialization của Parent rồi Child.
- **Constructor** chạy khi tạo mỗi instance, không thay cho class initialization.
- Gọi **ping** sau khi Child đã khởi tạo không chạy lại các khối static.

## 15. Superclass và superinterface: thứ tự initialization

Khi một class được khởi tạo, những **superclasses** chưa khởi tạo của nó phải được khởi tạo trước. Ngoài ra, những **superinterfaces có khai báo default methods** liên quan cũng được khởi tạo theo quy tắc của JLS, nếu chưa khởi tạo.

Với một interface được khởi tạo độc lập, **không mặc định khởi tạo toàn bộ superinterfaces** của nó.

~~~java
public class ParentOrderDemo {
    static class Parent {
        static {
            System.out.println("Parent");
        }
    }

    static class Child extends Parent {
        static {
            System.out.println("Child");
        }
    }

    public static void main(String[] args) {
        new Child();
    }
}
~~~

Kết quả:

~~~text
Parent
Child
~~~

Lưu ý: khi tham chiếu **Child.someStaticField** nhưng field thật ra được **khai báo bởi Parent**, thao tác chỉ khởi tạo Parent; không phải cứ ghi tên Child là JVM luôn khởi tạo Child.

Đối với interface, các trường mặc định là **public static final**, nhưng không phải mọi initializer là compile-time constant expression. Một field interface có initializer gọi phương thức có thể kích hoạt initialization khi được dùng.

## 16. Preparation khác initialization khi có phụ thuộc vòng

Static initialization có thể tham chiếu sang class khác, dẫn đến các chuỗi khởi tạo khó đoán:

~~~java
public class CircularDemo {
    static class A {
        static int x = B.y + 1;
    }

    static class B {
        static int y = A.x + 1;
    }

    public static void main(String[] args) {
        System.out.println("A.x=" + A.x);
        System.out.println("B.y=" + B.y);
    }
}
~~~

Khi bắt đầu khởi tạo A:

1. A.x đã có default value **0** từ preparation.
2. Tính A.x cần B.y, nên khởi tạo B.
3. B tính **A.x + 1** trong lúc A đang được khởi tạo bởi cùng thread; giá trị quan sát có thể là **0**, nên B.y thành **1**.
4. A tiếp tục, tính **B.y + 1**, nên A.x thành **2**.

Kết quả:

~~~text
A.x=2
B.y=1
~~~

Ví dụ chỉ minh họa việc thứ tự phụ thuộc và giá trị mặc định có thể ảnh hưởng kết quả, **không phải mô hình nên sử dụng cho nghiệp vụ**.

**Khuyến nghị:** tránh static initializers tham chiếu vòng, thực hiện I/O hay nắm lock trong thời gian dài. Dùng cấu hình và khởi tạo đối tượng qua dependency injection hoặc factory có lifecycle tường minh khi có nhiều phụ thuộc.

## 17. Initialization đa luồng và nguy cơ deadlock

JVM bảo đảm class/interface initialization theo cơ chế phối hợp giữa các thread. Nếu hai thread cùng cần khởi tạo một class, một thread có thể thực hiện initialization trong khi thread còn lại phải chờ.

Một class được khởi tạo thành công không chạy **static initializer** nhiều lần chỉ vì nhiều thread cùng truy cập. Tuy nhiên, điều đó **không** làm mọi trạng thái mutable static fields trở nên thread-safe sau khởi tạo.

Tình huống nguy hiểm: **ClassA.<clinit>** cần một lock hoặc gọi một thành phần đang đợi **ClassB.<clinit>**, trong khi một thread khác khởi tạo ClassB và đợi ClassA. Kết quả có thể là deadlock khó chẩn đoán.

~~~text
Thread-1: initializing ClassA
           └─ waits for ClassB

Thread-2: initializing ClassB
           └─ waits for ClassA
                => deadlock risk
~~~

Hãy dùng static initialization cho các giá trị nhỏ, xác định và ít tác dụng phụ. Nếu cần mở connection pool, khởi động scheduler hoặc đăng ký listener, hãy đưa chúng vào **application lifecycle** có startup/shutdown và error reporting rõ ràng.

## 18. Nếu static initializer thất bại thì sao?

Một lỗi trong quá trình khởi tạo class có thể khiến class ở trạng thái **erroneous** đối với class identity đó.

~~~java
public class FailedInitializationDemo {
    static class Broken {
        static final int VALUE = initialize();

        static int initialize() {
            throw new IllegalStateException("Configuration missing");
        }
    }

    public static void main(String[] args) {
        for (int attempt = 1; attempt <= 2; attempt++) {
            try {
                System.out.println(Broken.VALUE);
            } catch (LinkageError failure) {
                System.out.println(
                    attempt + ": " + failure.getClass().getSimpleName()
                );
            }
        }
    }
}
~~~

Thông thường trên JVM theo hợp đồng JLS/JVMS:

~~~text
1: ExceptionInInitializerError
2: NoClassDefFoundError
~~~

**Vì sao lần thứ hai khác lần đầu?**

- Nếu initializer ném một exception không phải Error, JVM thường bọc nó trong **ExceptionInInitializerError**.
- Sau khi initialization thất bại, class bị đánh dấu không thể khởi tạo thành công trong class identity hiện tại.
- Lần sử dụng tiếp theo thường gặp **NoClassDefFoundError** liên quan việc class không thể được khởi tạo.

Nếu initializer ném một **Error**, Error có thể được truyền thẳng, nên không giả định lần đầu **luôn** là ExceptionInInitializerError.

**Đừng xem NoClassDefFoundError chỉ có một nguyên nhân là thiếu JAR.** Nó cũng có thể theo sau lỗi initialization ban đầu; cần tìm exception đầu tiên trong log và cause chain.

## 19. ClassNotFoundException và NoClassDefFoundError

Hai lỗi này nghe giống nhau nhưng thường phản ánh những tình huống khác nhau:

| Dấu hiệu | Tình huống thường gặp | Cách xử lý |
|---|---|---|
| **ClassNotFoundException** (checked) | Code gọi **Class.forName** / **ClassLoader.loadClass** yêu cầu nạp một tên không tìm thấy | Kiểm tra class name, module path/classpath, loader và JAR |
| **NoClassDefFoundError** (LinkageError) | JVM cần class trong quá trình sử dụng nhưng định nghĩa thiếu hoặc không thể khởi tạo | Tìm missing dependency, binary mismatch hoặc lỗi init trước đó |
| **ExceptionInInitializerError** (Error) | Static initializer bị lỗi dạng exception cần bọc | Tìm nguyên nhân gốc trong static init |
| **UnsupportedClassVersionError** | Class file cần JVM hỗ trợ phiên bản mới hơn | Chạy với JVM phù hợp hoặc biên dịch cho target thích hợp |
| **VerifyError** / **ClassFormatError** | Định dạng hoặc bytecode không hợp lệ | Kiểm tra compiler, bytecode generator hoặc bản artifact |
| **NoSuchMethodError** / **NoSuchFieldError** | Phần mềm chạy với dependency không tương thích binary | Đồng bộ phiên bản ở runtime |
| **IllegalAccessError** | Quyền truy cập khi liên kết không cho phép | Kiểm tra exports/module và binary compatibility |

Một lỗi **NoClassDefFoundError: Could not initialize class ...** thường gợi ý initializer đã thất bại trước đó. Không chỉ nhìn stack trace của request cuối, vì nguyên nhân đầu tiên có thể nằm trong log startup.

## 20. ClassLoader: mô hình ủy quyền nạp class

**java.lang.ClassLoader** là lớp abstract chịu trách nhiệm tìm hoặc tạo định nghĩa class. Hành vi mặc định của phương thức **loadClass(String, boolean)** đi theo mô hình **parent delegation**:

1. Kiểm tra class đã được nạp bởi loader này hoặc được ghi nhận liên quan chưa.
2. Hỏi parent loader tìm class (hoặc bootstrap nếu không có parent).
3. Nếu parent không tìm thấy, gọi **findClass(name)** của loader hiện tại.
4. Nếu cần và được yêu cầu, thực hiện linking tương ứng.

~~~mermaid
flowchart TD
    R["Request loadClass('com.example.Plugin')"] --> C{"Đã có class?"}
    C -->|"Có"| O["Trả Class<?>"]
    C -->|"Không"| P["Nhờ parent loader"]
    P -->|"Parent tìm thấy"| O
    P -->|"Không tìm thấy"| F["findClass của loader con"]
    F -->|"Tìm thấy"| O
    F -->|"Không"| E["ClassNotFoundException"]
~~~

**Đây là mô hình mặc định, không phải bất biến cho mọi class loader tùy biến.** Một số môi trường plugin hoặc application server có chiến lược riêng để cô lập dependency; muốn thay đổi delegation phải hiểu hệ quả về danh tính kiểu, package sealing, bảo mật và tương thích module.

Không override **loadClass** chỉ để “tránh conflict” khi vấn đề thật sự là cấu hình version/dependency sai. Với class loader tùy biến theo parent-first, thường nên override **findClass** và để loadClass mặc định quản lý việc ủy quyền.

## 21. Ba built-in class loaders thường gặp

Java 27 có các cơ chế class loader built-in quan trọng:

| Loader | Vai trò khái quát | Lấy tham chiếu |
|---|---|---|
| **Bootstrap** | Nạp những class nền tảng cốt lõi theo quy tắc JVM | Thường được biểu diễn bằng **null** trong Class.getClassLoader() |
| **Platform** | Nạp một số platform modules/lớp nền tảng | **ClassLoader.getPlatformClassLoader()** |
| **Application/System** | Nạp phần lớn application classes theo cơ chế launcher | **ClassLoader.getSystemClassLoader()** |

~~~java
public class LoaderInspectionDemo {
    public static void main(String[] args) {
        System.out.println("String loader: "
            + String.class.getClassLoader());

        System.out.println("App loader: "
            + LoaderInspectionDemo.class.getClassLoader());

        System.out.println("Platform loader: "
            + ClassLoader.getPlatformClassLoader());

        System.out.println("System loader: "
            + ClassLoader.getSystemClassLoader());
    }
}
~~~

Đầu ra ví dụ với một JVM phổ biến:

~~~text
String loader: null
App loader: jdk.internal.loader.ClassLoaders$AppClassLoader@...
Platform loader: jdk.internal.loader.ClassLoaders$PlatformClassLoader@...
System loader: jdk.internal.loader.ClassLoaders$AppClassLoader@...
~~~

Tên class loader, định dạng **toString()** và identity hash ở đầu ra **không phải hợp đồng ổn định giữa các bản JVM**.

**Bootstrap không đồng nghĩa null là “không có class loader” ở cấp JVM.** Nó chỉ là cách API Java biểu diễn bộ nạp tích hợp của runtime trong trường hợp tương ứng.

## 22. Danh tính class = tên nhị phân + defining loader

Một trong những khái niệm quan trọng nhất của JVM:

> Hai class có cùng **binary name** nhưng được **hai defining class loaders khác nhau** định nghĩa có thể là **hai kiểu runtime khác nhau**.

~~~text
Loader A ── defines "com.example.api.Record" ──> Class A
Loader B ── defines "com.example.api.Record" ──> Class B

Tên giống nhau, nhưng Class A != Class B
~~~

Điều này giải thích lỗi gây khó hiểu như:

~~~text
ClassCastException: com.example.Plugin cannot be cast to com.example.Plugin
~~~

Vấn đề không nhất thiết là sai tên kiểu: **hai bản định nghĩa của cùng tên nằm trong những loader khác nhau**.

**Defining loader** là bộ nạp thực sự định nghĩa class. **Initiating loader** có thể là loader khác đã yêu cầu nạp và nhận kết quả do một loader được ủy quyền định nghĩa. Vì vậy, không nên nói rằng mọi loader gọi loadClass đều tạo ra một bản định nghĩa mới.

Thiết kế plugin tốt thường chia sẻ các **interface API** qua parent loader ổn định, đồng thời cô lập phần implementation và dependencies bằng loader riêng khi có lý do rõ ràng.

## 23. Demo hai loader định nghĩa cùng một tên class

Ví dụ **ClassLoaderIdentityDemo.java** dưới đây cố ý tạo hai loader tùy biến và định nghĩa lại bytes của một nested class đơn giản. Đây là **demo giáo dục**, không phải mẫu nạp mã không tin cậy trong production.

~~~java
import java.io.IOException;
import java.io.InputStream;

public class ClassLoaderIdentityDemo {
    static class Payload {
        String message() {
            return "hello";
        }
    }

    static final class IsolatedLoader extends ClassLoader {
        private final String isolatedName;

        IsolatedLoader(String isolatedName) {
            super(ClassLoaderIdentityDemo.class.getClassLoader());
            this.isolatedName = isolatedName;
        }

        @Override
        protected Class<?> loadClass(String name, boolean resolve)
                throws ClassNotFoundException {

            if (!name.equals(isolatedName)) {
                return super.loadClass(name, resolve);
            }

            synchronized (getClassLoadingLock(name)) {
                Class<?> result = findLoadedClass(name);

                if (result == null) {
                    String resource = name.replace('.', '/') + ".class";

                    try (InputStream input =
                             getParent().getResourceAsStream(resource)) {
                        if (input == null) {
                            throw new ClassNotFoundException(name);
                        }

                        byte[] bytes = input.readAllBytes();
                        result = defineClass(name, bytes, 0, bytes.length);

                    } catch (IOException failure) {
                        throw new ClassNotFoundException(name, failure);
                    }
                }

                if (resolve) {
                    resolveClass(result);
                }

                return result;
            }
        }
    }

    public static void main(String[] args) throws Exception {
        String name = Payload.class.getName();

        ClassLoader leftLoader = new IsolatedLoader(name);
        ClassLoader rightLoader = new IsolatedLoader(name);

        Class<?> left = leftLoader.loadClass(name);
        Class<?> right = rightLoader.loadClass(name);

        System.out.println(left.getName().equals(right.getName()));
        System.out.println(left == right);
        System.out.println(left.getClassLoader() == right.getClassLoader());
        System.out.println(Payload.class.isAssignableFrom(left));
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 ClassLoaderIdentityDemo.java
java ClassLoaderIdentityDemo
~~~

Kết quả:

~~~text
true
false
false
false
~~~

Hai loader đọc **cùng một nguồn bytecode** nhưng tạo hai định nghĩa có danh tính khác nhau. Class được nạp theo parent loader của ứng dụng, **Payload.class**, cũng không assignable từ bản Payload do loader con định nghĩa.

**Tại sao cố ý override loadClass trong demo?** Đây là thí nghiệm **child-first cho đúng một binary name** để chứng minh định danh. Trong production, cần cân nhắc delegation, package definition, lỗi liên kết và cách chia sẻ API; **không** thay toàn bộ hệ thống thành child-first chỉ để được hiệu ứng này.

Class loader không phải sandbox thực thi mã độc. Không cung cấp bytecode tùy ý từ nguồn không tin cậy vào loader này.

## 24. Classpath, module path và JPMS

Một ứng dụng Java 27 có thể khởi động bằng classpath hoặc module path:

~~~bash
# Classpath:
java -cp app.jar com.example.Main

# Module path:
java --module-path mods --module com.example.app/com.example.Main
~~~

| Khái niệm | Trách nhiệm |
|---|---|
| **Classpath** | Nơi lớp ở unnamed module có thể được tìm trong cấu hình tương ứng |
| **Module path** | Nơi JVM/launcher tìm named modules và xây cấu hình module |
| **module-info.java** | Khai báo **requires**, **exports**, **opens**, **uses**, **provides** |
| **ClassLoader** | Nạp hoặc định nghĩa class theo môi trường runtime |
| **Module** | Tổ chức quan hệ đọc và quyền truy cập package qua ranh giới module |
| **ModuleLayer** | Cấu trúc runtime cho việc định nghĩa/resolution các nhóm modules |

**JPMS và class loading là hai lớp cơ chế liên quan nhưng không đồng nhất.** Một class có thể tồn tại trên module path nhưng module chứa nó chưa được resolve vào cấu hình ứng dụng. Một package có thể được loader tìm thấy nhưng không được export cho module caller nên vẫn không thể sử dụng như public API.

Ngược lại, việc một module **exports** package **không tự** tạo một loader mới và không bảo đảm rằng class có thể được tìm trong một cấu hình sai đường dẫn.

**Mở package bằng opens** cho deep reflection cũng không phải giải pháp cho **ClassNotFoundException** khi artifact thực sự không nằm trong cấu hình runtime.

## 25. Reflection, ServiceLoader và context class loader

Với hệ thống plugin, một thư viện có thể cần tìm implementation theo interface API. Thay vì tự quét và truy cập private classes, ưu tiên sử dụng **ServiceLoader** khi hợp đồng phù hợp.

Ví dụ module có thể khai báo:

~~~java
module com.example.app {
    uses com.example.spi.Processor;
    exports com.example.spi;
}
~~~

Module triển khai:

~~~java
module com.example.processor {
    requires com.example.app;
    provides com.example.spi.Processor
        with com.example.processor.DefaultProcessor;
}
~~~

Code ứng dụng:

~~~java
for (Processor processor : ServiceLoader.load(Processor.class)) {
    processor.process();
}
~~~

Ví dụ trên giả định **Processor** là interface API công khai, **DefaultProcessor** là một implementation hợp lệ và các module đã được resolve/đưa vào cấu hình; đây là **đoạn thiết kế phân tán ở nhiều file/module**, không phải tệp Java độc lập.

Một số API discovery sử dụng **thread context class loader**:

~~~java
ClassLoader context =
    Thread.currentThread().getContextClassLoader();

System.out.println(context);
~~~

Context loader có thể giúp framework tìm classes/resources của ứng dụng khi thư viện nền tảng không biết trực tiếp classpath/module configuration của caller. Nhưng thay đổi context loader bừa bãi dễ khiến thư viện nạp sai phiên bản, giữ reference đến loader của plugin hoặc làm hành vi khác giữa các threads.

Khi đổi context loader trong một phạm vi cụ thể, phải lưu lại và khôi phục loader cũ trong **finally**.

## 26. Nạp resource không giống nạp class

ClassLoader còn hỗ trợ tìm resources:

~~~java
import java.io.InputStream;

ClassLoader loader = ClassLoader.getSystemClassLoader();

try (InputStream input =
         loader.getResourceAsStream("config/app.properties")) {

    if (input == null) {
        throw new IllegalStateException("Missing resource");
    }

    // Đọc cấu hình với giới hạn byte và charset xác định.
}
~~~

Những nguyên tắc:

- **getResourceAsStream** trả null khi không tìm thấy resource theo phạm vi tìm kiếm.
- Đường dẫn resource thông thường dùng dấu **/**, không dùng tên Java package dạng dấu chấm.
- Với **Class.getResourceAsStream**, resource path bắt đầu bằng **/** có nghĩa tuyệt đối theo quy tắc API; với **ClassLoader.getResourceAsStream**, không tự thêm dấu / đầu.
- Tài nguyên nằm trong **named module** còn chịu quy tắc đóng gói/visibility theo API tương ứng.
- Resource **không bắt buộc là file vật lý** trên ổ đĩa; không luôn chuyển resource URL thành **Path.of(...)** để đọc.

**Bảo vệ dữ liệu:** Không dùng tên resource từ người dùng để tìm bí mật nằm trên classpath; chỉ truy cập các resource ứng dụng đã chủ động công bố.

## 27. Thread safety khi tự viết ClassLoader

ClassLoader tùy biến cần xử lý các yêu cầu nạp đồng thời và tránh định nghĩa trùng một tên.

**getClassLoadingLock(name)** là công cụ API cho việc đồng bộ khi nạp class. Một loader được đăng ký **parallel capable** có thể dùng khóa theo tên lớp; loader không parallel-capable có thể dùng khóa chung, làm tăng tranh chấp.

~~~java
@Override
protected Class<?> loadClass(String name, boolean resolve)
        throws ClassNotFoundException {

    synchronized (getClassLoadingLock(name)) {
        // Kiểm tra class đã nạp, ủy quyền hoặc tự định nghĩa.
        // Không gọi defineClass lặp lại cho cùng một tên.
    }

    // Mã minh họa khái niệm, chưa phải implementation hoàn chỉnh.
}
~~~

Nếu loader chỉ cần thêm nơi tìm class trong mô hình parent-first, nên xem xét override **findClass** hoặc sử dụng loader có sẵn phù hợp, thay vì viết lại toàn bộ giao thức delegation và khóa.

**Không giữ lock trong lúc gọi mã plugin tùy ý**. Các class loaders gọi qua lại hoặc cùng chờ những locks khác có thể gây deadlock, đặc biệt khi nạp đồng thời nhiều plugin.

Khi tự định nghĩa class, còn phải xét tính nhất quán package, protection domain, module, sealing và loading constraints. **Không chỉ cần đọc bytes rồi gọi defineClass là có một hệ thống module/plugin đúng.**

## 28. JVM memory: class metadata, heap và metaspace

Trong **HotSpot** hiện đại, metadata của class thường được quản lý trong **metaspace**, sử dụng vùng nhớ native; điều này khác với các Java objects trên heap.

~~~text
JVM process memory (đơn giản hóa)
├── Java heap
│   ├── application objects
│   ├── Class mirrors và dữ liệu runtime liên quan
│   └── objects giữ tham chiếu đến loaders
├── Metaspace / class metadata (HotSpot)
├── Thread stacks
├── Code cache / JIT-generated code
└── Native allocations khác
~~~

Cần phân biệt:

- **Không thể suy toàn bộ bộ nhớ JVM chỉ từ -Xmx**.
- **Metaspace** là chi tiết triển khai của HotSpot, không phải mô hình vị trí byte tuyệt đối của mọi Java VM.
- Việc nạp quá nhiều class hoặc tạo nhiều loaders không được thu hồi có thể làm bộ nhớ metadata tăng mạnh.
- **Class objects** và **ClassLoader objects** trên heap có thể giữ tham chiếu khiến dữ liệu metadata tương ứng còn tồn tại.

Ví dụ giới hạn metaspace của một tiến trình HotSpot:

~~~bash
java -XX:MaxMetaspaceSize=256m -jar application.jar
~~~

Con số **256m chỉ là ví dụ**, không phải thông số khuyến nghị chung. Giới hạn quá thấp có thể gây **OutOfMemoryError: Metaspace**, ngay cả khi heap còn dung lượng.

## 29. Class unloading và vì sao loader dễ bị giữ lại

Class metadata có thể được thu hồi khi những điều kiện reachability và chính sách GC/unloading của JVM cho phép. Nhưng **không có bảo đảm rằng một class sẽ được unload ngay sau khi không còn dùng một instance**.

Với các plugin được nạp bằng class loader riêng, nguyên nhân giữ loader phổ biến:

- Một **static cache** trong class của ứng dụng cha giữ instance, Class object hoặc reflection Method liên quan plugin.
- Một **Thread** hoặc **thread context class loader** vẫn tham chiếu loader plugin.
- **ThreadLocal** hoặc task được đặt trong executor còn giữ dữ liệu plugin.
- Listener, callback, scheduler hoặc MBean chưa được unregister.
- Một registry, ServiceLoader/cache hoặc thư viện bên thứ ba vẫn giữ references.
- Class đang thực thi hoặc các đối tượng liên quan chưa thể thu hồi.

~~~mermaid
flowchart LR
    A["App singleton / cache"] --> B["Plugin instance / Class<?>"]
    B --> C["Plugin ClassLoader"]
    C --> D["Class metadata"]
    E["Long-lived thread / TCCL"] --> C
    F["Scheduled task / listener"] --> B
~~~

**Chỉ gọi close() trên URLClassLoader không bảo đảm unload class ngay.** Đóng loader phù hợp giúp giải phóng những tài nguyên có thể đóng, như handles đến JAR, nhưng JVM vẫn phải xét reachability.

Cũng không xem **System.gc()** là một thao tác “unload class bắt buộc”. Nó không bảo đảm việc thu hồi ngay cả khi được gọi.

## 30. Chẩn đoán class loading và unloading bằng JVM logging

Java 27 trên HotSpot hỗ trợ **Unified JVM Logging**, có thể quan sát việc nạp và unload class bằng tag phù hợp:

~~~bash
java -Xlog:class+load=info,class+unload=info \
  -cp . ClassLifecycleDemo
~~~

Lệnh trên trình bày cú pháp cho shell hỗ trợ **\\** nối dòng; trên Windows PowerShell cần viết một dòng hoặc sử dụng cú pháp xuống dòng phù hợp của shell:

~~~bash
java -Xlog:class+load=info,class+unload=info -cp . ClassLifecycleDemo
~~~

Thông tin log có thể bao gồm tên class và nơi class được nạp từ đó. **Khối lượng log có thể rất lớn** vì JVM nạp nhiều lớp nội bộ trước cả khi chạy code ứng dụng.

Khi cần quan sát thêm, có thể xem các logging tags có hỗ trợ cho **class initialization**, class resolution hoặc class loader data trên runtime đang chạy. Tránh dùng những cờ logging JVM quá cũ như một cơ chế chuẩn mới trong Java 27; tham khảo tài liệu **-Xlog** hiện hành.

Nếu chỉ cần chạy demo thứ tự static initializer, **không cần bật logging**; lệnh logging dành cho quan sát nội bộ JVM khi điều tra vấn đề.

## 31. Dùng jcmd để quan sát JVM đang chạy

**jcmd** là công cụ chẩn đoán trong JDK, có thể gửi một số lệnh tới JVM đang chạy khi có đủ quyền.

~~~bash
# Liệt kê Java processes mà công cụ quan sát được:
jcmd -l

# Dùng PID thực sự từ môi trường của bạn:
jcmd <pid> VM.classloaders
jcmd <pid> VM.classloader_stats
jcmd <pid> VM.metaspace

# Xem danh sách lệnh mà đúng JVM hỗ trợ:
jcmd <pid> help
~~~

| Lệnh | Dùng để làm gì? |
|---|---|
| **VM.classloaders** | Hiển thị quan hệ/hierarchy của class loaders |
| **VM.classloader_stats** | Thống kê class loaders và dữ liệu liên quan |
| **VM.metaspace** | Thống kê metaspace trong HotSpot |
| **VM.command_line** | Kiểm tra command line của JVM đang chạy |
| **help** | Tìm lệnh và tham số hiện được hỗ trợ |

**<pid>** trong ví dụ là chỗ điền PID, không phải một chuỗi gõ nguyên văn. Một số lệnh có overhead và có thể tác động đến tiến trình; chỉ chạy khi có quyền vận hành và cần thiết.

Không dựa vào một chỉ số duy nhất để kết luận “metaspace leak”. Cần xem class count/loader count theo thời gian, nhịp redeploy, tình trạng references, hoạt động GC và hành vi thực tế của workload.

## 32. Đo số class đã nạp bằng ClassLoadingMXBean

**java.lang.management.ClassLoadingMXBean** cho phép đọc các chỉ số tổng quát mà không cần parse JVM logging.

~~~java
import java.lang.management.ClassLoadingMXBean;
import java.lang.management.ManagementFactory;

public class ClassCountDemo {
    public static void main(String[] args) {
        ClassLoadingMXBean stats =
            ManagementFactory.getClassLoadingMXBean();

        System.out.println("Loaded now: "
            + stats.getLoadedClassCount());

        System.out.println("Total loaded: "
            + stats.getTotalLoadedClassCount());

        System.out.println("Total unloaded: "
            + stats.getUnloadedClassCount());
    }
}
~~~

- **getLoadedClassCount()**: số class hiện được nạp.
- **getTotalLoadedClassCount()**: tổng số class đã được nạp theo vòng đời JVM.
- **getUnloadedClassCount()**: tổng số class đã unload theo số liệu runtime.

Số liệu có thể thay đổi khi chính chương trình chạy và khi JVM nạp thêm code hỗ trợ metric/logging. Nếu số class hiện còn tăng qua nhiều lần tải/bỏ plugin dù có kỳ vọng unload, đó là dấu hiệu cần điều tra, **không đủ để khẳng định leak chỉ từ một snapshot**.

## 33. Class Data Sharing và việc tối ưu startup

Java hiện đại có những cơ chế giảm chi phí class loading hoặc tối ưu startup như **Class Data Sharing (CDS)** và các cơ chế cache/AOT mà JDK cung cấp.

Các cơ chế này có thể giúp giảm một phần công việc hoặc chia sẻ metadata theo quy tắc riêng của JVM, nhưng:

- **Không loại bỏ ranh giới class loader** hoặc biến hai lớp khác defining loader thành cùng một kiểu runtime.
- **Không cho phép bỏ các quy tắc initialization** của Java.
- **Không chứng minh mọi class đã được khởi tạo sẵn** trước khi main chạy.
- Hiệu quả phụ thuộc cấu hình launcher, bản JDK, workload, loại class và cách đóng gói.

Khi đo startup, phải phân biệt thời gian **loading/linking**, thời gian **static initialization**, thời gian dependency injection, I/O, JIT compilation và các bước khởi động dịch vụ. Một ứng dụng chậm không nhất thiết cần viết custom class loader.

## 34. Công cụ javap để xem class file và <clinit>

**javap** hỗ trợ xem cấu trúc class file/bytecode được biên dịch. Ví dụ, sau khi biên dịch ClassLifecycleDemo:

~~~bash
javap -c -p 'ClassLifecycleDemo$Child'
~~~

Trên Windows PowerShell, dấu nháy đơn bảo vệ ký tự **$** không bị xử lý như tham chiếu biến của shell. Lệnh tương ứng trên shell khác có thể cần cách quote thích hợp.

Với **-c**, javap in bytecode của các phương thức; **-p** cho phép xem cả những members không public. Có thể quan sát phương thức static initializer tương ứng với **<clinit>**, nếu class có phần khởi tạo runtime cần thực thi.

~~~text
static {};
  Code:
     ...
     invokestatic ...
     putstatic ...
     ...
~~~

Đây là công cụ quan sát bytecode, không phải giải pháp bắt buộc để hiểu mọi dòng Java source. Compiler có thể sinh thêm phương thức hoặc cấu trúc runtime, vì vậy đừng giả định mã nguồn và bytecode có quan hệ một-một cho mọi tính năng Java.

## 35. Lỗi thực tế thường gặp và cách khắc phục

| Lỗi / triệu chứng | Nguyên nhân khả dĩ | Cách điều tra |
|---|---|---|
| **ClassNotFoundException** | Sai tên, thiếu JAR, sai loader/module resolution | Kiểm tra tên nhị phân, classpath, module path, loader |
| **NoClassDefFoundError** | Runtime dependency thiếu hoặc class khởi tạo thất bại | Tìm lỗi đầu tiên, dependency, cause chain |
| **ExceptionInInitializerError** | Khối static hoặc field initializer lỗi | Xem nguyên nhân gốc, tránh I/O trong static init |
| **UnsupportedClassVersionError** | Runtime quá cũ cho class file | Đồng bộ JDK/toolchain và target release |
| **NoSuchMethodError** | Mã biên dịch và JAR chạy không cùng binary contract | Xác định JAR được nạp thực tế, kiểm tra dependency graph |
| **ClassCastException: X to X** | Hai class cùng tên do loaders khác nhau định nghĩa | Kiểm tra **getClassLoader()**, lớp API chung |
| **ServiceLoader không tìm thấy provider** | Sai module/service registration hoặc context loader | Kiểm tra uses/provides, module resolution, runtime environment |
| **Static initializer chạy nhiều lần khi hot reload** | Class được định nghĩa bởi loaders mới | Kiểm tra loader identity; mỗi class identity khởi tạo riêng |
| **Metaspace tăng sau redeploy** | Class loaders và metadata còn reachable | Kiểm tra thread, cache, listeners, Class objects, jcmd |
| **Deadlock khi startup** | Static init vòng hoặc locks/loader synchronization | Thread dump, thay static I/O bằng lifecycle rõ ràng |
| **Không đọc được resource dù có JAR** | Sai resource path hoặc module encapsulation | Kiểm tra loader, path, exports/opens theo API |
| **setAccessible bị chặn** | JPMS package chưa open | Sử dụng public API hoặc qualified opens đúng phạm vi |
| **Lỗi chỉ xảy ra production** | Module path/classpath, JDK, CDS, loader tree khác | Đối chiếu startup flags, runtime class sources |

Hãy luôn phân biệt **lỗi tìm class**, **lỗi liên kết**, **lỗi khởi tạo** và **lỗi runtime khi thực thi method**; cách sửa khác nhau.

## 36. Bài tập thực hành

**Bài tập 1 — Triggers.** Tạo class có compile-time constant, static final field gọi một method và một static block. Dùng **T.class**, **Class.forName(name,false,loader)**, đọc constant và đọc runtime field; ghi lại chính xác lúc static initializer chạy.

**Bài tập 2 — Parent order.** Tạo Parent và Child có static blocks; truy cập inherited static field thông qua tên Child, sau đó gọi static method được khai báo trực tiếp ở Child. So sánh những class thực sự được khởi tạo.

**Bài tập 3 — Error lifecycle.** Viết class có static initializer ném IllegalStateException. Bắt **LinkageError** ở lần dùng đầu và lần dùng sau; giải thích ExceptionInInitializerError và NoClassDefFoundError.

**Bài tập 4 — Class loader identity.** Chạy **ClassLoaderIdentityDemo** rồi in **getClassLoader()**, **getName()**, **==**, **isAssignableFrom**. Giải thích vì sao tên lớp bằng nhau không tạo cùng một kiểu.

**Bài tập 5 — Module path.** Tạo hai named modules: một module exports package API và module kia requires nó. Thử import package internal không được exports; giải thích vì sao lỗi truy cập khác với thiếu class.

**Bài tập 6 — Resource loading.** Đặt một resource test lên classpath và đọc bằng **Class.getResourceAsStream** và **ClassLoader.getResourceAsStream**. So sánh quy tắc đường dẫn có/không có dấu **/** đầu.

**Bài tập 7 — Diagnostics.** Chạy demo với **-Xlog:class+load=info,class+unload=info**. Tìm log chứa tên class của ứng dụng; không dựa vào thứ tự mọi class nội bộ trong JVM.

**Bài tập 8 — Metaspace.** Trên môi trường được phép, xem **VM.classloader_stats** và **VM.metaspace** bằng jcmd trước và sau khi tạo/bỏ một nhóm plugin loaders. Đo nhiều lần, không kết luận từ một snapshot.

**Bài tập 9 — Thiết kế plugin.** Đề xuất cách chia sẻ interface qua parent loader, load implementation bằng ServiceLoader, và đóng các tài nguyên/plugin threads khi unload. Nêu lý do tránh rò rỉ ClassLoader qua static caches.

## 37. Checklist về loading, linking và initialization trong Java 27

- [ ] Phân biệt **class file**, **Class object**, **class loader**, **instance** và metadata.
- [ ] Hiểu ba pha chính: **loading → linking → initialization**.
- [ ] Biết linking gồm **verification**, **preparation** và **resolution**; resolution có thể diễn ra muộn.
- [ ] Không nhầm preparation (default static values) với initialization (chạy biểu thức/khối static).
- [ ] Phân biệt **Class literal**, **Class.forName(false)** và những thao tác chủ động kích hoạt initialization.
- [ ] Kiểm tra compile-time constants khi thay đổi giá trị static final trên thư viện.
- [ ] Ghi nhớ superclass init trước subclass và quy tắc riêng cho superinterfaces có default methods.
- [ ] Tránh static initialization có I/O, lock dài hoặc phụ thuộc vòng.
- [ ] Hiểu lỗi initializer đầu tiên có thể là **ExceptionInInitializerError**, lần sau là **NoClassDefFoundError**.
- [ ] Phân biệt ClassNotFoundException, NoClassDefFoundError, VerifyError, UnsupportedClassVersionError và NoSuchMethodError.
- [ ] Sử dụng mô hình parent delegation trừ khi có yêu cầu isolation rõ ràng.
- [ ] Hiểu **defining loader + binary name** xác định danh tính class runtime.
- [ ] Chia sẻ plugin API qua loader ổn định; tránh duplicate API classes.
- [ ] Phân biệt module **requires/exports/opens** với trách nhiệm của ClassLoader.
- [ ] Không xem reflection hoặc custom class loading là sandbox an ninh.
- [ ] Quản lý thread context class loader, caches, listeners và executor lifecycle.
- [ ] Không giả định đóng URLClassLoader hoặc gọi System.gc() sẽ unload class ngay.
- [ ] Quan sát metaspace và class loader count qua logging, jcmd và MXBean khi cần.
- [ ] Không nhầm heap usage với tổng native/process memory.
- [ ] Xác nhận classpath/module path và class nguồn runtime khi phát sinh binary mismatch.
- [ ] Dùng các API/công cụ Java 27 hiện hành, không dựa vào extension mechanism hoặc cờ logging cũ.
- [ ] Tách việc chẩn đoán lỗi nạp class khỏi chạy Content QA chuyên sâu của toàn bộ giáo trình.

**Kết luận:** Class loading quyết định **định nghĩa kiểu nào được đưa vào JVM và bởi loader nào**; linking bảo đảm class có thể được dùng theo những ràng buộc của JVM; initialization thực thi các static initializers khi cần. Hiểu rõ ba giai đoạn cùng danh tính class loader giúp giải thích các lỗi tưởng khó hiểu như “X không cast được sang X”, lỗi khởi tạo lặp, missing method ở runtime và tăng metaspace sau redeploy. Với Java 27, hãy ưu tiên dependency/module configuration rõ ràng, API công khai ổn định, vòng đời tài nguyên tường minh và các công cụ quan sát JVM hiện đại.

## Tài liệu tham khảo

- [Java SE 27 — Java Language Specification, Chương 12](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-12.html): class loading, linking, initialization và class unloading.
- [Java SE 27 — Java Virtual Machine Specification, Chương 5](https://docs.oracle.com/en/java/javase/27/docs/specs/jvms/jvms-5.html): creation, loading, verification, preparation, resolution và initialization.
- [Java SE 27 — ClassLoader](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/ClassLoader.html): parent delegation, loadClass, findClass, getClassLoadingLock và resource loading.
- [Java SE 27 — Class](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/Class.html): class literals, forName, getClassLoader và reflection.
- [Java SE 27 — ServiceLoader](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/ServiceLoader.html): discovery provider và module-based services.
- [Java SE 27 — ClassLoadingMXBean](https://docs.oracle.com/en/java/javase/27/docs/api/java.management/java/lang/management/ClassLoadingMXBean.html): class counts được quản lý qua MXBean.
- [JDK 27 — java launcher](https://docs.oracle.com/en/java/javase/27/docs/specs/man/java.html): module path, classpath và Unified Logging **-Xlog**.
- [JDK 27 — jcmd](https://docs.oracle.com/en/java/javase/27/docs/specs/man/jcmd.html): VM.classloaders, VM.classloader_stats và VM.metaspace.
- [JDK 27 — javap](https://docs.oracle.com/en/java/javase/27/docs/specs/man/javap.html): bytecode inspection và static initializer.
