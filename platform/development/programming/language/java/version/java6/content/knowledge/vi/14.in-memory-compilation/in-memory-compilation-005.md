# Dependency của mã sinh và khả năng nhìn thấy kiểu khi biên dịch trong bộ nhớ

## 1. Đặt vấn đề

Trong Java, `JavaCompiler` (thuộc `javax.tools`) cho phép biên dịch source được tạo dưới dạng chuỗi hoặc `JavaFileObject`, rồi thu kết quả `.class` vào một `JavaFileManager` tùy chỉnh. Cách này thường phục vụ sinh mã động, template engine, công cụ phân tích mã, rule engine, trình tạo adapter hoặc công cụ kiểm thử. API vẫn được hỗ trợ trong các JDK hiện đại, gồm Java 17+.

**Điểm mấu chốt:** một lớp đã được sinh/biên dịch thành công **không tự động xuất hiện như dependency** đối với *lượt biên dịch sau*. Compiler phải nhìn thấy định nghĩa của kiểu phụ thuộc qua source đang được biên dịch trong cùng task, qua classpath/module path, hoặc qua `JavaFileManager` có thể cung cấp class/source từ bộ nhớ. Sau khi biên dịch, **JVM lại cần một `ClassLoader`** có thể tải các bytecode đó để chạy.

Ví dụ tình huống:
- Lượt 1 sinh và biên dịch `lesson.api.Greeter` thành `byte[]` chỉ tồn tại trong RAM.
- Lượt 2 biên dịch `lesson.impl.Hello implements lesson.api.Greeter`.
- Nếu compiler của lượt 2 không được cấp `Greeter` qua input source/classfile, nó sẽ báo không tìm được kiểu; **đặt `Greeter.class` trong một `Map<String, byte[]>` của ứng dụng chưa đủ**.
- Sau khi cấp `Greeter.class` cho file manager đúng cách, lượt 2 biên dịch được; muốn gọi `Hello.greet`, runtime loader phải tải được **cả** `Greeter` và `Hello`.

Sau bài này, bạn sẽ phân biệt hai bài toán *compile-time type visibility* và *runtime class loading*, biết cách cung cấp dependency trong bộ nhớ giữa các lượt biên dịch và hiểu lỗi thường gặp của cơ chế này.

## 2. Hai ranh giới: compiler nhìn thấy kiểu và runtime tải class

```text
             Giai đoạn BIÊN DỊCH
source đang biên dịch (JavaFileObject)
               |
               v
   JavaCompiler + JavaFileManager
       |       |        |
       |       |        +-- platform classes / modules
       |       +----------- dependency: .java / .class / JAR / RAM
       +------------------- output: bytecode .class -> Map<String,byte[]>
                                              |
                                              v
              Giai đoạn CHẠY
            ClassLoader nhận bytes
               |             |
          lesson.api.Greeter  lesson.impl.Hello
               \             /
                 JVM liên kết kiểu
                        |
                  gọi greet(...)
```

**Compiler nhìn thấy kiểu** nghĩa là bộ phân giải ký hiệu có thể đọc thông tin của `lesson.api.Greeter` lúc kiểm tra `implements`, import, chữ ký phương thức, constructor, kiểu trả về và các lời gọi. Cơ chế này đi qua `JavaFileManager` và các đường tìm kiếm thích hợp.

**Runtime tải class** nghĩa là JVM dùng `ClassLoader` để định nghĩa và liên kết `Class<?>` từ bytecode. Hai việc **khác thời điểm và khác API**. Đưa class vào `ClassLoader` chưa chắc khiến compiler tìm thấy nó; ngược lại, compiler có thể đọc dependency từ một JAR nhưng runtime không có JAR đó sẽ gặp lỗi.

Ví dụ minh họa về quan hệ nguồn:

```java
// lesson/api/Greeter.java
package lesson.api;

public interface Greeter {
    String greet(String name);
}
```

```java
// lesson/impl/Hello.java
package lesson.impl;

public class Hello implements lesson.api.Greeter {
    public String greet(String name) {
        return "Hello, " + name;
    }
}
```

Hai đoạn là **hai source file minh họa** với package tương ứng. Nếu cùng nằm trong một compilation task, javac có thể phân giải `Greeter` trực tiếp từ danh sách source. Nếu compile độc lập, task của `Hello` phải được cung cấp dependency.

## 3. Compiler lấy dependency từ đâu?

| Nguồn dependency | Cách cung cấp cho JavaCompiler | Lưu ý |
| --- | --- | --- |
| **Nhiều source trong cùng task** | `getTask(..., units)` với các `JavaFileObject` của cả API và implementation | Giải quyết cùng nhau, tiện khi toàn bộ mã sinh cùng một đợt. |
| **Class output đã ghi vào thư mục** | `StandardJavaFileManager` với `StandardLocation.CLASS_PATH` hoặc option `--class-path` | Thư mục phải chứa đúng đường dẫn package, ví dụ `lesson/api/Greeter.class`. |
| **JAR thư viện bên ngoài** | Thêm JAR vào compile classpath | Cũng cần JAR phù hợp ở runtime (trừ khi dependency chỉ dùng lúc compile). |
| **Classfile chỉ nằm trong RAM** | `JavaFileManager` tùy chỉnh trả `JavaFileObject.Kind.CLASS` từ `byte[]` | Cần hỗ trợ các thao tác tìm kiếm lớp mà compiler sử dụng, không chỉ thu output. |
| **Sourcefile chỉ nằm trong RAM ở lượt khác** | Cấp lại source ở task mới hoặc cấu hình file manager cung cấp source khi compiler tìm kiếm | Lưu chuỗi Java vào `Map` chưa tự làm compiler nhìn thấy. |
| **Named Java modules (JPMS)** | Module path, module location và `requires`/`exports` phù hợp | Không trộn lẫn máy móc với quy tắc unnamed-module classpath. |

Không có thuật toán “quét tất cả class trong JVM” để tự động tìm dependency. Trong cấu hình thông thường, `StandardJavaFileManager` thực hiện các truy vấn chuẩn trên filesystem/JAR/classpath; muốn dùng classfile chỉ tồn tại ở RAM, bạn phải nối dữ liệu đó vào **file manager của compilation task tiếp theo**.

Đặc biệt, **cùng tên đầy đủ chưa chắc cùng một kiểu ở runtime**: định danh class còn phụ thuộc defining `ClassLoader`. Đừng để host và generated code cùng định nghĩa hai bản độc lập của một interface dùng chung rồi ép kiểu qua biên giới loader.

## 4. Những API cốt lõi của biên dịch trong bộ nhớ

### 4.1. String source: SimpleJavaFileObject

Có thể biểu diễn một source file ảo bằng `SimpleJavaFileObject`:

```java
final class Source extends SimpleJavaFileObject {
    final String code;

    Source(String binaryName, String code) {
        super(
            URI.create("string:///" +
                    binaryName.replace('.', '/') +
                    Kind.SOURCE.extension),
            Kind.SOURCE
        );
        this.code = code;
    }

    @Override
    public CharSequence getCharContent(boolean ignoreEncodingErrors) {
        return code;
    }
}
```

Đây là **snippet**; class đặt trong file Java có các import `java.net.URI` và `javax.tools.SimpleJavaFileObject`. URI đóng vai trò định danh file ảo như `string:///lesson/api/Greeter.java`. Tên source cần khớp quy tắc tên file của top-level public class/interface được biên dịch.

### 4.2. Thu class output trong RAM

`JavaFileManager.getJavaFileForOutput(...)` quyết định compiler ghi `.class` ở đâu. Nếu muốn bytecode nằm trong RAM, có thể trả object `Kind.CLASS` với `openOutputStream()` ghi vào `ByteArrayOutputStream`.

Một bản `ForwardingJavaFileManager` thường bọc `StandardJavaFileManager`, giữ các hành vi mặc định rồi **override những điểm cần thiết**:

- `getJavaFileForOutput`: bắt class bytes được sinh.
- `getJavaFileForInput`: cung cấp class bytes *đã tồn tại* từ các lượt compile trước.
- `list`: cho compiler liệt kê các class của package đang phân giải.
- `inferBinaryName`: trả tên đầy đủ như `lesson.api.Greeter` cho một file class ảo do manager quản lý.

**Lỗi rất phổ biến:** chỉ override `getJavaFileForOutput` rồi tưởng compiler sau sẽ tự dùng các bytes cũ. Override đó chỉ quyết định **đầu ra của task hiện tại**, không tạo đầu vào của task mới.

`JavaFileManager` có thêm các API về module locations; ví dụ phía dưới tập trung vào **unnamed module / classpath** trên Java 17+. Đối với dự án JPMS, file manager phải quản lý module path và metadata module phù hợp chứ không thể chỉ gắn mọi thứ vào `CLASS_PATH`.

### 4.3. Thư viện nền tảng và JDK compiler

`ToolProvider.getSystemJavaCompiler()` trả compiler hệ thống khi runtime có implementation `jdk.compiler`; nó có thể trả `null` trong runtime image tối giản thiếu compiler. `javax.tools` là API được công bố bởi module `java.compiler`.

`--release 17` trong ví dụ xác định phiên bản **ngôn ngữ, class file và Java platform API** cho source. Option này **không tự cung cấp dependency ứng dụng** như `lesson.api.Greeter` hoặc thư viện bên ngoài.

## 5. Ví dụ chạy được hoàn toàn trong RAM: dependency thiếu, rồi có

Ví dụ này tạo source của hai kiểu riêng, biên dịch `Greeter` trước, thử compile `Hello` khi không có dependency, sau đó cung cấp class bytes của `Greeter` qua `JavaFileManager` rồi compile lại. Cuối cùng một `ClassLoader` tải cả hai class từ RAM và gọi phương thức.

**Yêu cầu:** JDK 17+, không cần Maven/Gradle, không tạo file `.java` hay `.class` cho hai kiểu sinh. Chỉ cần lưu **một file chạy thử** `MemoryDependencyDemo.java` để gọi Compiler API.

### 5.1. File MemoryDependencyDemo.java

```java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import javax.tools.DiagnosticCollector;
import javax.tools.FileObject;
import javax.tools.ForwardingJavaFileManager;
import javax.tools.JavaCompiler;
import javax.tools.JavaFileManager;
import javax.tools.JavaFileObject;
import javax.tools.SimpleJavaFileObject;
import javax.tools.StandardJavaFileManager;
import javax.tools.StandardLocation;
import javax.tools.ToolProvider;

public class MemoryDependencyDemo {

    // Source Java ảo: không cần ghi ra filesystem.
    static final class Source extends SimpleJavaFileObject {
        private final String source;

        Source(String binaryName, String source) {
            super(URI.create("string:///" +
                    binaryName.replace('.', '/') + Kind.SOURCE.extension),
                    Kind.SOURCE);
            this.source = source;
        }

        @Override
        public CharSequence getCharContent(boolean ignoreEncodingErrors) {
            return source;
        }
    }

    // Class ảo: ghi output vào RAM hoặc đọc bytecode dependency từ RAM.
    static final class Bytes extends SimpleJavaFileObject {
        final String binaryName;
        final ByteArrayOutputStream output = new ByteArrayOutputStream();
        final byte[] input;

        Bytes(String binaryName) {
            super(URI.create("mem:///" +
                    binaryName.replace('.', '/') + Kind.CLASS.extension),
                    Kind.CLASS);
            this.binaryName = binaryName;
            this.input = null;
        }

        Bytes(String binaryName, byte[] input) {
            super(URI.create("mem:///" +
                    binaryName.replace('.', '/') + Kind.CLASS.extension),
                    Kind.CLASS);
            this.binaryName = binaryName;
            this.input = input;
        }

        @Override
        public OutputStream openOutputStream() {
            if (input != null) {
                throw new UnsupportedOperationException("Read-only class");
            }
            return output;
        }

        @Override
        public InputStream openInputStream() {
            return new ByteArrayInputStream(content());
        }

        byte[] content() {
            return input == null ? output.toByteArray() : input;
        }
    }

    // Nối class bytes cũ vào đường tra cứu input của compiler.
    static final class MemoryManager
            extends ForwardingJavaFileManager<StandardJavaFileManager> {

        final Map<String, Bytes> generated = new LinkedHashMap<>();
        final Map<String, Bytes> dependencies = new LinkedHashMap<>();

        MemoryManager(StandardJavaFileManager standard,
                      Map<String, byte[]> previousClassFiles) {
            super(standard);
            previousClassFiles.forEach((name, bytes) ->
                    dependencies.put(name, new Bytes(name, bytes)));
        }

        @Override
        public JavaFileObject getJavaFileForOutput(
                Location location,
                String className,
                JavaFileObject.Kind kind,
                FileObject sibling) throws IOException {

            if (kind != JavaFileObject.Kind.CLASS) {
                return super.getJavaFileForOutput(
                        location, className, kind, sibling);
            }
            Bytes result = new Bytes(className);
            generated.put(className, result);
            return result;
        }

        @Override
        public JavaFileObject getJavaFileForInput(
                Location location,
                String className,
                JavaFileObject.Kind kind) throws IOException {

            if (location == StandardLocation.CLASS_PATH
                    && kind == JavaFileObject.Kind.CLASS
                    && dependencies.containsKey(className)) {
                return dependencies.get(className);
            }
            return super.getJavaFileForInput(location, className, kind);
        }

        @Override
        public Iterable<JavaFileObject> list(
                Location location,
                String packageName,
                Set<JavaFileObject.Kind> kinds,
                boolean recurse) throws IOException {

            List<JavaFileObject> result = new ArrayList<>();
            for (JavaFileObject file :
                    super.list(location, packageName, kinds, recurse)) {
                result.add(file);
            }

            if (location == StandardLocation.CLASS_PATH
                    && kinds.contains(JavaFileObject.Kind.CLASS)) {
                for (Bytes file : dependencies.values()) {
                    String name = file.binaryName;
                    String pkg = name.contains(".")
                            ? name.substring(0, name.lastIndexOf('.'))
                            : "";

                    if (pkg.equals(packageName)
                            || (recurse && (packageName.isEmpty()
                            || pkg.startsWith(packageName + ".")))) {
                        result.add(file);
                    }
                }
            }
            return result;
        }

        @Override
        public String inferBinaryName(Location location, JavaFileObject file) {
            if (file instanceof Bytes bytes) {
                return bytes.binaryName;
            }
            return super.inferBinaryName(location, file);
        }
    }

    // Runtime: tải bytecode; đây không phải công cụ phân giải compile-time.
    static final class MemoryLoader extends ClassLoader {
        private final Map<String, byte[]> classes;

        MemoryLoader(Map<String, byte[]> classes) {
            super(ClassLoader.getPlatformClassLoader());
            this.classes = classes;
        }

        @Override
        protected Class<?> findClass(String name)
                throws ClassNotFoundException {

            byte[] bytes = classes.get(name);
            if (bytes == null) {
                throw new ClassNotFoundException(name);
            }
            return defineClass(name, bytes, 0, bytes.length);
        }
    }

    static boolean compile(
            JavaCompiler compiler,
            JavaFileObject source,
            Map<String, byte[]> dependencies,
            Map<String, byte[]> output) throws IOException {

        DiagnosticCollector<JavaFileObject> diagnostics =
                new DiagnosticCollector<>();

        try (MemoryManager manager = new MemoryManager(
                compiler.getStandardFileManager(
                        diagnostics, Locale.ROOT, StandardCharsets.UTF_8),
                dependencies)) {

            JavaCompiler.CompilationTask task = compiler.getTask(
                    null,
                    manager,
                    diagnostics,
                    List.of("--release", "17", "-proc:none"),
                    null,
                    List.of(source));

            boolean ok = Boolean.TRUE.equals(task.call());
            if (ok) {
                manager.generated.forEach((name, file) ->
                        output.put(name, file.content()));
            }
            // diagnostics được thu nhưng không in: output demo ổn định.
            return ok;
        }
    }

    public static void main(String[] args) throws Exception {
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException(
                    "Need a JDK containing jdk.compiler");
        }

        var api = new Source(
                "lesson.api.Greeter",
                "package lesson.api; "
                + "public interface Greeter { String greet(String name); }"
        );

        var impl = new Source(
                "lesson.impl.Hello",
                "package lesson.impl; "
                + "public class Hello implements lesson.api.Greeter { "
                + "public String greet(String name) { "
                + "return \"Hello, \" + name; } }"
        );

        Map<String, byte[]> apiBytes = new LinkedHashMap<>();
        Map<String, byte[]> missingBytes = new LinkedHashMap<>();
        Map<String, byte[]> implBytes = new LinkedHashMap<>();

        System.out.println(
                "api=" + compile(compiler, api, Map.of(), apiBytes));
        System.out.println(
                "implWithoutApi=" +
                compile(compiler, impl, Map.of(), missingBytes));
        System.out.println(
                "implWithApi=" +
                compile(compiler, impl, apiBytes, implBytes));

        Map<String, byte[]> all = new LinkedHashMap<>(apiBytes);
        all.putAll(implBytes);

        Class<?> type = new MemoryLoader(all).loadClass("lesson.impl.Hello");
        Object instance = type.getConstructor().newInstance();

        System.out.println(
                "result=" +
                type.getMethod("greet", String.class).invoke(instance, "Lan"));
    }
}
```

### 5.2. Biên dịch và chạy

Đứng tại thư mục chứa `MemoryDependencyDemo.java`:

```bash
javac MemoryDependencyDemo.java
java MemoryDependencyDemo
```

Output Java được kỳ vọng và đã kiểm chứng với JDK hiện đại hỗ trợ `--release 17`:

```text
api=true
implWithoutApi=false
implWithApi=true
result=Hello, Lan
```

Chương trình chỉ in kết quả `true/false`; nội dung compiler diagnostics sẽ khác nhau tùy phiên bản JDK nên không đưa vào stdout chuẩn. Hai lớp `lesson.api.Greeter` và `lesson.impl.Hello` thực sự được compile thành bytes trong RAM, không thành các file `.class` cạnh chương trình.

### 5.3. Đọc từng bước

**Bước 1: tạo API.** `compile(compiler, api, Map.of(), apiBytes)` dùng source của `Greeter`. Compiler không cần dependency ứng dụng, nên trả `true` và lưu `lesson.api.Greeter -> byte[]`.

**Bước 2: thiếu API.** `compile(..., impl, Map.of(), missingBytes)` chỉ nhận source `Hello`. Do compiler không thấy `lesson.api.Greeter` từ file manager hoặc runtime classpath của demo, nó không giải được `implements`; kết quả `false`. Ở đây `apiBytes` có dữ liệu nhưng **không được truyền cho task 2**, nên hoàn toàn vô hình đối với nó.

**Bước 3: cấp API từ RAM.** `compile(..., impl, apiBytes, implBytes)` tạo `MemoryManager` với input class `Greeter`. Khi compiler tìm trong package `lesson.api`, `list` đưa ra class ảo, `inferBinaryName` trả đúng tên, và `getJavaFileForInput` có thể cung cấp bytecode khi compiler hỏi theo tên. Compilation thành công, sinh `Hello.class` vào `implBytes`.

**Bước 4: chạy.** `MemoryLoader` nhận cả `apiBytes` lẫn `implBytes`; JVM có thể định nghĩa `Greeter` và `Hello` trong cùng một loader. Reflection tạo instance và gọi `greet("Lan")`. Khi chỉ đưa `Hello` cho runtime loader mà bỏ `Greeter`, runtime vẫn có thể lỗi liên kết kiểu dù compile đã thành công.

**Ranh giới của ví dụ:** `MemoryManager` minh họa một use case classpath đơn giản. Nó không tự giải quyết annotation processing phức tạp, compilation với `module-info.java`, package conflicts, classloader isolation giữa nhiều tenant, hay vòng đời plugin production. Đây là cơ chế chuẩn cần mở rộng theo nhu cầu, không phải một framework hot-reload hoàn chỉnh.

## 6. Cách đơn giản hơn nếu tất cả source được tạo cùng lúc

Nếu `Greeter` và `Hello` đều là chuỗi nguồn trong RAM và **không cần compile qua hai giai đoạn độc lập**, hãy truyền cả hai cho cùng một task:

```java
JavaCompiler.CompilationTask task = compiler.getTask(
        null,
        manager,
        diagnostics,
        List.of("--release", "17", "-proc:none"),
        null,
        List.of(apiSource, implementationSource));

boolean ok = Boolean.TRUE.equals(task.call());
```

Đây là đoạn **minh họa** đặt trong phương thức đã chuẩn bị `compiler`, `manager`, `diagnostics`, `apiSource` và `implementationSource`. Vì compiler nhận toàn bộ source trong cùng compilation unit set, nó có thể phân giải tham chiếu giữa các kiểu thông qua source hiện có. Không cần biến kết quả task trước thành input dependency.

Tuy nhiên, nếu tên class/package được sinh động và phụ thuộc lẫn nhau giữa nhiều đợt, bạn nên thiết kế **dependency graph** rõ ràng: compile các kiểu API/nền trước; cung cấp chúng cho các task sau; phát hiện chu trình hoặc gộp các kiểu có chu trình vào cùng task. Không giả định kết quả compiler tự lan truyền qua các task riêng biệt.

## 7. Dùng dependency trên ổ đĩa/JAR thay vì RAM

Nếu dependency đã được biên dịch và đóng gói thành JAR hoặc thư mục class, `StandardJavaFileManager` có thể quản lý compile classpath. Đoạn minh họa:

```java
try (StandardJavaFileManager manager =
             compiler.getStandardFileManager(
                     diagnostics, Locale.ROOT, StandardCharsets.UTF_8)) {

    manager.setLocationFromPaths(
            StandardLocation.CLASS_PATH,
            List.of(Path.of("libs/api.jar"), Path.of("build/classes/java/main")));

    var task = compiler.getTask(
            null, manager, diagnostics,
            List.of("--release", "17", "-proc:none"),
            null, List.of(sourceObject));

    boolean success = Boolean.TRUE.equals(task.call());
}
```

Đây là **snippet**, không phải chương trình độc lập. Nó yêu cầu có các biến `compiler`, `diagnostics`, `sourceObject` và các đường dẫn dependency thực tế; cần import `java.nio.file.Path`, `java.util.List` cùng `javax.tools.*`. Với classpath trong file manager, javac sẽ tìm input ở những JAR/thư mục được cấu hình. `sourceObject` vẫn có thể nằm trong RAM; output cũng có thể được thu vào RAM nếu bọc manager bằng `ForwardingJavaFileManager` như ví dụ chính.

Có thể dùng option `"--class-path", <chuỗi-đường-dẫn>` thay thế, với dấu phân cách hệ điều hành thích hợp (`File.pathSeparator`). **Đừng trộn hai cách cấu hình một cách khó kiểm soát**. Nếu cần nhiều dependency, kiểm tra chúng đã có đủ các transitive dependencies chưa, phiên bản classfile tương thích compiler và các package không trùng không mong muốn.

### 7.1. Gradle và Maven

Trong dự án thực, để hạn chế sai khác giữa máy developer và CI:
- **Gradle:** khai báo dependency trên cấu hình đúng (`implementation`, `compileOnly` hoặc các cấu hình dành cho plugin/compiler) rồi đưa **đường dẫn được Gradle resolve** vào compiler khi gọi nhúng `JavaCompiler`. Việc code chạy trong Gradle không tự bảo đảm `ToolProvider.getSystemJavaCompiler()` có cùng compile classpath với task `JavaCompile`.
- **Maven:** dùng dependencies/plugin configuration để xác định những artifact có trên compile path; nếu ứng dụng chủ động gọi Compiler API tại runtime, chính ứng dụng cần nhận classpath/module path cho compilation task đó.
- **Không xây classpath bằng cách quét bừa toàn bộ process:** điều này có thể khiến compile phụ thuộc những JAR tình cờ có trên máy, gây khác biệt giữa local và production.
- **Khi source phải chạy trên Java release cụ thể:** dùng `--release` để khóa API nền tảng và bytecode, nhưng lưu ý `--release` **không** xác minh một dependency bên thứ ba được biên dịch ở release cao hơn.

## 8. Compile-time classpath khác runtime ClassLoader

Giả sử plugin có `PluginApi` và `PluginImpl`. Compiler được cấp `PluginApi.class` qua một JAR hoặc file manager RAM để kiểm tra chữ ký. Khi ứng dụng muốn tạo `PluginImpl`, runtime loader cũng phải nhìn thấy `PluginApi` ở **cùng identity runtime** với plugin.

| Tình huống | Biên dịch | Khi chạy |
| --- | --- | --- |
| API và implementation cùng task, output đủ | Compiler giải tham chiếu trong source | Loader phải cung cấp cả hai class hoặc có API từ parent. |
| API ở `.class` trong RAM nhưng chưa cung cấp file manager | Compiler không thấy dependency | Runtime loader có thể thấy API, nhưng compile vẫn thất bại. |
| API có trong compiler classpath nhưng không có ở runtime | Compile có thể pass | JVM có thể báo `NoClassDefFoundError` khi liên kết/tải class cần API. |
| API nằm trong hai defining loaders khác nhau | Compile có thể pass với một bản API | Ép kiểu/casting có thể thất bại vì hai `Class<?>` khác identity. |
| API ở parent loader, implementation ở child loader | Compile cần API được cấp đúng | Child có thể delegate sang parent để dùng chung API, nếu loader được cấu hình phù hợp. |

Để tránh duplicate type, hãy giữ **một API contract chung** trong host/parent loader và cho generated implementation dùng đúng API đó. Không đóng gói lại cùng FQCN API vào classloader của plugin rồi kỳ vọng ép kiểu sang bản API ở host.

Ví dụ dùng API được host định nghĩa:

```java
ClassLoader parent = PluginApi.class.getClassLoader();
ClassLoader generatedLoader = new GeneratedClassLoader(parent, classes);
```

Đây chỉ là minh họa kiến trúc: `PluginApi` và `GeneratedClassLoader` là các kiểu do ứng dụng tự định nghĩa. `ClassLoader` chỉ giải quyết **runtime visibility**; khi compile implementation, file manager vẫn phải thấy `PluginApi` từ source/classpath/module path phù hợp.

**Không nhầm `getClassLoader(Location)` của `JavaFileManager` với việc cấp toàn bộ compiler dependencies:** API đó còn được dùng cho classloader của công cụ như annotation processors và có vai trò riêng. Trả một loader từ `getClassLoader` không thay thế việc hỗ trợ `getJavaFileForInput`/`list` để javac phân giải các kiểu source/classpath.

## 9. Module path, JPMS và các lớp truy cập

Nếu mã sinh là **named module** (`module-info.java`), compiler còn xét:
- `module-info.java` với `requires` đến dependency module.
- `exports` của package API được truy cập từ module khác.
- Module path và việc resolve module trên location phù hợp.
- Bản sao module/class không xung đột và các module có thể đọc nhau.

Ví dụ đơn giản về hợp đồng module:

```java
module lesson.generated {
    requires lesson.api;
}
```

Đây là **một snippet `module-info.java`**, chỉ hợp lệ khi có named module `lesson.api` cung cấp package cần thiết và module path được cấu hình đúng. Đối với SPI hoặc reflection xuyên module, `uses`/`provides`, `opens` hoặc quyền truy cập module có thể cần thiết tùy tình huống.

**Đừng tự đưa mọi bytes ở named module vào `StandardLocation.CLASS_PATH` rồi coi như đã giải quyết JPMS.** File manager cần biểu diễn module locations khi compiler sử dụng module path; runtime có thể cần một `ModuleLayer` tương ứng. Ví dụ đầy đủ ở mục 5 **cố ý dùng unnamed-module/classpath** để tập trung vào dependency của mã sinh trong bộ nhớ.

## 10. Nhìn thấy kiểu và visibility của thành viên là hai chuyện khác nhau

Có file `lesson.api.Greeter.class` trong compile classpath không đồng nghĩa với việc code ở mọi package đều truy cập được mọi class/member.

Java vẫn kiểm tra:
- Class top-level `public` hay package-private.
- Method/constructor `public`, `protected`, package-private hay `private`.
- Tương thích kiểu của generic, overload và khả năng assign.
- `exports`/`requires` khi dùng named modules.

Ví dụ:

```java
package lesson.api;

class InternalHelper {
    static String version() {
        return "v1";
    }
}
```

Nếu `lesson.impl.Hello` ở package khác cố gọi `lesson.api.InternalHelper.version()`, compiler có thể tìm thấy classfile nhưng **vẫn báo lỗi truy cập** vì class không `public`. Đây không phải lỗi thiếu classpath; phải sửa thiết kế API/visibility phù hợp, không “hack” file manager để bỏ qua quy tắc ngôn ngữ.

Một tình huống khác là tên lớp được resolve đúng nhưng runtime loader không thể định nghĩa dependency. Compile thành công chưa chứng minh runtime binary compatibility; cần kiểm tra sau khi tải/liên kết class.

## 11. Diagnostics, phiên bản mã sinh và khả năng tái lập

Khi compile động, đừng chỉ trả về `boolean` mà không có thông tin lỗi. `DiagnosticCollector<JavaFileObject>` thu các chẩn đoán bao gồm `kind`, `code`, `lineNumber`, `columnNumber`, message. Một đoạn dùng sau `task.call()`:

```java
for (var diagnostic : diagnostics.getDiagnostics()) {
    System.err.printf(
        "%s %s:%d:%d %s%n",
        diagnostic.getKind(),
        diagnostic.getSource() == null ? "(unknown)" :
                diagnostic.getSource().getName(),
        diagnostic.getLineNumber(),
        diagnostic.getColumnNumber(),
        diagnostic.getMessage(Locale.ROOT)
    );
}
```

Snippet này nằm trong phương thức có biến `diagnostics`. Với code thật, nên phân loại lỗi **không tìm thấy dependency**, **không truy cập được member**, **lỗi cú pháp**, **unsupported release**, **lỗi hệ file manager**; không chỉ đưa ra lời khuyên “thêm import”.

Các lựa chọn đáng cố định:
- `--release 17` (hoặc target release của ứng dụng) để giới hạn ngôn ngữ/bytecode/JDK API.
- Compile classpath/module path từ danh sách dependency đã resolve có version ổn định.
- Danh sách source, tên binary name và package không xung đột.
- Encoding rõ ràng (`StandardCharsets.UTF_8` ở file manager).
- Annotation processing rõ ràng: trong demo dùng `-proc:none` để không chạy processor từ classpath; production có thể cần processor được chọn có kiểm soát.
- Một tác vụ biên dịch có thể có nhiều file output, gồm inner class như `Outer$Inner.class`; file manager nên lưu theo **tên binary đầy đủ**, không chỉ theo tên source ban đầu.

Nếu API bytes dùng lại từ cache, key của cache nên xét **source content + compiler/release/options + dependency versions**. Cache chỉ theo tên class có thể cấp bytecode stale hoặc không tương thích khi kiểu phụ thuộc đổi chữ ký.

## 12. Bảng lỗi thường gặp

| Biểu hiện | Nguyên nhân khả dĩ | Cách kiểm tra/sửa |
| --- | --- | --- |
| `package lesson.api does not exist` | Compiler không thấy source/classfile của API | Cung cấp API cùng compilation task, hoặc classpath/file manager input hợp lệ. |
| `cannot find symbol: class Greeter` | Tên/package sai, thiếu dependency, hoặc symbol không truy cập được | Đọc diagnostics, kiểm tra FQCN/visibility/module exports. |
| Compile lượt 1 pass, lượt 2 fail | Bytecode lượt 1 chỉ nằm trong output Map | Truyền bytes vào file manager **đầu vào** của lượt 2. |
| Override `getJavaFileForInput` nhưng vẫn không tìm thấy | Compiler còn cần liệt kê package/class | Bổ sung `list` và `inferBinaryName` phù hợp file manager của bạn. |
| Compile pass, `ClassNotFoundException` khi gọi `loadClass` | Runtime loader không tìm thấy class theo tên | Xác minh map bytes/JAR và parent delegation. |
| Compile pass, `NoClassDefFoundError` khi link | Dependency không có lúc runtime, hoặc class không thể được định nghĩa | Đưa đúng dependency vào loader/runtime, kiểm tra cause. |
| `ClassCastException` giữa hai interface cùng FQCN | Interface được định nghĩa bởi hai class loader khác nhau | Chia sẻ contract từ loader thống nhất; tránh copy API. |
| `IllegalAccessError` hoặc access problem | Thành viên/package không cho phép truy cập trong runtime | Kiểm tra Java access control và JPMS export/open phù hợp. |
| `UnsupportedClassVersionError` | Bytes được compile cho Java release cao hơn JVM chạy | Đặt `--release` đúng target; chạy test với JVM target. |
| Lỗi thất thường sau khi thay source | Cache bytecode cũ/loader cũ được giữ lại | Phiên bản hóa cache, tạo loader/layer mới theo vòng đời, không giả định JVM redefine class hiện có. |
| `ToolProvider.getSystemJavaCompiler() == null` | Runtime image không có module compiler | Dùng JDK hoặc image có `jdk.compiler`, hoặc thiết kế compiler service riêng. |
| Hai task dùng chung mutable manager và lỗi race | Trạng thái output/dependency bị thay đổi đồng thời | Tạo manager/task riêng cho mỗi compilation; đồng bộ map/cache đúng cách. |

## 13. Checklist tích hợp production

1. **Xác định graph kiểu phụ thuộc:** các class sinh dùng interface/DTO nào, nguồn API là Java source, JAR hay RAM?
2. **Quyết định compilation batches:** gộp source phụ thuộc nhau vào cùng task khi đơn giản; khi compile nhiều đợt, xuất bản snapshot dependency bytes sau mỗi lần thành công.
3. **Xây file manager đọc và ghi rõ ràng:** phân biệt source input, classfile input, output; giữ đúng binary names/package/module locations.
4. **Khóa target và dependency versions:** compiler version, `--release`, classpath/module path, encoding, processor config; chống cache stale.
5. **Kiểm soát lỗi:** thu diagnostics; xử lý missing type, access lỗi, configuration failure; không dùng class outputs chưa hoàn chỉnh sau compile fail.
6. **Chuẩn bị runtime loader:** cho generated code thấy cùng API contract như host; quản lý cache/loader lifetime, tránh rò rỉ memory.
7. **Chạy smoke test thực sự:** compile các class có dependency, load chúng bằng loader dự kiến, khởi tạo và gọi một method; kiểm tra trường hợp thiếu dependency và class trùng.
8. **Giới hạn code không tin cậy:** compile không tương đương sandbox. Annotation processor có thể thực thi trong compilation; tải/chạy generated bytecode có quyền process. Cần môi trường cách ly nếu source không đáng tin.
9. **Lưu ý đa luồng:** không mặc định `JavaCompiler.CompilationTask` hay custom file manager giữ mutable maps là thread-safe; tách vòng đời task và đồng bộ dữ liệu chia sẻ.
10. **Giữ mức trừu tượng hợp lý:** với plugin ổn định có thể dùng JAR trên classpath/module path; chỉ phát triển in-memory compiler/file manager khi có lợi ích thật về động học, latency hoặc vòng đời nội dung.

## 14. Câu hỏi tự kiểm tra

**Câu 1.** Đã biên dịch `A` ra `byte[]` và cất trong `Map`. Khi biên dịch `B extends A` bằng `JavaCompiler` task mới, `B` sẽ tự tìm thấy `A` chứ?

**Đáp án:** Không. Phải cấp `A` như source trong task hoặc classfile input từ `JavaFileManager`/classpath/module path.

**Câu 2.** Chỉ override `getJavaFileForOutput` của `ForwardingJavaFileManager` đủ để compiler sau nhìn thấy output trước không?

**Đáp án:** Không. Nó quản lý output. Để cung cấp input class ở RAM, cần hỗ trợ truy vấn tìm kiếm phù hợp như `getJavaFileForInput`, `list`, `inferBinaryName`.

**Câu 3.** Compiler thấy `Greeter.class` qua file manager và biên dịch `Hello` thành công. Tại sao chạy có thể còn lỗi?

**Đáp án:** Runtime loader có thể thiếu bytes của `Greeter`/`Hello`, dùng sai API identity hoặc thiếu dependency khác. Compile-time visibility không đảm bảo runtime visibility.

**Câu 4.** Hai classloader định nghĩa riêng class có cùng tên `lesson.api.Greeter`. Có thể coi đó là cùng kiểu vì tên như nhau không?

**Đáp án:** Không. JVM phân biệt theo tên binary và defining loader; cần dùng chung service/API contract khi giao tiếp.

**Câu 5.** Khi có `module-info.java` và dependency named module, chỉ thêm bytes vào `CLASS_PATH` có đủ không?

**Đáp án:** Không nhất thiết. Compiler và runtime còn phải tuân thủ module path, `requires`, `exports` và module layer phù hợp.

## 15. Tài liệu tham khảo chính thức

- [Java SE 17 — JavaCompiler](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/JavaCompiler.html): `getTask`, source units, diagnostics và file manager.
- [Java SE 17 — JavaFileManager](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/JavaFileManager.html): các API tìm `JavaFileObject` và class input/output.
- [Java SE 17 — ForwardingJavaFileManager](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/ForwardingJavaFileManager.html): decorator cho manager chuẩn.
- [Java SE 17 — StandardJavaFileManager](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/StandardJavaFileManager.html): đường tìm kiếm classpath/module path và các input file.
- [Java SE 17 — ToolProvider](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/ToolProvider.html): compiler hệ thống.
- [Java SE 17 — ClassLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html): nạp class, parent delegation và định nghĩa runtime type.
