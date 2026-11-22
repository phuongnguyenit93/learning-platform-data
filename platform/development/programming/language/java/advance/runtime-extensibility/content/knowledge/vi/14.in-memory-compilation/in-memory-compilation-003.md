# Quản lý nhiều lớp đầu ra, lớp lồng nhau và tên nhị phân khi biên dịch Java trong bộ nhớ

## 1. Một nguồn Java có thể tạo nhiều tệp class

JavaCompiler API (`javax.tools`) hỗ trợ compile mã nguồn trong bộ nhớ. Một compilation unit chứa `Outer` có thể tạo ra `Outer.class`, `Outer$Nested.class`, `Outer$Inner.class`, `Outer$1.class` và các class top-level khác. Vì thế không thể giả định mỗi source trả đúng một byte array. Một file manager đúng phải nhận **mọi callback `getJavaFileForOutput`** và lưu từng output dưới **binary name** do compiler cung cấp.

Phân biệt các tên:

| Đối tượng | Source/canonical name | Binary name | Đường dẫn JAR |
| --- | --- | --- | --- |
| Top-level | `demo.Outer` | `demo.Outer` | `demo/Outer.class` |
| Static nested | `demo.Outer.Nested` | `demo.Outer$Nested` | `demo/Outer$Nested.class` |
| Non-static inner | `demo.Outer.Inner` | `demo.Outer$Inner` | `demo/Outer$Inner.class` |
| Anonymous class | Không có canonical name | Có thể `demo.Outer$1` với javac | `demo/Outer$1.class` |

Không đoán suffix của local/anonymous classes; tên binary là kết quả của compiler, không phải chính sách đặt tên của ứng dụng. `ClassLoader.loadClass` và `Class.forName` nhận **binary name**, không nhận canonical name của nested class.

## 2. Kiến trúc file manager và classloader

```text
JavaFileObject SOURCE
        |
        v
JavaCompiler.getTask(...).call()
        |
        v
ForwardingJavaFileManager.getJavaFileForOutput
        | mỗi className, Kind.CLASS
        v
Map<String, byte[]> (binaryName -> class bytes)
        |
        v
MemoryClassLoader.findClass(binaryName)
        |
        v
defineClass(binaryName, bytes, 0, bytes.length)
```

File manager cần tạo `ByteArrayOutputStream` **riêng** cho từng `className`. Khi compile thất bại, không publish các bytecode partial. Khi compile thành công, snapshot toàn bộ map, truyền cho loader mới. Giữ API chung ở parent loader để không vô tình nạp trùng interface SPI.

## 3. Ví dụ Java 17+ đầy đủ

Tạo file `MemoryCompilerExample.java`. Ví dụ biên dịch một source chứa top-level, nested, inner và anonymous class; lưu các binary names; load và gọi method bằng reflection.

```java
import javax.tools.*;
import java.io.ByteArrayOutputStream;
import java.io.OutputStream;
import java.net.URI;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;

public final class MemoryCompilerExample {
    static final class Source extends SimpleJavaFileObject {
        private final String code;
        Source(String name, String code) {
            super(URI.create("string:///" + name.replace('.', '/')
                    + Kind.SOURCE.extension), Kind.SOURCE);
            this.code = code;
        }
        @Override
        public CharSequence getCharContent(boolean ignoreEncodingErrors) {
            return code;
        }
    }

    static final class Output extends SimpleJavaFileObject {
        private final ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        Output(String binaryName, Kind kind) {
            super(URI.create("mem:///" + binaryName.replace('.', '/')
                    + kind.extension), kind);
        }
        @Override
        public OutputStream openOutputStream() {
            return bytes;
        }
        byte[] bytes() {
            return bytes.toByteArray();
        }
    }

    static final class Manager
            extends ForwardingJavaFileManager<StandardJavaFileManager> {
        private final Map<String, Output> outputs = new TreeMap<>();
        Manager(StandardJavaFileManager delegate) {
            super(delegate);
        }
        @Override
        public JavaFileObject getJavaFileForOutput(
                JavaFileManager.Location location, String className,
                JavaFileObject.Kind kind, FileObject sibling) {
            if (kind != JavaFileObject.Kind.CLASS) {
                throw new IllegalArgumentException("Unexpected kind: " + kind);
            }
            if (outputs.containsKey(className)) {
                throw new IllegalStateException("Duplicate output: " + className);
            }
            Output output = new Output(className, kind);
            outputs.put(className, output);
            return output;
        }
        Map<String, byte[]> snapshot() {
            Map<String, byte[]> result = new TreeMap<>();
            outputs.forEach((name, output) -> result.put(name, output.bytes()));
            return result;
        }
    }

    static final class Loader extends ClassLoader {
        private final Map<String, byte[]> classes;
        Loader(ClassLoader parent, Map<String, byte[]> classes) {
            super(parent);
            this.classes = Map.copyOf(classes);
        }
        @Override
        protected Class<?> findClass(String binaryName)
                throws ClassNotFoundException {
            byte[] bytes = classes.get(binaryName);
            if (bytes == null) throw new ClassNotFoundException(binaryName);
            return defineClass(binaryName, bytes, 0, bytes.length);
        }
    }

    public static void main(String[] args) throws Exception {
        String code = """
                package demo;
                public class Outer {
                    public static class Nested {
                        public static String value() { return "nested"; }
                    }
                    public class Inner {
                        public String value() { return "inner"; }
                    }
                    public static String anonymous() {
                        Runnable r = new Runnable() {
                            public void run() {}
                        };
                        r.run();
                        return "anonymous";
                    }
                }
                """;

        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException("JDK compiler unavailable");
        }
        DiagnosticCollector<JavaFileObject> diagnostics =
                new DiagnosticCollector<>();
        Map<String, byte[]> bytes;
        try (StandardJavaFileManager standard =
                     compiler.getStandardFileManager(diagnostics, null, null);
             Manager manager = new Manager(standard)) {
            boolean ok = Boolean.TRUE.equals(
                    compiler.getTask(null, manager, diagnostics,
                            List.of("--release", "17"), null,
                            List.of(new Source("demo.Outer", code))).call());
            if (!ok) {
                diagnostics.getDiagnostics().forEach(System.err::println);
                throw new IllegalStateException("Compilation failed");
            }
            bytes = manager.snapshot();
        }

        System.out.println("Outputs:");
        bytes.keySet().forEach(System.out::println);
        Loader loader = new Loader(
                MemoryCompilerExample.class.getClassLoader(), bytes);
        Class<?> outer = loader.loadClass("demo.Outer");
        Class<?> nested = loader.loadClass("demo.Outer$Nested");
        Class<?> inner = loader.loadClass("demo.Outer$Inner");
        System.out.println("Nested: " +
                nested.getMethod("value").invoke(null));
        System.out.println("Anonymous: " +
                outer.getMethod("anonymous").invoke(null));
        Object outerObject = outer.getConstructor().newInstance();
        Object innerObject = inner.getConstructor(outer)
                .newInstance(outerObject);
        System.out.println("Inner: " +
                inner.getMethod("value").invoke(innerObject));
    }
}
```

Biên dịch và chạy với JDK 17+ (không chỉ runtime thiếu `jdk.compiler`):

```bash
javac --release 17 MemoryCompilerExample.java
java MemoryCompilerExample
```

Output dự kiến với `javac` của JDK 17:

```text
Outputs:
demo.Outer
demo.Outer$1
demo.Outer$Inner
demo.Outer$Nested
Nested: nested
Anonymous: anonymous
Inner: inner
```

`TreeMap` làm danh sách output có thứ tự ổn định khi in, **không phải** compiler bảo đảm thứ tự callback. Tên `demo.Outer$1` là kết quả với source này trên `javac`, không phải tên nên đoán khi sinh code. Class `Outer$Inner` nhận outer instance như tham số constructor tổng hợp, khác với static nested class.

## 4. Những bất biến cần giữ khi có nhiều class output

### Một callback, một output độc lập

Mỗi lần compiler gọi `getJavaFileForOutput(location, className, kind, sibling)`, cần trả một `JavaFileObject` có stream độc lập. Nếu bạn chỉ lưu `lastOutput`, bytecode trước đó bị mất, dẫn tới `NoClassDefFoundError` khi outer class tham chiếu inner/anonymous class.

### Binary name là key, không phải source filename

Map nên mang dạng `Map<String, byte[]>` với key như `demo.Outer$Inner`. Không dùng key `Outer.java`, không thay `$` bằng `.` và không tự tạo tên `$1`. `defineClass` phải được gọi với binary name phù hợp với tên thực trong bytecode; nếu sai, JVM có thể báo `NoClassDefFoundError: wrong name`.

### Publish sau thành công

`CompilationTask.call()` trả `Boolean`: `false` nghĩa biên dịch thất bại. Một số `.class` có thể đã được xuất ra trước khi lỗi xảy ra; đây là tập partial và **không nên publish**. Collect diagnostics, bỏ collector, để lần compile mới dùng trạng thái mới.

### Class identity và phiên bản

Một class runtime được định danh bởi binary name cùng defining classloader. Không `defineClass` lần hai với cùng tên trong cùng loader; thường nhận `LinkageError`. Muốn nạp phiên bản mới với cùng binary name, dùng **loader mới** và chuyển registry/instance có kiểm soát. Parent loader nên giữ service API chung để plugin class có thể được cast sang SPI interface.

## 5. Compile nhiều source units và nhiều lượt

Đầu vào của `JavaCompiler.getTask` có thể là nhiều `JavaFileObject.Kind.SOURCE`. Một task chứa `demo.A` và `demo.B` có thể tạo `demo.A`, `demo.A$Nested`, `demo.B`, cùng các class phụ khác. Collector phải nhận tất cả outputs từ cả task, không lọc theo tên main source.

Với nhiều lượt biên dịch liên tiếp, nếu lượt sau phụ thuộc bytecode chỉ tồn tại trong memory của lượt trước, việc override `getJavaFileForOutput` **chưa đủ**. Compiler cần tìm input classes: file manager có thể phải triển khai `list`, `getJavaFileForInput`, `inferBinaryName` và API liên quan để cung cấp classpath/module path trong bộ nhớ. Runtime `MemoryClassLoader` không tự khiến JavaCompiler nhìn thấy mọi class đã nạp.

Với annotation processing, compiler còn có thể sinh source mới và class outputs mới. Không giả định số lượng outputs biết trước hoặc chỉ có những class xuất hiện tường minh trong source ban đầu.

## 6. Đóng gói và lưu bytecode

Muốn xuất map bytecode thành JAR, chuyển binary name sang resource path: thay `.` của package bằng `/`, **giữ `$` nguyên** rồi nối `.class`. Ví dụ:

```text
demo.Outer        -> demo/Outer.class
demo.Outer$Inner  -> demo/Outer$Inner.class
demo.Outer$1      -> demo/Outer$1.class
```

Ví dụ đoạn code trong method có `classes: Map<String, byte[]>` và `jarPath: Path`:

```java
try (java.util.jar.JarOutputStream output =
        new java.util.jar.JarOutputStream(
                java.nio.file.Files.newOutputStream(jarPath))) {
    for (var entry : classes.entrySet()) {
        String path = entry.getKey().replace('.', '/') + ".class";
        output.putNextEntry(new java.util.jar.JarEntry(path));
        output.write(entry.getValue());
        output.closeEntry();
    }
}
```

Nếu dùng SPI, JAR còn cần `META-INF/services/<service FQCN>` hoặc JPMS module metadata đúng kiến trúc. Chỉ lưu `.class` chưa đủ nếu plugin cần resource files, manifest hay descriptor.

## 7. Lỗi phổ biến và cách chẩn đoán

| Triệu chứng | Nguyên nhân thường gặp | Cách sửa |
| --- | --- | --- |
| `ClassNotFoundException` với `demo.Outer.Inner` | Dùng canonical name | Gọi `loadClass("demo.Outer$Inner")` |
| `NoClassDefFoundError` cho `Outer$1` | Collector không lưu anonymous output | Lưu mọi callback output |
| `NoClassDefFoundError: wrong name` | Key khác binary name trong bytecode | Lấy đúng `className` từ compiler |
| `LinkageError` duplicate definition | Define lại cùng class trong loader | Dùng loader mới khi rebuild |
| `ClassCastException` sang SPI | Plugin loader tự định nghĩa API trùng | Chia sẻ API qua parent |
| Compiler lượt sau không thấy class cũ | Chỉ có output manager, không có input support | Bổ sung in-memory input lookup |
| Thất bại nhưng vẫn có `.class` partial | Publish map trước khi kiểm tra `call()` | Chỉ publish khi compile thành công |
| Memory tăng sau nhiều lần compile | Host giữ reference tới loader cũ | Dọn lifecycle và reference |

## 8. Checklist triển khai

- [ ] Kiểm tra có system compiler; dùng JDK phù hợp.
- [ ] Source URI đúng binary name top-level và đuôi `.java`.
- [ ] Ghi mọi `getJavaFileForOutput` theo `className`, mỗi output có stream riêng.
- [ ] Không đoán tên inner/local/anonymous class.
- [ ] Snapshot output chỉ sau compile thành công.
- [ ] Nạp toàn bộ output bằng một loader nhất quán; giữ SPI chung ở parent.
- [ ] Tạo loader mới cho phiên bản class mới khi trùng tên.
- [ ] Nếu compile nhiều lượt có dependency trong memory, hỗ trợ class input lookup.
- [ ] Khi xuất JAR, giữ `$` trong entry name và bổ sung resources/SPI metadata.
- [ ] Viết test cho outer, nested, inner, anonymous class và error diagnostics.
- [ ] Không coi compile trong bộ nhớ là sandbox: code chạy với quyền JVM host.

**Kết luận:** một compilation unit Java có thể tạo nhiều `.class`, nên output unit không phải source file mà là **class với binary name cụ thể**. Lưu tất cả bytes từ compiler theo đúng tên, đưa chúng vào một classloader phù hợp và quản lý phiên bản/diagnostics cẩn thận giúp tránh lỗi thiếu class, sai tên hoặc xung đột định nghĩa.
