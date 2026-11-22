# `InvocationTargetException` và ngoại lệ thật của phương thức được gọi trong Java

> **Chủ đề:** Java Core → Exception → Ngoại lệ API. Khi gọi một phương thức bằng **Java Reflection**, `java.lang.reflect.Method.invoke(...)` không truyền trực tiếp mọi exception do phương thức đích ném đến caller. Nếu phần mã được gọi (**target method**) hoàn tất bất thường bằng cách ném một `Throwable`, lời gọi phản chiếu thông thường báo một **`InvocationTargetException`**. Ngoại lệ thực tế nằm trong `getCause()` hoặc `getTargetException()` của wrapper. Nắm vững hai tầng này giúp chẩn đoán nguyên nhân, giữ stack trace, thiết kế xử lý lỗi và không nhầm vấn đề của Reflection với lỗi nghiệp vụ bên trong method.

## 1. Bản chất: một lời gọi, hai tầng ngoại lệ

Xét lời gọi trực tiếp:

```java
service.load();
```

Nếu `load()` ném `IOException`, code gọi trực tiếp có thể nhận `IOException`.

Khi gọi qua Reflection:

```java
java.lang.reflect.Method method =
        Service.class.getMethod("load");

method.invoke(service);
```

nếu **chính `load()`** ném `IOException`, code gọi `invoke` sẽ thấy `InvocationTargetException` (wrapper). Để biết lỗi thực sự:

```java
try {
    method.invoke(service);
} catch (java.lang.reflect.InvocationTargetException wrapper) {
    Throwable targetError = wrapper.getCause();
    System.out.println(targetError.getClass().getName());
}
```

Những đoạn code trên là **minh họa**, giả định `Service`, `service` và các ngoại lệ checked của lookup/invoke được giải quyết trong method thích hợp.

Sơ đồ quan hệ:

```text
Caller
  |
  | Method.invoke(target, args...)
  v
Reflection API
  |
  | Gọi phương thức thật: Service.load()
  v
Service.load()
  |
  | throw new IOException("Không đọc được file")
  v
IOException  <----------------------------+
  |                                        |
  | Reflection bao lỗi khi method ném       |
  v                                        |
InvocationTargetException                 |
  └── cause / targetException ------------+
  |
  v
Caller bắt wrapper và truy nguyên lỗi gốc
```

**Trọng tâm:** `InvocationTargetException` không có nghĩa tên phương thức bị sai, và cũng không đồng nghĩa phương thức đích ném loại exception mang tên đó. Đây là một **tầng biểu diễn lỗi** do Reflection tạo khi mã được gọi ném exception.

## 2. Phân loại `InvocationTargetException` trong cây `Throwable`

Lớp:

```text
java.lang.Throwable
└── java.lang.Exception
    └── java.lang.ReflectiveOperationException
        └── java.lang.reflect.InvocationTargetException
```

Vì vậy:

- `InvocationTargetException` là **checked exception**; nếu gọi `Method.invoke(...)` thì code Java thường phải **bắt** hoặc **khai báo `throws`** nó.
- Đây là subtype của `ReflectiveOperationException` và `Exception`; nó **không** phải `RuntimeException`.
- Target error bên trong có thể là checked `IOException`, unchecked `IllegalArgumentException`, `NullPointerException`, một custom exception hoặc thậm chí `Error`.
- Việc wrapper là checked **không biến target exception thành checked hay ngược lại**; hai đối tượng có kiểu riêng, stack trace riêng và nghĩa khác nhau.
- API `Constructor.newInstance(...)` cũng có thể tạo wrapper này khi constructor đích ném exception.
- Đừng suy rằng **mọi API Reflection** đều tạo `InvocationTargetException`. Nhiều thao tác như lookup field/method, kiểm tra truy cập và khởi tạo class có hợp đồng ngoại lệ riêng.

### 2.1. `getCause()` và `getTargetException()`

Hai phương thức thường dùng:

```java
Throwable getCause()
Throwable getTargetException()
```

Với một `InvocationTargetException` tạo bởi `Method.invoke` khi target thực sự ném lỗi, cả hai cung cấp **cùng ngoại lệ gốc được bọc**. `getTargetException()` là API đặc thù của lớp này; `getCause()` theo cơ chế **exception chaining** chung của `Throwable`, thuận tiện cho code xử lý chuỗi nguyên nhân.

Ví dụ ở điểm bắt:

```java
Throwable cause = wrapper.getCause();
Throwable target = wrapper.getTargetException();
boolean sameObject = cause == target;
```

`sameObject` sẽ là `true` cho wrapper tiêu chuẩn phản ánh cùng target failure.

**Không nhầm:** `wrapper.getStackTrace()` mô tả stack liên quan đến wrapper, trong khi `wrapper.getCause().getStackTrace()` mô tả stack của exception mà method đích đã ném.

### 2.2. Wrapper khác với message

`getMessage()` trên wrapper không phải một cách đáng tin để lấy message của target. Đọc thẳng:

```java
Throwable target = wrapper.getCause();
String targetMessage =
        target == null ? null : target.getMessage();
```

Thông thường wrapper do Reflection tạo sẽ có cause, nhưng khi viết tiện ích nhận các đối tượng `InvocationTargetException` do bên khác tạo thủ công, nên kiểm tra null trước khi truy cập cause.

## 3. Ba loại thất bại khác nhau phải tách biệt

Khi dùng Reflection, có ít nhất ba nhóm sự kiện:

| Nhóm | Ví dụ | Loại exception quan sát |
| --- | --- | --- |
| **Lookup metadata** | Không tìm thấy method tên `load` hoặc sai danh sách tham số trong `getMethod` | `NoSuchMethodException`, không phải lỗi của body method |
| **Gọi Reflection không hợp lệ** | `invoke` sai đối tượng nhận, sai số/kiểu tham số hoặc không được quyền truy cập | Có thể là `IllegalArgumentException`, `NullPointerException`, `IllegalAccessException`... do API gọi phản chiếu |
| **Mã đích ném Throwable** | Method body thực thi rồi ném `IOException`, `IllegalStateException`... | `InvocationTargetException` bọc `Throwable` thực tế |

Một số tình huống khác như thất bại khi khởi tạo lớp, lỗi linkage hoặc vấn đề môi trường module cần xét hợp đồng của từng lời gọi. Không ép mọi lỗi Reflection vào một nhánh.

**Phân biệt then chốt:** `Method.invoke(...)` tự ném `IllegalArgumentException` nếu truyền sai tham số thường **không** phải là `InvocationTargetException`. Nhưng nếu chính **method đích** ném `IllegalArgumentException`, bạn thường nhận **`InvocationTargetException` có cause là `IllegalArgumentException`**.

### 3.1. Có phải method body luôn đã chạy khi có `InvocationTargetException`?

Khi wrapper báo target đã ném, việc thực thi code được gọi đã được kích hoạt và kết thúc bất thường. Tuy nhiên không được suy rằng toàn bộ các dòng trong body đã chạy: method có thể ném ngay đầu, constructor có thể ném trước khi hoàn tất, hoặc target có thể gọi method khác phát sinh lỗi. Ngoài ra khởi tạo lớp liên quan đến target có quy tắc riêng. Muốn biết chính xác, xem stack trace của **cause** và các điều kiện điều khiển.

## 4. Java 17 — ví dụ 1: `Method.invoke` bọc checked `IOException`

Tạo **`ReflectiveMethodFailureDemo.java`**:

```java
import java.io.IOException;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;

public class ReflectiveMethodFailureDemo {
    public static final class Service {
        public String load(String key) throws IOException {
            if ("bad".equals(key)) {
                throw new IOException("Không đọc được bad");
            }
            return "loaded:" + key;
        }
    }

    public static void main(String[] args)
            throws ReflectiveOperationException {
        Service service = new Service();
        Method method =
                Service.class.getMethod("load", String.class);

        Object goodResult = method.invoke(service, "good");
        System.out.println("Good: " + goodResult);

        try {
            method.invoke(service, "bad");
        } catch (InvocationTargetException wrapper) {
            Throwable target = wrapper.getTargetException();
            System.out.println("Wrapper: "
                    + wrapper.getClass().getSimpleName());
            System.out.println("Target: "
                    + target.getClass().getSimpleName());
            System.out.println("Message: " + target.getMessage());
            System.out.println("Same cause: "
                    + (wrapper.getCause() == target));
        }
    }
}
```

Biên dịch/chạy với JDK 17 trở lên:

```bash
javac -encoding UTF-8 ReflectiveMethodFailureDemo.java
java ReflectiveMethodFailureDemo
```

**Stdout chính xác:**

```text
Good: loaded:good
Wrapper: InvocationTargetException
Target: IOException
Message: Không đọc được bad
Same cause: true
```

Giải thích lần lượt:

1. `Service.class.getMethod("load", String.class)` tìm một public method theo tên và **kiểu tham số**, chưa chạy method.
2. `method.invoke(service, "good")` gọi `load("good")`; method trả chuỗi nên `invoke` trả một `Object` chứa chuỗi đó.
3. `method.invoke(service, "bad")` gọi vào body của `load`; body ném checked `IOException`.
4. Caller của Reflection không nhận `IOException` trực tiếp từ `Method.invoke`; nó nhận `InvocationTargetException`.
5. `getTargetException()` và `getCause()` trỏ đến cùng đối tượng `IOException` thực tế.
6. `main` khai báo `throws ReflectiveOperationException` để giải quyết checked exception từ API Reflection có thể còn thoát, còn nhánh `catch(InvocationTargetException)` chủ động diễn giải target failure ở ca xấu.
7. Nếu gọi `service.load("bad")` trực tiếp, compiler sẽ đòi bắt/khai báo `IOException`; khi gọi qua `Method.invoke`, compiler biết **`InvocationTargetException`**, không “đọc” `throws IOException` của method được mô tả bằng đối tượng `Method`.

**Đừng dùng `method.invoke(service, "bad")` rồi viết `catch(IOException)` đơn độc** để chờ lỗi I/O từ thân method; chữ ký checked của Reflection không công bố một IOException trực tiếp như vậy.

## 5. Java Reflection không tự động ném lỗi target trực tiếp

Chữ ký công khai thường gặp (lược bớt annotation và chi tiết):

```java
public Object invoke(Object obj, Object... args)
        throws IllegalAccessException,
               IllegalArgumentException,
               InvocationTargetException
```

Đây là chữ ký của `java.lang.reflect.Method.invoke` ở mức API cần học. `IllegalArgumentException` là unchecked nên dù có xuất hiện trong phần `throws`, compiler không bắt buộc phải xử lý nó.

Điều quan trọng về biên hợp đồng:

- `Method` có thể đại diện cho method được khai báo `throws IOException`, `throws SQLException` hoặc không checked throws.
- Nhưng **`Method.invoke` có chữ ký riêng**, không tham số hóa kiểu checked exception của target.
- Java không suy luận checked exceptions của target khi method được tìm/chọn động qua reflection.
- `InvocationTargetException` tạo tầng bọc thống nhất để API có thể báo “mã được gọi đã ném lỗi” bất kể target là loại method nào.
- Để xử lý loại target cụ thể, bạn phải **unwrap** rồi áp chính sách, hoặc dùng thao tác gọi trực tiếp nếu có thể biết method tại compile-time.

### 5.1. `throws` của target vẫn có ý nghĩa

Nếu target khai báo `throws IOException`, lời gọi Java trực tiếp chịu hợp đồng đó. Khi call site dùng reflection, compiler áp chữ ký `Method.invoke`; điều đó **không biến unchecked thành checked hay loại bỏ lỗi I/O**. Lỗi I/O vẫn nằm trong đối tượng cause, và tầng gọi phải ra quyết định về cách báo/khôi phục.

Một target có thể ném unchecked exception dù chữ ký của chính nó không khai báo `throws`, và Reflection vẫn bọc target exception ấy.

## 6. Java 17 — ví dụ 2: unchecked exception do **method đích** ném

Tạo **`ReflectiveRuntimeFailureDemo.java`**:

```java
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;

public class ReflectiveRuntimeFailureDemo {
    public static final class Calculator {
        public int divide(int numerator, int denominator) {
            return numerator / denominator;
        }
    }

    public static void main(String[] args)
            throws ReflectiveOperationException {
        Method divide = Calculator.class.getMethod(
                "divide", int.class, int.class);
        Calculator calculator = new Calculator();

        Object ok = divide.invoke(calculator, 12, 3);
        System.out.println("Result: " + ok);

        try {
            divide.invoke(calculator, 12, 0);
        } catch (InvocationTargetException wrapper) {
            Throwable actual = wrapper.getCause();
            System.out.println("Actual: "
                    + actual.getClass().getSimpleName());
            System.out.println("Message: " + actual.getMessage());
        }
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 ReflectiveRuntimeFailureDemo.java
java ReflectiveRuntimeFailureDemo
```

Stdout:

```text
Result: 4
Actual: ArithmeticException
Message: / by zero
```

**Vì sao có wrapper nếu `ArithmeticException` là unchecked?**

`InvocationTargetException` không chỉ dùng để bọc **checked exception**. `Method.invoke` bọc Throwable mà method đích ném. Khi phép chia trong `Calculator.divide` gây `ArithmeticException`, Reflection vẫn tạo wrapper để caller phân biệt với lỗi do chính API `invoke` (như truyền tham số sai).

Một `catch(ArithmeticException)` đặt trực tiếp quanh `divide.invoke(...)` **không tự bắt** target exception ở ví dụ này; caller sẽ thấy wrapper. Nếu ứng dụng muốn xử lý loại `ArithmeticException` cụ thể, phải unwrap và kiểm tra `getCause()`.

### 6.1. Có thể target ném `Error` không?

Có. Method đích có thể ném `AssertionError` hoặc một `Error` khác. `Method.invoke` thường báo target-thrown `Throwable` qua `InvocationTargetException`. Nhưng có những lỗi của quá trình runtime khác (như lỗi khởi tạo class) với hợp đồng riêng, nên không nói “bất kỳ Error nào xảy ra quanh Reflection đều chắc chắn bị bọc”.

Không bắt `Error` rộng chỉ để “phục hồi mọi lỗi JVM”. Một framework chuyên biệt có thể cần giải phóng tài nguyên/log rồi để failure lan theo hợp đồng; rất nhiều `Error` không an toàn để coi là lỗi nghiệp vụ dự kiến.

## 7. `Constructor.newInstance` cũng có thể bọc lỗi target

Reflection không chỉ gọi method; `java.lang.reflect.Constructor<T>.newInstance(Object... initargs)` cho phép tạo object bằng constructor được mô tả. Nếu **constructor body** ném exception, API có thể báo `InvocationTargetException`.

Ví dụ constructor tự từ chối tham số âm:

```java
public Account(int amount) {
    if (amount < 0) {
        throw new IllegalArgumentException("amount âm");
    }
    this.amount = amount;
}
```

Nếu dùng `new Account(-1)` trực tiếp, caller nhận `IllegalArgumentException`. Nếu dùng `constructor.newInstance(-1)`, caller sẽ thường nhận **`InvocationTargetException`**, và cause là `IllegalArgumentException` từ constructor.

### 7.1. Java 17 — ví dụ 3: constructor exception

Tạo **`ReflectiveConstructorFailureDemo.java`**:

```java
import java.lang.reflect.Constructor;
import java.lang.reflect.InvocationTargetException;

public class ReflectiveConstructorFailureDemo {
    public static final class Account {
        private final int amount;

        public Account(int amount) {
            if (amount < 0) {
                throw new IllegalArgumentException("amount âm");
            }
            this.amount = amount;
        }

        public int amount() {
            return amount;
        }
    }

    public static void main(String[] args)
            throws ReflectiveOperationException {
        Constructor<Account> constructor =
                Account.class.getConstructor(int.class);

        Account valid = constructor.newInstance(5);
        System.out.println("Created: " + valid.amount());

        try {
            constructor.newInstance(-1);
        } catch (InvocationTargetException wrapper) {
            Throwable target = wrapper.getCause();
            System.out.println("Wrapper: "
                    + wrapper.getClass().getSimpleName());
            System.out.println("Target: "
                    + target.getClass().getSimpleName());
            System.out.println("Message: " + target.getMessage());
        }
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 ReflectiveConstructorFailureDemo.java
java ReflectiveConstructorFailureDemo
```

Stdout:

```text
Created: 5
Wrapper: InvocationTargetException
Target: IllegalArgumentException
Message: amount âm
```

Đây là constructor **public**, nên `getConstructor(int.class)` tìm thấy nó. Constructor không hoàn tất trong trường hợp `-1` và caller không nhận một object `Account` thành công. Wrapper không làm constructor tiếp tục hoặc rollback side effect đã xảy ra trước khi ném lỗi.

### 7.2. Không nhầm với `Class.getDeclaredConstructor`

- `getConstructor(...)` tìm constructor **public** phù hợp.
- `getDeclaredConstructor(...)` có thể tìm constructor được **khai báo trong lớp**, kể cả private; nhưng tìm thấy metadata không đồng nghĩa được phép gọi nó.
- Quyền truy cập Java và giới hạn module có thể khiến lời gọi thất bại trước khi constructor body được chạy.
- Khi không tìm thấy constructor phù hợp, `NoSuchMethodException` thuộc pha lookup, không phải lỗi trong constructor body.
- Việc truy cập private constructor bằng `setAccessible(true)`/`trySetAccessible` có những giới hạn bảo mật/encapsulation và module; đừng dùng để bỏ qua hợp đồng API không được cho phép.

## 8. Java 17 — ví dụ 4: lỗi của Reflection **không** phải target exception

Mục tiêu của ví dụ là phân biệt ba tình huống:

1. Tên method không tồn tại.
2. Cung cấp sai kiểu tham số cho `invoke`.
3. Tham số đúng, method body ném unchecked exception.

Tạo **`ReflectionVsTargetDemo.java`**:

```java
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;

public class ReflectionVsTargetDemo {
    public static final class Operations {
        public void process(String value) {
            if ("boom".equals(value)) {
                throw new IllegalStateException("Lỗi từ method đích");
            }
            System.out.println("Processed: " + value);
        }
    }

    public static void main(String[] args)
            throws ReflectiveOperationException {
        Operations target = new Operations();

        try {
            Operations.class.getMethod("missing");
        } catch (NoSuchMethodException e) {
            System.out.println("Lookup: NoSuchMethodException");
        }

        Method method =
                Operations.class.getMethod("process", String.class);

        try {
            method.invoke(target, 123);
        } catch (IllegalArgumentException e) {
            System.out.println("Argument: IllegalArgumentException");
        }

        try {
            method.invoke(target, "boom");
        } catch (InvocationTargetException wrapper) {
            System.out.println("Invocation: "
                    + wrapper.getClass().getSimpleName());
            System.out.println("Target: "
                    + wrapper.getCause().getClass().getSimpleName());
        }

        method.invoke(target, "ok");
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 ReflectionVsTargetDemo.java
java ReflectionVsTargetDemo
```

Stdout:

```text
Lookup: NoSuchMethodException
Argument: IllegalArgumentException
Invocation: InvocationTargetException
Target: IllegalStateException
Processed: ok
```

Giải thích:

- `getMethod("missing")` không tìm thấy member; **không chạy** body nào, nên báo `NoSuchMethodException`.
- `method.invoke(target, 123)` truyền `Integer` cho tham số `String`; Reflection từ chối việc truyền argument sai bằng `IllegalArgumentException`.
- `method.invoke(target, "boom")` có argument hợp lệ, body thực thi và ném `IllegalStateException`; Reflection bọc nó vào `InvocationTargetException`.
- `method.invoke(target, "ok")` hoàn tất thành công và in `Processed: ok`.

Một ví dụ đơn giản nhưng rất quan trọng: **cùng từ “ArgumentException” có thể nằm ở hai tầng khác nhau**. Hãy nhìn xem bạn bắt exception trực tiếp từ API invoke, hay lấy một exception qua `wrapper.getCause()`.

### 8.1. `IllegalAccessException` xảy ra lúc nào?

Nếu caller không được quyền gọi member theo cơ chế truy cập của Java, `Method.invoke` có thể ném checked `IllegalAccessException`. Đây là vấn đề **quyền truy cập phương thức** chứ không phải exception mà body method đã ném. Đừng unwrap `IllegalAccessException` như thể chắc chắn có `InvocationTargetException` đi kèm.

Một lookup thành công không bảo đảm invoke thành công: metadata có thể được tìm thấy bằng `getDeclaredMethod`, nhưng điều đó không tự cấp quyền gọi private member.

### 8.2. `NullPointerException` có thể đến từ hai nguồn

Nếu gọi một **instance method** qua `Method.invoke` mà truyền null receiver, API có thể ném `NullPointerException` do không có đối tượng đích. Nhưng nếu receiver hợp lệ và **body của target** ném `NullPointerException`, caller sẽ thấy wrapper `InvocationTargetException` mang cause `NullPointerException`.

Bởi vậy khi xử lý log, đừng chỉ nhìn tên loại ngoại lệ; cần biết **tầng phát sinh**.

## 9. Khi nào `Method.invoke` trả giá trị, và trả gì?

Với method trả về object hoặc primitive, `Method.invoke` trả kiểu `Object`. Nếu method gốc trả primitive như `int`, Reflection **boxing** nó vào wrapper object như `Integer`. Với method trả `void`, kết quả `invoke` là `null`.

Khi target ném exception, `invoke` **không có giá trị trả về thành công**; exception (wrapper) làm thay đổi luồng điều khiển.

### 9.1. Java 17 — ví dụ 5: method trả primitive, void và static

Tạo **`ReflectiveReturnValuesDemo.java`**:

```java
import java.lang.reflect.Method;

public class ReflectiveReturnValuesDemo {
    public static final class Calculator {
        public int add(int a, int b) {
            return a + b;
        }

        public void ping() {
            System.out.println("Ping");
        }

        public static String version() {
            return "v1";
        }
    }

    public static void main(String[] args)
            throws ReflectiveOperationException {
        Calculator target = new Calculator();

        Method add = Calculator.class.getMethod(
                "add", int.class, int.class);
        Object sum = add.invoke(target, 2, 3);
        System.out.println("Sum: " + sum);
        System.out.println("Boxed: "
                + sum.getClass().getSimpleName());

        Method ping = Calculator.class.getMethod("ping");
        Object voidResult = ping.invoke(target);
        System.out.println("Void result null: "
                + (voidResult == null));

        Method version = Calculator.class.getMethod("version");
        Object staticResult = version.invoke(null);
        System.out.println("Static: " + staticResult);
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 ReflectiveReturnValuesDemo.java
java ReflectiveReturnValuesDemo
```

Stdout:

```text
Sum: 5
Boxed: Integer
Ping
Void result null: true
Static: v1
```

Bài học:

- `getMethod("add", int.class, int.class)` dùng **kiểu tham số trong khai báo**, không dùng kiểu argument instance `Integer.class`.
- Kết quả của `int add(...)` được boxing thành `Integer`.
- `void ping()` làm `invoke` trả `null`, không có nghĩa body không chạy.
- Với `static version()`, có thể truyền `null` receiver cho `invoke`, do method static không dùng instance receiver.
- Đối với instance method, receiver phải phù hợp với lớp khai báo và quyền gọi.

Các điều này là **hợp đồng gọi reflection**, độc lập với phân biệt wrapper và target exception, nhưng giúp xác định nơi lỗi có thể xảy ra.

## 10. Chọn handler cho `InvocationTargetException` và nguyên nhân

Khi ở tầng có Reflection, handler nên trả lời:

1. **Lời gọi phản chiếu có thất bại khi chuẩn bị không?** Ví dụ lookup/permission/argument.
2. **Nếu target đã ném, loại thực tế là gì?** Đọc `wrapper.getCause()`.
3. **Tầng hiện tại có thể khôi phục không?** Có nên bỏ qua thao tác, trả failure có cấu trúc, ném lại checked cụ thể hay chuyển thành exception nghiệp vụ?
4. **Đối tượng cause có cần được giữ nguyên?** Tránh tạo một exception mới chỉ chứa message rồi bỏ trace gốc.
5. **Nếu có side effect trước khi ném**, phải đánh giá trạng thái; wrapping không rollback.

Một handler minh họa:

```java
try {
    method.invoke(target, argument);
} catch (InvocationTargetException wrapper) {
    Throwable cause = wrapper.getCause();
    if (cause instanceof java.io.IOException io) {
        reportIoFailure(io);
    } else if (cause instanceof RuntimeException re) {
        throw re;
    } else if (cause instanceof Error er) {
        throw er;
    } else {
        throw new IllegalStateException(
                "Method đích thất bại", cause);
    }
}
```

Đây là **mảnh code** cần định nghĩa `method`, `target`, `argument`, `reportIoFailure`, và xử lý các checked exceptions khác của `Method.invoke`. Nó diễn đạt một chính sách mẫu, không phải chiến lược duy nhất.

### 10.1. Vì sao không catch Exception rồi cast bừa?

Không nên:

```java
try {
    method.invoke(target);
} catch (Exception e) {
    throw (RuntimeException) e.getCause();
}
```

Đây là **phản ví dụ**. `e` có thể là `NoSuchMethodException` hay `IllegalAccessException` với cause `null`; target có thể ném một checked `IOException` hoặc `Error`; cast không an toàn có thể gây `ClassCastException`/`NullPointerException` và che nguyên nhân gốc.

Nếu cần unwrap, **chỉ áp dụng với `InvocationTargetException`**, rồi kiểm tra kiểu target `Throwable` thực tế.

## 11. Java 17 — ví dụ 6: ném lại `IOException` thật và giữ object gốc

Đôi khi một abstraction biết rõ target method có thể ném `IOException` và muốn public API tiếp tục có checked contract `throws IOException`, không biến lỗi thành generic runtime wrapper.

Tạo **`RethrowTargetIOExceptionDemo.java`**:

```java
import java.io.IOException;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;

public class RethrowTargetIOExceptionDemo {
    public static final class Source {
        public void fetch() throws IOException {
            throw new IOException("Kết nối bị ngắt");
        }
    }

    static void runReflectively()
            throws IOException, ReflectiveOperationException {
        Method method = Source.class.getMethod("fetch");
        try {
            method.invoke(new Source());
        } catch (InvocationTargetException wrapper) {
            Throwable target = wrapper.getCause();

            if (target instanceof IOException io) {
                throw io;
            }
            if (target instanceof RuntimeException re) {
                throw re;
            }
            if (target instanceof Error error) {
                throw error;
            }
            throw new IllegalStateException(
                    "Checked exception không mong đợi", target);
        }
    }

    public static void main(String[] args)
            throws ReflectiveOperationException {
        try {
            runReflectively();
        } catch (IOException e) {
            System.out.println("Caught: "
                    + e.getClass().getSimpleName());
            System.out.println("Message: " + e.getMessage());
            System.out.println("Top frame: "
                    + e.getStackTrace()[0].getMethodName());
        }
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 RethrowTargetIOExceptionDemo.java
java RethrowTargetIOExceptionDemo
```

Stdout khi chạy trực tiếp chương trình này trên JDK 17:

```text
Caught: IOException
Message: Kết nối bị ngắt
Top frame: fetch
```

Giải thích:

- `runReflectively` bắt checked wrapper do `Method.invoke` ném.
- Khi cause là `IOException`, code **ném lại chính đối tượng cause**, không tạo bản sao.
- `main` nhận `IOException` theo hợp đồng checked của method `runReflectively`.
- Vì dùng lại chính cause, stack trace thường vẫn có frame đầu là vị trí `IOException` được tạo trong `fetch()`, không bị thay bằng điểm unwrap.
- `getStackTrace()[0]` ở đây dùng trong ví dụ kiểm soát stack bình thường. Với code xử lý Throwable bất kỳ, mảng stack có thể rỗng hoặc bị tùy biến; không giả định luôn có frame.
- Với checked Throwable ngoài tập được phép, ví dụ chọn wrapper `IllegalStateException` có cause. Một API thực phải thiết kế chính sách này rõ theo domain, không giấu lỗi thành công.

### 11.1. Có cần khai báo `throws InvocationTargetException` ở API public?

Không bắt buộc nếu tầng Reflection đã bắt và diễn giải wrapper. Một thư viện có thể chọn **ẩn chi tiết Reflection** khỏi API bên ngoài, chỉ công bố exception nghiệp vụ hoặc checked exception phù hợp. Nếu caller thực sự có trách nhiệm quản lý Reflection, việc công bố `ReflectiveOperationException` cũng có thể đúng.

Điểm thiết kế là đừng để mọi tầng ứng dụng phải biết `InvocationTargetException` chỉ vì tầng triển khai bên dưới dùng Reflection.

## 12. Cẩn trọng với `Throwable` có cause là `Error`

Target có thể ném một `Error`, ví dụ `AssertionError`. Khi unwrap:

```java
Throwable cause = wrapper.getCause();
if (cause instanceof Error error) {
    throw error;
}
```

về mặt cú pháp là hợp lệ. Nhưng đừng chủ động bắt rộng `Error` và cố “sửa” mọi trạng thái. Với nhiều `Error`, môi trường hoặc invariant có thể đã không còn đáng tin để tiếp tục.

Nếu framework phải log rồi đưa error lên caller, nhớ phân biệt các failure xảy ra **bên trong target** với các lỗi runtime xảy ra trước khi target được gọi. Chọn chính sách riêng cho lỗi có tính fatal hoặc không thể phục hồi, không chỉ một handler chung.

## 13. Chuỗi `cause`: wrapper Reflection có thể chỉ là lớp ngoài cùng

Giả sử target method đã bọc lỗi I/O:

```java
public void process() {
    try {
        readConfiguration();
    } catch (IOException e) {
        throw new IllegalStateException(
                "Cấu hình không khả dụng", e);
    }
}
```

Đây là method minh họa, cần định nghĩa `readConfiguration()` phù hợp. Khi invoke reflection và target ném `IllegalStateException`, chuỗi có dạng:

```text
InvocationTargetException       ← do Method.invoke tạo
  └── cause: IllegalStateException("Cấu hình không khả dụng")
        └── cause: IOException("Lỗi đọc cấu hình")
```

Một lần gọi `wrapper.getCause()` chỉ trả **cause trực tiếp** là `IllegalStateException`, không trả ngay `IOException` sâu nhất. Muốn xem root cause, bạn có thể đi theo từng liên kết `getCause()`. Nhưng đừng luôn bỏ qua lớp trung gian: nó có thể mang ý nghĩa nghiệp vụ và thông điệp hữu ích.

### 13.1. Java 17 — ví dụ 7: hai tầng cause rõ ràng

Tạo **`ReflectionCauseChainDemo.java`**:

```java
import java.io.IOException;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;

public class ReflectionCauseChainDemo {
    public static final class Workflow {
        public void execute() {
            IOException source =
                    new IOException("Đọc dữ liệu lỗi");
            throw new IllegalStateException(
                    "Không hoàn tất workflow", source);
        }
    }

    public static void main(String[] args)
            throws ReflectiveOperationException {
        Method method =
                Workflow.class.getMethod("execute");

        try {
            method.invoke(new Workflow());
        } catch (InvocationTargetException wrapper) {
            Throwable directCause = wrapper.getCause();
            Throwable rootCause = directCause.getCause();

            System.out.println("Wrapper: "
                    + wrapper.getClass().getSimpleName());
            System.out.println("Direct cause: "
                    + directCause.getClass().getSimpleName());
            System.out.println("Root cause: "
                    + rootCause.getClass().getSimpleName());
            System.out.println("Root message: "
                    + rootCause.getMessage());
            System.out.println("Suppressed on wrapper: "
                    + wrapper.getSuppressed().length);
        }
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 ReflectionCauseChainDemo.java
java ReflectionCauseChainDemo
```

Stdout:

```text
Wrapper: InvocationTargetException
Direct cause: IllegalStateException
Root cause: IOException
Root message: Đọc dữ liệu lỗi
Suppressed on wrapper: 0
```

Điều cần hiểu:

- Wrapper do Reflection tạo nằm ngoài một `IllegalStateException` do code ứng dụng tạo.
- `IllegalStateException` lại có `IOException` làm cause.
- `getSuppressed()` là cơ chế khác với cause; ví dụ này không thêm lỗi suppressed nên bằng 0.
- Nếu target dùng try-with-resources rồi gặp lỗi ở `close()`, suppressed exceptions có thể nằm trên **target exception** hoặc một Throwable sâu hơn trong cause chain, không tự nằm trên wrapper Reflection.
- Vì thế một logger chỉ ghi `wrapper.getMessage()` có thể làm mất nhiều thông tin. Hãy ghi **Throwable đầy đủ**, hoặc phân tích chuỗi quan hệ khi có nhu cầu xử lý có cấu trúc.

## 14. Stack trace của wrapper và của method đích

Thông thường hai đối tượng Throwable có hai stack trace:

- `InvocationTargetException`: được tạo ở tầng gọi phản chiếu; trace của nó thường bắt đầu trong các lớp Reflection/JDK.
- Target exception: được tạo hoặc ném trong method thực tế; trace của nó thường dẫn tới dòng trong code đích và các caller bên trong.

Ví dụ output log kiểu:

```text
java.lang.reflect.InvocationTargetException
    at ... Method.invoke(...)
    at ... ReflectiveCaller.main(...)
Caused by: java.io.IOException: Không đọc được bad
    at ... Service.load(...)
    ... N more
```

Đây là **sơ đồ stack trace**, không phải stderr cố định. Tên lớp nội bộ Reflection, số dòng, frame rút gọn và thứ tự có thể khác giữa các bản JDK, chế độ thực thi và logger.

**Để debug:** thường đọc từ `InvocationTargetException` xuống phần **`Caused by:`**. Bên dưới đó là loại và trace của lỗi thực sự do target tạo/lan ra. Không chỉ dừng ở dòng `Method.invoke` rồi kết luận bug trong Java Reflection.

### 14.1. `getTargetException()` có lưu stack như thế nào?

Nó trả **đối tượng Throwable gốc** được wrapper giữ, không tự tạo một exception mới mỗi lần gọi. Đọc `target.getStackTrace()` để xem frame gắn với target. Cần bảo vệ các trường hợp mảng trace rỗng trong công cụ tổng quát, và không dùng dòng nguồn làm hợp đồng máy ổn định.

### 14.2. Có nên thay trace bằng `fillInStackTrace()`?

Thông thường **không**. Khi unwrap rồi ném lại target exception, giữ nguyên trace giúp thấy nguồn phát sinh gốc. Tự gọi `fillInStackTrace()` sẽ thay thông tin vị trí đã ghi, có thể khiến việc chẩn đoán mất dấu target ban đầu. Nếu cần bổ sung ngữ cảnh, nên dùng wrapper mới có `cause` hoặc logging context phù hợp hơn.

## 15. Nếu target body tự ném `InvocationTargetException` thì sao?

Vì đây là một lớp checked exception công khai, một method đích về mặt Java **cũng có thể chủ động ném một `InvocationTargetException`**. Khi gọi method ấy qua `Method.invoke`, Reflection bọc Throwable của target vào **một wrapper khác**; vì thế có thể xuất hiện hai tầng cùng loại:

```text
InvocationTargetException  ← wrapper ngoài do Method.invoke tạo
  └── cause: InvocationTargetException ← đối tượng target đã ném
        └── cause: IOException
```

Điều này thường không cần trong code thông thường, nhưng hữu ích để hiểu vì sao một tiện ích “unwrap tất cả `InvocationTargetException` liên tục” có thể làm mất ranh giới tầng API. Hãy xác định bạn muốn loại bỏ **wrapper do bước invoke hiện tại tạo** hay muốn đi đến exception nguyên nhân sâu nhất theo một chính sách khác.

Không có quy tắc chung bắt buộc “một lời gọi Reflection chỉ có đúng một Throwable trong chuỗi”. Mỗi tầng có thể tạo wrapper của riêng nó.

## 16. `Method.invoke` với `static`, instance, access và signature

Để phân biệt lỗi wrapper/target chính xác, cần biết một số quy tắc gọi Reflection:

| Thao tác | Điều cần đúng | Lỗi sai có thể là |
| --- | --- | --- |
| `getMethod(name, parameterTypes)` | Có public member phù hợp | `NoSuchMethodException` |
| `getDeclaredMethod(...)` | Có member được khai báo trực tiếp | `NoSuchMethodException` |
| `invoke(receiver, args...)` trên instance method | Receiver khác null và phù hợp với declaring class | `NullPointerException` hoặc `IllegalArgumentException` do API |
| `invoke(null, args...)` trên static method | `null` receiver được chấp nhận | Body method vẫn có thể ném wrapper khi lỗi |
| Truyền arguments | Số/kiểu tương thích với chữ ký, tính đến boxing/widening hợp lệ | `IllegalArgumentException` do Reflection |
| Gọi member bị hạn chế truy cập | Có quyền truy cập theo luật Java/module | `IllegalAccessException` hoặc vấn đề encapsulation |
| Body target thực thi rồi ném | Mã đích phát sinh Throwable | `InvocationTargetException` với cause |

**Lưu ý varargs:** chữ ký Java `Object... args` của `Method.invoke` có quy tắc varargs tại **call site của chính Reflection**, khác với tham số varargs của method đích. Với method nhận một tham số là mảng, có thể cần cast `(Object) array` để truyền một đối tượng mảng thay vì bị trình biên dịch trải thành varargs của `invoke`. Đây là vấn đề truyền đối số, không phải cách chữa lỗi target.

### 16.1. Metadata trả về không có nghĩa target chắc chắn được gọi

Method lookup có thể thành công nhưng invoke bị từ chối vì access. Với generic bridge methods, inherited method, visibility hoặc module encapsulation, đôi khi cần hiểu method thực được chọn và context class loader. Không gán mọi lỗi thất bại trước target cho exception của target.

## 17. `Class.newInstance()` và cách dùng nên tránh

API `Class.newInstance()` cũ đã được **deprecated** từ Java 9. Một điểm gây khó hiểu là API này có những hành vi liên quan đến exception của constructor không giống cơ chế bọc nhất quán của `Constructor.newInstance(...)`, và có thể truyền ngoại lệ checked của constructor ra ngoài theo cách gây bất ngờ cho hệ thống type checking.

Trong code Java 17 mới, nên ưu tiên:

```java
Constructor<MyType> constructor =
        MyType.class.getDeclaredConstructor();

MyType instance = constructor.newInstance();
```

Đây là **mảnh code minh họa**; cần import `Constructor`, lớp `MyType` phù hợp và xử lý checked reflection exceptions. Nếu constructor ném lỗi, `Constructor.newInstance` báo `InvocationTargetException`; caller có thể unwrap `getCause()`.

Đừng viết hướng dẫn dựa trên `Class.newInstance()` như API chuẩn được khuyến nghị khi có lựa chọn constructor reflection rõ hơn.

## 18. `MethodHandles` có cơ chế khác với `Method.invoke`

Reflection `Method.invoke` và API `java.lang.invoke.MethodHandle` có hình thức, kiểm tra kiểu và hợp đồng ngoại lệ khác nhau. Khi gọi một method handle qua `invokeExact`/`invoke`/`invokeWithArguments`, ngoại lệ do target ném **có thể lan trực tiếp** theo hợp đồng method-handle invocation, không bắt buộc biến thành `InvocationTargetException` như `Method.invoke`.

Không nên suy:

> “Hễ gọi phương thức động là sẽ có `InvocationTargetException`.”

Chỉ đúng đối với các API cụ thể đã định nghĩa cơ chế bọc, điển hình là `Method.invoke` và `Constructor.newInstance`.

### 18.1. Java 17 — ví dụ 8: MethodHandle cho IOException đi trực tiếp

Tạo **`MethodHandleVsReflectionDemo.java`**:

```java
import java.io.IOException;
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;

public class MethodHandleVsReflectionDemo {
    public static void fail() throws IOException {
        throw new IOException("Lỗi gốc");
    }

    public static void main(String[] args) throws Throwable {
        Method method =
                MethodHandleVsReflectionDemo.class.getMethod("fail");

        try {
            method.invoke(null);
        } catch (InvocationTargetException e) {
            System.out.println("Reflection: "
                    + e.getClass().getSimpleName());
            System.out.println("Reflection cause: "
                    + e.getCause().getClass().getSimpleName());
        }

        MethodHandle handle = MethodHandles.lookup()
                .findStatic(MethodHandleVsReflectionDemo.class,
                        "fail", MethodType.methodType(void.class));

        try {
            handle.invokeWithArguments();
        } catch (IOException e) {
            System.out.println("MethodHandle: "
                    + e.getClass().getSimpleName());
            System.out.println("Message: " + e.getMessage());
        }
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 MethodHandleVsReflectionDemo.java
java MethodHandleVsReflectionDemo
```

Stdout:

```text
Reflection: InvocationTargetException
Reflection cause: IOException
MethodHandle: IOException
Message: Lỗi gốc
```

**Giải thích:** cùng một static method `fail()` ném `IOException`. `Method.invoke(null)` bọc lỗi target trong `InvocationTargetException`, còn `MethodHandle.invokeWithArguments()` trong ví dụ cho `IOException` đi trực tiếp đến handler. Đây là đối chiếu **API contract**, không phải bằng chứng method handle luôn nhanh hơn hay thay được reflection ở mọi trường hợp.

Việc `main` khai báo `throws Throwable` chỉ để minh họa đầy đủ các checked `Throwable` mà API method handle có thể công bố; trong một API production nên chọn boundary, kiểu exception và chính sách phù hợp.

## 19. Dynamic proxy: có thể có `UndeclaredThrowableException` thay vì wrapper này

`java.lang.reflect.Proxy` sử dụng `InvocationHandler.invoke(...)`, có hợp đồng riêng. Khi handler ném một **checked Throwable không nằm trong các kiểu được interface method cho phép**, lời gọi qua proxy có thể ném `java.lang.reflect.UndeclaredThrowableException` (unchecked), giữ lỗi gốc qua `getUndeclaredThrowable()`/`getCause()`.

Điều này **khác** `InvocationTargetException` được `Method.invoke` tạo khi method đích ném lỗi.

Ví dụ hàm ý:

```text
Proxy interface method: void run()      (không throws IOException)
InvocationHandler: throw new IOException("network")
Caller của proxy: UndeclaredThrowableException
    └── cause: IOException
```

Đừng nhầm hai lớp chỉ vì cùng ở package `java.lang.reflect` và đều liên quan đến “gọi động”.

### 19.1. Khi một `InvocationHandler` tự dùng `Method.invoke`

Nếu handler nhận một `Method method` rồi gọi `method.invoke(realTarget, args)`, nó có thể nhận `InvocationTargetException` từ Reflection. Nếu handler **ném lại nguyên wrapper checked** mà interface proxy method không khai báo loại đó, proxy có thể bọc tiếp thành `UndeclaredThrowableException`. Do đó chuỗi có thể thành:

```text
UndeclaredThrowableException
  └── cause: InvocationTargetException
        └── cause: IOException
```

Một handler thiết kế tốt cần có chính sách **unwrap Reflection wrapper phù hợp** và quyết định cách chuyển lỗi ra hợp đồng của interface proxy. Đừng chuyển tất cả target failures thành một wrapper không liên quan rồi làm caller không thể hiểu.

### 19.2. Không áp logic unwrap Reflection cho mọi proxy error

Proxy có thể ném các lỗi của chính proxy hoặc handler trực tiếp. Nếu không có `InvocationTargetException` thật sự trong chain, không nên ép cast. Xem từng API, rồi đọc cause nếu cần.

## 20. Java 17 — ví dụ 9: `UndeclaredThrowableException` ở proxy

Tạo **`ProxyUndeclaredExceptionDemo.java`**:

```java
import java.io.IOException;
import java.lang.reflect.Proxy;
import java.lang.reflect.UndeclaredThrowableException;

public class ProxyUndeclaredExceptionDemo {
    public interface Task {
        void run();
    }

    public static void main(String[] args) {
        Task task = (Task) Proxy.newProxyInstance(
                Task.class.getClassLoader(),
                new Class<?>[] {Task.class},
                (proxy, method, values) -> {
                    throw new IOException("I/O trong handler");
                });

        try {
            task.run();
        } catch (UndeclaredThrowableException e) {
            System.out.println("Proxy wrapper: "
                    + e.getClass().getSimpleName());
            System.out.println("Undeclared: "
                    + e.getUndeclaredThrowable()
                            .getClass().getSimpleName());
            System.out.println("Cause message: "
                    + e.getCause().getMessage());
        }
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 ProxyUndeclaredExceptionDemo.java
java ProxyUndeclaredExceptionDemo
```

Stdout:

```text
Proxy wrapper: UndeclaredThrowableException
Undeclared: IOException
Cause message: I/O trong handler
```

**Ý nghĩa:** `Task.run()` không có checked `throws` nhưng handler ném checked `IOException`. Proxy buộc báo lỗi theo một wrapper unchecked phù hợp với hợp đồng method của interface. Đây không phải `Method.invoke`; không có `InvocationTargetException` trong ví dụ này.

Khi thiết kế proxy thật, hãy tách riêng lỗi từ business implementation, lỗi của handler và lỗi từ Reflection do handler có thể dùng.

## 21. Những ngộ nhận cần sửa ngay

| Nhầm lẫn | Thực tế |
| --- | --- |
| “`InvocationTargetException` chính là lỗi nghiệp vụ.” | Thường là wrapper do Reflection tạo; target error ở `getCause()`. |
| “Chỉ checked exception từ target mới bị bọc.” | Target có thể ném unchecked exception hoặc Error, và `Method.invoke` vẫn dùng wrapper cho target-thrown Throwable. |
| “`getTargetException()` trả một chuỗi message.” | Trả đối tượng `Throwable`. |
| “`getCause()` và `getTargetException()` luôn khác nhau.” | Trong wrapper Reflection tiêu chuẩn chúng trỏ tới cùng target throwable. |
| “`method.invoke` ném `IOException` trực tiếp vì method gốc `throws IOException`.” | Caller Reflection thấy checked `InvocationTargetException`; unwrap để lấy IOException. |
| “`IllegalArgumentException` quanh invoke luôn từ target.” | Sai tham số có thể làm chính API invoke ném trực tiếp IllegalArgumentException. |
| “Không tìm thấy method thì phải unwrap target.” | `NoSuchMethodException` xảy ra trong lookup, chưa có target invocation. |
| “`IllegalAccessException` là exception từ body.” | Thường là lỗi kiểm tra quyền truy cập của Reflection. |
| “Đã có wrapper thì toàn bộ body method chạy xong.” | Target đã ném và kết thúc bất thường; body có thể dừng rất sớm. |
| “Nếu target body ném NullPointerException thì catch NullPointerException quanh invoke sẽ bắt.” | Thông thường caller thấy `InvocationTargetException` bọc NPE. |
| “Stack trace của wrapper là đủ tìm dòng code gốc.” | Cần xem `Caused by`/stack của target. |
| “`wrapper.getMessage()` luôn giống message lỗi gốc.” | Phải đọc message từ cause thực tế. |
| “Bắt `Exception` rồi cast cause thành RuntimeException được.” | Có thể null/sai kiểu/checked Error; phải phân loại an toàn. |
| “Wrapper tự rollback side effect.” | Exception chaining chỉ giữ thông tin, không hoàn tác trạng thái. |
| “`Constructor.newInstance` không dùng InvocationTargetException.” | Constructor target ném lỗi có thể bị bọc. |
| “`Class.newInstance()` là lựa chọn hiện đại.” | API cũ đã deprecated; ưu tiên constructor reflection. |
| “MethodHandle cũng luôn bọc target vào InvocationTargetException.” | MethodHandle invocation có hợp đồng khác, có thể truyền trực tiếp target Throwable. |
| “Proxy và Reflection đều luôn dùng cùng wrapper.” | Dynamic proxy có thể dùng `UndeclaredThrowableException`. |
| “Chỉ cần log wrapper class name để biết root cause.” | Log cả Throwable/cause chain và thông tin ngữ cảnh an toàn. |

## 22. Cách debug trong một framework dùng Reflection

Nhiều framework gọi method của ứng dụng gián tiếp: test runner, plugin system, dependency injection, command dispatcher, annotation processor runtime hay một bộ đăng ký callback động. Khi log thấy `InvocationTargetException`:

1. **Đọc cấu trúc cause:** `wrapper.getCause()` có loại gì, message gì?
2. **Kiểm tra stack trace của cause** để tìm vị trí trong code method đích.
3. Xác định method/constructor được gọi, receiver và số/kiểu tham số.
4. Nếu gặp `NoSuchMethodException`/`IllegalAccessException` ở ngoài wrapper, hãy sửa lookup/quyền truy cập thay vì debug body.
5. Nếu target checked exception (ví dụ IOException), hỏi tầng nào có chính sách retry/fallback hoặc phải báo failure.
6. Nếu target unchecked exception, kiểm tra input, invariant và trạng thái trước khi ném.
7. Nếu có nhiều wrapper, duyệt chain một cách có mục đích, không chỉ lấy `cause.getCause()` một cách máy móc.
8. Nếu target sử dụng resource, xem `getSuppressed()` trên target Throwable và các cause phù hợp khi có lỗi dọn dẹp.
9. Đánh giá side effect trước thất bại: tác vụ đã ghi dữ liệu, gọi mạng hay sửa cache chưa?
10. Đặt log/monitoring ở ranh giới phù hợp, không in raw stack/cause ra client công khai.

### 22.1. Ví dụ log có ý nghĩa

Thay vì chỉ:

```text
ERROR InvocationTargetException
```

một báo cáo hữu ích hơn có thể lưu:

```text
Operation: Service.load
Wrapper: InvocationTargetException
Cause type: IOException
Cause message: Không đọc được bad
Correlation ID: REQ-42
```

Đây là **định dạng minh họa**, không phải API logger cụ thể. Với logger thực, tốt hơn là truyền chính đối tượng Throwable làm tham số lỗi để giữ stack/cause/suppressed, đồng thời ghi ngữ cảnh theo chính sách dữ liệu.

## 23. Bảo toàn stack và nguyên nhân khi chuyển tầng

Một adapter có thể muốn chuyển lỗi do target sang exception nghiệp vụ:

```java
try {
    method.invoke(target);
} catch (InvocationTargetException wrapper) {
    throw new ServiceOperationException(
            "Không hoàn tất thao tác", wrapper.getCause());
}
```

Đây là **mảnh code** giả định `ServiceOperationException` có constructor nhận cause và các checked exception Reflection khác được xử lý.

Bạn có hai lựa chọn có ý nghĩa khác nhau:

- **Giữ chính cause target làm cause của wrapper nghiệp vụ:** thuận tiện cho caller phân loại nguyên nhân và giảm lớp Reflection trong cause chain nếu tầng ngoài không cần chi tiết Reflection.
- **Giữ nguyên `InvocationTargetException` làm cause:** hữu ích khi cần cho thấy chính tầng Reflection thất bại, nhưng có thể để lộ chi tiết implementation cho nhiều tầng.

Không có quy tắc bắt buộc mọi nơi phải xóa wrapper Reflection. Quan trọng là **giữ đường nguyên nhân**, không làm mất target exception hoặc ép tất cả trường hợp về một loại lỗi không phù hợp.

### 23.1. Không tự động xóa thông tin về suppressed

Nếu target throwable có suppressed exceptions, việc truyền **cùng object target** làm cause thường giữ lại suppressed ở đúng đối tượng đó. Nếu tạo một exception mới chỉ với `getMessage()` và không truyền cause, thông tin suppressed có thể bị mất khỏi chuỗi báo cáo.

Điều này đặc biệt quan trọng khi target dùng try-with-resources: body ném một lỗi, `close()` ném thêm lỗi phụ, và Reflection lại bọc primary thành `InvocationTargetException`.

## 24. Khi nào nên dùng Reflection thay vì lời gọi trực tiếp?

Nếu kiểu target và tên method đã biết tại compile-time, lời gọi trực tiếp thường:

- Đơn giản, có type checking và kiểm tra checked exception rõ.
- Dễ refactor, được IDE hỗ trợ.
- Không cần lookup hoặc unwrap wrapper Reflection.
- Dễ đọc và test hơn.

Reflection phù hợp khi **động** thật sự là yêu cầu: framework nạp plugin, tìm handler theo annotation, tạo object theo metadata, gọi method được chọn lúc chạy, test runner, dependency injection hoặc mô hình extension.

**Quy tắc thiết kế:** không dùng Reflection chỉ để có thể gọi một method đã biết rõ. Nếu phải dùng, nên đóng gói logic lookup/invoke/error translation vào một tầng, không lan `InvocationTargetException` khắp mã nghiệp vụ nếu điều đó không cần thiết.

## 25. Bài tập thực hành

### Bài 1 — Phân biệt wrapper và target

Chạy `ReflectiveMethodFailureDemo`. Thay lỗi của `load("bad")` thành `IllegalStateException("input")`. Dự đoán `wrapper.getClass()` và `wrapper.getCause().getClass()`. Có cần `catch(IOException)` quanh `Method.invoke` không? Giải thích bằng chữ ký API.

### Bài 2 — Sai argument khác với target-throw

Trong `ReflectionVsTargetDemo`, đổi lời gọi `method.invoke(target, 123)` thành `method.invoke(target, "boom")` rồi quan sát loại ngoại lệ tại caller. Dự đoán vì sao một trường hợp là `IllegalArgumentException` trực tiếp của Reflection, còn trường hợp kia là wrapper có cause `IllegalStateException`.

### Bài 3 — Constructor target

Thêm một điều kiện `if (amount == 0) throw new IllegalStateException("zero");` vào `Account`. Gọi constructor reflection với 0 và -1; xác định wrapper có giống nhau không, và cause khác nhau thế nào.

### Bài 4 — Đọc cause chain

Chạy `ReflectionCauseChainDemo`. Tại handler, in message của wrapper, direct cause, root cause. Tại sao không nên phụ thuộc wrapper message để lấy error nghiệp vụ? Dùng getter nào để xem `IOException`?

### Bài 5 — Ném lại checked exception

Chạy `RethrowTargetIOExceptionDemo`. Đổi `runReflectively` để bọc IOException vào `IllegalStateException("...", cause)` thay vì ném trực tiếp. Caller phải thay handler ra sao? So sánh stack của wrapper mới và cause gốc.

### Bài 6 — So sánh method handle

Chạy `MethodHandleVsReflectionDemo`. Nêu tên API nào tạo `InvocationTargetException` khi `fail` ném IOException và API nào cho IOException đi trực tiếp trong ví dụ. Không dùng kết quả này để suy đoán hiệu năng.

### Bài 7 — Proxy

Chạy `ProxyUndeclaredExceptionDemo`. Thêm `throws IOException` vào khai báo `Task.run()`. Dự đoán khác biệt về khả năng checked exception đi qua proxy method khi handler ném IOException. Giải thích vì sao không nên cố bắt `InvocationTargetException` trong code chỉ gọi proxy trực tiếp.

### Bài 8 — Trả `void` và static

Chạy `ReflectiveReturnValuesDemo`. Vì sao `ping.invoke(target)` trả null, còn `version.invoke(null)` trả `"v1"`? Nếu gọi một **instance method** qua `invoke(null)`, lỗi thuộc nhóm target failure hay lỗi chuẩn bị invocation?

### Bài 9 — Thiết kế API

Một plugin framework chọn method theo tên rồi gọi qua `Method.invoke`. Hãy thiết kế API trả lỗi: caller có cần thấy `InvocationTargetException` không, hay nên nhận `PluginExecutionException` với target throwable làm cause? Nêu ưu/nhược của hai lựa chọn.

### Bài 10 — Root cause và suppressed

Giả sử target dùng try-with-resources, body ném `IOException("read")`, close ném `IOException("close")`, rồi Reflection bọc lỗi. Vẽ cấu trúc wrapper → target primary → suppressed. Phương thức getter nào truy cập từng tầng? Vì sao `wrapper.getSuppressed().length` có thể bằng 0 nhưng target vẫn có lỗi suppressed?

### Bài 11 — Lỗi từ lookup

Tạo một method public `hello(int)`. Gọi `getMethod("hello", String.class)`. Compiler có phát hiện sai không? Exception thực tế là gì? Method body có chạy không? Vì sao đây **không phải** `InvocationTargetException`?

### Bài 12 — Kiểm thử ổn định

Viết JUnit 5 test dùng `assertThrows(InvocationTargetException.class, () -> method.invoke(target))` khi body target chủ động ném `IllegalArgumentException`. Xác nhận cause type/message mà không so sánh stack trace text hoặc số dòng JDK.

## 26. Checklist hiểu và xử lý đúng

- [ ] Tôi biết `InvocationTargetException` là checked subtype của `ReflectiveOperationException` chưa?
- [ ] Tôi phân biệt rõ exception do `Method.invoke`/`Constructor.newInstance` **bọc** và target error **thật** chưa?
- [ ] Tôi biết `getCause()`/`getTargetException()` trả Throwable gốc, không phải message chưa?
- [ ] Tôi hiểu lỗi target là checked, unchecked hoặc Error đều có thể được bọc chưa?
- [ ] Tôi không bắt `IOException` đơn độc quanh `Method.invoke` rồi kỳ vọng nhận checked IOException từ body chứ?
- [ ] Tôi đã phân biệt lookup failure (`NoSuchMethodException`) với invocation failure chưa?
- [ ] Tôi không nhầm lỗi sai argument/access/null receiver do Reflection với lỗi từ body target chưa?
- [ ] Tôi hiểu `getStackTrace()` của wrapper khác với stack trace của cause chưa?
- [ ] Khi unwrap, tôi có phân loại `IOException`, `RuntimeException`, `Error` và checked khác theo hợp đồng chưa?
- [ ] Tôi không cast thẳng mọi cause sang RuntimeException chưa?
- [ ] Nếu đổi exception ở tầng cao, tôi giữ target Throwable làm cause khi phù hợp chưa?
- [ ] Tôi nhớ wrapper không rollback side effect của method/constructor đã chạy trước khi lỗi chưa?
- [ ] Với constructor Reflection, tôi biết tìm thấy metadata không tự cấp quyền gọi chưa?
- [ ] Tôi biết `Class.newInstance()` cũ đã deprecated và có cơ chế exception khác chưa?
- [ ] Tôi không mặc định `MethodHandle` hay proxy đều dùng InvocationTargetException chưa?
- [ ] Tôi phân biệt `UndeclaredThrowableException` của proxy với `InvocationTargetException` của Method.invoke chưa?
- [ ] Khi có nhiều tầng wrapping, tôi đọc cause chain có mục đích và không mất thông tin suppressed chưa?
- [ ] Tôi log target failure đầy đủ nhưng không phơi stack trace nội bộ cho client công khai chưa?
- [ ] Tôi cân nhắc lời gọi trực tiếp khi method được biết ở compile-time thay vì Reflection không cần thiết chưa?
- [ ] Tôi có test ít nhất một ca thành công, lỗi target, lỗi lookup và lỗi argument chưa?

**Kết luận:** `InvocationTargetException` là **lớp bọc do các API Reflection như `Method.invoke` và `Constructor.newInstance` báo khi mã được gọi ném lỗi**. Để biết ngoại lệ thực tế, dùng **`getCause()` hoặc `getTargetException()`**. Đừng đồng nhất lỗi của API Reflection trước khi chạy body với lỗi từ target, đừng suy target exception từ wrapper message, và hãy giữ cause/stack khi chuyển lỗi sang hợp đồng bên ngoài. Đọc đúng tầng ngoại lệ giúp chẩn đoán hệ thống dùng Reflection rõ ràng hơn và tránh xử lý sai loại failure.