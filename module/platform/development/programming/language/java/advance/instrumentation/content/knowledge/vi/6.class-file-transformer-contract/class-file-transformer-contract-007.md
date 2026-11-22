# Không sửa trực tiếp `classfileBuffer` do JVM cung cấp

**Chủ đề:** Java Advance → Instrumentation → **Hợp đồng transformer**.

Một `ClassFileTransformer` nhận mảng byte `classfileBuffer` đại diện cho **class file đầu vào ở lần callback hiện tại**. Mảng này được JVM hoặc transformer đứng trước cung cấp; nó **không thuộc quyền sửa tại chỗ** của transformer hiện tại. Hợp đồng Java quy định rõ:

- **Không thay đổi bất kỳ phần tử nào** trong `classfileBuffer`.
- Nếu **không cần biến đổi**, trả về **`null`**.
- Nếu **cần biến đổi**, tạo **một mảng `byte[]` mới**, chứa **class file hợp lệ** với các chỉnh sửa mong muốn, rồi trả mảng mới đó.

Quy tắc này được ghi trong Javadoc của `java.lang.instrument.ClassFileTransformer`, áp dụng cả callback khi **load**, **redefine** và **retransform**. Vi phạm có thể làm sai dữ liệu đầu vào của transformer kế tiếp, tạo kết quả khó tái lập và khiến quá trình class loading gặp lỗi; việc đôi khi “chạy được” không làm thao tác đó trở thành hợp lệ.

## 1. `classfileBuffer` là gì và thuộc về ai?

Khi một Java agent được đăng ký qua `Instrumentation.addTransformer(...)`, JVM gọi phương thức `transform` trước khi áp dụng định nghĩa lớp. Trên Java 9+, giao diện có hai overload: bản năm tham số truyền thống và bản sáu tham số có thêm `Module`. Chúng đều dùng kiểu `byte[] classfileBuffer`.

Dạng sáu tham số của Java 17+:

```java
@Override
public byte[] transform(
        Module module,
        ClassLoader loader,
        String className,
        Class<?> classBeingRedefined,
        ProtectionDomain protectionDomain,
        byte[] classfileBuffer)
        throws IllegalClassFormatException {
    // Chỉ đọc classfileBuffer; trả null hoặc mảng output mới.
    return null;
}
```

**Đây chỉ là fragment method**, không phải chương trình có thể biên dịch độc lập. `ClassFileTransformer`, `ProtectionDomain` và `IllegalClassFormatException` cần các import tương ứng trong class triển khai.

Ý nghĩa từng tham số:

| Tham số | Ý nghĩa |
| --- | --- |
| `module` | Module chứa lớp đang xử lý; khi có JPMS giúp nhận biết ngữ cảnh module |
| `loader` | Defining `ClassLoader`; **có thể `null`** với bootstrap loader |
| `className` | Tên nội bộ như `com/example/Service` (dùng dấu `/`); kiểm tra `null` trong code phòng vệ |
| `classBeingRedefined` | `null` khi định nghĩa mới; có thể là đối tượng `Class<?>` ở redefine/retransform |
| `protectionDomain` | Ngữ cảnh bảo vệ của lớp; không phải bằng chứng mảng đầu vào được phép chỉnh sửa |
| `classfileBuffer` | Bytes class file đầu vào, **chỉ được đọc**, do pipeline cung cấp |

Dù `byte[]` là kiểu **mutable** trong Java, API **không** trao quyền sửa. “Có thể gọi `array[0] = ...`” là khả năng kỹ thuật của Java, còn “được phép gọi” do **hợp đồng API** quyết định. Đây là một ví dụ về *quy ước ownership* trong API: tham chiếu có thể quan sát được không có nghĩa caller sở hữu vùng dữ liệu đó.

### 1.1. JVM cấp dữ liệu từ đâu?

Trong Javadoc, dữ liệu đưa tới transformer đầu tiên phụ thuộc thao tác:

1. **New class definition:** bytes được truyền đến `ClassLoader.defineClass` (hoặc đường native tương ứng).
2. **Redefinition:** bytes được đưa vào `ClassDefinition` của `Instrumentation.redefineClasses`.
3. **Retransformation:** dựa trên bytes ban đầu hoặc lần redefinition gần nhất, đồng thời các biến đổi từ transformer không có khả năng retransform được áp dụng lại theo quy tắc của VM.

Điều này **không** bảo đảm `classfileBuffer` luôn trùng với bytes nằm trên đĩa hoặc trùng bytes đã thấy ở callback trước đó. Nếu có nhiều transformers, input của transformer sau có thể chính là **output mới** từ transformer trước.

## 2. Transformer được nối chuỗi như thế nào?

Giả sử một lớp đi qua ba transformer A, B, C:

```text
B0: bytes đầu vào JVM
  │
  ▼
A.transform(B0) ──► trả B1 (mảng mới)
                      │
                      ▼
                 B.transform(B1) ──► trả null
                                      │
                                      ▼
                                 C.transform(B1) ──► trả B2 (mảng mới)
                                                       │
                                                       ▼
                                                  JVM dùng B2
```

- **A** thay đổi class và trả `B1` mới. B nhận `B1`, không buộc phải nhận `B0`.
- **B** không đổi gì và trả `null`. Pipeline giữ lại bytes đầu vào `B1` cho bước tiếp theo.
- **C** đọc `B1` rồi tạo `B2`, JVM xử lý `B2` theo luật kiểm tra/class loading.

**Nếu B lén sửa `B1` tại chỗ rồi trả `null`**, kết quả không còn phản ánh đúng “B không biến đổi”, có thể phá tính độc lập và khả năng so sánh của các giai đoạn. Đặc biệt, mảng input có thể là mảng đã được một transformer trước đó xuất ra; hợp đồng không cho B lấy quyền sở hữu mảng ấy.

Khi có nhiều transformers, trình tự được đặc tả theo nhóm: transformer Java không hỗ trợ retransform, transformer native không hỗ trợ retransform, transformer Java hỗ trợ retransform, rồi transformer native hỗ trợ retransform; trong từng nhóm, thứ tự đăng ký được giữ. Ở lần **retransformation**, nhóm không hỗ trợ retransform **không được gọi lại** theo cách thông thường: kết quả trước đây của chúng được tái sử dụng theo quy định. Vì vậy không được suy luận rằng callback luôn xử lý bytes gốc của một lần load.

## 3. Những dòng code sai thường gặp

### 3.1. Gán alias rồi tưởng là đã copy

```java
byte[] output = classfileBuffer;
output[10] = 42;         // SAI: đang sửa chính input
return output;           // Cũng trả cùng tham chiếu input
```

**Fragment mô tả lỗi**, tuyệt đối không dùng làm transformer thật. Trong Java, phép gán tham chiếu `byte[]` **không sao chép phần tử**. `output == classfileBuffer` là `true`.

### 3.2. Sửa trực tiếp rồi trả `null`

```java
classfileBuffer[10] = 42;  // SAI: vi phạm input read-only
return null;               // Trả null KHÔNG hợp thức hóa mutation
```

Nếu sửa sai byte của một class file, có thể còn tạo `ClassFormatError`/`VerifyError`. Kể cả tình cờ đổi một byte có ý nghĩa mà chương trình vẫn chạy, cách làm vẫn sai theo hợp đồng.

### 3.3. Các view hoặc API khác cũng có thể sửa cùng mảng

```java
ByteBuffer view = ByteBuffer.wrap(classfileBuffer);
view.put(10, (byte) 42);  // SAI: backing array vẫn là classfileBuffer
```

Đây cũng là **fragment mô tả lỗi**, cần `import java.nio.ByteBuffer;` nếu biên dịch. `ByteBuffer.wrap` chỉ tạo view lên mảng hiện có; nó không tạo bản sao. Tương tự, hàm helper nhận cùng array có thể sửa phần tử dù mã gọi helper không trực tiếp ghi `classfileBuffer[index]`.

### 3.4. “Không sửa tại chỗ” không có nghĩa “được trả bytes bất kỳ”

```java
byte[] output = classfileBuffer.clone();
output[10] = 42;  // Có thể tạo class file KHÔNG hợp lệ!
return output;
```

Đây là **minh họa tách ownership** chứ không phải một thuật toán biến đổi class file an toàn. `clone()` làm input không bị sửa, nhưng ghi vào offset tùy ý có thể phá constant pool, instruction operand, checksum của metadata hoặc class structure. Việc sinh output hợp lệ còn cần parser/writer và kiểm chứng riêng.

## 4. Ví dụ Java 17+ nhỏ nhất: khác biệt giữa alias và copy

Lưu chương trình độc lập dưới tên **`ArrayOwnershipDemo.java`**:

```java
import java.util.Arrays;

public final class ArrayOwnershipDemo {
    private ArrayOwnershipDemo() {}

    public static void main(String[] args) {
        byte[] input = {1, 2, 3};

        byte[] alias = input;
        System.out.println("alias-same=" + (alias == input));

        byte[] output = Arrays.copyOf(input, input.length);
        output[1] = 9;

        System.out.println("new-array=" + (output != input));
        System.out.println("input=" + Arrays.toString(input));
        System.out.println("output=" + Arrays.toString(output));
    }
}
```

Chạy với JDK 17 trở lên:

```bash
javac ArrayOwnershipDemo.java
java ArrayOwnershipDemo
```

Stdout **chính xác**:

```text
alias-same=true
new-array=true
input=[1, 2, 3]
output=[1, 9, 3]
```

Ví dụ dùng mảng **dữ liệu tùy ý, không phải class file**. Nó minh họa được **khác object identity** và **không ảnh hưởng input**, nhưng **không chứng minh** rằng sửa một byte tùy ý trong class file là hợp lệ. Đối với transformer, nguyên tắc copy cần đi cùng quá trình **parse → transform → emit** class file hợp chuẩn.

## 5. Mẫu đúng của `ClassFileTransformer`

Ở mức logic, transformer thường có cấu trúc:

```text
transform(metadata, classfileBuffer)
    nếu không phải lớp cần biến đổi:
        return null
    đọc classfileBuffer bằng parser, KHÔNG ghi vào input
    tạo output mới bằng bytecode writer
    nếu output hợp lệ và có sửa đổi:
        return output
    nếu không có thay đổi:
        return null
```

Đây là **pseudocode** để hiểu luồng quyết định. `null` là tín hiệu rõ nhất khi lớp không cần thay đổi; không cần tạo bản `clone` vô ích cho mỗi lớp JVM tải. Bộ giải mã nên xác định **đúng class name, loader/module, method descriptor và giai đoạn load/retransform**, tránh áp dụng nhầm cho mọi class.

Một cách an toàn là dùng **ASM `ClassReader`** để đọc bytes đầu vào và **ASM `ClassWriter`** để xuất mảng mới bằng `toByteArray()`. Parser và writer bảo đảm thao tác với **cấu trúc class file**, thay vì viết đè byte theo offset đoán trước. Dù vậy, vẫn phải bảo đảm stack effects, frames, constant pool, exception handler và giới hạn redefine hợp lệ.

## 6. Ví dụ agent chạy được trên Java 17+: biến đổi thật mà không sửa input

Ví dụ này dùng **Apache Maven** và **ASM 9.7.1** để thêm một lệnh in log ở đầu phương thức `Greeter.message()`. Transformer chỉ đọc `classfileBuffer`, sinh mảng output mới, rồi tự kiểm tra rằng nội dung input không đổi.

Cấu trúc thư mục:

```text
safe-buffer-agent/
├── pom.xml
└── src/main/java/
    ├── lesson/agent/ProbeAgent.java
    ├── lesson/agent/SafeBufferTransformer.java
    └── lesson/app/
        ├── Greeter.java
        └── Main.java
```

### 6.1. `pom.xml`

POM dưới đây dùng Java 17, ASM để đọc/ghi bytecode và Maven Shade Plugin để gói dependency ASM vào JAR agent. `Premain-Class` trong manifest chỉ tới entry point được chạy khi `-javaagent` khởi động.

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>lesson</groupId>
    <artifactId>safe-buffer-agent</artifactId>
    <version>1.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.ow2.asm</groupId>
            <artifactId>asm</artifactId>
            <version>9.7.1</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-shade-plugin</artifactId>
                <version>3.6.0</version>
                <executions>
                    <execution>
                        <phase>package</phase>
                        <goals>
                            <goal>shade</goal>
                        </goals>
                        <configuration>
                            <createDependencyReducedPom>false</createDependencyReducedPom>
                            <transformers>
                                <transformer implementation="org.apache.maven.plugins.shade.resource.ManifestResourceTransformer">
                                    <manifestEntries>
                                        <Premain-Class>lesson.agent.ProbeAgent</Premain-Class>
                                    </manifestEntries>
                                </transformer>
                            </transformers>
                        </configuration>
                    </execution>
                </executions>
            </plugin>
        </plugins>
    </build>
</project>
```

### 6.2. Lớp ứng dụng

Lưu **`src/main/java/lesson/app/Greeter.java`**:

```java
package lesson.app;

public final class Greeter {
    public String message() {
        return "hello";
    }
}
```

Lưu **`src/main/java/lesson/app/Main.java`**:

```java
package lesson.app;

public final class Main {
    private Main() {}

    public static void main(String[] args) {
        System.out.println("message=" + new Greeter().message());
    }
}
```

### 6.3. Entry point của agent

Lưu **`src/main/java/lesson/agent/ProbeAgent.java`**:

```java
package lesson.agent;

import java.lang.instrument.Instrumentation;

public final class ProbeAgent {
    private ProbeAgent() {}

    public static void premain(String arguments, Instrumentation instrumentation) {
        instrumentation.addTransformer(new SafeBufferTransformer());
    }
}
```

Đây là agent **startup**. `addTransformer` không có `canRetransform=true`, vì ví dụ chỉ xử lý lớp khi lần đầu được định nghĩa; không cần trigger `retransformClasses` hoặc attach vào JVM đang chạy.

### 6.4. Transformer đọc input và sinh output mới

Lưu **`src/main/java/lesson/agent/SafeBufferTransformer.java`**:

```java
package lesson.agent;

import java.lang.instrument.ClassFileTransformer;
import java.security.ProtectionDomain;
import java.util.Arrays;
import org.objectweb.asm.ClassReader;
import org.objectweb.asm.ClassVisitor;
import org.objectweb.asm.ClassWriter;
import org.objectweb.asm.MethodVisitor;
import org.objectweb.asm.Opcodes;

public final class SafeBufferTransformer implements ClassFileTransformer {
    @Override
    public byte[] transform(
            Module module,
            ClassLoader loader,
            String className,
            Class<?> classBeingRedefined,
            ProtectionDomain protectionDomain,
            byte[] classfileBuffer) {

        if (!"lesson/app/Greeter".equals(className)) {
            return null;
        }

        // Bản sao CHỈ để chứng minh JVM input không bị thay đổi.
        byte[] before = Arrays.copyOf(classfileBuffer, classfileBuffer.length);

        // Reader chỉ đọc input; Writer tích lũy định nghĩa class mới.
        ClassReader reader = new ClassReader(classfileBuffer);
        ClassWriter writer = new ClassWriter(
                reader, ClassWriter.COMPUTE_MAXS | ClassWriter.COMPUTE_FRAMES);

        ClassVisitor visitor = new ClassVisitor(Opcodes.ASM9, writer) {
            @Override
            public MethodVisitor visitMethod(
                    int access, String name, String descriptor,
                    String signature, String[] exceptions) {

                MethodVisitor downstream = super.visitMethod(
                        access, name, descriptor, signature, exceptions);

                if (downstream == null
                        || !"message".equals(name)
                        || !"()Ljava/lang/String;".equals(descriptor)) {
                    return downstream;
                }

                return new MethodVisitor(Opcodes.ASM9, downstream) {
                    @Override
                    public void visitCode() {
                        super.visitCode();
                        super.visitFieldInsn(
                                Opcodes.GETSTATIC,
                                "java/lang/System",
                                "out",
                                "Ljava/io/PrintStream;");
                        super.visitLdcInsn("agent-enter");
                        super.visitMethodInsn(
                                Opcodes.INVOKEVIRTUAL,
                                "java/io/PrintStream",
                                "println",
                                "(Ljava/lang/String;)V",
                                false);
                    }
                };
            }
        };

        reader.accept(visitor, ClassReader.EXPAND_FRAMES);
        byte[] output = writer.toByteArray();

        // Hai kiểm tra tách biệt: nội dung đầu vào và identity của output.
        boolean unchanged = Arrays.equals(before, classfileBuffer);
        boolean distinct = output != classfileBuffer;
        System.out.println("input-unchanged=" + unchanged);
        System.out.println("new-output-array=" + distinct);

        return output;
    }
}
```

**Vì sao ví dụ tuân thủ hợp đồng?**

- Chỉ xử lý `lesson/app/Greeter`; với các lớp khác, trả `null` ngay mà không clone toàn bộ bytes.
- `before` là **mảng snapshot riêng** để so sánh phục vụ bài học; không được dùng làm bằng chứng rằng có thể sửa input. Không cần snapshot này trong transformer production nếu thư viện đã được kiểm soát.
- `ClassReader` đọc `classfileBuffer` nhưng không ghi lên nó; `ClassWriter.toByteArray()` tạo **output class file mới**.
- Mỗi biến là local trong callback, không dùng chung mảng scratch giữa các thread. `output != classfileBuffer` chứng minh object identity khác, còn `Arrays.equals` kiểm tra nội dung input không bị thay đổi trong lần xử lý này. Hai điều kiện **khác nhau**.
- Chèn `getstatic System.out`, `ldc "agent-enter"` và `invokevirtual PrintStream.println(String)` vào đầu phương thức `message()`; khi println kết thúc, operand stack trở lại trạng thái như đầu method.
- `COMPUTE_MAXS | COMPUTE_FRAMES` yêu cầu ASM tính lại stack limits và stack-map frames. Ở ví dụ đơn giản không có nhánh, code dễ kiểm chứng. Với code phức tạp, tính frames còn có thể cần class hierarchy/class loader chính xác.
- Output hợp lệ vẫn có thể bị verifier từ chối nếu transformer viết opcode sai ở tình huống khác; không được hiểu `toByteArray()` là phép chứng minh ngữ nghĩa hoàn toàn đúng.
- `System.out.println` ngay trong transformer chỉ phục vụ **bài lab**. Với agent production, cần tránh I/O nặng, tái nhập class loading, lock, cấp phát lớn hoặc biến đổi nhầm các lớp nền tảng.

### 6.5. Biên dịch, chạy và quan sát stdout

Mở terminal trong thư mục `safe-buffer-agent`, bảo đảm có **JDK 17+** và Maven:

```bash
java -version
mvn -version
mvn -q -DskipTests package
```

Lệnh package tạo JAR có ASM và `Premain-Class` tại **`target/safe-buffer-agent-1.0.jar`** theo cấu hình Maven ở trên. Chạy **không dùng agent**:

```bash
java -cp target/classes lesson.app.Main
```

Stdout chính xác của lệnh này:

```text
message=hello
```

Chạy **với agent**:

```bash
java -javaagent:target/safe-buffer-agent-1.0.jar -cp target/classes lesson.app.Main
```

Stdout kỳ vọng trong môi trường JDK/ASM phù hợp:

```text
input-unchanged=true
new-output-array=true
agent-enter
message=hello
```

Hai dòng đầu do callback `transform` in khi lớp `Greeter` đang được định nghĩa. Dòng `agent-enter` do **bytecode được chèn** trong phương thức `message` in. Dòng cuối chứng minh ứng dụng vẫn nhận đúng chuỗi `hello`. Nếu nạp agent thất bại, JDK có thể in thông báo lỗi khác thay vì các dòng trên; kiểm tra manifest, JAR, classpath và JDK thực tế.

**Phạm vi của kiểm tra:** `input-unchanged=true` chỉ cho biết code trong lần callback này không làm thay đổi nội dung buffer giữa thời điểm snapshot và lúc kiểm tra. `new-output-array=true` kiểm tra object identity. Chúng không thay thế validation class format, kiểm tra concurrency hay test cho mọi JVM/vendor.

### 6.6. Quan sát bytecode sau instrumentation

```bash
javap -classpath target/classes -c -p lesson.app.Greeter
```

Lệnh trên đọc **class trên đĩa (BEFORE)**; nó không tự thấy bản được agent biến đổi **trong bộ nhớ JVM**. Trong BEFORE, method `message` có logic đại ý `ldc "hello"` rồi `areturn`. Trong AFTER ở runtime, các opcode log (`getstatic` → `ldc "agent-enter"` → `invokevirtual println(String)`) xuất hiện trước logic trả `hello`.

Nếu cần so `javap` chính xác hai phiên bản, triển khai cơ chế **dump mảng `output` mới ra snapshot có kiểm soát** ở môi trường test, rồi chạy `javap` trên tệp AFTER. Không ghi đè classfileBuffer hoặc file BEFORE; không dựa vào `javap -c` trỏ đến `target/classes` để kết luận transformer chưa chạy. Trong production, tránh dump tất cả class ngay trong callback nếu chưa đánh giá tác động I/O, loader identity và dữ liệu nhạy cảm.

## 7. Vì sao `return null` là lựa chọn đúng khi không thay đổi?

Có thể tưởng rằng `return classfileBuffer;` hoặc `return classfileBuffer.clone();` cũng “không thay đổi”. Tuy nhiên:

| Hành vi | Ý nghĩa và đánh giá |
| --- | --- |
| `return null;` | **Đúng và ưu tiên** khi không có transform; báo pipeline giữ nguyên input |
| `return output;` với `output` là mảng mới hợp lệ | **Đúng** khi thực sự tạo kết quả biến đổi |
| `return classfileBuffer;` | Không nên dùng: không cung cấp mảng mới như hướng dẫn của API và làm mờ ownership/ý nghĩa “có transform” |
| `return classfileBuffer.clone();` khi bytes y nguyên | Không cần thiết: tạo cấp phát và tăng công việc của pipeline; `null` diễn tả ý định rõ ràng hơn |
| Sửa `classfileBuffer` rồi `return null` | **Sai hợp đồng** dù không trả output |
| Sửa `classfileBuffer` rồi trả mảng mới | **Vẫn sai hợp đồng** vì input đã bị ghi |
| Trả mảng mới nhưng không phải class file hợp lệ | **Sai** vì vi phạm yêu cầu output hợp lệ |

`null` là tín hiệu **không tạo phép biến đổi mới ở callback này**, không phải chỉ thị bắt pipeline bỏ qua mọi biến đổi của những transformer đã chạy trước đó.

## 8. Điều gì xảy ra khi lỗi trong `transform`?

Theo Javadoc, nếu callback ném ngoại lệ chưa xử lý, các transformer tiếp theo **vẫn được gọi** và quá trình load/redefine/retransform **vẫn được thử tiếp**; tác dụng của việc ném ngoại lệ tương đương trả `null` ở lượt đó. Nếu nghi ngờ input không phải class file hợp lệ, API cho phép ném `IllegalClassFormatException` để tăng khả năng logging/debug, nhưng ngoại lệ **không tự động hủy toàn bộ class loading**.

Vì vậy, trong production nên:

- Giới hạn đúng lớp cần instrument, kiểm tra kiểu dữ liệu và dependency của bytecode library.
- Nếu không biến đổi được do một điều kiện đã dự tính và muốn giữ nguyên lớp, trả `null` theo chính sách agent.
- Ghi lỗi có cấu trúc bằng kênh logging được chuẩn bị trước, nhưng tránh tạo vòng lặp class loading. Không dựa vào `throw` trong transformer như cơ chế “fail closed” tuyệt đối.
- Không cố giữ mảng `classfileBuffer` rồi sửa ở một thread khác sau callback. Hợp đồng chỉ cho phép **đọc buffer**, không chuyển quyền ghi sang thread hoặc callback tương lai.

**Một lỗi rất khó truy vết:** transformer A tạo output mới, transformer B sửa input của nó tại chỗ, sau đó transformer C ném exception. Khi đọc log, có thể tưởng C “làm hỏng class”, trong khi B đã vi phạm ownership từ trước. Khi debug, ghi dấu vết theo **class + loader + giai đoạn + transformer + hash/snapshot phù hợp**, tuyệt đối không dump dữ liệu ứng dụng bừa bãi.

## 9. Retransformation và redefinition cần lưu ý gì?

`Instrumentation.addTransformer(transformer, true)` đăng ký **retransformation-capable transformer** nếu JVM có hỗ trợ tương ứng; `false` hoặc overload một tham số không đăng ký theo dạng này.

- Khi `retransformClasses` được gọi, **không được giả định** buffer đầu vào là mảng mà transformer đã nhận ở lần load trước. JVM có thể tái cấu thành pipeline theo cơ chế retransform, với kết quả của các transformer không retransform-capable được tái sử dụng.
- Mỗi lần callback vẫn phải giữ `classfileBuffer` bất biến, tạo output mới khi cần và trả `null` khi không thay đổi.
- Không dùng object identity của `byte[]` để phát hiện đã instrument hay chưa. Muốn tránh chèn log hai lần, hãy thiết kế transformer idempotent dựa trên **nội dung class file, marker hợp lệ, hoặc pipeline kiểm soát được**, đồng thời xét chính sách retransform.
- `redefineClasses`/`retransformClasses` có các **hạn chế về thay đổi schema/hierarchy và bytecode hợp lệ** tùy JVM/capability. Một byte array tách biệt và well-formed chưa chắc được phép dùng để redefine một class đã load.
- Nhiều class loaders có thể định nghĩa cùng `className`. Nếu cache state, key chỉ bằng tên lớp là không đủ; chú ý module/loader identity, class unloading và thread safety.

Nguyên tắc ownership **không thay đổi** khi agent chạy lúc startup với `premain` hay được nạp động qua `agentmain`. Agent động có thêm ràng buộc attach/policy, nhưng cách callback được phép dùng `classfileBuffer` vẫn như nhau.

## 10. Checklist review một transformer

Trước khi đưa instrumentation vào pipeline, hãy rà soát:

1. **Đầu vào:** chỉ có thao tác đọc `classfileBuffer`; không có `classfileBuffer[index]=...`, `System.arraycopy(..., classfileBuffer, ...)`, `ByteBuffer.wrap(classfileBuffer).put(...)` hoặc alias/helper ghi đè input.
2. **Không đổi:** nếu không có thay đổi thực sự, trả `null`; nếu đã viết nội dung rồi mới quyết định không đổi, chỉ bỏ bản output do mình sở hữu.
3. **Có đổi:** output là `byte[]` độc lập, chứa class file hợp lệ do parser/writer sinh; không trả trực tiếp `classfileBuffer`.
4. **Đúng đối tượng:** kiểm tra class name dùng dấu `/`, method descriptor, class loader/module nếu có nhiều bản cùng tên, và giai đoạn load/redefine/retransform.
5. **Bytecode hợp lệ:** opcode, operand stack, `max_stack`, `max_locals`, `StackMapTable`, exception handlers và branch offsets phải đúng.
6. **An toàn vận hành:** tránh I/O blocking, recursive instrumentation, static mutable buffer, giữ reference đầu vào quá lâu hoặc ghi log thông tin nhạy cảm.
7. **Pipeline:** biết có transformer khác đứng trước/sau; không giả định input là class trên ổ đĩa; không dựa vào thứ tự nếu quy trình chưa xác định.
8. **Kiểm thử:** chạy ứng dụng thật với agent, quan sát hành vi, so class snapshot BEFORE/AFTER, kiểm tra verifier và kiểm thử retransform nếu hỗ trợ.
9. **Lỗi:** có chiến lược logging và bỏ qua hợp lệ; biết rằng exception trong transform có thể được JVM coi tương đương `null`.
10. **Nhà cung cấp/phiên bản:** đối chiếu API/runtime và bytecode library với Java target (ví dụ ASM và class file version) thay vì suy đoán mọi JVM đồng nhất.

## 11. Sai lầm thường gặp và đáp án

| Nhận định sai | Cách hiểu đúng |
| --- | --- |
| “`byte[]` mutable nên sửa được tại chỗ” | Java cho phép về ngôn ngữ, nhưng **hợp đồng `ClassFileTransformer` cấm** |
| “`byte[] copy = classfileBuffer` là copy” | Đó là **alias** cùng object; dùng `clone`/`Arrays.copyOf` để sao chép thật |
| “`ByteBuffer.wrap` tách dữ liệu” | Nó dùng chung backing array; `put` vẫn sửa mảng gốc |
| “Trả `null` sau khi sửa đầu vào là đủ” | `null` không hợp thức hóa mutation; phải **không hề ghi vào input** |
| “Cứ copy rồi thay byte offset tùy ý” | Không sửa input là điều kiện cần; output còn phải là class file hợp lệ |
| “Trả chính `classfileBuffer` là cách tối ưu” | Nếu không đổi hãy trả `null`; nếu biến đổi hãy sinh mảng mới |
| “`javap` trên tệp .class luôn thấy agent runtime” | Tool đọc bytes nguồn được chỉ định; agent có thể chỉ biến đổi trong bộ nhớ |
| “Ngoại lệ từ transformer làm JVM dừng luôn” | Javadoc mô tả JVM vẫn thử các transformer/định nghĩa tiếp; cần xử lý lỗi riêng |
| “Retransform luôn bắt đầu từ output trước đó” | JVM có quy tắc tái áp dụng/reuse các transformer; không được suy đoán buffer identity |
| “Một tên lớp tương ứng một bộ bytes” | Các class loaders khác nhau có thể định nghĩa cùng binary name |

## 12. Tự kiểm tra

1. **Đoạn code `byte[] local = classfileBuffer; local[0] = 1;` có sửa input không?** Có. Hai biến tham chiếu cùng mảng.
2. **Muốn bỏ qua class `java/lang/String` mà không biến đổi, nên trả gì?** `null`, không clone tốn bộ nhớ.
3. **Có được sửa `classfileBuffer` rồi return một mảng mới khác không?** Không. Lệnh sửa input đã vi phạm hợp đồng, dù return object khác.
4. **`Arrays.copyOf` đã đủ để tạo output bytecode hợp lệ chưa?** Chưa. Nó chỉ tạo mảng độc lập; việc sửa class file phải tuân thủ class format và verifier.
5. **Transformer B nhận input là output của A. B có được sửa trực tiếp mảng đó không?** Không. Đó là `classfileBuffer` của B, vẫn phải read-only.
6. **`transform` ném lỗi thì JVM luôn chặn class loading?** Không; theo Javadoc, JVM vẫn thử tiếp các transformers và quá trình định nghĩa.
7. **Làm sao biết một transformer có sửa input trong lần chạy lab?** Snapshot bằng `Arrays.copyOf` trước callback logic, sau đó so `Arrays.equals`; đây là phép kiểm tra cục bộ và không thay thế kiểm tra mọi đường chạy.
8. **Vì sao chương trình ví dụ in `message=hello` cả trước và sau khi dùng agent?** Bytecode chèn thêm log nhưng giữ nguyên chuỗi trả về; ngữ nghĩa chính của method vẫn giữ nguyên.
9. **Tại sao cần kiểm tra cả `output != classfileBuffer` và `Arrays.equals(before, classfileBuffer)`?** Điều thứ nhất kiểm tra mảng trả về khác object; điều thứ hai kiểm tra **input không bị sửa nội dung**.
10. **Sau `retransformClasses`, có thể dùng tham chiếu cũ tới `classfileBuffer` để ghi tiếp không?** Không. Không sở hữu quyền ghi ở bất kỳ lần callback nào; giữ tham chiếu và ghi async cũng sai.

## 13. Tài liệu chính thức

- Oracle JDK 17, **`ClassFileTransformer` API** (quy tắc không sửa input, trả `null`/mảng mới, chain/retransform/error semantics): https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html
- Oracle JDK 25, **`ClassFileTransformer` API** (đối chiếu hợp đồng các JDK mới): https://docs.oracle.com/en/java/javase/25/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html
- Oracle JDK 17, **`Instrumentation` API** (đăng ký transformer, redefine/retransform, capabilities): https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html
- Oracle JDK 17, **`java.lang.instrument` agent package** (`premain`, `agentmain`, manifest): https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/package-summary.html
- Java Virtual Machine Specification 17, **`ClassFile` format và `Code` attribute**: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html
- ASM JavaDoc, **`ClassReader` / `ClassWriter` / `MethodVisitor`**: https://asm.ow2.io/javadoc/

Cốt lõi của hợp đồng: **đầu vào thuộc pipeline/JVM, transformer chỉ được đọc; kết quả sửa đổi phải là một class file mới tách biệt; không cần sửa thì trả `null`**. Quy tắc này giúp các transformer có thể kết hợp và kiểm tra được mà không dựa vào mutation ngầm.
