# Java Reflection không có API tự liệt kê mọi lớp trong classpath

Một giới hạn quan trọng của **Java Core Reflection** là: **không có phương thức chuẩn như `Class.getAllClassesInClasspath()` để nhận danh sách mọi class mà ứng dụng có thể sử dụng**.

Reflection rất giỏi trả lời câu hỏi về **một kiểu đã biết**: kiểu tên gì, có những constructor, field, method, annotation nào, có thể tạo instance hay gọi method nào. Nhưng câu hỏi “toàn bộ class trong classpath hiện tại là gì?” thuộc về việc **khám phá các nguồn chứa class, cơ chế class loading, cấu trúc module và môi trường chạy**; Reflection không tự làm công việc đó.

Bài này tập trung vào **ranh giới của Core Reflection**, các khái niệm dễ bị lẫn, cách khám phá class trong phạm vi xác định và lựa chọn thiết kế phù hợp khi cần xây dựng plugin scanner, test runner, annotation scanner hoặc framework.

## 1. “Liệt kê mọi lớp” thực sự có thể mang nhiều ý nghĩa

Trước khi chọn API, cần xác định mục tiêu:

| Câu hỏi thực tế | Tập dữ liệu muốn tìm | Có thể giải quyết bằng gì? |
| --- | --- | --- |
| “Class `com.example.User` có thuộc tính nào?” | Metadata của **một class đã biết** | `User.class`, `Class.forName`, `Class.getDeclaredFields` |
| “Class `Service` khai báo các nested class nào?” | Class/interface thành viên được **khai báo bên trong một class** | `Service.class.getDeclaredClasses()` |
| “Trong thư mục `build/classes` có file `.class` nào?” | Những **entry vật lý** trong một cây thư mục xác định | `Files.walk` với `java.nio.file` |
| “JAR `plugins.jar` chứa những entry `.class` nào?” | Entry thuộc **một JAR cụ thể** | `JarFile`, `JarEntry` |
| “Những implementation nào đã đăng ký cho SPI?” | Provider theo cơ chế đăng ký dịch vụ | `ServiceLoader` |
| “Trong module `m` có tài nguyên nào?” | Resource của **module đã xác định** | `ModuleReader.list()` với quyền/môi trường tương ứng |
| “JVM đã nạp những class nào?” | Các class **đã được load** tại thời điểm quan sát | `Instrumentation.getAllLoadedClasses()` qua Java agent, không thuộc Core Reflection |
| “Mọi class có thể được nạp bởi tất cả class loader, cả trong tương lai?” | Tập class tiềm năng có thể thay đổi động | **Không có cách tổng quát, đầy đủ cho mọi môi trường Java** |

Hai tập dữ liệu sau đây khác nhau:

- **Class *có mặt* trong một nguồn**: ví dụ file `com/acme/Plugin.class` nằm trong JAR. Chưa chắc được loader hiện tại tìm thấy, chưa chắc link thành công hay được truy cập.
- **Class *đã được nạp***: JVM đã tạo runtime `Class<?>` tương ứng qua một class loader. Một class được đóng gói trong JAR nhưng chưa hề được dùng có thể **chưa** được nạp.

Không được suy luận rằng mọi class đã nạp đều có file `.class` nằm trên `java.class.path`, hoặc rằng mọi file `.class` trên disk đều là một runtime class hợp lệ, có thể gọi được.

## 2. Core Reflection biết cấu trúc của class đã có tên

Các API quen thuộc:

```java
Class<?> type = String.class;

System.out.println(type.getName());
System.out.println(type.getDeclaredMethods().length > 0);
```

Khi đã có `Class<?>`, ta có thể duyệt:

- `getDeclaredFields()`: field khai báo trực tiếp, kể cả non-public (tìm thấy chưa đồng nghĩa có quyền truy cập).
- `getDeclaredMethods()`: method được khai báo trực tiếp, không tự cộng mọi method thừa kế.
- `getDeclaredConstructors()`: constructor khai báo trực tiếp.
- `getDeclaredAnnotations()`: các annotation hiện diện trực tiếp mà Reflection có thể quan sát tại runtime.
- `getDeclaredClasses()`: **member classes/interfaces khai báo trực tiếp bên trong class này**.

`getDeclaredClasses()` thường bị hiểu sai. Nó **không** duyệt tất cả class trong cùng package, JAR hoặc classpath; nó chỉ mô tả class thành viên theo quan hệ khai báo trong class hiện tại. Local class hoặc anonymous class cũng không được “quét toàn bộ” từ lời gọi này.

Ví dụ:

```java
class Container {
    static class Nested {}
}

class Independent {}
```

`Container.class.getDeclaredClasses()` có thể trả `Container.Nested`; nó không tự trả `Independent` chỉ vì hai class ở cùng file nguồn, cùng package hay cùng thư mục biên dịch.

### Biết tên khác với khám phá tất cả tên

`Class.forName("com.acme.SomeType")` thử tìm class theo **tên đã có**. API này không cung cấp bộ duyệt tên class. Biến thể một tham số có thể kích hoạt khởi tạo class.

```java
// Minh họa cho trường hợp đã biết tên class và có class loader phù hợp.
ClassLoader loader = Thread.currentThread().getContextClassLoader();
Class<?> type = Class.forName("com.acme.SomeType", false, loader);
```

`false` nghĩa là không yêu cầu khởi tạo class trong lệnh này. Nó **không có nghĩa** không load/link, không phát sinh lỗi liên quan class loading, hay class được tìm thấy chắc chắn có thể truy cập từ caller. Nếu class không tồn tại trong phạm vi loader: `ClassNotFoundException`. Khi có vấn đề linkage có thể nhận `LinkageError`.

**Class name chính xác** dùng cú pháp binary name, ví dụ nested class có thể có tên `com.acme.Outer$Inner`; dấu `$` trong tên nhị phân không nhất thiết đồng nghĩa một class member được khai báo theo cách đơn giản.

## 3. Vì sao classpath không phải một danh mục class duy nhất?

### 3.1. Classpath có nhiều nguồn và không mang sẵn “danh sách class”

Ứng dụng Java có thể lấy bytecode từ:

- Cây thư mục chứa các file `.class` sau biên dịch.
- JAR truyền qua `-cp` / `--class-path`; wildcard classpath hoặc manifest `Class-Path` có thể mở rộng nguồn mà runtime dùng.
- Class loader của application server, framework, test runner hoặc hệ thống plugin.
- Nguồn dữ liệu tùy biến: bộ nhớ, network, file mã hóa, lớp được sinh động, v.v.
- **Module path** trong ứng dụng JPMS, vốn có quy tắc riêng; không thể đơn giản đánh đồng với classpath.

`System.getProperty("java.class.path")` phản ánh một cấu hình classpath liên quan launcher/runtime, nhưng **không đại diện đầy đủ mọi nguồn của mọi class loader**. Không nên chỉ tách chuỗi này rồi kết luận đã tìm hết class trong một JVM.

### 3.2. Nhiều class loader có những “tầm nhìn” khác nhau

Hai class loader có thể định nghĩa class mang **cùng binary name** mà vẫn tạo ra **hai runtime type khác nhau**. Identity của một class gắn với cả tên nhị phân và defining class loader.

Ví dụ, plugin loader A có thể tìm thấy `com.plugins.PluginA` trong khi system loader không tìm thấy. Cùng tên đó cũng có thể tồn tại ở plugin loader B nhưng được xem là class khác.

Nhiều class loader không công bố tất cả URL/path nguồn nạp class, và một số nguồn thậm chí không phải file hoặc JAR thông thường. Không có hợp đồng trong `java.lang.ClassLoader` yêu cầu mọi subclass phải cung cấp “liệt kê tất cả class có thể nạp”.

### 3.3. Class có thể chưa được nạp hoặc không có file trực tiếp

Việc JVM nạp class thường diễn ra theo nhu cầu. Chương trình có thể chứa hàng ngàn file `.class` nhưng chỉ thực sự load một phần trong phiên chạy. Ngược lại, runtime có thể tạo class trong bộ nhớ hoặc dùng **hidden class** cho mục đích triển khai; những class đó không nhất thiết có tên có thể tìm lại qua `Class.forName`.

Còn có khác biệt về classpath, module path, các runtime image `jrt:/` và cách đóng gói của framework. Một thuật toán “duyệt tất cả file trong một thư mục” vì vậy không thể mặc định đúng cho mọi môi trường.

## 4. Các API dễ bị tưởng nhầm có chức năng quét classpath

| API | Thực tế trả về | Không bảo đảm |
| --- | --- | --- |
| `Class.forName(name)` | Class tương ứng **một tên đã cung cấp**, nếu tìm/nạp được | Tự tìm mọi tên class |
| `Class.getDeclaredClasses()` | Member classes/interfaces khai báo trực tiếp trong một class | Tất cả class cùng package/JAR/classpath |
| `Package.getPackages()` | Thông tin những package đã được định nghĩa theo cơ chế package runtime | Tên mọi class trong mỗi package |
| `ClassLoader.getDefinedPackages()` | Những package do loader đó đã định nghĩa | Mọi class trong nguồn loader có thể dùng |
| `ClassLoader.getResources(name)` | URL của những **resource có đúng tên được yêu cầu** | Glob `**/*.class` hoặc directory listing phổ quát |
| `ClassLoader.resources(name)` | Stream của các resource có một tên | Tập toàn bộ resource/class |
| `ModuleLayer.boot().modules()` | Các module đã có trong boot layer | Class của tất cả module hay tất cả layer |
| `Instrumentation.getAllLoadedClasses()` | Những class **đã load** tại thời điểm gọi, thông qua agent instrumentation | Tất cả class có thể load trong tương lai |

Đặc biệt, lời gọi sau **không** phải API quét package:

```java
var urls = Thread.currentThread()
        .getContextClassLoader()
        .getResources("com/acme/plugins");
```

Nó tìm resource mang **tên chính xác** `com/acme/plugins` (nếu có), không có nghĩa nó trả danh sách mọi file bên dưới. Trong JAR, “directory entry” có thể không tồn tại; URL có thể dùng nhiều giao thức khác nhau; module có các quy tắc encapsulation riêng đối với resource. Nếu một đoạn scanner dựa vào URL `file:` và `jar:` thì nó mới xử lý **hai loại nguồn được hỗ trợ**, chưa phải toàn bộ classpath.

## 5. Cách làm đúng khi cần một danh mục class trong phạm vi xác định

Trước hết hãy chọn **phạm vi hữu hạn, kiểm soát được**: ví dụ thư mục `out/` hoặc một tập JAR ứng dụng đã chỉ định. Tiếp theo:

1. **Liệt kê nguồn**: xác định chính xác thư mục/JAR/module/plugin location sẽ quét.
2. **Liệt kê entry**: duyệt file `.class` bằng `Files.walk` hoặc `JarFile` (hay API phù hợp riêng từng nguồn).
3. **Chuyển resource path thành ứng viên binary name**: `com/acme/Widget.class` → `com.acme.Widget`.
4. **Lọc và chống trùng**: loại `module-info`, `package-info` nếu cần, xử lý nested class, multi-release JAR và các tên trùng giữa nguồn.
5. **Xác minh khả năng load** với class loader đúng ngữ cảnh khi thật sự cần; thường dùng `Class.forName(name, false, loader)` để tránh yêu cầu khởi tạo ngay.
6. **Kiểm tra contract**: interface, annotation runtime, method/constructor, module accessibility và quyền ứng dụng trước khi instantiate/invoke.
7. **Giới hạn tài nguyên**: giới hạn path, số file, thời gian quét, kích thước JAR, số class ứng viên; ghi nhận lỗi từng nguồn thay vì nuốt exception.

**Đọc tên file** không thực thi class, nhưng **nạp class** có thể gây phát sinh việc đọc bytecode, giải quyết phụ thuộc, linkage error và hành vi tùy chỉnh của class loader. Không nên nạp và khởi tạo bừa bãi mọi tên tìm được chỉ để lọc annotation.

### Ví dụ A — Duyệt một thư mục class

Nếu có output của `javac -d out ...`:

```text
out/
└── com/
    └── demo/
        ├── Alpha.class
        ├── Beta.class
        └── Outer$Nested.class
```

`Files.walk(Path.of("out"))` có thể duyệt những file vật lý trong cây này. Chuyển path tương đối sang dấu chấm cho ra `com.demo.Alpha`, `com.demo.Beta` và `com.demo.Outer$Nested` — đó là **ứng viên theo file**, không phải mọi class loader đều load được từng ứng viên.

Nếu thư mục gốc bị chỉ sai, hoặc class không nằm trực tiếp trên nguồn mà loader sử dụng, tập tên có thể khác với thực tế runtime.

### Ví dụ B — Duyệt một JAR

`JarFile` có thể liệt kê `JarEntry` chứa `.class` trong **JAR cụ thể**. Đó là công cụ đọc nội dung archive, thuộc `java.util.jar`, không phải API liệt kê class của Core Reflection.

Một số chú ý khi quét JAR thực tế:

- `module-info.class` là mô tả module, `package-info.class` thường không phải implementation cần đăng ký.
- Multi-release JAR có thể chứa entry dưới `META-INF/versions/<version>/`. Không được biến nguyên path phiên bản thành binary name như class thông thường. Cần chọn phiên bản phù hợp runtime hoặc dùng công cụ hiểu multi-release.
- JAR trong JAR (*nested/fat JAR*) có thể yêu cầu cơ chế đọc và class loader riêng của framework; không thể coi mọi nested entry là class loadable trực tiếp.
- Cùng một binary name có thể có mặt trong nhiều JAR, nhưng loader thực tế có thể chỉ chọn một phiên bản theo thứ tự/thuật toán riêng.
- Class có trong JAR chưa bảo đảm phụ thuộc đầy đủ, đủ quyền JPMS hay khởi tạo an toàn.

## 6. Chương trình Java 17+: đối chiếu Reflection với việc liệt kê một nguồn

Ví dụ dưới đây làm **hai việc tách biệt**:

- Dùng `Class.forName` để truy cập một class đã biết tên, không khám phá tên.
- Quét **một root do người chạy truyền vào**: thư mục output hoặc một file `.jar`. Chương trình chỉ thu thập **tên ứng viên**, tuyệt đối không tự load mỗi class tìm được.

Để code độc lập và kết quả ổn định, ta tạo một class nested `ExamplePlugin` ngay trong cùng file. Chương trình cố ý chỉ hỗ trợ thư mục và JAR thường; không nhận là scanner tổng quát cho mọi class loader, module hoặc nested/multi-release JAR.

Tạo **`ClasspathInventoryDemo.java`**:

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.stream.Stream;
import java.util.jar.JarEntry;
import java.util.jar.JarFile;

public class ClasspathInventoryDemo {
    public static class ExamplePlugin {}

    private static String className(String relative) {
        if (!relative.endsWith(".class")) {
            throw new IllegalArgumentException("Không phải .class: " + relative);
        }
        return relative.substring(0, relative.length() - 6)
                .replace('/', '.').replace('\\', '.');
    }

    public static List<String> findClassNames(Path root) throws IOException {
        List<String> names = new ArrayList<>();
        if (Files.isDirectory(root)) {
            try (Stream<Path> files = Files.walk(root)) {
                files.filter(Files::isRegularFile)
                        .map(root::relativize)
                        .map(Path::toString)
                        .filter(name -> name.endsWith(".class"))
                        .map(ClasspathInventoryDemo::className)
                        .forEach(names::add);
            }
        } else if (Files.isRegularFile(root)
                && root.getFileName().toString().endsWith(".jar")) {
            try (JarFile jar = new JarFile(root.toFile())) {
                var entries = jar.entries();
                while (entries.hasMoreElements()) {
                    JarEntry entry = entries.nextElement();
                    String name = entry.getName();
                    if (!entry.isDirectory()
                            && name.endsWith(".class")
                            && !name.startsWith("META-INF/versions/")) {
                        names.add(className(name));
                    }
                }
            }
        } else {
            throw new IllegalArgumentException("Cần thư mục hoặc JAR: " + root);
        }
        Collections.sort(names);
        return List.copyOf(names);
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                    "Dùng: java ClasspathInventoryDemo <root>");
        }
        Class<?> known =
                Class.forName("ClasspathInventoryDemo$ExamplePlugin");
        System.out.println("Known: " + known.getName());

        List<String> names = findClassNames(Path.of(args[0]));
        System.out.println("Candidates: " + names.size());
        System.out.println("Contains plugin: "
                + names.contains("ClasspathInventoryDemo$ExamplePlugin"));
    }
}
```

**Biên dịch và chạy trên thư mục** với JDK 17 trở lên:

```bash
javac -encoding UTF-8 -d out ClasspathInventoryDemo.java
java -cp out ClasspathInventoryDemo out
```

**Kết quả:**

```text
Known: ClasspathInventoryDemo$ExamplePlugin
Candidates: 2
Contains plugin: true
```

Có hai file `.class` vì `javac` sinh một cho outer class `ClasspathInventoryDemo` và một cho nested class `ExamplePlugin`.

**Tạo JAR rồi thử cùng chương trình:**

```bash
jar --create --file demo.jar -C out .
java -cp out ClasspathInventoryDemo demo.jar
```

**Kết quả vẫn là:**

```text
Known: ClasspathInventoryDemo$ExamplePlugin
Candidates: 2
Contains plugin: true
```

Trong lệnh thứ hai, class được dùng để chạy chương trình vẫn được load từ `out`, còn `demo.jar` chỉ là **archive được chương trình đọc**. Chúng là hai hoạt động độc lập. Dùng `java -cp demo.jar ClasspathInventoryDemo demo.jar` cũng có thể chạy ví dụ này vì JAR chứa các class vừa biên dịch, nhưng code vẫn chỉ quét đúng một JAR được chỉ định.

**Đọc code cẩn thận:**

- `Class.forName("ClasspathInventoryDemo$ExamplePlugin")` thành công vì đã biết tên nhị phân và class có thể load; lời gọi này **không** phát hiện `ExamplePlugin` bằng cách liệt kê.
- `Files.walk(root)` chỉ duyệt cây thư mục chỉ định; luôn đóng `Stream<Path>` bằng try-with-resources.
- `JarFile.entries()` chỉ liệt kê entry trong một JAR chỉ định; luôn đóng `JarFile`.
- `className` chỉ chuyển tên đường dẫn có đuôi `.class` thành chuỗi. Đây chưa phải kiểm tra tên hợp lệ, chưa kiểm tra metadata và chưa cấp quyền load.
- `Collections.sort` làm thứ tự kết quả ổn định. Những class trùng giữa nhiều root sẽ cần cơ chế hợp nhất riêng.
- Bộ quét JAR trong ví dụ **cố ý bỏ qua** `META-INF/versions/`, nên không dùng nó để báo cáo chính xác toàn bộ lớp phiên bản trong multi-release JAR.
- Thí dụ không xử lý `module-info.class`, `package-info.class` hoặc nested JAR nếu tình cờ xuất hiện; công cụ thực tế phải lọc các entry đó theo mục đích.

Nếu kết quả `Candidates` thay đổi khi chạy trong thư mục chứa file bổ sung, đó là bình thường vì scanner đếm **entry trong root đã chỉ định**, không phải số class đã nạp trong JVM.

## 7. “Tìm các class có annotation” cần thêm một tầng khám phá

Giả sử bạn muốn các class được gắn `@MyPlugin`.

```java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface MyPlugin {}
```

**Đoạn khai báo annotation trên chỉ minh họa**, muốn biên dịch độc lập cần thêm import từ `java.lang.annotation` và đặt trong file hợp lệ.

Không tồn tại:

```java
// PSEUDOCODE: API này KHÔNG tồn tại trong Java Core Reflection.
List<Class<?>> types = Reflection.findAllAnnotatedClasses(MyPlugin.class);
```

Thực tế một scanner phải:

1. Xác định những root/module/source được quét.
2. Tìm entry hoặc metadata ứng viên bằng filesystem/JAR/API phù hợp.
3. Có thể phân tích metadata từ bytecode mà **không load class**, hoặc chọn load class theo class loader và kiểm soát lỗi.
4. Với class đã load được và annotation lưu ở runtime, gọi `clazz.isAnnotationPresent(MyPlugin.class)` / `getAnnotation`.
5. Kiểm tra contract/constructor/quyền truy cập rồi mới tạo instance và thực thi.

`isAnnotationPresent` xử lý **một** `Class<?>`, không tự cung cấp tập `Class<?>` ban đầu.

### Khi nào nên dùng thư viện scanner?

- Nếu cần duyệt cả **classpath phức tạp**, package filtering, nested JAR hoặc các loại loader, hãy cân nhắc thư viện có hỗ trợ môi trường đó, ví dụ **ClassGraph**, hoặc scanner của framework mà dự án đang dùng.
- Nếu đã dùng Spring, cơ chế component scanning/classpath metadata scanning của framework có thể phù hợp; việc Spring tự tìm bean **không biến tính năng đó thành API của `java.lang.reflect`**.
- Với môi trường plugin có contract rõ ràng, thường nên tránh quét toàn bộ classpath: dùng registry rõ ràng, tên plugin trong cấu hình, hoặc **`ServiceLoader`**.

Khi dùng thư viện, cần kiểm tra version/khả năng tương thích với JDK, JPMS, cách đóng gói và custom class loader. Không được kỳ vọng thư viện thứ ba tự phát hiện mọi class có thể xuất hiện động trong tương lai.

## 8. Nếu chỉ muốn plugin: `ServiceLoader` thường đúng bài toán hơn

Nhiều chương trình dùng Reflection scan cả classpath chỉ để tìm mọi implementation của một interface. Nếu bạn kiểm soát hợp đồng đăng ký plugin, **Service Provider Interface (SPI)** là lựa chọn rõ nghĩa hơn:

```java
// Phác thảo: PaymentPlugin là interface mà ứng dụng định nghĩa.
ServiceLoader<PaymentPlugin> plugins =
        ServiceLoader.load(PaymentPlugin.class);

for (PaymentPlugin plugin : plugins) {
    plugin.execute();
}
```

Đây là đoạn minh họa chưa độc lập vì ứng dụng cần định nghĩa `PaymentPlugin` và khai báo provider trong `META-INF/services/<tên.interface>` cho classpath, hoặc `provides ... with ...` trong module descriptor khi dùng named modules.

Điểm khác biệt:

- `ServiceLoader` liệt kê **provider đã được khai báo** cho một service cụ thể, không liệt kê mọi class.
- Có thể khám phá provider rồi khởi tạo/lấy instance theo yêu cầu (phụ thuộc cách sử dụng API).
- Mô hình này thể hiện rõ plugin contract và tránh việc scan mọi class để đoán đâu là plugin.
- Vẫn phải xử lý provider cấu hình sai, thiếu dependency, lỗi khởi tạo và giới hạn của loader/module phù hợp.

Nếu mục tiêu thực sự chỉ là “tìm plugin được đăng ký”, việc thêm một danh sách provider rõ ràng là hành vi thiết kế tốt hơn so với quét classpath không giới hạn.

## 9. Nếu muốn “các class đang được nạp”: Java agent khác Core Reflection

`java.lang.instrument.Instrumentation` có phương thức `getAllLoadedClasses()` cho các class **đã load vào JVM** khi gọi. Cần một instrumentation agent hợp lệ được cấp đối tượng `Instrumentation` (thường thông qua `premain` hoặc `agentmain` và manifest/thiết lập phù hợp).

Phương thức này:

- Không phải API từ `java.lang.Class` hay `java.lang.reflect`.
- Không xuất hiện tùy ý chỉ bằng `new Instrumentation()` (đây là interface mà agent nhận do JVM cung cấp).
- Không liệt kê mọi class có thể load về sau hoặc mọi entry của JAR chưa được dùng.
- Có thể trả những class từ nhiều class loader, kể cả các class không nằm trên application classpath.
- Chỉ trả snapshot tại một thời điểm, không phải bản đồ bất biến cho toàn bộ đời sống ứng dụng.

Đối với công cụ quan sát runtime, profiling và instrumentation, hướng này phù hợp hơn việc cố gắng suy diễn tập class đã load bằng quét file. Nhưng với scanner để tìm plugin có thể **chưa được load**, API này lại không thay thế bước khám phá nguồn.

## 10. Named modules và hình ảnh runtime Java 9+

Với Java Platform Module System (JPMS), đường đi không đơn giản chỉ là `-cp`. `ModuleLayer.boot().modules()` có thể cho biết module trong boot layer, nhưng đó là tập **module**, chưa phải toàn bộ class của mỗi module. Layer tự tạo sau đó cũng không nhất thiết nằm trong boot layer.

Để xem resource bên trong một module **đã được xác định**, hệ sinh thái `java.lang.module` có `ModuleReference.open()` và `ModuleReader.list()`; cách này vẫn phải bắt đầu từ module được giải quyết trong cấu hình chạy và tôn trọng giới hạn API. **Nó không phải phương thức Core Reflection tự liệt kê mọi classpath entry**.

Các class JDK còn có thể được lưu trong runtime image qua `jrt:/` thay vì những JAR kiểu `rt.jar` như các JDK rất cũ. Do đó không nên viết scanner chỉ đi tìm `rt.jar` và kết luận đã liệt kê được toàn bộ JDK.

**Phân biệt:** đọc được tên `.class` trong một module chưa bảo đảm consumer được phép gọi class đó. Java modules dùng `exports` cho API truy cập bình thường và `opens` cho một số trường hợp deep reflection; class loader và module access đều quan trọng.

## 11. Những bẫy thiết kế phổ biến

### Bẫy A — Dùng `ClassLoader.getResources("com/foo")` rồi coi URL trả về là danh sách package

API đó chỉ tìm **resource theo tên**, và một package không nhất thiết có directory entry trong JAR. Nó cũng không bảo đảm trả mọi nguồn class. Hãy giới hạn rõ nguồn, hỗ trợ từng scheme, hoặc dùng scanner có chủ đích.

### Bẫy B — Quét `java.class.path` và tuyên bố “đã tìm mọi class”

System property không mô tả đầy đủ custom loaders, named modules, generated classes, agent activity hoặc môi trường đặc thù. Tên trùng giữa các nguồn cũng đòi hỏi xét loader và thứ tự ưu tiên.

### Bẫy C — Nạp tất cả class để xem annotation

Điều đó có thể làm tăng I/O, memory footprint, gây class loading/linkage error và kích hoạt hành vi ngoài dự kiến khi dùng API có initialize. Ưu tiên lọc bằng metadata/bytecode trước; khi cần load hãy dùng loader đúng và `Class.forName(name, false, loader)`, với xử lý lỗi đầy đủ.

### Bẫy D — Coi file `.class` là plugin an toàn

Một file bytecode có thể có class phụ thuộc bị thiếu, class abstract, quyền truy cập không phù hợp, constructor thiếu hoặc logic nguy hiểm. Cần validate contract, allowlist và chính sách khởi tạo; quét tên chỉ là bước đầu.

### Bẫy E — Quét cả classpath quá rộng trong mỗi request

Classpath có thể rất lớn. Quét toàn bộ trên đường xử lý request vừa tốn chi phí vừa tăng khả năng lỗi. Giới hạn package/root, dùng cache theo vòng đời ứng dụng, chủ động invalidate khi class loader/redeploy thay đổi; với môi trường build kiểm soát được có thể sinh index ngay khi build.

### Bẫy F — Quên sự khác nhau giữa binary name và file path

`com/acme/Outer$Inner.class` là resource path; binary name thường là `com.acme.Outer$Inner`. Không biến dấu `$` thành dấu `.` tùy ý khi load class. Một số tên nội bộ, class local/anonymous, `module-info` hoặc `package-info` cần chính sách riêng.

### Bẫy G — Dựa vào thứ tự duyệt file/JAR

Thứ tự `Files.walk` hoặc `JarFile.entries` không phải thứ tự ưu tiên nghiệp vụ. Sắp xếp kết quả nếu cần output xác định và quy định giải quyết duplicate rõ ràng. Đừng dùng “class đầu tiên tìm thấy” làm plugin được chọn nếu không có contract thứ tự.

## 12. Chọn giải pháp dựa trên mục tiêu

| Mục tiêu | Cách nên bắt đầu |
| --- | --- |
| Biết tên class từ cấu hình | `Class.forName(name, false, loader)` và kiểm tra contract |
| Đọc field/method/annotation của class đã biết | `Class<?>` và Reflection |
| Liệt kê `.class` trong một thư mục/JAR **đã chỉ định** | `Files.walk` / `JarFile` |
| Tìm implementation đã đăng ký cho một interface | `ServiceLoader` / registry |
| Tìm bean/component trong ứng dụng Spring | Component scanning/metadata scanning của Spring |
| Quét package/classpath phức tạp của một ứng dụng cụ thể | Scanner chuyên dụng phù hợp môi trường |
| Thống kê class **đã load** trong một JVM | `Instrumentation` qua Java agent |
| Phân tích resource của **module đã xác định** | `ModuleReader` và module resolution API |
| Muốn mọi class có thể xuất hiện trong mọi loader của JVM | Phải thu hẹp định nghĩa và phạm vi; không có API tổng quát đáp ứng tuyệt đối |

## 13. Ghi nhớ

1. **Reflection bắt đầu từ một `Class<?>` hoặc một tên type đã biết.** Nó cho phép xem cấu trúc và thao tác động với thành viên của type đó, **không** có API core tự liệt kê tất cả class của classpath.
2. **Classpath entry, candidate class name, class loadable, class loaded và class accessible là năm khái niệm khác nhau.** Không tự đồng nhất các tập này.
3. **Khám phá class** là trách nhiệm của filesystem/JAR/module/source index/class loader framework phù hợp với môi trường chạy; mỗi cách chỉ bao phủ phần phạm vi mà nó hiểu.
4. Nếu cần plugin theo hợp đồng, hãy xem xét **`ServiceLoader` hoặc explicit registry** trước khi áp dụng quét rộng.
5. Nếu cần class đã load, xem hướng **Instrumentation**, không suy diễn từ số file `.class`.
6. Công cụ quét đúng cần có **phạm vi rõ, bộ lọc, xử lý class loader/module, lỗi và giới hạn tài nguyên**, không được quảng cáo kết quả quét một directory/JAR là “mọi lớp trong JVM”.

### Tự kiểm tra

- `getDeclaredClasses()` có tìm được các class top-level ở cùng package không? Vì sao?
- `Class.forName("com.example.Widget")` có tự khám phá tên class nào khác không?
- Vì sao `ClassLoader.getResources("com/example")` có thể trả rỗng dù vẫn load được `com.example.Widget`?
- Một file `.class` nằm trong JAR có chắc JVM đã load class đó chưa?
- Nếu hai custom class loader load cùng binary name, ta có chắc nhận một runtime type duy nhất không?
- Khi xây plugin registry, tại sao `ServiceLoader` thường hợp lý hơn quét tất cả JAR?
- `Instrumentation.getAllLoadedClasses()` giải quyết câu hỏi nào và **không** giải quyết câu hỏi nào?
- Vì sao code ví dụ chỉ nói “Candidates: 2” thay vì “All classes in classpath: 2”?

### Tài liệu tham khảo chính thức

- [`Class` — Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html): `getDeclaredClasses`, `forName` và Reflection theo một kiểu.
- [`ClassLoader` — Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html): `loadClass`, `getResources`, phạm vi và cơ chế delegation.
- [`JarFile` — Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/jar/JarFile.html): đọc entry từ một JAR đã chỉ định.
- [`ServiceLoader` — Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html): đăng ký và khám phá provider theo SPI.
- [`Instrumentation` — Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): `getAllLoadedClasses` qua agent.
- [`ModuleReader` — Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/module/ModuleReader.html): đọc và liệt kê resource của module xác định.
