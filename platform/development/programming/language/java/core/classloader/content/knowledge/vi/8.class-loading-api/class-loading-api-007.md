# Class.forName(name, initialize, loader) — nạp lớp, khởi tạo và chọn ClassLoader

## 1. Vì sao cần overload ba tham số?

Java cho phép tìm một lớp theo **tên dạng chuỗi** vào lúc chạy. Phương thức:

```java
public static Class<?> forName(
        String name,
        boolean initialize,
        ClassLoader loader
) throws ClassNotFoundException
```

nằm trong `java.lang.Class`. Nó giải quyết ba quyết định tách biệt:

1. **`name`:** tên binary của class/interface hoặc chuỗi mô tả một kiểu mảng cần tìm.
2. **`initialize`:** có yêu cầu JVM thực hiện **khởi tạo lớp/interface** sau khi tìm và nạp thành công hay không.
3. **`loader`:** ClassLoader nào được dùng để tìm lớp; nếu truyền `null`, yêu cầu dùng bootstrap class loader.

Kết quả là một `Class<?>` — **đối tượng mô tả runtime type**. `Class.forName` không tạo instance của lớp đích, không gọi constructor instance của nó và cũng không bảo đảm ta có quyền gọi mọi thành viên của lớp qua reflection.

Ví dụ sử dụng trong ứng dụng plugin:

```java
// Trích đoạn: pluginLoader được tạo và cấu hình ở nơi khác.
Class<?> pluginType =
        Class.forName("com.example.plugin.Handler", false, pluginLoader);

// Đã có Class<?> của kiểu, nhưng yêu cầu này chưa khởi tạo Handler.
```

Nếu đổi `false` thành `true`, phương thức sẽ **yêu cầu khởi tạo Handler nếu Handler chưa khởi tạo**. Điều này có thể chạy các phép gán field `static` và khối `static`, kéo theo code ứng dụng, I/O hoặc exception. Khác biệt này đặc biệt quan trọng với ứng dụng có plugin, service registry và các thư viện dùng reflection.

## 2. Luồng xử lý khái niệm

Với `Class.forName(name, initialize, loader)`, JVM phải tìm runtime type tương ứng và tuân theo các quy tắc loading/linking/initialization:

```text
Class.forName(name, initialize, loader)
       │
       ├─ Xác định dạng tên:
       │      ├─ Binary name của class/interface
       │      └─ Descriptor của array type
       │
       ├─ Sử dụng loader được chỉ định để tìm/nạp type
       │      └─ Chính sách ủy quyền tùy ClassLoader cụ thể
       │
       ├─ Liên kết/kiểm tra theo yêu cầu JVM
       │      └─ lỗi loading/linking vẫn có thể xảy ra
       │
       └─ Nếu là class/interface thông thường:
              ├─ initialize=false → không yêu cầu khởi tạo
              └─ initialize=true  → khởi tạo nếu chưa hoàn tất
                                      └─ static field initializers / blocks
          Nếu name là array descriptor:
              → JVM tạo/nhận array class;
                element class được nạp nhưng không
                bị khởi tạo chỉ vì lời gọi forName này
       │
       ▼
Trả Class<?> hoặc ném exception/error
```

Đây là **sơ đồ ngữ nghĩa**, không phải mô tả máy móc thứ tự mọi bước verification/resolution. JVM có thể trì hoãn việc phân giải một số symbolic references cho đến khi cần. Bảo đảm quan trọng là khi cần khởi tạo một class, nó phải được verification và preparation theo quy định trước.

`Class.forName` **không tự chọn ngẫu nhiên loader phù hợp**. Người gọi quyết định tham số `loader`; chính loader đó và chuỗi ủy quyền của nó quyết định có tìm được class nào.

## 3. Tham số name: binary name và descriptor của mảng

### 3.1. Binary name của lớp thông thường

Với class top-level:

```java
Class<?> c = Class.forName(
        "java.util.ArrayList",
        false,
        ClassLoader.getSystemClassLoader()
);
```

`name` là `"java.util.ArrayList"`, **không phải** đường dẫn `"java/util/ArrayList.class"`, chuỗi `"ArrayList.class"` hay source declaration.

Với nested/member class, binary name thường dùng ký tự `$`. Ví dụ trong file `Outer.java`:

```java
public class Outer {
    static class Inner {
    }
}
```

Binary name của class thành viên `Inner` là `Outer$Inner` (với package nếu có). Khi gọi:

```java
// Trích đoạn, giả sử class Outer đã nằm trong classpath.
Class<?> inner = Class.forName(
        "Outer$Inner",
        false,
        Outer.class.getClassLoader()
);
```

`"Outer.Inner"` là cách viết theo tên chuẩn nguồn, **không phải binary name** hợp lệ của member class trong tình huống này. Tên của anonymous/local class còn có đặc điểm do compiler sinh; nên lấy `SomeClass.class.getName()` khi đã có `Class<?>` thay vì đoán tên.

Đối với generic types, tên `"java.util.List<java.lang.String>"` cũng không hợp lệ cho `forName`; generic arguments không tạo runtime class riêng, do type erasure. Dùng `"java.util.List"`.

### 3.2. Tên kiểu mảng là descriptor

Đối với array class, `name` không viết bằng `"java.lang.String[]"`. Nó dùng cú pháp JVM descriptor:

| Kiểu Java | Chuỗi truyền `forName` |
|---|---|
| `int[]` | `"[I"` |
| `boolean[]` | `"[Z"` |
| `long[][]` | `"[[J"` |
| `String[]` | `"[Ljava.lang.String;"` |
| `String[][]` | `"[[Ljava.lang.String;"` |
| `mypackage.Widget[]` | `"[Lmypackage.Widget;"` |

Một dấu `[` biểu thị một chiều. `L...;` bao tên binary của reference component. Mã primitive thông dụng gồm `Z`, `B`, `C`, `D`, `F`, `I`, `J`, `S` cho boolean, byte, char, double, float, int, long, short.

**Quy tắc đặc biệt:** nếu `name` biểu diễn **array class**, class phần tử có thể được nạp nhưng **không khởi tạo**, **bất kể `initialize=true` hay `false`**. Lời gọi `Class.forName("[Lmypackage.Widget;", true, loader)` không phải một lối tắt để chạy `Widget.<clinit>`.

### 3.3. Primitive và void không được tìm bằng overload này

Các tên như `"int"`, `"boolean"`, `"void"` và descriptor chữ `"I"` khi dùng làm `name` đơn lẻ **không** trả `int.class` hoặc `void.class`. API sẽ cố tìm class theo tên đó; thông thường sẽ nhận `ClassNotFoundException`.

Muốn lấy đối tượng `Class` của primitive hoặc void, dùng:

```java
Class<?> integerType = int.class;
Class<?> voidType = void.class;
```

Nếu cần primitive array, dùng `Class.forName("[I", false, loader)` hoặc `int[].class`.

## 4. Tham số initialize: false và true khác nhau thế nào?

| `initialize` | Với class/interface thông thường | Với array descriptor |
|---|---|---|
| `false` | Yêu cầu tìm/nạp class, **không** yêu cầu chạy initializer | Tạo/nhận array class; không khởi tạo class phần tử |
| `true` | Sau khi tìm/nạp, yêu cầu initialization nếu chưa hoàn tất | Class phần tử vẫn **không** bị khởi tạo bởi lời gọi này |

### 4.1. Khi initialize=false

`Class.forName(name, false, loader)` có thể trả `Class<?>` để ta đọc metadata như `getName()`, `getDeclaredMethods()` hoặc kiểm tra type identity mà không chủ động khởi tạo lớp đích. Tuy nhiên:

- Lớp có thể **đã được khởi tạo trước đó** bởi lời gọi khác; `false` không “hoàn tác” trạng thái.
- JVM có thể vẫn phải **nạp/liên kết** lớp và các kiểu liên quan; `false` không phải cam kết “không có hoạt động nào khác” hoặc “không thể phát sinh lỗi”.
- Hoạt động reflection sau đó như gọi static method, đọc static field hoặc tạo instance có thể yêu cầu initialization.
- Custom loader có thể có **side effect riêng khi load**; `false` chỉ điều khiển yêu cầu khởi tạo của lớp đích theo ngữ nghĩa API, không vô hiệu hóa mọi code do loader tự viết.

### 4.2. Khi initialize=true

`Class.forName(name, true, loader)` yêu cầu JVM khởi tạo lớp/interface đích **nếu nó chưa được khởi tạo**. Với class, khởi tạo bao gồm các biểu thức khởi tạo static fields và `static { ... }` theo thứ tự nguồn; các superclass thích hợp được khởi tạo trước theo quy tắc JVM/JLS.

Không diễn giải `true` là "chạy lại static block mỗi lần gọi": initialization thành công được ghi nhận **một lần cho mỗi runtime class/interface**. Với cùng `Class<?>`, gọi lại `forName(..., true, ...)` không chạy lại `<clinit>`.

Nếu initializer có lỗi, `Class.forName` có thể ném `ExceptionInInitializerError` khi lần đầu khởi tạo (hoặc truyền lỗi thuộc họ `Error` theo quy tắc JLS). Runtime class thất bại trở thành erroneous; lần yêu cầu khởi tạo tiếp theo có thể gặp `NoClassDefFoundError` thay vì retry.

## 5. Ví dụ chạy được: quan sát rõ false → true → true

Tạo file `ForNameDemo.java`:

```java
public class ForNameDemo {
    static class Target {
        static int counter = initializeCounter();

        private static int initializeCounter() {
            System.out.println("Target initialized");
            return 7;
        }
    }

    public static void main(String[] args) throws Exception {
        ClassLoader loader = ForNameDemo.class.getClassLoader();

        System.out.println("start");
        Class<?> type = Class.forName(
                "ForNameDemo$Target", false, loader
        );
        System.out.println("loaded: " + type.getSimpleName());

        System.out.println("before init");
        Class<?> again = Class.forName(
                "ForNameDemo$Target", true, loader
        );
        System.out.println("same Class: " + (type == again));

        Class.forName("ForNameDemo$Target", true, loader);
        System.out.println("counter=" + Target.counter);
    }
}
```

Dùng JDK 17+:

```bash
javac ForNameDemo.java
java ForNameDemo
```

Stdout:

```text
start
loaded: Target
before init
Target initialized
same Class: true
counter=7
```

**Diễn giải:**

1. Lời gọi đầu có `false`: JVM trả `Class<?>` của `Target`, nhưng không yêu cầu chạy `initializeCounter()`.
2. `type.getSimpleName()` đọc metadata của `Class<?>`, không chạy static initializer của Target.
3. Lời gọi thứ hai có `true`: yêu cầu khởi tạo Target, nên in `Target initialized` đúng một lần và gán `Target.counter=7`.
4. `type == again` là `true` vì cả hai biểu diễn cùng một runtime class.
5. Lời gọi `true` thứ ba không chạy lại initializer; đọc `Target.counter` in giá trị 7.

**Không phải** `initialize=false` nghĩa là "chỉ trả tên", hay `initialize=true` nghĩa là "tạo instance". Cả hai trả đối tượng `Class<?>`; khác nhau ở yêu cầu initialization.

## 6. Tham số loader: chọn không gian tên runtime

### 6.1. Tại sao phải truyền loader tường minh?

Một class được JVM nhận diện về cơ bản bởi **binary name cùng defining ClassLoader**. Hai loader độc lập có thể định nghĩa hai lớp cùng tên nhưng không phải cùng runtime class; ép kiểu hoặc liên kết sai giữa chúng có thể thất bại dù chuỗi tên giống nhau.

Trong `Class.forName(name, initialize, loader)`, tham số `loader` quyết định loader **bắt đầu quá trình tìm lớp**. Loader đó có thể áp dụng parent-first delegation và trả một lớp **do parent định nghĩa**. Vì vậy:

```java
Class<?> type = Class.forName(name, false, pluginLoader);
ClassLoader definingLoader = type.getClassLoader();
```

Đây là trích đoạn, cần có `name` và `pluginLoader` ở nơi gọi. `definingLoader` **không bắt buộc bằng** `pluginLoader`: có thể lớp được parent/bootstrap định nghĩa. Hãy kiểm tra `type.getClassLoader()` khi tìm nguyên nhân dùng nhầm thư viện.

Nếu truyền **`loader=null`**, API dùng **bootstrap class loader**. Đây không phải lựa chọn "mặc định linh hoạt" hay "dùng system loader". Chẳng hạn:

```java
Class<?> stringType =
        Class.forName("java.lang.String", false, null);
System.out.println(stringType == String.class);
```

Trong method Java có `throws ClassNotFoundException` hoặc bắt exception tương ứng, stdout là `true`. Nhưng một class plugin chỉ nằm trong directory của custom loader thông thường sẽ không được bootstrap tìm thấy.

### 6.2. So với overload một tham số

`Class.forName("mypackage.Handler")` về mặt ngữ nghĩa tương đương `Class.forName("mypackage.Handler", true, currentLoader)`, với `currentLoader` là **defining loader của lớp chứa lời gọi** theo định nghĩa của API. Nó không tự lấy `Thread.currentThread().getContextClassLoader()`.

So sánh:

```java
// Trích đoạn: class và loader phải tồn tại ở context phù hợp.

Class<?> a = Class.forName("mypackage.Handler");
// Yêu cầu initialize=true và dùng loader của lớp gọi.

Class<?> b = Class.forName(
        "mypackage.Handler", false, explicitlyChosenLoader
);
// Không yêu cầu initialize; dùng loader được truyền tường minh.
```

Một thread context class loader (TCCL) có thể được framework thiết lập để hỗ trợ SPI/plugin. Nếu muốn dùng nó, phải **chủ động truyền**:

```java
ClassLoader context =
        Thread.currentThread().getContextClassLoader();

Class<?> type = Class.forName(
        "mypackage.Handler", false, context
);
```

Đây là **trích đoạn**, không phải chương trình độc lập. Chú ý `context` có thể `null`; truyền `null` vào overload ba tham số có nghĩa là dùng bootstrap loader, nên ứng dụng plugin cần chọn/kiểm tra fallback rõ ràng trước khi gọi.

### 6.3. Không nhất thiết được truy cập class vừa tìm

`Class.forName` **không kiểm tra trước liệu caller có quyền truy cập class đích**. Việc có `Class<?>` không cấp quyền gọi constructor hoặc member `private`/package-private. Quyền truy cập Java, quy tắc module và ràng buộc reflection vẫn áp dụng về sau. Dùng `setAccessible(true)` không mặc nhiên vượt qua module encapsulation của JDK hiện đại.

## 7. Ví dụ chạy được: tìm class trong thư mục plugin qua URLClassLoader

Ví dụ này minh họa lựa chọn loader tường minh và tác dụng của cờ `initialize`. Ta biên dịch class plugin **ra thư mục không nằm trên host classpath**, rồi dùng `URLClassLoader` để đọc nó.

### 7.1. Tạo Plugin.java

```java
package demo;

public final class Plugin {
    static {
        System.out.println("Plugin initialized");
    }

    public static String greet() {
        return "Hello plugin";
    }
}
```

### 7.2. Tạo PluginHost.java

```java
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;

public final class PluginHost {
    public static void main(String[] args) throws Exception {
        URL pluginDir = Path.of("plugin-classes").toUri().toURL();
        ClassLoader parent = PluginHost.class.getClassLoader();

        try (URLClassLoader pluginLoader =
                     new URLClassLoader(new URL[] { pluginDir }, parent)) {

            System.out.println("before loading");

            Class<?> type = Class.forName(
                    "demo.Plugin", false, pluginLoader
            );
            System.out.println("defined by plugin loader: "
                    + (type.getClassLoader() == pluginLoader));

            System.out.println("before initialization");
            Class<?> initialized = Class.forName(
                    "demo.Plugin", true, pluginLoader
            );
            System.out.println("same runtime class: "
                    + (type == initialized));

            Class.forName("demo.Plugin", true, pluginLoader);
            Object message = type.getMethod("greet").invoke(null);
            System.out.println(message);
        }
    }
}
```

### 7.3. Biên dịch và chạy

Trong thư mục chứa `Plugin.java` và `PluginHost.java`:

```bash
mkdir plugin-classes
javac -d plugin-classes Plugin.java
javac PluginHost.java
java -cp . PluginHost
```

Kết quả file:

```text
working-directory/
├── Plugin.java
├── PluginHost.java
├── PluginHost.class
└── plugin-classes/
    └── demo/
        └── Plugin.class
```

**Không thêm thư mục `plugin-classes` vào host classpath**. `java -cp . PluginHost` chỉ có host class trên classpath. Nếu thêm plugin class vào host classpath, parent có thể nạp nó trước và phép so sánh defining loader sẽ cho kết quả khác, vì `URLClassLoader` mặc định dùng parent-first.

Stdout khi chạy trong JVM mới với cấu trúc trên:

```text
before loading
defined by plugin loader: true
before initialization
Plugin initialized
same runtime class: true
Hello plugin
```

**Ý nghĩa kết quả:**

- `forName("demo.Plugin", false, pluginLoader)` khiến loader có thể tìm và định nghĩa Plugin, **chưa yêu cầu chạy** static block.
- `getClassLoader()==pluginLoader` là `true` vì parent không tìm thấy Plugin, và URLClassLoader tự định nghĩa class đó.
- `forName(..., true, pluginLoader)` yêu cầu khởi tạo lần đầu; static block in `Plugin initialized`.
- Lần gọi `true` tiếp theo trả cùng runtime class và không chạy lại static block.
- `getMethod("greet").invoke(null)` gọi static method và nhận chuỗi; Plugin đã initialized nên không có lần chạy initializer khác.
- Đóng `URLClassLoader` qua try-with-resources giải phóng tài nguyên URL/JAR mà loader nắm giữ; **không phải lệnh unload ngay lập tức** lớp đã định nghĩa. Unloading phụ thuộc khả năng JVM thu gom loader/class khi không còn reachable.

Nếu muốn có một bản `demo.Plugin` thứ hai cùng tên nhưng danh tính khác, dùng một defining loader **mới** không ủy quyền cho parent đã có Plugin. Không thể tạo định nghĩa khác trong cùng loader chỉ bằng cách gọi `forName` lại.

## 8. Ví dụ chạy được: tên array descriptor không khởi tạo element class

Tạo file `ForNameArrayDemo.java`:

```java
public class ForNameArrayDemo {
    static class Element {
        static {
            System.out.println("Element initialized");
        }
    }

    public static void main(String[] args) throws Exception {
        ClassLoader loader = ForNameArrayDemo.class.getClassLoader();

        System.out.println("before array forName");
        Class<?> arrayType = Class.forName(
                "[LForNameArrayDemo$Element;",
                true,
                loader
        );
        System.out.println("array type: " + arrayType.getTypeName());
        System.out.println("component name: "
                + arrayType.getComponentType().getSimpleName());

        System.out.println("before component initialization");
        Class.forName(
                "ForNameArrayDemo$Element", true, loader
        );
        System.out.println("done");
    }
}
```

Chạy bằng JDK 17+:

```bash
javac ForNameArrayDemo.java
java ForNameArrayDemo
```

Stdout:

```text
before array forName
array type: ForNameArrayDemo$Element[]
component name: Element
before component initialization
Element initialized
done
```

Dù lời gọi đầu dùng `initialize=true`, tên truyền vào là **array descriptor**. Java tạo/nhận array class, tải element type khi cần nhưng **không chạy Element static initializer** từ thao tác này. Static block chỉ chạy khi lời gọi thứ hai yêu cầu **chính Element** khởi tạo.

Đối với primitive array:

```java
Class<?> primitiveArray = Class.forName(
        "[I", true, ForNameArrayDemo.class.getClassLoader()
);
System.out.println(primitiveArray == int[].class);
```

Đây là trích đoạn cho method đã khai báo `throws ClassNotFoundException`; dòng `println` cho `true` trên JVM Java SE chuẩn. Không có initializer của primitive `int`.

## 9. Trường hợp lỗi khi tìm/nạp/khởi tạo

| Lỗi hoặc exception | Thời điểm thường xuất hiện | Nguyên nhân cần kiểm tra |
|---|---|---|
| `ClassNotFoundException` | Không tìm được tên qua loader đã chỉ định | Binary name, plugin directory/JAR, parent delegation, module/classpath |
| `LinkageError` | Loading/linking không đáp ứng quy tắc JVM | Bytecode không tương thích, định nghĩa trùng, xung đột binary dependencies |
| `UnsupportedClassVersionError` | Bytecode mới hơn JVM hỗ trợ | Major/minor class file, Java runtime thực sự chạy |
| `ExceptionInInitializerError` | Static initializer ném exception không thuộc `Error` khi init | Cause gốc từ `<clinit>` hoặc biểu thức gán static |
| `NoClassDefFoundError` sau initialization lỗi | Class runtime ở trạng thái erroneous | Lỗi init đầu tiên, chứ không chỉ classpath |
| `SecurityException` | Khi các điều kiện kiểm tra quyền bảo mật phù hợp tồn tại | Security manager/permission, môi trường đang dùng |

`ClassNotFoundException` là **checked exception**; code gọi `forName` cần `throws` hoặc `catch`. Các lỗi thuộc họ `LinkageError` không được khai báo trong `throws` nhưng vẫn có thể xảy ra. Không bắt tất cả lỗi rồi coi là “không có class”.

### 9.1. Ví dụ khởi tạo thất bại

Tạo `ForNameFailureDemo.java`:

```java
public class ForNameFailureDemo {
    static class Broken {
        static int state = failure();

        static int failure() {
            throw new IllegalStateException("bad initialization");
        }
    }

    public static void main(String[] args) throws Exception {
        ClassLoader loader = ForNameFailureDemo.class.getClassLoader();
        String name = "ForNameFailureDemo$Broken";

        System.out.println("loaded without initialization: "
                + (Class.forName(name, false, loader) != null));

        for (int attempt = 1; attempt <= 2; attempt++) {
            try {
                Class.forName(name, true, loader);
            } catch (LinkageError error) {
                System.out.println(
                        attempt + ": " + error.getClass().getSimpleName()
                );
            }
        }
    }
}
```

Chạy:

```bash
javac ForNameFailureDemo.java
java ForNameFailureDemo
```

Stdout:

```text
loaded without initialization: true
1: ExceptionInInitializerError
2: NoClassDefFoundError
```

Vì `initialize=false` không yêu cầu chạy `failure()`, lời gọi đầu thành công. Lời gọi `true` lần đầu kích hoạt code và ném `IllegalStateException`; JVM bọc bằng `ExceptionInInitializerError`. Khi runtime class đã erroneous, lần gọi `true` kế tiếp không chạy initializer lại, thường ném `NoClassDefFoundError`.

Đây là lý do phải kiểm tra **cause của lần lỗi đầu**, không chỉ thông báo ở những lần truy cập sau. Nếu muốn thử lại trong học tập, chạy một process JVM mới; dùng lại cùng runtime class trong cùng process không tự phục hồi state.

## 10. Phân biệt với ClassLoader.loadClass

Hai API đều có thể trả `Class<?>`, nhưng đối tượng điều khiển khác nhau:

| Tiêu chí | `Class.forName(name, initialize, loader)` | `loader.loadClass(name)` |
|---|---|---|
| Gọi qua | Static method của `Class` | Method của `ClassLoader` |
| Chọn loader | Truyền tường minh, `null` nghĩa bootstrap | Dùng chính object loader gọi method |
| Mặc định yêu cầu initialization? | Phụ thuộc tham số `initialize` | Không; public overload tương đương `loadClass(name, false)` |
| Nhận array descriptor? | Có, cú pháp như `[Ljava.lang.String;` | Không phải con đường portable để yêu cầu array type từ custom loader |
| Kết quả | `Class<?>` | `Class<?>` |
| Lỗi khi class thiếu | `ClassNotFoundException` | `ClassNotFoundException` |
| Có tạo instance? | Không | Không |

**Không đánh đồng `initialize=true` với `resolve=true`** trong protected `ClassLoader.loadClass(name, resolve)`. `resolveClass(c)` yêu cầu liên kết, còn initialization có thêm việc chạy static initializer. Tương tự `getDeclaredMethods()`, `getAnnotations()` hoặc các thao tác phản chiếu khác có các điều kiện loading/linking riêng; đọc metadata không tự động đồng nghĩa gọi `<clinit>`.

### Khi nào ưu tiên API nào?

- Có **binary name** và muốn chắc chắn lớp được khởi tạo: `Class.forName(name, true, chosenLoader)`.
- Có tên và chỉ muốn khám phá metadata/chưa muốn static side effects: `Class.forName(name, false, chosenLoader)`.
- Đang triển khai một ClassLoader và chỉ cần tìm lớp theo quy tắc loader: `loader.loadClass(name)`.
- Biết chính xác class lúc compile: thường dùng `SomeType.class`, tránh tìm theo chuỗi nếu không cần động.
- Có array component `Class<?>` khi làm plugin: dùng `java.lang.reflect.Array.newInstance(componentClass, size)` để nhận array object/array class đúng defining loader.

## 11. Class.forName(Module, String) là API khác

Từ Java 9, có overload:

```java
public static Class<?> forName(Module module, String name)
```

Nó **không tương đương** với overload ba tham số:

- Tìm class/interface với binary name trong **module được chỉ định**.
- Không khởi tạo class; theo tài liệu API, nó không thực hiện linking theo cách overload ba tham số yêu cầu.
- Nếu không tìm thấy class đúng module, có thể trả `null` thay vì ném `ClassNotFoundException`.
- Nó không hỗ trợ array descriptor như `"[Ljava.lang.String;"`.
- Việc có `Class<?>` vẫn không trao quyền truy cập member bị giới hạn bởi module/package.

Do đó, khi làm hệ module, không nên thay thẳng `Class.forName(name, false, loader)` thành `Class.forName(module, name)` rồi giả định cùng contract.

## 12. Những vấn đề thực tế với plugin và framework

### 12.1. Tên đúng nhưng loader sai

Một plugin chứa `com.acme.Plugin` nhưng host gọi:

```java
Class.forName("com.acme.Plugin");
```

Nếu loader của host không tìm thấy lớp plugin, lời gọi thất bại với `ClassNotFoundException`, dù file plugin thực sự có trên máy. Giải pháp là xác định **ClassLoader phù hợp** của plugin và truyền cho overload ba tham số.

Một vấn đề ngược lại: cả host và plugin cùng chứa một lớp API chung. Nếu custom loader dùng child-first cho API đó, hai runtime classes cùng binary name có thể không cast qua lại; `getName()` bằng nhau không có nghĩa `Class<?>` bằng nhau. Nên giữ các API giao tiếp giữa host/plugin do loader chung phù hợp định nghĩa.

### 12.2. initialize=true có tác dụng phụ

Với plugin registry, gọi `forName(name, true, loader)` trong lúc *quét danh sách* có thể chạy static block ngay cả khi plugin chưa được chọn sử dụng. Nếu initializer tạo thread, kết nối database, ghi log hoặc cấu hình global state, việc quét đơn thuần có thể trở thành thao tác tốn kém hoặc gây lỗi.

Một cách phân tách trách nhiệm:

1. **Discovery:** tìm class bằng `initialize=false`, đọc metadata và kiểm tra điều kiện cần.
2. **Validation:** xác định class phù hợp API, module/loader và kiểu constructor/method cần thiết.
3. **Activation:** khi thực sự dùng plugin, thực hiện operation yêu cầu initialization và tạo instance phù hợp.
4. **Failure handling:** phân biệt class missing, linkage incompatible, initialization failed và lỗi application logic.

Dù `false` tránh yêu cầu init của **class đích**, việc khám phá bằng reflection vẫn có thể tải các kiểu liên quan, và một số framework method tự có tác dụng phụ. Không đặt niềm tin tuyệt đối rằng discovery là thao tác không thể ném lỗi.

### 12.3. Parent-first hay child-first là chuyện của loader

`Class.forName` **không thay đổi chính sách delegation**. Nếu custom loader kế thừa `ClassLoader.loadClass` mặc định, nó ưu tiên `findLoadedClass`, rồi loader cha và mới đến `findClass`. Nếu loader override `loadClass` với quy tắc child-first có điều kiện, `Class.forName` sử dụng behavior thực của loader đó.

Muốn chẩn đoán, log cả:

```java
// Trích đoạn sau khi đã có Class<?> type:
System.out.println(type.getName());
System.out.println(type.getClassLoader());
System.out.println(type.getModule());
```

Bộ ba tên/defining loader/module hỗ trợ xác định class runtime đã tìm được, nhất là khi nhiều JAR có cùng binary name.

## 13. Checklist chẩn đoán Class.forName

Khi một lệnh `Class.forName` có kết quả khác dự kiến, kiểm tra theo thứ tự:

1. **Chuỗi `name`** có đúng **binary name** không? Nếu nested class, có dùng `$`? Nếu mảng, có dùng descriptor với `[` và `L...;`? Có vô tình đưa `.class`, dấu `/` hoặc generic arguments vào tên?
2. **Loader truyền vào** là gì? Có phải `null`, loader của host, TCCL hay plugin-specific loader? Parent có tìm được lớp khác cùng tên trước không?
3. **`initialize`** là `true` hay `false`? Static block có thể chạy từ lần dùng trước đó không? Có đang gọi array descriptor khiến element vẫn chưa initialize không?
4. **Runtime type đã được xác định** bằng `type.getName()`, `type.getClassLoader()` và nếu phù hợp `type.getModule()` chưa?
5. **Lỗi thuộc nhóm nào**: `ClassNotFoundException`, `LinkageError`, `ExceptionInInitializerError` hay lỗi reflection/access? Đọc đầy đủ cause và lỗi đầu tiên, không chỉ lần gọi lại.
6. **JDK/runtime** đúng phiên bản cho bytecode và module access chưa? `ClassNotFoundException` không phải lời giải thích duy nhất cho mọi lỗi loading.
7. **Test trong JVM mới** nếu đang kiểm tra thứ tự khởi tạo: một class đã initialized sẽ không chạy static block lần nữa trong cùng runtime class.
8. **Kiểm tra dependency của plugin**: tìm được entry-point class chưa đảm bảo mọi class mà nó sử dụng sẽ liên kết và chạy thành công.
9. **Không dùng `Class.forName` để “hot reload”** một class đã định nghĩa; cần thiết kế vòng đời plugin/loader và cơ chế reload phù hợp.

## 14. Câu hỏi tự kiểm tra

1. **`Class.forName("p.Service", false, loader)` có chạy `Service.<clinit>` không?** Không chủ động yêu cầu; Service có thể đã được khởi tạo trước.
2. **`Class.forName("p.Service", true, loader)` trả đối tượng Service không?** Không; nó trả `Class<?>` và có thể chạy static initializer.
3. **Gọi `forName` hai lần với `true` có chạy `<clinit>` hai lần không?** Không, nếu cùng runtime class đã init thành công.
4. **Truyền `loader=null` có dùng system class loader không?** Không; overload này chọn bootstrap loader.
5. **`Class.forName("Outer.Inner")` có đúng để tìm member class `Outer.Inner` trong source không?** Thông thường không; binary name là `Outer$Inner`.
6. **`Class.forName("int")` có trả `int.class` không?** Không; dùng `int.class` hoặc API tra primitive riêng khi có hỗ trợ.
7. **Muốn tìm `String[][]` qua overload ba tham số thì name là gì?** `"[[Ljava.lang.String;"`.
8. **`Class.forName("[Lp.Widget;", true, loader)` có buộc khởi tạo Widget không?** Không; array component class không bị khởi tạo bởi lời gọi này.
9. **Dùng `Class.forName("p.Service")` có ngầm lấy TCCL không?** Không; nó dùng defining loader của caller theo contract overload một tham số.
10. **Một plugin class được parent định nghĩa thì `type.getClassLoader()` có luôn bằng loader được truyền vào forName không?** Không; parent/boot có thể là defining loader.
11. **Tìm được `Class<?>` là đã được phép invoke mọi private method không?** Không; Java access và module boundaries vẫn áp dụng.
12. **`Class.forName(Module, String)` không tìm thấy class thì ném CNFE giống overload ba tham số không?** Không; nó có thể trả `null` và có contract riêng.

## 15. Tài liệu chuẩn

- [Java SE 21 API — `java.lang.Class.forName(String, boolean, ClassLoader)`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Class.html): hợp đồng từng tham số, array descriptors, exception và khác biệt overload.
- [Java SE 26 API — `java.lang.Class`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Class.html): tài liệu API mới, bao gồm `forPrimitiveName(String)` ở những phiên bản hỗ trợ.
- [Java SE 21 API — `java.lang.ClassLoader`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ClassLoader.html): loading, parent-first, `findLoadedClass`, `findClass`, defining loader.
- [JLS — 12.2 Loading; 12.3 Linking; 12.4 Initialization](https://docs.oracle.com/javase/specs/jls/se26/html/jls-12.html): quy tắc khởi tạo static state, superclass, reflection và loading/linking.
- [JVMS — 5 Loading, Linking, and Initializing](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-5.html): type identity, link/initialize và trạng thái lỗi.

Điểm cần nhớ khi thiết kế ứng dụng có ClassLoader động là **ba tham số kiểm soát ba thứ khác nhau**: `name` xác định kiểu được hỏi, `loader` xác định đường tìm và danh tính runtime có thể nhận được, `initialize` quyết định có yêu cầu chạy logic khởi tạo hay chưa. Phân biệt chúng sẽ tránh cả lỗi không tìm thấy plugin lẫn việc chạy initializer quá sớm.
