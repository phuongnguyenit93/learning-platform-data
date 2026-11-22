# appendToSystemClassLoaderSearch và yêu cầu với system class loader tùy chỉnh

Một Java instrumentation agent có thể cần gọi một lớp helper từ bytecode mà nó chèn vào ứng dụng. Nếu JVM không tìm thấy helper qua **class loader định nghĩa lớp chứa lời gọi**, bạn có thể gặp `NoClassDefFoundError` dù agent JAR vẫn khởi động bình thường. Một công cụ quan trọng để bố trí helper là `Instrumentation.appendToSystemClassLoaderSearch(JarFile)`: nó thêm **một JAR vào đường tìm kiếm của system class loader**, nhưng không tự làm mọi class loader trong JVM nhìn thấy JAR đó.

Bài này giải thích hợp đồng chính xác của API, cách nó làm việc với system loader mặc định và yêu cầu dành cho **custom system class loader** được chỉ định bằng `-Djava.system.class.loader=...`. Điểm thường bị bỏ sót là custom loader phải hỗ trợ một phương thức có **tên và chữ ký đặc biệt**: `appendToClassPathForInstrumentation(String)`. Ta sẽ chạy cùng một agent trên hai cấu hình class loader, xác nhận helper được nạp từ một JAR không nằm trong `-cp`, rồi phân tích các trường hợp lỗi và giới hạn về delegation, module và class resolution.

**Điều kiện thực hành:** ví dụ dùng API Java 17 và các công cụ `javac`/`jar` của JDK 17 trở lên. Mã đã được biên dịch với `javac --release 17` và chạy trên OpenJDK Zulu 24.0.2, với cả loader mặc định lẫn loader tùy chỉnh; một số thông báo của JVM ở stderr có thể khác theo vendor/phiên bản.

## 1. Vấn đề thực tế: helper được nạp bởi class loader nào?

Giả sử transformer thêm vào class nghiệp vụ một instruction tương đương:

~~~java
// Mô tả ý nghĩa bytecode đã được instrument; không phải file độc lập.
demo.helper.Greeting.message();
~~~

JVM phải resolve symbolic reference `demo/helper/Greeting` khi thực thi code có lời gọi. Việc resolve phụ thuộc vào **defining class loader của lớp đang chứa instruction**, các quy tắc delegation, và module/access rules. "Agent nhìn thấy Greeting" **không đồng nghĩa** "mọi lớp trong ứng dụng nhìn thấy Greeting".

Ví dụ các loader:

~~~text
                      Bootstrap loader
                            |
                      Platform loader
                            |
                      System/App loader  <--- helper.jar được append tại đây
                            |
                    Child / plugin loader
                            |
                   Một số lớp ứng dụng
~~~

Trong sơ đồ này, một child loader **có thể** tìm thấy helper qua parent nếu nó thực hiện delegation thích hợp và không có isolation/child-first rules cản trở. Nhưng một lớp do loader **ở phía trên** định nghĩa không thể mặc nhiên nhìn thấy classes chỉ có ở loader **con**. Nếu một plugin loader dùng chiến lược riêng, nó cũng không bắt buộc ủy quyền đúng như sơ đồ.

Vì vậy phải trả lời **hai câu hỏi riêng**:

1. `appendToSystemClassLoaderSearch` đã thêm JAR vào **system loader** thành công chưa?
2. **Lớp có bytecode được instrument** có thể resolve đúng helper thông qua loader/module của chính nó không?

Bài thực hành ở dưới cố tình dùng `Class.forName(name, true, ClassLoader.getSystemClassLoader())` để chứng minh câu hỏi thứ nhất. Nó **không suy diễn** từ đó rằng một lời gọi helper trong bất kỳ webapp/bootstrap/custom loader nào cũng luôn hoạt động.

## 2. Hợp đồng của `Instrumentation.appendToSystemClassLoaderSearch`

Chữ ký JDK 17:

~~~java
void appendToSystemClassLoaderSearch(java.util.jar.JarFile jarfile);
~~~

`Instrumentation` là object JVM cấp cho `premain(String, Instrumentation)` hoặc `agentmain(String, Instrumentation)`; không tạo bằng `new Instrumentation()`. Khi agent gọi API trên, một JAR được thêm vào danh sách nơi **system class loader** tìm classes và resources nếu quá trình tìm kiếm trước đó không thành công.

Các đặc điểm quan trọng từ Javadoc:

- Phương thức nhận một **`JarFile`**, không nhận thư mục, `URL`, `Path` hay `ClassLoader`.
- Khi system loader không tìm được một class qua delegation/đường tìm kiếm sẵn có, nó có thể tìm thêm entries trong JAR đã được append.
- Có thể gọi nhiều lần để thêm nhiều JAR; các JAR được thêm sẽ được tìm theo **thứ tự các lần append**.
- JAR nên chỉ chứa những instrumentation classes/resources cần được định nghĩa qua system loader. Thêm một JAR khổng lồ với classes trùng tên thư viện ứng dụng có thể tạo xung đột khó chẩn đoán.
- Giá trị property **`java.class.path` không thay đổi** do lời gọi này. Đọc `System.getProperty("java.class.path")` không thể thay thế kiểm tra class loader thực tế.
- Nếu system loader **không hỗ trợ append**, API có thể ném `UnsupportedOperationException`.
- Truyền `null` thay vì `JarFile` gây `NullPointerException`.
- Phương thức không làm những classes **đã định nghĩa** được nạp lại, không tự redefine/retransform class, và không thêm bất kỳ quyền module access nào.

Điểm cuối rất dễ nhầm: **"append vào search path" không phải "hot swap"**. Nếu JVM đã định nghĩa `demo.helper.Greeting` từ một JAR khác, thêm JAR mới trùng tên không thay thế `Class<?>` hiện có. Còn nếu JVM đã thất bại khi resolve một symbolic reference, có thêm giới hạn về **resolution failure được nhớ lại** (mục 7).

### 2.1. Khác `-cp` và khác JAR agent

So sánh:

| Cơ chế | Kích hoạt | Tác dụng chính |
| --- | --- | --- |
| `-cp app-out` | JVM launcher | Thiết lập application class path ban đầu |
| `-javaagent:agent.jar` | JVM launcher | Nạp agent class qua manifest `Premain-Class` trước `main` |
| `inst.appendToSystemClassLoaderSearch(helperJar)` | Code của agent | Thêm helper JAR vào đường tìm kiếm của system loader trong JVM đang chạy |
| `inst.appendToBootstrapClassLoaderSearch(helperJar)` | Code của agent | Thêm JAR vào đường tìm kiếm của **bootstrap loader**, là cơ chế khác |
| `ClassLoader.getSystemClassLoader().loadClass(...)` | Code runtime | Yêu cầu system loader load một class theo quy tắc của chính loader |

`appendToSystemClassLoaderSearch` **không tương đương** việc mở một class loader mới bằng `new URLClassLoader(...)`. Nó tác động lên đường tìm kiếm **của system loader hiện có**, kể cả khi system loader là một custom implementation tương thích.

Trong ví dụ bên dưới, `agent.jar` và `helper.jar` là **hai artifact riêng**: agent cung cấp `premain`; helper.jar chứa `demo.helper.Greeting` mà system loader sẽ tìm sau khi append.

## 3. Điều kiện đặc biệt khi có custom system class loader

Java cho phép thay system class loader mặc định bằng property khi khởi động:

~~~bash
java "-Djava.system.class.loader=CustomSystemLoader" -cp app-out Main
~~~

Lúc `ClassLoader.getSystemClassLoader()` được khởi tạo lần đầu, JVM dùng default system loader để load lớp `CustomSystemLoader`. Lớp này **phải có public constructor** nhận đúng một `ClassLoader` làm parent:

~~~java
public CustomSystemLoader(ClassLoader parent) {
    super(..., parent);
}
~~~

Đây là một mẫu constructor, không phải source độc lập. Parent do JVM cung cấp là **default system class loader**, không nên lấy bằng việc gọi lại `ClassLoader.getSystemClassLoader()` từ constructor. Javadoc cảnh báo nếu gây khởi tạo system loader đệ quy, có thể phát sinh `IllegalStateException`. Đảm bảo class loader implementation có thể được tìm bằng default system loader tại startup, thường là đặt `CustomSystemLoader.class` trên classpath ban đầu.

**Thêm một hợp đồng chỉ dành cho instrumentation:** custom system loader phải định nghĩa method tên:

~~~java
void appendToClassPathForInstrumentation(String jarPath);
~~~

- Tên **phải chính xác** là `appendToClassPathForInstrumentation`.
- Tham số duy nhất là `java.lang.String`. Trong implementation JVM phổ biến, method trả về `void`, như ví dụ.
- **Không bắt buộc method có modifier `public`** theo `Instrumentation` Javadoc; ví dụ chọn `public` để dễ thấy và dễ kiểm thử.
- JVM gọi method này và đưa vào **giá trị `jarfile.getName()`** của `JarFile` đã được truyền cho `appendToSystemClassLoaderSearch`; **không được mặc định đó luôn là một absolute path**. Custom method nên chuẩn hóa path theo môi trường nếu cần.
- Custom method phải thực sự **thêm JAR vào search path mà chính loader sẽ dùng** khi tìm class. Chỉ lưu chuỗi vào một danh sách mà `findClass` không bao giờ đọc thì không đáp ứng mục tiêu.
- Method này không nên ném lỗi; phải xử lý path/URL và các trường hợp không hợp lệ theo chính sách có kiểm thử. Nếu không hỗ trợ hoặc triển khai sai, startup/load agent hay lời gọi append có thể thất bại.

Custom loader là một bộ phận của **runtime infrastructure**, không phải chỉ một class phụ trang trí. Nếu cấu hình `java.system.class.loader` nhưng thiếu method hỗ trợ instrumentation, việc **nạp agent ngay khi startup** cũng có thể thất bại trước lúc `premain` của agent chạy. Nguyên nhân là cơ chế nạp agent phải tương tác với system-loader search path, không chỉ với helper JAR được append sau đó.

### 3.1. Có thể làm gì bên trong custom method?

Một cách đơn giản là xây custom loader từ `URLClassLoader`, dùng method `addURL(...)` được thừa kế ở mức `protected` để bổ sung URL của JAR. Nhưng lưu ý:

- `ClassLoader.getSystemClassLoader()` mặc định trên các JDK hiện đại **không nhất thiết là `URLClassLoader`**. Đừng ép kiểu loader mặc định thành `URLClassLoader` để gọi `addURL`.
- Việc một class loader **kế thừa** `URLClassLoader` không tự tạo ra method đặc biệt của instrumentation; bạn phải **định nghĩa** `appendToClassPathForInstrumentation(String)`.
- Khi một JAR được append, system loader vẫn có thể **delegate lên parent trước**. Nếu parent đã có class trùng tên, kết quả có thể là class của parent; JAR mới không có quyền ghi đè class đã được parent load.
- Nếu loader chứa state cần synchronized/locking, phải xem xét thread safety; class loading và việc append có thể cùng xảy ra khi hệ thống đang hoạt động.

Ở mục 5, ta viết một loader rất nhỏ có đúng constructor và method đặc biệt; class helper được load bằng **chính system loader mới** để kiểm chứng append.

## 4. Flow từ agent tới custom loader

~~~text
java "-Djava.system.class.loader=CustomSystemLoader"
     -javaagent:agent.jar=helper.jar
     -cp app-out Main
          |
          v
JVM tạo CustomSystemLoader(parent = default system loader)
          |
          v
JVM chuẩn bị nạp agent (custom loader phải hỗ trợ add JAR)
          |
          v
Agent.premain("helper.jar", instrumentation)
          |
          v
new JarFile("helper.jar")
          |
          v
inst.appendToSystemClassLoaderSearch(jar)
          |
          v
JVM gọi customLoader.appendToClassPathForInstrumentation(
                    jar.getName())
          |
          v
customLoader bổ sung URL trỏ đến helper.jar
          |
          v
Main gọi Class.forName("demo.helper.Greeting", true, system)
          |
          v
customLoader tìm class từ helper.jar; định nghĩa class
          |
          v
Greeting.message() -> "hello"
~~~

Mô hình này mô tả đường đi **trong demo**. JVM có thể sử dụng các chi tiết nội bộ khác tùy implementation; interface do Javadoc công bố là sự kết hợp giữa `Instrumentation.appendToSystemClassLoaderSearch` và method hỗ trợ của system loader.

Cũng cần phân biệt **class loader của `Main`** và **system loader**: với một custom system loader dùng delegation parent-first, lớp `Main` có thể đã được parent tìm thấy từ `-cp app-out`. Vì vậy demo **cố ý không đặt một symbolic reference tĩnh tới helper trong `Main`**. Thay vào đó nó yêu cầu `Class.forName(..., systemLoader)` và kiểm tra `helper.getClassLoader() == systemLoader`. Nếu một class thực sự do parent định nghĩa mà lại có bytecode gọi helper chỉ tồn tại ở child system loader, lời gọi tĩnh ấy **không tự được cứu** bởi việc helper xuất hiện ở child. Đây là ranh giới visibility đặc biệt quan trọng khi thiết kế instrumentation.

## 5. Demo đầy đủ Java 17+: helper JAR và hai system loaders

Tạo một thư mục `demo/` để làm bài, với **năm file đầu vào**:

~~~text
demo/
  Greeting.java
  Agent.java
  CustomSystemLoader.java
  Main.java
  MANIFEST.MF
~~~

Sau build, ta sẽ có ba thư mục output `helper-out/`, `agent-out/`, `app-out/` cùng hai JAR `helper.jar`, `agent.jar`. Tất cả chỉ phục vụ demo; không sửa classpath/môi trường hệ thống của máy.

### 5.1. `Greeting.java` — helper chỉ nằm trong `helper.jar`

~~~java
package demo.helper;

public final class Greeting {
    public static String message() { return "hello"; }
}
~~~

Tên binary class là `demo.helper.Greeting`, tương ứng entry `demo/helper/Greeting.class` trong helper JAR. File này **không** được đưa vào thư mục `app-out` và **không** xuất hiện trong `-cp app-out` ở lúc chạy. Đây là điểm cần giữ để chứng minh append.

### 5.2. `Agent.java` — thêm JAR vào system-loader search

~~~java
import java.lang.instrument.Instrumentation;
import java.io.IOException;
import java.nio.file.Path;
import java.util.jar.JarFile;

public final class Agent {
    public static void premain(String options, Instrumentation inst) {
        try (JarFile helper = new JarFile(Path.of(options).toFile())) {
            inst.appendToSystemClassLoaderSearch(helper);
            System.out.println("APPENDED=true");
        } catch (IOException e) {
            throw new IllegalStateException(e);
        }
    }
}
~~~

Agent nhận chuỗi `options` từ `-javaagent:agent.jar=helper.jar`. Nó mở một `JarFile` và gọi **đúng một lần** `appendToSystemClassLoaderSearch`. Sau khi lời gọi thành công, nó in `APPENDED=true`. Đây là thao tác thêm search entry, **không** trực tiếp gọi `Class.forName("demo.helper.Greeting")` trong `premain`.

Lưu ý:

- `options` của demo phải là một đường dẫn không rỗng đến JAR tồn tại; thiếu option có thể làm `Path.of(options)` ném lỗi. Phiên bản production cần validate null/blank/path trước.
- `IOException` được bắt khi mở/đóng JAR; `UnsupportedOperationException` nếu system loader không hỗ trợ append là lỗi khác, không được ép thành "file not found".
- `JarFile.getName()` cung cấp path mà JVM chuyển cho custom loader. Demo dùng tên tương đối `helper.jar` từ thư mục làm việc nên custom method chuyển thành absolute URL.
- `try-with-resources` đóng handle `JarFile` phía agent khi xong; trên OpenJDK thử nghiệm, JVM có thể tìm class helper sau đó. Không nên giữ file handles vô hạn hoặc xóa JAR khi runtime còn cần tra cứu từ nó.
- In console chỉ để học; agent thật nên tránh phụ thuộc vào logging framework lớn ở giai đoạn khởi tạo.

### 5.3. `CustomSystemLoader.java` — method bắt buộc

~~~java
import java.net.MalformedURLException;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;

public final class CustomSystemLoader extends URLClassLoader {
    public CustomSystemLoader(ClassLoader parent) {
        super(new URL[0], parent);
    }

    public void appendToClassPathForInstrumentation(String jarPath) {
        try {
            addURL(Path.of(jarPath).toAbsolutePath().toUri().toURL());
        } catch (MalformedURLException e) {
            throw new IllegalArgumentException(e);
        }
    }
}
~~~

Phân tích:

1. Lớp có **public constructor(ClassLoader)**; JVM có thể tạo nó khi đọc `java.system.class.loader`.
2. `super(new URL[0], parent)` tạo một URLClassLoader **chưa có URL riêng**, nhưng có parent làm nguồn delegation.
3. `appendToClassPathForInstrumentation(String)` có tên chính xác như Javadoc. `Instrumentation.appendToSystemClassLoaderSearch` yêu cầu loader hỗ trợ method này.
4. `Path.of(jarPath).toAbsolutePath().toUri().toURL()` chuyển path nhận được thành URL JAR hợp lệ trong điều kiện thử nghiệm.
5. `addURL(...)` bổ sung JAR vào danh sách mà **chính URLClassLoader này** tìm kiếm. Không cập nhật property `java.class.path`.
6. Ví dụ dùng method `public` dù Javadoc không yêu cầu `public`. Khi triển khai khác, chú ý return type/exception/thread-safety phù hợp và tránh biến method thành API business.
7. Class loader không gọi `ClassLoader.getSystemClassLoader()` trong constructor nên không tạo vòng khởi tạo hệ thống.

Method `addURL` ở đây là **protected** method của `URLClassLoader`, gọi được từ subclass. Đừng copy cách `((URLClassLoader)ClassLoader.getSystemClassLoader()).addURL(...)` vào code bình thường: loader mặc định có thể không phải URLClassLoader, và `addURL` không public.

Trong môi trường thật, method nên từ chối path không hợp lệ theo chính sách rõ, đảm bảo JAR có chữ ký/nguồn đáng tin và có kiểm tra concurrency. Demo chỉ minh họa hợp đồng minimal; không chứa cơ chế quản lý artifact, rollback hoặc chống JAR có tên class trùng nhau.

### 5.4. `Main.java` — xác minh class thực sự được nạp từ system loader

~~~java
public final class Main {
    public static void main(String[] args) throws Exception {
        ClassLoader system = ClassLoader.getSystemClassLoader();

        System.out.println("CUSTOM_LOADER="
                + system.getClass().getSimpleName().equals("CustomSystemLoader"));

        Class<?> helper =
                Class.forName("demo.helper.Greeting", true, system);

        System.out.println("CLASS_LOADER_IS_SYSTEM="
                + (helper.getClassLoader() == system));

        System.out.println("HELPER_MESSAGE="
                + helper.getMethod("message").invoke(null));

        System.out.println("CLASS_PATH_HAS_HELPER="
                + System.getProperty("java.class.path").contains("helper.jar"));
    }
}
~~~

`Main` **không** import `demo.helper.Greeting` để tránh làm thí nghiệm phụ thuộc vào cách parent loader định nghĩa Main. Thay vào đó, `Class.forName(name, true, system)` chủ động yêu cầu **system loader đang hoạt động**. Sau đó:

- `CUSTOM_LOADER` phân biệt loại loader trong hai lượt chạy.
- `CLASS_LOADER_IS_SYSTEM` kiểm tra helper có được **định nghĩa bởi đúng object system loader** không, không chỉ là "tìm thấy class ở đâu đó".
- `HELPER_MESSAGE` là lời gọi thật vào method của class được nạp.
- `CLASS_PATH_HAS_HELPER` chứng minh `java.class.path` không tự liệt kê JAR được append, đúng Javadoc.

Trong một chương trình lớn, so sánh tên class loader đơn giản bằng `getSimpleName` chỉ dành cho demo; hãy kiểm tra danh tính loader/parent/module có kiểm soát. Có thể có các class loaders trùng tên ở các module khác nhau.

### 5.5. `MANIFEST.MF` — chỉ định lớp startup agent

~~~text
Manifest-Version: 1.0
Premain-Class: Agent

~~~

Giữ newline và một dòng trống cuối main section của manifest. `Premain-Class` dành cho `-javaagent` khi JVM khởi động; demo không dùng `Agent-Class`/`agentmain` vì không attach động vào JVM đã chạy.

### 5.6. Biên dịch và đóng gói

Từ thư mục `demo/` chứa năm file:

~~~bash
javac --release 17 -d helper-out Greeting.java
javac --release 17 -d agent-out Agent.java
javac --release 17 -d app-out Main.java CustomSystemLoader.java

jar --create --file helper.jar -C helper-out .
jar --create --file agent.jar --manifest MANIFEST.MF -C agent-out .
~~~

Điểm then chốt ở build:

- `helper-out` chứa `demo/helper/Greeting.class`; chỉ `helper.jar` chứa nó lúc chạy.
- `agent-out` chứa `Agent.class`; `agent.jar` phải có `META-INF/MANIFEST.MF` và `Premain-Class: Agent`.
- `app-out` chứa `Main.class` và `CustomSystemLoader.class`; **không** chứa `demo/helper/Greeting.class`.
- JAR helper **không được đưa vào `-cp`** ở hai lệnh chạy bên dưới, để append là nguồn duy nhất cho việc system loader tìm nó.

Có thể kiểm tra:

~~~bash
jar --list --file helper.jar
jar --list --file agent.jar
~~~

`helper.jar` phải có `demo/helper/Greeting.class`. `agent.jar` phải có `Agent.class` và `META-INF/MANIFEST.MF`. Danh sách JAR còn có thể chứa các entry phụ như `META-INF/`; không yêu cầu nguyên văn output của lệnh liệt kê.

### 5.7. Chạy với system loader mặc định

~~~bash
java -javaagent:agent.jar=helper.jar -cp app-out Main
~~~

Standard output chính xác đã quan sát trên OpenJDK Zulu 24:

~~~text
APPENDED=true
CUSTOM_LOADER=false
CLASS_LOADER_IS_SYSTEM=true
HELPER_MESSAGE=hello
CLASS_PATH_HAS_HELPER=false
~~~

Diễn giải: agent đã gọi append thành công, system loader mặc định tải Greeting từ helper.jar, và `java.class.path` vẫn chỉ phản ánh cấu hình launcher `app-out` chứ không có tên `helper.jar`.

Tên/loại system loader cụ thể có thể thay đổi theo JVM implementation. Code chỉ so `getSimpleName` với chuỗi `CustomSystemLoader` nên trên cấu hình mặc định thông thường dòng `CUSTOM_LOADER=false` như trên.

### 5.8. Chạy với custom system loader

~~~bash
java "-Djava.system.class.loader=CustomSystemLoader" -javaagent:agent.jar=helper.jar -cp app-out Main
~~~

Standard output **của chương trình** đã quan sát trên OpenJDK Zulu 24:

~~~text
APPENDED=true
CUSTOM_LOADER=true
CLASS_LOADER_IS_SYSTEM=true
HELPER_MESSAGE=hello
CLASS_PATH_HAS_HELPER=false
~~~

**Lưu ý shell:** đối số `-Djava.system.class.loader=CustomSystemLoader` được **quote nguyên vẹn** trong lệnh trên. Đặt quote như vậy dùng được trong các shell thông dụng, đồng thời tránh một số cách phân tích argument khác biệt của Windows PowerShell. Không đặt property sau tên `Main`: khi ấy nó sẽ là application argument thay vì JVM option.

Trên HotSpot phiên bản thử nghiệm, dòng cảnh báo CDS có thể xuất hiện **trên stderr** khi bật `java.system.class.loader`, ví dụ về việc không sử dụng một số archived non-system classes. Cảnh báo này không phải một dòng output do mã demo in, không có nghĩa `append` thất bại. Tách stdout của demo khỏi diagnostics do JVM/vendor tự in.

Kết quả chứng minh:

1. Loader tùy chỉnh được chọn làm system loader.
2. JVM đã gọi đường hỗ trợ append và helper được định nghĩa qua loader tùy chỉnh.
3. App lấy được method `Greeting.message()` trong helper JAR không nằm trên launcher classpath.
4. `java.class.path` không được bổ sung tên helper.jar.

**Giới hạn chứng minh:** `Main` dùng reflection qua system loader. Không suy từ thử nghiệm này rằng các classes do **default parent loader** hoặc isolated plugin loaders định nghĩa cũng có thể liên kết trực tiếp tới Greeting sau append.

## 6. Tại sao thiếu `appendToClassPathForInstrumentation` là lỗi nghiêm trọng?

Tưởng tượng một loader tùy chỉnh:

~~~java
// Ví dụ thiết kế KHÔNG ĐỦ cho Java agent, không phải chương trình độc lập.
public final class BrokenLoader extends ClassLoader {
    public BrokenLoader(ClassLoader parent) {
        super(parent);
    }
    // Không có appendToClassPathForInstrumentation(String)!
}
~~~

Nó có thể đáp ứng yêu cầu constructor của `java.system.class.loader` nhưng **không đáp ứng contract instrumentation**. Khi JVM/agent cần append một JAR vào system-loader search path, không có method thích hợp để thực hiện. `Instrumentation.appendToSystemClassLoaderSearch` có thể báo `UnsupportedOperationException` khi system loader không hỗ trợ.

**Đặc biệt với `-javaagent`:** custom loader thiếu method có thể làm startup agent không nạp được ngay từ đầu, trước khi `premain` có cơ hội gọi API. Thông báo chi tiết và thời điểm lỗi tùy JVM/vendor. Đừng cố "sửa" bằng cách viết thêm `Premain-Class` nếu manifest đã đúng; hãy kiểm tra hợp đồng custom loader.

Một implementation sai khác:

~~~java
// Sai về mặt ý nghĩa: nhớ path nhưng không làm findClass thấy JAR mới.
public void appendToClassPathForInstrumentation(String jarPath) {
    knownPaths.add(jarPath);
}
~~~

Nếu `findClass`/delegation logic không sử dụng `knownPaths` để tìm class, đó **không phải một phép append hiệu quả**. Đoạn code chỉ minh họa lỗi thiết kế (giả định có biến `knownPaths`); không phải source độc lập. Điều cần kiểm tra không chỉ là "method tồn tại" mà là **class mới thực sự có thể được tìm sau khi append**.

### 6.1. Vì sao method có thể không cần public?

Javadoc `Instrumentation` nói rõ method `appendToClassPathForInstrumentation(String)` **không bắt buộc public**. JVM dùng cơ chế hỗ trợ nội bộ của class loader để gọi nó theo hợp đồng. Điều này không có nghĩa một class Java bất kỳ ở ngoài có thể gọi method private/package-private của custom loader bằng lời gọi bình thường. Ví dụ sử dụng `public void` để người học có thể trực tiếp hiểu, inspect và viết unit test.

Không dùng reflection để gọi lậu method nội bộ của system loader mặc định. Cách được hỗ trợ cho Java agent là **`Instrumentation.appendToSystemClassLoaderSearch(JarFile)`**, còn custom loader phải cung cấp hook mà JVM mong đợi.

## 7. Không nên thử một lần resolve thất bại rồi tin append sẽ sửa được

Javadoc nhắc tới một quy tắc của **symbolic reference resolution** trong JVM: nếu JVM đã cố resolve một symbolic reference và thất bại, một lần resolve tiếp theo của **cùng reference đó** vẫn thất bại với lỗi tương ứng, ngay cả khi sau đó một JAR mới được thêm vào search path.

Ví dụ về tình huống thiết kế sai:

~~~text
1. Class A đang chạy bytecode tham chiếu Helper.missing()
2. Symbolic reference resolution thất bại (lỗi linkage)
3. Agent append helper.jar có đúng class/method mong muốn
4. Class A thử lại cùng symbolic reference
5. JVM có thể lặp lại lỗi resolution cũ theo JVM Specification
~~~

Vì vậy, **append càng sớm càng tốt trước lần sử dụng helper đầu tiên**. Một diagnostic kiểu "cố ý gọi helper để thấy fail, sau đó append rồi gọi lại y hệt" có thể gây hiểu lầm và còn làm trạng thái lỗi khó đảo ngược.

Phân biệt:

- **Class/resource search mới** bằng API phù hợp có thể tìm thấy entry vừa append.
- **Một symbolic reference đã resolution thất bại** có thể bị ràng buộc bởi quy tắc failure được nhớ lại.
- **Một class đã định nghĩa** không bị thay thế bằng class có cùng tên chỉ vì JAR mới được append.

Bởi vậy demo chỉ gọi `Class.forName` **sau** khi `premain` đã append. Nó không cố kích hoạt lỗi resolve trước append rồi kiểm tra lại trên cùng reference.

## 8. Parent delegation: vì sao custom loader không giải quyết mọi visibility?

Trong demo, `CustomSystemLoader` là một **URLClassLoader có parent**. Default `URLClassLoader` sử dụng parent-first: khi cần load một class, nó thử parent trước, rồi mới tìm trong URLs của mình. Điều này có hai hệ quả:

1. **Lớp trùng tên:** nếu parent đã có `demo.helper.Greeting`, custom loader có thể trả class của parent thay vì class ở helper.jar. Bổ sung JAR không được dùng để override tùy tiện class đã có.
2. **Lớp được parent định nghĩa:** nếu một `Main` hoặc service class do parent định nghĩa chứa symbolic reference tới helper **chỉ có trong child custom loader**, parent không đương nhiên tìm ngược xuống child để resolve reference đó.

Sơ đồ tình huống thứ hai:

~~~text
Default system loader (parent)
   |-- định nghĩa Main / SomeService
   |      |
   |      +-- bytecode SomeService gọi demo.helper.Greeting
   |             -> resolve theo defining loader của SomeService
   |             -> parent không nhìn vào URL riêng của child
   |
   +-- CustomSystemLoader (system loader mới)
           |
           +-- URL helper.jar (đã append)
                  |
                  +-- có demo.helper.Greeting
~~~

Đây là lý do `Class.forName(name, true, ClassLoader.getSystemClassLoader())` trong demo là một phép kiểm tra **có chủ đích và có phạm vi**: nó yêu cầu chính child custom loader. Một lời gọi direct trong class đã được parent định nghĩa cần được kiểm chứng riêng.

Tương tự, ứng dụng với child-first/plugin loaders có thể có chính sách loại trừ hoặc class visibility không theo mặc định. Đừng thiết kế agent dựa vào suy luận "chèn JAR vào system loader xong tất cả classes trong JVM đều truy cập được". Phải thử trong **đúng defining loader** của class đang được instrument.

## 9. `appendToBootstrapClassLoaderSearch` có giải quyết được không?

Một số agent cần helper cho classes do **bootstrap loader** định nghĩa, ví dụ khi instrument classes thư viện nền tảng. Khi ấy, `appendToSystemClassLoaderSearch` **không đủ** vì bootstrap loader không delegate xuống system loader để tìm class.

API khác là:

~~~java
void appendToBootstrapClassLoaderSearch(java.util.jar.JarFile jarfile);
~~~

Nhưng không nên tự động thay thế mọi trường hợp bằng bootstrap append:

- Helper nạp bởi bootstrap cần có dependencies mà bootstrap loader thực sự có thể nhìn thấy; một helper yêu cầu thư viện ứng dụng ở system loader có thể gặp lỗi linkage.
- Javadoc cảnh báo JAR append chỉ nên chứa instrumentation classes/resources cần thiết. Classes tên trùng, nhất là package-private helpers, có thể gây `IllegalAccessError` do loader identity khác.
- Bootstrap search và system search có phạm vi khác nhau; việc chọn sai có thể làm **tăng rủi ro** thay vì giải quyết visibility.
- Named modules vẫn có quy tắc access; bootstrap append không tự mở mọi module/package.
- Nếu chỉ có một nhóm class ứng dụng thật sự do system loader định nghĩa, system append thường phù hợp hơn.

Chọn nơi đặt helper bằng cách xác định **lớp nào chứa invocation đã inject** và **defining loader của lớp đó**, sau đó kiểm tra module readability/exports khi dùng modules.

## 10. Phân biệt module path và classpath

`appendToSystemClassLoaderSearch` không có nghĩa là:

- Tạo một named module mới hoặc tự resolve nó vào boot layer.
- Sửa `--module-path`, `ModuleLayer` hoặc mọi trạng thái module resolution.
- Tự thêm `requires`/reads/exports/opens cho các named modules đã tồn tại.
- Cấp đặc quyền cho mã helper chỉ vì nó nằm trong instrumentation JAR.

Một class được định nghĩa từ helper.jar qua system loader thường thuộc **unnamed module** của loader đó nếu nó không được load như một named module theo cơ chế khác. Khi một class ở **named module** tham chiếu helper, phải xét readability và accessibility phù hợp. Với nhu cầu module runtime sâu, `Instrumentation.redefineModule(...)` có thể điều chỉnh **các quan hệ module được API cho phép**, nhưng đó là một thao tác riêng, không phải hiệu ứng mặc định của append.

Đối với ứng dụng dùng JPMS, kiểm thử class loading trên đúng module/loader topology, thay vì chỉ chạy một ứng dụng trên plain classpath và coi như đủ.

## 11. Lỗi thường gặp và hướng chẩn đoán

| Triệu chứng | Nguyên nhân khả dĩ | Hành động kiểm tra |
| --- | --- | --- |
| `UnsupportedOperationException` tại `appendToSystemClassLoaderSearch` | System loader không hỗ trợ append/hook tương ứng | Kiểm tra loại system loader và method đặc biệt |
| Startup thất bại với custom loader | Thiếu constructor `(ClassLoader)`, thiếu method append hoặc logic loader sai | Kiểm tra `-Djava.system.class.loader`, classpath chứa loader và thông điệp JVM |
| `IOException` khi tạo `JarFile` | Path sai, file thiếu, quyền/ZIP lỗi | Đối chiếu path từ working directory, file thật, quyền |
| `NullPointerException` khi `jarfile` null | Lỗi logic agent | Validate config/không truyền null |
| `ClassNotFoundException` sau append | Class không nằm trong JAR/path hoặc loader chọn sai | Kiểm tra JAR entries, defining loader, parent delegation |
| `NoClassDefFoundError` khi method đã inject chạy | Runtime không resolve được helper hoặc một dependency | Kiểm tra loader của class chứa hook, dependencies, lỗi gốc |
| `IllegalAccessError` hoặc lỗi module | Loader/package/module access khác nhau | Kiểm tra module rules, duplicate packages, package-private access |
| `NoSuchMethodError` | Helper class có version hoặc descriptor không đúng | Kiểm tra method tên, visibility, signature và class thực sự được load |
| Append báo thành công nhưng `java.class.path` không thay đổi | Hành vi **đúng contract** | Kiểm tra bằng load class/resource, không đo bằng property |
| Append rồi vẫn lỗi như trước | Symbolic reference đã resolution fail; hoặc class trùng đã load | Dò phase đầu tiên, không retry cùng reference mù quáng |
| Class có cùng tên nhưng version sai | Parent-first delegation hoặc JAR trùng classes | Kiểm tra `Class.getClassLoader()`, `ProtectionDomain`/code source có kiểm soát |
| JVM in cảnh báo CDS với custom loader | Chế độ archived classes khác đi | Phân biệt JVM stderr với stdout của demo |
| Loader tùy chỉnh không tìm thấy class agent | Loader không hỗ trợ thêm agent JAR ngay startup | Kiểm tra append hook và path trước khi phân tích `premain` |

Khi debug, ghi nhận **lớp cụ thể nào cần helper** và `someClass.getClassLoader()`, `ClassLoader.getSystemClassLoader()`, tên class được load thực tế và những JAR đã append. Không cần serialise nguyên loader object hoặc gọi `toString` vào thời điểm class loading nhạy cảm.

### 11.1. Trường hợp thiếu file so với trường hợp thiếu loader hook

Hai lỗi cần sửa ở hai nơi khác nhau:

- **File helper không tồn tại:** `new JarFile(...)` thất bại trước khi gọi append. Sửa đường dẫn, quyền và packaging.
- **Custom loader thiếu method hỗ trợ:** JAR có thể hoàn toàn hợp lệ, nhưng JVM không thể bổ sung nó vào search path của custom system loader. Sửa **implementation của loader** và kiểm thử lại startup; đừng đóng gói lại helper vô hạn nếu nó đã đúng.

Agent production nên báo lỗi theo giai đoạn `open JAR`, `append JAR`, `resolve helper`, `execute helper`. Một câu "agent failed" cho mọi trường hợp sẽ làm mất dấu lỗi cần sửa.

## 12. Thiết kế an toàn cho production

### 12.1. Chuẩn hóa và xác thực JAR path

Demo dùng `helper.jar` tương đối. Với triển khai nhiều môi trường:

- Lấy path rõ ràng từ cấu hình agent, tránh phụ thuộc working directory không ổn định.
- Chuyển thành absolute/normalized path và mở `JarFile` từ path ấy.
- Kiểm tra JAR tồn tại, đúng phiên bản, checksum/chữ ký theo policy và chỉ chứa classes/resources cần thiết.
- Không để input không tin cậy chọn tùy ý một JAR code có thể được nạp vào JVM.
- Tránh class-name collisions bằng package name riêng cho helper, ví dụ `com.example.observation.internal`.
- Nếu helper đã được nạp từ version khác, append file mới không thực hiện hot replacement.
- Không xóa/đổi path của JAR ngay sau append khi runtime có thể cần đọc entries thêm.

Mảnh code ý tưởng cho `premain` production, **không phải source độc lập**:

~~~java
Path normalized = Path.of(options).toAbsolutePath().normalize();
if (!java.nio.file.Files.isRegularFile(normalized)) {
    throw new IllegalArgumentException("Helper JAR missing: " + normalized);
}
try (JarFile helper = new JarFile(normalized.toFile())) {
    inst.appendToSystemClassLoaderSearch(helper);
} catch (IOException ex) {
    throw new IllegalStateException("Cannot read helper JAR", ex);
}
~~~

`options`, `inst` phải có trong method chứa snippet. Phải validate `options != null` và không blank **trước** đoạn này. `UnsupportedOperationException` của loader **không** nằm trong `IOException`; xử lý ở tầng có thể thông báo chính xác vấn đề capability.

### 12.2. Thời điểm append so với đăng ký transformer

Trong agent có transformer thật, thường nên chuẩn bị helper search path **trước** khi transformer bắt đầu tạo class files chứa lời gọi helper:

~~~text
premain/agentmain:
    validate JAR
    append helper JAR
    initialize agent state
    register transformer
    optionally retransform selected already-loaded classes
~~~

Nếu đăng ký transformer trước rồi class nghiệp vụ chạy được instrument ngay, helper có thể chưa khả dụng lúc JVM resolve invocation. Trong các hệ thống đa luồng, cuộc đua giữa class load/resolve và append càng khó tái hiện. Đồng thời tránh gọi `Class.forName` vào class **đang được định nghĩa** từ ngay trong `ClassFileTransformer.transform` chỉ để test loader: có thể tạo reentrancy hoặc class circularity. Kiểm tra tính khả dụng helper trong setup hoặc thử nghiệm được kiểm soát.

### 12.3. Chọn helper contract phù hợp

Một helper có thể chỉ gồm:

~~~java
public final class Probe {
    public static void onEnter(String operation) {
        // Ghi event vào buffer hữu hạn, tránh gọi network đồng bộ.
    }
}
~~~

Đây là **mẫu API**, chưa phải class chạy độc lập vì chỉ có thân minh họa. Khi bytecode đã inject `invokestatic Probe.onEnter(String)V`, JVM phải thấy method đúng descriptor. Không cho helper ném lỗi telemetry làm đổi kết quả nghiệp vụ nếu contract là quan sát best-effort; có thống kê drop/failure và xử lý reporter ngoài callback.

### 12.4. Tránh class loader leak và xung đột

Nếu agent giữ references tới `ClassLoader`, `Class<?>` hoặc `JarFile` trong cache không giới hạn, hot reload/plugin unload có thể giữ object graph sống ngoài ý muốn. Dữ liệu chẩn đoán nên dùng IDs/metadata nhỏ và cấu trúc có giới hạn; quản lý vòng đời tài nguyên rõ ràng.

Không dùng `appendToSystemClassLoaderSearch` như cách nạp tùy tiện toàn bộ dependencies của ứng dụng. Cơ chế này dành cho **instrumentation classes** cần thiết, không thay dependency management của dự án. Nếu một JAR chứa nhiều phiên bản `commons-*` hoặc logging framework trùng package với ứng dụng, kết quả class loading có thể thay đổi khó lường.

## 13. Kiểm thử có cấu trúc

| Ca | Thiết lập | Điều mong đợi |
| --- | --- | --- |
| Loader mặc định | Không có `-Djava.system.class.loader` | `APPENDED=true`; helper load được qua system loader |
| Loader tùy chỉnh hỗ trợ | Có `CustomSystemLoader` và method hook | `CUSTOM_LOADER=true`, helper được chính custom loader định nghĩa |
| Không truyền `-javaagent` | Chỉ `-cp app-out` | Main không tìm thấy helper vì helper.jar không nằm trong classpath |
| Helper JAR sai path | Cho một file không tồn tại | Agent báo lỗi đọc JAR rõ ràng |
| Loader thiếu hook | Tạo custom loader không có `appendToClassPathForInstrumentation` trong môi trường thử | Startup/append có thể thất bại; không nhầm với lỗi helper |
| Lớp đã được parent load | Parent có class trùng tên | Parent-first có thể chọn version của parent |
| Lời gọi từ class parent | Class chứa symbolic reference do parent định nghĩa | Không giả định parent tự thấy helper ở child |
| Class bootstrap cần helper | Instrument class do bootstrap định nghĩa | System append chưa đủ; đánh giá bootstrap search |
| Class trong named module | Helper ở unnamed module của loader | Kiểm tra readability/exports/access |
| Symbolic resolution fail trước append | Thử trong JVM test cách ly | Không mặc định append chữa được failure đã ghi nhớ |
| Thêm nhiều JAR | Gọi append theo thứ tự xác định | Thứ tự append được quan sát, không xung đột classes |
| Tải thực tế | Helper được gọi trên hot path | Đo CPU, GC, p99 latency, telemetry drops |

Để test behavior cuối cùng của **instrumented method**, không chỉ test `Class.forName`: dùng một lớp do loader mục tiêu định nghĩa, inject lời gọi helper, rồi chạy. Kiểm tra cả normal và exception paths, business results và biến thể module/loader của ứng dụng thật.

## 14. Các nhầm lẫn phổ biến

1. **"appendToSystemClassLoaderSearch là thêm vào `java.class.path`."** Không; property không đổi.
2. **"Mọi loader đều nhìn thấy helper sau append."** Không; phụ thuộc defining loader và delegation/module rules.
3. **"Custom system loader chỉ cần constructor là đủ để chạy agent."** Không; cần `appendToClassPathForInstrumentation(String)`.
4. **"Method đặc biệt phải public."** Javadoc không bắt buộc public, dù public tiện thử nghiệm.
5. **"JVM truyền absolute path vào hook."** Contract truyền `JarFile.getName()`; normalize path nếu cần.
6. **"Class loader mặc định luôn là URLClassLoader."** Không đúng trên JDK hiện đại.
7. **"Có thể cast default loader rồi gọi addURL."** Không nên; type và access không được bảo đảm.
8. **"Một JAR trùng tên class sẽ override class đã nạp."** Không; append chỉ mở rộng search cho những tra cứu hợp lệ về sau.
9. **"Append sau lần NoClassDefFoundError luôn sửa được lỗi."** Không; symbolic reference resolution failure có thể được ghi nhớ.
10. **"System append và bootstrap append như nhau."** Không; scope loader và dependency khác nhau.
11. **"System loader tùy chỉnh chắc chắn đã định nghĩa Main."** Không; với parent-first, parent có thể định nghĩa Main.
12. **"Nếu `Class.forName` qua system thành công, mọi bytecode ở parent cũng gọi được helper."** Không được suy như vậy.
13. **"Method loader tồn tại nhưng không thay findClass cũng đủ."** Không; method phải thực sự mở rộng search.
14. **"Append là cách tạo named module mới."** Không; module path và readability cần xử lý riêng.
15. **"JAR chứa bao nhiêu thư viện cũng an toàn."** Sai; trùng classes, helper dependencies và package boundaries cần kiểm soát.

## 15. Câu hỏi tự kiểm tra

1. `appendToSystemClassLoaderSearch` nhận `Path`, `URL` hay `JarFile`?
2. JAR được thêm vào đường tìm kiếm **của loader nào**? Nó có tự đổi `java.class.path` không?
3. Vì sao custom system loader cần cả public constructor `(ClassLoader)` lẫn method `appendToClassPathForInstrumentation(String)`?
4. JVM truyền giá trị nào từ `JarFile` cho method hook của custom loader?
5. Tại sao demo dùng `Class.forName(..., ClassLoader.getSystemClassLoader())` thay vì direct reference trong Main?
6. Điều gì xảy ra nếu `Main` do parent loader định nghĩa nhưng helper chỉ có ở child system loader?
7. Vì sao không nên gọi `ClassLoader.getSystemClassLoader()` trong constructor của custom loader?
8. `URLClassLoader.addURL` có thể được gọi ở đâu và vì sao không thể cast loader mặc định một cách vô điều kiện?
9. Nếu helper class đã resolution thất bại trước append, tại sao lần gọi cũ có thể tiếp tục lỗi?
10. Nếu muốn instrument bootstrap class, system append có phải giải pháp đủ trong mọi trường hợp không?
11. Làm sao kiểm tra JAR có đúng class `demo.helper.Greeting` mà không nhầm với JAR agent?
12. Nếu công cụ in `APPENDED=true`, điều gì **chưa** được chứng minh về named modules và child class loaders?
13. Nêu hai tình huống có thể gây `NoClassDefFoundError` dù agent JAR đã khởi động thành công.
14. Vì sao phải kiểm tra `CLASS_LOADER_IS_SYSTEM` ngoài việc chỉ gọi được `Greeting.message()`?
15. Bạn sẽ thiết kế test nào để chứng minh helper được nạp từ đúng package/loader trong ứng dụng thật?

## 16. Checklist triển khai

1. Xác định lớp nào sẽ được inject invocation và defining loader/module của lớp ấy.
2. Chọn nơi định nghĩa helper: system loader, bootstrap loader hoặc một cơ chế khác thật sự phù hợp.
3. Đặt helper trong JAR gọn, package riêng, không mang theo dependencies gây trùng classes.
4. Nếu cấu hình `java.system.class.loader`, bảo đảm custom loader có constructor đúng và hook `appendToClassPathForInstrumentation(String)` vận hành thật.
5. Validate JAR path, mở `JarFile` an toàn, gọi `appendToSystemClassLoaderSearch` trước khi hook được sử dụng.
6. Phân biệt lỗi `JarFile`/I/O với lỗi capability `UnsupportedOperationException`.
7. Tránh gây symbolic resolution failure trước append.
8. Xác minh helper class được định nghĩa bởi đúng loader và có descriptor/visibility mà bytecode cần.
9. Kiểm tra parent delegation, custom isolation, named module access và bootstrap classes.
10. Test class loading, behavior, exception và p95/p99 latency trong môi trường đúng topology.
11. Quản lý JAR/dependencies/loader lifecycle, không append tùy tiện nhiều bản trùng class.
12. Có runbook rollback và log chẩn đoán không chứa bí mật hoặc references quá lớn.

## 17. Kết luận

`Instrumentation.appendToSystemClassLoaderSearch(JarFile)` cho phép agent bổ sung JAR để **system class loader** tìm thêm instrumentation classes. Nó **không** sửa `java.class.path`, không đổi classes đã định nghĩa, không bảo đảm mọi loader trong JVM nhìn thấy helper, và không cấp quyền module mặc định.

Với một **system loader tùy chỉnh**, hai hợp đồng phải cùng đúng: lớp được cấu hình qua `java.system.class.loader` có **public constructor(ClassLoader)** và có method **`appendToClassPathForInstrumentation(String)`** thực sự bổ sung JAR vào search path. JVM lấy đối số method này từ `JarFile.getName()`. Nếu thiếu, Java agent có thể thất bại ngay khi khởi động hoặc khi append.

Bài học quan trọng nhất: **kiểm tra loader của chính lớp chứa lời gọi helper**, không chỉ loader của agent. Viết agent thành công, append JAR thành công và resolve helper thành công từ đúng defining loader là ba việc khác nhau.

### Tài liệu chính thức

- [Oracle JDK 17 — Instrumentation.appendToSystemClassLoaderSearch](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html#appendToSystemClassLoaderSearch(java.util.jar.JarFile)): hợp đồng `JarFile`, tên method đặc biệt của custom loader, `jarfile.getName()`, exception và property `java.class.path`.
- [Oracle JDK 17 — ClassLoader.getSystemClassLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html#getSystemClassLoader()): cấu hình `java.system.class.loader`, public constructor(ClassLoader), delegation và recursion.
- [Oracle JDK 17 — java.lang.instrument package](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/package-summary.html): startup/dynamic agent và yêu cầu custom system class loader.
- [Oracle JDK 17 — URLClassLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html): `addURL`, parent delegation và cách URL search hoạt động.
- [Java Virtual Machine Specification, SE 17 — Linking](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.4): quy tắc resolution failure và class loader linkage.
