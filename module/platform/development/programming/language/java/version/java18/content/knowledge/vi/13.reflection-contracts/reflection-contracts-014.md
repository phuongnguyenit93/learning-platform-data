# Null receiver, lỗi truy cập và lỗi khởi tạo lớp: xác định đúng giai đoạn thất bại

> **Phạm vi:** Chương **Hợp đồng reflection** trong module `JAVA_VERSION_JAVA18`. Java 18 và các JDK hiện đại tiếp tục dùng các hợp đồng công khai của `java.lang.reflect.Method`, `Field`, `Constructor`, `AccessibleObject` và quy tắc khởi tạo lớp của JVM. Bài giải thích cách xác định **lỗi phát sinh ở giai đoạn nào**: truyền receiver `null`, kiểm tra quyền truy cập, khởi tạo lớp (`<clinit>`) hay thực thi method/constructor. Không dùng API nội bộ hoặc giải pháp nới lỏng encapsulation đã lỗi thời.

**Liên hệ Java 18:** JEP 416 tái triển khai core reflection trên nền Method Handles; đây là thay đổi implementation, không phải lý do để ứng dụng thay đổi cách bắt `NullPointerException`, `IllegalAccessException`, `InvocationTargetException` hay `ExceptionInInitializerError` theo hợp đồng API. Trên JDK hiện đại, hãy dựa vào Javadoc chính thức thay vì giả định chi tiết class nội bộ thực hiện reflection.

## 1. Vấn đề: cùng một lời gọi reflection nhưng có nhiều điểm thất bại

Trong code Java bình thường, compiler thường kiểm tra kiểu và khả năng truy cập trước khi chạy. Với reflection, chương trình có thể lấy một `Method` hay `Field` ở runtime rồi thực hiện thao tác:

~~~java
Method method = targetClass.getDeclaredMethod("process");
Object result = method.invoke(receiver);
~~~

Hai dòng này **không cùng một giai đoạn**:

1. `getDeclaredMethod` lấy metadata về method, không tự chạy method.
2. `invoke` kiểm tra receiver, kiểu đối số và khả năng truy cập; với method `static`, nó có thể kích hoạt khởi tạo lớp; sau đó mới chạy thân method.
3. Nếu thân method ném lỗi, reflection bọc throwable đó bằng `InvocationTargetException`.

Một lời gọi thất bại có thể bắt nguồn từ dữ liệu đầu vào (receiver `null`), quyền truy cập, trạng thái khởi tạo lớp hoặc exception của chính code được gọi. Nếu chỉ bắt `Exception` chung và ghi “reflection failed”, ta sẽ không biết cần sửa gì.

~~~text
Tìm lớp và member
  │   Class.forName / getDeclaredMethod / getDeclaredField
  │
  ├── Metadata không tồn tại: ClassNotFoundException / NoSuchMethodException / ...
  ▼
Chuẩn bị gọi hoặc đọc/ghi
  │
  ├── Receiver null cho instance member: NullPointerException
  ├── Receiver/arguments sai kiểu: IllegalArgumentException
  └── Không đủ quyền thực hiện: IllegalAccessException
  │
  ▼
Kích hoạt khởi tạo lớp (khi thao tác yêu cầu)
  │
  └── Static initialization lỗi: ExceptionInInitializerError
  │
  ▼
Thực thi method / constructor
  │
  └── Code được gọi ném throwable: InvocationTargetException (cause)
~~~

Sơ đồ giúp **phân loại nguồn lỗi**, không cam kết mọi JVM kiểm tra các điều kiện sai đồng thời theo đúng thứ tự trên. Khi kiểm thử từng hợp đồng, hãy làm các điều kiện khác hợp lệ để lỗi quan sát được không nhập nhằng.

## 2. Receiver null: instance khác static

Chữ ký `Method.invoke`:

~~~java
Object invoke(Object obj, Object... args)
        throws IllegalAccessException, InvocationTargetException;
~~~

`obj` là **receiver**:

- Với **instance method**, `obj` phải là một object phù hợp với lớp khai báo. Nếu `obj == null`, `Method.invoke` ném `NullPointerException` trực tiếp.
- Với **static method**, receiver **được bỏ qua**; truyền `null` là hợp lệ và thường là cách biểu đạt rõ ràng nhất.
- Nếu receiver không null nhưng sai kiểu, `Method.invoke` ném `IllegalArgumentException`.

~~~java
Method instance = Greeter.class.getMethod("greet");
instance.invoke(null);           // NullPointerException
instance.invoke(new Greeter());  // Hợp lệ

Method staticMethod = Greeter.class.getMethod("version");
staticMethod.invoke(null);       // Hợp lệ cho static method
~~~

Tương tự với `Field.get(Object)` và `Field.set(Object, Object)`:

| Member | Receiver null | Lý do |
|---|---|---|
| Instance `Method.invoke(null)` | `NullPointerException` | Thiếu object để gọi method. |
| Static `Method.invoke(null)` | Hợp lệ | Receiver không được dùng. |
| Instance `Field.get(null)` | `NullPointerException` | Thiếu object chứa field. |
| Instance `Field.set(null, value)` | `NullPointerException` | Thiếu object cần sửa field. |
| Static `Field.get(null)` | Hợp lệ | Truy cập field thuộc class. |
| Static `Field.set(null, value)` | Hợp lệ nếu field được phép ghi | Receiver không dùng, nhưng quyền truy cập/`final` vẫn có thể chặn ghi. |

Không nhầm `null` receiver với **đối số truyền vào method**. Ví dụ một instance method nhận một tham số `String` có thể được gọi bằng `invoke(receiver, (Object) null)`; lúc này receiver vẫn là `receiver`, còn tham số được truyền vào có giá trị `null`.

### Vì sao NPE của receiver khác NPE trong method?

Giả sử method được gọi có code:

~~~java
public void crash() {
    String input = null;
    System.out.println(input.length());
}
~~~

- `method.invoke(null)` trên instance method: lỗi **trước khi chạy thân method**, `NullPointerException` trực tiếp.
- `method.invoke(validReceiver)`: method bắt đầu chạy, rồi `input.length()` gây `NullPointerException`. Reflection **bọc** throwable thành `InvocationTargetException`; `getCause()` là `NullPointerException`.

Đây là một dấu hiệu rất quan trọng để phân tích log: tên lớp exception ngoài cùng cho biết lỗi xảy ra trước hay trong lời gọi mục tiêu.

## 3. Access: tìm thấy method chưa có nghĩa được gọi

`Class.getDeclaredMethod("secret")` có thể lấy metadata cho một private method, kể cả khi caller không có quyền gọi nó. Tương tự, `getDeclaredField` có thể mô tả field private.

~~~java
Method hidden = Vault.class.getDeclaredMethod("secret");

// Đã lấy được Method không có nghĩa đã được quyền invoke.
hidden.invoke(vault); // Có thể ném IllegalAccessException.
~~~

Với các thao tác như `Method.invoke`, `Field.get`, `Field.set` và `Constructor.newInstance`, nếu vẫn áp dụng kiểm tra truy cập Java và member không thể truy cập từ caller, API ném **`IllegalAccessException`** (checked exception).

`getDeclaredMethod` khác `getMethod`:

| Tra cứu metadata | Đối tượng tìm được | Kiểm tra truy cập khi gọi |
|---|---|---|
| `getMethod(...)` | Public method (kể cả kế thừa khi phù hợp). | Vẫn cần class/member có thể truy cập từ caller. |
| `getDeclaredMethod(...)` | Method được khai báo trực tiếp, có thể là private. | Lấy metadata không bỏ qua access check. |
| `getDeclaredField(...)` | Field khai báo trực tiếp, có thể là private. | `Field.get/set` vẫn kiểm tra quyền. |
| `getDeclaredConstructor(...)` | Constructor được khai báo, có thể không public. | `newInstance` vẫn kiểm tra quyền. |

Một exception `NoSuchMethodException` ở bước lấy metadata có nghĩa là **không tìm được method theo tên và parameter types**, không phải `IllegalAccessException`. Đừng sửa quyền truy cập khi chương trình thực ra đang tra sai chữ ký method.

### Dùng trySetAccessible() và giới hạn module

Khi có lý do chính đáng để đọc member không public, API hiện đại cung cấp:

~~~java
Method hidden = Vault.class.getDeclaredMethod("secret");

if (hidden.trySetAccessible()) {
    // Có thể thử invoke sau khi suppress access check.
    Object value = hidden.invoke(vault);
} else {
    // Phải dùng public API hoặc cấu hình opens phù hợp.
}
~~~

`trySetAccessible()` trả `false` nếu không thể bật quyền bỏ qua access check. `setAccessible(true)`, trong trường hợp không thể bật, ném **`InaccessibleObjectException`** (unchecked).

Điểm khác nhau:

- `IllegalAccessException`: lỗi khi **thực hiện** thao tác reflectively (invoke/get/set/newInstance) mà không đủ quyền.
- `InaccessibleObjectException`: lỗi khi **cố bật** `setAccessible(true)` nhưng giới hạn truy cập — thường do ranh giới module — không cho phép.
- `trySetAccessible() == false`: kiểm tra khả năng mở quyền thất bại nhưng **không** ném `InaccessibleObjectException` cho trường hợp này.

Đừng gọi `setAccessible(true)` rồi giả định nó luôn hoạt động trên JDK hiện đại. JPMS bảo vệ private members của package trong named module **không được mở** cho module caller.

Với hai named modules, ví dụ:

~~~java
// module-info.java của module chứa model:
module example.model {
    exports example.model.api;
}
~~~

`exports` cho phép bên ngoài dùng public API, **không** có nghĩa mọi private method/field có thể mở bằng reflection. Nếu thật sự cần deep reflection cho module cụ thể:

~~~java
module example.model {
    exports example.model.api;
    opens example.model.api to example.consumer;
}
~~~

Chỉ mở package cần thiết cho consumer đã xác định. Không dùng các cờ runtime cũ để tắt hàng loạt encapsulation, và không cố thay đổi member private của JDK nếu có public API phù hợp.

## 4. Class initialization: khác class loading và đọc metadata

Một class có thể đã được load và có `Class<?>` object nhưng **chưa được khởi tạo**. Khởi tạo lớp bao gồm thực hiện static field initializer và static initializer (`<clinit>`).

Hai lời gọi này có ý nghĩa khác nhau:

~~~java
// Chỉ load, không yêu cầu chạy static initializer:
Class<?> type = Class.forName(
        "example.BrokenService",
        false,
        Thread.currentThread().getContextClassLoader());

// Dạng một tham số sẽ yêu cầu khởi tạo lớp:
Class<?> initialized = Class.forName("example.BrokenService");
~~~

Khi thực hành, nên dùng class loader rõ ràng của chương trình thay vì giả định thread context class loader luôn phù hợp.

Các thao tác lấy metadata như `Class.getDeclaredMethod` hoặc `getDeclaredField` **không tự thực thi** method và không yêu cầu class initialization chỉ vì đọc thông tin. Nhưng các thao tác sau có thể kích hoạt initialization nếu class chưa được khởi tạo:

- `Method.invoke(null, ...)` với **static method**.
- `Field.get(null)` hoặc `Field.set(null, value)` với **static field**.
- `Constructor.newInstance(...)` khi thực sự tạo instance.
- `Class.forName(String)` theo overload yêu cầu initialize.

Với instance object đã được tạo bình thường, declaring class thường đã được khởi tạo trước đó; đừng dùng instance method làm ví dụ chính để chứng minh lần đầu class initialization.

### Khi static initializer ném lỗi

~~~java
class BrokenService {
    static final int CONFIG = loadConfig();

    private static int loadConfig() {
        throw new IllegalStateException("CONFIG_INIT_FAILED");
    }

    public static int readConfig() {
        return CONFIG;
    }
}
~~~

Nếu reflection kích hoạt initialization của `BrokenService`:

1. `loadConfig()` ném một runtime exception.
2. Lần initialization thất bại được báo bằng **`ExceptionInInitializerError`** (một `Error`, không phải `Exception` thường).
3. Class bị đánh dấu là **erroneous** trong class loader đó. Các lần cố sử dụng lại class đã khởi tạo lỗi thường dẫn đến **`NoClassDefFoundError`** với thông tin cho thấy không thể initialize class.

**Không nên retry vô hạn trên cùng `Class<?>`** sau khi class initialization đã lỗi. Sửa cấu hình/dependency và khởi động một JVM mới trong thử nghiệm để kiểm tra lần initialization sạch. Cũng không nên bắt `Exception` chung rồi cho rằng đã bao quát `ExceptionInInitializerError`; vì nó là `Error`.

### Phân biệt ExceptionInInitializerError và InvocationTargetException

Hai loại lỗi nói lên hai giai đoạn:

| Exception | Thường xuất hiện khi | Gợi ý điều tra |
|---|---|---|
| `ExceptionInInitializerError` | JVM đang khởi tạo declaring class, static initialization thất bại. | Xem static fields, static blocks, nguyên nhân `getCause()`. |
| `InvocationTargetException` | Method/constructor **đã được gọi**, code mục tiêu ném throwable. | Xem `getCause()` hoặc `getTargetException()`. |
| `NoClassDefFoundError` sau initialization lỗi | JVM cố dùng lại class ở trạng thái erroneous. | Truy về lỗi `<clinit>` đầu tiên trong log; không coi là thiếu JAR nếu nguyên nhân là init fail. |

`NoClassDefFoundError` cũng có thể liên quan đến lỗi linking/classpath, vì vậy phải xem message và chuỗi nguyên nhân trước khi kết luận. Không suy ra mọi `NoClassDefFoundError` đều bắt nguồn từ static initialization.

## 5. Ví dụ Java 18+: kiểm chứng tách riêng từng giai đoạn

Ví dụ bên dưới có tất cả class trong **một tệp nguồn** để chạy bằng JDK 18+ mà không cần Gradle, thư viện ngoài, module descriptor hay thay đổi JVM flags. Dữ liệu lỗi cố ý không phụ thuộc môi trường:

- Public instance method/field + receiver null → `NullPointerException` trực tiếp.
- Public static method/field + receiver null → hợp lệ.
- Private method trong một top-level class **khác nest** → `IllegalAccessException`.
- Method body ném NPE → `InvocationTargetException` có cause NPE.
- `Class.forName(..., false, ...)` và `getDeclaredMethod` → chỉ lấy class/metadata.
- Invoke static method của class có static initializer lỗi → `ExceptionInInitializerError`; lần thử sau → `NoClassDefFoundError`.

Lưu tên `ReflectionFailureStages.java`:

~~~java
import java.lang.reflect.Field;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;

public final class ReflectionFailureStages {
    public static final class PublicTarget {
        public int score = 41;
        public static int total = 7;

        public String greet() {
            return "hello";
        }

        public static String version() {
            return "v1";
        }

        public void throwInside() {
            String value = null;
            System.out.println(value.length());
        }
    }

    @FunctionalInterface
    interface Operation {
        void run() throws Throwable;
    }

    // Chỉ dùng catch(Throwable) trong test harness để bắt cả Error.
    private static void expect(
            String label,
            Class<? extends Throwable> expected,
            Operation operation) {
        try {
            operation.run();
            throw new AssertionError("Expected " + expected.getName());
        } catch (Throwable failure) {
            if (!expected.isInstance(failure)) {
                throw new AssertionError(
                        label + " got unexpected failure", failure);
            }
            System.out.println(label + ": "
                    + failure.getClass().getSimpleName());
        }
    }

    public static void main(String[] args) throws Exception {
        Method greet = PublicTarget.class.getMethod("greet");
        Field score = PublicTarget.class.getField("score");

        expect("INSTANCE_METHOD_NULL", NullPointerException.class,
                () -> greet.invoke(null));

        expect("INSTANCE_FIELD_NULL", NullPointerException.class,
                () -> score.get(null));

        Method version = PublicTarget.class.getMethod("version");
        Field total = PublicTarget.class.getField("total");

        System.out.println("STATIC_METHOD_NULL: "
                + version.invoke(null));
        System.out.println("STATIC_FIELD_NULL: " + total.get(null));

        Method throwInside = PublicTarget.class.getMethod("throwInside");
        try {
            throwInside.invoke(new PublicTarget());
            throw new AssertionError("Expected target failure");
        } catch (InvocationTargetException wrapper) {
            if (!(wrapper.getCause() instanceof NullPointerException)) {
                throw new AssertionError("Wrong target exception", wrapper);
            }
            System.out.println("TARGET_BODY: InvocationTargetException"
                    + " -> NullPointerException");
        }

        Method secret = PrivateVault.class.getDeclaredMethod("secret");
        expect("ACCESS_CHECK", IllegalAccessException.class,
                () -> secret.invoke(new PrivateVault()));

        // Trong cùng unnamed module, có thể suppress access check.
        if (!secret.trySetAccessible()) {
            throw new AssertionError("Unexpected access restriction");
        }
        System.out.println("ACCESS_ENABLED: "
                + secret.invoke(new PrivateVault()));

        // false: chỉ load class, không chạy <clinit>.
        Class<?> broken = Class.forName(
                "BrokenInitialization",
                false,
                ReflectionFailureStages.class.getClassLoader());

        Method read = broken.getDeclaredMethod("read");
        System.out.println("METADATA_READY: " + read.getName());

        expect("FIRST_STATIC_INVOKE",
                ExceptionInInitializerError.class,
                () -> read.invoke(null));

        expect("SECOND_STATIC_INVOKE",
                NoClassDefFoundError.class,
                () -> read.invoke(null));
    }
}

// Top-level class khác: không phải nestmate của ReflectionFailureStages.
class PrivateVault {
    private String secret() {
        return "classified";
    }
}

// Chưa khởi tạo cho tới khi static method được thực sự gọi.
class BrokenInitialization {
    private static int value = initialize();

    private static int initialize() {
        throw new IllegalStateException("BROKEN_CLINIT");
    }

    public static int read() {
        return value;
    }
}
~~~

Biên dịch và chạy (một JVM mới):

~~~shell
javac ReflectionFailureStages.java
java ReflectionFailureStages
~~~

Kết quả dự kiến:

~~~text
INSTANCE_METHOD_NULL: NullPointerException
INSTANCE_FIELD_NULL: NullPointerException
STATIC_METHOD_NULL: v1
STATIC_FIELD_NULL: 7
TARGET_BODY: InvocationTargetException -> NullPointerException
ACCESS_CHECK: IllegalAccessException
ACCESS_ENABLED: classified
METADATA_READY: read
FIRST_STATIC_INVOKE: ExceptionInInitializerError
SECOND_STATIC_INVOKE: NoClassDefFoundError
~~~

**Điểm xác minh:** `PrivateVault` là top-level class riêng, không phải nested class của `ReflectionFailureStages`. Nếu đặt `PrivateVault` là nested class trong cùng nest, quyền truy cập private của nestmate trên Java hiện đại có thể làm case `IllegalAccessException` không còn đúng. Cấu trúc ví dụ chủ ý tách nest để kiểm thử quyền truy cập có tính xác định.

Cũng lưu ý `trySetAccessible()` thành công ở đây vì mã ví dụ ở cùng unnamed module. Khi chuyển sang hai named modules và package không được `opens`, nó có thể trả `false`; đây là điểm cần được kiểm thử riêng ở môi trường module thực tế.

## 6. Constructor.newInstance: lỗi ở <clinit> khác lỗi constructor body

`Constructor<T>.newInstance(Object... initargs)` không có receiver vì nó **tạo instance mới**. Tuy nhiên, nó vẫn chịu kiểm tra access, tham số và initialization.

~~~java
Constructor<Widget> ctor = Widget.class.getDeclaredConstructor();
Widget widget = ctor.newInstance();
~~~

Phân biệt:

| Giai đoạn | Ví dụ | Lỗi cần nhận diện |
|---|---|---|
| Tìm constructor | `getDeclaredConstructor(int.class)` nhưng không có chữ ký đó. | `NoSuchMethodException` |
| Kiểm tra access | Private constructor chưa được phép dùng. | `IllegalAccessException` |
| Kiểm tra arguments | Số lượng hoặc kiểu argument sai. | `IllegalArgumentException` |
| Khởi tạo declaring class | Static initializer của `Widget` lỗi. | `ExceptionInInitializerError` |
| Thực thi constructor body | Constructor chạy rồi ném exception. | `InvocationTargetException`, cause là throwable từ body. |

Mẫu minh họa để phân biệt body với initialization:

~~~java
class ConstructorThrows {
    ConstructorThrows() {
        throw new IllegalStateException("CTOR_BODY_FAILED");
    }
}

// Nếu code này nằm ở cùng package và có quyền truy cập:
var ctor = ConstructorThrows.class.getDeclaredConstructor();

try {
    ctor.newInstance();
} catch (InvocationTargetException ex) {
    System.out.println(ex.getCause().getMessage());
    // CTOR_BODY_FAILED
}
~~~

Trong ví dụ trên, code constructor **đã bắt đầu chạy**; đó không phải `<clinit>` thất bại. Để test lỗi khởi tạo lớp, dùng một class khác có static initializer ném lỗi và chạy trên JVM mới.

Tránh `Class.newInstance()` vì API này đã **deprecated** và có hợp đồng exception khác; hiện nay dùng `getDeclaredConstructor().newInstance()`.

## 7. Phân tích log bằng “giai đoạn thất bại”

Khi nhận lỗi runtime từ reflection, hãy lần theo các câu hỏi sau:

| Câu hỏi | Dữ kiện cần xem | Hành động thích hợp |
|---|---|---|
| Đã tìm đúng class/member? | `ClassNotFoundException`, `NoSuchMethodException`, `NoSuchFieldException`. | Kiểm tra tên đầy đủ, chữ ký parameter types, class loader. |
| Receiver có phù hợp? | `NullPointerException` trực tiếp ở `invoke/get/set`; `IllegalArgumentException` nếu sai kiểu. | Tạo instance đúng class, truyền đúng receiver và args. |
| Caller có đủ quyền? | `IllegalAccessException` ở lúc invoke/get/set/newInstance. | Dùng public API hoặc mở quyền theo module policy. |
| Có cố bypass encapsulation? | `InaccessibleObjectException` ở `setAccessible(true)` hoặc `trySetAccessible() == false`. | Cân nhắc `opens` có phạm vi; tránh phụ thuộc private API. |
| Class có đang initialize? | `ExceptionInInitializerError`, theo sau có thể là `NoClassDefFoundError`. | Xem nguyên nhân đầu tiên ở static initializer, sửa cấu hình/dependency rồi chạy mới. |
| Method/constructor có đã chạy? | `InvocationTargetException.getCause()`. | Điều tra logic bên trong code mục tiêu. |

Không nên bắt mọi `Throwable` trong production rồi trả `null` hoặc giá trị mặc định. Một `Error` từ class initialization thường chỉ ra trạng thái không thể tiếp tục bình thường trong class loader hiện tại. Với code kiểm thử, bắt `Throwable` có mục đích quan sát là được, nhưng cần giới hạn phạm vi và báo cáo lại chính xác.

### Nhầm lẫn hay gặp: cùng tên NullPointerException

Ví dụ trên có hai NPE:

- `INSTANCE_METHOD_NULL: NullPointerException` — **receiver null**, không có method body nào được chạy.
- `TARGET_BODY: InvocationTargetException -> NullPointerException` — **receiver hợp lệ**, NPE đến từ thân method.

Nếu chỉ log `getCause()` mà không log wrapper và giai đoạn gọi, hai tình huống có thể bị hiểu nhầm. Ngược lại, chỉ log outer exception `InvocationTargetException` mà không xem cause cũng chưa đủ để chẩn đoán lỗi business logic.

### Nhầm lẫn hay gặp: IllegalAccessException vs InaccessibleObjectException

- `IllegalAccessException` đến từ lời gọi thực thi không qua được access check.
- `InaccessibleObjectException` đến từ yêu cầu bật `setAccessible(true)` bị JPMS từ chối.
- `trySetAccessible()` có thể trả `false` để cho phép ứng dụng xử lý bằng đường khác.

Không phải mọi private member đều bị từ chối: quyền phụ thuộc module, package, nestmate, caller và cách member được khai báo.

## 8. Kiểm chứng trong thực tế: ma trận ca thử

| Ca | Điều kiện cô lập | Kết quả mong đợi |
|---|---|---|
| Instance method, receiver null | Public method, đúng số lượng argument. | `NullPointerException` trực tiếp. |
| Static method, receiver null | Public static method, class init thành công. | Thành công. |
| Instance field, receiver null | Public field, đúng loại field. | `NullPointerException` trực tiếp. |
| Static field, receiver null | Public static field, class init thành công. | Thành công. |
| Receiver sai kiểu | Instance method của class A, truyền instance B. | `IllegalArgumentException`. |
| Private method ngoài nest | Không gọi `trySetAccessible` trước khi invoke. | `IllegalAccessException`. |
| Private method trong unnamed module | Bật `trySetAccessible` nếu policy cho phép. | Có thể thành công; minh họa code demo. |
| Private member của named module không mở | Caller thuộc module khác. | `trySetAccessible` false hoặc `setAccessible(true)` ném `InaccessibleObjectException`. |
| Target method ném NPE | Receiver hợp lệ, method body gây NPE. | `InvocationTargetException`, cause NPE. |
| Chỉ lấy metadata class lỗi | `Class.forName(..., false, loader)` + `getDeclaredMethod`. | Không kích hoạt static initialization. |
| Lần đầu invoke static method class lỗi | Static initializer ném unchecked exception. | `ExceptionInInitializerError`. |
| Lần sau dùng lại class lỗi | Cùng ClassLoader/JVM. | `NoClassDefFoundError`. |
| Constructor body ném exception | Class init bình thường. | `InvocationTargetException`, cause từ constructor. |

Hãy ưu tiên **một điều kiện lỗi cho mỗi ca**. Đừng kết hợp receiver null, method private, arguments sai và static initializer lỗi rồi cố suy ra JVM bắt buộc chọn exception nào trước. Một test tốt phải xác nhận rõ giả thiết đầu vào của chính mình.

Với lỗi static initialization, cần chạy JVM mới nếu muốn lặp lại tình huống **lần đầu**. Trong cùng class loader, class đã khởi tạo lỗi không thể được coi là “chưa từng chạy `<clinit>`”.

## 9. Thực hành sửa lỗi theo từng loại

### Lỗi receiver

- Xác định `Modifier.isStatic(method.getModifiers())` hoặc `Modifier.isStatic(field.getModifiers())`.
- Với member instance, truyền đúng object không null.
- Với member static, truyền `null` để thể hiện rằng không cần receiver.
- Kiểm tra argument types/arity riêng với kiểm tra receiver.

~~~java
boolean isStatic = java.lang.reflect.Modifier.isStatic(
        method.getModifiers());
Object receiver = isStatic ? null : targetInstance;
Object result = method.invoke(receiver, arguments);
~~~

Nếu `targetInstance` có thể null và method instance, kiểm tra sớm để tạo thông báo rõ hơn.

### Lỗi quyền truy cập

- Ưu tiên API public và khai báo type/method/field với quyền phù hợp.
- Khi cần reflection vào package của named module khác, cân nhắc thêm `opens package.name to consumer.module` một cách có chủ đích.
- Có thể dùng `trySetAccessible()` để kiểm tra, nhưng không dựa vào `setAccessible(true)` như một bảo đảm.
- Không truy cập private internal JDK API cho một chức năng đã có public API.

### Lỗi khởi tạo lớp

- Xem `ExceptionInInitializerError.getCause()` để biết lỗi từ `<clinit>`.
- Tìm static field initializer, static block và dependency mà chúng gọi.
- Phân biệt lỗi khởi tạo lớp ban đầu với `NoClassDefFoundError` ở lần thử tiếp theo.
- Sửa cấu hình hoặc nguồn lỗi rồi chạy lại bằng JVM mới; không chỉ retry lời gọi reflection trong một class loader đã erroneous.

### Lỗi trong code mục tiêu

- Bắt `InvocationTargetException` tại biên reflection.
- Kiểm tra `getCause()`; có thể là checked exception, runtime exception hoặc error do code đích ném.
- Quyết định chính sách xử lý theo hợp đồng của ứng dụng; đừng biến mọi cause thành `IllegalAccessException` hoặc `NullPointerException` do reflection.

## 10. Câu hỏi tự đánh giá

1. Vì sao `Method.invoke(null)` trên instance method ném NPE, còn trên static method lại có thể thành công?
2. `Field.get(null)` với static field có nghĩa gì?
3. Lấy được `getDeclaredMethod("secret")` có đồng nghĩa có quyền gọi private method không?
4. `IllegalAccessException` và `InaccessibleObjectException` khác nhau ở giai đoạn nào?
5. Vì sao `exports` trong JPMS không tương đương `opens` cho deep reflection?
6. `Class.forName("Broken", false, loader)` khác `Class.forName("Broken")` như thế nào?
7. Vì sao lần đầu khởi tạo lớp có thể ném `ExceptionInInitializerError`, nhưng lần sau lại ném `NoClassDefFoundError`?
8. Vì sao NPE từ thân method bị bọc trong `InvocationTargetException` nhưng NPE do receiver null không bị bọc?
9. `Constructor.newInstance` khi constructor body ném exception trả lỗi nào? Khi static initialization thất bại trả lỗi nào?
10. Vì sao việc đặt class kiểm thử private thành nested class cùng nest có thể khiến bài test `IllegalAccessException` sai trên JDK hiện đại?

**Ghi nhớ:** Phân tích reflection bằng **giai đoạn** thay vì chỉ nhìn tên exception: **receiver null** của instance member → `NullPointerException` trực tiếp; **không đủ quyền thực thi** → `IllegalAccessException`; **không thể bật deep reflection** → `InaccessibleObjectException` hoặc `trySetAccessible() == false`; **static initialization lỗi** → `ExceptionInInitializerError`, sau đó có thể gặp `NoClassDefFoundError`; **code được gọi ném lỗi** → `InvocationTargetException` với cause gốc. Các hợp đồng này có từ Java lâu đời và vẫn có hiệu lực trên JDK hiện đại.

## Tài liệu tham khảo chính thức

- [OpenJDK JEP 416 – Reimplement Core Reflection with Method Handles](https://openjdk.org/jeps/416).
- [Java SE 26: `java.lang.reflect.Method` – `invoke`, receiver và lỗi khởi tạo](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/reflect/Method.html).
- [Java SE 26: `java.lang.reflect.Field` – `get/set`, quyền truy cập và class initialization](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/reflect/Field.html).
- [Java SE 26: `java.lang.reflect.Constructor` – `newInstance`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/reflect/Constructor.html).
- [Java SE 26: `java.lang.reflect.AccessibleObject` – `trySetAccessible` và JPMS](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/reflect/AccessibleObject.html).
- [Java SE 26: `java.lang.Class` – `forName` và metadata lookup](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Class.html).
- [Java SE 26: `ExceptionInInitializerError` – lỗi static initialization](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/ExceptionInInitializerError.html).
- [Java Language Specification, Chapter 12 – Execution: Initialization of Classes and Interfaces](https://docs.oracle.com/javase/specs/jls/se26/html/jls-12.html).
