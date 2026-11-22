# Java 11 — Kiểm thử thư viện bytecode với class file hiện hành

**Chủ đề:** Java 11 → **Hằng số động** (`CONSTANT_Dynamic`, thường gọi *condy*). Bài học hướng dẫn kiểm thử một thư viện đọc, sinh hoặc biến đổi bytecode — ví dụ **ASM** — khi phải xử lý cả class file Java 11 có hằng số động và **class file của các JDK hiện hành**. Kiểm thử không dừng ở “`ClassReader` không ném exception”: phải giữ được cấu trúc, ý nghĩa và thuộc tính cần bảo toàn sau biến đổi, đồng thời phân biệt khả năng **đọc bytecode** với khả năng **JVM thực thi** bytecode đó.

**Special Note của module:** Chỉ lấy kiến thức **vẫn áp dụng hiện nay**, không sử dụng API incubator/lỗi thời. Các ví dụ được viết tương thích **Java 11**; một fixture class file của Java 27 được thư viện **phân tích nhưng không cố thực thi trên JDK cũ**. Phiên bản thư viện/định dạng được ghi rõ để có thể thay theo các bản phát hành sau này.

**Mục tiêu sau bài:** Bạn sẽ biết `CONSTANT_Dynamic` (tag 17) khác `CONSTANT_InvokeDynamic` (tag 18) ra sao; các mốc major/minor version; lập ma trận parse/inspect/round-trip/transform/verify/load/execute; dùng ASM 9.11.1 tạo và kiểm hằng số động trong class file 55; đọc class file 71 hiện hành; chạy ví dụ Java và JUnit; kiểm cấu hình Maven, bảo vệ trước dữ liệu bytecode không đáng tin và thiết lập CI đa phiên bản JDK.

## 1. Vì sao “class file hiện hành” là vấn đề của thư viện bytecode?

Một thư viện bytecode có thể được triển khai cho ứng dụng chạy trên Java 11 nhưng phải **phân tích artifact** do Java 17, 21, 25, 26 hoặc 27 tạo ra. Đây là hai chiều tương thích **khác nhau**:

- **Java runtime chạy thư viện:** JVM đang nạp `org.objectweb.asm.*`, chương trình kiểm thử và build tool. Một thư viện bytecode có thể được viết/biên dịch để chạy trên Java 11.
- **Định dạng class file mà thư viện đọc:** các byte đầu vào có `major_version` cao hơn. Thư viện cập nhật có thể **đọc class file mới** trên JVM cũ mà **không nạp class đó để chạy**.
- **Version của class file thư viện sinh:** `ClassWriter.visit(version, ...)` lựa chọn version output. Chọn version 71 không biến JVM 11 thành JVM 27.
- **Khả năng thực thi/verify:** JVM phải hỗ trợ class major/minor, các cấu trúc/bytecode và những API runtime mà class tham chiếu. Parse thành công chưa đủ.

Ví dụ đúng:

~~~text
JDK 11 + ASM phiên bản mới
    | đọc các bytes của class file major 71
    v
ClassReader: có thể hiểu và phân tích cấu trúc
    |
    +-- ClassWriter: có thể ghi class file major 71
    |
    +-- JVM 11 defineClass(major 71): KHÔNG thể chạy
    |
    +-- JVM 27 defineClass(major 71): có thể chạy nếu class hợp lệ,
                                      không dùng feature ngoài runtime đó
~~~

**Không** đánh đồng “thư viện hỗ trợ Java 27 class file” với “thư viện chỉ chạy được trên JDK 27”. Ngược lại, việc thư viện chạy được trên JDK 27 **không chứng minh** nó biết mọi cấu trúc mới xuất hiện trong class file 71.

Trong hệ thống thực, các thư viện này nằm dưới compiler plugin, coverage tool, Java agent, ORM, mocking framework, proxy generator, dependency scanner, obfuscator hoặc static-analysis tool. Một bản ASM cũ bị kéo vào qua dependency bắc cầu cũng có thể gây lỗi đọc class file mới, dù code ứng dụng tự thân vẫn biên dịch.

## 2. Hằng số động `CONSTANT_Dynamic` từ Java 11

JEP 309 đưa **Dynamic Class-File Constants** vào Java 11, tức class file **major 55**. Constant pool có một entry:

~~~text
CONSTANT_Dynamic_info {
    u1 tag;                         // 17
    u2 bootstrap_method_attr_index;
    u2 name_and_type_index;
}
~~~

Điểm quan trọng:

1. `tag = 17` cho biết đây là `CONSTANT_Dynamic`. Tag **18** là `CONSTANT_InvokeDynamic`, cơ chế liên quan nhưng dành cho **call site** của lệnh `invokedynamic`.
2. `name_and_type_index` của condy chỉ đến `CONSTANT_NameAndType` chứa **tên và field descriptor** như `Ljava/lang/String;` hoặc `I`; `invokedynamic` dùng **method descriptor** như `()Ljava/lang/String;`.
3. `bootstrap_method_attr_index` chỉ vào một entry của class-level `BootstrapMethods` attribute. Entry đó chứa `MethodHandle` đến bootstrap method và các static bootstrap arguments.
4. Lệnh `ldc`/`ldc_w` có thể lấy dynamic constant kiểu không phải `long/double`; `ldc2_w` phù hợp với dynamic constant có descriptor `J` hoặc `D`.
5. JVM **resolve dynamic constant khi được dùng**, không nhất thiết ngay khi đọc/nạp class. Bootstrap method có thể chạy, gây side effect hoặc báo lỗi tại thời điểm resolution.
6. JVM chọn kết quả resolution cho một dynamic constant trong runtime constant pool. Nếu bootstrap bị gọi cạnh tranh giữa nhiều thread, không được thiết kế assumption “bootstrap method chắc chắn chỉ thực thi đúng một lần” khi có race; kết quả được chọn/cached theo contract.
7. Dynamic constant có thể tham chiếu static bootstrap arguments khác, kể cả một dynamic constant lồng nhau; thư viện cần hỗ trợ đệ quy, kiểm tham chiếu và giới hạn tài nguyên.

Một lời gọi `ldc` tới `ConstantDynamic` **không phải** lời gọi Java thông thường tới `static final` field. Nó có metadata trong constant pool và JVM đi qua cơ chế bootstrap khi resolve. Tuy nhiên sau khi resolve, nó biểu thị một **giá trị hằng** cho entry đó trong runtime constant pool, không phải callback được gọi lại mỗi lần `ldc` chạy.

### 2.1. So sánh nhanh

| Thuộc tính | `CONSTANT_Dynamic` | `CONSTANT_InvokeDynamic` |
| --- | --- | --- |
| Constant pool tag | **17** | **18** |
| Bắt đầu được hỗ trợ | **class file 55 / Java 11** | **class file 51 / Java 7** |
| Entry đại diện | Giá trị hằng được tính qua bootstrap | Call site để gọi method handle động |
| NameAndType descriptor | **Field descriptor**, như `Ljava/lang/String;` | **Method descriptor**, như `()V` |
| Bytecode thường dùng | `ldc`, `ldc_w`, `ldc2_w` | `invokedynamic` |
| Kết quả bootstrap | Giá trị phù hợp type của constant | `CallSite` phù hợp method type |
| Kiểm thử bytecode | `ConstantDynamic` trong `visitLdcInsn` của ASM | `visitInvokeDynamicInsn` của ASM |

Nếu tool chỉ kiểm `visitInvokeDynamicInsn` để phát hiện “dynamic”, nó **sẽ bỏ sót condy**. Ngược lại, nhìn thấy lambda/`invokedynamic` trong class file không chứng minh có tag 17.

### 2.2. `BootstrapMethods` là phần bắt buộc của bài kiểm tra

Class có `CONSTANT_Dynamic` hoặc `CONSTANT_InvokeDynamic` cần `BootstrapMethods` attribute đúng cấu trúc. Nếu tool rewrite bytecode nhưng làm hỏng index, method handle hoặc static arguments, một `ClassReader` có thể vẫn trả kết quả ở mức nào đó nhưng JVM có thể không verify/link hoặc gặp lỗi khi resolve constant.

Kiểm thử phải quan sát ít nhất:

- Tên/descriptor của condy.
- Bootstrap method handle: owner, name, descriptor, invocation kind.
- Số lượng, thứ tự và kiểu bootstrap arguments; dynamic constants lồng nhau khi có.
- Sự tồn tại và tính hợp lệ của `BootstrapMethods` sau write.
- Vị trí `ldc` và kiểu stack/result tương thích với signature của method.
- Resolution khi **thực thi class file hợp lệ đã được tạo trong test**.

## 3. Class file version hiện hành tính đến tháng 11/2026

**Phân biệt JDK release với class file major.** Theo JVM Specification, class file có header bắt đầu bằng magic `0xCAFEBABE`, tiếp theo là `minor_version` và `major_version`. Một số mốc quan trọng:

| Java release | Major | Thực hành kiểm thử |
| --- | ---: | --- |
| Java 8 | **52** | Test backward compatibility nếu còn yêu cầu artifact Java 8; **không** chèn condy vào class 52. |
| Java 11 | **55** | Bản tối thiểu cho `CONSTANT_Dynamic` / JEP 309. |
| Java 17 | **61** | Một mốc JDK LTS thường được kiểm trong CI. |
| Java 21 | **65** | Một mốc JDK LTS thường được kiểm trong CI. |
| Java 25 | **69** | Bản phát hành tháng 9/2025. |
| Java 26 | **70** | Bản phát hành tháng 3/2026. |
| Java 27 | **71** | **Bản phát hành tháng 9/2026; major hiện hành tại thời điểm viết.** |

**Java 28 đang ở giai đoạn phát triển** khi viết bài, không phải bản Java SE GA hiện hành. ASM 9.11.1 có `Opcodes.V28` cho class file 72 theo tài liệu release, nhưng điều đó **không có nghĩa mọi preview feature của Java 28 đã được hỗ trợ**. Khi Java tiếp tục ra phiên bản mới, hãy đối chiếu **JVM Specification và release notes thư viện**, không dùng bảng lịch sử như một giới hạn vĩnh viễn.

### 3.1. Minor version và preview

- Header gồm `u4 magic; u2 minor_version; u2 major_version`, theo thứ tự **big-endian**.
- Với class file major **56 trở lên**, minor thông thường là **0** hoặc **65535**.
- `minor = 65535` đánh dấu class file phụ thuộc **preview features** của đúng Java release đó.
- Preview class file major `M` **không thể** được nạp trên JDK mới hơn chỉ bằng cách bật `--enable-preview` của JDK mới. Nó chỉ phù hợp JVM đúng release `M` và preview được bật.
- Do đó, test “thư viện đọc được 71.65535” và test “JDK 27 chạy được 71.65535” là **hai lớp**; một thư viện có thể parse bytes nhưng chưa hiểu preview semantics.

Không cố “sửa” một class preview bằng cách tự đổi minor 65535 thành 0. Thao tác đó có thể xóa dấu hiệu tương thích quan trọng mà **không** chuyển đổi feature sang cấu trúc hợp lệ.

### 3.2. Đọc header thủ công để chẩn đoán

~~~java
static int major(byte[] bytes) {
    if (bytes.length < 8 ||
        (bytes[0] & 255) != 0xCA ||
        (bytes[1] & 255) != 0xFE ||
        (bytes[2] & 255) != 0xBA ||
        (bytes[3] & 255) != 0xBE) {
        throw new IllegalArgumentException("Not a class file");
    }
    return (bytes[6] & 255) << 8 | (bytes[7] & 255);
}
~~~

Đây là **method Java độc lập ở mức logic**, không phải trình parser class file hoàn chỉnh. `bytes[4..5]` là minor; `bytes[6..7]` là major. `major` chỉ xác định **version header**, không chứng minh constant pool, methods, frames, attributes đều đúng. Không nạp class chưa tin cậy chỉ để “xem version”.

## 4. Bốn câu hỏi khác nhau khi nâng thư viện bytecode

| Câu hỏi | Cần kiểm tra | Ví dụ kết quả hợp lệ |
| --- | --- | --- |
| Runtime có chạy được **tool** không? | Java bytecode version của chính thư viện ASM/test app. | Tool build `--release 11` chạy trên JDK 11+. |
| Tool có **đọc** class mới không? | `ClassReader` hiểu major, constant tags, attributes. | ASM 9.11.1 đọc fixture major 71. |
| Tool có **rewrite** mà giữ nghĩa không? | ClassWriter, frames, attributes, condy/BootstrapMethods. | Class file 55 vẫn có `ConstantDynamic` sau round-trip. |
| JVM có **nạp/chạy** output không? | Runtime version, verifier, symbol resolution, bootstrap. | Java 11+ chạy class 55 hợp lệ; Java 11 không chạy class 71. |

Đừng thiết kế một test duy nhất `assertDoesNotThrow(new ClassReader(bytes))` rồi coi là hỗ trợ đầy đủ class file hiện hành. Một parser có thể đọc được header nhưng bỏ qua điều kiện ở later pass, bỏ mất attribute hoặc biến đổi frames sai.

**Nếu tool chỉ đọc để phân tích, bạn chưa cần execute** class file mới. **Nếu tool làm instrumentation/agent, việc chạy class đã biến đổi là bắt buộc** trên JVM có hỗ trợ target version.

## 5. Chọn thư viện ASM hiện hành thay cho bản đã lỗi thời

Ở thời điểm **07/11/2026**, bản ASM ổn định được công bố là **9.11.1** (17/10/2026). Release notes có các sửa lỗi/sửa regression và các thay đổi về kiểm soát tài nguyên khi xử lý class file. ASM 9.11 thêm nhận diện `V28` và những hardening liên quan `BootstrapMethods`, recursion, code length và analyzer.

Các module thường gặp:

| Artifact | Khi nào cần |
| --- | --- |
| `org.ow2.asm:asm` | `ClassReader`, `ClassWriter`, `ClassVisitor`, `MethodVisitor`, `ConstantDynamic`, `Handle`. |
| `org.ow2.asm:asm-tree` | Cần cấu trúc cây `ClassNode`/`MethodNode` để inspect/transform. |
| `org.ow2.asm:asm-util` | `CheckClassAdapter`, `TraceClassVisitor`, text diagnostics/ASMifier. |
| `org.ow2.asm:asm-analysis` | Phân tích frames, data-flow và một số dạng kiểm bytecode. |
| `org.ow2.asm:asm-commons` | Adapters và thao tác transform thuận tiện; có dependencies riêng. |

Giữ **cùng version** cho các ASM artifacts liên quan và dependency graph thực tế. Một công cụ có thể dùng ASM qua Byte Buddy, compiler plugin hoặc coverage agent; **nâng ASM trực tiếp không bảo đảm** shaded copy ẩn trong dependency khác cũng được nâng.

**Các thao tác kiểm dependency:**

~~~bash
mvn dependency:tree
mvn dependency:tree -Dincludes=org.ow2.asm
~~~

Nếu dùng Gradle, kiểm `dependencyInsight` cho từng cấu hình. Với Java agent hoặc fat JAR/shading, kiểm cả thư viện đã relocate, không chỉ Maven dependency tree. Không sử dụng `jdk.internal.org.objectweb.asm` của JDK làm API công khai: đây là package nội bộ, không ổn định theo Java 11→27.

### 5.1. Khi nào cần nâng ASM?

- Compiler/JDK mới bắt đầu sinh class major mà bản hiện tại chưa hỗ trợ.
- Có dạng attribute/constant pool/preview mới mà công cụ phải **hiểu và bảo toàn**.
- Release notes nêu lỗi verifier, writer, analyzer, recursion, crash, OOM hoặc hardening ảnh hưởng input của bạn.
- Tool gặp `IllegalArgumentException: Unsupported class file major version ...` khi phân tích artifact hợp lệ từ phiên bản mới.
- Có class file lạ do agent, obfuscator, Kotlin/Scala compiler, generator hoặc Java toolchain tạo.

**Chỉ nâng dependency sau khi chạy lại ma trận kiểm thử.** Không coi “version càng mới” đồng nghĩa output transform luôn chính xác nếu adapter hoặc plugin của chính bạn còn gọi API theo contract cũ.

## 6. Cấu hình Maven minh họa, target Java 11

Ví dụ một project độc lập có hai file Java ở dưới cùng: source demo trong `src/main/java/CondyCompatibilityDemo.java`, tests trong `src/test/java/CondyCompatibilityDemoTest.java`. Maven config dùng `--release 11`, ASM 9.11.1 và JUnit Jupiter 5.13.4 (một bản JUnit 5 phù hợp Java 11). Với Maven/CI thật, quản lý versions tập trung và cập nhật dependency theo chính sách của tổ chức.

**Tệp `pom.xml`:**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
         https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>example</groupId>
  <artifactId>condy-compatibility-test</artifactId>
  <version>1.0.0</version>
  <properties>
    <maven.compiler.release>11</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>
  <dependencies>
    <dependency>
      <groupId>org.ow2.asm</groupId>
      <artifactId>asm</artifactId>
      <version>9.11.1</version>
    </dependency>
    <dependency>
      <groupId>org.junit.jupiter</groupId>
      <artifactId>junit-jupiter</artifactId>
      <version>5.13.4</version>
      <scope>test</scope>
    </dependency>
  </dependencies>
  <build>
    <plugins>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-compiler-plugin</artifactId>
        <version>3.14.1</version>
      </plugin>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-surefire-plugin</artifactId>
        <version>3.5.4</version>
      </plugin>
    </plugins>
  </build>
</project>
~~~

Đây là **POM có thể dùng để chạy demo và JUnit** khi có Maven, mạng/tập dependency đã cache và JDK phù hợp. Maven/JUnit không nằm sẵn trong Java SE. `maven.compiler.release=11` bảo đảm project source/class target 11; ASM vẫn được quyền **sinh bytes của class major 71 trong bộ nhớ** để parser kiểm tra.

Cấu hình sau không bao gồm toàn bộ các plugin production (coverage, lint, repository mirror, checksum enforcement). Nếu dùng repository mirror hoặc môi trường offline, tải/cấp đúng artifact qua quy trình nội bộ trước khi chạy.

## 7. Chương trình Java 11 hoàn chỉnh: sinh condy, round-trip và đọc class file 71

Demo này có **hai fixture khác nhau**:

- **`CondyFixture` major 55**: do ASM tạo với một `CONSTANT_Dynamic` tên `ticket`, descriptor `Ljava/lang/String;` và bootstrap method trong class demo. Nó được kiểm parse, round-trip và **thực thi** trên JVM hiện đang chạy (nếu JVM hỗ trợ Java 11).
- **`ModernClassFileFixture` major 71**: do ASM 9.11.1 tạo với một method static `number()` trả 7, **chỉ parse và round-trip** trong demo. Không cố `defineClass` trên JVM 11/17/21/24 vì JVM đó không hỗ trợ major 71.

Trong fixture condy, một method có bytecode `ldc dynamicConstant; areturn`. Bootstrap trả `"value:ticket"` và đếm số lượt gọi. Chương trình dùng hai class loaders khác nhau để định nghĩa **hai class độc lập nhưng cùng tên**, sau đó gọi mỗi class hai lần; kết quả bootstrap lần đầu của mỗi class được cache, tổng đếm trong đường thực thi đã thử là 2.

**Tệp `CondyCompatibilityDemo.java`:**

~~~java
import java.lang.invoke.MethodHandles;
import java.lang.reflect.Method;
import java.util.concurrent.atomic.AtomicInteger;
import org.objectweb.asm.ClassReader;
import org.objectweb.asm.ClassVisitor;
import org.objectweb.asm.ClassWriter;
import org.objectweb.asm.ConstantDynamic;
import org.objectweb.asm.Handle;
import org.objectweb.asm.MethodVisitor;
import org.objectweb.asm.Opcodes;

public final class CondyCompatibilityDemo {
    private static final AtomicInteger BOOTSTRAP_CALLS =
        new AtomicInteger();

    private CondyCompatibilityDemo() {}

    public static String bootstrap(MethodHandles.Lookup lookup,
            String name, Class<?> type) {
        if (!"ticket".equals(name) || type != String.class) {
            throw new IllegalArgumentException("Unexpected condy");
        }
        BOOTSTRAP_CALLS.incrementAndGet();
        return "value:" + name;
    }

    static byte[] makeCondy() {
        ClassWriter writer = new ClassWriter(0);
        writer.visit(Opcodes.V11,
            Opcodes.ACC_PUBLIC | Opcodes.ACC_SUPER,
            "CondyFixture", null, "java/lang/Object", null);

        Handle bootstrap = new Handle(
            Opcodes.H_INVOKESTATIC,
            "CondyCompatibilityDemo",
            "bootstrap",
            "(Ljava/lang/invoke/MethodHandles$Lookup;" +
            "Ljava/lang/String;Ljava/lang/Class;)Ljava/lang/String;",
            false);
        ConstantDynamic value = new ConstantDynamic(
            "ticket", "Ljava/lang/String;", bootstrap);

        MethodVisitor method = writer.visitMethod(
            Opcodes.ACC_PUBLIC | Opcodes.ACC_STATIC,
            "value", "()Ljava/lang/String;", null, null);
        method.visitCode();
        method.visitLdcInsn(value);
        method.visitInsn(Opcodes.ARETURN);
        method.visitMaxs(1, 0);
        method.visitEnd();
        writer.visitEnd();
        return writer.toByteArray();
    }

    static byte[] makeCurrentVersionFixture() {
        ClassWriter writer = new ClassWriter(0);
        writer.visit(Opcodes.V27,
            Opcodes.ACC_PUBLIC | Opcodes.ACC_SUPER,
            "ModernClassFileFixture", null, "java/lang/Object", null);
        MethodVisitor m = writer.visitMethod(
            Opcodes.ACC_PUBLIC | Opcodes.ACC_STATIC,
            "number", "()I", null, null);
        m.visitCode();
        m.visitIntInsn(Opcodes.BIPUSH, 7);
        m.visitInsn(Opcodes.IRETURN);
        m.visitMaxs(1, 0);
        m.visitEnd();
        writer.visitEnd();
        return writer.toByteArray();
    }

    static int major(byte[] bytes) {
        if (bytes.length < 8
                || (bytes[0] & 255) != 0xca
                || (bytes[1] & 255) != 0xfe
                || (bytes[2] & 255) != 0xba
                || (bytes[3] & 255) != 0xbe) {
            throw new IllegalArgumentException("Not a class file");
        }
        return (bytes[6] & 255) << 8 | (bytes[7] & 255);
    }

    static int countDynamicLdc(byte[] bytes) {
        final int[] found = {0};
        new ClassReader(bytes).accept(
            new ClassVisitor(Opcodes.ASM9) {
                @Override
                public MethodVisitor visitMethod(
                        int access, String name, String desc,
                        String signature, String[] exceptions) {
                    return new MethodVisitor(Opcodes.ASM9) {
                        @Override
                        public void visitLdcInsn(Object value) {
                            if (value instanceof ConstantDynamic) {
                                found[0]++;
                            }
                        }
                    };
                }
            },
            ClassReader.SKIP_DEBUG | ClassReader.SKIP_FRAMES);
        return found[0];
    }

    static byte[] roundTrip(byte[] source) {
        ClassWriter writer = new ClassWriter(0);
        new ClassReader(source).accept(writer, 0);
        return writer.toByteArray();
    }

    static final class FixtureLoader extends ClassLoader {
        FixtureLoader() {
            super(CondyCompatibilityDemo.class.getClassLoader());
        }
        Class<?> defineFixture(byte[] bytes) {
            return defineClass("CondyFixture", bytes, 0, bytes.length);
        }
    }

    static String runTrustedCondy(byte[] bytes) throws Exception {
        Class<?> fixture = new FixtureLoader().defineFixture(bytes);
        Method method = fixture.getMethod("value");
        String first = (String) method.invoke(null);
        String second = (String) method.invoke(null);
        if (!first.equals(second)) {
            throw new AssertionError("Condy changed within class");
        }
        return first;
    }

    public static void main(String[] args) throws Exception {
        byte[] oldClass = makeCondy();
        byte[] oldRoundTrip = roundTrip(oldClass);
        byte[] modern = makeCurrentVersionFixture();
        byte[] modernRoundTrip = roundTrip(modern);

        if (major(oldClass) != 55
                || countDynamicLdc(oldClass) != 1
                || countDynamicLdc(oldRoundTrip) != 1
                || major(modern) != 71
                || major(modernRoundTrip) != 71
                || !"ModernClassFileFixture".equals(
                    new ClassReader(modernRoundTrip).getClassName())) {
            throw new AssertionError("Bytecode compatibility failed");
        }

        String first = runTrustedCondy(oldClass);
        String second = runTrustedCondy(oldRoundTrip);
        if (!"value:ticket".equals(first)
                || !first.equals(second)
                || BOOTSTRAP_CALLS.get() != 2) {
            throw new AssertionError("Condy resolution failed");
        }

        System.out.println("condy.major=" + major(oldClass));
        System.out.println("condy.ldc.dynamic=" +
            countDynamicLdc(oldClass));
        System.out.println("condy.roundtrip.ldc.dynamic=" +
            countDynamicLdc(oldRoundTrip));
        System.out.println("condy.result=" + first);
        System.out.println("condy.bootstrap.calls=" +
            BOOTSTRAP_CALLS.get());
        System.out.println("current.major=" + major(modern));
        System.out.println("current.reader.name=" +
            new ClassReader(modernRoundTrip).getClassName());
        System.out.println("current.roundtrip.major=" +
            major(modernRoundTrip));
        System.out.println(
            "current.execution=SKIPPED_REQUIRES_JDK_27");
    }
}
~~~

**Lệnh với Maven project ở mục 6:**

~~~bash
mvn -q test
# Khi chỉ muốn chạy main và đã có classpath đầy đủ của ASM:
# Linux/macOS: java -cp "target/classes:/path/to/asm-9.11.1.jar" CondyCompatibilityDemo
# Windows:     java -cp "target/classes;C:\path\to\asm-9.11.1.jar" CondyCompatibilityDemo
~~~

Nếu muốn chạy trực tiếp không tạo Maven project, tải ASM 9.11.1 về một thư mục thư viện hợp lệ rồi:

~~~bash
# Linux/macOS
javac --release 11 -cp "lib/asm-9.11.1.jar" CondyCompatibilityDemo.java
java -cp ".:lib/asm-9.11.1.jar" CondyCompatibilityDemo
~~~

Trên Windows, thay dấu `:` phân cách classpath bằng `;`:

~~~powershell
javac --release 11 -cp "lib\asm-9.11.1.jar" CondyCompatibilityDemo.java
java -cp ".;lib\asm-9.11.1.jar" CondyCompatibilityDemo
~~~

**Stdout đã kiểm chứng với ASM 9.11.1:**

~~~text
condy.major=55
condy.ldc.dynamic=1
condy.roundtrip.ldc.dynamic=1
condy.result=value:ticket
condy.bootstrap.calls=2
current.major=71
current.reader.name=ModernClassFileFixture
current.roundtrip.major=71
current.execution=SKIPPED_REQUIRES_JDK_27
~~~

Chương trình đã được biên dịch bằng `javac --release 11` và thực thi thành công trên **JDK 24** có ASM 9.11.1. `--release 11` xác minh source/API/bytecode của **demo** tương thích target Java 11; máy thử hiện có JDK 24 nên **chưa xác nhận trực tiếp main trên JVM Java 11 hoặc việc execute fixture 71 trên JDK 27**. Hai trường hợp runtime riêng phải thuộc ma trận CI tương ứng.

### 7.1. Tại sao `condy.bootstrap.calls=2`?

- `oldClass` và `oldRoundTrip` có cùng tên logic `CondyFixture` nhưng được định nghĩa bằng **hai class loader khác nhau**, nên là hai class runtime riêng.
- Mỗi class có một `CONSTANT_Dynamic` được tham chiếu từ method `value()`. Trong đường thực thi tuần tự này, hai lần gọi `value()` trên cùng class dùng cùng kết quả resolution.
- Do đó counter toàn cục ở bootstrap tăng một lần cho mỗi class; tổng **2**.
- Nếu thiết kế test nhiều thread đồng thời resolve cùng condy, đừng assert bootstrap callback vật lý chỉ chạy duy nhất một lần; JVM có thể cho nhiều thread chạy bootstrap cạnh tranh và chỉ chọn một kết quả.

### 7.2. Tại sao chỉ scan bằng `SKIP_FRAMES` trong `countDynamicLdc`?

`countDynamicLdc` chỉ cần **quan sát `visitLdcInsn`**, không phân tích control-flow hay rewrite class. Bỏ debug/frames khi scan tiết kiệm thao tác. **Không copy tùy tiện flag `SKIP_FRAMES` vào pipeline transform**: nếu bạn thay method control flow rồi ghi lại mà không bảo toàn/recompute StackMapTable chính xác, JVM có thể ném `VerifyError`. Trong `roundTrip` demo, `ClassReader.accept(writer, 0)` giữ dữ liệu mà writer cần cho round-trip đơn giản.

### 7.3. Vì sao dùng `Opcodes.V11` và `Opcodes.V27`?

`Opcodes.V11` tạo header **major 55**, nơi tag 17 được phép. `Opcodes.V27` tạo header **major 71**, phù hợp Java 27. ASM 9.11.1 hỗ trợ viết/đọc class file version này mà code điều phối `CondyCompatibilityDemo` vẫn được compile target 11. **Tạo bytes major 71 khác với thực thi chúng.**

Fixture class 71 rất đơn giản: nó **không dùng tính năng ngôn ngữ độc quyền của Java 27**, ngoài việc gắn major 71. Đây là test header/parser/round-trip, **không phải bằng chứng công cụ đã hiểu toàn bộ các attributes mới, preview features hoặc bytecode phức tạp của Java 27**. Cần thêm corpus thực tế.

## 8. JUnit Jupiter: ba test có thể chạy không cần Internet sau khi tải dependencies

Đặt class dưới đây ở `src/test/java/CondyCompatibilityDemoTest.java` (cùng default package với demo). Nó kiểm:

1. Condy tồn tại trước/sau rewrite và giá trị bootstrap vẫn chạy đúng.
2. Parser đọc/ghi được class major 71 mà **không** load class đó trên JDK cũ.
3. Header sai magic bị từ chối bởi validation của chương trình, không âm thầm coi input là class hợp lệ.

~~~java
import org.junit.jupiter.api.Test;
import org.objectweb.asm.ClassReader;
import static org.junit.jupiter.api.Assertions.*;

class CondyCompatibilityDemoTest {
    @Test
    void condyPreservedByReadWriteRoundTrip() {
        byte[] source = CondyCompatibilityDemo.makeCondy();
        byte[] copied = CondyCompatibilityDemo.roundTrip(source);
        assertEquals(55, CondyCompatibilityDemo.major(source));
        assertEquals(1,
            CondyCompatibilityDemo.countDynamicLdc(source));
        assertEquals(1,
            CondyCompatibilityDemo.countDynamicLdc(copied));
        assertEquals("value:ticket",
            assertDoesNotThrow(() ->
                CondyCompatibilityDemo.runTrustedCondy(copied)));
    }

    @Test
    void parserUnderstandsCurrentJava27ClassFileWithoutLoadingIt() {
        byte[] modern =
            CondyCompatibilityDemo.makeCurrentVersionFixture();
        byte[] copied = CondyCompatibilityDemo.roundTrip(modern);
        assertEquals(71, CondyCompatibilityDemo.major(modern));
        assertEquals(71, CondyCompatibilityDemo.major(copied));
        assertEquals("ModernClassFileFixture",
            new ClassReader(copied).getClassName());
    }

    @Test
    void badMagicRejectedByOurValidation() {
        byte[] damaged = CondyCompatibilityDemo.makeCondy();
        damaged[0] = 0;
        assertThrows(IllegalArgumentException.class,
            () -> CondyCompatibilityDemo.major(damaged));
    }
}
~~~

Lệnh:

~~~bash
mvn -q test
~~~

**Kết quả đã kiểm chứng qua Surefire report trong môi trường thử:**

~~~text
Tests run: 3
Failures: 0
Errors: 0
Skipped: 0
~~~

Báo cáo JUnit/Surefire có thể có định dạng log khác nhau theo phiên bản; **các con số test mới là điều cần assert**. Bộ test này thực sự đã được biên dịch/chạy trong một Maven project tạm, độc lập với repository chính. Khi bổ sung thêm test mới, con số sẽ thay đổi.

**Giới hạn của bộ này:** chưa có các case malformed `BootstrapMethods`, preview, JVM Java 11 thực tế, ClassWriter frame recomputation, các attributes mới của Java 27, nhiều toolchain khác nhau hoặc stress/fuzz. Đó là nhiệm vụ của các lớp test ở phần tiếp theo, không được “suy luận pass” từ 3 unit tests.

## 9. Thứ tự các tầng QA nên áp dụng

Đối với bất kỳ tool đọc/biến đổi bytecode nào, hãy tách các tầng:

| Tầng | Hành động | Phát hiện |
| --- | --- | --- |
| **1. Header** | Kiểm magic, minor/major, length và byte budget. | File không phải class, version ngoài phạm vi. |
| **2. Parse** | `new ClassReader(bytes)` rồi `accept(visitor, ...)`. | Unknown tag, lỗi cấu trúc, unsupported class major. |
| **3. Semantic inspect** | Ghi lại name, super, interfaces, methods, code, condy và attributes. | Mất tag 17, sai descriptor/handle/metadata. |
| **4. Round-trip** | `ClassReader → ClassWriter → ClassReader`. | Mất cấu trúc sau lần ghi lại. |
| **5. Transform** | Áp dụng instrumentation thực; kiểm output. | Sai stack effects, frames, bootstrap references. |
| **6. Static verifier** | ASM `CheckClassAdapter`/analysis phù hợp. | Một số lỗi bytecode, stack/local/frame. |
| **7. JVM load/verify** | `defineClass` **chỉ với fixture tin cậy** trên JVM đúng version. | `ClassFormatError`, `VerifyError`, `UnsupportedClassVersionError`. |
| **8. Execution** | Gọi method, resolve condy, đo kết quả/side effects. | `BootstrapMethodError`, sai giá trị hoặc lỗi runtime. |
| **9. CI matrix** | Chạy các tầng phù hợp trên nhiều JDK/toolchain. | Regression ở JDK hoặc generator cụ thể. |

Không được “skip silently” các case không chạy được. Ghi rõ `PARSE_PASS`, `ROUNDTRIP_PASS`, `EXECUTION_SKIPPED_UNSUPPORTED_JVM` hoặc `EXECUTION_FAIL` thay vì một boolean `supported=true` không có ngữ cảnh.

## 10. Test corpus phải có cả class thật, không chỉ fixture tự sinh

Fixture sinh bằng cùng thư viện đang được kiểm là **smoke test**, không chứng minh interoperability với compiler hoặc producer khác. Nên duy trì corpus có nguồn gốc và build recipe rõ:

- Class do `javac --release 11` tạo từ nguồn bình thường; conformance cho major 55.
- Class condy do ASM generator được giữ cố định, có bootstrap args và method `ldc` đã xác nhận.
- Class Java 17/21/25/26/27 từ `javac` của **đúng toolchain** khi có JDK được cấp phép, không giả major bằng cách sửa header rồi coi là class compiler thật.
- Artifact do Kotlin, Scala, Groovy hoặc một bytecode library khác sinh ra **nếu thật sự nằm trong sản phẩm**.
- Class có `invokedynamic`, method handles, annotations, generic signatures, module metadata, nestmates, records, permitted subclasses và các attributes phù hợp version.
- Class preview từ đúng JDK/version trong suite tách biệt, chỉ khi sản phẩm chủ động hỗ trợ preview.
- Class được instrumentation thật bởi agent/coverage/mock framework ở các bản được dùng.
- Class có constant pool lớn, nhiều methods, nested condy, nhiều bootstrap args và các edge cases của frames/exception tables.
- Corpus negative: truncated constant pool, index không hợp lệ, thiếu/đứt `BootstrapMethods`, max length vượt giới hạn, version không hỗ trợ, malformed descriptors, bootstrap throw và input lồng sâu.

**Mỗi fixture nên lưu:** nguồn tạo, JDK/compiler version, compiler flags, SHA-256, major/minor, expected traits và lý do tồn tại. Không dựa vào tên tệp “Java27.class” như bằng chứng version; đọc header mới đúng.

### 10.1. Đừng chỉ so bytes trước/sau round-trip

ClassWriter có thể thay đổi **thứ tự constant pool**, indexes, layout của attributes hoặc representations mà vẫn giữ semantics. `assertArrayEquals(input, output)` là một test **binary reproducibility** hữu ích nếu sản phẩm yêu cầu, nhưng **không phải điều kiện chung** để một round-trip hợp lệ.

Ưu tiên assert semantic invariants:

~~~text
Input:
  major = 55, class = CondyFixture
  method value()Ljava/lang/String;
  LDC(ConstantDynamic name="ticket", desc="Ljava/lang/String;")
  bootstrap owner/method/descriptor

Output:
  major = 55, class = CondyFixture
  cùng method signature và type semantics
  vẫn có cùng condy và bootstrap contract
  nạp/verify/chạy đúng trên JVM 11+
~~~

Cũng đừng chỉ so tên/major mà quên **behavior**: hai class có cùng metadata cơ bản vẫn có thể trả dữ liệu sai hoặc ném lỗi khi bootstrap resolve.

## 11. Nâng độ khó: malformed condy và negative tests

Một số trường hợp cần test riêng (không có trong demo ngắn):

| Input | Hành vi kỳ vọng của tool/test |
| --- | --- |
| `CONSTANT_Dynamic` trong class file major **54** | Class không phù hợp định dạng; không tự tuyên bố hợp lệ chỉ vì parser đọc được bytes. |
| `CONSTANT_Dynamic` có field descriptor sai | Từ chối/đánh dấu invalid, JVM verification/link sẽ không hợp lệ. |
| Bootstrap method index ngoài bảng `BootstrapMethods` | Phát hiện class malformed. |
| Bootstrap handle/symbol không truy cập được | JVM có thể báo lỗi link/resolution; không biến thành success giả. |
| Bootstrap trả giá trị sai type | Error khi resolve; giữ cause và tên constant, không in secrets. |
| Bootstrap throw exception | Có thể dẫn đến `BootstrapMethodError` theo quy tắc linkage; test không phụ thuộc message cụ thể. |
| Dynamic constant lồng nhau theo chu trình | Có quy tắc lỗi resolution; tool phải có giới hạn recursion và xử lý an toàn. |
| Truncated class bytes hoặc độ dài attribute giả | Parser phải reject trong byte/resource budget. |
| Major cao hơn thư viện hỗ trợ | Fail rõ: unsupported class version, không “sửa” major xuống cho qua. |
| Minor `65535` của preview từ release khác | Không cố load bằng JVM bất kỳ/preview của release mới hơn. |

**Lưu ý loại exception:** `ClassReader` là một thư viện parser, trong khi `ClassFormatError`, `VerifyError`, `BootstrapMethodError` và `UnsupportedClassVersionError` phát sinh tại các giai đoạn JVM khác. Không assert một exception class từ `ClassReader` cho mọi input có thể khiến JVM từ chối ở giai đoạn khác.

### 11.1. Không tự “fix” class file bằng cách đổi major header

Đổi hai bytes major từ 71 thành 55 có thể khiến một class trông như target Java 11 nhưng vẫn chứa constant tags, attributes, method descriptors hoặc bytecode không được phép ở version 55. **Đây không phải backport hay cross-compile**. Nếu cần tương thích JDK11, compiler/generator phải thật sự tạo class theo JVM spec target11, thay thế API runtime mới, biến đổi cấu trúc hợp lệ và chạy test trên JVM11.

### 11.2. Binary fuzzing khác class fixture có chủ đích

Các negative tests có thể mutate một byte trong class file hoặc tạo length sai để kiểm parser; nhưng đó là **input malformed có chủ đích**, không dùng làm oracle semantic của class hợp lệ. Hãy đặt timeout, memory budget, recursion limits và isolate fuzz worker để tránh test tự biến thành denial-of-service cho CI.

## 12. Đọc/ghi frames đúng khi instrument code

Đối với tool sửa method, **StackMapTable** và control-flow graph đặc biệt quan trọng. Lỗi thường gặp:

- Insert instruction hoặc thêm nhánh nhưng không cập nhật `max_stack`, `max_locals` và frames.
- Bỏ `StackMapTable` khi class được verify theo class version hiện đại.
- Dùng `ClassReader.SKIP_FRAMES` trong đường transform mà không có chiến lược tính lại frames.
- Dùng `ClassWriter.COMPUTE_FRAMES` mà class loader không tìm được dependencies của class đang phân tích.
- Remap tên class/interface/descriptor nhưng bỏ sót `ConstantDynamic` bootstrap handle, method types hoặc nested args.
- Sửa method bytecode nhưng giữ signature/exception table không còn hợp lệ.

**Chiến lược:** Với transform giữ nguyên control flow, dùng visitor phù hợp để bảo toàn frames/attributes. Với transform thay control flow, xây pipeline có tính lại frames, test `CheckClassAdapter` và load trên JVM đích. Nếu dùng `COMPUTE_FRAMES`, cân nhắc cách resolve common superclass trong ClassWriter: không để việc phân tích class input dẫn tới **tự động nạp/chạy class không đáng tin** trong JVM sản phẩm.

**ASM verification:** `asm-util` cung cấp `CheckClassAdapter`; một số chế độ dựa trên `asm-tree`/`asm-analysis`. Khi muốn dùng chúng, khai báo đúng module, version đồng bộ, và kiểm kết quả bằng JVM thực tế. **CheckClassAdapter pass ≠ JVM chạy được** — nó là một lớp phòng vệ, không thay thế verifier và execution test.

## 13. Những vấn đề khi instrument thư viện có condy

Khi viết transformer, visitor phải xử lý được:

- `visitLdcInsn(Object value)` với `value instanceof ConstantDynamic`, không mặc định mọi `LDC` chỉ chứa `String`, `Integer`, `Type` hoặc `Handle`.
- `ConstantDynamic.getName()` và `getDescriptor()`; field descriptor có thể là primitive hoặc reference hợp lệ.
- `getBootstrapMethod()` và `getBootstrapMethodArgumentCount()/getBootstrapMethodArgument(i)`; arguments có thể chứa giá trị loadable khác, kể cả condy lồng.
- Chuyển đổi owner/descriptor của bootstrap handle khi rename packages/classes.
- Đảm bảo bootstrap owner/method tồn tại, accessible trong module/class loader đúng ngữ cảnh.
- Giữ class version thích hợp: tag 17 không hợp lệ cho output major 52 hoặc 54.
- Kiểm error path khi bootstrap resolve muộn, không chỉ khi visitor parse xong.

Ví dụ một inspector **minh họa** trong `MethodVisitor`:

~~~java
@Override
public void visitLdcInsn(Object value) {
    if (value instanceof ConstantDynamic) {
        ConstantDynamic d = (ConstantDynamic) value;
        System.out.println(d.getName() + " : " +
            d.getDescriptor());
        Handle handle = d.getBootstrapMethod();
        System.out.println(handle.getOwner() +
            "." + handle.getName());
        for (int i = 0;
             i < d.getBootstrapMethodArgumentCount(); i++) {
            Object arg = d.getBootstrapMethodArgument(i);
            inspectArgWithDepthLimit(arg);
        }
    }
    super.visitLdcInsn(value);
}
~~~

Đây là **đoạn minh họa**, không phải chương trình độc lập; `inspectArgWithDepthLimit` phải do ứng dụng cài đặt với **depth/node budget**. `ConstantDynamic` có thể lồng nhau; không gọi đệ quy không giới hạn khi input không đáng tin. Khi code được đặt trực tiếp trong `MethodVisitor` không có delegate, `super.visitLdcInsn` có thể chỉ chuyển tiếp nếu visitor được cấu hình delegate thích hợp.

## 14. API Class-File của JDK mới và bài học Java 11

Ngoài ASM, các bản JDK mới có **API class-file chuẩn** ở `java.lang.classfile`. Đây là một lựa chọn hiện đại đáng đánh giá trong những module chạy trên JDK hỗ trợ tương ứng; **nó không tồn tại trong Java 11**. Vì bài học target Java 11, ví dụ dùng ASM thay vì `java.lang.classfile.ClassFile`.

**Cách quyết định:**

- Nếu **runtime phải là Java 11**, dùng thư viện bytecode tương thích Java 11 (chẳng hạn ASM phiên bản còn được duy trì) và kiểm class-file major riêng.
- Nếu nâng **runtime/build tooling** lên JDK mới, có thể đánh giá `java.lang.classfile` để parse/transform nếu API và tính năng của nó đáp ứng; vẫn phải test output/semantic invariants.
- Không import `java.lang.classfile` vào source `--release 11`: compile sẽ fail vì API không thuộc target.
- Không nhầm API class file của JDK mới với khả năng JVM cũ thực thi class major mới. **Parser API và JVM supported bytecode là hai việc khác**.

Nếu tool của bạn có plugin chạy trên JDK11 nhưng phân tích artifact JDK27, lựa chọn phổ biến vẫn là một **user-space library** đủ mới và kiểm chất lượng security/compatibility theo từng release.

## 15. Ma trận CI khuyến nghị

Thay vì “một job `mvn test` trên một JDK là đủ”, tách kiểm thử theo **runtime** và **định dạng input/output**:

| Test suite | JDK chạy test | Fixture | Kỳ vọng |
| --- | --- | --- | --- |
| Core condy parse/rewrite | 11 | major 55 | PASS; đọc và bảo toàn `ConstantDynamic`. |
| Core condy execute | 11 | major 55 | PASS nếu bootstrap/bytecode/API chỉ dùng Java 11. |
| Core condy execute | 17, 21, 25, 27 | major 55 | PASS, theo phiên bản đích có trong CI. |
| Current parser | 11 hoặc 17/21 | major 71 | PASS **parse/inspect/round-trip** bằng ASM đủ mới, không defineClass. |
| Current execute | 27 | major 71 | PASS nếu fixture hợp lệ và thuộc feature JVM27 hỗ trợ. |
| Preview class test | Đúng release tạo preview | minor 65535 | Chỉ chạy khi preview được bật và tool có hỗ trợ. |
| Plugin transform | JVM runtime sản phẩm | Corpus compiler/agent thực tế | Không làm hỏng frames, attrs, condy, symbols. |
| Negative/fuzz | Môi trường cô lập có budget | Malformed input | Reject có kiểm soát, không treo/OOM. |

Với bộ test JUnit của bài, `mvn test` trên JDK11 có thể kiểm việc **parse major71** bằng ASM nhưng **không** thực thi fixture đó. Khi thêm JDK27 job, viết test load fixture 71 ở **JDK27**; không thêm điều kiện `if (currentJdk<27) return;` rồi báo toàn bộ bài test đã chạy. Nếu skip có chủ đích, dùng JUnit `Assumptions.assumeTrue(Runtime.version().feature() >= 27)` hoặc job riêng với báo cáo SKIPPED rõ ràng.

**Tối thiểu nên lưu report:** tested JDK vendor/version, ASM version, input major/minor, parser result, rewrite result, verifier result, load/execute result và link tới fixture/stacktrace đã lọc. Nếu tool nhận nhiều class files, ghi số files qua mỗi phase nhưng không log raw bytecode nhạy cảm.

## 16. Test runtime 27 phải là một job riêng

Trên một JVM JDK27, có thể định nghĩa một fixture major71 **do test tự sinh tin cậy** và gọi method static `number()` trả 7. Việc này phải thực hiện **chỉ sau khi** xác nhận runtime đúng JDK27 hoặc cao hơn phù hợp với class target. Một mẫu minh họa cho test riêng:

~~~java
if (Runtime.version().feature() < 27) {
    throw new IllegalStateException(
        "This execution test requires JDK 27");
}

byte[] bytes = CondyCompatibilityDemo.makeCurrentVersionFixture();
ClassLoader isolated = new ClassLoader(
    CondyCompatibilityDemo.class.getClassLoader()) {
    // Một helper defineClass phải được cung cấp bởi test loader.
};
// Dùng helper ClassLoader.defineClass ở class test của bạn,
// sau đó reflection gọi ModernClassFileFixture.number() và assert 7.
~~~

**Đây là phác thảo, không phải chương trình độc lập**. Mục đích là chỉ ra điều kiện môi trường và phép assert cần thực hiện; **không** gọi thẳng `ClassLoader.defineClass` từ code ngoài subclass. Khi phát triển test này, xây một `FixtureLoader` có method định nghĩa class tên `ModernClassFileFixture` tương tự mục 7, và chỉ chạy ở JDK27.

**Không** dùng header trick để thử ép JVM24 chạy major71. Nó phải ném `UnsupportedClassVersionError` và đó là hành vi đúng.

## 17. Đọc class thực tế bằng các công cụ bổ trợ

`javap -v` trên một JDK đủ mới giúp nhìn thấy version, constant pool, `BootstrapMethods` và bytecode:

~~~bash
javap -v -p -classpath target/classes YourClass
~~~

Với class fixture sinh động **trong bộ nhớ** (như `CondyFixture` của demo), có thể tạm lưu nó vào thư mục test để xem với `javap`:

~~~java
java.nio.file.Files.write(
    java.nio.file.Paths.get("CondyFixture.class"),
    CondyCompatibilityDemo.makeCondy());
~~~

Đây là **đoạn minh họa**; nên đặt trong test được cấp quyền ghi tệp, không trong code production tự ghi bytecode ra thư mục chạy. Các điểm cần tìm khi kiểm bằng `javap -v`:

~~~text
major version: 55
Constant pool: ... Dynamic ... #bootstrap_index ... ticket:Ljava/lang/String;
BootstrapMethods: ... CondyCompatibilityDemo.bootstrap ...
Code: ldc ...; areturn
~~~

Hình thức dòng/constant indexes do `javap` quyết định, không nên assert đúng số index khi không cần. Nếu dùng `javap` cũ cho class version mới hơn, tool có thể không hiểu mọi đặc tính. Dùng **JDK tương ứng class target** cho kiểm sâu, không dựa duy nhất vào một lệnh `javap` cũ.

### 17.1. Dấu vết nên đo khi tool lỗi

- Major/minor và runtime Java feature version.
- ASM / Byte Buddy / agent plugin version hiệu lực, không chỉ dependency bạn khai.
- Class name (đã lọc), source artifact, SHA-256 và build tool/compilation flags.
- Phase đang lỗi: parser, writer, verifier, defineClass, bootstrap resolution, execution.
- Field descriptor, bootstrap handle owner/name và error category **không nhạy cảm**.
- Nếu có `BootstrapMethodError`, cause chain ở log nội bộ có kiểm soát.

Tránh log toàn bộ class bytes của sản phẩm nếu có chứa literal/token, key, thông tin nội bộ hoặc source nhạy cảm.

## 18. Bảo mật khi nhận bytecode không tin cậy

Một class file là **binary input do bên ngoài cung cấp** nếu thư viện quét plugin, uploaded JAR hoặc dependency không đáng tin. Đọc class bằng parser có thể làm lộ bug về resource exhaustion, invalid length, recursion hoặc memory allocation. **Load/execute class là rủi ro lớn hơn nhiều**: Java không cung cấp một sandbox bảo mật chung đáng tin cậy chỉ vì bạn tạo `ClassLoader` khác.

Khuyến nghị:

1. Đặt **giới hạn kích thước file/JAR, số entry, tổng uncompressed bytes và thời gian** trước parse; chống ZIP bombs.
2. Dùng **ASM bản được vá** và theo dõi advisories/release notes. ASM 9.11 có hardening liên quan `BootstrapMethods` length, code length, recursion, `ConstantDynamic`; 9.11.1 sửa regression và giới hạn tính frames.
3. Giới hạn **độ sâu/khối lượng** khi duyệt nested dynamic constants, annotations, signatures và attributes.
4. Không để các phân tích `ClassWriter.COMPUTE_FRAMES` tùy tiện nạp classes từ artifact chưa tin cậy vào JVM dịch vụ.
5. Chạy fuzz/malformed tests trong **process/container cô lập** với CPU/memory/time quotas; hủy process khi vượt hạn.
6. **Không bao giờ `defineClass`/invoke method từ class chưa tin cậy** trong cùng process production chỉ để “kiểm tương thích”.
7. Ghi telemetry an toàn; không tạo high-cardinality metric từ mọi internal class name.
8. Bảo vệ repository/toolchain supply chain; pin dependencies, kiểm signatures/checksums theo policy.
9. Với input preview/unknown attribute, chọn **fail rõ ràng** thay vì xóa thông tin rồi trả output có vẻ thành công.
10. Kiểm test assets và parser trên JDK/OS thực tế, không suy từ một môi trường development.

Ví dụ demo **chỉ execute bytecode do chính test tạo**. Đây là một quyết định an toàn quan trọng, không phải một hạn chế ngẫu nhiên của ASM.

## 19. Các lỗi phổ biến và hướng sửa

| Sai lầm | Hậu quả | Hướng sửa |
| --- | --- | --- |
| Chỉ test `ClassReader` constructor | Có thể bỏ sót lỗi trong `accept`/visitor/write. | Parse + visitor + roundtrip + verifier/execute đúng mức. |
| Thấy `invokedynamic` rồi coi đó là condy | Tag 18 khác tag 17. | Kiểm `ConstantDynamic` trong `visitLdcInsn`. |
| Sinh condy ở major 52/54 | Vi phạm class file version hợp lệ. | Chọn major 55+ và test trên JVM phù hợp. |
| Dùng ASM cũ với class major 71 | Có thể báo unsupported version. | Nâng ASM/tool chain theo release notes và CI. |
| Chọn `Opcodes.V27` rồi kỳ vọng JVM11 chạy | JVM11 không hỗ trợ major71. | Tách parse/rewrite với execute; JDK27 job riêng. |
| Đổi hai byte version về 55 để chạy | Không thực hiện semantic backport. | Dùng compiler/generator target 11 thực sự. |
| Cho rằng mọi `ldc` là String/Integer | Bỏ qua `ConstantDynamic`. | Kiểm type, bootstrap metadata. |
| Bỏ `BootstrapMethods` khi rewrite | Condy không resolve/link hợp lệ. | Bảo toàn attr/handles/args và test execution. |
| Sai field descriptor của condy | Type mismatch hoặc verify/link error. | Validate descriptor theo JVMS. |
| Chỉ so bytes roundtrip | Thứ tự CP có thể thay đổi mà semantic vẫn đúng. | So semantic invariants + execute. |
| Chỉ so class name/version | Có thể mất condy hoặc hỏng method body. | Assert metadata, frames, bootstrap/result. |
| `SKIP_FRAMES` trong transformer | Có thể tạo `VerifyError`. | Bảo toàn/recompute frames đúng. |
| `COMPUTE_FRAMES` nạp class ngoài ý muốn | Thất bại classpath hoặc rủi ro execution. | Controlled loader & transform isolation. |
| Nuốt lỗi `BootstrapMethodError` | Che lỗi runtime resolution. | Giữ cause/phase và fail test. |
| Test Java27 class trên JVM24 và gọi đó là bug parser | JVM24 không chạy major71. | Parser test riêng, execute trên JDK27. |
| Tắt skip của preview mà không kiểm minor | Test chạy sai release hoặc fail bí ẩn. | Preview chỉ trên JDK phù hợp với `--enable-preview`. |
| ASM core mới nhưng plugin shaded ASM cũ | Dependency thực vẫn lỗi. | Kiểm dependency tree và shaded modules. |
| Parse class lạ không giới hạn độ dài/recursion | OOM/CPU DoS. | Limit + sandbox + bản thư viện vá lỗi. |
| Coi JUnit trên JDK24 đã chứng minh JVM11 | Chỉ chứng minh source target 11 và runtime24. | Chạy matrix job JDK11 thực sự. |

## 20. Bài tập thực hành

**Bài 1 — đọc header:** Tạo class từ `javac --release 11`, đọc 8 byte đầu. Xác nhận `CAFEBABE`, major `55` và minor phù hợp. Tại sao đọc header không chứng minh bytecode hợp lệ?

**Bài 2 — phân biệt tag:** Trong `CondyCompatibilityDemo`, chỉ ra `ConstantDynamic` tạo tag 17 ở đâu. So sánh với method visitor `visitInvokeDynamicInsn` cho tag 18. Tại sao không dùng một callback thay thế callback còn lại?

**Bài 3 — version matrix:** Chạy bộ test trên JDK11, JDK17 và JDK27 (khi có). Giải thích vì sao parse class71 có thể PASS trên JDK11 nhưng execution phải chuyển qua JDK27.

**Bài 4 — round-trip:** Đổi tên condy thành `configuration` và bootstrap trả `"value:configuration"`. Viết assertion không phụ thuộc thứ tự constant pool nhưng kiểm đúng result và bootstrap metadata.

**Bài 5 — nested condy:** Tạo static bootstrap argument là một `ConstantDynamic` khác. Viết visitor đếm số dynamic constants theo chiều sâu có **depth limit** và phát hiện chu trình/input nguy hiểm.

**Bài 6 — bootstrap error:** Thay bootstrap để ném một checked exception. Test class được load nhưng lỗi xuất hiện khi `ldc` resolve; ghi nhận `BootstrapMethodError` và cause theo JVM contract.

**Bài 7 — current class file:** Biên dịch một class đơn giản bằng JDK27 thật, đọc major71, đem vào ASM 9.11.1 và round-trip. So sánh với fixture `makeCurrentVersionFixture()` vốn chỉ tạo header/method đơn giản.

**Bài 8 — preview:** Chuẩn bị class minor65535 của đúng JDK release và thử test matrix. Vì sao bật `--enable-preview` trên một JDK khác không làm cho class cũ được phép chạy?

**Bài 9 — frames:** Dùng ASM chèn một nhánh vào method có nhiều branches. Chạy `CheckClassAdapter` và JVM verifier. Giải thích vì sao có thể cần tính lại frames thay vì chỉ tăng `maxStack`.

**Bài 10 — dependency conflict:** Tạo dự án có hai thư viện kéo ASM versions khác nhau. Dùng `mvn dependency:tree` tìm phiên bản hiệu lực và kiểm tool/plugin shaded ASM.

**Bài 11 — malformed input:** Tạo fixture class bị cắt giữa `constant_pool` hoặc có length sai. Test parser có quota, fail không treo. Không chạy bằng `defineClass` khi chưa tin cậy.

**Bài 12 — nghĩa của PASS:** Thiết kế báo cáo kết quả riêng cho PARSE, ROUNDTRIP, VERIFY, EXECUTE và BOOTSTRAP. Nếu parser71 pass nhưng JVM11 không hỗ trợ major71, trạng thái nào đúng?

**Bài 13 — corpus:** Lập danh sách classfiles từ javac11/17/21/27, một library ASM khác, và một agent thật. Ghi SHA-256/major/minor/expected trait cho từng fixture để CI có thể tái tạo.

**Bài 14 — hardening:** Đọc release notes ASM 9.11/9.11.1; xác định các thay đổi liên quan recursion, `BootstrapMethods`, frame limits và thiết kế regression test có budget cho input không tin cậy.

## 21. Checklist hoàn tất kiểm thử thư viện bytecode

- [ ] Đúng **target Java 11** cho source/tool nếu ứng dụng yêu cầu JVM11.
- [ ] Hiểu tag **17** = `CONSTANT_Dynamic`; tag **18** = `CONSTANT_InvokeDynamic`.
- [ ] Condy chỉ xuất hiện trong class file **major 55 trở lên**.
- [ ] Đọc chính xác `major/minor`, không tự hạ version để chạy.
- [ ] Class file hiện hành được đối chiếu với **JVM spec mới nhất**, không đoán từ tên JDK.
- [ ] ASM/module versions đủ mới và đồng bộ, kể cả plugin/agent/shaded dependencies.
- [ ] Có test `ConstantDynamic`, bootstrap handle, args, descriptor và `ldc`.
- [ ] Có round-trip test dựa trên **semantic invariants**, không chỉ byte equality.
- [ ] Có verifier và execute test trên **JVM đúng major**, chỉ với fixture tin cậy.
- [ ] Có test `BootstrapMethodError`, malformed, unsupported/preview version và negative input.
- [ ] Có corpus từ compiler/tool khác, không chỉ dữ liệu do chính ASM tạo.
- [ ] Instrumentation bảo toàn/recompute frames, attributes và BootstrapMethods đúng.
- [ ] Parser input không tin cậy có byte/time/depth/memory limits và môi trường cô lập.
- [ ] CI chạy Java11 runtime riêng và JDK27 runtime riêng nếu sản phẩm đòi thực thi class71.
- [ ] Telemetry phân biệt PARSE/ROUNDTRIP/VERIFY/EXECUTION/BOOTSTRAP và không báo pass giả khi skip.
- [ ] Bài test ví dụ target11 đã compile/run và JUnit assertions đã được đối chiếu.

## 22. Tài liệu chính thức và ghi nhớ

1. [JEP 309 — Dynamic Class-File Constants](https://openjdk.org/jeps/309): Java 11 bổ sung `CONSTANT_Dynamic`.
2. [JVM Specification Java SE 11 — Chapter 4, class file format](https://docs.oracle.com/javase/specs/jvms/se11/html/jvms-4.html): major55, constant pool, bootstrap metadata và format.
3. [JVM Specification Java SE 27 — Chapter 1](https://docs.oracle.com/javase/specs/jvms/se27/html/jvms-1.html): release/major version đến Java 27 (71).
4. [JVM Specification Java SE 27 — Chapter 4](https://docs.oracle.com/javase/specs/jvms/se27/html/jvms-4.html): `CONSTANT_Dynamic`, `BootstrapMethods`, major/minor và preview rules hiện hành.
5. [Java SE 11 — `java.lang.invoke`](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/lang/invoke/package-summary.html): cơ chế bootstrap, dynamic constants và thời điểm resolve.
6. [ASM official site](https://asm.ow2.io/): giới thiệu, tài liệu, cách lấy thư viện.
7. [ASM official release history](https://asm.ow2.io/versions.html): ASM 9.11.1 tháng 10/2026, hỗ trợ format và các fixes/hardening.
8. [Maven Central — org.ow2.asm:asm](https://central.sonatype.com/artifact/org.ow2.asm/asm): tọa độ dependency và phiên bản artifact.
9. [JUnit Jupiter 5.13.4 release notes](https://docs.junit.org/5.13.4/release-notes/): ví dụ test runner dùng với Maven/Java 11.
10. [Maven Surefire Plugin](https://maven.apache.org/surefire/maven-surefire-plugin/): chạy unit tests, báo kết quả tự động.

**Ghi nhớ cuối:** Khi kiểm **thư viện bytecode** trong chủ đề **hằng số động**, phải kiểm cả `CONSTANT_Dynamic` (tag 17), `BootstrapMethods` và **khả năng resolve khi thực thi**, không chỉ class header. Một parser ASM hiện đại có thể đọc/ghi class file major **71** trên JVM chạy code Java **11**, nhưng **JVM 11 không thể load/execute class71**. Tách rõ parse, round-trip, transform, verify và execute; dùng test fixtures, CI matrix và giới hạn tài nguyên để chứng minh tương thích một cách có thể tái lập.