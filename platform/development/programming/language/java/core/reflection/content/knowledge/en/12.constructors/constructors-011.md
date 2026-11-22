# Khởi tạo lớp và lỗi xảy ra trước hoặc trong constructor khi dùng Java Reflection

Khi tạo đối tượng bằng Reflection, nhiều lập trình viên thấy `Constructor.newInstance(...)` ném lỗi rồi kết luận rằng *constructor bị lỗi*. Kết luận này có thể sai: **JVM phải bảo đảm lớp đã được khởi tạo (class initialization) trước khi thực sự chạy constructor**. Lỗi có thể xảy ra trong static field initializer, static block, quá trình khởi tạo superclass, kiểm tra quyền truy cập, khớp tham số, instance initializer, superclass constructor hoặc thân constructor đang gọi.

Bài này tập trung phân biệt **khởi tạo lớp (`<clinit>`)** với **khởi tạo đối tượng (`<init>`)** và xác định lỗi ở giai đoạn nào khi dùng `Class`, `Constructor` và `Constructor.newInstance(...)`. Các ví dụ chạy được bằng Java 17+.

## 1. Hai khái niệm thường bị gọi chung là "khởi tạo"

### Class initialization: khởi tạo lớp

*Class initialization* là quá trình JVM thực thi các static field initializer và static initializer block thuộc một lớp, theo thứ tự văn bản khai báo và theo các quy tắc của Java Language Specification. JVM cần khởi tạo superclass liên quan trước khi khởi tạo lớp con, đồng thời bảo đảm quá trình khởi tạo một lớp được điều phối giữa các thread.

Ví dụ:

~~~java
class Service {
    static String config = loadConfig();

    static {
        System.out.println("Service static block");
    }

    private static String loadConfig() {
        System.out.println("Service static field");
        return "ready";
    }
}
~~~

Đây là **mã minh họa**, chưa có `main`. Trong lần khởi tạo `Service` đầu tiên, lời gọi `loadConfig()` in trước, rồi static block in sau. Hai hành động này thuộc **khởi tạo lớp**, không phải thân constructor. Trong bytecode, phần việc đó được JVM tổ chức trong phương thức khởi tạo lớp đặc biệt `<clinit>`.

**Không đồng nhất ba trạng thái:**

1. **Loading (nạp):** JVM tìm và định nghĩa cấu trúc lớp.
2. **Linking (liên kết):** xác minh, chuẩn bị và có thể phân giải các tham chiếu.
3. **Initialization (khởi tạo):** thực thi logic khởi tạo static nếu chưa thực thi xong.

Lấy được đối tượng `Class<?>` không tự chứng minh rằng initialization đã diễn ra.

### Object initialization: khởi tạo đối tượng

Khi thực sự tạo instance của một class thông thường, JVM cấp phát đối tượng rồi thực hiện chuỗi constructor theo quy tắc Java:

- Superclass constructor được gọi trong quy trình tạo instance trước khi chạy phần thân constructor của subclass.
- Các instance field initializer và instance initializer block của mỗi class chạy vào thời điểm thích hợp sau khi gọi superclass constructor và trước phần thân constructor tương ứng.
- Thân constructor có thể gán field, kiểm tra tham số, gọi service và ném exception.

Constructor xuất hiện trong bytecode với tên đặc biệt `<init>`. Đây **không phải** `<clinit>`; một class có thể được khởi tạo một lần rồi tạo nhiều instance bằng nhiều lời gọi constructor.

## 2. Reflection kích hoạt giai đoạn nào?

| Thao tác | Tự nó có bắt buộc khởi tạo class đích không? | Điều cần nhớ |
| --- | --- | --- |
| `SomeClass.class` | Không | Lấy class literal, chưa chạy static initializer chỉ vì thao tác này |
| `SomeClass.class.getDeclaredConstructor(...)` | Không | Chỉ tra cứu metadata/chữ ký constructor |
| `getDeclaredConstructors()`, `getConstructor(...)` | Không | Khám phá constructor; không tạo instance |
| `Class.forName("pkg.SomeClass")` | Có, mặc định yêu cầu khởi tạo | Lỗi static initializer có thể nổ **ngay tại `forName`** |
| `Class.forName(name, false, loader)` | Không yêu cầu khởi tạo class đích | Hữu ích khi muốn nạp/tra cứu metadata trước |
| `constructor.newInstance(args...)` | Có, nếu đủ điều kiện đi tới tạo instance và class chưa khởi tạo | JVM phải khởi tạo class trước khi thực thi constructor |
| `new SomeClass(...)` | Có | Tương tự về nhu cầu khởi tạo class, nhưng đường ngoại lệ khác Reflection |
| Truy cập/gọi một static member đủ điều kiện gây active use | Có thể | Có ngoại lệ về constant variables và quy tắc `JLS 12.4.1` |

**Chú ý phạm vi:** "không khởi tạo class đích" ở bảng không có nghĩa API không thể kích hoạt bất cứ hoạt động nạp/liên kết kiểu liên quan nào. Điều chắc chắn có ích trong bài là `getDeclaredConstructor` không chạy static block của class đích như hành vi mặc định của `Constructor.newInstance`.

Ví dụ hai lời gọi khác nhau:

~~~java
Class<?> metadataOnly = Class.forName(
        "com.example.Service", false,
        Thread.currentThread().getContextClassLoader());

Class<?> initialized = Class.forName("com.example.Service");
~~~

Đây là **mã minh họa**; cần class `com.example.Service` tồn tại và được class loader nhìn thấy. Lời gọi đầu không yêu cầu khởi tạo class đích; lời gọi thứ hai yêu cầu khởi tạo. Nếu class đã được khởi tạo từ trước, JVM không lặp lại static initializer chỉ vì có lời gọi mới.

## 3. Thứ tự class initialization và constructor trong một lần tạo object

Xét một lớp con kế thừa lớp cha. Trong tình huống class chưa được khởi tạo và gọi constructor thành công, thứ tự dễ quan sát như sau:

~~~text
Tìm Constructor bằng getDeclaredConstructor()
    ↓ không thực thi static initializer
Gọi Constructor.newInstance()
    ↓ kiểm tra điều kiện, chuẩn bị gọi
Khởi tạo superclass cần thiết
    ↓ static fields/static blocks của superclass
Khởi tạo class đích
    ↓ static fields/static blocks của class đích
Tạo instance và thực hiện chuỗi constructor
    ↓ superclass constructor; instance initializers
Chạy thân constructor của class đích
    ↓
newInstance() trả về đối tượng
~~~

Sơ đồ này mô tả đường thành công; một lỗi ở bất kỳ giai đoạn liên quan có thể cắt ngang các bước phía sau. Trình tự kiểm tra quyền, đối số và một số lỗi xảy ra trước khi class initialization còn phụ thuộc điều kiện cụ thể của API, nên đừng dùng sơ đồ để khẳng định thứ tự tất cả các lỗi kiểm tra đầu vào.

### Ví dụ đầy đủ 1: metadata không khởi tạo, `newInstance` mới khởi tạo

Tạo tệp **`ConstructorInitOrderDemo.java`**:

~~~java
import java.lang.reflect.Constructor;

class ParentStage {
    static {
        System.out.println("ParentStage.<clinit>");
    }

    ParentStage() {
        System.out.println("ParentStage.<init>");
    }
}

class ChildStage extends ParentStage {
    static {
        System.out.println("ChildStage.<clinit>");
    }

    ChildStage() {
        System.out.println("ChildStage.<init>");
    }
}

public class ConstructorInitOrderDemo {
    public static void main(String[] args)
            throws ReflectiveOperationException {
        System.out.println("Metadata lookup start");

        Class<ChildStage> type = ChildStage.class;
        Constructor<ChildStage> ctor = type.getDeclaredConstructor();

        System.out.println("Constructor found");
        ChildStage created = ctor.newInstance();

        System.out.println("Instance created: "
                + (created != null));
    }
}
~~~

Chạy trong cùng thư mục:

~~~bash
javac --release 17 ConstructorInitOrderDemo.java
java ConstructorInitOrderDemo
~~~

**Stdout:**

~~~text
Metadata lookup start
Constructor found
ParentStage.<clinit>
ChildStage.<clinit>
ParentStage.<init>
ChildStage.<init>
Instance created: true
~~~

Giải thích:

1. `ChildStage.class` và `getDeclaredConstructor()` cho phép lấy metadata mà chưa chạy static block của `ChildStage`.
2. `ctor.newInstance()` yêu cầu khởi tạo `ChildStage`. `ParentStage` cần được khởi tạo trước; hai dòng `<clinit>` xuất hiện theo thứ tự superclass rồi subclass.
3. Khi bắt đầu thực thi chuỗi constructor, `ParentStage()` chạy trước `ChildStage()`, nên hai dòng `<init>` xuất hiện sau static initializers.
4. `newInstance` hoàn tất và trả object, nên dòng `Instance created: true` xuất hiện cuối.

Trong một chương trình có nhiều lần tạo object, static block thường chỉ chạy **một lần cho mỗi lần khởi tạo thành công của class** tương ứng trong một runtime/class loader; constructor chạy **mỗi lần tạo instance**.

## 4. Lỗi **trước khi** thân constructor bắt đầu: static initialization

Nếu một static field initializer hoặc static block ném exception trong quá trình class initialization, thân constructor của class đích **chưa được chạy**. Với lỗi thuộc nhóm exception thông thường không phải `Error`, JVM biểu diễn lỗi khởi tạo bằng `ExceptionInInitializerError`. Ngoại lệ gây ra lỗi có thể đọc qua `getCause()`.

Ví dụ:

~~~java
class Broken {
    static final String VALUE = fail();

    private static String fail() {
        throw new IllegalStateException("cannot load configuration");
    }

    Broken() {
        System.out.println("Broken constructor entered");
    }
}
~~~

Đoạn này chỉ minh họa. Nếu tạo instance của `Broken` lần đầu và `fail()` ném `IllegalStateException`, JVM không tới được dòng in trong constructor.

### Ví dụ đầy đủ 2: lần đầu `ExceptionInInitializerError`, lần sau `NoClassDefFoundError`

Tạo tệp **`ConstructorStaticFailureDemo.java`**:

~~~java
import java.lang.reflect.Constructor;

class BrokenInitialization {
    static final String VALUE = fail();

    private static String fail() {
        System.out.println("BrokenInitialization.<clinit>");
        throw new IllegalStateException("static boom");
    }

    BrokenInitialization() {
        System.out.println("Constructor entered");
    }
}

public class ConstructorStaticFailureDemo {
    public static void main(String[] args)
            throws ReflectiveOperationException {
        Constructor<BrokenInitialization> ctor =
                BrokenInitialization.class.getDeclaredConstructor();

        System.out.println("Broken constructor found");

        try {
            ctor.newInstance();
        } catch (ExceptionInInitializerError error) {
            System.out.println("First: "
                    + error.getClass().getSimpleName());
            System.out.println("Cause: "
                    + error.getCause().getClass().getSimpleName());
        }

        try {
            ctor.newInstance();
        } catch (NoClassDefFoundError error) {
            System.out.println("Second: "
                    + error.getClass().getSimpleName());
        }
    }
}
~~~

~~~bash
javac --release 17 ConstructorStaticFailureDemo.java
java ConstructorStaticFailureDemo
~~~

**Stdout:**

~~~text
Broken constructor found
BrokenInitialization.<clinit>
First: ExceptionInInitializerError
Cause: IllegalStateException
Second: NoClassDefFoundError
~~~

**Vì sao có hai lỗi khác nhau?**

- Dòng đầu xác nhận lấy `Constructor` **không kích hoạt** static initialization.
- Lần `newInstance` đầu tiên đưa JVM vào khởi tạo `BrokenInitialization`; `fail()` ném `IllegalStateException`. JVM báo `ExceptionInInitializerError` tại ranh giới khởi tạo class.
- Dòng `Constructor entered` **không bao giờ xuất hiện**, vì class chưa hoàn tất initialization.
- Class thất bại initialization bị đánh dấu ở trạng thái **erroneous** đối với runtime đang xét. Lần active use tiếp theo cùng class thường gặp `NoClassDefFoundError` do class không thể được khởi tạo lại theo cách đơn giản trong cùng class loader.

`NoClassDefFoundError` ở đây **không** có nghĩa bytecode hoặc file `.class` tự nhiên biến mất. Nó có thể biểu thị class đã rơi vào trạng thái lỗi khởi tạo. Để tìm nguyên nhân, phải truy ngược log/stack trace về lỗi `ExceptionInInitializerError` lần đầu, thay vì chỉ truy tìm đường dẫn classpath.

**Ngoại lệ quan trọng:** nếu static initializer ném trực tiếp một `Error` (ví dụ một `Error` cụ thể do ứng dụng tạo hoặc lỗi VM), JVM có thể truyền chính `Error` đó thay vì bọc nó trong `ExceptionInInitializerError`. Vì vậy không nên viết logic bắt lỗi class initialization chỉ dựa vào một loại wrapper trong mọi tình huống.

## 5. Lỗi **trong** constructor: `InvocationTargetException`

Khác với static initialization trước khi vào constructor, khi code bên trong constructor ném exception, `Constructor.newInstance(...)` phản ánh lỗi đó qua `java.lang.reflect.InvocationTargetException`. Exception gốc nằm trong:

~~~java
Throwable original = invocationTargetException.getCause();
~~~

Đây là **đoạn mã minh họa**. `InvocationTargetException` cho biết phép gọi phản chiếu đã đi tới code thực thi, và một throwable xuất hiện từ code được gọi; nó không mô tả đầy đủ vị trí sâu nhất của lỗi nếu constructor gọi tiếp nhiều method khác.

### Ví dụ đầy đủ 3: class khởi tạo thành công nhưng constructor ném exception

Tạo tệp **`ConstructorBodyFailureDemo.java`**:

~~~java
import java.lang.reflect.Constructor;
import java.lang.reflect.InvocationTargetException;

class FailsInConstructor {
    static {
        System.out.println("FailsInConstructor.<clinit>");
    }

    FailsInConstructor() {
        System.out.println("FailsInConstructor.<init>");
        throw new IllegalArgumentException("ctor boom");
    }
}

public class ConstructorBodyFailureDemo {
    public static void main(String[] args)
            throws ReflectiveOperationException {
        Constructor<FailsInConstructor> ctor =
                FailsInConstructor.class.getDeclaredConstructor();

        try {
            ctor.newInstance();
        } catch (InvocationTargetException error) {
            System.out.println("Wrapper: "
                    + error.getClass().getSimpleName());
            System.out.println("Cause: "
                    + error.getCause().getClass().getSimpleName());
        }
    }
}
~~~

~~~bash
javac --release 17 ConstructorBodyFailureDemo.java
java ConstructorBodyFailureDemo
~~~

**Stdout:**

~~~text
FailsInConstructor.<clinit>
FailsInConstructor.<init>
Wrapper: InvocationTargetException
Cause: IllegalArgumentException
~~~

Phân tích: static initializer chạy thành công trước. Dòng `<init>` xác nhận constructor đã bắt đầu. Chính thân constructor ném `IllegalArgumentException`, vì vậy Reflection báo `InvocationTargetException` và giữ lỗi gốc làm `cause`.

**Một constructor ném exception không nhất thiết khiến class ở trạng thái erroneous.** Class trong ví dụ đã khởi tạo static thành công; những lời gọi constructor tiếp theo có thể được thử lại, dù constructor vẫn tiếp tục ném exception do logic của nó. Điều này khác với static initialization thất bại ở phần trước.

### Lỗi trong instance field initializer hoặc constructor của superclass

"Trong constructor" theo góc nhìn `Constructor.newInstance` bao gồm cả code được chạy trong quá trình tạo đối tượng, **không chỉ** những dòng trực tiếp trong thân constructor của class đích:

- Superclass constructor ném lỗi trước khi thân subclass constructor được thực hiện.
- Instance field initializer/instance initializer block của class đích ném lỗi.
- Constructor gọi một method khác và method đó ném lỗi.
- Constructor kích hoạt lần đầu một class phụ thuộc có static initializer bị lỗi.

Trong những trường hợp throwable phát sinh sau khi việc gọi constructor phản chiếu đã bắt đầu thực thi code khởi tạo đối tượng, `InvocationTargetException` có thể bọc throwable sâu hơn, bao gồm một `ExceptionInInitializerError` từ **class phụ thuộc được khởi tạo trong constructor**. Vì vậy **phải xem toàn bộ cause chain và stack trace**, không chỉ nhìn một wrapper ngoài cùng để đoán vị trí.

## 6. Bảng phân biệt các lỗi theo thời điểm

| Lỗi | Giai đoạn điển hình | Ý nghĩa và hướng xử lý |
| --- | --- | --- |
| `NoSuchMethodException` | Tra cứu `getDeclaredConstructor(...)` | Không có constructor đúng danh sách kiểu tham số; chưa đến bước gọi |
| `IllegalAccessException` | Gọi `Constructor.newInstance(...)` khi thiếu quyền | Constructor có nhưng caller không có quyền truy cập phù hợp |
| `InaccessibleObjectException` | Gọi `setAccessible(true)` | Module đích không cho phép mở quyền sâu trong điều kiện hiện tại |
| `IllegalArgumentException` | Xác thực đối số khi `newInstance(...)` | Số lượng/loại đối số không phù hợp với signature hoặc thao tác không hợp lệ |
| `InstantiationException` | Tạo instance một kiểu không thể instantiate (ví dụ abstract class) | Constructor metadata có thể tồn tại, nhưng không thể tạo instance trực tiếp |
| `ExceptionInInitializerError` | Class initialization trước constructor, khi exception thông thường xảy ra | Xem cause của lỗi static initialization, constructor chưa bắt đầu |
| `NoClassDefFoundError` | Sử dụng class đã khởi tạo thất bại hoặc không định nghĩa được class | Xem cause/stack trace, đặc biệt log lần đầu class initialization thất bại |
| `InvocationTargetException` | Throwable từ code được gọi trong quá trình chạy constructor | Xem `getCause()` để tìm lỗi thực tế |
| `LinkageError` và một số `Error` khác | Nạp/liên kết/khởi tạo class hoặc thực thi | Có thể truyền trực tiếp; phân tích theo loại lỗi và nguyên nhân gốc |

**Đừng nhầm `NoSuchMethodException` với `NoClassDefFoundError`:** cái đầu nói lookup constructor không có chữ ký đã hỏi; cái sau liên quan đến việc class không thể được định nghĩa/khởi tạo/thực thi như yêu cầu. Cũng đừng tự động bắt `Exception` rồi cho rằng đã bắt đủ class initialization errors vì `ExceptionInInitializerError` và `NoClassDefFoundError` đều thuộc nhánh `Error` của `Throwable`.

Cả `InvocationTargetException` và `ExceptionInInitializerError` có thể xuất hiện trong cùng một chuỗi nguyên nhân ở chương trình phức tạp. Hãy phân biệt lỗi *khởi tạo chính class đang new* với lỗi *khởi tạo class phụ thuộc trong thân constructor*.

## 7. Vai trò của `Class.forName`: lỗi có thể xảy ra sớm hơn bạn nghĩ

Nếu trình tự mã là:

~~~java
Class<?> type = Class.forName("com.example.Broken");
Constructor<?> ctor = type.getDeclaredConstructor();
Object value = ctor.newInstance();
~~~

Đây là **mã minh họa** với class `com.example.Broken` giả định. `Class.forName(String)` mặc định yêu cầu khởi tạo class, nên static initializer có thể lỗi **ngay ở dòng đầu**, trước khi `getDeclaredConstructor` được gọi. Nếu mục tiêu là phân tích metadata trước khi active use, dùng overload:

~~~java
ClassLoader loader = Thread.currentThread().getContextClassLoader();

Class<?> type = Class.forName(
        "com.example.Broken", false, loader);

Constructor<?> ctor = type.getDeclaredConstructor();
// Chỉ khi gọi ctor.newInstance() mới yêu cầu class đích khởi tạo.
~~~

Đoạn này cũng là **mã minh họa**, cần class có thật, quyền Reflection hợp lệ và xử lý ngoại lệ. `initialize=false` trì hoãn **initialization** chứ không biến class lỗi thành class có thể khởi tạo thành công. Việc nạp/liên kết hoặc kiểm tra class loader vẫn có thể gặp lỗi riêng.

Không dùng phương án `Class.forName(name, false, loader)` như cơ chế bảo mật để chạy code không tin cậy; nó chỉ thay đổi thời điểm class initialization chứ không loại bỏ các tác động khi class được sử dụng về sau.

## 8. Constructor Reflection còn có thể thất bại trước khi thực thi mã ứng dụng

### Chữ ký phải khớp tuyệt đối

~~~java
Constructor<?> ctor = Example.class
        .getDeclaredConstructor(String.class, int.class);
~~~

Đoạn này chỉ hợp lệ khi `Example` khai báo constructor đúng danh sách tham số `String, int`. Reflection **không** dùng autoboxing hoặc widening để tìm constructor theo "chữ ký gần đúng":

- `int.class` khác `Integer.class`.
- `String[].class` khác `String.class`; varargs `String...` được biểu diễn là tham số mảng `String[]`.
- Parameterized type như `List<String>` chịu type erasure ở runtime và thường tra theo `List.class`.
- Constructor không được kế thừa, nên không thể tra constructor của superclass trên `Class<?>` của subclass.

Sai chữ ký làm `getDeclaredConstructor` ném `NoSuchMethodException`, ngay cả khi constructor khác có thể tạo instance hợp lệ.

### Quyền truy cập và ranh giới module

`getDeclaredConstructor` có thể trả metadata cho constructor `private`, nhưng `newInstance` còn kiểm tra truy cập. Nếu cần deep reflection, `trySetAccessible()` có thể trả `false` khi module không cho phép; `setAccessible(true)` có thể ném `InaccessibleObjectException`. Nếu caller và target cùng module, thường có thể mở quyền sâu theo quy tắc JPMS, nhưng chỉ nên làm khi có mục tiêu chính đáng và đã xử lý điều kiện thất bại.

Một pattern an toàn:

~~~java
Constructor<?> ctor = type.getDeclaredConstructor(String.class);

if (!ctor.canAccess(null) && !ctor.trySetAccessible()) {
    throw new IllegalStateException("Cannot access constructor");
}

Object instance = ctor.newInstance("demo");
~~~

Đây là **đoạn mã minh họa**, với `type` là `Class<?>` hợp lệ. `Constructor#canAccess` dùng đối số `null`. Với field/method instance sẽ dùng receiver tương ứng. Nếu code dừng ở bước kiểm tra quyền, đó **không phải** lỗi trong thân constructor.

### Kiểu không được tạo instance trực tiếp

Một abstract class có thể có constructor để subclass gọi `super(...)`, và Reflection có thể tìm metadata của constructor đó, nhưng `Constructor.newInstance` vẫn không thể tạo object trực tiếp của abstract class: có thể ném `InstantiationException`. Interface không có constructor instance để tra cứu theo cách thông thường. Constructor enum cũng chịu hạn chế riêng khi khởi tạo qua Reflection; đừng dùng `Constructor.newInstance` để tạo enum constant mới.

## 9. Cách đọc stack trace để tìm gốc lỗi

Một quy trình chẩn đoán hữu ích:

1. **Đánh dấu giai đoạn:** log sau khi có `Class<?>`, sau khi tìm `Constructor<?>`, ngay trước và ngay sau `newInstance`. Thông tin này giúp biết lỗi xảy ra ở lookup, initialization hay invocation.
2. **Phân loại throwable:** `NoSuchMethodException` ở lookup; lỗi truy cập/đối số trước khi vào code đích; `ExceptionInInitializerError` liên quan initialization; `InvocationTargetException` liên quan throwable trong việc thực thi constructor.
3. **Đi sâu vào cause:** in class name, message và `getCause()` lặp lại có giới hạn hoặc ghi đầy đủ stack trace vào log an toàn.
4. **Xác định class thực sự thất bại:** có thể là superclass, class đích hoặc class phụ thuộc được active-use trong constructor.
5. **Nếu gặp `NoClassDefFoundError` ở lần sau:** tìm log **lần sử dụng đầu tiên**; lỗi thứ hai thường chỉ là hậu quả của init failure đầu.
6. **Sửa nguyên nhân gốc:** cấu hình static, file, classpath/module path, dependency, quyền truy cập hoặc logic constructor; hạn chế retry mù quáng nếu class đã ở trạng thái erroneous.

Ví dụ đoạn mã phân loại trong ứng dụng (giả sử `ctor` đã xác định và quyền truy cập hợp lệ):

~~~java
try {
    Object instance = ctor.newInstance();
    System.out.println("Created: " + instance.getClass().getName());
} catch (java.lang.reflect.InvocationTargetException e) {
    Throwable actual = e.getCause();
    System.err.println("Constructor path failed: " + actual);
} catch (ExceptionInInitializerError e) {
    System.err.println("Class initialization failed: " + e.getCause());
} catch (NoClassDefFoundError e) {
    System.err.println("Class cannot be initialized/defined: " + e);
}
~~~

Đây là **mã minh họa chẩn đoán**, cần được đặt trong phương thức khai báo/xử lý thêm checked exceptions như `InstantiationException` và `IllegalAccessException`; nó không phải chương trình độc lập. Log thực tế phải tránh tiết lộ bí mật từ exception message hoặc stack trace nếu dữ liệu nhạy cảm.

## 10. Khởi tạo thất bại có thể được chạy lại không?

Nếu static initialization của class **thất bại**, JVM đánh dấu class ở trạng thái erroneous trong runtime định nghĩa class đó. Một lần `newInstance` thứ hai trên **chính class ấy** thường sẽ thất bại với `NoClassDefFoundError`; không có API Reflection chuẩn để "reset" trạng thái class và chạy lại static initializer của cùng `Class<?>`.

Muốn phục hồi, thường phải xử lý nguyên nhân trước khi JVM khởi tạo class (ví dụ cấu hình hợp lệ), khởi động lại tiến trình, hoặc trong kiến trúc được thiết kế đặc biệt, nạp một bản định nghĩa class mới bằng class loader khác và xử lý lifecycle tương ứng. Đừng dùng loader mới làm giải pháp chữa cháy chung vì nó có thể thay đổi danh tính kiểu và quản lý tài nguyên phức tạp hơn.

Ngược lại, nếu **constructor** ném exception sau khi class đã init thành công, class không bị đánh dấu erroneous chỉ vì constructor thất bại. Lời gọi constructor tiếp theo có thể chạy lại và có thể thành công nếu điều kiện đầu vào/trạng thái cho phép.

### Vấn đề đa luồng

Initialization của một class được JVM đồng bộ theo quy tắc riêng. Một thread khởi tạo class và thất bại thì những thread khác cần sử dụng class đó có thể nhận lỗi do class không khởi tạo được. Không nên viết logic chỉ nhìn `ExceptionInInitializerError` để xác nhận tất cả các thread đều quan sát cùng một exception wrapper. Giữ nguyên cause chain và log sự kiện đầu giúp điều tra chính xác hơn.

## 11. Liên hệ với `Class.newInstance()` cũ

`Class.newInstance()` đã deprecated từ Java 9 và có thể để ngoại lệ checked từ constructor thoát ra theo cách gây khó khăn cho kiểm tra ngoại lệ. Ưu tiên `getDeclaredConstructor().newInstance()` để chọn constructor và nhận `InvocationTargetException#getCause()` cho lỗi trong quá trình khởi tạo instance. Cả hai API vẫn tuân theo quy tắc **class phải khởi tạo thành công trước khi constructor có thể chạy**; vì vậy phải phân biệt lỗi static initialization với lỗi trong constructor.

## 12. Các lỗi suy luận thường gặp

1. **Tưởng `getDeclaredConstructor` chạy static block.** Đây là lookup metadata; active use thông qua `newInstance` hoặc `Class.forName(name)` mới có thể yêu cầu initialization.
2. **Đồng nhất `<clinit>` với `<init>`.** `<clinit>` là class initialization; `<init>` là constructor của mỗi instance.
3. **Thấy `ExceptionInInitializerError` rồi sửa constructor body.** Trước hết phải kiểm tra static field initializer/static block và initialization của superclass.
4. **Thấy `InvocationTargetException` rồi chỉ log wrapper.** Lấy `getCause()` để thấy throwable thực sự từ constructor path.
5. **Thấy `NoClassDefFoundError` rồi kết luận class file bị xóa.** Có thể class init đã thất bại trước đó; tìm log ban đầu.
6. **Cho rằng mọi init failure đều bọc `ExceptionInInitializerError`.** Lỗi thuộc nhánh `Error` có thể truyền trực tiếp.
7. **Cho rằng constructor ném exception khiến class unusable mãi mãi.** Điều này khác class initialization thất bại; một constructor call lỗi không tự biến class thành erroneous.
8. **Bắt mỗi `Exception` để xử lý mọi loại thất bại.** `ExceptionInInitializerError`, `NoClassDefFoundError` thuộc `Error`; phân loại rõ rồi để lỗi nghiêm trọng đi lên khi phù hợp.
9. **Tự động mở toàn bộ module vì constructor `private`.** Quy tắc JPMS và quyền truy cập phải được xử lý cụ thể; mở module không sửa lỗi static initialization.
10. **Retry liên tục cùng `Constructor` sau khi class init thất bại.** Việc gọi lại không reset static state; có thể chỉ tạo chuỗi `NoClassDefFoundError`.
11. **Lẫn lỗi sai tham số với lỗi bên trong constructor.** `IllegalArgumentException` do `newInstance` kiểm tra argument khác với `InvocationTargetException` có `cause` là `IllegalArgumentException` do constructor tự ném.
12. **Không để ý superclass/instance initializer.** Lỗi ở code khởi tạo object của superclass hay initializer có thể xảy ra trước dòng đầu thân constructor của subclass, dù class initialization của subclass đã thành công.

## 13. Bài tự kiểm tra

**Câu 1.** `SomeType.class.getDeclaredConstructor()` có bảo đảm static block của `SomeType` đã chạy không?

**Đáp án:** Không. Lấy metadata constructor không tự khởi tạo class đích.

**Câu 2.** Static field initializer của class đích ném `IllegalStateException` ở lần active use đầu. `Constructor.newInstance` thường biểu hiện lỗi gì?

**Đáp án:** `ExceptionInInitializerError` có `cause` là `IllegalStateException`, phát sinh trước khi constructor body bắt đầu.

**Câu 3.** Sau init failure, vì sao gọi lại cùng `Constructor.newInstance` thường ném `NoClassDefFoundError`?

**Đáp án:** JVM đánh dấu class đã khởi tạo thất bại ở trạng thái erroneous, nên không chạy lại static initializer như một lần thử mới bình thường.

**Câu 4.** Static initializer chạy thành công, nhưng constructor ném `IllegalArgumentException`. Reflection trả lỗi gì?

**Đáp án:** `InvocationTargetException`; gọi `getCause()` sẽ thấy `IllegalArgumentException`.

**Câu 5.** Nếu `Class.forName("pkg.Broken")` được gọi trước lookup constructor thì init failure xảy ra ở đâu?

**Đáp án:** Có thể nổ ngay tại `Class.forName(String)`, vì overload này mặc định yêu cầu initialization.

**Câu 6.** Constructor của class con ném lỗi từ superclass constructor trước khi subclass body bắt đầu. Có thể thấy `InvocationTargetException` không?

**Đáp án:** Có. Đường thực thi gọi constructor bao gồm bước gọi superclass constructor; `InvocationTargetException#getCause()` giúp truy ngược throwable từ quá trình khởi tạo đối tượng.

**Câu 7.** `NoSuchMethodException` khi gọi `getDeclaredConstructor(int.class)` có đồng nghĩa lỗi class initialization không?

**Đáp án:** Không. Đây là thất bại của tra cứu chữ ký constructor, xảy ra trước việc gọi constructor.

**Câu 8.** Class đã init thành công, constructor thất bại vì một input cụ thể. Có thể khởi tạo instance khác không?

**Đáp án:** Có thể nếu sửa đầu vào/điều kiện và gọi constructor lại; class không trở thành erroneous chỉ vì một constructor call thất bại.

## 14. Checklist phân tích nhanh

Khi lỗi Reflection liên quan constructor, hãy ghi lại:

- **Class đích:** tên `Class#getName()`, class loader và module khi liên quan.
- **Metadata:** constructor tìm được chưa? Chữ ký `getParameterTypes()` đúng chưa?
- **Quyền:** `canAccess(null)`, `trySetAccessible()`, khả năng giới hạn bởi JPMS.
- **Điểm lỗi:** `Class.forName`, `getDeclaredConstructor`, `newInstance` hay một lời gọi bên trong constructor?
- **Throwable ngoài cùng và gốc:** `getCause()`, stack trace đầy đủ; có `ExceptionInInitializerError`/`NoClassDefFoundError` hay `InvocationTargetException`?
- **Thời điểm:** lần active use đầu hay lần dùng tiếp theo? Static initialization đã thành công chưa?
- **Superclass và dependency:** exception thực sự bắt nguồn từ initializer/constructor nào?

**Ghi nhớ:** `getDeclaredConstructor()` tìm metadata; `Constructor.newInstance()` yêu cầu class sẵn sàng, vì vậy JVM có thể chạy `<clinit>` **trước** khi vào `<init>`. Static initialization failure thường hiện ra qua `ExceptionInInitializerError` lần đầu và `NoClassDefFoundError` sau đó; throwable từ code của constructor path thường được Reflection bọc thành `InvocationTargetException`. Luôn đọc **cause chain** để sửa đúng nơi xảy ra lỗi.
