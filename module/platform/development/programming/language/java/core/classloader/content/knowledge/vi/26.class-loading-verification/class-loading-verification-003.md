# Kiểm chứng loadClass khác Class.forName về khởi tạo lớp trong Java

`ClassLoader.loadClass(...)` và `Class.forName(...)` đều có thể trả về `Class<?>` đại diện cho một kiểu Java ở runtime, nhưng **không có cùng cam kết về class initialization**. Đây là điểm quan trọng khi code dùng reflection, plugin, SPI, dependency injection hoặc tự xây `ClassLoader`: nhìn thấy `Class<?>` **chưa có nghĩa** static fields đã nhận giá trị cuối hoặc khối `static { ... }` đã chạy.

**Kết luận cốt lõi cho Java 17+:**

- **`loader.loadClass("p.Target")`:** theo triển khai chuẩn của `ClassLoader`, tìm/nạp lớp theo binary name và **không yêu cầu khởi tạo** lớp. Overload này tương đương gọi `loadClass(name, false)`. Subclass tùy biến có thể thêm side effects; không được suy luận về code override không kiểm soát.
- **`Class.forName("p.Target")`:** dùng class loader của **caller** và **yêu cầu khởi tạo** class nếu chưa initialized.
- **`Class.forName("p.Target", true, loader)`:** chọn loader được truyền tường minh, **yêu cầu khởi tạo** class nếu cần.
- **`Class.forName("p.Target", false, loader)`:** tìm/nạp class qua loader chỉ định nhưng **không yêu cầu khởi tạo**.
- **`Class.forName(module, "p.Target")`:** overload theo `Module` (Java 9+) chỉ cố tìm/nạp, **không link hoặc khởi tạo theo contract API**, trả `null` nếu không tìm thấy; không đồng nhất với overload một `String`.

Bài học thuộc **Java core – classloader / Kiểm chứng hành vi**. Mục tiêu là **chứng minh bằng stdout có kiểm soát** lúc nào `<clinit>` chạy, phân biệt loading/linking/initialization, xử lý lớp đã khởi tạo từ trước, TCCL, compile-time constants, arrays và lỗi initializer. Các thí nghiệm ưu tiên **Java 17+**, cung cấp mã độc lập, lệnh `javac`/`java` và giải thích tại sao output đúng.

## 1. Ba giai đoạn: loading, linking, initialization

Một mô hình dễ nhớ:

```text
Tên lớp + ClassLoader
         │
         ▼
       LOADING
      đọc/tìm bytes,
      tạo runtime Class<?>
         │
         ▼
       LINKING
 verification / preparation / resolution
         │
         ▼
    INITIALIZATION
  thực thi static field initializers
  và static initializer blocks
  (<clinit>) khi JVM yêu cầu
         │
         ▼
  CLASS ĐÃ INITIALIZED
```

- **Loading:** tạo hoặc tra cứu runtime class bằng tên và loader. Parent có thể trả class do parent định nghĩa, thay vì child tự define.
- **Linking:** JVM kiểm tra bytecode, chuẩn bị vùng static data và resolve symbolic references theo các ràng buộc của đặc tả. Một số resolution có thể xảy ra sớm hoặc muộn; **không nên coi sơ đồ là lịch trình cứng**.
- **Initialization:** thực thi các static field initializers và static blocks có liên quan, theo thứ tự quy định; JVM bảo đảm protocol initialization chỉ diễn ra một lần thành công cho **mỗi runtime class/interface**.

**Preparation không phải initialization:** một static field có thể đã được chuẩn bị với giá trị mặc định trước khi initializer Java gán giá trị mong muốn. Do đó đọc `Class<?>` qua `loadClass` chưa thể chứng minh static state “đã sẵn sàng”.

**Object creation còn là bước khác:** `ClassLoader.loadClass` hoặc `Class.forName` không tự gọi constructor instance; `new Target()` hay `Constructor.newInstance()` mới tạo object. Khi class chưa initialized, việc tạo instance yêu cầu initialization trước khi constructor hoạt động.

## 2. Bảng so sánh các overload trên Java 17

| Lời gọi | Loader sử dụng | Yêu cầu initialize? | Khi không tìm thấy |
| --- | --- | --- | --- |
| `loader.loadClass(name)` | `loader` object | **Không** theo implementation chuẩn | `ClassNotFoundException` |
| `Class.forName(name)` | Defining loader của **caller class** | **Có** | `ClassNotFoundException` |
| `Class.forName(name, true, loader)` | Loader được chỉ định; `null` nghĩa bootstrap | **Có** | `ClassNotFoundException` |
| `Class.forName(name, false, loader)` | Loader được chỉ định | **Không** | `ClassNotFoundException` |
| `Class.forName(module, name)` | Module được chỉ định và loader tương ứng | **Không**, và không link theo Javadoc | Trả `null` |
| `Target.class` | Compile-time type reference | **Không tự yêu cầu** | N/A; type phải hợp lệ trong ngữ cảnh biên dịch |
| `new Target()` | Type đã resolution từ bytecode | **Có nếu cần** | Có thể gặp lỗi loading/linking/initialization |

**Quan trọng:** `loadClass(name, false)` với `resolve=false` **không có nghĩa JVM chắc chắn không làm linking nào**. Một số linking/verification có thể xảy ra như một phần của runtime. Kết luận được hỗ trợ ở đây là **không yêu cầu thực thi initializer**, chứ không phải “bytes chưa từng được kiểm tra”.

**Không nhầm `resolveClass` với initialization.** `ClassLoader.resolveClass(Class<?>)` dùng cho linking; nó không phải API bảo đảm chạy `<clinit>`.

## 3. Cách tạo một thí nghiệm đáng tin

Thí nghiệm sai phổ biến là:

```java
System.out.println(Target.value);
Class<?> result = loader.loadClass("demo.Target");
```

Đây là **snippet sai mục đích kiểm chứng** nếu `Target.value` là static field không phải compile-time constant: lần đọc field đầu tiên có thể **đã khởi tạo `Target` trước khi gọi `loadClass`**. Khi đó không thấy static block chạy ở câu lệnh thứ hai không chứng minh điều mong muốn.

Để quan sát đúng:

1. Dùng **lớp đích chưa được active-use trước đó**, lý tưởng mỗi phép thử một class khác nhau.
2. In các dấu mốc **trước và sau** API cần kiểm tra.
3. Đặt dấu mốc `System.out.println("INIT ...")` bên trong static initializer của lớp đích.
4. Dùng **binary name string** để yêu cầu load mà không vô tình truy cập static member của lớp đích.
5. Chạy **mỗi chương trình trong một tiến trình JVM mới** khi cần reset trạng thái. Initialization thành công không thể chạy lại bằng cách gọi `forName` nhiều lần trên cùng runtime class.
6. Nếu so hai loaders, giữ rõ **defining loader identity** và tách classpath plugin khỏi host.
7. Không dùng `Thread.sleep` để suy đoán đã initialize hay chưa; dựa trên markers và hành vi Java/JVM được đặc tả.

Trên HotSpot, logging `-Xlog:class+load=info` có thể hỗ trợ quan sát loading, nhưng output dài và phụ thuộc JVM. **Static initializer marker là minh chứng đơn giản hơn cho thời điểm initialization** trong các demo nhỏ.

## 4. Thực hành A — `loadClass`, `forName(false)` và `forName(true)`

Tạo project:

```text
initialization-lab/
└── src/demo/LoadVsForNameDemo.java
```

**`src/demo/LoadVsForNameDemo.java`:**

```java
package demo;

public final class LoadVsForNameDemo {
    static final class LoadOnly {
        static {
            System.out.println("INIT LoadOnly");
        }
    }

    static final class FalseTarget {
        static {
            System.out.println("INIT FalseTarget");
        }
    }

    static final class TrueTarget {
        static {
            System.out.println("INIT TrueTarget");
        }
    }

    static final class ActiveTarget {
        static {
            System.out.println("INIT ActiveTarget");
        }

        static void ping() {
            System.out.println("PING ActiveTarget");
        }
    }

    private static String binaryName(String simpleName) {
        return LoadVsForNameDemo.class.getName() + "$" + simpleName;
    }

    public static void main(String[] args) throws Exception {
        ClassLoader app = LoadVsForNameDemo.class.getClassLoader();

        System.out.println("1 before loadClass");
        Class<?> loaded = app.loadClass(binaryName("LoadOnly"));
        System.out.println("2 loaded=" + loaded.getSimpleName());

        System.out.println("3 before forName(false)");
        Class<?> notInitialized = Class.forName(
                binaryName("FalseTarget"), false, app);
        System.out.println("4 loaded=" +
                notInitialized.getSimpleName());

        System.out.println("5 before forName(true)");
        Class<?> initialized = Class.forName(
                binaryName("TrueTarget"), true, app);
        System.out.println("6 loaded=" +
                initialized.getSimpleName());

        System.out.println("7 initialize the earlier LoadOnly");
        Class<?> later = Class.forName(
                binaryName("LoadOnly"), true, app);
        System.out.println("8 same Class=" + (loaded == later));

        System.out.println("9 before active use");
        ActiveTarget.ping();
        System.out.println("10 finished");
    }
}
```

Từ thư mục `initialization-lab`, biên dịch/chạy trên **JDK 17+**:

```sh
javac --release 17 -d out src/demo/LoadVsForNameDemo.java
java -cp out demo.LoadVsForNameDemo
```

**Stdout dự kiến trong một JVM mới:**

```text
1 before loadClass
2 loaded=LoadOnly
3 before forName(false)
4 loaded=FalseTarget
5 before forName(true)
INIT TrueTarget
6 loaded=TrueTarget
7 initialize the earlier LoadOnly
INIT LoadOnly
8 same Class=true
9 before active use
INIT ActiveTarget
PING ActiveTarget
10 finished
```

### Đọc kết quả từng đoạn

- Ở dòng **1–2**, `app.loadClass(...)` trả `Class<?>` của `LoadOnly` mà **không in `INIT LoadOnly`**. `getSimpleName()` chỉ lấy metadata tên, không yêu cầu static initialization của class đích.
- Dòng **3–4** cũng không in `INIT FalseTarget`: overload `Class.forName(name, false, app)` tìm/nạp class nhưng **không yêu cầu khởi tạo**.
- Dòng **5–6** có `INIT TrueTarget` **giữa hai markers**: overload `Class.forName(name, true, app)` yêu cầu initialization trước khi trả về thành công.
- Sau dòng **7**, `Class.forName(..., true, app)` nhận **chính runtime `LoadOnly` đã được `loadClass` trả trước đó**, nhưng lần này yêu cầu initialization. Vì thế xuất hiện `INIT LoadOnly`, rồi `loaded == later` bằng `true`.
- Ở dòng **9–10**, gọi `ActiveTarget.ping()` là **active use** của static method, buộc khởi tạo `ActiveTarget` trước khi in `PING`.
- `FalseTarget` **không hề in initializer** trong toàn bộ chương trình, vì không có hoạt động nào buộc nó initialize.

**Điểm đo thật sự:** thí nghiệm không chứng minh `loadClass` “không đọc bytecode”; nó chứng minh **không kích hoạt static initialization** trong cách gọi này.

## 5. `Class.forName(String)` khác thế nào với overload ba tham số?

Dạng rút gọn:

```java
Class<?> type = Class.forName("demo.Target");
```

Dựa trên Javadoc, nó dùng **defining loader của caller class** và **yêu cầu initialize**. Không có tham số `initialize=false` trong overload này.

Tương đương khái niệm khi đang ở code thuộc class `Caller`:

```java
Class<?> type = Class.forName(
        "demo.Target", true, Caller.class.getClassLoader());
```

Đây là **snippet minh họa** với `Caller` tồn tại và caller thực sự là `Caller`. Khi code nằm trong framework/library, **caller class loader** có thể khác plugin loader mà ứng dụng muốn dùng. Bởi vậy với plugin, thường nên truyền **loader tường minh** vào overload ba tham số.

**TCCL không tự được dùng bởi `Class.forName(String)`.** `Thread.currentThread().getContextClassLoader()` là cơ chế khác, thường được thư viện SPI như `ServiceLoader.load(service)` sử dụng. Thay TCCL không biến `Class.forName(name)` thành “tìm bằng TCCL”.

## 6. Thực hành B — thay TCCL không đổi loader của `forName(String)`

Bài này minh họa hai điểm độc lập: (1) class mà **child URLClassLoader** có thể nạp không nhất thiết có trên host classpath; (2) `Class.forName(name)` dùng loader của caller, **không tự đọc TCCL**.

Cây tệp:

```text
loader-choice-lab/
├── src/
│   ├── plugin/feature/PluginTarget.java
│   └── host/demo/LoaderChoiceDemo.java
├── plugin-out/
└── host-out/
```

**`src/plugin/feature/PluginTarget.java`:**

```java
package feature;

public final class PluginTarget {
    static {
        System.out.println("INIT PluginTarget");
    }

    public static String message() {
        return "plugin ready";
    }
}
```

**`src/host/demo/LoaderChoiceDemo.java`:**

```java
package demo;

import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;

public final class LoaderChoiceDemo {
    public static void main(String[] args) throws Exception {
        String name = "feature.PluginTarget";
        URL pluginRoot = Path.of("plugin-out")
                .toAbsolutePath().toUri().toURL();

        try (URLClassLoader pluginLoader = new URLClassLoader(
                    new URL[] {pluginRoot},
                    ClassLoader.getPlatformClassLoader())) {

            Class<?> loaded = pluginLoader.loadClass(name);
            System.out.println("loaded by plugin=" +
                    (loaded.getClassLoader() == pluginLoader));

            Thread thread = Thread.currentThread();
            ClassLoader oldContext = thread.getContextClassLoader();

            try {
                thread.setContextClassLoader(pluginLoader);

                try {
                    Class.forName(name);
                    System.out.println("unexpected one-arg success");
                } catch (ClassNotFoundException expected) {
                    System.out.println("one-arg not found=true");
                }

                Class<?> noInit =
                        Class.forName(name, false, pluginLoader);
                System.out.println("false same Class=" +
                        (loaded == noInit));

                System.out.println("before explicit true");
                Class<?> yesInit =
                        Class.forName(name, true, pluginLoader);
                System.out.println("true same Class=" +
                        (loaded == yesInit));
            } finally {
                thread.setContextClassLoader(oldContext);
            }
        }
    }
}
```

Biên dịch từ `loader-choice-lab`:

```sh
javac --release 17 -d plugin-out src/plugin/feature/PluginTarget.java
javac --release 17 -d host-out src/host/demo/LoaderChoiceDemo.java
```

Chạy (cố ý **chỉ** đưa `host-out` vào application classpath):

```sh
java -cp host-out demo.LoaderChoiceDemo
```

**Stdout dự kiến trong cấu hình trên:**

```text
loaded by plugin=true
one-arg not found=true
false same Class=true
before explicit true
INIT PluginTarget
true same Class=true
```

Giải thích:

1. Parent là platform loader, không biết `feature.PluginTarget` trong thư mục `plugin-out`. `URLClassLoader` tìm class từ URL riêng.
2. `pluginLoader.loadClass` trả runtime `Class<?>`, chưa in `INIT PluginTarget`.
3. Dù current thread TCCL đã đổi sang `pluginLoader`, `Class.forName(name)` trong `LoaderChoiceDemo` vẫn dùng **loader của caller host**; host không có plugin trên `-cp` nên `ClassNotFoundException`.
4. `Class.forName(name, false, pluginLoader)` nhận đúng class child vừa nạp và vẫn không initialize.
5. `Class.forName(name, true, pluginLoader)` kích hoạt `<clinit>`, in `INIT PluginTarget` trước khi trở về.
6. Ba class references `loaded`, `noInit`, `yesInit` đều là **cùng `Class<?>`** của plugin loader. Sự khác nhau là **initialization state**, không phải class identity.
7. `finally` khôi phục TCCL cũ; với pool threads, việc quên khôi phục có thể làm rò plugin loader hoặc ảnh hưởng SPI discovery sau đó.

**Không thêm `plugin-out` vào `-cp`** khi chạy ví dụ: như vậy `Class.forName(name)` của host có thể tìm class, mất giá trị so sánh.

## 7. Các thao tác làm thay đổi trạng thái của `Class`

`loadClass` và `Class.forName(name, false, loader)` **không tự yêu cầu initialization**. `new`, gọi static method, đọc nonconstant static field, gán static field hoặc `Class.forName(name, true, loader)` lại có thể là trigger. `T.class` và đọc compile-time constant không tự buộc `T` initialized. Đối với static field kế thừa, trigger nhắm tới **kiểu khai báo field**; việc initialize class còn kéo theo superclass và một số superinterface có default methods. Các bài về class initialization đã giải thích luật nền; bài này kiểm tra chính xác hiệu ứng các overload.

## 8. Thực hành C — constant, class literal và field runtime

Source file `src/demo/ConstantVsInitDemo.java`:

```java
package demo;

public final class ConstantVsInitDemo {
    static final class Values {
        static {
            System.out.println("INIT Values");
        }

        static final int COMPILE_TIME = 7;
        static final int RUNTIME = Integer.parseInt("8");
    }

    public static void main(String[] args) throws Exception {
        System.out.println("constant=" + Values.COMPILE_TIME);

        System.out.println("literal=" +
                Values.class.getSimpleName());

        ClassLoader app = ConstantVsInitDemo.class.getClassLoader();
        Class<?> c = Class.forName(
                ConstantVsInitDemo.class.getName() + "$Values",
                false, app);

        System.out.println("forName(false) returned=" +
                c.getSimpleName());

        System.out.println("before runtime field");
        System.out.println("runtime=" + Values.RUNTIME);
        System.out.println("runtime again=" + Values.RUNTIME);
    }
}
```

Biên dịch/chạy trong project chứa `src/demo/ConstantVsInitDemo.java`:

```sh
javac --release 17 -d out src/demo/ConstantVsInitDemo.java
java -cp out demo.ConstantVsInitDemo
```

**Stdout:**

```text
constant=7
literal=Values
forName(false) returned=Values
before runtime field
INIT Values
runtime=8
runtime again=8
```

**Tại sao có sự khác biệt?**

- `COMPILE_TIME` là **constant variable** vì `static final int` được gán bằng một constant expression `7`. Java compiler có thể nhúng giá trị vào code caller; việc dùng field này không kích hoạt initialization của `Values`.
- `Values.class` cung cấp `Class<?>` mà **không yêu cầu** chạy static initializer.
- `Class.forName(..., false, app)` lấy `Class<?>` nhưng vẫn để target chưa initialized.
- `RUNTIME` **không phải compile-time constant** dù là `static final`, vì `Integer.parseInt("8")` là lời gọi method. Lần đọc `Values.RUNTIME` đầu yêu cầu initialization: in marker rồi đặt `RUNTIME=8`.
- Dòng `runtime again=8` không in marker lần nữa vì `Values` **đã initialized thành công**.

**Cạm bẫy lớn:** `static final` **không đồng nghĩa** compile-time constant. Chỉ một subset các kiểu và biểu thức đạt định nghĩa *constant variable* của JLS. Ví dụ `static final String S = new String("x")` không là compile-time constant.

## 9. `Class.forName(..., true, ...)` không tạo object instance

Xét:

```java
Class<?> type = Class.forName(name, true, loader);
```

Lời gọi có thể khiến `static { ... }` của target chạy, nhưng nó **không phải `new`**. Constructor instance chưa chạy cho đến khi có thao tác tạo object.

Đối với reflection:

```java
Class<?> type = Class.forName(name, false, loader);
// Tại đây target chưa bắt buộc initialized.

Object object = type.getDeclaredConstructor().newInstance();
// Khi instance được tạo, JVM yêu cầu target initialized nếu cần.
```

Đây là **snippets** cần `name` và `loader` cùng xử lý exceptions. Nếu constructor không public, còn có thể vướng `IllegalAccessException` hoặc JPMS access rules; không tự gọi `setAccessible(true)` rồi cho rằng mọi module đều mở.

Phân biệt bytecode-level:

- `<clinit>`: class/interface initialization từ static initializers và static field assignments.
- `<init>`: instance initialization và constructor chain của từng object.

JVM thực thi `<clinit>` **tối đa một lần thành công cho mỗi runtime class**; rất nhiều object của class đó có thể được tạo sau, với `<init>` tương ứng mỗi lần.

## 10. `forName(true)` gọi lại có chạy initializer lần nữa không?

**Không**, nếu class đã initialized thành công. Một lần sau có thể trả cùng runtime `Class<?>` mà không lặp lại side effects của `<clinit>`.

Ví dụ:

```java
Class<?> first = Class.forName(name, true, loader);
Class<?> second = Class.forName(name, true, loader);
System.out.println(first == second);
```

Đây là **snippet** giả định `name` và `loader` giống nhau, target tồn tại và không có custom loading behavior phá contract. `true` cho so sánh cùng runtime definition; static initializer của target **không được chạy lại** vì lời gọi `forName` thứ hai.

### Một class có thể initialized nhiều lần trong JVM theo tên không?

Nếu **hai defining loaders khác nhau** tự định nghĩa **cùng binary name**, JVM coi đó là **hai runtime classes riêng**, nên mỗi class có initialization state riêng. Một ví dụ plugin reload:

```text
("plugin.Widget", loader-generation-1)
    → runtime Class A → initializer A

("plugin.Widget", loader-generation-2)
    → runtime Class B → initializer B

A.getName().equals(B.getName()) → true
A == B                           → false
```

Nhưng nếu `loader-generation-2` parent-first **nhận class A từ parent**, nó không tự tạo class B. Log defining loader bằng `Class.getClassLoader()` khi cần khẳng định isolation.

## 11. Thực hành D — lỗi initializer chỉ xuất hiện khi yêu cầu initialize

Chương trình này phân biệt **“load được bytes”** với **“class initialization thành công”**. Ta dùng một class có static initializer cố tình ném exception, và chủ động theo dõi hai lần active use.

Tệp `src/demo/InitFailureDemo.java`:

```java
package demo;

public final class InitFailureDemo {
    static final class Broken {
        static int value = compute();

        private static int compute() {
            System.out.println("INIT Broken");
            throw new IllegalStateException("invalid configuration");
        }
    }

    public static void main(String[] args) throws Exception {
        String name = InitFailureDemo.class.getName() + "$Broken";
        ClassLoader app = InitFailureDemo.class.getClassLoader();

        Class<?> loaded = app.loadClass(name);
        System.out.println("loaded without init=" +
                (loaded.getClassLoader() == app));

        try {
            Class.forName(name, true, app);
        } catch (ExceptionInInitializerError error) {
            System.out.println("first error=" +
                    error.getClass().getSimpleName());
            System.out.println("root cause=" +
                    error.getCause().getClass().getSimpleName());
        }

        try {
            Class.forName(name, true, app);
        } catch (NoClassDefFoundError error) {
            System.out.println("second error=" +
                    error.getClass().getSimpleName());
        }
    }
}
```

Biên dịch/chạy bằng JDK 17+ trong một JVM mới:

```sh
javac --release 17 -d out src/demo/InitFailureDemo.java
java -cp out demo.InitFailureDemo
```

**Stdout:**

```text
loaded without init=true
INIT Broken
first error=ExceptionInInitializerError
root cause=IllegalStateException
second error=NoClassDefFoundError
```

**Giải thích:**

1. `loadClass` trả runtime type của `Broken` thành công nhưng chưa buộc chạy `compute()`.
2. `Class.forName(name, true, app)` kích hoạt initialization; `compute()` in marker rồi ném `IllegalStateException`.
3. Vì exception ném từ initializer không phải một `Error`, JVM bọc thành `ExceptionInInitializerError`, đồng thời đánh dấu class ở trạng thái **erroneous**.
4. Gọi `Class.forName(..., true, ...)` lần nữa trên **cùng runtime class** không chạy initializer lại; JVM báo `NoClassDefFoundError` liên quan tới trạng thái erroneous.
5. `NoClassDefFoundError` không phải lúc nào cũng nghĩa file `.class` biến mất. Nó có thể là hậu quả **initialization thất bại trước đó**.

**Tại sao không đặt `throw new IllegalStateException(...)` trực tiếp trong static block vô điều kiện?** Với Java source, một static initializer không được “cannot complete normally” theo kiểm tra cú pháp/luồng điều khiển. Viết lời gọi `compute()` trong field initializer tạo một ví dụ compile được, có failure ở runtime.

**Vận hành:** đừng “sửa” bằng cách gọi `loadClass` lại. Trong cùng runtime class, initialization không reset. Cần xem **root cause đầu tiên** và xử lý vòng đời class loader nếu thật sự cần nạp generation mới.

## 12. `Class.forName(Module, String)` là overload khác hẳn

Java 9+ bổ sung:

```java
Class<?> found =
        Class.forName(SomeType.class.getModule(), "pkg.Target");
```

Đây là **snippet minh họa**; cần module/type tồn tại. Theo **Java 17 Javadoc**:

- Phương thức nhận **`Module` object**, không phải `ClassLoader`.
- Nó cố tìm/nạp class thuộc đúng module đã cho.
- Nó **không link** target class và **không chạy class initializer**.
- Nếu không có class theo binary name trong module ấy, kết quả là **`null`**, không giống `ClassNotFoundException` của overload ba tham số.
- Nó không tự bảo đảm class được access bởi caller; runtime module access checks vẫn phải được xét khi sử dụng members.
- Nếu loader của module định nghĩa những module khác, tên thuộc module khác có thể được nạp nhưng phương thức **trả null** vì không thuộc module được chỉ định.

**Đừng viết bài kiểm thử chỉ so string `Class.forName` mà bỏ chữ ký**. `Class.forName(String)` và `Class.forName(Module, String)` không có cùng initialization semantics.

## 13. Trường hợp đặc biệt: array class không initialize component type

Javadoc `Class.forName(name, boolean, loader)` có ngoại lệ: nếu `name` biểu thị **array class**, JVM nạp component type nhưng **không initialize component type chỉ vì array lookup**.

Ví dụ name của `demo.Item[]` ở dạng `Class.getName()`:

```text
[Ldemo.Item;
```

Cú pháp có dấu `[L` và dấu `;` là JVM binary descriptor-like name dành cho object arrays, khác tên source `demo.Item[]`.

### Thực hành E — array lookup và element initialization

**`src/demo/ArrayInitDemo.java`:**

```java
package demo;

public final class ArrayInitDemo {
    static final class Element {
        static {
            System.out.println("INIT Element");
        }

        Element() {
            System.out.println("CONSTRUCT Element");
        }
    }

    public static void main(String[] args) throws Exception {
        String elementName = ArrayInitDemo.class.getName() + "$Element";
        String arrayName = "[L" + elementName + ";";
        ClassLoader app = ArrayInitDemo.class.getClassLoader();

        System.out.println("before array forName(true)");
        Class<?> arrayClass = Class.forName(arrayName, true, app);
        System.out.println("array loaded=" + arrayClass.isArray());

        Element[] values = new Element[2];
        System.out.println("array length=" + values.length);

        System.out.println("before new element");
        values[0] = new Element();
        System.out.println("after new element");
    }
}
```

Biên dịch/chạy:

```sh
javac --release 17 -d out src/demo/ArrayInitDemo.java
java -cp out demo.ArrayInitDemo
```

**Stdout:**

```text
before array forName(true)
array loaded=true
array length=2
before new element
INIT Element
CONSTRUCT Element
after new element
```

**Vì sao?** `Class.forName(arrayName, true, app)` trả runtime **array class**, nhưng không buộc component `Element` initialized. `new Element[2]` tạo array với các phần tử ban đầu `null`, không tạo một `Element` object. Chỉ `new Element()` ở dòng sau yêu cầu initialize component class, rồi gọi constructor.

Đừng tổng quát một cách sai rằng `forName(..., true, ...)` luôn chạy initializer của **mọi type được nhắc đến trong name**. Phải xem class/interface/array case theo Javadoc.

## 14. Runtime class identity: cùng tên, cùng `Class<?>`, khác trạng thái

Trong thực hành A:

```text
app.loadClass("demo.LoadVsForNameDemo$LoadOnly")
    └── trả Class<?> C, chưa yêu cầu init

Class.forName("demo.LoadVsForNameDemo$LoadOnly", true, app)
    └── trả cũng Class<?> C, nhưng yêu cầu init trước khi trả
```

Sự khác nhau **không phải bytecode khác hay loader khác**. `Class<?>` object là cùng identity trong hai lần tra cứu. Chỉ **initialization side effect** khác.

Hãy kiểm tra:

```java
System.out.println(loaded == later);
System.out.println(loaded.getClassLoader() == app);
```

Hai snippets giả định tên biến từ thực hành A. Để hiểu tại sao static field có giá trị mặc định hay hoàn chỉnh, cần phân biệt state **prepared but not initialized** và **initialized** — `ClassLoader` API không cung cấp một public method `isInitialized(Class<?>)` tổng quát để kiểm tra trạng thái mà không làm gì thêm.

**Không cố suy trạng thái initialized chỉ từ việc có `Class<?>` hoặc `classLoader.findLoadedClass`.** `findLoadedClass` trả thông tin liên quan tới class đã được loader khởi xướng nạp, không phải một status API cho `<clinit>`.

## 15. Khởi tạo kiểu cha khi thử `forName(true)`

Yêu cầu initialize một class có thể chạy static initializer của superclass chưa initialized và các superinterface khai báo default methods trước phần mã static của class đó. Nhưng yêu cầu initialize một interface không mặc nhiên initialized mọi superinterface. Khi test `forName(true)`, đặt marker tại đúng kiểu dự kiến và ghi nhận **thứ tự** nếu có kế thừa. Quy tắc này khác riêng biệt với loader nào tìm/định nghĩa type.

## 16. Vì sao cần một fresh runtime class cho mỗi thử nghiệm

JVM đồng bộ hóa initialization để chỉ một thread thực hiện initializer của **cùng runtime class**, các thread khác chờ kết quả. Khi thành công, lặp `Class.forName(name, true, loader)` không chạy lại marker. Khi lỗi, cùng định nghĩa class trở thành erroneous; xem thí nghiệm lỗi mục 11. Muốn đo trigger đầu tiên độc lập, dùng defining loader mới thực sự tạo class mới hoặc khởi chạy JVM mới, như bài cuối chương hướng dẫn.

## 17. Không nhầm lỗi khởi tạo với lỗi nạp và reflection

- `ClassNotFoundException` khi tìm tên không chứng minh initializer đã chạy.
- `ExceptionInInitializerError` thường bọc unchecked exception từ initializer đầu tiên; sau đó cùng runtime class có thể báo `NoClassDefFoundError` vì erroneous.
- Reflection/constructor còn có `InvocationTargetException`, `IllegalAccessException` và các failure khác. Xem cause và vị trí bước thử nghiệm; không quy mọi lỗi do gọi `forName` cho **class loading**.

## 18. Kiểm chứng khi dùng plugin hoặc `URLClassLoader`

Một plugin framework thường thực hiện:

```java
Class<?> impl = pluginLoader.loadClass("plugin.ServiceImpl");
Object service = impl.getDeclaredConstructor().newInstance();
```

Đây là **snippet**, cần plugin loader và xử lý exceptions. Nếu implementation có static initializer:

- `loadClass` theo cách chuẩn **chưa yêu cầu** chạy initializer.
- `getDeclaredConstructor()` chỉ lấy constructor metadata, không tự gọi body constructor.
- `Constructor.newInstance()` là reflective instance creation và có thể **yêu cầu class initialization**.
- Lỗi `ExceptionInInitializerError` có thể xuất hiện khi tạo instance, dù `loadClass` đã hoàn tất thành công.

Nếu framework thay `loadClass` bằng `Class.forName(name, true, pluginLoader)` trong giai đoạn **discovery**, nó có thể chạy static code của plugin sớm hơn dự kiến. Điều này có thể gây I/O, kết nối mạng, khởi tạo thread hoặc throw lỗi trước giai đoạn lifecycle do host quản lý.

**Khuyến nghị thiết kế:** trong discovery, phân biệt rõ “biết type nào có thể dùng” và “cho phép code initializer chạy lúc nào”. Dùng loader và API phù hợp, sau đó kích hoạt service trong startup phase có logging, timeout và quyền hạn theo kiến trúc.

## 19. `ServiceLoader` và TCCL là thí nghiệm khác

`ServiceLoader.load(SPI)` thường sử dụng TCCL để tìm descriptors và providers; còn `Class.forName(String)` có lựa chọn loader gắn với caller. Trong plugin, đừng dựa vào thay TCCL để kết luận `forName(String)` sẽ thấy mọi class của plugin. Bài **Kiểm chứng tìm tài nguyên và provider dịch vụ** tách kiểm tra SPI identity, resource descriptor và provider instantiation.

## 20. Reflection: chỉ tra metadata hay thật sự sử dụng kiểu?

`type.getDeclaredConstructors()` và `type.getDeclaredMethods()` thường chỉ đọc metadata, còn `constructor.newInstance()`, `Field.get(null)` trên static field hoặc `Method.invoke(null, ...)` cho static method có thể kích hoạt initialization. Vì vậy kết quả “`loadClass` không in marker” chỉ có giá trị nếu **chưa có thao tác tiếp theo** tạo instance hoặc gọi static member. Tách từng hành động bằng marker riêng như mục 4.

## 21. Trường hợp đã được initialize từ trước: vì sao “không thấy marker” chưa đủ?

Nếu class `Target` đã được sử dụng trước phần đo:

```java
Target.ping();             // lần này có thể đã initialize
loader.loadClass("Target");
Class.forName("Target");
```

Đây là **pseudocode** với binary name cần chỉnh đúng. Khi gọi hai API sau, không in static initializer nữa dù `Class.forName` vẫn yêu cầu initialization theo contract, bởi JVM nhận thấy class **đã initialized**.

Do đó không thể chạy một chương trình rồi kết luận:

> “`Class.forName` không initialize vì tôi chẳng thấy `static { }` in gì.”

Kết luận đúng phải xét **trạng thái trước lời gọi**. Các bài thực hành trong README cố tình dùng các classes riêng hoặc tiến trình mới.

### Cách cải thiện test

- Tạo một target class **mới chưa active-use** cho mỗi phép thử.
- Đặt markers cạnh statements của API.
- Không dùng static non-constant field target để tạo tên class.
- Nếu cần test nhiều lần, chạy `java` process mới cho mỗi lượt thay vì trông chờ class initializer được reset.
- Nếu test reload qua loader mới, kiểm tra `type.getClassLoader()` để đảm bảo parent không âm thầm cung cấp cùng type cũ.

## 22. Thực hành F — `Class.forName(String)` có cùng kết quả init với true khi caller nhìn thấy class

Để xác nhận overload **một tham số**, dùng class đích mới trong project trên application classpath.

Tệp **`src/demo/OneArgumentForNameDemo.java`**:

```java
package demo;

public final class OneArgumentForNameDemo {
    static final class Target {
        static {
            System.out.println("INIT Target");
        }
    }

    public static void main(String[] args) throws Exception {
        String name = OneArgumentForNameDemo.class.getName()
                + "$Target";

        System.out.println("before one-arg");
        Class<?> type = Class.forName(name);
        System.out.println("after one-arg");
        System.out.println("same defining loader=" +
                (type.getClassLoader()
                        == OneArgumentForNameDemo.class.getClassLoader()));
    }
}
```

Biên dịch/chạy:

```sh
javac --release 17 -d out src/demo/OneArgumentForNameDemo.java
java -cp out demo.OneArgumentForNameDemo
```

**Stdout:**

```text
before one-arg
INIT Target
after one-arg
same defining loader=true
```

Lệnh `Class.forName(name)` yêu cầu initialization trước khi trả về, vì thế `INIT Target` xuất hiện giữa hai markers. `type.getClassLoader()` trùng loader của caller `OneArgumentForNameDemo` vì toàn bộ chương trình nằm trong application classpath theo lệnh chạy này.

**So với thực hành B:** overload một tham số ở đây thành công vì target nằm trên **classpath của caller**; ở thực hành B target chỉ nằm trong URL riêng của plugin loader, nên overload ấy thất bại dù TCCL đã được chuyển.

## 23. Cách kiểm tra bytecode để tránh “do optimizer làm mất initializer”

Khi dùng compile-time constants, compiler có thể sinh `ldc`/`bipush`/`sipush` thay vì `getstatic`. Xem bytecode giúp giải thích vì sao dùng constant không initialize declaring class.

Ví dụ từ thực hành C:

```sh
javap -classpath out -c -p demo.ConstantVsInitDemo
javap -classpath out -c -p 'demo.ConstantVsInitDemo$Values'
```

Trong shell POSIX/PowerShell, single quotes quanh nested binary name giúp bảo toàn ký tự `$`. `javap` có thể cho thấy `<clinit>` của `Values` chứa phần in marker và `Integer.parseInt("8")`; method `main` có thể sử dụng giá trị constant đã nhúng.

**Cẩn thận:** `javap` chỉ đọc class files trên đĩa, **không tự chứng minh** JVM đã chọn class file ấy qua runtime loader graph. Nếu classpath có nhiều versions của cùng binary name, phải kết hợp `Class.getClassLoader()`, `ProtectionDomain.getCodeSource()` và `-Xlog:class+load`.

## 24. Diagnostic logging có ích cho sự khác biệt loading/initialization

Một helper đơn giản khi đã có `Class<?>`:

```java
static void describe(Class<?> type) {
    ClassLoader definingLoader = type.getClassLoader();
    Module module = type.getModule();

    System.out.println("class=" + type.getName());
    System.out.println("loader=" +
            (definingLoader == null
                    ? "<bootstrap>" : definingLoader.getClass().getName()));
    System.out.println("module=" +
            (module.isNamed() ? module.getName() : "<unnamed>"));
}
```

Đây là **method minh họa**; các dòng metadata **không buộc chạy `<clinit>` của target**. Không dùng `Class.forName(name)` chỉ để log metadata của class chưa được tìm vì overload ấy có thể initialize target. Khi chỉ muốn biết class nào được load qua một loader, ưu tiên `Class.forName(name, false, loader)` nếu có lý do thực sự cần lookup.

Nếu phải ghi **CodeSource** của class, dùng đường null-safe:

```java
var domain = type.getProtectionDomain();
var source = domain == null ? null : domain.getCodeSource();
var url = source == null ? null : source.getLocation();
System.out.println(url == null ? "<unknown>" : url.toExternalForm());
```

Snippet cần `type` đã có; URL có thể chứa filesystem path hoặc thông tin nội bộ, nên tránh lộ ra client logs. CodeSource không tự chứng minh bytecode integrity hoặc khẳng định target đã initialized.

### JDK Unified Logging

Trên HotSpot hỗ trợ Unified Logging:

```sh
java -Xlog:class+load=info -cp out demo.LoadVsForNameDemo
java -Xlog:help
```

Log loading có thể hiển thị lúc class được tìm/nạp, nhưng **không phải log xác nhận static block đã chạy**. Một số HotSpot versions cũng cung cấp tag `class+init`; kiểm tra `-Xlog:help` trước. Không cố định stdout của những lệnh logging này, vì metadata/timestamps/VM versions khác nhau.

## 25. Debugging: nếu kết quả khác stdout dự kiến thì kiểm tra gì?

| Triệu chứng | Giả thuyết phổ biến | Cách kiểm tra |
| --- | --- | --- |
| `INIT` xuất hiện trước `loadClass` | Target đã active-use trước lúc đo | Tách target class; chạy JVM mới |
| `INIT` không xuất hiện ở `forName(true)` | Class đã initialized trước đó; hoặc target không có initializer in | Kiểm tra toàn bộ code path và loader identity |
| `Class.forName(name)` thất bại nhưng `child.loadClass(name)` thành công | Caller loader không thấy URL riêng của child | Truyền `child` vào overload ba tham số |
| Đổi TCCL mà `forName(String)` vẫn fail | Một tham số không tự dùng TCCL | In caller loader và TCCL; dùng explicit loader |
| `Class.forName(name,false,loader)` gặp `LinkageError` | Việc không initialize **không** loại trừ lỗi loading/linking | Đọc stacktrace, verify dependencies, bytecode |
| `Class.forName(name,true,loader)` ném `ExceptionInInitializerError` | Static initializer ném exception hoặc phụ thuộc init thất bại | Xem root cause/initializer code |
| Lần `forName(true)` tiếp ném `NoClassDefFoundError` | Class đã erroneous do init lần trước | Sửa lỗi gốc, reset bằng lifecycle phù hợp |
| Array `forName(true)` không in component marker | Array lookup không initialize element type | Active-use element class riêng |
| `static final` không tạo `INIT` | Field là compile-time constant | So `javap`, dùng non-constant static field để test |
| Plugin class lại do host loader định nghĩa | Parent-first hoặc plugin directory ở host classpath | In `type.getClassLoader()`, kiểm tra `-cp` và URLs |
| Thấy constructor message sau `forName(true)` | Code trong `<clinit>` có thể tự tạo object; không phải forName tự tạo instance | Xem static initializer và stacktrace |
| Test chạy khác trên IDE | IDE đưa plugin output vào host classpath hoặc chạy reused JVM/test order | Chạy lệnh `javac/java` riêng và xác định classpath |

Một kết quả “khác kỳ vọng” thường do **môi trường và thứ tự active use** hơn là do JVM ngẫu nhiên thay đổi hợp đồng API.

## 26. Những ngộ nhận cần tránh

- **“`loadClass` và `Class.forName` chỉ khác cách viết.”** Sai: initialization semantics và loader selection có thể khác.
- **“Có `Class<?>` tức là static block đã chạy.”** Sai; class có thể chỉ loaded/linked.
- **“`loadClass` chắc chắn không thể gây lỗi linking.”** Sai; không yêu cầu init khác với không thực hiện linking.
- **“`Class.forName(name, false, loader)` bảo đảm không tải bytecode.”** Sai; nó vẫn có thể tải class, chỉ không yêu cầu initializer.
- **“`Class.forName(name)` luôn dùng TCCL.”** Sai; dùng loader của caller class.
- **“`Class.forName(name, true, loader)` luôn tạo một object.”** Sai; trả `Class<?>`, không chạy constructor instance.
- **“`static final` luôn khiến class không initialize khi đọc.”** Sai; chỉ compile-time constant variables có ngoại lệ.
- **“`Target.class` sẽ chạy static initializer.”** Không theo hoạt động class literal thông thường.
- **“Gọi `forName(true)` hai lần sẽ chạy static block hai lần.”** Sai với cùng runtime class đã initialized thành công.
- **“Một binary name chỉ initialize một lần trong toàn JVM.”** Sai nếu các defining loaders khác nhau tạo runtime class identities khác nhau.
- **“`Class.forName(module,name)` giống `Class.forName(name)`.”** Sai: module overload không link/init và trả `null` nếu không tìm được.
- **“Array `forName(true)` luôn initialize component class.”** Sai theo Javadoc.
- **“`NoClassDefFoundError` luôn có nghĩa thiếu file `.class`.”** Sai nếu class initialization trước đó lỗi.
- **“Dùng `loadClass` là đủ bảo đảm plugin không chạy code trước startup.”** Không tuyệt đối: loader custom, linking/dependencies và application code có thể tạo side effects; phân tích đầy đủ execution path.
- **“Một JVM test rerun sẽ reset static initializer giữa test methods.”** Không nếu vẫn dùng cùng runtime class trong cùng process/loader.
- **“In log class name chứng minh parent hay child đã define.”** Không; cần `Class.getClassLoader()`.

## 27. Checklist kiểm chứng nhanh

1. Chọn target class **chưa active-use**; static initializer in một marker duy nhất.
2. In markers trước/sau từng API.
3. Dùng đúng binary name (`Outer$Inner` cho nested class).
4. Ghi rõ caller loader, explicit loader, parent và TCCL nếu có.
5. Thử `loadClass` → kiểm tra không có `INIT` trước active use.
6. Thử `Class.forName(name, false, loader)` trên target riêng → kiểm tra không có `INIT`.
7. Thử `Class.forName(name, true, loader)` → marker `INIT` trước khi method trả thành công.
8. Thử `Class.forName(name)` với class thuộc caller loader → xác nhận initializer và caller loader.
9. Thử `static final` compile-time constant so với runtime-initialized static field.
10. Thử array class lookup và tạo array, rồi tạo element instance.
11. Thử initializer ném lỗi → `ExceptionInInitializerError` trước và `NoClassDefFoundError` sau, giữ root cause.
12. Chạy mỗi thí nghiệm trong JVM mới khi cần reset.
13. Không vô tình thêm plugin output vào application classpath.
14. Kiểm tra `Class<?>` identity và defining loader nếu phải so sánh hai loader instances.
15. Với production, không dùng `Class.forName(..., true, ...)` chỉ để discovery khi static initialization chưa được cho phép.

## 28. Câu hỏi tự kiểm tra có đáp án

**1. `loader.loadClass("p.T")` theo mặc định có yêu cầu chạy `<clinit>` không?** Không.

**2. `Class.forName("p.T")` khác `loadClass` ở đâu về initialization?** Nó yêu cầu initialize target nếu chưa initialized.

**3. Làm sao nạp class qua loader chỉ định mà không yêu cầu initialization?** `Class.forName("p.T", false, loader)` hoặc `loader.loadClass("p.T")` theo hành vi chuẩn.

**4. `Class.forName("p.T", true, loader)` trả object instance hay `Class<?>`?** `Class<?>`; không tự chạy instance constructor.

**5. Đổi TCCL có đổi loader dùng bởi `Class.forName(String)` không?** Không. Overload đó dùng caller class loader.

**6. `Class.forName(Module,String)` khác gì?** Không link/init theo Javadoc và trả `null` nếu class không thuộc module được yêu cầu.

**7. Vì sao `static final int N=7` không in initializer khi đọc?** Nó là constant variable, có thể được compiler inline.

**8. Vì sao `static final int N=Integer.parseInt("7")` có thể in initializer?** Nó không phải constant expression, nên đọc field kích hoạt initialization.

**9. Hai calls `Class.forName(name,true,loader)` có chạy initializer hai lần không?** Không nếu cùng runtime class đã initialized thành công.

**10. `getDeclaredConstructor().newInstance()` có thể initialize class không?** Có, vì tạo instance là active use.

**11. Array `Class.forName("[Lp.T;", true, loader)` có buộc initialize `p.T` không?** Không theo Javadoc cho array class.

**12. Vì sao lần active use sau class initialization lỗi có thể ném `NoClassDefFoundError`?** Runtime class ở trạng thái erroneous, initializer không được thử lại.

**13. Hai class loaders định nghĩa cùng binary name có chung initialization state không?** Không; chúng là hai runtime types khác nhau.

**14. `resolveClass` có tương đương `Class.forName(..., true, ...)` không?** Không. `resolveClass` liên quan tới linking, không yêu cầu class initialization.

**15. Nếu chương trình không in `INIT` ở `Class.forName(name)`, kiểm tra gì trước?** Target đã initialized trước đó chưa, binary name/loader identity và thí nghiệm có dùng lớp mới/JVM mới không.

**16. Vì sao test class initialization bằng một static constant có thể gây hiểu lầm?** Vì compiler có thể inline giá trị và không phát sinh active use `getstatic` của declaring class.

## 29. Tài liệu chuẩn

- [Java SE 17 — ClassLoader Javadoc](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html): `loadClass(String)` và `loadClass(String, boolean)`, parent delegation, `resolveClass`.
- [Java SE 17 — Class Javadoc](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html): `forName(String)`, `forName(String, boolean, ClassLoader)`, `forName(Module, String)` và initialization semantics.
- [JLS Java SE 17 — 12.4.1 When Initialization Occurs](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.4.1): active use, static field, static method, superclass/interface initialization.
- [JLS Java SE 17 — 12.4.2 Detailed Initialization Procedure](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.4.2): trạng thái initialization, coordination và class erroneous.
- [JVMS Java SE 17 — Chapter 5](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html): loading/linking/initialization và runtime class identity.
- [Java SE 17 — Constructor Javadoc](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Constructor.html): reflective instance creation và liên quan initialization.
- [Java SE 17 — URLClassLoader Javadoc](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html): classpath-style plugin loader và parent delegation.
- [JDK 17 — javap](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javap.html): xem bytecode `<clinit>` và constant folding.

**Kết luận:** `loadClass` chuẩn và `Class.forName(name, false, loader)` giúp tìm/nạp class **mà không yêu cầu khởi tạo**; `Class.forName(name)` và `Class.forName(name, true, loader)` **yêu cầu khởi tạo**, nhưng chỉ khi runtime class chưa initialized. Phân biệt **loader được chọn, trạng thái initialization, active use và class identity**, rồi kiểm chứng bằng những static initializer markers trong **một JVM mới** để tránh kết luận sai từ việc class đã initialized trước đó.
