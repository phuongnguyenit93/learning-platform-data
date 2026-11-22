# Tạo fixture có cùng tên lớp trong hai JAR để kiểm chứng ClassLoader

## 1. Vì sao cần một fixture có class trùng tên?

Trong ứng dụng Java lớn, hai phiên bản của một thư viện có thể cùng đóng gói `com.example.Library.class`. Vấn đề quan trọng khi chẩn đoán không chỉ là “cả hai JAR đều chứa lớp” mà còn là **JVM đã chọn định nghĩa từ nguồn nào, qua ClassLoader nào và theo thứ tự nào**.

Nếu kiểm thử trên các JAR của dự án thực, kết quả dễ bị ảnh hưởng bởi dependency graph, parent delegation, module path, manifest `Class-Path`, wildcard classpath, build cache hoặc thứ tự classpath tình cờ. Một **fixture** là bộ đầu vào nhỏ, có thể tái tạo: ta tự tạo **hai JAR độc lập chứa cùng binary name**, nhưng nội dung lớp trả về hai kết quả phân biệt. Sau đó dùng các ClassLoader được cấu hình rõ ràng để kiểm tra từng giả thuyết.

Fixture của bài học:

```text
A.jar
├── fixture/same/Versioned.class
│   └── origin() trả "A"
└── fixture/label.txt
    └── A

B.jar
├── fixture/same/Versioned.class
│   └── origin() trả "B"
└── fixture/label.txt
    └── B
```

**Tên nhị phân** của cả hai bản là `fixture.same.Versioned`. Tên file entry trong JAR của cả hai là `fixture/same/Versioned.class`. Chỉ có **thân method** và tài nguyên marker khác, giúp xác minh nguồn được chọn mà không phải dựa vào tên JAR hay timestamp.

Mục tiêu kiểm chứng:

1. **Tạo đúng hai JAR thật**, mỗi JAR chứa cùng một class entry.
2. Nạp class qua `URLClassLoader` có URL order `[A.jar, B.jar]` và `[B.jar, A.jar]`.
3. Chứng minh URL order khác nhau có thể chọn **hai bản method khác nhau** khi parent không có class.
4. Chứng minh mỗi loader độc lập tạo **runtime class identity** riêng ngay cả khi binary name giống nhau.
5. Tạo **parent→child** để chứng minh parent-first delegation thường thắng bản trùng ở child.
6. Phân biệt **class definition** với **resource enumeration** khi một tên resource xuất hiện ở nhiều JAR.
7. Đảm bảo ví dụ có lệnh chạy và output xác định, tự dọn fixture, không cần dependency ngoài JDK.

## 2. Một số khái niệm cần đúng trước khi tạo JAR

### 2.1. Binary name khác đường dẫn entry trong JAR

Với source:

```java
package fixture.same;

public final class Versioned {
    public String origin() {
        return "A";
    }
}
```

Đây là **source minh họa** cho bản A. Bản B có khai báo package/class/method giống hệt nhưng trả `"B"`.

- **Binary name:** `fixture.same.Versioned`, dùng cho `loader.loadClass(...)`.
- **Class file entry:** `fixture/same/Versioned.class`, dùng khi đưa file vào JAR.
- **Root:** file JAR chứa entry ấy, không phải thư mục Java package.
- **Dấu phân tách:** tên entry trong JAR dùng `/` trên cả Linux, macOS và Windows.
- **Bytecode:** hai bản phải được **biên dịch riêng**, không phải biên dịch hai file có cùng fully-qualified name cùng lúc vào một output folder.

Hai class file có thể cùng tồn tại trong **hai JAR** mà không làm `javac` hoặc JAR format tự động từ chối. Xung đột được quan sát khi chúng **cùng tham gia vào đường tìm** của một loader/runtime hoặc khi bytecode khác nhau không tương thích với code gọi.

### 2.2. Parent-first delegation thường xảy ra trước URL order

`URLClassLoader` kế thừa cơ chế `loadClass` parent-first mặc định:

```text
child.loadClass("fixture.same.Versioned")
    |
    +-- đã được ghi nhận nạp? -> trả Class cũ
    |
    +-- parent có class?     -> trả Class của parent
    |
    +-- child.findClass     -> tìm các URL cục bộ theo đường tìm
           |
           +-- A.jar trước B.jar -> có thể chọn A
           +-- B.jar trước A.jar -> có thể chọn B
```

**Vì thế, “JAR A đứng trước JAR B” chỉ mô tả ưu tiên của đường tìm cục bộ trong điều kiện parent chưa cung cấp class.** Nếu parent đã có `fixture.same.Versioned`, child nhận định nghĩa của parent, dù child chỉ có B.jar.

Một plugin loader tùy chỉnh có thể thay đổi thành child-first hoặc theo package, nhưng đó **không phải** chính sách mặc định của `URLClassLoader`.

### 2.3. Cùng binary name không có nghĩa cùng runtime type

Runtime class/interface được xác định bằng cặp:

```text
(binary name, defining ClassLoader)
```

Do đó:

```text
("fixture.same.Versioned", LoaderAB) !=
("fixture.same.Versioned", LoaderBA)
```

Ngay cả khi hai loader dùng cùng một JAR và class file byte-for-byte giống nhau, nếu mỗi loader **tự định nghĩa** class thì hai `Class<?>` objects đại diện **hai runtime classes khác nhau**.

Dấu hiệu kiểm chứng là `Class.getClassLoader()`, `Class<?> ==`, `Class.isInstance(...)`, không phải chỉ so `getName()`.

## 3. Thiết kế fixture: đơn giản nhưng đủ cách phân biệt

Ta cố ý sử dụng các điều kiện sau:

| Thành phần | Thiết kế | Lý do |
| --- | --- | --- |
| Java version | Java 17+ | Chạy được với JDK phổ biến; hỗ trợ `JavaCompiler` và try-with-resources |
| Nguồn bytecode | `javax.tools.JavaCompiler` | Sinh class thật, không phải mảng byte giả |
| JAR packaging | `java.util.jar.JarOutputStream` | JAR thật với entry có tên chính xác, không lệ thuộc tool bên ngoài |
| Binary name | `fixture.same.Versioned` ở cả A và B | Tạo xung đột có chủ ý |
| Method phân biệt | `origin()` trả `A` hoặc `B` | Quan sát định nghĩa nào thắng qua stdout |
| Resource trùng | `fixture/label.txt` | Tách resource lookup khỏi class lookup |
| Parent của AB/BA | Platform ClassLoader | Tránh application loader tình cờ thấy class fixture |
| Parent-child test | Parent[A.jar] → Child[B.jar] | Xác minh parent-first |
| Resource cleanup | Close loaders, `JarFile`, streams, xóa thư mục tạm | Không giữ file handle trong ví dụ |
| Assertion/quan sát | In boolean và giá trị có tên rõ ràng | Không lệ thuộc object hash, PID, temp path |

Fixture có **hai JAR**, nhưng tạo **bốn đối tượng URLClassLoader** trong một lượt thử để tách rõ thứ tự URL và quan hệ parent. Không có nhu cầu dùng hai JAR bên ngoài hoặc thư viện kiểm thử riêng.

### Những giả định cần giữ

- Parent platform không chứa `fixture.same.Versioned` (đúng với JDK chuẩn).
- Chương trình không đặt A.jar/B.jar lên application classpath một cách riêng.
- Class được sinh là class thông thường trong unnamed module của loader riêng, không phải named module trong JPMS.
- Không dùng classloader policy tùy chỉnh, bytecode agent biến đổi hoặc manifest `Class-Path`.
- Máy có JDK với compiler module `jdk.compiler` và quyền đọc/ghi thư mục tạm.

Nhờ các điều kiện trên, stdout của chương trình có thể được dự đoán và kiểm chứng chính xác.

## 4. Chương trình Java 17 hoàn chỉnh tạo và thử hai JAR

Lưu **toàn bộ** mã dưới đây thành file `DuplicateJarFixture.java`. Chương trình:

1. Tạo thư mục tạm.
2. Sinh và biên dịch hai bản `fixture.same.Versioned` vào hai output roots khác nhau.
3. Đóng gói mỗi bản vào một JAR cùng resource marker.
4. Kiểm tra hai JAR đều chứa class entry.
5. Thử các ClassLoader với URL order và parent hierarchy khác nhau.
6. Đọc resource và kiểm tra runtime class identity.
7. Đóng JAR/loader và xóa các file tạm.

```java
import java.io.IOException;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.Enumeration;
import java.util.List;
import java.util.jar.JarEntry;
import java.util.jar.JarFile;
import java.util.jar.JarOutputStream;
import java.util.stream.Stream;
import javax.tools.JavaCompiler;
import javax.tools.ToolProvider;

public final class DuplicateJarFixture {
    private static final String BINARY = "fixture.same.Versioned";
    private static final String CLASS_ENTRY = "fixture/same/Versioned.class";
    private static final String LABEL_ENTRY = "fixture/label.txt";

    private static Path createJar(JavaCompiler compiler, Path root,
                                  String marker) throws IOException {
        Path source = root.resolve("source-" + marker + "/" + CLASS_ENTRY)
                .resolveSibling("Versioned.java");
        Path classes = root.resolve("classes-" + marker);
        Files.createDirectories(source.getParent());
        Files.createDirectories(classes);
        Files.writeString(source,
                "package fixture.same; public final class Versioned {"
              + " public String origin() { return \"" + marker + "\"; } }",
                StandardCharsets.UTF_8);
        int result = compiler.run(null, null, null,
                "--release", "17", "-encoding", "UTF-8",
                "-d", classes.toString(), source.toString());
        if (result != 0) {
            throw new IllegalStateException("Compilation failed: " + marker);
        }
        Path jar = root.resolve(marker + ".jar");
        try (JarOutputStream out = new JarOutputStream(Files.newOutputStream(jar))) {
            out.putNextEntry(new JarEntry(CLASS_ENTRY));
            out.write(Files.readAllBytes(classes.resolve(CLASS_ENTRY)));
            out.closeEntry();
            out.putNextEntry(new JarEntry(LABEL_ENTRY));
            out.write(marker.getBytes(StandardCharsets.UTF_8));
            out.closeEntry();
        }
        return jar;
    }

    private static String origin(Class<?> type) throws ReflectiveOperationException {
        Object instance = type.getDeclaredConstructor().newInstance();
        return (String) type.getMethod("origin").invoke(instance);
    }

    private static String read(URL resource) throws IOException {
        try (var in = resource.openStream()) {
            return new String(in.readAllBytes(), StandardCharsets.UTF_8);
        }
    }

    private static boolean hasEntry(Path jar, String entry) throws IOException {
        try (JarFile file = new JarFile(jar.toFile())) {
            return file.getJarEntry(entry) != null;
        }
    }

    public static void main(String[] args) throws Exception {
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException("Run with a full JDK 17+");
        }
        Path root = Files.createTempDirectory("duplicate-jar-fixture-");
        try {
            Path aJar = createJar(compiler, root, "A");
            Path bJar = createJar(compiler, root, "B");
            System.out.println("twoJarFiles="
                    + (Files.isRegularFile(aJar) && Files.isRegularFile(bJar)));
            System.out.println("bothContainClass="
                    + (hasEntry(aJar, CLASS_ENTRY) && hasEntry(bJar, CLASS_ENTRY)));
            URL a = aJar.toUri().toURL();
            URL b = bJar.toUri().toURL();
            ClassLoader platform = ClassLoader.getPlatformClassLoader();
            try (URLClassLoader ab = new URLClassLoader(new URL[]{a, b}, platform);
                 URLClassLoader ba = new URLClassLoader(new URL[]{b, a}, platform);
                 URLClassLoader parent = new URLClassLoader(new URL[]{a}, platform);
                 URLClassLoader child = new URLClassLoader(new URL[]{b}, parent)) {
                Class<?> classAB = ab.loadClass(BINARY);
                Class<?> classBA = ba.loadClass(BINARY);
                Class<?> classChild = child.loadClass(BINARY);
                System.out.println("abOrigin=" + origin(classAB));
                System.out.println("baOrigin=" + origin(classBA));
                System.out.println("abDefinedByAB=" + (classAB.getClassLoader() == ab));
                System.out.println("baDefinedByBA=" + (classBA.getClassLoader() == ba));
                System.out.println("sameBinaryName="
                        + classAB.getName().equals(classBA.getName()));
                System.out.println("sameRuntimeClass=" + (classAB == classBA));
                System.out.println("crossAssignable="
                        + classAB.isInstance(classBA.getDeclaredConstructor().newInstance()));
                System.out.println("repeatSameClass=" + (classAB == ab.loadClass(BINARY)));
                System.out.println("childOrigin=" + origin(classChild));
                System.out.println("childDefinedByParent="
                        + (classChild.getClassLoader() == parent));
                System.out.println("abFirstResource=" + read(ab.getResource(LABEL_ENTRY)));
                Enumeration<URL> resources = ab.getResources(LABEL_ENTRY);
                List<String> found = new ArrayList<>();
                while (resources.hasMoreElements()) {
                    found.add(read(resources.nextElement()));
                }
                System.out.println("abResources=" + String.join(",", found));
                System.out.println("resourceCount=" + found.size());
                System.out.println("stringFromBootstrap="
                        + (ab.loadClass("java.lang.String").getClassLoader() == null));
            }
        } finally {
            try (Stream<Path> paths = Files.walk(root)) {
                for (Path p : paths.sorted(Comparator.reverseOrder()).toList()) {
                    Files.deleteIfExists(p);
                }
            }
        }
    }
}
```

### 4.1. Biên dịch và chạy

Mở terminal trong thư mục chứa file `DuplicateJarFixture.java` và dùng JDK 17 trở lên:

```bash
javac --release 17 DuplicateJarFixture.java
java DuplicateJarFixture
```

**Không cần tạo sẵn** `A.jar` hoặc `B.jar`. Chúng được chương trình tạo trong thư mục tạm khi chạy, rồi xóa ở cuối. Vì mã nguồn sinh ra là Java 17-compatible, chương trình có thể chạy trên JDK 17+ với compiler đầy đủ.

### 4.2. Stdout kỳ vọng khi chạy fixture trên JDK 17+

Với Java compiler và bộ JAR do chương trình tạo, stdout dự kiến gồm 16 dòng:

```text
twoJarFiles=true
bothContainClass=true
abOrigin=A
baOrigin=B
abDefinedByAB=true
baDefinedByBA=true
sameBinaryName=true
sameRuntimeClass=false
crossAssignable=false
repeatSameClass=true
childOrigin=A
childDefinedByParent=true
abFirstResource=A
abResources=A,B
resourceCount=2
stringFromBootstrap=true
```

Nếu chạy trên một JDK tối giản không có `JavaCompiler`, chương trình cố ý báo `IllegalStateException` kèm hướng dẫn dùng JDK đầy đủ. Nếu không được phép tạo/xóa file tạm, lỗi I/O sẽ xuất hiện, không nên tự diễn giải thành lỗi parent-first.

### 4.3. Giải thích kết quả từng nhóm

**`twoJarFiles=true`:** file A.jar và B.jar thật đã được tạo. Điều này kiểm tra tồn tại file, nhưng một JAR tồn tại chưa chắc có class entry đúng — nên cần bước tiếp theo.

**`bothContainClass=true`:** dùng `JarFile.getJarEntry("fixture/same/Versioned.class")` để xác nhận cả hai JAR chứa cùng đường dẫn entry. Đây là kiểm tra cấu trúc JAR, không tự khẳng định JVM đã nạp class từ cả hai.

**`abOrigin=A`, `baOrigin=B`:** với parent platform không có fixture class, loader có URL[A,B] nhận bản A còn URL[B,A] nhận bản B. Đây là bằng chứng thực nghiệm về **thứ tự tìm local**.

**`abDefinedByAB=true`, `baDefinedByBA=true`:** `getClassLoader()` của các runtime classes đúng bằng loader tự định nghĩa chúng. Nếu parent có sẵn class, điều này có thể không còn đúng.

**`sameBinaryName=true`, `sameRuntimeClass=false`:** hai class có cùng tên Java nhưng khác defining loader, nên là **hai runtime types**. Không thể coi kết quả `getName().equals(...)` là bằng chứng cùng class.

**`crossAssignable=false`:** instance do class B tạo không phải instance của class A. Nếu cố ép kiểu trực tiếp giữa hai runtime class này, có thể gặp `ClassCastException` (trong ngữ cảnh cast phù hợp). Ví dụ dùng `Class.isInstance` để quan sát an toàn mà không cố tình làm chương trình thất bại.

**`repeatSameClass=true`:** loader AB đã định nghĩa `fixture.same.Versioned`, nên `ab.loadClass(BINARY)` lần sau trả lại cùng class object; đổi bytecode trên đĩa sẽ không tự tạo một định nghĩa mới trong cùng loader.

**`childOrigin=A`, `childDefinedByParent=true`:** child chỉ có B.jar, nhưng parent chứa A.jar. Theo parent-first delegation, child nhận Class do **parent** định nghĩa từ A.jar. Chỉ đổi JAR của child không làm bản B tự thắng.

**`abFirstResource=A`, `abResources=A,B`, `resourceCount=2`:** `getResource` trả resource đầu tiên; `getResources` liệt kê cả hai resource cùng tên trong các JAR. Resource lookup và class definition là **hai cơ chế khác nhau**. Hai resource không có nghĩa một loader đã định nghĩa hai class cùng binary name.

**`stringFromBootstrap=true`:** `java.lang.String` thuộc runtime JDK và do bootstrap loader định nghĩa. `null` từ `getClassLoader()` biểu diễn bootstrap trong API.

## 5. Đọc sơ đồ classloader của fixture

Hai thử nghiệm khác nhau đã được đưa vào cùng chương trình:

### 5.1. Kiểm thử thứ tự URL bằng hai loader độc lập

```text
Platform
    |
    +-- AB Loader: [A.jar, B.jar] -> Versioned.origin() = "A"
    |
    +-- BA Loader: [B.jar, A.jar] -> Versioned.origin() = "B"
```

Vì AB và BA là **hai defining loaders**, nên chúng có thể cùng định nghĩa tên `fixture.same.Versioned` như hai runtime classes độc lập. Trong từng loader riêng, không có hai định nghĩa class cùng binary name được tạo.

### 5.2. Kiểm thử parent-first bằng parent/child

```text
Platform
    |
    +-- Parent: [A.jar]
           |
           +-- Child: [B.jar]

Child.loadClass("fixture.same.Versioned")
    -> parent.loadClass(...)
    -> Parent trả class từ A.jar
    -> Child KHÔNG tự định nghĩa bản B
```

Đây là lý do phải có cả test **đảo URL** và test **parent delegation**. Nếu chỉ thử một loader AB, ta chưa chứng minh được trường hợp parent cung cấp class trước.

Nếu ứng dụng dùng child-first custom loader, phải viết test khác phản ánh đúng policy của nó, không lấy output parent-first ở đây làm kỳ vọng cho mọi framework.

## 6. Khi nào hai JAR được coi là “trùng lớp”?

Có nhiều kiểu trùng cần phân biệt:

| Hiện tượng | Ví dụ | Có nhất thiết là lỗi? |
| --- | --- | --- |
| Trùng **entry path** | Cả A.jar và B.jar chứa `fixture/same/Versioned.class` | Không tự động; loader có thể chọn một bản |
| Trùng **binary name** | Hai class files đều khai báo `fixture.same.Versioned` | Là xung đột cần quản lý nếu cùng đường tìm |
| Trùng bytecode byte-for-byte | Hai JAR sao chép đúng một `.class` | Vẫn có thể tạo runtime types khác nhau qua hai defining loaders |
| Trùng tên nhưng bytecode khác | Fixture A trả `A`, B trả `B` | Có thể ảnh hưởng logic hoặc tương thích ABI |
| Trùng **resource** | Cả hai chứa `fixture/label.txt` | Có thể có chủ đích, như service descriptors |
| Trùng package nhưng khác class | A.jar có `pkg.X`, B.jar có `pkg.Y` | Có thể hợp lệ, còn xét sealing/signers/JPMS |
| Hai module cùng package | Named modules trên module path | Có các quy tắc resolution/encapsulation riêng |

JAR format cho phép hai JAR **khác nhau** cùng chứa một entry path. Điều này khác với việc có **hai entry trùng tên trong cùng một JAR**, vốn cần tránh và thường bị công cụ tạo JAR từ chối bằng lỗi trùng entry.

### Phải kiểm tra cả tên thực trong class file

Đường `fixture/same/Versioned.class` trong JAR không tự chứng minh class file bên trong thật sự khai báo `fixture.same.Versioned`. Một file bị rename hoặc bytecode bị biến đổi có thể chứa binary name khác, dẫn đến lỗi “wrong name” khi nạp.

Trong fixture, `javac` biên dịch source cùng package/class name rồi chương trình lấy đúng path output, giúp tên path và binary name nhất quán. Với JAR nghi vấn, dùng `javap -verbose` hoặc công cụ phân tích class-file format thay vì dựa hoàn toàn vào tên entry.

## 7. Thử fixture trong dự án thực: giữ điều kiện tái lập

### 7.1. Không đưa hai class source cùng tên vào một lần javac

Sai lầm hay gặp là tạo hai file:

```text
src/a/fixture/same/Versioned.java
src/b/fixture/same/Versioned.java
```

rồi biên dịch cả hai cùng một invocation với chung output:

```bash
javac -d build/classes src/a/fixture/same/Versioned.java src/b/fixture/same/Versioned.java
```

Đây là **ví dụ lệnh sai có chủ ý**: khi cùng tạo `fixture.same.Versioned`, compiler có thể báo duplicate class. Nó **không** phải cách tạo hai JAR với bản bytecode độc lập.

Cách đúng là **hai invocation độc lập**, mỗi invocation có output root riêng:

```text
src-a/fixture/same/Versioned.java --javac--> classes-a/
src-b/fixture/same/Versioned.java --javac--> classes-b/

classes-a/fixture/same/Versioned.class --jar--> A.jar
classes-b/fixture/same/Versioned.class --jar--> B.jar
```

Chương trình fixture đã tự làm quy trình này bằng `compiler.run(...)` hai lần và `JarOutputStream`.

### 7.2. Không đặt fixture classes vào parent vô tình

Nếu chạy host với classpath:

```bash
java -cp "fixture/A.jar:fixture/B.jar:app/classes" my.app.Main
```

(đây là ví dụ Linux/macOS, Windows dùng `;`), application parent loader có thể nạp `fixture.same.Versioned` trước plugin child. Lúc đó việc đổi URL ở child chưa chắc làm kết quả thay đổi, vì parent-first đã ưu tiên parent.

Bài demo tránh sai số này bằng cách dùng **platform loader** làm parent của các URLClassLoader độc lập. Với ứng dụng thật, phải mô hình hóa class loader tree đúng với môi trường triển khai.

### 7.3. Wildcard không phải cách đảm bảo thứ tự JAR

Lệnh như:

```bash
java -cp "lib/*:app/classes" my.app.Main
```

được Java launcher mở rộng wildcard thành các JAR trong thư mục. Thứ tự wildcard expansion không được đảm bảo là alphabetic hoặc “bản mới nhất trước”; không nên xây dựng test kỳ vọng A thắng B chỉ vì tên file.

Trong fixture, mảng `new URL[]{a,b}` và `new URL[]{b,a}` được khai báo **rõ thứ tự**, nên không phụ thuộc wildcard.

### 7.4. Tính lặp lại khi build/test

Để test dễ tái lập, nên:

- Dùng cùng JDK toolchain/runtime target.
- Biên dịch tách A/B để không phụ thuộc classpath tình cờ.
- Gán binary name cố định và marker output rõ ràng.
- Đặt tên JAR/path tạm khác nhau, tách khỏi project artifact.
- Để test tự tạo và dọn fixture thay vì dùng một JAR sửa tay từ lần test trước.
- Không chọn nguồn class dựa trên timestamp, file size, filename version.
- Đảm bảo manifest không thêm classpath gián tiếp làm thứ tự tìm khó kiểm soát.
- Dùng class loaders riêng cho các tình huống khác nhau, đóng mỗi loader.
- Không để IDE/test runner tự thêm fixture classes vào application classpath.
- Kiểm tra kết quả **Class<?> thực tế**, không chỉ in mọi file tìm được trong JAR.

## 8. Giữ fixture để kiểm tra bằng jar và javap

Chương trình hoàn chỉnh ở phần 4 **xóa A.jar và B.jar sau khi chạy**, vì đây là test tự dọn. Muốn kiểm tra thủ công bằng `jar tf` và `javap`, có hai lựa chọn:

1. Dùng debugger hoặc một bản test phụ **được thiết kế để giữ artifacts** trong thư mục cụ thể thay vì xóa.
2. Dùng một quy trình build riêng để đóng gói hai bản source vào hai JAR ổn định phục vụ kiểm thử tích hợp.

Không nên chạy `jar tf A.jar` sau khi chương trình đã xóa thư mục tạm rồi kết luận fixture lỗi vì file không còn tồn tại.

Khi đã có hai JAR **được giữ lại**, lệnh kiểm tra:

```bash
jar tf A.jar
jar tf B.jar
javap -classpath A.jar -public fixture.same.Versioned
javap -classpath B.jar -public fixture.same.Versioned
```

`jar tf` liệt kê entry; `javap` hiển thị class và signatures. Vì bản A/B có cùng method descriptor `origin(): String`, `javap -public` **không cho thấy trực tiếp giá trị A/B** trong method body. Muốn soi bytecode method có thể dùng:

```bash
javap -c -classpath A.jar fixture.same.Versioned
javap -c -classpath B.jar fixture.same.Versioned
```

Lệnh này hiển thị instructions, trong đó có hằng `"A"` hoặc `"B"` trong bytecode tương ứng. Với nhiều class đang bị trùng, hãy đối chiếu cả tên, method descriptors và dependencies chứ không chỉ một method trả string.

### Kiểm chứng bằng CodeSource

Nếu cần biết JAR nào thật sự cung cấp một class đã nạp, có thể dùng:

```java
java.security.CodeSource codeSource =
        type.getProtectionDomain().getCodeSource();

System.out.println(codeSource == null
        ? "<unknown>"
        : codeSource.getLocation());
```

Đây là snippet, cần `Class<?> type` đã lấy từ lời gọi runtime. Với `URLClassLoader` nạp class từ JAR bình thường, `CodeSource.getLocation()` thường trỏ về URL JAR được chọn. Tuy nhiên, CodeSource có thể `null` với bootstrap/custom memory loaders; không nên coi thiếu CodeSource là bằng chứng class không được định nghĩa.

Trong test A/B, có thể bổ sung assertion so `type.getClassLoader()` và CodeSource URI với `A.jar`/`B.jar` theo điều kiện môi trường. Đây là **kiểm chứng bổ sung**, còn kết quả chính là method marker cùng loader identity.

## 9. Resource trùng tên và class trùng tên cho hai loại bằng chứng

Fixture đặt `fixture/label.txt` ở cả A.jar và B.jar. `ab.getResource("fixture/label.txt")` trả tài nguyên đầu tiên theo thứ tự tìm, còn `ab.getResources(...)` có thể liệt kê cả hai. Điều này **không có nghĩa AB loader đã định nghĩa hai runtime classes** với binary name `fixture.same.Versioned`: `loadClass` trả một `Class<?>` cho mỗi định nghĩa trong loader đó.

Trong ứng dụng thực tế, `META-INF/services/...` cũng có thể có nhiều bản resource hợp lệ và được `ServiceLoader` tiêu thụ. Phép thử resource ở đây chỉ kiểm tra *candidate resources* của fixture; bài **Kiểm chứng tìm tài nguyên và provider dịch vụ** dành riêng cho descriptor, API/service identity, TCCL và provider instantiation.

## 10. Từ fixture tới kiểm thử regression tự động

Fixture có thể chuyển thành các assert thay vì chỉ in stdout. Một test suite nên kiểm chứng:

| Assertion | Kỳ vọng | Điều được bảo vệ |
| --- | --- | --- |
| Hai file JAR tồn tại | A.jar và B.jar đều là file | Packaging đúng |
| Hai JAR có cùng class entry | `JarFile.getJarEntry(CLASS_ENTRY) != null` | Duplicate binary-name candidate |
| URL[A,B] → `origin()` | `A` | URL order local |
| URL[B,A] → `origin()` | `B` | Đảo URL đổi bản class |
| `classAB.getClassLoader() == ab` | `true` | AB là defining loader |
| `classBA.getClassLoader() == ba` | `true` | BA là defining loader |
| Hai `Class<?>` objects | `classAB != classBA` | Type identity khác |
| Instance B kiểm bởi class A | `isInstance(...) == false` | Không tự cast xuyên loader |
| Lặp `ab.loadClass(...)` | Trả cùng `Class<?>` | Cached class trong loader |
| Child(B) có Parent(A) | Nhận class từ parent A | Parent-first delegation |
| Resource A/B | Enumeration có hai marker | Class vs resource semantics |
| JDK String | Defining loader là bootstrap | Nạp class nền tảng |

Một hàm assertion Java 17 có thể dùng:

```java
static void check(boolean condition, String description) {
    if (!condition) {
        throw new AssertionError(description);
    }
}
```

Đây là helper, không phải chương trình độc lập. Bạn có thể thay các dòng `System.out.println` trong demo bằng `check(...)` với các kết quả mong đợi.

### Kiểm tra thứ tự và tránh flakiness

Khi kiểm tra fixture:

- **Không** dùng `ClassLoader.toString()`, object identity hash hoặc đường dẫn temp ngẫu nhiên làm stdout chính xác.
- **Không** dựa vào thời điểm JVM chạy class initializer nếu không chủ động kích hoạt/quan sát.
- **Không** yêu cầu garbage collector unload loader ngay sau `close()`.
- **Không** dùng cache từ lượt test trước khi cần nạp định nghĩa mới; tạo loader mới.
- **Không** chạy nhiều test dùng cùng binary name trong application parent classpath khiến kết quả phụ thuộc thứ tự test.
- Nếu test chạy nhiều thread, kiểm soát trạng thái môi trường và không dùng mutable URL list chung.
- Nên dùng tên package marker riêng, tránh xung đột với dependency thật trong test runner.

Fixture nhỏ có thể được nâng cấp thành test kiểm tra binary compatibility bằng cách cho A.jar và B.jar có **API khác nhau**, nhưng phải phân biệt kết quả cố ý fail do ABI với lỗi setup classloader.

## 11. Biến thể nâng cao: xung đột phiên bản API

Trong fixture chính, cả A và B cung cấp:

```java
public String origin()
```

nên code gọi method có cùng chữ ký ở hai bản. Để minh họa `NoSuchMethodError` do compile/runtime version mismatch, tạo hai bản library khác:

**Phiên bản biên dịch A:**

```java
package fixture.same;
public final class Versioned {
    public String origin() {
        return "A";
    }
    public String newMethod() {
        return "only-in-A";
    }
}
```

**Phiên bản runtime B:**

```java
package fixture.same;
public final class Versioned {
    public String origin() {
        return "B";
    }
}
```

Đây là **hai source versions thay thế nhau**, không được compile vào cùng một output root. Nếu consumer đã được biên dịch để gọi `Versioned.newMethod()` của A nhưng runtime classloader lại định nghĩa `Versioned` từ B, JVM có thể ném `NoSuchMethodError` khi resolution/invocation cần method ấy.

Kịch bản này **không phải stdout của demo chính**, mà là hướng mở rộng có chủ đích. Muốn kiểm thử chính xác:

1. Compile consumer với A.jar trên compile classpath.
2. Runtime loại A.jar khỏi loader sẽ định nghĩa `Versioned`, cung cấp B.jar thay thế.
3. Quan sát exception thật, stack trace và defining loader.
4. So method descriptors bằng `javap -classpath ... -p`.
5. Không dùng `catch Throwable` che lỗi link-time rồi báo test pass giả.

**Kết luận:** duplicate class không luôn gây exception ngay ở thời điểm nạp; đôi khi logic âm thầm thay đổi, đôi khi mới lỗi ở lần gọi method phụ thuộc vào API chỉ có trong phiên bản khác.

## 12. Giới hạn khi chuyển fixture sang JAR thật

Thí nghiệm dùng classpath/unnamed modules và hai class đơn giản. Với JAR có **package sealing** hoặc các chữ ký signer khác nhau, định nghĩa các class trong cùng package có thể thất bại trước khi ta quan sát phương thức `origin()`; các lỗi `SecurityException` hoặc ràng buộc certificate/package phải được điều tra riêng. Khi dùng **JPMS named modules**, module resolution, readability, exports và package conflicts áp dụng khác với thứ tự URL của classpath.

Không suy rộng output `AB=A` thành quy tắc chọn class cho mọi module layer, application server hay plugin loader có policy riêng. Bài kiểm chứng package-private tập trung vào **runtime package identity và loader** thay vì cùng đường dẫn package.

## 13. Lỗi thường gặp khi tạo và chạy duplicate-JAR fixture

| Triệu chứng | Nguyên nhân khả dĩ | Cách xử lý |
| --- | --- | --- |
| `duplicate class` tại compile time | Biên dịch hai source cùng binary name vào một invocation/output | Compile A/B độc lập và tách output |
| `ClassNotFoundException` | JAR entry path sai, URL không tồn tại, tên binary không đúng | Xác minh `JarFile`, path, `loadClass` name |
| `NoClassDefFoundError: wrong name` | Đổi tên entry file nhưng bytecode khai báo tên khác | Kiểm tra constant pool/class identity |
| `ClassFormatError` / `VerifyError` | Bytes hỏng/sinh không hợp lệ | Dùng `javac`, `javap -verbose`, kiểm tra source artifact |
| `UnsupportedClassVersionError` | Biên dịch bằng JDK mới hơn runtime hỗ trợ | Dùng `--release 17` và chạy JDK 17+ |
| A/B không đổi khi đảo URL | Parent đã có class, class đã cached hoặc đang kiểm tra cùng loader | In `getClassLoader()`, tạo loader riêng |
| `ClassCastException` cùng tên class | Hai defining loaders khác nhau | Chia sẻ API/SPI qua parent, đừng cast tùy tiện |
| `NoSuchMethodError` | Runtime chọn class version không có method compile-time | So ABI của hai JAR và CodeSource |
| Resource trả A dù class local là B | Parent-first resource lookup hoặc custom policy | Phân biệt resource vs class search |
| `SecurityException: sealing violation` | Package sealed bị định nghĩa từ nguồn không hợp lệ | Kiểm tra manifest và code source |
| JAR không xóa được trên Windows | File handle/JarFile/stream/loader chưa đóng | Dùng try-with-resources cho tất cả |
| `ToolProvider.getSystemJavaCompiler() == null` | Đang chạy runtime image không có compiler module | Dùng JDK đầy đủ |
| Stdout chứa path/ID ngẫu nhiên | Test log phụ thuộc temp directory, identity hash | Chỉ assert marker/boolean ổn định |

### Sai lầm: kiểm tra mỗi File tồn tại

`Files.exists(A.jar)` và `Files.exists(B.jar)` chưa đủ. JAR có thể rỗng, chứa sai class entry hoặc chứa cùng bytecode không phân biệt được bằng output. Cần kiểm tra bằng `JarFile`, rồi nạp class và xác nhận method trả marker dự kiến.

### Sai lầm: tin rằng tên file JAR cho biết “bản thắng”

Một file `lib-2.0.jar` không mặc nhiên được JVM ưu tiên hơn `lib-1.0.jar`. Với URLClassLoader, parent delegation, URL order và các nguồn gián tiếp liên quan mới là điều cần phân tích. Với Maven/Gradle, bước dependency resolution còn có thể chọn/loại phiên bản trước khi runtime được cấu hình.

### Sai lầm: không đóng các nguồn JAR

Nếu giữ `JarFile`, `JarInputStream` hoặc `URLClassLoader` mở vô hạn, test có thể để lại file handles và ảnh hưởng việc xóa/cập nhật fixture trên Windows. Ví dụ sử dụng try-with-resources và dọn thư mục tạm trong `finally`.

## 14. Ba phân biệt khi diễn giải fixture

- **Hai JAR cùng entry** khác với **một runtime loader định nghĩa hai class cùng tên**. Trong từng loader AB/BA, class được định nghĩa một lần và được cache theo identity.
- **URL order** quyết định lựa chọn cục bộ khi parent chưa cung cấp type; parent delegation có thể chọn version từ parent trước.
- **Hai `Class<?>` cùng `getName()`** không bảo đảm `==` hoặc cast hợp lệ nếu defining loaders khác nhau. Hãy đối chiếu defining loader và thực nghiệm `Class.isInstance(...)`.

## 15. Bài tập tự kiểm tra

**Câu 1.** Vì sao fixture phải biên dịch A và B trong hai output roots riêng?

**Đáp án:** Vì hai source cùng binary name; biên dịch chung có thể gây duplicate-class compile error, còn ta muốn tạo hai JAR độc lập mỗi JAR chứa một định nghĩa.

**Câu 2.** Nếu URLClassLoader AB có URL[A,B] và parent platform không có fixture class, `origin()` trả gì?

**Đáp án:** `A` theo đường tìm local thông thường; fixture xác nhận `abOrigin=A`.

**Câu 3.** Nếu đảo URL thành [B,A] trong loader **mới**, kết quả là gì?

**Đáp án:** `B`, và class do loader BA định nghĩa là runtime type khác bản do AB định nghĩa.

**Câu 4.** Child có B.jar nhưng parent có A.jar. Theo parent-first, `child.loadClass(BINARY)` trả bản nào?

**Đáp án:** Bản A do parent định nghĩa, nếu class hợp lệ và parent nạp được.

**Câu 5.** Hai `Class<?>` có `getName()` bằng nhau, có chắc `classA == classB`?

**Đáp án:** Không; cần cùng defining loader. Demo trả `sameRuntimeClass=false`.

**Câu 6.** Vì sao `getResources("fixture/label.txt")` có thể thấy cả A và B dù `loadClass` chọn bản A?

**Đáp án:** Resource enumeration trả nhiều URL trùng tên, còn class loading chọn/ghi nhận một định nghĩa theo delegation và loader.

**Câu 7.** Sau khi `ab.loadClass(BINARY)` đã trả class A, nếu sửa JAR A trên đĩa, gọi lại cùng loader có trả code mới không?

**Đáp án:** Không tự động. Loader đã ghi nhận class, và việc thay artifact đang mở còn tạo rủi ro file handle/trạng thái; phải dùng loader và fixture lifecycle phù hợp.

**Câu 8.** Hai bản class có API khác nhau. Dạng lỗi runtime điển hình khi bytecode consumer được compile với A nhưng runtime chọn B thiếu method là gì?

**Đáp án:** `NoSuchMethodError`, nếu lời gọi method bị thiếu được JVM phân giải/thực thi.

**Câu 9.** Khi lớp được nạp “sai JAR”, thông tin nào nên log đầu tiên?

**Đáp án:** Class thực tế, `type.getClassLoader()`, `CodeSource` nếu có, parent chain, URL order và runtime dependency graph. Không chỉ tên file trong lib directory.

**Câu 10.** Vì sao fixture không đặt hai JAR thành named modules có module-info.java?

**Đáp án:** Vì mục tiêu là kiểm chứng URLClassLoader/classpath search; JPMS có quy tắc module resolution và split package khác, không nên nhập nhằng.

## 16. Checklist kiểm chứng trước khi xem test là đạt

- [ ] Hai source classes có **cùng package và class binary name**.
- [ ] Hai source khác ở method marker, giúp nhận biết A/B.
- [ ] Biên dịch độc lập bằng JDK 17-compatible bytecode.
- [ ] Đóng gói đúng `fixture/same/Versioned.class` vào mỗi JAR.
- [ ] Kiểm tra JAR files tồn tại và `JarFile.getJarEntry` trả non-null.
- [ ] URL array AB/BA khai báo rõ thứ tự; không dùng wildcard phụ thuộc môi trường.
- [ ] Parent của AB/BA không có class fixture.
- [ ] Thử riêng parent A / child B để chứng minh parent-first.
- [ ] Đối chiếu `Class.getClassLoader()`, tên nhị phân, `Class<?> ==`, `isInstance`.
- [ ] Gọi cùng loader hai lần để xác nhận không tự định nghĩa lại class.
- [ ] Kiểm tra resource enumeration riêng với class lookup.
- [ ] Đóng JarFile/streams/URLClassLoader và xóa tệp tạm.
- [ ] Không ép GC/unload làm một phần stdout test.
- [ ] Với test sản phẩm, kiểm tra cả nguồn JAR và ABI của class thực tế.
- [ ] Không dùng các kết quả dựa vào tên file, timestamp, temp path hoặc hash làm assertion duy nhất.

## 17. Kết luận và tài liệu tham khảo

Fixture có hai JAR cùng định nghĩa `fixture.same.Versioned` nhưng trả marker A/B là một cách kiểm chứng rất trực quan: **URL order** có ý nghĩa khi loader tìm local, **parent-first delegation** có thể vượt qua thứ tự local của child, và **hai defining loaders riêng** có thể tạo hai runtime classes cùng tên nhưng không tương thích kiểu. Việc thêm resource trùng tên giúp tách biệt **resource enumeration** với **class definition**, tránh chẩn đoán sai chỉ từ `getResources`.

Khi xây dựng fixture, cần biên dịch hai source riêng, đóng gói đúng class entry, đảm bảo parent không vô tình chứa class, dùng JDK version ổn định và có cleanup. Từ đó có thể mở rộng thành regression test cho JAR collision, plugin isolation, dependency version mismatch và classloader routing.

Tài liệu chuẩn:

- Java SE 17 `URLClassLoader` API (URL search, `getURLs`, parent): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html
- Java SE 17 `ClassLoader` API (`loadClass`, `getResources`, delegation): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html
- Java SE 17 `JarOutputStream`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/jar/JarOutputStream.html
- Java SE 17 `JarFile`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/jar/JarFile.html
- Java SE 17 `JavaCompiler` API: https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/JavaCompiler.html
- Java SE 17 launcher `java` (classpath wildcard): https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html
- JVMS 17 §5.3, *Creation of Classes and Interfaces* (binary name + defining loader): https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.3
