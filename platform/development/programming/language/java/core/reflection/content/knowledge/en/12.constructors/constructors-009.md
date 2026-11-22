# Constructor ném ngoại lệ và lớp bọc `InvocationTargetException` trong Java Reflection

Khi tạo đối tượng thông qua Java Reflection, lệnh `Constructor.newInstance(...)` có thể thất bại vì **hai nhóm nguyên nhân rất khác nhau**:

1. **Constructor của ứng dụng thực sự được gọi rồi ném exception/error**. Reflection bọc đối tượng lỗi gốc trong `java.lang.reflect.InvocationTargetException`. Người gọi cần xem `getCause()` để biết vấn đề thực sự.
2. **Reflection chưa thể gọi constructor hợp lệ**, chẳng hạn sai kiểu đối số, thiếu quyền truy cập, kiểu đích là abstract class hoặc class initialization thất bại. Các trường hợp này thường được báo bằng **exception/error riêng**, không được coi mặc định là `InvocationTargetException`.

Phân biệt đúng hai nhóm này giúp lập trình viên sửa lỗi ở đúng nơi: kiểm tra dữ liệu đầu vào của constructor, giải quyết cấu hình access/module hoặc sửa logic bên trong constructor.

Mục tiêu của bài là hiểu chính xác khi nào `InvocationTargetException` xuất hiện, cách mở lớp bọc để xử lý checked/unchecked exceptions, cách nhận diện những lỗi không bị bọc, và cách viết code Java 17+ có thể biên dịch/chạy và chẩn đoán được.

## 1. Phân biệt tra cứu constructor và gọi constructor

Đối tượng `Class<T>` cung cấp:

```java
Constructor<T> ctor = type.getConstructor(parameterTypes);
Constructor<T> declared = type.getDeclaredConstructor(parameterTypes);
```

Hai lệnh trên chỉ lấy **metadata về constructor**. Chúng chưa tạo đối tượng và chưa chạy thân constructor. `getConstructor` chỉ tìm constructor **public** có đúng dãy kiểu tham số; `getDeclaredConstructor` tìm constructor khai báo trực tiếp ở lớp, kể cả constructor private.

Việc tạo instance xảy ra khi gọi:

```java
T instance = ctor.newInstance(arguments);
```

Đây là mẫu code mô tả ý tưởng; `T`, `type`, `parameterTypes` và `arguments` phải được định nghĩa trong chương trình thực. Hai loại vấn đề cần tách riêng:

- **Lookup thất bại:** `getConstructor(String.class)` không tìm được chữ ký public phù hợp thì ném `NoSuchMethodException`. Lúc đó constructor chưa chạy.
- **Invocation thất bại:** sau khi tìm được metadata, `newInstance("abc")` mới thử khởi tạo class (nếu cần), kiểm tra quyền/đối số và thực thi constructor. Khi **chính constructor** ném lỗi, Reflection phát ra `InvocationTargetException` bọc lỗi gốc.

Đối tượng `Constructor<T>` thuộc gói `java.lang.reflect`. Phương thức `newInstance(Object... initargs)` có kiểu trả về `T`, nhưng không có nghĩa là lời gọi chắc chắn thành công hoặc mọi vấn đề đều có cùng loại exception.

## 2. Vì sao Java Reflection cần `InvocationTargetException`?

Một constructor có thể khai báo và ném checked exception:

```java
public Person(String name) throws java.io.IOException {
    if (name == null) {
        throw new java.io.IOException("name is required");
    }
}
```

Nếu gọi trực tiếp `new Person(null)`, caller phải xử lý hoặc khai báo `IOException` theo cơ chế checked exception của Java. Nhưng khi Reflection gọi `Constructor.newInstance(...)`, chữ ký API không thể liệt kê trước mọi checked exception mà **bất kỳ constructor runtime nào** có thể ném ra.

Vì vậy, nếu constructor thực thi rồi ném `IOException`, `IllegalArgumentException`, `AssertionError` hoặc một `Throwable` khác từ thân constructor, Reflection báo một **`InvocationTargetException`**, trong đó giữ lỗi ban đầu làm **cause**.

Mô hình:

```text
Constructor.newInstance(arguments)
          |
          +-- chuẩn bị/check access, tham số, kiểu, class initialization
          |
          +-- gọi constructor <init>
                    |
                    +-- chạy thành công ----------> trả instance
                    |
                    +-- ném IOException ----------> InvocationTargetException
                    |                                  cause = IOException
                    +-- ném IllegalStateException -> InvocationTargetException
                    |                                  cause = IllegalStateException
                    +-- ném AssertionError --------> InvocationTargetException
                                                       cause = AssertionError
```

Sơ đồ mô tả **lỗi phát sinh trong constructor đã được gọi**. Exception hoặc error phát sinh trong **bước Reflection trước đó**, đặc biệt lỗi class initialization, có quy tắc riêng và không được gộp vào nhánh bọc trên.

### Hai thuộc tính của lớp bọc

`InvocationTargetException` là **checked exception**. Nó có:

- `getCause()`: trả `Throwable` gốc gây ra invocation thất bại.
- `getTargetException()`: phương thức tương thích lịch sử, cũng cho phép truy cập exception gốc. Trong code hiện đại, thường ưu tiên `getCause()`.

Ví dụ mẫu:

```java
try {
    Object instance = constructor.newInstance(values);
} catch (java.lang.reflect.InvocationTargetException e) {
    Throwable original = e.getCause();
    // Phân tích original để biết lỗi thực tế từ constructor.
}
```

Đây là đoạn minh họa; `constructor` và `values` có sẵn từ caller, và các checked exception khác của `newInstance` cần được xử lý hoặc khai báo bổ sung. Không chỉ in `InvocationTargetException` rồi bỏ qua `cause`, vì lỗi nghiệp vụ chính thường nằm ở lớp trong.

## 3. Ví dụ Java 17+ hoàn chỉnh: phân biệt nhiều loại lỗi

Lưu chương trình thành **`ConstructorExceptionDemo.java`**:

```java
import java.io.IOException;
import java.lang.reflect.Constructor;
import java.lang.reflect.InvocationTargetException;

public class ConstructorExceptionDemo {
    public static class Worker {
        private final String name;

        public Worker(String name) throws IOException {
            if (name == null) {
                throw new IOException("name is required");
            }
            if (name.isBlank()) {
                throw new IllegalArgumentException("blank name");
            }
            if (name.equals("error")) {
                throw new AssertionError("fatal problem");
            }
            this.name = name;
        }

        public String getName() {
            return name;
        }
    }

    public abstract static class AbstractWorker {
        public AbstractWorker() { }
    }

    public static class BrokenInit {
        static {
            if (shouldFail()) {
                throw new IllegalStateException("init failed");
            }
        }

        static boolean shouldFail() {
            return true;
        }

        public BrokenInit() { }
    }

    private static void printCause(String label, InvocationTargetException e) {
        Throwable cause = e.getCause();
        System.out.println(label + ": "
                + cause.getClass().getSimpleName()
                + " -> " + cause.getMessage());
    }

    public static void main(String[] args) throws Exception {
        Constructor<Worker> ctor = Worker.class.getConstructor(String.class);

        System.out.println("throws declared: "
                + ctor.getExceptionTypes()[0].getSimpleName());
        System.out.println("success: " + ctor.newInstance("Lan").getName());

        try {
            ctor.newInstance((Object) null);
        } catch (InvocationTargetException e) {
            printCause("checked", e);
        }

        try {
            ctor.newInstance(" ");
        } catch (InvocationTargetException e) {
            printCause("unchecked", e);
        }

        try {
            ctor.newInstance("error");
        } catch (InvocationTargetException e) {
            printCause("error", e);
        }

        try {
            ctor.newInstance(5);
        } catch (IllegalArgumentException e) {
            System.out.println("argument mismatch: "
                    + e.getClass().getSimpleName());
        }

        try {
            Worker.class.getConstructor(int.class);
        } catch (NoSuchMethodException e) {
            System.out.println("lookup failure: "
                    + e.getClass().getSimpleName());
        }

        Constructor<AbstractWorker> abstractCtor =
                AbstractWorker.class.getConstructor();
        try {
            abstractCtor.newInstance();
        } catch (InstantiationException e) {
            System.out.println("abstract: "
                    + e.getClass().getSimpleName());
        }

        Constructor<BrokenInit> brokenCtor =
                BrokenInit.class.getConstructor();
        try {
            brokenCtor.newInstance();
        } catch (ExceptionInInitializerError e) {
            Throwable root = e.getCause();
            System.out.println("class initialization: "
                    + root.getClass().getSimpleName()
                    + " -> " + root.getMessage());
        }
    }
}
```

Chạy từ thư mục chứa tệp với JDK 17 hoặc mới hơn:

```bash
javac ConstructorExceptionDemo.java
java ConstructorExceptionDemo
```

**Stdout đã đối chiếu bằng JDK 21:**

```text
throws declared: IOException
success: Lan
checked: IOException -> name is required
unchecked: IllegalArgumentException -> blank name
error: AssertionError -> fatal problem
argument mismatch: IllegalArgumentException
lookup failure: NoSuchMethodException
abstract: InstantiationException
class initialization: IllegalStateException -> init failed
```

### Phân tích từng kết quả

1. `getExceptionTypes()` liệt kê những loại exception có trong khai báo `throws` của constructor. `Worker(String)` khai báo `IOException`, nên dòng đầu in `IOException`. Metadata này **không có nghĩa constructor luôn ném exception**.
2. `ctor.newInstance("Lan")` gọi constructor thành công; chương trình nhận một instance và in `success: Lan`.
3. `ctor.newInstance((Object) null)` truyền **một đối số `null`** vào tham số `String`. Constructor được gọi, kiểm tra `name == null` và ném `IOException`. Reflection bọc nó trong `InvocationTargetException`. `getCause()` lấy lại `IOException` cùng thông điệp.
4. `ctor.newInstance(" ")` gọi được constructor; `isBlank()` trả `true`, nên constructor ném unchecked `IllegalArgumentException`. Vì lỗi xuất phát **bên trong constructor**, Reflection vẫn bọc trong `InvocationTargetException`.
5. `ctor.newInstance("error")` khiến chính constructor ném `AssertionError`. Trong ví dụ này, `InvocationTargetException` cũng bọc `AssertionError`: lớp bọc không chỉ áp dụng cho checked exceptions. Không nên tự động bắt rồi bỏ qua mọi `Error` trong ứng dụng sản xuất.
6. `ctor.newInstance(5)` có **kiểu đối số không phù hợp** với constructor `Worker(String)`. Reflection ném `IllegalArgumentException` ngay ở tầng invocation; thân constructor không chạy. Đây **không phải** `InvocationTargetException`.
7. `Worker.class.getConstructor(int.class)` thất bại tại **bước tra cứu** vì không tồn tại constructor public `Worker(int)`. Kết quả là `NoSuchMethodException`.
8. `AbstractWorker` có constructor public nhưng là **abstract class**; Reflection không thể tạo instance trực tiếp nên `Constructor.newInstance()` ném `InstantiationException`.
9. `BrokenInit` có khối static initializer ném `IllegalStateException`. Class initialization thất bại **trước khi thân constructor chạy**. JVM phát ra `ExceptionInInitializerError`; không nên nhầm với `InvocationTargetException`.

Trong ví dụ, các class con được khai báo `public static` và constructor cần thiết là public, tránh nhiễu từ lỗi visibility. Lỗi quyền truy cập sẽ được giải thích riêng.

## 4. Bảng nhận diện: lỗi đến từ lớp nào?

| Điểm xảy ra lỗi | Tình huống | Lỗi quan sát được | Có `InvocationTargetException` bọc không? |
|---|---|---|---|
| Tra cứu trên `Class` | Constructor phù hợp không tồn tại | `NoSuchMethodException` | Không |
| Chuẩn bị invocation | Số lượng/kiểu đối số không phù hợp | `IllegalArgumentException` | Không |
| Chuẩn bị invocation | Caller không có quyền gọi constructor | `IllegalAccessException` | Không |
| Chuẩn bị invocation | Không thể tạo instance của abstract class | `InstantiationException` | Không |
| Khởi tạo class | Static initializer thất bại do exception không phải `Error` | `ExceptionInInitializerError` | Không |
| Trong thân constructor | `throw new IOException(...)` | `InvocationTargetException`, cause = `IOException` | Có |
| Trong thân constructor | `throw new IllegalStateException(...)` | `InvocationTargetException`, cause = `IllegalStateException` | Có |
| Trong thân constructor | `throw new AssertionError(...)` | `InvocationTargetException`, cause = `AssertionError` | Có |

Bảng phản ánh các trường hợp thông thường qua **core Reflection**. Trường hợp class initialization ném trực tiếp một `Error`, JVM có thể truyền tiếp error đó theo quy tắc initialization; lỗi khởi tạo lặp lại của cùng runtime class về sau thường là `NoClassDefFoundError`. Không có bảo đảm rằng mọi lỗi trước constructor đều là `ExceptionInInitializerError`.

**Đặc biệt về `IllegalArgumentException`:** tên exception giống nhau nhưng nguồn lỗi khác nhau tạo ra hai cách bắt khác nhau:

```java
// Sai kiểu đối số: Reflection tự ném IllegalArgumentException.
ctor.newInstance(Integer.valueOf(5));

// Đối số hợp lệ là String nhưng constructor tự ném
// IllegalArgumentException: Reflection bọc trong InvocationTargetException.
ctor.newInstance(" ");
```

Hai dòng trên là ví dụ trích từ chương trình hoàn chỉnh, không được chạy nối tiếp mà thiếu xử lý ngoại lệ. Để kết luận lỗi đến từ đâu, hãy dựa vào **kiểu exception bên ngoài** và **cause**, không chỉ nhìn tên `IllegalArgumentException` xuất hiện trong stack trace.

## 5. `getCause()`: xem lỗi gốc mà không làm mất thông tin

Khi bắt `InvocationTargetException`, gọi:

```java
catch (InvocationTargetException e) {
    Throwable cause = e.getCause();
    cause.printStackTrace();
}
```

Đây là nhánh `catch` minh họa đặt trong một khối `try` thích hợp. `printStackTrace()` giúp thấy **đường đi lỗi bên trong constructor**; không cần in đồng thời nhiều bản stack trace giống nhau vào log. Trong ứng dụng thực tế, có thể log `e` đầy đủ để JVM hiển thị chuỗi `Caused by`.

Dùng `Throwable` cho cause vì code constructor có thể ném **checked exception, unchecked exception hoặc `Error`**. Không cast cứng mọi cause thành `Exception` nếu chưa kiểm tra kiểu.

`InvocationTargetException.getTargetException()` cũng trả exception gốc, nhưng `getCause()` tuân theo mô hình exception chaining chuẩn của Java, thuận tiện cho logging và các hệ thống xử lý `Throwable`.

### Giữ lại chuỗi cause khi báo lỗi lên tầng trên

Nếu ứng dụng muốn đổi lỗi thành một exception có ngữ cảnh:

```java
try {
    return ctor.newInstance(value);
} catch (InvocationTargetException e) {
    throw new IllegalStateException(
            "Failed to create " + ctor.getDeclaringClass().getName(),
            e.getCause());
}
```

Đây là đoạn **minh họa nằm trong một phương thức factory** với `ctor` và `value` đã có, cùng xử lý/khai báo các exception Reflection khác. Constructor `IllegalStateException(String, Throwable)` giữ **original cause**; khi đọc stack trace vẫn truy ngược được lỗi gốc.

Việc wrap lại là **quyết định hợp đồng API**. Với lỗi nghiệp vụ dự kiến (ví dụ dữ liệu người dùng không hợp lệ), một số API muốn truyền lại đúng loại exception đã được kiểm tra. Với `Error` nghiêm trọng, thường không nên biến nó thành lỗi nghiệp vụ bình thường rồi tiếp tục chạy.

### Không tự tin rằng `getCause()` là lỗi cuối cùng

Constructor có thể gọi service khác và nhận một exception vốn đã bọc exception sâu hơn, ví dụ `IllegalStateException` có cause là `IOException`. Khi ấy:

```text
InvocationTargetException
└── IllegalStateException
    └── IOException
```

`getCause()` một lần chỉ mở **lớp bọc Reflection**. Muốn điều tra tận cùng, xem toàn bộ cause chain và cả suppressed exceptions nếu có. Không mặc định rằng vòng lặp bóc đến cuối luôn là cách xử lý nghiệp vụ đúng; có thể lớp exception trung gian mang thông tin quan trọng.

## 6. Checked exception và unchecked exception trong constructor

Sự khác nhau giữa **khai báo `throws`** và **lỗi thực tế** là điểm rất quan trọng:

```java
public Worker(String name) throws IOException {
    if (name == null) throw new IOException("name is required");
    if (name.isBlank()) throw new IllegalArgumentException("blank name");
    this.name = name;
}
```

- `IOException` là checked exception: khai báo trong `throws IOException`, được phản ánh bởi `Constructor.getExceptionTypes()`.
- `IllegalArgumentException` là unchecked exception: không bắt buộc phải xuất hiện trong `throws`, nhưng constructor vẫn có thể ném nó.
- Cả hai loại đều thành `InvocationTargetException` ở **lớp ngoài** khi constructor được gọi bằng `Constructor.newInstance`.
- `getExceptionTypes()` chỉ là **metadata khai báo**, không phải danh sách bảo đảm đầy đủ mọi lỗi thực sự có thể xuất hiện. Nó không dự đoán đường đi code nào sẽ chạy.

Một constructor cũng có thể gọi một constructor khác qua `this(...)` hoặc `super(...)`. Nếu constructor ở chuỗi ấy ném exception, việc khởi tạo instance thất bại. Khi lời gọi Reflection bắt nguồn từ `Constructor.newInstance` và ngoại lệ được phát sinh trong luồng thực thi constructor, exception được đưa ra trong lớp bọc `InvocationTargetException`.

Vì thế, khi chẩn đoán **tại sao `newInstance` thất bại**, cần xem phần code thực sự chạy trong constructor, bao gồm field initializers, instance initializer blocks và các lời gọi constructor liên quan, thay vì chỉ nhìn dòng `return` hoặc `throws` ở lớp ngoài.

## 7. Phân biệt lỗi class initialization và lỗi constructor

Java có hai loại initialization dễ nhầm:

- **Class initialization:** thực hiện static field initializers và các khối `static` (`<clinit>`). Nó diễn ra theo quy tắc JVM khi class được sử dụng chủ động, trước khi tạo instance của class.
- **Instance/constructor initialization:** thực hiện quy trình khởi tạo object, instance field initializers và constructor (`<init>`) trong thứ tự Java quy định.

Ví dụ `BrokenInit` trong chương trình có static initializer thất bại. Chỉ lấy metadata:

```java
Constructor<BrokenInit> constructor =
        BrokenInit.class.getConstructor();
```

thông thường **chưa chủ động khởi tạo `BrokenInit`**. Nhưng:

```java
constructor.newInstance();
```

yêu cầu tạo instance, nên JVM phải bảo đảm class được khởi tạo trước. Nếu static initializer thất bại do `IllegalStateException`, JVM phát ra `ExceptionInInitializerError`; constructor `BrokenInit()` **chưa chạy**. Đây là lỗi class initialization, không phải exception từ thân constructor đã gọi.

Lần truy cập chủ động tiếp theo vào cùng class sau khi initialization đã thất bại có thể gây `NoClassDefFoundError` vì class ở trạng thái erroneous. Không nên retry liên tục cùng runtime class và kỳ vọng khối static sẽ tự chạy lại như chưa từng thất bại.

Một tình huống khác: constructor bắt đầu chạy nhưng instance field initializer hoặc superclass constructor ném lỗi; thông thường Reflection sẽ bọc lỗi đó trong `InvocationTargetException` vì lỗi phát sinh trong quá trình thực thi khởi tạo instance. Khi chẩn đoán cần xem **stack trace của cause** để xác định vị trí thực.

## 8. `Class.newInstance()` khác `Constructor.newInstance()` ở điểm gì?

Đừng dùng tên giống nhau để suy ra hành vi exception giống nhau:

| API | Tình trạng | Cách xử lý exception từ constructor |
|---|---|---|
| `Constructor<T>.newInstance(Object... initargs)` | API Reflection hiện hành, cho phép chọn constructor theo chữ ký | Bọc exception do constructor ném trong `InvocationTargetException` |
| `Class<T>.newInstance()` | **Deprecated** từ Java 9; không nên dùng cho code mới | Có thể truyền trực tiếp exception từ constructor, kể cả checked exception không được thể hiện rõ trong `throws` của API |

`Class.newInstance()` là API cũ chỉ dùng constructor không tham số có thể truy cập và có nhiều hạn chế. Java API documentation khuyến nghị dùng `getDeclaredConstructor().newInstance()` thay thế để có lựa chọn constructor và xử lý exception rõ ràng.

Điều đó có nghĩa:

```java
Sample obj = Sample.class.getDeclaredConstructor().newInstance();
```

là cách thường dùng cho code mới khi cần constructor không tham số (giả định có constructor phù hợp và caller được phép sử dụng). Nhưng `getDeclaredConstructor()` tìm được metadata **không đồng nghĩa** mọi constructor private đều được phép gọi qua các module; access rules vẫn được áp dụng.

Khi nâng cấp framework cũ đang dùng `Class.newInstance()`, cần rà soát cách xử lý exception vì lớp bọc của API mới khác API cũ. Không chỉ đổi tên hàm mà giữ nguyên logic catch một cách máy móc.

## 9. Quyền truy cập, constructor private và ranh giới module

`InvocationTargetException` không có nghĩa “constructor bị private”:

- `getConstructor(...)` chỉ tìm constructor `public`. Với constructor private, lookup có thể ném `NoSuchMethodException`.
- `getDeclaredConstructor(...)` có thể tìm constructor private, nhưng khi gọi `newInstance`, caller có thể gặp `IllegalAccessException`.
- `trySetAccessible()` hoặc `setAccessible(true)` có thể cho phép suppress access checks **khi quan hệ class/module cho phép**. Với Java named modules, deep reflection qua package có thể yêu cầu `opens` phù hợp; `setAccessible(true)` có thể ném `InaccessibleObjectException` nếu không được phép mở.
- `abstract` class không thể được tạo instance chỉ vì constructor của nó là public; `InstantiationException` vẫn là lỗi phù hợp.
- Constructor có thể nhận số lượng đối số đúng nhưng **sai kiểu**. Khi không có conversion Reflection hợp lệ, `IllegalArgumentException` phát sinh trước khi thân constructor được gọi.

Vì thế, catch `InvocationTargetException` phải dành cho **lỗi từ quá trình thực thi constructor**, còn lỗi lookup/access/type/instantiation cần chẩn đoán riêng.

### Với constructor varargs, tránh nhầm một đối số `null` và mảng varargs `null`

`Constructor.newInstance` có chữ ký `Object... initargs`. Để truyền **một đối số `null`** cho constructor `Worker(String)`, dùng:

```java
ctor.newInstance((Object) null);
```

Cast `(Object)` làm rõ rằng đây là **một argument**, thay vì một giá trị `null` có thể được hiểu như toàn bộ mảng varargs. Vì ví dụ `Worker(String)` nhận `String` reference, `null` là argument đúng kiểu; constructor sẽ chạy và tự ném `IOException`.

Nếu truyền đối số primitive là `null` hoặc số lượng/kiểu đối số không phù hợp với chữ ký constructor, Reflection có thể báo `IllegalArgumentException` trước khi chạy thân constructor. Không tự suy ra lỗi ấy đã được bọc.

## 10. Thiết kế xử lý lỗi trong factory/framework

Một factory có thể cần quy tắc rõ ràng:

1. Chọn constructor bằng parameter types **chính xác**.
2. Kiểm tra quyền truy cập của caller/module.
3. Validate dữ liệu trước khi invoke nếu có hợp đồng đầu vào.
4. Gọi `newInstance`.
5. Nếu gặp `InvocationTargetException`, xem `getCause()` để xử lý lỗi từ constructor.
6. Xử lý riêng các lỗi lookup, access, illegal argument, abstract class và class initialization.

Mẫu xử lý có kiểm soát cho một constructor public nhận `String` (đoạn này là **phương thức minh họa**, có thể đặt vào class phù hợp):

```java
import java.lang.reflect.Constructor;
import java.lang.reflect.InvocationTargetException;

static <T> T construct(Class<T> type, String name) {
    final Constructor<T> ctor;
    try {
        ctor = type.getConstructor(String.class);
    } catch (NoSuchMethodException e) {
        throw new IllegalArgumentException(
                "No public constructor(String) in " + type.getName(), e);
    }

    try {
        return ctor.newInstance(name);
    } catch (InvocationTargetException e) {
        Throwable cause = e.getCause();

        if (cause instanceof Error error) {
            throw error;
        }
        if (cause instanceof RuntimeException runtime) {
            throw runtime;
        }
        throw new IllegalStateException(
                "Checked exception from constructor of " + type.getName(),
                cause);
    } catch (InstantiationException | IllegalAccessException e) {
        throw new IllegalStateException(
                "Cannot instantiate " + type.getName(), e);
    }
}
```

**Lưu ý:** Khối code trên là **mẫu phương thức đặt trong một class**, không phải chương trình độc lập; phần import cần ở đầu tệp. Đoạn mẫu định nghĩa một hợp đồng cụ thể: phát lại `Error` và unchecked `RuntimeException`, bọc checked exception vào `IllegalStateException`. Đây là một lựa chọn thiết kế, **không phải quy tắc bắt buộc** cho mọi framework. `IllegalArgumentException` do đối số Reflection sai có thể đi ra ngoài; nếu cần thông báo riêng, thêm nhánh bắt và ngữ cảnh phù hợp.

Đối với API có checked exceptions được công bố công khai, có thể muốn giữ đúng loại checked exception theo hợp đồng thay vì bọc thành `IllegalStateException`. Trong trường hợp đó, phải xử lý type/throws của phương thức gọi theo ngôn ngữ Java, không cast `Throwable` tùy tiện.

Không nên:

```java
catch (Exception e) {
    return null;
}
```

Đây là **mẫu sai chỉ để minh họa**. Nó gom cả lỗi không tìm được constructor, lỗi quyền truy cập và lỗi nghiệp vụ vào cùng một giá trị `null`, làm mất thông tin chẩn đoán. Nếu một factory có semantics trả optional/nullable khi không tạo được object, nó vẫn cần phân biệt lỗi nào thuộc diện xử lý dự kiến.

## 11. Kiểm thử constructor thất bại

Khi viết test cho Reflection, hãy kiểm chứng **lớp ngoài và cause**:

```java
// Minh họa dạng assertion với JUnit 5;
// đặt trong test method, có import và dependency JUnit phù hợp.
InvocationTargetException thrown = assertThrows(
        InvocationTargetException.class,
        () -> ctor.newInstance((Object) null)
);
assertInstanceOf(java.io.IOException.class, thrown.getCause());
assertEquals("name is required", thrown.getCause().getMessage());
```

Đây là đoạn test minh họa, **không thuộc chương trình Java chạy độc lập ở mục 3**. `ctor` là `Constructor<Worker>` đã tra cứu, còn `assertThrows`, `assertInstanceOf`, `assertEquals` là API của JUnit Jupiter. Test giúp phân biệt chính xác “Reflection không gọi được” với “constructor đã chạy và báo lỗi”.

Các test có giá trị thực tế gồm: constructor thành công; checked exception từ thân constructor; unchecked exception; lỗi sai argument Reflection; constructor không tồn tại; access bị chặn; class initialization thất bại. Đối với `Error`, tránh nuốt lỗi một cách vô tình và giữ khả năng đọc cause chain.

## 12. Những nhầm lẫn thường gặp

1. **“Mọi exception từ `Constructor.newInstance` đều nằm trong `InvocationTargetException`.”** Sai. Lỗi tham số, access, abstract type và class initialization có đường báo lỗi riêng.
2. **“`InvocationTargetException` là lỗi gốc của constructor.”** Sai. Nó là lớp bọc Reflection; dùng `getCause()` để xem lỗi gốc.
3. **“Constructor ném unchecked exception thì Reflection ném thẳng exception đó.”** Sai với `Constructor.newInstance`: lỗi trong thân constructor thường được bọc dù là checked hay unchecked.
4. **“`IOException` nằm trong `getExceptionTypes()` nghĩa là constructor chắc chắn thất bại.”** Sai. Đó chỉ là các loại được khai báo trong `throws`.
5. **“Sai đối số cũng được bọc như lỗi constructor.”** Sai. Sai kiểu/số lượng đối số có thể gây `IllegalArgumentException` từ tầng Reflection trước khi constructor chạy.
6. **“`NoSuchMethodException` và `InvocationTargetException` giống nhau.”** Sai. Một lỗi là **không tìm được metadata**, một lỗi là **constructor được gọi rồi ném lỗi**.
7. **“`getDeclaredConstructor` luôn gọi được private constructor.”** Sai. Metadata không tự vượt qua Java/JPMS access checks.
8. **“Khối static ném exception thì lỗi đó nằm trong `InvocationTargetException`.”** Không mặc định. Class initialization thất bại xảy ra trước constructor, thường cho `ExceptionInInitializerError` hoặc error theo quy tắc JVM.
9. **“`Class.newInstance()` và `Constructor.newInstance()` có cùng xử lý checked exceptions.”** Sai. `Class.newInstance()` là API deprecated với hành vi lan truyền exception khác.
10. **“Catch lỗi rồi trả `null` là đủ.”** Dễ làm mất nguyên nhân và che lỗi quan trọng. Giữ type/cause hoặc cung cấp lỗi API rõ ràng.

## 13. Câu hỏi tự kiểm tra

**Câu 1.** Constructor `public Service(String x)` ném `IllegalStateException("bad")` trong thân. Caller gọi qua `Constructor.newInstance("x")` gặp exception ngoài cùng nào?

**Đáp án:** `InvocationTargetException`. `getCause()` cho `IllegalStateException` chứa thông điệp `bad`.

**Câu 2.** `Service.class.getConstructor(int.class)` không tìm thấy constructor tương ứng. Lỗi nào phát sinh?

**Đáp án:** `NoSuchMethodException` tại lookup. Không có constructor nào được gọi; không có `InvocationTargetException`.

**Câu 3.** `Constructor<Service>` nhận `String`, nhưng người gọi truyền `Integer`. Có bắt buộc vào constructor rồi ném lỗi không?

**Đáp án:** Không. Reflection nhận diện argument không tương thích và có thể ném `IllegalArgumentException` trước khi gọi constructor.

**Câu 4.** Constructor khai báo `throws IOException` nhưng nhận dữ liệu hợp lệ và hoàn tất. Reflection có tự tạo `InvocationTargetException` vì có khai báo `throws` không?

**Đáp án:** Không. Constructor chạy thành công thì `newInstance` trả instance. `InvocationTargetException` chỉ phát sinh khi constructor thực sự ném lỗi.

**Câu 5.** Static initializer thất bại trước khi constructor chạy. Có chắc `InvocationTargetException` là lớp ngoài cùng không?

**Đáp án:** Không. Nếu static initializer ném một exception không thuộc `Error`, JVM thường phát `ExceptionInInitializerError`; class initialization khác với thực thi thân constructor.

**Câu 6.** Khi bắt `InvocationTargetException`, muốn log đúng lỗi gốc và vẫn giữ cause chain thì làm thế nào?

**Đáp án:** Đọc `getCause()`, log đầy đủ Throwable/stack trace và khi bọc lại hãy truyền cause vào constructor của exception mới. Không chỉ log `e.getMessage()` rồi bỏ cause.

## Tài liệu chuẩn

- Java SE API — `java.lang.reflect.Constructor.newInstance(Object...)`: exception contract cho `InstantiationException`, `IllegalAccessException`, `IllegalArgumentException`, `InvocationTargetException`, `ExceptionInInitializerError`.
- Java SE API — `java.lang.reflect.InvocationTargetException`: `getCause()`, `getTargetException()`.
- Java SE API — `java.lang.reflect.Constructor.getExceptionTypes()`, `getGenericExceptionTypes()`, `getDeclaringClass()`.
- Java SE API — `java.lang.Class.getConstructor`, `getDeclaredConstructor`, và `Class.newInstance()` (deprecated).
- Java Language Specification — §12.4 *Initialization of Classes and Interfaces*, §12.5 *Creation of New Class Instances*, §11 *Exceptions*.
- Java Virtual Machine Specification — §5.5 *Initialization*, quy tắc class initialization failure.

**Ghi nhớ:** `Constructor.newInstance` bọc **lỗi do constructor thực thi ném ra** trong `InvocationTargetException`; hãy đọc `getCause()` để thấy nguyên nhân. Lỗi tra cứu constructor, kiểm tra đối số, access, abstract class và class initialization là **những trường hợp khác**, phải chẩn đoán theo exception thực tế thay vì gộp chung thành lỗi constructor.