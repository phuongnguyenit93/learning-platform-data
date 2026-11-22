# Trình tự mặc định: findLoadedClass, loader cha và findClass

## 1. Câu hỏi cốt lõi: khi yêu cầu nạp một lớp, ClassLoader tìm ở đâu trước?

Trong Java, lệnh yêu cầu nạp một lớp, chẳng hạn `loader.loadClass("example.Plugin")`, **không mặc nhiên đọc ngay tệp `Plugin.class` từ nơi loader đó quản lý**. Với triển khai mặc định của `java.lang.ClassLoader.loadClass(String, boolean)`, JVM/loader thực hiện trình tự:

1. **`findLoadedClass(name)`**: kiểm tra lớp đã được ghi nhận là đã nạp với loader đang được hỏi hay chưa.
2. **Ủy quyền cho loader cha (parent)**: nếu bước 1 chưa tìm được, hỏi parent trước. Nếu `parent == null`, dùng bộ nạp bootstrap tích hợp trong JVM.
3. **`findClass(name)`**: chỉ khi bên cha/ bootstrap không tìm thấy thì loader hiện tại mới thử tự tìm và định nghĩa lớp.
4. **`resolveClass(c)` nếu `resolve == true`**: yêu cầu liên kết lớp đã tìm được; trả đối tượng `Class<?>`.

Đây là **parent-first delegation** (ưu tiên loader cha), hay còn gọi là delegation model mặc định.

```text
loadClass("example.Plugin", resolve)
│
└─ synchronized(getClassLoadingLock(name))
   │
   ├─ 1. findLoadedClass(name)
   │    └─ tìm thấy? ── Có ───────────────┐
   │                                     │
   ├─ 2. parent.loadClass(name)          │
   │       hoặc bootstrap khi parent=null│
   │    └─ tìm thấy? ── Có ───────────────┤
   │                                     │
   ├─ 3. findClass(name)                 │
   │    ├─ tìm thấy → define/load ────────┤
   │    └─ không thấy → ClassNotFoundException
   │                                     │
   └─────────────────────────────────────┘
                                         │
                               resolve? ─┤
                                  Có → resolveClass(c)
                                  Không → bỏ qua bước này
                                         │
                                      return c
```

**Chốt ý:** thứ tự ba bước tìm lớp là **đã nạp → cha → tự tìm**. `findClass` không phải bước đầu tiên của mô hình mặc định. Thứ tự này là **hành vi của triển khai mặc định**; ClassLoader tùy chỉnh có thể override `loadClass` và thay đổi chính sách, nên không áp quy tắc parent-first tuyệt đối cho mọi class loader.

## 2. Từ API đến luồng thực thi

Hai overload của `ClassLoader` có vai trò khác nhau:

```java
public Class<?> loadClass(String name)
        throws ClassNotFoundException

protected Class<?> loadClass(String name, boolean resolve)
        throws ClassNotFoundException
```

- `loadClass(String name)` là API công khai; đối với triển khai `ClassLoader` thông thường, nó gọi `loadClass(name, false)`.
- `loadClass(String name, boolean resolve)` là API được bảo vệ; **triển khai mặc định** chứa thuật toán kiểm tra cache/ủy quyền/tự tìm/resolve.
- `name` là **binary name**, ví dụ `com.acme.PluginService`, không phải đường dẫn `com/acme/PluginService.class` hoặc tên tệp JAR.
- Cờ `resolve` chỉ điều khiển việc gọi `resolveClass` sau khi có lớp; **không có nghĩa** phải khởi tạo lớp hay gọi static initializer.

Mã giả sau minh họa **logic** của triển khai mặc định trong JDK hiện đại. `bootstrapLookup` bên dưới là tên giả để giải thích, **không phải phương thức API công khai**:

```java
// PSEUDOCODE — không phải định nghĩa ClassLoader dùng để biên dịch
protected Class<?> loadClass(String name, boolean resolve)
        throws ClassNotFoundException {
    synchronized (getClassLoadingLock(name)) {
        Class<?> found = findLoadedClass(name);

        if (found == null) {
            try {
                found = (parent != null)
                        ? parent.loadClass(name)
                        : bootstrapLookup(name);
            } catch (ClassNotFoundException notFoundInParent) {
                // Cha không tìm được; thử chính loader hiện tại.
            }

            if (found == null) {
                found = findClass(name);
            }
        }

        if (resolve) {
            resolveClass(found);
        }
        return found;
    }
}
```

Đối với loader không override `loadClass`, việc đồng bộ qua `getClassLoadingLock(name)` bảo vệ trình tự kiểm tra/tạo lớp trước các yêu cầu đồng thời. `getClassLoadingLock` có thể trả về khóa chung theo instance loader hoặc khóa riêng theo tên class nếu loader đã đăng ký parallel capable; không giả định mọi loader chỉ dùng một monitor duy nhất.

**Cần đọc luồng đúng:** `findLoadedClass` là kiểm tra trạng thái đã ghi nhận; parent delegation là một yêu cầu nạp khác đi lên chuỗi loader; `findClass` là điểm mở rộng để **tự định nghĩa** lớp từ nguồn riêng. Không có lời gọi tự động `findClass` sau khi parent đã trả kết quả thành công.

## 3. Bước 1 — findLoadedClass: lớp này đã từng được nạp chưa?

Khai báo API:

```java
protected final Class<?> findLoadedClass(String name)
```

Phương thức trả về:

- `Class<?>` nếu JVM đã ghi nhận loader hiện tại là **initiating loader** của class với binary name đó.
- `null` nếu chưa có bản ghi phù hợp.

Điểm dễ nhầm là **initiating loader** và **defining loader**:

- **Defining loader**: loader đã thực sự gọi `defineClass` (hoặc thực hiện cơ chế định nghĩa tương đương) để tạo runtime class.
- **Initiating loader**: loader được JVM ghi nhận là đã khởi xướng việc nạp class theo tên đó. Nó có thể **ủy quyền thành công** cho defining loader khác.

Vì vậy `findLoadedClass(name) != null` **không chứng minh loader hiện tại đã đọc bytes hoặc tự định nghĩa class**; lớp đó có thể do parent hoặc bootstrap định nghĩa. `Class<?>.getClassLoader()` cho biết defining loader trong trường hợp thông thường (với bootstrap được biểu diễn bằng `null`).

### Vì sao kiểm tra trước?

- Tránh lặp công việc tìm class và tạo định nghĩa mới cho những lần gọi sau.
- Bảo đảm các lần nạp thành công cùng binary name qua cùng initiating loader trở lại đối tượng `Class<?>` đã được ghi nhận, không định nghĩa thêm một class trùng danh tính.
- Hạn chế lỗi `LinkageError` dạng thử `defineClass` trùng binary name trong cùng defining loader.

Ví dụ, nếu plugin loader đã định nghĩa `plugin.Greeter` một lần, gọi `loadClass("plugin.Greeter")` lần nữa theo trình tự mặc định sẽ tìm lại bản đã nạp ở bước 1. Lần thứ hai **không gọi `findClass`** cho tên đó và không cần đọc lại file bytecode.

**Lưu ý:** `findLoadedClass` kiểm tra lớp đã ghi nhận, không hỏi xem source `.class` mới được sửa trên ổ đĩa hay không. Với cùng runtime class, thay file bytecode sau lần load **không tự cập nhật** class đã định nghĩa. Hot reload thực sự cần cơ chế phù hợp (chẳng hạn runtime class mới qua defining loader mới hoặc instrumentation theo giới hạn JVM), không phải chỉ gọi `loadClass` lần nữa.

## 4. Bước 2 — ủy quyền lên loader cha

Nếu chưa tìm thấy ở bước 1, ClassLoader mặc định gọi `parent.loadClass(name)` trước. Mỗi parent lại áp dụng chính sách của chính nó; với chuỗi parent-first, yêu cầu thường đi từ loader con lên các loader cao hơn cho đến khi một loader tìm thấy class.

```text
CustomPluginLoader
       │ hỏi parent trước
       ▼
Application ClassLoader
       │ hỏi parent trước
       ▼
Platform ClassLoader
       │ cơ chế truy cập parent/boot
       ▼
Bootstrap / built-in JVM loader
       │
       └─ nếu không ai tìm được:
          quay lại thử findClass ở loader phù hợp
```

Sơ đồ là một **mô hình khái niệm**. Trên JDK 9+, loader mặc định và hệ module có các chi tiết tìm kiếm riêng; không nên giả định classpath và module graph luôn biểu diễn bằng một chuỗi đường dẫn vật lý thuần túy. Với bộ nạp ứng dụng/tùy chỉnh kế thừa triển khai mặc định, ý quan trọng vẫn là **ưu tiên parent trước khi loader con định nghĩa class mới**.

### Vì sao ưu tiên cha?

1. **Tái sử dụng định nghĩa chung:** ví dụ một plugin tham chiếu `java.lang.String` phải dùng cùng định nghĩa runtime chuẩn thay vì tự dựng một bản khác.
2. **Giữ danh tính kiểu nhất quán** cho những thư viện/API chung giữa chương trình chính và plugin khi parent cung cấp chúng.
3. **Giảm vô tình shadow** một class mà parent đã tìm được: nếu cả parent và child cùng có file `com.acme.Api.class`, mặc định parent thắng.
4. **Giúp phân tách trách nhiệm:** parent cung cấp nền tảng/thư viện chia sẻ; child tìm class riêng khi parent không có.

Đây là quy tắc tìm kiếm, **không phải** lời bảo đảm tuyệt đối chống code độc hại hoặc xung đột phiên bản. ClassLoader tùy chỉnh có thể đổi chính sách; JVM còn có các quy tắc về package/module, truy cập, package sealing, bytecode và kiểu runtime.

### Nếu parent không tìm được thì điều gì xảy ra?

Với parent khác `null`, mặc định một `ClassNotFoundException` báo không tìm thấy từ parent được dùng làm tín hiệu để tiếp tục thử `findClass` của child. Nếu parent **tìm thấy**, child trả luôn class đó. Nếu parent gây lỗi khác như `LinkageError` hoặc `SecurityException`, không được suy ra rằng triển khai mặc định sẽ nuốt mọi lỗi và âm thầm tìm ở child: fallback bình thường dành cho trường hợp **không tìm thấy**.

Nếu `parent == null`, ClassLoader mặc định dùng cơ chế bootstrap tích hợp của máy ảo để thử trước, **không dùng `ClassLoader.getSystemClassLoader()` làm parent thay thế**.

## 5. Bước 3 — findClass: loader hiện tại tự tìm bytecode

Khai báo API:

```java
protected Class<?> findClass(String name)
        throws ClassNotFoundException
```

Đây là **điểm mở rộng chính** khi viết một custom loader giữ nguyên parent-first. Triển khai `ClassLoader` gốc của `findClass(String)` chỉ ném `ClassNotFoundException`; muốn tự đọc class từ directory, ZIP/JAR, network, mã đã sinh hoặc kho dữ liệu riêng, subclass cần override phương thức này.

Các bước trong một `findClass` tùy chỉnh thường là:

1. Chuyển binary name thành vị trí nguồn tương ứng, ví dụ `plugin.Greeter` → `plugin/Greeter.class`.
2. Đọc **đúng bytes** của class file.
3. Gọi `defineClass(name, bytes, 0, bytes.length)` để JVM định nghĩa runtime class với tên tương ứng.
4. Trả `Class<?>` nhận được; nếu không tìm được dữ liệu, ném `ClassNotFoundException` (có thể kèm nguyên nhân từ I/O).

`defineClass` chỉ định nghĩa lớp từ bytes; nó **không đồng nghĩa chạy `<clinit>`** của lớp đó. Các ràng buộc bytecode, module/package, quyền truy cập và binary compatibility vẫn do JVM thực thi.

### Vì sao thường override findClass thay vì loadClass?

Khi chỉ override `findClass` và kế thừa `loadClass`, ta có ngay:

- Thứ tự parent-first đúng triển khai mặc định.
- Kiểm tra `findLoadedClass` trước, tránh nạp trùng.
- Khóa đồng bộ `getClassLoadingLock(name)` trong quá trình loading.
- Gọi `resolveClass` khi protected overload được yêu cầu với `resolve=true`.
- Quy tắc lỗi và fallback đã được Java quy định.

Override `loadClass` chỉ phù hợp khi **thật sự cần chính sách khác** (chẳng hạn child-first cho nhóm namespace plugin) và khi đó người viết phải chủ động xử lý việc kiểm tra đã nạp, bảo vệ lớp nền tảng, khóa đồng bộ, fallback và việc resolve.

## 6. Ví dụ chạy được 1: parent thắng trước findClass

Ví dụ ngắn sau giúp quan sát fallback mà không phải tự tạo tệp bytecode.

Tạo file `ParentFirstDemo.java`:

```java
public class ParentFirstDemo {
    static final class TraceLoader extends ClassLoader {
        TraceLoader(ClassLoader parent) {
            super(parent);
        }

        @Override
        protected Class<?> findClass(String name)
                throws ClassNotFoundException {
            System.out.println("findClass: " + name);
            throw new ClassNotFoundException(name);
        }
    }

    public static void main(String[] args) throws Exception {
        TraceLoader loader = new TraceLoader(
                ParentFirstDemo.class.getClassLoader()
        );

        Class<?> core = loader.loadClass("java.lang.String");
        System.out.println("String defined by bootstrap: "
                + (core.getClassLoader() == null));

        try {
            loader.loadClass("my.example.DoesNotExist");
        } catch (ClassNotFoundException ex) {
            System.out.println("No such class");
        }
    }
}
```

Chạy với JDK 17+:

```bash
javac ParentFirstDemo.java
java ParentFirstDemo
```

Stdout dự kiến chính xác trên JVM Java SE chuẩn:

```text
String defined by bootstrap: true
findClass: my.example.DoesNotExist
No such class
```

**Diễn giải:**

- Với `java.lang.String`, parent/chuỗi loader nền tảng tìm được class. `TraceLoader.findClass("java.lang.String")` **không chạy**, nên không có dòng `findClass: java.lang.String`.
- Với `my.example.DoesNotExist`, parent không tìm thấy; thuật toán mới gọi `TraceLoader.findClass`, và ta nhìn thấy thông báo trước khi `ClassNotFoundException` được chuyển về chương trình.
- `String.class.getClassLoader() == null` được JVM dùng để biểu diễn lớp do bootstrap định nghĩa. Giá trị `null` ở đây **không có nghĩa** `String` thiếu loader hoặc nạp thất bại.
- Trong ví dụ này, `findClass` cố ý không định nghĩa lớp nào; ví dụ tiếp theo sẽ tải bytes thật.

## 7. Ví dụ chạy được 2: tự định nghĩa class, rồi dùng lại từ findLoadedClass

Ta tạo một class plugin **không nằm trên classpath của chương trình chính** và cho loader tùy chỉnh tìm từ directory riêng. Đây là tình huống tiêu biểu của parent-first: parent không có plugin nên child gọi `findClass`.

### 7.1. File plugin

Trong một thư mục làm việc trống, tạo file `Greeter.java`:

```java
package plugin;

public final class Greeter {
    static {
        System.out.println("Greeter initialized");
    }

    public static String greet() {
        return "Hello from plugin";
    }
}
```

### 7.2. File chương trình host

Cũng trong thư mục làm việc đó, tạo `PluginHost.java`:

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

public final class PluginHost {
    static final class DirectoryLoader extends ClassLoader {
        private final Path root;

        DirectoryLoader(Path root, ClassLoader parent) {
            super(parent);
            this.root = root;
        }

        @Override
        protected Class<?> findClass(String name)
                throws ClassNotFoundException {
            Path file = root.resolve(
                    name.replace('.', '/') + ".class"
            );
            byte[] bytes;
            try {
                bytes = Files.readAllBytes(file);
            } catch (IOException ex) {
                throw new ClassNotFoundException(name, ex);
            }

            System.out.println("findClass: " + name);
            return defineClass(name, bytes, 0, bytes.length);
        }
    }

    public static void main(String[] args) throws Exception {
        DirectoryLoader loader = new DirectoryLoader(
                Path.of("plugin-classes"),
                PluginHost.class.getClassLoader()
        );

        Class<?> first = loader.loadClass("plugin.Greeter");
        System.out.println("defined by child: "
                + (first.getClassLoader() == loader));

        Class<?> second = loader.loadClass("plugin.Greeter");
        System.out.println("same Class object: " + (first == second));

        System.out.println("before first active use");
        Object result = first.getMethod("greet").invoke(null);
        System.out.println(result);
    }
}
```

### 7.3. Biên dịch và chạy

Tạo thư mục kết quả riêng và biên dịch:

```bash
mkdir plugin-classes
javac -d plugin-classes Greeter.java
javac PluginHost.java
java -cp . PluginHost
```

Sau bước build, hai phần tách biệt như sau:

```text
working-directory/
├── Greeter.java
├── PluginHost.java
├── PluginHost.class
├── PluginHost$DirectoryLoader.class
└── plugin-classes/
    └── plugin/
        └── Greeter.class
```

**Quan trọng:** Khi chạy host, classpath là `.`; **không** thêm `plugin-classes` vào classpath host. Nếu thêm đường dẫn này vào classpath và parent có thể tìm `plugin.Greeter`, parent-first sẽ trả class của parent, và `DirectoryLoader.findClass` có thể không chạy.

Stdout chính xác với cấu trúc build ở trên:

```text
findClass: plugin.Greeter
defined by child: true
same Class object: true
before first active use
Greeter initialized
Hello from plugin
```

### 7.4. Vì sao các dòng xuất hiện đúng thứ tự này?

1. `PluginHost.class` do application loader nạp. `DirectoryLoader` nhận loader của host làm parent.
2. Lần gọi `loader.loadClass("plugin.Greeter")`: bước `findLoadedClass` chưa có class; parent tìm không thấy vì `plugin-classes` không trên classpath; `findClass` đọc bytes và gọi `defineClass`.
3. Kết quả `first.getClassLoader() == loader` là `true` vì **DirectoryLoader đã định nghĩa** class plugin.
4. Lần `loadClass` thứ hai trả lại cùng `Class<?>`. Không in `findClass` lần nữa: class này đã được JVM ghi nhận với loader đó.
5. `loadClass(name)` chưa bắt buộc chạy static block. Dòng `Greeter initialized` chỉ in khi reflection `Method.invoke` gọi `greet()`, làm JVM yêu cầu **initialization** của Greeter. Sau đó mới có chuỗi trả về.

Ví dụ chứng minh cả ba khía cạnh: **parent-first fallback**, **caching qua `findLoadedClass`**, và sự khác nhau giữa **load** với **initialize**.

Trong mã sản xuất, một loader lấy tên class từ input ngoài phải kiểm soát namespace, đường dẫn, mã nguồn, quyền truy cập, package/module và nguồn bytecode; ví dụ học tập chỉ minh họa cách nạp từ directory đã tin cậy.

## 8. Phân biệt findLoadedClass, findClass và defineClass

| API | Nhiệm vụ | Trả về / lỗi | Điểm cần nhớ |
|---|---|---|---|
| `findLoadedClass(name)` | Tra lớp đã ghi nhận với initiating loader | `Class<?>` hoặc `null` | Không đọc lại bytecode, không tự gọi parent |
| `parent.loadClass(name)` | Nhờ loader cha tìm lớp | `Class<?>` hoặc lỗi | Ưu tiên trước tìm cục bộ trong parent-first |
| `findClass(name)` | Hook tìm/định nghĩa lớp từ nguồn của child | `Class<?>` hoặc `ClassNotFoundException` | Chỉ được gọi trong thuật toán mặc định khi cha không tìm thấy |
| `defineClass(...)` | Định nghĩa runtime class từ bytecode | `Class<?>` hoặc lỗi định dạng/liên kết | Không tự thực thi initializer của class |
| `resolveClass(c)` | Yêu cầu liên kết runtime class | `void` | Không phải `Class.forName(..., true, ...)` và không đồng nghĩa initialization |
| `loadClass(name)` | Gọi luồng tìm class công khai | `Class<?>` hoặc lỗi | Tương đương yêu cầu `loadClass(name, false)` của API |

Một chi tiết hay bị bỏ sót: `findLoadedClass` là `final`; bạn **không override** nó để thay cache. Thông thường cũng **không gọi `findClass` trực tiếp từ code ứng dụng**, vì cách đó bỏ qua chuỗi parent-first và cơ chế khóa/tra class đã nạp của `loadClass`.

## 9. Nếu có cùng tên class ở parent và child?

Giả sử có hai nguồn cùng chứa binary name `com.example.Engine`:

```text
Application ClassLoader:
  com/example/Engine.class    (version A)

Custom Child ClassLoader:
  com/example/Engine.class    (version B)
```

Với `loadClass` mặc định, child luôn hỏi parent trước. Nếu parent tìm được `com.example.Engine`, child nhận **version A**, dù thư mục của child có **version B**. `findClass` của child không được gọi cho tên đó.

Đây là **parent-first shadowing**: parent giữ quyền ưu tiên tên. Khi làm plugin, cần thiết kế rõ namespace nào là API dùng chung và namespace nào riêng cho plugin. Nếu thực sự cần child-first trong một tập package, phải viết chính sách nạp có điều kiện và bảo đảm không vô tình nạp lại lớp nền tảng/chung một cách gây `ClassCastException`, `LinkageError` hoặc phá type identity.

**Danh tính runtime của class không chỉ là chuỗi tên:** hai class cùng binary name được định nghĩa bởi hai defining loaders khác nhau là hai runtime classes khác nhau. Parent-first giúp những class dùng chung được định nghĩa từ một parent, nhưng plugin class riêng do child định nghĩa vẫn có danh tính gắn với child.

Đừng sửa xung đột này bằng cách thay bytecode file rồi gọi `loadClass` lặp lại: sau lần nạp thành công, nhánh `findLoadedClass` ưu tiên kết quả đã ghi nhận.

## 10. Thứ tự tìm không đồng nghĩa thứ tự khởi tạo

`ClassLoader.loadClass("package.Type")` giúp lấy `Class<?>` và có thể liên kết lớp theo chính sách JVM, nhưng **không tự yêu cầu thực thi `Type.<clinit>`**.

Ví dụ với `Greeter` ở mục 7:

```java
Class<?> type = loader.loadClass("plugin.Greeter");
// Chưa yêu cầu chạy static initializer của Greeter.

Object greeting = type.getMethod("greet").invoke(null);
// Gọi static method ⇒ yêu cầu initialize Greeter.
```

Mã trên là **trích đoạn** từ ví dụ đầy đủ chứ không phải tệp Java độc lập.

Ngược lại:

```java
Class<?> type = Class.forName(
        "plugin.Greeter",
        true,
        loader
);
```

Với `initialize=true`, `Class.forName` yêu cầu khởi tạo class được chỉ định nếu chưa được khởi tạo. `Class.forName(name, false, loader)` không yêu cầu điều đó. Không nên dùng thông báo từ `static { System.out.println(...) }` để suy ra chính xác lúc nào `findLoadedClass`, verification hoặc resolution chạy; log static chỉ chứng minh **initialization** đã xảy ra.

Cờ `resolve=true` của protected `loadClass(name, resolve)` cũng **không phải** cờ `initialize`. `resolveClass` liên kết lớp, còn JVM có thể trì hoãn một số resolution của symbolic references đến lúc thực sự dùng, theo quy tắc đặc tả.

## 11. Phân biệt lỗi “không tìm thấy” với lỗi định nghĩa/liên kết

Khi thử nạp lớp theo parent-first, không phải lỗi nào cũng nói lên rằng bước `findClass` nên tiếp tục:

| Triệu chứng | Ý nghĩa thường gặp | Hành động kiểm tra |
|---|---|---|
| `ClassNotFoundException` | Parent và child không tìm được binary name qua đường nạp hiện tại | Tên nhị phân, classpath, thư mục plugin, nguồn loader |
| `NoClassDefFoundError` | JVM cần một class ở liên kết/thực thi nhưng định nghĩa thiếu hoặc lớp không thể khởi tạo | Cause, dependency, class bị lỗi init trước đó |
| `UnsupportedClassVersionError` | Bytecode yêu cầu JVM hỗ trợ major/minor mới hơn | `javap -verbose`, JDK runtime thực tế |
| `ClassFormatError` / `VerifyError` | Dữ liệu class file hoặc bytecode không hợp lệ | File nguồn, transformer, compiler |
| `LinkageError` do định nghĩa trùng | Có đường nạp tùy chỉnh gọi `defineClass` nhiều lần cho cùng class trong một loader | Tìm nơi override `loadClass`, đồng bộ, duplicate define |
| `ClassCastException` dù hai tên class giống nhau | Hai runtime classes cùng tên nhưng defining loaders khác nhau | Kiểm tra `getClassLoader()` hai phía |
| `SecurityException` | Vi phạm kiểm tra quyền, package/module hoặc quy tắc định nghĩa nhất định | Chính sách JVM, namespace, source bytecode |

**Điểm chốt của fallback:** mặc định **chỉ chuyển từ parent sang `findClass` khi parent không tìm được class**. `ClassNotFoundException` là dấu hiệu điển hình. Một `LinkageError` hoặc lỗi do cấu trúc bytecode của parent có thể đi thẳng ra ngoài; không hiểu đó là lý do để loader con thử “phiên bản khác”.

Nếu `findClass` đọc một đường dẫn không tồn tại, nên chuyển `IOException` thích hợp thành `ClassNotFoundException(name, cause)` để giữ nguyên ngữ nghĩa tìm kiếm. Nếu bytes có sẵn nhưng không phải class hợp lệ, việc định nghĩa có thể ném lỗi khác; không che mất nguyên nhân đó bằng một thông báo “file not found” chung.

## 12. Đồng bộ và yêu cầu nạp cùng tên từ nhiều thread

Đoạn `synchronized(getClassLoadingLock(name))` trong triển khai mặc định tồn tại vì hai thread có thể cùng gọi `loadClass("plugin.Greeter")`. Nếu cả hai cùng thấy chưa nạp rồi đồng thời gọi `defineClass` cùng binary name trên cùng loader, ít nhất một đường có thể thất bại vì định nghĩa trùng hoặc tạo trạng thái không mong muốn.

Mặc định, việc tìm loaded class, ủy quyền, fallback và `resolveClass` được đặt dưới khóa mà `getClassLoadingLock` cung cấp. Với class loader **parallel capable** đã được đăng ký thích hợp, khóa có thể là theo tên class để nạp những tên độc lập đồng thời; nếu không, thường đồng bộ trên đối tượng loader.

Khi custom loader override `loadClass`, người viết cần tự xem lại các quy tắc đồng bộ và delegation. Dùng tùy tiện nhiều loader gọi lẫn nhau còn có thể dẫn đến deadlock; không nên chỉ “bỏ synchronized để nhanh hơn”.

**Không nhầm hai lần nạp:**

- Nhiều thread cùng yêu cầu **cùng binary name + cùng loader**: cần phối hợp để không định nghĩa trùng.
- Hai **defining loaders khác nhau** định nghĩa cùng binary name: là hai runtime classes khác nhau và có thể hợp lệ cho mô hình plugin, nhưng không hoán đổi được như cùng kiểu Java.

## 13. Một số giới hạn của mô hình mặc định

- **ClassLoader tùy chỉnh có thể override `loadClass`:** những framework/container cần isolation hoặc child-first có thể chọn chính sách khác. Muốn biết thực sự dùng thứ tự nào, kiểm tra implementation của loader cụ thể.
- **Module-aware loading:** JDK 9+ có `findClass(String moduleName, String name)` và những loader phục vụ named modules; cách tìm class của loader xây dựng sẵn có thể xét module graph, không chỉ đường dẫn tệp đơn giản. Bài học đang mô tả phương thức `loadClass(String, boolean)` mặc định của `java.lang.ClassLoader`.
- **Class resource khác Class loading:** `getResource`/`getResources` có quy tắc tìm tài nguyên liên quan nhưng không suy diễn bytecode class chắc chắn được định nghĩa bằng việc tìm thấy một URL tài nguyên cùng tên.
- **Có bytecode không có nghĩa có quyền định nghĩa:** `defineClass` có thể bị từ chối bởi định dạng class, package name, module/package sealing và những quy tắc bảo vệ khác.
- **Không nhầm namespace của app với bootstrap:** `getClassLoader()==null` ở class nền tảng Java là cách biểu diễn bootstrap defining loader, không phải một lỗi giá trị null cần khắc phục.

## 14. Quy trình debug lớp được lấy từ loader nào

Khi một plugin “đang dùng nhầm class” hoặc loader con không đọc file plugin của nó, hãy làm theo thứ tự:

1. Ghi nhận **binary name** được đưa vào `loadClass` và **object loader** nào nhận yêu cầu đầu tiên.
2. Kiểm tra class đã được loader đó **initiated/loaded** trước đó chưa; nếu đã có, lần gọi sau trả class cũ thay vì đọc file mới.
3. Kiểm tra **parent**: `loader.getParent()` và chain loader của class caller, JVM/module path/classpath thực tế. Nếu parent có thể tìm tên đó, `findClass` của child có thể không chạy.
4. Nếu parent không tìm thấy, kiểm tra `findClass`: cách map tên thành đường dẫn, file bytes, `defineClass` và các lỗi bị bắt/chuyển đổi.
5. Với class trả về, log `type.getName()` và `type.getClassLoader()`. Đây là cách xác định tên và **defining loader**; không dùng mỗi tên class để chứng minh hai đối tượng `Class<?>` có cùng danh tính.
6. Nếu có lỗi ở runtime sau khi nạp xong, xác định đó là **linking**, **initialization** hay lỗi logic chương trình trước khi sửa thứ tự class loading.

Ví dụ lệnh chẩn đoán JDK trên JVM HotSpot hỗ trợ unified logging:

```bash
java -Xlog:class+load=info -cp . PluginHost
```

Log có thể rất dài và định dạng thay đổi theo JDK/VM. Nó giúp quan sát class được **nạp** từ đâu, nhưng không được coi là log bảo đảm mọi thao tác `findLoadedClass`, `findClass` hoặc static initializer đều sẽ được thể hiện bằng một dòng tương ứng.

## 15. Tự kiểm tra

1. **Đã từng gọi `loadClass("x.A")` thành công qua cùng loader, lần sau mặc định kiểm tra gì đầu tiên?** `findLoadedClass("x.A")`; nếu đã ghi nhận, trả class đó.
2. **Child có bản `x.A` riêng nhưng parent cũng tìm được `x.A`, mặc định dùng bản nào?** Bản parent đã nạp/trả về.
3. **Khi nào `findClass` được gọi?** Khi chưa tìm thấy ở `findLoadedClass` và parent/bootstrap không tìm được tên đó.
4. **Nếu không override `findClass` mà parent cũng không tìm thấy thì sao?** Triển khai `ClassLoader.findClass` mặc định ném `ClassNotFoundException`.
5. **`findLoadedClass(name) != null` chứng minh loader đó là defining loader không?** Không; initiating loader có thể ủy quyền cho loader khác định nghĩa.
6. **`loadClass(name)` có chạy static initializer không?** Không bắt buộc; bản public tương đương `loadClass(name, false)`, không yêu cầu khởi tạo.
7. **`resolve=true` có tương đương `initialize=true` của `Class.forName` không?** Không; `resolveClass` liên kết, còn initialization là bước khác.
8. **Tại sao lần gọi `loadClass("plugin.Greeter")` thứ hai không in `findClass` trong ví dụ?** `findLoadedClass` đã tìm được class do loader đó định nghĩa ở lần trước.
9. **Nếu parent ném `LinkageError` thay vì `ClassNotFoundException`, child có chắc được gọi `findClass` không?** Không; fallback của triển khai mặc định là đường không tìm thấy class.
10. **Muốn custom loader parent-first và đọc bytes từ thư mục riêng, nên override gì?** `findClass(String)`; kế thừa `loadClass` để dùng luồng kiểm tra cache, ủy quyền và khóa có sẵn.

## Tài liệu tham khảo chuẩn

- [Java SE 21 API — `java.lang.ClassLoader`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ClassLoader.html): mô tả thứ tự mặc định của `loadClass(String, boolean)`, `findLoadedClass`, `findClass`, `defineClass` và `resolveClass`.
- [Java SE 26 API — `java.lang.ClassLoader`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/ClassLoader.html): hợp đồng API hiện đại, bao gồm các khác biệt liên quan module và parallel-capable loader.
- [Java Virtual Machine Specification — §5.3 Creation of Classes and Interfaces](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-5.html#jvms-5.3): ý nghĩa defining/initiating loader và class identity.
- [Java Language Specification — §§12.2–12.4](https://docs.oracle.com/javase/specs/jls/se25/html/jls-12.html): loading, linking và initialization là các bước có ý nghĩa khác nhau.

**Ghi nhớ trình tự mặc định:** `findLoadedClass` → **parent** (hoặc bootstrap khi không có parent) → `findClass` → `resolveClass` nếu được yêu cầu → trả `Class<?>`. Khi viết loader tùy chỉnh tuân theo mô hình ủy quyền, override **`findClass`** là điểm bắt đầu hợp lý nhất.
