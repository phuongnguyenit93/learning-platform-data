# ExceptionInInitializerError khi Reflection kích hoạt khởi tạo lớp trong Java

## 1. Tình huống thường gặp

Bạn dùng Reflection để đọc metadata của một class: lấy `Class<?>`, liệt kê method, field, constructor. Mọi thứ hoạt động. Nhưng đến khi gọi method tĩnh, đọc field tĩnh, tạo đối tượng hoặc gọi `Class.forName(name)`, chương trình bất ngờ ném **`ExceptionInInitializerError`**, dù chưa chạy được logic của method đích.

Nguyên nhân thường là **quá trình khởi tạo lớp (class initialization) thất bại**. Những thao tác Reflection có thể kích hoạt khởi tạo lớp trước khi hoàn thành công việc thực tế. Nếu code trong quá trình khởi tạo ném ngoại lệ, bạn thấy lỗi ngay tại thao tác Reflection đã kích hoạt quá trình đó.

Bài này giúp bạn:
- Phân biệt **loading, linking và initialization**; biết khi nào thao tác Reflection làm khởi tạo lớp.
- Hiểu `<clinit>`, static field initializer, static initializer block và `ExceptionInInitializerError`.
- Dự đoán kết quả khi gọi lại một class đã khởi tạo thất bại: thường là **`NoClassDefFoundError`**.
- Phân biệt lỗi khởi tạo lớp với **`ClassNotFoundException`** và **`InvocationTargetException`**.
- Chẩn đoán nguyên nhân gốc và thiết kế thao tác Reflection hạn chế side effect ngoài ý muốn.

Ví dụ được viết cho **Java 17+** và có thể biên dịch bằng JDK tiêu chuẩn; không cần Spring, thư viện bên ngoài hay quyền mở package đặc biệt.

## 2. Class được nạp chưa chắc đã được khởi tạo

Java phân biệt ba giai đoạn quan trọng trong vòng đời của kiểu:

| Giai đoạn | Ý nghĩa | Cần phân biệt |
| --- | --- | --- |
| **Loading (nạp)** | JVM tìm/đọc định nghĩa lớp và tạo biểu diễn runtime cho lớp | Có `Class<?>` không có nghĩa static initializer đã chạy |
| **Linking (liên kết)** | Kiểm tra, chuẩn bị và xử lý tham chiếu ký hiệu theo quy tắc JVM | JVM có thể xử lý một số việc liên kết theo nhu cầu |
| **Initialization (khởi tạo)** | Thực thi logic khởi tạo các biến static và các static block do compiler gom vào phương thức khởi tạo lớp `<clinit>` | Đây là giai đoạn có thể làm phát sinh `ExceptionInInitializerError` |

Ví dụ lớp dưới đây khởi tạo trường static bằng một phương thức:

~~~java
final class Settings {
    static final String TOKEN = loadToken();

    private static String loadToken() {
        throw new IllegalStateException("Missing TOKEN");
    }
}
~~~

`Settings.class` có thể tạo tham chiếu `Class<Settings>` mà chưa gọi `loadToken()`. Nhưng thao tác **chủ động sử dụng** class theo quy tắc khởi tạo có thể chạy `loadToken()` và làm khởi tạo thất bại.

**Lưu ý về `<clinit>`:** đây là tên phương thức khởi tạo lớp ở mức bytecode/JVM; nó không phải API mà bạn thường xuyên gọi trực tiếp bằng `getDeclaredMethod("<clinit>")`. Java compiler có thể kết hợp nhiều field initializer và static block theo thứ tự quy định vào logic khởi tạo. Không phải mọi class đều có code khởi tạo static có side effect.

## 3. Thao tác nào có thể kích hoạt khởi tạo lớp?

Các quy tắc sử dụng tích cực (active use) của Java áp dụng cho cả mã Java thường lẫn nhiều lời gọi Reflection.

| Thao tác | Có khởi tạo class đích chưa được khởi tạo không? | Giải thích |
| --- | --- | --- |
| `SomeType.class` | **Không** chỉ vì tạo class literal | Lấy biểu diễn `Class`, không chạy initializer của `SomeType` |
| `obj.getClass()` | **Không** vì lệnh gọi này | Object đã tồn tại; lấy metadata không phải yêu cầu khởi tạo mới |
| `Class.forName(name)` | **Có**, theo overload một tham số | Tìm lớp và yêu cầu khởi tạo lớp |
| `Class.forName(name, false, loader)` | **Không** do tham số `false` | Có thể nạp/liên kết; không yêu cầu khởi tạo lớp đích |
| `type.getDeclaredMethod("run")` | **Không** chỉ vì tra cứu | Lấy metadata `Method` (có thể kéo theo xử lý kiểu tham chiếu) |
| `type.getDeclaredFields()` | **Không** chỉ vì liệt kê metadata | Chưa đọc giá trị field |
| `staticMethod.invoke(null)` | **Có**, với method tĩnh của lớp chưa khởi tạo | JVM khởi tạo lớp khai báo method trước khi thực thi method |
| `staticField.get(null)` hoặc `getInt(null)` | **Có**, với field tĩnh của lớp chưa khởi tạo | Reflection yêu cầu khởi tạo lớp khai báo field trước khi đọc giá trị |
| `constructor.newInstance(args)` | **Có**, khi tạo instance của lớp chưa khởi tạo | Phải khởi tạo class trước khi tạo và dùng instance |
| `new SomeType()` | **Có** | Đây là hành động tạo instance trực tiếp, không cần Reflection |

Các diễn giải trên xét class đích **chưa được khởi tạo** và hoạt động thông thường của JDK. Không đồng nghĩa việc thao tác metadata hoàn toàn không thể nạp các kiểu liên quan hoặc gặp các lỗi khác. Việc khởi tạo superclass hay superinterface có default method cũng có thể tham gia vào quá trình khởi tạo kiểu theo quy tắc JVM.

**Ngoại lệ cần nhớ:** đọc trực tiếp một **constant variable** kiểu primitive hoặc `String` có giá trị hằng compile-time (ví dụ `static final int LIMIT = 10`) thường không kích hoạt khởi tạo class khai báo vì giá trị có thể được compiler nội tuyến. Quy tắc này không có nghĩa `Field.get(null)` được miễn khởi tạo: **đọc field static qua Reflection vẫn yêu cầu khởi tạo lớp khai báo field nếu chưa khởi tạo**.

## 4. Cơ chế phát sinh ExceptionInInitializerError

Khi JVM tiến hành khởi tạo một class, nó chạy phần static initialization. Nếu quá trình này kết thúc bất thường:

1. JVM xác định `Throwable` gây lỗi.
2. Nếu `Throwable` đó **không phải `Error`**, JVM bọc nó thành **`ExceptionInInitializerError`**; lỗi gốc trở thành cause.
3. Nếu nguyên nhân **đã là `Error`**, JVM có thể truyền chính `Error` đó ra ngoài mà không tạo thêm `ExceptionInInitializerError`.
4. JVM đánh dấu `Class` tương ứng là **erroneous** (khởi tạo lỗi) trong phạm vi định danh lớp đó (bao gồm defining class loader).
5. Lần sử dụng tích cực tiếp theo của cùng class trong trạng thái erroneous sẽ thất bại với **`NoClassDefFoundError`** thay vì chạy lại static initialization.

Chẳng hạn:

~~~java
static int number = initialize();

static int initialize() {
    throw new IllegalStateException("Invalid configuration");
}
~~~

Trong lần khởi tạo đầu tiên, `IllegalStateException` là một `RuntimeException` (không phải `Error`), nên JVM bọc bằng **`ExceptionInInitializerError`**. Người xử lý lỗi lấy được nguyên nhân bằng `error.getCause()`.

**Đừng suy luận ngược tuyệt đối rằng mọi lỗi static initialization đều có `ExceptionInInitializerError`:** static initialization ném `AssertionError`, `OutOfMemoryError` hay một `Error` khác có thể khiến lần kích hoạt đầu nhận trực tiếp `Error`. Các lỗi trong bước nạp hoặc liên kết cũng có loại exception/error riêng.

Dù có từ **Exception** trong tên, **`ExceptionInInitializerError extends LinkageError`**, mà `LinkageError extends Error`. Vì vậy **`catch (Exception)` không bắt được `ExceptionInInitializerError`**.

## 5. Ví dụ hoàn chỉnh: tra cứu metadata bình thường, invoke thất bại

Lưu mã sau thành **`InitErrorReflectionDemo.java`** và dùng **JDK 17 trở lên**.

~~~java
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;

public class InitErrorReflectionDemo {
    private static int fail(String label) {
        System.out.println("initializing " + label);
        throw new IllegalStateException("failure " + label);
    }

    public static class BrokenInvoke {
        static int value = fail("invoke");

        public static int value() {
            return value;
        }
    }

    public static class BrokenForName {
        static int value = fail("forName");
    }

    public static void main(String[] args) throws Exception {
        // false: chỉ yêu cầu nạp lớp, không khởi tạo BrokenInvoke.
        Class<?> type = Class.forName(
                BrokenInvoke.class.getName(),
                false,
                InitErrorReflectionDemo.class.getClassLoader());

        System.out.println("metadata: " + type.getSimpleName());

        // Tra cứu method cũng chưa chạy static initialization.
        Method method = type.getDeclaredMethod("value");
        System.out.println("lookup: " + method.getName());

        // Gọi static method: JVM phải khởi tạo BrokenInvoke trước.
        try {
            method.invoke(null);
        } catch (ExceptionInInitializerError e) {
            System.out.println(
                    "invoke first: " + e.getClass().getSimpleName());
            System.out.println(
                    "root cause: " + e.getCause().getClass().getSimpleName());
        } catch (InvocationTargetException e) {
            // Chỉ để minh họa rằng lỗi khởi tạo lớp không đến qua
            // InvocationTargetException trong trường hợp này.
            System.out.println("unexpected wrapper: " + e);
        }

        // Cùng Class đã ở trạng thái erroneous: không init lại.
        try {
            method.invoke(null);
        } catch (NoClassDefFoundError e) {
            System.out.println(
                    "invoke second: " + e.getClass().getSimpleName());
        }

        // Overload Class.forName một tham số yêu cầu khởi tạo lớp.
        try {
            Class.forName(BrokenForName.class.getName());
        } catch (ExceptionInInitializerError e) {
            System.out.println(
                    "forName first: " + e.getClass().getSimpleName());
        }
    }
}
~~~

Biên dịch và chạy tại thư mục chứa tệp:

~~~bash
javac -encoding UTF-8 InitErrorReflectionDemo.java
java InitErrorReflectionDemo
~~~

**Đầu ra chính xác (đã kiểm chứng trên JDK 21):**

~~~text
metadata: BrokenInvoke
lookup: value
initializing invoke
invoke first: ExceptionInInitializerError
root cause: IllegalStateException
invoke second: NoClassDefFoundError
initializing forName
forName first: ExceptionInInitializerError
~~~

Đọc kết quả theo thứ tự:

1. `Class.forName(..., false, loader)` trả metadata của **BrokenInvoke** và in `metadata: BrokenInvoke`; không in dòng **initializing** vì chưa khởi tạo class.
2. `getDeclaredMethod("value")` tìm thấy method tĩnh và in `lookup: value`; vẫn chưa khởi tạo class.
3. `method.invoke(null)` yêu cầu khởi tạo class khai báo method trước khi gọi method. Static field initializer chạy và in `initializing invoke`, sau đó ném **IllegalStateException**. JVM bọc thành **ExceptionInInitializerError**.
4. Vì khởi tạo thất bại, method body **value()** thực tế chưa được thực thi. Lần `method.invoke(null)` thứ hai trên cùng class nhận **NoClassDefFoundError** và **không in lại** `initializing invoke`.
5. Với lớp **BrokenForName** khác, `Class.forName(name)` yêu cầu khởi tạo ngay lập tức. Nó in `initializing forName` rồi ném **ExceptionInInitializerError**.

Ví dụ dùng hai nested static class độc lập để quan sát hai đường kích hoạt khởi tạo. Nếu chỉ dùng một class đã fail rồi thử nhiều cách kích hoạt, những lần sau thường chỉ còn thấy **NoClassDefFoundError**, khiến người học dễ tưởng lệnh kiểm thử thứ hai là nguyên nhân ban đầu.

## 6. Phân biệt bốn loại lỗi dễ nhầm

| Lỗi | Điều gì thất bại? | Đặc điểm chẩn đoán |
| --- | --- | --- |
| **ClassNotFoundException** | Yêu cầu nạp class theo tên nhưng class không được tìm thấy trong phạm vi class loader thích hợp | Checked exception; thường ở `Class.forName` hoặc `ClassLoader.loadClass` |
| **ExceptionInInitializerError** | Khởi tạo class thất bại; nguyên nhân ban đầu không phải `Error` | Là **Error**; `getCause()` tiết lộ lỗi gốc như cấu hình sai, null, illegal state |
| **NoClassDefFoundError** | JVM không thể sử dụng định nghĩa class như kỳ vọng, ví dụ class đã khởi tạo thất bại ở lần trước hoặc thiếu dependency khi runtime | Là **LinkageError**; kiểm tra message, cause và lần lỗi đầu tiên |
| **InvocationTargetException** | **Method.invoke** đã gọi được method đích, nhưng method đích ném Throwable | Checked exception; `getCause()` là ngoại lệ từ method body |

Lỗi được ném trong **method body** khi gọi qua `Method.invoke` thường được bọc thành **InvocationTargetException**. Nhưng lỗi xảy ra **trước khi method body có thể chạy**, trong quá trình khởi tạo class phục vụ một lời gọi tĩnh, không phải ngoại lệ do method body ném. Ví dụ trên chứng minh nhánh này ném **ExceptionInInitializerError** trực tiếp thay vì **InvocationTargetException**.

Không nhầm thông điệp **"Could not initialize class ..."** của **NoClassDefFoundError** với **ClassNotFoundException**. Tên class có thể đã tìm được đầy đủ: vấn đề là JVM đã đánh dấu class đó ở trạng thái khởi tạo lỗi.

**Điều kiện phân biệt quan trọng:** không phải mọi **NoClassDefFoundError** đều bắt nguồn từ khởi tạo thất bại. Nó còn có thể xảy ra vì phụ thuộc runtime không có mặt dù class liên quan từng biên dịch được. Xem root cause và chuỗi sự kiện trước khi sửa.

## 7. Vai trò của Field.get, Constructor.newInstance và Class.forName

### Đọc static field bằng Reflection

Các thao tác tra cứu:

~~~java
Class<?> type = Settings.class;
var field = type.getDeclaredField("TOKEN");
~~~

thường chỉ lấy metadata, không khởi tạo **Settings**. Nhưng thao tác đọc:

~~~java
Object value = field.get(null);
~~~

sẽ yêu cầu khởi tạo class khai báo field static nếu chưa khởi tạo. Truyền **null** là thích hợp cho field static vì không cần instance đích. Nếu initialization thất bại, `field.get(null)` có thể ném **ExceptionInInitializerError**; không phải `NoSuchFieldException` chỉ vì field đã tìm thấy.

**Phân biệt:** `Field.get` có thể ném **IllegalAccessException** vì kiểm tra quyền truy cập; đó là vấn đề độc lập với khởi tạo lớp. Không dùng `setAccessible(true)` theo phản xạ khi stack trace thực chất chỉ đến một initializer bị lỗi.

### Tạo instance bằng Constructor.newInstance

Một `Constructor<?> constructor = type.getDeclaredConstructor();` chỉ tra cứu constructor. Nhưng `constructor.newInstance()` kích hoạt khởi tạo class nếu cần, trước khi tạo instance. Nếu static initialization fail, lỗi xuất hiện tại `newInstance`; constructor body có thể chưa bắt đầu.

Nếu constructor body đã chạy và ném exception, API Reflection sẽ phản ánh qua **InvocationTargetException**. Cần xác định lỗi ở phase khởi tạo class hay trong constructor body trước khi chọn catch phù hợp.

### Hai overload của Class.forName

~~~java
Class<?> a = Class.forName("com.example.Plugin");
Class<?> b = Class.forName(
        "com.example.Plugin",
        false,
        Thread.currentThread().getContextClassLoader());
~~~

Dòng thứ nhất **yêu cầu khởi tạo** class `Plugin`. Dòng thứ hai dùng `initialize=false`, hữu ích cho công cụ discovery cần đọc metadata trước khi quyết định có sử dụng plugin không.

Hai dòng là **minh họa**, không phải ví dụ độc lập có sẵn class `com.example.Plugin`; cần class thật với tên và class loader tương ứng. Lệnh `Class.forName(..., false, ...)` không bảo đảm toàn bộ hệ thống không có side effect khác (ví dụ class loader tùy biến), nhưng bản thân nó không yêu cầu khởi tạo class đích.

## 8. Điều xảy ra sau lần khởi tạo thất bại

Đối với cùng một `Class` và defining class loader, JVM ghi nhận class ở trạng thái erroneous khi khởi tạo thất bại. Vì vậy:

- **Không khởi tạo lại class** chỉ vì gọi lại `Class.forName(name)`, `Method.invoke`, `Field.get` hay `Constructor.newInstance` trong cùng quá trình nạp lớp.
- Các lần active use tiếp theo có thể ném **NoClassDefFoundError**, thường kèm thông báo không thể initialize class.
- Nếu ứng dụng thay đổi cấu hình bên ngoài rồi lập tức thử lại cùng class trong cùng class loader, việc khởi tạo **không tự được chạy lại**.
- Một class cùng tên được định nghĩa bằng class loader khác có danh tính runtime khác và có thể có vòng đời khởi tạo riêng. Đây là kiến thức để hiểu phạm vi lỗi, **không phải mẹo khuyến khích tạo class loader mới để che lỗi cấu hình**.

Tính chất này đặc biệt quan trọng ở hệ thống plugin, test runner hoặc ứng dụng sử dụng Reflection: lần lỗi đầu tiên cung cấp stack trace gần nguyên nhân nhất; các lỗi **NoClassDefFoundError** sau đó thường chỉ là hậu quả.

**Với lớp đã fail, ưu tiên sửa root cause và tái khởi động hoặc dùng vòng đời class loader được thiết kế sẵn**, thay vì viết vòng lặp retry không có khả năng đưa class về trạng thái bình thường.

## 9. Cách chẩn đoán ExceptionInInitializerError có hệ thống

Khi thấy `ExceptionInInitializerError` hoặc `NoClassDefFoundError: Could not initialize class ...`, thực hiện theo thứ tự:

1. **Xác định thao tác đầu tiên kích hoạt class initialization**: `Class.forName(name)`, `Method.invoke` method tĩnh, `Field.get` field tĩnh, `Constructor.newInstance`, hay lời gọi Java trực tiếp.
2. **Tìm lần lỗi đầu tiên trong cùng class loader**. Tránh chỉ nhìn stack trace ở lần retry sau khi class đã erroneous.
3. **Mở chuỗi cause** của `ExceptionInInitializerError` bằng `getCause()` (hoặc API lịch sử `getException()`). Đừng dừng ở tên wrapper.
4. **Kiểm tra các static field initializer, static block và phụ thuộc được khởi tạo**. Xem truy cập file/cấu hình, biến môi trường, parsing, phụ thuộc network, thứ tự static field, null, hoặc exception bị ném từ helper.
5. **Phân biệt phase**: nếu lỗi do method/constructor body sau khi class đã khởi tạo thành công, xem `InvocationTargetException`; nếu initializer fail trước method body, tập trung vào khởi tạo lớp.
6. **Xác nhận class loader và cấu hình runtime**. Cùng tên class có thể xuất hiện trong nhiều loader; classpath/module path cũng có thể làm nạp hoặc liên kết thất bại.
7. **Viết test cách ly có thể lặp lại**. Dùng class riêng chưa từng được initialize cho mỗi kịch bản, hoặc chạy trong JVM mới để quan sát chính xác lần lỗi đầu.

Ví dụ để lấy nguyên nhân từ lỗi khởi tạo:

~~~java
try {
    Class.forName("com.example.Plugin");
} catch (ExceptionInInitializerError e) {
    Throwable root = e.getCause();
    System.err.println("Static initialization failed: " + root);
}
~~~

Đoạn trên là ví dụ cho ứng dụng **có class Plugin tương ứng**. Bắt **Error** có chủ đích ở một ranh giới giám sát có thể giúp ghi log nguyên nhân; **không nên coi bắt được lỗi là class đã có thể tiếp tục dùng an toàn**.

Nếu có nhiều tầng wrapper (ví dụ framework bọc thêm một exception), duyệt chuỗi `getCause()` và lưu stack trace đầy đủ để tìm sự kiện đầu tiên. Tránh chỉ dùng `getMessage()` vì đôi khi nó không chỉ rõ nguyên nhân.

## 10. Giảm khởi tạo lớp ngoài ý muốn khi viết công cụ Reflection

- **Discovery trước, activation sau:** khi chỉ liệt kê plugin hoặc đọc thông tin cấu trúc, cân nhắc `Class.forName(name, false, loader)` và API metadata. Chỉ khởi tạo khi quyết định sử dụng class.
- **Giữ static initialization đơn giản:** tránh hoạt động IO, network, truy cập biến môi trường bất ổn hoặc phụ thuộc bên ngoài trong static field initializer nếu có thể hoãn sang thao tác khởi tạo tường minh, dễ trả lỗi có ngữ cảnh.
- **Phân biệt method static với instance:** `Method.invoke(null)` gọi method tĩnh, yêu cầu khởi tạo class; instance method cần receiver đã được tạo thích hợp, và quá trình tạo instance thông thường đã khởi tạo class.
- **Giữ nguyên cause khi báo lỗi:** bọc lỗi thành ngoại lệ nghiệp vụ tại ranh giới phù hợp nhưng không xóa stack trace gốc.
- **Đừng thử chữa bằng quyền Reflection:** `setAccessible(true)` xử lý một số quy tắc kiểm tra truy cập và có thể bị giới hạn bởi module; nó không chữa lỗi từ static initializer.
- **Không retry cùng class vô hạn:** JVM không tự chuyển class erroneous về trạng thái chưa khởi tạo.

Một API plugin tốt nên tách **inspect/discover** (không cần thực thi) khỏi **activate/create** (có thể chạy code khởi tạo), và có bước ghi lỗi rõ ràng tại ranh giới kích hoạt.

## 11. Những hiểu nhầm cần sửa

| Hiểu nhầm | Thực tế |
| --- | --- |
| “Lấy được `Class<?>` tức là static block đã chạy” | Metadata có thể tồn tại khi class chưa được initialize |
| “`getDeclaredMethod()` làm chạy method” | Nó chỉ tra cứu metadata; `invoke()` mới gọi method |
| “Mọi lỗi phát sinh từ `Method.invoke` đều là `InvocationTargetException`” | Lỗi khởi tạo lớp khi gọi static method có thể là `ExceptionInInitializerError` trực tiếp |
| “`ExceptionInInitializerError` là một checked exception” | Nó kế thừa `Error`, không được `catch (Exception)` bắt |
| “Lần khởi tạo đầu thất bại thì retry sẽ chạy lại static block” | Cùng class/loader đã erroneous; lần dùng sau thường ném `NoClassDefFoundError` |
| “Cứ thấy `NoClassDefFoundError` là thiếu file .class” | Nó cũng xuất hiện khi lớp đã khởi tạo thất bại ở lần trước |
| “Field `static final` không bao giờ kích hoạt init” | Compile-time constant trực tiếp có ngoại lệ riêng; **`Field.get` đọc static field vẫn yêu cầu initialization** |

## 12. Bài tập thực hành và tự đánh giá

**Bài tập 1 — tách tra cứu và kích hoạt.** Trong chương trình mẫu, thay `method.invoke(null)` bằng `type.getDeclaredFields()` và in tên field. Dự đoán: metadata được in nhưng **không xuất hiện** `initializing invoke` chỉ vì việc liệt kê. Sau đó thêm `Field.get(null)` trên field static và quan sát thời điểm xuất hiện lỗi.

**Bài tập 2 — thay loại nguyên nhân.** Thay `throw new IllegalStateException(...)` bằng `throw new AssertionError(...)` trong helper. Dự đoán: lần kích hoạt đầu có thể nhận **AssertionError** trực tiếp, còn lần sử dụng lại vẫn có thể gặp **NoClassDefFoundError** do class erroneous. Giải thích quy tắc JVM chỉ bọc nguyên nhân không phải `Error`.

**Bài tập 3 — phân biệt lỗi trước và trong method.** Tạo một class khác có static initialization thành công, nhưng method tĩnh `run()` ném `IllegalStateException`. Gọi nó qua `Method.invoke(null)`; giải thích vì sao trường hợp này nhận **InvocationTargetException** thay cho lỗi khởi tạo.

**Bài tập 4 — Class.forName.** So sánh `Class.forName(name, false, loader)` với `Class.forName(name)` trên hai class mẫu chưa được khởi tạo. In log từ static block để xác định khi nào quá trình khởi tạo xảy ra.

**Câu hỏi tự kiểm tra:**
1. Vì sao thao tác `Class.forName(name, false, loader)` thành công nhưng `Method.invoke(null)` sau đó vẫn có thể thất bại?
2. Nếu nguyên nhân gốc là `NullPointerException` trong static field initializer, lần kích hoạt đầu thường thấy lỗi nào? Lần tiếp theo trên cùng class thường thấy lỗi nào?
3. Vì sao `catch (Exception e)` không giữ được `ExceptionInInitializerError`?
4. Tại sao cần tìm **lần lỗi đầu tiên** chứ không chỉ đọc `NoClassDefFoundError` ở lần gọi thứ hai?

**Đáp án ngắn:** metadata không đồng nghĩa với initialization; `NullPointerException` khi initialize thường được bọc thành `ExceptionInInitializerError`; lần sử dụng kế tiếp của class erroneous thường là `NoClassDefFoundError`; `ExceptionInInitializerError` là `Error`; lần lỗi đầu chỉ ra nguyên nhân và vị trí khởi tạo thất bại.

**Tiêu chí hoàn thành:** bạn chạy được ví dụ Java 17+, giải thích chính xác bảy dòng stdout, phân biệt lỗi từ class initialization và method body, xác định thao tác Reflection kích hoạt initialization, đồng thời biết dùng root cause để sửa lỗi thay vì retry class erroneous.

**Tài liệu chuẩn để học sâu:** *Java Language Specification*, mục **12.4 Initialization of Classes and Interfaces**, và Javadoc của `Class.forName`, `Method.invoke`, `Field.get`, `Constructor.newInstance`, `ExceptionInInitializerError`, `NoClassDefFoundError`, `InvocationTargetException`.
