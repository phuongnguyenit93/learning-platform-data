# ASM, Byte Buddy và bộ đọc bytecode cần hỗ trợ class file mới

Trong quá trình **Java Advance Compatibility Migration**, một ứng dụng có thể biên dịch bình thường bằng JDK mới và chính JVM cũng có thể nạp được class của ứng dụng, nhưng quá trình chạy Gradle, Maven, coverage, mocking, instrumentation hoặc Java agent lại thất bại với thông báo:

```text
java.lang.IllegalArgumentException:
  Unsupported class file major version 65
```

Một lỗi khác có thể đến từ Byte Buddy:

```text
Java 21 (65) is not supported by the current version of Byte Buddy
```

Vấn đề không nhất thiết nằm ở mã nguồn, không nhất thiết do `JAVA_HOME` sai và cũng không có nghĩa Java 21 không thể chạy ứng dụng. **Một thư viện phân tích hoặc biến đổi bytecode đang đọc class file có định dạng mới hơn phạm vi mà phiên bản thư viện đó hiểu.**

**ASM** là bộ công cụ cấp thấp để đọc, phân tích và ghi Java class file. **Byte Buddy** là thư viện cao cấp cho việc sinh class, tạo proxy và instrumentation, có các thành phần phân tích class file bên dưới. Những công cụ như JaCoCo, Mockito, agent giám sát, framework proxy, build plugin và một số compiler/plugin khác có thể sử dụng trực tiếp hoặc gián tiếp các thư viện như vậy.

Bài học giải thích định dạng class file, version tương thích, các lớp nguyên nhân khi nâng JDK, cách nhận diện thành phần đang đọc bytecode, chiến lược nâng ASM/Byte Buddy và kiểm thử lại agent mà không phụ thuộc vào workaround che giấu lỗi.

## 1. Phân biệt ba loại khả năng tương thích

Khi nói “thư viện hỗ trợ Java 21”, cần hỏi chính xác **hỗ trợ điều gì**.

| Phạm vi | Câu hỏi | Ví dụ |
|---|---|---|
| JVM runtime | JVM có nạp và thực thi class file này không? | JDK 17 không nạp được class file được compile cho Java 21 |
| Bytecode parser/reader | Thư viện có đọc đúng cấu trúc class file này không? | ASM quá cũ có thể ném `Unsupported class file major version 65` |
| Bytecode writer/transformer | Thư viện có tạo hoặc biến đổi class hợp lệ cho phiên bản này không? | Agent có thể đọc class nhưng sinh StackMapTable hoặc attributes không đúng |
| Framework integration | Phiên bản framework có gọi parser/transformer đúng cách không? | Mocking hoặc coverage lỗi dù source compile thành công |
| Tool/process compatibility | Tool chứa parser đang chạy bằng JVM nào? | Gradle daemon JDK mới dùng plugin với ASM cũ |

Đây là các hợp đồng riêng biệt. **JVM mới hỗ trợ class file mới không đồng nghĩa mọi thư viện ASM/Byte Buddy trong cùng process cũng hỗ trợ.**

### 1.1. Biên dịch, nạp và đọc bytecode là ba thao tác khác nhau

Giả sử:

```text
javac JDK 21
     |
     v
App.class (major version 65)
     |
     +--> JVM JDK 21: có thể nạp class đúng version
     |
     +--> ASM cũ: có thể không parse được major 65
     |
     +--> Byte Buddy cũ: có thể từ chối mô hình class file
     |
     +--> JaCoCo agent cũ: có thể không instrument được
```

Một hệ thống có thể chạy được ở chế độ bình thường nhưng hỏng khi bật `-javaagent`, coverage hoặc inline mocking. Ngược lại, có khi build thất bại ngay tại phase cấu hình vì Gradle/Groovy/ASM phải đọc class file mới trong plugin.

### 1.2. Bytecode cũ chạy trên JVM mới khác bytecode mới chạy trên JVM cũ

Java có tính tương thích ngược ở nhiều trường hợp: JVM mới thường có thể nạp class file của các Java release cũ còn được hỗ trợ. Chiều ngược lại không đúng: JVM Java 17 không thể nạp class file Java 21.

Bytecode reader là một thư viện riêng và có vòng đời hỗ trợ riêng. Một phiên bản parser cũ không bắt buộc hiểu constant pool tag, attribute, version hoặc cấu trúc mới, ngay cả khi JVM hiện tại hiểu chúng.

## 2. Class file major và minor version

Class file Java là định dạng nhị phân có magic number `0xCAFEBABE`, minor version, major version và nhiều bảng cấu trúc như constant pool, fields, methods và attributes.

Phần đầu một class file:

```text
u4 magic
u2 minor_version
u2 major_version
u2 constant_pool_count
...
```

**Major version** thường thể hiện Java release mà class file nhắm tới. **Minor version** có thể mang ý nghĩa bổ sung, bao gồm marker preview trong những Java release có preview features.

### 2.1. Bảng major version thường gặp

| Java release | Class file major version |
|---|---:|
| Java 8 | 52 |
| Java 9 | 53 |
| Java 10 | 54 |
| Java 11 | 55 |
| Java 12 | 56 |
| Java 13 | 57 |
| Java 14 | 58 |
| Java 15 | 59 |
| Java 16 | 60 |
| Java 17 | 61 |
| Java 18 | 62 |
| Java 19 | 63 |
| Java 20 | 64 |
| Java 21 | 65 |
| Java 22 | 66 |
| Java 23 | 67 |
| Java 24 | 68 |
| Java 25 | 69 |

Với các release sau, phải đối chiếu tài liệu class file/JVMS của đúng JDK mục tiêu. Không nên cập nhật parser bằng cách tự sửa một hằng số major version rồi coi như đã hỗ trợ toàn bộ định dạng.

### 2.2. Cách xác định version từ lỗi

Ví dụ:

```text
Unsupported class file major version 65
```

cho biết class file có major 65, tương ứng Java 21. Điều đó **không chứng minh JVM hiện tại là Java 21**: file có thể được biên dịch bởi một module khác, một dependency mới, build plugin, Java agent hoặc annotation processor.

Cần xác định **class nào đang được đọc**, từ artifact nào, bởi parser nào, trong JVM nào.

### 2.3. Preview class và minor version

Một số class file được biên dịch với preview features mang minor version đặc biệt (thường là `65535`) và đòi hỏi điều kiện runtime phù hợp, bao gồm `--enable-preview` trên release tương ứng.

Trường hợp preview có thêm một trục tương thích:

- JVM phải thuộc đúng release và được phép dùng preview feature.
- Parser phải hiểu định dạng/class constructs có liên quan.
- Transformer phải bảo tồn và xử lý metadata đúng.
- Chỉ đổi major/minor bytes không tạo ra một class hợp lệ.

Không nên dùng preview bytecode cho thư viện cần phân phối rộng nếu dự án không chấp nhận các ràng buộc đó.

## 3. Phân biệt `UnsupportedClassVersionError` của JVM với lỗi từ ASM

Hai loại lỗi thường bị gộp chung vì đều nhắc đến “class file version”.

### 3.1. JVM không nạp được class

Ví dụ:

```text
java.lang.UnsupportedClassVersionError:
  com/example/App has been compiled by a more recent
  version of the Java Runtime ...
```

Đây là lỗi phát sinh khi JVM được yêu cầu nạp class file có major version cao hơn nó hỗ trợ. Hướng xử lý thông thường:

1. Chạy bằng JVM mới đủ mức.
2. Hoặc compile class về release thấp hơn nếu source và dependencies cho phép.
3. Xác minh bytecode của mọi runtime dependency, không chỉ class ứng dụng.

Thay ASM không làm JDK 17 chạy được bytecode Java 21.

### 3.2. ASM không đọc được class file

Ví dụ:

```text
java.lang.IllegalArgumentException:
  Unsupported class file major version 65
    at org.objectweb.asm.ClassReader...
```

Ở đây, JVM có thể hoàn toàn đủ khả năng chạy file; nhưng `ClassReader` của một phiên bản ASM cũ từ chối class file Java 21.

Hướng xử lý:

1. Xác định bản ASM đang được gọi.
2. Xác định thư viện/framework/plugin mang ASM đó.
3. Nâng lên một bản ASM hỗ trợ class file release mục tiêu.
4. Kiểm thử quá trình parse và transform, không chỉ startup.

### 3.3. Byte Buddy từ chối Java/class file version

Byte Buddy có cơ chế hiểu phiên bản Java và cấu trúc class file riêng. Nếu Byte Buddy cũ không hỗ trợ release mục tiêu, lỗi có thể xuất hiện khi tạo proxy, instrument class hoặc xử lý classfile version.

Hướng xử lý thường là nâng Byte Buddy và **thư viện sử dụng nó** như Mockito/agent, thay vì chỉ nâng một artifact tùy ý trong dependency graph.

### 3.4. Lỗi trông giống version nhưng do yếu tố khác

Không phải mọi lỗi `ClassReader` hoặc `ClassFormatError` đều do parser quá cũ. Class file có thể bị hỏng, bị transform sai, bị đóng gói không đúng hoặc có bytecode verifier metadata không hợp lệ.

Cần xem stack trace, code source của class, artifact checksum và giai đoạn xảy ra lỗi trước khi kết luận.

## 4. ASM là gì và khi nào nó xuất hiện?

ASM là thư viện cấp thấp có thể:

- Đọc nội dung class file (`ClassReader`).
- Đi qua cấu trúc bytecode bằng `ClassVisitor`, `MethodVisitor` và các visitor khác.
- Đọc hoặc xây dựng mô hình cây qua ASM Tree API.
- Tạo và ghi bytecode (`ClassWriter`).
- Phân tích dataflow/stack frames qua ASM Analysis API.
- Xử lý một số metadata, instruction và attribute phù hợp với phiên bản thư viện.

Một đoạn ví dụ đọc class:

```java
import java.io.IOException;
import java.io.InputStream;
import org.objectweb.asm.ClassReader;
import org.objectweb.asm.ClassVisitor;
import org.objectweb.asm.Opcodes;

public final class AsmInspector {
    public static void main(String[] args) throws IOException {
        try (InputStream in =
                AsmInspector.class.getResourceAsStream("/com/example/App.class")) {
            if (in == null) {
                throw new IOException("Không tìm thấy class resource");
            }

            ClassReader reader = new ClassReader(in);

            reader.accept(
                    new ClassVisitor(Opcodes.ASM9) {
                        @Override
                        public void visit(
                                int version,
                                int access,
                                String name,
                                String signature,
                                String superName,
                                String[] interfaces) {
                            System.out.println("Class: " + name);
                            System.out.println("Class file version: " + version);
                        }
                    },
                    ClassReader.SKIP_CODE);
        }
    }
}
```

Đây là minh họa cho ASM 9 API. Để compile, dự án cần dependency `org.ow2.asm:asm` phù hợp. `Opcodes.ASM9` là **ASM visitor API level**, không phải cam kết rằng mọi bản ASM 9.x hiểu mọi Java release trong tương lai.

### 4.1. Vì sao ASM cần cập nhật khi Java thêm class file features?

Một Java release mới có thể:

- Tăng major version.
- Định nghĩa một constant pool tag hoặc attribute mới.
- Thay đổi cấu trúc/semantics của metadata có liên quan.
- Bổ sung kiểu class/record/sealed/preview feature mới.
- Đưa thêm quy tắc verifier hoặc stack-map behavior.

Parser cần biết khi nào một cấu trúc hợp lệ, cách đọc độ dài/format và cách bảo tồn dữ liệu khi transform. Nếu chỉ bỏ kiểm tra major version, parser cũ có thể đọc sai attribute và ghi lại class không hợp lệ.

### 4.2. `ClassReader.SKIP_CODE` không sửa thiếu hỗ trợ version

Một số chương trình chỉ cần annotation hoặc class name nên dùng `SKIP_CODE`. Nhưng constructor của `ClassReader` đã có thể từ chối class file mới trước khi visitor được chạy.

Vì vậy, bỏ qua instructions không bảo đảm tránh được lỗi `Unsupported class file major version`.

### 4.3. ASM visitor API level khác classfile max supported version

ASM có những hằng như `ASM7`, `ASM8`, `ASM9`, biểu thị mức API visitor. Các bản cập nhật trong cùng major ASM có thể bổ sung hỗ trợ class file Java mới.

Đừng suy:

```text
Opcodes.ASM9 == Java 9
```

hoặc:

```text
Tôi thấy ASM9 nên chắc chắn hỗ trợ mọi Java 9+.
```

Cần kiểm tra release notes và thử parser thực tế trên class file của release mục tiêu.

## 5. Byte Buddy là gì và vì sao nó phụ thuộc khả năng đọc bytecode?

Byte Buddy cung cấp API để định nghĩa hoặc sửa đổi Java classes ở mức trừu tượng cao hơn ASM, thường dùng trong:

- Mocking và test instrumentation.
- Runtime proxy generation.
- Java agent cho tracing, metrics, profiling và application monitoring.
- Method interception và advice.
- Class transformation lúc nạp hoặc retransform.
- Code generation của framework.

Ví dụ minh họa **tạo class bằng Byte Buddy**:

```java
import net.bytebuddy.ByteBuddy;
import net.bytebuddy.dynamic.loading.ClassLoadingStrategy;
import static net.bytebuddy.matcher.ElementMatchers.named;
import static net.bytebuddy.implementation.FixedValue.value;

public final class ByteBuddyExample {
    public static class Greeting {
        public String message() {
            return "original";
        }
    }

    public static void main(String[] args) throws Exception {
        Class<?> generated = new ByteBuddy()
                .subclass(Greeting.class)
                .method(named("message"))
                .intercept(value("instrumented"))
                .make()
                .load(
                        ByteBuddyExample.class.getClassLoader(),
                        ClassLoadingStrategy.Default.WRAPPER)
                .getLoaded();

        Greeting instance =
                (Greeting) generated.getDeclaredConstructor().newInstance();
        System.out.println(instance.message());
    }
}
```

Một bản Byte Buddy có thể dùng ASM được đóng gói/đổi namespace nội bộ hoặc các phần phân tích khác theo thiết kế và version. Vì vậy, dependency graph của `org.ow2.asm:asm` **không luôn phản ánh toàn bộ parser mà Byte Buddy đang dùng**.

### 5.1. Nâng ASM bên ngoài không nhất thiết nâng ASM bên trong Byte Buddy

Nếu Byte Buddy đang sử dụng một bản ASM được shade/repackage, chỉ thêm:

```groovy
implementation 'org.ow2.asm:asm:<new-version>'
```

không nhất thiết thay đổi bản parser nội bộ của Byte Buddy. Phải nâng chính Byte Buddy hoặc thư viện/phần mềm đóng gói Byte Buddy phù hợp.

Tương tự, một build plugin có thể nhúng ASM trong JAR riêng. Nâng ASM ở application runtime classpath chưa chắc tác động đến plugin classpath của Gradle hoặc Maven.

### 5.2. Không coi chế độ thử nghiệm là giải pháp production

Một số phiên bản Byte Buddy có cơ chế thử nghiệm cho Java version chưa chính thức hỗ trợ, và có thể xuất hiện property dạng `net.bytebuddy.experimental`. Đây không phải một cam kết rằng bytecode mới đã được hiểu và transform an toàn.

Với migration production, ưu tiên phiên bản được nhà phát hành công bố hỗ trợ chính thức. Chỉ dùng chế độ thử nghiệm trong phạm vi phân tích có kiểm soát, với test rõ và kế hoạch nâng cấp thật sự.

### 5.3. Byte Buddy version còn ảnh hưởng generated class và verifier

Ngay cả khi phiên bản mới tránh được lỗi đầu vào, generated bytecode vẫn phải hợp lệ:

- Stack map frames.
- Method descriptors.
- Access flags và method visibility.
- Nestmate/record/sealed class constraints.
- Constructor/override semantics.
- Classloading strategy.
- Runtime package/module access.

Vì vậy, kiểm thử cần bao gồm **hành vi proxy/instrumentation**, không chỉ thử `ClassFileVersion.ofThisVm()` hoặc nạp được Byte Buddy library.

## 6. Java agent đọc và biến đổi class ở thời điểm nào?

Một Java instrumentation agent có thể được gắn từ đầu:

```bash
java -javaagent:monitoring-agent.jar -jar app.jar
```

hoặc được attach động bằng các cơ chế được hỗ trợ trong môi trường cho phép.

Java agent thường cung cấp một trong hai entrypoint:

```java
public static void premain(
        String agentArgs,
        java.lang.instrument.Instrumentation inst) {
    // Đăng ký transformer khi JVM khởi động.
}
```

hoặc:

```java
public static void agentmain(
        String agentArgs,
        java.lang.instrument.Instrumentation inst) {
    // Entry point cho cơ chế attach động.
}
```

Transformer nhận class bytes để kiểm tra hoặc thay đổi trước khi JVM định nghĩa class (hoặc trong những thao tác retransformation phù hợp).

### 6.1. Agent có thể làm cả ứng dụng không khởi động được

Ví dụ:

```text
java -javaagent:old-agent.jar -jar app.jar
```

Agent nạp ASM/Byte Buddy quá cũ, nhận class file major mới và ném exception. Khi transformer thất bại hoặc agent startup lỗi theo cách không được xử lý, ứng dụng có thể không khởi động hoặc không instrument được class mục tiêu.

Thử tắt agent trong môi trường kiểm thử có kiểm soát có thể giúp phân biệt vấn đề:

```text
Không có agent: ứng dụng chạy được
Có old-agent: lỗi ClassReader/Byte Buddy
```

Không nên dùng “bỏ agent mãi mãi” như phương án mặc định nếu agent đang cung cấp security instrumentation, monitoring hoặc coverage bắt buộc. Cần nâng agent lên bản tương thích và xác minh chức năng.

### 6.2. `ClassFileTransformer` và khả năng transform

Ví dụ skeleton:

```java
import java.lang.instrument.ClassFileTransformer;
import java.lang.instrument.Instrumentation;
import java.security.ProtectionDomain;

public final class ExampleAgent {
    public static void premain(
            String agentArgs,
            Instrumentation instrumentation) {

        instrumentation.addTransformer(new ClassFileTransformer() {
            @Override
            public byte[] transform(
                    ClassLoader loader,
                    String className,
                    Class<?> classBeingRedefined,
                    ProtectionDomain protectionDomain,
                    byte[] classfileBuffer) {

                // Ví dụ chỉ quan sát, không thay đổi bytecode.
                // Parser dùng ở đây phải hỗ trợ class file version mới.
                return null;
            }
        });
    }
}
```

`return null` nghĩa là không đề nghị thay đổi class trong callback đó. Nếu transformer sử dụng ASM/Byte Buddy, chính parser/writer của agent phải hiểu class file thực tế. Manifest agent và quá trình package entrypoint cần được cấu hình thêm khi phát hành.

### 6.3. Retransformation và redefinition không giống load ban đầu

Một số agent chỉ transform lúc class được load. Số khác muốn retransform hoặc redefine class đã nạp. Với `Instrumentation`, cần xem:

- JVM có hỗ trợ `isRetransformClassesSupported()` và khả năng tương ứng không.
- Agent có đăng ký transformer với chế độ có thể retransform không.
- Những hạn chế của redefinition đối với schema của class.
- Transformation có bảo toàn bytecode/attributes hợp lệ không.
- Việc thay đổi class đang hoạt động có tạo side effects không.

Một bản ASM/Byte Buddy đọc được class mới là điều kiện cần, nhưng **không đảm bảo mọi thao tác redefinition đều được JVM cho phép**.

### 6.4. Agent động và thay đổi runtime policy

Một số JDK mới đưa cảnh báo hoặc hạn chế liên quan dynamic agent loading; JDK 21 bắt đầu cảnh báo trong những kịch bản attach động theo hướng siết hành vi mặc định về sau. Cần kiểm tra chính sách cụ thể của runtime và cách agent được cài đặt.

Điều đó **khác** lỗi parser không hỗ trợ major version. Nếu agent không được phép attach, nâng ASM không sửa được; nếu agent attach được nhưng parser lỗi, thay đổi attach policy không phải nguyên nhân.

## 7. Các công cụ hay mang bộ đọc bytecode gián tiếp

Một dự án có thể không khai báo ASM/Byte Buddy trực tiếp nhưng vẫn phụ thuộc chúng.

| Thành phần | Vì sao đọc/ghi bytecode? | Điểm cần kiểm tra |
|---|---|---|
| JaCoCo | Instrument class để thu coverage | Version JaCoCo/agent có hỗ trợ class file target? |
| Mockito inline mock maker | Instrumentation và dynamic class generation qua Byte Buddy | Mockito và Byte Buddy versions có đồng bộ? |
| Byte Buddy Agent | Attach/transform class | Agent version, runtime policy, parser |
| APM/tracing agent | Instrument JDBC/HTTP/framework classes | Vendor agent có công bố JDK support? |
| Spring hoặc một số framework proxy | Phân tích/generate classes trong một số cấu hình | Framework/ASM embedded versions |
| Hibernate enhancement | Bytecode enhancement cho entities | Hibernate enhancer/provider support |
| Gradle/Groovy/Kotlin plugin | Parse class files, metadata hoặc compiler input | Gradle wrapper, plugin và bundled parser |
| Annotation processor | Đọc class metadata hoặc dùng compiler internals | Processor compatibility với compiler JDK |
| Obfuscator/shrinker | Phân tích và tái ghi class | Parser/writer hỗ trợ classfile target? |
| Static analyzer | Đọc bytecode để phát hiện rule violation | Tool/plugin release phù hợp với JDK mới |

Không phải mọi tool trong bảng đều dùng ASM hoặc Byte Buddy ở mọi version. Ý cần kiểm tra là **các thành phần trung gian thực sự đọc hoặc ghi class file**, kể cả khi thư viện ASM không có trong source dependencies của ứng dụng.

### 7.1. Coverage là tình huống thường gặp

Một ví dụ failure:

```text
org.jacoco.agent...:
  Error while instrumenting com/example/App
Caused by: java.lang.IllegalArgumentException:
  Unsupported class file major version 65
```

Ứng dụng có thể chạy được khi không thu coverage. Khi bật coverage, JaCoCo agent cũ đọc file major 65 và thất bại.

Hướng xử lý là chọn phiên bản JaCoCo hỗ trợ Java target, đồng thời kiểm tra wrapper/plugin tích hợp JaCoCo. Không nên chỉ đổi `targetCompatibility` xuống Java 17 khi dự án thực sự cần Java 21.

### 7.2. Mockito inline có thể lỗi dù unit test compile

Mockito có thể tạo mock bằng subclass hoặc inline instrumentation tùy version/cấu hình. Khi một mock maker dùng Byte Buddy không hỗ trợ Java version mới, test có thể lỗi lúc gọi `Mockito.mock(...)` dù compile và các test không dùng mock vẫn pass.

Cần xem nested cause có nhắc Byte Buddy/ASM, rồi nâng Mockito và các dependency phù hợp. Không nên tự ép Byte Buddy lên version bất kỳ mà không xem compatibility của Mockito đang dùng.

### 7.3. Framework và build plugin có classloader riêng

Gradle plugin chạy trong Gradle daemon, không nhất thiết chia sẻ `implementation` hoặc `runtimeClasspath` của dự án. Vì vậy:

```groovy
dependencies {
    implementation 'org.ow2.asm:asm:...'
}
```

không chắc thay được ASM được dùng bên trong plugin. Cần nâng plugin/Gradle wrapper, hoặc điều chỉnh dependency của build logic đúng tầng.

Với Maven, plugin dependencies cũng có class realm riêng. Nâng thư viện thuộc `<dependencies>` của ứng dụng có thể không tác động tới ASM do `maven-plugin` mang theo.

## 8. Maven: tìm ASM/Byte Buddy trong dependency graph

### 8.1. Dependency của ứng dụng

Chạy:

```bash
mvn dependency:tree
```

Tìm ASM:

```bash
mvn dependency:tree -Dincludes=org.ow2.asm:asm
```

Tìm Byte Buddy:

```bash
mvn dependency:tree -Dincludes=net.bytebuddy:byte-buddy
```

Những lệnh này hỗ trợ xác định dependency path và resolved version trong ngữ cảnh project. Để tìm các artifact ASM phụ (`asm-commons`, `asm-tree`, `asm-analysis`), cần tìm thêm module tương ứng hoặc xem tree đầy đủ.

### 8.2. Maven plugin dependencies có thể nằm ở chỗ khác

Nếu lỗi xuất hiện khi chạy một goal plugin, hãy kiểm tra plugin version và dependency của plugin. Runtime dependency tree của ứng dụng có thể không chứa bản ASM mà plugin đang sử dụng.

Một Maven build dùng compiler plugin mới nhưng bytecode analysis plugin cũ có thể thất bại sau khi compile thành công. Giải pháp cần áp dụng ở **plugin bị lỗi**, không chỉ application BOM.

### 8.3. Quản lý version tập trung

Nếu ứng dụng phụ thuộc trực tiếp ASM/Byte Buddy, có thể dùng `dependencyManagement` hoặc BOM/platform để thống nhất phiên bản thích hợp. Nhưng lưu ý:

- Một bản mới của `asm` không thay tự động thư viện đã **shade ASM** vào JAR.
- ASM modules nên thuộc cùng bộ version phù hợp; tránh trộn `asm`, `asm-tree` và `asm-commons` nhiều thế hệ.
- Không override dependency transitive mà không kiểm tra framework/agent có hỗ trợ bản mới không.
- Sau resolution, kiểm tra **artifact thực sự được package**.

## 9. Gradle: tìm parser trong đúng configuration

### 9.1. Xem resolved dependencies

```bash
./gradlew dependencies --configuration runtimeClasspath
```

Tìm ASM:

```bash
./gradlew dependencyInsight \
  --dependency asm \
  --configuration runtimeClasspath
```

Tìm Byte Buddy:

```bash
./gradlew dependencyInsight \
  --dependency byte-buddy \
  --configuration testRuntimeClasspath
```

Nếu lỗi xảy ra ở test mocking, `testRuntimeClasspath` thường quan trọng hơn `runtimeClasspath`. Nếu lỗi từ Gradle plugin ở configuration phase, dependencyInsight của application classpath có thể không phản ánh parser của plugin.

### 9.2. Giữ các lớp build và test riêng biệt

Một build có thể có:

```text
Gradle daemon JVM: JDK 17
JavaCompile toolchain: JDK 21
options.release: 21
Test JVM: JDK 21
JaCoCo agent: version cũ, parser không hỗ trợ major 65
```

Trong tình huống này, `./gradlew --version` chỉ giúp xác định JVM của Gradle, không xác định `JavaCompile` toolchain hay JaCoCo parser.

Nâng Gradle wrapper có thể cần thiết để hỗ trợ Java mới ở build engine, nhưng **cũng không tự đảm bảo JaCoCo, Mockito và mọi plugin đều đã được nâng**.

### 9.3. Ví dụ cấu hình toolchain và JaCoCo

Ví dụ Groovy DSL minh họa vị trí cấu hình:

```groovy
plugins {
    id 'java'
    id 'jacoco'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 21
}

jacoco {
    // Chọn phiên bản được công bố hỗ trợ class file của JDK mục tiêu.
    toolVersion = providers.gradleProperty('jacocoVersion').get()
}
```

Ở đây `jacocoVersion` là property dự án phải được khai báo theo chính sách dependency. Ví dụ không ấn định một số version dễ lỗi thời. Trước khi áp dụng, cần xem Gradle/JaCoCo compatibility và khả năng hỗ trợ JDK 21 của bản đã chọn.

Khi JDK mục tiêu khác 21, thay các giá trị tương ứng và xác nhận Gradle wrapper hỗ trợ compiler toolchain release đó.

### 9.4. Đừng force cả graph khi chưa hiểu nguồn lỗi

Một giải pháp vội vàng:

```groovy
resolutionStrategy.force 'org.ow2.asm:asm:<version>'
```

có thể không tác động tới ASM được shade, không tác động tới parser trong Gradle plugin classloader và có thể khiến các ASM modules còn lại không đồng bộ.

Dùng dependency constraints/platform và nâng component sở hữu parser là hướng dễ bảo trì hơn, sau khi đã xác định rõ artifact gây lỗi.

## 10. Shaded ASM và nhiều bản parser trong cùng ứng dụng

Shading là kỹ thuật đóng gói/relocate classes của một dependency vào namespace nội bộ. Một application có thể đồng thời có:

```text
org.objectweb.asm.ClassReader
net.bytebuddy.jar.asm.ClassReader
vendor.agent.internal.asm.ClassReader
```

Các tên này là ví dụ minh họa cho tình huống **một số thư viện mang parser riêng**; tên namespace cụ thể phụ thuộc phiên bản/nhà phát hành.

Nếu lỗi stack trace chỉ tới:

```text
vendor.agent.internal.asm.ClassReader
```

thì nâng `org.ow2.asm:asm` trên application classpath chưa chắc thay được parser đó.

### 10.1. Cách nhận diện nguồn gốc

Có thể xem:

- Stack trace có package của parser, framework và agent.
- JAR chứa class đó.
- Manifest và metadata version.
- Dependency graph của đúng process/classloader.
- Artifact APM/coverage/mock agent thực tế được deploy.

Với class đang được nạp, có thể in code source trong môi trường cho phép:

```java
Class<?> type = org.objectweb.asm.ClassReader.class;

System.out.println(type.getClassLoader());
System.out.println(
        type.getProtectionDomain().getCodeSource() == null
                ? "<no code source>"
                : type.getProtectionDomain().getCodeSource().getLocation());
```

`CodeSource` có thể null hoặc không chỉ ra tệp JAR trực tiếp trong custom loader, nên phải kết hợp class loading logs và cấu trúc artifact.

### 10.2. Tránh “dùng lại một ASM cũ vì chỉ cần một tính năng”

Nếu nhiều plugin/framework cùng chạy trong một process, việc ép chung một bản ASM cũ có thể làm thành phần cần bytecode mới bị lỗi. Ngược lại, nâng ASM quá mạnh so với framework cũ có thể gây API incompatibility nếu framework sử dụng internals không được đảm bảo.

Nên ưu tiên phiên bản framework/plugin chính thức hỗ trợ JDK mục tiêu, rồi để framework quản lý các dependency đã được kiểm nghiệm.

## 11. Đọc class file version mà không phụ thuộc ASM

Khi ASM cũ không đọc được class mới, có thể xác định major/minor bằng cách đọc tám byte đầu của `.class`. Ví dụ chương trình độc lập dùng Java SE:

```java
import java.io.DataInputStream;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

public final class ClassVersionReader {
    public static void main(String[] args) throws IOException {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                    "Usage: java ClassVersionReader <path-to-class>");
        }

        try (DataInputStream in =
                new DataInputStream(Files.newInputStream(Path.of(args[0])))) {

            int magic = in.readInt();
            if (magic != 0xCAFEBABE) {
                throw new IOException("Not a Java class file");
            }

            int minor = in.readUnsignedShort();
            int major = in.readUnsignedShort();

            System.out.println("major = " + major);
            System.out.println("minor = " + minor);
        }
    }
}
```

Biên dịch và chạy:

```bash
javac ClassVersionReader.java
java ClassVersionReader build/classes/java/main/com/example/App.class
```

Kỹ thuật này **chỉ đọc header**, không xác nhận phần còn lại của class file hợp lệ và không chứng minh ASM/Byte Buddy có thể transform class đó.

### 11.1. Dùng `javap`

JDK cung cấp `javap` để xem bytecode:

```bash
javap -verbose \
  -classpath build/classes/java/main \
  com.example.App
```

Tìm dòng:

```text
major version: 65
```

`javap` của một JDK mới đủ mức thường phù hợp để xem class file mới. Nếu công cụ trên PATH thuộc JDK cũ hơn class file, chính `javap` cũng có thể gặp giới hạn; kiểm tra `javap` đang đến từ JDK nào.

### 11.2. Kiểm tra class trong dependency JAR

Một dependency JAR có thể chứa class file mới hơn phần còn lại của ứng dụng. Đầu tiên liệt kê:

```bash
jar tf lib/example-library.jar
```

Sau đó dùng `javap -classpath lib/example-library.jar -verbose <ClassName>` để xem class mục tiêu.

Với multi-release JAR, cần chú ý các phiên bản class nằm dưới:

```text
META-INF/versions/11/...
META-INF/versions/17/...
META-INF/versions/21/...
```

Các entry versioned không tự động là lỗi duplicate class. JVM và tooling có quy tắc chọn class theo multi-release manifest, vì vậy **bộ đọc/transformer phải hiểu hoặc được cấu hình đúng để xử lý MR-JAR**. Quét tất cả entry rồi dùng bản cao nhất một cách mù quáng có thể dẫn tới kết luận sai.

## 12. Lỗi có thể xuất hiện dù source target đã hạ xuống

Giả sử build đặt:

```groovy
tasks.withType(JavaCompile).configureEach {
    options.release = 17
}
```

nhưng vẫn báo:

```text
Unsupported class file major version 65
```

Các lý do có thể gồm:

1. Dependency của dự án chứa Java 21 bytecode.
2. Test class được compile bằng cấu hình khác main source.
3. Build plugin hoặc Gradle script class được biên dịch cho Java 21.
4. Plugin quét toàn bộ JDK runtime hoặc dependency mới, không chỉ output main.
5. Multi-release JAR chứa entry dành cho Java 21.
6. Class được sinh bởi annotation processor hoặc code generator theo cấu hình khác.
7. Một agent đang instrument JDK/framework classes có class file mới.
8. Còn file cũ trong build output/cache do quá trình incremental build không như kỳ vọng.

Do đó, **không được mặc định cho rằng compiler target của project quyết định mọi class mà parser gặp**. Cần tìm đúng class bị đọc và artifact chứa nó.

### 12.1. `--release` không tự hạ dependency bytecode

`--release 17` kiểm soát Java language/API platform và class file của source đang được compile bởi tác vụ tương ứng. Nó không biến một JAR dependency đã compile cho Java 21 thành JAR Java 17.

Nếu dependency chỉ hỗ trợ Java 21, ứng dụng Java 17 cần version dependency khác, nguồn build tương thích hoặc thay đổi runtime target.

### 12.2. Gradle/Maven plugin cũng có classpath riêng

`JavaCompile.options.release` không sửa class file của Gradle plugin đang được load trong daemon. Tương tự, Maven Compiler Plugin `<release>` không hạ compiler/plugin dependencies của những plugin khác.

Hãy xác định lỗi xảy ra ở **configuration**, **compile**, **test instrumentation**, **package** hay **application runtime** trước khi sửa cấu hình target.

## 13. Ma trận kiểm thử khi nâng JDK

Một thử nghiệm compatibility cần bao gồm nhiều đường xử lý class file:

| Đường kiểm thử | Mục tiêu | Dấu hiệu thành công |
|---|---|---|
| Compile source | Compiler và language target phù hợp | Build được class file mong muốn |
| Load class trên JVM mục tiêu | JVM hỗ trợ major/minor và dependencies | Không có `UnsupportedClassVersionError` |
| ASM parse | Bộ đọc hiểu class file mới | `ClassReader` và visitor hoàn tất với input đại diện |
| Byte Buddy proxy | Sinh/load class đúng contract | Tạo proxy và gọi method như mong đợi |
| Byte Buddy agent | Transformer tương thích class target | Classload/retransform thành công, hành vi đúng |
| JaCoCo coverage | Agent instrument các class mới | Test chạy, coverage report hợp lệ |
| Mockito inline | Mock maker sử dụng parser tương thích | Mock và verification đúng |
| Framework enhancement | ORM/proxy/AOP xử lý class mới | Integration test thực tế thành công |
| Multi-release JAR | Chọn entry đúng theo runtime | Runtime và parser dùng class phù hợp |
| Production startup | Agent, plugins và launcher cuối | Không có lỗi linkage/transform |
| Bài kiểm thử chức năng | Bytecode sau biến đổi vẫn đúng | Không chỉ hết exception mà kết quả nghiệp vụ vẫn đúng |

Không cần bật tất cả công cụ cho mọi dự án, nhưng phải kiểm thử những thành phần thực sự tham gia build/run.

### 13.1. Xây một lớp mẫu để kiểm tra parser

Khi cần phát hiện sự cố sớm, có thể tạo một JAR mẫu biên dịch bằng JDK mục tiêu rồi đưa qua công cụ ASM/Byte Buddy/agent đang được sử dụng. Bộ test nên có cấu trúc đại diện, không chỉ một class rỗng.

Ví dụ tính năng có thể cần đại diện:

- Class thông thường, interface, generic signature.
- Record, sealed classes nếu project sử dụng.
- Lambdas, invokedynamic và method references.
- Annotations và metadata được framework đọc.
- Class có nested/inner classes.
- Preview features nếu được phép trong dự án.
- Class được instrument qua agent.
- Multi-release JAR nếu xuất hiện trong dependencies.

Khả năng parse một class đơn giản chưa chứng minh transformer xử lý đúng mọi feature mới.

## 14. Triệu chứng và cách định hướng nguyên nhân

| Triệu chứng | Giai đoạn thường gặp | Hướng điều tra |
|---|---|---|
| `Unsupported class file major version 65` trong `org.objectweb.asm.ClassReader` | Build/plugin/agent parser | Nâng component đang mang ASM, không chỉ JVM |
| Byte Buddy báo Java release chưa hỗ trợ | Mock/proxy/agent | Nâng Byte Buddy và thư viện chủ quản |
| `UnsupportedClassVersionError` | JVM nạp class | Đổi runtime hoặc giảm target/dependency bytecode |
| `ClassFormatError` | Class loader/verifier | Kiểm tra transform output và class file hợp lệ |
| `VerifyError` | JVM verifier | Kiểm tra stack frames, writer/transformer và bytecode target |
| Coverage agent lỗi nhưng không coverage thì chạy | JaCoCo/test instrumentation | Nâng JaCoCo/agent và kiểm tra target class |
| Plugin Gradle lỗi khi evaluate script | Gradle daemon/plugin | Xem wrapper/plugin compatibility và bundled parser |
| Mockito test fail trong `mock()` | Inline/subclass mock maker | Xem Byte Buddy version và test JVM |
| Agent chạy bình thường trên JDK cũ, fail trên JDK mới | Runtime instrumentation | Xem agent release, JDK support và module/attach policy |
| `InaccessibleObjectException` | JPMS reflection | Xem opens/exports; không mặc nhiên là classfile parser issue |
| `NoSuchMethodError` trong ASM/Byte Buddy | Dependency ABI mismatch | Tìm version/classpath conflict, không chỉ major class version |

Một stack trace đầy đủ là nguồn bằng chứng tốt hơn tên exception tóm tắt trong CI.

## 15. Quy trình migration thực hành

### Bước 1 — Lập danh sách những thành phần đọc hoặc viết bytecode

Kiểm kê ASM, Byte Buddy, JaCoCo, Mockito, APM agents, Hibernate enhancer, annotation processors, Gradle/Maven plugins, obfuscators và các công cụ tạo proxy/class.

Nên lưu module và phase sử dụng:

```text
Gradle daemon:  plugin A -> ASM embedded
JavaCompile:    annotation processor B
Test JVM:       Mockito -> Byte Buddy
Test JVM:       JaCoCo agent
Application:    monitoring-agent.jar
Runtime:        framework proxy/enhancer
```

### Bước 2 — Ghi runtime/compiler target

Thu thập:

- JDK vendor/full release của daemon/build process.
- Compiler toolchain JDK và `--release`.
- JDK của test workers.
- JDK production/container.
- Major/minor version của class đang lỗi.
- Version của thư viện parser/transformer nếu xác định được.

### Bước 3 — Chẩn đoán class file nào gây lỗi

Từ stack trace, tìm class được instrument hoặc đang bị parse. Dùng `javap -verbose` hoặc đọc class header để xác định major/minor. Nếu class thuộc dependency, xác định artifact và version thực tế.

### Bước 4 — Xác định ai đang sở hữu parser

Nếu stack trace là `org.objectweb.asm.ClassReader`, kiểm tra ASM version trên đúng classloader. Nếu là Byte Buddy, JaCoCo hoặc plugin có shaded ASM, tìm component chủ quản.

Không chỉ chạy dependency tree ở application runtime khi lỗi nằm trong plugin classloader.

### Bước 5 — Chọn phiên bản được hỗ trợ

Nâng:

- Gradle wrapper và plugin nếu build engine/plugin không hỗ trợ JDK mới.
- ASM modules khi application sở hữu ASM trực tiếp.
- Byte Buddy cùng Mockito/framework/agent khi chúng quản lý parser.
- JaCoCo agent/plugin nếu lỗi coverage.
- Vendor APM/monitoring agent nếu lỗi instrumentation ở production.

**Không đưa ra một bảng version cứng dùng cho mọi JDK** nếu chưa đối chiếu release notes và artifact cụ thể. Khả năng hỗ trợ class file có thể xuất hiện ở các bản cập nhật của cùng nhánh thư viện, còn phiên bản JDK liên tục phát hành mới.

### Bước 6 — Đồng bộ dependency và loại bỏ bản cũ

Sau khi chọn version, kiểm tra cả dependency graph lẫn artifact deploy. Nếu JAR có parser được shade, nâng đúng agent/plugin thay vì chỉ thêm ASM mới.

Khi có nhiều bản ASM không được shade trong cùng classloader, giải quyết version conflict và kiểm tra modules liên quan có version tương thích.

### Bước 7 — Kiểm thử parse, instrument và hành vi

Chạy đúng những đường code dùng parser:

- Build và compile task.
- Unit test với mocks.
- Coverage instrumentation.
- Framework proxy/enhancement.
- Agent startup và hoạt động sau startup.
- Runtime reflection/JDK modules khi có liên quan.
- Preview/MR-JAR nếu sản phẩm dùng chúng.

Một phép thử chỉ xem `--version` của thư viện không thay cho việc đưa class file thật vào parser.

### Bước 8 — Kiểm tra artifact cuối và rollout

Đảm bảo CI và production không sử dụng agent hoặc plugin khác version local. Ghi artifact checksum của agent/JAR, JDK vendor/update và version được kiểm nghiệm.

Nếu ứng dụng có agent bắt buộc, xác minh cả độ phủ giám sát hoặc enforcement sau khi nâng: việc agent “không crash” nhưng bỏ qua instrumentation cũng là thất bại chức năng.

## 16. Ví dụ tổng hợp: nâng project từ Java 17 lên Java 21

Giả sử hệ thống:

```text
Ứng dụng: Java 17, Spring-based services
Build: Gradle
Testing: JUnit + Mockito + JaCoCo
Production: OpenTelemetry/APM Java agent
Mục tiêu: Java 21
```

Sau khi nâng compiler toolchain lên 21, test fail:

```text
java.lang.IllegalArgumentException:
  Unsupported class file major version 65
    at org.objectweb.asm.ClassReader...
```

Một quy trình xử lý có cơ sở:

1. Xác minh class gây lỗi có major 65 bằng `javap`.
2. Đọc stack trace để xác định parser đến từ JaCoCo, Mockito, Gradle plugin hay agent.
3. Nếu lỗi khi coverage test: kiểm tra JaCoCo version và nâng bản hỗ trợ class file Java 21.
4. Nếu lỗi khi `Mockito.mock`: kiểm tra Byte Buddy/Mockito compatibility và nâng cả bộ phù hợp.
5. Nếu lỗi tại build configuration: kiểm tra Gradle wrapper và plugin parser thay vì chỉ application dependencies.
6. Nếu ứng dụng chỉ lỗi khi bật production agent: chọn agent release có công bố hỗ trợ Java 21.
7. Kiểm tra `runtimeClasspath`, `testRuntimeClasspath`, plugin classpaths và JAR cuối.
8. Chạy lại test, proxy, coverage, agent startup và các luồng sử dụng instrumented methods.
9. Ghim version trong CI và tạo regression gate cho lần nâng JDK tiếp theo.

Không nên chữa bằng cách giảm `targetCompatibility` về Java 17 nếu ứng dụng thực sự cần Java 21 language/runtime features. Nếu sản phẩm vẫn cần hỗ trợ Java 17 runtime, cần một chiến lược release target và dependency thích hợp riêng.

## 17. Tại sao không nên chỉ sửa major version trong file `.class`?

Một ý tưởng nguy hiểm là mở file binary và sửa byte major từ 65 về 61 để parser cũ không từ chối.

Điều này không an toàn vì:

- Class file có thể chứa attribute hoặc constant pool structure không được định nghĩa ở version cũ.
- JVM verifier có quy tắc tương ứng với class file version.
- Các instructions, descriptors hoặc metadata có thể không phù hợp.
- Compiler có thể tạo bytecode dùng Java API chỉ có ở runtime mới.
- Parser có thể hiểu sai và ghi lại class hỏng.
- Một binary thay đổi không còn tương ứng artifact được build/sign theo quy trình tin cậy.

**Không chỉnh byte class version thủ công để “giả lập tương thích”.** Nếu cần chạy trên runtime cũ, hãy biên dịch lại bằng toolchain/release phù hợp và kiểm tra toàn bộ dependencies; nếu cần parser hiểu class mới, nâng parser.

## 18. Khi nào fallback không instrumentation có thể dùng?

Trong một số môi trường phát triển, có thể tạm chạy test hoặc ứng dụng **không có agent** để khoanh vùng nguyên nhân. Nhưng quyết định này phải dựa trên mục đích:

- **Coverage agent:** bỏ coverage có thể giúp test chức năng chạy, nhưng pipeline cần chặn release nếu coverage là yêu cầu.
- **Mocking/instrumentation:** đổi mock maker có thể làm test khác hành vi; cần xác nhận phù hợp.
- **APM/tracing agent:** chạy không agent có thể được phép trong test chẩn đoán, nhưng không đồng nghĩa production được bỏ giám sát.
- **Security agent:** vô hiệu hóa agent có thể làm mất kiểm soát bảo mật; không nên coi là workaround vận hành mặc định.

Một khi đã xác định vấn đề do agent/parser, hãy cập nhật bản được hỗ trợ và khôi phục đường kiểm thử/giám sát đầy đủ.

## 19. Checklist kiểm tra trước khi nâng JDK

- [ ] Đã xác định Java target release và class file major/minor tương ứng.
- [ ] Đã phân biệt JVM `UnsupportedClassVersionError` với ASM `Unsupported class file major version`.
- [ ] Đã tìm parser cụ thể trong stack trace và artifact chứa nó.
- [ ] Đã kiểm tra bản ASM/Byte Buddy trực tiếp và các bản được shade.
- [ ] Đã kiểm tra JaCoCo, Mockito, tracing/APM và các Java agents khác.
- [ ] Đã xác định Gradle/Maven plugin classpaths tách khỏi application classpath.
- [ ] Đã xác nhận Gradle wrapper/daemon JDK tương thích với compiler JDK.
- [ ] Đã kiểm tra `--release`, test JVM và runtime production, không chỉ `JAVA_HOME`.
- [ ] Đã kiểm tra class files của dependencies và multi-release JAR.
- [ ] Đã xem nhu cầu preview feature và minor version nếu ứng dụng dùng preview.
- [ ] Đã chọn các phiên bản thư viện được công bố hỗ trợ JDK mục tiêu.
- [ ] Đã kiểm thử parser, writer, proxy và class transformation trên code đại diện.
- [ ] Đã kiểm thử coverage, mocking và agent trước/sau startup.
- [ ] Đã xác minh instrumentation không bị âm thầm bỏ qua.
- [ ] Đã kiểm tra tương thích reflection/JPMS và attach policy khi có liên quan.
- [ ] Đã cố định version, artifact checksum và runtime image trong CI/CD.
- [ ] Đã tránh chỉnh major bytes hoặc dùng experimental switch làm giải pháp production.
- [ ] Đã ghi rõ owner và lộ trình nâng agent/plugin khi lên JDK release tiếp theo.

## 20. Kết luận

Một bản Java mới không chỉ thay đổi compiler và runtime; nó có thể thay đổi định dạng class file mà toàn bộ hệ sinh thái tooling phải hiểu. JVM hỗ trợ class file mới không bảo đảm ASM, Byte Buddy, JaCoCo, Mockito, build plugins hoặc Java agents cũ đọc và biến đổi được bytecode đó. Lỗi “Unsupported class file major version” vì thế thường là **dấu hiệu thiếu tương thích ở bộ đọc/transformer**, không phải bản thân Java source sai.

Trong Java Advance Compatibility Migration, hãy xác định class file major/minor, tìm chính xác parser đang được gọi, nâng thành phần sở hữu parser theo hỗ trợ chính thức, đồng bộ dependency và kiểm thử đầy đủ quá trình instrumentation, proxy, coverage và runtime. Giữ riêng các lớp **JDK chạy Gradle**, **compiler toolchain**, **JVM nạp class** và **bộ đọc bytecode** sẽ giúp tìm đúng nguyên nhân thay vì thay JDK hoặc hạ target một cách ngẫu nhiên.
