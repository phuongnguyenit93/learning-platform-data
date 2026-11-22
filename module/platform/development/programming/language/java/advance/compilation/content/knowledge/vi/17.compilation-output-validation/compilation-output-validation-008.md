# Kiểm tra tệp `.class` đúng phiên bản trước khi đóng gói Java

## 1. Vì sao phải kiểm tra output cuối cùng?

Một dự án được cấu hình “Java 17” chưa chắc artifact cuối cùng đã chạy trên Java 17. Mã nguồn có thể được biên dịch bởi toolchain khác, một module dùng `--release 21`, class sinh bởi generator giữ target mới hơn, hoặc thư viện đi kèm được xây bằng JDK đời mới. Sau khi tạo JAR, WAR hoặc một bản phân phối, runtime Java thấp hơn có thể báo:

~~~text
java.lang.UnsupportedClassVersionError:
  ... has been compiled by a more recent version of the Java Runtime
~~~

Đó là lỗi **class-file compatibility**: JVM không hỗ trợ phiên bản cấu trúc class file mà nó được yêu cầu nạp. Một bước **verification gate trước khi đóng gói** nên đọc các class file thực sự được tạo, đối chiếu với minimum Java runtime đã cam kết, kiểm tra preview status và chỉ cho phép packaging khi đạt chính sách.

Bài này tập trung vào **kiểm chứng đầu ra** sau compilation và trước packaging, chứ không chỉ giải thích compiler flags. Kết quả cuối cùng cần trả lời:

- Có những `.class` nào trong build output và JAR?
- Mỗi tệp có **major/minor version** bao nhiêu?
- Tất cả có nằm trong giới hạn JVM mục tiêu không?
- Có preview class, class lạ hoặc JAR đa phiên bản cần ngoại lệ không?
- Có dependencies hoặc nested JAR chưa được quét không?
- Compiler/build scripts đã dùng `--release` đúng chưa?
- CI có **fail trước khi công bố artifact** khi phát hiện output không hợp lệ không?

## 2. Cấu trúc phần đầu class file và các số phiên bản

Theo Java Virtual Machine Specification, mỗi class file bắt đầu bằng:

~~~text
Offset   Kích thước   Trường
0x00     4 bytes      magic = 0xCAFEBABE
0x04     2 bytes      minor_version (unsigned u2)
0x06     2 bytes      major_version (unsigned u2)
0x08     ...          constant_pool_count và các cấu trúc khác
~~~

Các số trong class file được lưu theo **big-endian**. Java `DataInputStream.readInt()` và `readUnsignedShort()` có thể đọc lần lượt magic, minor và major ở đây. Không dùng cách đọc little-endian hoặc nhầm thứ tự `major` rồi `minor`.

Với các phiên bản Java thường gặp:

| Java release | Major version | Class file thông thường |
| --- | ---: | --- |
| Java 8 | 52 | 52.0 |
| Java 9 | 53 | 53.0 |
| Java 11 | 55 | 55.0 |
| Java 17 | 61 | 61.0 |
| Java 18 | 62 | 62.0 |
| Java 19 | 63 | 63.0 |
| Java 20 | 64 | 64.0 |
| Java 21 | 65 | 65.0 |
| Java 22 | 66 | 66.0 |
| Java 23 | 67 | 67.0 |
| Java 24 | 68 | 68.0 |

Với Java 9 trở lên, quan hệ phổ biến là **major = release + 44**. Công thức cũng cho 52 với Java 8; tuy nhiên một công cụ production nên dựa trên bảng/spec các release mà nó thực sự hỗ trợ, không đoán vô hạn phiên bản tương lai.

**Minor version:** class file bình thường của các bản Java hiện đại có minor `0`. Với các bản hỗ trợ preview class-file semantics, minor `65535` biểu thị class dùng **preview features** và chịu hạn chế chạy trên đúng release/flags tương ứng. Không xem `61.65535` tương đương `61.0`: build yêu cầu Java 17 ổn định nên từ chối preview class, kể cả khi major là 61.

### Kiểm tra bằng javap

~~~bash
javap -verbose -classpath out demo.PackageDemo
~~~

Tìm những dòng:

~~~text
minor version: 0
major version: 61
~~~

`javap` đọc class đã biên dịch, khác với việc mở `pom.xml` hoặc `build.gradle`. Nó hữu ích để điều tra một class cụ thể, nhưng việc gọi `javap` cho một class **không chứng minh toàn bộ artifact** có cùng target.

## 3. Ba phiên bản cần tách bạch khi review

| Khái niệm | Ví dụ | Kiểm chứng |
| --- | --- | --- |
| JDK công cụ chạy compiler | `javac 24.0.2` | `javac -version`, Gradle/Maven toolchain |
| Mức source language | Java 17 | `--release 17` hoặc `-source 17` |
| Class file target | 61.0 (Java 17) | Đọc bytes, `javap -verbose` |
| API Java SE được phép gọi | API có trong Java 17 | Ưu tiên `--release 17` |
| JVM thực sự triển khai | Java 17 hoặc mới hơn | Chạy tests trên runtime tối thiểu |

Ví dụ `javac` của JDK 24 biên dịch với `--release 17` có thể tạo bytecode **61.0**. Điều này hợp lệ: compiler version và class target **khác nhau**.

Đừng mặc định `-source 17 -target 17` đã bảo đảm Java 17 compatibility. Trên compiler JDK mới, hai cờ này có thể cho phép tham chiếu **API Java SE mới hơn 17**, dù bytecode vẫn là 61. Ví dụ `Thread.ofVirtual()` có trong Java 21 nhưng không có ở Java 17: để compiler mới chặn lời gọi này ngay ở compile time cho target 17, dùng `--release 17`.

**Kết luận thực tiễn:** class-file gate kiểm tra **định dạng** bytecode. `--release` kiểm soát thêm **API nền tảng** lúc biên dịch. Runtime tests và dependency verification kiểm tra các điều kiện tương thích còn lại. Ba lớp bảo vệ này bổ sung nhau, không thay thế nhau.

## 4. Thí nghiệm đầy đủ: cùng source, hai class versions

Dùng JDK hỗ trợ biên dịch cả `--release 17` và `--release 21` (ví dụ JDK 21 hoặc 24). Tạo file:

**`src/demo/PackageDemo.java`**

~~~java
package demo;

public final class PackageDemo {
    public static final class Nested {
        public String label() {
            return "nested";
        }
    }

    public static void main(String[] args) {
        System.out.println(new Nested().label());
    }
}
~~~

Đây là chương trình Java hoàn chỉnh, có class lồng nhau. Khi compile, compiler sinh **hai class files**, không chỉ một.

Tại thư mục project, dùng Bash:

~~~bash
mkdir -p out17 out21

javac --release 17 -encoding UTF-8 -d out17 \
  src/demo/PackageDemo.java

javac --release 21 -encoding UTF-8 -d out21 \
  src/demo/PackageDemo.java

java -cp out17 demo.PackageDemo
javap -verbose -classpath out17 demo.PackageDemo
javap -verbose -classpath out21 demo.PackageDemo
~~~

Trong Windows PowerShell/cmd, đặt mỗi invocation `javac` trên một dòng hoặc dùng ký hiệu nối dòng của shell thay vì `\` (Bash). Chỉ có thể chạy các lệnh nếu phiên bản `javac` hỗ trợ cả release 17 và 21.

Stdout của ứng dụng:

~~~text
nested
~~~

Hai lần kiểm tra `javap` cho class `demo.PackageDemo` cho biết:

~~~text
out17: minor version: 0, major version: 61
out21: minor version: 0, major version: 65
~~~

Đây là **bản tóm lược** hai trường từ đầu ra `javap -verbose`, không phải định dạng nguyên văn một dòng `javap`.

Một cách kiểm tra phần nested class (Bash/PowerShell cần giữ `$` đúng):

~~~bash
javap -verbose -classpath out17 'demo.PackageDemo$Nested'
~~~

Với `cmd.exe`, hãy dùng dấu nháy kép thay dấu nháy đơn. Đừng dựa vào việc `PackageDemo.class` đạt chuẩn rồi bỏ qua `PackageDemo$Nested.class`, anonymous classes, local classes hoặc các classes do annotation processor tạo. Tất cả đều có thể được JVM nạp.

## 5. Viết gate Java 17 để kiểm tra toàn bộ directory hoặc JAR

Một công cụ thực tế cần chạy trên thư mục classes **trước khi `jar` đóng gói**, và có thể chạy lại trên JAR sau khi tạo. Chương trình sau dùng Java 17 standard APIs, không phụ thuộc Maven/Gradle, và có chính sách **nghiêm ngặt**:

1. Mọi entry kết thúc bằng `.class` phải bắt đầu bằng `0xCAFEBABE`.
2. Major version phải nằm từ 45 đến **target release + 44**.
3. Minor version phải bằng **0**, tức không chấp nhận preview class file.
4. Nếu không tìm thấy class nào, build phải fail.
5. Bất kỳ class không đạt phải làm exit code khác 0, để CI/package task chặn phát hành.

Chính sách này cố ý **quét toàn bộ class entries**, kể cả entries trong `META-INF/versions/` của multi-release JAR. Điều đó an toàn nếu dự án **không có multi-release JAR**, nhưng có thể quá chặt đối với một multi-release JAR hợp lệ có classes cao hơn dành riêng cho JVM mới. Phần 9 nêu cách điều chỉnh khi thật sự dùng MR-JAR.

### 5.1. File ClassVersionGate.java

~~~java
import java.io.BufferedInputStream;
import java.io.DataInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Collections;
import java.util.Comparator;
import java.util.List;
import java.util.stream.Stream;
import java.util.zip.ZipEntry;
import java.util.zip.ZipFile;

public final class ClassVersionGate {
    private static int maxMajor;
    private static int count;
    private static int errors;

    private static void check(String name, InputStream source)
            throws IOException {
        try (DataInputStream in =
                     new DataInputStream(new BufferedInputStream(source))) {
            if (in.readInt() != 0xCAFEBABE) {
                System.out.println("FAIL " + name + " invalid magic");
                errors++;
                return;
            }

            int minor = in.readUnsignedShort();
            int major = in.readUnsignedShort();
            count++;

            boolean valid = major >= 45
                    && major <= maxMajor
                    && minor == 0;

            System.out.println((valid ? "OK " : "FAIL ")
                    + name + " " + major + "." + minor);

            if (!valid) errors++;
        }
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            System.err.println(
                    "Usage: ClassVersionGate "
                    + "<target-java-release> <classes-dir-or-jar>");
            System.exit(2);
        }

        int release = Integer.parseInt(args[0]);
        if (release < 8) {
            throw new IllegalArgumentException("Java 8+ expected");
        }
        maxMajor = release + 44;
        Path path = Path.of(args[1]);

        if (Files.isDirectory(path)) {
            try (Stream<Path> files = Files.walk(path)) {
                for (Path file : files
                        .filter(p -> p.toString().endsWith(".class"))
                        .sorted().toList()) {
                    check(path.relativize(file).toString()
                                    .replace('\\', '/'),
                            Files.newInputStream(file));
                }
            }
        } else if (path.toString().endsWith(".jar")) {
            try (ZipFile jar = new ZipFile(path.toFile())) {
                List<? extends ZipEntry> entries =
                        Collections.list(jar.entries()).stream()
                                .filter(e -> !e.isDirectory()
                                        && e.getName().endsWith(".class"))
                                .sorted(Comparator.comparing(ZipEntry::getName))
                                .toList();

                for (ZipEntry entry : entries) {
                    check(entry.getName(), jar.getInputStream(entry));
                }
            }
        } else {
            throw new IllegalArgumentException(
                    "Expected a classes directory or .jar file");
        }

        if (count == 0) {
            System.err.println("FAIL no .class files found");
            System.exit(1);
        }

        System.out.println(
                "RESULT checked=" + count + " errors=" + errors);

        if (errors != 0) System.exit(1);
    }
}
~~~

**Giải thích phần quan trọng:**
- `Files.walk(path)` lấy tất cả `.class` trong thư mục và thư mục con, kể cả nested/local/anonymous class do compiler tạo.
- `ZipFile` duyệt các entry `.class` trong JAR. Dùng `jar tf` thủ công sẽ giúp xác định tên và vị trí khi cần.
- `readInt` kiểm tra magic, `readUnsignedShort` lần lượt đọc **minor rồi major**.
- `major <= maxMajor` chấp nhận classes từ Java cũ có thể được JVM đích nạp theo quy tắc phiên bản, không buộc mọi class phải đúng bằng major tối đa.
- `minor == 0` là chính sách **không preview** cho các class thông thường. Đây là lựa chọn của gate, không phải tuyên bố JVMS rằng mọi class file trong lịch sử đều luôn có minor 0.
- `System.exit(1)` tạo exit code fail. Không được để packaging tool bỏ qua exit code của gate.

**Giới hạn chủ đích:** gate chỉ đọc **header** (magic/major/minor), chưa parse toàn bộ constant pool, chưa kiểm tra chữ ký JAR, chưa duyệt các JAR lồng bên trong, chưa xác nhận tính tương thích API/runtime. Header hợp lệ không chứng minh class file đầy đủ hoặc an toàn. Chỉ dùng với **artifact đáng tin trong build pipeline** hoặc triển khai các giới hạn đọc, ZIP bomb protection và xử lý file I/O nâng cao nếu áp dụng cho input không tin cậy.

### 5.2. Biên dịch gate

Tạo `ClassVersionGate.java` ở project root, sau đó:

~~~bash
mkdir -p toolout
javac --release 17 -encoding UTF-8 -d toolout ClassVersionGate.java
~~~

Gate này dùng được khi chạy bằng JDK 17+, miễn JVM có đầy đủ các Java standard APIs sử dụng. Cần dùng JDK để chạy compiler tạo gate; sau đó JVM có thể chạy class từ `toolout`.

### 5.3. Kiểm tra directory Java 17 — PASS

~~~bash
java -cp toolout ClassVersionGate 17 out17
~~~

Output từ phép thử đã thực hiện:

~~~text
OK demo/PackageDemo$Nested.class 61.0
OK demo/PackageDemo.class 61.0
RESULT checked=2 errors=0
~~~

**Exit code: 0.** Cả top-level và nested class đều có format phù hợp minimum Java 17. Gate này duyệt cả hai, thay vì chỉ gọi `javap` cho main class.

### 5.4. Kiểm tra class Java 21 khi target Java 17 — FAIL

~~~bash
java -cp toolout ClassVersionGate 17 out21
~~~

Output kiểm chứng:

~~~text
FAIL demo/PackageDemo$Nested.class 65.0
FAIL demo/PackageDemo.class 65.0
RESULT checked=2 errors=2
~~~

**Exit code: 1.** Đây là kết quả đúng mong muốn: JVM Java 17 không hỗ trợ class-file major 65 của Java 21.

Nếu target thật sự là Java 21:

~~~bash
java -cp toolout ClassVersionGate 21 out21
~~~

Output:

~~~text
OK demo/PackageDemo$Nested.class 65.0
OK demo/PackageDemo.class 65.0
RESULT checked=2 errors=0
~~~

**Exit code: 0.** Điều này chỉ cho biết định dạng class files tương thích với giới hạn Java 21; chưa xác nhận toàn bộ dependencies hay API.

## 6. Đặt gate trước bước jar packaging

### 6.1. Pipeline thủ công tối thiểu

Giả sử minimum Java runtime là 17 và code trong `src/demo`:

~~~bash
mkdir -p out17 toolout dist

javac --release 17 -encoding UTF-8 -d toolout ClassVersionGate.java
javac --release 17 -encoding UTF-8 -d out17 src/demo/PackageDemo.java

java -cp toolout ClassVersionGate 17 out17

jar --create --file dist/package-demo.jar -C out17 .

java -cp toolout ClassVersionGate 17 dist/package-demo.jar
java -cp dist/package-demo.jar demo.PackageDemo
~~~

Đây là trình tự **đúng về mặt phụ thuộc**, nhưng trong Bash CI nên bật chế độ dừng khi lệnh lỗi để tránh đi tiếp dù gate fail:

~~~bash
set -e
# Các lệnh javac, ClassVersionGate, jar như trên.
~~~

Lệnh `set -e` phải được cấu hình cùng ngữ cảnh shell script phù hợp; nếu sử dụng pipelines/conditionals phức tạp, cần kiểm tra cơ chế truyền exit status. Trong PowerShell, sau `java -cp ... ClassVersionGate 17 out17`, hãy kiểm tra `$LASTEXITCODE` và phát lỗi nếu khác 0; PowerShell 5.1 không luôn tự dừng script chỉ vì một native executable trả exit 1.

**Một cách tốt:** CI có các stage rõ ràng `compile → verify-classes → package → verify-package → integration-test → publish`. Publish chỉ chạy khi tất cả stages trước thành công.

### 6.2. Kiểm tra JAR sau khi tạo

~~~bash
jar --create --file package-demo.jar -C out17 .
java -cp toolout ClassVersionGate 17 package-demo.jar
jar --list --file package-demo.jar
~~~

Khi thử nghiệm, JAR chứa hai class files; gate in:

~~~text
OK demo/PackageDemo$Nested.class 61.0
OK demo/PackageDemo.class 61.0
RESULT checked=2 errors=0
~~~

Dù đã verify directory, vẫn cần verify JAR cuối nếu packaging step có thể thêm classes từ module khác, generated output, shading/relocation hoặc dependency classes. **Chính artifact được publish** mới là nguồn sự thật.

## 7. Maven: kiểm soát compiler release và ràng buộc packaging

Với Maven, cấu hình compiler release để giảm rủi ro ngay từ đầu. Đoạn ví dụ trong `pom.xml`:

~~~xml
<properties>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    <maven.compiler.release>17</maven.compiler.release>
</properties>
~~~

Đây chỉ là **phần cấu hình** của một POM hoàn chỉnh. Maven Compiler Plugin phải hỗ trợ `release` và JDK compiler đang dùng phải hỗ trợ Java 17 target. Nếu cần quản lý ổn định plugin version, thêm `maven-compiler-plugin` vào `build/plugins` hoặc parent `pluginManagement` theo chuẩn project.

Trong Maven lifecycle, `compile` diễn ra trước `package`. Một quy trình CI thực tế:

~~~bash
mvn clean compile

java -cp toolout ClassVersionGate 17 target/classes

mvn package
java -cp toolout ClassVersionGate 17 target/my-app.jar
~~~

Hai chỗ cần điều chỉnh khi áp dụng:
- `toolout` phải thật sự chứa `ClassVersionGate.class` đã được compile từ mục 5.
- `target/my-app.jar` là **tên minh họa**, thay bằng đường dẫn artifact thực tế lấy từ cấu hình Maven, không giả định mọi project có tên như vậy.

Nếu xây một command orchestration tự động, đặt bước gate thành **điều kiện bắt buộc trước package** (chẳng hạn một plugin execution ở phase phù hợp như `prepare-package`), không chỉ là lệnh người dùng nhớ chạy. Nếu `mvn package` có thể được chạy riêng mà không qua gate, quy trình thực tế vẫn có lỗ hổng.

Với dự án **multi-module Maven**, mỗi module có thể có compiler target khác nhau. Gate cần chạy cho các module class outputs được đưa vào artifact cuối, và tiếp tục chạy JAR/WAR cuối nếu assembly/shading có thể thêm class files mới. Không suy luận “parent POM đặt Java 17 nên mọi JAR trong distribution tự đạt 61.0”.

### Cần phân biệt compiler của Maven với runtime triển khai

`mvn -version` cho biết JVM chạy Maven, nhưng Maven Toolchains Plugin hoặc compiler configuration có thể sử dụng một compiler JDK khác. Kiểm tra **toolchain thực tế**, compiler args và `javap` kết quả. `maven.compiler.release=17` không thể hạ classfiles đã được biên dịch trong third-party dependencies.

## 8. Gradle: build task kiểm tra trước jar

Gradle Java plugin cung cấp `JavaCompile`, `classes`, `jar`. Đặt `options.release=17` để compiler kiểm soát source/target/platform API phù hợp:

~~~groovy
plugins {
    id 'java'
}

tasks.withType(JavaCompile).configureEach {
    options.encoding = 'UTF-8'
    options.release = 17
}
~~~

Đây là **đoạn `build.gradle`**, không phải Java source. Nếu project sử dụng Gradle Java Toolchains, có thể chọn compiler JDK khác Java 17 nhưng vẫn đặt `options.release = 17`.

Một cách kết nối gate mẫu (Groovy DSL) giả sử gate đã được biên dịch sẵn vào thư mục `tools/class-version-gate-classes`:

~~~groovy
tasks.register('verifyBytecode', JavaExec) {
    dependsOn tasks.named('classes')
    classpath = files("$rootDir/tools/class-version-gate-classes")
    mainClass = 'ClassVersionGate'
    args '17', layout.buildDirectory
            .dir('classes/java/main').get().asFile.absolutePath
}

tasks.named('jar') {
    dependsOn tasks.named('verifyBytecode')
}
~~~

Đây là **cấu hình tích hợp minh họa**, cần đặt cùng Java plugin và cần có `ClassVersionGate.class` ở đúng thư mục được khai báo. Nó không tự compile gate; trong production, nên đóng gói verifier thành một plugin/task chuyên dụng hoặc một build tool riêng có dependency được quản lý. Nếu project có output ở vị trí khác, multi-language build hoặc nhiều compile tasks, đừng hardcode mỗi `classes/java/main` rồi bỏ sót classes khác.

**Vòng phụ thuộc:** `verifyBytecode` phụ thuộc `classes`; `jar` phụ thuộc `verifyBytecode`; vì thế việc chạy `jar` phải đi qua gate. Nếu class vi phạm, JavaExec ném lỗi cho Gradle và packaging không tiếp tục theo mặc định.

Khi build final distribution, có thể cần **gate thứ hai** kiểm tra JAR cuối và dependencies được gộp trong shadow/fat JAR. Chỉ kiểm tra `build/classes/java/main` không đủ nếu `jar` hoặc `shadowJar` kéo thêm class từ nơi khác.

## 9. Multi-release JAR và class files dành riêng cho các JVM mới

**Multi-release JAR (MR-JAR)** có thể chứa nhiều phiên bản cùng một class, chẳng hạn:

~~~text
com/example/Feature.class
META-INF/versions/17/com/example/Feature.class
META-INF/versions/21/com/example/Feature.class
~~~

Manifest thường có thuộc tính:

~~~text
Multi-Release: true
~~~

Với MR-JAR hợp lệ, JVM Java 17 có thể chọn base class hoặc versioned entry phù hợp **không vượt quá runtime version**, trong khi JVM 21 có thể chọn entry của 21. Vì vậy một MR-JAR phục vụ Java 17 **có thể hợp pháp chứa class file major 65 trong `META-INF/versions/21/`**, miễn base và các lớp mà Java 17 thực sự dùng tương thích Java 17 và các quy tắc MR-JAR được tuân thủ.

Gate ở phần 5 **cố ý strict**: nó kiểm tra **tất cả** class entries và fail nếu bất kỳ major nào vượt 61. Nó thích hợp cho một artifact không dùng MR-JAR hoặc chính sách “toàn bộ entries đều Java 17”. **Không dùng gate strict một cách mù quáng để kết luận một MR-JAR hợp lệ là lỗi**.

Một verifier MR-JAR đúng cần:
1. Xác nhận manifest có `Multi-Release: true` nếu dựa vào versioned entries.
2. Phân biệt base entries với các paths `META-INF/versions/N/`.
3. Với target Java T, mô hình hóa **class được runtime T chọn**: versioned entry cao nhất cho cùng logical class mà N không vượt T, hoặc base entry.
4. Kiểm tra format và APIs của các effective entries mà Java T sẽ nạp; đồng thời kiểm tra versioned entries mới hơn theo **release riêng của chúng**, nếu artifact hứa hỗ trợ các runtime đó.
5. Kiểm tra tính nhất quán của package/API, service loading và module metadata, không chỉ major number.

MR-JAR phức tạp hơn rất nhiều so với một flat JAR. Nếu project không chủ động cần nó, tránh tự tạo thư mục `META-INF/versions` rồi coi mọi vi phạm gate là ngoại lệ.

## 10. Fat JAR, nested JAR, WAR và dependencies

Một JAR thông thường chứa các `.class` ở paths trực tiếp. Nhưng packaging khác có thể có:

- **Shaded/fat JAR:** class files của dependencies được merge thẳng vào JAR; gate quét được các class entries trực tiếp, nếu nó kiểm tra artifact cuối.
- **Spring Boot executable JAR:** classes có thể dưới `BOOT-INF/classes`, còn dependency JAR nằm trong `BOOT-INF/lib`. Gate ở phần 5 kiểm tra `.class` trực tiếp dưới `BOOT-INF/classes` nhưng **không mở các JAR lồng trong `BOOT-INF/lib`**.
- **WAR:** app classes ở `WEB-INF/classes`, dependencies có thể ở `WEB-INF/lib` — phải mở và kiểm chứng các JAR liên quan.
- **Modular JAR:** có `module-info.class` và module dependencies; module descriptor cũng là class file, cần được tính vào kiểm tra format.
- **Native image:** không phát hành theo cấu trúc JVM class files thông thường; dùng gate phù hợp với artifact/runtime thực tế.

Do đó cần **định nghĩa phạm vi scan**:
- Có quét application classes không?
- Có quét test classes không? Tests có thể được compile bằng Java mới hơn nếu dự án chấp nhận, nhưng không nên đi vào runtime artifact.
- Có quét dependencies dự định đi kèm không?
- Có quét generated classes (annotation processors, bytecode enhancement, Kotlin/Scala classes...) không?
- Có kiểm tra output sau shading, assembly hoặc repackaging không?
- Có thư viện container/runtime được cung cấp ngoài artifact cần test tương thích không?

**Không tuyên bố artifact tương thích hoàn toàn** chỉ vì một verifier chỉ đọc `target/classes` đã pass. Nó xác nhận đúng phần đã được kiểm tra.

## 11. Preview class files và release policy

Một lớp dùng preview feature có thể có minor version **65535**, ví dụ class file `65.65535` cho một preview build thuộc Java 21. Runtime cùng Java release cần các điều kiện preview tương ứng để nạp. Không thể chỉ đổi `major` cho nó để chạy trên Java 17.

Với chính sách phân phối ổn định, lựa chọn đơn giản là:
- **Không dùng preview**: yêu cầu `minor == 0` cho mọi class được kiểm tra (như gate mẫu).
- **Dùng preview có kiểm soát**: kiểm tra chính xác major, minor, release, `--enable-preview` lúc compile/run và ma trận JDK tương ứng; cấm xuất bản như artifact Java 17 ổn định nếu phụ thuộc preview của bản khác.

Không tự “sửa” bytecode bằng cách thay 2 bytes minor từ 65535 về 0: phần bytecode/ngữ nghĩa có thể cần preview runtime support. Binary patch không thay cho recompile đúng target.

## 12. Class-file version đúng chưa chắc API/runtime đúng

Một class major 61 có thể vẫn không chạy trên Java 17 nếu:
- Compile bằng `-source 17 -target 17` trên JDK mới nhưng dùng API Java 21/24; `--release 17` sẽ chặn nhiều lỗi kiểu này.
- Một dependency runtime được compile Java 21 và JVM 17 nạp class đó.
- Class tham chiếu method của thư viện phiên bản mới hơn, nhưng runtime cung cấp bản cũ (`NoSuchMethodError`).
- Có `ServiceLoader`, reflection, module exports, native/JNI hoặc generated proxies không tương thích.
- Class file có format hợp lệ nhưng phần còn lại của file bị hỏng hoặc bytecode không qua JVM verification.
- Nhiều JAR trùng một class, classpath order khiến JVM nạp phiên bản khác với bản đã verify.

Vì vậy một pipeline nghiêm túc nên kết hợp:

~~~text
javac --release N
      |
      v
Scan tất cả application .class cho target N
      |
      v
Kiểm tra dependency min-Java, classpath/module path
      |
      v
Package artifact
      |
      v
Scan chính package sau assembly/repackage
      |
      v
Chạy smoke/integration tests bằng Java N thật
      |
      v
Publish
~~~

Với thư viện Java cần hỗ trợ nhiều runtime, chạy test trên **minimum supported JDK** là điều thiết yếu. Chạy trên JDK 24 không chứng minh tác phẩm chạy trên JDK 17.

## 13. Phát hiện class version sai trong CI

**Tình huống 1: một module vô tình dùng Java 21**

Thông thường:
- `javap -verbose` ở module đó cho major 65.
- Gate target 17 in `FAIL ... 65.0`, exit code 1.
- Kiểm tra `--release`, JavaCompile task, compiler toolchain và plugin/module override.
- Build sạch module, verify lại trước packaging.

**Tình huống 2: source đúng nhưng generated class mới hơn**

Một bytecode generator, instrumentation task hoặc language plugin có thể tạo class files sau `javac`. Nếu gate chạy **trước** task đó nhưng không chạy sau, artifact vẫn có class mới hơn. Phải đặt verifier sau tất cả bước **transform** có thể thay đổi/ thêm class và trước bước publish.

**Tình huống 3: dependency trong fat JAR quá mới**

Application classes 61.0 đều đúng nhưng shaded dependency chứa class 65.0. Nếu gate chỉ quét output app, CI pass sai. Quét final shaded JAR hoặc resolved dependency artifacts tương ứng.

**Tình huống 4: JAR rỗng hoặc thiếu class**

Một script chỉ cần “không thấy version sai” có thể pass ngay cả khi không tìm class nào. Gate mẫu yêu cầu `checked > 0`. Nhưng không có nghĩa mọi artifact đều phải chứa classes (ví dụ resources-only JAR); chính sách riêng cần xác định artifact loại nào có thể hợp lệ khi không có class.

**Tình huống 5: gate gặp invalid magic**

Dữ liệu có tên `.class` nhưng không có magic `CAFEBABE`: package bị lỗi, tạo file sai kiểu hoặc data corruption. Gate từ chối; compiler/JVM cũng có thể không nạp được. Nếu file thuộc artifact không tin cậy, cần giới hạn memory/stream và dùng verifier phù hợp.

**Tình huống 6: cấu hình compiler và runtime khác**

`javac -version` không nhất thiết bằng `java -version`; Maven/Gradle toolchain còn có thể khác JVM chạy tool. Đọc compiler invocation, kiểm tra binary class file và xác nhận runtime thực tế trong image/container triển khai.

## 14. Checklist trước phát hành

- [ ] Minimum supported Java release được xác định chính thức (ví dụ 17).
- [ ] `javac` hoặc JavaCompile dùng `--release 17` (và encoding phù hợp).
- [ ] Build sạch, không có stale `.class` từ lần target khác.
- [ ] `javap -verbose` xác nhận version vài class điển hình.
- [ ] Gate duyệt **tất cả** application `.class`, kể cả nested/local/anonymous/generated classes.
- [ ] Magic và major/minor hợp lệ, không có preview class ngoài chính sách.
- [ ] Gate xuất **exit code khác 0** khi chủ ý trộn class Java 21 vào artifact Java 17.
- [ ] Output được verify đúng **sau** các bước compile/codegen/transform.
- [ ] Dependencies có class-file/API compatibility phù hợp.
- [ ] Packaging không tự thêm class chưa verify.
- [ ] Final JAR/WAR/fat JAR được verify theo **định dạng của nó**, gồm nested JAR khi có.
- [ ] Nếu dùng MR-JAR, verifier hiểu quy tắc versioned entries thay vì quét strict thiếu phân biệt.
- [ ] Test ít nhất một lần bằng **runtime Java tối thiểu thực**.
- [ ] CI chặn publish khi gate hoặc integration test thất bại.
- [ ] Build tool/plugin/JDK versions được ghi lại để tái lập kết quả.

## 15. Câu hỏi tự kiểm tra

**Câu 1.** Java 17 có class-file major version nào?  
**Đáp án:** 61.

**Câu 2.** Một JDK 24 compile `--release 17` có nhất thiết tạo major 68 không?  
**Đáp án:** Không. Nó tạo class target Java 17, bình thường major 61.

**Câu 3.** Chỉ `javap` main class ra 61.0, có thể phát hành chắc chắn chưa?  
**Đáp án:** Chưa; còn nested/generated classes và dependencies/final package.

**Câu 4.** Class 65.0 xuất hiện trong flat JAR target Java 17 phải làm gì?  
**Đáp án:** Chặn packaging, tìm module/dependency sinh class Java 21, sửa release hoặc thay dependency.

**Câu 5.** Major 61, minor 65535 có giống major 61, minor 0 không?  
**Đáp án:** Không. Minor 65535 có semantics preview; policy không preview phải từ chối.

**Câu 6.** Gate chỉ xem bytes 0–7 có kiểm chứng được class hoàn toàn hợp lệ không?  
**Đáp án:** Không. Nó chỉ kiểm tra magic và class-file version header.

**Câu 7.** MR-JAR có `META-INF/versions/21/Foo.class` major 65 nhưng target runtime 17. Luôn là lỗi sao?  
**Đáp án:** Không. Khi MR-JAR được cấu hình đúng, runtime Java 17 không chọn entry version 21; gate strict toàn bộ entries có thể báo false positive.

**Câu 8.** `jar tf` liệt kê `BOOT-INF/lib/dependency.jar`; gate mẫu có quét classes trong dependency đó không?  
**Đáp án:** Không. Cần verifier mở nested JAR hoặc kiểm tra dependency artifacts trước packaging.

**Câu 9.** Một app chỉ dùng `-target 17` rồi gọi API Java 21, class file 61.0. Gate có phát hiện API mismatch không?  
**Đáp án:** Không. Dùng `--release 17` và chạy test trên Java 17 thực.

**Câu 10.** Vì sao gate phải fail khi tìm thấy một class sai version, dù main class đúng?  
**Đáp án:** JVM có thể nạp class sai ở một nhánh code khác lúc chạy; một artifact không nên phát hành với class không tương thích ngoài chính sách.

## 16. Tài liệu chuẩn

- [JVMS 17 §4.1 — ClassFile structure và major/minor version](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.1)
- [Oracle Java 17 javac command — `--release`, `--target`](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html)
- [Oracle javap command — verbose class-file inspection](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javap.html)
- [JAR File Specification — Multi-Release JAR files](https://docs.oracle.com/en/java/javase/17/docs/specs/jar/jar.html#multi-release-jar-files)
- [Gradle JavaCompile and toolchains](https://docs.gradle.org/current/userguide/toolchains.html)
- [Maven Compiler Plugin — Setting `--release`](https://maven.apache.org/plugins/maven-compiler-plugin/examples/set-compiler-release.html)

**Ghi nhớ:** kiểm tra đúng phiên bản trước khi đóng gói không phải chỉ đọc `javac -version`. Hãy kiểm tra **header của mọi class file thực**, dùng `--release` để giới hạn source/target/API, tách rõ flat JAR với MR-JAR và nested dependencies, đặt gate làm điều kiện bắt buộc trước publish, rồi chạy thử trên minimum Java runtime. Chỉ khi những lớp kiểm chứng cùng đạt mới có cơ sở tin artifact tương thích mục tiêu.
