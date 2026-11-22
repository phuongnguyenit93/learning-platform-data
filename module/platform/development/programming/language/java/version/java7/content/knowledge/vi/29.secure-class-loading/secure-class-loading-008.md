# Kiểm thử đóng ClassLoader và thay đổi tài nguyên một cách an toàn

## 1. Bài toán: khi nạp plugin/JAR động, đóng loader có ý nghĩa gì?

Giả sử một ứng dụng Java mở một plugin từ file **plugin.jar**. Plugin chứa một lớp **sample.extension.Greeting** và một tài nguyên **config/version.txt**. Ban đầu lớp trả về **v1**, nội dung tài nguyên cũng là **v1**. Khi triển khai phiên bản **v2**, chúng ta muốn bảo đảm rằng:

1. Loader cũ đã được đóng để không tiếp tục mở thêm class/resource riêng từ JAR cũ.
2. Những luồng đọc tài nguyên và file JAR do loader mở được quản lý đúng, tránh khóa file hay rò rỉ file descriptor.
3. Loader mới có thể đọc **v2**; không nhầm với lớp hoặc resource **v1** đã được cache/nạp bởi loader cũ.
4. Hệ thống không dựa vào một giả định sai như “gọi close sẽ hủy mọi đối tượng và unload toàn bộ lớp”.
5. Không có thread nào còn sử dụng loader trong lúc thay thế; quy trình đóng và chuyển phiên bản có điểm đồng bộ rõ ràng.

Trọng tâm là **kiểm thử vòng đời loader và sự thay đổi tài nguyên**. API phù hợp nhất để minh họa là **java.net.URLClassLoader**, vì nó triển khai **Closeable/AutoCloseable** và có phương thức **close()**. Đừng áp dụng mù quáng hợp đồng đóng này cho mọi lớp kế thừa **ClassLoader**: bản thân **ClassLoader** không có một phương thức close() chung.

### Kỳ vọng đúng và kỳ vọng sai

| Sự kiện | Điều có thể kỳ vọng theo hợp đồng URLClassLoader |
| --- | --- |
| Trước close | Có thể nạp class/resource từ các URL mà loader quản lý, nếu tồn tại và quyền truy cập hợp lệ |
| Sau close | Loader không còn nạp được class/resource **mới do chính loader định nghĩa/tìm trong URL của nó** |
| Sau close, lớp đã được nạp | Đối tượng **Class** và instance đã có **vẫn dùng được**; close không hủy chúng |
| Sau close, class/resource do parent cung cấp | Vẫn có thể truy cập thông qua cơ chế delegation |
| Sau close, JAR/file đã được loader mở | **URLClassLoader.close()** cố gắng đóng các file do loader mở; có thể ném **IOException** |
| Mở loader mới trỏ tới artifact đã cập nhật | Có thể tải class/resource phiên bản mới, nếu cha không chặn bằng delegation và không có cache/file handle bên ngoài gây nhiễu |
| Gọi close | **Không** bảo đảm GC chạy, **không** ép unload lớp, **không** tự dừng thread, **không** đóng mọi resource do code plugin tự tạo |
| Đóng trong lúc thread khác đang load | Kết quả của thao tác nạp đồng thời **không được bảo đảm**; phải tự đồng bộ vòng đời |

Vì vậy, một test chỉ kiểm tra **loader.close() không ném exception** là **chưa đủ**. Cần kiểm chứng **hành vi sau close**, **nội dung resource trước/sau khi thay artifact**, **định danh lớp** và **giải phóng các tài nguyên liên quan**.

## 2. Hợp đồng của URLClassLoader.close()

Một cách dùng chuẩn:

~~~java
URL jarUrl = jarPath.toUri().toURL();

try (URLClassLoader loader = new URLClassLoader(
        new URL[] { jarUrl }, ClassLoader.getPlatformClassLoader())) {

    Class<?> plugin = loader.loadClass("sample.extension.Greeting");

    try (InputStream stream =
            loader.getResourceAsStream("config/version.txt")) {
        if (stream == null) {
            throw new FileNotFoundException("config/version.txt");
        }
        String text = new String(
                stream.readAllBytes(), StandardCharsets.UTF_8);
        System.out.println(text);
    }
} // Tự gọi loader.close() và stream.close() ở đúng phạm vi.
~~~

Đây là **đoạn minh họa**: cần import **URL, URLClassLoader, InputStream, FileNotFoundException, StandardCharsets**; cần khai báo **jarPath** và xử lý ngoại lệ I/O. Nó không phải chương trình tự chạy độc lập. Chương trình hoàn chỉnh nằm ở phần 6.

Các điểm chính:

- **try-with-resources** bảo đảm gọi **close()** cho loader khi rời phạm vi, kể cả khi khối lệnh ném exception. Nếu thao tác bên trong và close đều lỗi, Java giữ lỗi chính và có thể đưa lỗi đóng vào danh sách **suppressed exceptions**.
- **close()** của URLClassLoader có thể ném **IOException**. Không nên âm thầm bỏ qua vì lỗi này có thể báo file không được giải phóng hoàn toàn.
- Gọi close lần nữa lên loader đã đóng **không có hiệu ứng bổ sung** theo API.
- Khi đang có các tác vụ dùng loader, không thể coi close như phép hủy nguyên tử an toàn cho mọi thread. Hãy ngừng nhận công việc mới, đợi các tác vụ dùng plugin hoàn tất rồi đóng.
- API **getResourceAsStream(name)** trả **InputStream** hoặc **null** nếu không tìm thấy. Hãy đóng stream bằng try-with-resources dù loader sẽ xử lý các stream nó trực tiếp mở khi đóng.
- **ClassLoader.getResourceAsStream** và **URLClassLoader.getResourceAsStream** dùng cơ chế tìm resource có delegation. Không thể kết luận một resource chắc chắn được lấy từ plugin chỉ vì đã gọi qua đối tượng plugin loader.

**Lưu ý về stream:** Theo đặc tả URLClassLoader, các resource stream được mở **bằng chính phương thức getResourceAsStream của URLClassLoader** sẽ được đóng khi loader đóng. Tuy nhiên các stream, socket, JarFile, file watcher hoặc thread mà mã plugin tự mở không tự động thuộc quyền sở hữu của loader. Luôn đóng từng resource theo đúng nơi tạo ra nó. Một **URL** đã nhận từ getResource() rồi được bên ngoài mở bằng **URL.openStream()** cũng không nên được giả định là nằm trong cùng cơ chế tracking của loader; hãy tự quản lý stream đó.

## 3. Tách ba khái niệm: close, reload, unload

### Close: đóng khả năng truy cập mới của URLClassLoader

**close()** chuyển loader sang trạng thái không còn cung cấp class/resource **mới từ các URL riêng của nó**, đồng thời đóng những file đã mở mà nó quản lý. Nó **không xóa bytecode đã được định nghĩa trong JVM**.

### Reload: muốn lớp mới, thông thường cần loader mới

Một lớp Java được xác định bởi **tên nhị phân + class loader định nghĩa nó**, chứ không chỉ tên package/class. Nếu hai URLClassLoader khác nhau tự định nghĩa **sample.extension.Greeting**, JVM coi đó là **hai Class khác nhau** dù tên giống hệt. Vì vậy:

~~~java
Class<?> oldClass = oldLoader.loadClass(
        "sample.extension.Greeting");
Class<?> newClass = newLoader.loadClass(
        "sample.extension.Greeting");

boolean differentIdentity = oldClass != newClass;
~~~

Đây là minh họa: hai loader phải thật sự định nghĩa lớp này, không cùng được parent trả về. **differentIdentity** là **true** trong điều kiện đó. Nếu cả hai đều được parent nạp cùng một class, kết quả có thể là **false**. Một loader không thông thường “định nghĩa lại” cùng một binary name chỉ vì file JAR trên đĩa thay đổi.

### Unload: phụ thuộc tính còn sống của ClassLoader và GC

**Class unloading** chỉ có thể diễn ra khi JVM xác định lớp và loader tương ứng không còn được giữ sống bởi những root cần thiết. Giữ lại bất kỳ **Class**, instance, MethodHandle, stack frame, thread, context class loader, static cache hoặc tham chiếu khác có thể tiếp tục giữ loader/lớp sống. **close() không phải System.gc() và không bảo đảm unload**.

Tránh viết test kiểu **assert weakReference.get() == null** ngay sau **System.gc()**: GC không bảo đảm thu gom tại thời điểm cụ thể. Thay vào đó, kiểm tra các điều kiện tất định như:

- Tất cả tác vụ sử dụng loader đã kết thúc.
- Mọi stream, JarFile và handle thuộc quyền quản lý đã đóng.
- Loader cũ không nạp thêm lớp riêng mới.
- Loader mới đọc phiên bản cập nhật.
- Không còn cache/registration rõ ràng giữ loader cũ; dùng profiling/heap dump nếu nghi leak, không bắt test nghiệp vụ phụ thuộc thời điểm GC.

## 4. Thiết kế kiểm thử các tình huống có ý nghĩa

Một bộ kiểm thử thực tế nên có các kịch bản sau.

| Kịch bản | Chuẩn bị | Kết quả cần xác minh |
| --- | --- | --- |
| Nạp lần đầu | JAR v1 chứa class Greeting và resource version.txt v1 | Class trả v1, resource trả v1 |
| Đọc resource | Mở stream bằng getResourceAsStream | Đọc đúng UTF-8 và đóng stream |
| Đóng loader | Dùng try-with-resources hoặc close rõ ràng | Không xuất hiện IOException trong môi trường test thông thường |
| Nạp **class chưa từng nạp** sau close | JAR v1 có class Late nhưng trước close không yêu cầu loadClass(Late) | Với resource riêng và không có class trùng ở parent, loadClass(Late) ném ClassNotFoundException |
| Tìm **resource chưa sử dụng** sau close | JAR có config/late.txt không có ở parent | Không tìm được từ URL của loader đã đóng |
| Dùng class **đã nạp** sau close | Giữ lại tham chiếu tới Class Greeting | Vẫn có thể tạo đối tượng/gọi code của lớp đã nạp |
| Đổi artifact rồi tạo loader mới | Đóng loader v1, tạo JAR v2 cùng đường dẫn, tạo URLClassLoader mới | Class mới và resource mới trả v2 |
| So sánh class identity | Giữ Class v1, lấy Class v2 từ loader mới | Hai Class khác nhau nếu được hai loader định nghĩa |
| Đóng lặp lại | Gọi close lần hai | Không có hành động bổ sung |
| Resource không tồn tại | Dùng tên sai | getResourceAsStream trả null; test xử lý rõ |
| Parent chứa tài nguyên trùng tên | Parent và child đều có cùng resource | Cơ chế parent-first có thể trả bản của parent; không dùng kết quả này để chứng minh reload |
| Đọc JAR khi cập nhật | Stream cũ chưa đóng hoặc task còn hoạt động | Không được xem việc ghi đè an toàn; chuyển phiên bản khi tất cả công việc cũ đã dừng |

Để test đáng tin, dùng **tên package/resource duy nhất** không có ở classpath của ứng dụng thử nghiệm; đừng dùng **java.lang.String** hoặc resource quá phổ biến. Dùng **thư mục tạm** cho dữ liệu, không chỉnh classpath/JAR thật đang chạy. Dọn dữ liệu trong **finally** để không làm ô nhiễm môi trường kiểm thử.

## 5. Chọn parent loader và quản lý resource path

### Parent delegation có thể làm nhiễu kết quả

Trong Java, ClassLoader thường **ủy quyền tìm class/resource cho parent trước**. Ví dụ loader plugin trỏ tới JAR v2 nhưng application loader đã nạp một lớp có cùng tên từ JAR v1. **loadClass** qua loader mới có thể vẫn nhận class do parent định nghĩa. Khi đó, việc tạo **URLClassLoader mới** chưa đủ để quan sát v2.

Chương trình demo dùng:

~~~java
new URLClassLoader(
        new URL[] { jarPath.toUri().toURL() },
        ClassLoader.getPlatformClassLoader());
~~~

**ClassLoader.getPlatformClassLoader()** làm parent trong test. Với class plugin tự sinh chỉ dựa trên Java SE chuẩn, parent này không chứa **sample.extension.Greeting**. Nhờ vậy kiểm thử thật sự quan sát định nghĩa lớp của từng plugin loader. Đây là **cấu hình test**, không phải lời khuyên mọi plugin production đều nên dùng platform loader: plugin production thường cần thấy những API chung của host ở application loader để implement đúng interface.

Một thiết kế plugin thực tế nên để **API chung của host** trong parent loader ổn định, còn **implementation** trong plugin loader riêng. Cần tránh tạo hai phiên bản khác class loader của cùng một interface dự kiến dùng chung: khi đó có thể gặp **ClassCastException** dù tên lớp trông giống nhau.

### Tên tài nguyên không phải đường dẫn file hệ điều hành

Với **ClassLoader.getResourceAsStream** dùng tên resource **tương đối từ gốc classpath/JAR**, dùng dấu **/** bất kể hệ điều hành:

~~~java
loader.getResourceAsStream("config/version.txt");
~~~

Không thêm đường dẫn tuyệt đối của file trong JAR; tên thường **không bắt đầu bằng /**. API **Class.getResourceAsStream** có thêm quy tắc tương đối theo package của Class, khác cách dùng ClassLoader; hãy chọn API và tên nhất quán.

Resource có thể nằm trong directory hoặc JAR. Cần test **cả đường đọc chính** mà ứng dụng thực sự dùng: **ClassLoader.getResourceAsStream**, **Class.getResourceAsStream**, **Module.getResourceAsStream**, hoặc URL stream có semantics riêng. Trong **named modules**, quy tắc module encapsulation và mở package có thể ảnh hưởng việc tìm resource.

### Thay đổi resource không có nghĩa tự làm mới class đã load

Hai thao tác khác nhau:

- **Sửa file cấu hình ngoài JAR**: nếu code **mỗi lần đọc bằng Files.readString** trên Path thực tế, nó có thể thấy nội dung mới mà không thay ClassLoader. Nếu code cache nội dung trong một field, cần chính sách refresh cache riêng.
- **Sửa resource bên trong JAR và kỳ vọng loader cũ đọc bản mới**: không phải hợp đồng reload đáng tin cậy. JAR connection, file handles và class/resource lookup có thể cache; class đã định nghĩa càng không tự đổi bytecode. Hãy đóng luồng/loader, dựng artifact phiên bản mới và tạo loader mới khi cần reload.

Nếu cần hot reload trong production, ưu tiên artifact **được đánh version** (ví dụ plugin-v1.jar, plugin-v2.jar), chuẩn bị loader mới riêng, kiểm tra sức khỏe, chuyển routing rồi đóng loader cũ khi không còn công việc. **Không** ghi đè một JAR đang được sử dụng từ nhiều thread.

## 6. Chương trình Java 17+ hoàn chỉnh: đóng URLClassLoader, cập nhật JAR và kiểm thử v1/v2

Ví dụ tự dựng một JAR trong thư mục tạm. Nó tạo hai lớp:

- **sample.extension.Greeting** với phương thức **version()** trả chuỗi v1 hoặc v2.
- **sample.extension.Late**: được đóng gói nhưng **không nạp trước khi đóng loader**.

JAR cũng chứa **config/version.txt** và **config/late.txt**. Chương trình kiểm tra việc đọc **class + resource trước close**, không thể nạp thành viên mới **sau close**, lớp cũ vẫn dùng được và loader mới đọc **v2**. Demo sử dụng **JavaCompiler** của JDK, nên phải chạy bằng **JDK 17+ đầy đủ** (không chỉ runtime thiếu compiler module). Mọi file tạm được dọn trong **finally**.

Lưu mã bên dưới vào **LoaderLifecycleDemo.java**:

~~~java
import java.io.IOException;
import java.io.InputStream;
import java.io.UncheckedIOException;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.Comparator;
import java.util.stream.Stream;
import java.util.jar.JarEntry;
import java.util.jar.JarOutputStream;
import javax.tools.JavaCompiler;
import javax.tools.ToolProvider;

public class LoaderLifecycleDemo {
    private static final String NAME = "sample.extension.Greeting";
    private static final String RESOURCE = "config/version.txt";

    private static void add(JarOutputStream out, String name, byte[] bytes)
            throws IOException {
        out.putNextEntry(new JarEntry(name));
        out.write(bytes);
        out.closeEntry();
    }

    private static void buildJar(Path root, Path jar, String version)
            throws IOException {
        Path sourceDir = root.resolve("src/sample/extension");
        Path classes = root.resolve("classes");
        Files.createDirectories(sourceDir);
        Files.createDirectories(classes);

        Path greeting = sourceDir.resolve("Greeting.java");
        Path late = sourceDir.resolve("Late.java");
        Files.writeString(greeting,
                "package sample.extension; public class Greeting { "
                + "public String version() { return \"" + version + "\"; } }",
                StandardCharsets.UTF_8);
        Files.writeString(late,
                "package sample.extension; public class Late { }",
                StandardCharsets.UTF_8);

        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException("Cần JDK có javac");
        }
        int exit = compiler.run(null, null, null,
                "-encoding", "UTF-8",
                "-d", classes.toString(),
                greeting.toString(), late.toString());
        if (exit != 0) {
            throw new IllegalStateException("Compile failed: " + exit);
        }

        try (JarOutputStream out = new JarOutputStream(
                Files.newOutputStream(jar,
                        StandardOpenOption.CREATE,
                        StandardOpenOption.TRUNCATE_EXISTING))) {
            add(out, "sample/extension/Greeting.class",
                    Files.readAllBytes(
                            classes.resolve("sample/extension/Greeting.class")));
            add(out, "sample/extension/Late.class",
                    Files.readAllBytes(
                            classes.resolve("sample/extension/Late.class")));
            add(out, RESOURCE, version.getBytes(StandardCharsets.UTF_8));
            add(out, "config/late.txt",
                    "not-loaded".getBytes(StandardCharsets.UTF_8));
        }
    }

    private static String readResource(URLClassLoader loader)
            throws IOException {
        try (InputStream in = loader.getResourceAsStream(RESOURCE)) {
            if (in == null) {
                throw new IOException("Missing resource " + RESOURCE);
            }
            return new String(in.readAllBytes(), StandardCharsets.UTF_8);
        }
    }

    private static String invokeVersion(Class<?> greeting)
            throws ReflectiveOperationException {
        Object instance = greeting.getDeclaredConstructor().newInstance();
        return (String) greeting.getMethod("version").invoke(instance);
    }

    public static void main(String[] args) throws Exception {
        Path root = Files.createTempDirectory("loader-lifecycle-");
        try {
            Path jar = root.resolve("plugin.jar");
            buildJar(root, jar, "v1");
            URL location = jar.toUri().toURL();
            Class<?> oldClass;
            URLClassLoader first = new URLClassLoader(
                    new URL[] { location }, ClassLoader.getPlatformClassLoader());
            try (first) {
                oldClass = first.loadClass(NAME);
                System.out.println("firstClass=" + invokeVersion(oldClass));
                System.out.println("firstResource=" + readResource(first));
            }

            try {
                first.loadClass("sample.extension.Late");
                throw new AssertionError("Closed loader loaded a new class");
            } catch (ClassNotFoundException expected) {
                System.out.println("afterCloseNewClass=unavailable");
            }
            System.out.println("afterCloseNewResource="
                    + (first.getResource("config/late.txt") == null
                        ? "unavailable" : "still-visible"));
            System.out.println("oldClassAfterClose=" + invokeVersion(oldClass));

            buildJar(root, jar, "v2");
            try (URLClassLoader second = new URLClassLoader(
                    new URL[] { location }, ClassLoader.getPlatformClassLoader())) {
                Class<?> newClass = second.loadClass(NAME);
                System.out.println("newClass=" + invokeVersion(newClass));
                System.out.println("newResource=" + readResource(second));
                System.out.println("differentClassIdentity="
                        + (oldClass != newClass));
            }
        } finally {
            try (Stream<Path> stream = Files.walk(root)) {
                stream.sorted(Comparator.reverseOrder()).forEach(p -> {
                    try {
                        Files.deleteIfExists(p);
                    } catch (IOException e) {
                        throw new UncheckedIOException(e);
                    }
                });
            }
        }
    }
}
~~~

Biên dịch và chạy bằng terminal có **JDK 17+**:

~~~bash
javac LoaderLifecycleDemo.java
java LoaderLifecycleDemo
~~~

Kết quả kỳ vọng (đã biên dịch/chạy kiểm chứng với JDK 24 trên Windows):

~~~text
firstClass=v1
firstResource=v1
afterCloseNewClass=unavailable
afterCloseNewResource=unavailable
oldClassAfterClose=v1
newClass=v2
newResource=v2
differentClassIdentity=true
~~~

**Vì sao mỗi dòng có ý nghĩa?**

1. **firstClass/firstResource=v1**: loader đầu tìm đúng class và resource được đóng gói trong JAR v1. Resource stream được đóng ngay khi đọc xong.
2. **afterCloseNewClass=unavailable**: class **Late** nằm trong JAR nhưng không được load trước close. Sau close, loader đầu không thể lấy class mới từ JAR. Parent ở đây không chứa Late.
3. **afterCloseNewResource=unavailable**: tên **config/late.txt** chỉ nằm trong JAR v1 và chưa được lấy trước close. Sau close, kết quả **getResource** là null trong môi trường test này.
4. **oldClassAfterClose=v1**: giữ Class đã nạp nên vẫn tạo instance và gọi code v1 được; **close không unload** class ngay.
5. **newClass/newResource=v2**: sau khi đóng loader đầu và ghi JAR v2, loader thứ hai đọc được phiên bản mới.
6. **differentClassIdentity=true**: hai loader riêng đã định nghĩa hai class có cùng tên **sample.extension.Greeting**, nên danh tính runtime khác nhau.
7. Khối **finally** dùng **Files.walk** theo thứ tự đảo ngược để xóa file con trước thư mục cha. Một lỗi dọn file sẽ được truyền qua **UncheckedIOException**, không âm thầm báo test thành công.

**Phạm vi của demo:** ví dụ ghi lại **cùng đường dẫn plugin.jar** trong môi trường test tuần tự đã đóng loader v1, không phải chiến lược phát hành hot-reload cho production. Trong hệ thống thật, dùng **JAR mới có tên/version mới**, không sửa JAR đang được sử dụng. Demo cũng giữ lại tham chiếu **oldClass** có chủ đích để chứng minh close **không phải unload**; trong một bài test khả năng GC, phải loại bỏ mọi tham chiếu mạnh trước khi thảo luận chuyện class unloading.

### Kiểm chứng ngoài stdout

Để biến ví dụ thành integration test, thay một số **System.out.println** bằng assertions:

~~~java
// Phần minh họa, sử dụng các biến first/second từ ví dụ.
if (!"v1".equals(readResource(first))) {
    throw new AssertionError("Sai tài nguyên v1");
}
~~~

Tuy nhiên, hãy đặt assert **trước khi first bị close**. **Không sao chép đoạn này vào sau close** vì nó sẽ cố lấy lại resource từ loader đã đóng. Trong chương trình hoàn chỉnh, các dòng stdout và phép so sánh danh tính đã minh họa chính xác vị trí kiểm tra.

Có thể dùng **JUnit 5** cho integration test thực tế: **@TempDir** để tạo thư mục tạm; **assertThrows(ClassNotFoundException.class, ...)** cho lớp chưa load sau close; **assertEquals("v2", ...)** sau khi tạo loader mới; **assertNotSame(oldClass, newClass)** khi parent không định nghĩa class đó. Chú ý test chỉ kiểm chứng những hành vi được bảo đảm, không ép GC/unload theo thời gian cố định.

## 7. Quy trình an toàn để thay đổi resource hoặc plugin

Trong ứng dụng đang phục vụ yêu cầu người dùng, **đóng loader ngay khi có JAR mới** là cách dễ gây race condition. Một trình tự an toàn hơn:

~~~text
Nhận plugin-v2.jar (một artifact mới, bất biến)
        |
        v
Kiểm tra đường dẫn, metadata, checksum/chữ ký theo chính sách
        |
        v
Tạo URLClassLoader mới, nạp class và resource v2
        |
        v
Chạy health check, kiểm tra API/compatibility
        |
        v
Chuyển hướng công việc mới sang plugin v2
        |
        v
Chờ công việc đang dùng plugin v1 hoàn tất
        |
        v
Dừng thread, scheduler, stream, file watcher thuộc v1
        |
        v
Xóa đăng ký/caches/TCCL tham chiếu v1
        |
        v
Đóng loader v1 và kiểm tra lỗi close
        |
        v
Cho phép dọn artifact cũ khi không còn ai dùng
~~~

Điều kiện quan trọng:

- **Quản lý ownership**: lớp nào tạo **URLClassLoader** thường là lớp chịu trách nhiệm đóng nó. Không để một request nhỏ đóng loader đang được nhiều request khác dùng chung.
- **Dùng versioned artifacts**: đường dẫn riêng cho từng version giúp tránh ghi đè file đang mở và hỗ trợ rollback.
- **Chặn việc nạp mới qua loader cũ** trước khi đóng. **close()** không được bảo đảm an toàn khi thread khác đang load; cần một điểm chuyển trạng thái/đồng bộ ở phía quản lý.
- **Không để lại thread/plugin task**: một thread với **contextClassLoader** trỏ đến loader cũ, hoặc singleton/cache giữ instance plugin, có thể khiến loader không đủ điều kiện GC.
- **Không thay đổi một file JAR đang được đọc**. Trên Windows nó có thể bị khóa; trên những hệ điều hành khác ghi đè có thể dẫn đến hành vi khó đoán. Không xây dựng tính đúng đắn dựa vào một hệ điều hành cụ thể.
- **Nếu close ném IOException**, log thông tin phù hợp và quyết định chính sách lỗi dọn dẹp; không giả định mọi file đã giải phóng.
- **Dữ liệu cần di chuyển giữa v1/v2** nên dùng DTO/API có lớp được định nghĩa bởi parent loader chung; đừng cast trực tiếp instance của cùng-named class v1 sang class v2.

### Kiểm thử hot swap có nhiều thread

Một integration test riêng nên chạy **nhiều tác vụ đang dùng loader v1**, chuẩn bị v2 và kiểm tra rằng:

1. Tác vụ v1 đang chạy hoàn tất hoặc được dừng theo giao thức đã định.
2. Công việc mới sau điểm chuyển tiếp luôn đi qua v2.
3. Không có thread vừa **loadClass** trong loader v1 vừa bị gọi close bởi thread quản lý.
4. Các request không nhận pha trộn class của v1 và resource của v2.
5. Không còn resource stream/scheduler/watch service thuộc v1 sau khi shutdown.
6. Khởi động lại hoặc rollback sang một artifact riêng hoạt động dựa trên chính loader mới, không “mở lại” loader đã close.

Đối với **Thread Context ClassLoader (TCCL)**, code thực thi plugin có thể tạm đặt TCCL để tìm service/resource. Phải **khôi phục TCCL cũ trong finally**, nhất là khi chạy trên thread pool. Không đặt TCCL vĩnh viễn của worker threads sang loader plugin rồi kỳ vọng close sẽ tự dọn tham chiếu.

## 8. Những giới hạn dễ bị bỏ qua khi kiểm thử file và resource

### Stream đã mở không tự biến thành nội dung mới

Ví dụ:

~~~java
try (InputStream in = loader.getResourceAsStream(
        "config/version.txt")) {
    if (in == null) {
        throw new IOException("Resource not found");
    }
    byte[] snapshot = in.readAllBytes();
}
~~~

Đoạn này chỉ là minh họa trong một phương thức khai báo/handle **IOException**, với biến **loader** còn mở. **snapshot** là dữ liệu byte đã đọc ở thời điểm đó. Nếu file trên đĩa thay đổi sau đó, mảng byte cũ **không tự cập nhật**. Nếu một thư viện lưu cache bản parse của resource, cần cơ chế invalidation riêng; URLClassLoader mới không tự xóa mọi cache ứng dụng.

**Resource path** có thể bị shadow bởi parent hoặc classpath khác; tên resource không đủ để chứng minh nó đến từ JAR nào. Khi chẩn đoán, trong lúc loader còn mở có thể ghi lại:

~~~java
URL resourceUrl = loader.getResource("config/version.txt");
System.out.println(resourceUrl);
~~~

Đây là đoạn minh họa; URL thu được giúp kiểm tra vị trí nguồn, nhưng không phải lời hứa rằng sau khi loader đóng, **URL.openStream()** vẫn đọc được dữ liệu cũ. Một URL có thể mở kết nối mới hoặc chịu cơ chế caching và lifetime khác. Đừng dùng việc đọc URL sau close để thay cho kiểm thử hợp đồng **loader.getResource...**.

### Khóa file trên Windows và Unix

Khi một JAR đang được **JarFile/URLClassLoader** mở, thao tác **ghi đè/xóa/đổi tên** có thể bị hạn chế trên Windows do file handle còn giữ. Trên Unix, việc xóa một đường dẫn không nhất thiết đóng file descriptor còn đang mở, nên “xóa thành công” cũng không chứng minh không rò rỉ. Kiểm tra theo **ownership + close + trạng thái tác vụ**, không chỉ theo kết quả Files.delete.

### JarURLConnection và cache

**URLConnection** có chính sách **useCaches** và JAR URL connection có thể dùng cache riêng. Nếu ứng dụng mở resource URL bằng các API ngoài vòng đời loader, nó có thể giữ file JAR hoặc bản nội dung không mong muốn. Đóng **URLClassLoader** không thay thế việc quản lý toàn bộ các connection/stream được tạo bên ngoài. Với hệ thống cần thay nóng thường xuyên, hãy test việc mở và đóng resource theo đúng API sản xuất và tránh coi một cache implementation-specific là hợp đồng portable.

### Resource bị thiếu và lỗi I/O không cùng nghĩa

- **getResourceAsStream** trả **null** khi không tìm được resource (cũng có thể do quy tắc module visibility), chứ không phải tự tạo file rỗng.
- Trong khi **đọc một InputStream đã mở**, I/O có thể lỗi; phải phân biệt **resource absent** và **read failure**.
- **close()** có thể ném IOException; không đánh đồng với ClassNotFoundException.
- **ClassNotFoundException** khi thử nạp lớp chưa có sau close là một hành vi có thể kiểm chứng trong test cô lập, nhưng nếu parent có class cùng tên, **loadClass** vẫn có thể trả class parent.
- **NoClassDefFoundError** cũng có thể phát sinh do phụ thuộc cần resolve/khởi tạo không còn sẵn, không được dùng như tín hiệu chung rằng close đã thành công.

## 9. Không nhầm ClassLoader với ranh giới bảo mật

ClassLoader giúp **tách không gian tên class và cách tra cứu resource**, nhưng **không phải sandbox bảo mật** cho code Java không đáng tin. Đóng loader cũng không “thu hồi” khả năng thực thi của instance đã chạy hoặc ngăn code plugin mở file/socket qua những API mà ứng dụng cho phép.

Với plugin bên thứ ba hoặc resource từ nguồn bên ngoài:

- Chỉ chấp nhận artifact từ **nguồn tin cậy**, kiểm tra checksum/chữ ký theo mô hình triển khai.
- Kiểm soát đường dẫn đầu vào, **symlink**, traversal, quyền ghi thư mục và artifact thay đổi trong thời gian kiểm tra; dùng cấu trúc versioned immutable.
- Dùng API/module boundary rõ ràng, ưu tiên chỉ công khai những hợp đồng cần thiết.
- Không kỳ vọng ClassLoader hoặc **SecurityManager** kiểu cũ bảo vệ quy trình khỏi bytecode ác ý; SecurityManager đã bị loại bỏ khỏi các phiên bản JDK mới, không phù hợp làm nền tảng sandbox.
- Nếu phải chạy code không tin cậy, sử dụng **process/container isolation**, hệ thống quyền OS, tài nguyên giới hạn và giao thức giao tiếp rõ ràng.

Bài test vòng đời loader xác minh **quản lý tài nguyên và versioning**; nó **không chứng minh plugin an toàn để chạy** chỉ vì class/resource được nạp đúng và loader đóng thành công.

## 10. Ma trận lỗi, nguyên nhân và cách khắc phục

| Triệu chứng | Nguyên nhân có thể | Phép kiểm chứng / cách sửa |
| --- | --- | --- |
| Close xong nhưng vẫn gọi được code v1 | Class đã nạp và instance vẫn sống | Đây là hành vi bình thường; đừng coi close là unload |
| Close xong vẫn tìm thấy một class/resource | Parent delegation hoặc class đã nạp trước | Kiểm tra defining loader và tên resource/class có trong parent |
| Sau cập nhật JAR vẫn thấy v1 | Dùng loader cũ, parent shadow, cache ứng dụng hoặc connection cache | Tạo loader mới, dùng artifact versioned và test class identity |
| Không ghi đè/xóa JAR được trên Windows | Còn stream, JarFile, loader, hoặc URLConnection giữ file | Đóng toàn bộ tài nguyên và dùng JAR versioned |
| Reload v2 gây ClassCastException khi ép sang type v1 | Cùng tên nhưng được hai loader khác nhau định nghĩa | Giao tiếp qua interface/DTO của parent chung, không cast v1 sang v2 |
| getResourceAsStream trả null | Sai tên, resource thiếu, parent/module visibility hoặc loader đã đóng | Kiểm tra path với dấu /, đóng/mở đúng loader, log resource URL lúc còn mở |
| IOException khi close | Có lỗi khi đóng file/stream do loader quản lý | Log và báo lỗi lifecycle, không bỏ qua |
| Sau đóng vẫn thấy thread/counter plugin hoạt động | Thread/scheduler/instance vẫn giữ loader sống | Shutdown task, TCCL và cache trước close |
| Test unload thất bại không ổn định | Dựa vào System.gc và timing | Dùng heap profiler/WeakReference cho quan sát, không assertion GC tức thời |
| Resource v2 tải được nhưng class vẫn v1 | Resource được đọc lại, class cũ đã load hoặc parent cung cấp class | Test lớp do loader nào định nghĩa, dùng loader mới và versioned JAR |
| Một thread đang nạp class khi thread khác close | Thiếu giao thức shutdown và đồng bộ | Ngừng nhiệm vụ mới, đợi in-flight load xong rồi close |
| File temp còn sót sau test | Thiếu finally/close stream hoặc cleanup theo thứ tự sai | Dọn file trong finally, đóng stream và xóa con trước cha |

## 11. Checklist áp dụng cho ứng dụng thực tế

**Trước khi chạy test:**

1. Xác nhận loại loader có **close()** và rõ ownership; không tự giả định ClassLoader nói chung đều closeable.
2. Chọn tên class/resource duy nhất để loại trừ parent shadowing, hoặc kiểm tra rõ định danh defining loader.
3. Chuẩn bị artifact v1/v2 cố định và đường dẫn tạm độc lập, không sửa JAR production.
4. Thiết lập charset chuẩn (UTF-8), resource path dùng dấu **/** và các assertions rõ ràng.

**Trong test:**

1. Mở loader v1, load một class, đọc một resource có stream đóng đúng.
2. Chụp Class và giá trị v1, sau đó đóng loader v1.
3. Test class/resource **chưa được load/tìm** không còn được loader cũ cung cấp; đồng thời xác nhận class đã nạp vẫn dùng được.
4. Tạo artifact v2 và **loader mới**, kiểm tra nội dung class + resource v2 và **Class identity**.
5. Kiểm tra mọi thread/stream/file handle được đóng, kể cả khi test ném exception.
6. Dọn thư mục tạm trong finally; với kiểm thử riêng cho Windows, quan sát việc file không còn bị khóa sau shutdown.

**Trong production:**

1. Dùng **versioned immutable artifact**, chuyển lưu lượng sau health check.
2. Ngừng công việc mới vào v1, chờ công việc cũ kết thúc trước khi đóng loader.
3. Giải phóng stream, scheduler, thread, TCCL, cache và references của plugin cũ.
4. Đừng kết luận class unloading thành công từ **close** hoặc lần gọi GC riêng.
5. Nếu cần reload config liên tục, chọn chiến lược cache/refresh riêng thay vì mong classpath tự cập nhật.
6. Ghi log theo **plugin version + loader identity + resource origin** để điều tra nhầm phiên bản.

### Câu hỏi tự kiểm tra

1. **URLClassLoader.close() có xóa mọi lớp đã nạp không?** Không. Class đã nạp vẫn dùng được nếu còn tham chiếu.
2. **Vì sao thử class Late chưa nạp sau close?** Để kiểm chứng loader không thể nạp class mới từ JAR của nó; nếu chỉ thử class đã nạp thì không chứng minh được điều này.
3. **Vì sao loader mới có thể trả Class khác dù binary name giống?** Định danh class JVM phụ thuộc cả defining loader.
4. **getResourceAsStream("config/version.txt") sau close có thể trả từ parent không?** Có, nếu parent cung cấp resource đó; test cần cách ly nguồn.
5. **Xóa thành công JAR có chứng minh không rò rỉ file handle?** Không, đặc biệt trên hệ điều hành cho phép unlink khi descriptor vẫn mở.
6. **Nếu sửa JAR trong lúc loader vẫn chạy, kết quả reload có được bảo đảm không?** Không. Hãy dùng artifact mới và quy trình chuyển phiên bản.
7. **close có tự dừng các thread plugin không?** Không. Phải dừng và dọn chúng theo lifecycle.
8. **Kiểm thử có nên bắt buộc System.gc() làm oldClass biến mất ngay?** Không. Class unloading không có deadline bảo đảm.
9. **Trong module system, vì sao resource có thể không tìm thấy dù file tồn tại?** Vì quy tắc visibility/encapsulation của named modules và cách lookup resource.
10. **ClassLoader có đủ để sandbox mã không tin cậy không?** Không. Cần cách ly process/container và chính sách bảo mật phù hợp.

**Ghi nhớ:** Để kiểm thử an toàn việc đóng loader và thay đổi tài nguyên, cần xác minh **v1 trước close → giới hạn nạp mới sau close → v2 qua loader mới**, đồng thời phân biệt rõ **close, reload và class unloading**. Kết hợp try-with-resources, tên resource chính xác, parent delegation được kiểm soát, artifact versioned và quy trình shutdown không race condition.

**Tài liệu tham khảo đang còn áp dụng:**

- [Oracle Java SE 25 — URLClassLoader](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/net/URLClassLoader.html): close(), getResourceAsStream(), hành vi với JAR/file đã mở.
- [Oracle Java SE 25 — ClassLoader](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/ClassLoader.html): parent delegation, loadClass và resource lookup.
- [Oracle Java SE 25 — JavaCompiler](https://docs.oracle.com/en/java/javase/25/docs/api/java.compiler/javax/tools/JavaCompiler.html): compile source trong ví dụ JDK.
- [Oracle Java SE 25 — JarOutputStream](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/jar/JarOutputStream.html): xây dựng JAR trong test.
