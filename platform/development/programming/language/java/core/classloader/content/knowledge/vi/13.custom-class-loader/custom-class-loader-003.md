# Ưu tiên ghi đè findClass khi giữ cơ chế ủy quyền mặc định

## 1. Quy tắc cốt lõi

Khi xây dựng **custom class loader** trong Java, nếu mục tiêu chỉ là tìm và định nghĩa lớp từ một nguồn mới (thư mục, kho bytecode riêng, JAR/nguồn plugin đặc biệt) nhưng **vẫn muốn giữ cơ chế parent-first delegation**, cách thiết kế được tài liệu `ClassLoader` khuyến nghị là:

> **Kế thừa `ClassLoader`, ghi đè `findClass(String name)`, và giữ nguyên `loadClass(String, boolean)` của superclass.**

Lý do: lớp cơ sở đã cung cấp quy trình tìm lớp có cache, ủy quyền parent, khóa đồng bộ và bước link tùy chọn. Bạn chỉ cần viết phần **“khi parent không tìm được, loader của tôi lấy bytecode ở đâu và định nghĩa lớp thế nào?”**. Phần đó chính là hợp đồng của `findClass`.

Sự phân chia trách nhiệm:

| Thành phần | Vai trò chính | Khi viết loader parent-first |
| --- | --- | --- |
| `ClassLoader.loadClass(String)` | API bên ngoài dùng để yêu cầu lớp theo binary name; tương đương `loadClass(name, false)`. | **Giữ nguyên.** |
| `ClassLoader.loadClass(String, boolean)` | Điều phối cache, parent delegation, `findClass`, có thể gọi `resolveClass`. | **Thường giữ nguyên.** |
| `findLoadedClass(String)` | Kiểm tra loader này đã được JVM ghi nhận là initiating loader của lớp cùng tên chưa. | Đã được `loadClass` mặc định gọi. |
| `findClass(String)` | Tìm/định nghĩa lớp từ **nguồn riêng của loader hiện tại** sau khi parent không tìm thấy. | **Đây là chỗ nên override.** |
| `defineClass(...)` | Biến bytecode hợp lệ thành đối tượng `Class<?>`, ràng buộc với defining loader. | Gọi từ `findClass` sau khi đọc đúng bytes. |
| `resolveClass(Class<?>)` | Yêu cầu link class nếu cần. | Để `loadClass` mặc định gọi khi `resolve=true`. |

**Không nhầm:** `findClass` không phải API thông thường để ứng dụng gọi thẳng nhằm bỏ qua parent. Code bên ngoài nên gọi `loader.loadClass("pkg.Type")` (hoặc một API cấp cao phù hợp), để toàn bộ quy trình chuẩn được áp dụng.

## 2. Parent-first delegation: vì sao chỉ override findClass là đủ?

Thuật toán mặc định của `ClassLoader.loadClass(String, boolean)` được mô tả trong Java SE 21:

1. Gọi `findLoadedClass(name)` để tránh tìm/định nghĩa lại lớp đã biết với cùng tên.
2. Nếu chưa có, gọi `loadClass` của parent. Nếu parent là `null`, dùng loader tích hợp bootstrap của JVM.
3. Nếu parent không tìm được, gọi `findClass(name)` của loader hiện tại.
4. Khi tìm được và `resolve == true`, gọi `resolveClass(c)`.
5. Trả đối tượng `Class<?>`; hoặc ném `ClassNotFoundException` khi không có nơi nào tìm thấy.

~~~text
                loader.loadClass(name)
                         |
                         v
              findLoadedClass(name)?
                    /         \
                 có            chưa
                 |               |
                 |         parent.loadClass(name)
                 |            /      \
                 |         có        không
                 |         |           |
                 |         |     findClass(name)
                 |         |       (override)
                 |         |           |
                 +---------+-----------+
                           |
                   trả Class<?> đã tìm
                           |
             resolve=true? -> resolveClass(c)
~~~

Đây là **mô hình logic**; cơ chế thực còn có khóa từ `getClassLoadingLock(name)`, xử lý ngoại lệ và những quy tắc JVM/JDK khác. Điểm quan trọng là `findClass` **được gọi ở bước fallback**, nên bạn không phải tự viết lại toàn bộ thuật toán.

Ví dụ parent là application loader và child là loader của thư mục plugin:

~~~text
Application/System Loader (parent)
  ├── FolderLoaderDemo
  └── java APIs do parent/bootstrap cung cấp
              ^
              |
       ủy quyền trước
              |
Custom FolderClassLoader (child)
  └── source root:
      out/plugin/
         plugin/Greeter.class
~~~

- `child.loadClass("java.lang.String")` nhận lớp cốt lõi qua delegation; không cần `findClass` của child định nghĩa lại.
- `child.loadClass("plugin.Greeter")` hỏi parent trước; nếu parent không có plugin, child mới đọc `out/plugin/plugin/Greeter.class` trong `findClass`.
- Nếu parent **đã** có `plugin.Greeter`, child sẽ nhận bản parent. Việc override `findClass` không đảo ưu tiên sang child.
- Nếu child từng nhận lớp đó rồi, lần gọi sau có thể trả `Class<?>` đã ghi nhận mà không đọc class file thêm lần nữa.

**Defining loader** là loader thực sự định nghĩa class bằng `defineClass`; **initiating loader** có thể chỉ là loader khởi đầu yêu cầu được ủy quyền cho parent. Hai khái niệm không phải lúc nào cũng là cùng một đối tượng.

## 3. Hợp đồng findClass(String): nhận tên gì, trả kết quả gì?

Chữ ký phổ biến:

~~~java
@Override
protected Class<?> findClass(String name)
        throws ClassNotFoundException {
    // Tự tìm bytecode theo binary name, sau đó defineClass.
}
~~~

Đây là khung giải thích, chưa phải phương thức hoàn chỉnh. Những quy tắc quan trọng:

- `name` là **binary name**, ví dụ `plugin.Greeter`, không phải `"plugin/Greeter.class"` hay một đường dẫn file.
- Nếu đọc từ cây file class, ánh xạ tên theo package: `plugin.Greeter` → `plugin/Greeter.class`; đường dẫn được resolve **bên dưới root** mà loader sở hữu.
- Nếu tên **không có trong nguồn riêng**, ném `ClassNotFoundException(name)`, có thể giữ `cause` như `NoSuchFileException`.
- Nếu đọc file gặp `IOException`, có thể bọc vào `ClassNotFoundException` với nguyên nhân gốc để người gọi chẩn đoán; đừng lặng lẽ trả `null` từ overload một tham số này.
- Nếu bytes tìm được, dùng `defineClass(name, bytes, 0, bytes.length)` với **đúng tên và bytes tương ứng**. Không truyền tên của lớp A nhưng bytecode khai báo lớp B.
- Không tự đổi `ClassFormatError`, `VerifyError` hoặc `LinkageError` thành `ClassNotFoundException` bằng một `catch(Throwable)` chung. Những lỗi ấy không phải “không tìm thấy file”.
- `findClass` mặc định của `ClassLoader` chỉ ném `ClassNotFoundException`; override là nơi thực hiện logic tìm nguồn riêng.

### Vì sao gọi defineClass chứ không chỉ trả bytes?

`defineClass` tạo đối tượng `Class<?>` theo hợp đồng JVM. Khi class được định nghĩa thành công, loader này trở thành **defining loader** của class thông thường đó. Danh tính runtime của class/interface phụ thuộc cặp **binary name và defining loader**, không chỉ tên package.

Vì vậy, đừng tự duy trì cache độc lập kiểu `Map<String, Class<?>>` rồi trả nhầm class được định nghĩa bởi loader khác nếu không có lý do rõ ràng. `findLoadedClass` và thuật toán chuẩn vốn đã phối hợp với JVM để tránh nhiều định nghĩa trong cùng loader.

## 4. Ví dụ Java 17+ độc lập: loader đọc bytecode từ thư mục

Ví dụ này có **hai tệp nguồn Java** được biên dịch vào **hai thư mục output riêng**. Class plugin **không nằm trên classpath của host** khi chạy, để chứng minh child thực sự dùng `findClass`.

### Cấu trúc project

~~~text
example/
├── source/
│   ├── plugin/
│   │   └── Greeter.java
│   └── host/
│       └── FolderLoaderDemo.java
└── output/
    ├── plugin/          <-- sau biên dịch
    │   └── plugin/
    │       └── Greeter.class
    └── host/            <-- sau biên dịch
        ├── FolderLoaderDemo.class
        └── FolderLoaderDemo$FolderClassLoader.class
~~~

### File `source/plugin/Greeter.java`

~~~java
package plugin;

public class Greeter {
    static {
        System.out.println("Greeter initialized");
    }

    public static String greet() {
        return "Hello from plugin";
    }
}
~~~

### File `source/host/FolderLoaderDemo.java`

~~~java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.NoSuchFileException;
import java.nio.file.Path;

public class FolderLoaderDemo {
    static final class FolderClassLoader extends ClassLoader {
        private final Path root;

        FolderClassLoader(Path root, ClassLoader parent) {
            super(parent);
            this.root = root.toAbsolutePath().normalize();
        }

        @Override
        protected Class<?> findClass(String binaryName)
                throws ClassNotFoundException {
            Path classFile = root.resolve(
                    binaryName.replace('.', '/') + ".class").normalize();

            if (!classFile.startsWith(root)) {
                throw new ClassNotFoundException(binaryName);
            }

            final byte[] bytes;
            try {
                bytes = Files.readAllBytes(classFile);
            } catch (NoSuchFileException e) {
                throw new ClassNotFoundException(binaryName, e);
            } catch (IOException e) {
                throw new ClassNotFoundException(
                        "Cannot read class: " + binaryName, e);
            }

            System.out.println("findClass: " + binaryName);
            return defineClass(binaryName, bytes, 0, bytes.length);
        }
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException("plugin root");
        }

        ClassLoader parent = FolderLoaderDemo.class.getClassLoader();
        FolderClassLoader loader =
                new FolderClassLoader(Path.of(args[0]), parent);

        Class<?> jdk = loader.loadClass("java.lang.String");
        System.out.println("parent class: " + (jdk == String.class));

        Class<?> plugin = loader.loadClass("plugin.Greeter");
        System.out.println("plugin defined by child: "
                + (plugin.getClassLoader() == loader));

        System.out.println("cached Class: "
                + (plugin == loader.loadClass("plugin.Greeter")));

        System.out.println("method: "
                + plugin.getMethod("greet").invoke(null));

        try {
            loader.loadClass("plugin.Missing");
        } catch (ClassNotFoundException expected) {
            System.out.println("missing: ClassNotFoundException");
        }
    }
}
~~~

Điểm quyết định: **`FolderClassLoader` chỉ override `findClass`**; không override `loadClass`. Mọi đường gọi `loader.loadClass(...)` đều sử dụng cache, parent-first và cơ chế đồng bộ chuẩn có sẵn của `ClassLoader`.

`Path.toAbsolutePath().normalize()` dùng thư mục hiện tại tại lúc tạo loader để xác định root của plugin. `Files.readAllBytes` tiện cho file `.class` nhỏ trong thí nghiệm; với code thực tế phải có giới hạn kích thước và xác thực dữ liệu đầu vào nếu nguồn không tin cậy. Kiểm tra `classFile.startsWith(root)` giúp không đi ra ngoài root sau bước chuẩn hóa đường dẫn cú pháp, nhưng không phải **biện pháp chống symlink/path traversal hoàn chỉnh** cho nguồn không tin cậy; production cần kiểm soát filesystem và security model riêng.

### Chạy trên Linux/macOS

Đứng ở thư mục `example`:

~~~bash
mkdir -p output/plugin output/host

javac --release 17 -d output/plugin source/plugin/Greeter.java
javac --release 17 -d output/host source/host/FolderLoaderDemo.java

java -cp output/host FolderLoaderDemo output/plugin
~~~

Không thêm `output/plugin` vào tham số `-cp` của lệnh `java` cuối. Nếu thêm, parent có thể tự tìm `plugin.Greeter`, khiến `findClass` của child không được gọi.

### Chạy trên Windows PowerShell

Tại thư mục `example`:

~~~powershell
New-Item -ItemType Directory -Force output\plugin, output\host | Out-Null

javac --release 17 -d output\plugin source\plugin\Greeter.java
javac --release 17 -d output\host source\host\FolderLoaderDemo.java

java -cp output\host FolderLoaderDemo output\plugin
~~~

### Stdout chính xác

~~~text
parent class: true
findClass: plugin.Greeter
plugin defined by child: true
cached Class: true
Greeter initialized
method: Hello from plugin
missing: ClassNotFoundException
~~~

Mã đã được biên dịch với `javac --release 17` và chạy bằng Java thực tế; stdout khớp nội dung trên.

### Phân tích đầu ra

1. **`parent class: true`** — lời gọi nạp `java.lang.String` qua child được parent/bootstrap đáp ứng. Không có dòng `findClass: java.lang.String`, nên child không tự định nghĩa bản sao JDK.
2. **`findClass: plugin.Greeter`** — parent không tìm được plugin, nên `loadClass` mặc định mới gọi override `findClass` của child để đọc bytecode từ `output/plugin/plugin/Greeter.class`.
3. **`plugin defined by child: true`** — class được tạo qua `defineClass` của `FolderClassLoader`.
4. **`cached Class: true`** — gọi `loader.loadClass("plugin.Greeter")` lần hai nhận cùng đối tượng `Class<?>`; dòng log `findClass` không xuất hiện thêm lần nữa.
5. **`Greeter initialized`** — `loadClass` không tự chạy static initializer; việc gọi `greet` qua reflection là một active use của phương thức `static`, vì thế JVM khởi tạo class trước lần gọi.
6. **`method: Hello from plugin`** — kết quả thân phương thức `greet`.
7. **`missing: ClassNotFoundException`** — không có `plugin.Missing` ở parent lẫn thư mục child, nên `findClass` ném lỗi tìm lớp và `loadClass` chuyển lỗi ấy cho caller.

Ví dụ dùng reflection để không cần host compile trực tiếp dựa trên kiểu `plugin.Greeter`. Nếu host có `import plugin.Greeter;` rồi biên dịch với plugin trong compile classpath, bạn phải đặc biệt kiểm soát runtime classpath và loader resolution; đó là chủ đề dependency phức tạp hơn. Ở đây trọng tâm là **vị trí đúng để override khi giữ parent-first**.

## 5. Vì sao không nên tự override loadClass khi không cần?

Nếu override `loadClass(String, boolean)`, bạn phải tự đảm bảo nhiều bất biến mà superclass đã xử lý:

| Trách nhiệm dễ bị quên | Nếu override `loadClass` không cẩn thận |
| --- | --- |
| Kiểm tra `findLoadedClass(name)` | Có thể định nghĩa lại cùng binary name → `LinkageError` hoặc các lỗi khác. |
| Hỏi parent trước | Phá parent-first, có thể tạo bản sao API/JDK class không tương thích. |
| Fallback sang `findClass` | Mất cơ chế tìm từ nguồn riêng hoặc nuốt `ClassNotFoundException` sai cách. |
| Sử dụng `getClassLoadingLock(name)` | Hai luồng cùng cố `defineClass`; rủi ro race, lỗi và deadlock. |
| Xử lý `resolve` | Quên `resolveClass(c)` khi `resolve == true`, đổi hợp đồng với caller. |
| Bảo toàn lỗi gốc | Nuốt `LinkageError`/`SecurityException` và báo sai là “không tìm thấy lớp”. |
| Tôn trọng loader cha | Kết quả class được định nghĩa ở loader không như phần còn lại của hệ thống kỳ vọng. |

**Tình huống lỗi minh họa** (không dùng trong chương trình thật):

~~~java
@Override
public Class<?> loadClass(String name) throws ClassNotFoundException {
    byte[] bytes = readBytes(name); // hàm minh họa, chưa tồn tại
    return defineClass(name, bytes, 0, bytes.length);
}
~~~

Mã này **có chủ ý sai và không độc lập chạy được**. Nó bỏ qua cache, parent delegation và khóa class loading; có thể tìm/định nghĩa lặp lớp đã nạp. Nó còn có nguy cơ cố định nghĩa các class cốt lõi hoặc shared interface thay vì nhận từ parent.

**Sửa đúng khi vẫn cần parent-first:** bỏ override `loadClass` không cần thiết, chuyển logic `readBytes(name)` + `defineClass(...)` vào `findClass(name)` giống ví dụ phần 4.

### Parent-first đặc biệt hữu ích với API dùng chung

Giả sử host định nghĩa `api.Plugin` và child định nghĩa `plugins.GreetingPlugin implements api.Plugin`. Khi child hỏi parent trước, nó dùng **cùng một `Class<?>` của `api.Plugin`** mà host đã thấy. Nếu loader con tự định nghĩa một bản `api.Plugin` khác cùng tên, ép đối tượng plugin sang API bên host có thể gặp `ClassCastException` hoặc lỗi liên kết kiểu.

Parent-first giúp thống nhất nền tảng và interface dùng chung; đồng thời vẫn cho child đọc những class riêng từ `findClass`. Tuy nhiên, nếu host parent đã có một thư viện cùng binary name với plugin, parent-first sẽ ưu tiên bản parent. **Nếu thật sự cần cô lập hai phiên bản, phải thiết kế loader policy riêng**, không đơn giản ép mọi trường hợp dùng `findClass`.

## 6. Kiến thức quan trọng về concurrency và cache

`loadClass(String, boolean)` mặc định đồng bộ trong giai đoạn nạp bằng monitor trả từ `getClassLoadingLock(name)`. Class loader đăng ký **parallel capable** có thể có khóa riêng theo tên, nhưng các subclass có yêu cầu đăng ký riêng phù hợp; đừng suy luận rằng tất cả loader con mặc nhiên parallel capable chỉ vì superclass `ClassLoader` đã được đăng ký.

Trong ví dụ `FolderClassLoader`, không override `loadClass` nên logic khóa cơ sở vẫn hoạt động. `findClass` vẫn cần **không tự tạo những thread/race không kiểm soát** hoặc ghi bytecode đồng thời vào thư mục một cách nguy hiểm.

Một lần `defineClass` thành công ràng buộc lớp với defining loader. Định nghĩa lại **cùng tên trong cùng loader** có thể gây `LinkageError`, kể cả bạn đã sửa bytes trên ổ đĩa. Muốn tải version mới trong một class namespace độc lập, thường tạo **loader mới** và quản lý vòng đời các đối tượng/class cũ. Việc sửa file `.class` tại chỗ không khiến class đã được nạp tự cập nhật.

Cần phân biệt:

- `findLoadedClass` là truy vấn JVM về class loader này đã được ghi nhận nạp class theo tên hay chưa; không phải một `Map` bạn được phép sửa trực tiếp.
- `defineClass` đưa bytecode thành class runtime và có thể ném `LinkageError`/`ClassFormatError` nếu không hợp lệ.
- `resolveClass` là bước linking theo yêu cầu của overload có `resolve=true`; không phải lệnh chạy static initializer.
- `loadClass(name)` tương đương overload `resolve=false`, nhưng JVM vẫn có quyền link các class vào thời điểm hợp lệ theo đặc tả.

## 7. Exception handling trong findClass

Với loader đọc file, câu hỏi khó là “khi không tìm được hoặc bytecode lỗi, nên ném gì?”:

| Tình huống | Kết quả hợp lý | Tại sao? |
| --- | --- | --- |
| Không có `plugin/Missing.class` | `ClassNotFoundException(name)` | Loader không thể tìm lớp theo binary name. |
| Đọc file gặp `NoSuchFileException` | Bọc thành `ClassNotFoundException(name, cause)` | Giữ nguyên nhân filesystem. |
| File tồn tại nhưng không đọc được vì lỗi I/O | `ClassNotFoundException(..., cause)` trong loader file minh họa | Caller biết lỗi tra cứu kèm nguyên nhân gốc; production có thể cần chính sách rõ hơn. |
| Bytecode hỏng | `ClassFormatError` | Không biến nhầm thành thiếu file. |
| Tên được truyền không khớp tên định nghĩa trong bytes | `NoClassDefFoundError` có thể phát sinh từ `defineClass` | “Wrong name” là lỗi khác với tìm không thấy file. |
| Cố define lại tên đã có trong cùng loader | `LinkageError` | Trùng định nghĩa class. |
| Cố định nghĩa tên bắt đầu `java.` từ loader ứng dụng | `SecurityException` | JVM bảo vệ namespace nền tảng theo hợp đồng `defineClass`. |
| Lớp có dependency khác bị thiếu khi được resolve | Có thể `NoClassDefFoundError` tại thời điểm JVM cần lớp đó | Không nhất thiết xảy ra ngay khi `findClass` trả về. |
| Static initializer của plugin ném lỗi | Có thể `ExceptionInInitializerError` khi class được initialize | Đây không phải nhiệm vụ `findClass`. |

Đừng ghi đè tất cả lỗi bằng `catch (Throwable e) { throw new ClassNotFoundException(name); }`. Cách đó làm mất cause và che giấu lỗi runtime quan trọng. Trong ví dụ, chỉ các lỗi **I/O** khi đọc bytes được bọc; lỗi Java linkage/format do JVM xác định được giữ nguyên.

## 8. Nếu muốn nạp resource thì sao?

`findClass(String)` **chỉ xử lý class**. Nó không tự khiến loader tìm được resource khác như `plugin/config.yml`:

~~~java
Class<?> pluginType = loader.loadClass("plugin.Greeter");
URL resource = loader.getResource("plugin/config.yml");
~~~

Đoạn trên là minh họa, giả định có loader và resource. `getResource` mặc định cũng có cơ chế parent-first riêng; để tìm resource từ thư mục plugin, bạn có thể cần override `findResource(String name)` hoặc chọn loader có sẵn như `URLClassLoader`. Phân biệt rõ:

- `findClass("plugin.Greeter")`: binary name bằng dấu `.`, nhận `Class<?>`.
- `findResource("plugin/config.yml")`: resource name bằng dấu `/`, thường trả `URL` hoặc `null`.
- `findResources(String name)`: có thể trả nhiều URL phù hợp khi cần nhiều resource cùng tên, tùy implementation.

Chỉ override `findClass` không tạo cơ chế resource search tùy biến tự động; tuy nhiên lớp Java được nạp vẫn có thể lấy những resource do parent cung cấp theo khả năng của loader. Khi nhiệm vụ thực sự là tải cả class lẫn resource từ một **JAR hoặc thư mục**, `URLClassLoader` thường ít code và ít rủi ro hơn việc tự viết loader file.

## 9. Khi nào thực sự cần override loadClass?

Lý do hợp lý là **muốn thay đổi chính sách tìm lớp**, chứ không chỉ thay nguồn bytecode. Ví dụ:

- **Child-first** cho một namespace plugin nhất định: tìm plugin version trước parent, nhưng tiếp tục dùng parent cho JDK/shared API.
- **Reverse delegation hoặc multi-parent** theo thiết kế container/module phức tạp, nơi parent-first đơn giản không đủ.
- **Chặn/lọc các tên binary name** theo quy tắc hệ thống, nhưng vẫn phải xem xét hậu quả với liên kết kiểu và các API nền tảng.
- **Tùy biến nạp song song/đồng bộ** khi có kiến trúc loader thực sự đặc biệt và đội ngũ hiểu sâu hợp đồng của `ClassLoader`.

Khi đó, phải thiết kế đủ thuật toán: `synchronized(getClassLoadingLock(name))` hoặc chiến lược khóa tương đương, `findLoadedClass(name)`, thứ tự lookup, fallback parent, `resolveClass` nếu cần, class identity, shared interfaces, failure handling và deadlock avoidance. Class loader có quan hệ ủy quyền **không phân cấp thuần túy** cần đặc biệt cân nhắc **parallel capable** theo tài liệu.

Một chính sách child-first **không có nghĩa tự động** mọi parent nhìn được dependency của child. Dùng loader tường minh hoặc SPI/interface chung để giao tiếp giữa các tầng. Đừng vô tình override `loadClass` chỉ vì bạn muốn đọc bytes từ một thư mục mới: đó chính xác là công việc của `findClass`.

## 10. Các lỗi dễ mắc và cách khắc phục

**Lỗi 1: Override cả loadClass lẫn findClass dù chỉ thay thư mục nguồn.** Không cần. Đưa logic đọc bytes vào `findClass`; giữ delegation/caching đồng bộ mặc định.

**Lỗi 2: Trong findClass gọi super.findClass(name) và kỳ vọng parent search.** `super.findClass` mặc định ném `ClassNotFoundException`, không phải thuật toán parent lookup. Parent đã được thử bởi `loadClass` trước khi override `findClass` được gọi.

**Lỗi 3: Truyền đường dẫn `plugin/Greeter.class` cho loadClass.** API cần binary name `plugin.Greeter`. Đổi tên thành đường dẫn file **bên trong findClass**, không ở API caller.

**Lỗi 4: Class plugin vô tình nằm trên application classpath.** Parent-first sẽ tìm được plugin trước; `findClass` của child không chạy. Test custom loader nên để plugin trong thư mục riêng và chỉ truyền classpath host khi chạy.

**Lỗi 5: Đọc class bytes rồi gọi defineClass với sai tên.** Có thể gây `NoClassDefFoundError` dạng wrong name. Tên binary phải khớp `this_class` bên trong class file.

**Lỗi 6: Đọc toàn bộ filesystem không giới hạn.** `Files.readAllBytes` đơn giản nhưng không phù hợp với nguồn file quá lớn hoặc không tin cậy. Giới hạn kích thước, kiểm soát symlink và chỉ dùng bytecode từ nguồn đáng tin cậy.

**Lỗi 7: Tưởng đóng file hoặc xóa tệp `.class` làm JVM unload lớp.** Một class đã được định nghĩa có vòng đời riêng; khi cần cập nhật, tạo loader mới và quản lý tham chiếu cũ.

**Lỗi 8: Kỳ vọng override findClass tự xử lý tài nguyên và native library.** Các hook liên quan là `findResource/findResources` và `findLibrary`; chọn API đúng nhu cầu.

**Lỗi 9: Biên dịch host dựa trên class plugin rồi bỏ classpath runtime mà không nghĩ về resolution.** Lớp do parent định nghĩa có thể không tìm thấy dependency chỉ thuộc loader con. Dùng reflection hoặc interface chung được parent định nghĩa để thiết kế ranh giới plugin.

**Lỗi 10: Bắt `Exception` hay `Throwable` rồi báo mọi lỗi là ClassNotFoundException.** Hãy giữ các lỗi linkage/format/security đúng loại và cause để chẩn đoán.

## 11. Checklist ra quyết định

Trước khi code custom loader, hãy trả lời tuần tự:

1. Tôi chỉ cần **đổi nguồn tìm bytes**, hay phải **đổi thứ tự ủy quyền**? Nếu chỉ đổi nguồn, override `findClass`.
2. Root class file đã đúng chưa? `plugin.Greeter` nằm ở `root/plugin/Greeter.class`, không phải `root/Greeter.class`.
3. Parent nào cần chia sẻ JDK và API chung? Có lớp cùng tên trên classpath parent không?
4. Caller gọi `loadClass(binaryName)`, không gọi thẳng `findClass` để bỏ delegation?
5. `findClass` có ánh xạ tên sang path đúng, kiểm soát file nguồn và trả `Class<?>` từ `defineClass`?
6. Lỗi file vắng mặt/I/O có giữ `ClassNotFoundException` cùng nguyên nhân? Linkage/format có được giữ đúng loại?
7. Các lời gọi nhiều luồng có dùng nguyên thuật toán đồng bộ của superclass? Có nguy cơ tự định nghĩa trùng?
8. Loader có cần resource/JAR riêng không? Có nên dùng `URLClassLoader` thay vì tự viết `findClass`?
9. Có cần class mới ở loader mới cho hot reload không? Class đã load không thể đơn giản “define lại” vào cùng loader.
10. Đã kiểm tra `getClassLoader()`, stdout, classpath compile/runtime và lỗi `ClassNotFoundException` của một class không tồn tại chưa?

### Câu hỏi tự kiểm tra

**Câu 1.** Vì sao `findClass("plugin.Greeter")` không in log khi parent đã có `plugin.Greeter`?

**Đáp:** Vì `loadClass` theo parent-first hỏi parent trước. Nếu parent trả một lớp, nó không gọi `findClass` child.

**Câu 2.** Tại sao sau hai lần `loader.loadClass("plugin.Greeter")` chỉ thấy một log `findClass`?

**Đáp:** Loader/JVM đã ghi nhận cùng lớp; `findLoadedClass` giúp lời gọi sau trả `Class<?>` có sẵn, không define lại.

**Câu 3.** Muốn tải hai version có cùng binary name trong hai plugin độc lập, có nên define cả hai trong cùng loader?

**Đáp:** Không. Cần **hai defining loader riêng** và thiết kế API giao tiếp phù hợp, tránh cast nhầm qua hai namespace.

**Câu 4.** Muốn thêm class từ JAR nhưng không cần policy đặc biệt, bắt buộc tự viết findClass từ `JarFile` không?

**Đáp:** Không. `URLClassLoader` đã hỗ trợ thư mục và JAR; custom `findClass` thích hợp khi cần kiểm soát nguồn bytecode đặc biệt, còn parent-first vẫn được giữ.

## Tài liệu chuẩn

- [Java SE 21: ClassLoader.loadClass(String, boolean)](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ClassLoader.html#loadClass(java.lang.String,boolean)): thuật toán mặc định và khuyến nghị override `findClass`.
- [Java SE 21: ClassLoader.findClass(String)](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ClassLoader.html#findClass(java.lang.String)): contract tìm class khi parent không tìm được.
- [Java SE 21: ClassLoader.defineClass](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ClassLoader.html#defineClass(java.lang.String,byte%5B%5D,int,int)): định nghĩa lớp từ bytes, tên nhị phân và lỗi.
- [Java SE 21: URLClassLoader](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/URLClassLoader.html): giải pháp có sẵn cho thư mục/JAR.
- [JVMS Java SE 21 §5.3: Creation and Loading](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-5.html#jvms-5.3): defining loader, initiating loader và danh tính lớp.
