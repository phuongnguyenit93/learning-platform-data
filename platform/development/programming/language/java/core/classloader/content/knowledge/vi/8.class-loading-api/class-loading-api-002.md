# findClass: điểm mở rộng để tìm bytecode trong Java ClassLoader

## 1. Vì sao Java cần `findClass`?

Khi JVM cần một lớp Java, một `ClassLoader` có thể được yêu cầu nạp lớp theo **tên nhị phân** (*binary name*), chẳng hạn `com.example.plugin.PaymentPlugin`. Nhưng bytecode của lớp có thể nằm trong một thư mục riêng, JAR plugin, kho lưu trữ, một nguồn do ứng dụng quản lý hoặc một cơ chế nạp chuyên biệt. Java cung cấp phương thức **`findClass(String name)`** để lớp con của `ClassLoader` tự định nghĩa cách **tìm và tạo định nghĩa lớp từ bytecode** khi thuật toán nạp chọn sử dụng nguồn cục bộ của loader.

Ba phương thức có vai trò khác nhau:

- **`loadClass(name)`**: cửa vào thông thường để yêu cầu một lớp; triển khai mặc định xử lý lớp đã được nạp, ủy quyền cho parent, rồi mới nhờ `findClass`.
- **`findClass(name)`**: *extension point* để tìm định nghĩa ở nguồn dữ liệu mà loader hiện tại quản lý. Lớp con thường override phương thức này.
- **`defineClass(name, bytes, ...)`**: chuyển một chuỗi byte chứa định nghĩa lớp hợp lệ thành đối tượng `Class<?>` runtime gắn với **defining loader hiện tại**.

Vì vậy **`findClass` không phải là tên gọi khác của toàn bộ thao tác load class**. Phương thức này thường được gọi khi parent delegation không tìm ra lớp. Nó cũng không đồng nghĩa với việc chỉ trả về file `.class`: nếu tự triển khai `findClass` để định nghĩa một class, bạn thường phải đọc bytecode và gọi `defineClass`.

### Câu hỏi dẫn đường

Giả sử ứng dụng viết:

```java
Class<?> c = pluginLoader.loadClass("plugins.Report");
```

Lúc này có ít nhất hai kịch bản:

1. **Parent có `plugins.Report`:** parent trả về đối tượng `Class`; loader con có thể **không hề gọi** `findClass`. Defining loader là parent.
2. **Parent không có, plugin loader có bytecode riêng:** `loadClass` gọi `findClass` tại loader con; `findClass` đọc bytecode và dùng `defineClass`. Defining loader là plugin loader.

Hai kịch bản đều là kết quả bình thường của parent-first delegation. Dòng gọi `loadClass` không tự tiết lộ nơi định nghĩa class.

## 2. Chữ ký API, mặc định và quyền override

Trong `java.lang.ClassLoader`:

```java
protected Class<?> findClass(String name)
        throws ClassNotFoundException
```

Đây là chữ ký API dùng để minh họa, không phải một chương trình chạy độc lập.

- **`protected`**: lớp con có thể override để triển khai nguồn bytecode. Code bất kỳ ở ngoài class/quan hệ truy cập thích hợp không gọi trực tiếp `findClass` của loader.
- **Trả về `Class<?>`**: trả về định nghĩa runtime mà loader tìm được. Phương thức không trả về `byte[]` hoặc `Path`.
- **`throws ClassNotFoundException`**: khi nguồn mà loader chịu trách nhiệm không có lớp được yêu cầu, thường ném ngoại lệ này. `ClassNotFoundException` là checked exception.
- **Cài đặt mặc định của `ClassLoader.findClass(String)`**: ném `ClassNotFoundException`. Vì vậy, một lớp con chỉ gọi `super(parent)` nhưng không override `findClass` sẽ không tự tìm class ở thư mục tùy ý.
- **Phương thức không nhận đối số parent**: việc hỏi cha thuộc luồng logic của `loadClass`; `findClass` có nhiệm vụ cục bộ sau khi được chọn.

Mẫu tối giản:

```java
public final class BytecodeLoader extends ClassLoader {
    public BytecodeLoader(ClassLoader parent) {
        super(parent);
    }

    @Override
    protected Class<?> findClass(String binaryName)
            throws ClassNotFoundException {
        byte[] bytes = readOwnBytecode(binaryName);
        return defineClass(binaryName, bytes, 0, bytes.length);
    }

    private byte[] readOwnBytecode(String binaryName)
            throws ClassNotFoundException {
        throw new ClassNotFoundException(binaryName);
    }
}
```

Đây là **phác thảo cấu trúc**. Phương thức `readOwnBytecode` cố ý chưa có triển khai nguồn dữ liệu, nên không phải loader chức năng hoàn chỉnh. Ở phần thực hành bên dưới sẽ có chương trình Java 17 hoàn chỉnh, biên dịch và chạy được.

**Quan trọng:** nếu chỉ cần nạp class từ các URL của JAR/thư mục, `URLClassLoader` đã cung cấp cơ chế phù hợp cho nhiều tình huống. Tự viết `findClass` khi cần cách đọc bytecode khác, hoặc cần điều khiển rõ nguồn và vòng đời.

## 3. findClass nằm ở đâu trong thuật toán parent-first?

Cách thực thi mặc định của `ClassLoader.loadClass(String, boolean)` có thể được diễn giải như sau:

1. Lấy khóa nạp lớp phù hợp cho tên được yêu cầu (cơ chế `getClassLoadingLock(name)`).
2. Gọi `findLoadedClass(name)` để xem loader đã được ghi nhận là initiating loader của lớp ấy chưa.
3. Nếu chưa tìm thấy, thử hỏi **parent**. Khi không có parent Java-level, có cơ chế tra lớp ở bootstrap loader.
4. Nếu đường parent không tìm được lớp và ném `ClassNotFoundException`, gọi **`findClass(name)`** của loader hiện tại.
5. Nếu yêu cầu có tham số `resolve = true`, JVM có thể thực hiện `resolveClass(c)`; trả đối tượng `Class<?>`.

Sơ đồ:

```text
Application / JVM yêu cầu: child.loadClass("plugin.Report")
                    |
                    v
        findLoadedClass("plugin.Report")
                    |
             có? --+--> trả về Class đã ghi nhận
                    |
                 chưa có
                    |
                    v
            parent.loadClass(...)
                    |
            thành công? --yes--> trả Class do parent/ancestor định nghĩa
                    |
             ClassNotFoundException
                    |
                    v
            child.findClass(name)
                    |
          tìm bytecode -> defineClass(...)
                    |
                    v
                trả Class
```

Cần tránh hai hiểu lầm:

- **`findClass` không phải lúc nào cũng chạy.** Nếu parent trả về lớp, đường local search không cần được thực hiện.
- **`findClass` không nên tự gọi `loadClass(name)` với chính tên đang xử lý** để “thử thêm lần nữa”; dễ dẫn tới đệ quy không kết thúc hoặc vòng tìm class. Nếu cần nạp lớp khác, chỉ dùng API phù hợp với quan hệ phụ thuộc và delegation cụ thể.

Sơ đồ mô tả **mặc định**, không phải luật bắt buộc cho mọi custom loader. Framework có thể override `loadClass` để ưu tiên child-first theo package. Khi đó điểm gọi `findClass` thay đổi theo thuật toán framework.

## 4. Từ tên lớp sang bytecode: đường dẫn và nguồn dữ liệu

Nếu binary name là `com.acme.plugin.Report`, file class tương ứng trong một thư mục lớp thông thường có đường dẫn tương đối:

```text
com/acme/plugin/Report.class
```

Một cách lấy đường dẫn trên nền tảng có `Path`:

```java
Path file = classesRoot.resolve(
        binaryName.replace('.', '/') + ".class");
```

Đây là **đoạn minh họa**; nó giả định có sẵn biến `classesRoot` và `binaryName`, không phải chương trình độc lập.

Những điểm cần nhớ:

- `binaryName` khác với file path: tham số phương thức là `com.acme.plugin.Report`, **không** phải `com/acme/plugin/Report.class`.
- Class lồng nhau có binary name chứa `$`, ví dụ `Outer$Inner`. Không tự đổi `$` thành dấu `.`.
- Không phải mọi class đều tương ứng một file dễ tìm trên disk: class trong JAR, module image, generated bytecode, hidden classes và array classes có cơ chế khác.
- Đường dẫn phải được giới hạn trong vùng root được phép. Nếu nguồn tên/path đến từ cấu hình hoặc người dùng, cần validate tên nhị phân, chuẩn hóa đường dẫn và ngăn thoát khỏi root.
- `findClass` cần đóng tài nguyên khi đọc dữ liệu; những lỗi I/O thích hợp có thể được bọc vào `ClassNotFoundException` để caller thấy tên lớp và nguyên nhân gốc.

Đối với JAR thực tế, nên cân nhắc `URLClassLoader`, `JarFile` hoặc thư viện được quản lý thay vì tự giải nén thủ công mà bỏ qua manifest, multi-release JAR, package sealing hay tài nguyên đi kèm.

## 5. Thực nghiệm đầy đủ Java 17+: tự viết DirectoryClassLoader

Chương trình sau cho thấy **toàn bộ chuỗi** từ yêu cầu nạp tới bytecode:

1. Tạo tạm source code của một plugin.
2. Dùng compiler có sẵn trong JDK để biên dịch class vào thư mục tạm.
3. Khởi tạo một class loader có `findClass` đọc file `.class` trong thư mục đó.
4. Gọi `loadClass` hai lần cùng tên để quan sát cùng một `Class`.
5. So sánh loader được gọi với defining loader; kiểm tra trường hợp lớp có sẵn ở parent.
6. Dùng reflection tạo instance và gọi phương thức, không cần link trước plugin class vào project.

Tạo file `DirectoryClassLoaderDemo.java`:

```java
import java.io.IOException;
import java.lang.reflect.Method;
import java.nio.file.Files;
import java.nio.file.Path;
import javax.tools.JavaCompiler;
import javax.tools.ToolProvider;

public class DirectoryClassLoaderDemo {

    static final class DirectoryLoader extends ClassLoader {
        private final Path root;
        int localSearches;

        DirectoryLoader(Path root, ClassLoader parent) {
            super(parent);
            this.root = root.toAbsolutePath().normalize();
        }

        @Override
        protected Class<?> findClass(String binaryName)
                throws ClassNotFoundException {
            localSearches++;

            Path file = root.resolve(
                    binaryName.replace('.', '/') + ".class").normalize();
            if (!file.startsWith(root)) {
                throw new ClassNotFoundException(binaryName);
            }

            byte[] bytes;
            try {
                bytes = Files.readAllBytes(file);
            } catch (IOException e) {
                throw new ClassNotFoundException(binaryName, e);
            }

            return defineClass(binaryName, bytes, 0, bytes.length);
        }
    }

    public static void main(String[] args) throws Exception {
        Path root = Files.createTempDirectory("find-class-demo-");
        Path source = root.resolve("plugin/Greeter.java");
        Path bytecode = root.resolve("plugin/Greeter.class");

        try {
            Files.createDirectories(source.getParent());
            Files.writeString(source, """
                    package plugin;
                    public class Greeter {
                        public String message() {
                            return "Hello from plugin";
                        }
                    }
                    """);

            JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
            if (compiler == null) {
                throw new IllegalStateException("Run with a JDK");
            }
            int result = compiler.run(null, null, null,
                    "-d", root.toString(), source.toString());
            if (result != 0) {
                throw new IllegalStateException("Compilation failed");
            }

            DirectoryLoader child = new DirectoryLoader(
                    root, DirectoryClassLoaderDemo.class.getClassLoader());

            Class<?> first = child.loadClass("plugin.Greeter");
            Class<?> again = child.loadClass("plugin.Greeter");

            System.out.println("definedByChild="
                    + (first.getClassLoader() == child));
            System.out.println("sameClass=" + (first == again));
            System.out.println("localSearches=" + child.localSearches);

            Object instance = first.getDeclaredConstructor().newInstance();
            Method method = first.getMethod("message");
            System.out.println("message=" + method.invoke(instance));

            Class<?> fromParent = child.loadClass(
                    DirectoryClassLoaderDemo.class.getName());
            System.out.println("hostDefinedByParent="
                    + (fromParent.getClassLoader()
                       == DirectoryClassLoaderDemo.class.getClassLoader()));
            System.out.println("searchesAfterParent="
                    + child.localSearches);

            Class<?> stringType = child.loadClass("java.lang.String");
            System.out.println("stringFromBootstrap="
                    + (stringType.getClassLoader() == null));

            try {
                child.loadClass("plugin.Unknown");
            } catch (ClassNotFoundException e) {
                System.out.println("missing=ClassNotFoundException");
            }
            System.out.println("searchesAfterMissing="
                    + child.localSearches);
        } finally {
            Files.deleteIfExists(source);
            Files.deleteIfExists(bytecode);
            Files.deleteIfExists(root.resolve("plugin"));
            Files.deleteIfExists(root);
        }
    }
}
```

Biên dịch/chạy bằng **JDK 17 trở lên**:

```bash
javac DirectoryClassLoaderDemo.java
java DirectoryClassLoaderDemo
```

Stdout dự kiến nếu không có class trùng tên trong classpath, compiler tạo thành công bytecode và không có lỗi môi trường:

```text
definedByChild=true
sameClass=true
localSearches=1
message=Hello from plugin
hostDefinedByParent=true
searchesAfterParent=1
stringFromBootstrap=true
missing=ClassNotFoundException
searchesAfterMissing=2
```

### Giải thích kết quả chi tiết

**`definedByChild=true`:** lớp `plugin.Greeter` chỉ được tạo trong thư mục tạm. Parent của child không được cấu hình tìm thư mục đó; nó thất bại, nên child chuyển sang `findClass`, đọc bytecode và gọi `defineClass`. Vì thế defining loader của `Greeter` là `child`.

**`sameClass=true` và `localSearches=1`:** lần gọi `loadClass` đầu tiên tạo định nghĩa lớp và ghi nhận trạng thái nạp. Lần thứ hai với cùng loader và cùng tên được thỏa mãn bằng class đã được ghi nhận (mặc định qua `findLoadedClass`); không đọc lại file, không gọi `defineClass` lần nữa.

**`message=Hello from plugin`:** code ứng dụng không import `plugin.Greeter`. Reflection trên đối tượng `Class<?>` mà loader trả về vẫn tạo instance và gọi được phương thức public.

**`hostDefinedByParent=true`, `searchesAfterParent=1`:** lần yêu cầu nạp `DirectoryClassLoaderDemo` được parent xử lý. Child không cần gọi `findClass`, nên bộ đếm không đổi. Cùng một API `loadClass` có thể trả class do loader khác định nghĩa.

**`stringFromBootstrap=true`:** yêu cầu `java.lang.String` đi qua cơ chế tìm lớp nền tảng; `String.class.getClassLoader() == null` là dấu hiệu bootstrap loader.

**`missing=ClassNotFoundException` và `searchesAfterMissing=2`:** `plugin.Unknown` không có ở parent cũng không có trong thư mục bytecode, nên `findClass` đọc thất bại và ném `ClassNotFoundException`. Bộ đếm tăng thêm một. Chương trình chỉ bắt lỗi để minh họa, không chuyển lỗi thành class giả.

**Điều kiện chạy:** dùng JDK có `javax.tools.JavaCompiler`. Thư mục được tạo bằng `Files.createTempDirectory` và xóa sau khi thử nghiệm; mã không can thiệp vào file dự án hiện có. Trong môi trường khác, nếu parent đã có `plugin.Greeter` hoặc hạn chế tạo file tạm, kết quả sẽ thay đổi hoặc chương trình báo lỗi.

## 6. defineClass là bước tạo định nghĩa, không phải chỉ đọc dữ liệu

Trong `findClass` vừa viết:

```java
return defineClass(binaryName, bytes, 0, bytes.length);
```

Đây là **đoạn trích** từ ví dụ chạy được ở trên. Lời gọi thực hiện việc định nghĩa lớp bằng các byte class file. Một số hệ quả:

- Tên nhị phân truyền vào phải tương ứng với định nghĩa thực tế trong bytecode. Không thể “đổi tên class tùy ý” bằng cách đưa `name` khác.
- Bytecode không hợp lệ có thể gây `ClassFormatError`, `VerifyError` hoặc lỗi liên kết khác; không nên bắt tất cả rồi giả vờ lớp không tồn tại.
- Định nghĩa trùng binary name trong **cùng một defining loader** có thể gây `LinkageError`. Không được bỏ qua cơ chế tái sử dụng và cố gọi `defineClass` nhiều lần.
- JVM áp đặt các quy tắc, gồm giới hạn việc một loader tùy biến định nghĩa lớp trong namespace `java.*` và kiểm tra liên quan package/certificate. Không dùng custom loader để cố thay thế lớp nền tảng của JDK.
- Các quá tải `defineClass` cho phép truyền `ProtectionDomain` khi cần. Việc lấy bytecode từ một nguồn khác **không tự biến class loader thành sandbox an toàn**; nguồn code không tin cậy cần một mô hình cô lập bảo mật riêng.
- Một class đã được định nghĩa có thể cần nạp superclass, superinterface và các phụ thuộc khác khi JVM liên kết hay thực thi. `defineClass` thành công chưa bảo đảm mọi hành vi của class sau đó sẽ thành công.
- `resolveClass(c)` (phương thức protected/final) liên quan linking/resolution, **khác với initialization**. `loadClass` cũng không có nghĩa static initializer của class đã chạy.

Nếu file `Greeter.class` có đúng tên nhưng tham chiếu tới `plugin.Helper` không thể tìm, `Greeter` có thể thất bại ở một bước liên kết/sử dụng khác tùy loại tham chiếu và thời điểm resolution. Vì vậy, custom loader phải biết cách tìm cả những phụ thuộc cần thiết hoặc thiết kế delegation cho chúng.

## 7. Liên hệ với findLoadedClass: vì sao không định nghĩa lại lớp mỗi lần?

`ClassLoader.findLoadedClass(String)` là phương thức **protected final**. Nó trả về một `Class<?>` nếu JVM đã ghi nhận loader tương ứng là initiating loader cho lớp có binary name ấy; nếu không, trả `null`.

Triển khai mặc định của `loadClass` hỏi `findLoadedClass` **trước** parent và `findClass`. Điều này mang lại hai điểm quan trọng:

1. Nếu đã có lớp thích hợp, `loadClass` có thể trả ngay cùng đối tượng `Class` mà không đọc bytecode thêm lần nữa.
2. Điều được tái sử dụng là **định nghĩa runtime**, không chỉ kết quả lưu trong `Map<String, byte[]>` do ứng dụng tự tạo.

Không nên biến mỗi yêu cầu `loadClass("plugin.Greeter")` thành một lần gọi `defineClass` mới; trong một loader, cùng binary name không thể được định nghĩa lặp như các phiên bản độc lập.

### findLoadedClass không đồng nghĩa defining loader

Nếu loader con từng được JVM ghi nhận là **initiating loader** của class do parent định nghĩa, `findLoadedClass` có thể trả về class ấy, nhưng `clazz.getClassLoader()` vẫn trả **parent**. Sự ghi nhận initiating loader là phần của mô hình JVM, khác với định danh lớp (binary name + defining loader).

Không có một API public trực tiếp từ `Class<?>` để truy xuất “mọi initiating loader từng yêu cầu class này”. Việc `clazz.getClassLoader() == child` là kiểm tra defining loader, không phải phép thử xem child từng gửi request hay chưa.

**Đừng tự cài một cache Map thay cho findLoadedClass mà không hiểu concurrency:** cache tự quản có thể sai khi nhiều thread nạp cùng tên, khi delegation đổi kết quả hoặc khi loader được JVM ghi nhận initiating class theo một đường khác. Nếu không cần thuật toán đặc biệt, giữ `loadClass` mặc định sẽ đơn giản và an toàn hơn.

## 8. Đồng thời nhiều luồng: đặt logic ở đâu?

Nhiều luồng có thể đồng thời gọi `loader.loadClass("plugin.Greeter")`. Mặc định `ClassLoader.loadClass(String, boolean)` sử dụng `getClassLoadingLock(name)` để phối hợp nạp lớp; một loader đã đăng ký là *parallel capable* có thể dùng khóa theo tên lớp thay vì một khóa chung.

Khi chỉ override **`findClass`**, ta thường tận dụng sẵn các bước của `loadClass`: kiểm tra lớp đã nạp, đồng bộ, delegation và resolve khi được yêu cầu. Đây là lý do nên override `findClass` nếu chỉ muốn thay nguồn bytecode.

Nếu quyết định override chính **`loadClass`** để triển khai child-first, phải tự bảo toàn những quy tắc cần thiết:

- Kiểm tra lớp đã được ghi nhận nạp trước khi định nghĩa mới.
- Đồng bộ phù hợp để hai thread không cùng cố `defineClass` cùng tên.
- Giữ vùng namespace bắt buộc dùng chung, đặc biệt class JDK và API/SPI chung.
- Quy định rõ lúc nào gọi parent, lúc nào tìm cục bộ và cách báo lỗi.
- Đảm bảo linking, method signatures và type identity không bị xung đột.

Trong một lớp con custom, `getClassLoadingLock(name)` là API để lấy khóa đồng bộ mà cơ chế của `ClassLoader` sử dụng. Nhưng viết được đoạn `synchronized` không đủ để chứng minh một custom child-first loader an toàn; cần kiểm thử tình huống cạnh tranh, class circularity và classloader constraints.

**Phân biệt:** đồng bộ **nạp/định nghĩa lớp** ở đây khác đồng bộ **khởi tạo tĩnh** `<clinit>`. JVM còn có quy tắc riêng để một runtime class được initialized đúng trước active use.

## 9. findClass so với findResource và tài nguyên khác

Override `findClass` để đọc `plugin/Greeter.class` **không tự động** làm các lời gọi sau tìm được mọi tài nguyên nằm trong thư mục riêng:

```java
loader.getResource("plugin/config.properties");
loader.getResources("META-INF/services/example.Service");
```

Các đoạn trên là minh họa. `ClassLoader` có cơ chế riêng gồm `getResource`, `findResource`, `findResources`, các biến thể stream và tương tác với module. Nếu plugin cần cấu hình, ảnh, file metadata hoặc ServiceLoader provider files, phải đảm bảo resource lookup cũng được cấu hình.

Với `URLClassLoader`, nhiều hành vi tìm class và resource đã được cung cấp. Nếu tự viết custom loader, cần tách nhiệm vụ:
- **Class loading:** ánh xạ binary name tới bytecode và định nghĩa class phù hợp.
- **Resource loading:** ánh xạ resource name tới URL/stream hợp lệ theo thứ tự ưu tiên được thiết kế.
- **Service discovery:** xác định loader dùng để tìm provider và giữ SPI dùng chung có cùng định danh runtime.
- **Package/module boundary:** bảo vệ quan hệ package, sealing và cấu hình module đúng.

Không chuyển lỗi resource lookup thành lỗi class loading một cách tùy tiện; hai luồng API có hợp đồng và loại kết quả khác nhau.

## 10. Khi nào nên sử dụng URLClassLoader thay vì tự override?

Nếu bytecode nằm trong **các thư mục class hoặc JAR chuẩn**, `URLClassLoader` thường là lựa chọn đơn giản hơn. Nó đã tích hợp cơ chế tìm lớp từ URL và có xử lý tài nguyên/JAR cần thiết.

Ví dụ minh họa cấu hình:

```java
try (java.net.URLClassLoader loader =
         new java.net.URLClassLoader(
             new java.net.URL[]{classesDir.toUri().toURL()},
             App.class.getClassLoader())) {

    Class<?> plugin = loader.loadClass("plugin.Greeter");
    System.out.println(plugin.getClassLoader() == loader);
}
```

**Đây là snippet, không phải chương trình độc lập**: `classesDir` và `App` phải được cung cấp bởi ứng dụng. Kết quả chỉ là `true` nếu parent không định nghĩa `plugin.Greeter` và loader này thực sự định nghĩa bản plugin; phụ thuộc thực tế vào classpath/URL và delegation.

Khi cần nguồn bytecode tùy biến như dữ liệu sinh trong bộ nhớ hoặc giao thức do ứng dụng quản lý, override `findClass` thường phù hợp, nhưng phải xem xét kiểm soát input, quản lý vòng đời, thực thi code có tin cậy không và kiểm thử concurrent loading.

### Khi đóng một loader, class có tự biến mất không?

`URLClassLoader.close()` giải phóng tài nguyên được quản lý, như file JAR đang mở. Nhưng đóng loader **không** bảo đảm unload ngay mọi class mà nó đã định nghĩa. Class unloading phụ thuộc reachability: còn instance, object `Class<?>`, thread, thread context class loader, callback, static registry hoặc cache giữ loader/class thì JVM có thể vẫn giữ định nghĩa ấy.

Nếu cần “reload plugin”, tạo định nghĩa class mới thường đòi hỏi một **class loader mới**, đồng thời phải giải phóng tham chiếu tới loader cũ khi ngừng plugin. Không cố sử dụng `defineClass` lần nữa cho cùng binary name trong loader cũ để thay bytecode.

## 11. Lỗi và dấu hiệu chẩn đoán

| Lỗi/triệu chứng | Giả thuyết cần kiểm tra | Hướng xử lý |
| --- | --- | --- |
| `ClassNotFoundException` từ `findClass` | Không tìm thấy bytecode ở nguồn local hoặc I/O thất bại | Kiểm tra binary name, root path, classpath, cause và permissions |
| `NoClassDefFoundError` sau khi tìm thấy lớp | Phụ thuộc bắt buộc thiếu, mismatch tên bytecode, hoặc class initialization lỗi trước đó | Đọc thông báo/cause; kiểm tra tên class và dependency thực tế |
| `ClassFormatError` / `VerifyError` | Bytecode không hợp lệ hoặc không phù hợp ràng buộc JVM | Kiểm tra compiler/class file format, tránh sửa bytecode tùy tiện |
| `UnsupportedClassVersionError` | Bytecode được compile cho JVM mới hơn JVM hiện tại | Chạy JVM phù hợp hoặc biên dịch target release tương thích |
| `LinkageError: duplicate class definition` | Cố `defineClass` lại cùng binary name trong một loader | Giữ default `loadClass`, dùng `findLoadedClass` và đồng bộ phù hợp |
| `SecurityException` khi định nghĩa lớp | Vi phạm giới hạn package/nguồn/điều kiện của `defineClass` | Không cố định nghĩa lớp trong namespace JDK; xem API contract |
| Không thấy `findClass` được gọi | Parent đã có class hoặc loader đã ghi nhận class trước đó | Log đường delegation và `clazz.getClassLoader()` |
| Có `findClass` nhưng API host không cast được | Plugin tự định nghĩa bản SPI cùng tên thay vì dùng parent | Đặt interface/DTO chung tại loader chia sẻ |
| `NoSuchMethodError` sau khi load class thành công | Phiên bản API thực tế không khớp bytecode đã biên dịch | Xem class được định nghĩa bởi loader nào và JAR thực tế |
| Resource trong plugin không tìm được | Custom loader chỉ override `findClass`, chưa có tìm resource | Kiểm tra `findResource`/`getResource` và cơ chế plugin |

### Quy trình điều tra cụ thể

1. **Ghi binary name đầy đủ** và loader được yêu cầu: `myLoader.loadClass(name)`.
2. **Quan sát `findClass`**: ghi log tên class, vị trí được kiểm tra, trạng thái file, nguyên nhân IOException khi có. Tránh dump toàn bộ bytecode ra log.
3. **Nếu nạp thành công, in defining loader** bằng `clazz.getClassLoader()`; parent-first có thể làm kết quả khác loader được yêu cầu.
4. **Kiểm tra số lần define**: một loader không nên tự định nghĩa lại cùng binary name ở lần yêu cầu thứ hai.
5. **Xem cause của ngoại lệ**, đặc biệt phân biệt missing bytecode, missing dependency, bytecode invalid và failed initialization.
6. **Kiểm tra runtime JDK**: class file version có phù hợp, môi trường có đầy đủ class/module cần thiết không.
7. **Nếu có nhiều plugin hoặc loader**, so sánh defining loader ở ranh giới SPI để tránh hai bản class cùng tên.
8. **Nếu lỗi xuất hiện sau reload**, kiểm tra các tham chiếu cũ và thiết kế lifecycle; class loader cũ có thể chưa được giải phóng.

Có thể dùng unified logging trên JVM hỗ trợ để xem sự kiện nạp class:

```bash
java -Xlog:class+load=info DirectoryClassLoaderDemo
```

Log này không thay thế việc ghi dấu parent delegation và `findClass` trong custom loader, vì chỉ nhìn đường dẫn class file không cho biết đầy đủ lý do loader cụ thể được chọn.

## 12. Các ngộ nhận thường gặp

**“Override `findClass` nghĩa là ứng dụng chắc chắn ưu tiên class của loader con.”** Sai. Parent-first của `loadClass` vẫn có thể chọn class ở cha trước.

**“`findClass` được gọi mỗi lần `loadClass` được gọi.”** Sai. Class đã được ghi nhận có thể được trả về từ `findLoadedClass`; parent có thể xử lý trước.

**“`findClass` phải tự duyệt cây parent.”** Không phải trách nhiệm mặc định của extension point; thuật toán `loadClass` thông thường đã làm việc đó.

**“Chỉ cần trả byte array là lớp đã được nạp.”** Sai. Phải có một định nghĩa runtime hợp lệ thông qua API thích hợp như `defineClass`.

**“Một loader có thể định nghĩa nhiều version cùng binary name.”** Không. Muốn hai định nghĩa độc lập cùng binary name thì cần defining loader khác nhau, theo giới hạn và quy tắc JVM.

**“`ClassNotFoundException` và `NoClassDefFoundError` luôn cùng một lỗi.”** Sai. Một bên là ngoại lệ checked khi tìm lớp bằng API, bên kia là `LinkageError` có nhiều nguyên nhân, kể cả thiếu phụ thuộc hoặc khởi tạo lỗi.

**“Override `findClass` tự động nạp resource và ServiceLoader provider metadata.”** Sai. Resource lookup có API/luồng riêng.

**“Custom ClassLoader là sandbox bảo mật.”** Sai. Một cách định nghĩa class từ bytecode không tự tạo cơ chế cô lập an toàn đối với code không tin cậy.

## 13. Câu hỏi tự kiểm tra

**Câu 1.** `child.loadClass("api.Service")` thành công nhưng `findClass` của child không được gọi. Điều này có thể hoàn toàn đúng không?

**Đáp án:** Có. Parent hoặc kết quả đã được ghi nhận có thể thỏa mãn yêu cầu trước khi nhánh local `findClass` chạy.

**Câu 2.** Nếu `child.findClass("plugin.Greeter")` đã đọc bytecode thành công thì nó phải làm gì để trả class runtime?

**Đáp án:** Với loader tự định nghĩa lớp theo cách thông thường, gọi `defineClass` bằng binary name tương ứng và bytecode hợp lệ, rồi trả `Class<?>`.

**Câu 3.** Vì sao ở ví dụ `DirectoryLoader`, nạp `plugin.Greeter` lần thứ hai không tăng `localSearches`?

**Đáp án:** Mặc định `loadClass` kiểm tra `findLoadedClass` trước; cùng runtime class đã được ghi nhận nên trả lại thay vì định nghĩa lần thứ hai.

**Câu 4.** Nếu custom loader lấy bytecode từ file `plugin/Greeter.class` nhưng gọi `defineClass("plugin.Other", ...)` thì sao?

**Đáp án:** Tên nhị phân được truyền không khớp định nghĩa; JVM từ chối thay vì đổi tên class, thường biểu hiện lỗi liên kết/tên sai.

**Câu 5.** Loader con có chứa `lib.Json` phiên bản mới, parent đã có `lib.Json` cũ, vì sao `findClass` của con không được gọi?

**Đáp án:** Parent-first delegation chọn định nghĩa của parent trước. Cần thiết kế ranh giới và chính sách delegation phù hợp thay vì chỉ thêm JAR vào loader con.

**Câu 6.** Một plugin nạp được `Greeter.class` nhưng không tìm thấy `plugin/config.properties`. Có nên kết luận `findClass` sai không?

**Đáp án:** Không đủ dữ kiện. `findClass` xử lý class; resource lookup cần `getResource`/`findResource` và cấu hình nguồn resource.

**Câu 7.** Nếu hai thread cùng yêu cầu tên lớp, chỉ ghi override `findClass` có lợi gì?

**Đáp án:** Có thể tiếp tục tận dụng khóa nạp lớp, kiểm tra lớp đã ghi nhận và delegation trong `loadClass` mặc định, giảm nguy cơ tự định nghĩa trùng. Vẫn cần bảo đảm chính triển khai `findClass` và nguồn dữ liệu an toàn khi dùng đồng thời.

## 14. Kết luận và tham khảo

`findClass(String)` là **điểm mở rộng tìm bytecode** để một `ClassLoader` biết định nghĩa class từ nguồn riêng của mình. Trong mô hình mặc định, `loadClass` quyết định **khi nào cần gọi** extension point này, còn `defineClass` thực hiện **định nghĩa runtime** từ bytecode. Việc hiểu rõ ba trách nhiệm giúp tránh định nghĩa trùng, sai loader, xung đột type identity và nhầm lẫn giữa class loading với resource loading.

Tài liệu chính thức:

- Java SE 17 `ClassLoader` API, bao gồm `loadClass`, `findClass`, `findLoadedClass` và `defineClass`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html
- Java SE 17 `URLClassLoader` API: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html
- JVMS 17 §5.3, *Creation of Classes and Interfaces*: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.3
