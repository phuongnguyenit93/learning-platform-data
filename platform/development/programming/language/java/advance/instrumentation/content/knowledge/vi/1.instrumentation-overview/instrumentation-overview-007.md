# Ranh giới giữa API đăng ký biến đổi và công cụ thực sự đọc, sửa bytecode

Trong Java instrumentation, **đăng ký một transformer** và **biến đổi bytecode** là hai công việc khác nhau. `java.lang.instrument` cung cấp điểm nối với JVM để nhận các byte của lớp ở thời điểm thích hợp; thư viện như ASM, Byte Buddy hoặc Javassist cung cấp cơ chế phân tích và tạo bytecode mới. Một transformer có thể được gọi thành công nhưng chương trình vẫn chạy hệt như cũ nếu nó không trả về một bản class file đã được sửa.

Bài học thuộc chủ đề **Bức tranh instrumentation**, tập trung làm rõ ai đăng ký, ai đọc/sửa, ai áp dụng kết quả và cách kiểm chứng một phép biến đổi thực sự diễn ra.

## 1. Phân biệt bốn vai trò

| Thành phần | Chịu trách nhiệm | Không tự động làm gì? |
|---|---|---|
| Java agent (`premain` hoặc `agentmain`) | Là điểm vào của mã instrumentation; nhận đối tượng `Instrumentation` từ JVM | Không tự biết lớp/method nào cần sửa |
| `Instrumentation` | Đăng ký/gỡ `ClassFileTransformer`, yêu cầu retransform/redefine khi được hỗ trợ, kiểm tra một số khả năng của JVM | Không cung cấp trình phân tích/sửa cấu trúc bytecode như ASM |
| `ClassFileTransformer` | Nhận tên lớp, class loader, mảng byte class file; quyết định giữ nguyên hay trả về byte mới | Chỉ triển khai callback không đồng nghĩa đã thay đổi bytecode |
| ASM / Byte Buddy / Javassist | Đọc, mô hình hóa và/hoặc sinh class file, sửa instruction/method theo quy tắc do lập trình viên đặt ra | Không tự khiến JVM thay thế một lớp đang chạy chỉ vì đã tạo được mảng byte |
| JVM | Gọi transformer theo cơ chế được hỗ trợ, sử dụng bytes sau biến đổi và kiểm tra tính hợp lệ trước khi định nghĩa/cập nhật lớp | Không tự suy ra ý định của công cụ bytecode |

Lưu ý: bảng nói về **vai trò**, không phải quy định phải dùng riêng từng thư viện. Byte Buddy có thể bao bọc cả bước cấu hình/đăng ký transformer lẫn bước sinh bytecode; ASM có thể được dùng trực tiếp trong một `ClassFileTransformer`, hoặc dùng offline trong một công cụ build.

**Hình dung luồng khi một lớp sắp được định nghĩa:**

```text
java -javaagent:agent.jar
       |
       v
JVM gọi premain(..., Instrumentation)
       |
       v
agent gọi instrumentation.addTransformer(...)
       |
       v
JVM chuẩn bị định nghĩa demo.Greeter
       |
       v
ClassFileTransformer.transform(..., classfileBuffer)
       |
       +-- không sửa / không áp dụng? --> trả null
       |
       +-- muốn sửa? --> ASM đọc byte[] --> ASM tạo byte[] mới --> trả byte[] mới
       |
       v
JVM tiếp tục chuỗi transformer, kiểm tra và định nghĩa class
       |
       v
Ứng dụng thực thi phiên bản bytecode đã được chấp nhận
```

`classfileBuffer` là dữ liệu class file dạng byte, **không phải source `.java`** và cũng không phải `Class<?>` có thể trực tiếp sửa nội dung method. Java Reflection xem metadata và gọi thành viên có sẵn; nó không cung cấp API để thay instruction trong thân phương thức.

## 2. Chính xác `addTransformer` làm gì?

```java
instrumentation.addTransformer(transformer);
```

Lệnh trên **đăng ký** đối tượng `transformer` với JVM, tương đương `addTransformer(transformer, false)`. Sau khi đăng ký, các lần định nghĩa lớp phù hợp trong tương lai có thể kích hoạt callback. `addTransformer` tự nó không:

1. Đọc và phân tích toàn bộ classpath.
2. Thay đổi một method bất kỳ.
3. Tự gọi callback cho tất cả lớp đã được load từ trước.
4. Bảo đảm mọi lớp đều có thể bị sửa.

Callback truyền thống, vẫn sử dụng được trên Java 17+, có dạng:

```java
byte[] transform(
    ClassLoader loader,
    String className,
    Class<?> classBeingRedefined,
    ProtectionDomain protectionDomain,
    byte[] classfileBuffer
)
```

Ý nghĩa những đối số thường cần quan tâm:

- `className`: tên nội bộ, ví dụ `demo/Greeter` (dấu `/`, không phải `demo.Greeter`); có trường hợp giá trị là `null`.
- `loader`: class loader đang định nghĩa lớp, có thể là `null` với bootstrap loader. Cùng tên lớp nhưng khác class loader có thể là các lớp runtime khác nhau.
- `classBeingRedefined`: thường là `null` trong lúc load mới; có thể trỏ đến lớp hiện hữu trong quá trình redefine/retransform.
- `protectionDomain`: thông tin security domain gắn với lớp, hữu ích khi cần lọc.
- `classfileBuffer`: bytes đầu vào cho bước này trong chuỗi transformer.

Từ Java 9, interface còn có overload nhận thêm `Module` ở đầu. Phương thức overload mới mặc định chuyển tiếp sang phiên bản năm đối số, nên ví dụ ở dưới dùng chữ ký năm đối số để dễ theo dõi.

**Hợp đồng kết quả:**

```java
return null;             // Không biến đổi: JVM tiếp tục dùng bytes trước bước này
return transformedBytes; // Đề nghị JVM dùng bytes mới cho phần tiếp theo của pipeline
```

Một callback chỉ `println` và `return null` là **agent quan sát**, chưa phải agent viết lại bytecode. Trả một bản sao y hệt đầu vào về mặt ngữ nghĩa cũng không tạo ra thay đổi hành vi. Không sửa trực tiếp mảng `classfileBuffer`; nếu cần biến đổi, tạo mảng đầu ra riêng.

## 3. Công cụ bytecode làm phần nào?

Với ASM, ba vai trò thường gặp là:

- `ClassReader`: giải mã cấu trúc class file đầu vào.
- `ClassVisitor` / `MethodVisitor`: duyệt và điều chỉnh class, method, instruction.
- `ClassWriter`: sinh ra mảng byte class file mới để callback trả lại cho JVM.

Ví dụ về ý tưởng:

```java
ClassReader reader = new ClassReader(classfileBuffer);
ClassWriter writer = new ClassWriter(reader, 0);
reader.accept(myClassVisitor, 0);
byte[] rewrittenClassFile = writer.toByteArray();
return rewrittenClassFile;
```

Đoạn trên **chưa độc lập chạy được** vì `myClassVisitor` phải được khai báo và mô tả rõ phép biến đổi. Phần tiếp theo cung cấp một chương trình đầy đủ làm việc đó.

Byte Buddy thường cho API biểu đạt ý định ở mức cao hơn, như chặn lời gọi method hoặc thêm advice; ASM cho quyền kiểm soát gần instruction/JVM descriptor hơn. Javassist thường thuận tiện cho chỉnh sửa ở mức class/method. Dù chọn thư viện nào, vẫn phải bảo toàn cấu trúc class file hợp lệ, kiểu dữ liệu trên operand stack và stack-map frames khi thay đổi control flow.

## 4. Ví dụ Java 17+: đăng ký callback và thực sự đổi một instruction

Ta xây dựng **cùng một agent** có hai chế độ:

- `observe`: nhận callback, in log, `return null` — ứng dụng giữ nguyên.
- `rewrite`: dùng ASM thay hằng chuỗi trong method `greet()`, trả bytes mới — ứng dụng đổi kết quả.

Cấu trúc dự án Maven:

```text
agent-boundary-demo/
├── pom.xml
└── src/main/java/demo/
    ├── BoundaryAgent.java
    ├── Greeter.java
    └── Main.java
```

### 4.1. Ứng dụng mục tiêu

**`src/main/java/demo/Greeter.java`**

```java
package demo;

public final class Greeter {
    public String greet() {
        return "Hello";
    }
}
```

**`src/main/java/demo/Main.java`**

```java
package demo;

public final class Main {
    public static void main(String[] args) {
        System.out.println(new Greeter().greet());
    }
}
```

Khi không có agent, stdout của ứng dụng là:

```text
Hello
```

### 4.2. Agent đăng ký transformer và gọi ASM chỉ ở chế độ `rewrite`

**`src/main/java/demo/BoundaryAgent.java`**

```java
package demo;

import java.lang.instrument.ClassFileTransformer;
import java.lang.instrument.Instrumentation;
import java.security.ProtectionDomain;

import org.objectweb.asm.ClassReader;
import org.objectweb.asm.ClassVisitor;
import org.objectweb.asm.ClassWriter;
import org.objectweb.asm.MethodVisitor;
import org.objectweb.asm.Opcodes;

public final class BoundaryAgent {
    private BoundaryAgent() {
    }

    public static void premain(String agentArgs, Instrumentation instrumentation) {
        boolean rewrite = "rewrite".equals(agentArgs);

        // Bước 1: đăng ký callback với JVM.
        instrumentation.addTransformer(new ClassFileTransformer() {
            @Override
            public byte[] transform(
                    ClassLoader loader,
                    String className,
                    Class<?> classBeingRedefined,
                    ProtectionDomain protectionDomain,
                    byte[] classfileBuffer) {

                // Chỉ đụng lớp bài học; tránh instrument mọi lớp của JVM.
                if (!"demo/Greeter".equals(className)) {
                    return null;
                }

                System.out.println("[agent] callback: " + className);

                // Bước 2a: callback chạy nhưng không hề sửa bytecode.
                if (!rewrite) {
                    return null;
                }

                // Bước 2b: ASM đọc và viết lại class file.
                ClassReader reader = new ClassReader(classfileBuffer);
                ClassWriter writer = new ClassWriter(reader, 0);
                boolean[] changed = {false};

                ClassVisitor visitor = new ClassVisitor(Opcodes.ASM9, writer) {
                    @Override
                    public MethodVisitor visitMethod(
                            int access,
                            String name,
                            String descriptor,
                            String signature,
                            String[] exceptions) {

                        MethodVisitor delegate = super.visitMethod(
                                access, name, descriptor, signature, exceptions);

                        // Chỉ thay instruction trong String greet().
                        if (!"greet".equals(name)
                                || !"()Ljava/lang/String;".equals(descriptor)) {
                            return delegate;
                        }

                        return new MethodVisitor(Opcodes.ASM9, delegate) {
                            @Override
                            public void visitLdcInsn(Object constant) {
                                if ("Hello".equals(constant)) {
                                    changed[0] = true;
                                    super.visitLdcInsn("Hello instrumented");
                                } else {
                                    super.visitLdcInsn(constant);
                                }
                            }
                        };
                    }
                };

                reader.accept(visitor, 0);
                if (!changed[0]) {
                    return null;
                }

                System.out.println("[agent] ASM changed LDC in greet()");
                return writer.toByteArray();
            }
        });
    }
}
```

**Giải thích điểm ranh giới:**

1. `premain` được JVM gọi nhờ manifest `Premain-Class`; nó nhận `Instrumentation`.
2. `addTransformer(...)` chỉ **đăng ký**; lúc này code chưa đọc nội dung `Greeter`.
3. Khi `Greeter` được định nghĩa, JVM gọi `transform` với bytes của lớp.
4. Ở `observe`, việc in log chứng minh callback hoạt động, còn `return null` chứng minh **không có bytes thay thế**.
5. Ở `rewrite`, `ClassReader` tìm đến method `greet()` có descriptor `()Ljava/lang/String;`; `MethodVisitor` thay giá trị `LDC` từ `"Hello"` thành `"Hello instrumented"`.
6. `ClassWriter` sinh class file mới; `return writer.toByteArray()` đưa nó trở lại pipeline của JVM.

Ví dụ cố ý chỉ đổi **một hằng chuỗi**, không thêm method, không thay control flow, không thay kích thước operand stack hoặc stack-map frames. Vì vậy dùng `ClassWriter(reader, 0)` là phù hợp cho phép biến đổi nhỏ này. Với việc thêm nhánh, biến đổi stack hoặc exception handler, cần tính lại stack/maxs/frames đúng cách (ví dụ dùng các chế độ tính toán của ASM khi thích hợp), rồi kiểm tra bytecode được tạo.

### 4.3. Đóng gói JAR có manifest và thư viện ASM

**`pom.xml`**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>agent-boundary-demo</artifactId>
    <version>1.0.0</version>

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
                        <goals><goal>shade</goal></goals>
                        <configuration>
                            <transformers>
                                <transformer implementation="org.apache.maven.plugins.shade.resource.ManifestResourceTransformer">
                                    <manifestEntries>
                                        <Premain-Class>demo.BoundaryAgent</Premain-Class>
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

Ta đóng gói ASM cùng agent bằng Shade Plugin: nếu JAR chỉ chứa `BoundaryAgent.class` mà không có ASM trên đường nạp class của agent, JVM có thể gặp `NoClassDefFoundError` khi agent cần dùng ASM. `Premain-Class` cho JVM biết phương thức khởi động agent; nó **không** có nghĩa là JVM tự biết cách viết lại method.

### 4.4. Chạy và đối chiếu kết quả

Từ thư mục `agent-boundary-demo`, dùng JDK 17+ và Maven:

```bash
mvn -q -DskipTests package

java -cp target/agent-boundary-demo-1.0.0.jar demo.Main

java -javaagent:target/agent-boundary-demo-1.0.0.jar=observe \
     -cp target/agent-boundary-demo-1.0.0.jar demo.Main

java -javaagent:target/agent-boundary-demo-1.0.0.jar=rewrite \
     -cp target/agent-boundary-demo-1.0.0.jar demo.Main
```

Dấu `\` ở cuối dòng là cách nối lệnh trong shell Bash; trên PowerShell/cmd, viết mỗi lệnh `java` trên một dòng.

**Stdout dự kiến của từng lệnh `java` (không tính thông báo build của Maven):**

Không agent:

```text
Hello
```

Chế độ `observe`:

```text
[agent] callback: demo/Greeter
Hello
```

Chế độ `rewrite`:

```text
[agent] callback: demo/Greeter
[agent] ASM changed LDC in greet()
Hello instrumented
```

Kết quả quan trọng nhất: **cả `observe` và `rewrite` đều nhận callback; chỉ `rewrite` thay đổi kết quả của `greet()`**. Đây là phép kiểm chứng trực tiếp ranh giới giữa *đã đăng ký/được gọi* và *đã chỉnh bytes được JVM sử dụng*.

Có thể xem bytecode gốc bằng:

```bash
javap -c -p -cp target/agent-boundary-demo-1.0.0.jar demo.Greeter
```

Lệnh này đọc class trên **đĩa**, nên vẫn thấy hằng `"Hello"` ban đầu. Agent trong ví dụ chỉ biến đổi định nghĩa **trong JVM đang chạy**, không tự ghi đè `.class` trong JAR. Điều đó giúp phân biệt *runtime transformation* với *offline bytecode rewriting*.

## 5. Những thời điểm biến đổi dễ bị nhầm

### 5.1. Nạp mới: load-time transformation

Agent được khởi động với `-javaagent`, đăng ký transformer trong `premain`, và lớp được định nghĩa **sau khi đăng ký** sẽ đi qua callback thích hợp. Đây là cơ chế của ví dụ.

Nếu một class đã được định nghĩa trước khi đăng ký, chỉ gọi `addTransformer` sẽ không tự quay lại chạy callback cho lớp đó.

### 5.2. Retransform: chạy lại pipeline cho class đã load

Nếu JVM hỗ trợ, agent JAR khai báo khả năng thích hợp (`Can-Retransform-Classes: true`), transformer được đăng ký với `addTransformer(transformer, true)`, và lớp cụ thể có thể sửa được, thì `instrumentation.retransformClasses(Target.class)` yêu cầu JVM chạy lại quá trình biến đổi.

Trước khi dùng, cần kiểm tra:

```java
if (instrumentation.isRetransformClassesSupported()
        && instrumentation.isModifiableClass(Target.class)) {
    instrumentation.retransformClasses(Target.class);
}
```

`Target` trong đoạn này chỉ là ký hiệu cho một lớp đã tồn tại, **không phải mã độc lập chạy được**. Phương thức cũng có thể ném exception, ví dụ `UnmodifiableClassException`, nên code thật phải xử lý.

Điểm tinh tế: transformer đã đăng ký với `canRetransform=false` **không được gọi lại** khi retransform, nhưng kết quả biến đổi trước đó của nó được JVM tái áp dụng theo hợp đồng API. Transformer có `canRetransform=true` mới nhận callback trong lần retransform. Không thể suy từ việc đã đăng ký rằng callback nhất định sẽ chạy thêm lần nữa.

### 5.3. Redefine: cung cấp định nghĩa mới

`instrumentation.redefineClasses(new ClassDefinition(Target.class, bytes))` nhận **class file bytes đã được chuẩn bị**. Chúng có thể do ASM/Byte Buddy hoặc công cụ khác tạo. Đây là một con đường khác để yêu cầu JVM cập nhật lớp hiện hữu; nó cần `isRedefineClassesSupported()` và lớp có thể sửa, đồng thời phải tuân theo các giới hạn JVM về thay đổi cấu trúc class.

Không đồng nhất ba điều sau:

| Thao tác | Bản chất |
|---|---|
| `addTransformer(...)` | Đăng ký một callback cho các sự kiện phù hợp |
| `retransformClasses(...)` | Yêu cầu JVM chạy lại pipeline transform với lớp đã nạp |
| `redefineClasses(...)` | Yêu cầu JVM sử dụng một định nghĩa class mới được cung cấp |

Retransform và redefine không phải cơ chế để thoải mái thêm/xóa field, đổi chữ ký method hoặc thay hierarchy của lớp đang chạy. Các loại thay đổi được hỗ trợ tùy khả năng JVM, phải đối chiếu tài liệu và thử trên runtime mục tiêu.

### 5.4. Agent tải động và module system

Java còn có `agentmain` cho agent được tải sau khi JVM đã khởi động; khả năng attach/load động phụ thuộc JDK, cấu hình và chính sách runtime. Không coi nó luôn khả dụng như `-javaagent` lúc khởi động. Với hệ module (Java 9+), API `java.lang.instrument` cung cấp overload `transform(Module, ...)`; module access và class-loader visibility có thể ảnh hưởng code agent và thư viện phụ thuộc. Mọi thay đổi quyền đọc/mở module phải được quyết định riêng; `addTransformer` không tự cấp quyền truy cập tùy ý.

## 6. Ai quyết định một lần biến đổi thành công?

Transformer thường nhận `byte[]` và trả `byte[]` khác hoặc `null`, nhưng **JVM mới là bên chấp nhận và nạp định nghĩa lớp**. Đổi bytes không có nghĩa là đổi được mọi thứ.

Một class file có thể bị từ chối nếu:

- hỏng constant pool, opcode hoặc định dạng class file;
- bytecode vi phạm quy tắc kiểm tra kiểu, operand stack, stack-map frame;
- dùng class-file version mà runtime không hỗ trợ;
- biến đổi class đã load theo cách JVM không hỗ trợ;
- xung đột với transformer khác trong pipeline.

Nhiều transformer có thể chạy nối tiếp, nên một transformer có thể nhận bytes đã qua transformer trước đó. Không giả định đầu vào luôn giống từng byte với file `.class` nằm trên đĩa. Nếu tự viết transformer, nên thiết kế để chạy lặp an toàn, lọc tên lớp, tránh biến đổi thư viện của chính agent và giảm side effect trong callback.

**Chẩn đoán theo từng lớp trách nhiệm:**

1. Không thấy callback: kiểm tra manifest, `-javaagent`, thời điểm đăng ký, tên nội bộ và class loader.
2. Thấy callback nhưng hành vi không đổi: kiểm tra có thật sự đi vào nhánh sửa, có tạo bytes khác và có `return` đúng mảng mới không.
3. Có bytes mới nhưng lỗi load/verify: kiểm tra class-file structure, instruction, stack/frames và giới hạn retransform/redefine.
4. Có thay đổi nhưng sai lớp/method: kiểm tra `className`, descriptor (ví dụ `()Ljava/lang/String;`), overload và class loader.
5. Chạy được lần đầu nhưng lỗi khi retransform: kiểm tra khả năng của JVM/manifest, `canRetransform`, và tính ổn định khi chạy lại.

Dùng `java -Xverify:all ...` khi cần chủ động tăng kiểm tra bytecode trong môi trường thử nghiệm. Với biến đổi phức tạp, nên bổ sung kiểm tra ASM như `CheckClassAdapter` (cần dependency phù hợp) và các bài test xác nhận cả kết quả hành vi lẫn class loading. Log `"transform called"` **không đủ** làm bằng chứng method đã bị sửa.

## 7. Những hiểu lầm cần loại bỏ

- **“Đã gọi `addTransformer`, tức là đã instrument ứng dụng.”** Sai: mới đăng ký; callback có thể chưa chạy hoặc luôn trả `null`.
- **“`ClassFileTransformer` tự sửa bytecode.”** Sai: đây là interface/hợp đồng callback; logic sửa phải do code của bạn hoặc thư viện bytecode thực thi.
- **“ASM là một phần của `Instrumentation`.”** Sai: ASM là thư viện riêng; ví dụ phải đưa nó vào dependency và classpath/JAR của agent.
- **“Có ASM là tự sửa được code đang chạy.”** Sai: ASM sinh bytes; cần bước nạp/redefine/retransform phù hợp để JVM sử dụng bytes đó.
- **“`return null` là lỗi.”** Sai: đây là cách hợp lệ, phổ biến để nói “không thay đổi lớp này”.
- **“Mọi class đã load sẽ được sửa khi thêm transformer.”** Sai: phải chủ động xét retransform/redefine nếu được hỗ trợ.
- **“Mở JAR sau chạy sẽ thấy method đã đổi.”** Sai với ví dụ runtime: file trên đĩa không bị ghi đè.
- **“Chỉ cần thay chuỗi byte thô trong `.class`.”** Nguy hiểm: constant pool, độ dài, instruction và xác minh của JVM có quy tắc riêng; dùng công cụ class-file-aware như ASM.

## 8. Chọn công cụ theo nhu cầu

| Nhu cầu | Cách tiếp cận phù hợp |
|---|---|
| Chỉ quan sát lớp nào được load | Java agent + `ClassFileTransformer` lọc và `return null` |
| Sửa một instruction/descriptor cụ thể | Agent + ASM để kiểm soát bytecode chi tiết |
| Thêm advice/interceptor vào method với API mức cao | Byte Buddy với cơ chế agent/transformer phù hợp |
| Tạo/sửa `.class` trước khi đóng JAR, không có JVM đang chạy | ASM/Byte Buddy/Javassist ở build time; không nhất thiết cần Java agent |
| Đổi class đã được load | Kiểm tra năng lực JVM; chọn retransform hoặc redefine trong giới hạn được hỗ trợ |
| Kiểm chứng đã biến đổi thật | Quan sát hành vi/bytes đầu ra, kiểm tra verifier và đối chiếu với callback log |

## 9. Tự kiểm tra kiến thức

1. Transformer in tên `demo/Greeter` rồi trả `null`. Agent đã thực hiện công việc gì và chưa làm gì?  
   **Đáp án:** đã đăng ký/quan sát sự kiện định nghĩa class; chưa cung cấp bytecode thay thế.

2. ASM tạo ra bytes hợp lệ nhưng code chỉ gọi `reader.accept(...)` rồi `return null`. JVM có dùng class mới không?  
   **Đáp án:** không; kết quả tạo bởi ASM chưa được đưa về pipeline dưới dạng `return writer.toByteArray()`.

3. Vì sao `javap` đọc JAR vẫn hiển thị `"Hello"` sau khi bản chạy `rewrite` in `"Hello instrumented"`?  
   **Đáp án:** phép transform xảy ra trong JVM tại lúc định nghĩa class; file gốc trên đĩa không bị thay.

4. Muốn tác động class đã load, chỉ gọi `addTransformer` có đủ không?  
   **Đáp án:** không; cần con đường cập nhật lớp phù hợp, kiểm tra hỗ trợ và quyền sửa lớp, rồi yêu cầu JVM thực hiện.

5. Byte Buddy và `Instrumentation` có thay thế cho nhau hoàn toàn không?  
   **Đáp án:** không. Một bên cung cấp công cụ/abstraction để định nghĩa biến đổi; bên còn lại là API JVM cho đăng ký và quản lý quá trình instrumentation. Một giải pháp có thể phối hợp cả hai.

**Điểm cần nhớ:** `Instrumentation` và `ClassFileTransformer` tạo **đường đi và hợp đồng nhận/trả class bytes**; ASM/Byte Buddy/Javassist (hoặc code bytecode tương đương) tạo **nội dung thay đổi**; JVM quyết định **áp dụng bytes hợp lệ**. Chỉ khi cả ba phần phối hợp đúng, chương trình mới có hành vi đã được instrument.

## Tài liệu tham khảo

- Java 17 — [`Instrumentation`](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html)
- Java 17 — [`ClassFileTransformer`](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html)
- Java 17 — [Package `java.lang.instrument`](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/package-summary.html)
- ASM — [Trang dự án](https://asm.ow2.io/) và [artifact Maven Central](https://central.sonatype.com/artifact/org.ow2.asm/asm/9.7.1)
