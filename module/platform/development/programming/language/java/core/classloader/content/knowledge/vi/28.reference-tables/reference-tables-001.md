# Bảng đối chiếu `loadClass`, `forName`, `defineClass` và `resolveClass` trong Java

## 1. Nhìn nhanh: bốn API làm những việc khác nhau

Khi xử lý class loader, plugin, reflection hoặc lỗi liên kết lớp trong Java, bốn tên API này rất dễ bị hiểu là bốn cách gọi tương đương để “nạp một lớp”. Chúng thực ra đảm nhiệm các vai trò khác nhau: **tìm/nạp lớp**, **tìm lớp và tùy chọn khởi tạo**, **định nghĩa lớp từ bytecode** và **yêu cầu liên kết một lớp đã có**.

Bảng dưới dùng ngữ nghĩa Java SE 17, đặc biệt với `java.lang.ClassLoader` và `java.lang.Class`. Các chi tiết bên trong JVM, thời điểm liên kết từng symbolic reference và log chẩn đoán có thể thay đổi tùy implementation.

| API | Vị trí và quyền truy cập | Đầu vào chính | Công việc chính | Tự yêu cầu initialize? | Kết quả |
|---|---|---|---|---|---|
| `loader.loadClass(String name)` | `ClassLoader`, `public` | Binary name và loader đang gọi | Tìm/nạp lớp theo thuật toán loader, tương đương `loadClass(name, false)` | **Không** | `Class<?>` |
| `loader.loadClass(String name, boolean resolve)` | `ClassLoader`, `protected` | Binary name và cờ `resolve` | Tìm/nạp; khi `resolve=true`, gọi `resolveClass` cho lớp tìm được (trong triển khai mặc định) | **Không** | `Class<?>` |
| `Class.forName(String name)` | `Class`, `public static` | Tên lớp; **loader định nghĩa class đang gọi** được dùng theo đặc tả | Tìm/nạp và yêu cầu **initialize** nếu chưa khởi tạo | **Có** | `Class<?>` |
| `Class.forName(String name, boolean initialize, ClassLoader loader)` | `Class`, `public static` | Tên, cờ initialize và loader được chỉ định | Tìm/nạp bằng loader này; `true` yêu cầu initialize, `false` không | **Theo cờ** | `Class<?>` |
| `defineClass(String name, byte[] bytes, int off, int len)` | `ClassLoader`, `protected final` | Tên kỳ vọng và bytes của file class | Chuyển bytecode thành một **runtime class do loader này định nghĩa** | **Không** | `Class<?>` |
| `resolveClass(Class<?> c)` | `ClassLoader`, `protected final` | `Class` đã có | **Link** lớp đã được định nghĩa; nếu đã linked thì không làm thêm | **Không** | `void` |

**Điểm then chốt:** `resolve` trong `loadClass(name, true)` nghĩa là **liên kết**, không phải “initialize = true”. Hai cờ `resolve` và `initialize` thuộc **hai giai đoạn khác nhau**. Gọi `defineClass` chỉ tạo định nghĩa runtime; nó không tương đương “gọi static initializer”. Và `Class.forName` không tự tạo instance bằng constructor.

Ngoài các overload trên, Java 9+ còn có `Class.forName(Module module, String name)`: đây là API tra lớp theo **module**, trả về `null` nếu không tìm thấy; theo Javadoc, overload này **không liên kết và không chạy class initializer**. Không áp dụng mặc định “mọi `forName` đều initialize” cho overload `Module`.

## 2. Đặt vào vòng đời lớp để không nhầm thuật ngữ

Một cách hình dung thực dụng:

```text
Tên binary của lớp, ví dụ sample.ProbeTarget
                 │
                 ▼
       ClassLoader.loadClass(name)
                 │
     ┌───────────┴───────────┐
     │ Đã được nạp?          │
     ├─ Có ─► trả Class      │
     │ Chưa                  │
     ▼                       │
 Parent delegation / findClass
     │
     ▼
 Đọc bytes từ nguồn phù hợp
     │
     ▼
 defineClass(name, bytes, ...)
     │
     └───────────► Class<?> ───────────────┐
                                         │
                                         ▼
                               resolveClass(c)
                                         │
                                         ▼
                                 Linking / verification,
                                 preparation và resolution
                                         │
                    khi active use hoặc yêu cầu initialize
                                         ▼
                              Initialization (`<clinit>`)
```

Đây là **sơ đồ khái niệm**, không phải lời cam kết JVM phải thực thi đầy đủ mọi bước theo đúng một thứ tự log cứng. Linking gồm verification, preparation và resolution; resolution của một số symbolic reference có thể được thực hiện muộn. JVM cũng có quyền nạp các lớp phụ thuộc khi cần.

Phân biệt ba kết quả:

- **Loaded/defined:** một `Class<?>` đại diện cho một runtime class. Nó có thể vẫn **chưa initialization**.
- **Linked:** JVM đã thực hiện các bước liên kết theo ngữ nghĩa cần thiết. Điều này **không** có nghĩa mọi class mà mã nguồn từng tham chiếu đều đã được tải/khởi tạo.
- **Initialized:** JVM thực hiện quy trình khởi tạo lớp, bao gồm static initializers và static field initializers khi cần. Một lớp có thể được load và linked từ trước nhưng chưa init.

**Danh tính lớp runtime** được xác định bằng **binary name và defining class loader**. Hai loader có thể định nghĩa hai `Class<?>` khác nhau cùng tên `sample.ProbeTarget`. Cùng tên class không đồng nghĩa cùng kiểu Java khi chuyển object giữa hai loader.

## 3. `ClassLoader.loadClass`: tìm và nạp theo chiến lược loader

### `loadClass(String)`: API công khai thường dùng

```java
ClassLoader loader = Thread.currentThread().getContextClassLoader();
Class<?> type = loader.loadClass("com.example.Plugin");
```

Đoạn trên là **mảnh mã minh họa**, giả định `getContextClassLoader()` khác `null` và `com.example.Plugin` có thể được loader tìm thấy. Nó nhận `Class<?>`, **không tạo instance**, và việc chỉ gọi `loadClass` không yêu cầu khởi tạo lớp.

Đối với implementation mặc định của `ClassLoader`, `loadClass(name)` tương đương gọi `loadClass(name, false)`. Nếu lớp đã nạp, loader có thể trả về `Class` hiện có; không nhất thiết mở lại JAR hay đọc class bytes lần nữa.

### `loadClass(String, boolean)`: overload protected

Javadoc mô tả thuật toán mặc định của `loadClass(name, resolve)` theo thứ tự:

1. `findLoadedClass(name)` kiểm tra lớp tương ứng đã được nạp trong phạm vi mà loader này biết.
2. Nếu chưa có, ủy quyền cho parent loader; nếu không có parent, sử dụng cơ chế loader tích hợp của VM.
3. Nếu parent không tìm được, gọi `findClass(name)` — vị trí phổ biến để custom loader tải bytes và gọi `defineClass`.
4. Nếu tìm được và `resolve=true`, gọi `resolveClass(c)` cho `Class` kết quả.

Đây là **hành vi mặc định**; một subclass có thể override `loadClass` để thay đổi cách tìm hoặc delegation. Vì vậy đừng khẳng định mọi loader của plugin luôn parent-first: cần đọc implementation thực tế. Trong đa số loader theo delegation thông thường, override `findClass` là cách mở rộng an toàn và đúng thiết kế hơn là viết lại hoàn toàn `loadClass`.

```java
public final class MyLoader extends ClassLoader {
    public MyLoader(ClassLoader parent) {
        super(parent);
    }

    // Ví dụ rút gọn: trả kết quả của protected overload.
    public Class<?> loadAndLink(String binaryName)
            throws ClassNotFoundException {
        return super.loadClass(binaryName, true);
    }
}
```

Class `MyLoader` minh họa việc mở quyền gọi `protected` thông qua một method do subclass cung cấp; ví dụ này không triển khai `findClass` nên chưa phải một plugin loader tự tìm bytecode.

**Không nhầm `resolve=true` với `initialize=true`.** Hai cờ khác nhau, và `loadClass(name, true)` vẫn không tự yêu cầu thực thi `<clinit>`. Đổi tên biến `resolve` thành “initialize” trong code không đổi ngữ nghĩa thực tế.

## 4. `Class.forName`: lựa chọn tùy chọn initialization

### `Class.forName(String name)`

```java
Class<?> driver = Class.forName("com.example.Driver");
```

Đây là mảnh mã minh họa, giả định class có tồn tại. Overload một tham số **yêu cầu initialize** lớp nếu lớp chưa được init. Theo Javadoc Java SE 17, nó tương đương `Class.forName(name, true, currentLoader)`, trong đó `currentLoader` là **defining loader của class thực hiện lời gọi**. Không thể mặc nhiên thay nó bằng “system loader”, “thread context loader” hoặc “loader của mọi thư viện”.

Một ví dụ thường gặp là framework/plugin chạy dưới một class loader khác với caller. Gọi overload một tham số có thể **không tìm thấy class plugin**, dù plugin loader riêng biết class đó. Trong trường hợp ấy cần chỉ rõ loader thích hợp.

### `Class.forName(String name, boolean initialize, ClassLoader loader)`

```java
ClassLoader pluginLoader = /* loader đã được tạo đúng cách */;
Class<?> loaded = Class.forName(
        "com.example.Plugin", false, pluginLoader);

Class<?> initialized = Class.forName(
        "com.example.Plugin", true, pluginLoader);
```

Đây là **mã minh họa trong ngữ cảnh có biến `pluginLoader`**, không phải chương trình độc lập. Nếu lớp chưa được load, hai lời gọi có thể làm nó được load. Khác biệt quan trọng:

- `initialize=false`: **không yêu cầu chạy initializer** cho lớp đích ở lời gọi đó; không có nghĩa là JVM cam kết “chưa link bất kỳ thứ gì”.
- `initialize=true`: JVM bảo đảm khởi tạo theo quy tắc Java nếu lớp chưa được initialize. Trong quá trình đó, các superclass và một số superinterface cũng có thể được khởi tạo theo JLS.
- Nếu lớp đã initialize, gọi `forName(..., true, ...)` lần nữa trên **cùng runtime class** không chạy lại `<clinit>`.
- Nếu `loader == null` ở overload này, Javadoc quy định dùng **bootstrap class loader**, không phải “chọn loader hiện tại”.
- Nếu `name` là tên của array class, component type có thể được load nhưng **không được initialize chỉ bởi lời gọi cho array đó**.
- Chuỗi như `"int"` không trả về `int.class`; API này không phải cách tra primitive class object theo tên.

Với ứng dụng cần **xem metadata mà hạn chế side effects của static initializer**, lựa chọn `forName(name, false, correctLoader)` thường hữu ích. Dù vậy việc phản chiếu và thao tác tiếp theo (ví dụ invoke static method) vẫn có thể kích hoạt initialization.

### `forName` và reflection errors

`Class.forName` có thể ném `ClassNotFoundException` khi loader không tìm được class, `LinkageError` nếu liên kết bị lỗi và `ExceptionInInitializerError` nếu static initializer thất bại theo trường hợp áp dụng. Không coi việc bắt `ClassNotFoundException` là đủ để xử lý mọi sai lệch binary/API.

## 5. `defineClass`: định nghĩa lớp từ bytecode

`defineClass` là method **`protected final`** của `ClassLoader`. Các overload thường dùng:

```java
// Mã bên trong subclass của ClassLoader.
Class<?> type = defineClass(binaryName, bytecode, 0, bytecode.length);
```

JDK 17 còn có overload nhận `ProtectionDomain` hoặc `ByteBuffer`. `defineClass` chuyển dữ liệu hợp lệ của file class thành `Class<?>` được **loader hiện tại định nghĩa**, chịu các quy tắc về binary name, package và bảo vệ.

Một custom loader thường làm như sau:

```java
@Override
protected Class<?> findClass(String name) throws ClassNotFoundException {
    try {
        byte[] bytes = readBytecodeFor(name);
        return defineClass(name, bytes, 0, bytes.length);
    } catch (java.io.IOException e) {
        throw new ClassNotFoundException(name, e);
    }
}
```

Đây là **pseudocode Java** chỉ minh họa pattern: `readBytecodeFor(name)` chưa được khai báo và cần do người triển khai cung cấp. Ví dụ đầy đủ, chạy được nằm ở phần 7.

Lưu ý thiết yếu:

- `defineClass` **không tự quyết định cách tìm classpath, không tự triển khai parent delegation, không tự gọi constructor và không yêu cầu initialize**. Nó chỉ xử lý bytes mà caller cung cấp.
- Trong class loader tuân theo delegation, đường đi bình thường là `loadClass → findClass → defineClass` khi parent không tìm được. Gọi `defineClass` trực tiếp để “ép thay” một lớp đã được loader đó định nghĩa là sai mô hình.
- Cùng **binary name** không thể được định nghĩa hai lần bởi cùng defining loader theo cách thông thường; duplicate definition dẫn đến lỗi liên kết, ví dụ `LinkageError`.
- Tên kỳ vọng không trùng class bytes, dữ liệu không hợp lệ hoặc hạn chế package có thể dẫn đến `NoClassDefFoundError`, `ClassFormatError`, `SecurityException` hay lỗi liên kết tương ứng. Một loader ứng dụng không được tự định nghĩa class trong package bắt đầu bằng `java.`.
- `defineClass` với overload không chỉ rõ `ProtectionDomain` dùng protection domain mặc định của API. Khi thiết kế loader production, phải quan tâm quyền truy cập, nguồn code, signer/certificate consistency và vòng đời của package; không dùng mẫu tối giản này như giải pháp bảo mật hoàn chỉnh.
- Định nghĩa lớp tạo ra runtime identity gắn với loader. Hai loader khác nhau có thể định nghĩa cùng class bytes thành **hai loại runtime khác nhau**.

**Khi nào dùng?** Khi bạn **viết custom ClassLoader** và cần biến bytecode từ file/JAR/network/generated output thành runtime class. Code nghiệp vụ thông thường gần như không nên gọi trực tiếp API protected này.

## 6. `resolveClass`: liên kết, không chạy `<clinit>`

`resolveClass(Class<?> c)` cũng là method **`protected final`** của `ClassLoader`. Javadoc mô tả nó là thao tác **links the specified class**; nếu lớp đã được linked thì chỉ trở về. Tên method dễ gây hiểu nhầm: Java VM có khái niệm **resolution** của symbolic references, nhưng một số resolution có thể được trì hoãn cho tới khi sử dụng; đừng diễn dịch `resolveClass` là “tải và resolve toàn bộ dependency graph” hay “chạy static initializer”.

Ví dụ expose API từ subclass:

```java
final class LinkingLoader extends ClassLoader {
    void link(Class<?> type) {
        resolveClass(type);
    }
}
```

Đây là mảnh code minh họa: `link` chỉ có ý nghĩa nếu `type` đến từ một đường nạp/định nghĩa lớp phù hợp; đoạn trên không tự cung cấp bytes để tạo class. Trong custom loader, pattern phổ biến:

```text
bytes → defineClass(...) → Class<?> type → resolveClass(type)
                                │
                                └─ Sau đó một active use / forName(true)
                                   mới yêu cầu initialization
```

**`resolveClass` không có public overload** để code bất kỳ dùng trực tiếp bên ngoài subclass; khác với `Class.forName` vốn là static public API. `loadClass(name, true)` gọi `resolveClass` trong implementation mặc định; vì vậy **hai API có liên hệ nhưng không đồng nghĩa**.

## 7. Ví dụ Java 17+: so sánh ba loader, bốn API và thứ tự initialization

Thí nghiệm sau cố tình biên dịch class plugin **ngoài classpath của chương trình chủ**, để class chỉ được định nghĩa bởi loader tùy biến. Chúng ta quan sát bằng output cố định rằng `loadClass`, `defineClass`, `resolveClass` và `loadClass(name, true)` **không yêu cầu init**, trong khi `forName(..., true, loader)` làm khởi tạo mỗi runtime class.

### Cấu trúc

```text
working/
├── ClassLoadingComparison.java
├── plugin-src/
│   └── sample/
│       └── ProbeTarget.java
└── plugin-classes/
    └── sample/
        └── ProbeTarget.class  (javac tạo)
```

File **`plugin-src/sample/ProbeTarget.java`**:

```java
package sample;

public final class ProbeTarget {
    static {
        System.out.println("ProbeTarget initialized");
    }

    public static int value() {
        return 42;
    }
}
```

File **`ClassLoadingComparison.java`**:

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

public final class ClassLoadingComparison {
    private static final String NAME = "sample.ProbeTarget";

    static final class ByteLoader extends ClassLoader {
        ByteLoader() {
            super(ClassLoader.getPlatformClassLoader());
        }

        @Override
        protected Class<?> findClass(String name)
                throws ClassNotFoundException {
            if (!NAME.equals(name)) {
                throw new ClassNotFoundException(name);
            }
            try {
                byte[] bytes = Files.readAllBytes(
                        Path.of("plugin-classes", "sample", "ProbeTarget.class"));
                return defineClass(name, bytes, 0, bytes.length);
            } catch (IOException e) {
                throw new ClassNotFoundException(name, e);
            }
        }

        Class<?> defineDirectly(String name)
                throws ClassNotFoundException {
            return findClass(name);
        }

        void link(Class<?> type) {
            resolveClass(type);
        }

        Class<?> loadAndResolve(String name)
                throws ClassNotFoundException {
            return super.loadClass(name, true);
        }
    }

    public static void main(String[] args) throws Exception {
        ByteLoader a = new ByteLoader();
        System.out.println("A: loadClass");
        Class<?> first = a.loadClass(NAME);
        System.out.println("A: forName(false) same Class = "
                + (first == Class.forName(NAME, false, a)));
        System.out.println("A: forName(true)");
        Class.forName(NAME, true, a);
        System.out.println("A: value = "
                + first.getMethod("value").invoke(null));

        ByteLoader b = new ByteLoader();
        System.out.println("B: defineClass");
        Class<?> second = b.defineDirectly(NAME);
        System.out.println("B: resolveClass");
        b.link(second);
        System.out.println("B: forName(true)");
        Class.forName(NAME, true, b);
        System.out.println("A and B different = " + (first != second));

        ByteLoader c = new ByteLoader();
        System.out.println("C: loadClass(resolve=true)");
        c.loadAndResolve(NAME);
        System.out.println("C: forName(true)");
        Class.forName(NAME, true, c);
    }
}
```

### Biên dịch và chạy

Tại thư mục `working`, tạo trước thư mục `plugin-src/sample` và `plugin-classes`; đặt hai file như trên, rồi chạy:

```bash
javac -d plugin-classes plugin-src/sample/ProbeTarget.java
javac ClassLoadingComparison.java
java -cp . ClassLoadingComparison
```

**Không thêm `plugin-classes` vào `-cp .`**: nếu plugin ở classpath của chương trình chủ, class loader cha/khác có thể nạp nó và thí nghiệm sẽ không còn chứng minh đúng đường `ByteLoader.defineClass`. Với lệnh này, dấu `.` đại diện đúng **một** entry nên dùng giống nhau trên Windows và Unix.

Output ứng dụng (không bật log JVM) **chính xác**:

```text
A: loadClass
A: forName(false) same Class = true
A: forName(true)
ProbeTarget initialized
A: value = 42
B: defineClass
B: resolveClass
B: forName(true)
ProbeTarget initialized
A and B different = true
C: loadClass(resolve=true)
C: forName(true)
ProbeTarget initialized
```

Giải thích lần lượt:

- **Loader A:** `a.loadClass(NAME)` trả `Class` mà chưa in `ProbeTarget initialized`. `forName(NAME, false, a)` trả **cùng `Class`** và cũng không yêu cầu init. `forName(NAME, true, a)` kích hoạt static initializer; reflection gọi `value()` sau đó trả `42`.
- **Loader B:** `defineDirectly` gọi `findClass`, trong đó `defineClass` định nghĩa một lớp mới từ cùng bytes. `b.link(second)` gọi `resolveClass` nhưng không in static initializer. `forName(true)` sau đó làm lớp của B init lần đầu.
- **Hai loader A/B:** `first != second` là `true` dù cùng `sample.ProbeTarget` và cùng file `.class`: defining loader khác tạo runtime class identity khác.
- **Loader C:** `loadAndResolve` đi qua `super.loadClass(name, true)`, tức resolve-flag của loader API. Nó **không initialize**. Lệnh `forName(true)` tiếp theo mới làm static initializer của lớp C chạy.

Mỗi loader định nghĩa một **runtime class riêng**, nên thấy ba dòng `ProbeTarget initialized` là hợp lệ; không phải JVM khởi tạo lại **cùng một** lớp ba lần.

Ví dụ được thiết kế để diễn giải API công khai/protected; nó **không** phải custom loader production. `defineDirectly` cố ý bỏ qua đường tìm kiếm/delegation chỉ để phân biệt `defineClass` với `loadClass`. Trong sản phẩm, nên ưu tiên implementation loader có locking, lookup policy và quản lý package/protection domain chuẩn.

### Thêm log JVM để quan sát

Trên HotSpot JDK 17+:

```bash
java -Xlog:class+load=info,class+init=info -cp . ClassLoadingComparison
```

Tìm các dòng chứa `sample.ProbeTarget` và tag `[class,load]` hoặc `[class,init]`. Log có thể chứa nhiều lớp JDK và thông tin động (timestamp, address, loader data); **không** cố khẳng định mọi bản HotSpot tạo ra một chuỗi log byte-for-byte giống nhau. Nếu cần lưu file:

```bash
java -Xlog:class+load=info,class+init=info:file=class-events.log:time,uptime,level,tags -cp . ClassLoadingComparison
```

Bật log class ở **lượt quan sát**, tránh lấy kết quả timing của lượt log làm benchmark so sánh hiệu năng vì I/O/logging có overhead. Các log tag giúp xác nhận class thực sự được load và init, không biến resolve thành init.

## 8. Bảng chọn API theo tình huống

| Tình huống | Nên dùng | Lý do |
|---|---|---|
| Muốn loader tìm và trả class theo chính sách delegation, **chưa cần side effect init** | `loader.loadClass(name)` | API công khai, không yêu cầu initialize |
| Muốn điều khiển rõ loader và thời điểm initialization | `Class.forName(name, false/true, loader)` | Tường minh class loader và cờ initialize |
| Muốn gọi `forName` mà dùng loader của chính class caller | `Class.forName(name)` | Javadoc xác định current loader và init=true |
| Muốn viết custom loader từ bytecode file/network/generated bytes | `defineClass` bên trong `findClass` | Chuyển bytes thành runtime class của loader hiện tại |
| Muốn class loader chủ động **link** lớp đã có | `resolveClass(c)` hoặc `loadClass(name, true)` trong subclass | Link là trách nhiệm của loader, tách khỏi init |
| Muốn lấy `Class` theo một named module mà không init và có thể trả `null` | `Class.forName(module, name)` | Overload module có semantics riêng |
| Muốn tạo object, chạy constructor và sử dụng dependency | Lấy `Class`/type rồi dùng constructor/API tương ứng | Bốn API trong bảng **không tự tạo instance** |
| Muốn unload class/plugin | Quản lý vòng đời loader và tham chiếu, quan sát GC/unloading | Không API nào trong bốn method là “unloadClass” |

Lưu ý `loadClass(name)` và `forName(name, false, loader)` thường được dùng để “chỉ load”, nhưng **không nên tuyên bố** hai đường này tương đương tuyệt đối với mọi custom loader: `forName` có quy định riêng của `Class`, còn implementation `loadClass` của một subclass có thể thay đổi hành vi mặc định hoặc có side effects riêng.

## 9. Các lỗi, giới hạn quyền truy cập và điểm dễ hiểu sai

### Phân biệt tên binary và tên source

Các phương thức nhận tên class dưới dạng string thường dùng **binary name**, ví dụ `java.util.Map$Entry` cho nested type `Map.Entry`. Với class `com.example.Demo`, tên đúng là `"com.example.Demo"`, không phải đường dẫn `"com/example/Demo.class"`. Với overload `Class.forName(String, boolean, ClassLoader)`, tên array còn có dạng descriptor như `"[Ljava.lang.String;"`, nên phải xem hợp đồng API trước khi tự nối chuỗi.

`defineClass(name, bytes, ...)` yêu cầu nội dung bytecode phù hợp với binary name dự kiến. Không được lấy bytes của `com.example.A` rồi yêu cầu định nghĩa tên `com.example.B` và kỳ vọng VM tự đổi tên trong constant pool.

### `ClassNotFoundException`, `NoClassDefFoundError` và các `LinkageError`

- `ClassNotFoundException` là checked exception phổ biến khi **yêu cầu tra tên lớp** mà loader không thể tìm được.
- `NoClassDefFoundError` là `LinkageError`, thường xuất hiện khi runtime cần một định nghĩa lớp từng được kỳ vọng tồn tại nhưng không thể tìm/nạp ở thời điểm đó; cũng có thể xuất hiện khi class trước đó initialization thất bại và được dùng lại.
- `ClassFormatError`, `UnsupportedClassVersionError` và các lỗi liên kết khác liên quan bytes/class version không hợp lệ, không tương thích runtime hoặc quá trình linking.
- `ExceptionInInitializerError` thường cho thấy static initializer/initialization bị lỗi, có thể chỉ xuất hiện khi `forName(..., true, loader)` hoặc lần active use chạy.
- `ClassCastException` khi chuyển object giữa hai runtime type cùng tên nhưng khác defining loader không nhất thiết là lỗi “không tìm thấy class”.

Đừng giải quyết các lỗi trên bằng cách gọi `resolveClass` nhiều lần hoặc thêm `Class.forName` một cách tùy tiện. Cần kiểm tra exception type, classpath, loader delegation, binary identity và version.

### `protected` không đồng nghĩa public API

`defineClass`, `resolveClass` và `loadClass(name, boolean)` là protected của `ClassLoader`; `defineClass`/`resolveClass` còn là final. Code nghiệp vụ bên ngoài subclass thông thường **không thể gọi** trực tiếp các method protected qua một object bất kỳ. Trong code ví dụ, `ByteLoader` công khai các wrapper riêng (`defineDirectly`, `link`, `loadAndResolve`) để minh họa và quan sát. Các wrapper ấy **không phải API tiêu chuẩn của Java**.

Không cố bypass bảo vệ Java module/access hoặc phản chiếu vào `ClassLoader#defineClass` chỉ để load plugin; cách đó có thể bị chặn bởi encapsulation của module `java.base` và làm thiết kế phụ thuộc chi tiết runtime.

### Resolve không phải initialize; initialize không có nghĩa “instantiate”

- `resolveClass(c)` → link class theo đặc tả; **không chạy `new`/constructor**.
- `Class.forName(name, true, loader)` → yêu cầu class initialization, gồm static initialization; **không gọi constructor instance**.
- `Class.forName(name, false, loader)` → không yêu cầu initialization; **không cam kết mọi metadata/dependency đều chưa được VM xử lý**.
- `ClassLoader.loadClass(name)` → tra/nạp, không bắt buộc phải thực hiện `<clinit>`; **không được nhầm với `Class.forName(name)`**.
- `defineClass(...)` → tạo `Class` định nghĩa từ bytes; **không thay JAR runtime toàn cục**, không tái định nghĩa cùng lớp đã được loader đó define.

Nếu cần một đối tượng, phải chọn constructor/factory đúng API và xử lý riêng các bước truy cập/phản chiếu. Một lần khởi tạo class có thể kéo theo khởi tạo superclass trước, theo quy tắc JLS `12.4`.

## 10. Quy trình debug khi class loader cho kết quả bất ngờ

1. **Ghi đúng API đang được gọi:** `loadClass(name)`, `forName(name)`, `forName(name, false, loader)`, `defineClass` hay `resolveClass`. Đặc biệt ghi rõ cờ `initialize` hoặc `resolve`.
2. **Chứng minh defining loader:** lấy `type.getClassLoader()`; `null` có thể đại diện bootstrap loader. Đừng suy chỉ từ tên package/class.
3. **Kiểm tra nguồn bytes và delegation:** classpath/module path, thứ tự JAR, loader parent/child, `findClass`. Trong plugin environment, parent có thể nạp phiên bản khác với file plugin.
4. **Xác nhận sự kiện load/init:** trên HotSpot, bật `-Xlog:class+load=info,class+init=info` trước khi tái hiện; log class load khác với log class init.
5. **Đọc nguyên exception và stack trace:** phân biệt missing class, invalid bytecode, linkage conflict và lỗi `<clinit>`. Không catch một loại rồi giả định mọi lỗi là do classpath.
6. **Kiểm tra phiên bản JVM và bytecode:** class file major version phải được runtime hỗ trợ; thay đổi dependency tại runtime không làm loader đang giữ `Class` cũ tự quên chúng.
7. **Giải pháp theo ranh giới đúng:** sửa dependency/loader policy, thống nhất API implementation, tạo loader mới trong lifecycle plugin nếu phù hợp; không dùng `System.gc()` để “sửa” mâu thuẫn class definition.

Ví dụ in nhanh loader identity trong code Java khi đã có `Class<?> type`:

```java
System.out.println("Class name = " + type.getName());
System.out.println("Defining loader = " + type.getClassLoader());
System.out.println("Module = " + type.getModule().getName());
```

Đây là đoạn **minh họa sử dụng biến `type` đã có**, không phải chương trình độc lập. Một unnamed module có thể có tên `null`; class do bootstrap loader định nghĩa cũng có loader `null`. Với cùng tên `getName()` nhưng loader khác, hai `Class<?>` vẫn khác nhau.

## 11. Câu hỏi tự kiểm tra

**Câu 1.** Hai câu `loader.loadClass("X")` và `Class.forName("X")` có bảo đảm khởi tạo lớp như nhau không?  
**Đáp án:** Không. `loadClass(String)` không yêu cầu init; `Class.forName(String)` yêu cầu init và dùng defining loader của caller.

**Câu 2.** Cờ `resolve=true` có tương đương `initialize=true` không?  
**Đáp án:** Không. `resolve=true` yêu cầu link qua `resolveClass` trong loader mặc định; `initialize=true` yêu cầu class initialization theo ngữ nghĩa `Class.forName`.

**Câu 3.** Có thể gọi `defineClass` hai lần để “ghi đè” cùng class đã định nghĩa bởi một loader không?  
**Đáp án:** Không. Một defining loader không thể định nghĩa cùng binary name lần nữa như thế; tạo loader khác sẽ cho runtime class khác, không thay class cũ.

**Câu 4.** `Class.forName("int")` có phải `int.class` không?  
**Đáp án:** Không. Theo Javadoc, overload tên chuỗi không dùng để lấy primitive `Class` từ tên primitive.

**Câu 5.** Tại sao ví dụ in `ProbeTarget initialized` ba lần?  
**Đáp án:** Ba `ByteLoader` khác nhau đã định nghĩa ba runtime class cùng binary name; mỗi class được yêu cầu init riêng.

**Câu 6.** Muốn biết class đã load nhưng chưa chạy `<clinit>` thì nên dùng gì?  
**Đáp án:** `loadClass(name)` hoặc `Class.forName(name, false, loader)` và quan sát log `class+load` so với `class+init`; chú ý side effects từ custom loader và thao tác tiếp theo.

## 12. Tài liệu gốc

- [Java SE 17 — `ClassLoader`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html): `loadClass(String)`, `loadClass(String, boolean)`, `findClass`, `defineClass`, `resolveClass` và cơ chế delegation.
- [Java SE 17 — `Class`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html): ba nhóm overload `forName` với `String`, `String/boolean/ClassLoader` và `Module/String`.
- [JLS 17 — Chương 12: Execution](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html): định nghĩa loading, linking, initialization và unloading.
- [JVMS 17 — Chương 5: Loading, Linking and Initializing](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html): ngữ nghĩa VM và thời điểm liên kết.
- [JDK 17 — `java` command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html): cú pháp `-Xlog` để quan sát class load và init trên HotSpot.
