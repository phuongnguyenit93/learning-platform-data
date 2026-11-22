# Chọn Class-File API trên JDK hỗ trợ và phương án cho JDK thấp hơn

**Chủ đề:** Java Advance → instrumentation → **Đóng gói và triển khai**.

Một công cụ instrumentation cần đọc, sinh hoặc biến đổi bytecode của tệp `.class`. Kể từ **JDK 24**, Java có **Class-File API chính thức** trong gói `java.lang.classfile`, giúp xây các công cụ xử lý class file bằng API chuẩn mà không nhất thiết thêm thư viện bytecode bên ngoài. Tuy nhiên, **ứng dụng vẫn chạy trên Java 17, Java 21 hoặc JVM cũ hơn không tự có API này**. Chọn API theo phiên bản JVM **đang chạy công cụ/agent**, khả năng biên dịch của toolchain, **phiên bản class file đầu vào** và JVM **sẽ nạp bytecode đầu ra**.

Bài này trả lời bốn vấn đề triển khai cụ thể:

1. **JDK nào dùng được `java.lang.classfile`?** Mốc preview, stable, compiler flags và sự thay đổi giữa các bản phát hành.
2. **Nếu host chỉ dùng JDK 17/21 thì sao?** Dùng một thư viện bytecode phù hợp như **ASM** hoặc công cụ cấp cao như **Byte Buddy**, hoặc dùng `javap` khi chỉ cần đọc bằng tay.
3. **Làm sao đóng gói cho nhiều JVM?** Tách artifacts, shared API và tùy chọn **multi-release JAR**, tránh linkage tới class không tồn tại ở runtime thấp.
4. **Làm sao kiểm chứng?** Kiểm tra major version, parser hỗ trợ định dạng đầu vào, khả năng load agent, tính hợp lệ bytecode và hành vi ứng dụng.

Hai lab có mã nguồn hoàn chỉnh: **Java 17 + ASM** và **Java 24+ + Class-File API**, cùng đọc **một class file Java 17**. Chúng giúp phân biệt rõ “JDK chạy công cụ” với “phiên bản bytecode mà công cụ đang phân tích”.

> **Quy tắc cốt lõi:** Dùng Class-File API chuẩn khi **runtime của công cụ là JDK 24+** và các tính năng cần dùng được JVM đó hỗ trợ. Dùng ASM/Byte Buddy hoặc một engine tương thích khi **runtime phải còn hỗ trợ JDK thấp hơn**, đồng thời ghim phiên bản thư viện đủ mới cho class file cần đọc/ghi. Không sử dụng `jdk.internal.org.objectweb.asm` như API ứng dụng ổn định.

## 1. Ma trận hỗ trợ phiên bản

| Môi trường | Trạng thái Class-File API | Chọn phương án nào? |
| --- | --- | --- |
| JDK 8–21 | **Không có** `java.lang.classfile` như API chuẩn để dùng trực tiếp | ASM/Byte Buddy phiên bản tương thích, hoặc `javap`/công cụ riêng |
| JDK 22 | **Preview lần đầu — JEP 457** | Chỉ dùng nếu chấp nhận preview flags và API dễ thay đổi |
| JDK 23 | **Preview lần hai — JEP 466** | Vẫn cần preview flags; không xem như API stable để phát hành rộng |
| JDK 24 | **API chính thức — JEP 484** | Dùng `java.lang.classfile` trực tiếp, không cần `--enable-preview` cho chính API |
| JDK 25+ có API chuẩn | Class-File API tiếp tục có sẵn; chi tiết có thể được mở rộng theo JDK | Đọc Javadoc đúng bản JDK, test trên runtime thực tế |

Các mốc này là **lịch sử API**, không phải cam kết JVM đời cũ có thể chạy class đã biên dịch bởi JDK 24. Class file của `javac --release 24` có **major version 68**, trong khi Java 17 hiểu tối đa class-file major **61** đối với class thông thường không dùng preview. Java 21 là **65**, Java 22 là **66**, Java 23 là **67**.

Không nhầm ba biến độc lập:

- **Compiler JDK**: máy biên dịch dùng `javac` phiên bản nào.
- **Runtime JDK**: tiến trình chạy agent/tool hoặc ứng dụng dùng `java` phiên bản nào.
- **Class-file target major**: bytes đầu ra chứa version nào trong header `ClassFile`.

Một tool chạy JDK 24 có thể **đọc class file Java 17** (major 61). Nhưng chính class `JdkInspector.class` được biên dịch với `--release 24` không thể chạy trên Java 17. Nếu tool cần chạy trực tiếp trong tiến trình Java 17, phải cung cấp engine khác.

### 1.1. Preview không giống API chính thức

Ở JDK 22/23, `java.lang.classfile` từng là **preview API**. Khi biên dịch/run mã tham chiếu preview API, cần dùng các tùy chọn preview phù hợp **đúng phiên bản JDK đang sử dụng**. Ví dụ đối với JDK 23:

```bash
# Ví dụ khi sử dụng API preview của JDK 23;
# source phải viết theo chữ ký của chính API JDK 23.
javac --enable-preview --release 23 -d out23 src23/demo/PreviewInspector.java
java --enable-preview -cp out23 demo.PreviewInspector
```

**Đây là lệnh minh họa cho dự án preview riêng**, không phải lệnh chạy các nguồn JDK 24 ở lab phía dưới. Preview code có thể cần sửa source khi chuyển từ JDK 22 sang 23 hoặc 24; một artifact preview của release này không được coi là binary tương thích với mọi release khác. Những class files dùng preview features có thể có **minor version 65535** và bị giới hạn chạy theo đúng major release tương ứng.

**Khuyến nghị deploy:** với hệ thống production, ưu tiên API stable từ JDK 24 hoặc engine thư viện bytecode vốn hỗ trợ JDK thấp. Tránh thiết kế một binary dùng API preview rồi coi đó là giải pháp phát hành phổ thông.

## 2. Class-File API chuẩn cung cấp những gì?

Các package chính của **module `java.base`** từ JDK 24:

```text
java.lang.classfile
java.lang.classfile.attribute
java.lang.classfile.constantpool
java.lang.classfile.instruction
```

Không cần thêm Maven dependency cho chính API này trên JDK 24+. Những thành phần thường dùng:

| Thành phần | Vai trò |
| --- | --- |
| `ClassFile` | Ngữ cảnh API và options; tạo bằng `ClassFile.of()` |
| `ClassFile.parse(byte[])` / `parse(Path)` | Phân tích bytes/tệp để tạo `ClassModel`; gọi trên instance `ClassFile` |
| `ClassModel` | Mô hình bất biến của class file, có tên lớp, version, fields, methods, attributes |
| `FieldModel`, `MethodModel` | Mô hình members và descriptors |
| `CodeModel`, `Instruction` | Bytecode và các phần tử trong `Code` attribute |
| `ClassTransform`, `MethodTransform`, `CodeTransform` | Luồng biến đổi qua builders |
| `ClassFile.build(...)` | Sinh class file |
| `ClassFile.verify(...)` | Hỗ trợ kiểm tra class file, **không thay thế** chạy JVM verifier/behavior tests |

Cú pháp đúng:

```java
ClassFile context = ClassFile.of();
ClassModel model = context.parse(bytes);
```

Đây là **fragment**: cần import `ClassFile`/`ClassModel` và biến `byte[] bytes`. `parse` là **phương thức instance của context**; không nên viết `ClassFile.parse(bytes)` như lời gọi static.

Các models thuộc API được thiết kế immutable/lazy: lấy `ClassModel` không có nghĩa mọi method/instruction đã được parse hoặc xác minh sâu. Một `IllegalArgumentException` có thể xuất hiện khi đọc accessor sau đó vì dữ liệu chỉ được giải mã theo nhu cầu. Việc phân tích không tự load/initialize target class bằng `Class.forName`.

### 2.1. Khi nào ưu tiên dùng API chuẩn?

- Một tool/agent **chỉ cần chạy trên JDK 24+**, muốn giảm dependency, theo sát định dạng class file của JDK.
- Cần inspect bytecode, traverse fields/methods, phân tích symbolic operands, sinh/transform class files bằng API typed.
- Muốn tránh dựa vào **JDK internal ASM fork**.
- Có quy trình nâng JDK theo lịch rõ ràng, kiểm thử cùng JDK cụ thể của production.

API chuẩn không giải quyết mọi thứ: vẫn cần hiểu JVM verifier, frame computation, class loader, module access, class file versions, transformer chaining và ngữ nghĩa. Không phải một API “tự động thêm tracing đúng trên mọi method”.

### 2.2. Tool JDK 24 đọc bytes Java 17 có được không?

Có, nếu class file hợp lệ và định dạng được API hỗ trợ. Ví dụ JDK 24 tool parse một class major 61 sinh bởi `javac --release 17`. Nhưng chiều ngược lại **không đúng**: JVM Java 17 không nạp được class major 68 của bản tool JDK 24, và `java.lang.classfile` không tồn tại trong Java 17 runtime.

**Phải tách runtime của công cụ khỏi runtime của output.** Tool build-time chạy JDK 24 có thể sinh bytes nhắm Java 17, nhưng output đó chỉ chạy trên Java 17 khi **class-file major, instructions, referenced APIs và constraints** tương thích. Nếu sinh class bằng builder, cần điều khiển class version phù hợp (`ClassBuilder.withVersion(...)` khi thích hợp) và kiểm tra mọi instructions/API references trước khi phát hành.

## 3. Khi chỉ có JDK 17/21, chọn gì?

### 3.1. ASM — tầng bytecode trực tiếp

**ASM** là thư viện xử lý class file độc lập với `java.lang.classfile`. Những API cơ bản:

- `ClassReader` đọc bytes và gọi `ClassVisitor`/`MethodVisitor`.
- `ClassWriter` sinh class file, hoặc dùng để tiếp nhận output transformer.
- `MethodVisitor` đọc/chèn instructions với opcodes của JVM.
- `AdviceAdapter` trong artifact `asm-commons` hỗ trợ chèn hooks ở method entry/exit; phải xử lý exceptional exits đúng.
- `CheckClassAdapter` trong `asm-util` hữu ích để kiểm tra cấu trúc output và debug.

Chọn **phiên bản ASM đủ mới** cho **major version cao nhất mà công cụ sẽ gặp**, không chỉ cho JDK đang chạy thư viện. Ví dụ release **ASM 9.7.1** đã thêm constant `Opcodes.V24` (Java 24) và **ASM 9.9** có hỗ trợ thêm các versions về sau; hãy kiểm tra trang release của ASM trước khi cố parse class file từ JDK mới hơn nữa.

Một class Java 17 tool dùng ASM có thể xử lý class files được biên dịch bởi JDK cao hơn **nếu chính version ASM đó hỗ trợ format**, dù không có quyền chạy những classes ấy trên Java 17. Ngược lại, thư viện ASM quá cũ có thể báo `Unsupported class file major version ...` khi đọc input mới.

### 3.2. Byte Buddy — API cấp cao hơn

**Byte Buddy** giúp sinh subclass, intercept methods và tạo instrumentation agent dựa trên mô hình khai báo; nó thường sử dụng ASM bên dưới. Khi mục tiêu là “instrument method X để đo thời gian” và không muốn trực tiếp quản lý mọi opcode, Byte Buddy có thể giảm công sức.

Tuy nhiên cần xác minh **version Byte Buddy hỗ trợ runtime JDK và class-file version**; agent còn phụ thuộc class-loader constraints, module visibility và quyền attach/retransform. Không có nghĩa Byte Buddy trên Java 17 tự làm JVM Java 17 hiểu class-file Java 24.

### 3.3. `javap` — lựa chọn đơn giản khi chỉ đọc

Nếu chỉ cần **in thông tin** class file để chẩn đoán:

```bash
javap -verbose -p -c -classpath target/classes demo.Sample
```

`javap` của JDK đọc class files và in human-readable dump, không cung cấp API thao tác typed như ASM/Class-File API và không tự trả output class-file biến đổi. Rất phù hợp để QA bytes trước/sau instrumentation, nhưng nếu cần phân tích cấu trúc tự động sâu, nên dùng API/library chuyên dụng.

### 3.4. Không phụ thuộc vào `jdk.internal.org.objectweb.asm`

JDK có một implementation/nhánh ASM **nội bộ** phục vụ các thành phần JDK, nhưng nó **không phải API công khai được hứa ổn định** cho application/agent:

```java
// Không khuyến nghị cho production code:
import jdk.internal.org.objectweb.asm.ClassReader;
```

Lệnh ở trên là **fragment anti-pattern**. Trên JDK 9+, module encapsulation có thể làm code không compile/chạy nếu không có `--add-exports`, và phiên bản/semantics/internal packages có thể thay giữa các JDK. `--add-exports` là một workaround phụ thuộc JVM, **không** biến nội bộ đó thành API chuẩn. Tốt hơn là dùng ASM artifact chính thức hoặc Class-File API từ JDK 24.

## 4. Lab đối chiếu: cùng tệp `.class`, hai engine

Mục tiêu: biên dịch **`demo.Sample` thành major 61 (Java 17)** rồi dùng:

1. **ASM engine chạy trên JDK 17+**, có Maven dependency.
2. **Class-File API engine chạy trên JDK 24+**, không cần ASM dependency.

Hai engine in cùng tên lớp, major version, signatures và việc một method có `Code` attribute hay không. Ta **không cần nạp `demo.Sample` vào JVM** để kiểm tra class file.

Cấu trúc thư mục:

```text
class-file-choice/
├── pom.xml
├── src/
│   └── main/
│       └── java/
│           └── demo/
│               ├── Sample.java
│               └── AsmInspector.java
└── modern-src/
    └── demo/
        └── JdkInspector.java
```

Để chạy nhánh ASM, cần **JDK 17+ và Maven 3.x**, máy có thể tải dependency từ Maven Central hoặc cache nội bộ. Để chạy nhánh chuẩn, cần **JDK 24+**; cả hai sẽ đọc `target/classes/demo/Sample.class` do Maven biên dịch `--release 17`.

### 4.1. Tệp `src/main/java/demo/Sample.java`

```java
package demo;

public final class Sample {
    private Sample() {}

    public static int plus(int value) {
        return value + 1;
    }
}
```

Class mẫu rất ngắn, có private constructor và một method. Đây là **dữ liệu cho inspector**, không cần `main` của chính Sample.

### 4.2. Maven `pom.xml` — Java 17 + ASM

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
         https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>demo</groupId>
  <artifactId>class-file-choice</artifactId>
  <version>1.0.0</version>

  <properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>

  <dependencies>
    <dependency>
      <groupId>org.ow2.asm</groupId>
      <artifactId>asm</artifactId>
      <version>9.9</version>
    </dependency>
  </dependencies>

  <build>
    <plugins>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-compiler-plugin</artifactId>
        <version>3.14.0</version>
        <configuration>
          <release>17</release>
        </configuration>
      </plugin>
      <plugin>
        <groupId>org.codehaus.mojo</groupId>
        <artifactId>exec-maven-plugin</artifactId>
        <version>3.5.1</version>
      </plugin>
    </plugins>
  </build>
</project>
```

Maven khóa `maven.compiler.release=17` và version ASM cụ thể. `pom.xml` có artifact bên thứ ba `org.ow2.asm:asm`, nên deployment phải mang dependency đó theo; JDK 17 không cung cấp ASM public API trong classpath.

### 4.3. Tệp `src/main/java/demo/AsmInspector.java`

```java
package demo;

import java.nio.file.Files;
import java.nio.file.Path;
import org.objectweb.asm.ClassReader;
import org.objectweb.asm.ClassVisitor;
import org.objectweb.asm.MethodVisitor;
import org.objectweb.asm.Opcodes;

public final class AsmInspector {
    private AsmInspector() {}

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                    "Usage: AsmInspector <class-file-path>");
        }

        byte[] bytes = Files.readAllBytes(Path.of(args[0]));
        ClassReader reader = new ClassReader(bytes);

        System.out.println("ENGINE=ASM");
        reader.accept(new ClassVisitor(Opcodes.ASM9) {
            @Override
            public void visit(
                    int version, int access, String name,
                    String signature, String superName,
                    String[] interfaces) {

                System.out.println("CLASS=" + name);
                System.out.println("MAJOR=" + (version & 0xffff));
            }

            @Override
            public MethodVisitor visitMethod(
                    int access, String name, String descriptor,
                    String signature, String[] exceptions) {

                return new MethodVisitor(Opcodes.ASM9) {
                    boolean hasCode;

                    @Override
                    public void visitCode() {
                        hasCode = true;
                    }

                    @Override
                    public void visitEnd() {
                        System.out.println("METHOD=" + name
                                + descriptor + " HAS_CODE=" + hasCode);
                    }
                };
            }
        }, ClassReader.SKIP_DEBUG | ClassReader.SKIP_FRAMES);
    }
}
```

**Giải thích:**

- `ClassReader` parse bytes; `reader.accept` gọi visitor thay vì phải tự đọc các offsets/constant-pool entries.
- `visit` nhận **internal class name** `demo/Sample` và class-file version. `version & 0xffff` lấy major 16 bits thấp của giá trị version ASM.
- `visitMethod` tạo một `MethodVisitor` cho mỗi method. `visitCode` chạy khi method có `Code` attribute; `visitEnd` in `HAS_CODE` đúng một lần.
- Bỏ `SKIP_DEBUG` và `SKIP_FRAMES` trong lab chỉ để không cần xử lý debug tables/stack frames; **không** đặt `SKIP_CODE` vì sẽ khiến nhận diện code sai.
- Lệnh này **chỉ đọc**, không tạo transformed class. Từ ASM có thể chèn code bằng `ClassWriter` và visitors nhưng cần giữ max_stack/max_locals, stack map frames, exception handlers và semantics.

### 4.4. Chạy ASM engine trên JDK 17+

Đứng ở thư mục `class-file-choice`:

```bash
java -version
mvn -version
mvn -q compile exec:java -Dexec.mainClass=demo.AsmInspector -Dexec.args=target/classes/demo/Sample.class
```

Kết quả application stdout (không tính Maven/plugin logs):

```text
ENGINE=ASM
CLASS=demo/Sample
MAJOR=61
METHOD=<init>()V HAS_CODE=true
METHOD=plus(I)I HAS_CODE=true
```

Cả hai methods có `Code`. `<init>()V` là constructor riêng, còn `plus(I)I` là method nhận và trả `int`. `MAJOR=61` vì Maven biên dịch với `release=17`, dù bạn có thể chạy Maven bằng JDK 24.

**Khả năng chạy:** mã nguồn `AsmInspector` chỉ dùng Java 17 syntax/API và ASM public library. Nó chạy trên Java 17+ khi có dependency ASM 9.9 tương thích, nhưng việc parse class major cao hơn tùy version ASM; không đồng nghĩa JVM17 có thể **load/chạy** class major đó.

### 4.5. Tệp `modern-src/demo/JdkInspector.java`

```java
package demo;

import java.lang.classfile.ClassFile;
import java.lang.classfile.ClassModel;
import java.lang.classfile.MethodModel;
import java.nio.file.Path;

public final class JdkInspector {
    private JdkInspector() {}

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                    "Usage: JdkInspector <class-file-path>");
        }

        ClassModel model = ClassFile.of().parse(Path.of(args[0]));
        System.out.println("ENGINE=CLASS_FILE_API");
        System.out.println("CLASS=" + model.thisClass().asInternalName());
        System.out.println("MAJOR=" + model.majorVersion());

        for (MethodModel method : model.methods()) {
            System.out.println("METHOD="
                    + method.methodName().stringValue()
                    + method.methodType().stringValue()
                    + " HAS_CODE=" + method.code().isPresent());
        }
    }
}
```

Tệp này là **chương trình Java 24+ độc lập**, không cần ASM library. `ClassFile.of()` tạo context; `parse(Path)` trả `ClassModel`. `methods()` liệt kê phương thức; `code().isPresent()` phân biệt method có thân `Code` với method `abstract`/`native`.

### 4.6. Chạy JDK engine trên JDK 24+

Sau khi Maven đã tạo `target/classes/demo/Sample.class` (major 61), chuyển sang JDK 24+ rồi chạy ở thư mục gốc:

```bash
java -version
javac -version
javac --release 24 -d modern-classes modern-src/demo/JdkInspector.java
java -cp modern-classes demo.JdkInspector target/classes/demo/Sample.class
```

Stdout với đúng Sample đã biên dịch Java 17:

```text
ENGINE=CLASS_FILE_API
CLASS=demo/Sample
MAJOR=61
METHOD=<init>()V HAS_CODE=true
METHOD=plus(I)I HAS_CODE=true
```

**So với ASM output:** chỉ khác tên engine; thông tin class/major/method được đọc giống nhau. Đây là cách kiểm tra “một định dạng input — hai engine” thay vì chỉ kiểm tra compiler có tìm thấy `java.lang.classfile` hay không.

**Lưu ý:** `JdkInspector.class` của dòng `--release 24` có **major 68**. Nó chạy trên JDK 24+ (khi API còn tương thích), nhưng `java -cp modern-classes ...` bằng JDK 17 sẽ thất bại với `UnsupportedClassVersionError` trước khi có cơ hội parse input Java17. Kết quả `MAJOR=61` là **class file được đọc**, không phải major của chính inspector.

## 5. Class-File API trên JDK 24: biến đổi không phải ghi vào input

API chuẩn không chỉ dành cho inspect; nó có builder và transform:

```java
// Fragment chạy với JDK 24+.
// Cần import java.lang.classfile.ClassFile;
// java.lang.classfile.ClassModel;
// java.lang.classfile.ClassTransform.

ClassFile context = ClassFile.of();
ClassModel model = context.parse(inputBytes);

byte[] output = context.transformClass(
        model, ClassTransform.ACCEPT_ALL);
```

`inputBytes` phải là `byte[]` class file đã chuẩn bị. `ClassTransform.ACCEPT_ALL` cho builder nhận các elements hiện có; output là **một byte array mới** mô tả class file, **không được coi là byte-for-byte giống input** trong mọi trường hợp (constant-pool/attribute layout có thể thay do writer/options).

Nếu thực sự chèn instructions, cần chuyển biến đổi tới method/code transforms, xử lý stack maps, locals, branch targets, try/catch, constructors và annotations. **Không** chèn byte ngẫu nhiên bằng offsets cố định; không sửa trực tiếp `classfileBuffer` do `ClassFileTransformer` nhận từ JVM.

Một đoạn kiểm tra bổ sung:

```java
// Fragment JDK 24+, áp dụng sau khi có byte[] output.
var errors = ClassFile.of().verify(output);
System.out.println("VERIFY_ERRORS=" + errors.size());
```

`verify` giúp phát hiện một số vấn đề class file nhưng **không thay thế** tải class trên JVM đích, test method behavior và verifier trong runtime thật. Nếu `VERIFY_ERRORS=0`, đó không phải bảo đảm code mới đúng nghiệp vụ hay chạy được trên một JDK thấp hơn.

### 5.1. Biến đổi class file cho runtime thấp hơn

Một tool chạy JDK 24 có thể tạo output class files nhắm **Java 17** nếu output đáp ứng tất cả điều kiện:

1. Header class-file **major 61** (và minor phù hợp), không phải major 68 mặc định của tool.
2. Không có opcode, constant-pool form, attribute semantics hoặc language/runtime feature mà Java17 không hỗ trợ.
3. Không gọi API chỉ tồn tại trên Java24 từ class được phát hành cho Java17.
4. Stack map frames và handlers hợp lệ cho verifier Java17.
5. Chạy **integration tests trên JVM Java17 thực tế**, không chỉ trên JDK24.

Khi tự xây class trong Class-File API, `ClassBuilder.withVersion(61, 0)` là một API để chọn version **cho class được build**, nhưng chỉ chỉnh con số version **không tự loại bỏ** những bytecode features không tương thích. Trong transform một input Java17, trước tiên xác minh output có version đúng; không coi engine tự giữ/tự hạ version như lời hứa chung cho mọi option.

## 6. Tại sao `javac --release 17` không sửa được vấn đề thiếu API?

`javac --release N` không chỉ đặt class-file major; nó giới hạn **Java platform APIs** mà source có thể tham chiếu theo release N.

Nếu dùng JDK24 chạy:

```bash
javac --release 17 -d out modern-src/demo/JdkInspector.java
```

thì source import `java.lang.classfile.ClassFile` **không hợp lệ với Java17 API surface**, vì gói `java.lang.classfile` chưa tồn tại trong Java17. Nếu thay bằng:

```bash
javac --release 24 -d out modern-src/demo/JdkInspector.java
```

compiler tìm thấy API, nhưng output classfile major68 cần JDK24+ để chạy.

**Không có lựa chọn `--release` đơn lẻ nào vừa “gọi API chỉ có từ Java24” vừa “chạy trực tiếp trong Java17”**. Muốn hỗ trợ Java17 phải:

- Dùng thư viện độc lập tương thích (ASM/Byte Buddy).
- Chạy bước phân tích/transform trên process **JDK24 build-time** rồi chỉ phát hành bytes output thật sự tương thích Java17.
- Hoặc tách implementation theo phiên bản JVM bằng strategy/packaging phù hợp.

Điều này đặc biệt quan trọng với **Java agents**: nếu manifest `Premain-Class` trỏ tới class major68 hoặc static imports/calls chỉ có ở Java24, khởi động `-javaagent` trên Java17 có thể thất bại **trước khi `main` của ứng dụng chạy**.

## 7. Đóng gói cho nhiều runtime: ba chiến lược

### 7.1. Phương án A — chỉ hỗ trợ JDK 24+

Dễ nhất nếu toàn bộ runtime production đã ở JDK24+:

```text
agent-modern.jar
  META-INF/MANIFEST.MF
    Premain-Class: demo.ModernAgent
  demo/ModernAgent.class          (target JDK 24+)
  demo/ModernTransformer.class    (dùng java.lang.classfile)
```

Build với `--release 24` hoặc toolchain JDK tương ứng; compile và chạy tests trên JVM tối thiểu được cam kết. Không cần ASM runtime dependency nếu không dùng ASM ở các thành phần khác.

**Rủi ro:** nếu một deployment slot còn Java17/21, agent JAR có thể làm JVM dừng khi load do `UnsupportedClassVersionError` hoặc `NoClassDefFoundError`. Không gắn một artifact modern vào mọi runtime mà không có compatibility matrix.

### 7.2. Phương án B — hai artifacts độc lập

Tạo **hai bản JAR cho hai nhóm runtime**:

```text
agent-legacy.jar    Java17 bytecode + ASM/Byte Buddy compatible
agent-modern.jar    Java24 bytecode + java.lang.classfile

Deployment:
  runtime JDK17 / JDK21 -> agent-legacy.jar
  runtime JDK24+        -> agent-modern.jar
```

Đây là mô hình **được khuyến nghị khi muốn ít phức tạp**:

- Mỗi JAR có `Premain-Class` hợp lệ cho runtime tương ứng.
- Pipeline build/test riêng: `--release 17`, `--release 24`.
- Có thể dùng chung một **API module** được build cho Java17 và không chứa reference tới `java.lang.classfile`.
- Công cụ CI hoặc container image **chọn JAR tại deploy time**, không phân tích `java -version` bằng regex dễ vỡ ở runtime.
- ASM phải được bundle/chọn classpath hợp lệ; nếu chọn shade/fat-JAR, cần cân nhắc relocation, license, signatures và đụng độ dependency.
- Runtime modern có thể đọc lại data/class files cũ. Các tests về behavior cần so giữa engine legacy và modern.

**Tránh** xây một JAR với `Premain-Class` compiled Java24 rồi hy vọng `if (Runtime.version().feature() < 24)` có thể cứu Java17. JVM **phải load chính class entrypoint trước khi chạy nhánh if**, nên lỗi class version/linkage có thể xuất hiện từ rất sớm.

### 7.3. Phương án C — Multi-Release JAR (MR-JAR)

Từ Java9, **multi-release JAR** có thể chứa **một class name** ở baseline và bản thay thế dành cho runtime mới:

```text
inspector-mr.jar
├── META-INF/MANIFEST.MF
│     Multi-Release: true
│     Premain-Class: demo.AgentBootstrap
├── demo/AgentBootstrap.class            # Java17 baseline
├── demo/Inspector.class                 # Java17+ implementation, dùng ASM
└── META-INF/versions/24/
      └── demo/Inspector.class           # Java24+ implementation,
                                          # dùng java.lang.classfile
```

**Sơ đồ packaging, không phải một MR-JAR đã build sẵn.** Trên Java17/21, runtime chọn root `demo.Inspector`. Trên Java24+ nó có thể chọn versioned class ở `META-INF/versions/24`. Cần chú ý:

1. **Bootstrapping:** `Premain-Class`/entrypoint ở root phải **nạp được trên JVM tối thiểu**, ví dụ major61 nếu cam kết Java17. Đừng tham chiếu Java24 class trực tiếp trong static initializer root.
2. **Giữ binary contract:** root và versioned implementations có API/signature tương thích với callers cũ; versioned API không được vô tình đổi public contract khi đã chọn version khác.
3. **Maven dependencies:** root ASM implementation vẫn có dependency ASM, cần gói đúng; versioned implementation không được yêu cầu JDK24 API ở root code.
4. **Metadata:** manifest bắt buộc `Multi-Release: true`. Chỉ đặt thư mục `META-INF/versions/24` mà thiếu manifest chưa đủ.
5. **Build:** dùng JDK đủ mới tạo versioned classes; compiler cho root dùng `--release 17`, compiler cho versioned dùng `--release 24`; không trộn classes vào sai path.
6. **Validate:** dùng `jar --validate --file inspector-mr.jar` với JDK có công cụ MR-JAR phù hợp; kiểm thử cả Java17 và Java24.
7. **Class loading:** khi agent áp dụng loader/module rules riêng, kiểm tra thật rằng đúng implementation được chọn; không giả định mọi custom classloader/JAR processor hiểu MR-JAR như system loader.

MR-JAR tiết kiệm số artifact triển khai nhưng **tăng độ phức tạp build, dependency packaging và test matrix**. Không nhất thiết nên chọn nếu hai JAR tách biệt đã đủ.

## 8. Một API chung giúp hai engine không lan ra ứng dụng

Thay vì để mọi lớp ứng dụng tự import ASM hoặc `java.lang.classfile`, đặt một **boundary interface** biên dịch Java17:

```java
package demo.api;

public interface ClassInspector {
    InspectionResult inspect(byte[] classFile);
}
```

Đây là **fragment kiến trúc**: `InspectionResult` phải được định nghĩa trong module API với types Java17 tương thích. Ý tưởng:

```text
                         Shared API (Java17 baseline)
                         ClassInspector.inspect(byte[])
                                  │
                   ┌──────────────┴───────────────┐
                   ▼                              ▼
          AsmInspectorImpl                 JdkInspectorImpl
          runtime Java17+                  runtime Java24+
          org.ow2.asm                      java.lang.classfile
                   │                              │
                   └──────────────┬───────────────┘
                                  ▼
                      Normalized InspectionResult
```

Nếu cần chọn implementation tại runtime bằng `ServiceLoader` hoặc strategy factory:

- Đảm bảo provider Java24 **không bị load trên Java17**. Chỉ để file/class trong JAR không có nghĩa nó an toàn nếu code Java17 gọi `Class.forName` hoặc eager-scan nó.
- Khai báo service providers phù hợp versioned packaging. Nếu Java17 thấy service provider class major68 và cố instantiate, sẽ lỗi.
- Dữ liệu trả về dùng DTO trung lập, không trả thẳng `ClassModel` hay `ClassNode` vào API chung, nếu mục tiêu là thay engine độc lập.
- Test về **method owners, descriptors, attributes, instruction behavior** phải so bằng kết quả có ý nghĩa, không chỉ text dump khác layout.

Một dispatcher chỉ kiểm tra `Runtime.version().feature() >= 24` là **điều kiện cần, chưa đủ**: VM đó phải có API tương ứng và lớp implementation đúng được đóng gói; không để static references làm linkage hỏng trước khi dispatch.

## 9. Tầng agent startup và rủi ro loading

Một Java agent khai báo:

```text
Premain-Class: demo.AgentBootstrap
Can-Retransform-Classes: true
```

Khi JVM thấy `-javaagent:agent.jar`, nó sẽ load `demo.AgentBootstrap` và gọi `premain`. Nếu root class này được build major68 trong khi production chạy Java17, JVM có thể dừng **trước application main**.

Tốt hơn:

```text
Java17-compatible bootstrap:
    nhận Instrumentation
    chọn engine tương thích theo runtime/cấu hình
    đăng ký ClassFileTransformer
    không import trực tiếp java.lang.classfile

Versioned implementation:
    Java17: ASM
    Java24+: java.lang.classfile
```

Đây là **pseudocode kiến trúc**, không phải class Java đầy đủ. Nếu yêu cầu agent chạy lúc startup JDK17, phải build và test bootstrap trên Java17 thực. **Không** mặc định hệ thống module mở hết package cho agent; khi cần instrument classes trong named modules, có thể phải dùng `Instrumentation.redefineModule`/open packages theo policy.

Cả hai engines khi nhận `classfileBuffer` phải:

- **Không mutate** mảng đầu vào do JVM cấp.
- Trả `null` khi không thay đổi class.
- Trả **mảng output mới** có bytes class file hợp lệ khi thực sự transform.
- Không instrument chính logger/transformer helpers gây recursive loading.
- Kiểm soát version target, loaders, frames, branch targets, exception handlers, constructor semantics.
- Xem xét thứ tự transformers và retransform/redefine constraints (không tự ý thêm fields/methods khi VM không cho phép).
- Không giả định output “same hash” dù logic tương đương: constant pool/method ordering/attributes có thể khác.

Một nguồn lỗi deployment phổ biến là **shading ASM** mà không test relocation hoặc bỏ mất dependency `asm-commons`/`asm-util` cần thiết. Những package không đi cùng JAR có thể gây `NoClassDefFoundError` trong `premain`/transformer.

## 10. Năm lớp tương thích phải kiểm tra riêng

| Lớp tương thích | Câu hỏi | Ví dụ lỗi |
| --- | --- | --- |
| **1. Tool runtime API** | JDK chạy inspector/agent có `java.lang.classfile` hay ASM dependency? | `NoClassDefFoundError: java/lang/classfile/ClassFile` |
| **2. Bytecode version của tool** | JVM chạy tool nạp được `Inspector.class` major bao nhiêu? | `UnsupportedClassVersionError` khi agent compiled 24 chạy JDK17 |
| **3. Input format** | Parser hỗ trợ major/attributes/opcodes của target class file? | ASM cũ báo unsupported class file major |
| **4. Output class format** | Bytes được tạo có version, frames, references và class structure hợp lệ với target runtime? | `ClassFormatError`, `VerifyError` |
| **5. Packaging/loader** | Agent entrypoint, dependencies, MR-JAR resolution, module visibility đúng? | `ClassNotFoundException` / `NoClassDefFoundError` |

Cần phân biệt **“tool đọc được class file mới”** với **“JVM cũ chạy được class file mới”**. ASM 9.9 có thể parse bytes major cao trong một tool đang chạy Java17 nếu thư viện hỗ trợ, nhưng VM Java17 vẫn không thể định nghĩa class có major vượt 61.

### 10.1. Kiểm tra class-file header

`.class` bắt đầu bằng:

```text
u4 magic             0xCAFEBABE
u2 minor_version
u2 major_version
u2 constant_pool_count
...
```

Muốn xem major thật của một class:

```bash
javap -verbose -classpath target/classes demo.Sample
```

Tìm dòng `major version: 61` trong output, vì mẫu được Maven compiler với `--release 17`. Không lấy `java -version` của lệnh inspector làm version của file đang đọc.

Đối với class file được sinh/transform, nên lưu riêng **input major** và **output major** trong log QA. Nếu output target Java17 bất ngờ có major68, build pipeline đã chọn sai target hoặc transform không bảo toàn chính sách version.

## 11. Kiểm thử mô-đun và chương trình trên nhiều JDK

Một ma trận QA thực tế:

| Ca | JVM chạy tool | Input class | Kỳ vọng |
| --- | --- | --- | --- |
| ASM Java17 | JDK17 | Java17 major61 | Parse và in metadata đúng |
| ASM Java17 | JDK21 | Java17 major61 | Có thể chạy với ASM dependency đúng |
| ASM Java17 | JDK24 | Java17 major61 | Kết quả metadata tương đương |
| Class-File API | JDK24 | Java17 major61 | Parse và in metadata đúng |
| Class-File API | JDK24 | Java24 major68 | Parse khi class file hợp lệ |
| Class-File API class major68 | JDK17 | Java17 major61 | **Tool không load được**: `UnsupportedClassVersionError` |
| ASM cũ | JDK17 | Class major mới quá mức hỗ trợ | Parser từ chối; nâng version ASM |
| Agent dùng new bytecode output | JVM đích được cam kết | Class file transformed | JVM verifier, behavior và loading đều phải pass |

Lưu ý kết quả của lab Java 17 trên JDK 24 vẫn in **major61** nếu input `Sample.class` được Maven tạo với `release=17`. Đó là mục tiêu kiểm tra đúng.

### 11.1. Tách bài test theo mức

**Mức 1 — Parser test:** input `.class` khác versions, kiểm tra tên, method descriptors, attributes. Từ code có lazy parsing, phải traverse những phần sử dụng để phát hiện lỗi muộn.

**Mức 2 — Structural diff:** ánh xạ methods theo **name + descriptor**, CP entries theo symbolic references (không dùng raw index). Nếu hai engines output khác thứ tự field/method/constant pool, không vội kết luận ngữ nghĩa khác.

**Mức 3 — Bytecode verification:** `ClassFile.verify(...)` trên JDK24 hoặc `CheckClassAdapter` của ASM (khi thêm `asm-util`), cùng việc **load output trên JVM đích**. Lỗi stack maps, max locals, branch offsets có thể chỉ xuất hiện khi class được verify.

**Mức 4 — Behavioral tests:** so return values, exceptions, side effects, concurrency, class loader boundaries và agents đang chạy cùng lúc. Một verifier pass không chứng minh instrumentation logic đúng.

**Mức 5 — Deployment tests:** chạy `-javaagent` từ production launch script trên toàn bộ JDK matrix, kiểm tra classloaders, module rules, dependencies, startup failures và restart/rollback.

## 12. Lỗi điển hình và cách xử lý

| Triệu chứng | Nguyên nhân | Hướng xử lý |
| --- | --- | --- |
| `package java.lang.classfile does not exist` | Dùng compiler JDK≤21 hoặc `--release 17/21` | Dùng JDK24+ và `--release 24` cho implementation modern |
| `ClassFile` bị báo preview | Đang dùng JDK22/23 | Dùng flags phù hợp đúng release, hoặc lên JDK24+ |
| `UnsupportedClassVersionError` khi chạy modern tool trên JDK17 | Class tool major68 > JVM target61 | Chọn ASM fallback JAR hoặc nâng runtime |
| `NoClassDefFoundError: java/lang/classfile/ClassFile` | Runtime thiếu API chuẩn | Không dùng Java24 implementation trên JDK17/21 |
| ASM `Unsupported class file major version` | ASM quá cũ so với input | Nâng ASM theo official compatibility/releases |
| `ClassFormatError` | Output malformed, sai CP/attributes | Parse/write bằng API phù hợp, kiểm tra bytes |
| `VerifyError` | Stack maps, operand stack, handler ranges sai | Tính lại frames và verify trên target JVM |
| `ClassNotFoundException` của inspector/agent | Sai path, manifest hoặc classloader | Kiểm tra JAR entries và `Premain-Class` |
| `NoSuchMethodError` sau nâng engine | API version/library conflict hoặc code preview cũ | Ghim đúng dependencies và kiểm tra linkage |
| `NoClassDefFoundError: org/objectweb/asm/...` | Không bundle ASM hoặc classloader không nhìn thấy | Package dependency, shade/relocate theo policy |
| `IllegalArgumentException` khi parse | Class file lỗi/unsupported version hoặc lazy accessor | Xác định getter/opcode gây lỗi, kiểm tra input |
| MR-JAR chọn nhầm implementation | Thiếu `Multi-Release: true`, sai path hoặc custom loader | `jar --validate`, inspect manifest, test từng JDK |
| `Premain-Class` target compiled JDK24 | Bootstrap không chạy JDK17 | Build root bootstrap `--release 17` |
| Output class chạy trên JDK24 nhưng fail JDK17 | Major/API reference/instructions không tương thích | Verify và chạy regression tests trên JDK17 thật |
| Ghi đè input `classfileBuffer` | Vi phạm hợp đồng ClassFileTransformer | Parse input read-only, output bytes mới, `return null` nếu không đổi |
| Agent chạy lặp rồi hook nhân đôi | Transformer thiếu idempotency | Phân tích hook symbols, tests retransform nhiều lượt |
| Agent/ASM xung đột thư viện | Package/module/shade versions khác | Isolation/relocation, integration tests startup |
| `javap` thiếu method | Nhìn nhầm JAR/classpath hoặc class loader | Ghi snapshot input/output đúng stage, dùng `javap -classpath` |
| Java17 có ASM vẫn không load được major68 | Parser khác với JVM verifier/loader | Chỉ đọc offline; target class phải tương thích Java17 |

**Đừng xử lý bằng cách đổi class-file major 68 thành 61 bằng sửa vài byte header.** Bytecode có thể sử dụng các cấu trúc không được Java17 hiểu, và method references có thể trỏ tới API không tồn tại. Đây là thao tác “hạ version giả”, không phải backport đúng.

## 13. Đóng gói có trách nhiệm: dependency, module và quyền runtime

### 13.1. Chọn Maven dependency rõ

Với ASM, sử dụng artifact/version được ghi trong `pom.xml` và kiểm tra SBOM/license. Nếu cần `AdviceAdapter`, thêm `asm-commons` cùng version tương thích; nếu cần `CheckClassAdapter`, thêm `asm-util`. Không tự trộn các ASM artifacts khác minor versions rồi cho rằng API luôn tương thích.

Nếu ứng dụng đã kéo một version ASM khác, cân nhắc shading/relocation **có kiểm thử**, nhất là khi Java agent được load chung với classpath application. Ngược lại, Java24 `java.lang.classfile` nằm trong `java.base`, không cần đóng một bản copy API vào JAR.

### 13.2. Module và classloader trong Java agent

Khi instrument classes từ named modules, chỉ vì agent có `Instrumentation` không có nghĩa module cho phép mọi reflective access. Nếu cần truy cập sâu, thiết kế `redefineModule`/opens/exports đúng phạm vi. Java agent helper class phải được load bởi đúng loader hoặc bridge loader nếu instrument bootstrap/system classes; tránh dependencies không hiện diện khi JVM define target.

Tại runtime thấp, đừng để Java17 bootstrap tham chiếu trực tiếp modern engine compiled major68 qua static fields, superclass, signatures hoặc eager service-loading. Việc tách chỉ bằng `if` không phải luôn đủ vì class verification/linkage có thể xảy ra trước khi nhánh được quyết định.

### 13.3. Kiểm tra artifact phát hành

Với JAR/MR-JAR và class files:

```bash
jar tf agent-legacy.jar
jar tf agent-modern.jar
jar --validate --file inspector-mr.jar
javap -verbose -classpath target/classes demo.Sample
```

Đây là **các lệnh minh họa**; các tên `agent-legacy.jar`/`agent-modern.jar`/`inspector-mr.jar` chỉ tồn tại sau khi bạn xây các artifacts tương ứng. `jar tf` cho thấy JAR entries, `jar --validate` kiểm tra nhiều ràng buộc MR-JAR, `javap -verbose` xem class-file major. **Không** coi `jar --validate` đủ chứng minh agent khởi động được trên mọi JDK.

### 13.4. Tránh “chạy một engine trên mọi JDK” bằng suy đoán

Đặt compatibility policy theo **runtime baseline thực tế**:

```text
Runtime deployment matrix
  Java 17/21:
      Java17 bootstrap + ASM engine
      code target release 17
  Java 24+:
      Java24 Class-File API engine
      output target release theo workload
  Common:
      method signatures, normal/error behavior,
      output class verification, module/access rules
```

Đây là sơ đồ chiến lược, không phải lệnh shell. Trong ứng dụng phải hỗ trợ cả hai, build riêng, test riêng và rollout có khả năng rollback. Nếu kỳ vọng JDK24+ nhưng đang thực chạy JDK17 trong container, sửa **runtime image/launcher config hoặc chọn legacy artifact**; đừng chỉ thay `JAVA_HOME` của terminal developer.

## 14. Bảo mật và vận hành agent

Một Java agent được nạp khi startup chạy với quyền của JVM process và có thể làm thay đổi class definitions. Các biện pháp cần thiết:

- Chỉ dùng artifacts đáng tin, khóa checksum/signature/source và kiểm tra supply chain.
- Không ghi arguments, secrets hoặc toàn bộ input bytes vào log production nếu không cần.
- Giới hạn instrumentation targets; không chèn hook vào logger/agent support classes làm recursive class loading.
- Kiểm tra các callback path trên Java17 và Java24+, đặc biệt retransform, exception exits, constructors.
- Quan sát CPU/memory/GC overhead của parser, frame computation và bytecode transforms.
- Không nạp agent không tương thích vào JVM production chỉ để thử; luôn test trên environment tương đương.
- Tách kiểm thử bytecode format khỏi kiểm thử business behavior và rollback.
- Khi auto-upgrade JDK, nâng/test ASM version nếu có, không suy “JDK mới sẽ làm ASM cũ đọc được bytecode mới”.

## 15. Checklist quyết định

- [ ] Xác minh **JVM hiện chạy tool/agent** (không chỉ máy build).
- [ ] Nếu runtime Java24+, cân nhắc `java.lang.classfile` stable.
- [ ] Nếu runtime thấp hơn Java24, chọn ASM/Byte Buddy version tương thích.
- [ ] Nếu là JDK22/23 preview, áp dụng đúng preview flags và chấp nhận thay đổi API.
- [ ] Kiểm tra Java tool class major và API references; không “ép `--release 17`” cho mã gọi API Java24.
- [ ] Kiểm tra input class major, unsupported attributes/opcodes và ASM/JDK parser support.
- [ ] Xác định output class major và runtime mà output phải được JVM load.
- [ ] Với output cho Java17, test trên Java17 JVM thật; không chỉ verify bằng JDK24.
- [ ] Chọn một artifact modern, hai artifacts hoặc MR-JAR theo chi phí vận hành.
- [ ] Nếu MR-JAR, root bootstrap phải tương thích JDK baseline và manifest phải có `Multi-Release: true`.
- [ ] Kiểm tra ASM dependencies, relocation/shading, Java agent classloader và JPMS visibility.
- [ ] Với transformer, không sửa `classfileBuffer` và xử lý `return null` đúng contract.
- [ ] Test load/retransform/redefine, exception paths, class schema constraints và idempotency.
- [ ] Chạy regression tests trên matrix JDK, vendor/OS và module/classloader cases.
- [ ] Ghi rõ điều gì là kiểm tra source, unit tests, verifier, và behavior runtime.

## 16. Câu hỏi tự kiểm tra

1. **JDK 21 có `java.lang.classfile` API chuẩn không?**  
   Không. Dùng ASM/Byte Buddy hoặc nâng tool runtime.

2. **JDK 22 có thể dùng Class-File API hoàn toàn như JDK 24 không?**  
   Không. JDK22 là preview JEP457; JDK23 là preview JEP466; JDK24 mới final JEP484.

3. **Vì sao tool compiled `--release 24` không chạy trong Java17?**  
   Nó có class-file major68; JVM17 không hỗ trợ major đó, đồng thời `java.lang.classfile` không có trong Java17.

4. **Tool JDK24 parse input major61 được không?**  
   Có, với class file hợp lệ và API hỗ trợ; version input không bắt buộc bằng version tool.

5. **ASM chạy trên JDK17 có thể đọc class file từ Java24 không?**  
   Nếu ASM version hỗ trợ format mới thì có thể **parse offline**, nhưng JVM17 vẫn không thể định nghĩa class major68.

6. **`-javaagent` JAR có `Premain-Class` built Java24, chạy JVM17 được không?**  
   Không. Entry class phải load trước khi main; cần root bootstrap tương thích Java17 hoặc artifact legacy.

7. **`javac --release 17` từ JDK24 có cho import `java.lang.classfile`?**  
   Không. Release17 API surface không có package này.

8. **Có phải Class-File API chuẩn không cần test bytecode verifier nữa?**  
   Không. Build/transform đúng cấu trúc không chứng minh đúng behavior hay target runtime compatibility.

9. **Hai engines in ra cùng methods có chứng minh class output semantics giống mọi input không?**  
   Không. Đây mới là metadata inspection; cần code/attribute checks và behavioral tests.

10. **Trong MR-JAR, `META-INF/versions/24` có được chọn trên Java17?**  
    Không theo quy tắc MR-JAR chuẩn; Java17 dùng root baseline implementation.

11. **Đặt modern class dưới `META-INF/versions/24` nhưng quên `Multi-Release: true` thì sao?**  
    Runtime bình thường không chọn nó như bản thay thế theo MR-JAR rules.

12. **Tại sao không import `jdk.internal.org.objectweb.asm` trên Java17 để đỡ dependency?**  
    Đây là implementation JDK nội bộ, không có cam kết tương thích và bị module encapsulation.

13. **Output class major61 đủ chứng minh tương thích Java17?**  
    Chưa. Cần kiểm tra instructions, metadata, references đến Java APIs và chạy test trên JVM17.

14. **Nếu target Java17, có được dùng JDK24 để build/transform không?**  
    Có thể, nhưng output bytes phải thực sự hợp lệ/không gọi API mới và vượt tests trên Java17.

15. **ASM dependency được đưa vào Maven build nhưng thiếu ở agent JAR lúc chạy, lỗi gì?**  
    Có thể là `NoClassDefFoundError` đối với `org/objectweb/asm/...`, tùy quá trình load.

16. **Khi chạy `mvn compile exec:java`, kết quả `MAJOR=61` nói về gì?**  
    Class file `Sample.class` được biên dịch bởi release17, không phải major của JDK đang chạy Maven.

17. **Tại sao chia hai artifacts thường dễ hơn MR-JAR?**  
    Mỗi bản có compiler/runtime/dependency/premain rõ ràng; MR-JAR phải giữ binary contracts và versioned layout phức tạp.

18. **Nếu JVM mới có Class-File API, có còn lý do dùng Byte Buddy không?**  
    Có. Byte Buddy cung cấp API cấp cao cho intercept/generation, tích hợp agent và abstraction; chọn theo nhu cầu và compatibility.

## 17. Tài liệu tham khảo

1. **JEP 457 — Class-File API (Preview), JDK 22**: https://openjdk.org/jeps/457
2. **JEP 466 — Class-File API (Second Preview), JDK 23**: https://openjdk.org/jeps/466
3. **JEP 484 — Class-File API (Final), JDK 24**: https://openjdk.org/jeps/484
4. **Oracle JDK 24 — `java.lang.classfile` package**: https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/classfile/package-summary.html
5. **Oracle JDK 24 — `ClassFile`**, `of`, `parse`, `build`, `transformClass`, `verify`: https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/classfile/ClassFile.html
6. **Oracle JDK 24 — `ClassModel`, `ClassTransform`, `ClassBuilder.withVersion`**: https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/classfile/ClassModel.html
7. **Oracle — `javac --release`**: https://docs.oracle.com/en/java/javase/24/docs/specs/man/javac.html
8. **ASM official versions**, class file format support: https://asm.ow2.io/versions.html
9. **ASM public site**: https://asm.ow2.io/
10. **Byte Buddy docs**: https://bytebuddy.net/
11. **Oracle JDK 17 — `ClassFileTransformer` contract**: https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html
12. **Oracle JDK 17 — `java.lang.instrument` agent manifest/startup**: https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/package-summary.html
13. **Oracle — Multi-Release JAR format (`JAR File Specification`)**: https://docs.oracle.com/en/java/javase/24/docs/specs/jar/jar.html
14. **JVMS — ClassFile format and major version**: https://docs.oracle.com/javase/specs/jvms/se24/html/jvms-4.html

**Kết luận:** Class-File API trong `java.lang.classfile` là lựa chọn tự nhiên khi **tool/agent runtime là JDK 24+** và bạn muốn typed bytecode APIs không lệ thuộc thư viện ngoài. Khi phải chạy trực tiếp trên **JDK 17/21**, dùng một engine ASM/Byte Buddy tương thích hoặc tách triển khai; không cố “hạ `--release`” cho code tham chiếu API chỉ có trên JDK24. Luôn kiểm tra **tool runtime, class version của tool, class version của input, output target và packaging/classloader** như năm tầng tương thích độc lập.
