# Vì sao không dùng `Class.newInstance()` đã lỗi thời?

## 1. Mục tiêu học tập

Khi học Reflection, chúng ta thường gặp đoạn mã tạo object theo tên class:

```java
Class<?> type = Class.forName("com.example.Plugin");
Object instance = type.newInstance();
```

Lệnh `Class.newInstance()` ở dòng thứ hai **đã bị đánh dấu deprecated từ Java 9**. Java 17 vẫn có phương thức này để tương thích mã cũ, nhưng code mới nên dùng `Constructor<T>.newInstance(...)` qua một đối tượng `java.lang.reflect.Constructor<T>`.

Điểm cốt lõi không chỉ là cảnh báo deprecated. `Class.newInstance()` có ba hạn chế quan trọng:

1. **Chỉ gọi constructor không đối số**; không có cách truyền tham số khởi tạo.
2. **Có thể phát tán trực tiếp checked exception từ constructor**, trong khi chữ ký `Class.newInstance()` không khai báo exception đó. Đây là vấn đề an toàn kiểm tra ngoại lệ tại compile time.
3. **Không cho phép quản lý một constructor cụ thể**: khó kiểm tra signature, parameter types, annotations, modifiers và cân nhắc truy cập non-public constructor. API `Constructor` diễn đạt rõ hơn quy trình tìm, kiểm tra quyền rồi gọi constructor.

Cách thay thế cơ bản theo tài liệu Java 17:

```java
T object = clazz.getDeclaredConstructor().newInstance();
```

Ở đây `clazz` có kiểu `Class<T>`. `getDeclaredConstructor()` tìm constructor không tham số **khai báo bởi chính lớp**, `newInstance()` mới thực sự tạo instance. Cần xử lý `NoSuchMethodException` và `InvocationTargetException` cùng các lỗi Reflection có thể phát sinh. Không nên hiểu đoạn thay thế là mở quyền cho mọi constructor private; vấn đề truy cập vẫn phải xử lý riêng.

## 2. `Class.newInstance()` thực sự làm gì?

Chữ ký của phương thức cũ:

```java
@Deprecated(since = "9")
public T newInstance()
        throws InstantiationException, IllegalAccessException
```

`Class<T>.newInstance()` cố tạo một đối tượng thuộc class được biểu diễn bởi `Class<T>` thông qua **constructor không đối số** có thể truy cập được từ caller. Nếu lớp chưa được khởi tạo, lời gọi sẽ kích hoạt quá trình khởi tạo lớp khi cần.

Điều cần nhớ:

- `Class.newInstance()` **không phải** `Constructor.newInstance()`. Hai phương thức cùng tên nhưng thuộc hai kiểu khác nhau và có quy tắc exception khác nhau.
- Không thể truyền tên, id, service, configuration hoặc các constructor arguments khác vào `Class.newInstance()`.
- Nếu lớp không có constructor không đối số thích hợp, phương thức cũ thường ném `InstantiationException`. Với API mới, thiếu constructor khi tra cứu sẽ được biểu diễn rõ bằng `NoSuchMethodException`.
- Nếu lớp hoặc constructor không thể truy cập, phương thức cũ có thể ném `IllegalAccessException`.
- Nếu constructor tự ném checked exception, phương thức cũ **phát tán trực tiếp ngoại lệ đó** dù chữ ký chỉ khai báo hai loại checked exception ở trên.

`@Deprecated(since = "9")` là thông báo **không nên tiếp tục sử dụng API này trong code mới**. Deprecated không đồng nghĩa nó đã bị xóa khỏi JDK 17, cũng không có nghĩa mọi lời gọi cũ lập tức thất bại. Nhưng code mới nên dùng phương án được Java SE khuyến nghị.

## 3. Vấn đề nghiêm trọng nhất: phá vỡ kiểm tra checked exception

### 3.1. Checked exception thông thường

Java yêu cầu code xử lý hoặc khai báo checked exception mà compiler nhận biết được từ chữ ký phương thức và constructor.

Ví dụ một constructor hợp lệ:

```java
import java.io.IOException;

class Loader {
    public Loader() throws IOException {
        throw new IOException("resource unavailable");
    }
}
```

Lời gọi trực tiếp `new Loader()` yêu cầu caller xử lý hoặc khai báo `IOException`. Đây là bảo đảm quan trọng: compiler buộc chương trình nhận biết trường hợp tạo đối tượng có thể thất bại vì I/O.

### 3.2. Lỗ hổng của phương thức cũ

Giả sử code sau chạy với `Class<Loader>`:

```java
@SuppressWarnings("deprecation")
static Loader legacyCreate()
        throws InstantiationException, IllegalAccessException {
    return Loader.class.newInstance();
}
```

**Đây là ví dụ minh họa cần ghép với khai báo `Loader` phía trên.** Nó có thể biên dịch dù không `catch` và không `throws IOException`, bởi compiler chỉ thấy chữ ký `Class.newInstance()` khai báo `InstantiationException` và `IllegalAccessException`.

Khi constructor thực thi và ném `IOException`, `Class.newInstance()` có thể phát tán chính đối tượng exception đó ra ngoài. Nghĩa là runtime có thể ném **`IOException` mà phương thức `legacyCreate()` không khai báo**.

Kết quả không phải `InvocationTargetException`. Chính hành vi này khiến code có thể bỏ qua cơ chế kiểm tra checked exception của Java. Nó làm thiết kế hợp đồng lỗi của factory/helper khó dự đoán và dễ gây nhầm lẫn khi đọc code.

Một lưu ý về kỹ thuật thử lỗi: Nếu bạn muốn chứng minh trực tiếp việc phát tán exception từ code cũ, có thể dùng `catch (Exception e)` hoặc xử lý `Throwable` ở tầng thích hợp; compiler có thể từ chối một `catch (IOException e)` đặt quanh một lời gọi mà theo chữ ký không khai báo `IOException`, nếu trong khối `try` không có thao tác nào khác được khai báo ném `IOException`.

### 3.3. API mới giải quyết như thế nào?

`Constructor.newInstance(...)` có hợp đồng rõ ràng hơn: **ngoại lệ do chính constructor đích ném được bọc trong `InvocationTargetException`**.

```java
Constructor<Loader> constructor = Loader.class.getDeclaredConstructor();

try {
    Loader loader = constructor.newInstance();
} catch (InvocationTargetException ex) {
    Throwable original = ex.getCause();
    // original là IOException("resource unavailable")
}
```

Đoạn ví dụ này cần import `java.lang.reflect.Constructor`, `InvocationTargetException` và `Loader` phía trên; các checked exceptions khác của tra cứu/khởi tạo vẫn phải được xử lý hoặc khai báo.

Kết quả là caller phân biệt được hai nhóm lỗi:

- **Reflection không tìm được/không được quyền/không tạo được đối tượng**: các exception thuộc lớp Reflection.
- **Constructor đã chạy nhưng chính logic constructor thất bại**: `InvocationTargetException`, trong đó `getCause()` là lỗi gốc.

`InvocationTargetException` là checked exception, nên compiler buộc caller xử lý hoặc khai báo nó. Đây là điểm cải thiện trực tiếp về an toàn hợp đồng API.

## 4. So sánh `Class.newInstance()` và `Constructor.newInstance()`

| Tiêu chí | `Class.newInstance()` (deprecated) | `Constructor.newInstance(args...)` |
|---|---|---|
| Điểm xuất phát | Đối tượng `Class<T>` | Đối tượng `Constructor<T>` |
| Kể từ Java 9 | Được đánh dấu `@Deprecated` | API được khuyến nghị cho khởi tạo qua Reflection |
| Constructor hỗ trợ | Chỉ constructor không đối số | Constructor được chọn theo **signature**, có hoặc không có tham số |
| Chọn overloaded constructor | Không | Có, thông qua `getConstructor` / `getDeclaredConstructor` với đúng `Class<?>...` |
| Kiểm tra metadata constructor | Không qua đối tượng constructor riêng | Có `getParameterTypes()`, `getModifiers()`, `getAnnotations()`, `isVarArgs()` ... |
| Constructor non-public | Cần constructor truy cập được theo ngữ cảnh caller; không có đối tượng để yêu cầu suppression | Có thể tìm bằng `getDeclaredConstructor` rồi xét `canAccess`, `trySetAccessible` trong giới hạn module |
| Exception từ constructor | Phát tán trực tiếp, kể cả checked exception | Bọc trong `InvocationTargetException` |
| Thiếu constructor không đối số | Thường `InstantiationException` | `getDeclaredConstructor()` ném `NoSuchMethodException` |
| Constructor thực thi khi nào? | Ngay trong `Class.newInstance()` | Khi gọi `Constructor.newInstance()`, sau bước tra cứu |

Cột bên phải **không hứa** rằng mọi constructor đều được phép gọi. Kiểu abstract, enum, lỗi khởi tạo lớp, sai arguments, quyền module và những điều kiện runtime khác vẫn tồn tại.

## 5. Mẫu thay thế phù hợp cho từng nhu cầu

### 5.1. Tạo object bằng constructor không đối số

Nếu biết rõ class có public no-arg constructor:

```java
Class<MyService> type = MyService.class;

// Cũ (không nên tiếp tục viết):
// MyService service = type.newInstance();

// Mới:
MyService service = type.getDeclaredConstructor().newInstance();
```

Đây là snippet minh họa trong ngữ cảnh có lớp `MyService` và cơ chế xử lý checked exceptions; không phải file runnable độc lập.

`getDeclaredConstructor()` tìm constructor không đối số **kể cả private**. Nó chỉ trả metadata; việc gọi vẫn có thể bị chặn. Khi chủ đích chỉ hỗ trợ **public constructor**, sử dụng:

```java
MyService service = type.getConstructor().newInstance();
```

`getConstructor()` chỉ tìm public constructor, còn `getDeclaredConstructor()` tìm constructor ở mọi mức truy cập. **Không tự động bật `setAccessible(true)` cho mọi constructor** khi chuyển đổi API.

### 5.2. Tạo object có constructor tham số

`Class.newInstance()` không thể thực hiện tình huống này. Với constructor `public Worker(String name, int retries)`:

```java
Constructor<Worker> constructor =
        Worker.class.getConstructor(String.class, int.class);

Worker worker = constructor.newInstance("report", 3);
```

Đây là snippet cần khai báo `Worker` và import `Constructor` trong ngữ cảnh sử dụng.

Khi tra cứu constructor, các parameter types cần **khớp đúng chữ ký**. Ví dụ `int.class` khác `Integer.class`. Chọn đúng constructor trước khi gọi, thay vì mong `getConstructor` tự chọn overload theo đối số runtime. Khi thực thi `Constructor.newInstance`, Java có một số phép chuyển đổi đối số hợp lệ, nhưng điều này không làm `getConstructor` tự thay đổi luật tìm kiếm chữ ký.

### 5.3. Constructor private và kiểm tra module

Một số framework có nhu cầu tạo instance qua non-public constructor. Khi thiết kế thật sự đòi hỏi điều này, thực hiện có điều kiện:

```java
Constructor<SecretConfig> ctor =
        SecretConfig.class.getDeclaredConstructor(String.class);

if (!ctor.canAccess(null) && !ctor.trySetAccessible()) {
    throw new IllegalStateException(
            "Constructor không được phép mở quyền Reflection");
}

SecretConfig instance = ctor.newInstance("configured");
```

Đoạn này cần lớp `SecretConfig` được định nghĩa và xử lý checked exceptions, không phải chương trình độc lập. Với constructor, receiver cho `canAccess` luôn là `null`.

`trySetAccessible()` có thể trả `false` khi module chứa lớp đích không mở package tương ứng. `setAccessible(true)` có thể ném `InaccessibleObjectException`. Việc `getDeclaredConstructor` tìm thấy constructor private **không** đồng nghĩa đã được quyền sử dụng nó.

Với ứng dụng thông thường, public factory method, constructor injection hoặc dependency injection là lựa chọn dễ bảo trì hơn so với tự bỏ qua kiểm tra quyền truy cập private.

### 5.4. Tạo theo loại được chọn tại runtime

Khi nhận một `Class<? extends Handler>` từ registry tin cậy:

```java
static Handler create(Class<? extends Handler> implementation)
        throws ReflectiveOperationException {
    return implementation.getDeclaredConstructor().newInstance();
}
```

Hàm này cần các định nghĩa `Handler`/implementations ở dự án. Nó minh họa cách giữ kiểu trả về mà không ép kiểu không kiểm soát. Nếu lớp đã biết khi biên dịch, hãy ưu tiên `new`, constructor reference hoặc factory hơn Reflection.

Đối với tên class hoặc dữ liệu đầu vào từ nguồn không tin cậy, không tự động cho phép tạo bất kỳ class nào chỉ dựa trên chuỗi. Tạo whitelist/registry những implementation hợp lệ, xác nhận chúng triển khai interface mong đợi, và chỉ dùng constructor thuộc contract được cho phép.

## 6. Chương trình Java 17+ chạy được: so sánh hành vi cũ và mới

Ví dụ sau kiểm chứng bốn tình huống trong cùng một file:

1. Tạo bằng public constructor không đối số với API mới.
2. Thiếu constructor không đối số nhưng có constructor tham số.
3. Constructor ném checked `IOException`: API mới bọc lỗi, API cũ phát tán trực tiếp.
4. Constructor private: tìm metadata bằng `getDeclaredConstructor`, kiểm tra và yêu cầu mở quyền có kiểm soát.

### 6.1. Mã nguồn đầy đủ

Lưu vào file **`ConstructorMigrationDemo.java`**:

```java
import java.io.IOException;
import java.lang.reflect.Constructor;
import java.lang.reflect.InvocationTargetException;

public class ConstructorMigrationDemo {
    public static class Basic {
        public Basic() {}
        @Override public String toString() { return "basic"; }
    }

    public static class NeedsArgument {
        private final String value;
        public NeedsArgument(String value) { this.value = value; }
        public String value() { return value; }
    }

    public static class Exploding {
        public Exploding() throws IOException {
            throw new IOException("disk unavailable");
        }
    }

    @SuppressWarnings("deprecation")
    static <T> T oldCreate(Class<T> type)
            throws InstantiationException, IllegalAccessException {
        return type.newInstance();
    }

    public static void main(String[] args) throws ReflectiveOperationException {
        Basic basic = Basic.class.getDeclaredConstructor().newInstance();
        System.out.println("zero-arg: " + basic);

        try {
            NeedsArgument.class.getDeclaredConstructor();
        } catch (NoSuchMethodException e) {
            System.out.println("missing zero-arg: " + e.getClass().getSimpleName());
        }

        NeedsArgument withArg = NeedsArgument.class
                .getDeclaredConstructor(String.class)
                .newInstance("alpha");
        System.out.println("with-arg: " + withArg.value());

        try {
            Exploding.class.getDeclaredConstructor().newInstance();
        } catch (InvocationTargetException e) {
            Throwable cause = e.getCause();
            System.out.println("modern error: " + e.getClass().getSimpleName());
            System.out.println("root cause: " + cause.getClass().getSimpleName()
                    + ": " + cause.getMessage());
        }

        try {
            oldCreate(Exploding.class);
        } catch (Exception e) {
            System.out.println("legacy error: " + e.getClass().getSimpleName()
                    + ": " + e.getMessage());
        }

        Constructor<LockedWidget> locked =
                LockedWidget.class.getDeclaredConstructor(String.class);
        System.out.println("private canAccess: " + locked.canAccess(null));
        boolean opened = locked.trySetAccessible();
        System.out.println("private opened: " + opened);
        if (opened) {
            LockedWidget widget = locked.newInstance("secret");
            System.out.println("private created: " + widget.code());
        }
    }
}

class LockedWidget {
    private final String code;
    private LockedWidget(String code) { this.code = code; }
    public String code() { return code; }
}
```

Trong chương trình, `LockedWidget` là **top-level class riêng**, không cùng nest với `ConstructorMigrationDemo`. Vì constructor private, `locked.canAccess(null)` ban đầu trả `false`. Các lớp cùng file nằm trong unnamed module khi chạy trên classpath; ở môi trường minh họa thông thường, `trySetAccessible()` được phép mở quyền. Nếu chuyển sang named modules có ràng buộc `opens`, hành vi có thể khác.

Code cũ chỉ xuất hiện **cố ý để minh họa sự khác biệt về exception**, có `@SuppressWarnings("deprecation")` chỉ tại helper `oldCreate`. Không dùng helper này trong code production mới.

### 6.2. Biên dịch và chạy

Dùng JDK 17 trở lên tại thư mục chứa file:

```bash
javac --release 17 ConstructorMigrationDemo.java
java ConstructorMigrationDemo
```

Kết quả đã được kiểm chứng khi biên dịch với `--release 17` và chạy trên OpenJDK 21:

```text
zero-arg: basic
missing zero-arg: NoSuchMethodException
with-arg: alpha
modern error: InvocationTargetException
root cause: IOException: disk unavailable
legacy error: IOException: disk unavailable
private canAccess: false
private opened: true
private created: secret
```

### 6.3. Giải thích kết quả

- `Basic.class.getDeclaredConstructor().newInstance()` tạo đối tượng hợp lệ bằng public no-arg constructor.
- `NeedsArgument` chỉ có constructor nhận `String`, nên `getDeclaredConstructor()` (không tham số) ném `NoSuchMethodException`; tra cứu theo `String.class` rồi khởi tạo thành công.
- `Exploding` ném `IOException("disk unavailable")` ngay trong constructor. `Constructor.newInstance()` báo `InvocationTargetException`; `getCause()` xác nhận `IOException` là lỗi gốc.
- `oldCreate(Exploding.class)` dùng API deprecated và thực tế ném **trực tiếp `IOException`**, dù chữ ký `oldCreate` chỉ khai báo `InstantiationException` và `IllegalAccessException`.
- `LockedWidget` có constructor private. `getDeclaredConstructor(String.class)` lấy được metadata; `canAccess(null)` cho biết hiện chưa được truy cập; `trySetAccessible()` thành công trong môi trường ví dụ, sau đó `newInstance("secret")` tạo đối tượng.

Điểm chứng minh quan trọng nhất: **API mới tách việc tìm constructor và gọi constructor, làm rõ điểm phát sinh lỗi, đồng thời bao bọc exception do constructor thực thi.**

## 7. Cách bắt lỗi và chuyển exception hợp lý

Đoạn mã sau là một helper tạo object bằng constructor không đối số có thể tái sử dụng:

```java
import java.lang.reflect.InvocationTargetException;

public final class Constructors {
    private Constructors() {}

    public static <T> T create(Class<T> type) {
        try {
            return type.getDeclaredConstructor().newInstance();
        } catch (NoSuchMethodException e) {
            throw new IllegalArgumentException(
                    "Thiếu constructor không đối số: " + type.getName(), e);
        } catch (InvocationTargetException e) {
            throw new IllegalStateException(
                    "Constructor của " + type.getName() + " đã thất bại",
                    e.getCause());
        } catch (ReflectiveOperationException e) {
            throw new IllegalStateException(
                    "Không thể khởi tạo: " + type.getName(), e);
        }
    }
}
```

Đây là một **lớp tiện ích Java có thể biên dịch**, không có `main` riêng. Người dùng code gọi `Constructors.create(MyType.class)` khi lớp đích có zero-arg constructor hợp lệ. Helper này cố ý **không mở quyền private constructor**, và có thể thất bại nếu class/method không accessible theo luật Java/module.

Cách bắt này phân biệt:

1. `NoSuchMethodException`: không tìm thấy đúng constructor cần dùng.
2. `InvocationTargetException`: constructor có chạy và ném lỗi; chuyển lỗi gốc qua `getCause()`.
3. Các lỗi `ReflectiveOperationException` khác như `IllegalAccessException`, `InstantiationException`: khởi tạo bị cản bởi quyền hoặc tính chất của kiểu.

Chính sách wrap như `IllegalArgumentException`/`IllegalStateException` trong helper là **lựa chọn của ứng dụng**, không phải thứ Java Reflection bắt buộc. Nếu caller cần xử lý lỗi gốc theo từng loại, hãy giữ nguyên checked exceptions hoặc khai báo một domain exception có `cause`. Đừng nuốt lỗi hoặc chỉ log rồi trả `null` vì điều đó che giấu khởi tạo thất bại.

`InvocationTargetException` không phải exception duy nhất có thể gặp. Một lỗi từ quá trình **class initialization** có thể xuất hiện dưới dạng `ExceptionInInitializerError`; lỗi Java `Error` khác cũng không thuộc `ReflectiveOperationException` và cần được đánh giá theo chính sách ứng dụng.

## 8. Không có constructor mặc định? Đừng đoán

Đây là lỗi phổ biến khi di chuyển code cũ:

```java
class Job {
    Job(String id) {
    }
}
```

Vì `Job` khai báo constructor có tham số, compiler **không tự sinh** no-arg constructor. Kết quả:

```java
Job.class.getDeclaredConstructor(); // NoSuchMethodException
```

Không nên “sửa” bằng cách thêm constructor rỗng nếu domain bắt buộc `id`. Hãy khai báo chính xác constructor cần gọi:

```java
Job job = Job.class
        .getDeclaredConstructor(String.class)
        .newInstance("J-001");
```

Hai đoạn `Job` ở trên dùng làm minh họa ngắn trong cùng ngữ cảnh và cần bắt/khai báo checked exceptions khi chạy thực tế.

### 8.1. Constructor implicit và phạm vi truy cập

Nếu class không khai báo constructor nào, compiler có thể cung cấp **default constructor** không đối số theo luật Java. Tuy nhiên mức truy cập của constructor và khả năng truy cập lớp vẫn cần được xét. Một package-private class không tự trở thành public chỉ vì default constructor tồn tại.

Không nên dùng `Class.newInstance()` để đoán xem một class có thể khởi tạo hay không. Dùng `getDeclaredConstructor(...)` để xác định đúng chữ ký, kiểm tra quyền và xử lý rõ kết quả.

### 8.2. Record, enum và class đặc biệt

- **Record có components:** canonical constructor thường nhận các components theo đúng kiểu và thứ tự. Không thể mặc nhiên đòi có no-arg constructor. Có thể thêm constructor không đối số delegating hợp lệ trong một số thiết kế, nhưng không phải tự nhiên luôn có.
- **Enum:** không thể tùy ý tạo thêm enum constants qua `Constructor.newInstance`; Reflection có giới hạn riêng, và sẽ ném lỗi thích hợp.
- **Abstract class/interface:** không thể tạo instance trực tiếp bằng constructor Reflection.
- **Non-static inner class:** constructor ở mức bytecode thường cần thêm đối số enclosing instance; phải hiểu đúng chữ ký phản chiếu. `Class.newInstance()` không hỗ trợ việc truyền enclosing instance.
- **Array hoặc primitive `Class`:** không tạo như instance class thông thường bằng constructor Reflection; với array, dùng các cơ chế phù hợp như `java.lang.reflect.Array.newInstance` khi thực sự cần.

Một API khởi tạo động tốt phải có contract rõ về **những kiểu được phép tạo**, **constructor nào được hỗ trợ**, **tham số nào hợp lệ** và **exception nào được trả về**.

## 9. Bảng xử lý ngoại lệ khi dùng phương pháp mới

| Trường hợp | Bước điển hình | Kết quả |
|---|---|---|
| Không tồn tại constructor đúng parameter types | `getDeclaredConstructor(...)` | `NoSuchMethodException` |
| Constructor có tồn tại nhưng không được quyền gọi | `constructor.newInstance(...)` | `IllegalAccessException` |
| Cố mở deep reflection qua package chưa mở | `setAccessible(true)` / `trySetAccessible()` | Có thể gặp `InaccessibleObjectException` / trả `false` |
| Thiếu, thừa hoặc sai kiểu argument ở thời điểm gọi | `constructor.newInstance(args...)` | `IllegalArgumentException` |
| Đích abstract, không thể khởi tạo | `constructor.newInstance(...)` | `InstantiationException` |
| Constructor đích tự ném lỗi | `constructor.newInstance(...)` | `InvocationTargetException`, nguyên nhân trong `getCause()` |
| Class initialization thất bại | Trước hoặc lúc thực thi constructor | `ExceptionInInitializerError` |
| Cố tạo enum bằng constructor Reflection | `constructor.newInstance(...)` | `IllegalArgumentException` |
| Kiểm soát truy cập trong môi trường hạn chế | Tra cứu hoặc thao tác | Có thể có `SecurityException` |

Lưu ý: lỗi do class loader/linkage hoặc quyền truy cập module có thể xuất hiện từ bước lấy `Class` hoặc khi nạp class; bảng không nhằm liệt kê mọi `Error` của JVM.

`ReflectiveOperationException` là cha chung hữu ích của nhiều **checked exceptions** như `NoSuchMethodException`, `IllegalAccessException`, `InstantiationException` và `InvocationTargetException`; nó không bao phủ `IllegalArgumentException`, `InaccessibleObjectException` và `ExceptionInInitializerError`.

## 10. Những sai lầm thường gặp khi chuyển code cũ

**Sai lầm 1: Đổi tên API nhưng giữ nguyên cách bắt exception.** Sau khi chuyển sang `getDeclaredConstructor().newInstance()`, cần xử lý thêm `NoSuchMethodException` và `InvocationTargetException`. Nếu bỏ qua, code không biên dịch hoặc mất nguyên nhân từ constructor đích.

**Sai lầm 2: Bắt `Exception` rồi thông báo “constructor không tồn tại”.** `NoSuchMethodException` khác `IllegalAccessException` và khác `InvocationTargetException`. Hãy phân loại lỗi đúng bước.

**Sai lầm 3: Nghĩ `Class.newInstance()` chỉ deprecated vì “cú pháp cũ”.** Vấn đề checked exception bị phát tán trực tiếp là một lý do kỹ thuật thiết yếu, không đơn thuần là đổi tên phương thức.

**Sai lầm 4: Cứ dùng `getDeclaredConstructor()` là có quyền gọi private constructor.** API này tìm cả private constructor nhưng không tự cấp quyền truy cập. Bật suppression còn bị ràng buộc bởi module opens và ngữ cảnh caller.

**Sai lầm 5: Tự động `setAccessible(true)` cho mọi class.** Điều này xâm phạm ranh giới thiết kế, và có thể thất bại với JPMS. Nếu cần public contract, ưu tiên `getConstructor(...)`, public factory hoặc DI.

**Sai lầm 6: Dùng sai tham số tra cứu.** `getDeclaredConstructor(int.class)` khác `getDeclaredConstructor(Integer.class)`; cả số lượng lẫn thứ tự parameter types đều quan trọng.

**Sai lầm 7: Dùng Reflection khi không cần.** Nếu kiểu đã biết tại compile time, `new Widget(...)`, `Widget::new` hoặc `Supplier<Widget>` rõ ràng hơn, có compile-time type checking và không cần xử lý lỗi Reflection.

**Sai lầm 8: Mở rộng phạm vi kiểu tùy ý từ dữ liệu ngoài.** Khởi tạo class qua tên hoặc class loader bằng input không tin cậy có thể kích hoạt constructor/static initializer với side effects. Dùng registry hoặc danh sách implementation được cho phép.

**Sai lầm 9: Dùng một helper zero-arg cho record/class chỉ có constructor có tham số.** Nên xác định constructor phù hợp với domain và tạo object với các arguments bắt buộc, thay vì giả định mọi class đều có constructor mặc định.

## 11. Chọn phương án khởi tạo hợp lý

| Bối cảnh | Phương án nên ưu tiên | Lý do |
|---|---|---|
| Biết type/constructor tại compile time | `new SomeType(args)` | Rõ ràng, được compiler kiểm tra |
| Muốn truyền hành vi tạo object | `Supplier<T>` hoặc constructor reference | Giữ type safety, tránh Reflection |
| Class được chọn từ registry/plugin runtime | `getConstructor(...)` / `getDeclaredConstructor(...)` + `Constructor.newInstance(...)` | Hỗ trợ constructor có tham số, metadata và kiểm soát lỗi |
| Cần truy cập non-public constructor vì framework | `getDeclaredConstructor` rồi kiểm tra quyền rõ ràng | Tôn trọng Java access và JPMS |
| Ứng dụng dùng Spring/DI container | Cơ chế container/factory phù hợp | Giảm coupling vào chi tiết private constructor |
| Legacy code dùng `Class.newInstance()` | Di chuyển sang `Constructor.newInstance()` | Tránh API deprecated và checked-exception bypass |

### Checklist khi sửa code hiện có

1. Tìm các lời gọi `Class.newInstance()` thực tế, không nhầm với `Constructor.newInstance()`.
2. Xác định lớp đích và chữ ký constructor cần dùng. Nếu no-arg constructor không có, chọn overload đúng với thiết kế.
3. Dùng `getConstructor(...)` khi chỉ hỗ trợ public constructor; dùng `getDeclaredConstructor(...)` khi có lý do xét mọi mức truy cập.
4. Kiểm tra quyền truy cập/JPMS trước khi yêu cầu deep reflection.
5. Chuyển xử lý lỗi: phân biệt lỗi lookup, access, instantiation, arguments và exception phát sinh từ constructor đích.
6. Với `InvocationTargetException`, bảo tồn nguyên nhân gốc bằng `getCause()` (hoặc `getTargetException()`).
7. Kiểm thử những trường hợp khó: không có constructor đúng signature, constructor private, constructor ném checked exception, class abstract, tham số sai.
8. Xóa `@SuppressWarnings("deprecation")` cũ nếu không còn gọi API deprecated; không giữ suppression thừa để che cảnh báo khác.

## 12. Câu hỏi tự kiểm tra

1. Vì sao `Class.newInstance()` bị deprecated từ Java 9 dù vẫn tồn tại trong Java 17?
2. Tại sao constructor `Loader() throws IOException` có thể khiến `Class.newInstance()` ném trực tiếp `IOException` mà caller không khai báo?
3. `InvocationTargetException` giúp phân biệt lỗi ở giai đoạn nào? Cách lấy nguyên nhân gốc?
4. `getConstructor` và `getDeclaredConstructor` khác nhau về phạm vi visibility như thế nào?
5. Với `Worker(String, int)`, vì sao `getDeclaredConstructor()` không tham số thất bại? Viết signature đúng.
6. `trySetAccessible()` có bảo đảm truy cập được constructor private của named module khác không?
7. Khi nào dùng `new` hoặc `Supplier` thay cho cả hai dạng Reflection?
8. Vì sao việc đổi `Class.newInstance()` sang `getDeclaredConstructor().newInstance()` đòi hỏi xem lại catch/throws?

**Ghi nhớ:** Hãy dùng `Constructor.newInstance(...)` khi thật sự cần khởi tạo động bằng Reflection. Nó cho phép chọn constructor có tham số, kiểm tra metadata và quyền rõ ràng, và **đóng gói exception do constructor ném vào `InvocationTargetException`**. `Class.newInstance()` đã deprecated từ Java 9, chỉ hỗ trợ constructor không đối số và có thể bỏ qua cơ chế kiểm tra checked exception của compiler.

Tài liệu chuẩn: [Java SE 17 — `Class.newInstance()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html#newInstance()), [`Class.getDeclaredConstructor`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html#getDeclaredConstructor(java.lang.Class...)), [`Constructor.newInstance`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Constructor.html#newInstance(java.lang.Object...)), [`InvocationTargetException`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/InvocationTargetException.html).