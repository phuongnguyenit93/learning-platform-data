# Khi nào việc ghi đè loadClass là cần thiết?

## 1. Nguyên tắc lựa chọn

**Chỉ nên override ClassLoader.loadClass khi cần thay đổi chính sách chọn class loader hoặc thứ tự delegation.** Nếu mục tiêu chỉ là **tìm class bytes từ một nguồn mới**, chẳng hạn thư mục, JAR, mạng, bộ nhớ hoặc bytecode được tạo lúc runtime, hãy ưu tiên **override findClass**. Đây là khuyến nghị ngay trong Javadoc ClassLoader của Java.

Lý do: loadClass mặc định đã có đầy đủ logic **findLoadedClass → parent delegation → findClass → resolveClass nếu được yêu cầu**, kèm locking. Ghi đè loadClass toàn bộ chuyển trách nhiệm bảo đảm cache, synchronization, class identity và error handling cho chính bạn.

Override loadClass là lựa chọn có căn cứ khi:
- Một plugin cần **child-first có chọn lọc**, tức bản implementation riêng phải thắng bản cùng tên của parent.
- Runtime bắt buộc **routing class theo namespace/tenant** thay vì nhờ parent thông thường.
- Có chính sách **không cho delegate một số class name tới parent**; phải kiểm tra chính sách ngay tại entry point.
- Delegation đặc biệt qua nhiều loader ngang hàng cần điều phối thứ tự tùy chỉnh.

Nếu những tình huống trên không tồn tại, bạn thường không cần override. **Không nên đổi thuật toán nạp lớp chỉ vì muốn thay vị trí đọc file class.**

## 2. Ba phương thức có vai trò khác nhau

~~~java
public Class<?> loadClass(String name)
        throws ClassNotFoundException;

protected Class<?> loadClass(String name, boolean resolve)
        throws ClassNotFoundException;

protected Class<?> findClass(String name)
        throws ClassNotFoundException;
~~~

Đây là chữ ký API để tham khảo, không phải chương trình Java độc lập.

| Thành phần | Vai trò |
| --- | --- |
| **loadClass(String)** | Entry point public, tương đương loadClass(name, false). |
| **loadClass(String, boolean)** | Entry point protected có thuật toán tìm class và tùy chọn yêu cầu linking. |
| **findClass(String)** | Hook để tìm/định nghĩa class khi thuật toán mặc định cần loader hiện tại tự tìm. |
| **findLoadedClass(String)** | Kiểm tra class mà JVM đã ghi nhận loader là initiating loader. |
| **defineClass** | Định nghĩa runtime class từ bytecode và gắn defining loader. |
| **resolveClass(Class)** | Yêu cầu liên kết class; không khởi tạo static fields. |
| **getClassLoadingLock(String)** | Lock dành cho một tên class khi loading, cần khi tự viết loadClass. |

Vì overload hai tham số là **protected**, code ứng dụng thông thường gọi loader.loadClass(name). Nếu subclass ghi đè protected overload thì lời gọi public loadClass(name) kế thừa từ ClassLoader vẫn đi qua đường xử lý ấy.

**Tên name** thường là binary name, ví dụ **demo.Widget**, không phải đường dẫn file **demo/Widget.class**. Nested class thường có binary name với dấu **$**.

## 3. Đường nạp parent-first mặc định

ClassLoader.loadClass(name, resolve) được JDK mô tả theo thứ tự:

1. Đồng bộ trên đối tượng do **getClassLoadingLock(name)** trả về.
2. Gọi **findLoadedClass(name)** để tái sử dụng Class đã load.
3. Nếu chưa có, nhờ **parent.loadClass(name)**; nếu không có parent, dùng bootstrap loader.
4. Nếu parent không tìm được, gọi **findClass(name)** để loader hiện tại tự định nghĩa class.
5. Nếu **resolve=true**, gọi **resolveClass(c)** trên kết quả.
6. Trả **Class<?>**; không tự tạo instance hoặc chạy static initializer.

~~~text
loadClass(name, resolve)
       |
       v
getClassLoadingLock(name)
       |
       v
findLoadedClass(name)
       |
       +-- found ------------------+
       |                           |
       v                           |
parent.loadClass(name)             |
       |                           |
       +-- found ------------------+
       |                           |
       v                           |
findClass(name)                    |
       |                           |
       +---------------------------+
       |
       v
resolve=true? -> resolveClass(c)
       |
       v
return Class<?> c
~~~

**Override findClass chỉ thay một nút của luồng trên.** Bạn thêm cách lấy bytes mà vẫn kế thừa logic dùng lại Class, thứ tự parent-first, khóa loading và resolve.

Đó là lý do Javadoc khuyến nghị subclass override **findClass**, không override **loadClass** một cách mặc định.

### 3.1 Vì sao parent-first thường hữu ích?

- Các class nền tảng được chia sẻ thay vì bị child tự định nghĩa bản riêng.
- Shared interfaces/DTOs của host và plugin có thể có cùng Class identity.
- Giảm các tình huống ClassCastException nhìn bề ngoài khó hiểu.
- Ít code tự quản lý concurrent loading và tránh define trùng.
- Dễ hiểu hơn khi cần kiểm tra security, module access, package identity và loader constraints.

Parent-first không phải quy tắc bắt buộc cho mọi custom loader, nhưng đây là mặc định tốt khi hệ thống không đòi isolation ưu tiên child.

## 4. Những nhu cầu không cần override loadClass

| Nhu cầu | Điểm mở rộng nên cân nhắc |
| --- | --- |
| Nạp từ thư mục class riêng | findClass hoặc URLClassLoader. |
| Đọc bytes từ database, mạng hoặc memory | findClass + defineClass. |
| Giải mã/giải nén bytes trước khi định nghĩa | Tiền xử lý bytes bên trong findClass. |
| Sinh bytecode runtime theo tên class | Cơ chế defineClass/lookup thích hợp, có thể từ findClass. |
| Đọc tài nguyên *.properties hoặc templates | findResource/getResource; không phải loadClass. |
| Muốn class được initialized | Active use hoặc Class.forName(name, true, loader). |
| Muốn nạp class theo binary name | Gọi loadClass public hiện có. |
| Muốn xem loader nào định nghĩa class | Class.getClassLoader() trên kết quả. |
| Muốn thêm logging class loading | Ưu tiên JVM logging/đo tại hook thích hợp, không đổi thuật toán khi không cần. |

Với những trường hợp này, thay loadClass có thể khiến hệ thống phức tạp hơn mà không có ích lợi thực tế.

## 5. Ví dụ Java 17+ số 1: chỉ cần override findClass

Mục tiêu: loader tự tìm một class trong thư mục **plugin-out** khi parent không nhìn thấy class ấy.

Cấu trúc:

~~~text
project/
├── FinderDemo.java
└── src/
    └── plugin/
        └── Greeter.java
~~~

**src/plugin/Greeter.java**:

~~~java
package plugin;

public class Greeter {
    static {
        System.out.println("Greeter initialized");
    }

    public String message() {
        return "hello";
    }
}
~~~

**FinderDemo.java**:

~~~java
import java.nio.file.Files;
import java.nio.file.Path;
import java.io.IOException;

public class FinderDemo {
    static final class DirectoryLoader extends ClassLoader {
        private final Path root;

        DirectoryLoader(Path root) {
            super(ClassLoader.getPlatformClassLoader());
            this.root = root;
        }

        @Override
        protected Class<?> findClass(String name)
                throws ClassNotFoundException {

            if (!name.startsWith("plugin.")) {
                throw new ClassNotFoundException(name);
            }

            try {
                byte[] bytes = Files.readAllBytes(
                        root.resolve(name.replace('.', '/') + ".class")
                );
                System.out.println("findClass: " + name);
                return defineClass(name, bytes, 0, bytes.length);

            } catch (IOException error) {
                throw new ClassNotFoundException(name, error);
            }
        }
    }

    public static void main(String[] args) throws Exception {
        DirectoryLoader loader =
                new DirectoryLoader(Path.of("plugin-out"));

        Class<?> type = loader.loadClass("plugin.Greeter");

        System.out.println("defined by child = "
                + (type.getClassLoader() == loader));

        System.out.println("before instance");
        Object obj = type.getConstructor().newInstance();
        System.out.println("message = "
                + type.getMethod("message").invoke(obj));
    }
}
~~~

Từ thư mục **project**:

~~~bash
javac -d plugin-out src/plugin/Greeter.java
javac FinderDemo.java
java FinderDemo
~~~

Stdout đã kiểm tra trên JDK 21 (ví dụ tương thích Java 17+):

~~~text
findClass: plugin.Greeter
defined by child = true
before instance
Greeter initialized
message = hello
~~~

**Giải thích:**

1. **DirectoryLoader** không override loadClass; nó thừa hưởng parent-first.
2. **ClassLoader.getPlatformClassLoader()** làm parent trong ví dụ. Parent này không tìm thấy plugin.Greeter nằm ở plugin-out.
3. Thuật toán mặc định gọi **DirectoryLoader.findClass**, đọc bytes rồi defineClass.
4. **type.getClassLoader() == loader** là true vì DirectoryLoader định nghĩa class.
5. Dòng **Greeter initialized** chỉ xuất hiện khi reflection tạo instance; loadClass không tự khởi tạo class.

Nếu đưa **plugin-out** vào đường tìm của parent thích hợp, parent có thể tìm class trước và hook findClass của child sẽ không chạy. Đó là parent-first đúng theo thiết kế, không phải bug.

**An toàn nguồn class:** ví dụ dùng đường dẫn do code kiểm soát. Custom loader production phải kiểm soát binary name, path traversal/symlink, input bytes, package/protection domain, kích thước và nguồn tin cậy. Không dùng ví dụ này làm loader tải dữ liệu tùy ý từ người dùng.

## 6. Trường hợp thực sự cần override: selective child-first

Giả sử:
- Host chứa **demo.message.Version** với method source() trả **parent**.
- Plugin chứa một class **cùng binary name** nhưng source() trả **plugin**.
- Yêu cầu kiến trúc: implementation thuộc **demo.message.*** phải ưu tiên bản plugin.
- Những package khác, bao gồm Java platform và các API dùng chung, vẫn phải giữ parent-first.

Nếu chỉ override findClass, thuật toán mặc định sẽ để parent tìm Version trước. Parent đã có class cùng tên, nên child.findClass không được gọi. **Đây chính là lúc override loadClass có thể cần thiết** để đổi thứ tự trong một namespace đã chọn:

~~~text
Nếu name thuộc demo.message.*
    findLoadedClass
         |
         v
    thử findClass(child) trước
         |
         +-- không tìm được -> fallback parent
         |
         v
    resolve nếu được yêu cầu

Nếu name thuộc namespace khác
    super.loadClass -> parent-first mặc định
~~~

Vì thay thứ tự tìm class, bạn phải giữ cache, locking, resolve flag và xử lý exception đúng.

## 7. Ví dụ Java 17+ số 2: override loadClass có chọn lọc

Cấu trúc thư mục:

~~~text
project/
├── host-src/
│   ├── SelectivePolicyDemo.java
│   └── demo/message/Version.java
└── plugin-src/
    └── demo/message/Version.java
~~~

**host-src/demo/message/Version.java**:

~~~java
package demo.message;

public class Version {
    public String source() {
        return "parent";
    }
}
~~~

**plugin-src/demo/message/Version.java**:

~~~java
package demo.message;

public class Version {
    public String source() {
        return "plugin";
    }
}
~~~

**host-src/SelectivePolicyDemo.java**:

~~~java
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;

public class SelectivePolicyDemo {
    static final class PluginFirstLoader extends URLClassLoader {
        PluginFirstLoader(URL url, ClassLoader parent) {
            super(new URL[]{url}, parent);
        }

        @Override
        protected Class<?> loadClass(String name, boolean resolve)
                throws ClassNotFoundException {

            if (!name.startsWith("demo.message.")) {
                return super.loadClass(name, resolve);
            }

            synchronized (getClassLoadingLock(name)) {
                Class<?> found = findLoadedClass(name);

                if (found == null) {
                    try {
                        found = findClass(name);
                    } catch (ClassNotFoundException missing) {
                        found = super.loadClass(name, false);
                    }
                }

                if (resolve) {
                    resolveClass(found);
                }

                return found;
            }
        }
    }

    static String source(Class<?> clazz) throws Exception {
        return (String) clazz.getMethod("source")
                .invoke(clazz.getConstructor().newInstance());
    }

    public static void main(String[] args) throws Exception {
        ClassLoader parent = ClassLoader.getSystemClassLoader();
        URL pluginUrl = Path.of("plugin-out").toUri().toURL();

        try (URLClassLoader defaultLoader =
                     new URLClassLoader(new URL[]{pluginUrl}, parent);
             PluginFirstLoader selective =
                     new PluginFirstLoader(pluginUrl, parent)) {

            Class<?> parentClass = Class.forName(
                    "demo.message.Version", false, parent);

            Class<?> normal =
                    defaultLoader.loadClass("demo.message.Version");

            Class<?> plugin =
                    selective.loadClass("demo.message.Version");

            System.out.println("default = " + source(normal));
            System.out.println("selective = " + source(plugin));
            System.out.println("default same parent = "
                    + (normal == parentClass));
            System.out.println("selective same parent = "
                    + (plugin == parentClass));
            System.out.println("selective defined by child = "
                    + (plugin.getClassLoader() == selective));
        }
    }
}
~~~

Biên dịch **hai Version.java ở hai output roots khác nhau**, tránh trộn class files:

~~~bash
javac -d host-out host-src/demo/message/Version.java host-src/SelectivePolicyDemo.java
javac -d plugin-out plugin-src/demo/message/Version.java
java -cp host-out SelectivePolicyDemo
~~~

Stdout đã chạy kiểm chứng trên JDK 21:

~~~text
default = parent
selective = plugin
default same parent = true
selective same parent = false
selective defined by child = true
~~~

### 7.1 Vì sao bản default lấy từ parent?

URLClassLoader mặc định hỏi parent trước. Host-out nằm trên application classpath và có **demo.message.Version**, nên defaultLoader nhận Class do application loader định nghĩa; method trả **parent**.

### 7.2 Vì sao bản selective lấy từ plugin?

Với name bắt đầu bằng **demo.message.**, PluginFirstLoader gọi **findClass** trực tiếp trước khi hỏi parent. Nó tìm class trong plugin-out và tự định nghĩa kiểu. Kết quả method trả **plugin**.

Với những package khác, phương thức gọi super.loadClass để duy trì chính sách parent-first. Cách này tránh child-first vô tình lan tới toàn bộ các loại dùng chung.

### 7.3 Hai Class khác nhau dù tên giống

**normal** và **plugin** đều có binary name demo.message.Version, nhưng defining loader khác nhau. Vì class identity dựa trên **binary name + defining loader**, toán tử **normal == plugin** sẽ false.

Không tự ép instance plugin thành host Version chỉ vì tên giống nhau. Với host-plugin boundary, interface/DTO dùng chung thường phải đến từ một defining loader chung.

### 7.4 Vì sao code dùng findLoadedClass?

Khi một loader đã initiate class theo tên, các lần load kế tiếp phải nhất quán. **findLoadedClass** tránh cố gắng định nghĩa lặp lại Class cùng name trong cùng loader, điều có thể dẫn tới **LinkageError**.

### 7.5 Vì sao dùng getClassLoadingLock?

Nếu hai threads đồng thời cùng load demo.message.Version, cả hai có thể thử findClass và defineClass nếu không có locking. **synchronized(getClassLoadingLock(name))** giúp bảo đảm kiểm tra cache và quá trình định nghĩa diễn ra an toàn.

Trong ví dụ, subclass không tự đăng ký parallel capable, nên cách khóa hiện tại đủ cho minh họa. Với hệ thống parallel loading phức tạp, cần đánh giá thêm việc đăng ký parallel-capable trước khi tạo instance.

### 7.6 Vì sao giữ resolveClass khi resolve=true?

Overload protected có cờ **resolve**. Nếu true, custom implementation nên gọi **resolveClass(found)** để giữ hợp đồng linking. **Resolve không đồng nghĩa initialize**; static initializer vẫn theo quy tắc active use riêng.

### 7.7 Vì sao chỉ bắt ClassNotFoundException để fallback?

Nếu child không tìm thấy class, fallback qua parent có ý nghĩa. Nhưng nếu child có bytes sai và defineClass ném **ClassFormatError**, **VerifyError** hoặc **LinkageError**, không nên nuốt mọi Throwable và âm thầm dùng bản parent. Làm vậy che lỗi artifact của plugin và khiến chính sách chọn class không đáng tin.

Trong ví dụ, fallback super.loadClass(name,false) có thể thử lại findClass sau khi parent không tìm thấy; đây là hành vi có thể chấp nhận cho code minh họa. Loader production có thể tối ưu, nhưng vẫn phải giữ đúng cache, locking và bootstrap/parent semantics.

## 8. Những trường hợp override khác có thể hợp lý

### 8.1 Multi-tenant hoặc routing theo namespace

Một runtime có nhiều miền class riêng có thể quyết định rằng **tenant.alpha.impl** do loader Alpha định nghĩa, còn **tenant.beta.impl** do loader Beta. Nếu quyết định routing không thực hiện được dưới parent-first mặc định, custom loadClass có thể điều phối namespace.

Tuy nhiên, khi chỉ muốn mỗi loader tìm nguồn bytes của chính nó và parent không có bản cạnh tranh, override findClass vẫn đơn giản hơn.

### 8.2 Chủ động từ chối một package trước delegation

Nếu policy yêu cầu plugin **không được thấy** package nội bộ của host dù parent có class ấy, điểm kiểm tra phải nằm **trước parent delegation**, nên override loadClass có thể được cân nhắc.

Nhưng **ClassLoader không phải security sandbox hoàn chỉnh**. Từ chối một class name không thay thế process isolation, kiểm soát API khả dụng, module access hoặc cơ chế bảo mật khác. Không tuyên bố rằng chặn một package đủ để chạy code không tin cậy an toàn.

### 8.3 Delegation không thuần cây

Hệ module/plugin phức tạp có thể tìm class qua nhiều loader ngang hàng thay vì một parent duy nhất. Khi override loadClass để làm vậy, nguy cơ **deadlock** cao hơn do có thể hình thành chuỗi loader A chờ B, B chờ A.

Cần kiến trúc thứ tự lookup, caching, locking, parallel loading và giới hạn cycle rõ. Trước khi tự viết từ đầu, đánh giá framework/module system có chính sách phù hợp đã được kiểm chứng.

## 9. Concurrency: đừng phá tính nhất quán của class loading

### 9.1 getClassLoadingLock là công cụ nền tảng

ClassLoader.loadClass mặc định đồng bộ toàn bộ quá trình trên **getClassLoadingLock(name)**.

- Loader không parallel capable thường dùng khóa là object ClassLoader.
- Loader parallel capable có thể dùng khóa riêng theo binary name.
- Mục tiêu là tránh hai thread cùng define class một tên và kiểm soát tương tác với delegate loaders.

Một bản override bỏ toàn bộ synchronization dễ tạo race. Không phải mọi race đều lộ ngay; nó có thể chỉ xuất hiện khi server tải lớn.

### 9.2 Parallel-capable class loaders

Java cung cấp:

~~~java
protected static boolean registerAsParallelCapable();
protected Object getClassLoadingLock(String className);
~~~

Đây là chữ ký API. Khi subclass muốn được coi là parallel capable, việc đăng ký cần được thực hiện đúng quy tắc lúc class loader subclass được initialized và phụ thuộc tính parallel-capable của superclass. Không phải cứ superclass ClassLoader được đăng ký thì mọi subclass tự được đăng ký.

Mô hình delegation không phân cấp cần đặc biệt quan tâm parallel capability để tránh deadlock. Nếu loader đơn giản không có yêu cầu throughput lớn, ưu tiên thuật toán mặc định thay vì tự phức tạp hóa locking.

### 9.3 Không nên thay Class đã nạp trong cùng loader

Sau khi loader đã initiate class với một binary name, findLoadedClass có thể trả lại đúng Class đó. Không thể âm thầm thay toàn bộ Class bằng file bytes phiên bản mới chỉ bằng đổi policy sau đó.

Nếu kiến trúc phải hot-reload implementation, thường tạo **ClassLoader mới cho mỗi deployment** và quản lý việc đóng tài nguyên, hủy task, registry và tham chiếu loader cũ. Redefinition qua instrumentation là vấn đề khác, không phải thêm một class definition cùng name trong cùng loader.

## 10. Kiểm tra contract trước khi đổi thứ tự
Nếu đổi sang child-first, hãy xác định **type nào thực sự đi qua boundary host–plugin** trước khi chọn prefix. Ví dụ, hai implementation riêng có thể dùng thư viện private khác phiên bản; nhưng `api.Task` dùng làm interface host phải được cùng một defining loader cung cấp. Kiểm tra cụ thể:

```java
Class<?> pluginType = selective.loadClass("demo.message.Version");
System.out.println(pluginType.getClassLoader() == selective);
```

Đây là snippet đặt trong phạm vi ví dụ 7. Kết quả xác nhận implementation được định nghĩa bởi child; nó **không** chứng minh mọi DTO/annotation/exception contract đều được chia sẻ. Khi thêm namespace child-first, kiểm tra riêng `sharedApiFromChild == sharedApiFromHost` cho những API thực tế và giữ quy tắc package/platform tương ứng.

## 11. Những sai lầm thiết kế hay gặp

### 11.1 Override public loadClass và return findClass vô điều kiện

Đây là ví dụ **sai**, không sử dụng:

~~~java
@Override
public Class<?> loadClass(String name)
        throws ClassNotFoundException {
    return findClass(name);
}
~~~

Nó bỏ qua findLoadedClass, parent delegation, resolve path và locking. Kết quả có thể không nạp được class Java chuẩn hoặc cố define trùng class đã tồn tại.

### 11.2 Child-first cho mọi package

Nếu plugin-first áp dụng quá rộng, loader có thể tự định nghĩa shared APIs hoặc cố xử lý namespace nền tảng. Hậu quả là cast failure, LinkageError hoặc lỗi namespace protection.

**Filter namespace chặt chẽ.** Prefix **demo.message.** khác **demo.messages**; đừng dùng startsWith("demo.message") nếu không muốn match package cùng tiền tố nhưng khác.

### 11.3 Bắt Throwable rồi fallback parent

Một lỗi VerifyError hoặc ClassFormatError cho thấy bytes/định nghĩa không hợp lệ, không phải chỉ “không tìm thấy class”. Nếu nuốt và fallback tùy tiện, ứng dụng có thể lặng lẽ chọn nhầm phiên bản implementation.

### 11.4 Tự define class nhiều lần

Không bỏ qua **findLoadedClass**. Một defineClass thứ hai cho cùng binary name trong cùng loader có thể ném LinkageError. Đồng thời cần đồng bộ hóa.

### 11.5 Dùng loadClass để thay đổi initialization

**loadClass không tự chạy static initializer.** Cờ resolve là yêu cầu linking, không phải initialization. Nếu muốn chủ động initialize theo API phù hợp, cân nhắc **Class.forName(name, true, loader)**, hiểu rằng nó có thể gây side effects.

### 11.6 Cho rằng resource lookup tự đổi theo class lookup

**getResource/getResources** có chính sách resource riêng. Override loadClass để child-first class không tự làm resources child-first. Nếu plugin cần cùng độ ưu tiên cho template/config, cần thiết kế resource lookup phù hợp.

### 11.7 Quên vòng đời của ClassLoader

ClassLoader mới cho mỗi plugin giúp isolation nhưng không tự làm loader cũ collectible. Long-lived thread với context ClassLoader, ThreadLocal values, callback registry, executor queue hoặc static cache có thể tiếp tục giữ loader cũ. Thiết kế unload/cleanup là một phần của plugin policy.

## 12. Chẩn đoán khi custom loader hoạt động sai

### findClass không bao giờ được gọi

Kiểm tra parent có thể tìm class name hay không. Với parent-first, đây là hành vi bình thường. Xem **returnedClass.getClassLoader()** để biết defining loader.

### ClassCastException dù thông báo có hai tên giống nhau

So sánh **a == b** và **a.getClassLoader()**, **b.getClassLoader()**. String name giống không có nghĩa runtime type giống. Tìm shared API có bị mỗi loader tự define không.

### ClassNotFoundException

Kiểm tra binary name, bytecode source, parent chain và fallback. Nested class có ký tự **$** trong binary name. ClassNotFoundException từ findClass là tín hiệu không tìm được class; nên giữ cause khi I/O lỗi.

### NoClassDefFoundError

Có thể xuất hiện khi JVM cần type cho resolution/initialization mà class không thể sử dụng. Xem cause/stack trace và phân biệt với checked ClassNotFoundException của API lookup.

### LinkageError hoặc loader constraint violation

Kiểm tra định nghĩa trùng trong cùng loader, những shared types bị định nghĩa bởi nhiều loader, chữ ký method giữa host/plugin, package restrictions và module access.

### Deadlock khi concurrent loading

Lấy thread dump, tìm locks trên loader A/B và call chains. Đánh giá getClassLoadingLock, parallel capable và delegation cycles. Không bỏ synchronized chỉ để tránh bị chặn; race có thể gây sai class identity.

### Plugin JAR đã thay nhưng class cũ vẫn chạy

Kiểm tra ClassLoader có đang trả Class đã loaded hay không, source URL, parent-first và loader của deployment. Có thể phải tạo loader mới và unload loader cũ thay vì chỉ thay file trên đĩa.

## 13. Công cụ quan sát Java 17+

Trong môi trường JVM hỗ trợ Unified Logging:

~~~bash
java -Xlog:class+load=info -cp host-out SelectivePolicyDemo
java -Xlog:help
~~~

Logging có thể cho biết class được load và nguồn, nhưng format phụ thuộc JVM. Với class-file bytes:

~~~bash
javap -verbose -classpath host-out demo.message.Version
javap -verbose -classpath plugin-out demo.message.Version
~~~

Hai lệnh javap kiểm tra nội dung artifact, không chứng minh loader runtime nào đã define class. Vì thế kết hợp logs với **Class.getClassLoader()** và **Class object identity** trong chương trình.

Nếu dùng JAR:

~~~bash
jar --list --file plugin.jar
~~~

Một entry tồn tại trong JAR chưa có nghĩa runtime chọn nó. Parent delegation vẫn có thể trả class từ nơi khác.

## 14. Checklist trước khi quyết định override

Trước khi viết custom loadClass, hãy tự hỏi:

1. Parent-first có thực sự sai cho yêu cầu không?
2. Chỉ cần thêm nguồn class bytes thì findClass có đủ chưa?
3. Các package nào được child-first? Filter có chính xác và hẹp không?
4. Shared interface/DTO/JDK classes nào bắt buộc dùng từ parent?
5. Đã kiểm tra findLoadedClass và khóa trên getClassLoadingLock chưa?
6. Resolve flag có được bảo toàn không?
7. Chỉ fallback khi ClassNotFoundException hay đã lỡ nuốt LinkageError?
8. Khi parent cũng có class cùng name, kết quả mong đợi được test chưa?
9. Có hỗ trợ concurrent loading và đánh giá deadlock chưa?
10. Có module/package/security constraints không?
11. Resource lookup và class lookup có yêu cầu policy tương thích không?
12. Reload/unload có cleanup reference loader cũ không?
13. Đã có integration test với nhiều ClassLoaders và host API boundary chưa?

Nếu hầu hết câu trả lời đều là “không cần thay”, giữ ClassLoader mặc định và chỉ override findClass.

## 15. Tự kiểm tra

**1.** Muốn nạp class từ thư mục plugin-out mà parent không thấy nó. Override gì?

**Đáp án:** findClass (hoặc dùng loader dựng sẵn); không cần override loadClass.

**2.** Parent và child cùng có p.Version, cần ưu tiên bản child. Override gì có thể cần?

**Đáp án:** loadClass để thay parent-first thành selective child-first.

**3.** Vì sao phải dùng findLoadedClass trước findClass khi custom loadClass?

**Đáp án:** Tái sử dụng Class đã được JVM ghi nhận cho loader/name, tránh define trùng và bảo toàn type identity.

**4.** resolve=true có nghĩa static initializer phải chạy?

**Đáp án:** Không. Nó yêu cầu resolveClass/linking theo hợp đồng; initialization là bước khác.

**5.** Cùng binary name, cùng bytes nhưng khác defining loaders có phải cùng Class?

**Đáp án:** Không. Defining loader là thành phần của runtime class identity.

**6.** Vì sao shared interface api.Task thường nên do parent định nghĩa?

**Đáp án:** Host và plugin cần cùng một Class api.Task để cast và liên kết method signatures tương thích.

**7.** Có nên bắt Throwable từ child.findClass rồi fallback parent?

**Đáp án:** Không. Lỗi format, verification, linkage phải được phơi bày; ClassNotFoundException mới thể hiện child không tìm thấy.

**8.** Hai threads định nghĩa cùng name nếu không khóa có thể bị gì?

**Đáp án:** Race, duplicate definition, LinkageError hoặc trạng thái không nhất quán.

**9.** Override loadClass có tự làm getResource child-first không?

**Đáp án:** Không. Resource lookup có các API và policy riêng.

**10.** Muốn thay triển khai class đã load trong cùng loader bằng bytes mới có được không?

**Đáp án:** Không thể âm thầm redefine như một class mới cùng name; thường cần loader mới cho deployment mới hoặc cơ chế instrumentation riêng.

## 16. Ghi nhớ

~~~text
Chỉ thay nguồn bytecode?
        |
        +-- Có -> ưu tiên findClass
        |
        +-- Không, cần thay thứ tự/chính sách lookup?
                       |
                       +-- Có thể override loadClass
                                |
                                +-- findLoadedClass
                                +-- getClassLoadingLock
                                +-- package filters rõ ràng
                                +-- fallback có kiểm soát
                                +-- resolveClass khi resolve
                                +-- shared API identity
                                +-- concurrency, lỗi và lifecycle
~~~

**findClass** là điểm mở rộng mặc định cho nguồn bytecode; **loadClass** là điểm can thiệp vào chính sách chọn loader. Override loadClass chỉ khi nhu cầu chính sách thực sự đòi hỏi, và luôn bảo toàn cache, concurrency, resolution, type identity và ranh giới host-plugin.

### Tài liệu tham khảo

- ClassLoader Java SE 17: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html
- ClassLoader Java SE 21: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ClassLoader.html
- JVMS §5.3 Creation and Loading: https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-5.html#jvms-5.3
- JVMS §5.3.4 Loading Constraints: https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-5.html#jvms-5.3.4
- JLS §12.2 Loading of Classes and Interfaces: https://docs.oracle.com/javase/specs/jls/se21/html/jls-12.html#jls-12.2
