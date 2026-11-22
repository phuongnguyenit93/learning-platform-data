# Extension Class Loader trong Java 8 và thay đổi từ Java 9

> **Ngữ cảnh:** Java Core → ClassLoader → Loader tích hợp. Bài này giải thích **extension class loader của Java 8**, cơ chế tìm JAR trong extension directories, và vì sao từ **Java 9** cơ chế đó bị xóa trong khi **platform class loader** vẫn tồn tại. Trọng tâm là cách đọc hệ phân cấp loader, chẩn đoán lỗi và chuyển một ứng dụng từ JDK 8 sang JDK 9+ mà không lệ thuộc chi tiết nội bộ HotSpot.

## 1. Câu trả lời cần nhớ trước tiên

**JDK 8:** Java cung cấp cơ chế *installed/optional extensions*. Đặt JAR vào một **extension directory** của Java runtime cho phép JDK tìm thấy thư viện ngoài mà ứng dụng không cần liệt kê JAR ấy trên application class path. Một built-in loader thường gọi là **extension class loader** đóng vai trò nạp chúng.

**JDK 9 trở đi:** Cơ chế **extension directories** đã bị **loại bỏ**. Cách cũ như đặt JAR vào `lib/ext` hoặc truyền `-Djava.ext.dirs=...` không còn được hỗ trợ. Thư viện ứng dụng cần được khai báo rõ bằng **class path**, **module path** hoặc một cơ chế nạp do ứng dụng quản lý.

**Nhưng:** Bản thân vị trí loader ở giữa bootstrap và application **không biến mất**. Kể từ Java 9, vai trò built-in loader này được gọi là **platform class loader**, cung cấp công khai qua `ClassLoader.getPlatformClassLoader()`. Nó phục vụ các lớp nền tảng/JDK theo thiết kế runtime modular, **không tiếp tục làm trình quét JAR trong `lib/ext`**.

Đây là ba điều khác nhau cần tách bạch:

1. **Tên/role loader:** Extension loader (JDK 8) → platform loader (JDK 9+).
2. **Cơ chế triển khai thư viện tùy ý:** `java.ext.dirs` / `lib/ext` (JDK 8) → **bị xóa** từ JDK 9.
3. **Bộ tổ chức class của JDK:** `rt.jar` cùng các JAR nội bộ (JDK 8) → **modular runtime image** và JPMS (JDK 9+).

Đổi tên loader **không** có nghĩa `lib/ext` đã chuyển sang một thư mục “platform/ext” mới.

## 2. Java 8: extension class loader ở đâu trong delegation chain?

Với launcher và loader built-in mặc định của **Oracle/OpenJDK 8**, mô hình đơn giản:

~~~text
                       Bootstrap Class Loader
                    (thường biểu diễn bằng null)
                                |
                                v
              Extension Class Loader (ExtClassLoader)
                 JRE_HOME/lib/ext và extension dirs
                                |
                                v
            Application / System Class Loader (AppClassLoader)
                  -cp / -classpath / CLASSPATH
                                |
                                v
                 Custom loaders do ứng dụng tạo
~~~

Mũi tên trong hình đi từ **parent** xuống **child**; khi cần tìm lớp, phương thức `loadClass` mặc định thường *delegate lên parent trước* rồi mới `findClass` ở child. Do đó search precedence điển hình của launcher JDK 8 là:

1. Bootstrap: nhiều class nền tảng từ JDK/JRE, ví dụ phần lớn class lõi trong `rt.jar`.
2. Extension loader: thư viện được cài ở extension directories.
3. Application loader: class của ứng dụng và dependency trên `-cp`.

**Hệ quả:** Nếu một class cùng binary name nằm cả trong extension JAR và application class path, bản mà parent extension loader tìm thấy có thể **che** bản ứng dụng mong đợi. Đây là một nguồn “chạy đúng trên máy A, sai trên máy B” vì thư viện được cài sẵn ở JRE khác nhau.

### 2.1. Extension directories là gì?

Trong cách đóng gói JDK/JRE 8 truyền thống, JAR được đặt vào các vị trí như:

- `<JRE_HOME>/lib/ext` (trên nhiều cài đặt JDK 8, Java runtime nằm dưới `<JDK_HOME>/jre`).
- Extension directory dùng chung trên một số hệ điều hành/distribution.
- Vị trí do thuộc tính hệ thống `java.ext.dirs` quy định theo cơ chế Java 8.

Tên “installed extension” biểu thị cách triển khai **mức runtime**, không phải khái niệm extension giống browser plugin hay Java module. Ứng dụng không cần truyền `-cp` riêng cho các JAR mà extension loader tìm được trong cấu hình runtime đó.

Hai cấu hình cần phân biệt:

| Cấu hình Java 8 | Ai thường tìm thấy? | Phạm vi ảnh hưởng |
| --- | --- | --- |
| `<JRE_HOME>/lib/ext/vendor.jar` | Extension loader | Những ứng dụng dùng cùng JRE có thể thấy thư viện; gây xung đột toàn runtime |
| `-Djava.ext.dirs=some/extdir` | Cơ chế extension loader của JDK 8 | Phụ thuộc đúng cơ chế JDK 8; không có ý nghĩa trên JDK 9+ |
| `java -cp app.jar:vendor.jar Main` | Application class loader theo launcher mặc định | Chỉ tiến trình được cấu hình class path đó |
| Custom `URLClassLoader` nạp URL JAR | Loader do ứng dụng tạo | Do ứng dụng quản lý phạm vi, quyền và vòng đời |

Lưu ý path separator của `-cp`: trên Unix/Linux/macOS là dấu **`:`**, trên Windows là dấu **`;`**. Đừng sao chép nguyên lệnh giữa hệ điều hành mà bỏ qua dấu này.

**Không nên chỉnh sửa thư mục JRE cài đặt chung để làm thí nghiệm.** Các bước thực hành ở phần sau dùng thư mục thư viện riêng trong workspace và chỉ chạy với một JDK 8 kiểm soát được.

### 2.2. Extension loader có phải là một class trong Java SE API?

Các class triển khai như `sun.misc.Launcher$ExtClassLoader` (JDK 8 HotSpot) là **chi tiết nội bộ**. Đặc tả API không yêu cầu mọi JVM giữ chính xác tên, package hay cấu trúc class đó. Dùng `getParent()`, `getClassLoader()` và API chuẩn để quan sát hành vi; không import `sun.misc.Launcher` và không so sánh chuỗi `getClass().getName()` để quyết định logic.

Trong JDK 8, public API `ClassLoader` **chưa có** `getPlatformClassLoader()`. Thử gọi method ấy trong mã được biên dịch cho `--release 8` sẽ không hợp lệ vì API này ra đời từ Java 9.

## 3. Vì sao extension mechanism bị xóa từ Java 9?

Java 9 đưa vào **Java Platform Module System (JPMS)** với tập module có tên, quan hệ `requires` / `exports` và runtime image modular. Thay đổi này có nhiều động cơ: mô tả dependency rõ ràng, đóng gói và kiểm soát API nội bộ, thiết lập runtime image có thể tùy chọn module, hỗ trợ công cụ như `jlink`.

Extension mechanism cũ tạo ra một “kênh cài đặt ngầm”:

- JAR tự động được tìm qua JRE mà không xuất hiện trong dependency/app launch configuration.
- Phiên bản JAR có thể khác trên từng máy, làm kết quả class loading khó tái hiện.
- Extension JAR có thể chiếm precedence trước JAR của ứng dụng.
- Sao chép JAR vào image JDK/JRE phá vỡ tính bất biến của runtime và làm việc quản lý cập nhật/phát hành phức tạp.

Từ **JDK 9**, extension directories không còn là nơi runtime tự động quét để nạp thư viện. Cấu hình bằng `java.ext.dirs` bị từ chối, thay vì ngầm giữ hành vi cũ. Điều này là thay đổi **được công bố trong hướng dẫn migration**, không chỉ một tối ưu tùy ý ở HotSpot.

### 3.1. Đối chiếu trước và sau

| Chủ đề | Java 8 | Java 9+ |
| --- | --- | --- |
| Built-in loader trung gian | Thường gọi `ExtClassLoader` | **Platform class loader** |
| API công khai nhận loader trung gian | Chủ yếu quan sát `getParent()` trong cấu hình mặc định; không có `getPlatformClassLoader()` | `ClassLoader.getPlatformClassLoader()`, từ Java 9 |
| Cơ chế tự tìm JAR trong `lib/ext` | Có | **Đã xóa** |
| `-Djava.ext.dirs` | Cơ chế legacy của JDK 8 | Không được hỗ trợ; launcher báo lỗi |
| Hệ class nền tảng | Nhiều class trong `rt.jar` và JAR JRE | Các **modules** trong modular runtime image |
| Nguồn URL thường thấy của `java/lang/Class.class` | `jar:file:.../rt.jar!...` | `jrt:/java.base/java/lang/Class.class` |
| Application loader | Trên HotSpot 8 thường là một `URLClassLoader` | Trên OpenJDK 9+ là loại nội bộ khác, **không mặc định là `URLClassLoader`** |
| Thư viện ngoài ứng dụng | Class path hoặc cài extension JAR | Class path, module path hoặc custom loader |
| Khả năng truy cập code trong module | Chưa có JPMS | Chịu thêm kiểm tra readability, exports, opens |
| Override phần chuẩn của JDK | Có cơ chế endorsed standards cũ, tách khỏi extensions | Endorsed directories cũng bị xóa; một số module được nâng cấp qua **upgrade module path** |

**Chú ý:** Không suy ra “Java 9 đổi toàn bộ Java runtime thành modules nên mọi JAR đều là named module”. JAR chạy trên **class path** vẫn thuộc **unnamed module**; JAR đặt trên **module path** có thể là **automatic module** hoặc explicit named module tùy nội dung và cách resolve.

### 3.2. “Extension loader được giữ lại dưới tên platform loader” nghĩa chính xác là gì?

Oracle migration guide giải thích: extension class loader được **đổi tên thành platform class loader** trong hệ built-in loaders. Câu này nói về **vai trò lớp loader** chứ không hồi sinh cơ chế “JAR cài vào `lib/ext` được tìm tự động”.

Mô hình Java 9+ điển hình:

~~~text
Bootstrap loader (VM built-in, API có thể trả null)
       |
       v
Platform loader   <-- ClassLoader.getPlatformClassLoader()
       |
       v
Application/System loader <-- ClassLoader.getSystemClassLoader()
       |
       v
Custom loader nếu ứng dụng tạo
~~~

Các điểm chính:

- Mọi **platform class** đều phải **visible** qua platform loader, nhưng không nhất thiết do platform loader **define**. Một số class thuộc bootstrap loader; API `getClassLoader()` của những class này trả `null`.
- Bootstrap trong JDK 9+ định nghĩa ít class/module hơn mô hình JDK 8. Nếu custom loader trước kia chọn parent `null` và ngầm tin rằng nó nhìn thấy **toàn bộ** class nền tảng, giả định đó có thể sai sau migration.
- Platform loader có thể phải thực hiện **delegation đặc biệt** cho một số module đã được nâng cấp. Vì vậy sơ đồ parent-child chỉ là mô hình nền; không nên khẳng định mọi class chỉ được nhìn thấy qua một đường parent-first duy nhất.
- Runtime module readability/access và classloader delegation là hai cơ chế **khác nhau**. Class có thể tìm được nhưng caller vẫn không được phép truy cập package của module ấy.

## 4. Hai chương trình quan sát loader — không phụ thuộc tên internal class

### 4.1. Một source chạy được trên JDK 8 và JDK 9+

Tệp **`LoaderCompatibility.java`**, không dùng trực tiếp API mới tại compile time:

~~~java
public final class LoaderCompatibility {
    public static void main(String[] args) {
        ClassLoader system = ClassLoader.getSystemClassLoader();
        ClassLoader caller = LoaderCompatibility.class.getClassLoader();

        boolean hasPlatformApi;
        try {
            ClassLoader.class.getMethod("getPlatformClassLoader");
            hasPlatformApi = true;
        } catch (NoSuchMethodException ex) {
            hasPlatformApi = false;
        }

        System.out.println("platform API available: " + hasPlatformApi);
        System.out.println("caller uses system: " + (caller == system));
        System.out.println("system has parent: " + (system.getParent() != null));
        System.out.println("String bootstrap: "
                + (String.class.getClassLoader() == null));
    }
}
~~~

Biên dịch trên **JDK 8**:

~~~bash
javac LoaderCompatibility.java
java -cp . LoaderCompatibility
~~~

Hoặc biên dịch trên **JDK 9+** nhưng giữ API/bytecode mục tiêu Java 8:

~~~bash
javac --release 8 LoaderCompatibility.java
java -cp . LoaderCompatibility
~~~

Output kỳ vọng với **JDK 8 Oracle/OpenJDK mặc định và class path**:

~~~text
platform API available: false
caller uses system: true
system has parent: true
String bootstrap: true
~~~

Output kỳ vọng khi chạy **cùng class đã biên dịch** trên **JDK 17/21/25 OpenJDK mặc định và class path**:

~~~text
platform API available: true
caller uses system: true
system has parent: true
String bootstrap: true
~~~

Dòng đầu khác nhau vì `ClassLoader.getPlatformClassLoader()` chỉ xuất hiện từ Java 9. Ba dòng còn lại kiểm tra đặc tính của **môi trường chạy mặc định**; nếu launch bằng custom system loader, module layer hay môi trường container đặc biệt, không xem chúng là output bất biến của mọi JVM.

**Vì sao dùng reflection?** Viết thẳng `ClassLoader.getPlatformClassLoader()` trong source này sẽ khiến `javac --release 8` không biên dịch được. Reflection ở đây chỉ dùng để **phát hiện tồn tại phương thức**, không có nhu cầu mở quyền truy cập module nội bộ.

### 4.2. Sử dụng API được hỗ trợ từ JDK 9

Tệp **`PlatformLoaderProbe.java`** (chỉ biên dịch từ Java 9 trở lên):

~~~java
public final class PlatformLoaderProbe {
    public static void main(String[] args)
            throws ClassNotFoundException {
        ClassLoader platform = ClassLoader.getPlatformClassLoader();
        ClassLoader application = ClassLoader.getSystemClassLoader();

        System.out.println("platform exists: " + (platform != null));
        System.out.println("app sees platform as parent: "
                + (application.getParent() == platform));
        System.out.println("platform sees String: "
                + (platform.loadClass("java.lang.String") == String.class));
        System.out.println("String defined by bootstrap: "
                + (String.class.getClassLoader() == null));
    }
}
~~~

~~~bash
javac PlatformLoaderProbe.java
java -cp . PlatformLoaderProbe
~~~

Output điển hình với **OpenJDK 17/21/25, system loader mặc định**:

~~~text
platform exists: true
app sees platform as parent: true
platform sees String: true
String defined by bootstrap: true
~~~

Dòng thứ ba và tư minh họa sự khác nhau giữa **visible to** và **defined by**. Platform loader **nhìn thấy `java.lang.String` qua bootstrap**, chứ không tự định nghĩa một bản `String` khác. Chưa có cơ sở nào để khẳng định “mọi class Java SE đều do platform loader định nghĩa”.

Không cast `platform` hay `application` về `URLClassLoader` để lấy danh sách URL. Trên nhiều JDK 9+ HotSpot cast sẽ thất bại:

~~~java
// Phản ví dụ: KHÔNG dùng trong mã chuyển đổi JDK 9+.
java.net.URLClassLoader urls =
        (java.net.URLClassLoader) ClassLoader.getSystemClassLoader();
~~~

Nếu cần class path đã truyền cho launcher, hãy lưu cấu hình launch/build của ứng dụng. Nếu thực sự cần nạp JAR theo URL động, ứng dụng có thể **tự tạo** `URLClassLoader` với parent phù hợp; đây là một loader **do ứng dụng sở hữu**, không phải built-in system loader.

## 5. Thực hành migration: đưa một extension JAR sang class path

Ví dụ có một thư viện nhỏ trong package `legacy.greeting` và chương trình client. Cấu trúc thư mục minh họa:

~~~text
demo/
├─ src/
│  ├─ legacy/
│  │  └─ greeting/
│  │     └─ Greeting.java
│  └─ LegacyClient.java
└─ build/             (được tạo bởi lệnh biên dịch)
~~~

Tệp **`src/legacy/greeting/Greeting.java`**:

~~~java
package legacy.greeting;

public final class Greeting {
    private Greeting() { }

    public static String message() {
        return "hello from library";
    }
}
~~~

Tệp **`src/LegacyClient.java`**:

~~~java
import legacy.greeting.Greeting;

public final class LegacyClient {
    public static void main(String[] args) {
        System.out.println(Greeting.message());

        ClassLoader library = Greeting.class.getClassLoader();
        ClassLoader application = LegacyClient.class.getClassLoader();
        System.out.println("same defining loader: "
                + (library == application));
    }
}
~~~

### 5.1. Chuẩn bị JAR và class của client

Các lệnh sau chạy từ thư mục `demo` trong **POSIX shell**. Để thử cả Java 8 và Java 9+, hãy xây JAR và client bằng JDK 8 để không bị lỗi bytecode version khi chạy bản cũ:

~~~bash
mkdir -p build/libclasses build/clientclasses build/extensions
javac -d build/libclasses src/legacy/greeting/Greeting.java
jar cf build/greeting.jar -C build/libclasses .
javac -cp build/greeting.jar -d build/clientclasses src/LegacyClient.java
~~~

Các đường dẫn tương đối có thể thay bằng đường dẫn tương ứng trong PowerShell hoặc Gradle/Maven. Bước trên chỉ tạo artifact của **bài thí nghiệm**, không đụng tới `JAVA_HOME`.

### 5.2. Java 8: dùng extension directory riêng, có kiểm soát

Trong môi trường thực hành Java 8, sao chép `greeting.jar` vào `build/extensions`. Sau đó chạy:

~~~bash
cp build/greeting.jar build/extensions/
java -Djava.ext.dirs=build/extensions -cp build/clientclasses LegacyClient
~~~

Output kỳ vọng với **Oracle/OpenJDK 8 launcher mặc định**:

~~~text
hello from library
same defining loader: false
~~~

**Giải thích:** client được application loader định nghĩa; `Greeting` được extension loader (parent của application loader trong JDK 8) tìm thấy. Hai lớp không có cùng **defining loader**. Cách này cố ý mô phỏng cơ chế extension cũ mà không sao chép thư viện vào JRE chia sẻ.

Nếu chuyển dòng chạy trên sang JDK 9+, launcher sẽ **từ chối** `-Djava.ext.dirs=...`. Đừng chẩn đoán nhầm là `ClassNotFoundException` trong ứng dụng: lỗi có thể xảy ra **trước cả khi `main` chạy**.

### 5.3. Java 9+: chuyển JAR sang application class path

Sau khi **bỏ** property cũ, chạy với hai mục trên class path.

Linux/macOS:

~~~bash
java -cp "build/clientclasses:build/greeting.jar" LegacyClient
~~~

Windows PowerShell / Command Prompt:

~~~powershell
java -cp "build/clientclasses;build/greeting.jar" LegacyClient
~~~

Output kỳ vọng trên JDK 9+ launcher mặc định:

~~~text
hello from library
same defining loader: true
~~~

Không có extension mechanism: client và library đều nằm trong **application class path**, nên cùng system/application loader trong cấu hình thông thường. **API và hành vi nghiệp vụ vẫn đúng** dù class loader trả về đã đổi.

**Đừng ép hai loader phải khác nhau sau migration.** Thay đổi role/identity của loader khi chuyển deployment mode là điều mong đợi. Logic nghiệp vụ không nên phụ thuộc một JAR được nạp bởi `ExtClassLoader` để hoạt động.

### 5.4. Bài học thực tế từ ví dụ

- Thư viện dùng chung không nên được “cài toàn hệ thống” một cách bí mật; project nên khai báo dependency có version.
- Parent-first khiến extension JAR cũ có thể thắng phiên bản trên application class path trong JDK 8; di chuyển sang class path có thể làm thay đổi bản class được chọn khi JAR trùng lặp.
- Khi class identity đổi, `instanceof`, cast, serialized metadata, reflective lookup và caches có thể cho kết quả khác; kiểm tra dữ liệu trao đổi qua ranh giới loader.
- Nếu build bằng JDK mới rồi chạy bằng JDK 8, phải đặt target tương thích (`javac --release 8` trên compiler hỗ trợ) **và** bảo đảm dependency/API tương thích. JDK 8 hiểu class file major **52**, trong khi JDK 17 mặc định tạo major **61**.

## 6. Ba cách triển khai thư viện đúng trên Java 9+

### Cách A — Class path: phù hợp ứng dụng JAR legacy

Lệnh chạy rõ JAR chứa dependency:

~~~bash
# Linux/macOS
java -cp "app.jar:libs/*" com.example.Main
~~~

~~~powershell
# Windows
java -cp "app.jar;libs/*" com.example.Main
~~~

Khi viết chương trình thực, thay `com.example.Main` bằng main class trong ứng dụng. Lệnh dùng **wildcard class path** để lấy JAR nằm trực tiếp trong `libs`; nó **không quét đệ quy** các thư mục con. Build tool như Gradle/Maven thường quản lý dependency và tạo class path thay cho việc viết thủ công.

Ưu điểm: chuyển đổi tương đối trực tiếp từ JDK 8; JAR không bắt buộc có `module-info.class`. Hạn chế: các class trên class path cùng nằm trong unnamed module tương ứng loader; không nhận ngay strong encapsulation của named modules.

### Cách B — Module path: cho ứng dụng dùng JPMS

Một JAR có explicit `module-info.class` được chạy như named module, ví dụ sau khi bạn đã xây `app.jar` và các dependency thích hợp:

~~~bash
java --module-path "mods:libs" \
     --module com.example.app/com.example.Main
~~~

Windows thay ký tự phân tách trong module path thành `;` (hoặc dùng cách build tool sinh lệnh tương ứng). Module name và main class ở lệnh trên biểu thị **cách viết cú pháp**; dự án thật phải dùng đúng module descriptor và tên package của mình.

Đối với JAR legacy không có module descriptor, Java có cơ chế **automatic modules** khi đặt JAR lên module path. Nhưng để module được **resolved**, ứng dụng phải tạo graph phù hợp (chẳng hạn `requires` hoặc cấu hình `--add-modules`); đặt một JAR bất kỳ lên module path **không** có nghĩa tất cả class tự động visible.

Đường classpath và module path không thay thế nhau một cách máy móc: package conflict, split packages, exports/opens, service provider và module readability đều cần kiểm tra khi chuyển.

### Cách C — Custom loader khi có nhu cầu plugin isolation

Nếu ứng dụng chủ động nạp plugin theo phiên bản/runtime, custom loader hoặc `URLClassLoader` do ứng dụng tạo vẫn có thể hợp lệ:

~~~java
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;

public class PluginLoaderExample {
    public static void main(String[] args) throws Exception {
        URL jar = Path.of("plugins", "plugin.jar")
                      .toUri().toURL();

        try (URLClassLoader pluginLoader = new URLClassLoader(
                new URL[] { jar },
                ClassLoader.getPlatformClassLoader())) {
            // Chỉ minh họa tạo loader và giải phóng resource.
            System.out.println(pluginLoader.getParent()
                    == ClassLoader.getPlatformClassLoader());
        }
    }
}
~~~

Tệp **`PluginLoaderExample.java`**, biên dịch/chạy với Java 17+:

~~~bash
javac PluginLoaderExample.java
java PluginLoaderExample
~~~

Output:

~~~text
true
~~~

Bài toán ở đây minh họa **parent được chọn bằng API công khai**; ví dụ **không yêu cầu** `plugins/plugin.jar` có tồn tại để tạo một URL. Nếu cần tải lớp từ JAR, ứng dụng phải cung cấp file thật, gọi `loadClass` hoặc dùng module layer, và quản lý vòng đời/các dependency.

**Lưu ý lớn:** Chọn `ClassLoader.getPlatformClassLoader()` làm parent cho plugin sẽ **không mặc nhiên cấp quyền thấy các interface do application loader định nghĩa**. Nếu plugin cần dùng chung SPI/interface của host, thiết kế ranh giới parent phù hợp (thường dùng loader nhìn thấy contract chia sẻ), tránh duplicate class identity. Chọn platform parent khi mục tiêu là chỉ kế thừa platform classes và bạn hiểu dependency cụ thể.

`URLClassLoader.close()` giải phóng tài nguyên có thể đóng; nó **không bảo đảm class unloading tức thời**. Thread context class loader, cache, threads, listeners và static registry có thể tiếp tục giữ loader.

## 7. Không nhầm extension, endorsed và upgrade module path

Trong JDK 8 từng tồn tại ít nhất **hai cơ chế cũ khác nhau**:

1. **Extension mechanism**: các JAR của thư viện/optional packages tại `lib/ext`, cấu hình `java.ext.dirs`. Đã xóa từ JDK 9; thay bằng explicit class path/module path hoặc custom loading theo nhu cầu.
2. **Endorsed standards override mechanism**: `lib/endorsed`, `java.endorsed.dirs`, dùng thay phiên bản một số standard APIs được phép. Cũng đã xóa từ JDK 9; khi cần **nâng cấp đúng module được Java cho phép**, tìm hiểu `--upgrade-module-path` theo JPMS.

`--upgrade-module-path` **không** phải “tên mới của `java.ext.dirs`”. Nó chỉ áp dụng trong mô hình module, theo quy tắc module nào upgradeable, không có nhiệm vụ quét JAR utility tùy ý. Tương tự:

- `--patch-module` là cơ chế can thiệp nội dung **một named module cụ thể**; không dùng thay dependency bình thường.
- `--add-exports` hỗ trợ quyền truy cập package public không export trong tình huống migration; **không thêm** class/JAR bị thiếu.
- `--add-opens` liên quan deep reflection theo module; **không** bật lại extension class loader.
- `-Xbootclasspath/a` nếu được JVM hỗ trợ trong một số tình huống không phải giải pháp thay thế tổng quát cho extension mechanism.

Đặt đúng vấn đề trước khi chọn option: “Không thấy JAR” là vấn đề **deployment/class path/module path**; “thấy class nhưng bị cấm truy cập” là vấn đề **module/access**.

## 8. Chi tiết cần biết khi nâng cấp từ Java 8 sang 9, 11, 17, 21+

| Bản JDK | Điểm quan trọng trực tiếp liên quan extension/class loading |
| --- | --- |
| **8** | Có extension directories và cơ chế `java.ext.dirs`. Loader trung gian thường gọi `ExtClassLoader`. Runtime truyền thống chứa `rt.jar`. |
| **9** | **Loại bỏ extension & endorsed mechanisms**; xuất hiện platform class loader, `getPlatformClassLoader()`, JPMS, modular image và `jrt:/`; system/application loader của OpenJDK không còn là `URLClassLoader`. |
| **10** | Tiếp tục mô hình JDK 9. Kiểm tra launch scripts cũ vì các flag/thư mục extension không hợp lệ. |
| **11** | Đã loại các module Java EE/CORBA theo JEP 320, nên một số class/API có trong JDK 8 không còn nằm trong JDK; không thể “sửa loader” để JDK 11 tự cung cấp lại những class đã bị loại. |
| **17** | JEP 403 áp dụng strong encapsulation đối với nhiều internal JDK APIs; mã reflection cũ có thể gặp `InaccessibleObjectException` — đây là vấn đề quyền truy cập module, tách biệt với cơ chế extension bị xóa từ 9. |
| **21, 25 và bản mới hơn** | Tiếp tục dùng built-in bootstrap/platform/application loaders với JPMS; không xây logic dựa vào tên internal class hoặc layout `lib/ext`. Các option công cụ, module graph và class file version cần được kiểm tra theo bản runtime cụ thể. |

**Cần tách phiên bản lúc biên dịch và chạy:** `ClassLoader.getPlatformClassLoader()` thuộc **API từ Java 9**, nên một class được biên dịch với API Java 8 không thể gọi trực tiếp. Ngược lại, việc class file tương thích Java 8 không bảo đảm mọi JAR/Java SE API tồn tại trên JDK mới. Migration phải kiểm tra cả API, module graph, thư viện và cấu hình start.

## 9. Chẩn đoán khi ứng dụng nâng JDK bị lỗi

### Triệu chứng A: JVM từ chối start vì `java.ext.dirs`

Ví dụ thông điệp được Oracle ghi nhận:

~~~text
<java-home>/lib/ext exists, extensions mechanism no longer supported; Use -classpath instead.
Error: Could not create the Java Virtual Machine.
~~~

Hoặc thông báo tương tự với `-Djava.ext.dirs=...`. Cách xử lý:

1. Tìm cấu hình trong start script, IDE VM options, Dockerfile, Gradle/Maven launch task, application server và biến môi trường liên quan.
2. **Bỏ** `-Djava.ext.dirs`, không tái tạo thư mục `lib/ext` trong image JDK mới.
3. Đưa JAR cần thiết vào dependency/class path/module path với phiên bản xác định.
4. Chạy lại bằng đúng runtime và kiểm tra loader thực định nghĩa class.

### Triệu chứng B: `ClassNotFoundException` / `NoClassDefFoundError` sau migration

Nguyên nhân có thể là JAR từng nằm trong extension directory nhưng không còn trên classpath/module path. `ClassNotFoundException` thường xảy ra khi explicit class lookup thất bại; `NoClassDefFoundError` có thể xảy ra khi bytecode cần class không được giải tại runtime hoặc có một nguyên nhân initialization/linkage khác. Đừng kết luận thiếu JAR chỉ từ một tên exception; đọc đầy đủ cause.

Kiểm tra artifact:

~~~bash
jar tf build/greeting.jar
java -version
java -verbose:class -cp "build/clientclasses:build/greeting.jar" LegacyClient
~~~

Mã `jar tf` liệt kê entries trong JAR; `-verbose:class` cho biết các sự kiện class loading trên nhiều JDK, nhưng format log phụ thuộc VM/version. Trong lệnh trên dấu `:` dành cho Linux/macOS; trên Windows đổi thành `;`.

JDK 9+ HotSpot hỗ trợ unified logging:

~~~bash
java -Xlog:class+load=info -cp "build/clientclasses:build/greeting.jar" LegacyClient
~~~

Dùng `java -Xlog:help` để xem tag và option VM hiện có. Đây là **công cụ chẩn đoán HotSpot**, không phải một phần giao diện ổn định của mọi JVM implementation.

### Triệu chứng C: Cast system loader sang `URLClassLoader` bị lỗi

`ClassCastException` sau upgrade thường do mã đã giả định `ClassLoader.getSystemClassLoader()` là `URLClassLoader` dựa trên HotSpot 8. Hướng xử lý: thay bằng API `ClassLoader`/`Class` khi chỉ cần nạp class/resource, hoặc tạo `URLClassLoader` riêng nếu cần URL dynamic. Không cố cast theo tên class JDK nội bộ.

### Triệu chứng D: Custom loader có parent `null` không thấy class platform

Ở JDK 8, một số mã dùng `new URLClassLoader(urls, null)` vì tin bootstrap đã thấy mọi platform class. JDK 9+ một số class nền tảng được platform loader định nghĩa chứ không phải bootstrap; chọn `ClassLoader.getPlatformClassLoader()` làm parent có thể phù hợp nếu cần nhìn thấy lớp platform. Nếu plugin cần thêm **host API**, phải chọn parent/contract phù hợp hơn.

### Triệu chứng E: `IllegalAccessError` hoặc `InaccessibleObjectException`

Có thể liên quan named modules, package exports/opens và strong encapsulation. Cần kiểm tra module path, `module-info.java` và reflective call. Chuyển `lib/ext` sang classpath **không tự giải quyết** mọi lỗi module access.

## 10. Checklist migration theo từng bước

1. **Khóa môi trường trước khi đổi:** ghi `java -version`, launcher command, `java.class.path`, build dependencies, JDK vendor, mã nguồn và image runtime đang dùng.
2. **Tìm extension assumptions:** `lib/ext`, `java.ext.dirs`, `-extdirs`, `ExtClassLoader`, `sun.misc.Launcher`, cast system loader sang `URLClassLoader` và hard-coded `rt.jar`.
3. **Lập inventory extension JAR:** tên, version, source, license, API public, các transitive dependencies và class/package overlap. Đừng đưa nguyên thư mục JDK 8 sang JDK mới.
4. **Chọn deployment mới:** class path cho ứng dụng legacy thông thường; module path khi có thiết kế JPMS; custom loader nếu thực sự quản lý plugin động.
5. **Sửa launcher/build:** bỏ `java.ext.dirs` và các tùy chọn đã xóa; khai báo dependency trong build; xác thực path separator và JARs được đóng gói cùng artifact deploy.
6. **Kiểm tra class identity:** nếu có plugin/framework, xem defining loader của interface chung, module và binary name; tránh trùng thư viện giữa host/plugin nếu chúng phải chia sẻ type.
7. **Kiểm tra tương thích bytecode:** chạy bằng JDK mục tiêu, inspect major version với `javap -verbose` khi thấy `UnsupportedClassVersionError`.
8. **Kiểm tra module access:** phân biệt missing dependency với access errors; dùng module config chính xác.
9. **Chạy lại integration tests:** đặc biệt service provider, JDBC drivers, app servers, reflection, serialization, resource lookup và nạp plugin.
10. **Triển khai tái lập:** runtime image cố định, dependency version cố định, start command rõ ràng; không yêu cầu người vận hành copy JAR thủ công vào JDK.

## 11. Câu hỏi tự kiểm tra

1. **Java 9 có xóa platform loader không?** Không. Nó có tên/API công khai mới; thứ bị xóa là cơ chế extension directories.
2. **Có thể đổi `-Djava.ext.dirs=libs` thành `-Djava.platform.dirs=libs` không?** Không có option API như vậy.
3. **Một platform class phải do platform loader định nghĩa?** Không. Nó có thể do bootstrap định nghĩa nhưng vẫn visible từ platform loader.
4. **Đặt `foo.jar` lên module path là đủ để ứng dụng chắc chắn thấy module?** Không. Module cần nằm trong graph được resolved, và package phải cho phép access.
5. **Vì sao ứng dụng Java 8 đọc đúng class nhưng JDK 9+ đọc class phiên bản khác?** Có thể do extension JAR từng đứng trước application class path; sau migration deployment/loader precedence đổi.
6. **JDK 9+ có thể dùng `URLClassLoader` cho plugin không?** Có, bằng cách **ứng dụng tự tạo loader**, không cast built-in application loader.
7. **Dùng parent `null` trong custom loader có bảo đảm thấy mọi class Java SE không?** Không; trên JDK modular, chọn platform parent nếu cần các class nền tảng mà bootstrap không define.
8. **`java.endorsed.dirs` có phải tên khác của `java.ext.dirs`?** Không. Đây là hai cơ chế legacy riêng, cùng bị loại từ JDK 9.
9. **Khi thấy `NoClassDefFoundError` có luôn là JAR missing?** Không; phải xem cause, class file compatibility và initialization/linking.
10. **Có nên viết unit test assert tên nội bộ `jdk.internal.loader.ClassLoaders$PlatformClassLoader`?** Không; kiểm tra hành vi và API được hỗ trợ.

## 12. Tài liệu gốc nên tham khảo

1. [Oracle JDK Migration Guide — New Class Loader Implementations, Removed Extension Mechanism](https://docs.oracle.com/en/java/javase/26/migrate/migrating-from-jdk-8-later-jdk-releases.html): xác nhận system loader mới, platform loader và cách xử lý `lib/ext` / `java.ext.dirs`.
2. [Oracle Java SE 8 Extension Mechanism](https://docs.oracle.com/javase/8/docs/technotes/guides/extensions/spec.html): mô tả optional packages/installed extensions và precedence cũ.
3. [Oracle Java Tutorial JDK 8 — Understanding Extension Class Loading](https://docs.oracle.com/javase/tutorial/ext/basics/load.html): mô hình bootstrap → extension → class path ở Java 8; **tài liệu lịch sử, không áp dụng triển khai thư mục `lib/ext` trên JDK mới**.
4. [`ClassLoader` Java SE 9 API](https://docs.oracle.com/javase/9/docs/api/java/lang/ClassLoader.html): tài liệu chuẩn đầu tiên có `getPlatformClassLoader()` và built-in loaders.
5. [JEP 261 — Module System](https://openjdk.org/jeps/261): module path, readability/access và thay đổi class loading để hỗ trợ JPMS.
6. [JEP 220 — Modular Run-Time Images](https://openjdk.org/jeps/220): image modular, `rt.jar` không còn như trước và các hệ quả với công cụ đọc class/resource.
7. [JDK 9 Release Notes](https://www.oracle.com/java/technologies/javase/9-relnotes.html): xác nhận removal flags và migration recommendations.
8. [JEP 320 — Remove Java EE and CORBA Modules](https://openjdk.org/jeps/320), [JEP 403 — Strongly Encapsulate JDK Internals](https://openjdk.org/jeps/403): các lỗi nâng JDK khác dễ bị nhầm thành lỗi classloader.

**Kết luận thực hành:** Khi nâng từ Java 8, hãy loại bỏ mọi đường cài JAR vào `lib/ext` và những giả định vào class loader nội bộ. Trên Java 9+, dùng **platform class loader** qua API được hỗ trợ khi cần delegation tới các lớp nền tảng, còn dependency của ứng dụng phải được mô tả rõ trong **class path/module path** hoặc trong custom loader của ứng dụng.