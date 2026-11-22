# Phân biệt classpath, module path và đường dẫn native library

> Java Core → ClassLoader → Đường dẫn tìm kiếm. Ba loại đường dẫn này phục vụ ba cơ chế khác nhau: tìm Java classes/resources, tìm Java named modules và tìm native binaries. Không thể sửa lỗi của cả ba chỉ bằng cách thêm file vào một thư mục.

## 1. So sánh ba đường dẫn

| Loại | Artifact được tìm | Cấu hình thường dùng | Cơ chế |
| --- | --- | --- | --- |
| **Classpath** | Directory chứa cây `.class`, Java JAR và resources | `-cp`, `-classpath`, `--class-path` | ClassLoader và unnamed module |
| **Module path** | Exploded module, modular JAR, automatic-module JAR | `--module-path` hoặc `-p` | JPMS discovery, resolution và access graph |
| **Native library path** | `.dll`, `.so`, `.dylib` chứa mã máy | `-Djava.library.path=...`, `System.load`, `System.loadLibrary` | JNI/VM và OS dynamic loader |

~~~text
                         Java process
            +-----------------+------------------+
            |                 |                  |
       Classpath         Module path       Native search
     .class / JAR       Named modules       DLL/SO/dylib
            |                 |                  |
       ClassLoader        Module graph       OS/VM linker
~~~

Classloader nạp Java classes không tự động mở DLL chỉ vì DLL ở classpath. Ngược lại, `java.library.path` không dùng để tìm `.class`. Module path cũng không chỉ là classpath mang tên mới.

## 2. Classpath: Java classes và resources

Nếu class `demo.app.Main` được biên dịch vào `out/classes/demo/app/Main.class`, **classpath root** là `out/classes`, không phải `out/classes/demo/app`.

Linux/macOS:

~~~bash
java -cp "out/classes:libs/helper.jar" demo.app.Main
~~~

Windows PowerShell/CMD:

~~~powershell
java -cp "out/classes;libs/helper.jar" demo.app.Main
~~~

Phân cách classpath entries bằng **`:`** trên Unix và **`;`** trên Windows. `libs/*` mở rộng tới **JAR trực tiếp trong thư mục `libs`** khi Java launcher xử lý, không quét đệ quy. Luôn dùng binary class name (`demo.app.Main`), không dùng đường file của Main.class.

Classpath lúc biên dịch và lúc chạy là **hai cấu hình có thể khác nhau**: `javac -cp` dùng tìm kiểu lúc compile, `java -cp` dùng nạp class runtime. Nếu có JAR ở bước compile nhưng không có ở bước chạy, bạn có thể gặp `NoClassDefFoundError` hoặc `ClassNotFoundException` tùy tình huống.

- `CLASSPATH` là biến môi trường cho giá trị mặc định khi không có `-cp`; ưu tiên cấu hình explicit để dễ tái lập.
- Khi chạy main class qua classpath không cấu hình `-cp`/`CLASSPATH`, current directory thường là classpath mặc định.
- `java -jar app.jar` dùng `Main-Class` từ manifest. Trong launcher mode này, `-cp`/`CLASSPATH` không phải cách ghép thêm user classpath thông thường. Cần manifest `Class-Path`, distribution hợp lệ hoặc chạy với main class qua `-cp`.
- `System.getProperty("java.class.path")` không liệt kê toàn bộ class do custom loaders lấy từ plugin/network. Sửa property sau startup không buộc loader đọc lại classpath.

### 2.1. Unnamed module trên JDK 9+

Class từ classpath thuộc **unnamed module** của defining classloader; Java runtime vẫn chứa các named modules như `java.base`.

Tệp **ClasspathInfo.java**:

~~~java
public class ClasspathInfo {
    public static void main(String[] args) {
        Module current = ClasspathInfo.class.getModule();
        System.out.println("named=" + current.isNamed());
        System.out.println("name=" + current.getName());
        System.out.println("core=" + Object.class.getModule().getName());
    }
}
~~~

~~~bash
javac --release 17 ClasspathInfo.java
java -cp . ClasspathInfo
~~~

Stdout:

~~~text
named=false
name=null
core=java.base
~~~

`null` chỉ là tên của unnamed module, không phải lỗi nạp class.

### 2.2. Biên dịch library JAR và dùng nó từ classpath

Cây source:

~~~text
classpath-demo/
├─ src-lib/demo/lib/Greeter.java
└─ src-app/demo/app/Main.java
~~~

Tệp **src-lib/demo/lib/Greeter.java**:

~~~java
package demo.lib;

public final class Greeter {
    private Greeter() {}

    public static String message() {
        return "hello from classpath";
    }
}
~~~

Tệp **src-app/demo/app/Main.java**:

~~~java
package demo.app;

import demo.lib.Greeter;

public class Main {
    public static void main(String[] args) {
        System.out.println(Greeter.message());
        System.out.println(Greeter.class.getModule().isNamed());
    }
}
~~~

Từ thư mục classpath-demo (POSIX shell):

~~~bash
mkdir -p out/lib out/app dist
javac --release 17 -d out/lib src-lib/demo/lib/Greeter.java
jar --create --file dist/greeter.jar -C out/lib .
javac --release 17 -cp dist/greeter.jar -d out/app src-app/demo/app/Main.java
java -cp "out/app:dist/greeter.jar" demo.app.Main
~~~

Stdout:

~~~text
hello from classpath
false
~~~

Bước cuối là nơi xác định **runtime classpath**. Bỏ `dist/greeter.jar` khỏi lệnh Java có thể khiến Greeter không được tìm thấy lúc chạy dù `javac` đã thành công.

## 3. Module path: discovery và resolution của JPMS

Java 9 giới thiệu Java Platform Module System. `--module-path` chỉ cho module system nơi tìm module artifacts. Nó còn cần chọn **root modules**, theo `requires` để xây dựng dependency graph. Một JAR đặt trên module path **không tự động được resolve**.

Ba loại thường gặp:

- **Explicit named module**: có `module-info.class`; descriptor khai báo `requires`, `exports`, `opens`, services.
- **Automatic named module**: JAR không có descriptor nhưng ở module path; khi được resolve, module name có thể từ manifest `Automatic-Module-Name` hoặc tên file.
- **Unnamed module**: code ở classpath, không phải automatic named module, ngay cả khi JAR chứa manifest Automatic-Module-Name.

Điều kiện sử dụng named-module API:

1. **Resolution**: module cần ở graph.
2. **Readability**: caller module phải đọc module cung cấp.
3. **Exports**: package public API phải được export đến caller.
4. **Opens** khi cần deep reflection phù hợp module API; `opens` không đồng nghĩa `exports`.

Một classloader có thể định nghĩa nhiều modules; **loader parent delegation** và **module readability** là hai quan hệ độc lập.

### 3.1. Ví dụ hai named modules, Java 17+

Cấu trúc:

~~~text
src/
├─ demo.greeting/
│  ├─ module-info.java
│  └─ demo/greeting/Greeter.java
└─ demo.consumer/
   ├─ module-info.java
   └─ demo/consumer/Main.java
~~~

**src/demo.greeting/module-info.java**

~~~java
module demo.greeting {
    exports demo.greeting;
}
~~~

**src/demo.greeting/demo/greeting/Greeter.java**

~~~java
package demo.greeting;

public final class Greeter {
    private Greeter() {}

    public static String message() {
        return "hello from module";
    }
}
~~~

**src/demo.consumer/module-info.java**

~~~java
module demo.consumer {
    requires demo.greeting;
}
~~~

**src/demo.consumer/demo/consumer/Main.java**

~~~java
package demo.consumer;

import demo.greeting.Greeter;

public class Main {
    public static void main(String[] args) {
        System.out.println(Greeter.message());
        System.out.println(Greeter.class.getModule().getName());
        System.out.println(Main.class.getModule()
                .canRead(Greeter.class.getModule()));
    }
}
~~~

Biên dịch và chạy từ thư mục cha của src (POSIX shell):

~~~bash
mkdir -p mods/demo.greeting mods/demo.consumer
javac --release 17 -d mods/demo.greeting \
    src/demo.greeting/module-info.java \
    src/demo.greeting/demo/greeting/Greeter.java
javac --release 17 --module-path mods -d mods/demo.consumer \
    src/demo.consumer/module-info.java \
    src/demo.consumer/demo/consumer/Main.java
java --module-path mods --module demo.consumer/demo.consumer.Main
~~~

Stdout:

~~~text
hello from module
demo.greeting
true
~~~

`mods` chứa **hai exploded modules**, mỗi subfolder có module-info.class và package tree. Nếu xóa requires, consumer không đọc dependency; nếu xóa exports, public Greeter không truy cập như API cho consumer.

### 3.2. Kết hợp classpath và module path

~~~bash
java --module-path mods --class-path "legacy/*" \
    --module demo.consumer/demo.consumer.Main
~~~

Cấu hình hai đường đồng thời **không** khiến named module đọc toàn bộ unnamed module. Không thể viết `requires unnamed;` trong module descriptor. Khi cần migration, cân nhắc chuyển legacy JAR thành automatic/explicit named module hoặc dùng `--add-reads module=ALL-UNNAMED` với hiểu biết rõ về hạn chế.

Kiểm tra module:

~~~bash
java --list-modules
jar --describe-module --file libs/library.jar
java --show-module-resolution --module-path mods \
    --module demo.consumer/demo.consumer.Main
~~~

Các lệnh chỉ chạy khi JAR/modules ở ví dụ thực sự tồn tại. `java --list-modules` liệt kê system modules; `jar --describe-module` cho biết metadata/tên automatic module của JAR; `--show-module-resolution` cho phép theo dõi graph ở lần chạy.

## 4. Native library path: tìm binary của hệ điều hành

JNI/native code dùng shared library đã biên dịch cho **OS, kiến trúc CPU và ABI**. Logical name `codec` có mapping điển hình như `codec.dll` trên Windows, `libcodec.so` trên Linux và `libcodec.dylib` trên macOS. Tên thực được xác định bởi platform/JVM: hỏi `System.mapLibraryName("codec")`.

Hai API:

~~~java
System.loadLibrary("codec");                 // logical name
System.load("/opt/app/native/libcodec.so");  // absolute path Linux
~~~

Đây là snippet giải thích, không chạy nếu thiếu native binary thật.

- `System.loadLibrary` nhận **logical name**, không kèm thư mục hay extension.
- `System.load` nhận **đường dẫn tuyệt đối** tới native binary.
- JVM có thể gọi `ClassLoader.findLibrary(String)` của loader liên quan để nhận absolute path; nếu không, tìm theo native library paths có hiệu lực, như `java.library.path`.
- Đóng DLL/SO **bên trong JAR resource** chưa đủ: native loader không tự load file từ jar: URL. Một JNI wrapper có thể giải nén binary phù hợp ra file được kiểm tra và gọi `System.load(absolutePath)`.
- Native library gắn với các ràng buộc loader/lifecycle riêng; cùng binary cố load trong hai defining loaders khác nhau có thể nhận `UnsatisfiedLinkError`. `URLClassLoader.close()` không bảo đảm native library được unload tức thì.

Ví dụ Linux/macOS:

~~~bash
java -Djava.library.path=/opt/app/native -cp "app.jar:libs/*" com.acme.Main
~~~

Windows:

~~~powershell
java -Djava.library.path="C:\app\native" -cp "app.jar;libs/*" com.acme.Main
~~~

`-Djava.library.path` phải nằm **trước tên main class**. Đặt phía sau sẽ thành application argument. Đổi `System.setProperty("java.library.path", "...")` sau JVM startup **không bảo đảm** runtime cập nhật bảng tìm native.

### 4.1. JVM native lookup và OS dynamic linker là hai tầng

Tầng 1: JVM tìm `codec` theo `loadLibrary`/`load`. Tầng 2: OS loader tìm **dependent binaries** của `codec` như `libcrypto.so` hay DLL runtime khác. Linux có `LD_LIBRARY_PATH`/RPATH/RUNPATH; Windows có DLL search rules và PATH trong một số trường hợp; macOS có `@rpath`/loader paths/signing. Không thể suy ra chỉ cần `java.library.path` đúng thì mọi dependency native đều chắc chắn tìm được.

### 4.2. Ví dụ Java chỉ quan sát cấu hình

**NativePathView.java**

~~~java
public class NativePathView {
    public static void main(String[] args) {
        System.out.println("classpath=" +
                System.getProperty("java.class.path"));
        System.out.println("nativePath=" +
                System.getProperty("java.library.path"));
        System.out.println("mapped=" +
                System.mapLibraryName("codec"));
    }
}
~~~

~~~bash
javac --release 17 NativePathView.java
java -cp . NativePathView
~~~

Không có stdout toàn cục cố định: classpath, nativePath và mapped filename phụ thuộc OS/JDK/launcher. Mẫu này không thực sự load thư viện nào.

### 4.3. JNI class được nạp từ Java path, còn JNI binary là file khác

~~~java
public final class NativeBridge {
    static {
        System.loadLibrary("codec");
    }

    public static native int sum(int a, int b);
}
~~~

**NativeBridge.java** có thể biên dịch bằng:

~~~bash
javac --release 17 NativeBridge.java
~~~

Nhưng việc khởi tạo/gọi `sum` cần JNI binary thật có tên/ABI/symbol phù hợp. Class Java có thể có trên classpath/module path mà binary không có trên native search; lỗi khi đó là native loading/linking, không phải ClassNotFoundException đối với Java bridge class.

## 5. Native access restrictions từ JDK 24/25

Theo JEP 472, JDK 24+ kiểm soát restricted native operations như `System.load`/`System.loadLibrary`. JDK 25 mặc định cảnh báo cho native access chưa được cấp quyền; chế độ `deny` có thể ném `IllegalCallerException`.

Caller ở classpath/unnamed module:

~~~bash
java --enable-native-access=ALL-UNNAMED \
    -Djava.library.path=/opt/app/native \
    -cp "app.jar:libs/*" com.acme.Main
~~~

Caller ở named module:

~~~bash
java --enable-native-access=demo.nativeapp \
    --module-path mods \
    --module demo.nativeapp/demo.nativeapp.Main
~~~

**Tách biệt:** `--enable-native-access` cấp quyền; `java.library.path` tìm binary; `--module-path` tìm modules; `-cp` tìm Java class/resource. Bật quyền không làm xuất hiện file thiếu, và có file đúng path không tự cấp quyền. JDK 17/21 không có cùng chính sách/flag như JDK 25.

## 6. Resource lookup không phải native lookup

Một file `config/app.properties` đóng gói như resource thường đọc qua ClassLoader:

~~~java
try (var stream = Thread.currentThread()
        .getContextClassLoader()
        .getResourceAsStream("config/app.properties")) {
    if (stream == null) {
        throw new IllegalStateException("Missing resource");
    }
    // Xử lý stream tại đây.
}
~~~

Snippet này cần nằm trong method xử lý IOException. Nó tra classloader resources, không dùng `java.library.path`. Named module có thêm quy tắc resource encapsulation và `Module.getResourceAsStream`; resource không tìm thấy không đồng nghĩa Java class không load được.

## 7. Chẩn đoán theo đúng lỗi

| Lỗi | Tầng cần kiểm tra |
| --- | --- |
| `ClassNotFoundException` | Binary name, classpath, loader delegation |
| `NoClassDefFoundError` | Runtime dependency, linkage hoặc init failure trước đó |
| `FindException` “Module not found” | Module path, root modules, requires |
| `ResolutionException` | Module conflicts, split packages, readability graph |
| `IllegalAccessError`/`InaccessibleObjectException` | Exports, opens, module access |
| `UnsupportedClassVersionError` | Java runtime version và major bytecode |
| `UnsatisfiedLinkError` | Native filename/location, native ABI, missing dependency hoặc symbol |
| `IllegalCallerException` trên JDK mới | Native access policy của caller module |
| Chạy IDE được nhưng `java -jar` fail | Manifest/dependency distribution/classpath |

**Quy trình thực tế:** đọc lỗi đầu tiên và cause → xác định artifact thiếu (`.class`, named module hay DLL/SO) → ghi `java -version` và lệnh launch → kiểm tra đúng path/loader/module graph/native linker → sửa dependency packaging/version rồi chạy lại. Không đổi đồng thời cả ba paths theo phỏng đoán.

Lệnh hỗ trợ:

~~~bash
java -version
java --help
java --list-modules
jar --list --file libs/library.jar
jar --describe-module --file libs/library.jar
java --show-module-resolution --module-path mods \
    --module demo.consumer/demo.consumer.Main
~~~

Các ví dụ module/JAR trong lệnh cần được tạo hoặc thay bằng file thật. Nếu dùng HotSpot có unified logging, `java -Xlog:class+load=info ...` có thể cung cấp dấu vết class loading, nhưng định dạng log không phải hợp đồng JLS.

## 8. Checklist và câu hỏi ôn tập

- Classpath tìm Java class/resource trong unnamed module, module path làm module discovery/resolution, native path tìm binary của OS.
- Một JAR có mặt trên module path chưa chắc đã được **resolved**.
- Automatic module có tên; unnamed module từ classpath không có tên.
- Một loader thấy class chưa chắc module caller được phép truy cập package.
- Classpath separator Unix là `:`, Windows là `;`.
- `System.loadLibrary("codec")` không nhận nguyên tên `libcodec.so` làm argument.
- Đặt DLL trong JAR không tự khiến OS linker mở DLL.
- `java.library.path` không quyết định toàn bộ việc tìm dependent native libraries.
- Chạy `java -jar` không ghép thêm `-cp` theo cách launch main class.
- `--enable-native-access` ở JDK mới không thay `java.library.path`.
- Thay system properties sau startup không bảo đảm reload đường tìm của built-in loader.

## 9. Tài liệu chính thức

1. [Java launcher JDK 25](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html) — `--class-path`, `--module-path`, `--module`, `--enable-native-access`.
2. [javac JDK 25](https://docs.oracle.com/en/java/javase/25/docs/specs/man/javac.html) — compiler paths.
3. [ClassLoader Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/ClassLoader.html) — class loading, resource lookup, `findLibrary`.
4. [System Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/System.html) — `load`, `loadLibrary`, `mapLibraryName`.
5. [ModuleFinder Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/module/ModuleFinder.html) — explicit và automatic modules.
6. [JEP 261](https://openjdk.org/jeps/261) — Java Platform Module System.
7. [JEP 472](https://openjdk.org/jeps/472) — restricted JNI native access và cảnh báo từ JDK 24.

**Ghi nhớ:** Trước khi sửa đường tìm kiếm, phân loại đúng Java class, Java module hoặc native binary. Đây là ba cơ chế tách biệt, cần công cụ và phương án xử lý riêng.
