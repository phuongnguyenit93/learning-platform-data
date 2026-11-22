# Phiên bản bytecode agent, bytecode helper và phiên bản ứng dụng đích

Một Java instrumentation agent có thể chạy đúng trên máy phát triển nhưng không khởi động được trong production, hoặc agent khởi động thành công mà lời gọi helper vừa chèn vào ứng dụng lại thất bại khi thực thi. Một nguyên nhân phổ biến là **ba nhóm class files được xây với ba mức Java khác nhau**:

1. **Bytecode của agent:** các class của `Premain-Class`/`Agent-Class`, transformer, parser, exporter và dependencies được agent load.
2. **Bytecode của helper:** những class `Probe`, `Bridge`, `Advice` hoặc logging/metrics helpers mà agent phải nạp, đôi khi được đưa vào classpath/bootstrap để bytecode ứng dụng có thể gọi.
3. **Bytecode của ứng dụng đích:** class files do ứng dụng và libraries cung cấp, **cộng** class files mà transformer sinh ra hoặc thay thế trước khi JVM định nghĩa/redefine/retransform lớp.

Ba mức này **không buộc phải bằng nhau**, nhưng **mọi class thực sự được JVM nạp phải có định dạng bytecode và API tương thích với chính JVM đang chạy**. Agent Java 17 có thể instrument ứng dụng Java 21 trên JVM Java 21 nếu agent/toolkit xử lý được classfile Java 21; song một helper biên dịch Java 21 không thể được JVM Java 17 nạp chỉ vì agent chính đã biên dịch Java 17. Cũng không thể biến ứng dụng Java 21 thành ứng dụng Java 17 bằng việc đổi một vài byte ở header classfile.

Bài thuộc nhóm **Đóng gói và triển khai** của Java Advance – instrumentation. Mục tiêu là thiết kế ma trận tương thích rõ ràng, biết kiểm tra `major_version`/`minor_version`, dùng `javac --release` đúng cách, tách artifact agent/helper/app, hiểu lỗi `UnsupportedClassVersionError` xảy ra ở giai đoạn nào, xác minh bytecode mà transformer trả lại, và tổ chức pipeline CI/triển khai để không đưa artifact sai phiên bản vào JVM đích.

**Bài thực hành đã được chạy:** một startup Java agent và một helper JAR được biên dịch ở Java 17, ứng dụng được build theo Java 17 hoặc 21; kiểm thử **thành công trên JDK 17/JDK 21** và tái hiện ba loại lỗi không tương thích khi cố chạy bytecode 65 (Java 21) trên JDK 17. Mọi mã nguồn, lệnh và output cần thiết đều có trong bài. Kết quả những JVM khác có thể có phần stack trace/log khởi động khác nhau, nhưng bản chất lỗi phiên bản vẫn theo đặc tả classfile.

## 1. Ba phiên bản classfile là ba điều kiện độc lập

Hãy phân biệt **toolchain biên dịch**, **classfile major version** và **Java runtime thực tế**:

~~~text
Agent source + agent dependencies
        |
        +-- javac --release 17 --> agent17.jar (class major 61)
        |
Helper source + helper dependencies
        |
        +-- javac --release 17 --> helper17.jar (class major 61)
        |
App source + app dependencies
        |
        +-- javac --release 21 --> app21/ (class major 65)
                                         |
                                         v
                                  Java 21 JVM
                                  nạp agent 61
                                  nạp helper 61
                                  nạp app 65
                                  --> có thể chạy
~~~

Một JVM Java 21 biết đọc major 61 và major 65 theo classfile compatibility của nó. Không cần agent và ứng dụng có cùng `major_version`. Điều **bắt buộc** là mỗi classfile được nạp đúng định dạng JVM hỗ trợ, ngoài ra phải giải quyết thành công API references, class loader/module access và các điều kiện runtime khác.

Ngược lại:

~~~text
agent17.jar (major 61)   -> Java 17 JVM: OK
helper21.jar (major 65)  -> Java 17 JVM: KHÔNG NẠP ĐƯỢC
app17/ (major 61)       -> Java 17 JVM: OK nếu helper không gây lỗi

Kết quả: agent có thể bắt đầu premain, rồi helper liên kết thất bại.
~~~

Vì vậy kết luận "agent hỗ trợ Java 17" không thể dựa **chỉ** vào `Agent.class`. Phải kiểm tra **tất cả class files có thể được JVM Java 17 load**: nested classes, bootstrap helper, thư viện bytecode, libraries đồng hành, các phiên bản trong Multi-Release JAR và bất kỳ class nào được tạo động.

### 1.1. Không nhầm bốn loại "version"

| Thuật ngữ | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Build JDK** | `javac`, `jar`, Gradle/Maven đang được chạy bằng JDK nào | Dùng JDK 24 để build |
| **`--release`** | Language rules, public platform API và classfile target dùng khi biên dịch | `javac --release 17` |
| **Classfile major/minor** | Phiên bản lưu bên trong từng `.class`; JVM kiểm tra khi load | Java 17: `61.0` |
| **Runtime JDK/JVM** | Máy ảo thực sự chạy tiến trình ứng dụng/agent | `java -version` = 17, 21, 24 |

Một JDK 24 compiler khi dùng `--release 17` có thể tạo class major 61. **Không** có nghĩa runtime Java 24 bị thay thành Java 17. Và việc build bằng JDK 24 **không** tự khiến class major 68 nếu project đã cấu hình `--release 17` hợp lệ.

## 2. Major version nào tương ứng Java nào?

Theo Java Virtual Machine Specification, header một classfile chứa magic number, minor version và major version:

~~~text
Byte offset (0-based):
0..3 : magic         0xCAFEBABE
4..5 : minor_version (unsigned 16-bit, big-endian)
6..7 : major_version (unsigned 16-bit, big-endian)
8..  : constant_pool_count, constant pool, các thành phần khác
~~~

Một vài mốc được dùng nhiều:

| Java release | Major classfile | Major/minor thông thường |
| --- | ---: | --- |
| Java 8 | 52 | 52.0 |
| Java 11 | 55 | 55.0 |
| Java 17 | 61 | 61.0 |
| Java 21 | 65 | 65.0 |
| Java 22 | 66 | 66.0 |
| Java 23 | 67 | 67.0 |
| Java 24 | 68 | 68.0 |
| Java 25 | 69 | 69.0 |
| Java 26 | 70 | 70.0 |

Các mốc này dùng để **giải nghĩa bytecode**, không nói rằng mọi chương trình từ Java cũ sẽ chạy 100% trên JVM mới. Binary format có thể được JVM mới hỗ trợ, nhưng API bị thay đổi/gỡ, reflection encapsulation, module system, dependency hoặc JNI có thể khiến ứng dụng vẫn gặp lỗi.

Với Java SE 12 trở lên, minor `65535` biểu thị một classfile **phụ thuộc vào preview features của release tương ứng**. Ví dụ `65.65535` là Java 21 preview classfile: phải chạy trên **Java 21** với `--enable-preview`; không được suy rằng Java 22/24 sẽ nạp nó chỉ vì hỗ trợ major 65. `--enable-preview` của JVM release khác cũng không biến preview cũ thành tương thích.

### 2.1. JVM mới thường hỗ trợ classfile cũ; chiều ngược lại không đúng

JDK 21 hỗ trợ classfile major 61. Nhưng JDK 17 không hiểu major 65. Kết quả thường gặp:

~~~text
java.lang.UnsupportedClassVersionError:
  ... class file version 65.0,
  this version of the Java Runtime only recognizes
  class file versions up to 61.0
~~~

Đây là bản **rút gọn mô tả thông điệp**, không phải yêu cầu stack trace phải giống nguyên văn trên mọi JVM. Không nên chữa bằng cách đổi `JAVA_HOME` của build mà quên kiểm tra runtime production, hoặc đổi một chuỗi `java.version` trong manifest.

Hãy hỏi: **class nào đang được load có major cao hơn JVM?** Class ấy có thể là agent, helper, main app, thư viện transitive, bytecode generated runtime hay một entry phiên bản cao được chọn từ JAR.

### 2.2. Kiểm tra major và minor bằng `javap`

Khi đã có file class:

~~~bash
javap -verbose agent17/agent/VersionAgent.class
javap -verbose helper17/helper/Probe.class
javap -verbose app21/demo/Target.class
~~~

Trong output, tìm `minor version` và `major version`. Với các lệnh build ở mục 6, kết quả liên quan là:

~~~text
agent17/agent/VersionAgent.class -> major version: 61
helper17/helper/Probe.class     -> major version: 61
app21/demo/Target.class        -> major version: 65
~~~

Đây là **bản tóm tắt kết quả**, không phải nguyên văn đầy đủ của `javap -verbose`. Để xem class trong JAR, có thể dùng `javap -verbose -classpath agent17.jar agent.VersionAgent` và `javap -verbose -classpath helper17.jar helper.Probe`. Khi class có nhiều bản trong Multi-Release JAR, phải xác định **entry thực sự được chọn** theo runtime, không đoán dựa trên class trùng tên ở `META-INF/versions`.

## 3. `javac --release` khác `--source` / `--target`

Một build an toàn cho target Java 17:

~~~bash
javac --release 17 -d out src/demo/Main.java
~~~

Ý nghĩa `--release 17` là **ba phần cùng lúc**: dùng language rules tương ứng, sinh class files target Java 17 và **kiểm tra các public platform APIs có trong Java 17**. Đây thường là lựa chọn ưu tiên khi dùng JDK mới để build code phải chạy trên JVM cũ.

Một thiết lập chỉ có:

~~~bash
javac --source 17 --target 17 -d out src/demo/Main.java
~~~

có thể tạo major 61 nhưng **không tự bảo đảm** code được kiểm tra chống mọi API xuất hiện sau Java 17 nếu compiler dùng platform classes của JDK mới và chưa cấu hình platform tương ứng. Vì vậy chỉ xem `major=61` là chưa đủ để khẳng định phần Java APIs tương thích. `--release` làm việc này đáng tin cậy hơn với các standard platform APIs.

**Giới hạn của `--release`:** nó không kiểm tra độ tương thích bytecode/API của **mọi third-party JAR**; nếu dependency đã build Java 21, compiler có thể từ chối load nó hoặc một code path có thể chỉ fail ở runtime. Nó cũng không kiểm chứng class loader/module graph, JNI ABI hay reflection. Phải kiểm kê dependencies và thử chạy trên **JVM tối thiểu thực tế**.

### 3.1. Hai loại lỗi khác nhau khi cố dùng API mới

Ví dụ agent chỉ dùng `java.lang.instrument`, `Path.of` và `JarFile` đều có trong Java 17, nên `--release 17` phù hợp.

Nhưng nếu agent source import một API chuẩn mới chỉ có từ JDK 24, ví dụ `java.lang.classfile.ClassFile`:

~~~java
// Chỉ là mảnh minh họa một API không có trên JDK 17.
import java.lang.classfile.ClassFile;
~~~

thì build `javac --release 17` không thể hợp lệ: API ấy chưa tồn tại trong Java 17. **Đừng** biên dịch agent với JDK 24, vẫn để JAR tên `agent17.jar`, rồi cho rằng sẽ chạy trên Java 17. Nếu công cụ cần Class-File API chuẩn JDK 24 **bên trong JVM target**, JVM target cũng phải cung cấp API đó. Với Java 17, cân nhắc một thư viện bytecode tương thích hoặc làm biến đổi **offline trên JVM/toolchain mới rồi phát hành classfile target 17 đã được kiểm tra**.

Tương tự, `--release 17` không cho phép dùng Java 21 language feature cần Java 21 syntax. Cần quyết định minimum runtime của **từng artifact**, không chỉ chọn một setting cho toàn bộ repository.

## 4. Mức tối thiểu của agent và các thư viện bên trong agent

Một Java agent khởi động bằng:

~~~bash
java -javaagent:agent17.jar=helper17.jar -cp app17 demo.Main
~~~

JVM nạp class trong manifest `Premain-Class` rồi gọi:

~~~java
public static void premain(String options, Instrumentation inst)
~~~

Nếu `agent.VersionAgent` đã biên dịch major 65 mà runtime là Java 17 (chỉ nhận tới 61), JVM có thể **abort trước khi gọi `premain` và trước `main` của ứng dụng**. Không phải lỗi trong logic transformer, bởi class agent còn chưa load thành công.

Phải kiểm tra:

- Class `Premain-Class` và mọi nested/anonymous classes như `VersionAgent$1.class`.
- Mọi dependencies thực sự được agent load: parser, exporter, metrics API, logging framework, bytecode toolkit.
- API của JDK mà agent dùng có tồn tại trong minimum runtime không.
- Package/loader/module access của agent trong Java 9+.
- Có dùng preview features hoặc MR-JAR entry version cao hơn runtime không.
- Startup agent hay dynamic attach agent có manifest entry tương ứng (`Premain-Class` vs `Agent-Class`).

**Quan trọng:** một agent class major 61 có thể tự load được trên Java 17, nhưng nếu nó thực thi một method tham chiếu API mới chỉ có ở Java 21, kết quả có thể là `NoSuchMethodError` hoặc lỗi linkage khác. Version header **không thay thế** kiểm tra platform API và dependency ABI.

### 4.1. Tại sao JAR manifest không phải nơi “đặt Java version”?

Manifest `Premain-Class` chỉ nói JVM cần load class nào để gọi `premain`. Thuộc tính `Can-Retransform-Classes: true` hoặc `Can-Redefine-Classes: true` khai báo capability mà agent muốn sử dụng, **không** hạ target bytecode. Thuộc tính `Multi-Release: true` cho phép chọn các class entries theo runtime khi có cấu trúc đúng, nhưng **không** làm một class major 65 trong root JAR chạy được trên Java 17.

Nhãn artifact tên `agent-jdk17.jar`, trường `Implementation-Version` hoặc metadata build là thông tin phân phối, **không** thay sự kiểm tra class-file format của JVM.

## 5. Bytecode helper: điểm thất bại thường bị phát hiện muộn

Một transformer có thể chèn instruction tương đương:

~~~text
invokestatic helper/Probe.state:()Ljava/lang/String;
~~~

Nếu class instrumented thực thi instruction này, JVM phải resolve được `helper.Probe` và method `state()` trong loader/module phù hợp. Khi `helper/Probe.class` có major 65 nhưng JVM là Java 17, kết quả có thể là `UnsupportedClassVersionError` **tại thời điểm helper được load**; thời điểm có thể muộn hơn startup nếu helper chỉ được tham chiếu ở đường code hiếm chạy.

Ngoài version header, helper còn có những ràng buộc riêng:

1. **Visibility:** loader của class chứa invocation phải tìm thấy helper; agent load được helper không tự chứng minh app/child/bootstrap loader thấy helper.
2. **Package/module:** readable/exported/open phù hợp với kind của reference và reflective access; `ClassDesc` hoặc tên class đúng không tự cấp quyền.
3. **Method contract:** tên, descriptor, static/instance kind phải khớp. Lỗi có thể là `NoSuchMethodError`/`IncompatibleClassChangeError`.
4. **Dependencies:** helper major 61 nhưng gọi một dependency major 65 vẫn có thể fail trên Java 17.
5. **Nơi triển khai:** `appendToSystemClassLoaderSearch` đưa helper JAR vào system loader search; `appendToBootstrapClassLoaderSearch` là cơ chế riêng cho bootstrap classes, không thay thế lẫn nhau.
6. **Phase/class loading:** nếu helper gây nạp thêm framework phức tạp ngay trong `ClassFileTransformer.transform`, có nguy cơ reentrancy, recursion và overhead; preinitialize/filter cẩn thận.

Điều này dẫn tới yêu cầu CI: **build helper ở mức minimum runtime tương thích với lớp đích mà nó có thể được gọi từ đó**, nhưng không bỏ qua việc tất cả dependencies của helper phải cùng nằm trong tập APIs/bytecode mà JVM ấy hiểu.

### 5.1. "Helper Java 17" không nhất thiết an toàn cho Java 17

Ví dụ `helper/Probe.class` major 61, nhưng nó gọi `thirdparty.Library.someMethod()` từ JAR mà `Library.class` major 65. Nếu code path ấy được chạy trên Java 17, JVM không load được dependency. Tệ hơn, classfile major 61 có thể liên kết tới một method của JDK mới nếu build đã bỏ qua kiểm soát platform API. Vì vậy cần kiểm tra **closure của dependency graph** và chạy integration test trên JDK thấp nhất.

Với helper đưa vào **bootstrap class loader**, dependency visibility còn chặt hơn: những supporting classes được bootstrap load phải chỉ link với classes mà bootstrap loader có thể định nghĩa. Không đưa nguyên một logging framework phụ thuộc system/app loader vào bootstrap rồi cho rằng Java version khớp là đủ.

## 6. Demo chạy được: agent Java 17, helper Java 17/21 và ứng dụng Java 17/21

Thí nghiệm có bốn source files và một manifest. Chúng ta cố tình **giữ nguyên Java source code** giữa các bản build khác version, chỉ thay `--release`. Nhờ thế, khi một ca lỗi xuất hiện, nguyên nhân dễ quan sát là **classfile major**, không phải logic business khác nhau.

### 6.1. Cấu trúc thư mục

~~~text
version-demo/
  helper/
    Probe.java
  agent/
    VersionAgent.java
  demo/
    Target.java
    Main.java
  MANIFEST.MF

  helper17/   (đầu ra build)
  helper21/   (đầu ra build)
  agent17/    (đầu ra build)
  agent21/    (đầu ra build)
  app17/      (đầu ra build)
  app21/      (đầu ra build)

  helper17.jar  helper21.jar
  agent17.jar   agent21.jar
~~~

Tên `helper17`/`app21` là thư mục đầu ra, **không phải** tên Java package. Đặt đúng các file source ở đường dẫn như sơ đồ.

### 6.2. `helper/Probe.java`

~~~java
package helper;

public final class Probe {
    public static String state() {
        return "ready";
    }
}
~~~

`Probe` là helper đơn giản, không phụ thuộc thư viện ngoài Java chuẩn. Dùng cùng một source này để biên dịch hai bản class major 61 và 65.

### 6.3. `agent/VersionAgent.java`

~~~java
package agent;

import helper.Probe;
import java.lang.instrument.ClassFileTransformer;
import java.lang.instrument.Instrumentation;
import java.nio.file.Path;
import java.security.ProtectionDomain;
import java.util.jar.JarFile;

public final class VersionAgent {
    public static void premain(String options, Instrumentation inst)
            throws Exception {

        try (JarFile file = new JarFile(Path.of(options).toFile())) {
            inst.appendToSystemClassLoaderSearch(file);
        }

        System.out.println("AGENT=started");
        System.out.println("HELPER=" + Probe.state());

        inst.addTransformer(new ClassFileTransformer() {
            @Override
            public byte[] transform(
                    ClassLoader loader,
                    String name,
                    Class<?> redefining,
                    ProtectionDomain domain,
                    byte[] data) {

                if ("demo/Target".equals(name)) {
                    int major = ((data[6] & 0xff) << 8)
                            | (data[7] & 0xff);
                    System.out.println("TARGET_MAJOR=" + major);
                }
                return null;
            }
        });
    }
}
~~~

**Giải thích từng phần:**

1. `VersionAgent` có `public static premain(String, Instrumentation)`; JVM gọi nó trước `demo.Main.main` khi có `-javaagent`.
2. `options` là chuỗi sau dấu `=` của `-javaagent:agent17.jar=helper17.jar`. Demo yêu cầu giá trị này là đường dẫn JAR hiện hữu; agent production cần kiểm tra null/path.
3. `new JarFile(...); inst.appendToSystemClassLoaderSearch(file)` bổ sung helper JAR vào system loader search trước khi `Probe.state()` được gọi. Helper không nằm trên `-cp app17` hoặc `-cp app21`.
4. Dòng `AGENT=started` được in trước khi resolve `Probe`; nếu helper version quá mới, có thể thấy AGENT đã bắt đầu rồi gặp lỗi.
5. `ClassFileTransformer` có overload năm tham số được triển khai từ lâu; ở Java 9+, overload nhận thêm `Module` có default implementation chuyển tiếp đến overload này. Chọn dạng năm tham số giúp code tương thích với Java 17 và dễ đọc.
6. `"demo/Target"` là internal binary name JVM (dấu `/`); transformer chỉ in khi thấy đúng lớp đích. `data` là bytes của classfile ở bước transformer hiện tại và **không được sửa trực tiếp**.
7. `data[6]`, `data[7]` là hai byte của `major_version`, dạng unsigned big-endian. `& 0xff` tránh signed-byte issue của Java; khi dịch trái 8 bit và OR sẽ thu đúng major.
8. `return null` nghĩa là transformer **không sửa bytecode**. Demo minh họa việc nhận bytecode của ứng dụng phiên bản khác, **không** là công cụ tự downgrade classfile hay chèn helper vào Target.
9. Dùng `System.out.println` trong callback chỉ dành cho thí nghiệm ít lớp; instrumentation production phải tránh synchronous logging trên hot path và quản lý lỗi/metrics riêng.
10. `Agent.class` và helper nạp ở system loader trong cấu hình launcher thông thường. Custom loaders/named modules có thêm quy tắc; demo không chứng minh mọi loader đều nhìn thấy helper sau append.

**Giới hạn:** transformer nhận dữ liệu JVM cung cấp; nếu có transformer khác đứng trước, bytes có thể đã được sửa. Việc in major chỉ đo **classfile tại callback**, không chứng minh công cụ có thể phân tích đầy đủ mọi classfile version hay viết lại frames/constant pool đúng.

### 6.4. `demo/Target.java`

~~~java
package demo;

public final class Target {
    public static String value() {
        return "hello";
    }
}
~~~

### 6.5. `demo/Main.java`

~~~java
package demo;

public final class Main {
    public static void main(String[] args) {
        System.out.println("APP=" + Target.value());
    }
}
~~~

`Main` tham chiếu `Target.value()`, làm JVM load `demo.Target` khi chương trình chạy. Mục tiêu so sánh là header của Target, không phải performance hay tính đúng đắn của một phép bytecode injection.

### 6.6. `MANIFEST.MF`

~~~text
Manifest-Version: 1.0
Premain-Class: agent.VersionAgent

~~~

Giữ newline và dòng trống cuối. Vì không dùng redefine/retransform, demo **không cần** `Can-Redefine-Classes` hoặc `Can-Retransform-Classes`. Chỉ cần `Premain-Class` để JVM biết class nào chứa entrypoint.

### 6.7. Build với compiler JDK 21 trở lên

Sử dụng `javac` hỗ trợ cả `--release 17` và `--release 21`, chẳng hạn javac của JDK 21/24. Từ thư mục `version-demo/`:

~~~bash
javac --release 17 -d helper17 helper/Probe.java
javac --release 21 -d helper21 helper/Probe.java

javac --release 17 -cp helper17 -d agent17 agent/VersionAgent.java
javac --release 21 -cp helper17 -d agent21 agent/VersionAgent.java

javac --release 17 -d app17 demo/Target.java demo/Main.java
javac --release 21 -d app21 demo/Target.java demo/Main.java

jar --create --file helper17.jar -C helper17 .
jar --create --file helper21.jar -C helper21 .
jar --create --file agent17.jar --manifest MANIFEST.MF -C agent17 .
jar --create --file agent21.jar --manifest MANIFEST.MF -C agent21 .
~~~

**Quan trọng về bước compile agent:** cả hai lượt agent được biên dịch với `-cp helper17`. Bản `agent21` chỉ là biến thể class major 65 do `--release 21`, còn public interface của Probe và source code vẫn như cũ. Runtime quyết định nạp `helper17.jar` hoặc `helper21.jar` theo option của `-javaagent`, không theo classpath của lệnh biên dịch.

Đóng gói `-C agent17 .` là cần thiết vì agent source có anonymous transformer, compiler sinh thêm class `agent/VersionAgent$1.class`. Nếu JAR chỉ chứa `VersionAgent.class` mà quên class anonymous, có thể gặp `NoClassDefFoundError` dù major version của class chính hoàn toàn tương thích.

### 6.8. Kiểm tra major thực tế sau build

Dùng:

~~~bash
javap -verbose agent17/agent/VersionAgent.class
javap -verbose agent21/agent/VersionAgent.class
javap -verbose helper17/helper/Probe.class
javap -verbose helper21/helper/Probe.class
javap -verbose app17/demo/Target.class
javap -verbose app21/demo/Target.class
~~~

Cần thấy:

~~~text
agent17/agent/VersionAgent.class = major 61
agent21/agent/VersionAgent.class = major 65
helper17/helper/Probe.class     = major 61
helper21/helper/Probe.class     = major 65
app17/demo/Target.class        = major 61
app21/demo/Target.class        = major 65
~~~

Sáu kết quả này **đã được kiểm chứng bằng cách đọc trực tiếp header 8 byte của các class files sinh ra**. `javap` trình bày chúng dưới dạng `major version: 61` hoặc `major version: 65`. Kỹ thuật đọc bytes header hữu ích khi cần kiểm kê hàng nghìn JAR entries, nhưng không thay thế class-file parser cho các tác vụ sửa bytecode.

## 7. Hai ma trận chạy thành công

Để thử trên hai JVM, **chọn executable Java cụ thể** thay vì tin tưởng PATH. Ở Linux/macOS thường có `$JAVA17_HOME/bin/java` và `$JAVA21_HOME/bin/java` nếu môi trường đặt tên biến như vậy. Ở Windows, dùng đường dẫn tới `java.exe` bên trong hai bản JDK, chẳng hạn biến PowerShell `$java17`/`$java21` trỏ tới các file tương ứng. Không dùng đường dẫn máy soạn bài làm đường dẫn mặc định cho người học.

Nếu máy chỉ có một JDK, vẫn build classfiles và xem major được, nhưng để chứng minh runtime mismatch phải có JVM ở các version cần thử.

### 7.1. Trường hợp thành công A — Java 17 JVM

Sử dụng **java** từ JDK 17:

~~~bash
java -javaagent:agent17.jar=helper17.jar -cp app17 demo.Main
~~~

**Standard output chính xác đã kiểm chứng trên Corretto 17:**

~~~text
AGENT=started
HELPER=ready
TARGET_MAJOR=61
APP=hello
~~~

Giai đoạn:

1. JVM Java 17 nạp agent class major 61.
2. Agent append helper JAR và gọi helper major 61.
3. Transformer nhận `demo/Target` major 61, in thông tin rồi trả `null`.
4. Java code ứng dụng chạy, in `APP=hello`.

Từng class được nạp thuộc tập classfile versions mà JVM Java 17 hỗ trợ; APIs trong demo cũng có trong Java 17.

### 7.2. Trường hợp thành công B — Java 21 JVM

Sử dụng **java** từ JDK 21, giữ nguyên agent/helper Java 17 nhưng nâng ứng dụng:

~~~bash
java -javaagent:agent17.jar=helper17.jar -cp app21 demo.Main
~~~

**Standard output chính xác đã kiểm chứng trên Microsoft OpenJDK 21:**

~~~text
AGENT=started
HELPER=ready
TARGET_MAJOR=65
APP=hello
~~~

Đây là trường hợp quan trọng: **không yêu cầu agent bytecode major 65 để instrument ứng dụng có major 65**. Agent 61 hoạt động được vì Java 21 JVM tải classfile major 61 và helper major 61, còn callback đơn giản hiểu header chung của classfile major 65. Với **transformer thực sự viết lại code**, vẫn phải đảm bảo parser/builder có hỗ trợ features và attributes của classfile Java 21; chỉ compile agent ở Java 17 không tự chứng minh điều đó.

### 7.3. Ma trận tương thích rút gọn

| Runtime JVM | Agent major | Helper major | App major | Kết quả demo |
| --- | ---: | ---: | ---: | --- |
| Java 17 | 61 | 61 | 61 | **PASS** |
| Java 21 | 61 | 61 | 65 | **PASS** |
| Java 17 | 61 | 61 | 65 | **FAIL**: app `Main` không nạp được |
| Java 17 | 65 | 61 | 61 | **FAIL**: agent không nạp được |
| Java 17 | 61 | 65 | 61 | **FAIL**: helper không nạp được |
| Java 21 | 65 | 61 | 61 | Classfile versions **được phép**; vẫn cần runtime tests nếu muốn tuyên bố tương thích nghiệp vụ |

Ma trận này mô tả **đúng source/JAR của demo**. Trong ứng dụng thực, còn dependencies, generated proxies, preview, loader/module resolution và Java API linkage. Không dùng một bảng major numbers để thay toàn bộ integration tests.

## 8. Ba lỗi thực tế: ứng dụng, agent và helper

Các ca sau dùng executable `java` **của Java 17**. Mỗi lần chạy là một JVM mới để lỗi trước đó không ảnh hưởng test tiếp theo.

### 8.1. App Java 21 trên JVM Java 17

~~~bash
java -javaagent:agent17.jar=helper17.jar -cp app21 demo.Main
~~~

Các dòng agent/helper đã xuất hiện:

~~~text
AGENT=started
HELPER=ready
~~~

Sau đó tiến trình lỗi với thông tin chính (trích rút gọn từ thử nghiệm):

~~~text
java.lang.UnsupportedClassVersionError: demo/Main
class file version 65.0
this version of the Java Runtime only recognizes class file versions up to 61.0
~~~

Vì `demo.Main` đã là major 65, JVM không thể nạp **main class**. Do đó `Target` chưa cần được transformer quan sát và không có `TARGET_MAJOR=65`/`APP=hello` trong ca lỗi này. Agent startup có thể thành công **nhưng ứng dụng vẫn không khởi động**, vì phiên bản ứng dụng quá cao cho runtime.

**Cách xử lý:** chạy app21 trên Java 21+ nếu môi trường hỗ trợ; hoặc **biên dịch lại app với `--release 17`**, điều chỉnh APIs/dependencies/features không tương thích, rồi test trên JDK 17. Không được chỉ đổi header major từ 65 về 61.

### 8.2. Agent Java 21 trên JVM Java 17

~~~bash
java -javaagent:agent21.jar=helper17.jar -cp app17 demo.Main
~~~

Thông tin lỗi chính đã quan sát:

~~~text
java.lang.UnsupportedClassVersionError: agent/VersionAgent
class file version 65.0
this version of the Java Runtime only recognizes class file versions up to 61.0
~~~

Ở ca này JVM không thể load class `Premain-Class` nên **`premain` không bắt đầu**; ứng dụng cũng không được chạy. Một số JVM có thể in thêm diagnostics khi instrumentation process fail/abort trước `main`. Đừng nhầm đây là lỗi helper jar hoặc `JarFile`.

**Cách xử lý:** phát hành agent root/classes/dependencies có classfile và API phù hợp Java 17; trong demo dùng `agent17.jar`. Cần kiểm tra cả anonymous/nested classes trong agent JAR, không chỉ file đầu vào chính.

### 8.3. Helper Java 21 trên JVM Java 17

~~~bash
java -javaagent:agent17.jar=helper21.jar -cp app17 demo.Main
~~~

Trong thử nghiệm, agent đã in:

~~~text
AGENT=started
~~~

Rồi lỗi chính:

~~~text
Caused by: java.lang.UnsupportedClassVersionError: helper/Probe
class file version 65.0
this version of the Java Runtime only recognizes class file versions up to 61.0
~~~

Agent major 61 tải được. Nhưng khi `premain` gọi `Probe.state()` sau khi append JAR, helper class major 65 không nạp được. `premain` không hoàn tất, JVM abort trước ứng dụng. Đây là minh chứng rằng **một JAR helper không tương thích có thể phá startup dù agent JAR chính đã đúng version**.

Nếu helper chỉ được tham chiếu sau khi instrumented method chạy, lỗi tương tự có thể xuất hiện **muộn hơn**, không nhất thiết trong `premain`. Thời điểm phụ thuộc lúc class resolution và execution thực sự cần helper.

### 8.4. Đừng sửa sai tầng

| Lỗi hiển thị tên class nào? | Tầng cần kiểm tra trước | Thao tác ưu tiên |
| --- | --- | --- |
| `agent/VersionAgent` | Agent bytecode/JAR | Inspect `Premain-Class` và toàn bộ agent dependencies |
| `helper/Probe` | Helper bytecode/JAR | Inspect helper và vị trí class loader thực sự load |
| `demo/Main` hoặc `demo/Target` | Application bytecode/JAR | Inspect app artifact, runtime JDK và `--release` |
| Parser ném lỗi không hiểu classfile | Transformer/toolkit | Kiểm tra thư viện parser có support classfile version/features đó |
| JVM ném `VerifyError` sau transform | Bytecode output | Kiểm tra frames, max stack, descriptor và classfile output |
| `NoSuchMethodError`/`NoClassDefFoundError` | API/linkage/dependency | Kiểm tra JDK API và thư viện runtime, loader/module access |

Lỗi `UnsupportedClassVersionError` nói về **file đang được JVM nạp**. Nó không tự chỉ ra file ấy đến từ JAR nào nếu nhiều class loaders/JAR trùng lớp; cần đối chiếu code source/layer/class loader và danh sách artifact thực tế.

## 9. Ba ngưỡng tương thích phải được quản lý riêng

Một cách thiết kế phát hành rõ ràng:

~~~text
minimumRuntimeAgent       = 17
minimumRuntimeHelper      = 17
minimumRuntimeApplication = 21  (cho bản app21)
effectiveRuntimeMinimum   = 21  (cho bộ app21 + agent17 + helper17)
~~~

Đây là **mô hình kiểm soát** dựa trên bytecode/API của demo. Không có một trường JVM nào tự tính lại con số này thay cho kiểm thử dependencies.

Trong project thực, hệ thống có thể có nhiều nhóm:

- **Agent startup classes** cần tương thích với JVM trước khi `premain` có thể chạy.
- **Agent transformer implementation** có thể dùng parser biết đọc nhiều classfile versions; phải test compatibility parser với target bytecode.
- **Helper injected vào app** cần tương thích với JVM và accessible từ defining loader/module của app.
- **Generated classes** do transformer tạo phải có classfile major/minor và attributes hợp lệ cho target JVM, và mọi invoked helper phải link.
- **App/library classes** có thể được compiler sinh ở mức Java khác nhau; runtime chỉ nạp những class thực sự được tham chiếu theo đường chạy, nhưng production test cần bao phủ những đường ấy.
- **Multi-Release JAR variants** có thể cung cấp implementations cho Java 17/21 riêng; cần test đường chọn variant.

Do đó một “minimum supported JDK” cho **cả sản phẩm** thường là mức tối thiểu thỏa mãn mọi thành phần thực sự cần chạy, không phải version nhỏ nhất ghi trên một manifest.

## 10. Output transformer phải tương thích target JVM, không chỉ input

Lúc JVM tải một class, `ClassFileTransformer.transform` nhận `classfileBuffer` và có thể:

- Trả `null`: không biến đổi bytes ở lượt này.
- Trả `byte[]` mới: classfile đã biến đổi phải đúng format, hợp lệ để JVM verify/define/redefine/retransform.

Một lỗi nghiêm trọng là parser/builder tự động phát sinh **classfile major mới hơn runtime**. Ví dụ:

~~~text
Input app major 61 (Java 17)
  -> transformer dùng thư viện xây classfile với default major 65
  -> output major 65
  -> Java 17 JVM không thể định nghĩa lớp
~~~

Cách này không trở nên an toàn chỉ vì `VersionAgent.class` vẫn là major 61. Transformer output là **một classfile mới** mà JVM phải hiểu.

### 10.1. Bất biến nên kiểm tra trong pipeline

Với instrumentation **chỉ chèn hook** và không có lý do nâng classfile version:

1. **Đọc classfile major/minor từ input**; không giả định class nào cũng cùng major trong JVM.
2. **Kiểm tra parser hỗ trợ classfile target**: Java 21 có records, sealed classes, bytecode attributes và language features khác so với classfile cũ; thư viện cũ có thể không parse đúng.
3. **Giữ classfile major hợp lệ** cho runtime, thường giữ nguyên major/minor của input khi sinh output insert-only.
4. **Phát sinh frames/StackMapTable/constant pool/attributes hợp lệ** sau khi thêm instructions.
5. **Không đưa vào opcode/class attributes chỉ có nghĩa ở classfile version khác** mà runtime không chấp nhận.
6. **Không tạo references tới helper/API không thể resolve** hoặc không accessible qua loader/module thật.
7. **Verify output** và chạy với JVM thấp nhất, bao gồm đường exception, constructors, concurrency và nhiều class loaders.
8. Khi dùng redefine/retransform, tuân các giới hạn thay đổi cấu trúc class; không tự thêm field/method rồi cho rằng đó chỉ là instrument method body.

Nếu một library phát sinh bytecode mặc định ở Java 21, đặt explicit class writer target phù hợp Java 17 khi thực sự hỗ trợ. Nhưng **hạ con số major không tự làm ngữ nghĩa của class mới tương thích Java 17** nếu nó còn chứa cấu trúc, instruction hoặc API references chỉ có ở Java mới hơn.

### 10.2. Không mọi Java 21 feature đều downgrade được

`--release 17` yêu cầu source phù hợp language/API của Java 17. Một class đã biên dịch Java 21 có thể dùng features/attributes mà Java 17 không hiểu. Để hỗ trợ Java 17, cần **thiết kế và biên dịch một implementation có ngữ nghĩa phù hợp Java 17**, không “giả mạo” bytecode 65 thành 61.

Nếu ứng dụng dùng một JDK API bổ sung từ Java 21, transformer không tự chuyển lời gọi ấy thành API có trong Java 17. Một bytecode downgrade đúng nghĩa là bài toán chuyển đổi semantics/API/metadata lớn hơn nhiều so với thay hai bytes version.

## 11. Preview classfile và Java release gắn chặt với nhau

Một classfile phụ thuộc preview có thể có version như:

~~~text
major = 65  (Java 21)
minor = 65535 (preview)
~~~

Quy tắc chính: classfile preview của **Java N** chỉ được nạp trên **Java N** khi preview được bật theo cách JVM hỗ trợ, không phải Java N+1. Thường compiler và runtime đều cần `--enable-preview` phù hợp:

~~~bash
# Ví dụ công thức với compiler/runtime Java 21 khi source có preview:
javac --enable-preview --release 21 SomePreviewClass.java
java --enable-preview SomePreviewClass
~~~

Đây là **công thức cấu hình**, không phải một ví dụ source class độc lập: nguồn `SomePreviewClass.java` phải thực sự dùng preview feature có trong đúng release. Đừng thêm `--enable-preview` một cách cơ học vào toàn bộ agent distribution chỉ để sửa lỗi major mismatch; nó **không** khiến Java 17 hiểu major 65.

Một release build dành cho nhiều JVM nên ưu tiên **stable language features** và classfile minor 0 ở phần common agent/helper, trừ khi có lý do rõ ràng và ma trận preview riêng.

## 12. Multi-Release JAR giúp phân phối nhiều implementation, nhưng không phá quy tắc major

Một Multi-Release JAR (MR-JAR) có main manifest:

~~~text
Multi-Release: true
~~~

và có thể chứa:

~~~text
agent.jar
  META-INF/MANIFEST.MF
  helper/Probe.class                       (base, major 61)
  META-INF/versions/21/helper/Probe.class  (Java 21 variant, major <= 65)
~~~

Trên runtime hỗ trợ MR-JAR, class loader có thể chọn entry versioned phù hợp cao nhất **không vượt** Java runtime feature version, rồi fallback xuống base. Nếu chạy Java 17, entry Java 21 không được chọn; nếu chạy Java 21, entry Java 21 có thể được chọn. Base classes vẫn phải tương thích với minimum runtime đã công bố.

**Không nhầm `META-INF/versions/21` là classfile major 21:** con số `21` ở path là **Java SE release**, trong khi classfile Java 21 có major **65**.

Một số ràng buộc quan trọng:

- `Multi-Release: true` phải đặt trong main manifest.
- Các versioned entries phải theo cấu trúc `META-INF/versions/N` với N >= 9.
- `.class` trong entry N có major không vượt classfile version cho Java N.
- Public/protected API của variant phải tương thích với base theo quy tắc JAR specification.
- MR-JAR **không được bootstrap class loader hỗ trợ theo cùng cách** như classpath/modulepath JAR. Khi append MR-JAR vào boot classpath, JAR được đối xử như JAR thường theo JAR specification; phải test riêng, không suy mọi helper variant đều tự được chọn.
- Nếu muốn Java 17/21 behavior khác nhau, phải build/test **từng variant** trên JVM tương ứng.
- MR-JAR không sửa classfile không tương thích nằm ở root, không chữa lỗi parser/toolkit, và không mở module/access tự động.

Trong agent, MR-JAR có thể hữu ích để phân phối API-specific adapter code, nhưng phải chú ý cách JVM load **agent classes**, helper classes và bootstrap classes. Không gộp tất cả variant vào một JAR rồi nghĩ mọi loader đều chọn đúng.

## 13. Build pipeline: quản lý agent/helper/app như ba sản phẩm

Một mono-repo có thể gồm ba subprojects:

~~~text
root/
  agent-core/        -> min Java 17
  helper-runtime/    -> min Java 17
  sample-app/        -> Java 17 hoặc Java 21
~~~

Mỗi subproject cần khai báo mức bytecode/API riêng. Nếu dùng Maven Compiler Plugin, có thể đặt trong `pom.xml` của **từng module**:

~~~xml
<properties>
  <maven.compiler.release>17</maven.compiler.release>
</properties>
~~~

App dành riêng Java 21 có thể dùng `21` ở module của app. Đây là đoạn cấu hình **minh họa**, không phải một POM Maven độc lập; project còn cần plugins, dependencies, packaging và JAR manifest agent đúng.

Với Gradle Groovy DSL ở project agent/helper:

~~~groovy
tasks.withType(JavaCompile).configureEach {
    options.release = 17
}
~~~

App21 dùng `options.release = 21`. Không suy rằng Gradle/Maven toolchain đang chạy Java 21/24 sẽ tự tạo source/target version phù hợp; project phải định nghĩa và kiểm tra output thực tế.

**Chốt artifact contract:**

- `agent17.jar` chứa mọi class của agent ở major <= 61 (trừ variant MR-JAR được quản lý).
- `helper17.jar` chứa helper classes ở major <= 61, toàn bộ transitive dependencies phù hợp target JVM.
- `app21` có thể có major 65 và chỉ được triển khai ở Java 21+.
- Nếu transformer output cần chạy Java 17, nó phải là classfile được verifier/runtime Java 17 chấp nhận.
- Build metadata gắn minimum Java release, loại helper loader và danh sách supported JDKs, không chỉ tên file.

### 13.1. Kiểm kê cả nested classes và dependencies

`javap -verbose` trên một class là điểm khởi đầu, không đủ cho một distribution. Kiểm kê:

~~~bash
jar --list --file agent17.jar
jar --list --file helper17.jar
~~~

Kiểm tra tất cả entries `.class`, bao gồm anonymous/nested classes và dependencies được shaded vào JAR. `VersionAgent$1.class` phải được tính; một class level cao ẩn trong JAR có thể chỉ được nạp khi một tính năng được bật.

Với transitive JARs không đóng gói vào agent, kiểm tra versions của dependencies theo graph build. `jdeps` có thể giúp xác định package/module/API dependencies và `--multi-release` khi phân tích MR-JAR, nhưng không thay được integration tests trên đúng runtime và class-loader topology.

### 13.2. Vì sao test ở JDK mới nhất thôi không đủ?

JDK 24 có thể tải major 61 và 65, nên cả hai bản class có thể chạy thành công ở đó. Điều ấy **không chứng minh** phần agent/helper major 65 tương thích JDK 17. Phải test trên **JDK tối thiểu hỗ trợ**; nếu support cả Java 17 và 21, kiểm thử ít nhất:

- JVM 17 + agent17 + helper17 + app17.
- JVM 21 + agent17 + helper17 + app21.
- JVM 17 + agent17 + helper21 + app17 phải thất bại theo kỳ vọng của negative test.
- JVM 17 + agent21 + helper17 + app17 phải thất bại trước premain.
- JVM 17 + agent17 + helper17 + app21 phải thất bại vì app major 65.
- JVM 21 + transformer thật xử lý app21 class files, đảm bảo output đúng verifier và behavior.
- Nếu có preview/MR-JAR, chạy thêm đúng từng variant/release cần hỗ trợ.

**Dùng mỗi Java version như một môi trường test thực sự**, không chỉ gọi `javac --release` rồi kiểm tra trên JDK 24 duy nhất.

## 14. Compatibility của bytecode toolkits

Một agent có thể biên dịch Java 17 nhưng dùng thư viện parser/rewriter không nhận ra classfile Java 21. Chẳng hạn library phiên bản cũ có thể báo "unsupported class file major version 65" khi nó cố parse input. Đây **khác** `UnsupportedClassVersionError` do JVM ném khi load chính class library:

- **Library parser không hỗ trợ 65:** JVM Java 21 load agent/library có thể thành công, nhưng agent chủ động ném exception khi đọc Target.class major 65.
- **Library.class bản thân major 65 trên JVM 17:** JVM ném `UnsupportedClassVersionError` trước khi parser có cơ hội chạy.
- **Transformer output không hợp lệ:** JVM có thể ném `ClassFormatError`/`VerifyError`/lỗi linking khi định nghĩa lớp sau transform.
- **Runtime Java API thiếu:** có thể gặp `NoSuchMethodError`, `NoClassDefFoundError` hay lỗi khác dù class major hợp lệ.

Cách quản lý đúng:

1. Xác định **range classfile versions** mà thư viện biến đổi hỗ trợ, không chỉ minimum Java runtime của thư viện.
2. Pin và kiểm thử version của bytecode toolkit trên classfiles có records/sealed classes/lambda/attributes thật.
3. Nếu gặp classfile version chưa hỗ trợ, dùng chính sách rõ: skip transform trả `null` nếu telemetry optional; hoặc fail có kiểm soát nếu transform là điều kiện bắt buộc.
4. Không sửa header input hoặc output để "qua" parser; sửa bằng toolkit mới hoặc pipeline phù hợp.
5. Đánh giá cả bytecode của ứng dụng **sau khi có nhiều transformers cùng chạy**: input mà một transformer nhận có thể đã qua stage trước.

## 15. Các lỗi khác không nên gán nhầm cho phiên bản bytecode

| Lỗi | Câu hỏi ưu tiên |
| --- | --- |
| `UnsupportedClassVersionError` | Class nào có major/minor cao/preview so với JVM? |
| `NoClassDefFoundError` | Lớp/dependency có tồn tại trong loader/module này không; nguyên nhân sâu bên dưới là gì? |
| `ClassNotFoundException` | ClassLoader không tìm class được yêu cầu; search path/module đúng chưa? |
| `NoSuchMethodError` | Agent/helper đã compile với API có method nhưng runtime class thực sự có method ấy không? |
| `IncompatibleClassChangeError` | Method static/instance, class/interface, ABI mismatch? |
| `IllegalAccessError` | Package/module/visibility hoặc loader identity khác? |
| `ClassFormatError` | Classfile output/constant pool/attributes cấu trúc có hợp lệ? |
| `VerifyError` | Operand stack, frames, descriptor, control flow do transformer tạo có đúng? |
| `LinkageError` khác | Có duplicate classes, version skew, loader constraints, thay đổi definitions? |
| `IllegalClassFormatException` từ transformer | Parser/transformer báo classfile input không hợp lệ theo contract |
| `ExceptionInInitializerError` | Static init của helper/agent/dependency có thất bại không? |

Một `NoClassDefFoundError` có thể có **cause** liên quan `UnsupportedClassVersionError`. Đọc cả root cause và tên binary class thay vì chỉ xem top-level exception.

**Thời điểm lỗi cũng quan trọng:** trước `premain` nghiêng về agent class/manifest; trong `premain` sau log khởi động nghiêng về helper/dependency; sau `main` hoặc một request cụ thể nghiêng về application/injected helper path. Đây là heuristic để điều tra, không thay stack trace.

## 16. Packaging và triển khai đa JVM

### 16.1. Image/container và service launcher

Kiểm tra **runtime trong container/service**, không dùng `java -version` của máy developer để suy ra. Ví dụ một image build dùng JDK 24, runtime image chứa JRE 17: nếu artifact app compile major 65, môi trường runtime vẫn thất bại.

Với build Docker nhiều stage, chốt cặp:

~~~text
Build stage: JDK 24 + javac --release 17/21 theo từng artifact
Runtime image Java 17: agent17 + helper17 + app17
Runtime image Java 21: agent17 + helper17 + app21
~~~

Không sử dụng Java 21 dependency trong helper17 chỉ vì build stage chạy JDK 24. Pin tags/digests của runtime images và chạy smoke tests trên image thực sự sẽ triển khai.

### 16.2. Agent attach động và lớp đã load

Với dynamic attach, JVM đích đã chạy với một Java release cố định. `Agent-Class` và dependencies của agent phải tương thích với **JVM đó**, ngay cả khi công cụ gửi lệnh attach được chạy bằng một JDK mới hơn. Không thể dùng JDK mới của CLI để "nâng cấp" khả năng nạp bytecode của JVM đích đang chạy.

Với retransform/redefine, classfile output còn chịu giới hạn thay đổi schema. Java agent phải xác minh capability, isModifiableClass, class loader/module và classfile format trước khi cài bytes mới. Đừng diễn giải "agent đã attach thành công" thành "helper/API mới nhất có thể chạy trong VM cũ".

### 16.3. Dùng bytecode helper trong system/bootstrap

Nếu helper được append vào system class loader search, một class do bootstrap loader định nghĩa **không đương nhiên** thấy helper. Nếu cần bootstrap helper, phải dùng bố trí phù hợp như `appendToBootstrapClassLoaderSearch` và giới hạn dependencies của helper theo những classes bootstrap nhìn thấy.

Trong cả hai kiểu, helper major vẫn phải được JVM target hỗ trợ. Chuyển một file major 65 từ system loader sang bootstrap loader trên Java 17 **không** khiến nó hợp lệ.

## 17. Checklist CI/CD trước khi phát hành agent

- [ ] Xác định **minimum JVM version** của môi trường mà agent sẽ chạy (không chỉ build JDK).
- [ ] Xác định target release và kiểm tra **mọi** class trong agent, helper, nested classes, shaded JARs, external dependencies.
- [ ] Dùng `javac --release N` cho source thuộc minimum release N; kiểm tra APIs thực sự dùng, không chỉ header.
- [ ] Đóng gói manifest đúng `Premain-Class`/`Agent-Class` theo cách khởi động, không gộp với Main-Class.
- [ ] Kiểm tra bytecode major/minor của root và MR-JAR variants.
- [ ] Test agent + helper + app trên **JDK thấp nhất** và các runtime được hỗ trợ.
- [ ] Test JVM mới hơn với app classfiles mới, đảm bảo transformer hiểu format của chúng.
- [ ] Khi transformer trả byte[] mới, verify major/minor, constant pool, frames, method descriptors và các constraints của redefinition.
- [ ] Kiểm tra class loader/module resolution của helper tại **đúng lớp có hook**.
- [ ] Test các đường request hiếm, lazy loading và dynamic proxies (không chỉ startup).
- [ ] Test preview features trên đúng Java release hoặc tránh dùng trong common artifacts.
- [ ] Test Multi-Release JAR ở mỗi runtime và xét riêng bootstrap helper.
- [ ] Phân biệt lỗi platform API, binary ABI, compiler config và format classfile.
- [ ] Có phương án rollback an toàn: revert artifact/agent version; không cố rewrite header trên production classes.
- [ ] Ghi rõ classfile version support, runtime support và parser support trong release notes.

## 18. Câu hỏi tự kiểm tra

1. Agent `major 61` có thể xử lý class ứng dụng `major 65` trên Java 21 JVM không? Điều kiện nào ngoài major cần kiểm thử?
2. Vì sao `helper major 65` không chạy trên Java 17 dù agent `major 61`?
3. Java 21 classfile dùng major bao nhiêu? Java 17, Java 24 thì sao?
4. Dùng JDK 24 `javac --release 17` khác gì việc chạy ứng dụng trên JVM Java 17?
5. `--source 17 --target 17` có đảm bảo đối chiếu public platform APIs của JDK 17 giống `--release 17` không?
6. Byte offset nào trong classfile header chứa `major_version`?
7. Vì sao cần `& 0xff` khi đọc unsigned bytes bằng Java `byte`?
8. Một classfile có `65.65535` có chạy trên Java 24 với `--enable-preview` không? Vì sao?
9. Trong ví dụ, `AGENT=started` xuất hiện rồi helper load fail cho biết gì về giai đoạn lỗi?
10. Vì sao `VersionAgent$1.class` phải được đóng gói và kiểm tra classfile version riêng?
11. Nếu tool transformer dùng parser chưa hỗ trợ major 65, JDK 21 JVM có tự sửa giúp nó không?
12. Vì sao giữ nguyên major input thường an toàn hơn tự nâng major khi chỉ chèn hook?
13. Multi-Release JAR có thể chọn variant Java 21 trên JVM Java 17 không?
14. Vì sao entry `META-INF/versions/21` không có nghĩa classfile major là 21?
15. Nếu helper ở unnamed module của system loader, liệu mọi bootstrap/plugin class đều nhìn thấy nó?
16. Tại sao `UnsupportedClassVersionError` của app21 không thể sửa bằng cách đổi manifest `Premain-Class`?
17. Trong một Docker multi-stage build, con số Java nào quyết định bytecode có load được ở production?
18. Làm sao tách lỗi agent runtime mismatch khỏi lỗi classfile output của transformer?
19. Khi bytecode major tương thích, những lỗi `NoSuchMethodError`/`IllegalAccessError`/`VerifyError` còn có thể xảy ra vì sao?
20. Bạn sẽ viết ma trận CI nào cho hai bản app17/app21 và một agent17/helper17?

## 19. Kết luận

**Có ba lớp tương thích cần tính riêng**: Java bytecode của agent, bytecode của helper và bytecode của ứng dụng/transformer output. Không cần các lớp ấy cùng phiên bản — agent Java 17 cùng helper Java 17 có thể làm việc với ứng dụng Java 21 trên JVM Java 21 — nhưng **mỗi class được JVM nạp phải phù hợp với chính runtime đó** và toàn bộ chuỗi API/dependency/loader/module phải liên kết được.

`javac --release` là cách thực tiễn để build code với target release có kiểm soát; `javap -verbose` và kiểm tra header giúp phát hiện major/minor; kiểm thử trên JDK thấp nhất giúp bắt lỗi thực tế. Những giới hạn như preview, MR-JAR, bytecode toolkit support, helper visibility và verifier output phải được xử lý riêng.

Thí nghiệm của bài tái hiện được ba nguồn lỗi `UnsupportedClassVersionError`: **app**, **agent**, **helper**. Đó là một tiêu chí chẩn đoán quan trọng trước khi triển khai rộng: xác định đúng tầng phát sinh lỗi rồi sửa đúng artifact hoặc runtime, thay vì nâng/hạ Java version một cách mù quáng.

### Tài liệu chính thức

- [Java Virtual Machine Specification, Chapter 4 – Class File Format](https://docs.oracle.com/javase/specs/jvms/se24/html/jvms-4.html): `magic`, `major_version`, `minor_version` và phiên bản classfile.
- [Oracle JDK 17 – javac tool](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html): `--release`, `--source`, `--target` và platform API restrictions.
- [Oracle JDK 17 – java.lang.instrument](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/package-summary.html): `-javaagent`, `Premain-Class`, helper visibility và startup lifecycle.
- [Oracle JDK 17 – ClassFileTransformer](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html): `classfileBuffer`, `transform` và return `null` khi không sửa bytes.
- [Oracle JDK 17 – Instrumentation](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): append helper JAR, redefine/retransform và tương tác với class loaders.
- [Oracle JDK 17 – JAR File Specification](https://docs.oracle.com/en/java/javase/17/docs/specs/jar/jar.html): `Multi-Release: true`, versioned entries và quy tắc chọn classes.
- [Oracle JDK 21 – Preview Features](https://docs.oracle.com/en/java/javase/21/language/preview-language-and-vm-features.html): `--enable-preview` và tính ràng buộc theo release.
- [Apache Maven Compiler Plugin – Setting --release](https://maven.apache.org/plugins/maven-compiler-plugin-4.x/examples/set-compiler-release.html): cấu hình release của từng Maven module.
