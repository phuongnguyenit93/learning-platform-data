# ClassNotFoundException: yêu cầu tìm lớp tường minh không thành công

`java.lang.ClassNotFoundException` (thường viết tắt **CNFE**) là **checked exception** báo rằng một thao tác **chủ động yêu cầu tìm/nạp class theo tên** không thể tìm được định nghĩa phù hợp qua class loader được sử dụng. Những điểm vào tiêu biểu là `Class.forName(...)`, `ClassLoader.loadClass(...)` và các thư viện/framework gọi những API ấy để tải driver, plugin, implementation hoặc lớp cấu hình bằng tên.

Ví dụ một ứng dụng nhận `"com.example.plugins.Reporter"` từ file cấu hình rồi gọi:

~~~java
Class<?> type = Class.forName("com.example.plugins.Reporter");
~~~

Nếu loader được chọn không tìm ra class này, phương thức ném `ClassNotFoundException`. Điều đó **không chứng minh file `Reporter.class` không tồn tại trên máy**: class có thể nằm trong một JAR khác, một module chưa được resolve, thư mục chưa đặt đúng classpath hoặc một child loader mà caller không sử dụng.

**Ý chính của bài:**
- CNFE phản ánh **yêu cầu tìm class tường minh bị thất bại với loader và tên được yêu cầu**.
- `Class.forName(String)`, `Class.forName(String, boolean, ClassLoader)` và `loader.loadClass(String)` có quy tắc chọn loader/initialization khác nhau.
- Tên binary, đường dẫn classpath/module path và phạm vi nhìn thấy của loader phải đồng thời đúng.
- `NoClassDefFoundError` là lỗi JVM/linkage khác, thường xuất hiện khi một class mà bytecode cần tới không thể định nghĩa/khởi tạo; không nên coi hai tình huống là cùng một loại lỗi.
- Cách debug đúng là xác định **tên class được yêu cầu, loader nào tìm, artifact nào chứa bytecode và bước nào thực sự thất bại**.

## 1. Định nghĩa trong hệ thống ngoại lệ Java

Sơ đồ kế thừa:

~~~text
java.lang.Object
  └── java.lang.Throwable
       └── java.lang.Exception
            └── java.lang.ReflectiveOperationException
                 └── java.lang.ClassNotFoundException
~~~

Vì CNFE là checked exception, lời gọi có khai báo `throws ClassNotFoundException` phải được **catch** hoặc khai báo tiếp trong chữ ký method.

~~~java
public static Class<?> locate(String binaryName)
        throws ClassNotFoundException {
    return Class.forName(binaryName);
}
~~~

Đây là method minh họa. Caller phải xử lý ngoại lệ hoặc tiếp tục `throws`.

Ví dụ xử lý có ngữ cảnh:

~~~java
try {
    Class<?> type = Class.forName(configuredClassName);
    // Tiếp tục kiểm tra contract và khởi tạo.
} catch (ClassNotFoundException ex) {
    throw new IllegalStateException(
            "Configured provider was not found: " + configuredClassName,
            ex);
}
~~~

Đây là đoạn minh họa với `configuredClassName` đã có, không phải chương trình độc lập. Việc bọc trong `IllegalStateException` có thể thích hợp khi **thiếu plugin là lỗi cấu hình nghiêm trọng**; nếu plugin tùy chọn thì nên chọn chính sách fallback có chủ đích thay vì lúc nào cũng fail toàn bộ host.

### Tên class trong exception

Thông báo hoặc stack trace thường chứa binary name được yêu cầu, ví dụ:

~~~text
java.lang.ClassNotFoundException: com.example.plugins.Reporter
~~~

Thông báo thực tế có thể khác tùy loader/JVM; đừng dựa vào việc chuỗi lỗi nhất thiết đúng một mẫu ký tự. Điều đáng tin hơn là **loại exception**, tên đã truyền vào API, cause chain, và loader đang được dùng.

## 2. Vì sao “class tồn tại” nhưng vẫn nhận CNFE?

Một câu trả lời chính xác luôn cần ba phần:

~~~text
Lời gọi đang thực hiện:
  tên nhị phân nào?
              |
              v
  ClassLoader nào nhận yêu cầu?
              |
              v
  Loader ấy tìm ở nguồn nào?
              |
              v
  Class có sẵn/được tìm thấy theo quy tắc đó không?
       /                             \
     Có                              Không
     |                                 |
 Class<?> hoặc                  ClassNotFoundException
 lỗi ở bước khác                (tùy API)
~~~

Nếu `out/plugins/com/acme/Feature.class` tồn tại nhưng ứng dụng chỉ chạy với classpath `out/app`, application loader **không tự quét thêm** `out/plugins`. Tương tự, một JAR plugin có thể được một `URLClassLoader` con nhìn thấy, nhưng `Class.forName(String)` gọi từ host vẫn chọn loader của **caller** và không tự đoán child loader.

### Bốn điều kiện phổ biến

1. **Đúng tên:** `com.acme.Feature` chứ không phải `com/acme/Feature.class`.
2. **Đúng nơi:** root của classpath hoặc URL phải là thư mục/JAR chứa đường dẫn package đúng.
3. **Đúng loader:** loader thực thi lookup thực sự phải thấy nguồn đó, trực tiếp hoặc qua delegation có hiệu lực.
4. **Đúng cơ chế khởi chạy:** application classpath, executable JAR và JPMS module path không phải các cấu hình đồng nghĩa.

Nhiều lỗi CNFE là lỗi **configuration/loader visibility**, không phải thiếu file ở cấp hệ điều hành.

## 3. Những API nào có thể ném ClassNotFoundException?

### 3.1. `Class.forName(String)`

~~~java
Class<?> c = Class.forName("com.acme.Feature");
~~~

Overload một tham số sử dụng **defining class loader của class gọi API** để tìm class và mặc định yêu cầu initialization. Nó **không đơn giản lấy TCCL** mà thread đang mang.

Một class trong host có thể gọi thành công `Class.forName("com.acme.HostHelper")` nhưng thất bại với `"com.acme.plugin.Feature"` nếu Feature chỉ có trong child plugin loader.

### 3.2. `Class.forName(String, boolean, ClassLoader)`

~~~java
Class<?> c = Class.forName(
        "com.acme.plugin.Feature",
        false,
        pluginLoader);
~~~

Đây là mảnh minh họa khi `pluginLoader` đã được cấu hình.

- `name`: tên nhị phân của class/interface, hoặc dạng tên mảng theo quy tắc API.
- `initialize=false`: không yêu cầu chạy initializer của class.
- `initialize=true`: yêu cầu khởi tạo class nếu chưa initialized; có thể sinh exception/error ở giai đoạn initialization **khác với CNFE**.
- `loader`: class loader **chỉ định tường minh**; đây là cách đáng tin khi plugin class không nằm trong loader của host.
- Theo API, truyền `null` cho loader có ý nghĩa dùng bootstrap loader, không phải “tìm trên mọi classpath”.

Nếu class tìm được nhưng initializer ném exception, kết quả có thể là `ExceptionInInitializerError` hoặc một `Error` liên quan, **không phải CNFE** chỉ vì class không chạy được.

### 3.3. `ClassLoader.loadClass(String)`

~~~java
Class<?> c = pluginLoader.loadClass("com.acme.plugin.Feature");
~~~

`loadClass` mặc định **không yêu cầu initialization**; nó tìm/nạp kiểu theo chính sách delegation của loader. Nếu không tìm thấy, thường ném CNFE. Khi class tìm được nhưng bytes không hợp lệ hoặc linking/access không hợp lệ, các `LinkageError`/`SecurityException` khác có thể xuất hiện.

Với loader mặc định parent-first:

~~~text
child.loadClass(name)
      |
      v
findLoadedClass(name)
      |
      +-- chưa nạp -> parent.loadClass(name)
                           |
                           +-- parent tìm được -> trả Class của parent
                           |
                           +-- không -> child.findClass(name)
                                            |
                                            +-- có -> define Class
                                            |
                                            +-- không -> CNFE
~~~

**Gọi qua child không đồng nghĩa child sẽ là defining loader.** Nếu parent trả được class, `c.getClassLoader()` vẫn là parent. Khi debug, phân biệt initiating loader và defining loader.

### 3.4. Reflection và thư viện/framework

`ClassNotFoundException` có thể xuất hiện khi:

- Hệ thống plugin đọc tên implementation từ cấu hình và gọi `Class.forName`.
- Code tạo `URLClassLoader` rồi gọi `loadClass` với class name đã cấu hình.
- Framework đọc metadata chứa binary names và gọi reflection để tìm class.
- Hệ thống JDBC đời cũ gọi `Class.forName("...Driver")` để khởi tạo class driver; JDBC 4+ còn có cơ chế service-provider discovery nên **không phải driver nào cũng cần gọi `Class.forName` thủ công**.
- Một framework hay thư viện che CNFE bên dưới ngoại lệ cao hơn, ví dụ provider discovery failure hoặc wrapper exception.

**Không đánh đồng:** `new SomeClass()` trong mã đã biên dịch không phải một yêu cầu tên-string giống `Class.forName`. Khi dependency cho bytecode tham chiếu bị mất, JVM thường báo `NoClassDefFoundError`/linkage failure thay vì checked CNFE trực tiếp tại source Java.

## 4. Binary name, package path và classpath root

Giả sử source:

~~~java
package com.acme.plugin;

public final class Reporter {
}
~~~

Sau khi compile, file thường ở:

~~~text
out/plugin/
  com/
    acme/
      plugin/
        Reporter.class
~~~

Tên API `loadClass`/`forName` là:

~~~java
"com.acme.plugin.Reporter"
~~~

Không phải:

~~~text
com/acme/plugin/Reporter.class
com.acme.plugin.Reporter.class
/out/plugin/com/acme/plugin/Reporter.class
~~~

Những chuỗi sau là **đường dẫn** hoặc tên file, không phải binary class name mà các overload thông thường mong đợi.

### Inner/nested classes

Một static nested class:

~~~java
package com.acme;

public final class Outer {
    public static final class Inner {
    }
}
~~~

Tên nhị phân của nested class là:

~~~text
com.acme.Outer$Inner
~~~

Dùng `Class.forName("com.acme.Outer$Inner")`, **không** dùng `"com.acme.Outer.Inner"`. Trong code Java thông thường có thể tham chiếu `Outer.Inner.class`, nhưng string binary name và cú pháp source type name khác nhau.

### Mảng và primitive types

`Class.forName` có quy tắc riêng cho array class names, ví dụ:

~~~java
Class<?> a = Class.forName("[Ljava.lang.String;");
System.out.println(a == String[].class);
~~~

Với JDK thông thường, output là `true`. Còn:

~~~java
Class.forName("int");
~~~

không phải cách lấy `int.class`; lời gọi ấy ném `ClassNotFoundException`. Dùng trực tiếp `int.class` cho primitive types.

**Khi debug CNFE, luôn log chuỗi đầu vào chính xác**. Một dấu `/`, `.class`, tên package sai chữ hoa/thường hoặc nhầm `$` với dấu `.` có thể là toàn bộ nguyên nhân.

## 5. Ví dụ Java 17+ hoàn chỉnh: host không tìm class, loader plugin tìm được

Ta tạo:

- Một class `com.acme.plugin.Greeting` trong **thư mục plugin riêng**.
- Một host class `ClassNotFoundLab` được compile/chạy **không đưa plugin vào application classpath**.
- Một `URLClassLoader` được host tạo, trỏ đúng vào thư mục plugin.
- Cùng một binary name thất bại khi host dùng loader mặc định, nhưng thành công khi chọn plugin loader tường minh.
- Một static initializer để minh họa khác biệt giữa **load** và **initialize**.

### 5.1. Cấu trúc project

~~~text
project/
  src/
    plugin/
      com/
        acme/
          plugin/
            Greeting.java
    app/
      ClassNotFoundLab.java
  out/
    plugin/              (sinh bởi javac)
    app/                 (sinh bởi javac)
~~~

**Không** đặt `out/plugin` vào application classpath khi chạy host; đó là điểm then chốt của thí nghiệm.

### 5.2. File `src/plugin/com/acme/plugin/Greeting.java`

~~~java
package com.acme.plugin;

public final class Greeting {
    static {
        System.out.println("plugin initialized");
    }

    public static String message() {
        return "hello from plugin";
    }
}
~~~

Initializer chỉ in khi class thực sự initialized. `loadClass` không bắt buộc initializer chạy; `Class.forName(name, true, loader)` yêu cầu điều đó.

### 5.3. File `src/app/ClassNotFoundLab.java`

~~~java
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;

public final class ClassNotFoundLab {
    private static final String NAME =
            "com.acme.plugin.Greeting";

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                    "Usage: ClassNotFoundLab <plugin-directory-or-jar>");
        }

        // A. Host không thấy out/plugin trên application classpath.
        try {
            Class.forName(NAME);
            System.out.println("default Class.forName: found");
        } catch (ClassNotFoundException ex) {
            System.out.println(
                    "default Class.forName: ClassNotFoundException");
        }

        try {
            ClassLoader.getSystemClassLoader().loadClass(NAME);
            System.out.println("system loadClass: found");
        } catch (ClassNotFoundException ex) {
            System.out.println(
                    "system loadClass: ClassNotFoundException");
        }

        // B. Plugin loader có URL root tới out/plugin.
        URL root = Path.of(args[0]).toAbsolutePath()
                .toUri().toURL();

        ClassLoader parent = ClassNotFoundLab.class.getClassLoader();

        try (URLClassLoader pluginLoader =
                new URLClassLoader("plugin", new URL[] {root}, parent)) {

            Class<?> type = pluginLoader.loadClass(NAME);

            System.out.println(
                    "explicit loadClass: " + type.getName());
            System.out.println("defined by plugin loader: "
                    + (type.getClassLoader() == pluginLoader));

            Class<?> same = Class.forName(
                    NAME, false, pluginLoader);
            System.out.println(
                    "same Class object: " + (same == type));

            System.out.println("before initialization");
            Class.forName(NAME, true, pluginLoader);

            Object answer = type.getMethod("message").invoke(null);
            System.out.println("invoke: " + answer);

            try {
                pluginLoader.loadClass("com.acme.plugin.Missing");
                System.out.println("missing name: found");
            } catch (ClassNotFoundException ex) {
                System.out.println(
                        "missing name: ClassNotFoundException");
            }

            try {
                pluginLoader.loadClass(
                        "com/acme/plugin/Greeting");
                System.out.println("slash name: found");
            } catch (ClassNotFoundException ex) {
                System.out.println(
                        "slash name: ClassNotFoundException");
            }
        }

        try {
            Class.forName("int");
            System.out.println("primitive name: found");
        } catch (ClassNotFoundException ex) {
            System.out.println(
                    "primitive name: ClassNotFoundException");
        }
    }
}
~~~

Tại sao không import `Greeting` vào host? Nếu host compile dựa vào class đó rồi đưa plugin output vào application classpath, thí nghiệm có thể không còn biểu diễn **explicit lookup từ host không thấy plugin**. Plugin được gọi qua reflection chỉ sau khi host tạo đúng loader.

### 5.4. Compile và chạy

Các lệnh **Bash trên Linux/macOS** (hoặc môi trường Bash tương thích) từ thư mục `project`:

~~~bash
mkdir -p out/plugin out/app

javac -d out/plugin \
    src/plugin/com/acme/plugin/Greeting.java

javac -d out/app src/app/ClassNotFoundLab.java

java -cp out/app ClassNotFoundLab out/plugin
~~~

Đối với Windows PowerShell, tạo thư mục bằng `New-Item -ItemType Directory -Force` và chạy các lệnh `javac`/`java` tương đương. Ở đây classpath chỉ có **một** mục `out/app`, nên không cần dấu phân cách platform-specific giữa nhiều entries.

### 5.5. Stdout chính xác của ví dụ

~~~text
default Class.forName: ClassNotFoundException
system loadClass: ClassNotFoundException
explicit loadClass: com.acme.plugin.Greeting
defined by plugin loader: true
same Class object: true
before initialization
plugin initialized
invoke: hello from plugin
missing name: ClassNotFoundException
slash name: ClassNotFoundException
primitive name: ClassNotFoundException
~~~

**Giải thích:**

1. Hai lời gọi đầu sử dụng loader của host/system application, không thấy `out/plugin`, nên CNFE.
2. `URLClassLoader` được cung cấp URL trỏ đến đúng root `out/plugin/`. Khi parent không tìm class, child tìm `com/acme/plugin/Greeting.class` từ directory.
3. `getClassLoader() == pluginLoader` là `true`, chứng tỏ child thực sự là defining loader của class plugin.
4. `loadClass` đã trả `Class<?>` nhưng **không khởi tạo** class, do đó dòng `plugin initialized` chưa xuất hiện trước `before initialization`.
5. `Class.forName(NAME, false, pluginLoader)` trả lại cùng runtime class; `true` không chứng minh class đã initialized.
6. `Class.forName(NAME, true, pluginLoader)` kích hoạt initialization và in đúng một dòng `plugin initialized`.
7. Method static `message` chạy và trả `hello from plugin`.
8. `com.acme.plugin.Missing` không tồn tại, còn chuỗi dùng dấu `/` sai binary name, nên đều CNFE.
9. `Class.forName("int")` không lấy primitive `int.class`, nên cũng CNFE.

**Giới hạn rõ ràng:** stdout này giả định không có bản `com.acme.plugin.Greeting` trong application classpath, không có class khác cùng tên do parent định nghĩa, Java runtime tương thích và hai source files được tạo đúng như ví dụ.

### 5.6. Nếu đóng plugin thành JAR

Có thể đóng gói từ class output:

~~~bash
mkdir -p dist
jar --create --file dist/plugin.jar -C out/plugin .

jar --list --file dist/plugin.jar
~~~

JAR phải chứa `com/acme/plugin/Greeting.class`. Thử:

~~~bash
java -cp out/app ClassNotFoundLab dist/plugin.jar
~~~

Do host chuyển đối số thành `file:` URL qua `Path.toUri().toURL()`, URLClassLoader hỗ trợ **cả directory URL và JAR file URL**. Lệnh Usage cho phép thư mục hoặc JAR; thí nghiệm dùng cùng code với plugin JAR; khi class tồn tại trong JAR và không bị parent che, stdout vẫn giống.

**Lưu ý:** plugin JAR không cần `Main-Class` nếu chỉ nạp class bằng URLClassLoader; `Main-Class` dành cho executable JAR chạy bằng `java -jar`.

## 6. Phân biệt ClassNotFoundException và NoClassDefFoundError

Cả hai có thể xuất hiện khi một class bị thiếu, nhưng báo **hai tầng lỗi khác nhau**:

| | `ClassNotFoundException` | `NoClassDefFoundError` |
| --- | --- | --- |
| Nhánh Throwable | Checked `ReflectiveOperationException` | `LinkageError` → `Error` |
| Kích hoạt thường gặp | `Class.forName(name)`, `loader.loadClass(name)` yêu cầu tra theo tên | JVM resolve class mà bytecode đã tham chiếu hoặc class đã khởi tạo hỏng |
| Thông tin cần lấy | Chuỗi binary name, API overload và loader được chọn | Cause chain, class còn thiếu, lần thất bại đầu, linker và loader |

Ví dụ `Class.forName("plugin.Missing")` từ host có thể ném **CNFE**, trong khi bytecode đã compile để gọi `MissingDependency.run()` với dependency bị xóa ở runtime có thể ném **NCDFE**, đôi khi CNFE xuất hiện trong cause chain. Hai ví dụ này chỉ minh họa bối cảnh; bytecode gọi `MissingDependency` chỉ biên dịch nếu class thực sự tồn tại lúc compile.

**Với initialization failure**, lần active use đầu có thể ném `ExceptionInInitializerError`; những lần sau trong cùng defining loader có thể ném `NoClassDefFoundError: Could not initialize class ...`. Khi gặp dấu hiệu ấy phải tìm `<clinit>` và cause ban đầu, không chỉ thêm JAR.

Bài **NoClassDefFoundError do thiếu lớp phụ thuộc hoặc sai tên** có hai lab độc lập tái hiện lỗi thiếu dependency và class bytecode mang sai binary name. Bài **NoClassDefFoundError sau khi khởi tạo lớp thất bại** trình bày riêng erroneous state và cách phục hồi bằng loader mới. Trong bài CNFE này, câu hỏi trước tiên vẫn là **ai gọi lookup, tên nào, và loader nào thực sự tìm**.

## 7. Vì sao loader đúng về vật lý nhưng sai về phạm vi?

### 7.1. Parent không nhìn thấy child

~~~text
ApplicationLoader
      |
      +-- PluginLoader A -> plugin-a.jar
      |
      +-- PluginLoader B -> plugin-b.jar
~~~

Parent không có nghĩa vụ tìm class **ở các child loaders**. Plugin loader A cũng không tự thấy class riêng của plugin loader B khi chỉ có chung parent. Vì thế:

~~~java
Class.forName("plugin.b.Feature");
~~~

khi được gọi từ host có thể CNFE dù class nằm trong `plugin-b.jar` mà PluginLoader B thấy. Cần gọi `Class.forName(name, initialize, loaderB)` hoặc `loaderB.loadClass(name)` một cách có chủ đích.

**Không ép mọi plugin JAR vào global application classpath chỉ để xử lý CNFE**, vì điều đó có thể phá version isolation và loader lifecycle của hệ plugin.

### 7.2. Thread context class loader (TCCL)

Một số framework và `ServiceLoader.load(Service.class)` chọn **thread context class loader** để tìm provider. Nhưng:

~~~java
Class.forName("plugin.Feature");
~~~

không mặc định chuyển sang TCCL chỉ vì thread đã gán TCCL khác.

Nếu cần, làm tường minh:

~~~java
ClassLoader tccl =
        Thread.currentThread().getContextClassLoader();

Class<?> type = Class.forName("plugin.Feature", false, tccl);
~~~

Đây là mảnh minh họa; nếu `tccl == null`, overload này sử dụng bootstrap loader. Trong plugin runtime, cân nhắc xác định loader từ framework contract thay vì phụ thuộc ngầm vào trạng thái thread.

Khi thư viện yêu cầu TCCL, đặt có thời hạn và **restore trong `finally`**:

~~~java
Thread thread = Thread.currentThread();
ClassLoader old = thread.getContextClassLoader();
try {
    thread.setContextClassLoader(pluginLoader);
    // Gọi thư viện cần TCCL.
} finally {
    thread.setContextClassLoader(old);
}
~~~

Không để TCCL của thread pool trỏ tới plugin loader đã ngừng hoạt động: nó vừa gây sai discovery cho request sau, vừa có thể giữ loader cũ không unload được.

### 7.3. Parent-first có thể nạp bản khác với mong đợi

Giả sử parent có `lib.Parser` phiên bản v1, plugin JAR chứa v2. Lời gọi `pluginLoader.loadClass("lib.Parser")` với URLClassLoader mặc định có thể trả `Class<?>` v1 do parent định nghĩa, **không ném CNFE**. Nhưng khi plugin gọi method chỉ có ở v2, JVM có thể ném `NoSuchMethodError`.

Đây là tình huống **lookup thành công nhưng runtime behavior/linkage sai**. Đừng kết luận chỉ vì không thấy CNFE thì classpath và dependency versions đúng.

## 8. Classpath, executable JAR và module path

### 8.1. Classpath mode

Trên Linux/macOS:

~~~bash
java -cp "out/app:libs/plugin.jar" com.example.Main
~~~

Trên Windows:

~~~powershell
java -cp "out/app;libs/plugin.jar" com.example.Main
~~~

Các ví dụ cú pháp minh họa giả định `com.example.Main` tồn tại. Dấu phân cách classpath là `:` trên Unix-like, `;` trên Windows.

Classpath root có thể là thư mục hoặc JAR. Nếu binary name là `com.acme.Feature`, đường dẫn bên dưới root phải là `com/acme/Feature.class`.

Classpath CLI wildcard:

~~~bash
java -cp "out/app:libs/*" com.example.Main
~~~

Nó có thể thêm các file JAR trong thư mục `libs` theo quy tắc launcher; wildcard **không tìm đệ quy toàn cây thư mục**, và không tự bảo đảm version order. Không dùng wildcard nếu đang điều tra hai JAR có cùng class và cần biết chính xác bản nào được chọn.

### 8.2. Chế độ `java -jar`

~~~bash
java -cp "libs/*" -jar app.jar
~~~

**Không** có nghĩa `libs/*` được thêm vào user classpath của ứng dụng như ở classpath mode: với `-jar`, những thiết lập classpath thông thường như `-cp` và `CLASSPATH` bị bỏ qua trong việc chọn đường tìm class của ứng dụng. Các dependency có thể được khai báo qua `Class-Path` của manifest hoặc được đóng gói bằng cơ chế thích hợp.

Manifest ví dụ:

~~~text
Manifest-Version: 1.0
Main-Class: com.example.Main
Class-Path: libs/plugin.jar

~~~

Các entry `Class-Path` manifest được phân cách bằng **khoảng trắng** và resolve **tương đối vị trí JAR chứa manifest**, không theo dấu phân cách classpath của OS. Không viết `Class-Path: libs/*` rồi trông đợi wildcard như `-cp "libs/*"`.

### 8.3. JPMS named modules

Java 9+ có named modules được resolve qua **module path**, cùng các quan hệ `requires`, `exports`, `opens` và module layers.

**Phân biệt:**
- Thiếu module hoặc module chưa được resolved có thể khiến named-module class không thuộc phạm vi loader/module lookup mà caller yêu cầu.
- Package không `exports` là **vấn đề access từ module khác**, không tự đồng nghĩa class file không tồn tại và không phải mọi trường hợp đều báo CNFE. Có thể gặp `IllegalAccessError`/`IllegalAccessException` ở bước truy cập tùy tình huống.
- `opens` chủ yếu liên quan deep reflection/resource access; **không phải phương thuốc mặc định cho mọi CNFE**.
- `Class.forName(Module module, String name)` là overload đặc biệt: tìm class trong module chỉ định và **trả `null` khi không tìm thấy trong module đó** theo hợp đồng API; không ném CNFE chỉ vì lookup không tìm thấy. Nó không yêu cầu initialize class.
- `ClassLoader.loadClass(Module module, String name)` cũng có hợp đồng khác với `loadClass(String)` và có thể **trả `null` nếu class không tìm được trong module đã chỉ định**.

Do đó, **xác định overload API thực sự đang gọi** trước khi khẳng định một lookup không thành công luôn ném `ClassNotFoundException`.

## 9. Quy trình chẩn đoán CNFE theo từng lớp bằng chứng

### Bước 1 — Ghi đúng yêu cầu

Lấy **giá trị binary name** thực sự truyền vào API (sau khi trim/config parsing khi cần), API overload nào, thread, module của caller và stack trace/cause chain.

Một config có thể vô tình chứa khoảng trắng đầu/cuối:

~~~text
plugin.class = com.acme.plugin.Greeting
~~~

Nếu parser không chuẩn hóa hoặc đọc sai key, string truyền cho `Class.forName` có thể khác chuỗi bạn nhìn thấy bằng mắt.

### Bước 2 — In loader được dùng

~~~java
ClassLoader callerLoader =
        ClassNotFoundLab.class.getClassLoader();

ClassLoader tccl =
        Thread.currentThread().getContextClassLoader();

ClassLoader system =
        ClassLoader.getSystemClassLoader();

System.out.println(callerLoader);
System.out.println(tccl);
System.out.println(system);
~~~

Đây là đoạn minh họa khi `ClassNotFoundLab` có trong scope; không có bảo đảm ba loader bằng nhau. Trên nhiều ứng dụng đơn giản, chúng có thể trùng, nhưng plugin/container frameworks thường cấu hình khác.

**Nếu class chưa tìm được thì bạn chưa có `Class<?>` của chính nó để gọi `getClassLoader()`.** Hãy bắt đầu từ loader đang thực hiện lookup và search roots của loader đó.

### Bước 3 — Kiểm tra artifact có chứa class thật không

Với JAR:

~~~bash
jar --list --file libs/plugin.jar
~~~

Tìm đúng entry:

~~~text
com/acme/plugin/Greeting.class
~~~

Nếu chỉ thấy `com/acme/plugin/Greeting.java` thì JAR chứa source, **không nhất thiết chứa class file** để JVM nạp như kỳ vọng.

Với thư mục, kiểm tra root và package subdirectories. Đường dẫn `out/plugin/com/acme/plugin/Greeting.class` thì URL/classpath root là `out/plugin`, không phải `out/plugin/com/acme/plugin`.

### Bước 4 — Kiểm tra compile-time và runtime cấu hình khác nhau không

Một dự án compile được nhờ dependency nằm trong classpath của IDE/Maven/Gradle, nhưng lúc runtime dùng một JAR/launch script không mang dependency ấy.

Xác định:

- Lệnh `java` thực tế chạy (classpath mode hay `-jar`).
- Environment/module path của tiến trình runtime, không chỉ IDE.
- Artifact version/path và thư mục triển khai.
- Scope của dependency (compile-only/test-only vs runtime).
- Nếu là plugin framework, URL classloader của plugin có được khởi tạo đúng và còn sống không.

**Compile thành công không chứng minh runtime loader sẽ tìm được mọi class.**

### Bước 5 — Kiểm tra binary name thay vì path

~~~text
Tên Java cần truyền: com.acme.plugin.Greeting
Tệp JAR entry:       com/acme/plugin/Greeting.class
~~~

Với nested class, dùng `Outer$Inner`. Với primitive, dùng `int.class` chứ không dùng `Class.forName("int")`.

### Bước 6 — Thử explicit loader có kiểm soát

Nếu đang chẩn đoán một plugin đáng tin và biết vị trí artifact:

~~~java
URL url = Path.of("plugins", "plugin.jar")
        .toAbsolutePath().toUri().toURL();

try (URLClassLoader loader = new URLClassLoader(
        new URL[] {url},
        ClassLoader.getSystemClassLoader())) {
    Class<?> type = loader.loadClass("com.acme.plugin.Greeting");
    System.out.println(type.getName());
}
~~~

Đây là **mảnh minh họa**, cần import `URL`, `URLClassLoader`, `Path` và xử lý exceptions; plugin JAR thực sự phải tồn tại. Nếu tìm được với URL loader tường minh nhưng không tìm được bằng host loader, vấn đề nằm ở **visibility/loader choice** thay vì binary name không tồn tại.

**Không sửa global classpath của cả ứng dụng vội** khi plugin framework đã có loader riêng; làm vậy có thể tạo class version conflict hoặc duplicate runtime interfaces.

### Bước 7 — Xác định vấn đề sau khi tìm thấy

Nếu class đã nạp:

~~~java
Class<?> type = loader.loadClass("com.acme.plugin.Greeting");

System.out.println(type.getName());
System.out.println(type.getClassLoader());
System.out.println(type.getModule());
~~~

Nếu có CodeSource:

~~~java
var pd = type.getProtectionDomain();
var cs = pd == null ? null : pd.getCodeSource();

System.out.println(cs == null ? "source unavailable"
        : cs.getLocation());
~~~

Các đoạn trên chỉ là **mảnh chẩn đoán** với biến loader phù hợp. CodeSource có thể `null`; không phải chứng chỉ tuyệt đối của nguồn.

### Bước 8 — JVM class loading logs

Trên HotSpot/JDK 17+ có thể bật logging:

~~~bash
java -Xlog:class+load=info \
     -cp out/app ClassNotFoundLab out/plugin
~~~

Đây là **lệnh chẩn đoán** tạo thêm các dòng log tùy runtime; không thuộc stdout chuẩn ở phần ví dụ. Nó hữu ích để xem nguồn của những class **đã được load**, nhưng không phải tất cả class không tìm thấy đều có entry chi tiết ở mức `info`. Đừng ngộ nhận “không thấy log class X” là kết luận duy nhất về nguyên nhân thất bại.

## 10. Những lỗi thường gặp và cách khắc phục

| Triệu chứng | Khả năng thường gặp | Khắc phục đúng hướng |
|---|---|---|
| `Class.forName("pkg.X")` CNFE, JAR chứa `pkg/X.class` | JAR không nằm trong loader search roots | Cấu hình classpath/URL/module cho **loader đúng** |
| `Class.forName` từ host không thấy class plugin | Host loader không nhìn xuống child | Dùng explicit plugin loader hoặc API plugin framework |
| Có `.class` nhưng path dưới root sai | Chỉ định root tới sai thư mục | Đưa root lên đúng cấp package |
| `Class.forName("a/b/C.class")` | Dùng file path thay binary name | Đổi thành `a.b.C` |
| `Class.forName("a.Outer.Inner")` | Nhầm nested class binary name | Dùng `a.Outer$Inner` |
| `Class.forName("int")` | Primitive name không hợp lệ cho API | Dùng `int.class` |
| Chạy từ IDE thành công, `java -jar` CNFE | Runtime thiếu dependency/manifest reference | Kiểm tra artifact cuối, manifest và deployment |
| Plugin A thấy class, plugin B không | Loader graph/ownership khác | Chọn loader đúng và thiết kế SPI/API chung |
| CNFE trong `ServiceLoader`/framework wrapper | Provider config hoặc TCCL sai | Kiểm tra descriptor, provider type, TCCL và cause chain |
| `NoClassDefFoundError` ngoài cùng | JVM cần dependency khi link/init | Đọc cause, kiểm tra missing binary/module/init |
| `NoSuchMethodError` sau khi class tải được | Dependency version ở parent khác compile time | So runtime defining loader và bytecode signatures |
| `IllegalAccessError` / reflection error | Class tồn tại nhưng access/module khác | Kiểm tra package ownership, `exports`/`opens` phù hợp |
| `ClassFormatError` / `UnsupportedClassVersionError` | Bytes không hợp lệ hoặc JDK runtime quá cũ | Compile `--release` phù hợp, xác minh bytes/Java version |

### Vì sao “thêm dependency” đôi khi làm lỗi nặng hơn?

Ví dụ host cần API `api.Plugin` do parent định nghĩa, plugin con cần `plugin.Impl`. Nếu để sửa CNFE bạn copy luôn `api.Plugin` vào một child-first JAR, plugin có thể tự định nghĩa **bản API thứ hai**. Khi trả object về host, cast sẽ fail mặc dù tên interface giống nhau.

Đúng hơn là giữ **shared API ở parent**, implementation ở plugin child. Có những trường hợp lỗi lookup là tín hiệu bạn đang dùng nhầm class loader boundary; giải pháp tốt không phải “đưa mọi JAR vào mọi nơi”.

## 11. Thiết kế lỗi và xử lý ngoại lệ đúng mức

### Thiếu một plugin tùy chọn

Nếu phần mở rộng có tính tùy chọn, có thể log/warn và tiếp tục với provider mặc định:

~~~java
try {
    Class<?> provider = pluginLoader.loadClass(configuredProvider);
    // Kiểm tra interface và tạo instance theo contract.
} catch (ClassNotFoundException ex) {
    System.err.println("Optional provider unavailable: "
            + configuredProvider);
    // Chọn fallback theo chính sách đã thiết kế.
}
~~~

Đây là mảnh minh họa; `pluginLoader`/`configuredProvider` phải tồn tại. Khi triển khai production, log exception/cause và plugin ID đủ để tra cứu, nhưng không log dữ liệu cấu hình nhạy cảm.

### Thiếu một dependency bắt buộc

Với một ứng dụng không thể hoạt động nếu thiếu class cấu hình, nên **fail fast** và báo lỗi có bối cảnh (binary name, artifact/version, loader identity, runtime command). Không catch rồi bỏ qua để tạo lỗi liên kết khó hiểu ở bước sau.

### Không catch mọi `Throwable`

Đoạn như:

~~~java
try {
    Class.forName(name);
} catch (Throwable ignored) {
    // nguy hiểm: che lỗi linkage, OutOfMemoryError, initializer...
}
~~~

là **anti-pattern minh họa**, không phải cách sửa. `ClassNotFoundException` là một loại lỗi cụ thể; `NoClassDefFoundError`, `ExceptionInInitializerError`, `VerifyError` và `OutOfMemoryError` không nên bị coi như cùng một “không có plugin”.

Một hệ plugin có policy cô lập lỗi riêng có thể bắt một số `LinkageError` có chủ đích tại boundary, nhưng phải bảo toàn cause, phân loại fatal/nonfatal và quyết định lifecycle đúng; không gộp tất cả vào CNFE.

### `ClassNotFoundException` và cause chain

Một custom `findClass` có thể ném:

~~~java
throw new ClassNotFoundException(binaryName, ioException);
~~~

Đây là mảnh minh họa với biến `binaryName` và `ioException` có sẵn. Vì loader tìm bytes từ đĩa/JAR/nguồn từ xa có thể thất bại do I/O, cause chain mang thông tin hữu ích hơn một tên class đơn lẻ.

Nếu cause là permission denied, timeout hoặc resource corruption, sửa binary name hoặc thêm classpath không đủ. **Đọc `getCause()`**, xác định source URL/path và loader; không ném một CNFE trống rồi mất thông tin ban đầu.

## 12. Bảng quyết định nhanh

| Bằng chứng quan sát | Nghi ngờ đầu tiên | Bước tiếp theo |
|---|---|---|
| `Class.forName(name)` thất bại, `pluginLoader.loadClass(name)` thành công | Sai loader ở caller | Chọn explicit plugin loader/TCCL phù hợp |
| JAR không chứa entry `p/C.class` | Artifact chưa đóng gói class | Sửa build/package |
| JAR chứa class nhưng URL loader không tìm được | URL root/JAR không đúng, name sai hoặc delegation khác | Log `loader.getURLs()`, binary name, đường dẫn |
| `Class.forName(name,true,loader)` báo initializer error | Class đã được tìm nhưng init fail | Điều tra `static` code/cause |
| CNFE nằm trong cause của NCDFE | JVM cần một class khi link/runtime | Khắc phục dependency runtime, không đổi loại lỗi |
| Class nạp được nhưng `ClassCastException` | API class identity khác loader | Kiểm tra defining loader của cả hai kiểu |
| Class nạp được nhưng `NoSuchMethodError` | ABI/version sai | So compiler classpath với runtime defining loader |
| `java -jar` lỗi nhưng `-cp` mode chạy | Runtime JAR manifest/dependencies khác | Kiểm tra `Main-Class`/`Class-Path` và layout |
| Named-module lookup trả `null` | Dùng overload `Class.forName(Module, String)` | Kiểm tra module object, resolution/layer, tên |
| Chỉ lỗi trên một thread | TCCL hoặc framework loader khác | In thread name/TCCL, restore context sau use |

## 13. Checklist trước khi đóng ticket CNFE

- [ ] Có **binary name chính xác** được yêu cầu, không chỉ file path hoặc tên ngắn.
- [ ] Biết **API overload** nào đã được gọi và nó chọn loader theo cách nào.
- [ ] Phân biệt caller loader, system loader, TCCL và plugin loader.
- [ ] Biết class nằm ở JAR/thư mục nào và artifact runtime **thực sự** có file `.class`.
- [ ] Cấu trúc package path khớp binary name, kể cả nested class `$`.
- [ ] Đường dẫn classpath hoặc URL root trỏ đúng cấp thư mục/JAR.
- [ ] Chế độ khởi chạy là `-cp`, `-jar` hay JPMS; không áp dụng nhầm quy tắc.
- [ ] Nếu dùng `java -jar`, manifest `Class-Path`/deployment dependency đã đúng.
- [ ] Nếu dùng JPMS, module thực sự được resolved và package accessibility được xem riêng.
- [ ] Không nhầm checked CNFE với `NoClassDefFoundError`/linkage/initializer error.
- [ ] Kiểm tra runtime **dependency version** và parent delegation nếu class đã nạp nhưng hành vi sai.
- [ ] Không để workaround thêm JAR tạo duplicate shared API ở child loaders.
- [ ] Nếu class được nạp, kiểm tra defining loader và CodeSource khi có.
- [ ] Có test chạy từ **artifact thật** thay vì chỉ IDE.
- [ ] Log lỗi có ngữ cảnh, không làm lộ secrets và không catch mọi Throwable.
- [ ] Lựa chọn fail-fast hoặc fallback cho plugin dựa trên yêu cầu ứng dụng.

## 14. Tự kiểm tra

**Câu 1.** `out/plugin/com/acme/Foo.class` tồn tại. Ứng dụng chỉ chạy `java -cp out/app Main` rồi gọi `Class.forName("com.acme.Foo")`. Vì sao CNFE?

**Đáp án:** Application loader chỉ có `out/app`; đường tìm kiếm không bao gồm `out/plugin`. Dù file có trên đĩa, loader caller không thấy nó. Cần cấu hình classpath đúng hoặc chỉ định loader có URL tới `out/plugin`.

**Câu 2.** `Class.forName("com/acme/Foo.class")` có đúng không?

**Đáp án:** Không. API cần binary name `com.acme.Foo`; chuỗi có `/` và `.class` là path/filename.

**Câu 3.** Tại sao `Class.forName(name)` từ host thất bại còn `Class.forName(name, false, pluginLoader)` thành công?

**Đáp án:** Overload đầu sử dụng loader của caller; overload thứ hai dùng plugin loader được truyền tường minh. Parent thường không tìm trong child loader.

**Câu 4.** Một class có initializer lỗi. `Class.forName(name, true, loader)` có chắc ném CNFE không?

**Đáp án:** Không. Lookup có thể thành công nhưng class initialization thất bại với `ExceptionInInitializerError` hoặc lỗi liên quan, không phải CNFE.

**Câu 5.** `ClassNotFoundException` khác `NoClassDefFoundError` ở đâu?

**Đáp án:** CNFE là checked exception của explicit lookup thất bại; NCDFE là `LinkageError` khi JVM cần một class definition/initialization mà không thành công, có thể chứa CNFE trong cause chain.

**Câu 6.** `Class.forName("int")` có lấy primitive class object không?

**Đáp án:** Không; dùng `int.class`. `Class.forName("int")` ném CNFE.

**Câu 7.** Một nested class khai báo `Outer.Inner` trong source có binary name gì?

**Đáp án:** `Outer$Inner` (có package prefix nếu có), không phải `Outer.Inner`.

**Câu 8.** `Class.forName(module, "p.C")` không tìm thấy class. Nó phải ném CNFE chứ?

**Đáp án:** Không. Overload có `Module` trả `null` nếu không tìm thấy theo hợp đồng API; xác minh overload trước khi phân loại lỗi.

**Câu 9.** Class tìm được bằng URLClassLoader nhưng cast sang SPI của host thất bại. Có còn là CNFE không?

**Đáp án:** Không. Vấn đề có thể là **hai runtime SPI types** do different defining loaders, dẫn đến `ClassCastException` hoặc lỗi khác. Cần chia sẻ SPI ở parent.

**Câu 10.** Tại sao không nên sửa lỗi bằng cách `catch (Throwable ignored)`?

**Đáp án:** Nó che cả linkage errors, initializer errors và những lỗi nghiêm trọng; rất khó chẩn đoán và có thể tiếp tục trong trạng thái không hợp lệ.

## 15. Quy trình ghi nhớ

~~~text
ClassNotFoundException xuất hiện
            |
            v
Explicit API nào? name nào?
            |
            v
Class.forName(String) / loadClass(String)
hay overload có Module/loader?
            |
            v
Chọn loader thực tế (caller/TCCL/explicit)
            |
            v
Class đã nằm trong nguồn loader nhìn thấy?
       /                        \
     Không                       Có
       |                          |
Sửa runtime classpath/URL     Kiểm tra binary name,
module resolution            parent delegation,
hoặc loader selection         JAR contents, root
       |                          |
       +------------+-------------+
                    |
                    v
             Nếu đã tìm được:
   phân biệt init/linkage/access/type identity
                    |
                    v
       Test artifact thực + xác nhận cause
~~~

**Kết luận:** `ClassNotFoundException` là dấu hiệu một **yêu cầu tìm class tường minh không hoàn tất với tên và loader được chọn**. Cách sửa bền vững không phải cứ chép thêm `.class` hoặc bắt mọi exception, mà phải xác định **lookup API**, **binary name**, **loader graph**, **runtime artifact/search roots** và **giai đoạn lỗi**. Một khi đã tìm được class, hãy tiếp tục kiểm tra initialization, binary compatibility và runtime type identity trước khi coi việc khắc phục hoàn tất.

### Tài liệu chính thức

- [Java SE 17 — ClassNotFoundException API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassNotFoundException.html)
- [Java SE 17 — Class.forName và Class.getClassLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html)
- [Java SE 17 — ClassLoader.loadClass, delegation và resource lookup](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html)
- [Java SE 17 — NoClassDefFoundError](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/NoClassDefFoundError.html)
- [Java SE 17 — URLClassLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html)
- [Java SE 17 — java launcher/classpath/`-jar`](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html)
- [JVMS 17 `5.3 — Creation and Loading](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.3)
