# Kiểm tra bytecode của dependency và công cụ sinh lớp (Java 15 và các JDK hiện đại)

> **Chủ đề cha: Tương thích và build.** Một ứng dụng có thể biên dịch thành công nhưng thất bại lúc chạy vì `.class` của thư viện quá mới, annotation processor chưa tạo đủ lớp, thư viện thay đổi method signature hoặc một bytecode generator như ASM/Byte Buddy chưa hỗ trợ class-file version mới. Để xây dựng ứng dụng Java tương thích, không chỉ kiểm `App.class`: phải kiểm **JDK biên dịch, JDK đích, dependencies trực tiếp/transitive, multi-release JAR, lớp sinh tại build time, bytecode được transform/define runtime và artifact thực tế đem deploy**.

**Mốc Java 15:** class-file major `59`. Bài này lấy Java 15 làm bối cảnh lịch sử, nhưng ưu tiên Java 17+ cho ví dụ chạy được và hướng dẫn vẫn áp dụng ở JDK 21/25/26/27. Không khuyến nghị sử dụng một JDK 15 hết bảo trì để triển khai ứng dụng mới.

## 1. Những vấn đề cần phân biệt

Một pipeline thông thường:

~~~text
Java sources
    │
    ├─ javac --release 17 -> application classes, major 61
    ├─ dependency JAR A -> class major 61
    ├─ dependency JAR B -> class major 65 (Java 21!)
    ├─ annotation processors -> generated .java / .class
    ├─ bytecode enhancement -> transformed .class
    └─ packaging -> final JAR/WAR/container image
                                  │
                                  ▼
                          Actual Java 17 runtime
~~~

**Bốn ranh giới tương thích chính:**

| Lớp kiểm | Câu hỏi | Sai hỏng tiêu biểu |
| --- | --- | --- |
| **Class-file format** | JVM đích hiểu major/minor của class không? | `UnsupportedClassVersionError` |
| **JDK/API** | Class có gọi API chỉ xuất hiện ở JDK mới hơn không? | `NoSuchMethodError` hoặc `NoClassDefFoundError` |
| **Binary linkage** | Method/field/class mà app biên dịch dựa vào có tồn tại khi chạy? | `NoSuchMethodError`, `NoSuchFieldError` |
| **Generated/runtime code** | Processor, proxy, agent, enhancer tạo bytecode hợp lệ không? | `VerifyError`, `ClassFormatError`, lỗi ASM/parser |

**Major version hợp lệ là điều kiện cần, không đủ.** Một ứng dụng chỉ có class major61 vẫn có thể lỗi nếu runtime jar khác compile jar hoặc reflective access bị từ chối. Một static scanner cũng không thấy tất cả các lớp được sinh động khi ứng dụng chạy.

## 2. Class-file header, major và minor

Tám bytes đầu của class theo JVMS `4.1:

~~~text
Offset  Size  Field
0       4     magic = CA FE BA BE
4       2     minor_version (unsigned big-endian)
6       2     major_version (unsigned big-endian)
8       ...   constant pool và các thành phần khác
~~~

Ví dụ:

~~~text
CA FE BA BE 00 00 00 3D ...
            minor major: 0x003D = 61 = Java 17
~~~

| Java release | Class major |
| ---: | ---: |
| 8 | 52 |
| 11 | 55 |
| **15** | **59** |
| 17 | 61 |
| 21 | 65 |
| 24 | 68 |
| 25 | 69 |
| 26 | 70 |
| 27 | 71 |

Đây là các mốc từ bảng phiên bản của Java Virtual Machine Specification, không phải số bản release của một thư viện. Class major61 cần runtime hỗ trợ Java17 classfile hoặc mới hơn. Runtime Java15 chỉ hỗ trợ đến major59.

**Minor version và preview:** Với class major từ 56 (Java12) trở lên, minor `0` thông thường; minor `65535` biểu thị class dùng preview features của **đúng Java release**. Ví dụ class `61.65535` cần JVM Java17 với preview enabled, không thể dùng JVM Java21 và bật `--enable-preview` để đọc class preview của Java17. Không nên đưa preview classfile vào một library hứa hỗ trợ nhiều Java release.

**Không được đổi 2 bytes major trong file hex để backport.** Compiler có thể phát ra constant-pool entries, instructions, attributes, stack map frames hay runtime semantics mà JVM cũ không hiểu. Muốn hỗ trợ runtime cũ phải biên dịch/bảo trì code và dependencies đúng target, rồi test thực tế.

## 3. Chẩn đoán từ exception

| Exception/triệu chứng | Khả năng cao | Kiểm gì? |
| --- | --- | --- |
| `UnsupportedClassVersionError` | JVM gặp class major quá cao hoặc preview class không phù hợp | `java -version`, class minor/major |
| `ClassFormatError` | Class bytes không hợp lệ | Generator, transformer, header, constant pool |
| `VerifyError` | Bytecode sai type/stackmap/control flow | ASM/Byte Buddy/agent version, verifier |
| `NoSuchMethodError` | Compile API và runtime API không khớp | Method descriptor, dependency convergence |
| `NoSuchFieldError` | Field biến mất/đổi descriptor | Runtime jar và binary ABI |
| `AbstractMethodError` | Interface/class implementation không tương thích | Library versions, linkage |
| `ClassNotFoundException` | ClassLoader không tìm thấy class | Classpath, packaging, module path |
| `NoClassDefFoundError` | Dependency không load/init được | Root cause, transitive jar và runtime |
| `InaccessibleObjectException` | Reflection bị strong encapsulation chặn | Framework update, JPMS access |
| `IllegalAccessError` | Bytecode access không hợp lệ | Module/package/visibility and ABI |
| `Unsupported class file major version 70` từ ASM | Tool parser quá cũ, không nhất thiết JVM cũ | Stack trace, ASM/Byte Buddy version |
| Generated class không tồn tại | Processor không chạy hoặc không đóng gói | Build logs, generated-src, output/classes |

**Nên ghi full exception và class name** trước khi chọn hướng sửa. Không gom tất cả thành “Java không tương thích”.

## 4. Dùng công cụ JDK có sẵn

### 4.1. `javap`: version và bytecode của một class

~~~bash
# Class file riêng:
javap -verbose out/com/example/MyClass.class

# Class trong JAR:
javap -verbose -classpath library.jar com.example.MyClass
~~~

Trong output, tìm `minor version`, `major version`, methods, descriptors, constant pool, flags và attributes. `javap` không tự quét mọi class trong JAR hoặc toàn dependency graph; nó chỉ hiển thị các class được yêu cầu.

### 4.2. `jar`: archive thực tế và multi-release consistency

~~~bash
jar --list --file library.jar
jar --validate --file library.jar
~~~

`jar --list` cho thấy class, module descriptor, manifests, services, resources và các paths `META-INF/versions/N`. `jar --validate` có thể báo duplicate ZIP entry names, tên entry không hợp lệ và một số vi phạm API consistency của multi-release JAR. **Nó không chứng minh thư viện có binary linkage hoặc security hoàn toàn đúng.**

### 4.3. `jdeps`: dependencies ở cấp package/class/module

~~~bash
jdeps --summary library.jar
jdeps --verbose:class --class-path 'libs/*' app.jar
jdeps --jdk-internals app.jar
jdeps --multi-release 17 --summary library-mr.jar
~~~

`jdeps` giúp phát hiện phụ thuộc JDK internal APIs và các static dependencies nhưng **không nhìn thấy đầy đủ** reflection, ServiceLoader runtime configuration, JNI hay dynamic/hidden classes. Đối với JAR chứa nhiều phiên bản, luôn nêu `--multi-release N` để tránh hiểu sai target.

### 4.4. `javac --release`: bảo đảm đúng và giới hạn của nó

~~~bash
javac --release 17 -encoding UTF-8 \
    -d out src/com/example/App.java
~~~

`--release 17` quy định:
1. Language rules ở Java17.
2. Class-file target Java17 (thường major61).
3. **JDK platform APIs của Java17** được phép dùng.

Khác với chỉ `-source 17 -target 17`, `--release` có kiểm API surface JDK target. Tuy nhiên nó **không biên dịch lại các dependency JARs**. Nếu một class của `library.jar` đã có major65 thì App.class major61 vẫn không thể khiến thư viện Java21 chạy trên Java17.

Giá trị `--release` mà một `javac` mới hỗ trợ gồm current và một số bản cũ; không mặc định `--release 15` vẫn có ở mọi JDK tương lai. Kiểm `javac --help` và dùng toolchain phù hợp.

## 5. Ví dụ 1: chương trình kiểm class-file trong JAR

Ta viết một scanner Java17 không cần thư viện ngoài. Nó dùng `ZipFile` đọc mọi `.class` vật lý, kiểm magic/major/minor, đọc manifest `Multi-Release: true`, chọn class theo phiên bản Java mục tiêu và in kết quả. Nó cũng cố tình từ chối **preview classfiles** khi kiểm ở chế độ without-preview.

**Tệp `ClassFileVersionAudit.java` (độc lập Java17+):**

~~~java
import java.io.DataInputStream;
import java.nio.file.Path;
import java.util.Enumeration;
import java.util.Map;
import java.util.TreeMap;
import java.util.zip.ZipEntry;
import java.util.zip.ZipFile;
import java.util.jar.Manifest;

public class ClassFileVersionAudit {
    record Entry(String path, String logical, int layer,
                 int minor, int major) {}

    static Entry read(ZipFile zip, ZipEntry zipEntry)
            throws Exception {
        String path = zipEntry.getName();
        int layer = 0;
        String logical = path;
        String prefix = "META-INF/versions/";

        if (path.startsWith(prefix)) {
            String rest = path.substring(prefix.length());
            int slash = rest.indexOf('/');
            if (slash < 0) return null;
            try {
                layer = Integer.parseInt(
                        rest.substring(0, slash));
            } catch (NumberFormatException ignored) {
                return null;
            }
            if (layer < 9) return null;
            logical = rest.substring(slash + 1);
        }

        try (DataInputStream in = new DataInputStream(
                zip.getInputStream(zipEntry))) {
            if (in.readInt() != 0xCAFEBABE) {
                throw new IllegalArgumentException(
                        "Bad class magic: " + path);
            }
            int minor = in.readUnsignedShort();
            int major = in.readUnsignedShort();
            return new Entry(path, logical, layer, minor, major);
        }
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            throw new IllegalArgumentException(
                "Usage: ClassFileVersionAudit jar targetRelease");
        }
        int target = Integer.parseInt(args[1]);
        if (target < 9) {
            throw new IllegalArgumentException(
                    "target must be >=9");
        }

        try (ZipFile zip =
                     new ZipFile(Path.of(args[0]).toFile())) {
            ZipEntry mf = zip.getEntry("META-INF/MANIFEST.MF");
            boolean mr = false;
            if (mf != null) {
                try (var input = zip.getInputStream(mf)) {
                    Manifest manifest = new Manifest(input);
                    mr = "true".equalsIgnoreCase(
                        manifest.getMainAttributes()
                                .getValue("Multi-Release"));
                }
            }

            Map<String, Entry> selected = new TreeMap<>();
            int physical = 0;
            Enumeration<? extends ZipEntry> all = zip.entries();

            while (all.hasMoreElements()) {
                ZipEntry item = all.nextElement();
                if (item.isDirectory()
                        || !item.getName().endsWith(".class")) {
                    continue;
                }
                physical++;
                Entry e = read(zip, item);
                if (e == null) continue;

                if (e.layer() != 0
                        && (!mr || e.layer() > target)) {
                    continue;
                }

                Entry previous = selected.get(e.logical());
                if (previous == null
                        || e.layer() > previous.layer()) {
                    selected.put(e.logical(), e);
                }
            }

            System.out.println("multiRelease=" + mr);
            System.out.println("physicalClasses=" + physical);
            System.out.println("effectiveClasses=" +
                    selected.size());

            boolean compatible = true;
            for (Entry e : selected.values()) {
                boolean preview = e.minor() == 65535;
                boolean ok = e.major() <= target + 44
                        && (e.major() <= 55
                                || e.minor() == 0);
                compatible &= ok;

                System.out.println("class=" + e.logical()
                        + " source=" + e.path()
                        + " major=" + e.major()
                        + " minor=" + e.minor()
                        + " preview=" + preview
                        + " compatibleWithoutPreview=" + ok);
            }
            System.out.println(
                    "targetCompatibleWithoutPreview=" +
                    compatible);
        }
    }
}
~~~

Chạy sau khi tạo một JAR cần kiểm:

~~~bash
javac --release 17 -encoding UTF-8 ClassFileVersionAudit.java
java ClassFileVersionAudit dependency.jar 17
~~~

**Giới hạn quan trọng của demo:** Nó chỉ đánh giá class-file headers của effective entries trên target `≥9`. Nó chưa validate toàn bộ classfile layout/stackmaps, module rules, public API trong MR-JAR, signature/trust, ZIP bomb limits, dependency transitives, API ABI hoặc runtime generators. Nếu path của một versioned entry bị sai định dạng, demo bỏ qua entry đó; trong **CI production nên reject malformed archive**. Không dùng bản demo này làm bộ quét input không tin cậy mà không có limits.

## 6. Ví dụ 2: tạo multi-release JAR và kiểm theo từng Java target

**Multi-release JAR** có manifest `Multi-Release: true` và các class variants trong `META-INF/versions/N/`. Với target runtime `N`, loader tìm variant có version cao nhất `≤N` rồi mới fallback về base. Một entry Java17 không tự làm Java11 mất khả năng dùng JAR **nếu entry chỉ nằm ở versioned directory và base hợp lệ**.

### 6.1. Hai phiên bản cùng public API

**Tệp `src/base/demo/LibApi.java`:**

~~~java
package demo;

public final class LibApi {
    public static String value() {
        return "base11";
    }
}
~~~

**Tệp `src/v17/demo/LibApi.java`:**

~~~java
package demo;

public final class LibApi {
    public static String value() {
        return "variant17";
    }
}
~~~

Từ thư mục chứa hai source files, dùng Bash:

~~~bash
mkdir -p out/base out/v17

javac --release 11 -d out/base src/base/demo/LibApi.java
javac --release 17 -d out/v17 src/v17/demo/LibApi.java

jar --create --file lib-mr.jar \
    -C out/base . \
    --release 17 -C out/v17 .

jar --create --file lib17.jar -C out/v17 .
jar --validate --file lib-mr.jar
jar --list --file lib-mr.jar

javap --multi-release 11 -verbose \
    -classpath lib-mr.jar demo.LibApi
javap --multi-release 17 -verbose \
    -classpath lib-mr.jar demo.LibApi

java ClassFileVersionAudit lib-mr.jar 11
java ClassFileVersionAudit lib-mr.jar 17
java ClassFileVersionAudit lib17.jar 15
~~~

Các lệnh đã được kiểm chứng tương đương trên PowerShell/JDK24, với `jar --validate` hoàn thành thành công. Bash dùng `\` để nối dòng; Windows PowerShell cần viết command trên một dòng hoặc dùng cú pháp continuation riêng.

### 6.2. Output major của `javap`

~~~text
javap --multi-release 11:
  major version: 55

javap --multi-release 17:
  major version: 61
~~~

Nếu không truyền `--multi-release`, công cụ `javap` có thể hiển thị **base class** thay vì versioned class; trong JDK24 thử nghiệm, default đọc major55. Hãy chỉ rõ target khi audit MR-JAR.

### 6.3. Stdout chính xác của scanner với JAR thử nghiệm

**MR-JAR / target 11:**

~~~text
multiRelease=true
physicalClasses=2
effectiveClasses=1
class=demo/LibApi.class source=demo/LibApi.class major=55 minor=0 preview=false compatibleWithoutPreview=true
targetCompatibleWithoutPreview=true
~~~

**MR-JAR / target 17:**

~~~text
multiRelease=true
physicalClasses=2
effectiveClasses=1
class=demo/LibApi.class source=META-INF/versions/17/demo/LibApi.class major=61 minor=0 preview=false compatibleWithoutPreview=true
targetCompatibleWithoutPreview=true
~~~

**JAR thường Java17 / target 15:**

~~~text
multiRelease=false
physicalClasses=1
effectiveClasses=1
class=demo/LibApi.class source=demo/LibApi.class major=61 minor=0 preview=false compatibleWithoutPreview=false
targetCompatibleWithoutPreview=false
~~~

Đây là kiểm **format-level** theo target mô phỏng; không có nghĩa đã khởi chạy Java11 hoặc Java15 thật. Khi library tuyên bố hỗ trợ các runtime ấy, phải **chạy test trên những JDK thực tế**. `jar --validate` kiểm một số ràng buộc MR-JAR, còn runtime tests kiểm kết quả sử dụng.

## 7. Direct/transitive dependencies và artifact cuối

Một build có thể có:

~~~text
app major61 (target Java17)
    │
    ├─ lib-A major61
    │     └─ lib-B major65 (Java21, transitive)
    ├─ lib-C multi-release JAR
    ├─ library plugin chứa ASM version cũ
    ├─ annotation processor chỉ chạy trong javac
    └─ runtime agent sinh/biến đổi class khi start
~~~

**Không chỉ kiểm các dependency khai báo trực tiếp.** Thư viện B có thể được tải lazy lúc một feature chạy và tạo `UnsupportedClassVersionError` nhiều giờ sau khi ứng dụng start. Tương tự, trong Spring Boot/fat JAR có nested JARs và class relocation từ shading; bản runtime thật có thể không trùng với Maven compile classpath.

Lệnh tìm dependency graph:

~~~bash
# Với dự án Maven:
mvn dependency:tree

# Với dự án Gradle có wrapper:
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --configuration runtimeClasspath \
    --dependency asm

# Xem module/package dependencies:
jdeps --multi-release 17 --summary \
    --class-path 'libs/*' app.jar
~~~

Giới hạn: Các lệnh Maven/Gradle chỉ chạy trên dự án có cấu hình build thực, không phải chương trình độc lập của bài. `jdeps` không bắt hết reflection, runtime plugins hoặc classloaders. **Cần scan đúng JAR/WAR/container image được ship**, bao gồm dependencies đã resolve, generated classes, shaded/nested libs và resources.

## 8. Annotation processor cũng là một phần của compatibility gate

Từ **JDK23**, javac không mặc định chạy annotation processors chỉ vì chúng được tìm thấy trên ordinary classpath khi không có cấu hình processor tường minh. Khi nâng toolchain từ JDK21/22 lên JDK23+, một dự án dựa vào implicit discovery có thể **ngừng sinh mapper, DTO helper, service registration hoặc source class**.

Dùng `-processor`, `-processorpath`/`--processor-module-path` hoặc cấu hình `-proc:full` có chủ ý. Ưu tiên khai báo processor rõ ràng và pin phiên bản vì processor thực thi **code trong môi trường build**, không phải dữ liệu vô hại.

### 8.1. Ví dụ 3: annotation processor sinh class Java17

Ta cần ba source files và hai bước compile.

**`processor-src/example/AutoHello.java`:**

~~~java
package example;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.SOURCE)
public @interface AutoHello {}
~~~

**`processor-src/example/HelloProcessor.java`:**

~~~java
package example;

import java.io.IOException;
import java.io.Writer;
import java.util.Set;
import javax.annotation.processing.AbstractProcessor;
import javax.annotation.processing.RoundEnvironment;
import javax.annotation.processing.SupportedAnnotationTypes;
import javax.annotation.processing.SupportedSourceVersion;
import javax.lang.model.SourceVersion;
import javax.lang.model.element.TypeElement;

@SupportedAnnotationTypes("example.AutoHello")
@SupportedSourceVersion(SourceVersion.RELEASE_17)
public final class HelloProcessor extends AbstractProcessor {
    private boolean generated;

    @Override
    public boolean process(
            Set<? extends TypeElement> annotations,
            RoundEnvironment roundEnv) {

        if (!generated && !roundEnv.processingOver()
                && !roundEnv.getElementsAnnotatedWith(
                        AutoHello.class).isEmpty()) {
            generated = true;
            try (Writer writer = processingEnv.getFiler()
                    .createSourceFile(
                        "example.GeneratedHello").openWriter()) {
                writer.write(
                    "package example; " +
                    "public final class GeneratedHello {" +
                    "public static String value(){" +
                    "return \"hello-generated\"; }}");
            } catch (IOException ex) {
                throw new IllegalStateException(ex);
            }
        }
        return true;
    }
}
~~~

**`app-src/example/App.java`:**

~~~java
package example;

@AutoHello
public final class App {
    public static void main(String[] args) {
        System.out.println("generated=" +
                GeneratedHello.value());
    }
}
~~~

Bash build commands:

~~~bash
mkdir -p processor-classes app-classes generated-src

javac --release 17 -encoding UTF-8 \
    -d processor-classes \
    processor-src/example/AutoHello.java \
    processor-src/example/HelloProcessor.java

javac --release 17 -encoding UTF-8 \
    -cp processor-classes \
    -processorpath processor-classes \
    -processor example.HelloProcessor \
    -s generated-src -d app-classes \
    app-src/example/App.java

java -cp 'app-classes:processor-classes' example.App
javap -verbose -classpath app-classes example.GeneratedHello
~~~

**Stdout chương trình đã chạy trên JDK24:**

~~~text
generated=hello-generated
~~~

Các kiểm tra bổ sung đã đạt:
- Tồn tại `generated-src/example/GeneratedHello.java`.
- Tồn tại `app-classes/example/GeneratedHello.class`.
- `javap` báo **major version: 61** của generated class.

Trên Windows, `java -cp 'app-classes;processor-classes'` dùng dấu `;` để phân cách hai paths. Nếu bỏ `-processor`/processor path trên JDK24, build không được dựa vào implicit discovery; với chương trình này App sẽ thiếu `GeneratedHello`. Một clean build là cần thiết để tránh **stale generated classes** che mất lỗi.

### 8.2. Processor và generator cần được kiểm thế nào?

- Ghi phiên bản processor và compiler JDK.
- Xác minh processor đã thực thi, có annotation processing rounds phù hợp.
- Kiểm mã sinh trong `-s` và class thực tế trong `-d`.
- Kiểm class-file major/minor **sau khi compiler hoàn tất**.
- Xác minh generated class được đóng gói trong artifact thật.
- Với MapStruct/Lombok/Dagger/AutoService và các công cụ tương tự, kiểm compatibility matrix của **phiên bản đang dùng**, không copy một tuyên bố “hỗ trợ Java25” cho mọi bản cũ.
- Tách processor dependency khỏi runtime dependency khi có thể.
- Không chạy processor không tin cậy với build credentials/secrets.
- Khi nâng JDK, test codegen ở CI thay vì chỉ build local có cache.

**Lưu ý:** Một công cụ có thể trực tiếp ghi `.class` thông qua `Filer` hoặc bytecode library; không phải mọi generated class đều có generated `.java` tương ứng. Audit final class files quan trọng hơn chỉ kiểm source directory.

## 9. Runtime bytecode generation và thư viện ASM/Byte Buddy

Một nhóm dependencies không ship toàn bộ class bytes sẵn:
- ASM / Byte Buddy: parse, tạo, transform bytecode.
- Framework AOP/proxy, mock frameworks, Hibernate enhancement, agents.
- Coverage tools, instrumentation, classloader plugins.
- Compiler cho Kotlin/Groovy/Scala hoặc DSL sinh JVM bytecode.

Chẳng hạn khi chạy trên JDK26, một agent dùng ASM cũ có thể ném `IllegalArgumentException: Unsupported class file major version 70`. **Đừng lập tức kết luận JVM26 không hiểu major70**; cần xem stack trace exception do JVM loader hay **parser của thư viện**. Library parser thường có bảng hỗ trợ classfile version riêng.

### 9.1. Quy trình kiểm codegen compatibility

1. Xác định nơi codegen chạy: annotation processing, build postprocessing, class load time hay runtime.
2. Ghi đúng phiên bản compiler, framework, ASM, Byte Buddy, agent/plugin.
3. Kiểm transitive hoặc shaded/relocated ASM đang được load.
4. Đọc compatibility notes với **JDK/class major** mục tiêu.
5. Test các đường đi **tạo proxy, mở ORM session, serialize, mock, instrument và lazy-load plugin**, không chỉ application startup.
6. Nếu lấy được bytes lớp sinh ra, dùng `javap` hoặc parser tương ứng kiểm major/minor/structure.
7. Kiểm `VerifyError`, classpath/linkage và JPMS access trong runtime target.
8. Không làm cho JVM bỏ qua verification hoặc hạ major bằng hex editor để lách lỗi.

### 9.2. Class-File API hiện đại có từ JDK24

JEP 484 hoàn thiện **`java.lang.classfile`** ở Java 24 để parse/generate/transform bytecode bằng API chuẩn JDK. Với tooling chạy trên **JDK24+**, đây là lựa chọn đáng cân nhắc thay vì lệ thuộc internal `com.sun.tools.javac` APIs.

Mảnh minh họa **yêu cầu JDK24+, không thể compile với `--release 17`**:

~~~java
// Trong một phương thức đã có biến Path classPath, JDK24+:
byte[] bytes = java.nio.file.Files.readAllBytes(classPath);
java.lang.classfile.ClassModel model =
        java.lang.classfile.ClassFile.of().parse(bytes);
int major = model.majorVersion();
int minor = model.minorVersion();
~~~

Không coi API JDK24 là API Java15 hoặc Java17. Demo `DataInputStream` ở mục 5 là cách đơn giản để đọc class header trên Java17 mà không dùng internal APIs.

### 9.3. Hidden classes và bytecode không nằm trong JAR

Java15 giới thiệu **hidden classes (JEP371)**; nhiều framework sinh class bằng `MethodHandles.Lookup.defineHiddenClass`, `defineClass` hoặc các cơ chế tương đương. Chúng có thể không có class file có sẵn trên đĩa và không thể được audit chỉ bằng `jar --list`.

Muốn kiểm:
- Kích hoạt codepath sinh lớp trong integration tests trên JVM đích.
- Kiểm generator emits version đúng, stack maps/constant pool hợp lệ.
- Nếu cần, dùng diagnostics/instrumentation được cấp phép để quan sát lớp được define.
- Không kỳ vọng một pass qua JAR lúc build đủ chứng minh mọi generated runtime class sẽ hợp lệ.

## 10. Ví dụ 4: cùng major 61 vẫn có thể lỗi linkage

Ta tạo API v1 có method `message()`, API v2 đổi thành `renamed()`, và một App compile against v1. **Cả ba được biên dịch `--release 17`** nên đều major61, nhưng App gặp `NoSuchMethodError` khi chạy với v2.

**`src/v1/api/Contract.java`:**

~~~java
package api;

public final class Contract {
    public static String message() {
        return "v1";
    }
}
~~~

**`src/v2/api/Contract.java`:**

~~~java
package api;

public final class Contract {
    public static String renamed() {
        return "v2";
    }
}
~~~

**`src/app/LinkageCheckApp.java`:**

~~~java
import api.Contract;

public final class LinkageCheckApp {
    public static void main(String[] args) {
        try {
            System.out.println("value=" +
                    Contract.message());
        } catch (NoSuchMethodError expected) {
            System.out.println(
                    "sameMajorButLinkageFailed=true");
        }
    }
}
~~~

`catch (NoSuchMethodError)` chỉ dành cho bài thực hành để **nhìn thấy lỗi linkage**; production phải giải quyết dependency ABI mismatch, không tiếp tục chạy khi gặp linkage failure.

~~~bash
mkdir -p out/lib-v1 out/lib-v2 out/app

javac --release 17 -d out/lib-v1 \
    src/v1/api/Contract.java

javac --release 17 -cp out/lib-v1 \
    -d out/app src/app/LinkageCheckApp.java

javac --release 17 -d out/lib-v2 \
    src/v2/api/Contract.java

java -cp 'out/app:out/lib-v1' LinkageCheckApp
java -cp 'out/app:out/lib-v2' LinkageCheckApp

javap -verbose -classpath out/app LinkageCheckApp
javap -verbose -classpath out/lib-v1 api.Contract
javap -verbose -classpath out/lib-v2 api.Contract
~~~

**Kết quả thực nghiệm chính xác trên JDK24:**

~~~text
Runtime có lib-v1:
value=v1

Runtime có lib-v2:
sameMajorButLinkageFailed=true
~~~

`javap` của **cả ba classes** đều báo:

~~~text
major version: 61
~~~

JVM cần resolve `api.Contract.message:()Ljava/lang/String;`. Class `Contract` của v2 không còn method đó dù bytecode version hợp lệ, nên phát sinh `NoSuchMethodError`. Đây là bằng chứng rõ nhất rằng **class-file version checks phải được bổ sung bằng binary-linkage/runtime tests**.

## 11. Maven và Gradle: giữ target nhất quán

### 11.1. Maven

Một dự án **Maven3 + Compiler Plugin hỗ trợ `--release`** có thể khai báo `pom.xml`:

~~~xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
</properties>
~~~

Maven4 và Compiler Plugin4 có cơ chế cấu hình source targets khác, cần xem chính phiên bản đang dùng. `--release` cũng không tự thay đổi dependencies/transitives. Hãy kiểm Maven toolchain, plugin compiler, annotation processor paths và runtime JDK.

### 11.2. Gradle Kotlin DSL

Ví dụ project Gradle Java chạy **compiler toolchain21** nhưng emit classes cho Java17:

~~~kotlin
plugins {
    java
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(21))
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release.set(17)
}
~~~

Nếu dùng multi-module project có module `:processor`:

~~~kotlin
dependencies {
    annotationProcessor(project(":processor"))
}
~~~

Đây là các mảnh cấu hình cho một project đã có Gradle scripts thích hợp, không phải một ứng dụng Java độc lập. Toolchain chỉ định compiler JDK; `options.release` kiểm target API/language/bytecode; **Gradle daemon, tests và runtime Java** phải được kiểm riêng.

### 11.3. Vì sao phải ghi JDK thực tế?

`JAVA_HOME`, IDE, Maven toolchain, Gradle daemon, container build stage và runtime service có thể dùng các JDK khác nhau. CI nên lưu:
- Compiler JDK vendor/build/version;
- `javac --release`;
- Build tool và compiler plugin versions;
- Annotation processors/ASM/agents versions;
- Dependency lock/hash, final artifact SHA-256;
- Minimum supported runtime và các JVM đã test;
- MR-JAR variants và class-file audit summary.

Không chấp nhận “máy developer chạy được” là proof cho production runtime image.

## 12. Các rủi ro preview, module và packaging

**Preview classfile:** minor65535 không load tùy ý trên Java release khác, kể cả có `--enable-preview`. Nên build library production bằng ngôn ngữ/API ổn định.

**Module system:** Class major hợp lệ vẫn có thể bị JPMS access restrictions, missing exports/opens, module resolution, service descriptor hoặc split-package problems. Không thêm `--add-opens` tràn lan để che lỗi; cập nhật library và thiết kế module exports đúng.

**Shading/nested JAR:** Một build thành công có thể đóng gói một bản ASM/Netty/Guava khác compile-time version. Audit build artifact thực sau shading; kiểm classpath precedence, module path và plugin loaders.

**Generated runtime classes:** Chạy tests dùng proxies, serializers, ORM, mocks, agents; không chỉ một test `Class.forName` hay `java -version`.

**Security:** Bytecode header tương thích không có nghĩa dependency đáng tin. Cần provenance, supply-chain verification, SBOM/CVE policy, artifact checksum và giới hạn input cho archive scanners. Annotation processors có quyền thực thi trong build, do đó không tự động load processors không kiểm soát.

## 13. Pipeline kiểm thử được khuyến nghị

~~~text
1. Pin compiler toolchain + minimum runtime release
             │
2. Resolve and lock direct/transitive dependencies
             │
3. Compile với --release + explicit annotation processing
             │
4. Kiểm generated .java / generated .class / resources
             │
5. Package JAR/WAR/fat JAR/container, có shading nếu dùng
             │
6. Scan class major/minor trên TẤT CẢ shipped artifacts
             │
7. Kiểm MR-JAR theo mỗi supported runtime, jar --validate
             │
8. jdeps + JDK internal API checks + binary ABI checks
             │
9. Chạy integration test trên MINIMUM supported Java runtime
             │
10. Kích hoạt runtime-generated classes/proxies/agents
             │
11. Chạy supported higher JDK matrix + benchmark cần thiết
             │
12. Publish artifact đã kiểm, ghi checksum + build report
~~~

### 13.1. Ma trận phù hợp

| Trường | Ví dụ | Điều cần bảo đảm |
| --- | --- | --- |
| Compiler JDK | 21 có build hash cụ thể | Toolchain tái tạo |
| `--release` | 17 | Ứng dụng emit classfile target 17 và dùng JDK APIs phù hợp |
| Minimum runtime | 17 | Kiểm thật app + dependency/runtime generation |
| Runtimes khác | 21,25,27 nếu sản phẩm tuyên bố hỗ trợ | Không bị lỗi bytecode parser/agent mới |
| Dependencies | compile/runtime + transitive | Không có major, API/ABI conflict |
| Multi-release JAR | Base và các versions liên quan | Variant selection, API consistency |
| Codegen | Processor, ASM, Byte Buddy | Generated bytes hợp lệ và đã được đóng gói |
| Final packaging | Boot JAR, shaded JAR, container | Bytes deploy khớp với bytes đã kiểm |

Không yêu cầu test mọi JVM trên thế giới; chỉ cần test **những phiên bản sản phẩm chính thức hỗ trợ**. Nhưng với những runtime đã cam kết, một scanner kiểm mỗi major không đủ thay integration tests.

## 14. Những sai lầm thường gặp

| Sai lầm | Cách đúng |
| --- | --- |
| Chỉ xem `App.class` mà bỏ qua dependencies | Scan direct/transitive/runtime và packaged JARs |
| Dùng `--release 17` và nghĩ library major65 được “hạ” | Dùng dependency phù hợp hoặc thay runtime policy |
| Xem mọi class variant trong MR-JAR đều được load | Kiểm effective layer cho target và manifest |
| Chỉ đọc base entry của MR-JAR | Dùng `javap --multi-release N`/`jdeps --multi-release N` |
| Tin `jar --validate` là runtime verifier hoàn chỉnh | Bổ sung ABI checks và JVM integration tests |
| Quên JDK23 thay đổi annotation processing | Khai báo explicit processor path/name hoặc proc mode |
| Chỉ kiểm generated source, quên generated class | Kiểm output `-d` và final archive |
| Không clean build | Stale generated classes có thể che thiếu processor |
| Không kiểm shaded ASM | Tra actual loaded parser version/transitive dependencies |
| Parser ném unsupported major, tưởng lỗi JVM loader | Đọc stacktrace, update generator/agent |
| Sửa byte header major để “hạ JDK” | Recompile đúng target + APIs và dependencies |
| Dùng `--enable-preview` của JDK mới cho preview class cũ | Preview chỉ hợp lệ đúng release tạo ra nó |
| Chỉ test app start | Kích hoạt lazy-loading, proxy, reflection, serialization |
| Major hợp lệ nên cho rằng không thể `NoSuchMethodError` | Kiểm API/ABI runtime linkage |
| Dựa vào Java trên PATH thay runtime production | Kiểm exact executable/container image hash |
| Coi bytecode compatible là dependency an toàn | Provenance, SBOM, license, vulnerability policy riêng |

## 15. Bài tập tự kiểm tra có đáp án

**Câu 1.** Major59 là Java nào? Java11 chạy được không?

**Đáp án:** Major59 là **Java15**. Java11 hỗ trợ tới major55, nên không thể load class major59.

**Câu 2.** App `--release 17` nhưng transitive lib major65. Có đủ an toàn để deploy Java17?

**Đáp án:** Không. Phải thay lib/target runtime và kiểm artifact + runtime thực. `--release` không downgrade JAR có sẵn.

**Câu 3.** Vì sao MR-JAR có major61 vẫn chạy trên Java11?

**Đáp án:** Nếu manifest `Multi-Release: true` và có base major55 hợp lệ, Java11 chọn base; variant17 chỉ được chọn từ Java17 trở lên.

**Câu 4.** Vì sao `javap --multi-release 17` hữu ích?

**Đáp án:** Nó xem đúng class variant khi muốn kiểm Java17; `javap` mặc định có thể hiển thị base.

**Câu 5.** `jar --validate` đủ chứng minh app chạy production?

**Đáp án:** Không. Nó không kiểm toàn bộ runtime dependency ABI, reflection, agents hay generated classes.

**Câu 6.** Tại sao `--release` tốt hơn chỉ `-source`/`-target`?

**Đáp án:** Nó giới hạn cả **JDK API surface** của target, ngoài language và bytecode target.

**Câu 7.** Vì sao JDK25 build có thể ngừng tạo MapStruct class khi JDK21 build từng thành công?

**Đáp án:** Từ JDK23, annotation processors cần explicit configuration. Kiểm compiler plugin/processor path/version và generated output.

**Câu 8.** Generated source có nhưng compiled class không có thì đã đạt QA chưa?

**Đáp án:** Chưa. Cần kiểm annotation processing rounds, compilation, `-d`, runtime jar.

**Câu 9.** Ba classes đều major61, nhưng vẫn gặp `NoSuchMethodError`. Vì sao?

**Đáp án:** Binary method descriptor/callee runtime API khác compile dependency. Major chỉ kiểm class-file format.

**Câu 10.** ASM báo unsupported major71 trên JDK27. Đây luôn là lỗi JVM27?

**Đáp án:** Không. Có thể parser/agent ASM cũ; kiểm nested stacktrace và upgrade đúng library version.

**Câu 11.** Class minor65535 phát từ Java17 preview có chạy trên JDK21 khi bật preview không?

**Đáp án:** Không. Preview classes gắn với đúng release tạo ra chúng.

**Câu 12.** `java.lang.classfile` có dùng làm Java17 API được không?

**Đáp án:** Không. Đây là Class-File API chuẩn từ **JDK24**; Java17 code cần lựa chọn khác hoặc tách tooling chạy JDK24+.

**Câu 13.** Tại sao phải audit final fat JAR?

**Đáp án:** Packaging có thể thêm transitive/nested/shaded classes và thay dependency resolution, khác với compiler source output.

**Câu 14.** Tại sao `jdeps` không đủ để kiểm hidden classes?

**Đáp án:** Hidden/dynamic classes có thể chỉ được define lúc chạy; cần test generator và runtime codepath.

## 16. Checklist áp dụng

- [ ] Minimum supported Java runtime được nêu rõ.
- [ ] Compiler toolchain được pin; `--release` đúng.
- [ ] Đã kiểm major/minor của classes trong output và mọi shipped JAR.
- [ ] Có xử lý riêng MR-JAR manifest/base/versioned entries.
- [ ] Có Java integration tests với minimum runtime.
- [ ] Annotation processors được khai báo explicit và kiểm generated source/class.
- [ ] Codegen/ASM/Byte Buddy/agents tương thích target classfile version.
- [ ] Runtime classpath/module path và dependency convergence đã được xác nhận.
- [ ] Có binary API/linkage tests để phát hiện `NoSuchMethodError`.
- [ ] Không ship preview classes ngoài phạm vi release phù hợp.
- [ ] Container/package JDK là đúng executable được test.
- [ ] Không sửa major header để backport; không tắt bytecode verification.
- [ ] Có provenance/checksum/security review độc lập với compatibility checks.

## 17. Ghi nhớ và tài liệu hiện hành

**Ghi nhớ:** Một build tương thích không phải build có mỗi `App.class` đúng major; nó phải tương thích ở **compiler/API, mọi class/dependency được ship, generated bytecode, linkage, module boundaries và JVM thực tế**. `javap`, `jar`, `jdeps` và scanner giúp phát hiện vấn đề sớm, nhưng **runtime integration tests** trên JDK thấp nhất được hỗ trợ là phép kiểm quyết định.

Nguồn chính thức để cập nhật khi nâng JDK hoặc build tools:

- [Java SE 27 JVM Specification — class-file major-version table](https://docs.oracle.com/en/java/javase/27/docs/specs/jvms/jvms-1.html)
- [Java SE 26 JVMS `4.1 — class-file format, major/minor và preview](https://docs.oracle.com/en/java/javase/26/docs/specs/jvms/jvms-4.html)
- [Oracle JDK 26 `javac` — `--release`, annotation processor options](https://docs.oracle.com/en/java/javase/26/docs/specs/man/javac.html)
- [Oracle JDK 25 `javap` — class metadata và `--multi-release`](https://docs.oracle.com/en/java/javase/25/docs/specs/man/javap.html)
- [Oracle JDK 25 `jar` — `--release` và `--validate`](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jar.html)
- [Oracle JDK 26 `jdeps` — dependencies và `--multi-release`](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jdeps.html)
- [Java SE 26 JAR Specification — multi-release JAR behavior](https://docs.oracle.com/en/java/javase/26/docs/specs/jar/jar.html)
- [JDK 23 release notes — annotation processing default policy](https://www.oracle.com/java/technologies/javase/23-relnote-issues.html)
- [Inside Java — explicit annotation processing trên JDK23+](https://inside.java/2024/06/18/quality-heads-up/)
- [JEP 484 — Class-File API finalized in JDK24](https://openjdk.org/jeps/484)
- [Java SE 26 `java.lang.classfile` API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/classfile/package-summary.html)
- [JEP 371 — Hidden Classes ở Java15](https://openjdk.org/jeps/371)
- [Gradle — JVM toolchains và release](https://docs.gradle.org/current/userguide/toolchains.html)
- [Maven Compiler Plugin — `--release` configuration](https://maven.apache.org/plugins/maven-compiler-plugin-4.x/examples/set-compiler-release.html)
