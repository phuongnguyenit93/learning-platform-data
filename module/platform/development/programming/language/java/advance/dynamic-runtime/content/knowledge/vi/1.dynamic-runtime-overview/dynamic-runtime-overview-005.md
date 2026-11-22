# 1.5. Phân biệt sử dụng mã đã biên dịch với tạo, biên dịch và định nghĩa mã mới

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt **sử dụng lớp đã được biên dịch** với **tạo mã nguồn**, **biên dịch mã nguồn thành bytecode**, và **định nghĩa một lớp từ bytecode trong JVM đang chạy**.
- Giải thích vai trò riêng của trình biên dịch, class loader, quá trình liên kết/khởi tạo lớp, Reflection và JIT.
- Chỉ ra trường hợp nào thực sự tạo bytecode hoặc một định nghĩa lớp mới trong runtime, kể cả khi không có mã nguồn Java.
- Chọn cách tiếp cận phù hợp cho ứng dụng, plugin, proxy, công cụ sinh mã; nhận diện giới hạn về class loader, triển khai và an toàn.

## 1. Bốn hành động dễ bị nhầm lẫn

Trong Java, câu “dùng lớp động” có thể chỉ nhiều hành động khác nhau. Cần hỏi chính xác: **mã nguồn có được tạo mới không, bytecode có được biên dịch/sinh mới không, và JVM có đang định nghĩa một lớp mới từ bytecode hay chỉ dùng một định nghĩa đã có?**

| Hành động | Đầu vào | Kết quả trực tiếp | Có nhất thiết tạo bytecode mới lúc chạy? |
| --- | --- | --- | --- |
| **Sử dụng mã đã biên dịch** | Các lớp đã có trong classpath/module path, hoặc một thư viện có sẵn | Gọi constructor, method, field; có thể chọn lớp bằng tên hoặc qua giao diện | Không |
| **Tạo mã nguồn mới** | Chuỗi, template, AST hoặc cấu hình | Văn bản nguồn như một file Java | Chưa; chỉ có nguồn chưa đủ để JVM chạy |
| **Biên dịch mã nguồn** | Nguồn Java và các phụ thuộc cần thiết | Bytecode trong file .class hoặc vùng nhớ; kèm lỗi chẩn đoán nếu thất bại | Có, nếu biên dịch thành công và thực sự sinh bytecode |
| **Định nghĩa lớp (class definition)** | Bytecode của một class hợp lệ và ngữ cảnh nạp lớp | Đối tượng Class đại diện cho định nghĩa lớp trong JVM | Không nhất thiết: bytecode có thể đã được biên dịch từ trước |

**“Định nghĩa lớp” trong ngữ cảnh JVM không đồng nghĩa với viết câu lệnh khai báo lớp trong source.** Khi một class loader định nghĩa lớp từ dữ liệu .class, JVM tạo danh tính runtime cho lớp đó. Việc này cũng diễn ra khi một lớp đã biên dịch từ trước được nạp lần đầu; vì vậy “định nghĩa lớp mới trong JVM” **không tự chứng minh** rằng mã nguồn hoặc bytecode vừa được sinh lúc chạy.

Một cách quan sát rõ hơn là theo hai trục độc lập:

1. **Bytecode xuất hiện khi nào?** Trước khi chạy (build/deploy) hoặc trong khi chương trình đang chạy.
2. **Bytecode được định nghĩa bởi class loader nào, vào lúc nào?** Lớp có thể được JVM định nghĩa khi cần, dù bytecode đã tồn tại trên đĩa rất lâu.

Ví dụ, một plugin .jar được biên dịch hôm qua nhưng hôm nay mới được ứng dụng tải vào JVM vẫn là **sử dụng bytecode đã biên dịch**, đồng thời có thể là **định nghĩa lần đầu lớp ấy trong một class loader**. Ngược lại, chương trình có thể biên dịch source mới ra .class nhưng chưa bao giờ tải/định nghĩa lớp đó.

## 2. Chuỗi xử lý từ source tới thực thi

~~~text
Lúc phát triển / lúc chạy:
.java --(javac hoặc JavaCompiler)--> .class (bytecode)
                                        |
                                        v
                    class loader tìm/đọc bytecode cần nạp
                                        |
                                        v
                             định nghĩa lớp trong JVM
                                        |
                                        v
                       liên kết: verify, prepare, resolve (*)
                                        |
                                        v
                       khởi tạo lớp khi điều kiện yêu cầu
                                        |
                                        v
                  new / gọi method / Reflection / MethodHandle
                                        |
                                        v
                 JVM thông dịch hoặc JIT tối ưu mã thực thi
~~~

(*) **Resolution** có thể được thực hiện theo nhu cầu; không nên hiểu sơ đồ là mọi tham chiếu đều phải resolve xong ngay theo một lịch cố định. Việc **nạp (loading)**, **liên kết (linking)** và **khởi tạo (initialization)** là những khái niệm khác nhau:

- **Loading/defining:** tìm bytes và hình thành một lớp trong JVM, gắn với class loader định nghĩa.
- **Verification:** kiểm tra các quy tắc hợp lệ của bytecode; **preparation:** cấp phát và thiết lập giá trị mặc định cho biến tĩnh; **resolution:** chuyển tham chiếu ký hiệu sang tham chiếu cụ thể (có thể trì hoãn).
- **Initialization:** thực hiện khởi tạo biến tĩnh và khối static theo ngữ nghĩa Java, khi lớp được chủ động sử dụng hoặc khi API yêu cầu.
- **Execution/JIT:** thực thi phương thức và có thể biên dịch bytecode thành mã máy để tối ưu; **JIT không phải** là bước biên dịch source Java thành file .class.

**Class.forName("TenLop")** thường được dùng để chọn lớp theo tên ở runtime. Với overload một tham số, nó còn yêu cầu khởi tạo lớp. **ClassLoader.loadClass("TenLop")** tải lớp nhưng bản thân thao tác này không nhất thiết khởi tạo ngay. Cả hai không có nhiệm vụ tự tạo source hoặc biên dịch source Java.

## 3. Trường hợp A: dùng lớp đã biên dịch, kể cả khi chọn lớp bằng Reflection

Tạo hai file Java trong cùng thư mục.

**ExistingGreeting.java**

~~~java
public class ExistingGreeting {
    public String message() {
        return "Xin chào từ bytecode có sẵn!";
    }
}
~~~

**UseExisting.java**

~~~java
public class UseExisting {
    public static void main(String[] args) throws ReflectiveOperationException {
        // Tên lớp chỉ được quyết định khi chương trình chạy.
        Class<?> type = Class.forName("ExistingGreeting");

        Object instance = type.getDeclaredConstructor().newInstance();
        String text = (String) type.getMethod("message").invoke(instance);

        System.out.println(text);
    }
}
~~~

Biên dịch trước, rồi chạy:

~~~bash
javac -encoding UTF-8 ExistingGreeting.java UseExisting.java
java UseExisting
~~~

Kết quả trên stdout:

~~~text
Xin chào từ bytecode có sẵn!
~~~

**Điều thực sự xảy ra:**

1. Lệnh **javac** tạo **ExistingGreeting.class** và **UseExisting.class** trước lúc chạy lệnh **java**.
2. Khi **UseExisting** đang chạy, **Class.forName** tìm lớp theo tên và có thể khiến JVM tải, định nghĩa và khởi tạo **ExistingGreeting** nếu trước đó chưa thực hiện.
3. Reflection lấy constructor/method từ định nghĩa lớp đó rồi gọi phương thức.
4. **Không có** source Java mới nào được tạo; **không có** lệnh biên dịch mới nào được gọi từ **UseExisting**.

Nếu bỏ **ExistingGreeting.class** ra khỏi classpath (và lớp không thể tìm thấy ở đâu khác), câu lệnh **Class.forName** sẽ thất bại với **ClassNotFoundException**. Reflection không tự suy ra hoặc biên dịch file **ExistingGreeting.java** còn nằm trên đĩa.

**Lưu ý:** Cú pháp **new ExistingGreeting()** cũng sử dụng lớp đã biên dịch, nhưng tên lớp được tham chiếu trực tiếp trong code. **Class.forName** thêm khả năng **chọn** lớp theo tên tại runtime; đó là lựa chọn động về lớp sẽ dùng, không đồng nghĩa với sinh lớp mới.

## 4. Trường hợp B: tạo source, biên dịch rồi tải lớp mới ngay khi chương trình chạy

Java cung cấp API chuẩn **javax.tools.JavaCompiler** (JSR 199) để một chương trình có thể yêu cầu trình biên dịch Java biên dịch source tại runtime. Đây là một chuỗi nhiều bước: **tạo source → biên dịch → lấy bytecode → tải/định nghĩa lớp → sử dụng**.

Ví dụ dưới đây độc lập, chạy được trên **JDK 17+ có module trình biên dịch jdk.compiler**. Nó tạo file source trong thư mục tạm, gọi compiler, mở URLClassLoader để tải file .class vừa sinh và gọi method.

**CompileAtRuntime.java**

~~~java
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import javax.tools.DiagnosticCollector;
import javax.tools.JavaCompiler;
import javax.tools.JavaFileObject;
import javax.tools.StandardJavaFileManager;
import javax.tools.ToolProvider;

public class CompileAtRuntime {
    public static void main(String[] args) throws Exception {
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException(
                    "Runtime này không cung cấp JavaCompiler (jdk.compiler).");
        }

        Path dir = Files.createTempDirectory("runtime-java-");
        Path sourceFile = dir.resolve("RuntimeOnlyGreeting.java");

        String source = """
                public class RuntimeOnlyGreeting {
                    public String message() {
                        return "Xin chào từ mã vừa biên dịch!";
                    }
                }
                """;

        try {
            // Bước 1: chương trình tự tạo source khi đang chạy.
            Files.writeString(sourceFile, source, StandardCharsets.UTF_8);

            // Bước 2: biên dịch source vừa tạo thành file .class.
            DiagnosticCollector<JavaFileObject> diagnostics =
                    new DiagnosticCollector<>();

            try (StandardJavaFileManager manager =
                    compiler.getStandardFileManager(
                            diagnostics, null, StandardCharsets.UTF_8)) {

                Iterable<? extends JavaFileObject> units =
                        manager.getJavaFileObjects(sourceFile.toFile());

                Boolean success = compiler.getTask(
                        null,
                        manager,
                        diagnostics,
                        List.of("-encoding", "UTF-8", "-d", dir.toString()),
                        null,
                        units
                ).call();

                if (!Boolean.TRUE.equals(success)) {
                    throw new IllegalStateException(
                            "Biên dịch thất bại: " + diagnostics.getDiagnostics());
                }
            }

            // Bước 3: nạp/định nghĩa lớp từ .class vừa được sinh.
            URL[] urls = { dir.toUri().toURL() };
            try (URLClassLoader loader = new URLClassLoader(
                    urls, CompileAtRuntime.class.getClassLoader())) {

                Class<?> type =
                        Class.forName("RuntimeOnlyGreeting", true, loader);

                // Bước 4: sử dụng lớp mới qua Reflection.
                Object instance = type.getDeclaredConstructor().newInstance();
                System.out.println(type.getMethod("message").invoke(instance));
            }
        } finally {
            // Ví dụ chỉ sinh đúng một file .java và một file .class.
            Files.deleteIfExists(dir.resolve("RuntimeOnlyGreeting.class"));
            Files.deleteIfExists(sourceFile);
            Files.deleteIfExists(dir);
        }
    }
}
~~~

Chạy trong thư mục chứa file ví dụ:

~~~bash
javac -encoding UTF-8 CompileAtRuntime.java
java CompileAtRuntime
~~~

Kết quả trên stdout:

~~~text
Xin chào từ mã vừa biên dịch!
~~~

Sơ đồ trách nhiệm tương ứng:

| Đoạn mã | Vai trò | Điều nó chưa tự làm |
| --- | --- | --- |
| **Files.writeString** | Tạo source Java mới | Không biên dịch hoặc nạp lớp |
| **JavaCompiler.getTask(...).call()** | Phân tích, kiểm tra và biên dịch source; xuất file .class | Không tự gọi method của class mới |
| **new URLClassLoader(...)** | Chuẩn bị đường tìm class cho loader | Tạo loader chưa có nghĩa mọi class được nạp |
| **Class.forName(..., true, loader)** | Yêu cầu tìm/tải, định nghĩa nếu cần và khởi tạo lớp | Không tạo source hay biên dịch source |
| **getMethod(...).invoke(...)** | Gọi hành vi trên đối tượng của lớp đã định nghĩa | Không tạo thêm lớp chỉ vì dùng Reflection |

**Điểm quan trọng:** Ví dụ này sinh một tên lớp mới (**RuntimeOnlyGreeting**) mà loader cha không có; **URLClassLoader** có thể đọc .class từ thư mục tạm. Loader cuối cùng sử dụng cơ chế định nghĩa lớp của JVM. Code không trực tiếp gọi **ClassLoader.defineClass**, nhưng bước **định nghĩa** vẫn đã diễn ra.

Một số điều kiện thực tế: **ToolProvider.getSystemJavaCompiler()** có thể trả về **null** nếu runtime không cung cấp compiler; mã nguồn phải hợp lệ; tên file public class phải khớp; dependency và compiler options phải được cấu hình chính xác. JavaCompiler có thể biên dịch source trong bộ nhớ bằng **JavaFileObject/FileManager** tùy biến, không nhất thiết phải ghi .java/.class xuống ổ đĩa như ví dụ học tập.

## 5. Định nghĩa lớp trực tiếp từ bytecode: không bắt buộc có source Java

Nếu đã có một mảng byte biểu diễn file .class hợp lệ, code có thể định nghĩa lớp mà **không gọi JavaCompiler**. Bytecode đó có thể do một bytecode generator sinh trong runtime, do một chương trình khác biên dịch từ trước, hoặc được đọc từ một nguồn bên ngoài.

Các API/cơ chế thường gặp:

- **ClassLoader.defineClass(...)**: API protected, được subclass của class loader sử dụng khi cần định nghĩa class từ bytecode. Không thể tùy tiện gọi protected method này từ mọi lớp ở mọi ngữ cảnh.
- **MethodHandles.Lookup.defineClass(byte[])**: định nghĩa một class thông thường từ bytecode trong **cùng runtime package và class loader** với lookup class, với các quyền truy cập cần thiết; nó không tự thực hiện static initialization.
- **MethodHandles.Lookup.defineHiddenClass(...)**: phục vụ các class ẩn cho cơ chế runtime chuyên biệt; danh tính và quy tắc tra cứu khác class thông thường.
- **java.lang.reflect.Proxy**: có thể tạo class proxy tại runtime để triển khai các interface đã biết. Điều này tạo class runtime mới dù ứng dụng không tự viết và biên dịch một chuỗi source Java.
- Thư viện như **Byte Buddy** hoặc **ASM** có thể xây dựng bytecode trực tiếp, nhưng là thư viện bổ sung chứ không phải hành vi mặc định của Reflection.

Đoạn sau **chỉ minh họa một bước API, không phải chương trình chạy độc lập**; biến **bytes** phải chứa file class hợp lệ đã được chuẩn bị, tên package của class phải tương thích với lookup và lookup phải có quyền **PACKAGE**:

~~~java
// bytes: bytecode hợp lệ của một class chưa được định nghĩa
// trong class loader/package tương ứng.
byte[] bytes = obtainValidClassBytes();
Class<?> defined = java.lang.invoke.MethodHandles
        .lookup()
        .defineClass(bytes);
~~~

Hàm **obtainValidClassBytes()** ở đây là ký hiệu minh họa, không thuộc Java SE. Đoạn này chứng minh sự tách biệt: **định nghĩa lớp từ bytes** là một bước riêng; không có thao tác tạo source hay gọi javac.

Nếu bytes không hợp lệ, không đúng package/quyền truy cập, sai phiên bản bytecode, hoặc trùng tên class đã được định nghĩa trong cùng loader, API có thể phát sinh lỗi tương ứng (**ClassFormatError**, **IllegalArgumentException**, **IllegalAccessException**, **UnsupportedClassVersionError**, **LinkageError**, ...).

## 6. Bảng phân loại các tình huống thực tế

| Tình huống | Tạo source mới trong runtime? | Sinh/biên dịch bytecode mới trong runtime? | Có thể định nghĩa class runtime mới? | Diễn giải đúng |
| --- | --- | --- | --- | --- |
| **new MyService()** với class có sẵn | Không | Không | Có, nếu class lần đầu được loader tải/định nghĩa | Sử dụng mã đã biên dịch |
| **Class.forName("plugin.Impl")** với .jar có sẵn | Không | Không | Có, nếu class chưa được định nghĩa bởi loader | Nạp và sử dụng mã đã biên dịch theo tên |
| **ServiceLoader.load(MyService.class)** tìm provider đã đóng gói | Không | Không | Có thể | Phát hiện/khởi tạo provider có sẵn, không tự biên dịch provider |
| **JavaCompiler** biên dịch source sinh ra từ template | Có | Có khi biên dịch thành công | Chỉ khi bytecode sau đó được tải/định nghĩa | Sinh source + biên dịch động |
| Chương trình **đọc .class đã có rồi gọi defineClass** trong loader mới | Không | Không | Có | Định nghĩa từ bytecode có sẵn |
| **Proxy.newProxyInstance(...)** | Không phải source Java do ứng dụng cung cấp | Có thể sinh bytecode proxy khi cần | Có | Runtime tạo proxy class, khác với chỉ gọi Reflection |
| Generator **ASM/Byte Buddy** sinh bytes và định nghĩa class | Không bắt buộc | Có | Có | Tạo class từ bytecode trực tiếp |
| **JIT** tối ưu một method đang chạy | Không | Không sinh file .class mới | Không phải vì riêng bước JIT | Biên dịch bytecode sang mã máy, một nghĩa khác của “compile” |

Từ bảng này có thể rút ra ba quy tắc:

1. **Reflection không mặc định là code generation**: Reflection có thể quan sát và gọi thành viên trên các class đã tồn tại.
2. **Tạo bytecode chưa đồng nghĩa với tải lớp**: compiler có thể tạo .class nhưng chương trình chưa sử dụng hoặc định nghĩa lớp ấy.
3. **Tải/định nghĩa lớp chưa đồng nghĩa với biên dịch động**: loader thường chỉ đọc bytecode đã được build sẵn.

## 7. Danh tính class loader và vì sao lớp mới không đơn giản là “ghi đè lớp cũ”

Trong JVM, danh tính của một class thông thường được xác định bởi **binary name** (ví dụ **com.example.Plugin**) **và class loader định nghĩa**. Hai file .class cùng tên do hai loader khác nhau định nghĩa là hai kiểu khác nhau trong runtime; không thể mặc nhiên ép kiểu đối tượng của lớp này sang lớp kia.

Ví dụ khái niệm:

~~~text
Loader A định nghĩa com.example.Plugin -> Class A
Loader B định nghĩa com.example.Plugin -> Class B

Cùng binary name, nhưng Class A != Class B.
Đối tượng của Class A không tự động là đối tượng của Class B.
~~~

Trong một loader, **không thể định nghĩa lại cùng binary name như một lớp thông thường khác** bằng cách gọi lại defineClass; việc cố gắng trùng định nghĩa sẽ gặp lỗi liên kết. Thay file .class trên đĩa cũng **không làm thay đổi** định nghĩa đang sống trong loader.

Muốn triển khai phiên bản mới khi ứng dụng vẫn chạy, một cách thiết kế là dùng **loader mới** để nạp phiên bản mới, chuyển các tham chiếu nghiệp vụ sang instance mới, rồi cho các object/loader cũ hết được giữ tham chiếu nếu muốn JVM có cơ hội giải phóng. Không nên diễn giải đây là thay thế class cũ “tại chỗ”; các instance cũ vẫn thuộc class của loader cũ. Cơ chế **Instrumentation/redefinition** có hợp đồng và giới hạn riêng, không phải hệ quả tự động của JavaCompiler hoặc defineClass.

Class loader thông thường theo mô hình **parent delegation** sẽ hỏi parent trước. Vì vậy việc đặt bytecode mới cùng tên một lớp đã thấy ở parent không bảo đảm loader con sẽ chọn bản mới. Với plugin, cần thiết kế rõ policy classpath, parent, package được chia sẻ, interface/API chung và vòng đời loader. Đóng **URLClassLoader** giúp giải phóng các tài nguyên I/O do nó giữ, nhưng **không bảo đảm** class sẽ lập tức được unload; unload phụ thuộc khả năng thu hồi class loader và các tham chiếu liên quan.

## 8. Phân biệt các loại “động” thường gặp trong Java

**Dynamic dispatch:** Khi gọi một method override qua interface/base class, runtime chọn implementation theo kiểu thực tế của object. Tính “động” ở đây là **chọn method**, không nhất thiết tạo/biên dịch class mới.

**Reflection:** Runtime xem metadata, tìm constructor/method/field và truy cập theo quy tắc visibility/modules. Nó làm cách sử dụng class linh hoạt hơn, nhưng các thành viên được gọi thường đã nằm trong bytecode có sẵn.

**MethodHandle và invokedynamic:** Hỗ trợ mô hình liên kết lời gọi linh hoạt ở JVM. Tên “dynamic” không có nghĩa cứ sử dụng chúng thì source Java mới được biên dịch. Một số cơ chế nội bộ hoặc framework có thể sinh class phụ trợ/hidden class, nhưng cần phân tích cụ thể từng cơ chế.

**Dynamic proxy/code generation:** Runtime sinh cấu trúc class/bytecode để tạo interceptor, adapter hoặc triển khai interface, thường không cần phát sinh source .java đọc được.

**Runtime Java compilation:** Ứng dụng chủ động phát sinh/nhận source, chạy compiler rồi xử lý .class mới. Đây là phương án rõ nhất khi đề bài thực sự cần “biên dịch Java ngay trong lúc ứng dụng chạy”, đổi lại cần compiler, nguồn phụ thuộc, xử lý diagnostics và quản lý loader.

**JIT compilation:** JVM tối ưu bytecode đã nạp thành mã máy phục vụ thực thi. Đừng đánh đồng với API **JavaCompiler** hoặc trình biên dịch **javac** tạo .class.

## 9. Lựa chọn cơ chế phù hợp

| Yêu cầu thực tế | Hướng tiếp cận thường phù hợp | Cân nhắc |
| --- | --- | --- |
| Gọi code ứng dụng đã biết ở thời điểm build | Reference tĩnh, interface, dependency injection | Đơn giản; dễ kiểm tra kiểu và triển khai |
| Chọn implementation theo cấu hình/tên lớp, implementation đã build | Interface + **ServiceLoader** hoặc **Class.forName** | Quản lý classpath/module path, hợp đồng API, constructor |
| Nạp plugin .jar mà không restart | Class loader chuyên dụng, API plugin được chia sẻ | Phân tách class identity, vòng đời và giải phóng loader |
| Tạo đối tượng bao quanh interface để chặn method | **java.lang.reflect.Proxy** hoặc proxy framework | Phải nắm rõ giới hạn của interface/proxy và cách gọi |
| Sinh class theo schema hoặc cấu hình tốc độ cao | Bytecode generator như Byte Buddy/ASM | Phức tạp hơn, cần kiểm tra bytecode và phiên bản JVM |
| Thực thi source Java mới do hệ thống sinh | **JavaCompiler** + class loader, hoặc pipeline build riêng | Cần JDK/compiler, xử lý lỗi và bảo mật thực thi |

Không phải mọi nhu cầu “cấu hình động” đều cần tạo class mới. Nếu các biến thể chỉ là dữ liệu (quy tắc, tham số, chiến lược đã biết), ưu tiên cấu hình và các interface có sẵn trước khi đưa thêm bước biên dịch/định nghĩa class runtime.

## 10. Ràng buộc kỹ thuật và lỗi hay gặp

### 10.1. Compiler khác runtime chạy Java

**java** chạy ứng dụng đã biên dịch, còn **javac** là compiler; **ToolProvider.getSystemJavaCompiler()** cung cấp compiler chỉ khi môi trường runtime có implementation phù hợp (thường là JDK đầy đủ với **jdk.compiler**). Ứng dụng đóng gói bằng custom runtime image có thể thiếu module này. Cần kiểm tra trên đúng môi trường deploy, không chỉ trên máy phát triển.

### 10.2. Source/bytecode phải nhất quán

Public top-level class trong source phải phù hợp tên file khi dùng file Java thông thường. Cần tính tới import, classpath/module path, phiên bản target, encoding và API version. Bytecode sinh bởi JDK mới có thể không chạy trên JVM cũ, gây **UnsupportedClassVersionError**.

### 10.3. Biên dịch thành công chưa chắc tải được

Một class có thể compile được nhưng runtime thiếu dependency, khác phiên bản API hoặc sai khả năng truy cập module. Các lỗi điển hình bao gồm:

- **ClassNotFoundException:** thao tác tìm class theo tên không thấy class.
- **NoClassDefFoundError:** JVM không thể có định nghĩa cần thiết trong quá trình liên kết/sử dụng (ví dụ dependency thiếu hoặc lỗi khởi tạo trước đó).
- **ClassFormatError/VerifyError:** file class sai cấu trúc hoặc vi phạm yêu cầu bytecode.
- **LinkageError** và các lớp con: vấn đề liên kết như định nghĩa trùng, phiên bản class không tương thích.
- **ExceptionInInitializerError:** khởi tạo tĩnh của class gặp lỗi.

Lỗi khi biên dịch qua **JavaCompiler** cần được thu thập và trình bày bằng **DiagnosticCollector**, không chỉ ghi “compile failed”.

### 10.4. Class loader không phải sandbox bảo mật

Biên dịch và chạy source tùy ý tương đương cho code đó cơ hội thực hiện hành vi mà tiến trình JVM có quyền làm. Chỉ chuyển code sang class loader mới **không** làm code trở nên an toàn. Nếu có source/bytecode không đáng tin, cần thiết kế ranh giới thực thi riêng (ví dụ tiến trình cô lập, quyền hệ điều hành hạn chế, chính sách tài nguyên, giới hạn thời gian/bộ nhớ, kiểm soát đầu vào và auditing) phù hợp mô hình đe dọa. Không nên dựa vào Reflection, class loader hay tên package để kiểm soát quyền thực thi.

### 10.5. Quản lý tài nguyên và vòng đời

Biên dịch thường tốn CPU, bộ nhớ và I/O; tạo quá nhiều class/loader có thể tăng metadata trong metaspace, thời gian warm-up và rủi ro giữ tham chiếu lâu dài. Cần cache theo khóa/version thích hợp, đóng file manager/loader khi không còn dùng, theo dõi diagnostics và định nghĩa rõ chính sách nâng cấp plugin. Việc xóa file .class sau khi đã tải không tương đương unload class.

## 11. Tự kiểm tra

**Câu 1.** Ứng dụng đọc tên implementation từ config, gọi **Class.forName**, sau đó gọi method. Nó có tự biên dịch class mới không?

**Đáp án:** Không. Nó chọn và dùng class có bytecode sẵn. Nếu class chưa được loader định nghĩa, bước tải/định nghĩa có thể xảy ra tại runtime, nhưng không có bước compile Java mới.

**Câu 2.** Một chương trình dùng **JavaCompiler** để tạo **Plugin.class** trong thư mục tạm rồi kết thúc, không gọi loader. JVM đã sử dụng định nghĩa runtime của Plugin chưa?

**Đáp án:** Chưa, ít nhất không phải chỉ vì công đoạn biên dịch đó. File .class tồn tại chưa đủ để nói class đã được nạp/định nghĩa và sử dụng trong JVM ứng dụng.

**Câu 3.** Framework sinh bytecode bằng ASM, sau đó gọi API định nghĩa class; không tạo source .java. Có phải tạo class runtime mới không?

**Đáp án:** Có. Việc sinh bytecode và định nghĩa class không đòi phải có source Java tương ứng.

**Câu 4.** Hai loader khác nhau cùng định nghĩa tên **example.Plugin**. Có thể xem là cùng một kiểu chỉ vì tên giống nhau không?

**Đáp án:** Không. Danh tính class bao gồm cả loader định nghĩa; phải tính khả năng tương thích kiểu và interface chung.

**Câu 5.** Sau khi chương trình chạy, JVM JIT một phương thức. Điều đó có nghĩa ứng dụng vừa sinh source Java và gọi javac không?

**Đáp án:** Không. JIT tối ưu bytecode sang mã máy để chạy, khác đường đi từ source Java sang file .class.

## Ghi nhớ

- **Sử dụng code đã biên dịch** trả lời câu hỏi “chương trình chạy hành vi từ bytecode nào?”.
- **Tạo source** trả lời câu hỏi “source mới được sinh/thu nhận ở đâu?”.
- **Biên dịch** trả lời câu hỏi “source đã được biến thành bytecode chưa?”.
- **Định nghĩa class** trả lời câu hỏi “loader nào đã đưa bytecode thành một kiểu runtime trong JVM?”.
- Bốn hoạt động có thể xảy ra kết hợp, nhưng **không nên dùng một thuật ngữ thay cho tất cả**. Đặc biệt, **Class.forName/Reflection không tự là JavaCompiler**, và **JavaCompiler không tự là bước định nghĩa/sử dụng class**.

## Tài liệu tra cứu

- Java SE 17, **JavaCompiler / ToolProvider**: https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/ToolProvider.html
- Java SE 17, **MethodHandles.Lookup**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html
- Java SE 17, **ClassLoader**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html
- Java Language Specification, **Chapter 12 — Execution**: https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html
