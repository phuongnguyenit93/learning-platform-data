# Đọc và kiểm tra bytecode từ thư mục, bộ nhớ hoặc nguồn riêng trong Java ClassLoader

## 1. Mục tiêu và bài toán

Java có thể nạp lớp không chỉ từ JAR và classpath thông thường mà còn từ thư mục cấu hình riêng, một mảng byte trong bộ nhớ hoặc một kho bytecode do ứng dụng quản lý. Khả năng này cho phép triển khai plugin, sinh mã động, cô lập phiên bản thư viện hoặc các cơ chế triển khai tùy chỉnh.

Điểm mở rộng quen thuộc là `ClassLoader.findClass(String name)`. Ứng dụng con override phương thức này để **tìm bytecode**, kiểm tra đầu vào cần thiết, rồi dùng `defineClass(...)` để tạo định nghĩa runtime của lớp.

Nhưng thao tác “đọc được mảng byte và gọi `defineClass`” chưa đủ để thiết kế một loader an toàn. Cần quan tâm đến:

- **Tên lớp (binary name):** phải trùng định nghĩa thực sự trong class file.
- **Nguồn byte:** thư mục đúng root, kho trong bộ nhớ hoặc nguồn riêng được kiểm soát.
- **Dữ liệu hợp lệ:** định dạng class file, phiên bản bytecode, cấu trúc, mức độ tin cậy và giới hạn kích thước.
- **Delegation:** loader cha có thể đã cung cấp class trước khi `findClass` được gọi.
- **Danh tính kiểu:** hai loader định nghĩa cùng binary name tạo thành hai runtime types khác nhau.
- **Lỗi và concurrency:** phải báo lỗi tìm lớp đúng nghĩa, tránh định nghĩa trùng khi nhiều thread yêu cầu cùng class.
- **Vòng đời:** resource lookup, rò rỉ loader, cache bytecode và tải lại plugin phải được thiết kế riêng.

Bài này phân biệt rõ **đọc bytecode từ nguồn riêng** với **kiểm chứng bytecode** và **định nghĩa một class trong JVM**.

## 2. Ba bước riêng biệt: tìm, kiểm tra, định nghĩa

Với tên `lesson.plugin.Greeting`, một loader tùy chỉnh thường thực hiện:

```text
request: loader.loadClass("lesson.plugin.Greeting")
       |
       v
ClassLoader.loadClass:
  (1) đã được ghi nhận nạp? -> trả Class cũ
  (2) parent có lớp?        -> trả Class parent
  (3) chưa có               -> findClass(binaryName)
                                   |
                            lấy bytecode từ nguồn
                                   |
                            kiểm tra sơ bộ/policy
                                   |
                            defineClass(name, bytes, ...)
                                   |
                            JVM kiểm tra, tạo định nghĩa
                                   |
                            trả Class<?> runtime
```

**Vai trò API:**

| API | Trách nhiệm | Điều dễ nhầm |
| --- | --- | --- |
| `loadClass(String)` | Đầu vào tìm/nạp lớp, mặc định theo parent-first delegation | Không có nghĩa loader được gọi là defining loader |
| `findLoadedClass(String)` | Kiểm tra lớp JVM đã ghi nhận nạp với initiating loader này | Không phải một cache bytecode tùy ý do ứng dụng quản lý |
| `findClass(String)` | Điểm mở rộng tìm/định nghĩa lớp cục bộ | Không tự động đọc thư mục/JAR nếu không có implementation |
| `defineClass(String, byte[], int, int)` | Tạo định nghĩa runtime bằng bytecode do loader cung cấp | Không chỉ đơn giản “parse header”; JVM còn áp dụng các quy tắc class/linking |
| `resolveClass(Class<?>)` | Liên quan linking/resolution của lớp đã định nghĩa | Không đồng nghĩa chạy `static initializer` |
| `Class.forName(name, initialize, loader)` | Tra kiểu và chọn có chủ động khởi tạo hay không | Có thể bị parent delegation ảnh hưởng như `loadClass` |

Khi chỉ cần thay **nguồn bytecode**, thường nên override `findClass` và giữ thuật toán `loadClass` mặc định. Nếu override `loadClass` để áp dụng child-first, bạn phải tự giữ quy tắc đồng bộ, lớp đã nạp, tương thích class loader và namespace bắt buộc.

## 3. Tên nhị phân và ánh xạ tới thư mục

Giả sử bytecode được biên dịch từ:

```java
package lesson.plugin;

public final class Greeting {
    public String message() {
        return "hello";
    }
}
```

Đây là mã nguồn của một lớp ví dụ, không phải một chương trình có `main` độc lập. Tên nhị phân của nó là `lesson.plugin.Greeting`. Với một **classpath root** là thư mục `plugins/classes`, class file thường nằm tại:

```text
plugins/classes/lesson/plugin/Greeting.class
```

Do đó cách ánh xạ quen thuộc là:

```java
Path classFile = root.resolve(
        binaryName.replace('.', '/') + ".class");
```

Đây là snippet, giả định `root` và `binaryName` tồn tại.

**Không được nhầm:**

- `lesson.plugin.Greeting` là **binary name**, còn `lesson/plugin/Greeting.class` là đường dẫn tương đối trong một root.
- Class lồng nhau có dấu `$` trong tên nhị phân, ví dụ `Outer$Nested`; không đổi thành `Outer.Nested` khi truyền cho `loadClass`.
- Một JAR dùng dấu `/` trong entry names, bất kể dấu phân tách đường dẫn của hệ điều hành.
- Parent có thể đã định nghĩa `lesson.plugin.Greeting`; việc file riêng tồn tại không bảo đảm `findClass` của child sẽ chạy.

### Thư mục là nguồn dữ liệu, không phải lớp bảo mật

Nếu tên class có thể đến từ bên ngoài, không nên nối thẳng nó vào đường dẫn mà bỏ kiểm tra. Cần giới hạn namespace, chuẩn hóa đường dẫn, kiểm tra root, xử lý symbolic link và quyền truy cập phù hợp. Đường dẫn hợp lệ về mặt cú pháp vẫn có thể dẫn tới nội dung do đối tượng không tin cậy kiểm soát.

Nếu ứng dụng chỉ tải class trong `lesson.plugin.*`, chính sách allowlist package giúp tránh vô ý đọc bytecode của vùng API khác. Tuy nhiên, allowlist tên **không** chứng minh bytecode an toàn.

## 4. Bytecode từ bộ nhớ: không cần file JAR lúc định nghĩa

Một nguồn khác là `Map<String, byte[]>` chứa class file bytes:

```text
"lesson.plugin.Greeting" -> [0xCA, 0xFE, 0xBA, 0xBE, ...]
"lesson.plugin.Helper"   -> [0xCA, 0xFE, 0xBA, 0xBE, ...]
```

Đây là mô tả cấu trúc dữ liệu. Một `MemoryClassLoader` có thể lấy `byte[]` theo binary name rồi gọi `defineClass`; JVM **không yêu cầu** class phải xuất phát từ file trên ổ đĩa.

Những lựa chọn triển khai đáng chú ý:

- **Copy mảng byte:** nếu bên ngoài còn giữ mảng và thay đổi nó trong lúc loader sử dụng, kết quả có thể khó dự đoán. Copy mảng khi nhận vào loader và tránh cho bên ngoài sửa bản đang sử dụng.
- **Cache định nghĩa, không định nghĩa lại:** `findLoadedClass` và thuật toán `loadClass` mặc định giúp tái sử dụng `Class<?>` đã được ghi nhận.
- **Bản đồ đầy đủ phụ thuộc:** bytecode của `Greeting` có thể yêu cầu `Helper` hoặc interface cha; nguồn loader phải có cách tìm chúng hoặc nhờ parent.
- **Giới hạn bộ nhớ:** lưu nhiều bản class bytes, plus runtime metadata, có thể làm tăng bộ nhớ; sau khi lớp được định nghĩa, không nhất thiết cần giữ mọi `byte[]` gốc mãi mãi.
- **Danh tính lớp:** bytecode giống hệt nhưng nạp bằng hai defining loader khác nhau tạo hai loại runtime khác nhau.

Bytecode từ network/database không tự nhiên “đáng tin” hơn bytecode từ bộ nhớ. Với nguồn riêng, phải thiết kế thêm xác thực, quản trị phiên bản, cache, timeout, checksum/signature từ nguồn đáng tin cậy và rollback khi nguồn không khả dụng.

## 5. Những mức “kiểm tra bytecode” cần phân biệt

Có ba tầng không được đánh đồng.

### 5.1. Kiểm tra trước khi gọi defineClass

Ứng dụng có thể kiểm tra:

1. **Tên/namespace được cho phép:** ví dụ chỉ chấp nhận `lesson.plugin.*`; không cố định nghĩa `java.*`.
2. **Nguồn:** root đã cấu hình, kho bytecode nội bộ, hoặc artifact ID nằm trong allowlist.
3. **Kích thước:** không đọc file quá lớn vô điều kiện; cân nhắc đọc stream có giới hạn thay vì chỉ dựa vào kích thước file tại một thời điểm.
4. **Class-file magic:** bốn byte đầu của class file là `CA FE BA BE`. Điều này **chỉ là kiểm tra sơ bộ**, không chứng minh class hợp lệ.
5. **Phiên bản class file:** major version phải được runtime hỗ trợ; không chỉ dựa trên phần mở rộng `.class`.
6. **Integrity/authenticity:** kiểm tra SHA-256 so với digest được phát hành qua kênh đáng tin hoặc xác minh chữ ký artifact thích hợp. Không có ý nghĩa bảo mật nếu “expected hash” được lấy từ chính nguồn không tin cậy cùng lúc với bytecode.
7. **Policy bổ sung:** package sealing, signer/certificate, protection domain và cách cho phép plugin kết nối API host.

Kiểm tra tên **bên ngoài** không thay thế việc JVM đối chiếu tên nhị phân thực trong class file.

### 5.2. JVM định dạng và verification

Khi gọi `defineClass(name, bytes, offset, length)`, JVM áp dụng những kiểm tra cần thiết cho định nghĩa class. Tùy lỗi, thời điểm và quy tắc JVM, có thể gặp:

| Lỗi | Ý nghĩa điển hình |
| --- | --- |
| `ClassFormatError` | Cấu trúc class file không hợp lệ |
| `UnsupportedClassVersionError` | Class file dùng phiên bản bytecode JVM hiện tại không hỗ trợ |
| `NoClassDefFoundError` do wrong name | Tên yêu cầu không trùng với tên định nghĩa trong class file |
| `VerifyError` | Bytecode không đáp ứng điều kiện verifier |
| `SecurityException` | Vi phạm hạn chế định nghĩa, namespace, package hoặc nguồn/certificate |
| `LinkageError` do duplicate definition | Cố định nghĩa lại cùng binary name trong một defining loader |
| `NoClassDefFoundError` do thiếu phụ thuộc | Superclass/superinterface hoặc phụ thuộc cần thiết không thể nạp khi JVM cần |
| `ExceptionInInitializerError` | Lỗi **initialization** khi thực thi mã tĩnh, không đồng nghĩa `defineClass` hỏng |

Một class có thể **định nghĩa thành công** mà sau đó mới gặp lỗi resolution của class phụ thuộc hoặc lỗi initialization khi active use. Đừng ép kết luận “defineClass hoàn tất = toàn bộ graph bytecode đều đã được kiểm chứng, liên kết và khởi tạo”.

### 5.3. Không coi JVM verifier là sandbox cho code không tin cậy

JVM bytecode verifier đảm bảo nhiều ràng buộc an toàn kiểu/máy ảo, nhưng **không** ngăn một class hợp lệ gọi API có quyền của tiến trình. Loader tùy chỉnh tự nó không cô lập network, filesystem, process execution hoặc native code. Với plugin không tin cậy, cần mô hình cách ly mạnh hơn (ví dụ một tiến trình/container được quản lý với quyền hạn được giảm), chứ không dựa vào `ClassLoader` như hàng rào bảo mật.

## 6. Ví dụ Java 17 chạy được: cùng bytecode từ thư mục và Map trong bộ nhớ

Thí nghiệm này tự sinh và biên dịch một class `lesson.plugin.Greeting` bằng `JavaCompiler` của JDK, rồi tải **cùng bytecode** theo hai cách:

1. `DirectoryLoader` đọc file `.class` từ thư mục gốc.
2. `MemoryLoader` đọc `byte[]` từ một `Map`.
3. Cả hai loader có parent là platform loader, để parent không nạp class plugin từ application classpath.
4. JVM tạo hai định nghĩa runtime riêng dù cùng binary name.
5. Chương trình kiểm tra tìm class đã được ghi nhận, kiểm tra bootstrap class và trường hợp class không tồn tại.

**Lưu toàn bộ chương trình** vào `BytecodeSourceDemo.java`:

```java
import java.io.IOException;
import java.lang.reflect.Method;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.HashMap;
import java.util.Map;
import javax.tools.JavaCompiler;
import javax.tools.ToolProvider;

public class BytecodeSourceDemo {
    private static final String TYPE = "lesson.plugin.Greeting";
    private static final int MAX_BYTES = 1_000_000;

    private static void checkBytes(String name, byte[] bytes)
            throws ClassNotFoundException {
        if (!TYPE.equals(name) || bytes == null
                || bytes.length < 8 || bytes.length > MAX_BYTES) {
            throw new ClassNotFoundException(name);
        }
        if ((bytes[0] & 0xFF) != 0xCA
                || (bytes[1] & 0xFF) != 0xFE
                || (bytes[2] & 0xFF) != 0xBA
                || (bytes[3] & 0xFF) != 0xBE) {
            throw new ClassNotFoundException(
                    "Not a class-file header: " + name);
        }
    }

    static final class DirectoryLoader extends ClassLoader {
        private final Path root;

        DirectoryLoader(Path root, ClassLoader parent) {
            super(parent);
            this.root = root.toAbsolutePath().normalize();
        }

        @Override
        protected Class<?> findClass(String name)
                throws ClassNotFoundException {
            if (!TYPE.equals(name)) {
                throw new ClassNotFoundException(name);
            }
            Path file = root.resolve(
                    name.replace('.', '/') + ".class").normalize();
            if (!file.startsWith(root)) {
                throw new ClassNotFoundException(name);
            }

            byte[] bytes;
            try {
                if (!Files.isRegularFile(file)
                        || Files.size(file) > MAX_BYTES) {
                    throw new ClassNotFoundException(name);
                }
                bytes = Files.readAllBytes(file);
            } catch (IOException exception) {
                throw new ClassNotFoundException(name, exception);
            }

            checkBytes(name, bytes);
            return defineClass(name, bytes, 0, bytes.length);
        }
    }

    static final class MemoryLoader extends ClassLoader {
        private final Map<String, byte[]> source;

        MemoryLoader(Map<String, byte[]> source, ClassLoader parent) {
            super(parent);
            this.source = new HashMap<>();
            source.forEach((name, bytes) ->
                    this.source.put(name, bytes.clone()));
        }

        @Override
        protected Class<?> findClass(String name)
                throws ClassNotFoundException {
            byte[] stored = source.get(name);
            if (stored == null) {
                throw new ClassNotFoundException(name);
            }
            byte[] bytes = stored.clone();
            checkBytes(name, bytes);
            return defineClass(name, bytes, 0, bytes.length);
        }
    }

    private static String invokeGreeting(Class<?> type)
            throws Exception {
        Object instance = type.getDeclaredConstructor().newInstance();
        Method method = type.getMethod("message");
        return (String) method.invoke(instance);
    }

    public static void main(String[] args) throws Exception {
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException("Run with a full JDK");
        }

        Path temp = Files.createTempDirectory("bytecode-source-");
        Path source = temp.resolve(
                "src/lesson/plugin/Greeting.java");
        Path classes = temp.resolve("classes");
        Path bytecode = classes.resolve(
                "lesson/plugin/Greeting.class");

        try {
            Files.createDirectories(source.getParent());
            Files.createDirectories(classes);
            Files.writeString(source, """
                    package lesson.plugin;
                    public final class Greeting {
                        public String message() {
                            return "hello";
                        }
                    }
                    """);

            int exit = compiler.run(null, null, null,
                    "--release", "17",
                    "-d", classes.toString(), source.toString());
            if (exit != 0) {
                throw new IllegalStateException("javac failed");
            }

            byte[] originalBytes = Files.readAllBytes(bytecode);
            ClassLoader parent = ClassLoader.getPlatformClassLoader();

            DirectoryLoader directory =
                    new DirectoryLoader(classes, parent);
            MemoryLoader memory = new MemoryLoader(
                    Map.of(TYPE, originalBytes), parent);

            Class<?> fromDirectory = directory.loadClass(TYPE);
            Class<?> fromMemory = memory.loadClass(TYPE);

            System.out.println("directory="
                    + invokeGreeting(fromDirectory));
            System.out.println("memory="
                    + invokeGreeting(fromMemory));
            System.out.println("sameName="
                    + fromDirectory.getName().equals(
                            fromMemory.getName()));
            System.out.println("sameClass="
                    + (fromDirectory == fromMemory));
            System.out.println("directoryDefining="
                    + (fromDirectory.getClassLoader() == directory));
            System.out.println("memoryDefining="
                    + (fromMemory.getClassLoader() == memory));
            System.out.println("directoryCached="
                    + (fromDirectory == directory.loadClass(TYPE)));
            System.out.println("stringBootstrap="
                    + (memory.loadClass("java.lang.String")
                            .getClassLoader() == null));

            try {
                memory.loadClass("lesson.plugin.Missing");
            } catch (ClassNotFoundException exception) {
                System.out.println("missing=ClassNotFoundException");
            }
        } finally {
            Files.deleteIfExists(source);
            Files.deleteIfExists(bytecode);
            Files.deleteIfExists(source.getParent());
            Files.deleteIfExists(
                    source.getParent().getParent());
            Files.deleteIfExists(temp.resolve("src"));
            Files.deleteIfExists(bytecode.getParent());
            Files.deleteIfExists(
                    bytecode.getParent().getParent());
            Files.deleteIfExists(classes);
            Files.deleteIfExists(temp);
        }
    }
}
```

Biên dịch và chạy với **JDK 17 trở lên** (không chỉ một runtime image không có compiler):

```bash
javac BytecodeSourceDemo.java
java BytecodeSourceDemo
```

**Stdout mong đợi khi compiler và hệ thống file hoạt động bình thường:**

```text
directory=hello
memory=hello
sameName=true
sameClass=false
directoryDefining=true
memoryDefining=true
directoryCached=true
stringBootstrap=true
missing=ClassNotFoundException
```

### Giải thích kết quả

- Hai loader tìm được **cùng bytecode** do `javac` tạo, nên gọi `message()` đều trả `hello`.
- `sameName=true` vì `Class.getName()` của cả hai là `lesson.plugin.Greeting`.
- `sameClass=false` vì hai loader là **hai defining loaders khác nhau**; JVM không xem chúng là một class runtime.
- `directoryDefining=true` và `memoryDefining=true` chứng tỏ class được định nghĩa bởi loader nhận trách nhiệm tìm bytecode, không phải platform parent.
- `directoryCached=true`: với cùng một loader, lần yêu cầu thứ hai nhận lại định nghĩa đã nạp, không gọi `defineClass` thêm lần nữa.
- `stringBootstrap=true`: `java.lang.String` vẫn được bootstrap loader định nghĩa theo delegation.
- Khi `MemoryLoader` không có byte array cho `lesson.plugin.Missing`, `findClass` ném `ClassNotFoundException`. Đây là hợp đồng hợp lý khi nguồn loader không chứa class được yêu cầu.

### Giới hạn chủ đích của thí nghiệm

- Chỉ cho phép **một binary name** `lesson.plugin.Greeting`: giúp tránh vô tình đọc/định nghĩa class ngoài phạm vi bài học. Loader thực tế phải có policy rộng hơn và hợp lệ với các lớp phụ thuộc.
- Kiểm tra `CA FE BA BE` là **sơ bộ**; JVM mới là bên kiểm tra class file theo đặc tả. Không tuyên bố chương trình này đã xác minh chữ ký artifact hay sandbox code.
- `Files.size` trước `Files.readAllBytes` là một bước giới hạn thuận tiện; nếu file có thể bị thay đồng thời, sẽ có rủi ro *time-of-check/time-of-use*. Nguồn không tin cậy cần đọc stream có giới hạn và chính sách filesystem mạnh hơn.
- Các đường dẫn chỉ được tạo từ tên cố định, vì vậy ví dụ không phô diễn đầy đủ cách chống path traversal, symlink escape hoặc arbitrary namespace.
- Ví dụ dùng JavaCompiler của JDK để tránh cần JAR bên ngoài; khi nạp bytecode từ database hoặc HTTP, chỉ thay **nguồn bytes** và giữ quy tắc validate/define tương ứng.

## 7. Kiểm tra dữ liệu sai: làm gì với bytecode hỏng?

Phân biệt hai nhóm lỗi:

**Nhóm 1 — Loader không tìm được nguồn hợp lệ:** tên nằm ngoài namespace cho phép, file không tồn tại, không thể đọc, byte array không có trong kho. `findClass` nên báo `ClassNotFoundException`, có thể kèm `IOException` làm cause.

**Nhóm 2 — Đã lấy được bytes, nhưng bytes không phải class file hợp lệ:** `defineClass`/JVM có thể ném `ClassFormatError`, `UnsupportedClassVersionError`, `VerifyError` hoặc các `LinkageError` phù hợp. Không nên bắt hết mọi `Throwable` rồi biến thành `ClassNotFoundException` vì sẽ che giấu nguyên nhân kỹ thuật.

Ví dụ một mảng không phải class file:

```java
byte[] invalid = new byte[]{1, 2, 3, 4};
```

Đây là đoạn minh họa. Nếu đưa mảng này vào loader trên với key hợp lệ, kiểm tra `checkBytes` sẽ loại bỏ trước do độ dài nhỏ hơn 8. Nếu vượt qua kiểm tra magic nhưng vẫn có nội dung class file sai, JVM có thể từ chối tại `defineClass` hoặc giai đoạn linking tiếp theo. **Magic bytes không đủ để khẳng định bytecode an toàn hoặc đúng cấu trúc.**

### Nếu tên được yêu cầu khác tên trong class file

Giả sử bạn yêu cầu `lesson.plugin.Other` nhưng đưa vào bytes thực sự định nghĩa `lesson.plugin.Greeting`. Khi gọi `defineClass("lesson.plugin.Other", bytes, ...)`, JVM phải áp dụng ràng buộc tên; kết quả không phải việc âm thầm “đổi tên class” sang Other. Trong những cấu hình thông thường có thể báo `NoClassDefFoundError` với thông tin wrong name.

**Không nên cố sửa tên nhị phân bằng cách thay một vài byte trong class file.** Class file chứa constant pool, descriptors, signatures, bootstrap methods và nhiều metadata ràng buộc khác; nếu cần đổi tên thực sự phải dùng công cụ biến đổi bytecode phù hợp và kiểm tra lại tính nhất quán.

## 8. Nạp từ nguồn riêng: database, kho artifact, HTTP hoặc code sinh động

Có thể trừu tượng nguồn bytecode để `findClass` không phụ thuộc vào filesystem:

```java
@FunctionalInterface
interface BytecodeRepository {
    byte[] read(String binaryName) throws java.io.IOException;
}
```

Đây là snippet về interface nguồn dữ liệu, không phải một ứng dụng chạy riêng. Tùy triển khai, phương thức `read` có thể nhận byte array từ:

- Một `Map<String,byte[]>` được compiler/runtime sinh ra.
- Object storage hoặc database có ánh xạ chính xác từ binary name sang blob bytes/version.
- Một artifact registry có metadata checksum/signature/nguồn phát hành.
- Bộ biên dịch động dùng `javax.tools.JavaCompiler` và `JavaFileManager` để thu bytes trực tiếp vào bộ nhớ.
- Một tầng cache nội bộ chứa lớp plugin đã được xác minh/cho phép.

**Tránh tải trực tiếp bytecode từ URL không được xác thực rồi execute trong JVM ứng dụng.** Với nguồn có độ tin cậy thấp, nên ưu tiên cấu trúc artifact ký số từ pipeline build tin cậy, xác minh nguồn, giới hạn truy cập và cân nhắc cô lập thực thi qua tiến trình riêng. SHA-256 chỉ chứng minh dữ liệu trùng với digest được **tin cậy từ trước**, không cho biết “code này không độc hại”.

### Cache là cache bytes, không phải “reload lớp” trong cùng loader

Kho nguồn có thể cập nhật bản `Greeting.class` theo version. Nhưng một loader đã định nghĩa `lesson.plugin.Greeting` thì không thể tự ý thay definition bằng cách đọc bytes bản mới và gọi `defineClass` lần nữa cùng tên. Lần nạp lặp với `loadClass` mặc định thường lấy class đã ghi nhận.

Nếu cần hot reload, thường phải **tạo loader mới** cho version mới, đổi đường routing của ứng dụng và giải phóng tham chiếu tới loader cũ. Bài toán migration state và đối tượng xuyên giữa các loader cần xử lý riêng; hai bản `Greeting` có thể không ép kiểu qua nhau.

## 9. Bytecode hợp lệ vẫn cần dependency và API chung

Một class mới được `defineClass` thành công vẫn có thể cần superclass, interface hay phương thức từ các thư viện **chưa được phân giải**. Loader phải tìm được các dependency ấy, trực tiếp hoặc qua parent. Chẳng hạn một implementation trong `lesson.plugin` khai báo `implements lesson.api.Plugin`: host và plugin chỉ trao đổi object dưới kiểu `Plugin` an toàn khi cả hai dùng **cùng định nghĩa `Class<?>`** của interface chia sẻ.

Trong hệ plugin, thường để API/SPI và những DTO dùng chung ở loader cha, còn class implementation ở loader plugin. Các thư viện cần cô lập phiên bản phải có phạm vi lookup riêng; parent-first mặc định sẽ chọn bản parent nếu parent đã tìm thấy cùng binary name. JVM vẫn áp đặt loading constraints khi các method signatures đi qua ranh giới loader.

**Cần phân biệt hai kiểm tra:** integrity/authenticity của **bytes nguồn** trước `defineClass`, và tính khả dụng/đồng nhất của **các kiểu liên quan** khi linking. Một checksum đúng không chứng minh graph dependency hợp lệ hay plugin có thể cast qua interface host.

## 10. Đồng thời nhiều luồng và định nghĩa lớp trùng

Khi nhiều thread đồng thời yêu cầu `loader.loadClass("lesson.plugin.Greeting")`, cơ chế `ClassLoader.loadClass` mặc định gồm đồng bộ trên khóa nạp phù hợp và kiểm tra `findLoadedClass` trước khi chọn `findClass`. Vì vậy, nếu chỉ override `findClass`, bạn thường tận dụng được quy tắc chống nạp trùng của phần lõi.

Nếu tự override `loadClass`, cần kiểm soát:

1. Chính sách parent/child rõ ràng.
2. Kiểm tra class đã được ghi nhận nạp trước khi định nghĩa mới.
3. Khóa nạp lớp phù hợp với `getClassLoadingLock(name)` và trạng thái parallel-capable nếu có.
4. Tránh tự gọi `loadClass(name)` từ `findClass(name)` cho cùng tên dẫn đến đệ quy.
5. Không giữ khóa ứng dụng dài qua network fetch hoặc gọi ngược sang các loader khác mà tạo vòng chờ.
6. Chính sách cache + timeout để nguồn remote không làm mọi thread chờ vô hạn.

Cùng một defining loader không được định nghĩa hai lần cùng binary name như hai lớp độc lập. Nếu có xung đột, JVM có thể báo `LinkageError`. **Không được catch lỗi này rồi trả một đối tượng Class tùy ý không đúng tên/loader** chỉ để “qua” lượt nạp.

### Loading khác initialization

`defineClass` và `loadClass` không phải API “thực thi code trong static block”. JVM có giai đoạn loading/linking/initialization riêng. Tạo instance hoặc gọi static method có thể gây initialization sau đó; loader do ứng dụng viết không nên dùng log trong `static {}` để suy ra mọi lần đọc bytecode.

## 11. Lỗi thường gặp và hướng chẩn đoán

| Hiện tượng | Câu hỏi cần kiểm tra |
| --- | --- |
| `ClassNotFoundException` | Loader được yêu cầu có đúng binary name/namespace? Root, repository key, quyền đọc và source có đúng? |
| `NoClassDefFoundError` | Thiếu superclass/interface, dependency khác, wrong name hoặc class từng initialization lỗi? |
| `ClassFormatError` | Bytes có phải class file cấu trúc hợp lệ? Nguồn có trả HTML/JSON thay vì `.class`? |
| `UnsupportedClassVersionError` | Java runtime có đủ mới để đọc major version của class file? |
| `VerifyError` | Bytecode có vi phạm các ràng buộc verifier? Đã bị biến đổi/sinh không hợp lệ? |
| `LinkageError` duplicate definition | Có hai thread/đường code gọi `defineClass` lại cùng tên trong cùng loader? |
| `ClassCastException` giữa lớp cùng tên | Hai defining loader có tạo hai runtime types khác nhau? |
| `SecurityException` | Có cố định nghĩa `java.*` hoặc vi phạm package certificate/protection constraint? |
| `NoSuchMethodError` | Runtime dependency có khác API mà bytecode plugin được compile với không? |
| `ExceptionInInitializerError` | Mã khởi tạo tĩnh lỗi sau active use, không phải lỗi đọc bytes? |
| Không tìm được resource `.properties` | Custom loader có override/thiết lập `findResource(s)` hoặc package/module resource lookup phù hợp? |
| Plugin cũ còn chiếm bộ nhớ | ClassLoader cũ có bị static registry, thread, TCCL, callback hoặc cache giữ lại không? |

**Lưu ý:** `ClassNotFoundException` (checked) và `NoClassDefFoundError` (Error) không được hoán đổi tùy tiện. Khi `findClass` không tìm thấy bytes, dùng `ClassNotFoundException`; khi JVM phát hiện class phụ thuộc không khả dụng, thông điệp runtime có thể là `NoClassDefFoundError`. Phải xem toàn bộ cause.

### Công cụ hữu ích

Với file `.class` hoặc JAR có thể truy cập:

```bash
javap -verbose -classpath plugins/classes lesson.plugin.Greeting
jar tf plugins/plugin.jar
java -Xlog:class+load=info -cp app/classes app.Main
```

Đây là các **lệnh minh họa**, phụ thuộc cách bố trí file và class runtime của dự án. `javap` cho biết thông tin constant pool, major version và cấu trúc class; `jar tf` liệt kê các entry của JAR; log class-load hỗ trợ xác định nhiều class được load từ nguồn nào. Với loader trong bộ nhớ, `CodeSource` có thể không thể hiện như URL file/JAR; điều đó không đồng nghĩa định nghĩa lớp sai.

Để biết defining loader của một class đã nạp:

```java
static void inspect(Class<?> type) {
    System.out.println("name=" + type.getName());
    System.out.println("definingLoader=" + type.getClassLoader());
    System.out.println("module=" + type.getModule());
}
```

Đây là phương thức hỗ trợ, cần được đặt vào một class ứng dụng rồi gọi; không phải chương trình có `main` độc lập. `getClassLoader() == null` là trường hợp lớp do bootstrap loader định nghĩa.

## 12. Resource lookup và giới hạn khi nạp từ memory/database

Một loader chỉ override `findClass` có thể nạp `Greeting.class` từ database, nhưng:

```java
loader.getResource("lesson/plugin/config.properties");
```

có thể trả `null`. Điều này không mâu thuẫn, bởi class loading và resource lookup là hai đường API khác nhau.

Nếu repository chứa cả resource, phải cân nhắc `findResource` và `findResources`, hoặc cung cấp một abstraction riêng cho plugin. Đặc biệt, `getResource` thường ưu tiên parent theo mặc định, còn `getResources` có thể trả nhiều URL. Việc trả URL không mở stream được sẽ khiến API tiêu thụ thất bại dù lookup tưởng như thành công.

Nếu class nằm trong named module, `ClassLoader.getResource` và `Module.getResourceAsStream` còn chịu những quy tắc về module visibility và package openness. Không tự giả định nguồn bytes trong bộ nhớ biến class thành named module nếu không có cấu hình module tương ứng.

## 13. Các hiểu lầm cần tránh

**“Đọc được bốn byte CA FE BA BE là class hợp lệ.”** Sai; đó chỉ là magic header. JVM verifier, class format rules và các constraint khác mới đánh giá sâu hơn.

**“Có byte[] thì tự nhiên class sẽ tồn tại.”** Sai; cần `defineClass` hoặc cơ chế tạo class phù hợp và phân giải đúng tên.

**“`defineClass` thành công tức bytecode an toàn để chạy.”** Sai; bytecode hợp lệ vẫn có thể thực thi hành vi mà tiến trình được phép, gồm truy cập dữ liệu và network.

**“Hai loader nạp cùng bytes sẽ trả cùng đối tượng Class.”** Sai; defining loader khác nhau tạo hai type runtime riêng.

**“Map bytecode thay đổi thì loader cũ tự thay class.”** Sai; một binary name đã được định nghĩa không tự bị thay trong cùng defining loader.

**“Khi không tìm thấy class cứ trả null từ findClass.”** Sai; `findClass` cần báo `ClassNotFoundException` khi không có class tương ứng, theo hợp đồng API.

**“Nếu class đã có trong parent thì findClass chắc chắn được gọi rồi.”** Sai; `loadClass` parent-first có thể trả từ parent trước khi tìm local.

**“Lọc dấu ../ là đủ ngăn mọi path traversal.”** Sai; cần xét symlink, canonical/real path, filesystem race và quyền truy cập nếu tên/path không tin cậy.

**“ClassLoader tùy chỉnh là một security sandbox.”** Sai; cần isolation/process policy phù hợp khi phải chạy code không tin cậy.

## 14. Bài tập tự kiểm tra

**Câu 1.** `DirectoryLoader` được gọi với `lesson.plugin.Greeting`. Loader cần ánh xạ tên này tới file nào nếu root là `plugins/classes`?

**Trả lời:** `plugins/classes/lesson/plugin/Greeting.class`, đồng thời phải xác minh path nằm trong root được phép.

**Câu 2.** Một mảng byte bắt đầu bằng `CA FE BA BE`. Đã đủ để khẳng định class hợp lệ và an toàn chưa?

**Trả lời:** Chưa. Magic chỉ là điều kiện sơ bộ; còn phiên bản, cấu trúc, verification, linkage, nguồn tin cậy và quyền thực thi.

**Câu 3.** Hai loader độc lập nhận cùng bytes với cùng binary name. Có thể cast instance của bản loader A sang class do loader B định nghĩa không?

**Trả lời:** Không chỉ nhờ cùng tên/bytes. Danh tính runtime phụ thuộc defining loader nên hai class khác nhau.

**Câu 4.** Đã định nghĩa `Greeting` trong một loader, repository cập nhật bytes mới. Gọi `loadClass` cùng tên có reload không?

**Trả lời:** Không. Loader tái sử dụng class đã nạp; cần một defining loader mới cho định nghĩa độc lập.

**Câu 5.** Bytecode được tải qua HTTP không có chữ ký nhưng magic header hợp lệ. Có nên chạy trong JVM chính không?

**Trả lời:** Không thể kết luận an toàn. Cần nguồn tin cậy, xác minh artifact theo kênh đáng tin cậy, giới hạn đặc quyền và có thể cô lập tiến trình.

**Câu 6.** `findClass` có bytecode nhưng class sau đó báo `NoSuchMethodError` khi gọi một thư viện. Vì sao?

**Trả lời:** Bytecode class được định nghĩa không bảo đảm các API runtime khác phiên bản compile-time ABI đều có method được tham chiếu.

**Câu 7.** Hai thread cùng yêu cầu một tên class trong cùng loader. Vì sao override chỉ `findClass` thường dễ an toàn hơn override cả `loadClass`?

**Trả lời:** Thuật toán `loadClass` mặc định đã phối hợp khóa nạp lớp, parent delegation và `findLoadedClass` để tránh định nghĩa trùng.

## 15. Checklist cho loader sử dụng trong sản phẩm

- [ ] Xác định namespace/package được phép và nguồn dữ liệu nào được tin cậy.
- [ ] Ánh xạ binary name sang path/key an toàn; xử lý symlink, path traversal và quyền đọc.
- [ ] Giới hạn kích thước và thời gian đọc; kiểm soát bộ nhớ khi nguồn trả `byte[]` lớn.
- [ ] Kiểm tra tính toàn vẹn/xác thực bằng expected digest hoặc chữ ký từ nguồn tin cậy.
- [ ] Giữ phần lỗi I/O trong `ClassNotFoundException` với cause, không che lỗi class format/linkage.
- [ ] Đảm bảo superclass/superinterface, API/SPI và phụ thuộc được cung cấp đúng loader.
- [ ] Tận dụng `loadClass` mặc định nếu chỉ cần thay cách tìm bytecode.
- [ ] Xử lý concurrency và tránh `defineClass` trùng binary name.
- [ ] Phân biệt caching bytes với lifecycle của runtime `Class`.
- [ ] Thiết kế resource lookup và cleanup cho plugin/redeploy.
- [ ] Không coi custom ClassLoader là sandbox code không tin cậy.
- [ ] Kiểm thử thiếu file, sai tên, bytes hỏng, sai JDK version, hai loader khác nhau và dependency conflict.

## 16. Kết luận và tài liệu chính thức

Một custom `ClassLoader` có thể đọc bytecode từ **thư mục, memory map hoặc nguồn riêng**. Nhưng thiết kế đúng cần tách **tìm bytecode** (`findClass`) khỏi **định nghĩa lớp** (`defineClass`), kiểm tra tên/source/kích thước/integrity trước khi giao cho JVM, để JVM thực hiện kiểm tra định dạng và các ràng buộc liên kết. Sau đó phải quản lý delegation, identity, phụ thuộc, lỗi và vòng đời loader một cách có chủ đích.

Tài liệu chuẩn:

- Java SE 17 `ClassLoader` API, đặc biệt `findClass`, `defineClass`, `loadClass` và `findLoadedClass`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html
- JVMS 17 §4, *The class File Format*: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html
- JVMS 17 §5, *Loading, Linking, and Initializing*: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html
- Java SE 17 `JavaCompiler` API: https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/JavaCompiler.html
