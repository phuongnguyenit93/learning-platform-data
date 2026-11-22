# Xác định lớp Java đến từ thư mục, JAR hay runtime image nào

> **Java Core → ClassLoader → Chẩn đoán.** Khi gặp `ClassNotFoundException`, `NoSuchMethodError`, lỗi thư viện trùng phiên bản hoặc muốn biết JVM thật sự nạp một lớp ở đâu, câu hỏi “class này đến từ file nào?” không thể luôn trả lời chỉ bằng `java.class.path`. Nguồn có thể là một thư mục biên dịch, một JAR trong URL search path, một module trong runtime image (`jrt:`), hoặc bytecode do custom loader sinh/đọc từ nguồn không có tệp `.class` tương ứng. Bài này hướng dẫn kết hợp **`Class<?>` thực tế**, **defining loader**, **`Module`**, **`ProtectionDomain.CodeSource`**, **class-resource URL** và **JVM class-loading logs** để tìm nguyên nhân đúng; gồm chương trình Java 17+ tạo và kiểm chứng đủ ba trường hợp thư mục/JAR/runtime image.

## 1. “Class đến từ đâu?” có nhiều ý nghĩa

Hãy phân biệt năm câu hỏi trước khi dùng API:

1. **Class identity:** object `Class<?>` nào thật sự được JVM sử dụng, với binary name và defining loader nào?
2. **Source artifact:** bytecode thường đến từ thư mục classes, một tệp JAR, module runtime image, hay bộ nạp tùy chỉnh?
3. **Resource URL:** có tìm được resource `.../Foo.class` cùng tên và URL protocol của nó là gì?
4. **Module ownership:** class thuộc named module `java.base`, một named module ứng dụng, hay unnamed module?
5. **Nguồn được khai báo:** `CodeSource.location` của `ProtectionDomain` cho biết loader/runtime **gắn nhãn** nguồn nào?

Không phải năm câu hỏi này luôn có cùng một đáp án.

Ví dụ một lớp `com.example.Widget` được JVM định nghĩa từ bytes do custom loader lấy qua HTTP nhưng loader không cung cấp `CodeSource`, đồng thời resource lookup của loader có thể không tìm thấy `com/example/Widget.class`. Trong trường hợp đó, **không có URL file/JAR đáng tin nào để suy ra** chỉ bằng reflection.

Ngược lại, với `URLClassLoader` tiêu chuẩn đọc một directory hoặc JAR file, `CodeSource` và resource URL thường cung cấp bằng chứng chẩn đoán rất hữu ích.

## 2. Tổng quan các tín hiệu chẩn đoán

| Tín hiệu | API/công cụ | Cho biết | Giới hạn |
| --- | --- | --- | --- |
| Defining class loader | `clazz.getClassLoader()` | Loader gắn với runtime `Class<?>`. | `null` với bootstrap-defined classes; không cho biết path. |
| Named/unnamed module | `clazz.getModule()` | Module chứa class, `Module.getName()`. | Unnamed module thường có tên `null`; không tự chỉ JAR. |
| CodeSource | `clazz.getProtectionDomain().getCodeSource().getLocation()` | URL nguồn được gắn vào protection domain nếu có. | Có thể `null` hoặc được custom loader tự gán, không bảo đảm là source thật đã xác minh. |
| Class resource | `clazz.getResource("/p/Foo.class")` | URL resource tra cứu được theo tên trong context của class. | Có thể `null`, trùng tên, khác bytes thực đã define, custom loader không expose resource. |
| Search path loader | `((URLClassLoader) loader).getURLs()` | Các URL cấu hình trực tiếp trên instance URLClassLoader. | Không phải đường nguồn chính xác của class; không bao gồm parent/module toàn JVM. |
| JVM loading event | `-Xlog:class+load=info` (HotSpot) | Nguồn được JVM ghi nhận khi nạp class. | Log phụ thuộc runtime/format; cần quan sát class thật, không thay API contract. |
| Runtime image modules | `jrt:` / `FileSystems.getFileSystem(URI.create("jrt:/"))` | Module resources thuộc runtime image hiện chạy. | Không phải file JAR `rt.jar` và không nên biến URL sang `File` thông thường. |

Chọn **đúng object `Class<?>`** làm điểm xuất phát. Chỉ nhìn string class name hoặc application classpath có thể sai khi có hai loaders khác nhau định nghĩa cùng binary name.

## 3. Xác định defining loader trước khi xác định đường dẫn

Một class runtime được phân biệt bởi **(binary name, defining class loader)** theo JVM Specification.

```java
Class<?> type = Class.forName("com.example.Widget", false, loader);
System.out.println(type.getName());
System.out.println(type.getClassLoader());
System.out.println(type.getModule());
```

Đây là **snippet** cần biến `loader` là một `ClassLoader` đã biết và class có tồn tại; nó không phải chương trình độc lập.

### Vì sao chọn đúng Class<?> quan trọng?

Giả sử:

```text
Host loader H:
  com.example.PluginApi.class

Plugin loader P1:
  com.example.Impl.class from plugin-v1.jar

Plugin loader P2:
  com.example.Impl.class from plugin-v2.jar
```

`P1.loadClass("com.example.Impl")` và `P2.loadClass("com.example.Impl")` có thể trả về **hai `Class<?>` khác nhau**. Nếu bạn dùng `Class.forName("com.example.Impl")` không truyền đúng loader, kết quả có thể được hỏi từ loader của caller, không phải loader quản lý plugin bạn muốn chẩn đoán.

`clazz.getClassLoader() == null` với các lớp JDK nền tảng được **bootstrap loader** định nghĩa, như `java.lang.String`. `null` **không** có nghĩa lớp không được JVM nạp hoặc có file nguồn ở path `null`. Các lớp được định nghĩa ở platform loader hay application loader thường trả object loader tương ứng, không nhất thiết là `URLClassLoader`.

**Không ép kiểu mù:**

```java
// KHÔNG di động trên Java 9+:
java.net.URLClassLoader app =
        (java.net.URLClassLoader) ClassLoader.getSystemClassLoader();
```

Built-in system/application loader của OpenJDK Java 9+ không phải `URLClassLoader` trong cấu hình thông dụng; câu lệnh có thể ném `ClassCastException`. Chỉ dùng `getURLs` nếu **instance thật sự** là `URLClassLoader`.

## 4. Nhìn vào Module: named, unnamed và java.base

`Class.getModule()` cho biết module **thực sự chứa class**. Với:

```java
Module module = String.class.getModule();
System.out.println(module.isNamed());
System.out.println(module.getName());
```

Kết quả trên Java 17+:

```text
true
java.base
```

Class `java.lang.String` thuộc named module `java.base` nằm trong Java runtime image. Đừng tìm nó bằng đường dẫn `lib/rt.jar` như trên Java 8.

Một class ứng dụng đặt ở classpath thông thường thường thuộc **unnamed module** của defining loader:

```java
Module m = someApplicationClass.getModule();
System.out.println(m.isNamed()); // thường false cho classpath class
System.out.println(m.getName());  // null nếu unnamed
```

Đây là snippet cần `someApplicationClass` được cung cấp. **Không suy ra** chỉ vì module unnamed thì class đến từ directory chứ không phải JAR: cả directory lẫn JAR trên classpath/`URLClassLoader` đều có thể thuộc unnamed module.

Named module `m.library` có thể được lấy từ một JAR trên module path, thư mục modules biên dịch, hoặc một module trong runtime image; `getModule().getName()` là **tên module**, không phải full path tới JAR.

## 5. ProtectionDomain.CodeSource.location: hữu ích nhưng phải xử lý null

Với một class đã được nạp:

```java
import java.net.URL;
import java.security.CodeSource;
import java.security.ProtectionDomain;

// Snippet: clazz là Class<?> cần kiểm tra.
ProtectionDomain pd = clazz.getProtectionDomain();
CodeSource cs = pd == null ? null : pd.getCodeSource();
URL location = cs == null ? null : cs.getLocation();
System.out.println(location);
```

`CodeSource.location` là một `URL` mô tả nguồn được gắn với class. Với `URLClassLoader` nạp từ directory/JAR, location thường là **URL đường dẫn directory hoặc archive**:

```text
file:/.../classes/                 (directory class source)
file:/.../lib/example.jar          (JAR code source)
```

Lưu ý: **CodeSource của class bên trong JAR thường là `file:...jar`**, không phải `jar:...!/p/Foo.class`. Đây là sự khác biệt quan trọng giữa **nguồn archive** và **URL tới entry/resource cụ thể**.

CodeSource có thể là `null` với các Java runtime classes, một số generated classes, hidden classes, custom loaders hoặc security domains đặc biệt. Vì vậy không gọi:

```java
// Dễ gây NullPointerException:
clazz.getProtectionDomain().getCodeSource().getLocation();
```

mà không kiểm tra các giá trị có thể rỗng.

### CodeSource có phải chứng cứ bảo mật?

Không. Một custom `SecureClassLoader` có thể tự tạo:

```java
new java.security.CodeSource(
        claimedUrl, (java.security.cert.Certificate[]) null);
```

và gắn URL đó vào class bytes đọc từ một nơi khác. Đoạn này là snippet cần `claimedUrl` trong context và **không xác minh bytecode thực sự được lấy từ URL đã nêu**. Với audit an toàn, kiểm chứng artifact/hash/signatures/source qua pipeline đáng tin, không chỉ ghi lại `CodeSource`.

### Đừng tự động biến mọi URL thành Path

`Path.of(location.toURI())` chỉ có nghĩa khi URI scheme và file-system provider tương ứng hỗ trợ. Một `file:` code source có thể chuyển thành `Path` với `Path.of(URI)` trên file system mặc định; `jar:` và `jrt:` có semantics khác, thường không chuyển trực tiếp sang `new File(...)`.

Xem `URL.getProtocol()` trước; giữ `URL` nếu mục đích chỉ là chẩn đoán.

## 6. Class resource URL: dấu hiệu file:, jar:, jrt:

`Class.getResource(String)` tìm resource bằng URL:

```java
Class<?> clazz = /* class đã tìm được */;
String classResourceName = "/" +
        clazz.getName().replace('.', '/') + ".class";
java.net.URL classResource = clazz.getResource(classResourceName);
System.out.println(classResource);
```

Đây là snippet; `clazz` cần định nghĩa trước. Dấu `/` đầu chuỗi nghĩa đường dẫn resource **tuyệt đối từ root**. Cách xây tên này phù hợp với **lớp thường có binary name**; với array, primitive, hidden/generated classes hoặc custom representation, không thể giả định luôn có resource `.class`.

Các URL phổ biến:

| Nguồn | Resource URL minh họa | `getProtocol()` |
| --- | --- | --- |
| Directory trên classpath/custom URLClassLoader | `file:/work/out/demo/Widget.class` | `file` |
| Entry trong JAR | `jar:file:/work/plugins/widget.jar!/demo/Widget.class` | `jar` |
| Runtime image JDK 9+ | `jrt:/java.base/java/lang/String.class` | `jrt` |

Phần sau ký tự `!` trong `jar:...!/entry` là tên **entry bên trong archive**, không phải path file riêng có thể `Files.readAllBytes(Path.of(...))` theo default filesystem.

Các URL là **ví dụ**, path thực tế khác theo máy và JDK. Trên Windows, URL có thể có drive letter và escaping; không ghép chuỗi `"file:" + path` thủ công.

### Resource URL có chắc là bytes dùng để định nghĩa Class<?> không?

**Không phải lúc nào cũng chắc.** `clazz.getResource(...)` thực hiện **resource lookup**, trong khi class loading dùng cơ chế `loadClass`/`findClass`/`defineClass`. Một custom loader có thể:

- Định nghĩa class từ bytes tạo trực tiếp trong memory nhưng không expose resource nào.
- Sửa/transform bytes trước khi `defineClass`, trong khi resource URL vẫn trỏ bản gốc.
- Nạp class qua một nguồn nhưng `findResource` lại dùng mapping khác.
- Trả resource từ parent/delegated source mà không đúng class object muốn khảo sát.

Nếu có **hai JAR chứa resource/class cùng tên**, `getResource` có thể trả một URL theo delegation/order policy của loader. Một URL hiện có không chứng minh bytecode của class đang chạy được nạp từ URL đó khi class đã được define trước hoặc loader có strategy khác.

Cách suy luận tốt: so sánh **defining loader + module + CodeSource + class resource + class-load logs**; khi không đồng nhất, kiểm tra loader implementation và transformation path thay vì coi một URL đơn lẻ là chân lý.

## 7. Thí nghiệm Java 17+: ba nguồn directory, JAR và runtime image

Ta sẽ tự tạo hai class:

- `demo.dir.FromDirectory` biên dịch vào `out/dir`.
- `demo.jar.FromJar` được đóng gói trong `plugin.jar`.
- `java.lang.String` có sẵn trong `java.base` runtime image của JDK 17+.

Ứng dụng `OriginDemo` chạy từ `out/app`, tạo một `URLClassLoader` với đường tìm gồm **directory URL** và **JAR URL**. Parent là platform loader, nhờ vậy hai demo classes được custom loader tự định nghĩa.

### Cấu trúc project

```text
src/
  dir/
    demo/dir/FromDirectory.java
  jar/
    demo/jar/FromJar.java
  app/
    OriginDemo.java
out/
  dir/         (javac tạo)
  jar/         (javac tạo)
  app/         (javac tạo)
plugin.jar     (jar tạo)
```

**File `src/dir/demo/dir/FromDirectory.java`:**

```java
package demo.dir;

public final class FromDirectory {
    public String value() {
        return "directory";
    }
}
```

**File `src/jar/demo/jar/FromJar.java`:**

```java
package demo.jar;

public final class FromJar {
    public String value() {
        return "jar";
    }
}
```

**File `src/app/OriginDemo.java`:**

```java
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;
import java.security.CodeSource;
import java.security.ProtectionDomain;

public class OriginDemo {
    private static URL resourceFor(Class<?> type) {
        String path = "/" + type.getName().replace('.', '/') + ".class";
        return type.getResource(path);
    }

    private static URL sourceFor(Class<?> type) {
        ProtectionDomain pd = type.getProtectionDomain();
        CodeSource cs = pd == null ? null : pd.getCodeSource();
        return cs == null ? null : cs.getLocation();
    }

    public static void main(String[] args) throws Exception {
        URL dir = Path.of("out/dir")
                .toAbsolutePath().toUri().toURL();
        URL jar = Path.of("plugin.jar")
                .toAbsolutePath().toUri().toURL();

        try (URLClassLoader loader = new URLClassLoader(
                new URL[]{dir, jar},
                ClassLoader.getPlatformClassLoader())) {

            Class<?> directory = Class.forName(
                    "demo.dir.FromDirectory", false, loader);
            Class<?> archive = Class.forName(
                    "demo.jar.FromJar", false, loader);

            System.out.println("directory loader owned: "
                    + (directory.getClassLoader() == loader));
            System.out.println("directory resource protocol: "
                    + resourceFor(directory).getProtocol());
            System.out.println("directory CodeSource matches: "
                    + dir.equals(sourceFor(directory)));

            System.out.println("jar loader owned: "
                    + (archive.getClassLoader() == loader));
            System.out.println("jar resource protocol: "
                    + resourceFor(archive).getProtocol());
            System.out.println("jar resource inside archive: "
                    + resourceFor(archive).toExternalForm()
                       .contains("!/demo/jar/FromJar.class"));
            System.out.println("jar CodeSource matches: "
                    + jar.equals(sourceFor(archive)));

            System.out.println("loader search URLs: "
                    + loader.getURLs().length);

            Class<?> jdk = String.class;
            System.out.println("runtime module: "
                    + jdk.getModule().getName());
            System.out.println("runtime loader null: "
                    + (jdk.getClassLoader() == null));

            URL jrt = resourceFor(jdk);
            System.out.println("runtime resource protocol: "
                    + (jrt == null ? "null" : jrt.getProtocol()));
            System.out.println("runtime resource module path: "
                    + (jrt != null
                       && jrt.toExternalForm().contains(
                            "java.base/java/lang/String.class")));
            System.out.println("runtime CodeSource absent: "
                    + (sourceFor(jdk) == null));
        }
    }
}
```

### Biên dịch và đóng gói

Đứng ở thư mục gốc có `src` (chạy trên Java 17+):

```bash
javac --release 17 -d out/dir src/dir/demo/dir/FromDirectory.java
javac --release 17 -d out/jar src/jar/demo/jar/FromJar.java
jar --create --file plugin.jar -C out/jar .
javac --release 17 -d out/app src/app/OriginDemo.java
java -cp out/app OriginDemo
```

Chương trình ứng dụng **không** thêm `out/dir` hoặc `plugin.jar` vào `-cp`. Bởi vậy không vô tình cho application loader nạp hai class này trước custom loader. Đường `out/dir` được tạo bởi `Path.toUri().toURL()` để có directory URL đúng; `plugin.jar` là URL trỏ file JAR.

**Stdout chính xác đã biên dịch và kiểm chứng với `javac --release 17`, chạy trên OpenJDK 24:**

```text
directory loader owned: true
directory resource protocol: file
directory CodeSource matches: true
jar loader owned: true
jar resource protocol: jar
jar resource inside archive: true
jar CodeSource matches: true
loader search URLs: 2
runtime module: java.base
runtime loader null: true
runtime resource protocol: jrt
runtime resource module path: true
runtime CodeSource absent: true
```

### Vì sao ba kiểu nguồn được nhận ra?

1. **Directory class:** `URLClassLoader` đọc `out/dir/demo/dir/FromDirectory.class`; URL của class resource có `file:` protocol, còn `CodeSource.location` bằng root `out/dir/`. Class thực sự do custom loader define.
2. **JAR class:** `plugin.jar` chứa entry `demo/jar/FromJar.class`. Resource URL có `jar:...!/demo/jar/FromJar.class`; `CodeSource.location` là URL tới **toàn bộ plugin.jar**. Class do cùng custom loader define.
3. **Runtime class:** `String.class` thuộc `java.base`, do bootstrap loader quản lý (`getClassLoader() == null`). Resource lookup trả `jrt:`; `CodeSource` của lớp này không được công bố theo kiểu file/JAR trong demo.
4. **`getURLs().length == 2`** chỉ nói loader cấu hình hai search URLs. Không có nghĩa toàn JVM chỉ có hai nguồn classes; `String` vẫn được nạp từ runtime image qua bootstrap.
5. `Class.forName(name, false, loader)` yêu cầu JVM nạp/tìm class nhưng không buộc chạy static initializer. Test tập trung **provenance**, không dựa vào tác dụng phụ của initialization.

Các path thực tế phụ thuộc nơi chạy, nên bài in ra **protocol và các phép kiểm tra Boolean** thay vì hard-code đường dẫn tuyệt đối.

### Những gì ví dụ KHÔNG chứng minh

- Không chứng minh `CodeSource` là chữ ký/xác thực nguồn đáng tin.
- Không chứng minh mọi custom loader đều cung cấp resource `.class`.
- Không chứng minh `getURLs()` liệt kê class đã load; nó là cấu hình search path.
- Không kiểm tra trường hợp hai JAR có cùng tên class/resource hoặc class được transform trước define.
- Không đo được chính xác thời gian/class unloading khi loader đóng.

Muốn biết loader thật đã đọc entry nào trong production, kết hợp logging và kiểm tra framework loader implementation.

## 8. Runtime image jrt: là gì?

Từ Java 9, JDK/JRE image dùng **modular runtime image**. Các lớp Java nền tảng thường không còn được phát hành trong một `rt.jar` chuẩn như Java 8. Với API Java 9+, tài nguyên module được biểu diễn dưới dạng URI/URL scheme **`jrt:`**.

Ví dụ:

```text
jrt:/java.base/java/lang/String.class
jrt:/java.logging/java/util/logging/Logger.class
```

Cấu trúc logic:

```text
jrt:/
  java.base/
    java/lang/String.class
  java.logging/
    java/util/logging/Logger.class
```

Đây là **không gian đường dẫn logic của runtime image**, không phải thông báo rằng trên disk có một thư mục thực `java.base` với các tệp `.class` thông thường. Với HotSpot/OpenJDK runtime images, các module data thường được lưu trong image file `lib/modules`; định dạng này khác JAR/ZIP truyền thống.

**Đừng chuyển `jrt:/java.base/...` sang `new File(...)` rồi thử đọc.** Nếu cần duyệt dữ liệu runtime module có quyền truy cập, sử dụng jrt filesystem provider:

```java
import java.net.URI;
import java.nio.file.FileSystem;
import java.nio.file.FileSystems;
import java.nio.file.Path;

// Snippet: Java 9+ trên JDK hỗ trợ jrt file system:
URI uri = URI.create("jrt:/");
FileSystem fs = FileSystems.getFileSystem(uri);
Path stringClass = fs.getPath(
        "/modules/java.base/java/lang/String.class");
System.out.println(java.nio.file.Files.exists(stringClass));
```

Đây là snippet minh họa trong method có `throws IOException` hoặc xử lý ngoại lệ phù hợp; `getFileSystem` phụ thuộc provider/file system đã được tạo/có sẵn trong môi trường. Đừng hard-code layout vật lý hay mong `jrt` dùng được trên Java 8.

### Runtime image khác module JAR

Một **named module** có thể đến từ:

- Runtime image (`jrt:`, ví dụ `java.base`).
- Modular JAR trên module path (`file:`/`jar:` về artifact).
- Exploded module directory trên module path.
- ModuleLayer tùy chỉnh với nguồn classes riêng.

Vì vậy `clazz.getModule().isNamed() == true` **không đủ** để kết luận class thuộc JDK runtime image. Cần xem **module name và resource/source** cùng runtime provenance. Ngược lại, một Java class trong plugin JAR có thể thuộc unnamed module khi được URLClassLoader nạp từ classpath-style search path.

## 9. Class resource, ClassLoader.getResource và duplicate resources

Các phương thức:

```java
// Snippet với Class<?> clazz:
java.net.URL viaClass =
        clazz.getResource("/demo/Widget.class");

ClassLoader loader = clazz.getClassLoader();
java.net.URL viaLoader = loader == null ? null
        : loader.getResource("demo/Widget.class");
```

Hai tên resource khác nhau về cú pháp:

- `Class.getResource("/p/Foo.class")`: dấu `/` đầu báo **absolute** resource name.
- `ClassLoader.getResource("p/Foo.class")`: tên resource dùng path với dấu `/`, **không bắt đầu bằng `/`**.
- `Class.getResource("Foo.class")`: **relative** theo package của chính class nhận lời gọi.
- `ClassLoader.getSystemResource(...)` dùng system class loader và không phải lời giải phổ quát cho custom loader khác.

Với named modules, resource lookup chịu **module encapsulation** và có ngoại lệ đối với resources tên kết thúc bằng `.class` theo API; resource bình thường trong package đóng có thể bị chặn. Đừng dùng một resource `config.yml` bị `null` để kết luận module/class không được load.

Khi có trùng resource names trên nhiều URL/JAR, `ClassLoader.getResources(String)` có thể liệt kê nhiều URL được tìm thấy (theo policy delegation/visibility) để debug:

```java
// Snippet: loader là ClassLoader đang khảo sát:
java.util.Enumeration<java.net.URL> urls =
        loader.getResources("demo/Widget.class");
while (urls.hasMoreElements()) {
    System.out.println(urls.nextElement());
}
```

**Không phải danh sách mọi class JVM đã define.** `getResources` trả những resources có thể tìm theo tên, không phải list class objects. Nếu một loader đã define `Widget` từ JAR A, sau đó thứ tự resource đổi hoặc class file trong JAR A bị thay, kết quả hiện tại không nhất thiết là bytes chính xác JVM đã dùng trước đó.

Nếu muốn nhận biết **nhiều bản class cùng tên**, log từng resource URL, kiểm tra artifact checksums và quan sát `clazz.getClassLoader()`/`CodeSource` của class thực sự được dùng.

## 10. URLClassLoader.getURLs: search path không phải provenance cuối

`URLClassLoader` cho phép đọc cấu hình URL search path:

```java
if (loader instanceof java.net.URLClassLoader urlLoader) {
    for (java.net.URL url : urlLoader.getURLs()) {
        System.out.println(url);
    }
}
```

Đây là snippet dùng pattern-matching `instanceof` (ổn định ở Java 17+), với biến `loader` kiểu `ClassLoader`. Mảng `getURLs()` gồm URLs khởi tạo và URLs được `addURL` bổ sung cho chính loader.

Nhưng:

- Parent delegation có thể trả `Class<?>` từ parent, không nằm trong search URLs của child.
- Một source URL có thể chứa hàng trăm classes; có URL chưa từng được dùng.
- Manifest Class-Path và multi-release JAR lookup có semantics riêng.
- Class đã được define vẫn là class đó; thêm URL mới **không** thay bytecode của class ấy.
- Loader có thể không phải URLClassLoader, đặc biệt built-in app loader ở Java 9+.

**Nếu câu hỏi là “Class X thực sự đến từ đâu?” thì `clazz`, không phải `loader.getURLs()`, là điểm xuất phát.**

## 11. Khi nào class-loading log giúp xác nhận source?

Trong HotSpot JDK 17+, có thể bật `-Xlog:class+load=info` **trước khi tái hiện** để ghi sự kiện load và source của lớp liên quan:

```bash
java -Xlog:class+load=info -cp out/app OriginDemo
```

Một dòng thường chứa binary class name và `source:`; với JDK classes còn có thể thấy `shared objects file` từ CDS thay vì một `jrt:` URL. Đừng ép URL ở log trùng với `Class.getResource` hay `CodeSource.location`: đó là các tín hiệu khác nhau. Nếu thiếu event, có thể class đã load trước mốc ghi log. Khi source từ custom loader, module layer hoặc instrumentation chưa rõ, kết hợp `Class<?>` thực tế, loader identity và source metadata. Chi tiết cách bật/lọc log và phân biệt load/init/unload nằm ở hai bài chuyên biệt về Unified Logging.
## 12. Dữ liệu có thể không nằm trên disk: generated/hidden/custom classes

Một số frameworks tạo bytecode ngay trong memory (proxies, lambda implementations, hidden classes, code generation). Chúng có thể:

- Không có `.class` tương ứng ở thư mục/JAR thông thường.
- Không expose class resource qua `Class.getResource(...)`.
- Có `CodeSource.location == null` hoặc metadata không trỏ đến một file thực.
- Có tên class mang cấu trúc đặc biệt không phù hợp xây resource path một cách mù quáng.
- Được định nghĩa bởi custom loader từ bytes đọc qua database/network/transformation pipeline.

Một lớp tên `com.example.GeneratedProxy` không nhất thiết tương ứng với tệp `com/example/GeneratedProxy.class`. `getResource` trả `null` không chứng minh class là lỗi hoặc không thể load: chính `Class<?>` đang tồn tại là bằng chứng nó đã được JVM biết tới.

Với **arrays/primitives**:

```java
System.out.println(int.class.getClassLoader());
System.out.println(String[].class.getClassLoader());
```

Cả hai có thể `null` trên runtime thông thường, vì primitive classes không do user-defined loader tạo; array class có loader semantics theo component type. Đừng cố tìm `[Ljava/lang/String;.class` như một JAR entry thật.

Nếu chương trình sử dụng generated classes, cách tốt nhất là bật **diagnostic mode của bytecode generator** để dump/ghi provenance (chỉ khi được quyền và không chứa secrets), theo dõi loader.defineClass calls và lưu metadata build/version riêng.

## 13. Khi nào có thể tin source và khi nào cần kiểm chứng thêm?

Một checklist trước khi kết luận “class đến từ JAR A”:

1. **Đã có Class<?> đang thực sự được dùng chưa?** Nếu chỉ có class name, bạn chưa biết loader instance.
2. **Defining loader có đúng expected loader không?** `clazz.getClassLoader()` cùng identity check.
3. **Module name là gì?** Named module có thể từ runtime image, module JAR, exploded directory hoặc custom layer.
4. **Resource URL protocol là gì?** `file:`, `jar:`, `jrt:` hay `null`.
5. **CodeSource location là gì?** Có null không? `file:...jar` hay `file:...classes/`?
6. **Class-loading log có ghi sự kiện tương ứng?** Log có thể bắt đầu trước khi bạn cấu hình nếu class đã nạp từ trước.
7. **Có duplicate class/resource ở nhiều JARs không?** Dùng `getResources` hoặc dependency diagnostics.
8. **Có transformation/instrumentation không?** Bytes trong archive có thể khác bytes JVM định nghĩa.
9. **Artifact có thể bị thay sau khi JVM load không?** Nguồn đang có trên disk không đảm bảo vẫn là bytes đã load.
10. **Bạn đang điều tra lỗi runtime hay bảo mật?** CodeSource là metadata/diagnostics, không phải chứng thực provenance.

Trong kiến trúc plugin, lưu bản ghi khi kích hoạt gồm `pluginId`, checksum artifact, loader identity, module identity, version, cùng tên class entry có thể giúp debug hơn chỉ in `getURLs()` vào lúc xảy ra lỗi.

## 14. Lỗi thường gặp và cách xử lý

| Lỗi / giả định sai | Hậu quả | Cách sửa |
| --- | --- | --- |
| Dùng `System.getProperty("java.class.path")` để xác định mọi class JVM | Không bao gồm toàn bộ modules/custom loaders. | Bắt đầu từ `Class<?>`, loader, module, source. |
| Dùng `new File(resource.toURI())` với `jar:`/`jrt:` | `IllegalArgumentException` hoặc không có filesystem path thông thường. | Giữ URL/stream; dùng JarFile hoặc jrt FileSystem khi cần. |
| Thấy `CodeSource == null` thì kết luận lớp bị lỗi | Runtime/hidden/custom classes có thể không có location. | Phân tích module, resource URL, logs. |
| Thấy `getResource == null` thì nghĩ class không tồn tại | Resource lookup có semantics khác class definition. | Dùng `Class<?>`, loader/module; kiểm tra source custom loader. |
| Thấy `file:...jar` trong CodeSource và mong protocol `jar` | CodeSource thường trỏ archive, resource trỏ entry. | Phân biệt archive location vs entry URL. |
| Trông đợi Java 17 `String.class` nằm trong `rt.jar` | Runtime image Java 9+ không dùng legacy rt.jar như Java 8. | Xem `jrt:/java.base/...`. |
| Đổi loader khi chỉ muốn xem source của một class | Tạo namespace class khác, không đại diện class đang chạy. | Inspect đúng Class object. |
| Ép system loader sang URLClassLoader | Java 9+ không bảo đảm subtype. | Chỉ cast nếu `instanceof`; dùng class/module/provenance APIs. |
| Gọi `getURLs` rồi coi URL đầu tiên chứa class | Parent/ordering/JAR metadata có thể thay kết quả. | Xác định loader và source thực của class. |
| Parse URL bằng chuỗi `split("!")` không kiểm tra | Các URI schemes và encoding khác nhau. | Dùng `JarURLConnection`/`URI` APIs thích hợp, xử lý `null`. |
| In đủ paths vào log production công khai | Có thể lộ cấu trúc máy/chỗ triển khai. | Sanitize và giới hạn quyền xem logs. |
| `CodeSource` có URL nên bytes chắc có chữ ký hợp lệ | Custom loader có thể tự gán URL. | Xác minh nguồn/signature/hash độc lập. |
| Source filename ở disk đã đổi nhưng class đang chạy vẫn “bản mới” | Class đã define từ trước không tự cập nhật. | Reload với loader mới theo plugin architecture, quản lý identity. |
| Không xét multi-release JAR | JVM có thể chọn versioned entry theo runtime. | Kiểm tra manifest/`META-INF/versions` và loader semantics. |

## 15. Quy trình điều tra một lỗi dependency/plugin thực tế

**Tình huống:** App gặp `NoSuchMethodError: com.vendor.lib.Util.newMethod()` dù bạn đã thêm một JAR “đúng phiên bản” vào startup script.

### Bước A — tìm caller/callee class đang thực sự chạy

Từ debugger hoặc đoạn log có quyền:

```java
// Snippet: class VendorUtil được resolve trong app:
Class<?> util = com.vendor.lib.Util.class;
System.out.println("class: " + util.getName());
System.out.println("loader: " + util.getClassLoader());
System.out.println("module: " + util.getModule());
```

Đây là snippet phụ thuộc vendor class tồn tại trong project; không phải code của demo chính.

### Bước B — đọc CodeSource an toàn với null

```java
java.security.ProtectionDomain pd = util.getProtectionDomain();
java.security.CodeSource cs =
        pd == null ? null : pd.getCodeSource();
System.out.println("source: " +
        (cs == null ? "<not reported>" : cs.getLocation()));
```

Nếu hiển thị `file:/opt/app/lib/util-1.2.jar` trong khi bạn mong `util-2.0.jar`, đã có dấu hiệu **runtime chọn JAR cũ**. Nếu `CodeSource` không có, cần chuyển sang event log/module data thay vì tự đoán.

### Bước C — tra resource duplicates

```java
ClassLoader loader = util.getClassLoader();
if (loader != null) {
    var entries = loader.getResources(
            "com/vendor/lib/Util.class");
    while (entries.hasMoreElements()) {
        System.out.println("candidate: " + entries.nextElement());
    }
}
```

Kết quả có thể có nhiều candidate resources; thứ tự tìm resource không nhất thiết là chứng cứ bytecode nào đã được define bởi custom loader.

### Bước D — xác định chính runtime đang chạy

Kiểm tra `java -version` của **process thực** (server, container, IDE run configuration), dependency tree, loader hierarchy và `-Xlog:class+load=info` nếu JVM HotSpot hỗ trợ. `getURLs` hoặc `java.class.path` đơn lẻ không mô tả toàn bộ resolution/module graph.

### Bước E — sửa đúng nguồn/class loading policy

- Loại JAR phiên bản cũ **khỏi đúng loader path**.
- Căn chỉnh dependencies trong build và deployment artifacts.
- Nếu class đã được define trong JVM, cần restart hoặc loader generation mới theo thiết kế; chỉ copy JAR vào folder không cập nhật class đang chạy.
- Với plugin child loaders, kiểm tra parent-first delegation có trả bản API/dependency từ host trước không.
- Nếu class đến từ runtime module, không cố thêm JAR trùng `java.*` để override.
- Chạy test xác nhận phiên bản API/method và load-source logs sau khi sửa.

Đừng nhảy đến giải pháp `ClassLoader#addURL` hoặc ép system loader: nó có thể không tác động tới loader dùng để resolve class đang lỗi.

## 16. Tự kiểm tra

1. **Muốn biết class nào thật sự đang chạy, nên bắt đầu từ tên string hay `Class<?>`?**  
   Từ `Class<?>` được code thực sử dụng, vì nó gắn với defining loader và module.

2. **`clazz.getClassLoader() == null` thường có ý nghĩa gì với `String.class`?**  
   `String` do bootstrap loader định nghĩa, không phải JVM “quên” class.

3. **`CodeSource.location` cho class JAR và resource URL có cùng protocol không?**  
   Không bắt buộc. Với `URLClassLoader` trong demo: code source là `file:...plugin.jar`, class resource là `jar:file:...plugin.jar!/entry`.

4. **URL class resource `file:/tmp/classes/p/X.class` gợi ý nguồn nào?**  
   Một class-file resource trong directory tree trên filesystem; cần đối chiếu defining loader và CodeSource.

5. **`jrt:/java.base/java/lang/String.class` có phải file JAR trên disk không?**  
   Không. Nó là đường dẫn logic vào Java runtime image module `java.base`.

6. **Named module chắc chắn nằm trong runtime image?**  
   Không. Named module có thể là modular JAR/exploded module trên module path hoặc custom layer.

7. **Nếu `CodeSource` null nhưng `Class<?>` tồn tại, đó có phải class loading thất bại?**  
   Không. Nguồn có thể không được công bố qua CodeSource.

8. **`URLClassLoader.getURLs()` trả hai URL có nghĩa loader đã nạp hai class?**  
   Không. Nó liệt kê search path được cấu hình.

9. **`Class.getResource` luôn trả đúng bytes JVM đã define?**  
   Không. Loader có thể transform bytes, resource lookup khác path hoặc class được generate.

10. **Tại sao nên dùng `clazz.getModule()` khi chẩn đoán JDK 17+?**  
    Nó xác định module chứa class, giúp phân biệt runtime module, named module ứng dụng và unnamed modules.

11. **Có thể chuyển mọi URL `jar:` hoặc `jrt:` thành `new File(...)` không?**  
    Không. Cần scheme-specific API hoặc stream/filesystem provider tương ứng.

12. **`-Xlog:class+load=info` có phải chuẩn Java bắt buộc trên mọi JVM vendor?**  
    Không. Đây là diagnostic của JVM có Unified Logging (đặc biệt OpenJDK/HotSpot); tùy implementation.

13. **Chỉ thấy `Class.forName` tìm được class, có chắc resource `Foo.class` tìm được không?**  
    Không. Class lookup và resource lookup là hai API với hợp đồng/semantics riêng.

14. **Nếu loader đã nạp phiên bản cũ của một class, copy JAR mới có tự thay runtime type không?**  
    Không. Một defining loader không tự redefine class khi file trên disk bị thay.

## 17. Tham khảo chính thức

- [Java SE 21 — Class](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Class.html): `getClassLoader`, `getModule`, `getResource` và runtime Class object.
- [Java SE 21 — ClassLoader](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ClassLoader.html): delegation, `getResource`, `getResources` và module encapsulation đối với resources.
- [Java SE 21 — URLClassLoader](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/URLClassLoader.html): directory/JAR URL search path, `getURLs`, `findClass`.
- [Java SE 21 — CodeSource](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/CodeSource.html): URL location và certificates/signers metadata.
- [Java SE 21 — ProtectionDomain](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/ProtectionDomain.html): code source và security domain properties.
- [Java SE 21 — Module](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Module.html): `getName`, `isNamed`.
- [Java SE 21 — FileSystems](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/FileSystems.html): `getFileSystem(URI)` cho file systems phù hợp, gồm jrt provider trong môi trường hỗ trợ.
- [Java SE 21 — java launcher](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html): `-Xlog:class+load`, Unified Logging và diagnostics.
- [JDK 9 — JEP 220 Modular Run-Time Images](https://openjdk.org/jeps/220): mô hình runtime image thay cho các archive `rt.jar` truyền thống.
- [JVMS Java SE 21 `5.3](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-5.html#jvms-5.3): class identity theo binary name và defining loader.
