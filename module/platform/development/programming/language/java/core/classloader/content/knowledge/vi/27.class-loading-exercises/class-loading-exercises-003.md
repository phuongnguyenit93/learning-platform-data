# Xây dựng ClassLoader nạp bytecode trực tiếp từ bộ nhớ

## 1. Mục tiêu bài thực hành

Một `ClassLoader` không bắt buộc phải lấy định nghĩa lớp từ file `.class` trên ổ đĩa, từ JAR hay qua URL. JVM cần một **mảng byte biểu diễn class file hợp lệ**, tên class phù hợp và một defining loader có quyền định nghĩa class. Nguồn của các bytes có thể là:

- Kết quả biên dịch source Java ngay trong chương trình bằng `JavaCompiler`.
- Bytecode do bộ sinh mã (bytecode generator) tạo.
- Một artifact được đọc và kiểm tra rồi giữ trong memory cache.
- Bytes được truyền qua IPC/network hoặc đọc từ một kho dữ liệu (nếu ứng dụng tin cậy nguồn đó và có chính sách xác minh phù hợp).

Trọng tâm là tự xây dựng loader kiểu **map binary name → byte[]** để class được định nghĩa từ bộ nhớ bằng protected `ClassLoader.defineClass`. Sau đó ghép loader với `javax.tools.JavaCompiler` để tạo một ví dụ **biên dịch và nạp hoàn toàn trong RAM**, không cần ghi file `Hello.class` lên đĩa.

Bài thuộc nhóm **Thực hành** của module *Java core – classloader*. Sau bài này, bạn có thể:

1. Viết subclass `MemoryLoader extends ClassLoader` và override `findClass(String)` đúng cách.
2. Biên dịch source Java thành `byte[]` bằng `JavaCompiler` và custom `JavaFileManager`.
3. Đưa bytes vào map và gọi `loadClass` để tạo runtime `Class<?>`.
4. Dùng reflection/contract chung để tạo object và gọi method.
5. Kiểm chứng việc **load cùng tên trên cùng loader** trả cùng class, còn **hai loaders khác nhau** có thể tạo hai runtime types khác nhau.
6. Phân biệt **nạp từ bộ nhớ** với chuyện **công bố resource `.class` qua `getResource`**.
7. Xử lý đúng `ClassNotFoundException`, `LinkageError`, classfile version, parent delegation, initialization và nguy cơ memory leak.
8. Biết giới hạn của bài demo so với production, nơi bytecode phải được xác minh và vòng đời classloader được quản lý.

**Phiên bản:** Java 17 trở lên. Ví dụ không cần Maven/Gradle, Internet, JAR bên ngoài hay API không công khai của JDK. Chương trình đầy đủ đã được biên dịch bằng `javac --release 17` và chạy thực tế.

## 2. Hiểu đúng “nạp bytecode từ bộ nhớ”

### 2.1. Source → byte[] → runtime Class

Một luồng thông thường:

~~~text
Hello.java
  |
  | javac
  v
Hello.class trên disk
  |
  | ClassLoader đọc file/JAR
  v
byte[] classfile
  |
  | defineClass
  v
Class<?> trong JVM
~~~

Trong bài này ta thay bằng:

~~~text
Java source nằm trong String
  |
  | JavaCompiler (JSR 199)
  v
JavaFileObject chứa ByteArrayOutputStream
  |
  | snapshot()
  v
Map<String,byte[]> trong RAM
  |
  | MemoryLoader.findClass(name)
  | -> defineClass(name, bytes, 0, bytes.length)
  v
Class<?> trong JVM
  |
  | Reflection
  v
Instance + method invocation
~~~

Điểm khác biệt là **bytes đầu vào được giữ trong map và chuyển thẳng cho `defineClass`**. Không có bước tạo file `memory/generated/Hello.class` trên disk. Tuy nhiên Java VM vẫn tạo thông tin class ở runtime, gồm metadata/linking structures, và có thể phát sinh mã native/JIT theo hoạt động bình thường.

**“Từ bộ nhớ” không đồng nghĩa “không có metadata, không có memory footprint, không có kiểm tra an toàn JVM”.**

### 2.2. Binary name khác resource path

Nếu source khai báo:

~~~java
package memory.generated;

public final class Hello {
    public String greet(String person) {
        return "MEMORY:" + person;
    }
}
~~~

thì:

- **Binary name:** `memory.generated.Hello`.
- **Resource path thông thường:** `memory/generated/Hello.class`.
- **Source path biểu diễn trong công cụ biên dịch:** `memory/generated/Hello.java`.
- **Runtime class identity:** phụ thuộc **binary name + defining ClassLoader**, không chỉ chuỗi tên.

Map của loader nên dùng binary names làm key:

~~~java
Map<String, byte[]> compiled = Map.of(
    "memory.generated.Hello", classfileBytes);
~~~

Đây là snippet minh họa, cần có biến `classfileBytes` chứa bytecode classfile thật. Nếu vô tình dùng key `memory/generated/Hello.class` rồi gọi `loadClass("memory.generated.Hello")`, lookup map sẽ không khớp.

### 2.3. `ClassLoader.loadClass` và `findClass` không giống nhau

- `loadClass(String)` là entry point công khai thường được caller dùng.
- Implementation mặc định xử lý cache class đã nạp, parent delegation và chỉ gọi `findClass` khi cần.
- `findClass(String)` là hook mà subclass override để **tìm bytes và định nghĩa class do loader mình quản lý**.
- `defineClass(...)` là thao tác thực sự chuyển classfile bytes thành class được JVM định nghĩa cho loader này.

Do đó, bài chỉ cần override **`findClass`**, không cần tự viết lại `loadClass`. Giữ implementation mặc định giúp tận dụng synchronization, `findLoadedClass` và parent delegation để tránh nhiều lỗi khó tái hiện.

## 3. MemoryLoader tối thiểu: phần cốt lõi cần nhớ

Nếu đã có một `Map<String, byte[]>` đáng tin và bất biến sau khi xây dựng, loader chính chỉ cần:

~~~java
import java.util.Map;

final class MemoryLoader extends ClassLoader {
    private final Map<String, byte[]> bytecodes;

    MemoryLoader(Map<String, byte[]> bytecodes, ClassLoader parent) {
        super(parent);
        this.bytecodes = Map.copyOf(bytecodes);
    }

    @Override
    protected Class<?> findClass(String name)
            throws ClassNotFoundException {
        byte[] bytes = bytecodes.get(name);
        if (bytes == null) {
            throw new ClassNotFoundException(name);
        }
        return defineClass(name, bytes, 0, bytes.length);
    }
}
~~~

Đây là **một snippet class hoàn chỉnh về cơ chế nạp**, nhưng chưa có `main` và chưa tạo bytecode. Các bước quan trọng:

1. `MemoryLoader` kế thừa `ClassLoader` với parent được chỉ định.
2. Map dùng binary name → Java classfile bytes.
3. `findClass(name)` tìm mảng bytes.
4. Nếu không có entry, **ném `ClassNotFoundException(name)`** — đừng trả `null`.
5. Nếu có, gọi `defineClass(name, bytes, 0, bytes.length)`.
6. JVM kiểm tra classfile, tên, verification/linking constraints theo hợp đồng và tạo `Class<?>` khi hợp lệ.

**Lưu ý về bất biến:** `Map.copyOf` chỉ copy map structure, **không clone mảng byte[]**. Nếu caller sửa các mảng sau khi cấp loader, sẽ tạo race và hành vi khó dự đoán. Trong production, tạo **defensive copies** của từng byte array tại boundary, không đưa map có thể thay đổi vào code không tin cậy. Trong demo đầy đủ, compiler tạo mảng riêng và không có thread khác chỉnh sửa.

### 3.1. Vì sao không gọi `defineClass` trực tiếp từ application code?

`defineClass` là protected API. Đặt lời gọi trong `ClassLoader` subclass là cách được hỗ trợ. Nó không phải public static method kiểu:

~~~java
Class<?> clazz = ClassLoader.defineClass(...);
~~~

Dòng trên là **mã sai có chủ đích**. Bài đầy đủ gọi `defineClass` từ `MemoryLoader.findClass`, sau đó application code gọi `loader.loadClass(binaryName)`.

### 3.2. Vì sao không override `loadClass` ngay từ đầu?

Tự override `loadClass` và luôn `defineClass` rất dễ tạo race hoặc duplicate-definition lỗi:

~~~text
Thread A: findClass("X") -> defineClass X -> thành công
Thread B: findClass("X") -> defineClass X -> LinkageError
~~~

Implementation chuẩn `loadClass` đồng bộ đúng critical section và kiểm tra `findLoadedClass` trước khi dùng hook `findClass`. Nếu bạn cần child-first plugin policy, đó là thiết kế nâng cao đòi hỏi khóa `getClassLoadingLock(name)` và kiểm tra cache/delegation kỹ lưỡng. Không nên đổi policy chỉ để giải quyết bài nạp bytecode trong RAM.

### 3.3. Parent-first có thể “thắng” map của MemoryLoader

Giả sử application loader đã có class `memory.generated.Hello` trên `-cp`. Khi child gọi `loadClass("memory.generated.Hello")`, parent có thể trả class của parent **trước khi `findClass` được gọi**. Kết quả là bạn nghĩ memory map bị bỏ qua nhưng thực ra đó là parent-first delegation đúng thiết kế.

Để tái hiện bài thực hành:

- Chỉ compile **`MemoryLoaderDemo.java`** làm launcher.
- Source `Hello` nằm trong **String**, không có `Hello.class` trên app classpath.
- Gọi `MemoryLoader.loadClass(NAME)` với parent là loader định nghĩa host.
- Đừng vô tình thêm JAR khác cũng có `memory.generated.Hello` lên application classpath.

## 4. Tạo bytecode trong RAM bằng JavaCompiler

### 4.1. `javax.tools.JavaCompiler` là gì?

`ToolProvider.getSystemJavaCompiler()` lấy compiler Java được cung cấp bởi JDK đang chạy:

~~~java
JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
if (compiler == null) {
    throw new IllegalStateException("Run with a JDK, not a JRE");
}
~~~

Trên JDK 17+, công cụ compiler nằm trong module `java.compiler` (API) và implementation/compiler support của JDK (thường module `jdk.compiler`). Nếu chạy với custom runtime image không chứa system compiler, `getSystemJavaCompiler()` có thể trả `null`. Khi đó không thể dùng cách “compile source ở runtime” mà không bổ sung compiler; **MemoryLoader vẫn có thể load bytes đã compile sẵn**.

### 4.2. `JavaFileObject` cho source Java từ String

Thay vì trỏ compiler tới file `.java`, ta tạo `SimpleJavaFileObject` mang một URI giả và trả source string bằng `getCharContent`:

~~~java
static final class SourceFile extends SimpleJavaFileObject {
    final String code;

    SourceFile(String name, String code) {
        super(URI.create("string:///" +
              name.replace('.', '/') + Kind.SOURCE.extension),
              Kind.SOURCE);
        this.code = code;
    }

    @Override
    public CharSequence getCharContent(boolean ignoreEncodingErrors) {
        return code;
    }
}
~~~

Đây là **snippet bên trong class**, cần `URI` và `javax.tools.SimpleJavaFileObject` imports. `string:///...` là **URI đặt tên JavaFileObject**, không phải file cần tồn tại hoặc giao thức mạng thật.

### 4.3. `JavaFileObject` ghi `.class` vào `ByteArrayOutputStream`

Đầu ra của compiler bình thường là file `.class`. Ta thay đích bằng object tự ghi vào RAM:

~~~java
static final class ClassFile extends SimpleJavaFileObject {
    final ByteArrayOutputStream out = new ByteArrayOutputStream();

    ClassFile(String name, Kind kind) {
        super(URI.create("bytes:///" +
              name.replace('.', '/') + kind.extension), kind);
    }

    @Override
    public OutputStream openOutputStream() {
        return out;
    }

    byte[] bytes() {
        return out.toByteArray();
    }
}
~~~

Đây là snippet cần `ByteArrayOutputStream`, `OutputStream`, `URI`, `SimpleJavaFileObject` imports. URI `bytes:///...` chỉ là định danh của compiler output object; mảng bytes thật nằm trong buffer `out`.

### 4.4. Custom JavaFileManager nhận từng class được compile

Một lượt compile có thể phát sinh **nhiều `.class`** từ một source (inner/nested classes, các lớp bổ trợ). Vì vậy không nên chỉ có một biến `byte[] compiledOutput` cho mọi tên. Ta tạo file manager:

~~~java
static final class MemoryFileManager
        extends ForwardingJavaFileManager<StandardJavaFileManager> {
    final Map<String, ClassFile> outputs = new HashMap<>();

    MemoryFileManager(StandardJavaFileManager delegate) {
        super(delegate);
    }

    @Override
    public JavaFileObject getJavaFileForOutput(
            Location location, String className,
            JavaFileObject.Kind kind, FileObject sibling) {
        ClassFile file = new ClassFile(className, kind);
        outputs.put(className, file);
        return file;
    }

    Map<String, byte[]> snapshot() {
        Map<String, byte[]> all = new HashMap<>();
        outputs.forEach((name, file) -> all.put(name, file.bytes()));
        return Map.copyOf(all);
    }
}
~~~

Đây là snippet trong class bao ngoài với imports JavaCompiler/JavaFileManager, HashMap/Map, FileObject, JavaFileObject. `getJavaFileForOutput` được compiler gọi khi muốn ghi class bytes. Ta giữ mỗi output theo **binary class name** do compiler cung cấp.

**Tác dụng thật:** compiler ghi classfile vào RAM, rồi `snapshot()` lấy byte arrays. Trong ví dụ một class `Hello` sẽ có một entry `memory.generated.Hello`; với inner classes còn có thể có `Outer$Inner`.

## 5. Chương trình Java 17+ đầy đủ và chạy được

Ví dụ hoàn chỉnh bên dưới tự compile source `memory.generated.Hello` nằm trong String, dùng `MemoryLoader` để define bytes, gọi method bằng reflection, sau đó nạp cùng bytes trong loader thứ hai.

### 5.1. Cây project

~~~text
memory-loader-demo/
├── MemoryLoaderDemo.java
└── out/
    └── MemoryLoaderDemo*.class  (tạo khi javac launcher)
~~~

Không cần file `Hello.java` và **không có file `Hello.class` trên disk**. Dùng JDK 17+ để chạy chương trình từ một directory bạn có quyền tạo file của launcher; toàn bộ kết quả compile **lớp sinh động `Hello`** ở trong memory.

### 5.2. Tệp `MemoryLoaderDemo.java`

~~~java
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.OutputStream;
import java.net.URI;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import javax.tools.DiagnosticCollector;
import javax.tools.FileObject;
import javax.tools.ForwardingJavaFileManager;
import javax.tools.JavaCompiler;
import javax.tools.JavaFileObject;
import javax.tools.SimpleJavaFileObject;
import javax.tools.StandardJavaFileManager;
import javax.tools.ToolProvider;

public final class MemoryLoaderDemo {
    static final String NAME = "memory.generated.Hello";
    static final String CODE = """
            package memory.generated;
            public final class Hello {
                public String greet(String person) {
                    return "MEMORY:" + person;
                }
            }
            """;

    static final class SourceFile extends SimpleJavaFileObject {
        final String code;
        SourceFile(String name, String code) {
            super(URI.create("string:///" +
                  name.replace('.', '/') + Kind.SOURCE.extension),
                  Kind.SOURCE);
            this.code = code;
        }
        @Override
        public CharSequence getCharContent(boolean ignoreEncodingErrors) {
            return code;
        }
    }

    static final class ClassFile extends SimpleJavaFileObject {
        final ByteArrayOutputStream out = new ByteArrayOutputStream();
        ClassFile(String name, Kind kind) {
            super(URI.create("bytes:///" +
                  name.replace('.', '/') + kind.extension), kind);
        }
        @Override
        public OutputStream openOutputStream() {
            return out;
        }
        byte[] bytes() { return out.toByteArray(); }
    }

    static final class MemoryFileManager
            extends ForwardingJavaFileManager<StandardJavaFileManager> {
        final Map<String, ClassFile> outputs = new HashMap<>();

        MemoryFileManager(StandardJavaFileManager delegate) {
            super(delegate);
        }

        @Override
        public JavaFileObject getJavaFileForOutput(
                Location location, String className,
                JavaFileObject.Kind kind, FileObject sibling) {
            ClassFile file = new ClassFile(className, kind);
            outputs.put(className, file);
            return file;
        }

        Map<String, byte[]> snapshot() {
            Map<String, byte[]> all = new HashMap<>();
            outputs.forEach((name, file) -> all.put(name, file.bytes()));
            return Map.copyOf(all);
        }
    }

    static final class MemoryLoader extends ClassLoader {
        final Map<String, byte[]> bytecodes;

        MemoryLoader(Map<String, byte[]> bytecodes) {
            super(MemoryLoaderDemo.class.getClassLoader());
            this.bytecodes = bytecodes;
        }

        @Override
        protected Class<?> findClass(String name)
                throws ClassNotFoundException {
            byte[] bytes = bytecodes.get(name);
            if (bytes == null) {
                throw new ClassNotFoundException(name);
            }
            return defineClass(name, bytes, 0, bytes.length);
        }
    }

    public static void main(String[] args) throws Exception {
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException("Run with a JDK, not a JRE");
        }

        DiagnosticCollector<JavaFileObject> diagnostics =
                new DiagnosticCollector<>();
        Map<String, byte[]> compiled;

        try (StandardJavaFileManager standard =
                     compiler.getStandardFileManager(
                             diagnostics, null, null);
             MemoryFileManager files = new MemoryFileManager(standard)) {
            boolean ok = compiler.getTask(
                    null, files, diagnostics,
                    List.of("--release", "17", "-proc:none"),
                    null, List.of(new SourceFile(NAME, CODE))).call();
            if (!ok) {
                throw new IllegalStateException(
                        "Compilation failed: " + diagnostics.getDiagnostics());
            }
            compiled = files.snapshot();
        }

        System.out.println("compiledNames=" + compiled.keySet());
        System.out.println("validClassBytes="
                + (compiled.get(NAME).length > 4));

        MemoryLoader first = new MemoryLoader(compiled);
        Class<?> c1 = first.loadClass(NAME);
        System.out.println("definedByMemoryLoader="
                + (c1.getClassLoader() == first));
        System.out.println("repeatedLoadSameClass="
                + (first.loadClass(NAME) == c1));

        Object obj = c1.getDeclaredConstructor().newInstance();
        Object reply = c1.getMethod("greet", String.class)
                         .invoke(obj, "Java");
        System.out.println("result=" + reply);

        MemoryLoader second = new MemoryLoader(compiled);
        Class<?> c2 = second.loadClass(NAME);
        System.out.println("differentLoaderDifferentClass=" + (c1 != c2));
        System.out.println("parentStringShared="
                + (first.loadClass("java.lang.String") == String.class));
        System.out.println("resourceNotAutoPublished="
                + (first.getResource("memory/generated/Hello.class") == null));

        try {
            MemoryLoaderDemo.class.getClassLoader().loadClass(NAME);
            System.out.println("appLoaderFindsGenerated=true");
        } catch (ClassNotFoundException expected) {
            System.out.println("appLoaderFindsGenerated=false");
        }

        try {
            first.loadClass("memory.generated.Absent");
            System.out.println("missingClassRejected=false");
        } catch (ClassNotFoundException expected) {
            System.out.println("missingClassRejected=true");
        }
    }
}
~~~

**Phần cần nhớ:** `ClassFile` được compiler ghi ra trong RAM; `MemoryFileManager.snapshot()` cung cấp map bytes; `MemoryLoader.findClass` là nơi duy nhất gọi `defineClass`. Host không import `memory.generated.Hello` và không có dependency runtime với file `Hello.class`.

### 5.3. Lệnh biên dịch và chạy

Linux/macOS:

~~~sh
mkdir -p out
javac --release 17 -d out MemoryLoaderDemo.java
java -cp out MemoryLoaderDemo
~~~

Windows PowerShell:

~~~powershell
New-Item -ItemType Directory -Force out | Out-Null
javac --release 17 -d out MemoryLoaderDemo.java
java -cp out MemoryLoaderDemo
~~~

**Chú ý về bản JDK:** nguồn sử dụng Java text block (`"""`), API từ Java 9+ và `--release 17`. Phải dùng **JDK 17+ có system JavaCompiler**; một custom runtime image thiếu `jdk.compiler` có thể không chạy được phần compile động.

### 5.4. Stdout chính xác đã kiểm chứng

~~~text
compiledNames=[memory.generated.Hello]
validClassBytes=true
definedByMemoryLoader=true
repeatedLoadSameClass=true
result=MEMORY:Java
differentLoaderDifferentClass=true
parentStringShared=true
resourceNotAutoPublished=true
appLoaderFindsGenerated=false
missingClassRejected=true
~~~

**Kết quả được kiểm chứng bằng chương trình thật**: đầu tiên biên dịch `MemoryLoaderDemo.java` với `javac --release 17`, sau đó chạy bằng `java` trên JDK. Chương trình chỉ compile đúng **một class** trong memory nên thứ tự key của map không gây khác biệt cho dòng đầu.

### 5.5. Phân tích từng dòng output

| Output | Điều kiểm chứng |
|---|---|
| `compiledNames=[memory.generated.Hello]` | Compiler đã trả bytes và file manager lưu theo binary name |
| `validClassBytes=true` | `byte[]` tồn tại và dài hơn header tối thiểu; **không phải phép verify hoàn chỉnh** |
| `definedByMemoryLoader=true` | JVM gán defining loader của generated class bằng instance `first` |
| `repeatedLoadSameClass=true` | `loadClass` trên cùng loader/tên trả lại cùng `Class<?>` sau lần định nghĩa đầu |
| `result=MEMORY:Java` | Reflection đã tạo object và gọi method của generated class |
| `differentLoaderDifferentClass=true` | Hai loader khác nhau định nghĩa hai runtime class identities cùng tên |
| `parentStringShared=true` | Java `String` được parent/bootstrap tìm và cả loader cùng dùng |
| `resourceNotAutoPublished=true` | Lưu bytes trong map **không** tự tạo resource URL `Hello.class` |
| `appLoaderFindsGenerated=false` | Application loader không tự thấy generated class |
| `missingClassRejected=true` | Không có entry tương ứng thì `findClass` ném `ClassNotFoundException` |

Ba kiểm chứng `definedByMemoryLoader`, `repeatedLoadSameClass` và `differentLoaderDifferentClass` giúp phân biệt vai trò **defining loader**, cache loader và identity một cách quan sát được.

## 6. Tại sao `getResource("...Hello.class")` không tìm ra bytes?

Một sai lầm khi xây MemoryLoader là tưởng:

~~~java
loader.getResource("memory/generated/Hello.class");
~~~

sẽ tự động trả URL vì loader đã có map bytecode. **Không đúng.** `findClass` là hook tìm/define class, còn `findResource`/`findResources` là các hooks **khác** dành cho resource lookup.

Trong demo:

~~~text
Map entry:
  memory.generated.Hello -> byte[]

loadClass("memory.generated.Hello"):
  -> findClass -> defineClass -> Class<?>

getResource("memory/generated/Hello.class"):
  -> parent resource search
  -> child findResource (chưa override)
  -> null
~~~

Điều này bình thường. Nếu framework cần expose `.class` hoặc JSON/config/resource từ RAM, bạn phải bổ sung **resource store** và một giải pháp `URL`/`URLConnection`/stream phù hợp, hoặc cung cấp một API nhận bytes trực tiếp. Đừng ngầm ghi file lên disk chỉ để `getResource` hoạt động nếu yêu cầu ban đầu là chỉ dùng RAM.

### 6.1. Hai namespace nên được thiết kế rõ

- **Class map:** `Map<String,byte[]>`, key là binary class name.
- **Resource map:** `Map<String,byte[]>`, key là slash-separated resource path.

Hai map này có thể cùng trỏ tới bytes classfile cho đường `memory/generated/Hello.class`, nhưng chúng **không tự liên kết** với nhau. Cần xác định cách tra parent/resources và quyền công bố URL nếu ứng dụng cần.

### 6.2. CodeSource location có thể không có

Khi gọi `ClassLoader.defineClass(name, bytes, ...)` không truyền một `ProtectionDomain` tường minh, JDK có default protection domain. Bạn **không nên giả định CodeSource có location URL trỏ tới file JAR**.

Một class được nạp chỉ từ RAM có thể có `CodeSource` với `getLocation()==null`. Đây không phải dấu hiệu không có defining loader hoặc bytecode bị lỗi. Nếu cần provenance, cần **lưu metadata riêng khi nhận bytecode** (artifact ID/hash, origin đã xác minh, phiên bản) chứ không suy luận từ `getResource`.

## 7. Hai loader dùng cùng byte[] nhưng tạo hai Class<?> khác nhau

Runtime identity của ordinary class gồm:

~~~text
(binary class name, defining ClassLoader)
~~~

Trong demo, cả hai đều có tên `memory.generated.Hello`:

~~~java
Class<?> c1 = first.loadClass(NAME);
Class<?> c2 = second.loadClass(NAME);
System.out.println(c1 == c2); // false
~~~

Đây là snippet dùng biến demo đã tạo. Hai objects `Class<?>` khác nhau vì **defining loader khác nhau** dù bytes giống nhau.

Hệ quả:

- Không cast instance `Hello` từ loader A sang type `Hello` của loader B chỉ vì binary names giống nhau.
- Reflection với `Class<?>` của mỗi loader vẫn có thể sử dụng đúng instances.
- Nếu muốn host/plugin giao tiếp type-safe, hãy đưa **interface/DTO chung** vào parent loader và để generated class implements contract đó.
- Đừng để generated library chứa bản sao của shared API rồi vô tình child-first define API khác; dễ gặp `ClassCastException`, `LinkageError` hoặc `ServiceConfigurationError`.

### 7.1. Không thể “redefine” cùng class trong cùng loader bằng cách sửa map

Sau khi `first.loadClass(NAME)` thành công, đổi bytes trong map không làm JVM tự thay `c1`. Lần gọi `loadClass(NAME)` tiếp theo thường trả class đã có.

Nếu cố gọi `defineClass` lần nữa với cùng binary name trong cùng loader, có thể gặp `LinkageError` do duplicate definition. Muốn tạo version mới thường phải dùng **MemoryLoader instance mới** và quản lý references/lifecycle thích hợp; điều đó cũng tạo **runtime type identity mới**.

### 7.2. Khi nào class được initialized?

Lời gọi `MemoryLoader.loadClass(NAME)` tạo/load class; không tự đồng nghĩa chạy static initialization. Trong demo, `Hello` không có static initializer.

Nếu thêm:

~~~java
static {
    System.out.println("HELLO_INITIALIZED");
}
~~~

vào class source được compile, dòng này sẽ được in khi class được **initialized** (ví dụ new instance), không chỉ vì ta đã giữ một `Class<?>` từ `loadClass`.

Phân biệt:

~~~text
load/define -> verify/link/resolution (khi cần) -> initialize (active use)
~~~

Với `Class.forName(NAME, true, first)`, cờ `true` yêu cầu initialization, còn `Class.forName(NAME, false, first)` không yêu cầu initialize ngay. Không nhầm với `Class.forName(Module, String)` có hợp đồng khác.

## 8. Các lỗi và trường hợp khó cần xử lý

### 8.1. Không tìm thấy class trong map

~~~java
byte[] bytes = bytecodes.get(name);
if (bytes == null) {
    throw new ClassNotFoundException(name);
}
~~~

Đây là hành vi đúng trong `findClass`. `ClassNotFoundException` là checked exception cho đường tìm class chủ động; đừng trả `null` rồi để code bên ngoài lỗi `NullPointerException`.

Nếu generated class tham chiếu helper class mà map không chứa và parent cũng không tìm được, bạn có thể gặp `NoClassDefFoundError` khi VM cố liên kết/sử dụng helper. Cần lưu **mọi output classes**, không chỉ class entry point.

### 8.2. Class bytes sai format

`defineClass` có thể ném:

- `ClassFormatError`: classfile không đúng cấu trúc.
- `UnsupportedClassVersionError`: classfile target vượt khả năng JVM.
- `VerifyError`: bytecode vi phạm verification rules.
- `NoClassDefFoundError` hoặc các lỗi linkage khác khi dependencies/binary names không phù hợp.

Không biến mọi `LinkageError` thành `ClassNotFoundException`; chúng có nguyên nhân và cách khắc phục khác. Hãy giữ stack trace/cause khi debug.

### 8.3. Binary name không khớp nội dung class file

Nếu map có key `memory.generated.Hello` nhưng bytecode khai báo `another.pkg.Hello`, `defineClass(name, bytes, ...)` có thể ném `NoClassDefFoundError` hoặc linkage error về wrong name.

Phần quan trọng cần đảm bảo:

~~~text
requested name == map key == binary name trong classfile
~~~

Trong ví dụ, compiler cung cấp `className` chuẩn cho `MemoryFileManager.getJavaFileForOutput` nên map key được hình thành nhất quán với class output.

### 8.4. Package `java.*` bị bảo vệ

Không cố dùng custom loader để định nghĩa class trong `java.lang` hoặc packages mà JVM không cho phép application loader tạo. Có thể gặp `SecurityException` do quy tắc package bảo vệ. Cũng cần tuân thủ sealing và package metadata nếu nạp từ signed/sealed libraries.

Đây là quy tắc bảo vệ namespace nền tảng, **không phải một sandbox tổng quát** chống code không tin cậy.

### 8.5. Compiler không có ở runtime

`ToolProvider.getSystemJavaCompiler()==null` xảy ra với runtime không có compiler module (ví dụ một số custom jlink images). Hai lựa chọn:

1. **Biên dịch ở build/deploy phase**, chuyển classfile bytes đã kiểm tra vào chương trình.
2. Chạy trên JDK/runtime được cấu hình có compiler.

`MemoryLoader` chỉ cần bytes, không phụ thuộc có compiler. **Phần compile tại runtime mới cần `JavaCompiler`**.

### 8.6. Compiler phát sinh nhiều classes

Một source có inner class, anonymous class hoặc các top-level classes phụ có thể sinh nhiều outputs:

~~~text
memory.generated.Outer
memory.generated.Outer$Inner
memory.generated.Helper
~~~

Nếu file manager chỉ lưu `Outer.class`, đường sử dụng `Outer$Inner` có thể ném `NoClassDefFoundError` sau đó. Bởi vậy, `MemoryFileManager` của demo **lưu mọi tên do compiler phát sinh** thay vì một buffer duy nhất.

### 8.7. Dependencies compile-time và runtime khác nhau

`JavaCompiler` phải resolve được các dependencies khi compile source. `MemoryLoader` lại phải load các classes cần thiết khi runtime. Hai hoạt động có **classpath/loader graph riêng**:

~~~text
JavaCompiler classpath/modulepath -> compile source
MemoryLoader parent + bytecode map -> runtime resolution
~~~

Nếu source tham chiếu một thư viện có sẵn lúc compile nhưng library đó không ở parent/map khi chạy, chương trình vẫn có thể ném `NoClassDefFoundError`. Không tự suy rằng compile success nghĩa runtime visibility đủ.

### 8.8. Concurrency và race

Vì demo override **`findClass`, không phải `loadClass`**, implementation mặc định của `ClassLoader.loadClass` kiểm tra đã load và giữ khóa tương ứng. Đây là con đường dễ bảo trì.

Khi bạn làm compiler/file manager cho nhiều requests đồng thời:

- Không chia sẻ một `ByteArrayOutputStream` cho nhiều class names hoặc compilation tasks.
- Snapshot map chỉ sau khi compiler hoàn thành.
- Tạo immutable catalog per generation và không chỉnh mảng bytes khi loader đang đọc.
- Nếu cần custom child-first `loadClass`, phải bảo vệ `findLoadedClass + findClass/defineClass` trong cùng vùng đồng bộ theo `getClassLoadingLock(name)`.
- Tách caches/versions theo tenant/plugin và quản lý cleanup.

Race trong producer map là vấn đề riêng; bản thân ClassLoader synchronization không tự làm mọi map của ứng dụng thread-safe.

## 9. Bộ nhớ, unload và vòng đời loader

### 9.1. Bytes map khác JVM class metadata

Sau `defineClass` thành công, JVM có thông tin class riêng, không đồng nghĩa mảng bytes trong map là bản lưu duy nhất mà JVM cần giữ. Có ít nhất hai loại memory cần quan tâm:

- **Java heap:** `Map`, `byte[]` buffers, source strings, instances, metadata do ứng dụng giữ.
- **VM/native/metaspace & code caches:** metadata/linking/JIT structures tương ứng loaded classes.

Giữ mọi generations trong static registry sẽ khiến cả bytes map và ClassLoader/classes/instances sống lâu. Nếu build tool bên trong server compile hàng ngàn class mỗi phút, phải có retention/eviction policy.

### 9.2. Loader có thể unload khi nào?

Đối với ordinary class, unload liên quan đến việc **defining ClassLoader không còn reachable** theo điều kiện của JVM. Không có API:

~~~java
loader.unloadClass("memory.generated.Hello");
~~~

Dòng trên là **mã không tồn tại**. Bạn không thể xóa một entry khỏi map rồi yêu cầu JVM “quên” `Class<?>` đã define.

Một quy trình reload plugin hợp lý:

1. Dừng nhận requests cho generation cũ.
2. Chờ hoặc hủy tasks còn chạy bằng chính sách rõ ràng.
3. Dọn instances, callbacks, listeners, thread locals, reflection caches và TCCL references.
4. Bỏ references tới `MemoryLoader` và `Class<?>` của generation cũ.
5. Tạo **MemoryLoader instance mới** cho bytes generation mới.
6. Để garbage collector thu hồi class metadata khi đủ điều kiện; không đòi thời điểm chính xác.

`System.gc()` không bảo đảm unload ngay. Nên quan sát memory/metrics phù hợp nếu ứng dụng liên tục sinh classes.

### 9.3. MemoryLoader không phải security sandbox

Bytecode hợp lệ do custom loader định nghĩa vẫn chạy trong **cùng JVM process với host** và thường có quyền của process đối với file/network/threads/resources. Dùng ClassLoader riêng giúp **namespace isolation**, không tự tạo OS-level permission isolation.

Nếu cho người dùng nhập source Java không đáng tin rồi compile/load trong JVM phục vụ dữ liệu quan trọng, đó là rủi ro lớn. Compiler cũng có thể tiêu tốn CPU/RAM hoặc kích hoạt annotation processors nếu không kiểm soát. Trong demo đã dùng `-proc:none` để tắt annotation processing, nhưng **điều đó không tạo sandbox**.

Đối với code untrusted cần process/container/VM isolation với quyền OS tối thiểu, quotas, network policy, artifact provenance và IPC authorization. Trên JDK 24+, SecurityManager không còn bật được (JEP 486); không dựa vào `SecurityManager` hay `ProtectionDomain` để thiết kế permission sandbox hiện đại.

## 10. Nếu muốn triển khai MemoryLoader trong ứng dụng thực tế

### 10.1. Thiết kế input contract

Một API tạo loader nên nhận **một snapshot đáng tin**:

~~~java
Map<String, byte[]> snapshot = new HashMap<>();
input.forEach((name, bytes) -> snapshot.put(name, bytes.clone()));

MemoryLoader loader =
        new MemoryLoader(Map.copyOf(snapshot), sharedApiLoader);
~~~

Đây là snippet minh họa. `input` là map của caller; `sharedApiLoader` là parent ClassLoader chứa contract được thống nhất. Clone byte arrays giúp không phụ thuộc nguồn mutable. Cần kiểm tra `name` không null/rỗng và giới hạn tổng bytes/class count theo chính sách.

### 10.2. Đặt policy cho namespace

Không nhận mọi binary name từ untrusted source rồi cố define. Nên xác định:

- Prefix package nào thuộc generated implementation, ví dụ `memory.generated.*`.
- API packages nào phải delegate cho parent.
- Không tạo class trong packages dành cho JDK.
- Tránh trùng runtime package có sealing/certificate constraints không đáp ứng.
- Nếu source compile có public classes, package path và binary name phải phù hợp.

Map key/name từ compiler đáng tin hơn map key tùy ý, nhưng code input vẫn phải có nguồn/validation rõ khi deploy.

### 10.3. Chia API với host

Nếu host cần gọi generated implementation theo interface, ví dụ:

~~~java
package shared.api;

public interface Operation {
    String execute(String argument);
}
~~~

thì `Operation` nên do **shared API loader/parent** định nghĩa. Source class sinh động có thể `implements shared.api.Operation`, trong khi bytes của implementation nằm ở child MemoryLoader.

Lúc đó host có thể:

~~~java
Class<?> implementation = loader.loadClass("memory.generated.OpImpl");
Operation operation = (Operation)
        implementation.getDeclaredConstructor().newInstance();
System.out.println(operation.execute("hello"));
~~~

Đây là snippet kiến trúc, **không nằm trong chương trình demo chạy ở mục 5**, vì ví dụ chính chỉ dùng reflection. Khi áp dụng phải bảo đảm compiler tìm thấy `shared.api.Operation` và runtime child delegation nhìn thấy **cùng `Operation.class`** host dùng. Nếu parent/child định nghĩa hai versions của API thì `ClassCastException` vẫn xảy ra.

### 10.4. Logging và diagnostics

Khi compile failure, `DiagnosticCollector` có line/column/error code. Có thể xử lý:

~~~java
for (var diagnostic : diagnostics.getDiagnostics()) {
    System.err.println(
            diagnostic.getKind() + " line " + diagnostic.getLineNumber()
            + ": " + diagnostic.getMessage(null));
}
~~~

Đây là snippet ở method có `diagnostics`. Không log source code/paths/secrets của người dùng nếu chứa dữ liệu nhạy cảm. Với runtime errors, log:

- Binary class name được yêu cầu.
- Loader identity (và version/generation ID do host cấp, không chỉ `toString()`).
- Available class names trong snapshot (cẩn trọng với log privacy).
- Source/compiler diagnostics, target classfile major version.
- Full `ClassNotFoundException`/`LinkageError` stack trace và cause.
- Artifact bytes hash được tính từ dữ liệu được chấp nhận (nếu cần provenance).

### 10.5. Giới hạn kích thước và thời gian

Dynamic compilation là một pipeline có thể tiêu tốn memory. Production nên có:

- Max source size, số source files, số output classes, max classfile bytes.
- Timeouts đối với compilation/execution ở **process boundary cưỡng chế** nếu code không tin cậy.
- Cơ chế không giữ vô hạn compiled byte arrays.
- Compiler options kiểm soát classpath, module path, annotation processors.
- Metrics số generated classes và ClassLoader generations còn reachable.
- Cache key dựa trên source/options/dependency versions, không chỉ binary name.

Không coi `Map.copyOf` hoặc `try-with-resources` là đủ để giải quyết memory leaks của loaded classes.

## 11. So sánh các hướng nạp bytecode động

| Hướng | Khi nên dùng | Cần nhớ |
|---|---|---|
| `ClassLoader.findClass` + `defineClass` từ `byte[]` | Loader tự sở hữu namespace generated classes, nhiều binary names | Parent delegation, runtime identity, lifecycle |
| `Lookup.defineClass(byte[])` | Định nghĩa ordinary class trong package/loader của lookup class, với access constraints | Không tự tạo loader mới; package/nest/module rules |
| `Lookup.defineHiddenClass(...)` | Framework sinh implementation nội bộ không cần tra lại bằng tên | Hidden class không discoverable bằng `Class.forName`/`loadClass` |
| `URLClassLoader` | Nạp class/resources từ URLs/JARs đã đóng gói | Có filesystem/JAR path, không phải pure in-memory byte map |
| `JavaCompiler` + custom file manager | Compile source Java text thành bytecode RAM | Cần compiler module; output files/map riêng |
| Bytecode library/generator | Tạo classfile bytes không qua Java source compiler | Phải bảo đảm classfile hợp lệ và phù hợp JVM target |
| ModuleLayer | Định nghĩa named modules và mapping loader(s) | JPMS module graph/access không tự được tạo bởi map bytes |

Bài hiện tại chủ ý xây **ordinary class nạp từ bytecode memory**, không phải hidden class, không phải một JPMS named module và không phải nạp JAR resource bằng URLClassLoader.

## 12. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Cách điều tra |
|---|---|---|
| `getSystemJavaCompiler() == null` | Runtime thiếu compiler | Dùng JDK có compiler hoặc compile trước ở build |
| `compilation failed` | Source syntax/dependency/options | In `DiagnosticCollector`, kiểm tra `--release`/classpath |
| `ClassNotFoundException` cho class entry point | Sai map key/binary name; parent không thấy | In compiled key set, kiểm tra package |
| `NoClassDefFoundError` khi gọi method | Thiếu generated nested/helper class hoặc runtime dependency | Lưu mọi outputs, so loader graph |
| `NoClassDefFoundError: wrong name` | Key/name không khớp nội dung classfile | Tạo key theo compiler output |
| `UnsupportedClassVersionError` | Bytecode target lớn hơn JVM | Dùng `--release` phù hợp runtime |
| `ClassFormatError`/`VerifyError` | Bytes hỏng/sinh không hợp lệ | Kiểm tra generator/JavaFileObject và origin |
| `LinkageError` khi define lặp | Định nghĩa cùng tên hai lần trong một loader | Dùng `loadClass` mặc định, tạo loader mới cho generation |
| `ClassCastException` giữa hai cùng tên class | Defining loaders khác nhau | Dùng parent-shared API types |
| `getResource("Hello.class") == null` | Bytes map không tự là resource store | Bổ sung `findResource` hoặc API bytes riêng |
| Parent trả class khác với memory map | Parent-first loader có cùng binary name | Cô lập app classpath; namespace policy |
| Static initializer không chạy ngay sau `loadClass` | Load/link khác initialization | Kích hoạt active use hoặc `Class.forName(...,true,...)` |
| Memory tăng sau nhiều compiles | Maps/caches/handles/loaders cũ vẫn reachable | Giới hạn generations, dọn references, profile |
| Nhiều threads dùng cùng map tạo lỗi | Mutable bytes hoặc publish trước compile xong | Snapshot bất biến, defensive copy |
| Code compile thành công nhưng runtime fail | Compiler classpath khác memory loader graph | Kiểm tra compiled + runtime dependencies |
| Plugin có thể đọc file/secrets của host | Loader khác không là security sandbox | Process isolation/OS permissions |
| Code mới không được dùng sau cập nhật map | Class đã định nghĩa một lần trong loader | Tạo MemoryLoader generation mới |

### Checklist trước khi dùng production

1. Nguồn source/bytecode có đáng tin và được validate theo policy không?
2. Có quy định rõ packages/binary names cho generated classes không?
3. Bytes map đã được **deep copy** và đóng băng trước khi publish cho loader chưa?
4. Có lưu tất cả compiler outputs, kể cả nested/helper classes không?
5. Compiler runtime và target JVM version có tương thích không?
6. Compiler classpath có khớp dependencies mà MemoryLoader/parent cung cấp khi chạy không?
7. API xuyên boundary có đúng một defining loader không?
8. Có metrics, diagnostics, memory/classloader generation lifecycle không?
9. Có giới hạn lượng source/output bytes và compilation time không?
10. Nếu source untrusted, có **sandbox process-level** và quyền OS phù hợp không?

## 13. Bài tập thực hành nâng cao

1. Trong ví dụ, tại sao map key phải là `memory.generated.Hello` thay vì `memory/generated/Hello.class`?
2. Vì sao `findClass` phải ném `ClassNotFoundException` khi không có bytes?
3. Nếu compiler tạo thêm inner class `Hello$Inner`, file manager phải làm gì?
4. Vì sao method `getJavaFileForOutput` cần giữ output theo class name?
5. Vì sao `ClassLoader.loadClass` nên được giữ implementation mặc định cho demo?
6. Định danh runtime class phụ thuộc binary name và yếu tố nào nữa?
7. Hai loaders cùng bytes tạo hai `Class<?>` objects khác nhau có hợp lệ không?
8. Gọi `first.loadClass(NAME)` hai lần có define lại class không?
9. Khi nào `Class.forName(NAME, true, first)` khác `loadClass(NAME)` về initialization?
10. Vì sao `Map.copyOf` không bảo vệ mảng byte[] khỏi bị sửa?
11. Tại sao `getResource("memory/generated/Hello.class")` trả null trong demo?
12. Nếu parent đã có class cùng tên, loader nào được ưu tiên?
13. Nếu source compile nhưng generated class tham chiếu thư viện không có lúc runtime, điều gì xảy ra?
14. Vì sao không dùng `defineClass` để thay trực tiếp class đã định nghĩa trong một loader?
15. Có cần JDK compiler module để **load** bytes đã compile sẵn không?
16. Vì sao không nên đánh đồng MemoryLoader với sandbox?
17. Khi nào nên dùng `Lookup.defineHiddenClass` thay vì ordinary MemoryLoader?
18. Cách nào lưu generated classes để host gọi theo interface mà không reflection?
19. `ClassFormatError`, `UnsupportedClassVersionError` và `ClassNotFoundException` khác nhau về nguyên nhân?
20. Khi memory leak xuất hiện sau reload nhiều lần, kiểm tra references nào trước?
21. Vì sao mở rộng code sang multi-threaded compiler cần chiến lược snapshot riêng?
22. Muốn hỗ trợ dynamic config/resource JSON trong RAM, cần thêm API nào?
23. Tại sao loader không tự được unload khi xóa entry map?
24. Nếu kết quả compile nằm trong `byte[]` RAM, lúc nào JVM có thể cần thêm metaspace?
25. Khi nhận bytecode từ mạng, cần xác thực origin/integrity và hạn chế execution ra sao?

**Tiêu chí hoàn thành:** tự chạy chương trình với JDK 17+, giải thích được đầy đủ 10 dòng stdout; sửa generated source để tạo một method khác rồi tạo loader generation mới; trình bày được pipeline `JavaCompiler → JavaFileManager → Map<String,byte[]> → findClass → defineClass → Class<?>`; biết xử lý dependencies, type identity, resources và vòng đời.

## 14. Tài liệu chính thức

- [Java SE 21 — ClassLoader](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ClassLoader.html): `findClass`, `defineClass`, `loadClass`, `findLoadedClass`, class identity.
- [Java SE 21 — JavaCompiler](https://docs.oracle.com/en/java/javase/21/docs/api/java.compiler/javax/tools/JavaCompiler.html): compiler task, file manager và diagnostics.
- [Java SE 21 — JavaFileManager](https://docs.oracle.com/en/java/javase/21/docs/api/java.compiler/javax/tools/JavaFileManager.html): output JavaFileObject và location.
- [Java SE 21 — ForwardingJavaFileManager](https://docs.oracle.com/en/java/javase/21/docs/api/java.compiler/javax/tools/ForwardingJavaFileManager.html): wrapper cho standard file manager.
- [Java SE 21 — SimpleJavaFileObject](https://docs.oracle.com/en/java/javase/21/docs/api/java.compiler/javax/tools/SimpleJavaFileObject.html): source và bytecode output objects.
- [Java SE 21 — ToolProvider](https://docs.oracle.com/en/java/javase/21/docs/api/java.compiler/javax/tools/ToolProvider.html): lấy system JavaCompiler.
- [JVMS Java SE 21, Chapter 5](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-5.html): loading, linking, initialization và runtime class identity.
- [JEP 486 — Permanently Disable the Security Manager](https://openjdk.org/jeps/486): lý do không dựa ClassLoader/legacy SecurityManager để chạy bytecode không đáng tin.

**Kết luận:** MemoryClassLoader là một cách dùng ClassLoader rất thực tế: JVM không quan tâm bytes đến từ file JAR hay RAM miễn classfile hợp lệ và loader định nghĩa đúng. Kết hợp `JavaCompiler` với `JavaFileManager`, bạn có thể biên dịch, giữ toàn bộ classfile outputs và nạp chúng trực tiếp trong memory. Điều khó hơn phần code là **duy trì runtime type identity, parent delegation, dependency visibility, resource policy, memory lifecycle và permission boundary** khi mở rộng hệ thống.