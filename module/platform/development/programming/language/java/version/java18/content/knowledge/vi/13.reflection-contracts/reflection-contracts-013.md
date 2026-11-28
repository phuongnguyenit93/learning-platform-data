# InvocationTargetException và getCause(): tách lỗi nghiệp vụ của đích khỏi lỗi lời gọi reflection

> **Chương:** Hợp đồng reflection — **mô-đun:** `JAVA_VERSION_JAVA18`. Bài học thuộc lộ trình Java 18 và tập trung vào hợp đồng Reflection API vẫn còn hiệu lực trên các JDK hiện đại. Bạn sẽ học cách nhận diện lỗi được ném **bên trong phương thức/constructor đích** so với lỗi do **cách gọi reflection**, truy xuất `getCause()`, bảo toàn stack trace và báo lỗi đúng trách nhiệm.

Khi gọi phương thức Java theo cách thông thường, exception phát sinh từ phương thức đi thẳng tới caller. Khi dùng `Method.invoke(...)` hoặc `Constructor.newInstance(...)`, exception do mã đích ném được đưa vào một lớp bọc `InvocationTargetException`. Ngược lại, truyền sai receiver, sai số lượng/kiểu tham số, hoặc thiếu quyền truy cập là những vấn đề của thao tác reflection; chúng thường được báo **trực tiếp**, không có lớp bọc `InvocationTargetException`.

Phân biệt hai nguồn lỗi này là điều kiện để chẩn đoán chính xác. Nếu chỉ log tên `InvocationTargetException`, hệ thống sẽ che đi nguyên nhân như `IllegalArgumentException` của nghiệp vụ, `IOException` từ adapter hay `IllegalStateException` của đối tượng đích. Nếu luôn quy mọi `IllegalArgumentException` thành lỗi tham số của reflection, bạn cũng dễ xử lý sai khi chính phương thức đích ném kiểu exception đó.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích điều kiện phát sinh `InvocationTargetException` tại `Method.invoke` và `Constructor.newInstance`.
2. Dùng `InvocationTargetException.getCause()` để lấy đúng `Throwable` do mã đích ném.
3. Phân biệt lỗi nghiệp vụ trong đích với `IllegalAccessException`, `IllegalArgumentException`, `NullPointerException` và lỗi khởi tạo lớp của thao tác reflection.
4. Nhận diện vì sao **cùng một lớp exception** có thể có ý nghĩa khác nhau tùy vị trí xuất hiện trong chuỗi lỗi.
5. Viết mã xử lý phù hợp cho exception checked, unchecked và `Error`, không làm mất nguyên nhân.
6. Áp dụng quy tắc logging, mapping lỗi và chẩn đoán trong ứng dụng sử dụng plugin, DI container, RPC hoặc adapter dựa trên reflection.

## 2. Hợp đồng `InvocationTargetException`

`InvocationTargetException` là một **checked exception**, kế thừa `ReflectiveOperationException`. Theo Javadoc, nó bọc ngoại lệ được ném bởi phương thức hoặc constructor đích khi gọi qua Reflection API.

```text
Ứng dụng
  |
  | Method.invoke(target, args)
  v
Reflection API --------------------------------------+
  |                                                  |
  | kiểm tra receiver, arguments, access             | lỗi tại lời gọi reflection
  |                                                  +--> IllegalArgumentException,
  |                                                       IllegalAccessException, ...
  v
Phương thức đích thực sự chạy
  |
  +--> trả kết quả thành công --> Method.invoke trả kết quả
  |
  +--> ném Throwable ---------> InvocationTargetException
                                  |
                                  +--> getCause() == Throwable của đích
```

Với `Constructor.newInstance(...)`, quy tắc tương tự: constructor ném exception thì caller nhận `InvocationTargetException`; còn lỗi chọn constructor, truyền tham số hay truy cập constructor có các lỗi riêng.

### 2.1. `getCause()` là API nên dùng

`InvocationTargetException.getCause()` trả về ngoại lệ đích đã được bọc. API cũ `getTargetException()` vẫn còn, nhưng Javadoc khuyến nghị dùng `Throwable.getCause()` theo cơ chế exception chaining chung.

```java
try {
    method.invoke(target, arguments);
} catch (InvocationTargetException wrapper) {
    Throwable targetFailure = wrapper.getCause();
    // Phân loại, ghi log hoặc chuyển tiếp targetFailure.
}
```

`getCause()` trả về `Throwable`, không phải mặc định `Exception`. Mã đích có thể ném `RuntimeException`, checked exception, hoặc `Error`. Đừng ép kiểu thẳng sang một exception nghiệp vụ cụ thể khi chưa kiểm tra `instanceof`.

API cho phép `InvocationTargetException` được tạo với target exception bằng `null`. Trong luồng `Method.invoke` thông thường khi đích thực sự ném lỗi, nguyên nhân sẽ được cung cấp; song một utility hoặc thư viện tạo wrapper thủ công có thể khiến `getCause()` trả `null`. Mã xử lý tổng quát nên có nhánh dự phòng.

### 2.2. Không gọi lại phương thức đích để “lấy lỗi thật”

Một lỗi sai là thấy wrapper rồi gọi `method.invoke` lại để tìm nguyên nhân. Điều này có thể lặp giao dịch, ghi dữ liệu hai lần hoặc thay đổi trạng thái hệ thống. Chỉ cần đọc `wrapper.getCause()` để truy vết exception của lần thực thi đã thất bại.

## 3. Bảng phân biệt lỗi đích và lỗi tại lời gọi reflection

| Tình huống | Exception quan sát ở caller | Nguồn phát sinh |
|---|---|---|
| Đích ném `IllegalArgumentException` | `InvocationTargetException`; `getCause()` là `IllegalArgumentException` | Mã đích |
| Đích ném `IOException` | `InvocationTargetException`; cause là `IOException` | Mã đích |
| Đích ném `IllegalStateException` | `InvocationTargetException`; cause là `IllegalStateException` | Mã đích |
| Đích ném `AssertionError` | `InvocationTargetException`; cause là `AssertionError` | Mã đích |
| Truyền receiver sai kiểu cho instance method | `IllegalArgumentException` trực tiếp | Lời gọi reflection |
| Sai số lượng/kiểu tham số hoặc không thể unbox/convert | `IllegalArgumentException` trực tiếp | Lời gọi reflection |
| Receiver `null` khi gọi instance method | `NullPointerException` trực tiếp | Lời gọi reflection |
| Không được truy cập method/constructor | `IllegalAccessException` trực tiếp | Lời gọi reflection |
| `setAccessible(true)` bị chặn bởi module encapsulation | `InaccessibleObjectException` tại thao tác mở quyền | Thiết lập quyền truy cập |
| Khởi tạo lớp kích hoạt bởi invocation bị lỗi | `ExceptionInInitializerError` theo hợp đồng của `Method.invoke` / `Constructor.newInstance` | Khởi tạo lớp, trước khi đích hoàn thành |
| Không tìm thấy method/constructor theo signature | `NoSuchMethodException` tại bước tra cứu | Khâu tìm member |

**Quy tắc phân loại:** bắt `InvocationTargetException` trước, sau đó đọc `getCause()`. Những exception khác phát sinh trực tiếp từ lời gọi hoặc bước chuẩn bị reflection cần được xử lý ở nhánh riêng. Đừng đoán nguồn lỗi chỉ từ tên lớp `IllegalArgumentException`.

## 4. Thực hành: cùng `IllegalArgumentException` nhưng hai nguồn lỗi khác nhau

Ví dụ sau chạy từ source file trên JDK 18 trở lên. Chương trình tạo một đối tượng, lấy method và constructor công khai, rồi cố ý gây các trường hợp lỗi.

Tạo `ReflectionFailureLab.java`:

```java
import java.io.IOException;
import java.lang.reflect.Constructor;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;

public class ReflectionFailureLab {

    public static final class CheckoutService {
        public CheckoutService(int initialBalance) {
            if (initialBalance < 0) {
                throw new IllegalArgumentException(
                        "Số dư ban đầu không hợp lệ");
            }
        }

        public int charge(int amount) throws IOException {
            if (amount < 0) {
                throw new IllegalArgumentException(
                        "Số tiền thanh toán phải không âm");
            }
            if (amount == 0) {
                throw new IOException("Cổng thanh toán không phản hồi");
            }
            return amount * 2;
        }

        public void failWithError() {
            throw new AssertionError("Lỗi nghiêm trọng tại đích");
        }
    }

    @FunctionalInterface
    interface ReflectiveCall {
        Object execute() throws ReflectiveOperationException;
    }

    private static void probe(String label, ReflectiveCall call) {
        System.out.println("\n" + label);
        try {
            Object value = call.execute();
            System.out.println("SUCCESS: " + value);
        } catch (InvocationTargetException wrapper) {
            Throwable cause = wrapper.getCause();
            System.out.println("TARGET_THROWN: " +
                    (cause == null ? "(cause = null)" :
                     cause.getClass().getSimpleName()));
            System.out.println("Message: " +
                    (cause == null ? "(unknown)" : cause.getMessage()));
        } catch (ReflectiveOperationException e) {
            System.out.println("REFLECTION_FAILURE: " +
                    e.getClass().getSimpleName());
        } catch (IllegalArgumentException | NullPointerException e) {
            System.out.println("REFLECTION_CALL_ERROR: " +
                    e.getClass().getSimpleName());
        }
    }

    public static void main(String[] args) throws Exception {
        CheckoutService service = new CheckoutService(100);
        Method charge = CheckoutService.class.getMethod(
                "charge", int.class);
        Method fail = CheckoutService.class.getMethod("failWithError");
        Constructor<CheckoutService> constructor =
                CheckoutService.class.getConstructor(int.class);

        probe("1. Thành công", () -> charge.invoke(service, 5));

        probe("2. Đích ném IllegalArgumentException",
                () -> charge.invoke(service, -1));

        probe("3. Đích ném checked IOException",
                () -> charge.invoke(service, 0));

        probe("4. Sai kiểu tham số reflection",
                () -> charge.invoke(service, "năm"));

        probe("5. Sai receiver reflection",
                () -> charge.invoke("not-a-service", 5));

        probe("6. Receiver null cho instance method",
                () -> charge.invoke(null, 5));

        probe("7. Constructor đích ném exception",
                () -> constructor.newInstance(-1));

        probe("8. Sai tham số Constructor.newInstance",
                () -> constructor.newInstance("not-an-int"));

        probe("9. Đích ném Error",
                () -> fail.invoke(service));
    }
}
```

Chạy:

```text
java ReflectionFailureLab.java
```

Kết quả rút gọn dự kiến:

```text
1. Thành công
SUCCESS: 10

2. Đích ném IllegalArgumentException
TARGET_THROWN: IllegalArgumentException

3. Đích ném checked IOException
TARGET_THROWN: IOException

4. Sai kiểu tham số reflection
REFLECTION_CALL_ERROR: IllegalArgumentException

5. Sai receiver reflection
REFLECTION_CALL_ERROR: IllegalArgumentException

6. Receiver null cho instance method
REFLECTION_CALL_ERROR: NullPointerException

7. Constructor đích ném exception
TARGET_THROWN: IllegalArgumentException

8. Sai tham số Constructor.newInstance
REFLECTION_CALL_ERROR: IllegalArgumentException

9. Đích ném Error
TARGET_THROWN: AssertionError
```

Điểm then chốt nằm ở trường hợp 2 và 4: cả hai đều liên quan đến `IllegalArgumentException`, nhưng trường hợp 2 được bọc trong `InvocationTargetException` vì mã nghiệp vụ đã chạy và ném lỗi; trường hợp 4 bị từ chối khi chuẩn bị gọi method, trước khi method đích nhận được tham số.

### 4.1. Checked exception trong method đích không thoát trực tiếp

`CheckoutService.charge` khai báo `throws IOException`. Khi gọi trực tiếp, caller phải xử lý hoặc khai báo `IOException`. Khi gọi qua `Method.invoke`, phần khai báo `throws` của API reflection là `IllegalAccessException` và `InvocationTargetException`; checked `IOException` của đích nằm trong cause.

Điều này không có nghĩa checked exception bị mất. Nó vẫn là đối tượng `Throwable` nguyên gốc và có thể được lấy qua `getCause()`, sau đó chuyển đổi sang error contract phù hợp của adapter.

### 4.2. Constructor ném lỗi cũng được bọc

Ở trường hợp 7, constructor của `CheckoutService` bắt đầu chạy rồi ném `IllegalArgumentException`. `Constructor.newInstance` bọc lỗi đó vào `InvocationTargetException`. Ở trường hợp 8, tham số `String` không phù hợp tham số `int` của constructor, nên `newInstance` ném `IllegalArgumentException` ngay tại tầng reflection.

Trong mã hiện đại, dùng `getDeclaredConstructor(...)` hoặc `getConstructor(...)` rồi `Constructor.newInstance(...)`. Tránh `Class.newInstance()` vì phương thức này đã deprecated và có hành vi lan truyền exception của constructor khác với API `Constructor.newInstance`.

## 5. Ba bước xử lý lỗi an toàn

Khi viết adapter gọi reflection, nên giữ rõ các nhánh xử lý:

1. **Phân biệt nguồn lỗi tại ranh giới `invoke`:** bắt `InvocationTargetException` để biết lỗi đến từ mã đích; bắt các exception reflection trực tiếp cho lỗi cấu hình hoặc gọi sai.
2. **Giữ nguyên nguyên nhân:** chuyển cause vào exception cấp ứng dụng bằng constructor nhận `Throwable cause`, hoặc truyền tiếp exception nếu hợp đồng cho phép.
3. **Giữ bối cảnh phù hợp:** bổ sung tên member, loại thao tác và mã định danh request/operation mà không ghi các tham số chứa bí mật.

### 5.1. Một adapter giữ phân loại đúng

Đoạn mã sau minh họa một adapter gọi method có một đối số; nó giữ nguyên unchecked exception của đích, chuyển checked exception sang wrapper nghiệp vụ, còn lỗi gọi reflection được chuyển sang exception cấu hình riêng:

```java
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;

public final class ReflectiveInvoker {

    public static final class TargetCheckedFailure
            extends RuntimeException {
        public TargetCheckedFailure(String message, Throwable cause) {
            super(message, cause);
        }
    }

    public static final class ReflectiveCallFailure
            extends RuntimeException {
        public ReflectiveCallFailure(String message, Throwable cause) {
            super(message, cause);
        }
    }

    public static Object callOneArgument(
            Method method, Object receiver, Object argument) {

        try {
            return method.invoke(receiver, argument);

        } catch (InvocationTargetException wrapper) {
            Throwable cause = wrapper.getCause();

            if (cause instanceof RuntimeException runtime) {
                throw runtime;
            }
            if (cause instanceof Error error) {
                throw error;
            }

            throw new TargetCheckedFailure(
                    "Đích thất bại khi gọi " + method.toGenericString(),
                    cause != null ? cause : wrapper);

        } catch (IllegalAccessException
                 | IllegalArgumentException
                 | NullPointerException callFailure) {

            throw new ReflectiveCallFailure(
                    "Không thể gọi " + method.toGenericString(),
                    callFailure);
        }
    }
}
```

Cách xử lý trên phù hợp khi contract của adapter cho phép unchecked exception của đích đi ra nguyên trạng. Trong một số framework, bạn có thể muốn bọc **mọi** lỗi của đích vào một kiểu `TargetFailure` để không trộn lỗi nghiệp vụ với lỗi lập trình ở tầng caller. Dù chọn chiến lược nào, hãy giữ cause và phân loại ngay tại nơi gọi reflection.

Lưu ý: nếu `method` bằng `null` thì `method.invoke(...)` ném `NullPointerException` và nhánh xây dựng message sẽ lại truy cập `method.toGenericString()`, tạo thêm lỗi. Adapter dùng trong production nên kiểm tra đối số bắt buộc ngay đầu hàm:

```java
java.util.Objects.requireNonNull(method, "method");
```

Khi xử lý `Error`, chỉ truyền tiếp nếu chính sách xử lý của hệ thống cho phép; không âm thầm coi nó là lỗi nghiệp vụ có thể retry.

### 5.2. Vì sao phải bắt `InvocationTargetException` trước?

`InvocationTargetException` kế thừa `ReflectiveOperationException`. Nếu chỉ có:

```java
catch (ReflectiveOperationException e) {
    log(e);
}
```

thì code có thể gộp lỗi do đích ném với lỗi truy cập method. Khi cần phân loại, bắt `InvocationTargetException` trước và `ReflectiveOperationException` sau như trong ví dụ `probe`. Nếu đảo thứ tự hai nhánh catch theo quan hệ cha/con trong cùng try, Java compiler sẽ báo nhánh con không thể tới được.

## 6. Khi nào `getCause()` không phải “lỗi gốc cuối cùng”?

`getCause()` của `InvocationTargetException` trả về **lỗi mà method/constructor đích ném ra**, không có nghĩa luôn là điểm bắt đầu sâu nhất của một chuỗi nguyên nhân.

Ví dụ phương thức đích có thể bắt `SQLException`, rồi ném `RepositoryException` có cause là `SQLException`:

```text
InvocationTargetException
  caused by RepositoryException (do mã đích ném)
    caused by SQLException (được mã đích gắn vào cause)
```

Ở ranh giới reflection, `wrapper.getCause()` là `RepositoryException`. Tùy mục đích, bạn có thể đọc tiếp `RepositoryException.getCause()` khi chẩn đoán. Nhưng không nên tự động đi tới “root cause” rồi loại bỏ `RepositoryException`, vì wrapper này có thể mang thông tin nghiệp vụ quan trọng như mã giao dịch và ngữ cảnh repository.

Trường hợp khác: method đích tự sử dụng reflection và ném tiếp `InvocationTargetException` nội bộ. Khi đó, `getCause()` của **wrapper ngoài cùng** có thể là một `InvocationTargetException` khác. Điều này không biến lần `Method.invoke` ngoài thành lỗi infrastructure; chính method đích đã ném object exception đó. Phải xét từng ranh giới lời gọi.

## 7. Stack trace, logging và truyền lỗi qua tầng API

### 7.1. In toàn bộ chuỗi cause khi chẩn đoán

Cách sau giữ chuỗi lỗi khi ghi stack trace:

```java
catch (InvocationTargetException wrapper) {
    wrapper.printStackTrace();
}
```

`Throwable.printStackTrace()` hiển thị cả phần `Caused by`. Trong hệ thống thực tế, dùng logger có thể nhận đối tượng `Throwable` nguyên vẹn:

```java
logger.error("Reflective target failed: {}", method.toGenericString(),
             wrapper.getCause());
```

Đoạn logger là ví dụ minh họa API của logging framework, không phải mã Java SE chạy độc lập.

Nếu chỉ log `wrapper.getMessage()`, thông tin có thể rất ít hoặc `null`, mất tên lỗi và stack trace của method đích. Nếu log cùng một exception ở mọi tầng, hệ thống sẽ tạo nhiều sự kiện trùng gây nhiễu; nên quyết định một tầng chịu trách nhiệm log đầy đủ và để các tầng khác chuyển tiếp nguyên nhân.

### 7.2. Đừng gửi stack trace nội bộ ra client

Trong HTTP/RPC endpoint, phân loại lỗi nhằm quyết định response:

| Loại lỗi | Hướng xử lý |
|---|---|
| Đích báo lỗi validate/input theo contract | Trả mã lỗi nghiệp vụ hoặc response được chuẩn hóa |
| Đích báo lỗi tạm thời với retry policy rõ ràng | Có thể retry theo chính sách nghiệp vụ; cân nhắc idempotency |
| Lỗi cấu hình reflection, sai method signature, sai receiver | Log như lỗi tích hợp/lập trình; trả lỗi server thích hợp |
| Không có quyền truy cập theo JPMS | Kiểm tra exports/opens và thiết kế module, không mặc định mở toàn bộ module |
| `Error` từ đích | Bảo toàn tín hiệu lỗi nghiêm trọng theo chính sách runtime |
| `ExceptionInInitializerError` | Kiểm tra static initializer và nguyên nhân được báo theo hợp đồng khởi tạo lớp |

Không nên trả nguyên văn stack trace, tên class nội bộ hoặc thông tin nhạy cảm tới người dùng cuối. Nhưng trong log chẩn đoán an toàn, lưu tên member, class loader/module khi cần, nơi gọi, loại exception và chuỗi cause.

## 8. Những lỗi ở giai đoạn chuẩn bị khác với lỗi ở đích

Thao tác reflection thường có nhiều giai đoạn:

```text
Class.forName / load class
          |
          v
getMethod / getDeclaredMethod
          |
          v
kiểm tra và cấu hình access
          |
          v
Method.invoke / Constructor.newInstance
          |
          v
mã đích (nếu bắt đầu chạy)
```

Các lỗi trước khi gọi method có ý nghĩa riêng:

- `ClassNotFoundException` khi không tìm thấy class theo tên ở bước tra cứu.
- `NoSuchMethodException` khi không tìm thấy method/constructor với tên và kiểu tham số chính xác.
- `IllegalAccessException` nếu reflection call phải thực thi kiểm soát truy cập và member không được phép truy cập.
- `InaccessibleObjectException` có thể xảy ra khi `setAccessible(true)` không thể mở quyền truy cập do module encapsulation. `trySetAccessible()` có thể trả `false` thay vì ném exception đó.
- `IllegalArgumentException` khi receiver hoặc tham số truyền vào không phù hợp, kể cả sai số lượng tham số hoặc chuyển đổi primitive không hợp lệ.

Không dùng `setAccessible(true)` một cách tràn lan như giải pháp mặc định cho mọi lỗi reflection. Trên JDK hiện đại, Java Platform Module System có quy tắc `exports`/`opens`; API mở access có giới hạn được quy định trong `AccessibleObject`.

### 8.1. Khởi tạo lớp thất bại là nhánh riêng

Khi `Method.invoke` gọi static method hoặc `Constructor.newInstance` khởi tạo một class, việc khởi tạo lớp có thể được kích hoạt. Nếu static initializer thất bại, Javadoc khai báo `ExceptionInInitializerError` theo hợp đồng của các thao tác này.

Do đó không nên mặc định rằng mọi exception quan sát thấy khi invoke đều là `InvocationTargetException`. Phân biệt lỗi khởi tạo lớp với exception do **thân** phương thức hoặc constructor đã thực sự chạy và ném.

## 9. Kiểm thử mà không phụ thuộc stack trace nguyên văn

Stack trace có thể thay đổi giữa JDK, build và implementation. Thay vì assert một chuỗi stack trace cố định, kiểm thử **kiểu exception và chuỗi cause**.

Ví dụ kiểm thử độc lập theo cách assert bằng Java thông thường:

```java
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;

public class ReflectionFailureAssertions {
    public static final class Validator {
        public void validate(int value) {
            if (value < 0) {
                throw new IllegalArgumentException("negative");
            }
        }
    }

    public static void main(String[] args) throws Exception {
        Method method = Validator.class.getMethod("validate", int.class);
        Validator target = new Validator();

        try {
            method.invoke(target, -1);
            throw new AssertionError("Phải nhận InvocationTargetException");
        } catch (InvocationTargetException wrapper) {
            if (!(wrapper.getCause() instanceof IllegalArgumentException)) {
                throw new AssertionError("Sai cause", wrapper);
            }
        }

        try {
            method.invoke(target, "wrong");
            throw new AssertionError("Phải nhận IllegalArgumentException");
        } catch (IllegalArgumentException expected) {
            // Sai kiểu tham số tại tầng reflection; không có wrapper.
        }

        System.out.println("PASS: phân loại lỗi đúng theo nguồn phát sinh");
    }
}
```

Chạy:

```text
java ReflectionFailureAssertions.java
```

Bài kiểm thử cho thấy cùng một kiểu `IllegalArgumentException` nhưng xuất hiện ở hai tầng khác nhau. Bạn có thể mở rộng thêm cho checked exception, constructor, static initializer và trường hợp access bị từ chối trong một module boundary.

## 10. Ranh giới với các API gọi động khác

Mô hình ngoại lệ trong bài này là hợp đồng của **Core Reflection API** `Method.invoke` và `Constructor.newInstance`.

- `MethodHandle.invoke` và `MethodHandle.invokeExact` có hợp đồng riêng, khai báo `throws Throwable`; lỗi từ underlying target có thể lan truyền trực tiếp, không tự động có `InvocationTargetException` như Core Reflection.
- Dynamic proxy qua `InvocationHandler` có cơ chế exception riêng; với checked exception không nằm trong `throws` của interface, proxy có thể phát sinh `UndeclaredThrowableException`. Đây là một wrapper khác với `InvocationTargetException`.
- Một framework có thể bọc `InvocationTargetException` thêm bằng exception của chính framework, ví dụ exception do plugin loader hoặc DI container định nghĩa. Khi debug, đọc từng lớp cause từ API framework tới lớp reflection rồi tới exception của mã đích.

Dù triển khai Core Reflection trên các JDK mới có thay đổi nội bộ kể từ Java 18, ứng dụng nên dựa vào hợp đồng Javadoc công khai của `Method.invoke` và `Constructor.newInstance`, không dựa vào tên class implementation xuất hiện trong một phiên bản stack trace.

## 11. Checklist khi xử lý sự cố reflection

1. Xác định rõ lời gọi lỗi tại `getMethod`, `setAccessible`, `Method.invoke` hay `Constructor.newInstance`.
2. Nếu nhận `InvocationTargetException`, đọc `getCause()` và giữ nguyên object `Throwable` nếu phải báo tiếp.
3. Nếu nhận `IllegalArgumentException` trực tiếp từ `invoke`, kiểm tra receiver, số lượng và kiểu tham số đã truyền.
4. Nếu nhận `IllegalAccessException` hoặc `InaccessibleObjectException`, kiểm tra access visibility và ranh giới module.
5. Nếu nhận `ExceptionInInitializerError`, điều tra static initializer và lỗi khởi tạo class.
6. Ghi lại `method.toGenericString()`, class/module liên quan và dữ liệu chẩn đoán không nhạy cảm.
7. Không gọi lại target chỉ để tái tạo exception. Retry chỉ khi nghiệp vụ cho phép và đã xem xét side effects/idempotency.
8. Không làm mất cause bằng cách tạo `new RuntimeException(e.getMessage())` mà không truyền nguyên nhân.
9. Phân biệt lỗi nghiệp vụ/target với lỗi wiring reflection trước khi quyết định retry, response status hoặc báo động.
10. Kiểm tra trên JDK chạy thật; không viết test phụ thuộc vào tên internal reflection accessor hoặc thứ tự stack frame.

## 12. Bài tập tự kiểm tra

1. `InvocationTargetException` là checked hay unchecked exception?
2. `InvocationTargetException.getCause()` khác gì `getTargetException()` theo hướng dẫn Javadoc hiện đại?
3. Vì sao target ném `IllegalArgumentException` lại khác việc `Method.invoke` ném trực tiếp `IllegalArgumentException`?
4. Nếu target ném `IOException`, caller dùng `Method.invoke` sẽ bắt kiểu gì ở tầng đầu tiên?
5. `Constructor.newInstance(-1)` khi constructor ném lỗi khác gì `Constructor.newInstance("abc")` với constructor nhận `int`?
6. Vì sao không thể ép `getCause()` sang `Exception` trong mọi trường hợp?
7. Nếu `getCause()` trả `RepositoryException` có cause là `SQLException`, bạn nên giữ thông tin nào khi chuyển lỗi?
8. Khi `setAccessible(true)` bị từ chối bởi JPMS, đó có phải `InvocationTargetException` từ target không?
9. Vì sao nên bắt `InvocationTargetException` trước `ReflectiveOperationException`?
10. Vì sao `MethodHandle.invokeExact` không thể mặc định xử lý giống `Method.invoke`?
11. Vì sao một lần retry target không nên được thực hiện chỉ để lấy stack trace rõ hơn?

**Tiêu chí hoàn thành:** Bạn có thể nhìn vào vị trí ném exception và chuỗi cause để xác định lỗi thuộc đích hay cơ chế gọi reflection, bảo toàn exception gốc và viết cách xử lý/kiểm thử phù hợp trên JDK hiện đại.

## 13. Tài liệu chuẩn

- [Method — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/reflect/Method.html): hợp đồng `Method.invoke`, conversions, receiver và các exception trực tiếp.
- [Constructor — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/reflect/Constructor.html): hợp đồng `Constructor.newInstance` và phân biệt lỗi tham số/lỗi constructor.
- [InvocationTargetException — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/reflect/InvocationTargetException.html): `getCause()` và lý do nên dùng thay vì `getTargetException()`.
- [AccessibleObject — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/reflect/AccessibleObject.html): kiểm soát truy cập, `trySetAccessible()` và module encapsulation.
- [Class — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Class.html): `getMethod`/`getDeclaredMethod` và lưu ý về `Class.newInstance()` deprecated.
- [Throwable — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Throwable.html): chuỗi cause, stack trace và chaining.
- [MethodHandle — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/invoke/MethodHandle.html): hợp đồng ném `Throwable` của `invoke` và `invokeExact`.
- [JEP 416 — Reimplement Core Reflection with Method Handles](https://openjdk.org/jeps/416): thay đổi implementation ở Java 18 mà ứng dụng cần phân biệt với hợp đồng API.

