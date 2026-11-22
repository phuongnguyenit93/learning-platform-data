# Quan hệ giữa class loader, định danh lớp và tài nguyên trong Java

**Chủ đề:** Java 7 — Nạp lớp an toàn  
**Bài học:** Quan hệ giữa class loader, định danh lớp và tài nguyên  
**Môi trường thực hành:** Java 17+ (các khái niệm class loader có từ Java rất sớm và **vẫn hiện hành**). Ví dụ dùng API chuẩn `ClassLoader`, `Class`, `URLClassLoader`, `Module`, `ServiceLoader`, `JavaCompiler`. Không dựa vào extension mechanism cũ, `SecurityManager` như một sandbox mới, hoặc truy cập `sun.*`/`jdk.internal.*` không được hỗ trợ.

## 1. Vì sao cùng tên lớp chưa chắc cùng lớp?

Trong mã nguồn, một kiểu thường được nhận diện bằng tên như `com.example.plugins.Task`. Nhưng JVM có thể chạy nhiều phiên bản của cùng thư viện trong những **không gian nạp lớp (class loader namespaces)** khác nhau.

Quy tắc trung tâm của JVM:

> **Danh tính runtime của một class/interface thông thường được xác định bởi cặp (binary name, defining class loader).**

Điều đó có nghĩa:

- Cùng **binary name** và cùng **defining loader** → cùng runtime class (với class thông thường).
- Cùng binary name nhưng **defining loader khác nhau** → **hai class khác nhau**, dù bytecode giống hệt.
- Hai `Class<?>` có cùng `getName()` chưa chắc `==`, `isAssignableFrom` hay cast tương thích.
- Hai bản copy của interface chung được nạp bởi hai loader riêng cũng có thể gây lỗi plugin `ClassCastException` hoặc `LinkageError`.
- Một loader **được yêu cầu** nạp class không nhất thiết là loader **định nghĩa** class đó: delegation có thể chuyển công việc cho parent.

Đây không phải một vấn đề chỉ tồn tại trong app server cũ. Nó xuất hiện ở hệ thống plugin hiện đại, hệ thống chạy nhiều phiên bản library, test tools, JDK modules/class loaders và hot reload.

### 1.1. Mô hình một host và hai plugin

```text
JVM
 ├─ Bootstrap loader
 │    └─ java.lang.String, java.lang.Object, ...
 ├─ Platform class loader
 │    └─ Một phần platform modules
 └─ Application / system class loader
      └─ com.example.api.TaskPlugin   <-- HỢP ĐỒNG CHUNG
           |
           +-- Plugin loader A
           |     └─ com.example.plugin.Widget  (Class object A)
           |
           +-- Plugin loader B
                 └─ com.example.plugin.Widget  (Class object B)

Class object A != Class object B dù đều getName()=="com.example.plugin.Widget"
```

**Phân biệt quan trọng:** class loader không chỉ là nơi “tìm file .class”. Nó tham gia quyết định **runtime type identity**, quy tắc delegation, tài nguyên đi kèm code, module visibility, lifecycle và khả năng tách biệt thư viện. Nhưng **class loader isolation không tự là security sandbox** cho bytecode không đáng tin cậy.

## 2. Class loading, linking và initialization khác nhau

Một câu như “class đã được load” có thể che nhiều giai đoạn JVM:

1. **Loading:** tìm binary representation và tạo `Class<?>`.
2. **Linking:** verification, preparation và resolution theo các quy định JVM; resolution có thể lười (lazy).
3. **Initialization:** chạy class initialization, ví dụ static field initializers và static blocks.

`ClassLoader.loadClass("x.Y")` thường dùng để load class, không mặc định khởi tạo nó. `Class.forName(String)` overload một tham số có thể **kích hoạt initialization** theo API; `Class.forName(name, false, loader)` yêu cầu không initialize tại thời điểm đó.

Không nên gọi `Class.forName(name,false,loader)` là một phép “kiểm tra an toàn tuyệt đối”. Class vẫn có thể được verified/linked, loader thực thi code riêng, và các thao tác sau có thể kích hoạt initialization hay các side effects khác.

### 2.1. Vì sao biết giai đoạn này có ích?

- Một plugin có static initializer gọi filesystem/network trước khi app có đủ kiểm soát.
- Một dependency bị thiếu chỉ lộ ra khi JVM giải quyết một reference, không nhất thiết ngay khi bạn lấy được `Class<?>`.
- Code có thể xử lý `ClassNotFoundException` sai chỗ, trong khi lỗi runtime thực tế là `NoClassDefFoundError`.
- Kết quả `loadClass` có thể là một `Class` do parent định nghĩa chứ không phải phiên bản JAR mà bạn vừa thêm vào child loader.

## 3. Bootstrap, platform, application và custom loaders

JDK hiện đại thường có các tầng quan trọng:

| Thành phần | Vai trò | Điểm cần nhớ |
| --- | --- | --- |
| Bootstrap class loader | Load những lớp nền tảng quan trọng của JVM | Thường biểu diễn bằng `null` ở `Class.getClassLoader()` |
| Platform class loader | Load một phần Java platform modules | Lấy qua `ClassLoader.getPlatformClassLoader()` |
| System/application class loader | Load ứng dụng theo class path hoặc module configuration | `ClassLoader.getSystemClassLoader()` |
| Custom `ClassLoader` | Không gian nạp lớp do ứng dụng/framework định nghĩa | Có thể delegate/định nghĩa classes và resources |
| `URLClassLoader` | Loader hữu ích cho URLs như thư mục/JAR | `AutoCloseable`; cần đóng để giải phóng file/JAR handles |
| Thread context class loader (TCCL) | Một **tham chiếu loader gắn với thread**, thường dùng cho service/provider discovery | Không phải luôn là defining loader của code đang chạy |

**Chú ý:** không phải mọi JVM deployment đều có đúng hình cây như ví dụ. Platform/system loaders có thể được cấu hình/customized. API contract và actual loader identity mới là điều cần kiểm tra.

### 3.1. Chương trình độc lập: xem các loader quan trọng

Lưu `LoaderHierarchyDemo.java`:

```java
public class LoaderHierarchyDemo {
  public static void main(String[] args) {
    ClassLoader application = LoaderHierarchyDemo.class.getClassLoader();
    ClassLoader platform = ClassLoader.getPlatformClassLoader();
    ClassLoader system = ClassLoader.getSystemClassLoader();
    System.out.println("application-loader-present=" + (application != null));
    System.out.println("platform-loader-present=" + (platform != null));
    System.out.println("string-bootstrap-null=" + (String.class.getClassLoader() == null));
    System.out.println("system-loader-matches-main=" + (application == system));
  }
}
```

Biên dịch/chạy trên JDK 17+ với classpath mặc định:

```bash
javac -encoding UTF-8 -Xlint:all LoaderHierarchyDemo.java
java LoaderHierarchyDemo
```

**stdout đã kiểm thử trong môi trường classpath tiêu chuẩn:**

```text
application-loader-present=true
platform-loader-present=true
string-bootstrap-null=true
system-loader-matches-main=true
```

Demo không dựa vào tên class implementation loader như `jdk.internal.loader.ClassLoaders$AppClassLoader`. Đây là implementation detail có thể thay đổi. Ở môi trường tùy biến, loader của ứng dụng không bắt buộc trùng system loader; test demo đang minh họa **một cấu hình phổ biến**, không nên copy boolean cuối làm assertion xuyên mọi deployment.

## 4. Defining loader và initiating loader

JVM phân biệt:

- **Defining loader:** loader tạo `Class<?>` từ class bytes bằng `defineClass` hoặc cơ chế định nghĩa tương đương.
- **Initiating loader:** loader mà JVM ghi nhận đã khởi xướng việc load class. Nó có thể tự định nghĩa hoặc được parent nạp giúp.
- **Delegation:** loader con hỏi parent trước rồi mới tìm trong nguồn của chính nó theo thuật toán mặc định.

Ví dụ child loader được gọi `child.loadClass("java.lang.String")` nhưng `String.class.getClassLoader()==null` vì bootstrap đã định nghĩa nó.

**Không suy ngược rằng `obj.getClass().getClassLoader()==child` chỉ vì bạn gọi `child.loadClass(...)`.** Hỏi loader nào định nghĩa class bằng `getClassLoader()`.

### 4.1. Chương trình: child yêu cầu nhưng parent định nghĩa

Lưu `InitiatingVsDefiningDemo.java`:

```java
import java.net.URL;
import java.net.URLClassLoader;
public class InitiatingVsDefiningDemo {
  public static void main(String[] args) throws Exception {
    ClassLoader defining = InitiatingVsDefiningDemo.class.getClassLoader();
    try (URLClassLoader delegating = new URLClassLoader(new URL[0], defining)) {
      Class<?> resolved = delegating.loadClass(InitiatingVsDefiningDemo.class.getName());
      Class<?> bootstrap = delegating.loadClass("java.lang.String");
      System.out.println("parent-defined-same-class=" + (resolved == InitiatingVsDefiningDemo.class));
      System.out.println("requested-loader-not-defining=" + (resolved.getClassLoader() != delegating));
      System.out.println("parent-is-defining=" + (resolved.getClassLoader() == defining));
      System.out.println("bootstrap-string-null-loader=" + (bootstrap.getClassLoader() == null));
    }
  }
}
```

```bash
javac -encoding UTF-8 -Xlint:all InitiatingVsDefiningDemo.java
java InitiatingVsDefiningDemo
```

**stdout đã kiểm thử:**

```text
parent-defined-same-class=true
requested-loader-not-defining=true
parent-is-defining=true
bootstrap-string-null-loader=true
```

Child có **0 URLs**, nên nó không có nguồn để tự định nghĩa class. Nó delegate tới parent — parent trả đúng class đã nạp từ application classpath. Cơ chế này giải thích tại sao **đối tượng loader đi tìm** không phải lúc nào cũng là **loader quyết định identity**.

## 5. Cùng binary name nhưng hai loader: hai kiểu không cast được

Một trong những lỗi thường thấy ở plugin/runtime là:

```text
java.lang.ClassCastException:
  class example.Widget cannot be cast to class example.Widget
```

Thông báo trông mâu thuẫn vì tên lớp giống nhau. Nhưng hai class objects có **defining loaders khác nhau**.

Để chứng minh đúng cách, chương trình sau dùng `JavaCompiler` của **JDK** tạo một `example.identity.Widget` trong thư mục tạm, rồi dùng **hai `URLClassLoader` khác nhau** load cùng class file. Không tải bytecode từ mạng và không sửa project.

### 5.1. Chương trình: chứng minh class identity

Lưu `ClassIdentityDemo.java`:

```java
import java.io.IOException;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.*;
import java.util.Comparator;
import java.util.stream.Stream;
import javax.tools.*;
public class ClassIdentityDemo {
  static void clean(Path root) throws IOException {
    try (Stream<Path> paths = Files.walk(root)) {
      for (Path p : paths.sorted(Comparator.reverseOrder()).toList()) Files.deleteIfExists(p);
    }
  }
  public static void main(String[] args) throws Exception {
    Path root = Files.createTempDirectory("identity-demo-");
    try {
      Path source = root.resolve("Widget.java");
      Files.writeString(source,
          "package example.identity; public class Widget { public String label() { return \"alpha\"; } }");
      JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
      if (compiler == null || compiler.run(null, null, null, "-encoding", "UTF-8",
          "-d", root.toString(), source.toString()) != 0) throw new AssertionError("compile");
      URL[] urls = {root.toUri().toURL()};
      try (URLClassLoader first = new URLClassLoader(urls, ClassLoader.getPlatformClassLoader());
           URLClassLoader second = new URLClassLoader(urls, ClassLoader.getPlatformClassLoader())) {
        Class<?> one = first.loadClass("example.identity.Widget");
        Class<?> two = second.loadClass("example.identity.Widget");
        Object instance = one.getDeclaredConstructor().newInstance();
        boolean castDenied = false;
        try { two.cast(instance); } catch (ClassCastException ex) { castDenied = true; }
        System.out.println("same-binary-name=" + one.getName().equals(two.getName()));
        System.out.println("distinct-defining-loader=" + (one.getClassLoader() != two.getClassLoader()));
        System.out.println("distinct-class-object=" + (one != two));
        System.out.println("cross-loader-cast-denied=" + castDenied);
      }
    } finally { clean(root); }
  }
}
```

```bash
javac -encoding UTF-8 -Xlint:all ClassIdentityDemo.java
java ClassIdentityDemo
```

**stdout đã kiểm thử:**

```text
same-binary-name=true
distinct-defining-loader=true
distinct-class-object=true
cross-loader-cast-denied=true
```

**Đọc kỹ:**

1. `JavaCompiler` biên dịch đúng **một** source file, ra một phiên bản bytecode.
2. `first` và `second` cùng thấy đúng URL thư mục; nhưng **mỗi loader tự định nghĩa** `Widget`.
3. `one.getName().equals(two.getName())` là true.
4. `one != two` và `one.getClassLoader()!=two.getClassLoader()` là true.
5. Instance được tạo bởi `one` không thể cast thành `two`: `Class.cast` ném `ClassCastException`.

Vấn đề không nằm ở khác version bytecode; ngay cả bytecode giống hệt vẫn tạo **hai runtime types** khi định nghĩa bởi hai loaders.

### 5.2. Hệ quả với interface chung

Nếu plugin A định nghĩa một bản `com.example.api.Plugin` riêng và host định nghĩa bản khác, class thực thi interface **theo bản của plugin** có thể không được host xem là `instanceof com.example.api.Plugin`.

**Thiết kế tốt:** đặt service interface, DTO hợp đồng, annotation API và shared SPI trong parent/module được chia sẻ, để plugin loaders delegate nạp **cùng một Class object** cho các types tại boundary. Đừng tự copy tất cả JARs vào từng plugin loader mà không phân biệt shared API với private implementation.

### 5.3. Class identity không phải so sánh class name

Không kiểm tra plugin compatibility bằng:

```java
if (a.getClass().getName().equals(b.getClass().getName())) { /* cast */ }
```

Đây là snippet **không đủ an toàn kiểu**. Cần kiểm tra `Class.isAssignableFrom`, `instanceof`, interface/classloader contract và module policy phù hợp. Nếu cần giao tiếp giữa hai versions không tương thích, chuyển qua một **protocol/DTO được định nghĩa bởi loader chung** hoặc serialization có schema rõ, không cast bừa.

## 6. Parent-first delegation và giới hạn của “mỗi loader có một không gian độc lập”

Trong `ClassLoader.loadClass` mặc định:

```text
loadClass(binaryName)
  |
  +-- Đã load trong loader này? -> trả Class
  |
  +-- Parent (nếu có) -> hỏi parent
  |
  +-- Không được parent tìm thấy -> findClass của child
  |
  +-- resolve/link khi phù hợp
```

**Parent-first** tránh việc một plugin vô tình định nghĩa lại các lớp shared/platform và giảm xung đột type identities tại boundary. Nhưng đây là **chiến lược mặc định**, không phải quy luật JVM bắt buộc mọi custom loader phải tuân theo. Một số frameworks dùng child-first có kiểm soát để cô lập dependency versions.

### 6.1. Không chỉ override loadClass rồi kết luận mọi thứ child-first

Một điểm tinh tế: **class lookup và resource lookup là hai nhánh có thể được override độc lập**.

Nếu bạn override `loadClass` thành child-first nhưng giữ `getResource` mặc định parent-first, có thể xảy ra:

- Class `sample.Mode` được định nghĩa từ **child**.
- Nhưng `child.getResource("sample/mode.txt")` lại lấy nội dung từ **parent**.
- Cả class và file đều có tên/path phù hợp, nhưng **không đến từ cùng một artifact**.
- Config, schema, message catalog hay native files có thể bị đọc nhầm phiên bản.

Ví dụ ở phần 11 chứng minh tình huống này. Trong production, custom delegation phải được xem xét cho **cả classes và resources**, với tests version isolation.

### 6.2. Delegation không tự thực hiện phân quyền dữ liệu

Một parent-first loader có thể ngăn child ghi đè một số shared classes, nhưng **không làm plugin không tin cậy trở thành an toàn**. Bytecode có thể gọi public APIs được cho phép, sử dụng IO/network hay gây lỗi tài nguyên theo sandbox/process policy. Không coi cách sắp xếp parent-child là một cơ chế thực thi authorization thay thế process isolation.

## 7. Class.getResource và ClassLoader.getResource: cùng tên, khác quy tắc tên đường dẫn

Class loader còn có trách nhiệm tìm các **resources**: `.properties`, JSON schema, templates, images, service descriptors, `.class` files... Resource được định danh bởi một **chuỗi path với dấu “/”**, không phải tự động một `Path` file trên máy.

Cực kỳ quan trọng:

| API | Tên không có `/` đầu | Tên có `/` đầu |
| --- | --- | --- |
| `Class.getResource("name.txt")` | **Relative** theo package của class | **Absolute** từ root của resource namespace (bỏ dấu `/` đầu) |
| `Class.getResourceAsStream("name.txt")` | Relative theo package | Absolute từ root |
| `ClassLoader.getResource("pkg/name.txt")` | Dùng tên resource **từ root**, không thêm package | **Không** có quy tắc “dấu / = absolute” như `Class`; tránh leading slash |
| `ClassLoader.getResourceAsStream("pkg/name.txt")` | Tương tự loader resource | Tránh leading slash |
| `Module.getResourceAsStream("pkg/name.txt")` | Resource thuộc **module** | Có thể bỏ leading slash theo Module API, nhưng subject to module encapsulation |

Ví dụ nếu class `lesson.resources.Reader` đang ở package `lesson.resources`:

- `Reader.class.getResource("settings.txt")` tìm `lesson/resources/settings.txt`.
- `Reader.class.getResource("/lesson/resources/settings.txt")` tìm đúng cùng resource từ root.
- `Reader.class.getClassLoader().getResource("lesson/resources/settings.txt")` dùng tên từ root **không có /** đầu.
- `Reader.class.getClassLoader().getResource("settings.txt")` tìm resource ở **root**, không phải trong package.

### 7.1. Chương trình runnable: xác nhận cách đặt tên

Lưu `ResourceNamesDemo.java`, lưu ý dòng `package` ở đầu:

```java
package lesson.resources;
public class ResourceNamesDemo {
  public static void main(String[] args) {
    Class<?> anchor = ResourceNamesDemo.class;
    ClassLoader loader = anchor.getClassLoader();
    String full = "lesson/resources/ResourceNamesDemo.class";
    System.out.println("class-relative-found=" + (anchor.getResource("ResourceNamesDemo.class") != null));
    System.out.println("class-absolute-found=" + (anchor.getResource("/" + full) != null));
    System.out.println("class-wrong-root-missing=" + (anchor.getResource("/ResourceNamesDemo.class") == null));
    System.out.println("loader-no-leading-slash-found=" + (loader.getResource(full) != null));
    System.out.println("loader-leading-slash-missing=" + (loader.getResource("/" + full) == null));
  }
}
```

Biên dịch có `-d .` vì file khai báo package; chạy bằng tên fully qualified:

```bash
javac -encoding UTF-8 -Xlint:all -d . ResourceNamesDemo.java
java lesson.resources.ResourceNamesDemo
```

**stdout đã kiểm thử:**

```text
class-relative-found=true
class-absolute-found=true
class-wrong-root-missing=true
loader-no-leading-slash-found=true
loader-leading-slash-missing=true
```

**Lưu ý:** demo dùng `ResourceNamesDemo.class` làm resource có sẵn sau biên dịch, tránh phải chuẩn bị một file text phụ. Đối với file JSON/properties thực tế, bạn cần **đóng gói nó trong đúng thư mục/JAR/module**; class loader không tự tìm file bất kỳ ở working directory.

## 8. Đọc resource an toàn bằng stream, UTF-8 và try-with-resources

Không dùng `URL.getFile()` rồi chuyển thành `new File(...)` một cách vô điều kiện. Resource URL có thể dùng các scheme:

- `file:` khi class/resource ở thư mục.
- `jar:` khi nằm trong JAR; ví dụ `jar:file:/...!/config/app.txt`.
- `jrt:` cho modules nằm trong runtime image JDK.
- Scheme đặc thù của framework/container.

**Một resource không nhất thiết là một file OS có thể sửa/xóa trực tiếp.** Để đọc nội dung, dùng `getResourceAsStream` và **đóng stream** bằng try-with-resources.

### 8.1. Chương trình runnable: tạo resource UTF-8 trong thư mục tạm

Lưu `ResourceStreamDemo.java`:

```java
import java.io.*;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
public class ResourceStreamDemo {
  public static void main(String[] args) throws Exception {
    Path root = Files.createTempDirectory("resource-demo-");
    try {
      Files.createDirectories(root.resolve("assets"));
      Files.writeString(root.resolve("assets/greeting.txt"), "xin-chao",
          StandardCharsets.UTF_8);
      try (URLClassLoader loader = new URLClassLoader(new URL[]{root.toUri().toURL()}, null)) {
        String data;
        try (InputStream in = loader.getResourceAsStream("assets/greeting.txt")) {
          if (in == null) throw new AssertionError("missing resource");
          data = new String(in.readAllBytes(), StandardCharsets.UTF_8);
        }
        System.out.println("resource-text=" + data);
        System.out.println("url-present=" + (loader.getResource("assets/greeting.txt") != null));
        System.out.println("missing-is-null=" + (loader.getResourceAsStream("assets/missing.txt") == null));
        System.out.println("leading-slash-not-used=" + (loader.getResource("/assets/greeting.txt") == null));
      }
    } finally {
      Files.deleteIfExists(root.resolve("assets/greeting.txt"));
      Files.deleteIfExists(root.resolve("assets"));
      Files.deleteIfExists(root);
    }
  }
}
```

```bash
javac -encoding UTF-8 -Xlint:all ResourceStreamDemo.java
java ResourceStreamDemo
```

**stdout đã kiểm thử:**

```text
resource-text=xin-chao
url-present=true
missing-is-null=true
leading-slash-not-used=true
```

**Cần nhớ:**

1. `getResourceAsStream` trả `null` nếu resource không tìm thấy hoặc không truy cập được theo API.
2. Stream có thể giữ file/JAR handles; **đóng nó**.
3. `StandardCharsets.UTF_8` quyết định charset, không phụ thuộc default platform encoding.
4. Resource name dùng `/` kể cả trên Windows.
5. Sau khi đọc xong, URLClassLoader cũng được close.
6. Ví dụ sử dụng **nguồn cục bộ do chương trình tạo** nên không mở file Internet hoặc chạy code không tin cậy.

### 8.2. Khi resource bị thiếu

Production code thường không nên để `NullPointerException` xuất hiện ngẫu nhiên ở `new InputStreamReader(null)`. Hãy tạo exception rõ:

```java
try (InputStream in = Objects.requireNonNull(
        anchor.getResourceAsStream("/app/defaults.properties"),
        "Missing packaged resource: /app/defaults.properties")) {
    // Đọc và validate nội dung.
}
```

Đây là **snippet** cần imports và biến `anchor`. `Objects.requireNonNull` chỉ kiểm resource tồn tại, **không xác thực nội dung** và không bảo đảm origin an toàn. Với user-controlled resources, giới hạn tên, kích thước và parser policy.

## 9. Tài nguyên trùng tên: getResource và getResources

Nếu hai JARs hoặc hai loaders cung cấp cùng resource path, `getResource(name)` chỉ chọn **một URL** theo search policy; `getResources(name)` liệt kê **nhiều URL**.

Với implementation mặc định `ClassLoader`, resource search **hỏi parent trước**, sau đó `findResource` của child; `getResources` cũng đưa parent resources trước child resources. **Không** áp dụng kết luận này cho mọi custom loader: implementation có thể override.

Với nhiều **named modules được cùng một loader định nghĩa**, JavaDoc còn cảnh báo ordering của các modules chứa resource cùng tên **không được bảo đảm**. Vì vậy không dựa vào một thứ tự “classpath lookup” tự suy đoán khi module graph phức tạp.

### 9.1. Chương trình: parent và child cùng có một resource

Lưu `ParentFirstResourceDemo.java`:

```java
import java.io.*;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.*;
import java.util.stream.*;
public class ParentFirstResourceDemo {
  static String read(URL url) throws IOException {
    try (InputStream in = url.openStream()) {
      return new String(in.readAllBytes(), StandardCharsets.UTF_8);
    }
  }
  public static void main(String[] args) throws Exception {
    Path root = Files.createTempDirectory("duplicate-resource-");
    try {
      Path parent = Files.createDirectories(root.resolve("parent/config"));
      Path child = Files.createDirectories(root.resolve("child/config"));
      Files.writeString(parent.resolve("mode.txt"), "PARENT");
      Files.writeString(child.resolve("mode.txt"), "CHILD");
      try (URLClassLoader parentLoader = new URLClassLoader(
               new URL[]{root.resolve("parent").toUri().toURL()}, null);
           URLClassLoader childLoader = new URLClassLoader(
               new URL[]{root.resolve("child").toUri().toURL()}, parentLoader)) {
        URL first = childLoader.getResource("config/mode.txt");
        List<URL> all = Collections.list(childLoader.getResources("config/mode.txt"));
        System.out.println("single-resource=" + read(Objects.requireNonNull(first)));
        System.out.println("resource-count=" + all.size());
        System.out.println("resource-order=" + read(all.get(0)) + "," + read(all.get(1)));
      }
    } finally {
      try (Stream<Path> paths = Files.walk(root)) {
        for (Path p : paths.sorted(Comparator.reverseOrder()).toList()) Files.deleteIfExists(p);
      }
    }
  }
}
```

```bash
javac -encoding UTF-8 -Xlint:all ParentFirstResourceDemo.java
java ParentFirstResourceDemo
```

**stdout đã kiểm thử:**

```text
single-resource=PARENT
resource-count=2
resource-order=PARENT,CHILD
```

**Giải thích:** parent và child nằm ở hai folders độc lập, có nội dung khác nhau dưới cùng `config/mode.txt`. `getResource` theo parent-first trả URL từ parent; `getResources` thấy cả hai, theo thứ tự parent rồi child trong cấu hình demo.

### 9.2. Hệ quả trong production

- Một file `config.yaml` cũ trong shared dependency có thể che file mới của plugin.
- `META-INF/services/...` có thể xuất hiện ở nhiều artifacts; một loader/service mechanism phải liệt kê, không chỉ đọc “file đầu tiên”.
- Một schema JSON tải từ resource sai version có thể khiến code mới parse không tương thích.
- Nếu thật sự cần **resource thuộc cùng artifact với class plugin**, kiểm soát lookup scope và kiểm chứng URL origin, không chỉ truyền path cho loader có parent.
- Không gộp các config files cùng tên một cách tùy tiện nếu semantics không hỗ trợ merge.

## 10. Child-first class loading không kéo theo child-first resource loading

Class delegation và resource delegation là **hai cơ chế**. Một custom loader có thể override `loadClass` để ưu tiên child cho một class nhưng vẫn kế thừa `getResource` parent-first.

### 10.1. Chương trình: class từ CHILD nhưng resource lại từ PARENT

Lưu `ChildFirstMismatchDemo.java`:

```java
import java.io.*;
import java.lang.reflect.Method;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.Comparator;
import java.util.stream.Stream;
import javax.tools.JavaCompiler;
import javax.tools.ToolProvider;
public class ChildFirstMismatchDemo {
  static void build(Path dir, String text) throws Exception {
    Files.createDirectories(dir.resolve("sample"));
    Path source = dir.resolve("Mode.java");
    Files.writeString(source, "package sample; public class Mode { public static String origin(){ return \"" + text + "\"; }}");
    JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
    if (compiler == null || compiler.run(null,null,null, "-encoding","UTF-8","-d",
        dir.toString(), source.toString()) != 0) throw new AssertionError("compile");
    Files.writeString(dir.resolve("sample/mode.txt"), text, StandardCharsets.UTF_8);
  }
  static String read(URL resource) throws IOException {
    try (InputStream in = resource.openStream()) {
      return new String(in.readAllBytes(), StandardCharsets.UTF_8);
    }
  }
  public static void main(String[] args) throws Exception {
    Path root = Files.createTempDirectory("child-first-demo-");
    try {
      Path parentDir = Files.createDirectory(root.resolve("parent"));
      Path childDir = Files.createDirectory(root.resolve("child"));
      build(parentDir, "PARENT");
      build(childDir, "CHILD");
      try (URLClassLoader parent = new URLClassLoader(
              new URL[]{parentDir.toUri().toURL()}, ClassLoader.getPlatformClassLoader());
           URLClassLoader child = new URLClassLoader(
              new URL[]{childDir.toUri().toURL()}, parent) {
             @Override protected Class<?> loadClass(String name, boolean resolve)
                 throws ClassNotFoundException {
               if (!name.equals("sample.Mode")) return super.loadClass(name, resolve);
               synchronized (getClassLoadingLock(name)) {
                 Class<?> found = findLoadedClass(name);
                 if (found == null) found = findClass(name);
                 if (resolve) resolveClass(found);
                 return found;
               }
             }
           }) {
        Class<?> fromParent = parent.loadClass("sample.Mode");
        Class<?> fromChild = child.loadClass("sample.Mode");
        Method method = fromChild.getMethod("origin");
        System.out.println("child-class=" + method.invoke(null));
        System.out.println("different-classes=" + (fromChild != fromParent));
        System.out.println("resource-from-parent=" + read(
            java.util.Objects.requireNonNull(child.getResource("sample/mode.txt"))));
      }
    } finally {
      try (Stream<Path> paths = Files.walk(root)) {
        for (Path p : paths.sorted(Comparator.reverseOrder()).toList()) Files.deleteIfExists(p);
      }
    }
  }
}
```

```bash
javac -encoding UTF-8 -Xlint:all ChildFirstMismatchDemo.java
java ChildFirstMismatchDemo
```

**stdout đã kiểm thử:**

```text
child-class=CHILD
different-classes=true
resource-from-parent=PARENT
```

### 10.2. Tại sao demo cố tình chỉ override một tên class?

Đây là một **minh họa an toàn trong sandbox**, không phải một loader child-first production-ready. Nó override `loadClass` cho **đúng tên `sample.Mode`**; mọi lớp khác delegate theo default. Nếu override rộng và bỏ qua các ràng buộc JVM, có thể gặp lỗi `java.*` package restriction, duplicate class definition, loader constraints, `LinkageError` và race.

**Không nên copy nguyên loader minh họa rồi dùng để nạp plugin không tin cậy.** Loader production cần bảo vệ namespace shared API, define package đúng, xử lý concurrency, signing/code source khi thích hợp, JPMS, resource search policy và lifecycle.

### 10.3. Quy tắc triển khai

Nếu sản phẩm cần child-first classes, hãy xác định:

1. Những packages nào luôn phải parent-first: `java.*`, shared host APIs, SPI/DTO contracts.
2. Những packages nào được plugin self-define.
3. Resource lookup có theo chính sách tương ứng hay không.
4. Duplicate resources được chọn/merge thế nào.
5. Custom loader có parallel-capable policy và locking đúng không.
6. Modules/classloaders có đang định nghĩa cùng package với runtime restrictions?
7. Nếu reload plugin, refs cũ được giải phóng hay giữ lại?
8. Resource URLs có thể tồn tại khi underlying loader đã close không?
9. Có kiểm tra chính xác origin/version của config không?
10. Có test cast, `ServiceLoader`, reflection và serialized messages qua boundary không?

## 11. Thread context class loader (TCCL) và resource visibility

Trong một container/plugin architecture, thư viện hạ tầng được parent loader định nghĩa nhưng cần tìm implementation/resources của một plugin do child loader sở hữu.

Vấn đề:

```text
Host library chạy bên parent loader
    |
    +-- Parent không thấy plugin.jar trong search path
    |
Thread đang xử lý plugin request:
    |
    +-- TCCL = plugin loader
    |
    +-- Framework lấy Thread.currentThread().getContextClassLoader()
             để tra providers/resources của plugin
```

**TCCL là một reference trên thread**, có thể được thay đổi và được truyền thừa theo lifecycle threads tùy cách tạo/scheduling. Nó **không** biến mọi class/resource request tự động dùng context loader: code nào gọi `getClassLoader` của chính class vẫn dùng defining loader; thư viện chỉ thấy plugin thông qua TCCL nếu **có chủ ý dùng nó**.

### 11.1. Chương trình: resource chỉ có ở plugin loader

Lưu `ContextClassLoaderDemo.java`:

```java
import java.io.*;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
public class ContextClassLoaderDemo {
  public static void main(String[] args) throws Exception {
    Path root = Files.createTempDirectory("context-resource-");
    ClassLoader original = Thread.currentThread().getContextClassLoader();
    try {
      Files.createDirectories(root.resolve("plugins"));
      Files.writeString(root.resolve("plugins/feature.txt"), "plugin-available");
      try (URLClassLoader plugin = new URLClassLoader(
          new URL[]{root.toUri().toURL()}, original)) {
        boolean absentFromApplication =
            ContextClassLoaderDemo.class.getClassLoader().getResource("plugins/feature.txt") == null;
        Thread.currentThread().setContextClassLoader(plugin);
        String loaded;
        try (InputStream in = Thread.currentThread().getContextClassLoader()
            .getResourceAsStream("plugins/feature.txt")) {
          if (in == null) throw new AssertionError("plugin resource missing");
          loaded = new String(in.readAllBytes(), StandardCharsets.UTF_8);
        } finally {
          Thread.currentThread().setContextClassLoader(original);
        }
        System.out.println("app-does-not-see-plugin=" + absentFromApplication);
        System.out.println("context-loads=" + loaded);
        System.out.println("context-restored=" +
            (Thread.currentThread().getContextClassLoader() == original));
      }
    } finally {
      Thread.currentThread().setContextClassLoader(original);
      Files.deleteIfExists(root.resolve("plugins/feature.txt"));
      Files.deleteIfExists(root.resolve("plugins"));
      Files.deleteIfExists(root);
    }
  }
}
```

```bash
javac -encoding UTF-8 -Xlint:all ContextClassLoaderDemo.java
java ContextClassLoaderDemo
```

**stdout đã kiểm thử:**

```text
app-does-not-see-plugin=true
context-loads=plugin-available
context-restored=true
```

**Điểm cần nhớ:** cả program class và plugin resource cùng nằm trong JVM, nhưng **different loader scopes**. Khi TCCL được gán plugin loader, API sử dụng TCCL có thể thấy file; class loader gốc của program vẫn không biết folder plugin.

### 11.2. TCCL trong thread pool

Thread pool **tái sử dụng threads**; nếu application set TCCL cho request A rồi không restore, request B trên cùng worker có thể nhìn nhầm plugin A. Đây là **context leakage**, gây lẫn resources, SPI providers, class loader retention hoặc security confusion.

Pattern đúng:

```java
Thread thread = Thread.currentThread();
ClassLoader before = thread.getContextClassLoader();
try {
    thread.setContextClassLoader(pluginLoader);
    // Chỉ thực hiện đoạn việc được giao dưới plugin context.
} finally {
    thread.setContextClassLoader(before);
}
```

Đây là snippet. `pluginLoader` phải có lifecycle ownership hợp lệ. **Không biến TCCL thành một nơi lưu session data chung**, và không giả định mọi asynchronous completion chạy trên cùng thread như đoạn set ban đầu.

## 12. ServiceLoader: giao thức SPI và context class loader

`java.util.ServiceLoader` là API hiện hành cho service provider discovery. Một convenience overload:

```java
ServiceLoader.load(Greeting.class)
```

tương đương về lựa chọn loader với:

```java
ServiceLoader.load(
    Greeting.class,
    Thread.currentThread().getContextClassLoader())
```

khi dùng classpath/service configuration phù hợp. Đây là lý do TCCL hay xuất hiện trong thư viện hạ tầng: thư viện có thể được parent nạp, nhưng provider nằm trong plugin loader.

### 12.1. Hợp đồng class identity trong SPI

- Interface `Greeting` phải được **host và provider cùng nhìn nhận là một Class object**.
- Provider phải có constructor/cấu hình đúng contract của `ServiceLoader`.
- Trên classpath, service descriptor tại `META-INF/services/<service-binary-name>` liệt kê tên providers.
- Trong named modules, `uses`/`provides ... with ...` là cơ chế module-aware, không nên coi classpath-only file descriptor là toàn bộ câu chuyện.
- `ServiceLoader` có thể lazy instantiate providers và throw `ServiceConfigurationError`; cần error policy và scope/lifetime rõ.
- Không cache một `ServiceLoader` global bất chấp TCCL/module layer thay đổi.

### 12.2. Chương trình: provider độc lập tìm bằng TCCL

Lưu `ServiceContextDemo.java`, có dòng `package`:

```java
package demo.spi;
import java.io.IOException;
import java.net.*;
import java.nio.file.*;
import java.util.*;
import java.util.stream.Stream;
import java.util.Comparator;
import javax.tools.*;
public class ServiceContextDemo {
  public interface Greeting { String hello(); }
  public static void main(String[] args) throws Exception {
    Path root = Files.createTempDirectory("service-loader-demo-");
    ClassLoader original = Thread.currentThread().getContextClassLoader();
    try {
      Path source = root.resolve("HelloProvider.java");
      Files.writeString(source,
          "package providers; public class HelloProvider implements demo.spi.ServiceContextDemo.Greeting " +
          "{ public String hello() { return \"provider-ok\"; } }");
      JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
      if (compiler == null || compiler.run(null, null, null, "-encoding", "UTF-8",
          "-classpath", System.getProperty("java.class.path"), "-d",
          root.toString(), source.toString()) != 0) throw new AssertionError("compile");
      Path services = Files.createDirectories(root.resolve("META-INF/services"));
      Files.writeString(services.resolve(Greeting.class.getName()), "providers.HelloProvider\n");
      try (URLClassLoader plugin = new URLClassLoader(
          new URL[]{root.toUri().toURL()}, ServiceContextDemo.class.getClassLoader())) {
        Thread.currentThread().setContextClassLoader(plugin);
        List<Greeting> providers = new ArrayList<>();
        for (Greeting provider : ServiceLoader.load(Greeting.class)) providers.add(provider);
        System.out.println("service-provider-count=" + providers.size());
        System.out.println("service-message=" + providers.get(0).hello());
        System.out.println("provider-loader-is-plugin=" +
            (providers.get(0).getClass().getClassLoader() == plugin));
        System.out.println("interface-parent-defined=" +
            (providers.get(0) instanceof Greeting));
      }
    } finally {
      Thread.currentThread().setContextClassLoader(original);
      try (Stream<Path> paths = Files.walk(root)) {
        for (Path p : paths.sorted(Comparator.reverseOrder()).toList()) Files.deleteIfExists(p);
      }
    }
  }
}
```

Biên dịch từ thư mục có write permission, không cần external JAR vì provider được biên dịch runtime:

```bash
javac -encoding UTF-8 -Xlint:all -d . ServiceContextDemo.java
java demo.spi.ServiceContextDemo
```

**stdout đã kiểm thử:**

```text
service-provider-count=1
service-message=provider-ok
provider-loader-is-plugin=true
interface-parent-defined=true
```

**Giải thích:** `Greeting` do loader của ứng dụng định nghĩa. Plugin class `providers.HelloProvider` được compiled vào thư mục tạm, và service descriptor chỉ chứa tên provider. `ServiceLoader.load(Greeting.class)` dùng TCCL đang trỏ plugin loader, tìm ra provider, nhưng provider implement đúng `Greeting` của parent, nên cast/instanceof hợp lệ.

### 12.3. Lỗi khi copy interface vào plugin

Nếu plugin còn chứa một bản `demo.spi.ServiceContextDemo$Greeting` và custom loader **child-first** cả package API, provider có thể implement “Greeting của plugin” thay vì “Greeting của host”. Kết quả: `ServiceLoader` có thể báo provider **not a subtype** hoặc ứng dụng không cast được. Giải pháp không phải bật reflection để “ép cast”; **xác định shared API loader/JPMS boundary đúng**.

## 13. Class.forName và hậu quả của initialization

`Class.forName(name,true,loader)` load/link/initialize theo contract; khi `initialize=false`, đó **không** phải lời bảo đảm initializer không bao giờ chạy về sau.

### 13.1. Chương trình: khác biệt false và true

Lưu `ClassInitializationDemo.java`:

```java
public class ClassInitializationDemo {
  private static int initialized = 0;
  static final class Probe {
    static { initialized++; }
    static String message() { return "ready"; }
  }
  public static void main(String[] args) throws Exception {
    String name = ClassInitializationDemo.class.getName() + "$Probe";
    ClassLoader loader = ClassInitializationDemo.class.getClassLoader();
    Class<?> withoutInit = Class.forName(name, false, loader);
    boolean stillZero = initialized == 0;
    Class<?> withInit = Class.forName(name, true, loader);
    boolean exactlyOne = initialized == 1;
    Class.forName(name, true, loader);
    System.out.println("load-without-init=" + stillZero);
    System.out.println("initialized-on-true=" + exactlyOne);
    System.out.println("no-repeat-initialize=" + (initialized == 1));
    System.out.println("same-class-object=" + (withoutInit == withInit));
  }
}
```

```bash
javac -encoding UTF-8 -Xlint:all ClassInitializationDemo.java
java ClassInitializationDemo
```

**stdout đã kiểm thử:**

```text
load-without-init=true
initialized-on-true=true
no-repeat-initialize=true
same-class-object=true
```

**Cần nhớ:** initialization một lần cho cùng runtime Class theo rules JVM. Nạp class **bằng một defining loader khác** tạo một runtime Class khác; lần initialization của class phiên bản đó có thể xảy ra riêng. Không dùng class initialization như một “global singleton duy nhất trong toàn JVM” nếu app có nhiều loaders.

### 13.2. Nếu tên class đến từ input

Nếu hệ thống cho user truyền tên class tùy ý rồi gọi `Class.forName(name,true,loader)`, họ có thể kích hoạt static initialization của code đã có trên classpath, gây side effects không mong muốn. **Dùng allowlist, package policy, verification và trust boundary**; không coi khả năng nạp class là authorization.

## 14. ClassNotFoundException khác NoClassDefFoundError

Hai loại lỗi thường bị trộn:

- `ClassNotFoundException`: một thao tác tìm class theo tên như `loadClass`/`Class.forName` không tìm được class yêu cầu.
- `NoClassDefFoundError`: JVM đã cố sử dụng/resolve một definition tham chiếu nhưng class dependency không tìm thấy hoặc không thể định nghĩa lúc cần; đây là một `LinkageError`, không phải checked exception.
- `ExceptionInInitializerError`: class initialization thất bại vì exception trong static initializer.
- `UnsupportedClassVersionError`: bytecode version không được JDK runtime hỗ trợ.
- `ClassCastException`: class identity/type mismatch khi cast.
- `ServiceConfigurationError`: SPI provider configuration/loading thất bại; có thể do identity mismatch.
- `SecurityException` hoặc access errors: loại khác tùy API và policy.

**Không catch `ClassNotFoundException` rồi mặc định coi mọi failure của plugin là “file JAR bị thiếu”**. Lỗi thật có thể xuất hiện khi một dependency được resolve ở thời điểm invocation.

### 14.1. Chương trình: Dependent tồn tại nhưng dependency biến mất

Lưu `MissingDependencyDemo.java`:

```java
import java.io.IOException;
import java.lang.reflect.InvocationTargetException;
import java.net.*;
import java.nio.file.*;
import java.util.Comparator;
import java.util.stream.Stream;
import javax.tools.*;
public class MissingDependencyDemo {
  public static void main(String[] args) throws Exception {
    Path root = Files.createTempDirectory("missing-dependency-");
    try {
      Path dependent = root.resolve("Dependent.java");
      Path requirement = root.resolve("Requirement.java");
      Files.writeString(requirement,
          "package tests; public class Requirement { public static String read(){return \"ok\";} }");
      Files.writeString(dependent,
          "package tests; public class Dependent { public static String read(){return Requirement.read();} }");
      JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
      if (compiler == null || compiler.run(null,null,null,"-encoding","UTF-8","-d",
          root.toString(),requirement.toString(),dependent.toString()) != 0)
        throw new AssertionError("compile");
      Files.delete(root.resolve("tests/Requirement.class"));
      try (URLClassLoader loader = new URLClassLoader(
          new URL[]{root.toUri().toURL()}, ClassLoader.getPlatformClassLoader())) {
        boolean notFound = false, linkage = false;
        try { loader.loadClass("tests.Unknown"); }
        catch (ClassNotFoundException ex) { notFound = true; }
        Class<?> resolved = loader.loadClass("tests.Dependent");
        try { resolved.getMethod("read").invoke(null); }
        catch (InvocationTargetException ex) {
          linkage = ex.getCause() instanceof NoClassDefFoundError;
        }
        System.out.println("missing-class-not-found=" + notFound);
        System.out.println("missing-runtime-dependency=" + linkage);
        System.out.println("dependent-defined=" + (resolved.getClassLoader() == loader));
      }
    } finally {
      try (Stream<Path> paths = Files.walk(root)) {
        for (Path p : paths.sorted(Comparator.reverseOrder()).toList()) Files.deleteIfExists(p);
      }
    }
  }
}
```

```bash
javac -encoding UTF-8 -Xlint:all MissingDependencyDemo.java
java MissingDependencyDemo
```

**stdout đã kiểm thử:**

```text
missing-class-not-found=true
missing-runtime-dependency=true
dependent-defined=true
```

**Giải thích:**

1. JDK compiler tạo `tests.Requirement` và `tests.Dependent`.
2. Demo xóa file `Requirement.class` **trong thư mục tạm**, không xóa source/project file.
3. `loader.loadClass("tests.Unknown")` báo `ClassNotFoundException`: class được yêu cầu theo tên không tồn tại.
4. `tests.Dependent` vẫn được load.
5. Lúc gọi `Dependent.read()`, JVM cần `Requirement` nhưng không còn binary representation. Error gốc `NoClassDefFoundError` được reflection bọc trong `InvocationTargetException`.
6. Đây là lỗi dependency/runtime linkage, **không phải một lỗi truy cập resource path thông thường**.

### 14.2. Cách khắc phục

- Kiểm tra dependency graph và class loader visibility, không chỉ top-level JAR.
- So binary versions và chỗ shared APIs được định nghĩa.
- Với `ServiceLoader`, kiểm tra provider subtype identity và service descriptor.
- Đừng sửa bằng cách copy trùng API JAR vào mọi plugin khi class identity là nguyên nhân.
- Không ẩn lỗi bằng `catch(Throwable ignored)` rồi cố dùng plugin ở trạng thái không xác định.

## 15. JPMS: tài nguyên trong named modules có thể bị encapsulate

Từ Java 9, module boundaries tạo một mức quy tắc mới. **Resource path tồn tại** không bảo đảm mọi loader/caller đều tìm được nó.

Các API cần phân biệt:

- `ClassLoader.getResource(name)` / `getResources(name)`: với named modules, API có giới hạn rất chặt: non-`.class` resource trong package của named module thường chỉ discover được khi package **open unconditionally**.
- `Class.getResourceAsStream(name)` trên một class thuộc named module: truy xuất module resource theo caller và **module encapsulation**.
- `Module.getResourceAsStream(name)`: đọc resource của module được chọn, xét package có **open tới caller module** hay không; resource `.class` có ngoại lệ quan trọng.
- `exports` public API packages **không giống** `opens` package cho deep resource/reflection access.

**Không kết luận** “nếu `ClassLoader.getResource` trả null thì file chắc chắn không được đóng gói”. Nó còn có thể bị module encapsulation, loader scope hoặc custom lookup policy chặn.

### 15.1. Resource thuộc package và module boundary

Với module `example.library` có resource `com/example/lib/config.properties` trong package `com.example.lib`:

```java
module example.library {
    exports com.example.lib.api;
    opens com.example.lib to example.app;
}
```

Đây là **snippet module-info.java**, không phải chương trình độc lập; yêu cầu module `example.app` tồn tại và được khai báo đúng. `opens` có chủ ý cho phép module app deep resource/reflection access theo rules. `ClassLoader.getResource` còn có yêu cầu **open unconditionally** cho non-class resources nằm trong named module package, do vậy *qualified opens* không tự làm mọi classloader-wide resource lookup nhìn thấy resource.

Đây là khác biệt dễ bỏ qua nếu bạn chỉ thử classpath/unnamed module.

### 15.2. Chương trình: `java.base` exports `java.lang` nhưng không opens package này

Lưu `ModuleResourceDemo.java`:

```java
import java.io.*;
public class ModuleResourceDemo {
  public static void main(String[] args) throws Exception {
    Module core = String.class.getModule();
    Module caller = ModuleResourceDemo.class.getModule();
    boolean classVisible;
    try (InputStream in = core.getResourceAsStream("java/lang/String.class")) {
      classVisible = in != null;
    }
    System.out.println("java-base-named=" + core.isNamed());
    System.out.println("java-lang-exported=" + core.isExported("java.lang", caller));
    System.out.println("java-lang-not-open=" + !core.isOpen("java.lang", caller));
    System.out.println("class-resource-visible=" + classVisible);
    System.out.println("app-unnamed-module=" + !caller.isNamed());
  }
}
```

```bash
javac -encoding UTF-8 -Xlint:all ModuleResourceDemo.java
java ModuleResourceDemo
```

**stdout đã kiểm thử với Java 17 classpath mặc định, không dùng `--add-opens`:**

```text
java-base-named=true
java-lang-exported=true
java-lang-not-open=true
class-resource-visible=true
app-unnamed-module=true
```

Tại sao `String.class` có thể đọc dù `java.lang` không opened? Với `Module.getResourceAsStream`, resource name kết thúc bằng `.class` là **trường hợp đặc biệt không bị encapsulate** theo quy tắc resource. Điều này **không** có nghĩa đã có quyền thực thi arbitrary code hay đọc mọi private resources trong `java.base`.

**Không hard-code** output về opens nếu JVM được chạy với module-opening flags. Những flags đó có thể thay đổi kết quả. Bài dùng default JVM configuration đã kiểm thử.

### 15.3. META-INF/services là trường hợp đặc thù

Trong classpath, `META-INF/services/com.example.Plugin` là một file descriptor, không phải một Java package hợp lệ để suy ra kiểu package export thông thường. Service provider discovery của named modules còn dựa vào `provides`/`uses` trong `module-info.java`. Không tùy tiện áp dụng rules của `ClassLoader.getResource` cho mọi service discovery mode của `ServiceLoader`.

## 16. URLClassLoader và JAR resources

`URLClassLoader` có thể tìm class/resource từ một thư mục hoặc JAR trên `URL[]`. Đối với resource từ JAR, `URL` thường có protocol `jar`; không được xem nó như file OS có path trùng resource name.

### 16.1. Chương trình: tạo JAR nhỏ, đọc resource và đóng đúng cách

Lưu `JarResourceDemo.java`:

```java
import java.io.*;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.jar.*;
public class JarResourceDemo {
  public static void main(String[] args) throws Exception {
    Path dir = Files.createTempDirectory("jar-resource-fixed-");
    Path jar = dir.resolve("demo.jar");
    try {
      try (JarOutputStream out = new JarOutputStream(Files.newOutputStream(jar))) {
        out.putNextEntry(new JarEntry("config/app.txt"));
        out.write("jar-data".getBytes(StandardCharsets.UTF_8));
        out.closeEntry();
      }
      try (URLClassLoader loader = new URLClassLoader(
          new URL[]{jar.toUri().toURL()}, null)) {
        URL resource = loader.getResource("config/app.txt");
        if (resource == null) throw new AssertionError("missing JAR resource");
        String data;
        try (InputStream in = loader.getResourceAsStream("config/app.txt")) {
          if (in == null) throw new AssertionError("missing stream");
          data = new String(in.readAllBytes(), StandardCharsets.UTF_8);
        }
        System.out.println("resource-protocol=" + resource.getProtocol());
        System.out.println("resource-text=" + data);
        System.out.println("missing-jar-resource=" + (loader.getResource("config/nope.txt") == null));
      }
    } finally {
      Files.deleteIfExists(jar);
      Files.deleteIfExists(dir);
    }
  }
}
```

```bash
javac -encoding UTF-8 -Xlint:all JarResourceDemo.java
java JarResourceDemo
```

**stdout đã kiểm thử:**

```text
resource-protocol=jar
resource-text=jar-data
missing-jar-resource=true
```

**Giải thích:**

- `JarOutputStream` chỉ tạo JAR nhỏ chứa `config/app.txt` trong thư mục tạm.
- `URLClassLoader` cung cấp resource qua URL protocol `jar`.
- Code dùng `loader.getResourceAsStream` và try-with-resources để đọc.
- `URLClassLoader.close()` đóng các file handles/JAR files mà loader quản lý, cho phép xóa JAR trong thử nghiệm trên Windows.

### 16.2. Một bẫy thực tế: URL.openStream và cache của JarURLConnection

`URL.openStream()` trên `jar:` URL có thể tương tác với `JarURLConnection` và **caching** ở mức URL handler. Trong một số tình huống, stream đã đóng nhưng **JAR file vẫn bị giữ mở bởi cache**, khiến Windows không cho xóa JAR ngay cả khi `URLClassLoader` đã close.

Khi đọc resource của URLClassLoader và muốn loader kiểm soát lifecycle, ưu tiên `loader.getResourceAsStream(name)` và close stream/loader. Nếu code cần dùng `URLConnection` trực tiếp, cân nhắc `setUseCaches(false)` trước khi mở stream trong ngữ cảnh có hot reload/delete, nhưng test theo JDK/container cụ thể. **Không coi `close()` là cơ chế ép mọi URL ngoài loader lập tức mất file handles.**

### 16.3. Multi-release JARs

Java hỗ trợ multi-release JAR cho bytecode/version-specific entries. Khi đóng gói resources/classes theo release, đừng tự giả định mọi `java -jar`/custom loader luôn chọn cùng path version mà không xem metadata JAR và runtime behavior. Với plugin có resource/schema theo version, test chính JDK/version và packaging strategy đang dùng.

## 17. Đóng loader không đồng nghĩa “unload” ngay classes đã định nghĩa

`URLClassLoader.close()` ngăn một số thao tác nạp thêm và giải phóng resources như JAR handles, nhưng **không xóa ngay Class objects đã được load**. Các class đã nạp vẫn có thể được dùng khi còn references và dependencies thích hợp.

### 17.1. Chương trình: class vẫn dùng được sau close()

Lưu `CloseLoaderDemo.java`:

```java
import java.io.IOException;
import java.net.*;
import java.nio.file.*;
import java.util.Comparator;
import java.util.stream.Stream;
import javax.tools.*;
public class CloseLoaderDemo {
  public static void main(String[] args) throws Exception {
    Path root = Files.createTempDirectory("close-loader-");
    try {
      Path source = root.resolve("Alive.java");
      Files.writeString(source,
          "package isolated; public class Alive { public static String ping(){return \"still-running\";} }");
      JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
      if (compiler == null || compiler.run(null,null,null,"-d",root.toString(),
          source.toString()) != 0) throw new AssertionError("compile");
      URLClassLoader loader = new URLClassLoader(
          new URL[]{root.toUri().toURL()}, ClassLoader.getPlatformClassLoader());
      Class<?> loaded;
      try { loaded = loader.loadClass("isolated.Alive"); }
      finally { loader.close(); }
      String ping = (String) loaded.getMethod("ping").invoke(null);
      System.out.println("closed-loader-reference-retained=" + (loaded.getClassLoader() == loader));
      System.out.println("previously-loaded-class-callable=" + ping);
    } finally {
      try (Stream<Path> paths = Files.walk(root)) {
        for (Path p : paths.sorted(Comparator.reverseOrder()).toList()) Files.deleteIfExists(p);
      }
    }
  }
}
```

```bash
javac -encoding UTF-8 -Xlint:all CloseLoaderDemo.java
java CloseLoaderDemo
```

**stdout đã kiểm thử:**

```text
closed-loader-reference-retained=true
previously-loaded-class-callable=still-running
```

**Không suy luận:** khi loader close xong, tất cả methods đã loaded phải thất bại. Handle/Class/objects vẫn có thể sống. Để unload được một plugin:

- Dừng tác vụ và threads của plugin.
- Khôi phục TCCL.
- Đóng resource streams/JAR/loader.
- Xóa references từ registries, static caches, thread locals, scheduled callbacks.
- Giải phóng class objects, instances và method handles đang được host giữ.
- Dùng công cụ GC/classloader metrics để **quan sát**, không coi `System.gc()` là lệnh bảo đảm unload.
- Đừng giữ strong references tới plugin classloader trong `ServiceLoader` hoặc host-level caches mãi mãi.

### 17.2. Vì sao hot reload hay rò bộ nhớ?

Mỗi lần reload có thể tạo một defining loader mới, từ đó tạo class identities mới. Nếu cache của host vẫn giữ instance/class từ loader cũ, loader cũ không được thu gom, class metadata và plugin data có thể tích lũy. Chúng ta cần quản lý lifecycle, không chỉ gọi `close()`.

## 18. Resource name không phải path do user tùy ý chỉ định

`ClassLoader.getResourceAsStream(name)` nhận một resource path trong namespace của loader, không phải một policy bảo mật. Nếu bạn nối trực tiếp input của user vào path mà không kiểm tra, người dùng có thể yêu cầu tài nguyên ngoài danh sách được phép — tùy loader và layout.

Một policy an toàn hơn:

1. **Allowlist** resource identifiers hợp lệ, không nhận một path bất kỳ.
2. Chuẩn hóa/investigate tên, không cho `../` hoặc path separators nếu API chỉ cho simple identifiers.
3. Không chấp nhận user-controlled JAR URLs hoặc directories mà không có trust policy.
4. Áp giới hạn kích thước resource trước khi `readAllBytes()` trong hệ thống sản phẩm.
5. Parse dữ liệu như untrusted input; với XML/JSON/YAML áp dụng parser security configurations tương ứng.
6. Đừng lấy resource tồn tại làm bằng chứng caller có quyền access business secret.
7. Không dùng class loader để chạy bytecode không tin cậy trong cùng JVM rồi gọi đó là sandbox.

### 18.1. Chương trình: validate resource identifier trước khi ghép

Lưu `ResourceNameGuardDemo.java`:

```java
public class ResourceNameGuardDemo {
  static String approvedName(String userProvided) {
    if (!userProvided.matches("[A-Za-z0-9_-]{1,32}\\.properties"))
      throw new IllegalArgumentException("invalid resource identifier");
    return "profiles/" + userProvided;
  }
  public static void main(String[] args) {
    String safe = approvedName("default.properties");
    int blocked = 0;
    for (String input : new String[]{"../secret.txt", "/etc/passwd", "nested/route.properties",
        "bad:name.properties", "longname.properties/"}) {
      try { approvedName(input); } catch (IllegalArgumentException ex) { blocked++; }
    }
    System.out.println("safe-resource-path=" + safe);
    System.out.println("blocked-names=" + blocked);
    System.out.println("name-validation-not-a-sandbox=true");
  }
}
```

```bash
javac -encoding UTF-8 -Xlint:all ResourceNameGuardDemo.java
java ResourceNameGuardDemo
```

**stdout đã kiểm thử:**

```text
safe-resource-path=profiles/default.properties
blocked-names=5
name-validation-not-a-sandbox=true
```

Regex trong demo áp chính sách **tên cố định kết thúc bằng `.properties`**, không cho dấu slash hoặc dot-dot path. Đây là một lớp validation, **không có tác dụng cô lập bytecode**. Nếu resource chứa secrets thì secrets vẫn cần ACL, encryption hoặc separate process/storage boundary.

## 19. Thiết kế plugin thực tế và nguyên tắc nạp lớp an toàn

Một thiết kế nên có:

```text
                         HOST
              Shared service interface/API
                       + DTO contract
                            |
                   Parent class loader
                            |
           +----------------+---------------+
           |                                |
    Plugin loader A                  Plugin loader B
    Implementation A                 Implementation B
    Private dependencies             Private dependencies
    Plugin resources                 Plugin resources
           |                                |
           +--------------+-----------------+
                          |
           Host only uses shared SPI API
           No arbitrary plugin-to-plugin cast
```

### 19.1. Shared API phải do ai định nghĩa?

Chọn một authority rõ ràng:

- Host classloader hoặc shared module định nghĩa service interface.
- Plugins **delegate** tới authority đó khi load interface/API contracts.
- Plugins có thể giữ implementation/dependencies riêng nếu policy cho phép.
- Tránh duplicate resources/classes gây shadowing ở đúng paths của API.
- Host xác minh subtype bằng `isAssignableFrom` hoặc `ServiceLoader`, không so class names thuần túy.
- Với modules, đọc `requires`/`exports`/`opens`, không mặc nhiên mọi classloader có quyền thấy mọi provider.

### 19.2. Khi nào cần custom class loader?

Chỉ khi yêu cầu thực sự gồm plugin isolation, multiple versions, dynamic code generation, in-memory definitions hoặc reload. Nếu ứng dụng nhỏ không có những nhu cầu này, classpath/module path với build dependency graph rõ ràng thường đáng tin hơn.

### 19.3. An toàn không đồng nghĩa “bất kỳ plugin nào cũng có thể chạy trong cùng JVM”

Class loader boundaries giúp **class namespace isolation**, không phải một security boundary hoàn chỉnh. Java không còn coi `SecurityManager` là lựa chọn tiêu chuẩn để sandbox ứng dụng mới. Nếu code là **không tin cậy**, ưu tiên tách process/container và cấp phép OS/network/filesystem rõ, ký/verifying artifacts và supply-chain policy.

## 20. Các vấn đề cấu hình resource trong ứng dụng thực

### 20.1. Classpath và working directory

`ClassLoader.getResource("app/config.properties")` tìm trong resource roots của loader, **không tự tìm** `./app/config.properties` dưới working directory. Nếu file là configuration bên ngoài JAR và do operator thay đổi, nên có **external config path** rõ, dùng `Files.newInputStream`/`Path` với quyền OS thích hợp, không lẫn với packaged resources.

### 20.2. Absolute resource path không có nghĩa filesystem absolute

Trong `MyClass.class.getResource("/config/app.properties")`, dấu `/` là **root resource namespace**, không phải root directory của ổ đĩa. Trên Windows/Linux, API vẫn dùng `/` làm separator.

### 20.3. Khi resource không tồn tại hoặc bị module encapsulation

`getResourceAsStream` trả null cho cả tình huống không tìm được **và** có thể khi bị từ chối access. Thay vì đoán “file bị mất”, kiểm:

- Có đúng resource path/name casing không?
- Build có copy resources vào JAR/module output không?
- Anchor class có ở package bạn tưởng không?
- Loader nào thực hiện resource lookup?
- Có resource trùng tên ở parent không?
- Có named module và `opens`/resource encapsulation không?
- URLClassLoader đã bị đóng trước khi mở resource không?
- Có security restrictions/custom loader implementation không?
- Dữ liệu đến từ bản JAR/version nào?

### 20.4. Khi đi từ IDE sang packaged JAR

Một resource có thể chạy trong IDE do IDE đưa `src/main/resources` vào classpath. Khi build JAR, nó chỉ chạy nếu build thực sự đóng gói resource tại đúng path. **Đừng dựa vào đường dẫn source-tree** trong production; dùng `getResourceAsStream` và kiểm artifact output.

## 21. Phân biệt class resource và artifact provenance

`URLClassLoader.getResource` có thể trả `file:` hoặc `jar:` URL, nhưng URL này **không phải chữ ký tin cậy của code**.

Nếu plugin lấy từ một kho dữ liệu không tin cậy, ứng dụng cần:

- Verify artifact digest/signature theo policy trước khi load.
- Áp exact version constraints của host-plugin contract.
- Kiểm các dependencies và transitive dependencies.
- Tránh load một file JAR đang được ghi dở hoặc tự động thay đổi.
- Có staging/atomic publish để không nạp binary corrupt.
- Không tin resource content chỉ vì nó nằm trong cùng package với một class.
- Pin code source và audit artifact provenance khi có yêu cầu.
- Chạy unknown plugins trong isolated process nếu threat model cần.

**Cùng package name không bảo đảm cùng runtime package**: JVM xem package identity theo package name **và defining loader**. Modules thêm các ràng buộc package placement; package-private access không xuyên qua hai loaders chỉ vì chuỗi package text giống nhau.

## 22. Một số vấn đề liên quan đến class loader và native/JVM state

- **Static fields:** một class được hai loaders định nghĩa có **static state riêng** theo runtime Class. Đừng hiểu static singleton là một singleton toàn JVM.
- **Class literals:** `Widget.class` trong bytecode của plugin được resolve theo loader constraints của code đó. Nó không tự là Widget của host.
- **Arrays:** array class identity còn liên quan component type; các arrays của hai component classes khác defining loaders không tự assignable.
- **Reflection/MethodHandles:** cần đúng `Class<?>` object; lookup quyền Java access còn phụ thuộc module visibility.
- **ServiceLoader:** service interface must be the shared parent-defined type; provider loader có thể khác.
- **Serialization:** deserializing một binary class name cần resolver loader và compatibility policy rõ; không nhận arbitrary serialized objects từ untrusted source.
- **Thread context:** worker threads có thể giữ TCCL của plugin cũ và gây retention leak.
- **Native libraries:** nạp native libraries có lifecycle/linking constraints riêng, không nên copy một JNI binary vào nhiều loaders rồi dự đoán nó độc lập.
- **GC/unloading:** không bảo đảm immediate class unloading khi close loader; chỉ có thể quan sát khi không còn strong refs và JVM quyết định GC.
- **Hot reload:** update JAR trên disk không thay thế **đã định nghĩa** Class objects; thường cần loader mới và chuyển ownership.

## 23. Phân tích ba lỗi thực tế

### 23.1. ClassCastException với cùng tên class

**Triệu chứng:** hai class names giống nhau trong exception message.

**Điều tra:**

```java
System.out.println(first.getClass().getName());
System.out.println(first.getClass().getClassLoader());
System.out.println(second.getClass().getName());
System.out.println(second.getClass().getClassLoader());
```

Đây là snippet trong ngữ cảnh có `first`/`second`. Kết luận phải dựa vào **Class identity và defining loader**, không đoán chỉ từ class name. Kiểm xem shared interface/DTO có bị plugin đóng gói trùng vào JAR không.

### 23.2. getResourceAsStream trả null dù JAR chứa file

**Triệu chứng:** kiểm JAR thấy file `config/app.properties`, app vẫn nhận null.

**Điều tra:** xác nhận caller dùng `Class` hay `ClassLoader`; có leading slash không; JAR có nằm trong loader URLs không; có parent resource shadow; module resource encapsulation; TCCL có phải plugin loader không; plugin đã close chưa.

**Khắc phục:** chọn anchor/loader phù hợp, path root đúng, module opens khi có chủ ý, build packaging đúng; không mở cả JDK modules vô tội vạ.

### 23.3. Hot reload plugin nhưng hành vi vẫn từ version cũ

**Triệu chứng:** reload JAR mới, class name giống cũ nhưng method vẫn xuất hiện hành vi cũ hoặc cached resource cũ.

**Điều tra:** code có còn giữ `Class<?>`, `MethodHandle` hoặc instance từ loader cũ? TCCL còn trỏ loader cũ? URL connection cache giữ JAR file? Provider cache/registry còn tham chiếu plugin cũ? Resource search đang lấy parent copy?

**Khắc phục:** dùng lifecycle rõ, stop plugin tasks, detach registries/TCCL, close URLClassLoader, release references rồi tạo loader mới; không yêu cầu JVM tự redefine một class thông thường từ file đã thay đổi.

## 24. Lỗi thường gặp và cách sửa

| Anti-pattern | Vì sao sai | Cách đúng |
| --- | --- | --- |
| So class identity chỉ qua `getName()` | Bỏ qua defining loader | So `Class<?>`, `isAssignableFrom` và SPI |
| Thấy cùng bytecode, suy cast được | Defining loaders khác nhau tạo types khác | Chia sẻ loader cho contract types |
| Tin `child.loadClass` tức child tự định nghĩa | Delegation có thể cho parent define | Kiểm `Class.getClassLoader` |
| Dùng child-first cho cả shared API | Hai bản SPI/DTO không cast được | Parent-first/consistent shared API |
| Custom child-first `loadClass` nhưng quên `getResource` | Có thể class CHILD, resource PARENT | Thiết kế cả hai lookup policies |
| Gọi `ClassLoader.getResource("/x")` | Leading slash không được xử lý như Class API | Tên root path không có `/` đầu |
| Gọi `MyClass.class.getResource("x")` rồi tưởng ở root | Class API tự prefix package | Dùng `"/x"` nếu muốn root |
| Coi resource URL luôn là `file:` | JAR/JRT/custom schemes | Dùng stream/URL.openConnection đúng cách |
| Không close InputStream | JAR/file handles có thể bị giữ | try-with-resources |
| Không close URLClassLoader | Leak resource handles | Close theo lifecycle |
| Close loader rồi chờ class unload ngay | Class objects/instances còn refs | Stop tasks, release refs, observe GC |
| Không restore TCCL | Thread pool context leakage | finally restore old TCCL |
| Cache `ServiceLoader` JVM-wide | TCCL/module layer thay đổi | Cache theo plugin context/lifecycle |
| Nhét shared interface vào mọi plugin | Type identity split | Host-defined SPI |
| Gọi `Class.forName` với arbitrary input | Có thể kích hoạt initialization | Allowlist + trust boundary |
| Catch `ClassNotFoundException` cho mọi linkage | `NoClassDefFoundError` là Error | Phân loại lỗi đúng nguyên nhân |
| Mặc định `getResourceAsStream` null nghĩa file vắng | Module encapsulation/loader mismatch | Kiểm module/loader/path |
| Chỉ dựa `exports` để đọc non-class resources | Qualified opens/resource rules khác | `Module.getResourceAsStream` và opens policy |
| Mở `--add-opens` mọi package | Gia tăng access, che thiết kế sai | Qualified opens/public APIs |
| Dùng custom class loader làm sandbox | Namespace không phải security boundary | Process/OS isolation cho untrusted bytecode |
| Dùng bytecode/JAR từ URL chưa được verify | Supply chain/code execution risk | Verify artifacts, allowlist origins |
| Không giới hạn resource size | Memory abuse qua `readAllBytes` | Streaming + quotas |
| Dùng `ClassLoader` làm arbitrary file browser | Có thể lộ packaged resources | Resource allowlist |
| Dùng default charset | Kết quả khác OS | `UTF_8` |
| Dùng static singleton như global across loaders | Class copies có static state riêng | Host-owned shared singleton |
| Dùng `System.gc()` để ép unload | GC không bảo đảm như vậy | Detach refs, monitor metrics |
| So class names trong log mà không log loader | Khó debug same-name types | Log loader identity an toàn |
| Suy tài nguyên theo class binary name là file cùng JAR | Delegation có thể khác | Kiểm URL origin, package resource policy |

## 25. Checklist code review cho nạp lớp và tài nguyên

1. Class nào định nghĩa shared interfaces/DTOs giữa host và plugins?
2. Có tránh duplicate shared API JARs trong plugin loaders không?
3. Có biết **binary name + defining loader** quyết định runtime identity không?
4. Có phân biệt **initiating** với **defining** loader không?
5. Có xác minh `Class.getClassLoader()` thay vì đoán từ đối tượng gọi `loadClass` không?
6. Delegation policy parent-first/child-first có được document rõ không?
7. Nếu child-first, resources có được kiểm tra consistency riêng không?
8. Class loading có thể kích hoạt static initializer lúc nào?
9. Có tránh `Class.forName(name,true,loader)` từ untrusted names không?
10. Khi reload, có thực sự dùng loader mới và release mọi refs loader cũ không?
11. URLClassLoader có được close theo lifecycle không?
12. Resource streams có được đóng không?
13. JAR URLs có bị cache khiến file handles còn sống trên Windows không?
14. Resource path có đúng dấu `/` theo Class-vs-ClassLoader API không?
15. Resource có được đóng gói vào deployment artifact đúng thư mục không?
16. Có phân biệt classpath resources với filesystem external config không?
17. Có xử lý `null` khi resource không tồn tại hay không truy cập được không?
18. Resource bytes có được decode bằng charset rõ và kiểm size/format không?
19. Có nhiều resources trùng tên trong parent/child/JARs không?
20. Có tránh giả định search order giữa các named modules không?
21. Nếu dùng JPMS, `exports`/`opens`/caller module đã đúng chưa?
22. Nếu dùng `Module.getResourceAsStream`, có hiểu encapsulation của resource không?
23. Nếu dùng ServiceLoader, service type có cùng Class identity ở parent không?
24. Service descriptor có đúng binary name của interface/provider không?
25. TCCL được set trong scope hẹp và restore bằng finally không?
26. Có tránh cache `ServiceLoader`/Class objects vượt plugin lifetime không?
27. Có phân biệt `ClassNotFoundException`/`NoClassDefFoundError`/`ClassCastException` không?
28. Có kiểm tra dependency graph và loader constraints khi linkage thất bại không?
29. Có không chạy bytecode không tin cậy chỉ vì custom loader “cô lập” không?
30. Có verify plugin JAR integrity/signatures, version policy và provenance không?
31. Có test trên Windows khi cần xóa/reload JAR không?
32. Có test packaged JAR và named module chứ không chỉ IDE classpath không?
33. Có metrics cho số loader/class, heap/metaspace, file handles và TCCL không?
34. Có tránh mở JDK internals với flags tùy tiện không?
35. Có áp dụng Java 17+ public APIs hiện hành theo Special Note không?

## 26. Bài tập thực hành

**Bài 1 — Loader hierarchy.** Chạy `LoaderHierarchyDemo`, in thêm loader của một class từ platform module. Giải thích tại sao bootstrap thường hiển thị null.

**Bài 2 — Initiating vs defining.** Chạy `InitiatingVsDefiningDemo`, thêm một `URLClassLoader` con nữa và kiểm class vẫn do parent định nghĩa.

**Bài 3 — Same name, different class.** Chạy `ClassIdentityDemo`; nêu đầy đủ cặp (binary name, defining loader) của từng Widget.

**Bài 4 — isAssignableFrom.** Thêm `one.isAssignableFrom(two)` vào demo identity; vì sao không cast được dù tên class giống nhau?

**Bài 5 — Parent-first.** Chạy `ParentFirstResourceDemo` và giải thích vì sao `getResource` trả PARENT.

**Bài 6 — Multiple resources.** Dùng `getResources("config/mode.txt")`, đọc cả hai nội dung và lý giải khi nào nên cho phép merge.

**Bài 7 — Class vs ClassLoader resource name.** Chạy `ResourceNamesDemo` và thay đổi các tên có/không có `/` đầu; ghi kết quả.

**Bài 8 — Resource bytes/charset.** Chạy `ResourceStreamDemo` với nội dung UTF-8 tiếng Việt, đọc lại qua `StandardCharsets.UTF_8`.

**Bài 9 — Missing resource.** Thay path bằng file không tồn tại và xử lý `null` thành một thông báo có đường dẫn an toàn.

**Bài 10 — Child-first mismatch.** Chạy `ChildFirstMismatchDemo`, xác nhận class CHILD và resource PARENT. Nêu thay đổi policy nào phải được kiểm thử.

**Bài 11 — TCCL.** Chạy `ContextClassLoaderDemo`; cố bỏ `finally` trong sandbox để hiểu context leakage (sau đó khôi phục ngay).

**Bài 12 — ServiceLoader.** Chạy `ServiceContextDemo`, thêm một provider và kiểm thứ tự/identity mà không phụ thuộc provider object string.

**Bài 13 — Initialization.** Chạy `ClassInitializationDemo`, thử thêm method call của Probe và xác định khi nào static block chạy.

**Bài 14 — Missing dependency.** Chạy `MissingDependencyDemo`, phân biệt `ClassNotFoundException` và `NoClassDefFoundError`.

**Bài 15 — Module resource.** Chạy `ModuleResourceDemo` trên classpath và một named-module test, giải thích `exports`/`opens` và exception của `.class`.

**Bài 16 — JAR URL.** Chạy `JarResourceDemo`; vì sao URL là `jar:` nhưng không phải `File` tương ứng với `config/app.txt`?

**Bài 17 — Loader close.** Chạy `CloseLoaderDemo`; giải thích tại sao class vẫn callable sau close, và liệt kê refs giữ loader sống.

**Bài 18 — Resource allowlist.** Chạy `ResourceNameGuardDemo`, cho thêm case sai và mở rộng chính sách một cách có kiểm soát.

**Bài 19 — Plugin SPI boundary.** Thiết kế host/plugin contract trong đó interface do parent định nghĩa còn implementation do child định nghĩa; viết integration test `instanceof`.

**Bài 20 — Hot reload.** Lập runbook: stop threads, restore TCCL, detach registries, close streams/JAR loader, create new loader, validate new resources/provider, monitor old-loader retention.

**Bài 21 — Security architecture.** Đề xuất process-isolated execution cho plugins không tin cậy, không dùng class loaders làm sandbox.

**Bài 22 — Diagnosing duplicate classes.** Cho hai classloaders tạo cùng binary class name từ cùng bytecode; giải thích vì sao không thể ép cast bằng reflection.

**Bài 23 — Java resource packaging.** Tạo một JAR chứa `assets/banner.txt` và `META-INF/services/...`. Đọc bằng ClassLoader API sau khi packaged.

**Bài 24 — Conflict handling.** Tạo hai resources `config/defaults.properties` ở parent/child; xây chính sách tránh đọc nhầm config bất chấp phiên bản.

## 27. Tổng kết

- **Runtime class identity không chỉ là class name.** Nó được xác định bởi **binary name + defining class loader**; hai classes tên giống nhau do hai loaders định nghĩa là hai types khác nhau.
- **Initiating loader không nhất thiết là defining loader.** Default delegation thường parent-first nhưng custom loader có thể thay đổi.
- **Resource lookup tách biệt class lookup.** Custom child-first classes không tự biến `getResource` thành child-first; có thể class đến từ CHILD, resource đến từ PARENT.
- **`Class.getResource` và `ClassLoader.getResource` dùng quy tắc tên khác nhau.** Class-relative resource không giống loader-root resource; tránh leading slash trong loader API.
- **Resources có thể nằm trong JAR/JRT/module, không phải file OS.** Đọc bằng stream, dùng UTF-8 và đóng streams/`URLClassLoader`.
- **TCCL giúp libraries tìm resources/service providers của plugin**, nhưng phải restore trong `finally` để tránh leakage khi thread được tái sử dụng.
- **`ServiceLoader` cần shared service type identity**. Parent-defined SPI giúp plugin implementations được host chấp nhận.
- **JPMS resource encapsulation còn phân biệt `exports` với `opens`**; không phải resource tồn tại là mọi caller thấy được.
- **`Class.forName(...,false,loader)` không initialize ngay**, nhưng loading vẫn có thể dẫn đến code execution về sau; trust/authorization là vấn đề riêng.
- **`URLClassLoader.close` không lập tức unload Class objects**; hot reload cần giải phóng references và quản lý lifecycle.
- **ClassLoader không phải security sandbox.** Với code không tin cậy, dùng process/OS isolation và artifact verification.
- Các APIs trong bài **vẫn còn phù hợp cho Java 17+**, không cần các kỹ thuật legacy hoặc undocumented internals.

## Tài liệu chính thức

- [ClassLoader — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ClassLoader.html): class delegation, defining/initiating behavior, `getResource`, `getResources`, named-module resource restrictions.
- [Class — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Class.html): `getClassLoader`, `forName`, `getResource`/`getResourceAsStream`, class-relative và absolute names.
- [URLClassLoader — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/URLClassLoader.html): URL/JAR class paths, `close()`, resource streams.
- [Module — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Module.html): `getResourceAsStream`, `isOpen`, `isExported`.
- [ServiceLoader — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/ServiceLoader.html): provider discovery, TCCL convenience overload, named modules/`uses`/`provides`.
- [Thread — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Thread.html): `getContextClassLoader`/`setContextClassLoader`.
- [JavaCompiler — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.compiler/javax/tools/JavaCompiler.html): JDK compiler trong test harness.
- [JarURLConnection — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/JarURLConnection.html): JAR URL caching và cách mở streams.
- [Java Virtual Machine Specification `5.3 — Creation of Classes and Interfaces](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-5.html#jvms-5.3): binary name, defining loader, initiating loader, runtime identity.
- [Java Virtual Machine Specification `5.4 — Linking](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-5.html#jvms-5.4): verification, preparation, resolution và loader constraints.
- [Java Language Specification `12 — Execution](https://docs.oracle.com/javase/specs/jls/se21/html/jls-12.html): loading/linking/initialization.
