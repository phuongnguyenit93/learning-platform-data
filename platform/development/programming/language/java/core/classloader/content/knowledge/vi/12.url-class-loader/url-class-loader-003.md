# Thứ tự URL và xử lý JAR hoặc lớp trùng nhau trong URLClassLoader

## 1. Vấn đề: nhiều nguồn có cùng một binary name

Trong hệ Java sử dụng nhiều thư viện, hai file JAR có thể cùng chứa `com.example.lib.Parser.class` nhưng ở **hai phiên bản** khác nhau. Một `URLClassLoader` có thể được tạo với danh sách URL trỏ tới nhiều JAR hoặc thư mục:

```java
try (URLClassLoader loader = new URLClassLoader(
        new URL[] {firstJarUrl, secondJarUrl},
        parentLoader)) {
    Class<?> parser = loader.loadClass("com.example.lib.Parser");
}
```

Đây là **đoạn minh họa**; biến URL và parent phải được ứng dụng cung cấp. Câu hỏi quan trọng là: nếu cả hai URL đều chứa `Parser.class`, JVM có nạp hai bản rồi chọn bản mới nhất, hay có một quy tắc ưu tiên khác?

Trong mô hình thông thường:

1. `URLClassLoader` kế thừa thuật toán `ClassLoader.loadClass` có **parent-first delegation**. Nếu parent cung cấp được class, loader con nhận ngay class của parent và không cần tìm các URL cục bộ.
2. Nếu parent không tìm được class, `URLClassLoader` tìm bytecode trong **các URL thuộc đường tìm của chính loader đó**, theo thứ tự tìm kiếm đã cấu hình và cơ chế mở rộng classpath/JAR tương ứng.
3. Với một binary name cụ thể, khi loader đã định nghĩa thành công class, các lời gọi `loadClass` tiếp theo trên cùng loader thường **tái sử dụng định nghĩa đã nạp**, không tự đổi sang bản ở URL đứng sau.
4. Nếu cần hai bản class cùng tên tồn tại dưới hai danh tính runtime độc lập, chúng phải được định nghĩa bởi **hai defining loaders khác nhau**. Trong cùng một defining loader không thể tùy ý định nghĩa lặp lại binary name như hai phiên bản.

Nói ngắn gọn: **thứ tự URL chỉ có ý nghĩa đối với những lớp/resource mà parent chưa thỏa mãn và loader thực sự phải tìm tại nguồn cục bộ**. Không được chỉ nhìn thứ tự JAR mà bỏ qua parent delegation.

## 2. URLClassLoader nhận những URL nào?

`URLClassLoader` là một `ClassLoader` có thể tìm class và resource từ các URL tới thư mục hoặc JAR hỗ trợ, thường dùng để xây dựng môi trường plugin, công cụ, hoặc bộ nạp thư viện động. Cách khởi tạo phổ biến:

```java
URL[] paths = {
    Path.of("plugins/api.jar").toUri().toURL(),
    Path.of("plugins/implementation.jar").toUri().toURL()
};

try (URLClassLoader loader = new URLClassLoader(paths, parentLoader)) {
    Class<?> implementation = loader.loadClass(
            "com.example.plugin.Implementation");
}
```

Đây là **snippet**, giả định hai JAR hợp lệ, class và `parentLoader` tồn tại, đồng thời import các API cần thiết. Một URL tới **thư mục** phải được thiết lập như URL thư mục hợp lệ (thường có dấu `/` cuối), ví dụ từ `Path.toUri().toURL()` của thư mục tồn tại.

Các điểm cần phân biệt:

- URL chỉ tới **JAR**: JAR chứa các entry như `com/example/plugin/Implementation.class`.
- URL chỉ tới **thư mục gốc của package tree**: thư mục chứa đường `com/example/plugin/Implementation.class`, không phải thư mục `.../com/example/plugin/`.
- **Thứ tự URL**: khi loader phải tìm cục bộ, những entry được tìm trước có cơ hội cung cấp class/resource trước.
- **Parent loader**: parent có thể cung cấp class trước toàn bộ đường tìm cục bộ; điều này độc lập với thứ tự URL trong child.
- `loader.getURLs()` trả các URL đã đăng ký trong danh sách tìm của loader theo thứ tự; đó **không nhất thiết** là bản liệt kê đầy đủ tất cả nguồn gián tiếp do manifest/JAR hoặc cấu hình launcher đưa vào quá trình tìm kiếm.

Một URL chỉ được liệt kê **không chứng minh** file tồn tại, có quyền đọc, đúng manifest, đúng class file version hay thực sự được chọn để định nghĩa class.

## 3. Parent-first trước, URL order sau

Giả sử có:

```text
Application Loader (parent)
  └── lib.Json  [version 1.0]

Plugin URLClassLoader (child)
  ├── URL[0] = plugin/lib-json-2.0.jar
  └── URL[1] = plugin/plugin.jar
```

Nếu code gọi:

```java
Class<?> json = pluginLoader.loadClass("lib.Json");
```

và parent đã có định nghĩa `lib.Json`, kết quả thường là **class do parent định nghĩa**, mặc dù URL đầu tiên của child chứa phiên bản 2.0.

Điều này xảy ra vì thuật toán mặc định:

```text
child.loadClass("lib.Json")
    |
    +-- findLoadedClass("lib.Json") -> đã ghi nhận? trả Class
    |
    +-- parent.loadClass("lib.Json") -> tìm thấy? trả Class parent
    |
    +-- child.findClass("lib.Json")  -> chỉ khi parent không tìm ra
              |
              +-- tìm theo các nguồn URL của child
```

Sơ đồ là logic tổng quan; phương thức thực tế còn liên quan khóa nạp lớp, kiểm tra hợp lệ, linking/resolution và trạng thái loader.

**Vì thế:** chuyển JAR phiên bản 2.0 từ URL[1] lên URL[0] **không giúp gì** nếu parent-first đã chọn bản 1.0 của parent. Trước khi thay đổi thứ tự URL, cần xác định **defining loader** của class đang được nạp.

Một số plugin framework thiết kế **child-first chọn lọc** cho package riêng, nhưng đó là chính sách tùy chỉnh. Không nên mặc nhiên giả định `URLClassLoader` dùng child-first.

## 4. Nếu hai URL của cùng loader chứa cùng một class

Xét loader con mà parent không có class `sample.Duplicate`:

```text
URL[0] -> A.jar
           └── sample/Duplicate.class  (origin() trả "A")
URL[1] -> B.jar
           └── sample/Duplicate.class  (origin() trả "B")
```

Khi `URLClassLoader` tìm cục bộ, nó gặp bản trong A trước và định nghĩa `sample.Duplicate` từ A (với giả định không có redirect đặc biệt hoặc nguồn gián tiếp làm thay đổi đường tìm). Class đã định nghĩa không tự được thay bằng bản trong B chỉ vì lần gọi sau “muốn phiên bản B”.

Nếu tạo **một URLClassLoader khác** với URL đảo lại:

```text
URL[0] -> B.jar
URL[1] -> A.jar
```

loader mới có thể định nghĩa `sample.Duplicate` từ B. Hai lớp trả về:

- Cùng `Class.getName()`: `"sample.Duplicate"`.
- Có thể có bytecode/logic khác nhau.
- **Không bằng nhau** dưới phép so sánh `Class<?> == Class<?>` vì defining loader khác nhau.
- Không thể coi các instance là cùng kiểu chỉ nhờ tên nhị phân giống nhau.

Dù dùng cùng một file `.class` ở cả hai nguồn, danh tính kiểu vẫn phụ thuộc **(binary name, defining loader)**.

### Không có quy tắc “JAR mới hơn thắng”

`URLClassLoader` không tự so sánh Maven version, timestamp, tên file JAR hay số phiên bản trong `pom.properties` để chọn bản “tốt nhất”. Nếu nhiều class có cùng tên nằm trên đường tìm của loader, **thứ tự và delegation** là những điều cần kiểm tra, không phải “bản cuối sẽ ghi đè”.

Nếu hai JAR cùng tồn tại nhưng chứa những package/class khác nhau, loader có thể nạp lớp từ cả hai. Điều gây vấn đề là **trùng binary name**, **phụ thuộc không tương thích**, hoặc ràng buộc package/module, chứ không phải mọi trường hợp có nhiều JAR.

## 5. Thực nghiệm Java 17+: đảo URL đổi lớp được chọn

Ví dụ dưới đây tạo hai thư mục riêng thay cho hai JAR. Với `URLClassLoader`, cả JAR và thư mục class đều là URL search roots phù hợp; dùng thư mục giúp bài thực hành hoàn toàn tự chứa, không phải chuẩn bị JAR thủ công.

Chương trình:

1. Tạo hai file nguồn `sample.Duplicate` có **cùng binary name** nhưng trả về giá trị khác nhau.
2. Biên dịch từng nguồn vào thư mục A hoặc B bằng `JavaCompiler`.
3. Tạo hai `URLClassLoader` độc lập, một có URL[A,B], một có URL[B,A].
4. Kiểm tra class trả về, defining loader và tài nguyên cùng tên.
5. Đóng loader, dọn file tạm sau khi hoàn tất.

Lưu **toàn bộ** mã sau thành `UrlOrderDemo.java`:

```java
import java.io.IOException;
import java.io.InputStream;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Enumeration;
import java.util.List;
import javax.tools.JavaCompiler;
import javax.tools.ToolProvider;

public class UrlOrderDemo {
    private static final String CLASS_NAME = "sample.Duplicate";
    private static final String MARKER =
            "lesson-url-order-2026.marker";

    private static String read(URL url) throws IOException {
        try (InputStream input = url.openStream()) {
            return new String(input.readAllBytes(),
                    StandardCharsets.UTF_8);
        }
    }

    private static void compile(JavaCompiler compiler,
                                Path source, Path output) {
        int exit = compiler.run(null, null, null,
                "--release", "17",
                "-d", output.toString(), source.toString());
        if (exit != 0) {
            throw new IllegalStateException("Compilation failed");
        }
    }

    public static void main(String[] args) throws Exception {
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException("Use a full JDK");
        }

        Path root = Files.createTempDirectory("url-order-demo-");
        Path a = root.resolve("a");
        Path b = root.resolve("b");
        Path sourceA = a.resolve("sample/Duplicate.java");
        Path sourceB = b.resolve("sample/Duplicate.java");
        Path classA = a.resolve("sample/Duplicate.class");
        Path classB = b.resolve("sample/Duplicate.class");
        Path markerA = a.resolve(MARKER);
        Path markerB = b.resolve(MARKER);

        try {
            Files.createDirectories(sourceA.getParent());
            Files.createDirectories(sourceB.getParent());

            Files.writeString(sourceA,
                    "package sample; public class Duplicate { "
                    + "public static String origin() { return \"A\"; } }");
            Files.writeString(sourceB,
                    "package sample; public class Duplicate { "
                    + "public static String origin() { return \"B\"; } }");
            Files.writeString(markerA, "A");
            Files.writeString(markerB, "B");

            compile(compiler, sourceA, a);
            compile(compiler, sourceB, b);

            URL urlA = a.toUri().toURL();
            URL urlB = b.toUri().toURL();
            ClassLoader parent = ClassLoader.getPlatformClassLoader();

            try (URLClassLoader first = new URLClassLoader(
                        new URL[] {urlA, urlB}, parent);
                 URLClassLoader reverse = new URLClassLoader(
                        new URL[] {urlB, urlA}, parent)) {

                Class<?> ca = first.loadClass(CLASS_NAME);
                Class<?> cb = reverse.loadClass(CLASS_NAME);

                System.out.println("firstClass="
                        + ca.getMethod("origin").invoke(null));
                System.out.println("reverseClass="
                        + cb.getMethod("origin").invoke(null));
                System.out.println("sameBinaryName="
                        + ca.getName().equals(cb.getName()));
                System.out.println("sameClassObject=" + (ca == cb));
                System.out.println("firstDefiningIsFirst="
                        + (ca.getClassLoader() == first));
                System.out.println("reverseDefiningIsReverse="
                        + (cb.getClassLoader() == reverse));

                System.out.println("firstResource="
                        + read(first.getResource(MARKER)));
                Enumeration<URL> urls = first.getResources(MARKER);
                List<String> values = new ArrayList<>();
                while (urls.hasMoreElements()) {
                    values.add(read(urls.nextElement()));
                }
                System.out.println("firstResources=" + values);
                System.out.println("reverseResource="
                        + read(reverse.getResource(MARKER)));
                System.out.println("stringDefinedByBootstrap="
                        + (first.loadClass("java.lang.String")
                                .getClassLoader() == null));
            }
        } finally {
            Files.deleteIfExists(sourceA);
            Files.deleteIfExists(sourceB);
            Files.deleteIfExists(classA);
            Files.deleteIfExists(classB);
            Files.deleteIfExists(markerA);
            Files.deleteIfExists(markerB);
            Files.deleteIfExists(a.resolve("sample"));
            Files.deleteIfExists(b.resolve("sample"));
            Files.deleteIfExists(a);
            Files.deleteIfExists(b);
            Files.deleteIfExists(root);
        }
    }
}
```

Biên dịch và chạy (JDK 17 trở lên):

```bash
javac UrlOrderDemo.java
java UrlOrderDemo
```

**Stdout trong môi trường JDK chuẩn** khi không có nguồn bên ngoài trùng tên `sample.Duplicate` hoặc marker của bài thực nghiệm:

```text
firstClass=A
reverseClass=B
sameBinaryName=true
sameClassObject=false
firstDefiningIsFirst=true
reverseDefiningIsReverse=true
firstResource=A
firstResources=[A, B]
reverseResource=B
stringDefinedByBootstrap=true
```

### Phân tích kết quả

- **`firstClass=A`**: loader thứ nhất có thứ tự URL[A,B], nên class `sample.Duplicate` từ A thắng trong đường tìm local.
- **`reverseClass=B`**: loader thứ hai có thứ tự URL[B,A], nên class từ B thắng.
- **`sameBinaryName=true`**, **`sameClassObject=false`**: hai class có cùng tên nhưng được hai defining loader khác nhau định nghĩa, nên là **hai runtime types**.
- **Hai dòng defining=true**: trong ví dụ, cả hai loader đều tự định nghĩa class; parent platform không có `sample.Duplicate`.
- **`firstResource=A`**: `getResource` tìm resource đầu tiên theo delegation + thứ tự URL local.
- **`firstResources=[A, B]`**: `getResources` có thể trả **cả hai URL** của resource trùng tên theo thứ tự tìm kiếm. Chọn một class định nghĩa duy nhất **không đồng nghĩa** bỏ hết những resource trùng tên.
- **`reverseResource=B`**: đảo thứ tự URL cũng đổi resource đầu tiên khi parent không có bản resource ấy.
- **`stringDefinedByBootstrap=true`**: dù gọi `first.loadClass("java.lang.String")`, class nền tảng do bootstrap loader định nghĩa, minh họa parent/bootstrap delegation ưu tiên lớp JDK.

**Điều kiện thực nghiệm:** chương trình yêu cầu JDK có module compiler `jdk.compiler` (không chỉ một runtime image tối giản). Hai root tạm được tạo và đóng URLClassLoader trước khi dọn dẹp. Nếu môi trường có hạn chế tạo file hoặc đã chèn một class/resource trùng tên qua loader cha, kết quả cần được phân tích lại theo đường tìm thực tế.

### Vì sao ví dụ dùng hai ClassLoader?

Nếu tạo **một** `URLClassLoader` rồi gọi `loadClass("sample.Duplicate")` hai lần, cùng loader thường trả lại **cùng đối tượng Class** nhờ cơ chế lớp đã được nạp. Thay đổi thứ tự mảng URL bên ngoài sau khi tạo loader, hoặc thêm một JAR khác chứa cùng tên bằng `addURL`, không thay thế class đã được định nghĩa.

Muốn quan sát cả hai định nghĩa độc lập, cần hai loader riêng với URL order tương ứng. Tuy nhiên, hai lớp đó không mặc nhiên có thể ép kiểu qua lại trong ứng dụng: chúng khác type identity.

## 6. Các API và thứ tự URL: class khác resource

Một lớp có thể được định nghĩa **chỉ một lần** cho mỗi binary name trong cùng loader, nhưng **resource** trùng tên có thể được liệt kê nhiều lần.

| API | Hành vi quan trọng |
| --- | --- |
| `loadClass(name)` | Theo mặc định kiểm tra class đã nạp, hỏi parent, rồi mới tìm trong các URL local; trả một `Class<?>` |
| `findClass(name)` của `URLClassLoader` | Tìm/định nghĩa class từ các URL do loader hỗ trợ nếu delegation đến bước local |
| `findLoadedClass(name)` | Kiểm tra class JVM ghi nhận đã nạp đối với loader đó; tránh cần định nghĩa lại |
| `getResource(name)` | Trả **một URL**; parent-first theo mặc định, rồi nguồn local |
| `getResources(name)` | Trả các URL từ parent và local, có thể chứa nhiều resource cùng tên |
| `findResource(name)` / `findResources(name)` | Điểm tìm kiếm local; `URLClassLoader` có triển khai dựa trên URL |
| `getURLs()` | Xem các URL đã được đăng ký cho loader, hỗ trợ điều tra thứ tự search roots |
| `close()` | Đóng URLClassLoader và giải phóng tài nguyên JAR/URL do loader quản lý; không “gỡ” class đã được định nghĩa khỏi JVM ngay |

**Không dùng `getResources` để kết luận rằng JVM đã nạp nhiều bản class cùng tên.** Tìm một resource tên `sample/Duplicate.class` ở hai JAR có thể trả hai URL, trong khi JVM đã chọn một định nghĩa class cụ thể cho loader.

Ngược lại, thành công khi gọi `loadClass` không bảo đảm mọi resource trong cùng JAR đều có thể tìm bằng API bạn đang dùng: resource name, module encapsulation, nguồn được chọn và policy của loader vẫn quan trọng.

## 7. Duplicate JAR, “JAR hell” và binary compatibility

Sự cố không chỉ nằm ở việc lớp nào thắng. Giả sử ứng dụng được biên dịch với thư viện phiên bản A có method:

```java
package lib;
public class Converter {
    public static String convert(String s) {
        return "A:" + s;
    }
}
```

Nhưng trong runtime, do URL order hoặc parent-first, JVM lại định nghĩa `lib.Converter` từ phiên bản B vốn **không còn** method `convert(String)`:

```java
package lib;
public class Converter {
    public static String render(String s) {
        return "B:" + s;
    }
}
```

Hai đoạn là **hai phiên bản thay thế nhau**, không biên dịch đồng thời với cùng tên vào một output.

Bytecode ứng dụng đã compile có thể vẫn chứa lời gọi `invokestatic lib/Converter.convert:(Ljava/lang/String;)Ljava/lang/String;`. Khi runtime phân giải lời gọi ấy với class phiên bản B, ứng dụng có thể gặp `NoSuchMethodError`.

Các dạng mismatch điển hình:

| Triệu chứng | Nguyên nhân khả dĩ |
| --- | --- |
| `NoSuchMethodError` | Runtime chọn class không có method signature mà code được compile với |
| `NoSuchFieldError` | Runtime chọn class không có field mà bytecode tham chiếu |
| `IncompatibleClassChangeError` | Runtime/compile-time không tương thích về kiểu class/interface hoặc static/instance |
| `ClassCastException` giữa hai class cùng tên | Hai defining loaders tạo hai runtime types độc lập |
| `LinkageError` kiểu loader constraint violation | Phạm vi loader không nhất quán đối với các type qua chữ ký phương thức |
| `NoClassDefFoundError` | Có thể thiếu phụ thuộc gián tiếp, lỗi loading hoặc trạng thái initialization lỗi trước đó |
| Lỗi package sealing hoặc signer | Các class trong cùng package được định nghĩa từ nguồn không tương thích với yêu cầu sealing/chứng chỉ |

Phải đọc toàn bộ stack trace và `Caused by`. Không thể xem mọi lỗi `LinkageError` là “chỉ cần đảo hai JAR”.

### Package sealing và certificates

JAR có thể khai báo **sealing** trong manifest. Khi một package được sealed về một code source, việc cố định nghĩa class cùng package từ một URL/JAR khác có thể vi phạm điều kiện sealing; tương tự, các class cùng package trong một loader có thể phải đáp ứng tính nhất quán về certificate/signing.

Đây là lý do “lớp A từ JAR1 và lớp B cùng package từ JAR2” không phải lúc nào cũng hợp lệ. Nếu có `SecurityException: sealing violation` hoặc thông báo certificate mismatch, điều tra manifest, nguồn JAR và cách bố trí package, **không** tắt kiểm tra hoặc đổi JAR bừa bãi.

### JPMS (Java 9+) khác với classpath truyền thống

Các ví dụ parent-first + URL order chủ yếu xét class trên **classpath/unnamed module** qua `URLClassLoader`. Với named modules, module resolution và phạm vi package/readability bổ sung quy tắc; đặt nhiều JAR trên module path không có nghĩa URLClassLoader sẽ quyết định mọi xung đột bằng thứ tự mảng URL.

Đặc biệt, split package, `requires`, `exports` và việc phát hiện duplicate modules có các quy tắc khác. Phải phân biệt **module path resolution** với **classpath search order** trước khi chẩn đoán.

## 8. Manifest Class-Path, thư viện phụ thuộc và đường tìm gián tiếp

Một JAR có thể khai báo thuộc tính **`Class-Path`** trong `META-INF/MANIFEST.MF` để tham chiếu các JAR/thư mục phụ thuộc:

```text
Manifest-Version: 1.0
Class-Path: lib/helper.jar lib/support.jar
```

Các mục ở đây được giải nghĩa theo quy tắc manifest Class-Path, thường tương đối với vị trí JAR chứa manifest. Khi cơ chế loader hỗ trợ xử lý thuộc tính này, những nguồn phụ thuộc **gián tiếp** có thể tham gia đường tìm.

Vì thế:

- Danh sách URL truyền trực tiếp vào constructor không nhất thiết mô tả **đủ mọi vị trí** loader có thể tìm class.
- Sự tham gia của manifest Class-Path ảnh hưởng cách tính thứ tự tìm kiếm khi loader thực sự đi đến JAR khai báo thuộc tính.
- Không nên tự tuyên bố “URL[1] chắc chắn luôn được kiểm tra trước bất kỳ phụ thuộc nào nêu trong manifest của URL[0]”. Quy tắc mở rộng đường tìm và điều kiện hợp lệ của manifest cần được xét theo loader và đặc tả JAR.
- Đừng giả định `getURLs()` luôn liệt kê toàn bộ URL gián tiếp được tìm qua manifest theo cùng cách với constructor URLs.

Muốn kết quả triển khai dự đoán được, nên đóng gói/khai báo dependency nhất quán bằng build tool thay vì dựa vào tình cờ thứ tự nhiều bản JAR.

## 9. Tại sao thứ tự JAR trên -cp và thứ tự URL trong URLClassLoader không luôn tương đương?

Ứng dụng có thể được chạy bằng:

```bash
java -cp "lib/*:app/classes" com.example.Main
```

Đây là ví dụ cú pháp **Linux/macOS**; Windows dùng dấu `;`. Wildcard `lib/*` do **Java launcher** mở rộng thành tập JAR trong thư mục, và thứ tự liệt kê JAR của wildcard **không được bảo đảm theo tên file/phiên bản một cách ổn định** để ứng dụng phụ thuộc vào.

Một danh sách URL tạo rõ ràng bằng `new URL[] {urlA, urlB}` trong `URLClassLoader` cung cấp thứ tự do code quy định; tuy nhiên parent delegation và các nguồn bổ sung như manifest vẫn có thể ảnh hưởng.

Các tình huống cần phân biệt:

| Môi trường | Điểm cần kiểm tra |
| --- | --- |
| `java -cp "a.jar:b.jar"` | Launcher classpath và thứ tự các entry đã được đưa vào application loader |
| `java -cp "lib/*"` | Các JAR thực sự được mở rộng từ wildcard; đừng dựa vào alphabetic order |
| `new URLClassLoader({a,b}, parent)` | Thứ tự URL trực tiếp và chính sách parent-first |
| `java -jar app.jar` | Quy tắc entry point/manifest, không coi `-cp` cạnh `-jar` là user classpath thông thường |
| Maven/Gradle | Dependency graph, conflict resolution, runtimeClasspath, artifact được đóng gói |
| Plugin/container | Loader tree, delegation rule của framework và class riêng/shared packages |
| JPMS module path | Module resolution/readability/exports, không chỉ URL array |

Một build chạy ổn trên máy này nhưng hỏng máy kia vì có nhiều bản JAR trùng class và phụ thuộc vào thứ tự wildcard là dấu hiệu **đóng gói không xác định**, không phải JVM ngẫu nhiên chọn class.

## 10. Nếu phải ưu tiên bản thư viện của plugin

Một chiến lược plugin thường muốn:

- **API/SPI do host cung cấp** (`com.company.api.*`) phải được **chia sẻ**: để parent định nghĩa.
- **Implementation và thư viện riêng** (`plugin.internal.*` hoặc package được phép cô lập) có thể để plugin loader tự định nghĩa.
- Các package nền tảng của JDK không bị custom loader tìm cách giả mạo.
- Các type xuyên qua method parameters/return types phải nhất quán về defining loader để tránh `ClassCastException`/loader constraint violations.

Với `URLClassLoader` mặc định, nếu parent đã có một thư viện, parent-first thường thắng. Nếu bắt buộc cần hai phiên bản thư viện cùng tồn tại, có thể xét:

1. **Tách class loader phù hợp:** mỗi plugin dùng một defining loader cho implementation/dependencies riêng, chung một loader host cho API.
2. **Delegation theo namespace:** plugin framework định nghĩa rõ package nào parent-first và package nào local-first, kèm chính sách tài nguyên.
3. **Shading/relocation trong build:** thay package name của một phiên bản thư viện (nếu bản quyền và cơ chế thư viện cho phép) để tránh cùng binary name trong cùng ranh giới loader.
4. **Dọn dependency tree:** ưu tiên một phiên bản thống nhất khi không thật sự cần cô lập.

Không nên tự override toàn bộ `loadClass` thành child-first cho **mọi package** để sửa một lỗi. Việc này có thể tạo bản riêng của interface host, phá type identity, hoặc chạm ràng buộc an toàn/định nghĩa lớp.

## 11. Chẩn đoán: class nào thực sự được JVM nạp?

Nếu có thể lấy đối tượng `Class<?>`, ba thông tin quan trọng là **binary name, defining loader và nguồn code**.

Đặt phương thức hỗ trợ sau trong class ứng dụng:

```java
static void describe(Class<?> type) {
    System.out.println("name=" + type.getName());
    System.out.println("definingLoader=" + type.getClassLoader());

    java.security.ProtectionDomain pd = type.getProtectionDomain();
    java.security.CodeSource cs =
            pd == null ? null : pd.getCodeSource();
    System.out.println("codeSource=" +
            (cs == null ? "<unknown>" : cs.getLocation()));
}
```

Đây là **snippet hỗ trợ**, không có `main` riêng. Cần import API hoặc dùng tên đầy đủ như trên. `getClassLoader() == null` biểu thị bootstrap loader; `CodeSource` có thể `null` và không được coi đó là bằng chứng loader sai.

### Checklist điều tra khi có trùng class/JAR

1. **Xác định tên lớp bị ảnh hưởng** từ exception/stack trace, ví dụ `lib.Json`.
2. **Ghi loader nhận yêu cầu và defining loader** của class thật sự trả về. Parent-first có thể khiến hai đối tượng loader khác nhau.
3. **In `getURLs()` của URLClassLoader liên quan**, trong trường hợp có quyền truy cập đối tượng loader. So sánh thứ tự constructor URLs, URL được thêm sau và đường nguồn thực tế.
4. **Kiểm tra các bản trùng**: `jar tf plugin-a.jar` và `jar tf plugin-b.jar` để xem cùng chứa `lib/Json.class` không; đối chiếu method signatures bằng `javap`.
5. **Xác minh runtime artifact** chứ không chỉ compile dependency. Binary đã build có thể dùng API phiên bản khác class được nạp lúc chạy.
6. **Đọc manifest và JAR metadata**: `Class-Path`, sealing, multi-release JAR, signer, package version; không chỉ nhìn tên JAR.
7. **Đối chiếu resource lookup**: dùng `getResources` nếu cần tìm mọi bản `lib/config.properties`; phân biệt nhiều URL resource với một runtime Class.
8. **Kiểm tra class loader cũ** sau hot reload/deploy: class/instance đã định nghĩa không tự bị thay bằng việc sửa URL hoặc JAR trên đĩa.
9. **Đọc đúng loại lỗi**: `NoSuchMethodError` thường là mismatch ABI; `ClassCastException` có thể do hai defining loaders; sealing violation là vấn đề package/JAR policy.
10. **Nếu chạy trên module path**, xác định module graph và readability trước khi dựa vào giả định về classpath URL order.

### Dùng công cụ JDK hỗ trợ

```bash
jar tf plugins/a.jar
jar tf plugins/b.jar
javap -classpath plugins/a.jar -public lib.Json
javap -classpath plugins/b.jar -public lib.Json
```

Đây là các ví dụ lệnh; tên file `plugins/a.jar`, `plugins/b.jar` và `lib.Json` cần thay bằng artifact/lớp thực tế. Với JVM có unified logging:

```bash
java -Xlog:class+load=info -cp "app/classes:lib/*" com.example.Main
```

Lệnh dùng separator Linux/macOS; trên Windows thay `:` thành `;`. Log có thể cho biết nguồn bytecode, nhưng vẫn cần phân tích **defining loader** và cách classpath được mở rộng. File/JAR “được log” không tự nói vì sao một bản bị ưu tiên hơn bản kia.

## 12. Resource trùng tên và ServiceLoader

Không phải chỉ file `.class` mới trùng: nhiều JAR thường cùng chứa `META-INF/services/com.example.spi.Plugin`. Đặc điểm ở đây khác class duplication:

- `getResource(name)` thường lấy URL đầu tiên theo delegation và thứ tự nguồn cục bộ.
- `getResources(name)` có thể liệt kê **nhiều URL** cùng tên từ parent lẫn local, giúp các thư viện khám phá nhiều descriptor.
- `ServiceLoader` tiêu thụ thông tin provider theo giao thức riêng, có thể dựa trên loader/context loader được chỉ định; không nên tự coi nó chỉ đọc JAR URL[0].
- Provider phải tương thích với **chính interface SPI runtime** mà host/consumer dùng. Nếu host và plugin tự định nghĩa hai bản `spi.Plugin` khác defining loader, provider có thể không hợp lệ dù file descriptor đúng tên.

Nếu hai JAR chứa resource cấu hình `app.properties`, việc đổi thứ tự URL có thể đổi bản mà code dùng `getResource` nhận đầu tiên. Nhưng nếu code dùng `getResources` rồi merge tất cả nội dung, “file thắng” lại do **logic merge của ứng dụng**, không chỉ URLClassLoader.

Từ Java 9, named modules bổ sung các quy tắc resource visibility. Không dùng kết quả `getResources` trên classpath để suy luận trực tiếp cách mọi resource trong named modules được mở.

## 13. Những hiểu lầm cần tránh

| Hiểu lầm | Sự thật |
| --- | --- |
| “URL[0] luôn thắng mọi nguồn khác.” | Không nếu parent-first đã tìm được class/resource trước hoặc có quy tắc nguồn gián tiếp. |
| “JAR có version lớn nhất sẽ được chọn.” | URLClassLoader không tự chọn Maven semantic version mới nhất. |
| “Đổi thứ tự URL sau khi đã load class sẽ thay definition.” | Một runtime class đã định nghĩa không được tự thay bằng nguồn khác trong cùng loader. |
| “Có hai file Duplicate.class thì cùng loader chứa hai runtime classes.” | Cùng binary name chỉ được định nghĩa một lần trong một defining loader; phiên bản nào thắng phụ thuộc đường tìm. |
| “Hai loader khác nhau định nghĩa cùng binary name thì vẫn cast được.” | Không nhất thiết; chúng là hai runtime types độc lập. |
| “getResources trả hai URL .class nghĩa là JVM đã định nghĩa hai class.” | Resource enumeration và định nghĩa runtime Class là hai cơ chế khác nhau. |
| “Mọi JAR chứa class cùng package đều nạp chung được.” | Sealing/certificates hoặc module boundaries có thể cấm trộn nguồn. |
| “lib/* luôn sắp xếp JAR theo tên.” | Wildcard expansion order không nên được coi là thứ tự version ổn định. |
| “Chỉ xem getURLs là biết mọi phụ thuộc được mở.” | Manifest Class-Path và parent/framework có thể bổ sung nguồn không thể suy ra chỉ từ mảng URL. |
| “Đóng URLClassLoader sẽ unload class ngay.” | Close giải phóng tài nguyên do loader quản lý; unloading phụ thuộc reachability. |
| “Chỉ cần child-first cho mọi package là giải quyết được.” | Có thể gây nhân đôi API/SPI và lỗi type identity. |

## 14. Câu hỏi tự kiểm tra

**Câu 1.** Child URLClassLoader có URL[A.jar,B.jar], cả hai có `lib.X`; parent cũng có `lib.X`. Class nào được chọn theo parent-first mặc định?

**Đáp án:** Class do parent (hoặc ancestor phù hợp) cung cấp nếu parent tìm được. Thứ tự A/B của child chưa có cơ hội được xét.

**Câu 2.** Parent không có `lib.X`. A.jar và B.jar đều có class này. Nếu thứ tự URL là A rồi B, điều gì thường xảy ra?

**Đáp án:** Loader tìm cục bộ từ URL A trước và định nghĩa class từ A, theo điều kiện đường tìm thông thường. Không tự so sánh phiên bản JAR.

**Câu 3.** Đảo URL thành B rồi A trong một **loader mới**; tên lớp giữ nguyên. Hai `Class<?>` từ hai loader có bằng nhau không?

**Đáp án:** Không nếu mỗi loader tự định nghĩa bản tương ứng. Defining loader khác nhau nên runtime type identity khác.

**Câu 4.** Đã nạp `lib.X` từ A trong loader L; sau đó thêm B qua `addURL` (nếu có subclass cho phép). Lần gọi kế tiếp `L.loadClass("lib.X")` có đổi sang B không?

**Đáp án:** Không. Loader tái sử dụng class đã được ghi nhận/định nghĩa; không thay definition cùng binary name.

**Câu 5.** `getResources("config.properties")` trả hai URL. Điều đó có nghĩa có hai `Config` classes runtime không?

**Đáp án:** Không. Nó chỉ cho thấy hai nguồn resource cùng tên; class identity phải kiểm tra qua `Class<?>` và defining loader.

**Câu 6.** Thư viện đang chạy báo `NoSuchMethodError` dù class có mặt trên classpath. Vì sao URL order có thể liên quan?

**Đáp án:** Runtime có thể chọn bản class khác phiên bản compile-time, thiếu method descriptor mà bytecode đã gọi.

**Câu 7.** Dùng `java -cp "lib/*"` và kỳ vọng `a.jar` luôn thắng `z.jar`. Có ổn không?

**Đáp án:** Không nên dựa vào thứ tự expansion wildcard. Loại bỏ xung đột hoặc cấu hình classpath/dependency rõ ràng.

**Câu 8.** Hai JAR khác nhau chứa class khác nhau nhưng cùng một package sealed. Nguy cơ gì?

**Đáp án:** Sealing violation khi loader cố định nghĩa class của một package đã sealed từ nguồn không hợp lệ. Cần thiết kế package/JAR theo ràng buộc manifest.

## 15. Kết luận và tài liệu chính thức

Khi sử dụng `URLClassLoader`, cần phân biệt hai tầng ưu tiên: **parent delegation** trước, rồi mới đến **thứ tự các URL cục bộ** khi loader phải tự tìm class/resource. Trùng binary name trong các JAR không làm một loader định nghĩa hai class cùng tên; bản đã chọn sẽ được tái sử dụng. Resource có thể được liệt kê nhiều URL, còn muốn tồn tại hai runtime classes cùng tên phải dùng các **defining loaders khác nhau** và kiểm soát ranh giới kiểu.

Để tránh “JAR hell”, hãy chuẩn hóa dependency graph, kiểm tra defining loader/code source thực tế, tránh phụ thuộc vào wildcard ordering, và hiểu ràng buộc manifest, sealing cùng module path trước khi kết luận cần đổi URL order.

Nguồn tham khảo:

- Java SE 17 `URLClassLoader` API: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html
- Java SE 17 `ClassLoader` API: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html
- Java SE 17 `java` launcher (classpath, wildcard): https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html
- Java SE 17 `JarFile` API và multi-release JAR: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/jar/JarFile.html
- JAR File Specification (manifest Class-Path, sealing): https://docs.oracle.com/javase/8/docs/technotes/guides/jar/jar.html
- JVMS 17 §5.3, Creation of Classes and Interfaces: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.3
